"""
ui/gradio_app.py — Gradio Blocks interface for Odysseus Part 3.

Layout
------
Top    : Query textbox + Submit button
Mid-L  : Live processing log (streaming, step-by-step)
Mid-R  : Results gallery (HTML cards, clickable)
Bottom : Video player (HTML5 <video> with JS seek-to-timestamp)

States
------
Match state        : Result cards rendered, log green tick, video player ready.
No confident match : Gray panel with explicit message, log shows FAIL reason.
No video selected  : Bottom player shows placeholder message.

# TODO: SWAP FOR ACHILLES'S REAL IMPLEMENTATION (marked in 3 places below)
"""

from __future__ import annotations

import json
import sys
import os

# Make the project root importable when running from any CWD
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import gradio as gr

import config as _config
from config import load_threshold
from engine.parser_gateway import parse_query
from engine.qdrant_gateway import get_qdrant_client, get_collection_name
from engine.stub_data import count_stub_rows
from engine.paths import get_video_path, get_frame_path  # noqa: F401  (used in JS template injection + card TODO)
from engine.search import search_structured, Result
from engine.explanation import generate_explanation

# ---------------------------------------------------------------------------
# Initialise Qdrant client (module-level singleton)
# ---------------------------------------------------------------------------
# Controlled by USE_STUB_QDRANT in config.py / .env
# TODO: SWAP FOR ACHILLES — set USE_STUB_QDRANT=False in .env and point to real collection
_QDRANT_CLIENT  = get_qdrant_client()
_COLLECTION     = get_collection_name()
_STUB_ROW_COUNT = count_stub_rows()

# ---------------------------------------------------------------------------
# CSS
# ---------------------------------------------------------------------------

CUSTOM_CSS = """
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');

* { box-sizing: border-box; }

body, .gradio-container {
    font-family: 'Inter', system-ui, sans-serif !important;
    background: #07070f !important;
}

/* ── Header ─────────────────────────────────────────────────────────────── */
.app-header {
    text-align: center;
    padding: 32px 24px 16px;
    background: linear-gradient(135deg, #0d0d1a 0%, #12122a 100%);
    border-radius: 16px;
    border: 1px solid #1e1e3f;
    margin-bottom: 20px;
}
.app-title {
    font-size: 2rem;
    font-weight: 700;
    background: linear-gradient(90deg, #818cf8, #c084fc, #f472b6);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
    margin: 0 0 8px;
}
.app-subtitle {
    color: #64748b;
    font-size: 0.95rem;
    margin: 0;
}
.app-badge {
    display: inline-block;
    margin-top: 12px;
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
    padding: 12px 16px 0;
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
    margin: 0 0 10px;
    cursor: pointer;
    transition: all 0.18s ease;
    position: relative;
    overflow: hidden;
    user-select: none;
}
.result-card::before {
    content: '';
    position: absolute;
    inset: 0;
    background: linear-gradient(135deg, rgba(99,102,241,0.04), transparent);
    opacity: 0;
    transition: opacity 0.18s;
}
.result-card:hover::before { opacity: 1; }
.result-card:hover {
    border-color: #6366f1;
    transform: translateY(-2px);
    box-shadow: 0 8px 28px rgba(99, 102, 241, 0.18);
}
.result-card.selected {
    border-color: #818cf8;
    box-shadow: 0 0 0 2px rgba(129, 140, 248, 0.25);
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
    color: #475569;
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
    font-family: monospace;
    font-size: 0.7rem;
    color: #475569;
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
    color: #94a3b8;
    font-style: italic;
    line-height: 1.5;
    margin-top: 6px;
    padding-top: 6px;
    border-top: 1px solid #1e1e3f;
}
.click-hint {
    font-size: 0.68rem;
    color: #2d2d50;
    text-align: right;
    margin-top: 6px;
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
.no-match-text  { font-size: 0.85rem; color: #374151; max-width: 280px; line-height: 1.5; margin: 0; }

/* ── Video player ────────────────────────────────────────────────────────── */
.video-panel {
    background: #08080f;
    border: 1px solid #1a1a2e;
    border-radius: 12px;
    padding: 16px;
    margin-top: 12px;
}
.video-panel-header {
    font-size: 0.8rem;
    font-weight: 600;
    color: #475569;
    text-transform: uppercase;
    letter-spacing: 0.8px;
    margin-bottom: 12px;
}
.video-placeholder {
    height: 180px;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    background: #0c0c1a;
    border: 1px dashed #1e1e3f;
    border-radius: 10px;
    color: #374151;
    font-size: 0.88rem;
}
video {
    width: 100%;
    border-radius: 8px;
    background: #000;
}
.video-info-bar {
    display: flex;
    gap: 10px;
    margin-bottom: 10px;
    flex-wrap: wrap;
}
.vid-badge, .time-badge {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    padding: 4px 12px;
    border-radius: 6px;
    font-size: 0.8rem;
    font-weight: 600;
}
.vid-badge  { background: rgba(99,102,241,0.12); color: #818cf8; border: 1px solid rgba(99,102,241,0.3); }
.time-badge { background: rgba(16,185,129,0.12); color: #10b981; border: 1px solid rgba(16,185,129,0.3); }

/* ── Submit button ───────────────────────────────────────────────────────── */
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
# JavaScript injected on load
# ---------------------------------------------------------------------------
# Inject Python path templates as JS globals so _updateVideoPlayer() uses
# config-driven paths instead of hardcoded strings.
_VIDEO_TPL_JS  = json.dumps(_config.VIDEO_PATH_TEMPLATE)
_FRAME_TPL_JS  = json.dumps(_config.FRAME_PATH_TEMPLATE)

SETUP_JS = (
    f"window._ODYSSEUS_VIDEO_TPL = {_VIDEO_TPL_JS};\n"
    f"window._ODYSSEUS_FRAME_TPL = {_FRAME_TPL_JS};\n\n"
) + """
function setupOdysseus() {
    // ── Card click handler ──────────────────────────────────────────────
    document.addEventListener('click', function(e) {
        const card = e.target.closest('[data-video-id]');
        if (!card) return;

        const videoId  = card.dataset.videoId;
        const ts       = parseFloat(card.dataset.timestamp);

        // Visual: toggle selected state
        document.querySelectorAll('.result-card').forEach(c => c.classList.remove('selected'));
        card.classList.add('selected');

        // Update video player directly (no Python round-trip needed for UX)
        _updateVideoPlayer(videoId, ts);

        // Also notify Python via hidden Gradio input for state tracking
        _notifyGradio('odysseus-card-data', JSON.stringify({video_id: videoId, timestamp: ts}));
    });
}

function _updateVideoPlayer(videoId, timestamp) {
    const container = document.getElementById('video-player-inner');
    if (!container) return;

    // Resolve video URL from Python-injected path template
    // TODO: SWAP FOR ACHILLES'S REAL IMPLEMENTATION
    // Set VIDEO_PATH_TEMPLATE in config.py (or .env) to point to real video files.
    const rawTpl  = window._ODYSSEUS_VIDEO_TPL || '/mnt/agents/output/videos/{video_id}.mp4';
    const videoUrl = rawTpl.replace('{video_id}', videoId);

    container.innerHTML = `
        <div class="video-info-bar">
            <span class="vid-badge">📹 ${videoId}</span>
            <span class="time-badge">⏱ Seeking to ${timestamp.toFixed(1)}s</span>
        </div>
        <video id="main-player" controls>
            <source src="${videoUrl}" type="video/mp4">
            <p style="color:#475569;text-align:center;padding:32px 0;font-size:0.88rem;">
                🎬 Stub mode — real footage will appear here after Part 1 integration.<br>
                <span style="font-size:0.75rem;color:#374151;">Video: <b>${videoId}</b> &nbsp;|&nbsp; Timestamp: <b>${timestamp.toFixed(2)}s</b></span>
            </p>
        </video>
    `;
    const vid = document.getElementById('main-player');
    if (vid) {
        vid.addEventListener('loadedmetadata', () => { vid.currentTime = timestamp; });
        // Fallback for if metadata already loaded (src already cached)
        if (!isNaN(vid.duration)) { vid.currentTime = timestamp; }
    }
}

function _notifyGradio(elemId, value) {
    const el = document.querySelector('#' + elemId + ' textarea');
    if (!el) return;
    const setter = Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, 'value').set;
    setter.call(el, value);
    el.dispatchEvent(new Event('input', { bubbles: true }));
}

// Run setup once DOM is ready
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', setupOdysseus);
} else {
    setupOdysseus();
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
    <div class="no-match-icon" style="animation: pulse 1s infinite alternate;">⚙️</div>
    <p class="no-match-title" style="color:#818cf8;">Processing…</p>
</div>
"""

_NO_VIDEO_HTML = """
<div class="video-placeholder">
    <span style="font-size:32px;margin-bottom:10px;opacity:0.4;">📺</span>
    No video selected — click a result card to load
</div>
"""

_VIDEO_PLAYER_WRAP = """
<div id="video-player-inner">{inner}</div>
"""


# ---------------------------------------------------------------------------
# Result card rendering
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
    """Render a tiny normalised bbox overlay inside the thumbnail."""
    if len(bbox) < 4:
        return ""
    x1, y1, x2, y2 = bbox
    # Scale to 100% × 88px container
    lp = int(x1 * 100)
    tp = int(y1 * 100)
    wp = max(int((x2 - x1) * 100), 5)
    hp = max(int((y2 - y1) * 100), 5)
    return (
        f'<div class="thumb-bbox" '
        f'style="left:{lp}%;top:{tp}%;width:{wp}%;height:{hp}%;"></div>'
    )


def render_result_card(result: Result, explanation: str, idx: int) -> str:
    """Render one result as an HTML card with click attributes."""
    # TODO: SWAP FOR ACHILLES'S REAL IMPLEMENTATION
    # Replace thumb_icon with real frame image using get_frame_path():
    #   from engine.paths import get_frame_path
    #   fi   = result.matched_objects[0].get(_config.FIELD_MAP["qdrant_frame_idx"], 0)
    #   src  = get_frame_path(result.video_id, fi)
    #   thumb_html = f'<img src="{src}" style="width:100%;border-radius:8px;">'
    thumb_icon = "🎬"

    # Payload field names from FIELD_MAP
    _qc  = _config.FIELD_MAP["qdrant_class"]
    _qo  = _config.FIELD_MAP["qdrant_color"]
    _qb  = _config.FIELD_MAP["qdrant_bbox"]

    # Build bbox overlays from matched objects
    bbox_lines = []
    thumb_overlays = ""
    for obj in result.matched_objects:
        cls_name = obj.get(_qc, "?")
        color    = obj.get(_qo, "?")
        bbox     = obj.get(_qb, [])
        if bbox:
            bbox_str = ", ".join(f"{b:.2f}" for b in bbox)
            bbox_lines.append(f"{cls_name}/{color}: [{bbox_str}]")
            thumb_overlays += _bbox_thumb_svg(bbox)

    bbox_html = "".join(
        f'<span class="bbox-tag">{line}</span>' for line in bbox_lines[:3]
    )

    vid_id = result.video_id
    ts     = result.timestamp
    scene  = result.scene_id
    cc     = _conf_class(result.confidence_score)
    cl     = _conf_label(result.confidence_score)

    return f"""
<div class="result-card"
     data-video-id="{vid_id}"
     data-timestamp="{ts}"
     id="result-card-{idx}">

    <div class="result-card-header">
        <span class="vid-label">📹 {vid_id}</span>
        <span class="conf-badge {cc}">{cl}</span>
    </div>

    <div class="result-meta">
        ⏱ {ts:.1f}s &nbsp;·&nbsp; Scene {scene}
        &nbsp;·&nbsp; {len(result.matched_objects)} object(s)
    </div>

    <div class="thumb-placeholder">
        <span class="thumb-icon">{thumb_icon}</span>
        {thumb_overlays}
    </div>

    {bbox_html}

    <p class="explanation-text">💡 {explanation}</p>
    <p class="click-hint">▶ Click to seek video</p>
</div>
"""


def render_results_html(results: list[Result]) -> str:
    if not results:
        return _NO_MATCH_HTML
    cards = "".join(
        render_result_card(r, generate_explanation(r), i)
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
# Log builder
# ---------------------------------------------------------------------------

def _log_html(lines: list[tuple[str, str]]) -> str:
    """
    Build the processing log HTML.

    lines: list of (css_class, text) where css_class ∈ {pass, fail, info, warn, muted}
    """
    items = "".join(
        f'<div class="log-step {cls}">{text}</div>' for cls, text in lines
    )
    return f'<div class="log-container">{items}</div>'


# ---------------------------------------------------------------------------
# Core generator — drives the Gradio streaming update
# ---------------------------------------------------------------------------

def process_query(query: str):
    """
    Gradio generator function. Yields (log_html, results_html, video_html)
    tuples so each processing step appears live in the UI.
    """
    if not query or not query.strip():
        yield (
            _log_html([("muted", "⌛ Waiting for a query…")]),
            _NO_RESULTS_HTML,
            _VIDEO_PLAYER_WRAP.format(inner=_NO_VIDEO_HTML),
        )
        return

    threshold = load_threshold()
    log: list[tuple[str, str]] = []

    # ── Step 1: Parse ───────────────────────────────────────────────────────
    log.append(("info", "⏳ Parsing query…"))
    yield _log_html(log), _LOADING_HTML, _VIDEO_PLAYER_WRAP.format(inner=_NO_VIDEO_HTML)

    # TODO: SWAP FOR ACHILLES — parser routed via parser_gateway (config.PARSER_MODULE)
    filter_dict = parse_query(query)
    filters_display = json.dumps(filter_dict.get("filters", {}), indent=None)
    log.append(("muted", f"🔍 Filter: <code>{filters_display}</code>"))
    yield _log_html(log), _LOADING_HTML, _VIDEO_PLAYER_WRAP.format(inner=_NO_VIDEO_HTML)

    # ── No-match from parser ─────────────────────────────────────────────────
    if filter_dict.get("status") != "match":
        log.append(("warn", "⚠️  Parser returned no_match — query not understood"))
        log.append(("fail", f"🔴 Threshold check: FAIL — best score 0.00 &lt; threshold {threshold:.2f}"))
        yield (
            _log_html(log),
            _NO_MATCH_HTML,
            _VIDEO_PLAYER_WRAP.format(inner=_NO_VIDEO_HTML),
        )
        return

    # ── Step 2: Search ───────────────────────────────────────────────────────
    log.append(("info", "🔎 Searching Qdrant…"))
    yield _log_html(log), _LOADING_HTML, _VIDEO_PLAYER_WRAP.format(inner=_NO_VIDEO_HTML)

    results = search_structured(filter_dict, _QDRANT_CLIENT, _COLLECTION)

    log.append(("muted", f"📦 Found {len(results)} raw result(s) from {_STUB_ROW_COUNT}-row stub"))
    yield _log_html(log), _LOADING_HTML, _VIDEO_PLAYER_WRAP.format(inner=_NO_VIDEO_HTML)

    # ── Step 3: Rerank ───────────────────────────────────────────────────────
    log.append(("info", "📊 Reranking by confidence…"))
    yield _log_html(log), _LOADING_HTML, _VIDEO_PLAYER_WRAP.format(inner=_NO_VIDEO_HTML)

    # (results already sorted by search_structured)

    # ── Step 4: Group ────────────────────────────────────────────────────────
    log.append(("muted", "📂 Grouping by source video…"))
    yield _log_html(log), _LOADING_HTML, _VIDEO_PLAYER_WRAP.format(inner=_NO_VIDEO_HTML)

    # ── Step 5: Threshold ────────────────────────────────────────────────────
    best_score = results[0].confidence_score if results else 0.0

    if not results or best_score < threshold:
        log.append((
            "fail",
            f"🔴 Threshold check: FAIL — best score {best_score:.2f} &lt; threshold {threshold:.2f}",
        ))
        yield (
            _log_html(log),
            _NO_MATCH_HTML,
            _VIDEO_PLAYER_WRAP.format(inner=_NO_VIDEO_HTML),
        )
        return

    log.append((
        "pass",
        f"✅ Threshold check: PASS — best score {best_score:.2f} ≥ threshold {threshold:.2f}",
    ))
    yield _log_html(log), _LOADING_HTML, _VIDEO_PLAYER_WRAP.format(inner=_NO_VIDEO_HTML)

    # ── Step 6: Render ───────────────────────────────────────────────────────
    log.append(("pass", f"🎯 Returning {len(results)} result(s) — click a card to seek video"))
    results_html = render_results_html(results)
    yield (
        _log_html(log),
        results_html,
        _VIDEO_PLAYER_WRAP.format(inner=_NO_VIDEO_HTML),
    )


# ---------------------------------------------------------------------------
# Build the Gradio app
# ---------------------------------------------------------------------------

def build_app() -> gr.Blocks:
    with gr.Blocks(
        title="Odysseus — Video Query Engine",
    ) as demo:

        # ── Header ──────────────────────────────────────────────────────────
        gr.HTML("""
        <div class="app-header">
            <h1 class="app-title">🎯 Odysseus</h1>
            <p class="app-subtitle">Natural Language Video Query Engine</p>
            <span class="app-badge">Milestone 1 · Stub-Wired</span>
        </div>
        """)

        # ── Query row ────────────────────────────────────────────────────────
        with gr.Row(elem_classes=["query-row"]):
            query_box = gr.Textbox(
                placeholder=(
                    "Try: 'person in red'  ·  'person without helmet'  ·  "
                    "'two people'  ·  'person left of car'"
                ),
                label="",
                scale=5,
                lines=1,
                max_lines=1,
                elem_id="query-input",
            )
            submit_btn = gr.Button("🔍 Search", variant="primary", scale=1, min_width=120)

        # ── Middle row ───────────────────────────────────────────────────────
        with gr.Row():
            # Processing log
            with gr.Column(scale=1):
                gr.HTML('<div class="panel-label">Processing Log</div>')
                log_output = gr.HTML(
                    _log_html([("muted", "⌛ Waiting for query…")]),
                    elem_id="log-panel",
                )

            # Results
            with gr.Column(scale=2):
                gr.HTML('<div class="panel-label">Results</div>')
                results_output = gr.HTML(_NO_RESULTS_HTML, elem_id="results-panel")

        # ── Video player ─────────────────────────────────────────────────────
        gr.HTML('<div class="panel-label" style="margin-top:16px;">Video Player</div>')
        video_output = gr.HTML(
            _VIDEO_PLAYER_WRAP.format(inner=_NO_VIDEO_HTML),
            elem_id="video-panel",
        )

        # Hidden textbox for JS→Python card-click notification
        selected_card_data = gr.Textbox(
            visible=False,
            elem_id="odysseus-card-data",
            label="",
        )

        # ── Quick-test buttons ────────────────────────────────────────────────
        with gr.Accordion("📋 Verification Queries (Milestone 1 Checklist)", open=False):
            gr.Markdown(
                "Click any button to pre-fill the query box with a verification test case."
            )
            with gr.Row():
                for q in [
                    "person in red",
                    "person without helmet",
                    "two people",
                    "person left of car",
                    "purple elephant",
                ]:
                    btn = gr.Button(q, size="sm")
                    btn.click(lambda v=q: v, outputs=query_box)

        # ── Footer ───────────────────────────────────────────────────────────
        gr.HTML("""
        <div style="text-align:center;padding:20px 0 8px;color:#1e1e3f;font-size:0.75rem;">
            Odysseus Part 3 · Milestone 1 · Stub-Wired ·
            No FAISS · No Embeddings · No LLM
        </div>
        """)

        # ── Wire events ──────────────────────────────────────────────────────
        search_inputs  = [query_box]
        search_outputs = [log_output, results_output, video_output]

        submit_btn.click(
            fn=process_query,
            inputs=search_inputs,
            outputs=search_outputs,
        )
        query_box.submit(
            fn=process_query,
            inputs=search_inputs,
            outputs=search_outputs,
        )

    return demo
