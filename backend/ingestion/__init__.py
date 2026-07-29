"""
backend/ingestion/__init__.py
"""
from .extraction_engine import extract_frames, LONG_SHOT_THRESHOLD_S, SCENE_DETECT_THRESHOLD

__all__ = ["extract_frames", "LONG_SHOT_THRESHOLD_S", "SCENE_DETECT_THRESHOLD"]
