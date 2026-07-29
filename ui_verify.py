"""
ui_verify.py — Verify UI output logic (parse->search->threshold->explanation) for Phase 3.
Runs without browser: directly calls the same functions the Gradio app calls.
"""
import importlib.util
import sys
from pathlib import Path

ODYESSUES2 = Path(__file__).resolve().parent.parent / "ODYESSUES-2"
ODYESSUES3 = Path(__file__).resolve().parent.parent / "ODYESSUES-3"

for p in [str(ODYESSUES2)]:
    sys.path.append(p)
sys.path.insert(0, str(ODYESSUES3))

# Load Part 3 config explicitly
import os
os.environ["USE_STUB_QDRANT"] = "false"

spec = importlib.util.spec_from_file_location('config', str(ODYESSUES3 / 'config.py'))
cfg = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cfg)
sys.modules['config'] = cfg

from engine.parser_gateway import parse_query
from engine.qdrant_gateway import get_qdrant_client, get_collection_name
from engine.search import search_structured
from engine.explanation import generate_explanation
from config import load_threshold

client = get_qdrant_client()
collection = get_collection_name()
threshold = load_threshold()
print(f"Collection: '{collection}'")
print(f"Threshold: {threshold}")
count = client.count(collection_name=collection, exact=True).count
print(f"Qdrant count: {count}\n")


def run_query(label, query):
    print(f"{'='*60}")
    print(f"  QUERY: {repr(query)}  [{label}]")
    print(f"{'='*60}")

    # Step 1: Parse
    fd = parse_query(query)
    print(f"  [1] parse_query -> {fd}")

    status = fd.get("status")
    if status != "match":
        print(f"  [2] status='{status}' -> UI: NO CONFIDENT MATCH panel (parser short-circuit)")
        return "no_match"

    # Step 2: Search
    results = search_structured(filter_dict=fd, client=client, collection_name=collection)
    print(f"  [2] search_structured -> {len(results)} result(s)")

    if not results:
        print(f"  [3] 0 results -> UI: NO CONFIDENT MATCH panel")
        return "no_results"

    top = results[0]
    print(f"  [3] top.confidence_score = {top.confidence_score:.4f}  (threshold={threshold})")

    if top.confidence_score < threshold:
        print(f"  [4] BELOW threshold -> UI: NO CONFIDENT MATCH panel")
        return "below_threshold"

    # Step 3: Explanation
    explanation = generate_explanation(top)
    print(f"  [4] ABOVE threshold -> UI: MATCH state")
    print(f"  [5] generate_explanation -> {repr(explanation)[:200]}")
    print(f"      video_id        = {top.video_id}")
    print(f"      timestamp       = {top.timestamp}s  (video player seeks here)")
    print(f"      scene_id        = {top.scene_id}")
    print(f"      confidence_score= {top.confidence_score:.4f}")
    print(f"      explanation_facts= {top.explanation_facts}")
    print(f"      matched_objects = {len(top.matched_objects)} object(s)")
    if top.matched_objects:
        obj = top.matched_objects[0]
        print(f"      bbox[0]         = {obj.get('bbox')}  (bounding box overlay rendered)")
        print(f"      class_name      = {obj.get('class_name')}")
        print(f"      frame_path      = {obj.get('frame_path')}")
    return "match"


print()
outcomes = {}

# Valid queries
for label, query in [
    ("V1-simple", "sky"),
    ("V2-simple", "sun"),
    ("V3-spatial", "sun left of sky"),
    ("V4-counting", "more than 0 sky"),
]:
    outcomes[label] = run_query(label, query)
    print()

# Nonsense queries
for label, query in [
    ("N1-nonexistent", "purple elephant dancing"),
    ("N2-nonexistent", "flying unicorn on fire"),
    ("N3-gibberish", "xkzpqr bwmvf"),
]:
    outcomes[label] = run_query(label, query)
    print()

print("="*60)
print("  SUMMARY")
print("="*60)
for label, outcome in outcomes.items():
    icon = "✓" if outcome == "match" else ("✗ no_match" if outcome == "no_match" else outcome)
    print(f"  {label}: {outcome}")

match_count = sum(1 for v in outcomes.values() if v == "match")
no_match_count = sum(1 for v in outcomes.values() if v not in ("match",))
print(f"\n  MATCH state triggered: {match_count} time(s)")
print(f"  NO CONFIDENT MATCH state triggered: {no_match_count} time(s)")
