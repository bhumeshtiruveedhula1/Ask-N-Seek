"""
Ask-N-Seek Bridge Server v2.4 — Real Backend
=============================================
Runs at: fresh_clone/frontend/bridge_server.py
Launch:  uvicorn bridge_server:app --port 8000
         (or: python bridge_server.py)

LOCKED — does NOT modify any file in fresh_clone/engine/ or fresh_clone/backend/.
"""

from __future__ import annotations

import difflib
import json
import logging
import mimetypes
import os
import string
import sys
import tempfile
import threading
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any, Optional

# MIME type map for video formats
_VIDEO_MIME: dict[str, str] = {
    ".mp4":  "video/mp4",
    ".mov":  "video/quicktime",
    ".avi":  "video/x-msvideo",
    ".mkv":  "video/x-matroska",
    ".webm": "video/webm",
    ".m4v":  "video/mp4",
    ".wmv":  "video/x-ms-wmv",
    ".flv":  "video/x-flv",
}

from fastapi import FastAPI, File, Form, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

# ═══════════════════════════════════════════════════════════════════
# BACKEND PATH RESOLUTION
# bridge_server.py lives at fresh_clone/frontend/bridge_server.py
# Backend root is fresh_clone/ (one level up from frontend/)
# ═══════════════════════════════════════════════════════════════════
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
BACKEND_PATH = os.path.abspath(os.path.join(_THIS_DIR, ".."))  # → fresh_clone/

if BACKEND_PATH not in sys.path:
    sys.path.insert(0, BACKEND_PATH)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════════
# BACKEND IMPORTS
# ═══════════════════════════════════════════════════════════════════
_backend_available = False
_MOCK_MODE = False

try:
    import config as _config
    from config import load_threshold
    from engine.parser_gateway import parse_query
    from engine.search import search_structured
    from engine.explanation import generate_explanation
    from engine.diagnosis import run_diagnosis
    from engine.live_ingestor import LiveIngestor
    from engine.query_cache import QueryCache
    from engine.scenario_presets import get_scenarios
    from engine.result_scoring import ScoreBreakdown
    from engine.storage import get_class_counts, get_videos, get_latest_video_id
    from backend.vision.vocabulary import VOCABULARY, VOCABULARY_SET, SYNONYM_MAP
    from backend.query.patterns import COLOR_VOCAB, COLOR_ALIASES
    from backend.query.query_parser import _preprocess_query as _parser_preprocess

    _query_cache = QueryCache()
    _backend_available = True

    # Active video_id: prefer the most recently ingested video from SQLite.
    # Falls back to None if no video has been ingested yet.
    _active_video_id: str | None = get_latest_video_id()

    logger.info("✅ Backend connected — path: %s", BACKEND_PATH)
    logger.info("✅ Active video: %s", _active_video_id or "(none — upload a video)")

except Exception as _e:
    logger.warning("⚠️  Backend import failed: %s", _e)
    logger.warning("    Running in MOCK MODE")
    _MOCK_MODE = True
    _active_video_id = None
    _query_cache = None  # type: ignore

# ═══════════════════════════════════════════════════════════════════
# VOCABULARY HELPERS (real if backend available, mock fallback)
# ═══════════════════════════════════════════════════════════════════
_QUERY_SYNTAX_WORDS: set[str] = {
    # Articles, prepositions, conjunctions
    "in", "on", "at", "with", "without", "no", "not", "of", "to", "the", "a", "an",
    "and", "or", "is", "are", "has", "have", "wearing", "less",
    # Numbers
    "one", "two", "three", "four", "five", "six",
    "seven", "eight", "nine", "ten", "couple", "few", "several",
    "more", "fewer", "than", "least", "exactly",
    # Proximity / spatial relation words (map to 'near' in parser)
    "next", "near", "beside", "by", "close", "adjacent", "alongside",
    "holding", "touching", "around",
    # Directional / positional words
    "left", "right", "top", "bottom", "above", "below", "behind", "front",
    "between", "across", "from", "through", "over", "under",
    # Person class words
    "person", "people", "man", "woman", "child",
    # Vehicle class words
    "car", "vehicle", "truck", "bus", "van", "motorcycle", "bicycle",
    "sedan", "suv", "minivan", "jeep",
    # Common query verbs / intent words
    "show", "find", "get", "where", "what", "who", "which", "give",
    "me", "all", "any", "most", "some", "seen", "detected", "appeared",
}

if _backend_available:
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
        | _QUERY_SYNTAX_WORDS
    )
    _VOCAB_LIST = list(VOCABULARY)
else:
    KNOWN_TOKENS = _QUERY_SYNTAX_WORDS | {
        "person", "people", "man", "woman", "child", "car", "vehicle", "truck",
        "bus", "bicycle", "motorcycle", "helmet", "bag", "backpack", "book",
        "laptop", "phone", "chair", "table", "door", "window", "red", "blue",
        "green", "yellow", "white", "black", "dark", "light",
        "more", "than", "two", "three", "one", "exactly", "fewer", "at", "least",
    }
    _VOCAB_LIST = list(KNOWN_TOKENS)


def _check_vocab(query: str) -> list[dict]:
    """
    Return list of {token, type, suggestion} for OOV tokens.
    PROMPT 5 Task 4 (v2): Tighter suggestion quality:
    - Length-adjusted cutoff: short tokens (<4) use 0.8, longer use 0.72
    - Candidate must NOT be shorter than original by more than 2 chars
    - SequenceMatcher ratio >= 0.70 required (rejects kurta->curtain, giving->railing)
    - If no high-quality match: type="unknown", suggestion=None (no false suggestions)
    PROMPT 3 FIX: Apply _preprocess_query first so compound words like
    'redshirt' are split to 'red shirt' before vocab check, matching the
    parser's own preprocessing behaviour.
    """
    # Align with parser preprocessing (compound split + negation normalisation)
    if _backend_available:
        try:
            query = _parser_preprocess(query)
        except Exception:
            pass  # non-fatal: fall through to raw check
    punct_trans = str.maketrans(string.punctuation, " " * len(string.punctuation))
    clean_q = query.translate(punct_trans).lower()
    tokens = clean_q.split()
    warnings = []
    for token in tokens:
        if token in KNOWN_TOKENS or token.isdigit():
            continue
        tok_len = len(token)
        # Length-adjusted initial cutoff for get_close_matches
        cutoff = 0.8 if tok_len < 4 else 0.72
        # Get top 3 candidates
        candidates = difflib.get_close_matches(token, _VOCAB_LIST, n=3, cutoff=cutoff)
        best = None
        for cand in candidates:
            # Rule 1: never suggest a word shorter than original by more than 2 chars
            if len(cand) < tok_len - 2:
                continue
            # Rule 2: SequenceMatcher ratio >= 0.70
            # This uses longest-common-subsequence quality, rejecting false cross-word matches
            ratio = difflib.SequenceMatcher(None, token, cand).ratio()
            if ratio < 0.70:
                continue
            best = cand
            break
        if best:
            warnings.append({"token": token, "type": "suggestion", "suggestion": best})
        else:
            # No high-quality suggestion — report unknown cleanly
            warnings.append({"token": token, "type": "unknown", "suggestion": None})
    return warnings


# ═══════════════════════════════════════════════════════════════════
# INGESTION JOB STATE (thread-safe dict)
# ═══════════════════════════════════════════════════════════════════
_ingest_jobs: dict[str, dict] = {}
_jobs_lock = threading.Lock()


def _collect_top_classes(video_id: str, top_n: int = 10) -> list[dict]:
    """Return top N class counts for a video from SQLite."""
    try:
        counts = get_class_counts(video_id)
        sorted_cls = sorted(counts.items(), key=lambda kv: -kv[1])
        return [{"class": cls, "count": cnt} for cls, cnt in sorted_cls[:top_n]]
    except Exception as exc:
        logger.warning("_collect_top_classes failed (non-fatal): %s", exc)
        return []


def _run_ingestion_job(job_id: str, video_path: str) -> None:
    """Background thread: runs LiveIngestor, updates _ingest_jobs."""
    if not _backend_available:
        with _jobs_lock:
            _ingest_jobs[job_id].update({
                "status": "error",
                "progress": 0,
                "phase": "error",
                "message": "Backend not available — running in mock mode",
                "stats": {},
                "collection_name": None,
            })
        return

    try:
        ingestor = LiveIngestor()
        with _jobs_lock:
            _ingest_jobs[job_id]["phase"] = "starting"
            _ingest_jobs[job_id]["status"] = "running"

        for upd in ingestor.ingest(video_path):
            phase = upd.get("phase", "")
            pct = upd.get("progress_pct", 0)
            msg = upd.get("message", "")
            stats = upd.get("stats", {})

            with _jobs_lock:
                # TASK 2: update elapsed_seconds on every tick
                start = _ingest_jobs[job_id].get("_start_time", time.monotonic())
                _ingest_jobs[job_id].update({
                    "phase":           phase,
                    "progress":        pct,
                    "message":         msg,
                    "stats":           stats,
                    "status":          "running",
                    "elapsed_seconds": round(time.monotonic() - start, 1),
                })

                if phase == "complete":
                    video_id = stats.get("video_id") or ingestor.video_id
                    _ingest_jobs[job_id]["collection_name"] = video_id
                    _ingest_jobs[job_id]["status"] = "complete"
                    if _query_cache is not None:
                        _query_cache.clear()
                    # Update active video_id in memory
                    global _active_video_id
                    _active_video_id = video_id
                    logger.info("Ingestion complete — video_id: %s", video_id)

                elif phase == "error":
                    _ingest_jobs[job_id]["status"] = "error"

        # TASK 2: collect top_classes after pipeline finishes
        with _jobs_lock:
            final_collection = _ingest_jobs[job_id].get("collection_name")
            start = _ingest_jobs[job_id].get("_start_time", time.monotonic())
            _ingest_jobs[job_id]["elapsed_seconds"] = round(time.monotonic() - start, 1)

        if final_collection:
            top = _collect_top_classes(final_collection)
            with _jobs_lock:
                _ingest_jobs[job_id]["top_classes"] = top
                logger.info("Top classes collected: %s", top[:3])

    except Exception as exc:
        logger.exception("Ingestion job %s failed: %s", job_id, exc)
        with _jobs_lock:
            _ingest_jobs[job_id]["status"] = "error"
            _ingest_jobs[job_id]["message"] = f"Error: {exc}"

    # NOTE: TASK 3 — we do NOT delete the temp file here.
    # /video/{filename} needs it to serve the video for playback.
    # The file stays in tempdir until the OS or a future cleanup pass removes it.


# ═══════════════════════════════════════════════════════════════════
# SCORE BREAKDOWN SERIALIZER
# ═══════════════════════════════════════════════════════════════════
def _serialize_score_breakdown(sb) -> Optional[dict]:
    if sb is None:
        return None
    return {
        "total": getattr(sb, "total", 0),
        "object_score": getattr(sb, "object_score", 0),
        "color_score": getattr(sb, "color_score", 0),
        "spatial_score": getattr(sb, "spatial_score", 0),
        "negation_score": getattr(sb, "negation_score", 0),
        "details": getattr(sb, "details", {}),
    }


# ═══════════════════════════════════════════════════════════════════
# FASTAPI APP
# ═══════════════════════════════════════════════════════════════════
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("=" * 60)
    logger.info("  Garuda Gamana Bridge Server v3.0")
    logger.info("  Mode: %s", "MOCK" if _MOCK_MODE else "CONNECTED")
    logger.info("  Backend path: %s", BACKEND_PATH)
    logger.info("=" * 60)
    yield
    logger.info("🛑 Server shutting down...")


app = FastAPI(
    title="Garuda Gamana Bridge v3.0",
    description="REST API connecting the HTML frontend to the real backend pipeline",
    version="3.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve static frontend files
_frontend_dir = os.path.dirname(os.path.abspath(__file__))
app.mount("/static", StaticFiles(directory=_frontend_dir), name="static")


class QueryRequest(BaseModel):
    query: str
    collection_name: Optional[str] = None


# ═══════════════════════════════════════════════════════════════════
# HEALTH
# ═══════════════════════════════════════════════════════════════════
@app.get("/health")
def health():
    return {
        "status": "ok",
        "backend_mode": "mock" if _MOCK_MODE else "connected",
        "backend_path": BACKEND_PATH,
        "version": "2.4.0",
        "active_video": _active_video_id,
    }


# ═══════════════════════════════════════════════════════════════════
# SCENARIOS
# ═══════════════════════════════════════════════════════════════════
@app.get("/scenarios")
def scenarios_endpoint():
    """Return the 5 formal scenario presets."""
    if _backend_available:
        return get_scenarios()
    # Fallback presets matching engine/scenario_presets.py exactly
    return [
        {"id": "safety_violation", "label": "🔴 Safety Violation", "query": "person without helmet"},
        {"id": "traffic_incident", "label": "🚗 Traffic Incident",  "query": "car left of person"},
        {"id": "lost_item",        "label": "🎒 Lost Item",         "query": "backpack without owner"},
        {"id": "access_control",   "label": "🚪 Access Control",    "query": "person without badge"},
        {"id": "crowd_check",      "label": "👥 Crowd Check",       "query": "more than two people"},
    ]


# ═══════════════════════════════════════════════════════════════════
# VOCAB CHECK
# ═══════════════════════════════════════════════════════════════════
@app.post("/vocab/check")
async def vocab_check(query: str = Form(...)):
    """Check query tokens against known vocabulary. Returns list of warnings."""
    return _check_vocab(query)


# ═══════════════════════════════════════════════════════════════════
# QUERY
# ═══════════════════════════════════════════════════════════════════
@app.post("/query")
async def query_endpoint(req: QueryRequest):
    """Parse query, search Qdrant, score results, run diagnosis if needed."""
    query = req.query.strip()
    if not query:
        return {"status": "error", "message": "Empty query"}

    # video_id: prefer explicit collection_name from request (set by frontend after ingestion),
    # then fall back to the most-recently-ingested video in SQLite.
    target_vid = req.collection_name or _active_video_id
    vocab_warnings = _check_vocab(query)

    # ── Mock mode fallback ──────────────────────────────────────────
    if _MOCK_MODE:
        is_nonsense = any(w in query.lower() for w in ["purple elephant", "flying dinosaur"])
        if is_nonsense:
            return {
                "status": "no_match",
                "parsed": {"status": "no_match", "filters": {}},
                "results": [],
                "diagnosis": {
                    "html": "<p style='color:#94a3b8'>No confident match — the vocabulary contains no <em>purple elephant</em>.</p>",
                    "best_score": 0.0,
                },
                "threshold": 0.3197,
                "best_score": 0.0,
                "vocab_warnings": vocab_warnings,
            }
        return {
            "status": "mock",
            "parsed": {"status": "match", "filters": {"class": "person"}},
            "results": [],
            "diagnosis": None,
            "threshold": 0.3197,
            "best_score": 0.0,
            "vocab_warnings": vocab_warnings,
            "message": "Running in MOCK MODE — start bridge with real backend for results",
        }

    # ── Real backend path ───────────────────────────────────────────

    # Check QueryCache first
    cached = _query_cache.get(query, target_vid or "")
    if cached is not None:
        logger.info("Cache HIT for query='%s' video='%s'", query, target_vid)
        cached_response = dict(cached)
        cached_response["cached"] = True
        return cached_response

    # Parse
    try:
        parsed = parse_query(query)
    except Exception as exc:
        logger.error("parse_query failed: %s", exc)
        return {"status": "error", "message": str(exc), "vocab_warnings": vocab_warnings}

    if parsed.get("status") != "match":
        return {
            "status": "no_match",
            "parsed": parsed,
            "results": [],
            "diagnosis": None,
            "threshold": load_threshold(),
            "best_score": 0.0,
            "vocab_warnings": vocab_warnings,
        }

    # Inject video_id into filters so search_structured scopes to this video
    filters_with_vid = dict(parsed.get("filters", {}))
    if target_vid:
        filters_with_vid["video_id"] = target_vid
    parsed_with_vid = dict(parsed)
    parsed_with_vid["filters"] = filters_with_vid

    # Search
    try:
        results = search_structured(parsed_with_vid)
    except Exception as exc:
        logger.error("search_structured failed: %s", exc)
        return {"status": "error", "message": str(exc), "vocab_warnings": vocab_warnings}

    threshold = load_threshold()
    best_score = results[0].confidence_score if results else 0.0

    # Serialize results
    enriched = []
    for r in results:
        sb = _serialize_score_breakdown(getattr(r, "score_breakdown", None))
        enriched.append({
            "video_id":         r.video_id,
            "timestamp":        r.timestamp,
            "scene_id":         r.scene_id,
            "confidence_score": r.confidence_score,
            "matched_objects":  r.matched_objects,
            "explanation":      generate_explanation(r),
            "score_breakdown":  sb,
        })

    # Diagnosis if no results or score below threshold
    diagnosis = None
    if not results or best_score < threshold:
        try:
            diag = run_diagnosis(parsed.get("filters", {}))
            diagnosis = {
                "html": diag.get("html", "") if isinstance(diag, dict) else str(diag),
                "best_score": best_score,
            }
        except Exception as exc:
            logger.warning("run_diagnosis failed: %s", exc)
            diagnosis = {"html": f"<p>Diagnosis unavailable: {exc}</p>", "best_score": best_score}

    status = "match" if (results and best_score >= threshold) else "no_match"

    response = {
        "status":         status,
        "parsed":         parsed,
        "results":        enriched,
        "diagnosis":      diagnosis,
        "threshold":      threshold,
        "best_score":     best_score,
        "vocab_warnings": vocab_warnings,
        "collection":     target_vid,
        "cached":         False,
    }

    # Cache ONLY successful matches
    if status == "match" and enriched:
        _query_cache.set(query, target_vid or "", response)

    return response


# ═══════════════════════════════════════════════════════════════════
# INGESTION — START
# ═══════════════════════════════════════════════════════════════════
@app.post("/ingest/start")
async def ingest_start(video: UploadFile = File(...)):
    """
    Accept multipart video upload, save to temp file, start real LiveIngestor
    in background thread. Returns job_id for polling.
    """
    job_id = str(uuid.uuid4())[:12]

    # Save uploaded file to temp location
    suffix = os.path.splitext(video.filename or ".mp4")[1] or ".mp4"
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    try:
        content = await video.read()
        tmp.write(content)
        tmp.flush()
        tmp.close()
    except Exception as exc:
        tmp.close()
        os.unlink(tmp.name)
        return JSONResponse(status_code=500, content={"error": f"Upload failed: {exc}"})

    temp_path = tmp.name
    logger.info("Video saved to temp: %s (%.1f MB)", temp_path, len(content) / 1_048_576)

    # Initialize job state — TASK 2 & 3
    with _jobs_lock:
        _ingest_jobs[job_id] = {
            "job_id":               job_id,
            "status":               "queued",
            "phase":                "queued",
            "progress":             0,
            "message":              "Queued for ingestion…",
            "stats":                {},
            "collection_name":      None,
            "filename":             video.filename,
            "top_classes":          [],       # filled after completion
            "elapsed_seconds":      0,
            # internal keys (prefixed _) are stripped from status response
            "_temp_path":           temp_path,
            "_original_video_path": temp_path,   # TASK 3: kept for /video serving
            "_start_time":          time.monotonic(),
        }

    # Clear query cache immediately — new video means old results are stale
    if _query_cache is not None:
        _query_cache.clear()
        logger.info("Query cache cleared on new ingestion start (job_id=%s)", job_id)

    # Launch background thread
    t = threading.Thread(
        target=_run_ingestion_job,
        args=(job_id, temp_path),
        daemon=True,
        name=f"ingest-{job_id}",
    )
    t.start()


    return {
        "job_id":    job_id,
        "status":    "queued",
        "filename":  video.filename,
        "message":   "Ingestion started",
    }


# ═══════════════════════════════════════════════════════════════════
# INGESTION — STATUS
# ═══════════════════════════════════════════════════════════════════
@app.get("/ingest/status/{job_id}")
def ingest_status(job_id: str):
    """Poll ingestion progress. Returns job state including top_classes and elapsed_seconds."""
    with _jobs_lock:
        job = _ingest_jobs.get(job_id)
        if job is None:
            return JSONResponse(status_code=404, content={"error": f"Job {job_id} not found"})

        # Don't expose internal keys (prefixed _) — dict copy inside the lock
        safe = {k: v for k, v in job.items() if not k.startswith("_")}
        # Grab _start_time while still holding the lock
        start = job.get("_start_time")

    # TASK 2: compute live elapsed_seconds even while polling
    if start is not None:
        safe["elapsed_seconds"] = round(time.monotonic() - start, 1)

    return safe


# ═══════════════════════════════════════════════════════════════════
# VIDEO SERVING — TASK 1: fixed search order + MIME detection
# ═══════════════════════════════════════════════════════════════════
@app.get("/video/{filename:path}")
async def serve_video(filename: str):
    """
    Serve a video file for playback.
    Search order (TASK 1):
      1. Original uploaded temp path stored in the active job (_original_video_path)
      2. ./temp_frames/ inside BACKEND_PATH
      3. Parent BACKEND_PATH directory itself
      4. BACKEND_PATH/outputs/
      5. System temp directory
      6. VIDEO_SEARCH_PATHS env var (colon/semicolon separated)
    MIME type detected from extension.
    """
    from fastapi.responses import FileResponse

    # NOTE: video_id may contain spaces and dots (e.g. "WhatsApp Video 2026-08-05 at 5.16.45 PM (1)").
    # os.path.splitext() would incorrectly split on the first dot, giving wrong stems.
    # Since video_ids NEVER have extensions, use the full filename as the match key.
    #
    # Matching strategy (case-insensitive):
    #   exact_key  = full filename lowercased (e.g. "whatsapp video 2026-08-05 at 5.16.45 pm (1)")
    #   file_stem  = os.path.splitext(file)[0].lower()  (strip ONLY the actual .mp4/.mov extension)
    exact_key = filename.lower().strip()

    # ── 1. Check all active jobs for the original uploaded path ────────────
    with _jobs_lock:
        jobs_snapshot = list(_ingest_jobs.values())

    for job in jobs_snapshot:
        orig = job.get("_original_video_path")
        if orig and os.path.isfile(orig):
            orig_name = os.path.basename(orig)
            orig_stem = os.path.splitext(orig_name)[0].lower()   # strip actual ext
            if orig_name.lower() == exact_key or orig_stem == exact_key:
                logger.info("Serving video from job path: %s", orig)
                ext  = os.path.splitext(orig)[1].lower()
                mime = _VIDEO_MIME.get(ext, "video/mp4")
                return FileResponse(orig, media_type=mime, headers={
                    "Accept-Ranges": "bytes",
                    "Cache-Control": "no-cache, no-store, must-revalidate",
                    "Pragma": "no-cache",
                    "Expires": "0",
                })

    # ── 2. Search known directories ────────────────────────────────────────
    env_paths: list[str] = []
    raw_env = os.environ.get("VIDEO_SEARCH_PATHS", "")
    if raw_env:
        import re as _re
        env_paths = [p.strip() for p in _re.split(r"[;:]", raw_env) if p.strip()]

    search_dirs = [
        os.path.join(BACKEND_PATH, "videos"),       # persistent library (highest priority)
        os.path.join(BACKEND_PATH, "temp_frames"),
        BACKEND_PATH,
        os.path.join(BACKEND_PATH, "outputs"),
        tempfile.gettempdir(),
        *env_paths,
    ]

    mime_default = mimetypes.guess_type(filename + ".mp4")[0] or "video/mp4"

    for d in search_dirs:
        if not os.path.isdir(d):
            continue
        try:
            for entry in os.scandir(d):
                if not entry.is_file():
                    continue
                # Strip the REAL extension (.mp4 / .mov etc.) from the stored file
                file_stem = os.path.splitext(entry.name)[0].lower()
                file_name = entry.name.lower()
                # Match if the requested video_id equals the file stem OR the full filename
                if file_stem == exact_key or file_name == exact_key:
                    logger.info("Serving video (match): %s", entry.path)
                    c_ext  = os.path.splitext(entry.name)[1].lower()
                    c_mime = _VIDEO_MIME.get(c_ext, mime_default)
                    return FileResponse(entry.path, media_type=c_mime, headers={
                        "Accept-Ranges": "bytes",
                        "Cache-Control": "no-cache, no-store, must-revalidate",
                        "Pragma": "no-cache",
                        "Expires": "0",
                    })
        except PermissionError:
            continue

    logger.warning("Video not found: '%s' | searched: %s", filename, search_dirs)
    return JSONResponse(
        status_code=404,
        content={"error": "Video file not found", "requested": filename},
    )


@app.get("/collections")
def list_collections():
    """List all ingested videos (previously 'collections' in Qdrant era)."""
    if not _backend_available:
        return {"collections": [], "videos": [], "mode": "mock"}
    try:
        videos = get_videos()
        return {
            "videos":       videos,
            "active_video": _active_video_id,
            # Legacy key for any frontend code that reads "collections"
            "collections":  videos,
        }
    except Exception as exc:
        return {"error": str(exc)}



# ═══════════════════════════════════════════════════════════════════
# CHAT  --  Stateful Chat Engine
# Exposes BOTH /chat (app.js compat) and /api/chat (clean REST path)
# ═══════════════════════════════════════════════════════════════════

class ChatRequest(BaseModel):
    """
    Payload sent by the frontend chat UI.
    Both the vexed app.js and any REST client use this shape.
    """
    text:         str                # raw user message (may be structured like "color: Red")
    video_id:     Optional[str] = None   # collection_name / active video
    display_text: Optional[str] = None  # user-visible label (e.g. "Red") used in XAI heading


def _handle_chat(req: ChatRequest) -> dict:
    """
    Shared handler for /chat and /api/chat.
    Routes to chat_engine.process_chat() when the backend is available,
    falls back to a polite mock reply in MOCK_MODE.
    """
    msg      = (req.text or "").strip()
    video_id = req.video_id or _active_video_id or ""

    # Determine whether a video has been ingested (needed for Phase B gate)
    is_video_uploaded = bool(video_id)

    # ── MOCK fallback ─────────────────────────────────────────────────────
    if _MOCK_MODE or not _backend_available:
        return {
            "reply":                  (
                "I'm currently running in mock mode (no backend connected). "
                "Start the server with the real backend to enable AI search."
            ),
            "results":                [],
            "language_detected":      "en",
            "session_id":             video_id,
            "filters_used":           {},
            "awaiting_clarification": False,
        }

    # ── Real backend path ─────────────────────────────────────────────────
    try:
        from engine.chat_engine import process_chat
        return process_chat(
            session_id        = video_id,
            message           = msg,
            is_video_uploaded = is_video_uploaded,
            display_text      = req.display_text,
        )
    except Exception as exc:
        logger.exception("chat endpoint error: %s", exc)
        return {
            "reply":                  f"Chat engine error: {exc}. Please try again.",
            "results":                [],
            "language_detected":      "en",
            "session_id":             video_id,
            "filters_used":           {},
            "awaiting_clarification": False,
        }


@app.post("/chat")
async def chat_endpoint(req: ChatRequest):
    """
    /chat  --  backward-compatible route (used by frontend_vexed/app.js).
    Accepts {text, video_id}, returns {reply, results, language_detected, ...}.
    """
    return _handle_chat(req)


@app.post("/api/chat")
async def api_chat_endpoint(req: ChatRequest):
    """
    /api/chat  --  clean REST path for external tooling or future mobile clients.
    Identical handler to /chat.
    """
    return _handle_chat(req)


@app.delete("/chat/session/{session_id}")
async def clear_chat_session(session_id: str):
    """
    Clear the conversation memory for a given session (video).
    Useful when the user uploads a new video and wants a fresh context.
    """
    try:
        from engine.session_db import clear_session
        clear_session(session_id)
        return {"status": "ok", "message": f"Session {session_id} cleared."}
    except Exception as exc:
        return {"status": "error", "message": str(exc)}


# ═══════════════════════════════════════════════════════════════════
# VIDEOS LIBRARY  (persistent folder for pre-stored videos)
# ═══════════════════════════════════════════════════════════════════
_VIDEOS_DIR = os.path.join(BACKEND_PATH, "videos")
os.makedirs(_VIDEOS_DIR, exist_ok=True)  # auto-create on startup

_VIDEO_EXTENSIONS = {".mp4", ".mov", ".avi", ".mkv", ".webm", ".m4v"}


@app.get("/videos/list")
async def list_library_videos():
    """
    Return all video files in fresh_clone/videos/ as a JSON list.
    Each entry: {name, video_id, size_mb, already_ingested}
    """
    videos_out = []
    try:
        for fname in sorted(os.listdir(_VIDEOS_DIR)):
            if fname.startswith("."):
                continue  # skip .gitkeep etc.
            ext = os.path.splitext(fname)[1].lower()
            if ext not in _VIDEO_EXTENSIONS:
                continue
            fpath    = os.path.join(_VIDEOS_DIR, fname)
            size_mb  = round(os.path.getsize(fpath) / (1024 * 1024), 1)
            vid_id   = os.path.splitext(fname)[0]  # stem = video_id
            # Check if already ingested in SQLite
            ingested = False
            if _backend_available:
                try:
                    counts = get_class_counts(vid_id)
                    ingested = len(counts) > 0
                except Exception:
                    pass
            videos_out.append({
                "name":             fname,
                "video_id":         vid_id,
                "size_mb":          size_mb,
                "already_ingested": ingested,
            })
    except Exception as exc:
        logger.warning("list_library_videos error: %s", exc)
    return {"videos": videos_out}


class VideoSelectRequest(BaseModel):
    video_id: str


@app.post("/videos/select")
async def select_library_video(req: VideoSelectRequest):
    """
    Set a library video as the active video.
    If already ingested → instant switch (no re-ingest).
    If not ingested → triggers ingestion job in background.
    Returns: {status, video_id, ingested, job_id?}
    """
    global _active_video_id
    vid_id = req.video_id.strip()

    # Find the file in the library
    target_path: str | None = None
    for fname in os.listdir(_VIDEOS_DIR):
        stem = os.path.splitext(fname)[0]
        if stem == vid_id:
            target_path = os.path.join(_VIDEOS_DIR, fname)
            break

    if not target_path or not os.path.isfile(target_path):
        return {"status": "error", "message": f"Video '{vid_id}' not found in library."}

    # Check if already ingested
    already_ingested = False
    if _backend_available:
        try:
            counts = get_class_counts(vid_id)
            already_ingested = len(counts) > 0
        except Exception:
            pass

    if already_ingested:
        # Instant switch — just set active video
        _active_video_id = vid_id
        logger.info("Library video selected (already ingested): %s", vid_id)
        return {"status": "ok", "video_id": vid_id, "ingested": True}

    # Not yet ingested — start background ingestion
    job_id = str(uuid.uuid4())[:8]
    with _jobs_lock:
        _ingest_jobs[job_id] = {
            "status":                 "queued",
            "progress":               0,
            "phase":                  "queued",
            "video_id":               vid_id,
            "collection_name":        None,
            "_original_video_path":   target_path,
            "_start_time":            time.monotonic(),
        }
    thread = threading.Thread(
        target=_run_ingestion_job,
        args=(job_id, target_path),
        daemon=True,
    )
    thread.start()
    logger.info("Library video ingestion started: %s (job %s)", vid_id, job_id)
    return {"status": "ingesting", "video_id": vid_id, "job_id": job_id, "ingested": False}



# ═══════════════════════════════════════════════════════════════════
# RUN
# ═══════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=False)

