"""
ui/gradio_app.py — Ask-N-Seek Gradio 6 UI/UX.

Ask-N-Seek: Natural Language Video Retrieval Engine.
"""

from __future__ import annotations

import datetime
import difflib
import json
import logging
import os
import queue
import string
import sys
import threading
from datetime import datetime

# Make the project root importable when running from any CWD
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import gradio as gr

import config as _config
from config import load_threshold
from engine.parser_gateway import parse_query
from engine.qdrant_gateway import get_qdrant_client, get_collection_name
from engine.search import search_structured, Result
from engine.explanation import generate_explanation
from engine.diagnosis import run_diagnosis
from engine.live_ingestor import LiveIngestor
try:
    from engine.scenario_presets import SCENARIO_PRESETS
except ImportError:
    SCENARIO_PRESETS = [
        "person in red",
        "person without helmet",
        "two people",
        "person left of car",
        "purple elephant",
    ]
from engine.result_scoring import ScoreBreakdown
from backend.vision.vocabulary import VOCABULARY, VOCABULARY_SET, SYNONYM_MAP
from backend.query.patterns import COLOR_VOCAB, COLOR_ALIASES
from engine.query_cache import QueryCache
from engine.paths import get_video_path, get_frame_path
try:
    from engine.stub_data import count_stub_rows as count_stub_row
except ImportError:
    try:
        from engine.stub_data import count_stub_row
    except ImportError:
        def count_stub_row() -> int:
            return 72

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Initialise singletons
# ---------------------------------------------------------------------------
_QDRANT_CLIENT = get_qdrant_client()
_COLLECTION = get_collection_name()
_QUERY_CACHE: QueryCache = QueryCache()

# ---------------------------------------------------------------------------
# Visual Design System (CSS)
# ---------------------------------------------------------------------------
CUSTOM_CSS = """
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;500;600&display=swap');

* { box-sizing: border-box; }

body, .gradio-container {
    font-family: 'Inter', system-ui, sans-serif !important;
    background: #07070f !important;
    color: #e2e8f0 !important;
}

/* ── Header ─────────────────────────────────────────────────────────────── */
.app-header {
    text-align: center;
    padding: 32px 24px 20px;
    background: linear-gradient(135deg, #0d0d1a 0%, #12122a 100%);
    border-radius: 16px;
    border: 1px solid #1e1e3f;
    margin-bottom: 20px;
    box-shadow: 0 10px 30px rgba(0, 0, 0, 0.4);
}
.app-title {
    font-size: 2.2rem;
    font-weight: 700;
    background: linear-gradient(90deg, #818cf8, #c084fc, #f472b6);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
    margin: 0 0 8px;
    letter-spacing: -0.5px;
}
.app-subtitle {
    color: #94a3b8;
    font-size: 1rem;
    margin: 0;
    font-weight: 400;
}
.app-badge {
    display: inline-block;
    margin-top: 14px;
    padding: 4px 14px;
    background: rgba(99, 102, 241, 0.15);
    border: 1px solid rgba(99, 102, 241, 0.4);
    border-radius: 20px;
    color: #818cf8;
    font-size: 0.75rem;
    font-weight: 600;
    letter-spacing: 0.5px;
    text-transform: uppercase;
}

/* ── Preset buttons ──────────────────────────────────────────────────────── */
.preset-row {
    gap: 8px !important;
    margin-bottom: 12px !important;
}
.preset-row button {
    background: rgba(30, 30, 63, 0.6) !important;
    border: 1px solid #1e1e3f !important;
    color: #818cf8 !important;
    font-size: 0.8rem !important;
    font-weight: 500 !important;
    border-radius: 8px !important;
    padding: 6px 12px !important;
    transition: all 0.15s ease !important;
}
.preset-row button:hover {
    background: rgba(99, 102, 241, 0.2) !important;
    border-color: #6366f1 !important;
    color: #c7d2fe !important;
    transform: translateY(-1px) !important;
}

/* ── Query row ───────────────────────────────────────────────────────────── */
.query-row { gap: 12px !important; }
.query-row input, .query-row textarea {
    background: #0f0f1f !important;
    border: 1px solid #1e1e3f !important;
    border-radius: 10px !important;
    color: #e2e8f0 !important;
    font-size: 1rem !important;
}
.query-row input:focus, .query-row textarea:focus {
    border-color: #6366f1 !important;
    box-shadow: 0 0 0 3px rgba(99, 102, 241, 0.15) !important;
}

/* ── Section panels ──────────────────────────────────────────────────────── */
.panel-box {
    background: #0c0c1e !important;
    border: 1px solid #1a1a35 !important;
    border-radius: 12px !important;
    padding: 0 !important;
}
.panel-label {
    font-size: 0.8rem;
    font-weight: 600;
    color: #475569;
    text-transform: uppercase;
    letter-spacing: 0.8px;
    padding: 12px 16px 4px;
}

/* ── Processing log ─────────────────────────────────────────────────────── */
.log-container {
    background: #080812;
    border: 1px solid #1a1a2e;
    border-radius: 10px;
    padding: 14px 16px;
    height: 420px;
    overflow-y: auto;
    font-family: 'JetBrains Mono', 'Fira Code', monospace;
    font-size: 0.82rem;
    line-height: 1.8;
    color: #94a3b8;
    scroll-behavior: smooth;
}
.log-container::-webkit-scrollbar { width: 4px; }
.log-container::-webkit-scrollbar-thumb { background: #2d2d50; border-radius: 2px; }
.log-step { padding: 1px 0; }
.log-step.pass { color: #10b981; }
.log-step.fail { color: #ef4444; }
.log-step.info { color: #818cf8; }
.log-step.warn { color: #f59e0b; }
.log-step.muted { color: #475569; }

/* ── Result cards ────────────────────────────────────────────────────────── */
.results-scroll {
    height: 420px;
    overflow-y: auto;
    padding: 4px 4px 4px 0;
}
.results-scroll::-webkit-scrollbar { width: 4px; }
.results-scroll::-webkit-scrollbar-thumb { background: #1e1e3f; border-radius: 2px; }

.result-card {
    background: linear-gradient(135deg, #0d0d20 0%, #11112a 100%);
    border: 1px solid #1e1e3f;
    border-radius: 12px;
    padding: 14px;
    margin: 0 0 12px;
    transition: all 0.18s ease;
    position: relative;
    overflow: hidden;
}
.result-card-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 8px;
}
.vid-label {
    font-weight: 600;
    font-size: 0.88rem;
    color: #c7d2fe;
}
.conf-badge {
    display: inline-flex;
    align-items: center;
    gap: 4px;
    padding: 3px 10px;
    border-radius: 20px;
    font-size: 0.72rem;
    font-weight: 700;
    letter-spacing: 0.4px;
    text-transform: uppercase;
}
.conf-high { background: rgba(16,185,129,0.12); color: #10b981; border: 1px solid rgba(16,185,129,0.4); }
.conf-med  { background: rgba(245,158,11,0.12);  color: #f59e0b; border: 1px solid rgba(245,158,11,0.4); }
.conf-low  { background: rgba(239,68,68,0.12);   color: #ef4444; border: 1px solid rgba(239,68,68,0.4); }

.result-meta {
    font-size: 0.75rem;
    color: #64748b;
    margin-bottom: 8px;
}
.thumb-placeholder {
    width: 100%;
    height: 88px;
    background: linear-gradient(135deg, #0f0f20, #161630);
    border-radius: 8px;
    display: flex;
    align-items: center;
    justify-content: center;
    border: 1px dashed #1e1e3f;
    margin-bottom: 10px;
    position: relative;
    overflow: hidden;
}
.thumb-placeholder .thumb-icon {
    font-size: 28px;
    opacity: 0.6;
}
.thumb-placeholder .thumb-bbox {
    position: absolute;
    border: 2px solid rgba(99,102,241,0.7);
    border-radius: 3px;
    background: rgba(99,102,241,0.08);
}
.bbox-tag {
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.7rem;
    color: #94a3b8;
    background: rgba(0,0,0,0.4);
    padding: 3px 8px;
    border-radius: 4px;
    margin: 2px 0;
    display: block;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
}
.explanation-text {
    font-size: 0.78rem;
    color: #cbd5e1;
    font-style: italic;
    line-height: 1.5;
    margin-top: 6px;
    padding-top: 6px;
    border-top: 1px solid #1e1e3f;
}

/* ── No match ────────────────────────────────────────────────────────────── */
.no-match-panel {
    height: 420px;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    background: linear-gradient(135deg, #0a0a14 0%, #0d0d1a 100%);
    border: 1px dashed #1e1e3f;
    border-radius: 12px;
    text-align: center;
    padding: 32px;
    color: #475569;
}
.no-match-icon { font-size: 48px; margin-bottom: 16px; opacity: 0.6; }
.no-match-title { font-size: 1rem; font-weight: 600; color: #64748b; margin: 0 0 8px; }
.no-match-text  { font-size: 0.85rem; color: #475569; max-width: 280px; line-height: 1.5; margin: 0; }

/* ── Video player ────────────────────────────────────────────────────────── */
.video-panel {
    background: #08080f;
    border: 1px solid #1a1a2e;
    border-radius: 12px;
    padding: 16px;
    margin-top: 12px;
}
button.primary {
    background: linear-gradient(135deg, #6366f1, #818cf8) !important;
    border: none !important;
    border-radius: 10px !important;
    font-weight: 600 !important;
    font-size: 0.95rem !important;
    transition: all 0.18s !important;
    box-shadow: 0 4px 15px rgba(99,102,241,0.3) !important;
}
button.primary:hover {
    transform: translateY(-1px) !important;
    box-shadow: 0 6px 20px rgba(99,102,241,0.45) !important;
}
"""

# ---------------------------------------------------------------------------
# JavaScript for auto-focusing query input on ingestion complete
# ---------------------------------------------------------------------------
SETUP_JS = """
function setupAskNSeek() {
    // ── History item click: re-run query ─────────────────────────────
    document.addEventListener('click', function(e) {
        var historyItem = e.target.closest('[data-history-query]');
        if (historyItem) {
            var qText = historyItem.getAttribute('data-history-query');
            var inputEl = document.querySelector('#query-input textarea') || document.querySelector('#query-input input');
            if (inputEl) {
                var setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value') &&
                             Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set;
                if (!setter) setter = Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, 'value') &&
                                       Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, 'value').set;
                if (setter) setter.call(inputEl, qText); else inputEl.value = qText;
                inputEl.dispatchEvent(new Event('input', { bubbles: true }));
                setTimeout(function() {
                    var submitBtn = document.querySelector('.query-row button') || document.querySelector('#submit-btn');
                    if (submitBtn) submitBtn.click();
                }, 50);
            }
        }
    });
}

// Auto-focus query box when ingestion completes (__FOCUS_QUERY__ marker).
setInterval(function() {
    var logEl = document.querySelector('#ingest-log textarea') ||
                document.querySelector('#ingest-log input');
    if (logEl && logEl.value && logEl.value.includes('__FOCUS_QUERY__')) {
        var inputEl = document.querySelector('#query-input textarea') ||
                      document.querySelector('#query-input input');
        if (inputEl) {
            inputEl.focus();
            logEl.value = logEl.value.replace('__FOCUS_QUERY__', '');
        }
    }
}, 500);

if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', setupAskNSeek);
} else {
    setupAskNSeek();
}
"""

# ---------------------------------------------------------------------------
# HTML fragments
# ---------------------------------------------------------------------------
_NO_RESULTS_HTML = """
<div class="no-match-panel">
    <div class="no-match-icon">🔭</div>
    <p class="no-match-title">No results yet</p>
    <p class="no-match-text">Enter a query above and press Search to begin.</p>
</div>
"""

_NO_MATCH_HTML = """
<div class="no-match-panel">
    <div class="no-match-icon">🔍</div>
    <p class="no-match-title">No confident match found</p>
    <p class="no-match-text">
        No confident match found for this query.<br>
        Try broadening your description.
    </p>
</div>
"""

_LOADING_HTML = """
<div class="no-match-panel">
    <div class="no-match-icon">⚙️</div>
    <p class="no-match-title" style="color:#818cf8;">Processing…</p>
</div>
"""

# ---------------------------------------------------------------------------
# Result card rendering & score breakdown helper
# ---------------------------------------------------------------------------
def _conf_class(score: float) -> str:
    if score >= 0.75:
        return "conf-high"
    if score >= 0.50:
        return "conf-med"
    return "conf-low"


def _conf_label(score: float) -> str:
    if score >= 0.75:
        return f"HIGH {score:.2f}"
    if score >= 0.50:
        return f"MED {score:.2f}"
    return f"LOW {score:.2f}"


def _bbox_thumb_svg(bbox: list[float]) -> str:
    if len(bbox) < 4:
        return ""
    x1, y1, x2, y2 = bbox
    lp = int(x1 * 100)
    tp = int(y1 * 100)
    wp = max(int((x2 - x1) * 100), 5)
    hp = max(int((y2 - y1) * 100), 5)
    return f'<div class="thumb-bbox" style="left:{lp}%;top:{tp}%;width:{wp}%;height:{hp}%;"></div>'


def _render_score_bars(sb: ScoreBreakdown | None) -> str:
    if sb is None:
        return ""

    cats = [
        ("Object", getattr(sb, "object_score", 0), 40),
        ("Color", getattr(sb, "color_score", 0), 20),
        ("Spatial", getattr(sb, "spatial_score", 0), 20),
        ("Negation", getattr(sb, "negation_score", 0), 20),
    ]

    lines = []
    for cat_name, s_val, max_val in cats:
        filled = int((s_val / max_val) * 40) if max_val > 0 else 0
        filled = max(0, min(40, filled))
        empty = 40 - filled
        bar = "█" * filled + "░" * empty
        lines.append(f"{cat_name:<10} {bar} {s_val}/{max_val}")

    bars_str = "\n".join(lines)
    total = getattr(sb, "total", 0)

    return f"""
    <div class="smart-score-panel" style="
        font-family: 'JetBrains Mono', 'Fira Code', monospace;
        font-size: 0.72rem;
        background: rgba(15, 23, 42, 0.7);
        border: 1px solid #1e1e3f;
        border-radius: 8px;
        padding: 8px 10px;
        margin-top: 8px;
        color: #94a3b8;
    ">
        <div style="font-weight: 600; color: #818cf8; margin-bottom: 4px; font-size: 0.7rem; text-transform: uppercase; letter-spacing: 0.5px;">Score Breakdown</div>
        <pre style="margin: 0; padding: 0; font-family: inherit; font-size: inherit; color: #cbd5e1; line-height: 1.4;">{bars_str}</pre>
        <div style="font-weight: 700; color: #c084fc; margin-top: 4px; text-align: right; font-size: 0.75rem;">
            Score: {total}/100
        </div>
    </div>
    """


def render_result_card(result: Result, explanation: str, idx: int, video_path: str = "") -> str:
    thumb_icon = "🎬"

    _qc = _config.FIELD_MAP.get("qdrant_class", "class_name")
    _qo = _config.FIELD_MAP.get("qdrant_color", "color")
    _qb = _config.FIELD_MAP.get("qdrant_bbox", "bbox")

    bbox_lines = []
    thumb_overlays = ""
    for obj in result.matched_objects:
        cls_name = obj.get(_qc, "?")
        color = obj.get(_qo, "?")
        bbox = obj.get(_qb, [])
        if bbox:
            bbox_str = ", ".join(f"{b:.2f}" for b in bbox)
            bbox_lines.append(f"{cls_name}/{color}: [{bbox_str}]")
            thumb_overlays += _bbox_thumb_svg(bbox)

    bbox_html = "".join(f'<span class="bbox-tag">{line}</span>' for line in bbox_lines[:3])

    vid_id = result.video_id
    ts = result.timestamp
    scene = result.scene_id
    cc = _conf_class(result.confidence_score)
    cl = _conf_label(result.confidence_score)

    score_bars_html = _render_score_bars(getattr(result, "score_breakdown", None))

    return f"""
<div class="result-card" id="result-card-{idx}">
    <div class="result-card-header">
        <span class="vid-label">📹 {vid_id}</span>
        <span class="conf-badge {cc}">{cl}</span>
    </div>

    <div class="result-meta">
        ⏱ {ts:.1f}s &nbsp;·&nbsp; Scene {scene} &nbsp;·&nbsp; {len(result.matched_objects)} object(s)
    </div>

    <div class="thumb-placeholder">
        <span class="thumb-icon">{thumb_icon}</span>
        {thumb_overlays}
    </div>

    {bbox_html}

    <p class="explanation-text">💡 {explanation}</p>
    {score_bars_html}
    <p class="click-hint" style="color:#64748b;font-size:0.68rem;text-align:right;margin-top:6px;">🔽 Select from dropdown below to play this clip</p>
</div>
"""


def render_results_html(results: list[Result], video_path: str = "") -> str:
    if not results:
        return _NO_MATCH_HTML
    cards = "".join(
        render_result_card(r, generate_explanation(r), i, video_path)
        for i, r in enumerate(results)
    )
    count_label = f"{len(results)} result{'s' if len(results) != 1 else ''}"
    return f"""
<div>
    <div style="font-size:0.75rem;color:#475569;margin-bottom:8px;letter-spacing:0.5px;text-transform:uppercase;">
        {count_label} — sorted by confidence
    </div>
    <div class="results-scroll">{cards}</div>
</div>
"""


# ---------------------------------------------------------------------------
# Processing Log Builder
# ---------------------------------------------------------------------------
def _log_html(lines: list[tuple[str, str]]) -> str:
    items = "".join(f'<div class="log-step {cls}">{text}</div>' for cls, text in lines)
    return f'<div class="log-container">{items}</div>'


# ---------------------------------------------------------------------------
# Vocabulary Coverage & History Helpers
# ---------------------------------------------------------------------------
QUERY_SYNTAX_WORDS: set[str] = {
    "in", "on", "at", "with", "without", "no", "not", "of", "to", "the", "a", "an",
    "and", "or", "left", "right", "is", "are", "has", "have", "wearing", "less",
    "top", "bottom", "near", "beside", "one", "two", "three", "four", "five", "six",
    "seven", "eight", "nine", "ten", "couple", "few", "several", "more", "fewer",
    "than", "least", "exactly", "person", "people", "man", "woman", "child", "car",
}

_COLOR_WORDS: set[str] = set()
for _mc in list(COLOR_VOCAB) + list(COLOR_ALIASES.keys()):
    for _w in _mc.split():
        _COLOR_WORDS.add(_w)

KNOWN_TOKENS: set[str] = (
    VOCABULARY_SET
    | set(SYNONYM_MAP.keys())
    | set(SYNONYM_MAP.values())
    | COLOR_VOCAB
    | set(COLOR_ALIASES.keys())
    | _COLOR_WORDS
    | QUERY_SYNTAX_WORDS
)


def check_vocabulary_banner(query: str) -> str:
    punct_trans = str.maketrans(string.punctuation, " " * len(string.punctuation))
    clean_q = query.translate(punct_trans).lower()
    tokens = clean_q.split()
    oov_messages = []

    for token in tokens:
        if token in KNOWN_TOKENS or token.isdigit():
            continue
        matches = difflib.get_close_matches(token, VOCABULARY, n=1, cutoff=0.6)
        if matches:
            oov_messages.append(f"⚠️ '{token}' not in vocabulary. Did you mean: '{matches[0]}'?")
        else:
            oov_messages.append(f"⚠️ '{token}' not recognized — try a different term.")

    if not oov_messages:
        return ""

    banner_items = "<br>".join(oov_messages)
    return f"""
    <div style="
        background:#451a03;
        border:1px solid #f59e0b;
        color:#fef3c7;
        padding:10px 14px;
        border-radius:8px;
        margin-bottom:12px;
        font-size:0.88rem;
    ">
        {banner_items}
    </div>
    """


def render_history_html(history: list[dict] | None) -> str:
    if not history:
        return """
        <div style="color:#64748b;font-size:0.85rem;padding:8px 0;font-style:italic;">
            No queries submitted yet in this session.
        </div>
        """
    items = []
    for item in history:
        q_text = item.get("query_text", "")
        ts = item.get("timestamp", "")
        cnt = item.get("result_count", 0)
        score = item.get("top_score", 0.0)
        q_attr = q_text.replace('"', '&quot;')

        items.append(f"""
        <div class="history-item" data-history-query="{q_attr}" style="
            background:#0f172a;
            border:1px solid #1e293b;
            border-radius:6px;
            padding:8px 12px;
            margin-bottom:6px;
            font-size:0.85rem;
            color:#cbd5e1;
            display:flex;
            justify-content:space-between;
            align-items:center;
            cursor:pointer;
        ">
            <div>
                <b style="color:#f8fafc;">Q: {q_text}</b>
                <span style="color:#64748b;margin:0 6px;">|</span>
                <span>{cnt} result{'s' if cnt != 1 else ''}</span>
                <span style="color:#64748b;margin:0 6px;">|</span>
                <span>score {score:.2f}</span>
            </div>
            <div>
                <span style="color:#64748b;font-size:0.75rem;margin-right:10px;">{ts}</span>
                <span class="rerun-btn" style="
                    background:#3b82f6;
                    color:#ffffff;
                    padding:2px 8px;
                    border-radius:4px;
                    font-size:0.75rem;
                    font-weight:500;
                ">&#x25B6; Re-run</span>
            </div>
        </div>
        """)
    return f"""
    <div style="max-height:220px;overflow-y:auto;padding-right:4px;">
        {''.join(items)}
    </div>
    """


# ---------------------------------------------------------------------------
# Generator Function: process_query
# ---------------------------------------------------------------------------
def process_query(
    query: str,
    collection_name: str | None = None,
    history: list[dict] | None = None,
    video_path: str = "",
):
    target_coll = collection_name or _COLLECTION
    history_list = list(history or [])

    if not query or not query.strip():
        yield (
            _log_html([("muted", "⌛ Waiting for a query…")]),
            _NO_RESULTS_HTML,
            None,
            "",
            render_history_html(history_list),
            history_list,
            gr.update(choices=[], visible=False),
        )
        return

    banner_html = check_vocabulary_banner(query)
    threshold = load_threshold()
    log: list[tuple[str, str]] = []

    # ── Cache hit check ──────────────────────────────────────────────────────
    cached = _QUERY_CACHE.get(query, target_coll)
    if cached is not None:
        log_html, res_html, vid_upd, b_html, hist_h, hist_l, pick_upd = cached
        cached_log_html = _log_html([
            ("pass", "✅ Result served from cache"),
            ("info", f"⚡ Returning cached results for: '{query}'"),
        ])
        yield (
            cached_log_html,
            res_html,
            vid_upd,
            b_html,
            render_history_html(history_list),
            history_list,
            pick_upd,
        )
        return

    # ── Step 1: Parse ───────────────────────────────────────────────────────
    log.append(("info", "⏳ Parsing query…"))
    yield (
        _log_html(log),
        _LOADING_HTML,
        None,
        banner_html,
        render_history_html(history_list),
        history_list,
        gr.update(),
    )

    filter_dict = parse_query(query)
    filters_display = json.dumps(filter_dict.get("filters", {}), indent=None)
    log.append(("muted", f"🔍 Filter: <code>{filters_display}</code>"))
    yield (
        _log_html(log),
        _LOADING_HTML,
        None,
        banner_html,
        render_history_html(history_list),
        history_list,
        gr.update(),
    )

    # ── No-match from parser ─────────────────────────────────────────────────
    if filter_dict.get("status") != "match":
        log.append(("warn", "⚠️  Parser returned no_match — query not understood"))
        log.append(("fail", f"🔴 Threshold check: FAIL — best score 0.00 &lt; threshold {threshold:.2f}"))

        entry = {
            "query_text": query,
            "timestamp": datetime.now().strftime("%H:%M:%S"),
            "parsed_filter": filter_dict.get("filters", {}),
            "result_count": 0,
            "top_score": 0.0,
        }
        history_list = [entry] + history_list

        yield (
            _log_html(log),
            _NO_MATCH_HTML,
            None,
            banner_html,
            render_history_html(history_list),
            history_list,
            gr.update(choices=[], visible=False),
        )
        return

    # ── Step 2: Search ───────────────────────────────────────────────────────
    log.append(("info", f"🔎 Searching Qdrant ({target_coll})…"))
    yield (
        _log_html(log),
        _LOADING_HTML,
        None,
        banner_html,
        render_history_html(history_list),
        history_list,
        gr.update(),
    )

    results = search_structured(filter_dict, _QDRANT_CLIENT, target_coll)

    log.append(("muted", f"📦 Found {len(results)} raw result(s)"))
    yield (
        _log_html(log),
        _LOADING_HTML,
        None,
        banner_html,
        render_history_html(history_list),
        history_list,
        gr.update(),
    )

    # ── Step 3: Rerank ───────────────────────────────────────────────────────
    log.append(("info", "📊 Reranking by confidence…"))
    yield (
        _log_html(log),
        _LOADING_HTML,
        None,
        banner_html,
        render_history_html(history_list),
        history_list,
        gr.update(),
    )

    # ── Step 4: Group ────────────────────────────────────────────────────────
    log.append(("muted", "📂 Grouping by source video…"))
    yield (
        _log_html(log),
        _LOADING_HTML,
        None,
        banner_html,
        render_history_html(history_list),
        history_list,
        gr.update(),
    )

    # ── Step 5: Threshold ────────────────────────────────────────────────────
    best_score = results[0].confidence_score if results else 0.0

    if not results or best_score < threshold:
        log.append((
            "fail",
            f"🔴 Threshold check: FAIL — best score {best_score:.2f} &lt; threshold {threshold:.2f}",
        ))
        yield (
            _log_html(log),
            _LOADING_HTML,
            None,
            banner_html,
            render_history_html(history_list),
            history_list,
            gr.update(),
        )

        log.append(("muted", "🔬 Running no-match diagnosis…"))
        yield (
            _log_html(log),
            _LOADING_HTML,
            None,
            banner_html,
            render_history_html(history_list),
            history_list,
            gr.update(),
        )
        try:
            diag = run_diagnosis(
                filter_dict.get("filters", {}),
                _QDRANT_CLIENT,
                target_coll,
            )
            diag_html = diag.get("html", _NO_MATCH_HTML) if isinstance(diag, dict) else _NO_MATCH_HTML
        except Exception as exc:
            logger.warning("diagnosis failed: %s", exc)
            diag_html = _NO_MATCH_HTML

        entry = {
            "query_text": query,
            "timestamp": datetime.now().strftime("%H:%M:%S"),
            "parsed_filter": filter_dict.get("filters", {}),
            "result_count": len(results),
            "top_score": round(best_score, 2),
        }
        history_list = [entry] + history_list

        yield (
            _log_html(log),
            diag_html,
            None,
            banner_html,
            render_history_html(history_list),
            history_list,
            gr.update(choices=[], visible=False),
        )
        return

    log.append((
        "pass",
        f"✅ Threshold check: PASS — best score {best_score:.2f} ≥ threshold {threshold:.2f}",
    ))
    yield (
        _log_html(log),
        _LOADING_HTML,
        None,
        banner_html,
        render_history_html(history_list),
        history_list,
        gr.update(),
    )

    # ── Step 6: Render ───────────────────────────────────────────────────────
    log.append(("pass", f"🎯 Returning {len(results)} result(s) — select from dropdown to play clip"))
    results_html = render_results_html(results, video_path)

    entry = {
        "query_text": query,
        "timestamp": datetime.now().strftime("%H:%M:%S"),
        "parsed_filter": filter_dict.get("filters", {}),
        "result_count": len(results),
        "top_score": round(best_score, 2),
    }
    history_list = [entry] + history_list

    _picker_choices = [
        (
            f"{i+1}. {r.video_id} @ {r.timestamp:.1f}s  [{_conf_label(r.confidence_score)}]",
            f"{video_path}:::{r.timestamp}"
        )
        for i, r in enumerate(results)
    ] if results else []

    final_tuple = (
        _log_html(log),
        results_html,
        None,
        banner_html,
        render_history_html(history_list),
        history_list,
        gr.update(choices=_picker_choices, value=None, visible=bool(_picker_choices)),
    )
    _QUERY_CACHE.set(query, target_coll, final_tuple)
    yield final_tuple


# ---------------------------------------------------------------------------
# Detection summary helper
# ---------------------------------------------------------------------------
def _generate_ingest_summary(collection_name: str, client) -> str:
    if not collection_name:
        return ""
    try:
        points, _ = client.scroll(
            collection_name=collection_name,
            limit=10000,
            with_payload=True,
            with_vectors=False,
        )
    except Exception:
        return ""

    if not points:
        return ""

    tally: dict[str, dict[str, int]] = {}
    for pt in points:
        p = pt.payload or {}
        cls = p.get("class_name", "unknown")
        color = p.get("color") or "unknown"
        tally.setdefault(cls, {}).setdefault(color, 0)
        tally[cls][color] += 1

    EMOJI = {
        "person": "🚶", "car": "🚗", "truck": "🚚", "bus": "🚌",
        "bicycle": "🚲", "motorcycle": "🏍", "dog": "🐕", "cat": "🐈",
        "chair": "🪑", "bottle": "🍶", "laptop": "💻", "cell phone": "📱",
        "backpack": "🎒", "umbrella": "☂", "traffic light": "🚦",
        "stop sign": "🛑", "bench": "🪑",
    }

    _TOP_N = 20
    rows_html = ""
    sorted_classes = sorted(tally, key=lambda c: -sum(tally[c].values()))
    for cls in sorted_classes[:_TOP_N]:
        emoji = EMOJI.get(cls, "📦")
        total = sum(tally[cls].values())
        color_parts = ", ".join(
            f"{col}({cnt})"
            for col, cnt in sorted(tally[cls].items(), key=lambda x: -x[1])
            if col != "unknown"
        )
        color_str = f" \u2014 {color_parts}" if color_parts else ""
        rows_html += (
            f'<div class="detected-item" style="'
            f'padding:4px 8px;border-radius:6px;margin:3px 0;'
            f'background:#1e293b;font-size:0.87rem;color:#e2e8f0;">'
            f'{emoji} <b>{cls}</b> <span style="color:#94a3b8;">'
            f'\u00d7{total}{color_str}</span></div>\n'
        )

    total_classes = len(sorted_classes)
    footer = (
        f'<div style="font-size:0.72rem;color:#475569;margin-top:4px;">'
        f'Showing top {min(_TOP_N, total_classes)} of {total_classes} class types</div>'
    )

    return (
        '<div class="detected-summary" style="'
        'max-height:220px;overflow-y:auto;padding:8px;'
        'border-radius:8px;border:1px solid #334155;background:#0f172a;">'
        '<div style="font-size:0.78rem;color:#64748b;margin-bottom:6px;">'
        'Objects detected in this video:</div>\n'
        + rows_html
        + footer
        + '</div>'
    )


# ---------------------------------------------------------------------------
# Main Gradio App Builder
# ---------------------------------------------------------------------------
def build_app() -> gr.Blocks:
    with gr.Blocks(
        title="Ask-N-Seek — Natural Language Video Retrieval",
    ) as demo:

        # ── 1. HEADER ────────────────────────────────────────────────────────
        gr.HTML("""
        <div class="app-header">
            <h1 class="app-title">Ask-N-Seek</h1>
            <p class="app-subtitle">Type what happened. We'll show you exactly where — and prove it.</p>
            <span class="app-badge">Backend Ready</span>
        </div>
        """)

        # ── Session state ───────────────────────────────────────────────────
        judge_collection = gr.State(value=None)
        query_history = gr.State(value=[])
        video_path_state = gr.State(value="")

        # ── 2. INGESTION PANEL ───────────────────────────────────────────────
        with gr.Accordion("📥 Live Judge-Video Ingestion", open=True):
            gr.HTML('<div class="panel-label">Drop a video to index it for querying</div>')
            with gr.Row():
                upload_video = gr.File(
                    label="Drop a video file (.mp4 / .avi / .mov)",
                    file_types=[".mp4", ".avi", ".mov", ".mkv"],
                    elem_id="upload-video",
                    scale=2,
                )
                with gr.Column(scale=3):
                    ingest_progress = gr.Slider(
                        minimum=0, maximum=100, value=0,
                        label="Ingestion Progress",
                        interactive=False,
                        elem_id="ingest-progress",
                    )
                    ingest_log = gr.Textbox(
                        label="Ingestion Log",
                        lines=6,
                        interactive=False,
                        elem_id="ingest-log",
                    )
                    ingest_stats = gr.JSON(
                        label="Stats",
                        elem_id="ingest-stats",
                    )
                    ingest_summary = gr.HTML(
                        value="",
                        label="Detected Objects",
                        elem_id="ingest-summary",
                    )

        gr.HTML('<hr style="border-color:#1e293b;margin:16px 0;">')

        # ── 3. QUERY SECTION ─────────────────────────────────────────────────
        with gr.Column(visible=True, elem_id="query-section"):
            gr.HTML('<div class="panel-label">Scenario Presets</div>')
            preset_btns = []
            with gr.Row(elem_classes=["preset-row"]):
                for preset in SCENARIO_PRESETS:
                    p_btn = gr.Button(preset, size="sm", variant="secondary")
                    preset_btns.append((p_btn, preset))

            gr.HTML('<div class="panel-label" style="margin-top:8px;">Search Query</div>')
            with gr.Row(elem_classes=["query-row"]):
                query_box = gr.Textbox(
                    placeholder="Try: 'person in red' · 'person without helmet' · 'two people' · 'person left of car'",
                    label="",
                    scale=5,
                    lines=1,
                    max_lines=1,
                    elem_id="query-input",
                )
                submit_btn = gr.Button("🔍 Search", variant="primary", scale=1, min_width=120)

        # ── Hidden / State elements ──────────────────────────────────────────
        current_video_path = gr.Textbox(
            visible=False,
            elem_id="current-video-path",
            label="",
            value="",
        )

        # ── 4. MAIN WORKSPACE (2 columns) ────────────────────────────────────
        with gr.Row():
            # LEFT: Processing Log
            with gr.Column(scale=1):
                gr.HTML('<div class="panel-label">Processing Log</div>')
                log_output = gr.HTML(
                    _log_html([("muted", "⌛ Waiting for a query…")]),
                    elem_id="log-panel",
                )

            # RIGHT: Results Panel + Seek Dropdown
            with gr.Column(scale=2):
                gr.HTML('<div class="panel-label">Results</div>')
                vocab_banner = gr.HTML("", elem_id="vocab-banner")
                results_output = gr.HTML(_NO_RESULTS_HTML, elem_id="results-panel")
                result_picker = gr.Dropdown(
                    label="▶ Jump to result (click to seek video)",
                    choices=[],
                    value=None,
                    interactive=True,
                    visible=False,
                    elem_id="result-picker",
                )

        # ── 5. VIDEO PLAYER ──────────────────────────────────────────────────
        gr.HTML('<div class="panel-label" style="margin-top:16px;">Video Player</div>')
        video_output = gr.Video(
            label="Selected Clip",
            value=None,
            autoplay=False,
            interactive=False,
            elem_id="video-panel",
        )

        # ── 6. QUERY HISTORY ─────────────────────────────────────────────────
        with gr.Accordion("📜 Session Query History", open=True):
            history_panel = gr.HTML(render_history_html([]), elem_id="history-panel")

        # Footer
        gr.HTML("""
        <div style="text-align:center;padding:24px 0 8px;color:#334155;font-size:0.75rem;">
            Ask-N-Seek · Natural Language Video Retrieval Engine
        </div>
        """)

        # ── WIRING & EVENT HANDLERS ──────────────────────────────────────────
        search_inputs = [query_box, judge_collection, query_history, video_path_state]
        search_outputs = [log_output, results_output, video_output, vocab_banner, history_panel, query_history, result_picker]

        def _threaded_process_query(
            query: str,
            collection_name: str | None = None,
            history: list[dict] | None = None,
            video_path: str | None = None,
        ):
            q: queue.Queue = queue.Queue()

            def _worker():
                try:
                    for update in process_query(query, collection_name, history, video_path or ""):
                        q.put(update)
                except Exception as exc:
                    logger.error("process_query thread error: %s", exc)
                finally:
                    q.put(None)

            t = threading.Thread(target=_worker, daemon=True)
            t.start()

            while True:
                item = q.get()
                if item is None:
                    break
                yield item

        # Search submit triggers
        submit_btn.click(
            fn=_threaded_process_query,
            inputs=search_inputs,
            outputs=search_outputs,
        )
        query_box.submit(
            fn=_threaded_process_query,
            inputs=search_inputs,
            outputs=search_outputs,
        )

        # Preset buttons: pre-fill query_box AND auto-submit
        for p_btn, preset in preset_btns:
            p_btn.click(
                fn=lambda p=preset: p,
                outputs=[query_box],
            ).then(
                fn=_threaded_process_query,
                inputs=search_inputs,
                outputs=search_outputs,
            )

        # Video Seek Dropdown event handler
        def _on_result_picked(encoded_value: str):
            if not encoded_value or ":::" not in encoded_value:
                return gr.update(value=None)
            parts = encoded_value.split(":::", 1)
            vpath = parts[0].strip()
            try:
                ts = float(parts[1].strip())
            except (ValueError, IndexError):
                ts = 0.0
            if not vpath or vpath == "None":
                return gr.update(value=None)
            return gr.update(value=vpath, playback_position=ts)

        result_picker.change(
            fn=_on_result_picked,
            inputs=[result_picker],
            outputs=[video_output],
        )

        # Ingestion Handler
        def _start_ingestion(file_obj, current_collection):
            if file_obj is None:
                yield "", 0, None, current_collection, "", "", ""
                return

            video_path = file_obj.name if hasattr(file_obj, "name") else str(file_obj)
            ingestor = LiveIngestor(_QDRANT_CLIENT)
            iq: queue.Queue = queue.Queue()
            log_lines: list[str] = []

            def _worker():
                try:
                    for upd in ingestor.ingest(video_path):
                        iq.put(upd)
                except Exception as exc:
                    logger.error("ingestion thread error: %s", exc)
                finally:
                    iq.put(None)

            threading.Thread(target=_worker, daemon=True).start()

            new_collection = current_collection
            summary_html = ""
            while True:
                upd = iq.get()
                if upd is None:
                    break
                phase = upd.get("phase", "")
                pct = upd.get("progress_pct", 0)
                msg = upd.get("message", "")
                stats = upd.get("stats", {})
                log_lines.append(f"[{phase}] {msg}")
                if phase == "complete":
                    new_collection = stats.get("collection", new_collection)
                    _QUERY_CACHE.clear()
                    log_lines.append("__FOCUS_QUERY__")
                    summary_html = _generate_ingest_summary(new_collection, _QDRANT_CLIENT)
                yield "\n".join(log_lines[-20:]), pct, stats, new_collection, video_path, summary_html, video_path

        upload_video.change(
            fn=_start_ingestion,
            inputs=[upload_video, judge_collection],
            outputs=[ingest_log, ingest_progress, ingest_stats, judge_collection, current_video_path, ingest_summary, video_path_state],
        )

    return demo


if __name__ == "__main__":
    demo = build_app()
    demo.launch(
        server_name="127.0.0.1",
        server_port=7860,
        show_error=True,
        head=f"<style>{CUSTOM_CSS}</style><script>{SETUP_JS}</script>",
    )
