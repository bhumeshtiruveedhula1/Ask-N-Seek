"""Ask-N-Seek API Bridge. Auto-detects backend, falls back to mock data."""
import os, sys, uuid, difflib, string

# ── Bridge-to-Backend Path Resolution ──────────────────────────────────────
# Bridge lives at fresh_clone/frontend/bridge/. Backend engine lives at
# fresh_clone/engine/. Add fresh_clone/ to sys.path so that engine.* imports
# work regardless of where uvicorn is launched from.
_BRIDGE_DIR   = os.path.dirname(os.path.abspath(__file__))
# 2 levels up from bridge/ → fresh_clone/
_BACKEND_ROOT = os.path.normpath(os.path.join(_BRIDGE_DIR, "..", ".."))
if os.path.exists(os.path.join(_BACKEND_ROOT, "engine", "scenario_presets.py")):
    if _BACKEND_ROOT not in sys.path:
        sys.path.insert(0, _BACKEND_ROOT)
else:
    # Fallback: scan up to 3 levels (legacy / flat layout support)
    for _depth in range(1, 5):
        _candidate = os.path.normpath(os.path.join(_BRIDGE_DIR, *[".."] * _depth))
        if os.path.exists(os.path.join(_candidate, "engine", "scenario_presets.py")):
            if _candidate not in sys.path:
                sys.path.insert(0, _candidate)
            break
# ── End Path Resolution ────────────────────────────────────────────────────

from typing import Any
from contextlib import asynccontextmanager
from fastapi import FastAPI, Form
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

def _find_backend():
    env = os.environ.get("BACKEND_PATH", "").strip()
    if env:
        env = os.path.normpath(env)
        if os.path.isfile(os.path.join(env, "config.py")): return env
    bridge_dir = os.path.dirname(os.path.abspath(__file__))
    for up in [2, 1, 3]:
        parent = os.path.abspath(os.path.join(bridge_dir, *([".."] * up)))
        for name in ["Ask-N-Seek", "ask-n-seek", "Ask_N_Seek", "ask_n_seek",
                     "Ask-N-Seek-main", "ask-n-seek-main", "Ask_N_Seek_integration",
                     "main-project", "1.main-project", "backend", "Ask_N_Seek"]:
            c = os.path.join(parent, name)
            if os.path.isfile(os.path.join(c, "config.py")): return c
    for up in [2, 1, 3]:
        parent = os.path.abspath(os.path.join(bridge_dir, *([".."] * up)))
        for root, dirs, files in os.walk(parent):
            if root[len(parent):].count(os.sep) > 2:
                del dirs[:]
                continue
            if "config.py" in files and os.path.isdir(os.path.join(root, "engine")):
                return root
    print("[bridge] Could not find backend. Will use MOCK data.")
    return ""

BACKEND_PATH = _find_backend()
_backend_available = False

try:
    if BACKEND_PATH:
        sys.path.insert(0, BACKEND_PATH)
        import config as _config
        from config import load_threshold
        from engine.parser_gateway import parse_query
        from engine.qdrant_gateway import get_qdrant_client, get_collection_name
        from engine.search import search_structured
        from engine.explanation import generate_explanation
        from engine.diagnosis import run_diagnosis
        from engine.scenario_presets import get_scenarios as _get_scenarios
        from backend.vision.vocabulary import VOCABULARY, VOCABULARY_SET, SYNONYM_MAP
        from backend.query.patterns import COLOR_VOCAB, COLOR_ALIASES
        _qdrant_client = get_qdrant_client()
        _collection = get_collection_name()
        _backend_available = True
        print("[bridge] Backend connected successfully.")
    else:
        raise ImportError("No backend path found")
except Exception as e:
    print(f"[bridge] Backend import failed: {e}")
    print("[bridge] Running in MOCK mode.")
    _backend_available = False
    _qdrant_client = None
    _collection = "mock_collection"

    class MockResult:
        def __init__(self):
            self.video_id = "demo_video"
            self.timestamp = 12.5
            self.scene_id = 3
            self.confidence_score = 0.85
            self.matched_objects = [{"class_name": "person", "color": "red", "bbox": [0.2, 0.3, 0.5, 0.8], "confidence": 0.9}]
            self.score_breakdown = None  # populated below as a plain dict for mock

    _MOCK_SCORE_BREAKDOWN = {
        "total": 71,
        "object_score": 28,
        "color_score": 0,
        "spatial_score": 18,
        "negation_score": 20,
        "details": {
            "object": "person detected, conf 0.71",
            "color": "no color constraint",
            "spatial": "left_of car",
            "negation": "no helmet detected",
        },
    }

    def _get_scenarios():
        return [
            {"id": "safety_violation", "label": "\U0001f534 Safety Violation", "query": "person without helmet"},
            {"id": "traffic_incident",  "label": "\U0001f697 Traffic Incident",  "query": "car left of person"},
            {"id": "lost_item",         "label": "\U0001f392 Lost Item",          "query": "backpack without owner"},
            {"id": "access_control",    "label": "\U0001f6aa Access Control",     "query": "person without badge"},
            {"id": "crowd_check",       "label": "\U0001f465 Crowd Check",        "query": "more than two people"},
        ]

    def parse_query(q):
        return {"status": "match", "filters": {"class": "person", "color": "red"}}
    def load_threshold(): return 0.3197
    def search_structured(fd, client, coll):
        if "purple elephant" in str(fd).lower() or "nonsense" in str(fd).lower(): return []
        return [MockResult()]
    def generate_explanation(r):
        return "Matched: person detected with red color at high confidence."
    def run_diagnosis(filters, client, coll):
        return {"html": "<p><strong>Person:</strong> 23 scenes found.<br><strong>Red:</strong> 8 scenes found.<br><strong>Together:</strong> 0 scenes.</p>"}
    VOCABULARY = ["person", "car", "truck", "bicycle", "dog", "cat", "chair", "bottle", "laptop", "cell phone", "backpack"]
    VOCABULARY_SET = set(VOCABULARY)
    SYNONYM_MAP = {}
    COLOR_VOCAB = {"red", "blue", "green", "yellow", "black", "white", "dark blue", "dark green"}
    COLOR_ALIASES = {}

QUERY_SYNTAX_WORDS = {
    "in", "on", "at", "with", "without", "no", "not", "of", "to", "the", "a", "an",
    "and", "or", "left", "right", "is", "are", "has", "have", "wearing", "less",
    "top", "bottom", "near", "beside", "one", "two", "three", "four", "five", "six",
    "seven", "eight", "nine", "ten", "couple", "few", "several", "more", "fewer",
    "than", "least", "exactly", "person", "people", "man", "woman", "child", "car",
}

_COLOR_WORDS = set()
for mc in list(COLOR_VOCAB) + list(COLOR_ALIASES.keys()):
    for w in mc.split():
        _COLOR_WORDS.add(w)

KNOWN_TOKENS = (
    VOCABULARY_SET | set(SYNONYM_MAP.keys()) | set(SYNONYM_MAP.values()) |
    COLOR_VOCAB | set(COLOR_ALIASES.keys()) | _COLOR_WORDS | QUERY_SYNTAX_WORDS
)

def _check_vocab(query: str):
    punct = str.maketrans(string.punctuation, " " * len(string.punctuation))
    clean = query.translate(punct).lower()
    tokens = clean.split()
    warnings = []
    for token in tokens:
        if token in KNOWN_TOKENS or token.isdigit():
            continue
        matches = difflib.get_close_matches(token, VOCABULARY, n=1, cutoff=0.6)
        if matches:
            warnings.append({"token": token, "suggestion": matches[0]})
        else:
            warnings.append({"token": token, "suggestion": ""})
    return warnings

class QueryRequest(BaseModel):
    query: str
    collection_name: str | None = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    print("Bridge server starting...")
    print(f"   Backend: {'CONNECTED' if _backend_available else 'MOCK MODE'}")
    yield
    print("Bridge server shutting down...")

app = FastAPI(title="Ask-N-Seek Bridge", version="2.3.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/health")
def health():
    return {"status": "ok", "bridge": "v2.3", "backend_mode": "real" if _backend_available else "mock", "backend_path": BACKEND_PATH or "not_found"}

@app.post("/query")
def query_endpoint(req: QueryRequest):
    target = req.collection_name or _collection
    parsed = parse_query(req.query)
    if parsed.get("status") != "match":
        return {"status": "no_match", "parsed": parsed, "results": [], "diagnosis": None, "vocab_warnings": _check_vocab(req.query)}
    results = search_structured(parsed, _qdrant_client, target)
    threshold = load_threshold()
    best_score = results[0].confidence_score if results else 0.0
    enriched = []
    for r in results:
        # Serialize score_breakdown if present
        sb = getattr(r, "score_breakdown", None)
        sb_dict: dict | None = None
        if sb is not None:
            if hasattr(sb, "total"):  # real ScoreBreakdown dataclass
                sb_dict = {
                    "total":          sb.total,
                    "object_score":   sb.object_score,
                    "color_score":    sb.color_score,
                    "spatial_score":  sb.spatial_score,
                    "negation_score": sb.negation_score,
                    "details":        getattr(sb, "details", {}),
                }
            else:  # already a plain dict (mock mode)
                sb_dict = sb
        elif not _backend_available:
            sb_dict = _MOCK_SCORE_BREAKDOWN
        enriched.append({
            "video_id": r.video_id,
            "timestamp": r.timestamp,
            "scene_id": r.scene_id,
            "confidence_score": r.confidence_score,
            "matched_objects": r.matched_objects,
            "explanation": generate_explanation(r),
            "score_breakdown": sb_dict,
        })
    diagnosis = None
    if not results or best_score < threshold:
        try:
            diag = run_diagnosis(parsed.get("filters", {}), _qdrant_client, target)
            diagnosis = {"html": diag["html"], "best_score": best_score}
        except Exception as e:
            diagnosis = {"html": f"<p>Diagnosis unavailable: {e}</p>", "best_score": best_score}
    return {"status": "match" if (results and best_score >= threshold) else "no_match", "parsed": parsed, "results": enriched, "diagnosis": diagnosis, "threshold": threshold, "best_score": best_score, "vocab_warnings": _check_vocab(req.query)}

@app.post("/ingest/start")
def ingest_start(video_path: str = Form(...)):
    job_id = str(uuid.uuid4())[:8]
    collection = f"judge_session_{uuid.uuid4().hex[:12]}"
    return {"job_id": job_id, "collection_name": collection, "video_path": video_path, "status": "started"}

@app.get("/ingest/status/{job_id}")
def ingest_status(job_id: str):
    return {"job_id": job_id, "status": "complete", "progress": 100}

@app.post("/vocab/check")
def vocab_check(query: str = Form(...)):
    return _check_vocab(query)


@app.get("/scenarios")
def get_scenarios_endpoint():
    """Return the 5 one-click investigation scenario presets."""
    return {"scenarios": _get_scenarios()}
