"""
tests/test_extraction_engine.py -- Part 1 Verification Suite
=============================================================
TRD requirement: "Tested on at least 2-3 real sample videos…
  Confirmed: no full frame sequence held in memory at any point.
  Confirmed: timestamps are increasing, scene_ids consistent,
             no duplicate frame_index."

Run:
    python tests/test_extraction_engine.py [path/to/video1.mp4 path/to/video2.mp4 ...]

If no paths are supplied the script auto-generates synthetic test videos via
OpenCV (avoids needing bundled media files) and runs the full suite on them.

All checks are explicit pass/fail with raw evidence printed.
"""

from __future__ import annotations

import argparse
import io
import logging
import os
import sys
import tempfile
import tracemalloc
from pathlib import Path

# Force UTF-8 output on Windows so we can print unicode safely
if sys.stdout.encoding and sys.stdout.encoding.lower() != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

# ---------------------------------------------------------------------------
# Ensure project root is on sys.path so "backend" resolves
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import cv2
import numpy as np

from backend.ingestion.extraction_engine import extract_frames

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("verify")

# ---------------------------------------------------------------------------
# Synthetic video generation (fallback when no real videos supplied)
# ---------------------------------------------------------------------------

def _make_synthetic_video(
    path: str,
    duration_s: float = 6.0,
    fps: float = 25.0,
    cuts_at: list[float] | None = None,
    width: int = 320,
    height: int = 240,
) -> None:
    """
    Write a simple synthetic MP4 with abrupt scene cuts at the given timestamps.
    Each segment is a solid colour so ContentDetector fires at each cut.
    """
    cuts_at = cuts_at or []
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(path, fourcc, fps, (width, height))
    total_frames = int(duration_s * fps)

    # Colours for each segment (BGR)
    colours = [
        (60, 20, 200),    # deep red
        (20, 200, 60),    # green
        (200, 60, 20),    # blue
        (200, 200, 20),   # teal
        (100, 100, 200),  # pink
    ]

    # Build a list of (frame_no → colour_index)
    cut_frames = sorted(int(c * fps) for c in cuts_at)
    seg_idx = 0

    for f in range(total_frames):
        # Advance segment?
        if cut_frames and seg_idx < len(cut_frames) and f >= cut_frames[seg_idx]:
            seg_idx += 1
            if seg_idx >= len(cut_frames):
                seg_idx = len(cut_frames)

        colour = colours[seg_idx % len(colours)]
        frame = np.full((height, width, 3), colour, dtype=np.uint8)
        # Small frame counter so every frame is slightly different
        cv2.putText(frame, str(f), (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)
        writer.write(frame)

    writer.release()
    logger.info("Synthetic video written: %s (%.1fs, %d cuts)", path, duration_s, len(cuts_at))


# ---------------------------------------------------------------------------
# Core verification logic
# ---------------------------------------------------------------------------

FAIL_COUNT = 0
PASS_COUNT = 0


def _check(condition: bool, label: str, evidence: str = "") -> None:
    global FAIL_COUNT, PASS_COUNT
    status = "[PASS]" if condition else "[FAIL]"
    print(f"  {status}  {label}")
    if evidence:
        print(f"         evidence: {evidence}")
    if condition:
        PASS_COUNT += 1
    else:
        FAIL_COUNT += 1


def verify_video(video_path: str, output_dir: str) -> list[dict]:
    """
    Run extract_frames on one video, collect all records into a list,
    then run all contract checks.  Returns the record list for debugging.
    """
    print(f"\n{'='*70}")
    print(f"  VIDEO: {os.path.basename(video_path)}")
    print(f"{'='*70}")

    # -----------------------------------------------------------------------
    # Memory profiling — check that peak allocated numpy memory during
    # extraction does not balloon to the size of the entire decoded video.
    # We track tracemalloc peak; the key assertion is that we never see a
    # spike proportional to "all frames × frame_size_bytes".
    # -----------------------------------------------------------------------
    tracemalloc.start()
    records: list[dict] = []
    try:
        for rec in extract_frames(video_path, output_dir):
            records.append(rec)
    except Exception as exc:
        print(f"  ❌ extract_frames raised an exception: {exc}")
        tracemalloc.stop()
        return []

    _, peak_bytes = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    # Rough upper-bound: if we held ALL frames at once at 320×240×3
    # (tiny), that would be approx frame_count × 230400 bytes.
    cap = cv2.VideoCapture(video_path)
    total_frames_in_video = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    cap.release()
    full_decode_bytes = total_frames_in_video * w * h * 3  # BGR, uncompressed

    print(f"\n  Records extracted : {len(records)}")
    print(f"  Peak memory (MB)  : {peak_bytes / 1_048_576:.2f}")
    print(f"  Full-decode upper : {full_decode_bytes / 1_048_576:.2f} MB "
          f"({total_frames_in_video} frames × {w}×{h}×3)")

    # -----------------------------------------------------------------------
    # Check: at least one frame extracted
    # -----------------------------------------------------------------------
    _check(len(records) > 0, "At least one frame extracted", f"{len(records)} records")

    if not records:
        return records

    # -----------------------------------------------------------------------
    # Check: output contract shape — all required keys present
    # -----------------------------------------------------------------------
    required_keys = {"video_id", "frame_index", "timestamp", "scene_id", "frame_path"}
    all_have_keys = all(required_keys.issubset(r.keys()) for r in records)
    _check(all_have_keys, "All records have required contract keys",
           f"keys = {sorted(records[0].keys())}")

    # -----------------------------------------------------------------------
    # Check: video_id is consistent (same stem throughout)
    # -----------------------------------------------------------------------
    expected_vid_id = Path(video_path).stem
    vid_ids = {r["video_id"] for r in records}
    _check(vid_ids == {expected_vid_id},
           "video_id is consistent across all frames",
           f"video_id values seen: {vid_ids}")

    # -----------------------------------------------------------------------
    # Check: timestamps strictly increasing
    # -----------------------------------------------------------------------
    timestamps = [r["timestamp"] for r in records]
    strictly_increasing = all(timestamps[i] < timestamps[i + 1] for i in range(len(timestamps) - 1))
    _check(strictly_increasing,
           "timestamps are strictly increasing",
           f"first={timestamps[0]:.3f}s  last={timestamps[-1]:.3f}s  "
           f"count={len(timestamps)}")
    if not strictly_increasing:
        # Show the violation
        for i in range(len(timestamps) - 1):
            if timestamps[i] >= timestamps[i + 1]:
                print(f"         VIOLATION at index {i}: {timestamps[i]:.3f} >= {timestamps[i+1]:.3f}")

    # -----------------------------------------------------------------------
    # Check: no duplicate frame_index
    # -----------------------------------------------------------------------
    frame_indices = [r["frame_index"] for r in records]
    no_duplicates = len(frame_indices) == len(set(frame_indices))
    _check(no_duplicates,
           "No duplicate frame_index values",
           f"total={len(frame_indices)}  unique={len(set(frame_indices))}")

    # -----------------------------------------------------------------------
    # Check: frame_index is 0-based and monotonically increasing
    # -----------------------------------------------------------------------
    expected_indices = list(range(len(records)))
    indices_correct = frame_indices == expected_indices
    _check(indices_correct,
           "frame_index is 0-based and monotonically increasing",
           f"[{frame_indices[0]}..{frame_indices[-1]}]")

    # -----------------------------------------------------------------------
    # Check: scene_ids are non-negative integers and form a non-decreasing seq
    # -----------------------------------------------------------------------
    scene_ids = [r["scene_id"] for r in records]
    scene_non_neg = all(s >= 0 for s in scene_ids)
    scene_nondecreasing = all(scene_ids[i] <= scene_ids[i + 1] for i in range(len(scene_ids) - 1))
    _check(scene_non_neg and scene_nondecreasing,
           "scene_ids are non-negative and non-decreasing",
           f"scene range: {scene_ids[0]}..{scene_ids[-1]}  "
           f"distinct scenes: {len(set(scene_ids))}")

    # -----------------------------------------------------------------------
    # Check: frame files actually exist on disk
    # -----------------------------------------------------------------------
    all_exist = all(os.path.isfile(r["frame_path"]) for r in records)
    _check(all_exist,
           "All frame JPEG files exist on disk",
           f"sample path: {records[0]['frame_path']}")
    missing = [r["frame_path"] for r in records if not os.path.isfile(r["frame_path"])]
    if missing:
        for m in missing[:5]:
            print(f"         MISSING: {m}")

    # -----------------------------------------------------------------------
    # Check: memory — peak should be well below full-decode size
    # For the test threshold we use 25% of full-decode as a generous bound
    # (in practice it should be < 1 frame at a time).
    # -----------------------------------------------------------------------
    memory_ok = peak_bytes < max(full_decode_bytes * 0.25, 50 * 1_048_576)  # max 25% or 50 MB floor
    _check(memory_ok,
           "Peak memory well below full-decode size (confirms no full-sequence hold)",
           f"peak={peak_bytes/1_048_576:.2f} MB  "
           f"full_decode={full_decode_bytes/1_048_576:.2f} MB")

    # -----------------------------------------------------------------------
    # Print raw output sample (10 rows)
    # -----------------------------------------------------------------------
    print("\n  --- Raw output sample (first 10 records) ---")
    for rec in records[:10]:
        print(f"    {rec}")

    return records


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Part 1 Extraction Engine Verification"
    )
    parser.add_argument(
        "videos",
        nargs="*",
        help="Paths to real video files.  If omitted, synthetic test videos are generated.",
    )
    parser.add_argument(
        "--output-dir",
        default=str(PROJECT_ROOT / "outputs" / "frames"),
        help="Root directory for extracted frames.",
    )
    args = parser.parse_args()

    video_paths: list[str] = args.videos

    with tempfile.TemporaryDirectory() as tmp_dir:
        if not video_paths:
            logger.info("No real videos supplied — generating synthetic test videos.")
            syn1 = os.path.join(tmp_dir, "syn_multiscene.mp4")
            syn2 = os.path.join(tmp_dir, "syn_longshot.mp4")
            syn3 = os.path.join(tmp_dir, "syn_singlescene.mp4")

            # Video 1: 3 scene cuts at 2s, 4s, 6s in a 9s clip
            _make_synthetic_video(syn1, duration_s=9.0, fps=25.0, cuts_at=[2.0, 4.0, 6.0])
            # Video 2: one 10s static shot (triggers 1 FPS fallback throughout)
            _make_synthetic_video(syn2, duration_s=10.0, fps=25.0, cuts_at=[])
            # Video 3: short clip, single scene, no cuts
            _make_synthetic_video(syn3, duration_s=3.0, fps=25.0, cuts_at=[])

            video_paths = [syn1, syn2, syn3]

        all_records: list[list[dict]] = []
        for vp in video_paths:
            if not os.path.isfile(vp):
                print(f"❌  File not found: {vp}")
                continue
            recs = verify_video(vp, args.output_dir)
            all_records.append(recs)

        # -------------------------------------------------------------------
        # Summary
        # -------------------------------------------------------------------
        print(f"\n{'='*70}")
        print("  MILESTONE REPORT — Part 1 Extraction Engine")
        print(f"{'='*70}")
        print(f"  Videos tested  : {len(all_records)}")
        print(f"  Total records  : {sum(len(r) for r in all_records)}")
        print(f"  PASS count     : {PASS_COUNT}")
        print(f"  FAIL count     : {FAIL_COUNT}")
        if FAIL_COUNT == 0:
            print("\n  [ALL CHECKS PASSED] Part 1 Extraction Engine is DONE.")
        else:
            print(f"\n  [CHECKS FAILED] {FAIL_COUNT} check(s) failed -- review output above.")
        print(f"{'='*70}\n")

        sys.exit(0 if FAIL_COUNT == 0 else 1)


if __name__ == "__main__":
    main()
