"""
engine/search.py — Structured search engine for Ask-N-Seek (SQLite backend).

All retrieval is structured SQL filtering — no vector similarity, no Qdrant,
no embeddings. Filters are applied in Python post-query for spatial/negation/count.

Pipeline
--------
1. SQL query  : class_name + color filters (index-backed)
2. Group by frame: (video_id, frame_index) → list of detections
3. Spatial filter: object-level post-filter on spatial_relations
4. Negation filter: frame-level post-filter — drop frames where negated class exists
5. Count filter  : frame-level post-filter — keep frames with ≥/=/≤ N objects
6. Build Result  : aggregate matched_objects, compute confidence, facts

Field name note
---------------
SQLite stores objects under 'class_name' (not 'class').
The Achilles filter dict uses 'class' as the key.
This module maps filters["class"] → "class_name" internally.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

# ---------------------------------------------------------------------------
# Result dataclass (public contract — unchanged from Qdrant version)
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
        Detection rows for matching objects in this frame.
    confidence_score : float
        Maximum confidence among matched_objects.
    explanation_facts : list[str]
        Structured facts for templated explanation generation.
    score_breakdown : ScoreBreakdown | None
        Per-dimension score breakdown.
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
    # Legacy positional args (ignored — kept for call-site compat during migration)
    _client: Any = None,
    _collection: Any = None,
) -> list[Result]:
    """
    Execute a structured search against SQLite and return ranked results.

    Parameters
    ----------
    filter_dict : dict
        Parsed filter dict in Achilles format:
        {"status": "match"|"no_match", "filters": {...}}
    _client, _collection : ignored (legacy Qdrant args, kept for compat)

    Returns
    -------
    list[Result] sorted by confidence_score descending.
    """
    from engine.storage import search_detections, get_all_in_frames

    if filter_dict.get("status") != "match":
        return []

    filters: dict = filter_dict.get("filters", {})
    if not filters:
        return []

    class_filter: str | None      = filters.get("class")
    color_filter:  str | None     = filters.get("color")
    negated:       list[str]      = filters.get("negated") or []
    spatial:       dict | None    = filters.get("spatial_relation")
    count_constraint: dict | None = filters.get("count_constraint")
    video_id:      str | None     = filters.get("video_id")

    # -----------------------------------------------------------------------
    # Step 1: SQL query — class_name + color (index-backed, fast)
    # -----------------------------------------------------------------------
    # Resolve the class to query. If we have a top-level class filter, use it.
    # If only count_constraint carries a class, use that to reduce data volume.
    query_class = class_filter or (
        count_constraint.get("class") if count_constraint else None
    )

    candidate_rows = search_detections(
        class_name=query_class,
        color=color_filter,
        video_id=video_id,
        limit=1000,  # generous — Python-level filters will reduce this
    )

    if not candidate_rows:
        return []

    # -----------------------------------------------------------------------
    # Step 2: Group candidate rows by (video_id, frame_index)
    # -----------------------------------------------------------------------
    candidates_by_frame: dict[tuple, list[dict]] = defaultdict(list)
    for row in candidate_rows:
        key = (row["video_id"], row["frame_index"])
        candidates_by_frame[key].append(row)

    # -----------------------------------------------------------------------
    # Step 3: Apply spatial filter (object-level + cross-object frame check)
    # -----------------------------------------------------------------------
    if spatial:
        from engine.storage import get_all_in_frames as _get_all_in_frames

        # First collect all frame keys we need to cross-check
        vid_to_frames: dict[str, list[int]] = defaultdict(list)
        for (vid, fidx) in candidates_by_frame:
            vid_to_frames[vid].append(fidx)

        # Bulk-fetch ALL detections in candidate frames (not just primary class)
        all_objects_by_frame: dict[tuple, list[dict]] = {}
        for vid, frame_idxs in vid_to_frames.items():
            frame_map = _get_all_in_frames(vid, frame_idxs)
            for fidx, rows in frame_map.items():
                all_objects_by_frame[(vid, fidx)] = rows

        filtered: dict[tuple, list[dict]] = {}
        for key, objs in candidates_by_frame.items():
            # Direction A: primary object itself has the spatial relation
            direct_match = [o for o in objs if _has_spatial_relation(o, spatial, class_filter)]
            if direct_match:
                filtered[key] = direct_match
                continue

            # Direction B: any OTHER object in the same frame has the
            # INVERSE spatial relation (e.g. person has 'near car' recorded on
            # the person row, not the car row — both are symmetric for 'near').
            all_in_frame = all_objects_by_frame.get(key, [])
            target_cls = spatial.get("target_class", "")
            rel_type   = spatial.get("type", "near")

            # Build inverse spatial spec: look for target_class objects that
            # have a spatial relation with class_filter (the primary class)
            inverse_spatial = {
                "type":         rel_type,
                "target_class": class_filter or "",
            }
            cross_match = [
                o for o in all_in_frame
                if o.get("class_name") == target_cls
                and _has_spatial_relation(o, inverse_spatial, target_cls)
            ]
            if cross_match:
                filtered[key] = objs  # keep the original primary-class objects
                continue

            # Direction C (proximity fallback for 'near'): if the spatial type
            # is 'near', simply require both classes to co-exist in the same frame.
            # This handles cases where spatial_relations was not fully written for
            # some detections (e.g. low-confidence frames at ingest time).
            if rel_type == "near":
                co_exists = any(
                    o.get("class_name") == target_cls
                    for o in all_in_frame
                )
                if co_exists:
                    filtered[key] = objs

        candidates_by_frame = filtered

    if not candidates_by_frame:
        return []

    # -----------------------------------------------------------------------
    # Step 4: Apply negation filter (frame-level — checks ALL objects in frame)
    # -----------------------------------------------------------------------
    if negated:
        # Fetch all objects in the candidate frames (not just the matched class)
        # so we can check for presence of negated classes.
        NEGATION_EXCLUSION_THRESH = 0.40

        # Group frame_indices by video_id for bulk fetch
        vid_to_frames: dict[str, list[int]] = defaultdict(list)
        for (vid, fidx) in candidates_by_frame:
            vid_to_frames[vid].append(fidx)

        all_by_frame: dict[tuple, list[dict]] = {}
        for vid, frame_idxs in vid_to_frames.items():
            frame_map = get_all_in_frames(vid, frame_idxs)
            for fidx, rows in frame_map.items():
                all_by_frame[(vid, fidx)] = rows

        filtered = {}
        for key, objs in candidates_by_frame.items():
            all_in_frame = all_by_frame.get(key, objs)
            has_confident_negated = any(
                o.get("class_name") in negated
                and float(o.get("confidence", 1.0)) >= NEGATION_EXCLUSION_THRESH
                for o in all_in_frame
            )
            if not has_confident_negated:
                filtered[key] = objs
        candidates_by_frame = filtered

    # -----------------------------------------------------------------------
    # Step 5: Apply count constraint (frame-level)
    # -----------------------------------------------------------------------
    if count_constraint:
        cc_class = count_constraint.get("class")
        cc_op    = count_constraint.get("operator", ">=")
        cc_val   = int(count_constraint.get("value", 1))

        filtered = {}
        for key, objs in candidates_by_frame.items():
            if cc_class:
                countable = [o for o in objs if o.get("class_name") == cc_class]
            else:
                countable = objs
            if _apply_operator(len(countable), cc_op, cc_val):
                filtered[key] = objs
        candidates_by_frame = filtered

    # -----------------------------------------------------------------------
    # Step 6: Build Result objects
    # -----------------------------------------------------------------------
    from engine.result_scoring import score_result

    results: list[Result] = []
    for (vid, frame_index), objs in candidates_by_frame.items():
        if not objs:
            continue
        ref = objs[0]
        confidence_score = max(float(o.get("confidence", 0.0)) for o in objs)
        explanation_facts = _build_facts(objs, filters)

        result = Result(
            video_id=vid,
            timestamp=float(ref["timestamp"]),
            scene_id=int(ref.get("scene_id", 0)),
            matched_objects=list(objs),
            confidence_score=confidence_score,
            explanation_facts=explanation_facts,
        )
        result.score_breakdown = score_result(result, filter_dict)
        results.append(result)

    # Sort by confidence descending, cap at 20 for frontend performance
    results.sort(key=lambda r: r.confidence_score, reverse=True)
    return results[:20]


def group_by_video(results: list[Result]) -> dict[str, list[Result]]:
    """Group a sorted result list by video_id (preserves confidence order)."""
    grouped: dict[str, list[Result]] = defaultdict(list)
    for r in results:
        grouped[r.video_id].append(r)
    return dict(grouped)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _has_spatial_relation(
    obj: dict,
    spatial: dict,
    primary_class: str | None = None,
) -> bool:
    """
    Return True if the object has the requested spatial relation.

    Handles two stored formats:
    - Dict format (Achilles SpatialRelation TypedDict):
        {"subject": "person", "subject_idx": 0, "relation": "near",
         "object_": "car", "object_idx": 1}
      Key is "object_" (trailing underscore to avoid Python keyword clash).
    - String format: "left_of:car"  (legacy stub data)

    NOTE: filter dict uses key "target_class" (parser output),
    but SQLite payload uses "object_" (Achilles spatial.py).
    """
    rel_type   = spatial.get("type", "")
    target_cls = spatial.get("target_class", "")
    relations  = obj.get("spatial_relations") or []

    for rel in relations:
        if isinstance(rel, dict):
            obj_class  = rel.get("object_") or rel.get("object_class") or ""
            subj_class = rel.get("subject") or rel.get("subject_class") or ""
            rel_kind   = rel.get("relation") or rel.get("type") or ""

            if rel_kind == rel_type:
                # Direct match: this object IS the subject, target is the object
                if obj_class == target_cls:
                    return True
                # Reverse direction: this object IS the object, target is the subject
                # (e.g. obj=car has relation near person — subject=person, object_=car)
                if subj_class == target_cls:
                    return True
        elif isinstance(rel, str):
            # e.g. "left_of:car"
            if rel == f"{rel_type}:{target_cls}":
                return True
    return False


def _apply_operator(count: int, op: str, value: int) -> bool:
    """Apply a comparison operator for count constraints."""
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
) -> list[str]:
    """Build structured explanation facts. No hallucination."""
    facts: list[str] = []

    # 1. Class
    class_names = {o.get("class_name") for o in matched_objs if o.get("class_name")}
    for cls in sorted(class_names):
        facts.append(f"{cls} detected")

    # 2. Negation
    for neg_cls in (filters.get("negated") or []):
        facts.append(f"no {neg_cls} detected")

    # 3. Color
    color_filter = filters.get("color")
    if color_filter:
        facts.append(f"{color_filter} color confirmed")

    # 4. Spatial
    spatial = filters.get("spatial_relation")
    if spatial:
        rel_type   = spatial.get("type", "").replace("_", " ")
        target_cls = spatial.get("target_class", "")
        facts.append(f"{rel_type} {target_cls}")

    # 5. Count
    count_constraint = filters.get("count_constraint")
    if count_constraint:
        cc_class = count_constraint.get("class", "object")
        cc_op    = count_constraint.get("operator", ">=")
        cc_val   = count_constraint.get("value", 1)
        facts.append(f"count satisfied: {cc_op} {cc_val} {cc_class}")

    return facts
