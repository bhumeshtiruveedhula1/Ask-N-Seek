"""
extraction/extraction.py

Extraction layer interface contract for Achilles.
Provides `extract_frames(video_path)` which returns `ExtractionResult`.
"""

import os
from dataclasses import dataclass
from typing import List, Any


@dataclass
class FrameData:
    frame_index: int
    timestamp: float
    scene_id: int
    image: Any  # PIL Image, numpy array (BGR/RGB), or JPEG bytes


@dataclass
class ExtractionResult:
    frames: List[FrameData]
    backend: str


def extract_frames(video_path: str) -> ExtractionResult:
    """
    Extract frames from a video file.
    
    This function is maintained by Achilles.
    Returns an ExtractionResult containing list of FrameData objects and backend descriptor.
    """
    if not os.path.exists(video_path):
        raise FileNotFoundError(f"Video file not found at path: {video_path}")

    # Standard fallback / reference extraction using cv2 if available
    try:
        import cv2
        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            raise ValueError(f"Could not open video file: {video_path}")
            
        fps = cap.get(cv2.CAP_PROP_FPS)
        if fps <= 0:
            fps = 30.0  # Fallback FPS
            
        frames: List[FrameData] = []
        frame_idx = 0
        scene_id = 0
        last_timestamp = -1.0
        
        # Simple scene change threshold on mean intensity shift for fallback
        prev_gray = None
        
        while True:
            ret, frame = cap.read()
            if not ret:
                break
                
            timestamp = round(frame_idx / fps, 4)
            
            # Simple scene change detection demo (every ~30 frames or on color shift)
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            if prev_gray is not None:
                diff = cv2.absdiff(gray, prev_gray).mean()
                if diff > 30.0:  # Threshold for scene transition
                    scene_id += 1
            prev_gray = gray
            
            # Convert BGR to RGB for standard image saving/processing
            rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            
            frames.append(FrameData(
                frame_index=frame_idx,
                timestamp=timestamp,
                scene_id=scene_id,
                image=rgb_frame
            ))
            frame_idx += 1
            
        cap.release()
        return ExtractionResult(frames=frames, backend="opencv_reference")
        
    except ImportError:
        raise NotImplementedError(
            "OpenCV is not installed in the environment for reference extraction. "
            "Achilles will provide the production PySceneDetect/OpenCV extraction implementation."
        )
