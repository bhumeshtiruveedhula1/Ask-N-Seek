"""
metadata/validate.py

Validation harness for Odysseus Part 1 Metadata & Frames.

Verifies:
1. Timestamps are increasing appropriately within each video
2. Scene IDs are non-decreasing within each video
3. No duplicate frame_index values within a video
4. Every frame_path actually exists

A successful run must end with: "0 errors"
"""

import csv
import json
import os
import sys
from typing import Any, Dict, List


def validate_metadata(json_path: str = "metadata/metadata.json", csv_path: str = "metadata/metadata.csv") -> int:
    error_count = 0

    print("[*] Starting metadata and frame validation...")

    # Check existence of metadata files
    if not os.path.exists(json_path):
        print(f"[!] ERROR: JSON metadata file missing at '{json_path}'")
        error_count += 1
        print(f"\nValidation failed with {error_count} errors.")
        return error_count

    if not os.path.exists(csv_path):
        print(f"[!] ERROR: CSV metadata file missing at '{csv_path}'")
        error_count += 1
        print(f"\nValidation failed with {error_count} errors.")
        return error_count

    # Read JSON metadata
    with open(json_path, "r", encoding="utf-8") as f:
        records: List[Dict[str, Any]] = json.load(f)

    # Read CSV metadata to verify parity
    csv_records: List[Dict[str, Any]] = []
    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            csv_records.append({
                "video_id": row["video_id"],
                "frame_index": int(row["frame_index"]),
                "timestamp": float(row["timestamp"]),
                "scene_id": int(row["scene_id"]),
                "frame_path": row["frame_path"]
            })

    if len(records) != len(csv_records):
        print(f"[!] ERROR: JSON record count ({len(records)}) does not match CSV record count ({len(csv_records)})")
        error_count += 1

    # Group records by video_id
    videos_data: Dict[str, List[Dict[str, Any]]] = {}
    for r in records:
        vid = r["video_id"]
        videos_data.setdefault(vid, []).append(r)

    print(f"[*] Validating metadata for {len(videos_data)} video(s), total {len(records)} frame record(s)...")

    for video_id, frames in videos_data.items():
        seen_indices = set()
        prev_timestamp = -1.0
        prev_scene_id = -1

        # Sort frames by frame_index to check order consistency
        sorted_frames = sorted(frames, key=lambda x: x["frame_index"])

        for frame in sorted_frames:
            f_idx = frame["frame_index"]
            ts = frame["timestamp"]
            sc_id = frame["scene_id"]
            f_path = frame["frame_path"]

            # Rule 3: Check duplicate frame_index
            if f_idx in seen_indices:
                print(f"[!] ERROR: Video '{video_id}' has duplicate frame_index {f_idx}")
                error_count += 1
            seen_indices.add(f_idx)

            # Rule 1: Check timestamps increasing appropriately
            if prev_timestamp >= 0.0 and ts <= prev_timestamp:
                print(f"[!] ERROR: Video '{video_id}' frame {f_idx} timestamp {ts} is not strictly greater than previous timestamp {prev_timestamp}")
                error_count += 1
            prev_timestamp = ts

            # Rule 2: Check scene IDs non-decreasing
            if prev_scene_id >= 0 and sc_id < prev_scene_id:
                print(f"[!] ERROR: Video '{video_id}' frame {f_idx} scene_id {sc_id} decreased from previous scene_id {prev_scene_id}")
                error_count += 1
            prev_scene_id = sc_id

            # Rule 4: Check frame_path existence
            # Normalize path for OS filesystem check
            norm_path = os.path.normpath(f_path)
            if not os.path.exists(norm_path):
                print(f"[!] ERROR: Video '{video_id}' frame {f_idx} frame_path does not exist: '{norm_path}'")
                error_count += 1

    print(f"\nValidation Summary:")
    print(f"{error_count} errors")
    return error_count


if __name__ == "__main__":
    json_file = sys.argv[1] if len(sys.argv) > 1 else "metadata/metadata.json"
    csv_file = sys.argv[2] if len(sys.argv) > 2 else "metadata/metadata.csv"
    errs = validate_metadata(json_file, csv_file)
    sys.exit(errs)
