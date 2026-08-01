"""
engine/result_scoring.py — Per-result score breakdown for Ask-N-Seek.

Computes a 0-100 score split across four categories:
  object_score   (0-40) — confidence of class match
  color_score    (0-20) — ratio of objects with the requested color
  spatial_score  (0-20) — presence of requested spatial relation
  negation_score (0-20) — negation constraint satisfied (passed search filter)

The module is completely stateless: same inputs always produce same outputs.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from engine.search import Result

# Qdrant payload field names (mirrors config.py → FIELD_MAP)
_QC = "class_name"
_QO = "color"
_QF = "confidence"
_QS = "spatial_relations"


# ---------------------------------------------------------------------------
# Public dataclass
# ---------------------------------------------------------------------------

@dataclass
class ScoreBreakdown:
    """
    Per-dimension score breakdown for a single Result.

    Attributes
    ----------
    total          : 0-100 sum of the four category scores
    object_score   : 0-40
    color_score    : 0-20
    spatial_score  : 0-20
    negation_score : 0-20
    details        : human-readable explanation per category
    """
    total: int
    object_score: int
    color_score: int
    spatial_score: int
    negation_score: int
    details: dict[str, str] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def score_result(result: "Result", filter_dict: dict) -> ScoreBreakdown:
    """
    Compute a ScoreBreakdown for *result* given the query's *filter_dict*.

    Parameters
    ----------
    result      : engine.search.Result
    filter_dict : {"status": "match", "filters": {...}}

    Returns
    -------
    ScoreBreakdown
    """
    filters: dict = filter_dict.get("filters", {})
    objs: list[dict] = result.matched_objects

    # All-zero guard — empty matched_objects
    if not objs:
        return ScoreBreakdown(
            total=0,
            object_score=0,
            color_score=0,
            spatial_score=0,
            negation_score=0,
            details={
                "object": "no objects matched",
                "color": "no objects matched",
                "spatial": "no objects matched",
                "negation": "no objects matched",
            },
        )

    object_score, object_detail     = _score_object(objs, filters)
    color_score,  color_detail      = _score_color(objs, filters)
    spatial_score, spatial_detail   = _score_spatial(objs, filters)
    negation_score, negation_detail = _score_negation(filters)

    total = object_score + color_score + spatial_score + negation_score

    return ScoreBreakdown(
        total=total,
        object_score=object_score,
        color_score=color_score,
        spatial_score=spatial_score,
        negation_score=negation_score,
        details={
            "object": object_detail,
            "color": color_detail,
            "spatial": spatial_detail,
            "negation": negation_detail,
        },
    )


# ---------------------------------------------------------------------------
# Category scorers
# ---------------------------------------------------------------------------

def _score_object(objs: list[dict], filters: dict) -> tuple[int, str]:
    """
    Object score (0-40).

    With class filter : average confidence of objects whose class_name matches.
    Without           : max confidence across all matched objects.
    Confidence values are 0.0-1.0; scaled by 40.
    """
    class_filter: str | None = filters.get("class")

    if class_filter:
        matching = [o for o in objs if o.get(_QC) == class_filter]
        if not matching:
            return 0, f"{class_filter} not found in matched objects"
        avg_conf = sum(o.get(_QF, 0.0) for o in matching) / len(matching)
        score = round(avg_conf * 40)
        return score, f"{class_filter} detected, conf {avg_conf:.2f}"

    # No class constraint — use max confidence
    max_conf = max(o.get(_QF, 0.0) for o in objs)
    score = round(max_conf * 40)
    return score, f"no object constraint, max conf {max_conf:.2f}"


def _score_color(objs: list[dict], filters: dict) -> tuple[int, str]:
    """
    Color score (0-20).

    With color filter : fraction of matched objects that have the target color.
    Without           : 0 (no constraint applied).
    """
    color_filter: str | None = filters.get("color")

    if not color_filter:
        return 0, "no color constraint"

    matched_color = sum(1 for o in objs if o.get(_QO) == color_filter)
    total = len(objs)
    ratio = matched_color / total
    score = round(ratio * 20)

    if matched_color > 0:
        return score, f"{color_filter} color confirmed ({matched_color}/{total})"
    return 0, f"color mismatch — expected {color_filter}, got {set(o.get(_QO) for o in objs)}"


def _score_spatial(objs: list[dict], filters: dict) -> tuple[int, str]:
    """
    Spatial score (0-20).

    With spatial filter : 20 if ANY matched object has the relation, else 0.
    Without             : 0.
    """
    spatial: dict | None = filters.get("spatial_relation")

    if not spatial:
        return 0, "no spatial constraint"

    rel_type   = spatial.get("type", "")
    target_cls = spatial.get("target_class", "")

    for obj in objs:
        relations = obj.get(_QS) or []
        for rel in relations:
            if isinstance(rel, dict):
                if rel.get("relation") == rel_type and rel.get("object_") == target_cls:
                    return 20, f"{rel_type} {target_cls}"
            elif isinstance(rel, str):
                if rel == f"{rel_type}:{target_cls}":
                    return 20, f"{rel_type} {target_cls}"

    return 0, f"spatial constraint not met: {rel_type} {target_cls}"


def _score_negation(filters: dict) -> tuple[int, str]:
    """
    Negation score (0-20).

    Negation is enforced at search time in search.py — a Result that exists
    has already passed the negation filter. So if negated list is non-empty,
    score = 20 (constraint satisfied). If empty, score = 0 (no constraint).
    """
    negated: list[str] = filters.get("negated") or []

    if not negated:
        return 0, "no negation constraint"

    negated_str = ", ".join(negated)
    return 20, f"no {negated_str} detected"


# ---------------------------------------------------------------------------
# Manual verification block
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    from dataclasses import dataclass as _dc, field as _field

    # Minimal mock Result (avoids importing engine.search to keep this standalone)
    @_dc
    class _MockResult:
        video_id: str
        timestamp: float
        scene_id: int
        matched_objects: list
        confidence_score: float
        explanation_facts: list = _field(default_factory=list)

    print("=" * 60)
    print("  engine/result_scoring.py — manual verification")
    print("=" * 60)

    # ── Test 1: person in red, spatial left_of car ───────────────
    mock_result_1 = _MockResult(
        video_id="parking_lot",
        timestamp=23.5,
        scene_id=3,
        matched_objects=[
            {
                "class_name": "person",
                "color": "red",
                "confidence": 0.85,
                "spatial_relations": [{"relation": "left_of", "object_": "car"}],
            },
            {
                "class_name": "person",
                "color": "red",
                "confidence": 0.72,
                "spatial_relations": [],
            },
        ],
        confidence_score=0.85,
    )
    filter_1 = {
        "status": "match",
        "filters": {
            "class": "person",
            "color": "red",
            "negated": [],
            "spatial_relation": {"type": "left_of", "target_class": "car"},
            "count_constraint": None,
        },
    }
    bd1 = score_result(mock_result_1, filter_1)
    print("\nTest 1: person in red, left of car")
    print(f"  object_score   : {bd1.object_score}/40  — {bd1.details['object']}")
    print(f"  color_score    : {bd1.color_score}/20   — {bd1.details['color']}")
    print(f"  spatial_score  : {bd1.spatial_score}/20  — {bd1.details['spatial']}")
    print(f"  negation_score : {bd1.negation_score}/20  — {bd1.details['negation']}")
    print(f"  TOTAL          : {bd1.total}/100")
    assert bd1.object_score == round(((0.85 + 0.72) / 2) * 40), "object_score mismatch"
    assert bd1.color_score == 20, "color_score should be 20 (2/2 red)"
    assert bd1.spatial_score == 20, "spatial_score should be 20"
    assert bd1.negation_score == 0, "negation_score should be 0 (no negation)"
    print("  [PASS]")

    # ── Test 2: person without helmet ────────────────────────────
    mock_result_2 = _MockResult(
        video_id="construction_site",
        timestamp=45.0,
        scene_id=7,
        matched_objects=[
            {
                "class_name": "person",
                "color": "unknown",
                "confidence": 0.60,
                "spatial_relations": [],
            },
        ],
        confidence_score=0.60,
    )
    filter_2 = {
        "status": "match",
        "filters": {
            "class": "person",
            "color": None,
            "negated": ["helmet"],
            "spatial_relation": None,
            "count_constraint": None,
        },
    }
    bd2 = score_result(mock_result_2, filter_2)
    print("\nTest 2: person without helmet")
    print(f"  object_score   : {bd2.object_score}/40  — {bd2.details['object']}")
    print(f"  color_score    : {bd2.color_score}/20   — {bd2.details['color']}")
    print(f"  spatial_score  : {bd2.spatial_score}/20  — {bd2.details['spatial']}")
    print(f"  negation_score : {bd2.negation_score}/20  — {bd2.details['negation']}")
    print(f"  TOTAL          : {bd2.total}/100")
    assert bd2.object_score == round(0.60 * 40), "object_score mismatch"
    assert bd2.color_score == 0, "no color filter → 0"
    assert bd2.spatial_score == 0, "no spatial filter → 0"
    assert bd2.negation_score == 20, "negation present → 20"
    print("  [PASS]")

    # ── Test 3: empty matched_objects ────────────────────────────
    mock_result_3 = _MockResult(
        video_id="empty",
        timestamp=0.0,
        scene_id=0,
        matched_objects=[],
        confidence_score=0.0,
    )
    bd3 = score_result(mock_result_3, filter_2)
    print("\nTest 3: empty matched_objects")
    print(f"  TOTAL : {bd3.total}/100")
    assert bd3.total == 0, "empty → total must be 0"
    print("  [PASS]")

    print("\n" + "=" * 60)
    print("  All assertions passed. Scores are deterministic.")
    print("=" * 60)
