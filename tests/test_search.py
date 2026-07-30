"""
tests/test_search.py — Milestone 1 verification checklist tests.

Covers all 5 items from the spec checklist:
  [ ] "person in red"        → only class=person AND color=red
  [ ] "person without helmet"→ person present, no helmet in same frame
  [ ] "two people"           → frames with ≥2 person objects
  [ ] "person left of car"   → only rows with matching spatial_relation
  [ ] "purple elephant"      → 0 results, triggers no-match state

Also tests:
  - Processing log ordering (parser → search → threshold)
  - Explanation templating (no hallucination)
  - Calibration harness runs without error
  - No FAISS / embedding code paths (import guard)

Run with:
    cd ODYESSUES-3
    pytest tests/ -v
"""

from __future__ import annotations

import sys
import os

# Ensure project root is importable
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from qdrant_client import QdrantClient

from engine.stub_data import STUB_COLLECTION, get_stub_client, seed_stub_collection
from engine.stub_parser import parse_query_stub
from engine.search import search_structured, Result
from engine.explanation import generate_explanation
from engine.calibration import calibrate_threshold


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def client() -> QdrantClient:
    """In-memory Qdrant client seeded with stub data (shared across tests)."""
    return get_stub_client()


def _search(query: str, client: QdrantClient) -> list[Result]:
    """Helper: parse + search."""
    fd = parse_query_stub(query)
    return search_structured(fd, client, STUB_COLLECTION)


# ---------------------------------------------------------------------------
# Verification checklist — item 1
# ---------------------------------------------------------------------------

class TestPersonInRed:
    """Query: 'person in red' — must return ONLY class=person AND color=red."""

    def test_returns_results(self, client):
        results = _search("person in red", client)
        assert len(results) > 0, "Expected at least one result for 'person in red'"

    def test_all_matched_objects_are_person(self, client):
        results = _search("person in red", client)
        for r in results:
            for obj in r.matched_objects:
                assert obj["class_name"] == "person", (
                    f"Non-person object in matched_objects: {obj['class_name']}"
                )

    def test_all_matched_objects_are_red(self, client):
        results = _search("person in red", client)
        for r in results:
            for obj in r.matched_objects:
                assert obj["color"] == "red", (
                    f"Non-red object in matched_objects: {obj['color']}"
                )

    def test_results_sorted_by_confidence_desc(self, client):
        results = _search("person in red", client)
        scores = [r.confidence_score for r in results]
        assert scores == sorted(scores, reverse=True), "Results not sorted by confidence"

    def test_no_car_or_other_class_in_results(self, client):
        results = _search("person in red", client)
        non_person = [
            obj for r in results for obj in r.matched_objects
            if obj["class_name"] != "person"
        ]
        assert non_person == [], f"Found non-person objects: {non_person}"


# ---------------------------------------------------------------------------
# Verification checklist — item 2
# ---------------------------------------------------------------------------

class TestPersonWithoutHelmet:
    """Query: 'person without helmet' — must return frames with person but NO helmet."""

    def test_returns_results(self, client):
        results = _search("person without helmet", client)
        assert len(results) > 0

    def test_all_frames_have_person(self, client):
        results = _search("person without helmet", client)
        for r in results:
            class_names = {obj["class_name"] for obj in r.matched_objects}
            assert "person" in class_names, (
                f"Frame {r.video_id}@{r.timestamp} has no person in matched_objects"
            )

    def test_no_frame_has_helmet(self, client):
        """Frame-level negation: the stub stores ALL objects per frame in payload.
        We verify by checking the video_id+frame_index against known helmet frames."""
        results = _search("person without helmet", client)
        # Known helmet frames from stub_data.py
        helmet_frames = {
            ("vid1", 2),   # frame_index 2, ts=5.0
            ("vid2", 2),   # frame_index 2, ts=6.0
            ("vid2", 7),   # frame_index 7, ts=20.0
        }
        for r in results:
            # Reconstruct frame_index from matched_objects
            frame_index = r.matched_objects[0].get("frame_index")
            key = (r.video_id, frame_index)
            assert key not in helmet_frames, (
                f"Frame {r.video_id}[{frame_index}] has a helmet but was returned!"
            )

    def test_vid1_frame2_excluded(self, client):
        """vid1 frame_index=2 (ts=5.0) contains a helmet — must NOT appear."""
        results = _search("person without helmet", client)
        helmet_frame_timestamps = {
            (r.video_id, round(r.timestamp, 1))
            for r in results
        }
        assert ("vid1", 5.0) not in helmet_frame_timestamps


# ---------------------------------------------------------------------------
# Verification checklist — item 3
# ---------------------------------------------------------------------------

class TestTwoPeople:
    """Query: 'two people' — must return ONLY frames with ≥2 person objects."""

    def test_returns_results(self, client):
        results = _search("two people", client)
        assert len(results) > 0

    def test_all_frames_have_two_or_more_persons(self, client):
        results = _search("two people", client)
        for r in results:
            person_count = sum(
                1 for obj in r.matched_objects if obj["class_name"] == "person"
            )
            assert person_count >= 2, (
                f"Frame {r.video_id}@{r.timestamp} has only {person_count} person(s)"
            )

    def test_single_person_frames_excluded(self, client):
        """vid3 frame_index=4 (ts=14.0) has only 1 person — must not appear."""
        results = _search("two people", client)
        for r in results:
            if r.video_id == "vid3" and abs(r.timestamp - 14.0) < 0.1:
                pytest.fail("Single-person frame vid3@14.0 incorrectly returned")

    def test_no_person_frames_excluded(self, client):
        """vid1 frame_index=5 (ts=13.0) has 0 persons — must not appear."""
        results = _search("two people", client)
        for r in results:
            if r.video_id == "vid1" and abs(r.timestamp - 13.0) < 0.1:
                pytest.fail("No-person frame vid1@13.0 incorrectly returned")


# ---------------------------------------------------------------------------
# Verification checklist — item 4
# ---------------------------------------------------------------------------

class TestPersonLeftOfCar:
    """Query: 'person left of car' — only rows with spatial_relation left_of car."""

    def test_returns_results(self, client):
        results = _search("person left of car", client)
        assert len(results) > 0

    def test_all_matched_objects_are_person(self, client):
        results = _search("person left of car", client)
        for r in results:
            for obj in r.matched_objects:
                assert obj["class_name"] == "person", (
                    f"Non-person in matched: {obj['class_name']}"
                )

    def test_all_matched_have_left_of_car_relation(self, client):
        results = _search("person left of car", client)
        for r in results:
            for obj in r.matched_objects:
                rels = obj.get("spatial_relations", [])
                has_rel = any(
                    (isinstance(rel, dict)
                     and rel.get("relation") == "left_of"
                     and rel.get("object_") == "car")   # Achilles key: object_ not target_class
                    or (isinstance(rel, str) and rel == "left_of:car")
                    for rel in rels
                )
                assert has_rel, (
                    f"Object {obj['class_name']} at {r.video_id}@{r.timestamp} "
                    f"lacks left_of:car relation. Relations: {rels}"
                )

    def test_persons_without_spatial_relation_excluded(self, client):
        """vid3 frame_index=8 (ts=26.0) has 2 red persons but NO spatial relation."""
        results = _search("person left of car", client)
        for r in results:
            if r.video_id == "vid3" and abs(r.timestamp - 26.0) < 0.1:
                # If this frame appears, all matched objects must have the relation
                for obj in r.matched_objects:
                    rels = obj.get("spatial_relations", [])
                    has_rel = any(
                        isinstance(rel, dict) and rel.get("relation") == "left_of"
                        for rel in rels
                    )
                    assert has_rel, "No-spatial-relation object slipped through"


# ---------------------------------------------------------------------------
# Verification checklist — item 5
# ---------------------------------------------------------------------------

class TestNonsenseQuery:
    """Query: 'purple elephant' → 0 results, triggers no confident match state."""

    def test_purple_elephant_returns_empty(self, client):
        results = _search("purple elephant", client)
        assert results == [], f"Expected empty results, got {len(results)}"

    def test_flying_car_returns_empty(self, client):
        results = _search("flying car", client)
        assert results == []

    def test_invisible_dinosaur_returns_empty(self, client):
        results = _search("invisible dinosaur", client)
        assert results == []

    def test_parser_returns_no_match_status(self):
        fd = parse_query_stub("purple elephant dancing")
        assert fd["status"] == "no_match", (
            f"Expected no_match, got {fd['status']}"
        )

    def test_empty_results_below_threshold(self, client):
        """Confirm that empty results triggers no-match UI state."""
        results = _search("purple elephant", client)
        best_score = results[0].confidence_score if results else 0.0
        threshold = 0.5  # Milestone 1 placeholder
        assert best_score < threshold, (
            f"Nonsense query scored {best_score} ≥ threshold {threshold}"
        )


# ---------------------------------------------------------------------------
# Explanation templating
# ---------------------------------------------------------------------------

class TestExplanation:
    def test_explanation_format(self, client):
        results = _search("person in red", client)
        assert results
        explanation = generate_explanation(results[0])
        assert "Matched because:" in explanation
        assert "Confidence:" in explanation

    def test_explanation_contains_facts(self, client):
        results = _search("person in red", client)
        assert results
        expl = generate_explanation(results[0])
        assert "person" in expl.lower()
        assert "red" in expl.lower()

    def test_explanation_no_hallucination(self, client):
        """Explanation must not mention facts absent from explanation_facts."""
        results = _search("person in red", client)
        for r in results:
            expl = generate_explanation(r)
            # Should NOT mention helmet (not a filter in this query)
            assert "helmet" not in expl.lower(), (
                f"Hallucinated 'helmet' in: {expl}"
            )

    def test_no_model_call(self):
        """Verify explanation.py does not import any ML/LLM library."""
        import engine.explanation as expl_mod
        import inspect
        src = inspect.getsource(expl_mod)
        forbidden = ["openai", "anthropic", "transformers", "torch", "faiss",
                     "sentence_transformers", "clip", "langchain"]
        for lib in forbidden:
            assert lib not in src, f"Forbidden library '{lib}' found in explanation.py"


# ---------------------------------------------------------------------------
# Calibration harness
# ---------------------------------------------------------------------------

class TestCalibration:
    def test_calibration_runs_without_error(self):
        """Calibration harness must be callable against stub data."""
        threshold = calibrate_threshold(save=False)
        assert isinstance(threshold, float)
        assert 0.0 <= threshold <= 1.0

    def test_calibration_nonsense_threshold_reasonable(self):
        """Threshold must be > 0 (some margin above 0 for nonsense queries)."""
        threshold = calibrate_threshold(save=False)
        # Nonsense queries return 0 results → score 0.0 → threshold = 0.0 + 0.05 = 0.05
        assert threshold >= 0.04, f"Threshold {threshold} suspiciously low"


# ---------------------------------------------------------------------------
# Architecture guard — no forbidden imports
# ---------------------------------------------------------------------------

class TestNoForbiddenCode:
    def _check_imports_for_forbidden(self, filepath: str, forbidden: list[str]) -> None:
        """Check only actual import lines (not comments or docstrings)."""
        with open(filepath, "r", encoding="utf-8") as f:
            lines = f.readlines()
        import_lines = [
            ln.strip() for ln in lines
            if ln.strip().startswith(("import ", "from "))
        ]
        src = "\n".join(import_lines)
        for token in forbidden:
            assert token not in src, (
                f"Forbidden import '{token}' found in {os.path.basename(filepath)}"
            )

    def test_search_py_no_faiss(self):
        path = os.path.join(os.path.dirname(__file__), "..", "engine", "search.py")
        self._check_imports_for_forbidden(path, ["faiss", "FAISS", "SigLIP", "siglip"])

    def test_search_py_no_embedding(self):
        path = os.path.join(os.path.dirname(__file__), "..", "engine", "search.py")
        self._check_imports_for_forbidden(path, ["sentence_transformers", "openai", "langchain"])

    def test_gradio_app_no_faiss(self):
        path = os.path.join(os.path.dirname(__file__), "..", "ui", "gradio_app.py")
        self._check_imports_for_forbidden(path, ["faiss", "FAISS", "SigLIP"])
