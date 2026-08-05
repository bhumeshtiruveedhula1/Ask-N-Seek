"""
config.py — Odysseus Part 3 configuration.

All sensitive values are loaded from environment variables or a .env file.
No secrets are hardcoded.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Qdrant connection (for production — Part 2 real collection)
# ---------------------------------------------------------------------------
QDRANT_URL: str = os.getenv("QDRANT_URL", "http://localhost:6333")
QDRANT_API_KEY: str | None = os.getenv("QDRANT_API_KEY", None)
QDRANT_COLLECTION: str = os.getenv("QDRANT_COLLECTION", "video_objects")

# Structured host/port (used by qdrant_gateway.py for direct connections)
QDRANT_HOST: str = os.getenv("QDRANT_HOST", "localhost")
QDRANT_PORT: int = int(os.getenv("QDRANT_PORT", "6333"))

# ---------------------------------------------------------------------------
# Stub collection name (in-memory, Milestone 1/2)
# ---------------------------------------------------------------------------
STUB_COLLECTION: str = "stub_video_objects"

# ---------------------------------------------------------------------------
# Judge session collections (ephemeral, per-evaluator isolation)
# ---------------------------------------------------------------------------
JUDGE_SESSION_PREFIX: str    = "judge_session_"
MAX_SESSION_AGE_MINUTES: int = 30

# ---------------------------------------------------------------------------
# Data-source switch: True → in-memory stub, False → real Qdrant
# TODO: SWAP FOR ACHILLES — set USE_STUB_QDRANT = False in .env when ready
# ---------------------------------------------------------------------------
USE_STUB_QDRANT: bool = os.getenv("USE_STUB_QDRANT", "true").lower() in {
    "true", "1", "yes",
}

# ---------------------------------------------------------------------------
# Parser configuration (for engine/parser_gateway.py)
# WIRED: Achilles real parser (backend.query.query_parser.parse_query)
# ---------------------------------------------------------------------------
# integration/part3 fix (2026-07-30): default now points at Achilles's real parser.
# Previously defaulted to engine.stub_parser (stub only recognised fixture vocab).
# To revert to stub for isolated testing: set PARSER_MODULE=engine.stub_parser
#   PARSER_FUNCTION=parse_query_stub in .env
# NOTE: ParseResult (Achilles) is a dataclass — parser_gateway.py normalises it to
#       the Odysseus stub dict shape {status, filters} before returning.
PARSER_MODULE: str   = os.getenv("PARSER_MODULE",   "backend.query.query_parser")
PARSER_FUNCTION: str = os.getenv("PARSER_FUNCTION", "parse_query")

# ---------------------------------------------------------------------------
# Field name mapping — change here if Qdrant schema or parser contract changes.
# search.py reads field names exclusively from this dict.
# ---------------------------------------------------------------------------
FIELD_MAP: dict[str, str] = {
    # Parser filter dict → key name used by Achilles's parse_query output
    "filter_class":      "class",
    # Qdrant payload → field names stored by Part 2
    "qdrant_class":      "class_name",
    "qdrant_color":      "color",
    "qdrant_spatial":    "spatial_relations",
    "qdrant_bbox":       "bbox",
    "qdrant_confidence": "confidence",
    "qdrant_video_id":   "video_id",
    "qdrant_frame_idx":  "frame_index",
    "qdrant_timestamp":  "timestamp",
    "qdrant_scene_id":   "scene_id",
    # Achilles SpatialRelation dict keys (from backend/vision/spatial.py)
    # Each spatial_relations list item has exactly these keys:
    "spatial_subject":     "subject",       # class_name of the left object
    "spatial_subject_idx": "subject_idx",   # index in frame's detections list
    "spatial_relation":    "relation",      # "left_of" | "right_of"
    "spatial_object":      "object_",       # class_name of the right object
    "spatial_object_idx":  "object_idx",    # index in frame's detections list
}

# ---------------------------------------------------------------------------
# Threshold
# ---------------------------------------------------------------------------
# Milestone 1/2 placeholder: 0.5
# Milestone 2: calibrate_threshold() will overwrite threshold_config.json
PLACEHOLDER_THRESHOLD: float = 0.5
THRESHOLD_CONFIG_PATH: Path = Path(__file__).parent / "threshold_config.json"


def load_threshold() -> float:
    """
    Load the calibrated threshold from threshold_config.json.
    Falls back to PLACEHOLDER_THRESHOLD (0.5) with a logged warning if missing.
    """
    if THRESHOLD_CONFIG_PATH.exists():
        try:
            with open(THRESHOLD_CONFIG_PATH, encoding="utf-8") as fh:
                data = json.load(fh)
            return float(data.get("threshold", PLACEHOLDER_THRESHOLD))
        except (json.JSONDecodeError, KeyError, TypeError) as exc:
            logger.warning("load_threshold: corrupt threshold_config.json (%s). Using default.", exc)
    else:
        logger.warning(
            "load_threshold: threshold_config.json missing — using placeholder %.1f. "
            "Run: python -m engine.calibration --data-source stub",
            PLACEHOLDER_THRESHOLD,
        )
    return PLACEHOLDER_THRESHOLD


# ---------------------------------------------------------------------------
# Path templates (for engine/paths.py — change if deployment layout changes)
# ---------------------------------------------------------------------------
FRAME_PATH_TEMPLATE: str = os.getenv(
    "FRAME_PATH_TEMPLATE",
    "/mnt/agents/output/frames/{video_id}/{frame_index:04d}.jpg",
)
VIDEO_PATH_TEMPLATE: str = os.getenv(
    "VIDEO_PATH_TEMPLATE",
    "/mnt/agents/output/videos/{video_id}.mp4",
)

# ---------------------------------------------------------------------------
# Keyframe extraction caps (consumed by backend/ingestion/extraction_engine.py)
# ---------------------------------------------------------------------------
# Maximum keyframes extracted per scene during the 1-FPS fallback.
# Prevents long static shots from inflating Qdrant payload and slowing ingestion.
MAX_KEYFRAMES_PER_SCENE: int = 5

# Minimum seconds between evenly-distributed fallback keyframes.
# Effective interval = scene_duration / n_keyframes  (always >= this floor).
MIN_KEYFRAME_INTERVAL_S: float = 2.0

# ---------------------------------------------------------------------------
# Ingestion speed optimisation
# ---------------------------------------------------------------------------
# Drop detections below this confidence BEFORE color extraction and spatial
# computation. Reduces wasted cv2/k-means work on uncertain detections.
# Must be well below THRESHOLD (0.3197) to preserve near-threshold hits.
EARLY_CONFIDENCE_FILTER: float = 0.30

# Minimum number of frames a class must appear in to show up in top_classes.
# Classes seen in only 1 frame are very likely YOLO-World zero-shot hallucinations.
# Set to 1 to disable this filter (show all classes including single-frame detections).
MIN_FRAME_PRESENCE: int = 2

# Edge-to-edge pixel gap below which two detected objects are considered "near".
# Used by spatial.py compute_spatial_relations() for the "near" relation type.
# Increase for wider proximity detection; decrease to require closer objects.
SPATIAL_NEAR_GAP_PX: int = 50

# ---------------------------------------------------------------------------
# Per-class confidence gates (overrides EARLY_CONFIDENCE_FILTER for specific classes)
# ---------------------------------------------------------------------------
# These classes are high-variance open-vocab attractors in YOLO-World:
# their zero-shot embeddings activate on visually similar but unrelated objects.
# A higher confidence gate suppresses hallucinations while keeping
# the global EARLY_CONFIDENCE_FILTER at 0.30 for all other classes.
#
# IMPORTANT: keys must match POST-canonicalization class names (after SYNONYM_MAP).
# "bat" maps to "baseball bat" via SYNONYM_MAP, so the key is "baseball bat".
HIGH_VARIANCE_CLASSES: frozenset[str] = frozenset({
    "baseball bat",  # "bat" → "baseball bat" via SYNONYM_MAP; activates on bottles/sticks
    "hockey stick",  # "stick" → "hockey stick"; activates on poles, brooms, wires
    "fishing rod",   # "rod" → "fishing rod"; activates on thin cylinders (pipes, tubes)
    "tennis net",    # "net" → "tennis net"; activates on grid/mesh patterns
    "skateboard",    # "board" → "skateboard"; activates on flat rectangles
    "kite",          # activates on triangular geometries (road signs, flags)
    "skis",          # activates on long thin objects (pipes, rails)
    "frisbee",       # activates on circular flat objects (plates, wheels)
})

# Auto-generated — add a class to HIGH_VARIANCE_CLASSES and the gate applies automatically
CLASS_CONFIDENCE_GATES: dict[str, float] = {cls: 0.45 for cls in HIGH_VARIANCE_CLASSES}




# ---------------------------------------------------------------------------
# Gradio
# ---------------------------------------------------------------------------
GRADIO_PORT: int = int(os.getenv("GRADIO_PORT", "7860"))
GRADIO_HOST: str = os.getenv("GRADIO_HOST", "0.0.0.0")

