"""
orchestrate.py

Odysseus Part 1: Metadata & Orchestration Layer.

Orchestrates frame extraction, directory creation, frame image saving,
and metadata generation in JSON and CSV formats.
"""

import argparse
import csv
import json
import os
import re
import sys
from typing import Any, List, Dict

from PIL import Image

from extraction.extraction import extract_frames, ExtractionResult, FrameData


def sanitize_video_id(video_name: str) -> str:
    """Generate a clean, deterministic video_id from video filename."""
    base = os.path.splitext(os.path.basename(video_name))[0]
    sanitized = re.sub(r'[^a-zA-Z0-9_\-]', '_', base).strip('_')
    return sanitized if sanitized else "video_0"


def save_frame_image(image_data: Any, target_path: str) -> None:
    """
    Save frame image data to target JPG file without requiring OpenCV.
    Supports PIL Image objects, numpy arrays (RGB), raw bytes, or objects with save().
    """
    os.makedirs(os.path.dirname(target_path), exist_ok=True)

    if isinstance(image_data, bytes):
        with open(target_path, "wb") as f:
            f.write(image_data)
    elif hasattr(image_data, "save") and callable(getattr(image_data, "save")):
        image_data.save(target_path, "JPEG" if not target_path.lower().endswith(".jpg") else None)
    elif hasattr(image_data, "shape") and hasattr(image_data, "dtype"):
        # Numpy array assumption: RGB format
        img = Image.fromarray(image_data)
        img.save(target_path, "JPEG", quality=95)
    else:
        raise ValueError(f"Unsupported image data format: {type(image_data)}")


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


def orchestrate(video_dir: str = "videos", output_frames_dir: str = "frames", metadata_dir: str = "metadata") -> List[Dict[str, Any]]:
    """
    Main orchestration function.
    Iterates over videos, invokes extract_frames(), saves frame JPGs,
    and produces metadata.json and metadata.csv.
    """
    print(f"[*] Discovering videos in folder: '{video_dir}'...")
    video_paths = discover_videos(video_dir)

    if not video_paths:
        print(f"[!] ERROR: No video files found in directory '{video_dir}'.")
        print(f"[!] Please place video files (.mp4, .avi, .mov, .mkv, .webm) into '{video_dir}' and rerun.")
        sys.exit(1)

    print(f"[*] Found {len(video_paths)} video file(s): {[os.path.basename(p) for p in video_paths]}")

    all_metadata: List[Dict[str, Any]] = []

    for vpath in video_paths:
        video_id = sanitize_video_id(vpath)
        print(f"\n[*] Processing video '{vpath}' (video_id='{video_id}')...")

        try:
            result: ExtractionResult = extract_frames(vpath)
        except Exception as e:
            print(f"[!] ERROR: Extraction failed for video '{vpath}': {e}")
            raise e

        print(f"    - Extraction completed using backend '{result.backend}'. Extracted {len(result.frames)} frame(s).")

        video_frame_dir = os.path.join(output_frames_dir, video_id)
        os.makedirs(video_frame_dir, exist_ok=True)

        for frame in result.frames:
            # Construct exact required relative frame path (using POSIX slashes for JSON/CSV portability)
            rel_frame_path = f"{output_frames_dir}/{video_id}/{frame.frame_index}.jpg"
            abs_frame_path = os.path.join(output_frames_dir, video_id, f"{frame.frame_index}.jpg")

            save_frame_image(frame.image, abs_frame_path)

            # EXACT metadata schema required: video_id, frame_index, timestamp, scene_id, frame_path
            record = {
                "video_id": video_id,
                "frame_index": int(frame.frame_index),
                "timestamp": float(frame.timestamp),
                "scene_id": int(frame.scene_id),
                "frame_path": rel_frame_path
            }
            all_metadata.append(record)

    # Ensure metadata directory exists
    os.makedirs(metadata_dir, exist_ok=True)

    json_path = os.path.join(metadata_dir, "metadata.json")
    csv_path = os.path.join(metadata_dir, "metadata.csv")

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
    parser.add_argument("--video-dir", type=str, default="videos", help="Directory containing input videos")
    parser.add_argument("--frames-dir", type=str, default="frames", help="Output directory for saved frames")
    parser.add_argument("--metadata-dir", type=str, default="metadata", help="Output directory for metadata files")
    args = parser.parse_args()

    orchestrate(video_dir=args.video_dir, output_frames_dir=args.frames_dir, metadata_dir=args.metadata_dir)
