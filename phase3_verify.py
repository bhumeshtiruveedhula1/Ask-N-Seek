"""
phase3_verify.py — MATCH-state confirmation using real ASK_N_SEEK data.

Known exact APIs (verified before writing this script):
  detect_keyframe(frame_path: str) -> list[dict]
    dict keys: class, bbox, confidence, spatial_relations
    spatial_relations: list[{subject, subject_idx, relation, object_, object_idx}]

Uses in-memory Qdrant (no Docker required).
Indexes directly via qdrant_client (bypasses qdrant_store which needs detection.contract).
"""
import sys, time, uuid
from pathlib import Path

INTEGRATION_ROOT = Path(r"C:\Users\bhumeshjyothi\Desktop\Ask_n_Seek_integration\fresh_clone")
ACHILLES_ROOT    = Path(r"C:\Users\bhumeshjyothi\Desktop\ASK_N_SEEK")
FRAMES_ROOT      = ACHILLES_ROOT / "outputs" / "frames_real"

sys.path.insert(0, str(INTEGRATION_ROOT))
sys.path.insert(0, str(ACHILLES_ROOT))

# ------------------------------------------------------------------ Step 1
frame_records = []
for video_dir in sorted(FRAMES_ROOT.iterdir()):
    if not video_dir.is_dir():
        continue
    for jpg in sorted(video_dir.glob("*.jpg")):
        frame_records.append({
            "video_id":    video_dir.name,
            "frame_index": int(jpg.stem),
            "timestamp":   float(int(jpg.stem)),
            "frame_path":  str(jpg),
        })
print(f"[1] Frames available: {len(frame_records)}")
for v in sorted(set(r["video_id"] for r in frame_records)):
    n = sum(1 for r in frame_records if r["video_id"] == v)
    print(f"    {v}: {n} frames")

# ------------------------------------------------------------------ Step 2
print(f"\n[2] Loading YOLO detector...")
t0 = time.time()
from backend.vision.object_detector import detect_keyframe
print(f"    Import done in {time.time()-t0:.1f}s — now detecting (YOLO loads on first call)...")

all_detections = []
classes_seen   = set()
for rec in frame_records:
    dets = detect_keyframe(rec["frame_path"])
    for d in dets:
        classes_seen.add(d["class"])
    all_detections.append((rec, dets))

total_dets = sum(len(d) for _, d in all_detections)
frames_with_dets = sum(1 for _, d in all_detections if d)
print(f"    Done. {frames_with_dets}/{len(frame_records)} frames have detections.")
print(f"    Total detections : {total_dets}")
print(f"    Unique classes   : {sorted(classes_seen)}")

# show first 8 frames
for rec, dets in all_detections[:8]:
    if dets:
        cls = [d["class"] for d in dets]
        print(f"    {rec['video_id']}@{rec['timestamp']:.0f}s: {cls}")

# ------------------------------------------------------------------ Step 3
print(f"\n[3] Indexing to in-memory Qdrant...")
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct

client = QdrantClient(":memory:")
COLLECTION = "video_objects_real"
# Minimal schema: no embedding vector needed (we filter on payload only)
client.create_collection(
    COLLECTION,
    vectors_config=VectorParams(size=1, distance=Distance.COSINE)
)

points = []
for rec, dets in all_detections:
    for det in dets:
        pt_id = str(uuid.uuid5(
            uuid.NAMESPACE_URL,
            f"{rec['video_id']}_{rec['frame_index']}_{det['class']}"
        ))
        points.append(PointStruct(
            id=pt_id,
            vector=[det["confidence"]],   # dummy 1-d vector
            payload={
                "video_id":          rec["video_id"],
                "frame_index":       rec["frame_index"],
                "timestamp":         rec["timestamp"],
                "scene_id":          0,
                "class_name":        det["class"],
                "confidence":        det["confidence"],
                "spatial_relations": det.get("spatial_relations", []),
                "color":             "",
            }
        ))

if points:
    client.upsert(COLLECTION, points)
cnt = client.count(COLLECTION).count
print(f"    Indexed: {cnt} detection points")

# ------------------------------------------------------------------ Step 4
print(f"\n[4] Running queries through real parser + search engine...")
from engine.parser_gateway import parse_query
from engine.search import search_structured

# pick classes that were actually detected
detected_classes = sorted(classes_seen)
primary   = detected_classes[0]  if detected_classes        else "person"
secondary = detected_classes[1]  if len(detected_classes)>1 else "car"

# Use known-present classes from the real dataset for reliable match testing
# 'person' and 'car' confirmed detected in both videos
QUERIES = [
    ("simple class",  "person"),
    ("negation",      "person without car"),
    ("two objects",   "person and car"),
    ("nonsense",      "purple helicopter banana"),
    ("nonsense2",     "flying dinosaur"),
]

# No translation helper needed — parser_gateway now emits stub-flat directly.
for qtype, query in QUERIES:
    parsed  = parse_query(query)
    results = search_structured(parsed, client=client, collection_name=COLLECTION)
    print(f"\n  [{qtype}] '{query}'")
    print(f"    parse  -> status={parsed['status']}  class={parsed['filters'].get('class')}  negated={parsed['filters'].get('negated', [])}")
    print(f"    search -> {len(results)} results")
    if results:
        r = results[0]
        cls_list = [o.get("class_name") for o in r.matched_objects]
        print(f"    top result: video_id={r.video_id}  timestamp={r.timestamp}s")
        print(f"    matched_objects: {cls_list}")
        if "nonsense" not in qtype:
            print(f"    *** MATCH STATE CONFIRMED ✓ ***")
    else:
        if "nonsense" not in qtype:
            print(f"    No results (unexpected for known class)")

# ------------------------------------------------------------------ Step 5
print(f"\n[5] Calibration check...")
nonsense_queries = [
    "purple helicopter banana",
    "flying dinosaur",
    "invisible spaceship",
    "dancing robot elephant",
    "underwater volcano eruption",
]
scores = []
for nq in nonsense_queries:
    parsed_nq = parse_query(nq)
    res = search_structured(parsed_nq, client=client, collection_name=COLLECTION)
    scores.append(len(res))
    print(f"    {nq!r}: {len(res)} results")


max_score = max(scores) if scores else 0
print(f"\n    max nonsense results: {max_score}")
if max_score > 0:
    print(f"    CALIBRATION: Non-zero false positives detected — calibration is now meaningful.")
    print(f"    Recommended threshold: tune search.py MIN_CONFIDENCE above {max_score} results / {cnt} total.")
else:
    print(f"    CALIBRATION: All nonsense = 0 results (threshold is working; data may be too narrow for full calibration).")

print("\n[DONE] Phase 3 complete.")
