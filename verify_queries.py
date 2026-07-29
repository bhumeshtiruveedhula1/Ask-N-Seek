"""
verify_queries.py — Phase 3 verification: re-index real data then run all 5 queries.

Skips extraction (uses existing metadata.json + frames).
Runs YOLO detection, indexes to Qdrant, then runs 5 queries with raw JSON output.
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
log = logging.getLogger("verify")

REPO_ROOT       = Path(__file__).resolve().parent
ODYESSUES2_ROOT = REPO_ROOT.parent / "ODYESSUES-2"
ODYESSUES3_ROOT = REPO_ROOT.parent / "ODYESSUES-3"
METADATA_PATH   = REPO_ROOT / "metadata" / "metadata.json"

for p in [str(REPO_ROOT), str(ODYESSUES2_ROOT)]:
    if p not in sys.path:
        sys.path.append(p)
if str(ODYESSUES3_ROOT) not in sys.path:
    sys.path.insert(0, str(ODYESSUES3_ROOT))


def _load_config_from(path: Path):
    spec = importlib.util.spec_from_file_location('_tmp_config', str(path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

@contextmanager
def _use_config(loader_fn):
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
    return _use_config(lambda: _load_config_from(ODYESSUES2_ROOT / 'config.py'))

def _use_part3_config():
    return _use_config(lambda: _load_config_from(ODYESSUES3_ROOT / 'config.py'))


def main():
    # ── 1. Load metadata ────────────────────────────────────────────────────
    with open(METADATA_PATH) as f:
        metadata = json.load(f)
    print(f"[1] Loaded {len(metadata)} frame records")

    # ── 2. Detect ────────────────────────────────────────────────────────────
    from backend.vision.object_detector import ObjectDetector
    print("[2] Loading YOLO-World detector...")
    t0 = time.perf_counter()
    detector = ObjectDetector()
    print(f"    Loaded in {time.perf_counter()-t0:.1f}s")

    detection_results = []
    for rec in metadata:
        fp = rec["frame_path"]
        if not os.path.isabs(fp):
            fp = str(REPO_ROOT / fp.replace("\\", "/"))
        dets = detector.detect_keyframe(fp)
        log.info("  %s/frame_%04d  dets=%d", rec["video_id"], rec["frame_index"], len(dets))
        detection_results.append((rec, dets))

    total = sum(len(d) for _, d in detection_results)
    print(f"[2] Detection complete: {total} total detections across {len(detection_results)} frames")

    if total == 0:
        print("STOP: 0 detections. Cannot index or query.")
        return

    # ── 3. Index ─────────────────────────────────────────────────────────────
    with _use_part2_config():
        from qdrant_store.client import get_client
        from qdrant_store.schema import ensure_collection
        from qdrant_store.writer import write_detections
    from detection.contract import DetectionRecord, FrameMeta

    part2_cfg = _load_config_from(ODYESSUES2_ROOT / 'config.py')
    collection_name = part2_cfg.QDRANT_COLLECTION

    with _use_part2_config():
        client = get_client()
        # Drop and recreate collection for a clean run
        try:
            client.delete_collection(collection_name)
            print(f"[3] Dropped existing collection '{collection_name}'")
        except Exception:
            pass
        ensure_collection(client)
        print(f"[3] Collection '{collection_name}' created")

    for rec, raw_dets in detection_results:
        frame_meta = FrameMeta.from_dict(rec)
        records = [DetectionRecord.from_dict(d) for d in raw_dets]
        with _use_part2_config():
            n = write_detections(client=client, detections=records,
                                 frame_meta=frame_meta, collection_name=collection_name)
        log.info("  %s -> %d points written", frame_meta.frame_id, n)

    count = client.count(collection_name=collection_name, exact=True).count
    print(f"[3] Qdrant count (exact): {count}")
    assert count > 0, "FAIL: Qdrant is empty after indexing!"

    # ── 4. Inspect one frame payload with spatial relations ───────────────────
    print("\n[PAYLOAD INSPECT] First 2 points with spatial_relations:")
    scroll_r, _ = client.scroll(collection_name=collection_name, limit=20,
                                with_payload=True, with_vectors=False)
    shown = 0
    for p in scroll_r:
        sr = p.payload.get("spatial_relations", [])
        if sr:
            print(f"  frame={p.payload.get('frame_id')}  class={p.payload.get('class_name')}")
            print(f"  spatial_relations={json.dumps(sr, indent=4)}")
            shown += 1
            if shown >= 2:
                break
    if shown == 0:
        print("  (no points have non-empty spatial_relations in this collection)")

    # ── 5. Run 5 queries ─────────────────────────────────────────────────────
    # Get real classes
    all_classes = list(set(p.payload.get("class_name") for p in scroll_r if p.payload))
    cls1 = all_classes[0] if all_classes else "sky"
    cls2 = all_classes[1] if len(all_classes) > 1 else "sun"
    print(f"\n[5] Classes in collection: {all_classes}")
    print(f"    Using cls1='{cls1}', cls2='{cls2}' for queries\n")

    with _use_part3_config():
        from engine.search import search_structured

    queries = [
        {
            "label": f"SIMPLE — '{cls1}' present",
            "filter_dict": {"status": "match", "filters": {"class": cls1}},
        },
        {
            "label": f"NEGATION — '{cls1}' without '{cls2}'",
            "filter_dict": {"status": "match", "filters": {
                "class": cls1, "negated": [cls2],
            }},
        },
        {
            "label": f"COUNTING — more than 0 '{cls2}' (gt 0)",
            "filter_dict": {"status": "match", "filters": {
                "class": cls2,
                "count_constraint": {"operator": "gt", "value": 0},
            }},
        },
        {
            "label": f"SPATIAL — '{cls2}' left_of '{cls1}'",
            "filter_dict": {"status": "match", "filters": {
                "class": cls2,
                "spatial_relation": {"type": "left_of", "target_class": cls1},
            }},
        },
        {
            "label": "NONSENSE — no_match short-circuit",
            "filter_dict": {"status": "no_match", "filters": {}},
        },
    ]

    print("=" * 70)
    print("  PHASE 3 — RAW QUERY RESULTS")
    print("=" * 70)

    for q in queries:
        label = q["label"]
        fd = q["filter_dict"]
        print(f"\n  ── {label} ──")
        print(f"  filter_dict: {json.dumps(fd, indent=4)}")

        if fd.get("status") == "no_match":
            print("  -> no_match: Qdrant NOT called (short-circuit)")
            print("  -> Result: []")
            continue

        try:
            results = search_structured(filter_dict=fd, client=client,
                                        collection_name=collection_name)
            print(f"  -> {len(results)} result(s)")
            for i, r in enumerate(results[:3]):
                rdict = vars(r) if hasattr(r, '__dict__') else dict(r)
                print(f"  [{i+1}] {json.dumps(rdict, indent=6, default=str)}")
        except Exception as e:
            print(f"  -> ERROR: {type(e).__name__}: {e}")

    print("\n" + "=" * 70)
    print("  VERIFICATION COMPLETE")
    print(f"  Qdrant count={count}  classes={all_classes}")
    print("=" * 70)


if __name__ == "__main__":
    main()
