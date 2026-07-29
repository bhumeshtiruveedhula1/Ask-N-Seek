"""backend/vision/__init__.py — package marker with full exports"""
from .object_detector import ObjectDetector, DetectionResult, detect_keyframe, get_detector
from .vocabulary import VOCABULARY, VOCABULARY_SET, SYNONYM_MAP, get_vocabulary, resolve_synonym
from .spatial import compute_spatial_relations, SpatialRelation
from .color_extractor import extract_color

__all__ = [
    "ObjectDetector", "DetectionResult", "detect_keyframe", "get_detector",
    "VOCABULARY", "VOCABULARY_SET", "SYNONYM_MAP", "get_vocabulary", "resolve_synonym",
    "compute_spatial_relations", "SpatialRelation",
    "extract_color",
]
