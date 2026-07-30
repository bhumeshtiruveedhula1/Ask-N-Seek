"""
tests/test_explanation.py — Unit tests for engine/explanation.py (Milestone 2).

Tests edge cases and defensive behaviour per the M2 spec:
  - Normal case with full facts
  - Empty explanation_facts → "object detected" fallback
  - Negation-only facts
  - Spatial-only facts
  - Count-only facts
  - Fact truncation at 80 chars
  - Confidence == 1.0 shown as "1.00"
  - None explanation_facts treated as empty
"""

from __future__ import annotations

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from engine.search import Result
from engine.explanation import generate_explanation, _MAX_FACT_LEN


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_result(facts: list[str] | None, score: float = 0.85) -> Result:
    """Build a minimal Result with given explanation_facts."""
    return Result(
        video_id="vid1",
        timestamp=3.5,
        scene_id=1,
        matched_objects=[],
        confidence_score=score,
        explanation_facts=facts if facts is not None else [],
    )


# ---------------------------------------------------------------------------
# Normal case
# ---------------------------------------------------------------------------

class TestNormalCase:
    def test_format_has_matched_because(self):
        result = _make_result(["person detected", "red color confirmed"])
        expl = generate_explanation(result)
        assert expl.startswith("Matched because:"), expl

    def test_format_has_confidence(self):
        result = _make_result(["person detected"], score=0.89)
        expl = generate_explanation(result)
        assert "Confidence: 0.89." in expl, expl

    def test_facts_joined_with_comma(self):
        result = _make_result(["person detected", "red color confirmed"])
        expl = generate_explanation(result)
        assert "person detected, red color confirmed" in expl, expl

    def test_returns_single_string(self):
        result = _make_result(["person detected"])
        expl = generate_explanation(result)
        assert isinstance(expl, str)
        assert len(expl) > 0


# ---------------------------------------------------------------------------
# Empty facts edge case
# ---------------------------------------------------------------------------

class TestEmptyFacts:
    def test_empty_list_returns_object_detected(self):
        result = _make_result([])
        expl = generate_explanation(result)
        assert "object detected" in expl, expl

    def test_empty_list_still_has_confidence(self):
        result = _make_result([], score=0.72)
        expl = generate_explanation(result)
        assert "Confidence: 0.72." in expl, expl

    def test_none_facts_treated_as_empty(self):
        result = _make_result(None)
        expl = generate_explanation(result)
        assert "object detected" in expl, expl

    def test_whitespace_only_facts_treated_as_empty(self):
        result = _make_result(["   ", "\t", ""])
        expl = generate_explanation(result)
        assert "object detected" in expl, expl

    def test_never_returns_empty_string(self):
        for facts in [[], None, ["  "]]:
            result = _make_result(facts)
            expl = generate_explanation(result)
            assert expl.strip(), f"Empty string returned for facts={facts}"


# ---------------------------------------------------------------------------
# Negation-only facts
# ---------------------------------------------------------------------------

class TestNegationOnly:
    def test_negation_fact_in_output(self):
        result = _make_result(["no helmet detected"])
        expl = generate_explanation(result)
        assert "no helmet detected" in expl, expl

    def test_multiple_negations(self):
        result = _make_result(["no helmet detected", "no bag detected"])
        expl = generate_explanation(result)
        assert "no helmet detected" in expl
        assert "no bag detected" in expl


# ---------------------------------------------------------------------------
# Spatial-only facts
# ---------------------------------------------------------------------------

class TestSpatialOnly:
    def test_spatial_fact_in_output(self):
        result = _make_result(["left of car"])
        expl = generate_explanation(result)
        assert "left of car" in expl, expl

    def test_spatial_followed_by_confidence(self):
        result = _make_result(["left of car"], score=0.81)
        expl = generate_explanation(result)
        assert "Confidence: 0.81." in expl


# ---------------------------------------------------------------------------
# Count-only facts
# ---------------------------------------------------------------------------

class TestCountOnly:
    def test_count_fact_in_output(self):
        result = _make_result(["count satisfied: >= 2 person"])
        expl = generate_explanation(result)
        assert "count satisfied" in expl, expl


# ---------------------------------------------------------------------------
# Truncation at 80 chars
# ---------------------------------------------------------------------------

class TestTruncation:
    def test_long_fact_truncated(self):
        long_fact = "x" * 100
        result = _make_result([long_fact])
        expl = generate_explanation(result)
        # The fact in the output should be at most _MAX_FACT_LEN chars
        # (plus the trailing "…")
        facts_part = expl.replace("Matched because: ", "").split(". Confidence:")[0]
        assert len(facts_part) <= _MAX_FACT_LEN + 1  # +1 for "…"
        assert "…" in expl, "Truncated fact should end with ellipsis"

    def test_short_fact_not_truncated(self):
        short_fact = "person detected"
        result = _make_result([short_fact])
        expl = generate_explanation(result)
        assert "person detected" in expl
        assert "…" not in expl


# ---------------------------------------------------------------------------
# Confidence formatting
# ---------------------------------------------------------------------------

class TestConfidenceFormatting:
    def test_confidence_1_shows_two_decimals(self):
        result = _make_result(["person detected"], score=1.0)
        expl = generate_explanation(result)
        assert "1.00" in expl, expl

    def test_confidence_zero_shows_two_decimals(self):
        result = _make_result(["person detected"], score=0.0)
        expl = generate_explanation(result)
        assert "0.00" in expl, expl

    def test_confidence_shown_at_two_decimal_places(self):
        result = _make_result(["person detected"], score=0.9)
        expl = generate_explanation(result)
        # Should be "0.90" not "0.9"
        assert "0.90" in expl, expl
