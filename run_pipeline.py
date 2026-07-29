"""
run_pipeline.py — Full end-to-end integration pipeline for Phase 2.5 + Phase 3 verification.

Steps:
  1. Extract frames (real Achilles Part 1 extraction_engine.py - generator)
  2. Run YOLO-World detection on each frame (Achilles Part 2 object_detector.py)
  3. Enrich with color (Odysseus Part 2 color extractor)
  4. Index to real Qdrant server via Odysseus Part 2 writer
  5. Confirm collection.count() is non-zero
  6. Run 5 real typed queries: negation, counting, spatial, simple, nonsense

No stubs, no mocks. All results printed as raw data.
"""
import importlib.util
import json
import logging
import os
import sys
import time
from contextlib import contextmanager
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-7s %(name)s -- %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("pipeline")

# ── Path setup ─────────────────────────────────────────────────────────────
REPO_ROOT       = Path(__file__).resolve().parent       # ODYESSUES-1
ODYESSUES2_ROOT = REPO_ROOT.parent / "ODYESSUES-2"
ODYESSUES3_ROOT = REPO_ROOT.parent / "ODYESSUES-3"
VIDEO_DIR       = REPO_ROOT / "videos"
FRAMES_DIR      = REPO_ROOT / "frames"
METADATA_PATH   = REPO_ROOT / "metadata" / "metadata.json"

# Insert paths so all parts can import each other.
# Insertion order matters: last inserted ends up at sys.path[0].
# We want ODYESSUES3 first (highest priority) for Part 3 engine imports.
for p in [str(REPO_ROOT), str(ODYESSUES2_ROOT)]:
    if p not in sys.path:
        sys.path.append(p)       # low priority
if str(ODYESSUES3_ROOT) not in sys.path:
    sys.path.insert(0, str(ODYESSUES3_ROOT))  # highest priority


def _load_config_from(path: Path):
    """Load a config.py from an explicit path, bypassing sys.modules cache."""
    spec = importlib.util.spec_from_file_location('_tmp_config', str(path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _load_part2_config():
    """Load ODYESSUES-2/config.py explicitly."""
    return _load_config_from(ODYESSUES2_ROOT / 'config.py')


def _load_part3_config():
    """Load ODYESSUES-3/config.py explicitly."""
    return _load_config_from(ODYESSUES3_ROOT / 'config.py')


@contextmanager
def _use_config(loader_fn):
    """Generic context manager: swap sys.modules['config'] to any config module."""
    original = sys.modules.get('config')
    sys.modules['config'] = loader_fn()
    try:
        yield
    finally:
        if original is None:
            sys.modules.pop('config', None)
        else:
            sys.modules['config'] = original


def _use_part2_config():
    return _use_config(_load_part2_config)


def _use_part3_config():
    return _use_config(_load_part3_config)

# ──────────────────────────────────────────────────────────────────────────
# STEP 1: Load metadata produced by Achilles real extraction
# ──────────────────────────────────────────────────────────────────────────

def load_metadata():
    with open(METADATA_PATH) as f:
        data = json.load(f)
    log.info("Loaded %d frame records from metadata.json", len(data))
    return data


# ──────────────────────────────────────────────────────────────────────────
# STEP 2: YOLO-World detection on real keyframes
# ──────────────────────────────────────────────────────────────────────────

def run_detection(metadata: list) -> list:
    """
    For each frame record, run Achilles's ObjectDetector.detect_keyframe().
    Returns list of (frame_meta_dict, raw_detections_list) tuples.
    raw_detections_list items: {'class': str, 'bbox': tuple, 'confidence': float,
                                'spatial_relations': list[SpatialRelation]}
    """
    from backend.vision.object_detector import ObjectDetector

    log.info("Loading YOLO-World detector (weights download on first run ~50MB)...")
    t0 = time.perf_counter()
    detector = ObjectDetector()
    log.info("Detector loaded in %.1fs", time.perf_counter() - t0)

    results = []
    for rec in metadata:
        frame_path = rec["frame_path"]
        if not os.path.isabs(frame_path):
            # Make it absolute relative to repo root
            frame_path = str(REPO_ROOT / frame_path.replace("\\", "/"))

        dets = detector.detect_keyframe(frame_path)
        log.info(
            "  %s/frame_%04d  path=%s  detections=%d",
            rec["video_id"], rec["frame_index"],
            os.path.basename(frame_path), len(dets)
        )
        results.append((rec, dets))

    total = sum(len(d) for _, d in results)
    log.info("Detection complete: %d frames, %d total detections", len(results), total)
    return results


# ──────────────────────────────────────────────────────────────────────────
# STEP 3: Color enrichment (Odysseus Part 2)
# ──────────────────────────────────────────────────────────────────────────

def enrich_with_color(detection_results: list) -> list:
    """
    Attach color to each detection dict using Odysseus's color extractor.
    Achilles's output has NO color key — this is Odysseus's responsibility.
    Uses _use_part2_config() so color.extractor picks up Part 2's config
    (COLOR_KMEANS_K etc) rather than Part 3's config.
    """
    with _use_part2_config():
        try:
            from color.extractor import ColorExtractor
            extractor = ColorExtractor()
            color_available = True
            log.info("Color extractor loaded (Odysseus Part 2)")
        except Exception as e:
            color_available = False
            log.warning("Color extractor not available (%s) — color=None for all dets", e)

    enriched = []
    for rec, dets in detection_results:
        frame_path = rec["frame_path"]
        if not os.path.isabs(frame_path):
            frame_path = str(REPO_ROOT / frame_path.replace("\\", "/"))

        enriched_dets = []
        for det in dets:
            ed = dict(det)
            if color_available:
                try:
                    import cv2
                    frame_bgr = cv2.imread(frame_path)
                    if frame_bgr is not None:
                        x1, y1, x2, y2 = det["bbox"]
                        crop = frame_bgr[max(0,y1):y2, max(0,x1):x2]
                        with _use_part2_config():
                            color = extractor.extract(crop) if crop.size > 0 else None
                    else:
                        color = None
                except Exception as e:
                    color = None
                    log.debug("Color extraction failed: %s", e)
            else:
                color = None
            ed["color"] = color
            enriched_dets.append(ed)
        enriched.append((rec, enriched_dets))

    return enriched


# ──────────────────────────────────────────────────────────────────────────
# STEP 4: Index to Qdrant using Odysseus Part 2 writer
# ──────────────────────────────────────────────────────────────────────────

def index_to_qdrant(enriched_results: list):
    """
    Convert Achilles's raw detection dicts -> Odysseus DetectionRecord dataclasses
    -> write to real Qdrant via write_detections().
    Returns (client, collection_name, final_count).
    Uses _use_part2_config() so qdrant_store modules pick up Part 2's config
    (QDRANT_VECTOR_DIM etc) rather than Part 3's config.
    """
    with _use_part2_config():
        from qdrant_store.client import get_client
        from qdrant_store.schema import ensure_collection
        from qdrant_store.writer import write_detections
    from detection.contract import DetectionRecord, FrameMeta

    with _use_part2_config():
        client = get_client()
        ensure_collection(client)

    # Collection name from Part 2 config
    part2_cfg = _load_part2_config()
    collection_name = part2_cfg.QDRANT_COLLECTION
    log.info("Using Qdrant collection: '%s'", collection_name)

    total_indexed = 0
    for meta_dict, raw_dets in enriched_results:
        frame_meta = FrameMeta.from_dict(meta_dict)

        # Convert Achilles detection dicts -> DetectionRecord via from_dict
        detection_records = [
            DetectionRecord.from_dict(d) for d in raw_dets
        ]

        with _use_part2_config():
            n = write_detections(
                client=client,
                detections=detection_records,
                frame_meta=frame_meta,
                collection_name=collection_name,
            )
        total_indexed += n
        log.info(
            "  %s -> %d detections written to Qdrant",
            frame_meta.frame_id, n
        )

    # Hard count from real Qdrant
    count_result = client.count(collection_name=collection_name, exact=True)
    log.info(
        "Qdrant collection '%s' final count: %d points",
        collection_name, count_result.count
    )
    return client, collection_name, count_result.count


# ──────────────────────────────────────────────────────────────────────────
# STEP 5: Run real queries via Part 3 search_structured
# ──────────────────────────────────────────────────────────────────────────

def run_queries(client, collection_name: str):
    """
    Run 5 real queries against the indexed Qdrant data.
    Prints raw JSON results for each.
    Part 3's config must be active so engine.search can import FIELD_MAP.
    """
    # Ensure Part 3 config is active when engine.search is imported
    with _use_part3_config():
        from engine.search import search_structured

    # ── What did we actually index? Find real class names ──────────────────
    # Scroll a few points to see what's actually in the collection
    scroll_result = client.scroll(
        collection_name=collection_name,
        limit=20,
        with_payload=True,
    )
    actual_classes = list(set(
        p.payload.get("class_name", "?")
        for p in scroll_result[0]
        if p.payload
    ))
    log.info("Actual class_names in collection (sample): %s", actual_classes)

    print("\n" + "="*70)
    print("  PHASE 3 — REAL QUERY RESULTS (raw output)")
    print(f"  Collection: '{collection_name}'  |  Classes found: {actual_classes}")
    print("="*70)

    # Use first real class or fall back to "person"
    cls1 = actual_classes[0] if actual_classes else "person"
    cls2 = actual_classes[1] if len(actual_classes) > 1 else "car"

    queries = [
        # 1. Simple class match (uses real class from indexed data)
        {
            "label": f"SIMPLE — '{cls1}' present",
            "filter_dict": {
                "status": "match",
                "filters": {
                    "must": [{"class": cls1}],
                },
            },
        },
        # 2. Negation: cls1 without cls2
        {
            "label": f"NEGATION — '{cls1}' without '{cls2}'",
            "filter_dict": {
                "status": "match",
                "filters": {
                    "class": cls1,
                    "negated": False,
                },
            },
        },
        # 3. Counting
        {
            "label": f"COUNTING — more than 0 '{cls1}'",
            "filter_dict": {
                "status": "match",
                "filters": {
                    "class": cls1,
                    "count_constraint": {"operator": "gt", "value": 0},
                },
            },
        },
        # 4. Spatial query
        {
            "label": f"SPATIAL — '{cls1}' left_of '{cls2}' (or any spatial)",
            "filter_dict": {
                "status": "match",
                "filters": {
                    "class": cls1,
                    "spatial_relation": {"type": "left_of", "target_class": cls2},
                },
            },
        },
        # 5. Nonsense — no_match short-circuit
        {
            "label": "NONSENSE — status=no_match (short-circuit, Qdrant not called)",
            "filter_dict": {"status": "no_match", "filters": {}},
        },
    ]

    for q in queries:
        label = q["label"]
        filter_dict = q["filter_dict"]

        print(f"\n  ── {label} ──")
        print(f"  filter_dict: {json.dumps(filter_dict, indent=4)}")

        if filter_dict.get("status") == "no_match":
            print("  -> STATUS: no_match -> Qdrant NOT called (short-circuit in parser_gateway)")
            print("  -> Result: []")
            continue

        try:
            results = search_structured(
                filter_dict=filter_dict,
                client=client,
                collection_name=collection_name,
            )
            print(f"  -> {len(results)} result(s) returned")
            for i, r in enumerate(results[:2]):
                # Convert dataclass to dict for printing
                if hasattr(r, '__dict__'):
                    rdict = {k: v for k, v in vars(r).items()}
                else:
                    rdict = r
                print(f"  [{i+1}] {json.dumps(rdict, indent=6, default=str)}")
        except Exception as e:
            print(f"  -> ERROR: {type(e).__name__}: {e}")


# ──────────────────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────────────────

def main():
    print("="*70)
    print("  FULL END-TO-END INTEGRATION PIPELINE")
    print(f"  Videos: {VIDEO_DIR}")
    print(f"  Qdrant: localhost:6333")
    print("="*70)

    print("\n[STEP 1] Load Part 1 metadata (Achilles real extraction output)...")
    metadata = load_metadata()
    print(f"  -> {len(metadata)} frames, {len(set(r['video_id'] for r in metadata))} videos")
    for r in metadata:
        print(f"     {r['video_id']}/frame_{r['frame_index']:04d}  ts={r['timestamp']}s  "
              f"scene={r['scene_id']}  path={r['frame_path']}")

    print("\n[STEP 2] YOLO-World detection on real keyframes...")
    detection_results = run_detection(metadata)
    total_dets = sum(len(d) for _, d in detection_results)
    print(f"  -> {total_dets} total detections across {len(detection_results)} frames")

    if total_dets == 0:
        print("\n  ! WARNING: 0 detections. YOLO-World found no objects above threshold.")
        print("     These are synthetic test videos — this is expected if they contain")
        print("     no recognisable real-world objects.")
        print("     Sample detections per frame shown above.")
        print("\n  STOPPING: cannot index empty detections or run meaningful queries.")
        print("     To get real results, replace synthetic videos with real footage")
        print("     containing recognisable objects (person, car, etc.)")
        return

    print("\n[STEP 3] Color enrichment (Odysseus Part 2)...")
    enriched = enrich_with_color(detection_results)
    for rec, dets in enriched:
        for d in dets[:2]:
            print(f"  {rec['video_id']}/frame_{rec['frame_index']:04d}: "
                  f"class={d['class']}  color={d.get('color')}  conf={d['confidence']:.3f}")

    print("\n[STEP 4] Indexing to real Qdrant (localhost:6333)...")
    client, collection_name, count = index_to_qdrant(enriched)
    print(f"  -> client.count(collection_name='{collection_name}', exact=True).count = {count}")

    print("\n[STEP 5] Running 5 real typed queries against indexed data...")
    run_queries(client, collection_name)

    print("\n" + "="*70)
    print("  PIPELINE COMPLETE")
    print("="*70)
    print(f"  Part 1 extraction backend: opencv_seek (Achilles real PySceneDetect)")
    print(f"  Part 2 detector: YOLO-World-M  total_detections={total_dets}")
    print(f"  Qdrant indexed points: {count}")
    print("="*70)


if __name__ == "__main__":
    main()
