# ASK-N-SEEK — MASTER HANDOFF REPORT v2.4.2
## Session: 2026-08-04 (Frontend Corruption Recovery + Clean Rebuild)
## From: Kimi (Moonshot AI) | To: Next AI Agent
## Status: SYSTEM COMPLETE | Tests: 103/103 Passing | Commit: 20a8744

---

## 0. HOW TO PULL THIS PROJECT (For Next AI)

```bash
git clone https://github.com/bhumeshtiruveedhula1/Ask-N-Seek.git
cd Ask-N-Seek
git checkout stable_merge
# Primary branch: stable_merge @ commit 20a8744
```

**Repository:** `https://github.com/bhumeshtiruveedhula1/Ask-N-Seek`
**Primary branch:** `stable_merge` (was `integration/part3`, now merged forward)
**Fallback branch:** `integration/part3` @ `29ceb5e`
**Latest commit:** `20a8744` — "feat(frontend): rebuild HTML v2 with Prompts 1-5 features"
**Previous commit:** `29ceb5e` — "fix: add core backend files"

---

## 1. WHAT HAPPENED IN THIS SESSION (2026-08-04)

This session was a **corruption recovery and clean rebuild session** — not new features.

### The Incident
- **Prompts 1-2 (working):** Backend bridge fixes + frontend visual polish worked correctly.
- **Prompt 3-4 (corrupted):** Previous AI used Python regex-injection scripts to modify a 3,000-line `app.js`. On Windows CRLF files, `\n` in Python string literals became real newline characters in JS. `\'` became real quotes. This broke string literals and regex patterns throughout the file.
- **Result:** Browser threw `SyntaxError: Invalid or unexpected token` at `app.js:394`. Frontend completely dead.

### The Fix
- **Nuclear reset:** Restored `app.js`, `index.html`, `styles.css` from the clean `ask-n-seek-frontend-v2/` design reference (24KB clean JS, passes `node --check`).
- **Clean rebuild:** Wrote all three frontend files completely in one shot (no injection scripts, no regex patches). Re-added ALL Prompts 1-5 features on top of the clean foundation.
- **Verification:** `node --check app.js` passes. Browser test: upload → ingestion → presets → search → score bars → 6s clip playback → all working.

### Commit History (This Session)

| Commit | Message | What Changed |
|---|---|---|
| `20a8744` | feat(frontend): rebuild HTML v2 with Prompts 1-5 features | Clean rebuild of `frontend/app.js`, `index.html`, `styles.css` |
| `29ceb5e` | fix: add core backend files | Previous stable base (backend only) |
| `37a4fa3` | chore(frontend): remove tracked Next.js source files | Historical — Next.js removal |

**Backend tests: 103/103 passing. Zero regressions. Zero backend files touched.**

---

## 2. CURRENT FEATURES (All Working)

### Backend (Locked, Untouched)
- YOLO-World-M detection, CIELAB color, left/right spatial
- Qdrant payload filters + keyword indexes
- Rule-based spaCy parser with preprocessing
- No-Match Diagnosis, Session Isolation, Threshold 0.3197
- Smart Result Scoring (ScoreBreakdown dataclass)
- Query Result Caching, Scenario Presets

### Frontend (Rebuilt, Verified)
- **Bright terminal logs** — qlog glow colors (blue/green/red/amber)
- **Elapsed timer + percentage** — live MM:SS + large gold pct during ingestion
- **Top-10 detected objects grid** — post-ingestion cards with counts
- **Ingestion stats grid** — Scenes / Keyframes / Objects counts
- **Gold timestamp cards** — replace clapperboard, large `10.0s` display
- **6-second clip player** — auto-seeks `t-3`, auto-pauses at `t+3`, replay button
- **Score bar micro-labels** — "No color constraint" / "Not detected"
- **Result jump list** — clickable list below player with active highlight
- **Smart scenario presets** — dim irrelevant (25% opacity), green "Detected" badge on relevant
- **Quick search chips** — top 5 detected class pills
- **Hover tooltips** — preset hover shows class counts
- **Vocab warnings** — "Did you mean: X?" banner
- **Query history** — sidebar with cache reuse on replay
- **Video seek** — click result → 6s clip playback
- **Collection badge** — gold left border + green ready dot

---

## 3. KNOWN ISSUES (Do Not Try to Fix These Again)

### Issue A: Color on Vehicles with Large Windows
**Location:** `backend/vision/color_extractor.py`
**Why:** Center-weighted crop reads window glass instead of body paint.
**Status:** Architectural limitation. Demo strategy: "Color reads center pixels; on vehicles with large windows it may see the glass."

### Issue B: System Feels Slower on Some Videos
**Location:** `engine/live_ingestor.py`
**Why:** More motion → more scene boundaries → more keyframes.
**Status:** Acceptable. ~30-45s for typical 1-3 min videos.

---

## 4. VALIDATION RESULTS

### Backend Tests
```
103 passed, 2 warnings, 0 regressions
```

### TypeScript Check
Not applicable — HTML v2 frontend (zero build).

### Bridge API Test
```
GET http://localhost:8000/health
→ HTTP 200, {"status":"ok","backend_mode":"connected"}

GET http://localhost:8000/scenarios
→ HTTP 200, 5 scenarios returned
```

### Frontend Visual Test
```
Upload zone responsive ✓
Progress bar + timer + percentage render ✓
Top-10 objects grid appears post-ingestion ✓
Scenario presets filter by detected classes ✓
Search returns results with score bars ✓
6-second clip playback auto-seeks and pauses ✓
Jump list navigates between results ✓
No-Match Diagnosis renders correctly ✓
```

---

## 5. CURRENT FILE STATE

| File | Status | Note |
|---|---|---|
| `engine/*` | ✅ Clean | 103/103 tests, untouched |
| `backend/*` | ✅ Clean | Untouched |
| `ui/gradio_app.py` | ✅ Clean | Fallback UI still works |
| `frontend/bridge_server.py` | ✅ Clean | Prompt 1 fixes preserved |
| `frontend/index.html` | ✅ Rebuilt | All DOM elements present |
| `frontend/app.js` | ✅ Rebuilt | `node --check` passes |
| `frontend/styles.css` | ✅ Rebuilt | Original v2 + new feature styles |
| `config.py` | ✅ Clean | Untouched |
| `start_dev.py` | ✅ Clean | Launches bridge + static server |

---

## 6. ARCHITECTURE — STILL LOCKED

**Do NOT change these decisions:**
- YOLO-World-M (50MB) — do not swap models
- Rule-based parser (spaCy) — do not swap for LLM
- Qdrant payload filters — no embedding fallback
- Threshold 0.3197 — hardcoded, do not recalibrate
- Left/right spatial only
- No-Match Diagnosis — decomposed sub-queries + closest miss
- Session isolation — `judge_session_<uuid>`
- HTML v2 frontend — do not revert to Next.js or Gradio
- FastAPI bridge on port 8000
- Frontend theme: black (#000000), cream (#f5f3ef), sand (#c4b8a5)

---

## 7. WHAT'S LEFT TO DO

### Immediate (Before Hackathon)
1. **REHEARSAL** — Run the 60-second demo flow 5 times with different videos
2. **Full E2E test** — Upload → preset → verify Smart Score Bars → clip playback
3. **Fresh clone validation** — One clean install test on teammate's machine
4. **Backend optimization** — If time permits post-demo-hardening (see below)

### Not To Do (Locked Out)
- Cascade Vocabulary Fallback — cut
- Parse Lens — cut
- Click-to-Query — cut
- Real-time camera stream — out of scope
- Embedding fallback — cut
- Near/above/behind spatial — locked out
- Entering/leaving tracking — locked out
- YOLO model swap — do not do this
- Voice query input — cut
- Performance telemetry — cut
- Export report — cut

### Post-Rehearsal (If Time Permits)
- Multi-scale inference (YOLO at 640+1280)
- Test-time augmentation (horizontal flip)
- Whisper audio transcript search
- Local LLM parser (stretch goal, last)

---

## 8. KEY CONTRACTS (For Next AI)

### ParseResult dataclass (READ-ONLY)
```python
result.objects   # list of dicts: {class_name, color, negated:bool, count_op, count_val}
result.spatial   # list of dicts: {subject, relation, object_}
result.unresolved_tokens  # list[str]
result.qdrant_filter      # DO NOT USE — use objects/spatial instead
```

### parser_gateway.parse_query() output
```python
{
    "status": "match" | "no_match",
    "filters": {
        "class":            str | None,
        "color":            str | None,
        "negated":          list[str],
        "spatial_relation": {"type": str, "target_class": str} | None,
        "count_constraint": {"class": str, "op": str, "value": int} | None,
    }
}
```

### ScoreBreakdown dataclass
```python
@dataclass
class ScoreBreakdown:
    total: int           # 0-100
    object_score: int    # 0-40
    color_score: int     # 0-20
    spatial_score: int   # 0-20
    negation_score: int  # 0-20
    details: dict[str, str]  # human-readable per category
```

### search_structured() signature
```python
def search_structured(
    filter_dict: dict,          # must be stub-flat shape above
    client: QdrantClient = ..., # defaults to qdrant_gateway default
    collection_name: str = ..., # defaults to config.QDRANT_COLLECTION
) -> list[Result]              # each Result has .score_breakdown
```

### LiveIngestor usage
```python
from engine.live_ingestor import LiveIngestor
from engine.qdrant_gateway import get_qdrant_client

client = get_qdrant_client()
ingestor = LiveIngestor(client, collection_name=None)  # auto-generates judge_session_<uuid>

for update in ingestor.ingest("path/to/video.mp4"):
    print(update)  # {phase, progress_pct, message, stats}
```

### Scenario Presets
```python
from engine.scenario_presets import SCENARIO_PRESETS, get_scenarios
# Returns: [{"id": "safety_violation", "label": "🔴 Safety Violation", "query": "person without helmet"}, ...]
```

### Bridge API (Current State)
```
GET  /health                 → {"status":"ok","backend_mode":"connected","collection":"..."}
GET  /scenarios              → {"scenarios": [...]}
POST /query                  → {"results": [...], "diagnosis": {...}, "parsed": {...}}
GET  /ingest/status/{job_id} → {"status":"complete","progress_pct":100,"top_classes":[...],"elapsed_seconds":42,"collection_name":"..."}
POST /ingest/start           → {"job_id":"...","collection":"..."}
POST /vocab/check            → {"warnings": [{"token":"...","type":"suggestion","suggestion":"..."}]}
GET  /video/{filename:path}  → Video file stream
```

---

## 9. HOW TO PROMPT THE NEXT AI

Give them:
1. **This handoff report** (v2.4.2)
2. **All canonical documents** (v2.4.1 versions — unchanged except this report)
3. **The code repository** (or `git pull origin stable_merge`)
4. **These instructions:**

```
You are continuing a hackathon build for Ask-N-Seek, a natural-language
video retrieval system. The base system is complete (103/103 tests passing).
Frontend was corrupted during Prompts 3-4 by newline-injection bugs and has
been cleanly rebuilt at commit 20a8744 on stable_merge.

Your job is execution coordinator, not architect. All technical decisions
are locked in 03_Architecture_Final_v2.4.1.md. Do not propose alternatives.

Current priority: REHEARSAL ONLY. The backend and zero-build HTML v2 frontend
are complete and verified. The win is in presentation now. No more building.

Model routing: Claude Sonnet for logic, Gemini Flash for bulk UI.
Always verify with raw evidence (pytest, timing numbers, node --check).

Git: https://github.com/bhumeshtiruveedhula1/Ask-N-Seek
Branch: stable_merge (commit 20a8744)
```

---

## 10. FINAL WORD

This system is **structurally complete, empirically tested, frontend-integrated, and demo-ready**.
The architecture is sound. The research is validated. The code is passing.
The benchmark is within target. The video seek works. The Smart Score Bars prove structured search.
The Scenario Presets make the demo flow effortless.

**The frontend corruption has been fixed. The rebuild is clean. All features from Prompts 1-5 are present and verified.**

What remains is **rehearsal** — not more building.

The win condition: A judge drops their own video, clicks "Safety Violation",
gets a result with 4 colored bars proving the system understood their question,
then types "purple elephant" and gets an honest diagnosis.
That's it. Everything else is noise.

---

"Type what happened, we'll show you exactly where — and prove it."

"Give us any video. We'll ingest it live, show you how we understood your
question, and if nothing matches, we'll tell you precisely why."
