"""
tests/create_test_videos.py

Generates local test videos for the 3 required categories:
1. hard cuts (hard_cuts.mp4)
2. static shot (static_shot.mp4)
3. continuous motion (continuous_motion.mp4)
"""

import os
import numpy as np
import cv2


def create_hard_cuts_video(output_path: str, duration_sec: int = 3, fps: int = 30):
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    height, width = 240, 320
    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    out = cv2.VideoWriter(output_path, fourcc, fps, (width, height))

    colors = [
        (0, 0, 255),    # Red
        (0, 255, 0),    # Green
        (255, 0, 0),    # Blue
    ]

    frames_per_color = (duration_sec * fps) // len(colors)
    for color in colors:
        frame = np.full((height, width, 3), color, dtype=np.uint8)
        for _ in range(frames_per_color):
            out.write(frame)

    out.release()
    print(f"[+] Created 'hard cuts' test video: {output_path}")


def create_static_shot_video(output_path: str, duration_sec: int = 3, fps: int = 30):
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    height, width = 240, 320
    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    out = cv2.VideoWriter(output_path, fourcc, fps, (width, height))

    # Single static background frame
    frame = np.full((height, width, 3), (128, 128, 128), dtype=np.uint8)
    cv2.putText(frame, "Static Shot", (60, 120), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (255, 255, 255), 2)

    total_frames = duration_sec * fps
    for _ in range(total_frames):
        out.write(frame)

    out.release()
    print(f"[+] Created 'static shot' test video: {output_path}")


def create_continuous_motion_video(output_path: str, duration_sec: int = 3, fps: int = 30):
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    height, width = 240, 320
    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    out = cv2.VideoWriter(output_path, fourcc, fps, (width, height))

    total_frames = duration_sec * fps
    radius = 20

    for i in range(total_frames):
        frame = np.zeros((height, width, 3), dtype=np.uint8)
        center_x = int(radius + (width - 2 * radius) * (i / max(1, total_frames - 1)))
        center_y = height // 2
        cv2.circle(frame, (center_x, center_y), radius, (0, 255, 255), -1)
        out.write(frame)

    out.release()
    print(f"[+] Created 'continuous motion' test video: {output_path}")


def generate_all_test_videos(video_dir: str = "videos"):
    print(f"[*] Generating test videos in directory: '{video_dir}'...")
    create_hard_cuts_video(os.path.join(video_dir, "hard_cuts.mp4"))
    create_static_shot_video(os.path.join(video_dir, "static_shot.mp4"))
    create_continuous_motion_video(os.path.join(video_dir, "continuous_motion.mp4"))
    print("[+] All test video categories generated successfully.")


if __name__ == "__main__":
    generate_all_test_videos()
