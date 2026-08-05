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

import concurrent.futures
import cv2
import numpy as np
import time

import config as _config

from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams

from backend.ingestion.extraction_engine import extract_frames
from backend.vision.color_extractor import extract_color
from backend.vision.object_detector import get_detector, ObjectDetector
from backend.vision.vocabulary import SYNONYM_MAP
from engine.qdrant_gateway import make_judge_collection_name

logger = logging.getLogger(__name__)

_DUMMY_VECTOR: list[float] = [0.0]
_PAYLOAD_INDEX_FIELDS = ("class_name", "color", "spatial_relations")
_BATCH_SIZE = 100          # Qdrant upsert batch size


# ---------------------------------------------------------------------------
# Secondary NMS deduplication (Fix 1)
# ---------------------------------------------------------------------------
# YOLO-World's internal NMS at IoU=0.45 lets marginally overlapping zero-shot
# boxes through. A single bottle can produce 3-5 detections with IoU 0.50-0.60,
# inflating max_concurrent. This secondary pass at 0.65 merges same-object
# duplicates while preserving distinct nearby objects.

def _calculate_iou(box_a: tuple, box_b: tuple) -> float:
    """Intersection over Union for two (x1,y1,x2,y2) boxes."""
    x1 = max(box_a[0], box_b[0])
    y1 = max(box_a[1], box_b[1])
    x2 = min(box_a[2], box_b[2])
    y2 = min(box_a[3], box_b[3])
    inter = max(0, x2 - x1) * max(0, y2 - y1)
    area_a = (box_a[2] - box_a[0]) * (box_a[3] - box_a[1])
    area_b = (box_b[2] - box_b[0]) * (box_b[3] - box_b[1])
    union = area_a + area_b - inter
    return inter / union if union > 0 else 0.0


def _calculate_ioa(small_box: tuple, large_box: tuple) -> float:
    """Intersection over Area of small_box (0.0-1.0). Used for accessory parent binding."""
    x1 = max(small_box[0], large_box[0])
    y1 = max(small_box[1], large_box[1])
    x2 = min(small_box[2], large_box[2])
    y2 = min(small_box[3], large_box[3])
    inter = max(0, x2 - x1) * max(0, y2 - y1)
    area_small = (small_box[2] - small_box[0]) * (small_box[3] - small_box[1])
    return inter / area_small if area_small > 0 else 0.0


# Accessory classes: small items that sit inside a person's bounding box.
# IoA-based parent binding keeps one accessory per person instead of per detection.
_ACCESSORY_CLASSES: frozenset[str] = frozenset({
    "necklace", "glasses", "watch", "bracelet", "earring",
})

# All person-role classes (post synonym-map resolution) that can be accessory parents.
_PERSON_CLASSES: frozenset[str] = frozenset({
    "person", "man", "woman", "child", "boy", "girl", "baby",
    "firefighter", "traffic warden", "police", "officer", "soldier",
    "worker", "construction worker", "chef", "doctor", "nurse",
    "patient", "student", "teacher", "pedestrian",
})


def _deduplicate_detections(
    detections: list[dict],
    iou_thresh: float = 0.65,
) -> list[dict]:
    """
    Secondary NMS with IoA-based parent binding for accessories.

    For non-accessories: class-grouped greedy NMS at iou_thresh (unchanged).
    For accessories (necklace, glasses, watch, bracelet, earring):
      - Bind each to its containing person box via IoA > 0.50.
      - Keep only the highest-confidence detection per (accessory_class, person).
      - Accessories with no parent fall back to standard NMS.
    This prevents necklace x4 when two people stand side by side.
    """
    if not detections:
        return detections

    # ── Split accessories from non-accessories ──────────────────────────────
    accs   = [d for d in detections if (d.get("class") or d.get("class_name")) in _ACCESSORY_CLASSES]
    others = [d for d in detections if (d.get("class") or d.get("class_name")) not in _ACCESSORY_CLASSES]

    # ── Standard class-grouped NMS on non-accessories ───────────────────────
    by_class: dict[str, list[dict]] = {}
    for d in others:
        cls = d.get("class") or d.get("class_name", "unknown")
        by_class.setdefault(cls, []).append(d)

    deduped_others: list[dict] = []
    for cls_dets in by_class.values():
        cls_dets.sort(key=lambda x: x.get("confidence", 0), reverse=True)
        keep: list[dict] = []
        for det in cls_dets:
            bbox = det.get("bbox") or det.get("box")
            if not bbox or len(bbox) != 4:
                keep.append(det)
                continue
            overlap = any(
                len(k.get("bbox") or k.get("box", [])) == 4
                and _calculate_iou(bbox, k.get("bbox") or k.get("box")) > iou_thresh
                for k in keep
            )
            if not overlap:
                keep.append(det)
        deduped_others.extend(keep)

    # ── Find person boxes from the deduped non-accessory set ────────────────
    person_boxes = [
        d for d in deduped_others
        if (d.get("class") or d.get("class_name")) in _PERSON_CLASSES
    ]

    # ── Bind accessories to parent person via IoA > 0.50 ───────────────────
    # Group: (accessory_class, id(parent_person)) → keep highest confidence
    grouped: dict[tuple[str, int], list[dict]] = {}
    orphan_accs: list[dict] = []

    for acc in accs:
        abox = acc.get("bbox") or acc.get("box")
        if not abox or len(abox) != 4:
            orphan_accs.append(acc)
            continue
        best_parent = None
        best_ioa = 0.0
        for person in person_boxes:
            pbox = person.get("bbox") or person.get("box")
            if not pbox or len(pbox) != 4:
                continue
            ioa = _calculate_ioa(abox, pbox)
            if ioa > best_ioa and ioa > 0.50:
                best_ioa = ioa
                best_parent = person
        if best_parent is not None:
            key = (acc.get("class") or acc.get("class_name", "unknown"), id(best_parent))
            grouped.setdefault(key, []).append(acc)
        else:
            orphan_accs.append(acc)

    deduped_accs: list[dict] = []
    for group in grouped.values():
        group.sort(key=lambda x: x.get("confidence", 0), reverse=True)
        deduped_accs.append(group[0])

    # ── Fallback standard NMS on orphan accessories (no parent found) ───────
    if orphan_accs:
        orphan_by_class: dict[str, list[dict]] = {}
        for d in orphan_accs:
            cls = d.get("class") or d.get("class_name", "unknown")
            orphan_by_class.setdefault(cls, []).append(d)
        for cls_dets in orphan_by_class.values():
            cls_dets.sort(key=lambda x: x.get("confidence", 0), reverse=True)
            keep: list[dict] = []
            for det in cls_dets:
                bbox = det.get("bbox") or det.get("box")
                if not bbox or len(bbox) != 4:
                    keep.append(det)
                    continue
                overlap = any(
                    len(k.get("bbox") or k.get("box", [])) == 4
                    and _calculate_iou(bbox, k.get("bbox") or k.get("box")) > iou_thresh
                    for k in keep
                )
                if not overlap:
                    keep.append(det)
            deduped_accs.extend(keep)

    n_before = len(detections)
    n_after  = len(deduped_others) + len(deduped_accs)
    if n_after < n_before:
        logger.debug("[dedup] %d → %d detections (dropped %d duplicates)",
                     n_before, n_after, n_before - n_after)
    return deduped_others + deduped_accs


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

            # Fix A: Canonicalize class names at ingestion using SYNONYM_MAP.
            # YOLO detects "man"/"woman" but Qdrant must store "person" so that
            # user queries for "person" return results.
            # Without this, SYNONYM_MAP only helped at query time — the DB had
            # "man" stored, so "person" filter returned 0 results.
            for det in dets:
                raw_cls = det.get("class", "unknown")
                det["class"] = SYNONYM_MAP.get(raw_cls, raw_cls)

            # Conditional NMS: new IoA-based accessory dedup (Bug 4 fix).
            # _ACCESSORY_CLASSES now at module level; _deduplicate_detections
            # handles parent binding internally — call site unchanged.
            if any(d.get("class", "") in _ACCESSORY_CLASSES for d in dets):
                dets = _deduplicate_detections(dets, iou_thresh=0.40)
            else:
                dets = _deduplicate_detections(dets, iou_thresh=0.55)
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
        _color_phase_start = time.time()
        yield _progress("color", 60, "Extracting dominant colors…", stats)

        # Task 1: Per-class confidence gates.
        # CLASS_CONFIDENCE_GATES overrides EARLY_CONFIDENCE_FILTER for attractor
        # classes (bat, kite, skis, frisbee, rod, stick) that hallucinate at
        # confidence 0.30-0.44. Keys match post-canonicalization names.
        ecf   = getattr(_config, "EARLY_CONFIDENCE_FILTER", 0.30)
        gates = getattr(_config, "CLASS_CONFIDENCE_GATES", {})
        for fp in list(detections_map.keys()):
            all_dets = detections_map[fp]
            filtered = []
            for d in all_dets:
                conf     = d.get("confidence", 0)
                cls_name = d.get("class", "")
                gate     = gates.get(cls_name, ecf)  # per-class or global floor
                if conf >= gate:
                    filtered.append(d)
            n_dropped = len(all_dets) - len(filtered)
            if n_dropped:
                logger.debug("Conf gate: dropped %d dets from %s", n_dropped, os.path.basename(fp))
            detections_map[fp] = filtered


        # ── Optimization 2: Parallel color extraction per frame ──────────
        # Each frame's detections are color-extracted in parallel using a
        # thread pool (cv2/numpy release the GIL for most operations).
        color_map: dict[str, list[str]] = {}

        def _extract_frame_colors(record: dict) -> tuple[str, list[str]]:
            """Worker: read frame from disk, run extract_color for each det."""
            fp   = record["frame_path"]
            dets = detections_map.get(fp, [])
            if not dets:
                return fp, []
            frame_bgr = cv2.imread(fp)
            if frame_bgr is None:
                return fp, ["unknown"] * len(dets)
            colors = []
            for det in dets:
                try:
                    # Bundle 2 call-site: pass class_name for class-aware crop
                    c = extract_color(frame_bgr, det["bbox"], class_name=det.get("class"))
                except Exception:  # noqa: BLE001
                    c = "unknown"
                colors.append(c)
            return fp, colors

        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
            futures = {executor.submit(_extract_frame_colors, r): r for r in frame_records}
            for future in concurrent.futures.as_completed(futures):
                fp, cols = future.result()
                color_map[fp] = cols

        _color_phase_elapsed = time.time() - _color_phase_start
        yield _progress("color", 75, f"Color extraction complete in {_color_phase_elapsed:.2f}s.", stats)

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

        top_classes_raw = sorted(
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
        )

        # Fix C: Suppress single-frame hallucinations from quick chips.
        # Classes seen in only 1 frame are almost certainly false positives
        # from YOLO-World's zero-shot mode on unfamiliar objects.
        min_frames = getattr(_config, "MIN_FRAME_PRESENCE", 2)
        top_classes = [c for c in top_classes_raw if c["frames_detected"] >= min_frames]
        filtered_count = len(top_classes_raw) - len(top_classes)
        if filtered_count:
            filtered_names = [c["class"] for c in top_classes_raw
                              if c["frames_detected"] < min_frames]
            logger.debug("Filtered %d single-frame class(es) from top_classes: %s",
                         filtered_count, filtered_names)
        top_classes = top_classes[:10]

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
