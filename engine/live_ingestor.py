"""
engine/live_ingestor.py — Live Judge-Video Ingestion Mode (U1)

Wraps the existing Achilles pipeline (extract → detect → color → spatial → Qdrant)
in a background thread, streaming progress dicts via a generator.

CALLS existing functions — does NOT reimplement:
  - backend.ingestion.extraction_engine.extract_frames()
  - backend.vision.object_detector.get_detector()
  - backend.vision.color_extractor.extract_color()
  - engine.qdrant_gateway.make_judge_collection_name()

NOTE: extract_color() takes frame_bgr (np.ndarray), NOT frame_path.
      We cv2.imread the saved keyframe before calling it.
"""
from __future__ import annotations

import logging
import os
import queue
import shutil
import threading
import uuid
from pathlib import Path
from typing import Generator

import cv2
import numpy as np

from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams

from backend.ingestion.extraction_engine import extract_frames
from backend.vision.color_extractor import extract_color
from backend.vision.object_detector import get_detector, ObjectDetector
from engine.qdrant_gateway import make_judge_collection_name

logger = logging.getLogger(__name__)

_DUMMY_VECTOR: list[float] = [0.0]
_PAYLOAD_INDEX_FIELDS = ("class_name", "color", "spatial_relations")
_BATCH_SIZE = 100          # Qdrant upsert batch size


class LiveIngestor:
    """
    Full ingestion pipeline for a single video, streaming progress updates.

    Usage::

        client   = get_qdrant_client()
        ingestor = LiveIngestor(client)
        for update in ingestor.ingest(video_path):
            print(update)   # dict with phase, progress_pct, message, stats
        # Final update has phase="complete" and stats["collection"]
    """

    def __init__(
        self,
        qdrant_client: QdrantClient,
        collection_name: str | None = None,
        detector: ObjectDetector | None = None,
    ) -> None:
        self._client     = qdrant_client
        self._collection = collection_name or make_judge_collection_name()
        self._detector   = detector or get_detector()

    @property
    def collection_name(self) -> str:
        return self._collection

    # ------------------------------------------------------------------
    # Public generator
    # ------------------------------------------------------------------

    def ingest(
        self,
        video_path: str,
        output_dir: str = "./temp_frames",
    ) -> Generator[dict, None, None]:
        """
        Run the full pipeline in a background thread; yield progress dicts.

        Phases and progress estimates:
          scene_detection  0  → 10 %
          extraction      10  → 25 %
          detection       25  → 60 %
          color           60  → 75 %
          indexing        80  → 100 %
          complete        100 %
        """
        q: queue.Queue = queue.Queue()

        def _worker():
            try:
                for item in self._run_pipeline(video_path, output_dir):
                    q.put(item)
            except Exception as exc:  # noqa: BLE001
                logger.exception("LiveIngestor pipeline error: %s", exc)
                q.put({
                    "phase":        "error",
                    "progress_pct": 0,
                    "message":      f"Pipeline error: {exc}",
                    "stats":        {},
                })
            finally:
                q.put(None)  # sentinel

        t = threading.Thread(target=_worker, daemon=True)
        t.start()

        while True:
            item = q.get()
            if item is None:
                break
            yield item

    # ------------------------------------------------------------------
    # Internal: full pipeline (runs in background thread)
    # ------------------------------------------------------------------

    def _run_pipeline(
        self,
        video_path: str,
        output_dir: str,
    ) -> Generator[dict, None, None]:

        stats = {"scenes": 0, "keyframes": 0, "objects": 0, "collection": self._collection}

        # ── Phase 1: Scene detection (0 → 10%) ──────────────────────────
        yield _progress("scene_detection", 0, "Starting scene detection…", stats)

        # extract_frames runs PySceneDetect internally — we collect all frame
        # records first so we know total count for progress reporting.
        frame_records: list[dict] = []
        detections_map: dict[str, list[dict]] = {}   # frame_path → detections

        # Phase 2 begins as soon as extract_frames yields the first frame.
        # We interleave extraction + detection in one pass (memory-safe):
        # extract_frames yields one record at a time, we detect immediately.

        yield _progress("extraction", 10, "Extracting keyframes…", stats)

        # ── Phases 2 + 3 interleaved: extraction + detection (10 → 60%) ─
        frame_count = 0
        obj_count   = 0

        # Honest count tracking: per-scene peak concurrent detections per class.
        # scene_max_counts[scene_id][class_name] = max detections in any single frame
        # scene_class_seen[scene_id] = set of classes that appeared (for frames_detected)
        scene_max_counts: dict[int, dict[str, int]] = {}
        scene_class_seen: dict[int, set] = {}

        for record in extract_frames(video_path, output_dir):
            frame_records.append(record)
            frame_path = record["frame_path"]
            scene_id   = record["scene_id"]
            frame_count += 1

            # Object detection
            dets = self._detector.detect_keyframe(frame_path)
            detections_map[frame_path] = dets
            obj_count += len(dets)

            # Track per-scene peak counts per class
            if scene_id not in scene_max_counts:
                scene_max_counts[scene_id] = {}
                scene_class_seen[scene_id] = set()
            frame_class_counts: dict[str, int] = {}
            for det in dets:
                cls = det["class"]
                frame_class_counts[cls] = frame_class_counts.get(cls, 0) + 1
                scene_class_seen[scene_id].add(cls)
            for cls, cnt in frame_class_counts.items():
                scene_max_counts[scene_id][cls] = max(
                    scene_max_counts[scene_id].get(cls, 0), cnt
                )

            stats = {
                "scenes":     scene_id + 1,
                "keyframes":  frame_count,
                "objects":    obj_count,
                "collection": self._collection,
            }

            if frame_count % 5 == 0:
                # Asymptotic progress: each batch of 5 frames adds ~2%, capped at 59
                # so the bar visibly moves without knowing total frame count up front.
                # Formula: pct grows from 10 toward 59; step = 2 per 5-frame batch.
                pct = _clamp(10 + (frame_count // 5) * 2, 10, 59)
                yield _progress(
                    "detection", pct,
                    f"Frame {frame_count}: {obj_count} objects so far", stats,
                )

        stats["keyframes"] = frame_count
        stats["objects"]   = obj_count
        yield _progress("detection", 60, f"Detection done: {obj_count} objects across {frame_count} frames", stats)

        if frame_count == 0:
            yield _progress("complete", 100, "No frames extracted — check video path/codec.", stats)
            return

        # ── Phase 4: Color extraction (60 → 75%) ────────────────────────
        yield _progress("color", 60, "Extracting dominant colors…", stats)

        color_map: dict[str, list[str]] = {}   # frame_path → [color per detection]
        for record in frame_records:
            fp   = record["frame_path"]
            dets = detections_map.get(fp, [])
            if not dets:
                color_map[fp] = []
                continue
            frame_bgr = cv2.imread(fp)
            if frame_bgr is None:
                color_map[fp] = ["unknown"] * len(dets)
                continue
            colors = []
            for det in dets:
                try:
                    c = extract_color(frame_bgr, det["bbox"])
                except Exception:  # noqa: BLE001
                    c = "unknown"
                colors.append(c)
            color_map[fp] = colors

        yield _progress("color", 75, "Color extraction complete.", stats)

        # ── Phase 5: Spatial (already inside detections — just log) ─────
        yield _progress("spatial", 75, "Spatial relations already computed by detector.", stats)

        # ── Phase 6: Qdrant indexing (80 → 100%) ────────────────────────
        yield _progress("indexing", 80, f"Creating collection {self._collection}…", stats)

        self._create_collection()

        points: list[PointStruct] = []
        for record in frame_records:
            fp    = record["frame_path"]
            dets  = detections_map.get(fp, [])
            cols  = color_map.get(fp, [])

            for i, det in enumerate(dets):
                color = cols[i] if i < len(cols) else "unknown"
                pt_id = str(uuid.uuid5(
                    uuid.NAMESPACE_URL,
                    f"{record['video_id']}_{record['frame_index']}_{i}",
                ))
                payload = {
                    "video_id":          record["video_id"],
                    "frame_index":       record["frame_index"],
                    "timestamp":         record["timestamp"],
                    "scene_id":          record["scene_id"],
                    "frame_path":        fp,
                    "class_name":        det["class"],
                    "color":             color,
                    "confidence":        det["confidence"],
                    "bbox":              list(det["bbox"]),
                    "spatial_relations": det.get("spatial_relations", []),
                    "detection_source":  det.get("detection_source", "full_primary"),
                }
                points.append(PointStruct(id=pt_id, vector=_DUMMY_VECTOR, payload=payload))

        # Batch upsert
        total_pts = len(points)
        for batch_start in range(0, total_pts, _BATCH_SIZE):
            batch = points[batch_start: batch_start + _BATCH_SIZE]
            self._client.upsert(self._collection, batch)
            pct = _clamp(80 + int((batch_start + len(batch)) / max(total_pts, 1) * 20), 80, 99)
            yield _progress(
                "indexing", pct,
                f"Indexed {batch_start + len(batch)}/{total_pts} points…", stats,
            )

        stats["objects"] = total_pts
        yield _progress("indexing", 99, f"Indexed {total_pts} points. Cleaning up…", stats)

        # Optional cleanup: remove temp frames directory
        try:
            video_id   = Path(video_path).stem
            frames_dir = Path(output_dir) / video_id
            if frames_dir.exists():
                shutil.rmtree(frames_dir)
                logger.info("Removed temp frames: %s", frames_dir)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Temp cleanup failed (non-fatal): %s", exc)

        # ── Honest top_classes aggregation ──────────────────────────────
        # frames_detected = number of scenes where class was seen (not raw frame count).
        # max_concurrent  = peak simultaneous detections in any single frame/scene.
        # count           = alias for frames_detected (backward compat).
        class_frames: dict[str, int] = {}   # class → scenes where it appeared
        class_peak:   dict[str, int] = {}   # class → max concurrent in any scene
        for scene_id, class_map in scene_max_counts.items():
            for cls, peak in class_map.items():
                class_frames[cls] = class_frames.get(cls, 0) + 1
                class_peak[cls]   = max(class_peak.get(cls, 0), peak)

        top_classes = sorted(
            [
                {
                    "class":           cls,
                    "frames_detected": class_frames[cls],
                    "max_concurrent":  class_peak[cls],
                    "count":           class_frames[cls],  # backward compat
                }
                for cls in class_frames
            ],
            key=lambda x: -x["frames_detected"],
        )[:10]

        stats["collection"]      = self._collection
        stats["top_classes"]     = top_classes
        stats["total_keyframes"] = frame_count
        yield _progress(
            "complete", 100,
            f"Ready to search — {stats['keyframes']} frames, {total_pts} points in {self._collection}",
            stats,
        )

    # ------------------------------------------------------------------
    # Qdrant helpers
    # ------------------------------------------------------------------

    def _create_collection(self) -> None:
        existing = {c.name for c in self._client.get_collections().collections}
        if self._collection in existing:
            logger.info("Collection %r already exists — skipping create.", self._collection)
            return
        self._client.create_collection(
            collection_name=self._collection,
            vectors_config=VectorParams(size=1, distance=Distance.COSINE),
        )
        for field in _PAYLOAD_INDEX_FIELDS:
            self._client.create_payload_index(
                collection_name=self._collection,
                field_name=field,
                field_schema="keyword",
            )
        logger.info("Created collection %r with payload indexes.", self._collection)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _progress(phase: str, pct: int, message: str, stats: dict) -> dict:
    return {
        "phase":        phase,
        "progress_pct": pct,
        "message":      message,
        "stats":        dict(stats),
    }


def _clamp(val: int, lo: int, hi: int) -> int:
    return max(lo, min(hi, val))
