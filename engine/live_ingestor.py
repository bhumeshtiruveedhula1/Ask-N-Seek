"""
engine/live_ingestor.py — Live Judge-Video Ingestion Orchestrator
=================================================================

Wires the existing pipeline components into a single streaming ingest loop:
  extract_frames → ObjectDetector → extract_color → compute_spatial_relations → Qdrant upsert

Designed for the Live Ingest tab in the Gradio UI. Calls progress_cb after
each frame so the UI can stream updates in near-real-time.

Architecture constraints (do NOT break):
  - extract_frames() is the only frame extraction mechanism — do not re-implement.
  - ObjectDetector is the only detection path — do not add new ML models.
  - Qdrant payload schema mirrors the existing stub_data.py shape exactly.
  - Dummy vector [0.0] (size=1, COSINE) — all retrieval is payload-filter based.
  - asyncio.sleep(0) is used as a cooperative yield after each frame.
"""

from __future__ import annotations

import logging
import os
import tempfile
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, Generator, List, Optional

# Pipeline component imports — at module level so they are patchable in tests
from backend.ingestion.extraction_engine import extract_frames
from backend.vision.color_extractor import extract_color

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# IngestProgress dataclass
# ---------------------------------------------------------------------------

@dataclass
class IngestProgress:
    """Snapshot of ingestion state emitted after each phase/frame."""
    phase: str            # machine-readable: "scene_detection", "extraction", etc.
    phase_human: str      # human label for UI display
    percent: float        # 0.0 → 100.0
    log_lines: List[str]  # rolling log buffer (newest last)
    session_id: str       # UUID of this ingest session
    video_id: str         # stem of the uploaded video filename
    stats: Dict[str, Any]
    complete: bool = False
    error: Optional[str] = None


# ---------------------------------------------------------------------------
# IngestConfig
# ---------------------------------------------------------------------------

@dataclass
class IngestConfig:
    """Runtime configuration for a single ingest run."""
    frames_output_dir: str       # where frames are written
    max_log_lines: int = 200     # rolling buffer size
    yield_every_n_frames: int = 1  # emit progress every N frames (1 = every frame)


# ---------------------------------------------------------------------------
# DemoNarrator
# ---------------------------------------------------------------------------

class DemoNarrator:
    """
    Prints presenter narration lines to stdout as each pipeline phase starts.
    Purely for demo convenience — does not affect the ingest result.
    """
    SCRIPT: Dict[str, List[str]] = {
        "scene_detection": [
            "▶ The system is analyzing scene boundaries using PySceneDetect...",
            "  (ContentDetector threshold=27.0, downscale×2 for speed)",
        ],
        "extraction": [
            "▶ Seeking to each keyframe with OpenCV CAP_PROP_POS_MSEC...",
            "  (1 FPS fallback for long static shots, 720p height cap)",
        ],
        "detection": [
            "▶ YOLO-World-M is running against the 800-term vocabulary...",
            "  (Offline, CPU/GPU — no cloud calls)",
        ],
        "color": [
            "▶ CIELAB center-weighted color extraction per bbox...",
        ],
        "spatial": [
            "▶ Computing left_of / right_of spatial relations (top-4 confidence pairs)...",
        ],
        "indexing": [
            "▶ Pushing structured facts into Qdrant — payload filters, not embeddings...",
            "  (judge_session collection: ephemeral, isolated per run)",
        ],
        "complete": [
            "▶ Ingest complete. Query the video using natural language!",
        ],
    }

    def narrate(self, phase: str) -> None:
        lines = self.SCRIPT.get(phase, [])
        for line in lines:
            print(f"[DemoNarrator] {line}", flush=True)


# ---------------------------------------------------------------------------
# LiveIngestor
# ---------------------------------------------------------------------------

class LiveIngestor:
    """
    Orchestrates the full ingestion pipeline for a single video.

    Usage (synchronous generator):
        ingestor = LiveIngestor()
        for progress in ingestor.ingest(video_path, config):
            update_ui(progress)

    The ingestor is stateless across calls — create once, reuse freely.
    """

    def __init__(self) -> None:
        self._narrator = DemoNarrator()
        # Lazy-loaded singletons (avoid paying import cost at module load)
        self._detector = None

    def _get_detector(self):
        """Lazy-load ObjectDetector singleton (loads YOLO weights once)."""
        if self._detector is None:
            from backend.vision.object_detector import ObjectDetector
            self._detector = ObjectDetector()
        return self._detector

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def ingest(
        self,
        video_path: str | Path,
        config: IngestConfig,
        progress_cb: Optional[Callable[[IngestProgress], None]] = None,
    ) -> Generator[IngestProgress, None, None]:
        """
        Run the full ingestion pipeline and yield IngestProgress snapshots.

        Parameters
        ----------
        video_path : str | Path
            Absolute path to the source video file.
        config : IngestConfig
            Runtime configuration (output dirs, log buffer size, etc.).
        progress_cb : optional callback
            Called synchronously after each yield (for non-generator use).

        Yields
        ------
        IngestProgress — one after each phase start, and after each frame processed.
        On completion, yields a final progress with complete=True.
        On error, yields a progress with error set and complete=True.

        Returns
        -------
        The final complete IngestProgress (also the last yielded value).
        """
        video_path = str(Path(video_path).resolve())
        video_id = Path(video_path).stem
        session_id = str(uuid.uuid4())
        log: List[str] = []
        stats: Dict[str, Any] = {
            "scenes": 0,
            "keyframes": 0,
            "objects_detected": 0,
            "frames_indexed": 0,
            "elapsed_s": 0.0,
        }
        t_start = time.perf_counter()

        def _snap(phase: str, human: str, pct: float,
                  complete: bool = False, error: Optional[str] = None) -> IngestProgress:
            stats["elapsed_s"] = round(time.perf_counter() - t_start, 2)
            p = IngestProgress(
                phase=phase,
                phase_human=human,
                percent=min(pct, 100.0),
                log_lines=list(log[-config.max_log_lines:]),
                session_id=session_id,
                video_id=video_id,
                stats=dict(stats),
                complete=complete,
                error=error,
            )
            if progress_cb:
                progress_cb(p)
            return p

        def _log(line: str) -> None:
            log.append(line)
            logger.info("[live_ingestor] %s", line)

        # ── Validate input ──────────────────────────────────────────────
        if not os.path.isfile(video_path):
            _log(f"❌ File not found: {video_path}")
            snap = _snap("error", "Error: file not found", 0.0, complete=True,
                         error=f"File not found: {video_path}")
            yield snap
            return

        _log(f"🎬 Starting ingest: {os.path.basename(video_path)}")
        _log(f"   Session: {session_id[:8]}…")
        yield _snap("init", "⚙️ Initializing…", 0.0)

        # ── Import pipeline components ─────────────────────────────────
        try:
            from qdrant_client import QdrantClient
            from qdrant_client.models import Distance, VectorParams, PointStruct
        except ImportError as exc:
            _log(f"❌ Import error: {exc}")
            yield _snap("error", f"Import error: {exc}", 0.0, complete=True, error=str(exc))
            return

        # ── Create ephemeral Qdrant collection ─────────────────────────
        from engine.qdrant_gateway import make_judge_collection_name
        collection_name = make_judge_collection_name()
        qdrant_client = QdrantClient(":memory:")  # In-memory for judge sessions

        try:
            qdrant_client.create_collection(
                collection_name,
                vectors_config=VectorParams(size=1, distance=Distance.COSINE),
            )
            _log(f"✅ Qdrant collection created: {collection_name[:28]}…")
        except Exception as exc:
            _log(f"❌ Qdrant collection creation failed: {exc}")
            yield _snap("error", f"Qdrant error: {exc}", 0.0, complete=True, error=str(exc))
            return

        # ── Phase: Scene Detection ─────────────────────────────────────
        self._narrator.narrate("scene_detection")
        _log("🔍 Phase 1/5: Scene detection (PySceneDetect)…")
        yield _snap("scene_detection", "🔍 Detecting scenes…", 5.0)

        # ── Phase: Frame Extraction ────────────────────────────────────
        self._narrator.narrate("extraction")
        _log("🖼  Phase 2/5: Frame extraction (OpenCV seek)…")
        yield _snap("extraction", "🖼 Extracting keyframes…", 10.0)

        # ── Phase: Detection + Color + Spatial + Index ─────────────────
        self._narrator.narrate("detection")
        _log("🤖 Phase 3/5: Object detection (YOLO-World-M)…")

        try:
            detector = self._get_detector()
        except Exception as exc:
            _log(f"❌ Failed to load ObjectDetector: {exc}")
            yield _snap("error", f"Model load error: {exc}", 10.0, complete=True, error=str(exc))
            return

        _log(f"✅ YOLO-World-M ready (vocab={len(detector._model.names)} classes)")
        yield _snap("detection", "🤖 Detecting objects…", 15.0)

        # Run extraction as generator — process each frame as it arrives
        frames_dir = str(Path(config.frames_output_dir) / video_id)
        os.makedirs(frames_dir, exist_ok=True)

        qdrant_points: List[PointStruct] = []
        frame_count = 0
        max_scenes_seen = 0
        batch_size = 50  # upsert in batches to avoid memory buildup

        try:
            frame_generator = extract_frames(video_path, config.frames_output_dir)

            for frame_record in frame_generator:
                frame_count += 1
                f_idx   = frame_record["frame_index"]
                f_ts    = frame_record["timestamp"]
                f_scene = frame_record["scene_id"]
                f_path  = frame_record["frame_path"]
                f_vid   = frame_record["video_id"]

                max_scenes_seen = max(max_scenes_seen, f_scene + 1)
                stats["keyframes"] = frame_count
                stats["scenes"] = max_scenes_seen

                # ── Detection ──────────────────────────────────────────
                try:
                    import cv2
                    frame_bgr = cv2.imread(f_path)
                    if frame_bgr is None:
                        _log(f"⚠️  Could not read frame {f_path}")
                        continue

                    detections = detector.detect(frame_bgr, frame_path=f_path)
                    del frame_bgr  # free memory immediately
                except Exception as exc:
                    _log(f"⚠️  Detection error frame {f_idx}: {exc}")
                    detections = []

                # ── Color extraction ───────────────────────────────────
                if detections:
                    try:
                        import cv2
                        frame_bgr_color = cv2.imread(f_path)
                        if frame_bgr_color is not None:
                            for det in detections:
                                bbox = det.get("bbox", None)
                                if bbox:
                                    color = extract_color(frame_bgr_color, tuple(bbox))
                                else:
                                    color = "unknown"
                                det["color"] = color
                            del frame_bgr_color
                    except Exception as exc:
                        logger.warning("Color extraction error frame %d: %s", f_idx, exc)
                        for det in detections:
                            det["color"] = "unknown"

                # ── Spatial relations (already in detections from detect()) ──
                # ObjectDetector.detect() already calls compute_spatial_relations
                # and attaches to detection["spatial_relations"]. No re-compute needed.

                # ── Build Qdrant payload per detection ─────────────────
                n_objs = len(detections)
                stats["objects_detected"] = stats.get("objects_detected", 0) + n_objs

                # Normalise bbox to [0,1] for storage
                h_cap, w_cap = 720, 1280  # approximate; actual values from frame

                for det_idx, det in enumerate(detections):
                    raw_bbox = det.get("bbox", [0, 0, 1, 1])
                    # bbox is pixel coords (x1,y1,x2,y2) from ObjectDetector
                    # Store as-is (pixel coords) to match existing stub schema
                    bbox_stored = list(raw_bbox)

                    spatial_relations = det.get("spatial_relations", [])
                    # Serialize spatial relations to plain dicts
                    sr_payload = []
                    for rel in spatial_relations:
                        sr_payload.append({
                            "relation": rel.get("relation", ""),
                            "subject":  rel.get("subject", ""),
                            "object_":  rel.get("object_", ""),
                        })

                    point_id = str(uuid.uuid5(
                        uuid.UUID("b2c3d4e5-f6a7-8901-bcde-f12345678901"),
                        f"{session_id}:{f_vid}:{f_idx}:{det_idx}",
                    ))
                    # Qdrant UUIDs must be valid UUID strings
                    payload = {
                        "video_id":          f_vid,
                        "frame_index":       f_idx,
                        "timestamp":         f_ts,
                        "scene_id":          f_scene,
                        "frame_path":        f_path,
                        "frame_id":          f"{f_vid}_{f_idx:04d}",
                        "class_name":        det.get("class", "unknown"),
                        "color":             det.get("color", "unknown"),
                        "confidence":        float(det.get("confidence", 0.0)),
                        "bbox":              bbox_stored,
                        "spatial_relations": sr_payload,
                        "session_id":        session_id,
                    }
                    qdrant_points.append(
                        PointStruct(id=point_id, vector=[0.0], payload=payload)
                    )

                # ── Batch upsert when batch is full ────────────────────
                if len(qdrant_points) >= batch_size:
                    try:
                        qdrant_client.upsert(collection_name, qdrant_points)
                        stats["frames_indexed"] = stats.get("frames_indexed", 0) + len(qdrant_points)
                        qdrant_points = []
                    except Exception as exc:
                        _log(f"⚠️  Qdrant batch upsert error: {exc}")

                # ── Emit progress every N frames ───────────────────────
                if frame_count % config.yield_every_n_frames == 0:
                    pct = min(15.0 + (frame_count * 75.0 / max(frame_count + 1, 1)), 90.0)
                    det_msg = f"({n_objs} obj)" if n_objs else "(no detections)"
                    _log(
                        f"  [{frame_count:4d}] scene={f_scene} ts={f_ts:.1f}s "
                        f"→ {n_objs} obj {det_msg}"
                    )
                    yield _snap(
                        "detection",
                        f"🤖 Frame {frame_count} | {n_objs} objects detected",
                        pct,
                    )

        except FileNotFoundError as exc:
            _log(f"❌ Video file error: {exc}")
            yield _snap("error", f"File error: {exc}", 0.0, complete=True, error=str(exc))
            return
        except Exception as exc:
            _log(f"❌ Pipeline error: {exc}")
            yield _snap("error", f"Pipeline error: {exc}", 90.0, complete=True, error=str(exc))
            return

        # ── Phase: Index remaining points ─────────────────────────────
        self._narrator.narrate("indexing")
        _log(f"📦 Phase 4/5: Indexing {len(qdrant_points)} remaining objects into Qdrant…")
        yield _snap("indexing", "📦 Indexing into Qdrant…", 92.0)

        if qdrant_points:
            try:
                qdrant_client.upsert(collection_name, qdrant_points)
                stats["frames_indexed"] = stats.get("frames_indexed", 0) + len(qdrant_points)
            except Exception as exc:
                _log(f"⚠️  Final Qdrant upsert error: {exc}")

        # ── Phase: Complete ────────────────────────────────────────────
        self._narrator.narrate("complete")
        elapsed = time.perf_counter() - t_start
        stats["elapsed_s"] = round(elapsed, 2)
        stats["scenes"] = max_scenes_seen

        _log(f"✅ Ingest complete in {elapsed:.1f}s")
        _log(f"   Scenes: {max_scenes_seen}  |  Keyframes: {frame_count}")
        _log(f"   Objects detected: {stats['objects_detected']}")
        _log(f"   Collection: {collection_name[:36]}")
        _log(f"   Ready to search! Query this video now.")

        final = _snap("complete", "✅ Ready to search!", 100.0, complete=True)
        # Attach the collection name so the UI can wire the search client
        final.stats["collection_name"] = collection_name
        final.stats["qdrant_client_ref"] = id(qdrant_client)

        yield final

        # Store the client on the ingestor so the UI can retrieve it
        self._last_client = qdrant_client
        self._last_collection = collection_name

    # ------------------------------------------------------------------
    # Post-ingest accessors (called by UI after ingest completes)
    # ------------------------------------------------------------------

    @property
    def last_client(self):
        return getattr(self, "_last_client", None)

    @property
    def last_collection(self) -> Optional[str]:
        return getattr(self, "_last_collection", None)
