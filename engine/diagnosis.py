"""
engine/diagnosis.py — Intelligent No-Match Diagnosis for Ask-N-Seek.

When search returns 0 results or best_score < threshold, decomposes the
structured filter dict into individual sub-queries to explain which constraints
individually match, which combination causes failure, and computes the closest miss.

No LLM — all output is templated & deterministic Qdrant payload queries.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from qdrant_client import QdrantClient

from engine.search import search_structured, Result
from config import FIELD_MAP

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------

@dataclass
class ConstraintResult:
    constraint_type: str  # "must", "must_not", "count", "spatial"
    description: str      # Human-readable, e.g. "Object: person"
    scenes_matched: int   # How many scenes satisfy THIS constraint alone
    confidence: float     # Best score for this constraint alone


@dataclass
class ClosestMiss:
    video_id: str
    timestamp: float
    score: float
    violated_constraint: str  # Which constraint caused the miss
    what_was_found: str       # What the scene actually contained


@dataclass
class DiagnosisResult:
    query_text: str
    overall_status: str  # "no_match"
    constraint_breakdown: list[ConstraintResult]
    closest_miss: ClosestMiss | None
    suggested_rephrasing: str | None


# ---------------------------------------------------------------------------
# Internal constraint representation & helpers
# ---------------------------------------------------------------------------

def _build_flat_filter(
    class_name: str | None = None,
    color: str | None = None,
    negated: list[str] | None = None,
    spatial: dict | None = None,
    count: dict | None = None,
) -> dict:
    """Build a normalized flat filter dict for search_structured()."""
    return {
        "status": "match",
        "filters": {
            "class":            class_name,
            "color":            color,
            "negated":          negated or [],
            "spatial_relation": spatial,
            "count_constraint": count,
        },
    }


def _extract_clauses(structured_filter: dict) -> list[tuple[str, str, dict]]:
    """
    Extract individual clauses from structured_filter (supports both flat dict
    and Qdrant/ParseResult filter shapes).

    Returns
    -------
    list[tuple[constraint_type, description, sub_filter_dict]]
    """
    clauses: list[tuple[str, str, dict]] = []

    # Handle wrapper dict if present
    filters = structured_filter.get("filters", structured_filter)

    # 1. Flat dict format keys
    cls     = filters.get("class")
    color   = filters.get("color")
    negated = filters.get("negated") or []
    spatial = filters.get("spatial_relation")
    count   = filters.get("count_constraint")

    # 2. Qdrant filter format keys (must / must_not / spatial / counts)
    q_must     = filters.get("must") or []
    q_must_not = filters.get("must_not") or []
    q_spatial  = filters.get("spatial") or []
    q_counts   = filters.get("counts") or []

    # Parse flat format if present
    if cls or color or negated or spatial or count:
        if cls and not color:
            clauses.append((
                "must",
                f"Object: {cls}",
                _build_flat_filter(class_name=cls),
            ))
        if cls and color:
            clauses.append((
                "must",
                f"Object: {cls}",
                _build_flat_filter(class_name=cls),
            ))
            clauses.append((
                "must",
                f"Color: {color}",
                _build_flat_filter(class_name=cls, color=color),
            ))
        elif color:
            clauses.append((
                "must",
                f"Color: {color}",
                _build_flat_filter(color=color),
            ))

        for neg in negated:
            clauses.append((
                "must_not",
                f"Without: {neg}",
                # Sub-query for must_not: invert to test if negated object exists in DB
                _build_flat_filter(class_name=neg),
            ))

        if spatial:
            rel = spatial.get("type", "").replace("_", " ")
            tgt = spatial.get("target_class", "")
            clauses.append((
                "spatial",
                f"Spatial: {rel} {tgt}".strip(),
                _build_flat_filter(class_name=cls, spatial=spatial),
            ))

        if count:
            c_cls = count.get("class") or cls or "object"
            c_op  = count.get("op") or count.get("operator") or ">="
            c_val = count.get("value", 1)
            clauses.append((
                "count",
                f"Count: {c_op} {c_val} {c_cls}",
                _build_flat_filter(class_name=cls, count=count),
            ))

    # Fallback/supplement with Qdrant format keys if flat format was not parsed
    if not clauses:
        for m in q_must:
            k = m.get("key", "")
            v = m.get("match", {}).get("value", "")
            if "class_name" in k and v:
                cls = v
                clauses.append(("must", f"Object: {v}", _build_flat_filter(class_name=v)))
            elif "color" in k and v:
                clauses.append(("must", f"Color: {v}", _build_flat_filter(class_name=cls, color=v)))

        for mn in q_must_not:
            v = mn.get("match", {}).get("value", "")
            if v:
                clauses.append(("must_not", f"Without: {v}", _build_flat_filter(class_name=v)))

        for sp in q_spatial:
            rel = sp.get("relation", "").replace("_", " ")
            tgt = sp.get("object") or sp.get("target_class", "")
            sp_dict = {"type": sp.get("relation"), "target_class": tgt}
            clauses.append(("spatial", f"Spatial: {rel} {tgt}".strip(), _build_flat_filter(class_name=cls, spatial=sp_dict)))

        for cnt in q_counts:
            c_cls = cnt.get("class_name") or cls
            c_op  = cnt.get("operator", ">=")
            c_val = cnt.get("value", 1)
            cnt_dict = {"class": c_cls, "op": c_op, "value": c_val}
            clauses.append(("count", f"Count: {c_op} {c_val} {c_cls}", _build_flat_filter(class_name=cls, count=cnt_dict)))

    return clauses


def _describe_scene_content(res: Result) -> str:
    """Build a concise, human-readable summary of what a Result scene contained."""
    if res.explanation_facts:
        return ", ".join(res.explanation_facts)
    objs = res.matched_objects
    if not objs:
        return "Empty scene"
    qc = FIELD_MAP["qdrant_class"]
    qo = FIELD_MAP["qdrant_color"]
    items = []
    for o in objs:
        c = o.get(qc, "object")
        col = o.get(qo)
        items.append(f"{col} {c}" if col else c)
    return ", ".join(items)


# ---------------------------------------------------------------------------
# Core Diagnosis Engine
# ---------------------------------------------------------------------------

def diagnose_no_match(
    query_str: str,
    structured_filter: dict,
    collection_name: str | None = None,
    qdrant_client: "QdrantClient" | None = None,
) -> DiagnosisResult:
    """
    Decompose a query into individual constraints, run sub-queries,
    and present a breakdown plus closest miss and rephrasing suggestion.

    Parameters
    ----------
    query_str : str
        The raw user query string.
    structured_filter : dict
        Filter dict (flat or ParseResult qdrant_filter).
    collection_name : str | None
    qdrant_client : QdrantClient | None

    Returns
    -------
    DiagnosisResult
    """
    clauses = _extract_clauses(structured_filter)

    breakdown: list[ConstraintResult] = []

    # Step 1: Constraint-by-constraint breakdown
    for c_type, desc, sub_filter in clauses:
        res = search_structured(sub_filter, client=qdrant_client, collection_name=collection_name)
        scenes_matched = len(res)
        best_conf = res[0].confidence_score if res else 0.0
        breakdown.append(ConstraintResult(
            constraint_type=c_type,
            description=desc,
            scenes_matched=scenes_matched,
            confidence=round(best_conf, 4),
        ))

    # Step 2: Compute Closest Miss by relaxing ONE constraint at a time
    closest_miss: ClosestMiss | None = None
    best_relaxed_score = -1.0
    blocker_clause_desc: str | None = None
    blocker_scene_count: int = 0

    if len(clauses) > 1:
        for idx in range(len(clauses)):
            violated_desc = clauses[idx][1]
            # Omit constraint idx to build relaxed filter
            relaxed_clauses = [clauses[i] for i in range(len(clauses)) if i != idx]

            # Construct relaxed flat filter
            cls = None
            color = None
            negated = []
            spatial = None
            count = None

            for c_type, desc, s_filter in relaxed_clauses:
                f = s_filter.get("filters", {})
                if f.get("class") and not cls:
                    cls = f["class"]
                if f.get("color") and not color:
                    color = f["color"]
                if f.get("negated"):
                    negated.extend(f["negated"])
                if f.get("spatial_relation") and not spatial:
                    spatial = f["spatial_relation"]
                if f.get("count_constraint") and not count:
                    count = f["count_constraint"]

            relaxed_filter = _build_flat_filter(
                class_name=cls,
                color=color,
                negated=negated,
                spatial=spatial,
                count=count,
            )

            res = search_structured(relaxed_filter, client=qdrant_client, collection_name=collection_name)

            if res:
                top = res[0]
                if top.confidence_score > best_relaxed_score:
                    best_relaxed_score = top.confidence_score
                    blocker_clause_desc = violated_desc
                    blocker_scene_count = len(res)
                    closest_miss = ClosestMiss(
                        video_id=top.video_id,
                        timestamp=top.timestamp,
                        score=round(top.confidence_score, 4),
                        violated_constraint=violated_desc,
                        what_was_found=_describe_scene_content(top),
                    )

    # Step 3: Suggested Rephrasing
    suggested_rephrasing: str | None = None
    if closest_miss and blocker_clause_desc:
        clean_desc = blocker_clause_desc.replace("Object: ", "").replace("Color: ", "").replace("Spatial: ", "").replace("Without: ", "").replace("Count: ", "")
        suggested_rephrasing = f"Try removing '{clean_desc}' — {blocker_scene_count} scene(s) match without it."
    elif breakdown:
        # Check if a single constraint has 0 matches
        zero_matches = [c for c in breakdown if c.scenes_matched == 0]
        if zero_matches:
            z_desc = zero_matches[0].description.replace("Object: ", "").replace("Color: ", "").replace("Spatial: ", "").replace("Without: ", "").replace("Count: ", "")
            suggested_rephrasing = f"Constraint '{z_desc}' yielded 0 matches in database. Try broadening this term."

    return DiagnosisResult(
        query_text=query_str,
        overall_status="no_match",
        constraint_breakdown=breakdown,
        closest_miss=closest_miss,
        suggested_rephrasing=suggested_rephrasing,
    )


# ---------------------------------------------------------------------------
# HTML Renderer
# ---------------------------------------------------------------------------

def render_diagnosis_html(diagnosis: DiagnosisResult) -> str:
    """Render a DiagnosisResult into a clean, modern HTML diagnosis card."""
    rows_html = []
    max_count = max((c.scenes_matched for c in diagnosis.constraint_breakdown), default=1)
    if max_count == 0:
        max_count = 1

    for c in diagnosis.constraint_breakdown:
        pct = int((c.scenes_matched / max_count) * 100) if c.scenes_matched > 0 else 0
        if c.scenes_matched > 0:
            bar_color = "linear-gradient(90deg, #10b981, #059669)"
            badge_class = "background:rgba(16,185,129,0.15);color:#10b981;border:1px solid rgba(16,185,129,0.3);"
        else:
            pct = 100
            bar_color = "linear-gradient(90deg, #ef4444, #dc2626)"
            badge_class = "background:rgba(239,68,68,0.15);color:#ef4444;border:1px solid rgba(239,68,68,0.3);"

        rows_html.append(f"""
        <div style="margin-bottom:10px;">
          <div style="display:flex;justify-content:space-between;font-size:0.85rem;margin-bottom:4px;">
            <span style="font-weight:500;color:#e2e8f0;">{c.description}</span>
            <span style="padding:2px 8px;border-radius:12px;font-size:0.75rem;font-weight:600;{badge_class}">
              {c.scenes_matched} scene(s)
            </span>
          </div>
          <div style="height:6px;background:#1e293b;border-radius:3px;overflow:hidden;">
            <div style="width:{pct}%;height:100%;background:{bar_color};border-radius:3px;transition:width 0.3s;"></div>
          </div>
        </div>
        """)

    table_html = "".join(rows_html)

    # Closest miss section
    if diagnosis.closest_miss:
        cm = diagnosis.closest_miss
        miss_html = f"""
        <div style="margin-top:16px;padding:12px 14px;background:rgba(251,191,36,0.08);border:1px solid rgba(251,191,36,0.3);border-radius:8px;">
          <div style="font-weight:600;color:#fbbf24;font-size:0.85rem;margin-bottom:4px;">
            🎯 Closest match: {cm.video_id} @ {cm.timestamp:.1f}s (Score: {cm.score:.2f})
          </div>
          <div style="font-size:0.8rem;color:#cbd5e1;">
            <b>Found:</b> {cm.what_was_found}<br>
            <span style="color:#f59e0b;"><b>Violated constraint:</b> {cm.violated_constraint}</span>
          </div>
        </div>
        """
    else:
        miss_html = """
        <div style="margin-top:16px;padding:10px 14px;background:#1e293b;border-radius:8px;font-size:0.8rem;color:#94a3b8;">
          No partial matches found for individual constraints.
        </div>
        """

    # Rephrasing suggestion
    if diagnosis.suggested_rephrasing:
        rephrase_html = f"""
        <div style="margin-top:12px;padding:10px 14px;background:rgba(129,140,248,0.1);border:1px solid rgba(129,140,248,0.3);border-radius:8px;font-size:0.83rem;color:#c7d2fe;">
          💡 <b>Suggestion:</b> {diagnosis.suggested_rephrasing}
        </div>
        """
    else:
        rephrase_html = ""

    return f"""
<div style="
    background: linear-gradient(135deg, #0d0d20 0%, #11112a 100%);
    border: 1px solid #1e1e3f;
    border-radius: 12px;
    padding: 20px 24px;
    color: #e2e8f0;
    font-family: inherit;
">
  <div style="font-size:1rem;font-weight:600;margin-bottom:14px;color:#f87171;display:flex;align-items:center;gap:8px;">
    <span>🔍 No confident match found. Here's why:</span>
  </div>
  
  <div style="margin-bottom:12px;">
    {table_html}
  </div>
  
  {miss_html}
  {rephrase_html}
</div>
"""


# ---------------------------------------------------------------------------
# Backward Compatibility API
# ---------------------------------------------------------------------------

def run_diagnosis(
    filters: dict,
    client: "QdrantClient",
    collection_name: str,
    query_str: str = "",
) -> dict:
    """Legacy wrapper returning dict output contract for existing calls."""
    diag = diagnose_no_match(
        query_str=query_str,
        structured_filter=filters,
        collection_name=collection_name,
        qdrant_client=client,
    )
    return {
        "constraint_counts": {c.description: c.scenes_matched for c in diag.constraint_breakdown},
        "closest_miss": {
            "relaxed_constraint": diag.closest_miss.violated_constraint,
            "score": diag.closest_miss.score,
            "video_id": diag.closest_miss.video_id,
            "timestamp": diag.closest_miss.timestamp,
        } if diag.closest_miss else None,
        "html": render_diagnosis_html(diag),
        "diagnosis_result": diag,
    }
