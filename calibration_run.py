"""
calibration_run.py — Run 10 valid + 5 nonsense queries, compute threshold.

Architecture §7 formula: threshold = max(nonsense_top_scores) + margin
Margin = 0.05 (locked in calibration.py)

Reports raw scores per query and the computed threshold.
"""
import importlib.util
import json
import sys
from contextlib import contextmanager
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent
ODYESSUES2_ROOT = REPO_ROOT.parent / "ODYESSUES-2"
ODYESSUES3_ROOT = REPO_ROOT.parent / "ODYESSUES-3"

for p in [str(REPO_ROOT), str(ODYESSUES2_ROOT)]:
    if p not in sys.path:
        sys.path.append(p)
if str(ODYESSUES3_ROOT) not in sys.path:
    sys.path.insert(0, str(ODYESSUES3_ROOT))

def _load_config_from(path):
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

def use_part2():
    return _use_config(lambda: _load_config_from(ODYESSUES2_ROOT / 'config.py'))

def use_part3():
    return _use_config(lambda: _load_config_from(ODYESSUES3_ROOT / 'config.py'))


def main():
    from qdrant_client import QdrantClient

    with use_part2():
        from qdrant_store.client import get_client
        client = get_client()

    part2_cfg = _load_config_from(ODYESSUES2_ROOT / 'config.py')
    collection_name = part2_cfg.QDRANT_COLLECTION

    count = client.count(collection_name=collection_name, exact=True).count
    print(f"Qdrant collection '{collection_name}' — count={count}")

    if count == 0:
        print("STOP: collection is empty. Run verify_queries.py first to index data.")
        return

    # What's in the collection?
    scroll_r, _ = client.scroll(collection_name=collection_name, limit=50,
                                with_payload=True, with_vectors=False)
    all_classes = list(set(p.payload.get("class_name") for p in scroll_r if p.payload))
    print(f"Classes in collection: {all_classes}\n")

    with use_part3():
        from engine.search import search_structured

    MARGIN = 0.05  # Architecture §7 locked margin

    # ─────────────────────────────────────────────────────────────────
    # 10 VALID QUERIES (diverse across query types)
    # ─────────────────────────────────────────────────────────────────
    valid_queries = [
        # Simple class match
        {"label": "V1: sky present", "filter_dict": {"status": "match", "filters": {"class": "sky"}}},
        {"label": "V2: sun present", "filter_dict": {"status": "match", "filters": {"class": "sun"}}},
        # Counting — gt 0 (trivially satisfied: 1 sky per frame)
        {"label": "V3: sky gt 0", "filter_dict": {"status": "match", "filters": {
            "class": "sky", "count_constraint": {"operator": "gt", "value": 0}}}},
        {"label": "V4: sun gt 0", "filter_dict": {"status": "match", "filters": {
            "class": "sun", "count_constraint": {"operator": "gt", "value": 0}}}},
        # Counting — gte 1 (equivalent to gt 0)
        {"label": "V5: sky gte 1", "filter_dict": {"status": "match", "filters": {
            "class": "sky", "count_constraint": {"operator": "gte", "value": 1}}}},
        # Spatial
        {"label": "V6: sun left_of sky", "filter_dict": {"status": "match", "filters": {
            "class": "sun", "spatial_relation": {"type": "left_of", "target_class": "sky"}}}},
        {"label": "V7: sky left_of sun", "filter_dict": {"status": "match", "filters": {
            "class": "sky", "spatial_relation": {"type": "left_of", "target_class": "sun"}}}},
        # Counting — eq 1 (exactly 1 sky per frame — all sky frames should match)
        {"label": "V8: sky eq 1", "filter_dict": {"status": "match", "filters": {
            "class": "sky", "count_constraint": {"operator": "eq", "value": 1}}}},
        # Negation
        {"label": "V9: sky without sun", "filter_dict": {"status": "match", "filters": {
            "class": "sky", "negated": ["sun"]}}},
        # Simple — continuous_motion only (has multi-object frames)
        {"label": "V10: sun present (simple, rerun)", "filter_dict": {"status": "match",
            "filters": {"class": "sun"}}},
    ]

    # ─────────────────────────────────────────────────────────────────
    # 5 NONSENSE QUERIES
    # ─────────────────────────────────────────────────────────────────
    nonsense_queries = [
        # Classes that were never indexed
        {"label": "N1: person (no_match status)", "filter_dict": {"status": "no_match", "filters": {}}},
        {"label": "N2: car present (no data)", "filter_dict": {"status": "match",
            "filters": {"class": "car"}}},
        {"label": "N3: helmet present (no data)", "filter_dict": {"status": "match",
            "filters": {"class": "helmet"}}},
        {"label": "N4: sky gt 1 (impossible: 1 sky/frame)", "filter_dict": {"status": "match",
            "filters": {"class": "sky", "count_constraint": {"operator": "gt", "value": 1}}}},
        {"label": "N5: sun without sky (sun always with sky)", "filter_dict": {"status": "match",
            "filters": {"class": "sun", "negated": ["sky"]}}},
    ]

    print("=" * 65)
    print("  VALID QUERIES (10)")
    print("=" * 65)
    valid_scores = []
    for q in valid_queries:
        fd = q["filter_dict"]
        if fd.get("status") == "no_match":
            top_score = 0.0
            n = 0
        else:
            try:
                results = search_structured(filter_dict=fd, client=client,
                                            collection_name=collection_name)
                n = len(results)
                top_score = results[0].confidence_score if results else 0.0
            except Exception as e:
                n = -1
                top_score = 0.0
                print(f"  ERROR: {e}")
        valid_scores.append(top_score)
        status = "PASS" if n > 0 else "MISS"
        print(f"  [{status}] {q['label']}: n={n}  top_score={top_score:.4f}")

    print()
    print("=" * 65)
    print("  NONSENSE QUERIES (5)")
    print("=" * 65)
    nonsense_scores = []
    for q in nonsense_queries:
        fd = q["filter_dict"]
        if fd.get("status") == "no_match":
            top_score = 0.0
            n = 0
        else:
            try:
                results = search_structured(filter_dict=fd, client=client,
                                            collection_name=collection_name)
                n = len(results)
                top_score = results[0].confidence_score if results else 0.0
            except Exception as e:
                n = -1
                top_score = 0.0
        nonsense_scores.append(top_score)
        status = "OK" if top_score == 0.0 else "LEAK"  # a nonsense query returning a score is a leak
        print(f"  [{status}] {q['label']}: n={n}  top_score={top_score:.4f}")

    # ─────────────────────────────────────────────────────────────────
    # Threshold computation
    # ─────────────────────────────────────────────────────────────────
    max_nonsense = max(nonsense_scores) if nonsense_scores else 0.0
    threshold = max_nonsense + MARGIN

    print()
    print("=" * 65)
    print("  CALIBRATION RESULT")
    print("=" * 65)
    print(f"  Valid query scores:    {[round(s,4) for s in valid_scores]}")
    print(f"  Nonsense scores:       {[round(s,4) for s in nonsense_scores]}")
    print(f"  max(nonsense):         {max_nonsense:.4f}")
    print(f"  margin (locked):       {MARGIN}")
    print(f"  threshold (formula):   {threshold:.4f}")
    print()

    # Coverage check
    valid_above = [s for s in valid_scores if s >= threshold]
    print(f"  Valid queries above threshold: {len(valid_above)}/{len(valid_scores)}")
    print()

    if max_nonsense == 0.0:
        print("  *** DATA ADEQUACY WARNING ***")
        print("  All nonsense queries returned score=0.0 — they hit no indexed data at all.")
        print("  The threshold of 0.05 is a floor based on margin alone, not a meaningful")
        print("  calibration against real false-positive scores. The current synthetic footage")
        print("  (sky/sun only) cannot produce a meaningful threshold calibration for")
        print("  real-world queries (person, car, helmet, etc.).")
        print("  Threshold 0.05 is committed as the minimum-viable placeholder.")
        print("  A re-calibration with real footage is REQUIRED before production.")
    else:
        print("  Threshold reflects real nonsense score distribution.")

    # Write threshold config
    import json
    threshold_path = ODYESSUES3_ROOT / "threshold_config.json"
    threshold_data = {
        "threshold": threshold,
        "max_nonsense_score": max_nonsense,
        "margin": MARGIN,
        "calibration_note": (
            "Calibrated on synthetic sky/sun footage (3 videos, 8 detections). "
            "All nonsense queries returned 0.0 (no matching data). "
            "Threshold=0.05 is margin-only. Re-calibrate with real footage before production."
            if max_nonsense == 0.0
            else f"Calibrated on real data. max_nonsense={max_nonsense:.4f} + margin={MARGIN}."
        )
    }
    with open(threshold_path, "w") as f:
        json.dump(threshold_data, f, indent=2)
    print(f"\n  Wrote: {threshold_path}")
    print(f"  threshold_config.json: {json.dumps(threshold_data, indent=4)}")


if __name__ == "__main__":
    main()
