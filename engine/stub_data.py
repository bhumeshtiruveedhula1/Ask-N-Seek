"""
engine/stub_data.py — In-memory Qdrant stub dataset for Odysseus Part 3.

# TODO: SWAP FOR ACHILLES'S REAL IMPLEMENTATION
# This module seeds an in-memory QdrantClient(":memory:") with 72 synthetic
# detection rows that cover all Milestone 1 verification scenarios.
#
# Integration point:
#   Replace seed_stub_collection() / get_stub_client() with:
#       from qdrant_store.client import get_client
#   pointing at the real Part 2 Qdrant collection ("video_objects").
#   All search logic in engine/search.py is already compatible — only the
#   client and collection_name arguments need to change.
#
# Payload schema mirrors Part 2 exactly (field names match qdrant_store/writer.py):
#   video_id, frame_index, timestamp, scene_id, frame_path, frame_id,
#   class_name, color, confidence, bbox, spatial_relations

Coverage of 72 rows:
- 3 video IDs: vid1, vid2, vid3
- Classes: person, car, dog, bicycle, helmet, bag
- Colors: red, blue, white, black, green, brown
- Confidence range: 0.38 – 0.93
- Spatial relations: left_of car (dict format)
- Frames with helmet (for negation testing)
- Frames with ≥2 persons (for count constraint testing)
"""

from __future__ import annotations

import uuid

from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams

STUB_COLLECTION: str = "stub_video_objects"
_DUMMY_VECTOR: list[float] = [0.0]
_NAMESPACE: uuid.UUID = uuid.UUID("b2c3d4e5-f6a7-8901-bcde-f12345678901")

# ---------------------------------------------------------------------------
# Frame specs
# Each entry: (video_id, frame_index, timestamp, scene_id, [detections])
# Each detection: (class_name, color, confidence, bbox, spatial_relations)
# bbox: normalised [x1, y1, x2, y2]
# spatial_relations: list of {"relation": ..., "object_": ...}
# ---------------------------------------------------------------------------

_FRAME_SPECS: list[tuple] = [

    # =====================================================================
    # VID1 — Street intersection footage
    # =====================================================================

    # Frame 0 — 2 people (red + blue), car, no helmet
    # Satisfies: "person in red", "two people", "person without helmet"
    ("vid1", 0, 1.0, 1, [
        ("person",  "red",   0.89, [0.10, 0.20, 0.30, 0.60], []),
        ("person",  "blue",  0.85, [0.50, 0.20, 0.70, 0.60], []),
        ("car",     "white", 0.92, [0.30, 0.40, 0.90, 0.80], []),
    ]),

    # Frame 1 — person/red left_of car, no helmet
    # Satisfies: "person in red", "person left of car", "person without helmet"
    ("vid1", 1, 3.5, 1, [
        ("person",  "red",   0.91, [0.10, 0.15, 0.35, 0.65],
         [{"relation": "left_of", "object_": "car"}]),
        ("car",     "white", 0.88, [0.45, 0.20, 0.95, 0.85], []),
    ]),

    # Frame 2 — person + HELMET → excluded from "person without helmet"
    ("vid1", 2, 5.0, 2, [
        ("person",  "blue",  0.76, [0.20, 0.10, 0.50, 0.70], []),
        ("helmet",  "black", 0.82, [0.22, 0.08, 0.45, 0.25], []),
    ]),

    # Frame 3 — 2 people (red + blue), no helmet
    # Satisfies: "two people", "person without helmet", "person in red"
    ("vid1", 3, 8.0, 2, [
        ("person",  "red",   0.82, [0.10, 0.10, 0.40, 0.70], []),
        ("person",  "blue",  0.78, [0.50, 0.15, 0.80, 0.75], []),
    ]),

    # Frame 4 — low confidence, person green + bag
    ("vid1", 4, 10.5, 3, [
        ("person",  "green", 0.38, [0.30, 0.20, 0.60, 0.80], []),
        ("bag",     "black", 0.45, [0.28, 0.60, 0.55, 0.85], []),
    ]),

    # Frame 5 — cars only (no people)
    ("vid1", 5, 13.0, 3, [
        ("car",     "black", 0.87, [0.10, 0.30, 0.55, 0.70], []),
        ("car",     "white", 0.83, [0.55, 0.25, 0.95, 0.75], []),
    ]),

    # Frame 6 — 3 people (2 red, 1 blue), no helmet
    # Satisfies: "two people" (3≥2), "person in red" ×2, "person without helmet"
    ("vid1", 6, 15.0, 4, [
        ("person",  "red",   0.88, [0.05, 0.10, 0.35, 0.70], []),
        ("person",  "red",   0.86, [0.40, 0.12, 0.65, 0.72], []),
        ("person",  "blue",  0.79, [0.68, 0.15, 0.92, 0.75], []),
    ]),

    # Frame 7 — cars only
    ("vid1", 7, 18.0, 4, [
        ("car",     "blue",  0.74, [0.10, 0.20, 0.50, 0.75], []),
        ("car",     "black", 0.69, [0.55, 0.25, 0.95, 0.80], []),
    ]),

    # Frame 8 — person/black left_of car + bicycle
    # Satisfies: "person left of car", "person without helmet"
    ("vid1", 8, 21.0, 5, [
        ("person",  "black", 0.80, [0.05, 0.10, 0.30, 0.75],
         [{"relation": "left_of", "object_": "car"}]),
        ("car",     "white", 0.91, [0.38, 0.15, 0.95, 0.85], []),
        ("bicycle", "black", 0.64, [0.00, 0.50, 0.30, 0.90], []),
    ]),

    # Frame 9 — person/red + bag
    # Satisfies: "person in red", "person without helmet"
    ("vid1", 9, 24.0, 5, [
        ("person",  "red",   0.73, [0.20, 0.10, 0.55, 0.80], []),
        ("bag",     "blue",  0.58, [0.60, 0.50, 0.90, 0.85], []),
    ]),

    # =====================================================================
    # VID2 — Parking lot footage
    # =====================================================================

    # Frame 0 — car/red + bicycle (no people)
    ("vid2", 0, 2.0, 1, [
        ("car",     "red",   0.87, [0.10, 0.30, 0.50, 0.70], []),
        ("bicycle", "green", 0.72, [0.55, 0.40, 0.85, 0.80], []),
    ]),

    # Frame 1 — person/white + dog, no helmet
    # Satisfies: "person without helmet"
    ("vid2", 1, 4.0, 1, [
        ("person",  "white", 0.80, [0.10, 0.10, 0.40, 0.75], []),
        ("dog",     "brown", 0.75, [0.50, 0.40, 0.80, 0.90], []),
    ]),

    # Frame 2 — 2 people (black + green) + HELMET
    # Satisfies: "two people"; EXCLUDED from "person without helmet"
    ("vid2", 2, 6.0, 2, [
        ("person",  "black", 0.77, [0.10, 0.10, 0.35, 0.70], []),
        ("person",  "green", 0.68, [0.50, 0.15, 0.75, 0.72], []),
        ("helmet",  "red",   0.84, [0.12, 0.08, 0.33, 0.28], []),
    ]),

    # Frame 3 — bag + bicycle (no people)
    ("vid2", 3, 9.0, 3, [
        ("bag",     "blue",  0.65, [0.30, 0.50, 0.60, 0.90], []),
        ("bicycle", "black", 0.71, [0.00, 0.20, 0.40, 0.80], []),
    ]),

    # Frame 4 — person/white left_of car
    # Satisfies: "person left of car", "person without helmet"
    ("vid2", 4, 12.0, 3, [
        ("person",  "white", 0.83, [0.05, 0.10, 0.35, 0.75],
         [{"relation": "left_of", "object_": "car"}]),
        ("car",     "blue",  0.90, [0.40, 0.20, 0.95, 0.80], []),
    ]),

    # Frame 5 — dog + person/red (low confidence)
    ("vid2", 5, 15.0, 4, [
        ("dog",     "white", 0.66, [0.10, 0.30, 0.50, 0.80], []),
        ("person",  "red",   0.42, [0.55, 0.10, 0.85, 0.70], []),
    ]),

    # Frame 6 — person/red left_of car + person/blue + car, no helmet
    # Satisfies: "person in red", "person left of car", "two people", "person without helmet"
    ("vid2", 6, 17.0, 4, [
        ("person",  "red",   0.85, [0.05, 0.10, 0.30, 0.75],
         [{"relation": "left_of", "object_": "car"}]),
        ("person",  "blue",  0.79, [0.35, 0.12, 0.58, 0.73], []),
        ("car",     "white", 0.93, [0.60, 0.15, 0.98, 0.85], []),
    ]),

    # Frame 7 — person/blue + HELMET
    # EXCLUDED from "person without helmet"
    ("vid2", 7, 20.0, 5, [
        ("helmet",  "white", 0.73, [0.20, 0.05, 0.45, 0.30], []),
        ("person",  "blue",  0.67, [0.15, 0.10, 0.48, 0.75], []),
    ]),

    # Frame 8 — bag/green + dog
    ("vid2", 8, 23.0, 5, [
        ("bag",     "green", 0.55, [0.30, 0.40, 0.65, 0.80], []),
        ("dog",     "red",   0.60, [0.70, 0.30, 0.95, 0.85], []),
    ]),

    # Frame 9 — 2 people (red + white), no helmet
    # Satisfies: "two people", "person without helmet", "person in red"
    ("vid2", 9, 26.0, 6, [
        ("person",  "red",   0.81, [0.05, 0.10, 0.40, 0.80], []),
        ("person",  "white", 0.76, [0.45, 0.12, 0.80, 0.78], []),
    ]),

    # Frame 10 — 3 cars (no people)
    ("vid2", 10, 29.0, 6, [
        ("car",     "white", 0.90, [0.05, 0.15, 0.40, 0.75], []),
        ("car",     "red",   0.86, [0.42, 0.18, 0.78, 0.72], []),
        ("car",     "black", 0.78, [0.80, 0.20, 0.98, 0.70], []),
    ]),

    # =====================================================================
    # VID3 — Pedestrian zone footage
    # =====================================================================

    # Frame 0 — 2 people (both red), one left_of car, no helmet
    # Satisfies: "person in red" ×2, "person left of car", "two people", "person without helmet"
    ("vid3", 0, 1.5, 1, [
        ("person",  "red",   0.87, [0.05, 0.10, 0.30, 0.70],
         [{"relation": "left_of", "object_": "car"}]),
        ("person",  "red",   0.84, [0.35, 0.10, 0.60, 0.70], []),
        ("car",     "white", 0.90, [0.55, 0.20, 0.98, 0.85], []),
    ]),

    # Frame 1 — dog + bicycle (no people)
    ("vid3", 1, 3.0, 1, [
        ("dog",     "black", 0.73, [0.20, 0.30, 0.60, 0.80], []),
        ("bicycle", "white", 0.68, [0.00, 0.10, 0.35, 0.70], []),
    ]),

    # Frame 2 — person/blue left_of car (spatial match, not red)
    # Satisfies: "person left of car", "person without helmet"
    ("vid3", 2, 7.0, 2, [
        ("person",  "blue",  0.79, [0.10, 0.15, 0.35, 0.75],
         [{"relation": "left_of", "object_": "car"}]),
        ("car",     "black", 0.88, [0.40, 0.10, 0.95, 0.80], []),
    ]),

    # Frame 3 — bicycle + bag (low confidence, no people)
    ("vid3", 3, 11.0, 3, [
        ("bicycle", "white", 0.55, [0.10, 0.20, 0.50, 0.80], []),
        ("bag",     "red",   0.48, [0.55, 0.50, 0.85, 0.90], []),
    ]),

    # Frame 4 — 1 person/green (no helmet)
    # Satisfies: "person without helmet"
    ("vid3", 4, 14.0, 3, [
        ("person",  "green", 0.72, [0.20, 0.10, 0.55, 0.80], []),
    ]),

    # Frame 5 — 3 people (red, blue, black), no helmet
    # Satisfies: "two people" (3≥2), "person without helmet", "person in red"
    ("vid3", 5, 17.0, 4, [
        ("person",  "red",   0.86, [0.05, 0.10, 0.35, 0.75], []),
        ("person",  "blue",  0.80, [0.38, 0.12, 0.68, 0.77], []),
        ("person",  "black", 0.74, [0.70, 0.15, 0.95, 0.80], []),
    ]),

    # Frame 6 — car/green + bicycle (no people)
    ("vid3", 6, 20.0, 5, [
        ("car",     "green", 0.69, [0.10, 0.25, 0.55, 0.75], []),
        ("bicycle", "red",   0.63, [0.60, 0.30, 0.90, 0.85], []),
    ]),

    # Frame 7 — person/white left_of car + dog, no helmet
    # Satisfies: "person left of car", "person without helmet"
    ("vid3", 7, 23.0, 5, [
        ("person",  "white", 0.81, [0.05, 0.10, 0.32, 0.78],
         [{"relation": "left_of", "object_": "car"}]),
        ("car",     "red",   0.89, [0.38, 0.12, 0.92, 0.82], []),
        ("dog",     "brown", 0.67, [0.00, 0.55, 0.30, 0.90], []),
    ]),

    # Frame 8 — 2 people (both red), no helmet
    # Satisfies: "two people", "person in red" ×2, "person without helmet"
    ("vid3", 8, 26.0, 6, [
        ("person",  "red",   0.85, [0.10, 0.10, 0.45, 0.80], []),
        ("person",  "red",   0.82, [0.50, 0.12, 0.85, 0.78], []),
    ]),

    # Frame 9 — 2 people (green + blue), no helmet (lower confidence)
    # Satisfies: "two people", "person without helmet"
    ("vid3", 9, 29.0, 6, [
        ("person",  "green", 0.70, [0.10, 0.15, 0.45, 0.80], []),
        ("person",  "blue",  0.65, [0.50, 0.18, 0.88, 0.82], []),
    ]),
]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def make_point_id(video_id: str, frame_index: int, det_index: int) -> str:
    """Generate a deterministic UUID5 point ID for stub data."""
    key = f"{video_id}:{frame_index}:{det_index}"
    return str(uuid.uuid5(_NAMESPACE, key))


def get_stub_client() -> QdrantClient:
    """
    Create a fresh in-memory QdrantClient and seed it with stub detections.

    # TODO: SWAP FOR ACHILLES'S REAL IMPLEMENTATION
    # Replace this call with the real Qdrant client from Part 2:
    #     from qdrant_store.client import get_client
    #     return get_client()
    # and update STUB_COLLECTION → config.QDRANT_COLLECTION in all callers.

    Returns
    -------
    QdrantClient
        In-memory client with stub_video_objects collection ready to query.
    """
    client = QdrantClient(":memory:")
    seed_stub_collection(client)
    return client


def seed_stub_collection(client: QdrantClient, collection_name: str = STUB_COLLECTION) -> int:
    """
    Seed the given QdrantClient with stub detection data.

    Idempotent: skips seeding if the collection already exists.

    Parameters
    ----------
    client : QdrantClient
    collection_name : str

    Returns
    -------
    int
        Number of points upserted (0 if already seeded).
    """
    existing = {c.name for c in client.get_collections().collections}
    if collection_name in existing:
        return 0

    client.create_collection(
        collection_name=collection_name,
        vectors_config=VectorParams(size=1, distance=Distance.COSINE),
    )

    # Payload indexes for fast keyword filtering (class, color, spatial)
    for field in ("class_name", "color", "spatial_relations"):
        client.create_payload_index(
            collection_name=collection_name,
            field_name=field,
            field_schema="keyword",
        )

    points: list[PointStruct] = []
    for video_id, frame_index, timestamp, scene_id, detections in _FRAME_SPECS:
        frame_path = f"frames/{video_id}/{frame_index:04d}.jpg"
        frame_id = f"{video_id}_{frame_index}"
        for det_index, (class_name, color, confidence, bbox, spatial_relations) in enumerate(detections):
            point_id = make_point_id(video_id, frame_index, det_index)
            payload = {
                # Frame traceability (matches Part 2 schema)
                "video_id":          video_id,
                "frame_index":       frame_index,
                "timestamp":         timestamp,
                "scene_id":          scene_id,
                "frame_path":        frame_path,
                "frame_id":          frame_id,
                # Detection fields (matches Part 2 schema)
                "class_name":        class_name,
                "color":             color,
                "confidence":        confidence,
                "bbox":              bbox,
                "spatial_relations": spatial_relations,
            }
            points.append(PointStruct(id=point_id, vector=_DUMMY_VECTOR, payload=payload))

    client.upsert(collection_name=collection_name, points=points)
    return len(points)


def count_stub_rows() -> int:
    """Return the total number of stub detection rows (for tests/logging)."""
    return sum(len(dets) for _, _, _, _, dets in _FRAME_SPECS)
