"""
object_detector.py — YOLO-World-M Object Detection Engine
==========================================================
Architecture ref : 03_Architecture_Final.md §2 (Object detector row)
TRD ref          : TRD-Build-Plan-Achilles.md §PART 2

Canonical rules:
  - Model: YOLO-World-M (Ultralytics integration).
  - Fixed, pre-compiled vocabulary from vocabulary.py — compiled ONCE at init.
  - Runs on every keyframe from Part 1.
  - Outputs: class, bbox, confidence, color, spatial_relations.
  - Color populated by color_extractor.py (center-weighted crop + k-means + CIELAB).
  - Spatial: left/right only, top-4-confidence pairs (spatial.py).
  - NO proximity / near / close-to logic.

Public API:
    detector = ObjectDetector()            # loads model + compiles vocab once
    results  = detector.detect(frame_bgr)  # returns list[DetectionResult]

    OR convenience:
    results = detect_keyframe(frame_path)  # load frame from disk, run detection
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import TypedDict

import cv2
import numpy as np

from .color_extractor import extract_color
from .spatial import compute_spatial_relations, SpatialRelation
from .vocabulary import VOCABULARY

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Output contract (TRD §PART 2)
# ---------------------------------------------------------------------------

# Functional TypedDict form required: 'class' is a Python reserved word
# and cannot be used as a bare identifier in class-syntax TypedDict.
# The functional form supports it as a string key.
DetectionResult = TypedDict('DetectionResult', {
    'class':           str,                   # vocabulary class label (Odysseus contract)
    'bbox':            tuple,                  # (x1, y1, x2, y2) pixels
    'confidence':      float,                  # 0.0 - 1.0
    'color':           str,                    # CIELAB palette name or "unknown"
    'spatial_relations': list,                 # SpatialRelation items
})


# ---------------------------------------------------------------------------
# Confidence / NMS thresholds (tuneable without changing the contract)
# ---------------------------------------------------------------------------
CONF_THRESHOLD: float = 0.25   # discard detections below this
IOU_THRESHOLD:  float = 0.45   # NMS IoU threshold (Ultralytics default)


# ---------------------------------------------------------------------------
# Detector class
# ---------------------------------------------------------------------------

class ObjectDetector:
    """
    YOLO-World-M detector with fixed vocabulary, initialised once.

    The model is loaded on first instantiation and the fixed vocabulary is
    compiled at that point.  Re-use one instance across all keyframes in a
    single ingestion run.
    """

    def __init__(
        self,
        model_name: str = "yolov8m-worldv2.pt",
        conf: float = CONF_THRESHOLD,
        iou: float = IOU_THRESHOLD,
        device: str | None = None,
    ) -> None:
        """
        Parameters
        ----------
        model_name : Ultralytics model identifier or local path.
                     "yolov8m-worldv2.pt" is the recommended YOLO-World-M checkpoint.
        conf       : minimum confidence threshold.
        iou        : NMS IoU threshold.
        device     : "cuda", "cpu", or None (auto-detect).
        """
        from ultralytics import YOLO

        logger.info("Loading YOLO-World model: %s", model_name)
        self._model = YOLO(model_name)

        # Compile fixed vocabulary — done ONCE here, never per-frame
        logger.info("Setting fixed vocabulary: %d terms", len(VOCABULARY))
        self._model.set_classes(list(VOCABULARY))

        self._conf   = conf
        self._iou    = iou
        self._device = device or ("cuda" if self._cuda_available() else "cpu")
        logger.info("ObjectDetector ready on device=%s  vocab=%d  conf=%.2f",
                    self._device, len(VOCABULARY), self._conf)

    @staticmethod
    def _cuda_available() -> bool:
        try:
            import torch
            return torch.cuda.is_available()
        except ImportError:
            return False

    # ------------------------------------------------------------------
    # Public: detect from a numpy BGR frame
    # ------------------------------------------------------------------

    def detect(
        self,
        frame_bgr: np.ndarray,
        frame_path: str = "",
    ) -> list[DetectionResult]:
        """
        Run detection on a single BGR frame.

        Parameters
        ----------
        frame_bgr  : H×W×3 uint8 BGR image (as returned by cv2.imread).
        frame_path : optional, for logging only.

        Returns
        -------
        list[DetectionResult] — may be empty if no objects exceed conf threshold.
        """
        if frame_bgr is None or frame_bgr.size == 0:
            logger.warning("detect() received empty frame: %s", frame_path)
            return []

        # -- Run inference (single frame, no streaming, no batch) --------
        results = self._model.predict(
            source=frame_bgr,
            conf=self._conf,
            iou=self._iou,
            device=self._device,
            verbose=False,
            stream=False,
        )

        if not results or results[0].boxes is None:
            return []

        boxes = results[0].boxes
        if len(boxes) == 0:
            return []

        # -- Parse raw detections ----------------------------------------
        raw_detections: list[DetectionResult] = []

        xyxy_arr   = boxes.xyxy.cpu().numpy().astype(int)    # (N, 4)
        conf_arr   = boxes.conf.cpu().numpy().astype(float)  # (N,)
        cls_arr    = boxes.cls.cpu().numpy().astype(int)     # (N,)

        for i in range(len(xyxy_arr)):
            x1, y1, x2, y2 = xyxy_arr[i]
            conf  = float(conf_arr[i])
            cls   = int(cls_arr[i])

            # Map class index → vocabulary string
            class_name = self._model.names.get(cls, VOCABULARY[cls] if cls < len(VOCABULARY) else "unknown")

            # Color from center-weighted crop
            bbox = (int(x1), int(y1), int(x2), int(y2))
            color = extract_color(frame_bgr, bbox)

            raw_detections.append({
                'class':           class_name,
                'bbox':            bbox,
                'confidence':      round(conf, 4),
                'color':           color,
                'spatial_relations': [],          # filled below
            })

        # -- Compute spatial relations for this frame --------------------
        # Pass raw_detections as DetectionDict-compatible list
        all_relations = compute_spatial_relations(
            [{'class': d['class'],
              'bbox': d['bbox'],
              'confidence': d['confidence'],
              'color': d['color']}
             for d in raw_detections],
            top_k_pairs=4,
        )

        # Attach relations back to each detection that participates
        for rel in all_relations:
            # subject is "left_of" object — attach to BOTH
            raw_detections[rel["subject_idx"]]["spatial_relations"].append(rel)

        logger.debug(
            "detect(): %d objects, %d spatial relations | %s",
            len(raw_detections), len(all_relations),
            os.path.basename(frame_path) if frame_path else "frame",
        )

        return raw_detections

    # ------------------------------------------------------------------
    # Convenience: detect from a JPEG path (as written by extraction_engine)
    # ------------------------------------------------------------------

    def detect_keyframe(self, frame_path: str) -> list[DetectionResult]:
        """
        Load a JPEG keyframe from disk and run detection.

        This is the primary interface consumed by Odysseus's orchestration script:
          for frame_record in extract_frames(video_path, output_dir):
              detections = detector.detect_keyframe(frame_record["frame_path"])
        """
        frame_bgr = cv2.imread(frame_path)
        if frame_bgr is None:
            logger.error("Could not read frame: %s", frame_path)
            return []
        return self.detect(frame_bgr, frame_path=frame_path)


# ---------------------------------------------------------------------------
# Module-level convenience (lazy singleton for simple scripts)
# ---------------------------------------------------------------------------

_SINGLETON: ObjectDetector | None = None


def get_detector(**kwargs) -> ObjectDetector:
    """Return a module-level singleton ObjectDetector (created on first call)."""
    global _SINGLETON
    if _SINGLETON is None:
        _SINGLETON = ObjectDetector(**kwargs)
    return _SINGLETON


def detect_keyframe(frame_path: str) -> list[DetectionResult]:
    """Convenience one-liner: detect_keyframe('/frames/vid1/0042.jpg')"""
    return get_detector().detect_keyframe(frame_path)
