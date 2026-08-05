"""
engine/diagnosis.py — No-Match Diagnosis for Odysseus Part 3.

When search returns 0 results or best_score < threshold, decomposes the
stub-flat filter dict into individual sub-queries to explain which constraints
individually match and which combination causes the failure.

No LLM — all output is templated.
Does not call parse_query or change search_structured signature.
"""
from __future__ import annotations

import logging

from engine.search import search_structured, Result

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Sub-query builders — each returns a stub-flat filter dict for one constraint
# ---------------------------------------------------------------------------

def _fd(class_name, color=None, negated=None, spatial=None, count=None) -> dict:
    """Build a minimal stub-flat filter dict."""
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


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def run_diagnosis(
    filters: dict,
    # Legacy args from Qdrant era — ignored now, kept for call-site compat
    _client: object = None,
    _collection_name: str = "",
) -> dict:
    """
    Decompose filters into individual sub-queries and find the closest miss.

    Parameters
    ----------
    filters : dict
        Stub-flat filters dict (class, color, negated, spatial_relation, count_constraint).
    client : QdrantClient
    collection_name : str

    Returns
    -------
    dict with keys:
        constraint_counts : dict[str, int]   — hit count per sub-query
        closest_miss      : dict | None      — {relaxed_constraint, score, video_id, timestamp}
        html              : str              — rendered diagnosis HTML
    """
    cls       = filters.get("class")
    color     = filters.get("color")
    negated   = filters.get("negated") or []
    spatial   = filters.get("spatial_relation")
    count     = filters.get("count_constraint")

    counts: dict[str, int] = {}
    candidates: list[tuple[str, list[Result]]] = []  # (relaxed_constraint_name, results)

    # 1. Class only
    if cls:
        r = search_structured(_fd(cls))
        counts["class_only"] = len(r)
        if r:
            candidates.append(("class only", r))

    # 2. Class + color
    if cls and color:
        r = search_structured(_fd(cls, color=color))
        counts["class+color"] = len(r)
        if r:
            candidates.append(("class+color", r))

    # 3. Class + negated
    if cls and negated:
        r = search_structured(_fd(cls, negated=negated))
        counts["class+negated"] = len(r)
        if r:
            candidates.append(("class+negated", r))

    # 4. Class + spatial
    if cls and spatial:
        r = search_structured(_fd(cls, spatial=spatial))
        counts["class+spatial"] = len(r)
        if r:
            candidates.append(("class+spatial", r))

    # 5. Class + count
    if cls and count:
        r = search_structured(_fd(cls, count=count))
        counts["class+count"] = len(r)
        if r:
            candidates.append(("class+count", r))

    # Closest miss: the relaxed sub-query with the highest best_score
    closest_miss = None
    best_score   = 0.0
    for name, results in candidates:
        top_score = results[0].confidence_score if results else 0.0
        if top_score > best_score:
            best_score   = top_score
            closest_miss = {
                "relaxed_constraint": name,
                "score":              round(top_score, 4),
                "video_id":           results[0].video_id,
                "timestamp":          results[0].timestamp,
            }

    html = _render_diagnosis_html(cls, color, negated, spatial, count, counts, closest_miss)

    return {
        "constraint_counts": counts,
        "closest_miss":      closest_miss,
        "html":              html,
    }


# ---------------------------------------------------------------------------
# HTML rendering (no LLM — templated only)
# ---------------------------------------------------------------------------

def _render_diagnosis_html(
    cls, color, negated, spatial, count,
    counts: dict[str, int],
    closest_miss: dict | None,
) -> str:
    lines: list[str] = []

    # Per-constraint hit counts
    if cls:
        lines.append(f"<li><b>{cls}</b> detected: <b>{counts.get('class_only', 0)}</b> scene(s)</li>")
    if color:
        lines.append(
            f"<li>{cls} + color <b>{color}</b>: <b>{counts.get('class+color', 0)}</b> scene(s)</li>"
        )
    for neg in negated:
        lines.append(
            f"<li>without <b>{neg}</b>: <b>{counts.get('class+negated', 0)}</b> scene(s)</li>"
        )
    if spatial:
        rel  = spatial.get("type", "?")
        tgt  = spatial.get("target_class", "?")
        lines.append(
            f"<li>{cls} <b>{rel}</b> {tgt}: <b>{counts.get('class+spatial', 0)}</b> scene(s)</li>"
        )
    if count:
        op  = count.get("op", "?")
        val = count.get("value", "?")
        lines.append(
            f"<li>count {op} {val}: <b>{counts.get('class+count', 0)}</b> scene(s)</li>"
        )
    lines.append("<li>All constraints together: <b>0</b> scene(s)</li>")

    bullet_html = "".join(f"<ul style='margin:6px 0;padding-left:18px;'>{l}</ul>" for l in lines)

    if closest_miss:
        miss_line = (
            f"<p style='margin:10px 0 0;color:#fbbf24;font-size:0.85rem;'>"
            f"&#x1F3AF; Closest miss: <b>{closest_miss['video_id']}</b>"
            f" @ {closest_miss['timestamp']:.1f}s"
            f" — relaxing <b>{closest_miss['relaxed_constraint']}</b>"
            f" gives score <b>{closest_miss['score']:.2f}</b>"
            f"</p>"
        )
    else:
        miss_line = (
            "<p style='margin:10px 0 0;color:#94a3b8;font-size:0.85rem;'>"
            "No partial matches found for any individual constraint."
            "</p>"
        )

    return f"""
<div style="
    background:linear-gradient(135deg,#1e293b,#0f172a);
    border:1px solid #334155;
    border-radius:12px;
    padding:20px 24px;
    color:#e2e8f0;
    font-family:inherit;
">
  <div style="font-size:1rem;font-weight:600;margin-bottom:12px;">
    &#x1F50D; No confident match &mdash; here&rsquo;s why:
  </div>
  {bullet_html}
  {miss_line}
</div>
"""
