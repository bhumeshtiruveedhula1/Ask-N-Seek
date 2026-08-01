"""
engine/search.py — Structured search engine for Odysseus Part 3.

This module implements filter-based retrieval over a Qdrant collection.
NO vector similarity, NO FAISS, NO embedding models are used — all retrieval
is structured payload filtering and in-Python post-filtering.

Pipeline
--------
1. Qdrant query  : class_name + color filters (index-backed keyword match)
2. Group by frame: deduplicate multiple objects in the same frame
3. Spatial filter: object-level post-filter on spatial_relations field
4. Negation filter: frame-level post-filter — drop frames where any negated
                    class exists (checks ALL objects in that frame)
5. Count filter  : frame-level post-filter — keep frames with ≥/=/≤ N objects
6. Build Result  : aggregate matched_objects, compute confidence, facts

Field name note
---------------
Part 2 stores objects under 'class_name' (not 'class').
The Achilles filter dict uses 'class' as the key.
This module maps filters["class"] → "class_name" internally.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

from qdrant_client import QdrantClient
from qdrant_client.models import FieldCondition, Filter, MatchValue

from config import FIELD_MAP, STUB_COLLECTION

# ---------------------------------------------------------------------------
# Qdrant payload field aliases (derived from FIELD_MAP — edit config.py, not here)
# ---------------------------------------------------------------------------
_FC  = FIELD_MAP["filter_class"]       # "class"             — key in filter_dict
_QC  = FIELD_MAP["qdrant_class"]       # "class_name"        — Qdrant payload
_QO  = FIELD_MAP["qdrant_color"]       # "color"             — Qdrant payload
_QS  = FIELD_MAP["qdrant_spatial"]     # "spatial_relations" — Qdrant payload
_QF  = FIELD_MAP["qdrant_confidence"]  # "confidence"        — Qdrant payload
_QV  = FIELD_MAP["qdrant_video_id"]    # "video_id"          — Qdrant payload
_QI  = FIELD_MAP["qdrant_frame_idx"]   # "frame_index"       — Qdrant payload
_QT  = FIELD_MAP["qdrant_timestamp"]   # "timestamp"         — Qdrant payload
_QN  = FIELD_MAP["qdrant_scene_id"]    # "scene_id"          — Qdrant payload


# ---------------------------------------------------------------------------
# Result dataclass (public contract)
# ---------------------------------------------------------------------------

@dataclass
class Result:
    """
    A single frame-level search result.

    Attributes
    ----------
    video_id : str
    timestamp : float
    scene_id : int
    matched_objects : list[dict]
        Full Qdrant payloads of all matching objects in this frame.
    confidence_score : float
        Maximum confidence among matched_objects.
    explanation_facts : list[str]
        Structured facts for templated explanation generation (no hallucination).
    score_breakdown : ScoreBreakdown | None
        Per-dimension score breakdown (populated by search_structured).
    """
    video_id: str
    timestamp: float
    scene_id: int
    matched_objects: list[dict]
    confidence_score: float
    explanation_facts: list[str] = field(default_factory=list)
    score_breakdown: "ScoreBreakdown | None" = field(default=None, repr=False)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def search_structured(
    filter_dict: dict,
    client: QdrantClient | None = None,
    collection_name: str | None = None,
) -> list[Result]:
    """
    Execute a structured search against Qdrant and return ranked results.

    Parameters
    ----------
    filter_dict : dict
        Parsed filter dict in the Achilles output contract format:
        {"status": "match"|"no_match", "filters": {...}}
    client : QdrantClient
        Active Qdrant client (in-memory stub or production).
    collection_name : str
        Target collection name.

    Returns
    -------
    list[Result]
        Results sorted by confidence_score descending.
        Empty list if status is "no_match" or no frames pass all filters.
    """
    # Resolve client and collection from qdrant_gateway if not supplied
    if client is None:
        from engine.qdrant_gateway import get_qdrant_client
        client = get_qdrant_client()
    if collection_name is None:
        from engine.qdrant_gateway import get_collection_name
        collection_name = get_collection_name()

    if filter_dict.get("status") != "match":
        return []

    filters: dict = filter_dict.get("filters", {})
    if not filters:
        return []

    class_filter: str | None      = filters.get(_FC)
    color_filter: str | None      = filters.get("color")
    negated: list[str]            = filters.get("negated") or []
    spatial: dict | None          = filters.get("spatial_relation")
    count_constraint: dict | None = filters.get("count_constraint")

    # -----------------------------------------------------------------------
    # Step 1: Qdrant query — class_name + color (index-backed, fast)
    # -----------------------------------------------------------------------
    must_conditions = []

    # Determine which class to query from Qdrant.
    # If top-level class filter: use it.
    # Else if count_constraint carries a class: use that to reduce data volume.
    qdrant_class = class_filter or (
        count_constraint.get("class") if count_constraint else None
    )

    if qdrant_class:
        must_conditions.append(
            FieldCondition(key=_QC, match=MatchValue(value=qdrant_class))
        )
    if color_filter:
        must_conditions.append(
            FieldCondition(key=_QO, match=MatchValue(value=color_filter))
        )

    qdrant_filter = Filter(must=must_conditions) if must_conditions else None

    # Fetch candidate objects from Qdrant (all matching class + color)
    candidate_points = _scroll_all(client, collection_name, qdrant_filter)

    if not candidate_points:
        return []

    # Collect all frame keys that have at least one candidate
    candidate_frame_keys: set[tuple[str, int]] = {
        (_p["video_id"], _p["frame_index"]) for _p in candidate_points
    }

    # -----------------------------------------------------------------------
    # Step 2: Fetch ALL objects in candidate frames (needed for negation)
    # -----------------------------------------------------------------------
    # For stub data this is a full scroll — acceptable for 72 rows.
    # For production, use a targeted filter on video_id + frame_index.
    all_points = _scroll_all(client, collection_name, qdrant_filter=None)

    all_by_frame: dict[tuple, list[dict]] = defaultdict(list)
    for p in all_points:
        key = (p[_QV], p[_QI])
        all_by_frame[key].append(p)

    # Group candidates by frame
    candidates_by_frame: dict[tuple, list[dict]] = defaultdict(list)
    for p in candidate_points:
        key = (p[_QV], p[_QI])
        candidates_by_frame[key].append(p)

    # -----------------------------------------------------------------------
    # Step 3: Apply spatial filter (object-level)
    # -----------------------------------------------------------------------
    if spatial:
        filtered: dict[tuple, list[dict]] = {}
        for key, objs in candidates_by_frame.items():
            matching = [o for o in objs if _has_spatial_relation(o, spatial)]
            if matching:
                filtered[key] = matching
        candidates_by_frame = filtered

    # -----------------------------------------------------------------------
    # Step 4: Apply negation filter (frame-level — checks ALL objects)
    # -----------------------------------------------------------------------
    if negated:
        filtered = {}
        for key, objs in candidates_by_frame.items():
            all_in_frame = all_by_frame.get(key, [])
            frame_classes = {o.get(_QC) for o in all_in_frame}
            if not frame_classes.intersection(negated):
                filtered[key] = objs
        candidates_by_frame = filtered

    # -----------------------------------------------------------------------
    # Step 5: Apply count constraint (frame-level)
    # -----------------------------------------------------------------------
    if count_constraint:
        cc_class   = count_constraint.get("class")
        cc_op      = count_constraint.get("operator", ">=")
        cc_val     = int(count_constraint.get("value", 1))

        filtered = {}
        for key, objs in candidates_by_frame.items():
            # Count objects of cc_class in this frame's matched objects
            if cc_class:
                countable = [o for o in objs if o.get(_QC) == cc_class]
            else:
                countable = objs
            if _apply_operator(len(countable), cc_op, cc_val):
                filtered[key] = objs
        candidates_by_frame = filtered

    # -----------------------------------------------------------------------
    # Step 6: Build Result objects
    # -----------------------------------------------------------------------
    from engine.result_scoring import score_result  # local import avoids circular

    results: list[Result] = []
    for (video_id, frame_index), objs in candidates_by_frame.items():
        if not objs:
            continue
        ref = objs[0]  # use first matched object for frame-level metadata
        confidence_score = max(o.get(_QF, 0.0) for o in objs)
        explanation_facts = _build_facts(objs, filters, all_by_frame.get((video_id, frame_index), []))

        result = Result(
            video_id=video_id,
            timestamp=ref[_QT],
            scene_id=ref[_QN],
            matched_objects=list(objs),
            confidence_score=confidence_score,
            explanation_facts=explanation_facts,
        )
        result.score_breakdown = score_result(result, filter_dict)
        results.append(result)

    # -----------------------------------------------------------------------
    # Rerank by confidence descending
    # -----------------------------------------------------------------------
    results.sort(key=lambda r: r.confidence_score, reverse=True)
    return results


def group_by_video(results: list[Result]) -> dict[str, list[Result]]:
    """Group a sorted result list by video_id (preserves confidence order)."""
    grouped: dict[str, list[Result]] = defaultdict(list)
    for r in results:
        grouped[r.video_id].append(r)
    return dict(grouped)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _scroll_all(
    client: QdrantClient,
    collection_name: str,
    qdrant_filter: Filter | None,
    page_size: int = 500,
) -> list[dict]:
    """
    Retrieve all matching points from Qdrant via paginated scroll.

    Returns a flat list of payload dicts (point IDs stripped).
    """
    payloads: list[dict] = []
    offset: Any = None

    while True:
        response, next_offset = client.scroll(
            collection_name=collection_name,
            scroll_filter=qdrant_filter,
            limit=page_size,
            offset=offset,
            with_payload=True,
            with_vectors=False,
        )
        for point in response:
            payloads.append(point.payload or {})

        if next_offset is None:
            break
        offset = next_offset

    return payloads


def _has_spatial_relation(obj: dict, spatial: dict) -> bool:
    """
    Return True if the object has the requested spatial relation.

    Handles two stored formats:
    - Dict format (Achilles SpatialRelation TypedDict):
        {"subject": "sun", "subject_idx": 1, "relation": "left_of",
         "object_": "sky", "object_idx": 0}
      Key is "object_" (trailing underscore to avoid Python keyword clash).
    - String format: "left_of:car"  (legacy stub data)

    NOTE: filter dict uses key "target_class" (parser output),
    but Qdrant payload uses "object_" (Achilles spatial.py).
    """
    rel_type    = spatial.get("type", "")
    target_cls  = spatial.get("target_class", "")
    relations   = obj.get(_QS) or []

    for rel in relations:
        if isinstance(rel, dict):
            # Achilles stores target class under "object_", not "target_class"
            if rel.get("relation") == rel_type and rel.get("object_") == target_cls:
                return True
        elif isinstance(rel, str):
            # e.g. "left_of:car"
            if rel == f"{rel_type}:{target_cls}":
                return True
    return False


def _apply_operator(count: int, op: str, value: int) -> bool:
    """Apply a comparison operator for count constraints.

    Accepts both symbolic and word-form operators:
      ">="  | "gte"  → count >= value
      ">"   | "gt"   → count >  value
      "=="  | "="    | "eq" → count == value
      "<="  | "lte"  → count <= value
      "<"   | "lt"   → count <  value

    Achilles's patterns.py emits word-form operators ("gt", "gte", etc.).
    Stub parser also uses word forms. Both are handled here.
    """
    if op in (">=", "gte"):
        return count >= value
    if op in (">", "gt"):
        return count > value
    if op in ("==", "=", "eq"):
        return count == value
    if op in ("<=", "lte"):
        return count <= value
    if op in ("<", "lt"):
        return count < value
    return False


def _build_facts(
    matched_objs: list[dict],
    filters: dict,
    all_frame_objs: list[dict],
) -> list[str]:
    """
    Build a list of structured explanation facts from filter results.
    Facts are derived only from actual data — no hallucination.
    """
    facts: list[str] = []

    # 1. Class fact
    class_names = {o.get(_QC) for o in matched_objs if o.get(_QC)}
    for cls in sorted(class_names):
        facts.append(f"{cls} detected")

    # 2. Negation facts (spec order: class → negation → color → spatial → count)
    negated: list[str] = filters.get("negated") or []
    for neg_cls in negated:
        facts.append(f"no {neg_cls} detected")

    # 3. Color fact
    color_filter = filters.get("color")
    if color_filter:
        facts.append(f"{color_filter} color confirmed")

    # 4. Spatial fact
    spatial = filters.get("spatial_relation")
    if spatial:
        rel_type   = spatial.get("type", "").replace("_", " ")
        target_cls = spatial.get("target_class", "")
        facts.append(f"{rel_type} {target_cls}")

    # 5. Count fact
    count_constraint = filters.get("count_constraint")
    if count_constraint:
        cc_class = count_constraint.get("class", "object")
        cc_op    = count_constraint.get("operator", ">=")
        cc_val   = count_constraint.get("value", 1)
        actual   = sum(1 for o in matched_objs if o.get(_QC) == cc_class)
        facts.append(f"count satisfied: {cc_op} {cc_val} {cc_class}")

    return facts
