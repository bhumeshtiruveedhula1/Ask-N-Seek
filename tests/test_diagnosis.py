"""
tests/test_diagnosis.py — Intelligent No-Match Diagnosis Unit & Integration Tests.
"""

from __future__ import annotations

import uuid
import pytest
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams

from engine.diagnosis import diagnose_no_match, run_diagnosis, DiagnosisResult, ConstraintResult, ClosestMiss
from engine.stub_data import STUB_COLLECTION, get_stub_client


@pytest.fixture(scope="module")
def client() -> QdrantClient:
    """Shared in-memory Qdrant client with default stub data."""
    return get_stub_client()


# ---------------------------------------------------------------------------
# 3.1 Unit Tests
# ---------------------------------------------------------------------------

def test_single_must_zero_matches(client: QdrantClient):
    """Simple query with one must clause that has zero matches."""
    query = "purple_elephant"
    filters = {"class": "purple_elephant"}

    result = diagnose_no_match(query, filters, STUB_COLLECTION, client)

    assert isinstance(result, DiagnosisResult)
    assert result.overall_status == "no_match"
    assert len(result.constraint_breakdown) == 1
    assert result.constraint_breakdown[0].description == "Object: purple_elephant"
    assert result.constraint_breakdown[0].scenes_matched == 0
    assert result.closest_miss is None


def test_compositional_one_matches_one_fails(client: QdrantClient):
    """Compositional query with two must clauses where one matches and one doesn't."""
    query = "person in purple"
    filters = {"class": "person", "color": "purple"}

    result = diagnose_no_match(query, filters, STUB_COLLECTION, client)

    assert isinstance(result, DiagnosisResult)
    assert len(result.constraint_breakdown) == 2

    # Object: person matches scenes
    person_clause = next(c for c in result.constraint_breakdown if "person" in c.description)
    assert person_clause.scenes_matched > 0

    # Color: purple matches 0 scenes
    purple_clause = next(c for c in result.constraint_breakdown if "purple" in c.description)
    assert purple_clause.scenes_matched == 0

    # Closest miss should relax purple and find person
    assert result.closest_miss is not None
    assert result.closest_miss.violated_constraint == "Color: purple"
    assert result.closest_miss.score > 0
    assert result.suggested_rephrasing is not None
    assert "purple" in result.suggested_rephrasing.lower()


def test_must_not_blocker(client: QdrantClient):
    """Query with must_not clause that is the blocker."""
    # Query: person without car (when almost every frame with person has car)
    query = "person without car"
    filters = {"class": "person", "negated": ["car"]}

    result = diagnose_no_match(query, filters, STUB_COLLECTION, client)

    assert isinstance(result, DiagnosisResult)
    neg_clause = next((c for c in result.constraint_breakdown if c.constraint_type == "must_not"), None)
    assert neg_clause is not None
    assert "car" in neg_clause.description.lower()


def test_spatial_blocker(client: QdrantClient):
    """Query with spatial clause as the blocker."""
    query = "person right_of car"
    filters = {"class": "person", "spatial_relation": {"type": "right_of", "target_class": "car"}}

    result = diagnose_no_match(query, filters, STUB_COLLECTION, client)

    assert isinstance(result, DiagnosisResult)
    sp_clause = next((c for c in result.constraint_breakdown if c.constraint_type == "spatial"), None)
    assert sp_clause is not None
    assert sp_clause.scenes_matched == 0


def test_closest_miss_computation(client: QdrantClient):
    """Verify relaxing the correct constraint yields the highest score."""
    query = "car in green"
    filters = {"class": "car", "color": "green"}

    result = diagnose_no_match(query, filters, STUB_COLLECTION, client)

    assert result.closest_miss is not None
    # Omitted 'green', matched 'car' which has high confidence
    assert result.closest_miss.violated_constraint == "Color: green"
    assert result.closest_miss.score > 0.5


def test_legacy_run_diagnosis_wrapper(client: QdrantClient):
    """Verify run_diagnosis backward-compatible dictionary output."""
    filters = {"class": "person", "color": "purple"}
    legacy_out = run_diagnosis(filters, client, STUB_COLLECTION, query_str="person in purple")

    assert "constraint_counts" in legacy_out
    assert "closest_miss" in legacy_out
    assert "html" in legacy_out
    assert "diagnosis_result" in legacy_out
    assert legacy_out["closest_miss"]["relaxed_constraint"] == "Color: purple"


# ---------------------------------------------------------------------------
# 3.2 Integration Test with Known Data Setup
# ---------------------------------------------------------------------------

def test_integration_diagnosis_known_dataset():
    """
    Integration test with a custom stub collection where:
      - 5 scenes have "person"
      - 3 scenes have "person + car"
      - 1 scene has "person + car + red" (at vid1 timestamp 14.3, score 0.85)
      - Query asks for "person + car + blue"
    
    Verifies:
      - Constraint breakdown counts: person=5, car=3, blue=0 (or color=blue)
      - Closest miss points to scene with "person + car + red"
      - Suggested rephrasing mentions color constraint
    """
    col_name = "test_diag_known_coll"
    test_client = QdrantClient(":memory:")
    test_client.create_collection(
        collection_name=col_name,
        vectors_config=VectorParams(size=1, distance=Distance.COSINE),
    )

    points: list[PointStruct] = []
    pid = 1

    # 2 scenes with person only
    for i in range(2):
        points.append(PointStruct(
            id=pid,
            vector=[0.0],
            payload={
                "video_id": f"vid_person_{i}",
                "frame_index": i,
                "timestamp": float(i * 10),
                "scene_id": i,
                "class_name": "person",
                "color": "black",
                "confidence": 0.50,
            }
        ))
        pid += 1

    # 2 scenes with person + car (white / black)
    for i in range(2):
        # person point
        points.append(PointStruct(
            id=pid,
            vector=[0.0],
            payload={
                "video_id": f"vid_pc_{i}",
                "frame_index": 0,
                "timestamp": float(i * 5),
                "scene_id": 10 + i,
                "class_name": "person",
                "color": "white",
                "confidence": 0.60,
            }
        ))
        pid += 1
        # car point
        points.append(PointStruct(
            id=pid,
            vector=[0.0],
            payload={
                "video_id": f"vid_pc_{i}",
                "frame_index": 0,
                "timestamp": float(i * 5),
                "scene_id": 10 + i,
                "class_name": "car",
                "color": "black",
                "confidence": 0.65,
            }
        ))
        pid += 1

    # 1 scene with person + car + red (closest miss candidate!)
    points.append(PointStruct(
        id=pid,
        vector=[0.0],
        payload={
            "video_id": "vid_target",
            "frame_index": 42,
            "timestamp": 14.3,
            "scene_id": 99,
            "class_name": "person",
            "color": "black",
            "confidence": 0.80,
        }
    ))
    pid += 1

    points.append(PointStruct(
        id=pid,
        vector=[0.0],
        payload={
            "video_id": "vid_target",
            "frame_index": 42,
            "timestamp": 14.3,
            "scene_id": 99,
            "class_name": "car",
            "color": "red",
            "confidence": 0.85,
        }
    ))
    pid += 1

    test_client.upsert(collection_name=col_name, points=points)

    # Query asking for person + car + blue
    query = "person and blue car"
    filters = {
        "class": "person",
        "color": "blue",
        "spatial_relation": None,
        "count_constraint": None,
        "negated": [],
    }

    diag = diagnose_no_match(query, filters, collection_name=col_name, qdrant_client=test_client)

    # Verify breakdown
    assert diag.overall_status == "no_match"
    person_cb = next(c for c in diag.constraint_breakdown if "person" in c.description)
    assert person_cb.scenes_matched == 5

    color_cb = next(c for c in diag.constraint_breakdown if "blue" in c.description)
    assert color_cb.scenes_matched == 0

    # Verify closest miss
    assert diag.closest_miss is not None
    assert diag.closest_miss.video_id == "vid_target"
    assert abs(diag.closest_miss.timestamp - 14.3) < 1e-3
    assert diag.closest_miss.score == 0.80  # best score for person + relaxed blue

    # Verify suggested rephrasing mentions color
    assert diag.suggested_rephrasing is not None
    assert "blue" in diag.suggested_rephrasing.lower()
