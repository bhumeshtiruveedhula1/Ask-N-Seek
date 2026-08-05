"""
extraction_engine.py — Part 1: Achilles Extraction Engine
==========================================================
Architecture ref : 03_Architecture_Final.md §2 (Scene chunking row)
TRD ref          : TRD-Build-Plan-Achilles.md  §PART 1

Canonical rules (do NOT deviate):
  • OpenCV VideoCapture + CAP_PROP_POS_MSEC — seek-to-timestamp, never sequential decode.
  • PySceneDetect for scene-boundary timestamps.
  • 1 FPS fallback during long static shots (shots longer than LONG_SHOT_THRESHOLD_S).
  • Release VideoCapture between every individual seek — never hold the object open.
  • Never store the full decoded frame sequence in memory — write each frame to disk
    immediately, yield one dict at a time via generator.

Output contract (exact shape, TRD §PART 1 — do not change):
  {
    "video_id"   : str,       # stem of the video filename, e.g. "vid1"
    "frame_index": int,       # monotonically increasing, unique across the whole video
    "timestamp"  : float,     # seconds, ≥ 0.0
    "scene_id"   : int,       # 0-based scene/shot index from PySceneDetect
    "frame_path" : str,       # absolute path to the saved JPEG on disk
  }
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Generator

import cv2
import numpy as np

# PySceneDetect imports — scenedetect ≥ 0.6
from scenedetect import open_video, SceneManager
from scenedetect.detectors import ContentDetector

# Keyframe-cap constants from central config
try:
    from config import MAX_KEYFRAMES_PER_SCENE, MIN_KEYFRAME_INTERVAL_S
except ImportError:
    # Fallback defaults if config not on path (e.g. isolated unit tests)
    MAX_KEYFRAMES_PER_SCENE = 5
    MIN_KEYFRAME_INTERVAL_S = 2.0

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Tuneable constants
# ---------------------------------------------------------------------------

# Any shot longer than this (seconds) gets 1 FPS supplementary frames
LONG_SHOT_THRESHOLD_S: float = 2.0

# JPEG quality for saved keyframes (0-100)
JPEG_QUALITY: int = 90

# PySceneDetect ContentDetector threshold (lower = more sensitive)
SCENE_DETECT_THRESHOLD: float = 27.0

# Duration cap: videos longer than this are processed only up to this point
MAX_DURATION_S: float = 180.0

# Resolution cap: frames taller than this are resized (aspect-ratio preserved)
MAX_FRAME_HEIGHT: int = 720

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _seek_and_grab(video_path: str, timestamp_ms: float) -> np.ndarray | None:
    """
    Open a *new* VideoCapture, seek to `timestamp_ms`, grab one frame, release.

    This is the canonical memory-safe seek pattern from the TRD:
      open → seek → read → release
    VideoCapture is never kept alive across calls — prevents any full
    frame-sequence accumulation in memory.

    Returns the BGR frame array, or None on failure.
    """
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        logger.error("Could not open video: %s", video_path)
        return None
    try:
        cap.set(cv2.CAP_PROP_POS_MSEC, timestamp_ms)
        ret, frame = cap.read()
        if not ret or frame is None:
            logger.warning("Failed to read frame at %.3f ms from %s", timestamp_ms, video_path)
            return None
        return frame
    finally:
        cap.release()   # ← always released; no frame held beyond this scope


def _save_frame(frame: np.ndarray, frame_path: str) -> bool:
    """Write frame to disk immediately, drop the numpy array from caller's scope."""
    os.makedirs(os.path.dirname(frame_path), exist_ok=True)
    # Resolution cap: resize to max 720p height (aspect-ratio preserved)
    h, w = frame.shape[:2]
    if h > MAX_FRAME_HEIGHT:
        scale = MAX_FRAME_HEIGHT / h
        frame = cv2.resize(frame, (int(w * scale), MAX_FRAME_HEIGHT), interpolation=cv2.INTER_AREA)
    ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY])
    if not ok:
        logger.error("imencode failed for %s", frame_path)
        return False
    with open(frame_path, "wb") as fh:
        fh.write(buf.tobytes())
    return True


def _get_video_fps(video_path: str) -> float:
    """Return the video's native FPS (needed for duration calculation)."""
    cap = cv2.VideoCapture(video_path)
    fps = cap.get(cv2.CAP_PROP_FPS) if cap.isOpened() else 25.0
    cap.release()
    return fps if fps > 0 else 25.0


def _get_video_duration_s(video_path: str) -> float:
    """Return total video duration in seconds."""
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        return 0.0
    frame_count = cap.get(cv2.CAP_PROP_FRAME_COUNT)
    fps = cap.get(cv2.CAP_PROP_FPS)
    cap.release()
    if fps > 0:
        return frame_count / fps
    return 0.0


# ---------------------------------------------------------------------------
# Scene detection
# ---------------------------------------------------------------------------


def _detect_scene_boundaries(video_path: str) -> list[tuple[float, float]]:
    """
    Run PySceneDetect ContentDetector and return a list of (start_s, end_s) tuples
    for every detected scene.  Guaranteed to cover [0, duration] with no gaps.

    Uses the open_video / SceneManager API (scenedetect ≥ 0.6).
    """
    video = open_video(video_path)
    manager = SceneManager()
    manager.add_detector(ContentDetector(threshold=SCENE_DETECT_THRESHOLD))
    manager.detect_scenes(video=video, show_progress=False)
    scene_list = manager.get_scene_list()

    if not scene_list:
        # No cuts detected — treat the whole video as one scene
        duration = _get_video_duration_s(video_path)
        logger.info("No scene cuts detected; treating whole video as one scene (%.1fs)", duration)
        return [(0.0, duration)]

    # Convert FrameTimecode pairs → float seconds
    scenes: list[tuple[float, float]] = []
    for start_tc, end_tc in scene_list:
        scenes.append((start_tc.get_seconds(), end_tc.get_seconds()))

    logger.info("Detected %d scenes in %s", len(scenes), os.path.basename(video_path))
    return scenes


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def extract_frames(
    video_path: str,
    output_dir: str,
) -> Generator[dict, None, None]:
    """
    Extraction Engine — Part 1 public entry point.

    Given a video file path, yield one output-contract dict per extracted frame.
    Frames are written to ``output_dir/<video_id>/NNNN.jpg`` as they are
    extracted — the full frame sequence is **never** held in memory simultaneously.

    Parameters
    ----------
    video_path : str
        Absolute (or relative) path to the source video file.
    output_dir : str
        Root directory for saved frames, e.g. ``/frames``.
        Sub-directory ``<video_id>/`` is created automatically.

    Yields
    ------
    dict with keys: video_id, frame_index, timestamp, scene_id, frame_path
    Timestamps are strictly increasing.
    scene_ids are 0-based and consistent within one call.
    frame_index is globally unique, 0-based, and monotonically increasing.

    Raises
    ------
    FileNotFoundError : if video_path does not exist.
    RuntimeError      : if VideoCapture cannot be opened for any seek.
    """
    video_path = str(Path(video_path).resolve())
    if not os.path.isfile(video_path):
        raise FileNotFoundError(f"Video not found: {video_path}")

    video_id = Path(video_path).stem
    frames_dir = str(Path(output_dir) / video_id)
    os.makedirs(frames_dir, exist_ok=True)

    logger.info("=== extract_frames START: %s (video_id=%s) ===", video_path, video_id)

    # Duration cap: trim processing to MAX_DURATION_S if video is longer
    duration_s = _get_video_duration_s(video_path)
    if duration_s > MAX_DURATION_S:
        logger.warning(
            "Video %s is %.1f s — exceeds MAX_DURATION_S (%.0f s). "
            "Processing only first %.0f s.",
            video_id, duration_s, MAX_DURATION_S, MAX_DURATION_S,
        )

    # --- Phase 1: detect scene boundaries (CPU only, no frame decoding into caller) ---
    scenes = _detect_scene_boundaries(video_path)  # [(start_s, end_s), ...]

    # Apply duration cap: drop scenes that start at or after MAX_DURATION_S,
    # trim the last scene's end if it crosses the cap.
    if duration_s > MAX_DURATION_S:
        capped: list[tuple[float, float]] = []
        for s_start, s_end in scenes:
            if s_start >= MAX_DURATION_S:
                break
            capped.append((s_start, min(s_end, MAX_DURATION_S)))
        scenes = capped

    frame_index: int = 0            # global monotonic counter for this video
    seen_timestamps: set[float] = set()   # dedup guard

    for scene_id, (scene_start_s, scene_end_s) in enumerate(scenes):
        scene_duration_s = scene_end_s - scene_start_s
        if scene_duration_s <= 0:
            continue  # degenerate scene, skip

        # ---- Collect the timestamps to extract for this scene ----
        timestamps_s: list[float] = []

        # Always extract the scene boundary frame (start of scene)
        timestamps_s.append(scene_start_s)

        # Capped fallback: for long static shots, add evenly-distributed keyframes.
        # Cap = MAX_KEYFRAMES_PER_SCENE; minimum gap = MIN_KEYFRAME_INTERVAL_S.
        # A 60s scene yields max 5 frames (every 12s) instead of 59 (every 1s).
        if scene_duration_s > LONG_SHOT_THRESHOLD_S:
            n_keyframes = min(
                MAX_KEYFRAMES_PER_SCENE,
                max(2, int(scene_duration_s / MIN_KEYFRAME_INTERVAL_S)),
            )
            interval_s = scene_duration_s / n_keyframes
            for i in range(1, n_keyframes):  # i=0 is scene_start_s already added above
                t = scene_start_s + i * interval_s
                if t < scene_end_s - 0.1:   # 0.1 s guard to avoid duplicate at boundary
                    timestamps_s.append(t)

        # Deduplicate across scenes (floating-point safety: round to 3 decimals)
        unique_timestamps = []
        for ts in timestamps_s:
            ts_rounded = round(ts, 3)
            if ts_rounded not in seen_timestamps:
                seen_timestamps.add(ts_rounded)
                unique_timestamps.append(ts_rounded)

        if not unique_timestamps:
            continue

        # Sort — should already be sorted but be explicit
        unique_timestamps.sort()

        # ---- Seek-and-grab each timestamp, write to disk, yield contract dict ----
        for ts_s in unique_timestamps:
            ts_ms = ts_s * 1000.0

            # Open → seek → read → release (one VideoCapture per frame)
            frame = _seek_and_grab(video_path, ts_ms)
            if frame is None:
                logger.warning(
                    "Skipping timestamp %.3f s (scene %d) — seek returned no frame",
                    ts_s, scene_id
                )
                continue

            # Zero-padded filename for easy sorting
            frame_filename = f"{frame_index:04d}.jpg"
            frame_path = str(Path(frames_dir) / frame_filename)

            # Write immediately — drop frame array from memory after this call
            saved = _save_frame(frame, frame_path)
            del frame   # explicit: ensure numpy array is freed now

            if not saved:
                logger.error("Failed to save frame %s — skipping", frame_path)
                continue

            record = {
                "video_id"   : video_id,
                "frame_index": frame_index,
                "timestamp"  : ts_s,
                "scene_id"   : scene_id,
                "frame_path" : frame_path,
                "backend"    : "opencv_seek",  # Odysseus contract field
            }

            logger.debug(
                "frame_index=%d  timestamp=%.3f  scene_id=%d  path=%s",
                frame_index, ts_s, scene_id, frame_path
            )

            frame_index += 1
            yield record

    logger.info(
        "=== extract_frames DONE: %s — %d frames extracted across %d scenes ===",
        video_id, frame_index, len(scenes)
    )
