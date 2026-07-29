"""
orchestrate.py

Odysseus Part 1: Metadata & Orchestration Layer.

Orchestrates frame extraction, directory creation, frame image saving,
and metadata generation in JSON and CSV formats.

Integration note (Step 4.1 — 2026-07-29):
  Achilles's extract_frames(video_path, output_dir) is a GENERATOR that:
    - Writes each frame to disk itself (no save_frame_image call needed)
    - Yields one dict per frame: {video_id, frame_index, timestamp, scene_id,
      frame_path, backend}
    - Never materialises the full frame list in memory

  The reference/stub extract_frames(video_path) returns ExtractionResult
  (dataclass with .frames list and .backend str).

  This orchestrator detects which API is active and handles both:
    - If result is a generator/iterator → Achilles's real implementation
    - If result is ExtractionResult     → reference stub (backward-compat)
"""

import argparse
import csv
import inspect
import json
import os
import re
import sys
from typing import Any, List, Dict

from extraction.extraction import extract_frames


def sanitize_video_id(video_name: str) -> str:
    """Generate a clean, deterministic video_id from video filename."""
    base = os.path.splitext(os.path.basename(video_name))[0]
    sanitized = re.sub(r'[^a-zA-Z0-9_\-]', '_', base).strip('_')
    return sanitized if sanitized else "video_0"


def discover_videos(video_dir: str) -> List[str]:
    """Find all supported video files in the specified directory."""
    if not os.path.exists(video_dir):
        return []

    valid_extensions = {".mp4", ".avi", ".mov", ".mkv", ".webm"}
    videos = []
    for entry in sorted(os.listdir(video_dir)):
        ext = os.path.splitext(entry)[1].lower()
        if ext in valid_extensions:
            videos.append(os.path.join(video_dir, entry))
    return videos


def _is_generator_api(fn) -> bool:
    """
    Return True if extract_frames is a generator function (Achilles real API).
    Return False if it is a regular function returning ExtractionResult (stub).
    """
    return inspect.isgeneratorfunction(fn)


def orchestrate(video_dir: str = "videos", output_frames_dir: str = "frames", metadata_dir: str = "metadata") -> List[Dict[str, Any]]:
    """
    Main orchestration function.
    Iterates over videos, invokes extract_frames(), and produces
    metadata.json and metadata.csv.

    Handles two extract_frames APIs:
      - Achilles real: generator yielding dicts {video_id, frame_index,
                       timestamp, scene_id, frame_path, backend}
                       (frames written to disk by Achilles — no save needed)
      - Reference stub: returns ExtractionResult(frames=[FrameData,...], backend=str)
                       (frames held in memory, saved here via PIL)
    """
    print(f"[*] Discovering videos in folder: '{video_dir}'...")
    video_paths = discover_videos(video_dir)

    if not video_paths:
        print(f"[!] ERROR: No video files found in directory '{video_dir}'.")
        print(f"[!] Please place video files (.mp4, .avi, .mov, .mkv, .webm) into '{video_dir}' and rerun.")
        sys.exit(1)

    print(f"[*] Found {len(video_paths)} video file(s): {[os.path.basename(p) for p in video_paths]}")

    use_generator_api = _is_generator_api(extract_frames)
    if use_generator_api:
        print("[*] Extraction API: Achilles generator (lazy, memory-safe)")
    else:
        print("[*] Extraction API: reference stub (ExtractionResult)")

    all_metadata: List[Dict[str, Any]] = []

    for vpath in video_paths:
        video_id = sanitize_video_id(vpath)
        print(f"\n[*] Processing video '{vpath}' (video_id='{video_id}')...")

        try:
            if use_generator_api:
                # ── Achilles real API ────────────────────────────────────────
                # Frames are written to disk inside extract_frames; we just iterate
                # and collect the metadata dicts.
                frame_count = 0
                backend = "unknown"
                for record in extract_frames(vpath, output_frames_dir):
                    # record keys: video_id, frame_index, timestamp, scene_id,
                    #              frame_path, backend
                    meta_record = {
                        "video_id":    record["video_id"],
                        "frame_index": int(record["frame_index"]),
                        "timestamp":   float(record["timestamp"]),
                        "scene_id":    int(record["scene_id"]),
                        "frame_path":  record["frame_path"],
                    }
                    all_metadata.append(meta_record)
                    backend = record.get("backend", "opencv_seek")
                    frame_count += 1

                print(f"    - Extraction completed using backend '{backend}'. Extracted {frame_count} frame(s).")

            else:
                # ── Reference stub API ──────────────────────────────────────
                from PIL import Image as _PIL_Image

                def _save_frame_image(image_data: Any, target_path: str) -> None:
                    os.makedirs(os.path.dirname(target_path), exist_ok=True)
                    if isinstance(image_data, bytes):
                        with open(target_path, "wb") as f:
                            f.write(image_data)
                    elif hasattr(image_data, "save") and callable(getattr(image_data, "save")):
                        image_data.save(target_path)
                    elif hasattr(image_data, "shape") and hasattr(image_data, "dtype"):
                        img = _PIL_Image.fromarray(image_data)
                        img.save(target_path, "JPEG", quality=95)
                    else:
                        raise ValueError(f"Unsupported image data format: {type(image_data)}")

                result = extract_frames(vpath)
                print(f"    - Extraction completed using backend '{result.backend}'. Extracted {len(result.frames)} frame(s).")

                video_frame_dir = os.path.join(output_frames_dir, video_id)
                os.makedirs(video_frame_dir, exist_ok=True)

                for frame in result.frames:
                    rel_frame_path = f"{output_frames_dir}/{video_id}/{frame.frame_index}.jpg"
                    abs_frame_path = os.path.join(output_frames_dir, video_id, f"{frame.frame_index}.jpg")
                    _save_frame_image(frame.image, abs_frame_path)

                    record = {
                        "video_id":    video_id,
                        "frame_index": int(frame.frame_index),
                        "timestamp":   float(frame.timestamp),
                        "scene_id":    int(frame.scene_id),
                        "frame_path":  rel_frame_path,
                    }
                    all_metadata.append(record)

        except Exception as e:
            print(f"[!] ERROR: Extraction failed for video '{vpath}': {e}")
            raise e

    # Ensure metadata directory exists
    os.makedirs(metadata_dir, exist_ok=True)

    json_path = os.path.join(metadata_dir, "metadata.json")
    csv_path  = os.path.join(metadata_dir, "metadata.csv")

    print(f"\n[*] Writing metadata to '{json_path}'...")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(all_metadata, f, indent=2)

    print(f"[*] Writing metadata to '{csv_path}'...")
    fieldnames = ["video_id", "frame_index", "timestamp", "scene_id", "frame_path"]
    with open(csv_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(all_metadata)

    print(f"[+] Orchestration complete. Processed {len(all_metadata)} total frame record(s).")
    return all_metadata


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Odysseus Orchestration Layer")
    parser.add_argument("--video-dir",    type=str, default="videos",   help="Directory containing input videos")
    parser.add_argument("--frames-dir",   type=str, default="frames",   help="Output directory for saved frames")
    parser.add_argument("--metadata-dir", type=str, default="metadata", help="Output directory for metadata files")
    args = parser.parse_args()

    orchestrate(video_dir=args.video_dir, output_frames_dir=args.frames_dir, metadata_dir=args.metadata_dir)
