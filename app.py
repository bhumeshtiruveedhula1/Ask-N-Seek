"""
app.py — Ask-N-Seek Streamlit Frontend
Progressive Filtering + Interactive Query Refinement + XAI Output.

Run:
    streamlit run app.py
"""

from __future__ import annotations

import sys
import os
import sqlite3
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import streamlit as st
from test_baseline_pipeline import (
    extract_entities_spacy,
    generate_sql_query,
    format_xai_explanation,
    setup_sample_database,
    DB_PATH,
)

# ---------------------------------------------------------------------------
# Page config — must be first Streamlit call
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="Ask-N-Seek | Video Intelligence",
    page_icon="🎯",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ---------------------------------------------------------------------------
# Custom CSS
# ---------------------------------------------------------------------------
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap');

html, body, [class*="css"] {
    font-family: 'Inter', system-ui, sans-serif !important;
    background-color: #07070f !important;
    color: #e2e8f0 !important;
}
.block-container { padding: 1.5rem 2rem 3rem !important; max-width: 1100px; }

.header-card {
    background: linear-gradient(135deg, #0d0d1a 0%, #12122a 100%);
    border: 1px solid #1e1e3f;
    border-radius: 16px;
    padding: 28px 32px 22px;
    margin-bottom: 24px;
    box-shadow: 0 8px 32px rgba(0,0,0,0.5);
    text-align: center;
}
.header-title {
    font-size: 2.4rem;
    font-weight: 700;
    background: linear-gradient(90deg, #818cf8, #c084fc, #f472b6);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
    margin: 0 0 6px;
    letter-spacing: -0.5px;
}
.header-sub { color: #64748b; font-size: 0.95rem; margin: 0; }
.badge {
    display: inline-block; margin-top: 12px; padding: 3px 14px;
    background: rgba(99,102,241,0.15); border: 1px solid rgba(99,102,241,0.4);
    border-radius: 20px; color: #818cf8; font-size: 0.72rem;
    font-weight: 600; letter-spacing: 0.8px; text-transform: uppercase;
}

/* Filter pills */
.filter-pill { display: inline-block; padding: 4px 12px; border-radius: 12px;
    font-size: 0.78rem; font-weight: 600; margin: 2px 3px; border: 1px solid; }
.pill-class  { background: rgba(99,102,241,0.15); border-color: #818cf8; color: #818cf8; }
.pill-color  { background: rgba(192,132,252,0.15); border-color: #c084fc; color: #c084fc; }
.pill-excl   { background: rgba(244,63,94,0.15);   border-color: #f43f5e; color: #f43f5e; }

/* Refinement prompt box */
.refine-box {
    background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
    border: 1px solid #f59e0b;
    border-radius: 14px;
    padding: 18px 22px;
    margin: 16px 0;
    box-shadow: 0 0 20px rgba(245,158,11,0.1);
}
.refine-title { font-size: 1rem; font-weight: 600; color: #fbbf24; margin-bottom: 6px; }
.refine-sub   { font-size: 0.85rem; color: #94a3b8; }

/* Result cards */
.result-card {
    background: #0f172a; border: 1px solid #1e293b; border-radius: 12px;
    padding: 16px 20px; margin: 8px 0;
    transition: border-color 0.2s, box-shadow 0.2s;
}
.result-card:hover { border-color: #6366f1; box-shadow: 0 0 0 2px rgba(99,102,241,0.15); }
.result-ts   { font-size: 1.15rem; font-weight: 600; color: #e2e8f0; }
.result-conf { font-size: 0.85rem; color: #94a3b8; margin-top: 4px; }
.conf-bar-bg { background: #1e293b; border-radius: 4px; height: 5px; margin-top: 8px; overflow: hidden; }
.conf-bar-fill { height: 100%; border-radius: 4px; background: linear-gradient(90deg, #6366f1, #c084fc); }

.section-label {
    font-size: 0.72rem; font-weight: 600; letter-spacing: 1.2px;
    text-transform: uppercase; color: #475569; margin: 18px 0 8px;
}
.empty-state { text-align: center; padding: 40px 20px; }
.empty-icon  { font-size: 3rem; margin-bottom: 12px; }
.empty-msg   { font-size: 0.9rem; color: #475569; }

/* Inputs & buttons */
div[data-testid="stTextInput"] > div > div > input {
    background: #0f172a !important; border: 1px solid #334155 !important;
    border-radius: 10px !important; color: #e2e8f0 !important;
    font-size: 1rem !important; padding: 12px 16px !important;
}
div[data-testid="stTextInput"] > div > div > input:focus {
    border-color: #6366f1 !important; box-shadow: 0 0 0 3px rgba(99,102,241,0.2) !important;
}
div[data-testid="stCheckbox"] label { color: #94a3b8 !important; font-size: 0.88rem !important; }
.stButton > button {
    background: linear-gradient(135deg, #6366f1, #8b5cf6) !important;
    color: white !important; border: none !important; border-radius: 10px !important;
    font-weight: 600 !important; padding: 10px 22px !important;
    font-size: 0.9rem !important; transition: opacity 0.2s !important;
}
.stButton > button:hover { opacity: 0.85 !important; }
div[data-testid="stExpander"] {
    background: #0d0d1a !important; border: 1px solid #1e1e3f !important;
    border-radius: 10px !important;
}
</style>
""", unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Session State Initialisation
# ---------------------------------------------------------------------------

def _init_state() -> None:
    defaults: dict = {
        # Core filter + results
        "active_filters":          {},
        "current_results":         [],
        "last_query":              "",
        "last_sql":                "",
        "last_sql_params":         [],
        "xai_lines":               [],
        "latency_ms":              0.0,
        "history":                 [],
        # ── Temporal conversational state ──────────────────────────────────
        # Holds timestamp_ms of the top result from the PREVIOUS search.
        # Passed into generate_sql_query() for follow-up queries like
        # "red car after that" -> AND timestamp_ms > <last_match_timestamp_ms>
        "last_match_timestamp_ms": None,
        # ── Refinement intercept state ──────────────────────────────────────
        "awaiting_refinement":     False,
        "pending_entities":        {},
        "submitted_query":         "",
        "submitted_progressive":   False,
    }
    for key, val in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = val


_init_state()
setup_sample_database(DB_PATH)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

COLOR_OPTIONS = ["Red", "Blue", "Black", "White", "Silver", "Green", "Yellow"]

_COLOR_EMOJI = {
    "Red": "🔴", "Blue": "🔵", "Black": "⚫", "White": "⚪",
    "Silver": "🪙", "Green": "🟢", "Yellow": "🟡",
}


# ---------------------------------------------------------------------------
# Core helpers
# ---------------------------------------------------------------------------

def _ms_to_hhmmss(ms: float) -> str:
    total_s = int(ms / 1000)
    h, rem = divmod(total_s, 3600)
    m, s   = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


def _is_vague(entities: dict) -> bool:
    """Return True when only object_class is set — color and exclusions absent."""
    return (
        bool(entities.get("object_class"))
        and not entities.get("color")
        and not entities.get("excluded_objects")
    )


def _merge_filters(base: dict, new_entities: dict) -> dict:
    """Progressive merge: scalars overwrite; excluded_objects list is unioned."""
    merged = dict(base)
    if new_entities.get("object_class"):
        merged["object_class"] = new_entities["object_class"]
    if new_entities.get("color"):
        merged["color"] = new_entities["color"]
    existing_excl = set(merged.get("excluded_objects", []))
    existing_excl.update(new_entities.get("excluded_objects", []))
    merged["excluded_objects"] = sorted(existing_excl)
    return merged


def _execute_sql_and_store(merged_filters: dict, source_query: str) -> None:
    """Run SQL against SQLite (with optional temporal window) and update all session-state result keys."""
    t0 = time.perf_counter()

    # Pass the temporal anchor timestamp from the previous search
    last_ts = st.session_state.get("last_match_timestamp_ms")
    sql, params = generate_sql_query(merged_filters, last_match_timestamp=last_ts)

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(sql, params).fetchall()
    conn.close()
    latency_ms = round((time.perf_counter() - t0) * 1000, 3)

    # Save the top-result timestamp for the next conversational turn
    top_ts: float | None = rows[0]["timestamp_ms"] if rows else None

    st.session_state.active_filters        = merged_filters
    st.session_state.current_results       = [dict(r) for r in rows]
    st.session_state.last_query            = source_query
    st.session_state.last_sql              = sql
    st.session_state.last_sql_params       = params
    st.session_state.latency_ms            = latency_ms
    st.session_state.last_match_timestamp_ms = top_ts
    st.session_state.xai_lines             = format_xai_explanation(
        merged_filters, last_match_timestamp=last_ts
    )
    st.session_state.history.insert(0, (source_query, len(rows)))
    # Clear refinement intercept
    st.session_state.awaiting_refinement = False
    st.session_state.pending_entities    = {}


def _handle_new_query(query: str, progressive: bool) -> None:
    """
    Called when the user submits a new query.

    Decision tree
    -------------
    1. Extract entities.
    2. Build merged filter (progressive or fresh).
    3. If merged filter is VAGUE → intercept: store pending_entities, set awaiting_refinement.
    4. Otherwise → run SQL immediately.
    """
    entities = extract_entities_spacy(query)

    if progressive and st.session_state.active_filters:
        merged = _merge_filters(st.session_state.active_filters, entities)
    else:
        merged = entities

    if _is_vague(merged):
        # Intercept — ask user for color before running SQL
        st.session_state.awaiting_refinement  = True
        st.session_state.pending_entities     = merged
        st.session_state.current_results      = []
        st.session_state.xai_lines            = []
        st.session_state.last_sql             = ""
        st.session_state.last_sql_params      = []
    else:
        _execute_sql_and_store(merged, query)


# ---------------------------------------------------------------------------
# UI sub-renderers
# ---------------------------------------------------------------------------

def _render_filter_pills() -> None:
    af = st.session_state.active_filters
    if not af:
        return
    pills = '<div style="margin:6px 0 14px;">'
    if af.get("object_class"):
        pills += f'<span class="filter-pill pill-class">📦 {af["object_class"]}</span>'
    if af.get("color"):
        pills += f'<span class="filter-pill pill-color">🎨 {af["color"]}</span>'
    for excl in af.get("excluded_objects", []):
        pills += f'<span class="filter-pill pill-excl">❌ {excl}</span>'
    pills += "</div>"
    st.markdown(pills, unsafe_allow_html=True)


def _render_refinement_prompt() -> None:
    """
    Show the color-picker intercept UI.
    Buttons trigger state mutation + st.rerun() so execution resumes cleanly.
    """
    entities = st.session_state.pending_entities
    obj_cls  = entities.get("object_class", "object")

    st.markdown(f"""
    <div class="refine-box">
        <div class="refine-title">🤔 Your search for <em>"{obj_cls}"</em> is quite broad.</div>
        <div class="refine-sub">Would you like to narrow it down by color? Pick one below or skip to see all.</div>
    </div>
    """, unsafe_allow_html=True)

    # Color buttons in a single row
    color_cols = st.columns(len(COLOR_OPTIONS) + 1, gap="small")
    for idx, color in enumerate(COLOR_OPTIONS):
        with color_cols[idx]:
            emoji = _COLOR_EMOJI.get(color, "🎨")
            if st.button(f"{emoji} {color}", key=f"color_btn_{color}", use_container_width=True):
                # Inject selected color and execute
                refined = dict(entities)
                refined["color"] = color.lower()
                query_label = f"{st.session_state.submitted_query} [{color}]"
                _execute_sql_and_store(refined, query_label)
                st.rerun()

    with color_cols[-1]:
        if st.button("⏭ Skip & Show All", key="color_btn_skip", use_container_width=True):
            _execute_sql_and_store(entities, st.session_state.submitted_query)
            st.rerun()


def _render_xai_block() -> None:
    if not st.session_state.xai_lines:
        return
    st.markdown('<div class="section-label">What the system understood</div>', unsafe_allow_html=True)
    for line in st.session_state.xai_lines:
        if "Excluded" in line:
            st.error(line, icon="🚫")
        elif "Color" in line:
            st.info(line, icon="🎨")
        elif "Object" in line:
            st.info(line, icon="📦")
        elif line.startswith("⏩"):
            st.success(line, icon="⏩")
        elif line.startswith("⏪"):
            st.success(line, icon="⏪")
        elif "⚠" in line:
            st.warning(line)
        else:
            st.success(line, icon="✅")


def _render_sql_trace() -> None:
    if not st.session_state.last_sql:
        return
    with st.expander("🔬 Backend Trace (For Judges)"):
        st.markdown(f"**Query:** `{st.session_state.last_query}`")
        st.code(st.session_state.last_sql, language="sql")
        st.markdown("**Bound Parameters:**")
        st.json(st.session_state.last_sql_params)
        st.caption(f"⏱ Execution latency: **{st.session_state.latency_ms} ms**")


def _render_results() -> None:
    results = st.session_state.current_results

    # Only render results section if not awaiting refinement
    if st.session_state.awaiting_refinement:
        return

    if results:
        label = f'{len(results)} match{"es" if len(results) != 1 else ""} found'
        st.markdown(f'<div class="section-label">{label}</div>', unsafe_allow_html=True)
        for row in results:
            ts_str   = _ms_to_hhmmss(row["timestamp_ms"])
            conf_pct = int(row["confidence"] * 100)
            st.markdown(f"""
            <div class="result-card">
                <div class="result-ts">🎞️ Match at <strong>{ts_str}</strong>
                    &nbsp;·&nbsp; Frame #{row['frame_id']}</div>
                <div class="result-conf">Confidence: {conf_pct}%</div>
                <div class="conf-bar-bg">
                    <div class="conf-bar-fill" style="width:{conf_pct}%;"></div>
                </div>
            </div>
            """, unsafe_allow_html=True)

    elif st.session_state.last_query and not st.session_state.awaiting_refinement:
        st.markdown("""
        <div class="empty-state">
            <div class="empty-icon">🔍</div>
            <div class="result-ts">No matches found</div>
            <div class="empty-msg">Try relaxing your filters or a different query.</div>
        </div>""", unsafe_allow_html=True)

    else:
        st.markdown("""
        <div class="empty-state">
            <div class="empty-icon">🎬</div>
            <div class="result-ts">Enter a query above to begin</div>
            <div class="empty-msg">
                Examples: &nbsp;<code>red car</code>&nbsp;·&nbsp;
                <code>person without helmet</code>&nbsp;·&nbsp;
                <code>car</code> (triggers color picker)
            </div>
        </div>""", unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Layout
# ---------------------------------------------------------------------------

# ── Header ──────────────────────────────────────────────────────────────────
st.markdown("""
<div class="header-card">
    <div class="header-title">🎯 Ask-N-Seek</div>
    <p class="header-sub">Natural Language Video Intelligence — SQLite · spaCy · Zero-Dependency</p>
    <span class="badge">Interactive Refinement Mode</span>
</div>
""", unsafe_allow_html=True)

col_main, col_side = st.columns([3, 1], gap="large")

# ╔══════════════════════════════════════════════╗
# ║  LEFT — Search + Refinement + Results        ║
# ╚══════════════════════════════════════════════╝
with col_main:

    # ── Search bar ──────────────────────────────────────────────────────────
    search_col, btn_col = st.columns([5, 1], gap="small")
    with search_col:
        query_input = st.text_input(
            label="query",
            placeholder='e.g. "red car"  |  "person without helmet"  |  "car"  (vague → triggers refine)',
            label_visibility="collapsed",
            key="query_input_field",
        )
    with btn_col:
        search_clicked = st.button("Search", use_container_width=True)

    # ── Progressive toggle ────────────────────────────────────────────────────
    progressive_on = st.checkbox(
        "🔁 Refine Current Search (merge with previous filters)",
        value=False,
        key="progressive_toggle",
    )

    # ── Active filter pills (when progressive is ON) ───────────────────────
    if st.session_state.active_filters and progressive_on:
        st.markdown('<div class="section-label">Active Filters</div>', unsafe_allow_html=True)
        _render_filter_pills()

    # ── Handle new query submission ─────────────────────────────────────────
    if search_clicked and query_input.strip():
        new_query = query_input.strip()
        # Detect if the user typed a genuinely NEW query (not same as last)
        if new_query != st.session_state.submitted_query:
            # New query always resets refinement intercept
            st.session_state.awaiting_refinement = False
            st.session_state.pending_entities    = {}

        st.session_state.submitted_query      = new_query
        st.session_state.submitted_progressive = progressive_on
        _handle_new_query(new_query, progressive=progressive_on)

    # ── Refinement intercept UI ─────────────────────────────────────────────
    if st.session_state.awaiting_refinement:
        _render_refinement_prompt()
    else:
        # ── XAI explanation ──────────────────────────────────────────────────
        _render_xai_block()

        # ── SQL trace expander ───────────────────────────────────────────────
        _render_sql_trace()

        # ── Results ─────────────────────────────────────────────────────────
        _render_results()


# ╔══════════════════════════════════════════════╗
# ║  RIGHT — Stats + History + Reset             ║
# ╚══════════════════════════════════════════════╝
with col_side:
    st.markdown('<div class="section-label">Session Stats</div>', unsafe_allow_html=True)
    st.metric("Queries Run", len(st.session_state.history))
    st.metric("Total Matches", sum(c for _, c in st.session_state.history))
    if st.session_state.latency_ms:
        st.metric("Last Latency", f"{st.session_state.latency_ms} ms")

    st.markdown('<div class="section-label">Actions</div>', unsafe_allow_html=True)

    if st.button("🗑 Clear All Filters", use_container_width=True):
        for key in [
            "active_filters", "current_results", "last_query",
            "last_sql", "last_sql_params", "xai_lines", "latency_ms",
            "awaiting_refinement", "pending_entities", "submitted_query",
            "last_match_timestamp_ms",
        ]:
            st.session_state[key] = {} if key in ("active_filters", "pending_entities") else \
                                    [] if key in ("current_results", "last_sql_params", "xai_lines") else \
                                    False if key == "awaiting_refinement" else \
                                    0.0 if key == "latency_ms" else \
                                    None if key == "last_match_timestamp_ms" else ""
        st.rerun()

    if st.session_state.history:
        st.markdown('<div class="section-label">Query History</div>', unsafe_allow_html=True)
        for q, cnt in st.session_state.history[:8]:
            badge_color = "#22c55e" if cnt > 0 else "#ef4444"
            st.markdown(
                f'<div style="font-size:0.78rem;padding:5px 0;border-bottom:1px solid #1e293b;">'
                f'<span style="color:#94a3b8;">{q}</span>&nbsp;'
                f'<span style="background:{badge_color};color:white;border-radius:8px;'
                f'padding:1px 7px;font-size:0.68rem;font-weight:600;">{cnt}</span></div>',
                unsafe_allow_html=True,
            )
