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
    "in", "on", "at", "with", "without", "no", "not", "of", "to", "the", "a", "an",
    "and", "or", "left", "right", "is", "are", "has", "have", "wearing", "less",
    "top", "bottom", "near", "beside", "one", "two", "three", "four", "five", "six",
    "seven", "eight", "nine", "ten", "couple", "few", "several", "more", "fewer",
    "than", "least", "exactly", "person", "people", "man", "woman", "child", "car",
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
    logger.info("  Ask-N-Seek Bridge Server v2.4")
    logger.info("  Mode: %s", "MOCK" if _MOCK_MODE else "CONNECTED")
    logger.info("  Backend path: %s", BACKEND_PATH)
    logger.info("=" * 60)
    yield
    logger.info("🛑 Server shutting down...")


app = FastAPI(
    title="Ask-N-Seek Bridge v2.4",
    description="REST API connecting the HTML frontend to the real backend pipeline",
    version="2.4.0",
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

    # ── 1. Check all active jobs for the original uploaded path (TASK 3) ──
    filename_stem = os.path.splitext(os.path.basename(filename))[0].lower()
    with _jobs_lock:
        jobs_snapshot = list(_ingest_jobs.values())

    for job in jobs_snapshot:
        orig = job.get("_original_video_path")
        if orig and os.path.isfile(orig):
            orig_stem = os.path.splitext(os.path.basename(orig))[0].lower()
            # Match if: filename exactly matches OR stems match
            if os.path.basename(orig) == filename or orig_stem == filename_stem:
                logger.info("Serving video from job path: %s", orig)
                ext = os.path.splitext(orig)[1].lower()
                mime = _VIDEO_MIME.get(ext, "video/mp4")
                return FileResponse(
                    orig,
                    media_type=mime,
                    headers={"Accept-Ranges": "bytes"},
                )

    # ── 2-6. Fallback: search known directories ──
    # Build VIDEO_SEARCH_PATHS from env (colon or semicolon separated)
    env_paths: list[str] = []
    raw_env = os.environ.get("VIDEO_SEARCH_PATHS", "")
    if raw_env:
        import re as _re
        env_paths = [p.strip() for p in _re.split(r"[;:]", raw_env) if p.strip()]

    search_dirs = [
        os.path.join(BACKEND_PATH, "temp_frames"),
        BACKEND_PATH,
        os.path.join(BACKEND_PATH, "outputs"),
        tempfile.gettempdir(),
        *env_paths,
    ]

    # Detect MIME from requested filename extension
    req_ext = os.path.splitext(filename)[1].lower()
    mime = _VIDEO_MIME.get(req_ext, None) or mimetypes.guess_type(filename)[0] or "video/mp4"

    # Try exact match first, then stem-only match (handles mp4/mov differences)
    for d in search_dirs:
        # Exact match
        candidate = os.path.join(d, filename)
        if os.path.isfile(candidate):
            logger.info("Serving video (exact): %s", candidate)
            c_ext = os.path.splitext(candidate)[1].lower()
            c_mime = _VIDEO_MIME.get(c_ext, mime)
            return FileResponse(
                candidate,
                media_type=c_mime,
                headers={"Accept-Ranges": "bytes"},
            )

    # Stem-only match in each directory (allows video_id without extension)
    for d in search_dirs:
        if not os.path.isdir(d):
            continue
        try:
            for entry in os.scandir(d):
                if entry.is_file():
                    entry_stem = os.path.splitext(entry.name)[0].lower()
                    if entry_stem == filename_stem:
                        logger.info("Serving video (stem match): %s", entry.path)
                        c_ext = os.path.splitext(entry.name)[1].lower()
                        c_mime = _VIDEO_MIME.get(c_ext, mime)
                        return FileResponse(
                            entry.path,
                            media_type=c_mime,
                            headers={"Accept-Ranges": "bytes"},
                        )
        except PermissionError:
            continue

    logger.warning("Video not found: '%s' | searched: %s", filename, search_dirs)
    return JSONResponse(
        status_code=404,
        content={"error": f"Video file not found", "requested": filename},
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
# RUN
# ═══════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=False)

