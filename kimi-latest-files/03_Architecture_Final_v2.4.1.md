# ARCHITECTURE DOCUMENT — Hybrid Plan, LOCKED v2.4.1
### Validated across two independent adversarial passes (Gemini Pro
### Research + Perplexity). Convergent findings applied. This is the
### architecture the team builds against — not subject to further
### re-evaluation absent a genuine new finding.
### v2.2: No-Match Diagnosis built; performance fixes applied; payload
###   indexes + session isolation required; Live Ingestion, Query History,
###   Vocab Indicator approved; Parse Lens and Click-to-Query rejected.
### v2.3: Demo hardening — 7 commits fixing progress bar, color binding,
###   vocab noise, summary cap, GPU logging, click-to-seek.
### v2.4: Frontend integration — Next.js 14 + FastAPI bridge, Smart Result
###   Scoring, Query Scenario Presets, Query Result Caching.
### v2.4.1: Frontend pivoted to HTML/CSS/JS v2 (zero build). Real ingestion
###   wired in bridge_server.py. Parser preprocessing, 6s clip playback,
###   context-aware presets, quick chips, top-10 objects, elapsed timer,
###   score bar micro-labels, video serving endpoint.
### v2.5: Touching/near spatial (IoU + edge-gap), typo auto-correction,
###   wearing→in preprocessing, ambiguous class disambiguation (bat/stick/rod/
###   net/board), HIGH_VARIANCE_CLASSES confidence gates at 0.45.

---

## 1. System Diagram

```
┌───────────────────────────── INGESTION (once per video) ─────────────────────────────┐
│                                                                                        │
│  Video file(s) → PySceneDetect (scene-boundary timestamps, CPU, downscale_factor=2)   │
│       → release video object, seek + extract keyframes only at scene boundaries       │
│       → frame resize to max 720p height before save                                   │
│       → YOLO-World-M detection (fixed, pre-compiled vocabulary, 800+ terms)           │
│              ├─ bounding boxes + class labels + confidence                            │
│              ├─ center-weighted crop → resize 32×32 → k-means (max_iter=5, attempts=1) │
│              │   → nearest CIELAB color name                                           │
│              └─ left/right spatial relations (top-4-confidence pairs only)            │
│       → structured facts stored in Qdrant (payload filters + keyword index)           │
│         ├─ payload indexes: class_name (keyword), color (keyword),                     │
│         │   spatial_relations (keyword)                                               │
│         └─ per-session collection: "judge_session_<uuid>" for judge uploads            │
│                                                                                        │
│  [Whisper transcript search — added AFTER the above works end-to-end, not core MVP]   │
└────────────────────────────────────────────────────────────────────────────────────┘
                                          │
┌───────────────────────────── QUERY TIME (every search) ──────────────────────────────┐
│                                                                                        │
│  User types a natural-language query (or clicks a Scenario Preset or Quick Chip)       │
│       │                                                                                │
│  PRE-PROCESSING LAYER (v2.4.1 + v2.5)                                                   │
│       - "with no" / "having no" / "wearing no" → "without"                            │
│       - color+object compound splitting: "redshirt" → "red shirt"                     │
│       - synonym expansion: woman/man/lady/gentleman → "person"                        │
│       - wearing → "in" (v2.5, negation-safe): garment color binding                   │
│       - typo auto-correction (v2.5): difflib 0.70 ratio on OOV tokens                 │
│       │                                                                                │
│  RULE-BASED QUERY PARSER (required, primary — no model inference)                       │
│       - pattern-matches: negation ("without X", "no X", "lacking X"),                  │
│         counting ("more than N", "exactly N"),                                          │
│         spatial: left_of/right_of (centroid), touching (IoU>0.15), near (gap<50px),   │
│         compositional (object + attribute combinations)                                 │
│       - maps synonyms onto the fixed vocabulary via a curated lookup table              │
│       - binds modifiers to nouns via spaCy amod/compound/neg edges                     │
│       - KNOWN CEILING: prepositional negation ("without") uses surface phrase            │
│         matching + proximity heuristics, not prep→pobj dependency traversal.           │
│         Complex conjunctions ("without A or B") may misbind. Accepted boundary.         │
│       → structured Qdrant filter (stub-flat shape)                                    │
│       │                                                                                │
│  [STRETCH GOAL, LAST, OPTIONAL: swap this step for a local LLM                          │
│   (Qwen2.5-7B-Instruct, vLLM + xgrammar backend, flattened schema,                      │
│   reasoning-first field) — only after everything else is proven stable.                │
│   Does not change anything downstream if added later.]                                  │
│       │                                                                                │
│  Qdrant structured search → confidence-weighted rerank → grouped by source video       │
│       │                                                                                │
│  Score Breakdown (v2.4) — per-result 4-bar scoring:                                   │
│       - object_score: avg confidence of class-matched objects × 40                      │
│       - color_score: fraction of objects with target color × 20                         │
│       - spatial_score: 20 if spatial relation present, 0 if not                         │
│       - negation_score: 20 if negation satisfied (enforced at search time)              │
│       → ScoreBreakdown dataclass attached to each Result                               │
│       │                                                                                │
│  Confidence threshold check (calibrated: 10 valid + 5 near-miss queries,                │
│  threshold = 0.3197, hard-coded)                                                        │
│       │                                                                                │
│  below threshold ──────────────────┬──────────────── above threshold                     │
│       │                             │                                                   │
│  NO-MATCH DIAGNOSIS (v2.2)      Templated explanation + Score Breakdown bars            │
│  - Decompose filter into sub-    ("Matched because: person detected, no helmet,        │
│    queries per constraint           left of car, confidence 0.81")                      │
│  - Count matches per constraint   + Score: 94/100 [Object 32/40, Color 0/20,            │
│  - Find closest miss by relaxing     Spatial 18/20, Negation 20/20]                    │
│    one constraint at a time                                                            │
│  - Render diagnosis HTML                                                               │
│                                                                                        │
│  [VOCABULARY COVERAGE INDICATOR (v2.2 upgrade)]                                        │
│   - Scan query tokens against VOCABULARY + SYNONYM_MAP before search                    │
│   - If OOV: show "Did you mean: X?" banner                                              │
│   - Quality gate (v2.4.1): SequenceMatcher.ratio >= 0.70 required                      │
│                                                                                        │
│  [QUERY RESULT CACHING (v2.4 upgrade)]                                                  │
│   - Dict-backed cache: query+collection → complete result tuple                         │
│   - Auto-clear on new video ingestion                                                   │
│   - GIL-safe, no external deps                                                          │
│                                                                                        │
└────────────────────────────────────────────────────────────────────────────────────┘

┌───────────────────────────── LIVE INGESTION MODE (v2.2 upgrade) ──────────────────────┐
│                                                                                        │
│  Judge drops video → HTML upload zone → drag-and-drop or file picker                  │
│       → POST /ingest/start (multipart/form-data) → FastAPI Bridge                     │
│       → Saves to temp path, instantiates LiveIngestor(client)                          │
│       → Background thread + queue.Queue + Python generator (yield per phase)           │
│       → Streaming progress log: "Scene detection...", "Keyframe extraction...",          │
│         "YOLO detection...", "Color extraction...", "Spatial relations...",              │
│         "Qdrant indexing..."                                                           │
│       → Per-session collection: judge_session_<uuid>                                    │
│       → On completion: auto-reveal query section, render top-10 objects grid,          │
│         show collection badge with green ready dot                                     │
│       → Frontend polls /ingest/status/{job_id} every 800ms                             │
│                                                                                        │
└────────────────────────────────────────────────────────────────────────────────────┘

┌───────────────────────────── FRONTEND STACK (v2.4.1 — HTML v2) ──────────────────────┐
│                                                                                        │
│  HTML5 / CSS3 / Vanilla JS (zero build step)                                           │
│       → Semantic HTML, 11 editorial sections                                           │
│       → Tailwind-like custom CSS (dark luxury editorial: black/cream/sand)             │
│       → Canvas particle engine (hero section)                                          │
│       → IntersectionObserver scroll reveals                                            │
│       → Drag-and-drop upload zone with radial spotlight                                │
│       → No external JS frameworks, no npm, no build pipeline                           │
│                                                                                        │
│  FastAPI Bridge (port 8000) — frontend/bridge_server.py                                │
│       → Auto-discovers Python backend (scans parent dir)                               │
│       → Falls back to MOCK mode if backend disconnected                                │
│       → Endpoints: GET /scenarios, POST /query, GET /health,                          │
│                     POST /ingest/start, GET /ingest/status/{id},                      │
│                     POST /vocab/check, GET /video/{filename}                           │
│       → Serves score_breakdown in query responses                                      │
│       → Serves video files for 6-second clip playback                                  │
│                                                                                        │
│  Static File Server (port 3000)                                                        │
│       → Python http.server serving frontend/ directory                                 │
│       → index.html is the entry point                                                  │
│                                                                                        │
│  Dev Launcher: start_dev.py                                                            │
│       → Opens Bridge (uvicorn) and static server in separate terminals                 │
│       → Cross-platform (Windows .bat / Unix .sh wrappers available)                    │
│                                                                                        │
│  Sections (11):                                                                        │
│       1. Navigation    2. Hero    3. Quote    4. About    5. Concept                     │
│       6. Cinematic    7. SVG Path Text    8. Pipeline Breakdown    9. Infrastructure   │
│       10. Interactive Demo (upload, search, results, score bars, 6s clips)   11. Footer│
│                                                                                        │
└────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Component Table (final, locked v2.4.1)

| Layer | Decision | Status |
|---|---|---|
| Object detector | YOLO-World-M, fixed vocabulary expanded to 800+ terms | Locked ✅ |
| Color extraction | Center-weighted crop → resize 32×32 → k-means (max_iter=5, attempts=1) → CIELAB | Locked ✅ |
| Scene chunking | PySceneDetect, downscale_factor=2, timestamp-then-seek memory pattern | Locked ✅ |
| Frame resize | Max 720p height, aspect-preserved, before save | Locked ✅ |
| Duration cap | MAX_DURATION_S=180, auto-trim + warning | Locked ✅ |
| Spatial relations | Left/right/touching/near, top-4-confidence pairs (left/right); all pairs (touching/near) | Locked ✅ (v2.5) |
| Ambiguous class gates | HIGH_VARIANCE_CLASSES: 0.45 confidence for bat/kite/skis/stick/rod/net/board | Locked ✅ (v2.5) |
| Structured store | Qdrant, payload filters + **keyword indexes on class_name, color, spatial_relations** | Locked ✅ |
| Session isolation | Per-session collections: `judge_session_<uuid>` | Locked ✅ |
| Query parser | **Rule-based / pattern-matching (required, primary)** | Locked ✅ |
| Parser preprocessing | "with no" → "without", compound splitting, synonym expansion, wearing→in, typo correction | Locked ✅ (v2.5) |
| Parser typo correction | difflib SequenceMatcher >= 0.70 on OOV tokens, structural words protected | Locked ✅ (v2.5) |
| Touching spatial | IoU > 0.15 between any pair of bboxes → "touching" relation stored in Qdrant | Locked ✅ (v2.5) |
| Near spatial | Edge-to-edge gap < SPATIAL_NEAR_GAP_PX (50px) → "near" relation stored in Qdrant | Locked ✅ (v2.5) |
| Wearing preprocess | "wearing" → "in" before spaCy (negative lookbehind guards negation phrases) | Locked ✅ (v2.5) |
| Explanation generation | **Templated from structured facts (required, primary)** | Locked ✅ |
| No-Match Diagnosis | Decomposed sub-queries + closest miss relaxation | Locked ✅ |
| Threading model | Background daemon thread + queue.Queue for ingestion handlers | Locked ✅ |
| Smart Result Scoring | ScoreBreakdown dataclass, 4-bar per-result scoring | Locked ✅ |
| Score bar micro-labels | "No [X] constraint" / "Not detected" labels | Locked ✅ (v2.4.1) |
| Query Scenario Presets | 5 investigation presets, `/scenarios` endpoint | Locked ✅ |
| Context-aware presets | Dim irrelevant, green "Detected" badge, hover tooltips | Locked ✅ (v2.4.1) |
| Quick Search Chips | Top-5 detected class pills | Locked ✅ (v2.4.1) |
| Query Result Caching | Dict-backed, auto-clear on ingestion | Locked ✅ |
| 6-Second Clip Playback | Seek t-3, auto-pause t+3, replay button, jump list | Locked ✅ (v2.4.1) |
| Top-10 Objects Grid | Post-ingestion detected class summary | Locked ✅ (v2.4.1) |
| Video serving endpoint | `/video/{filename:path}`, multi-dir search, MIME detection | Locked ✅ (v2.4.1) |
| Frontend framework | **HTML5/CSS3/Vanilla JS v2** (replaces Next.js for demo reliability) | Locked ✅ (v2.4.1) |
| Frontend theme | Dark luxury editorial: black (#000000), cream (#f5f3ef), sand (#c4b8a5) | Locked ✅ |
| Typography | Playfair Display (headlines), Inter (body), JetBrains Mono (data) | Locked ✅ |
| Bridge server | FastAPI on port 8000, auto-discovery + mock fallback | Locked ✅ |
| Dev launcher | `start_dev.py` — uvicorn + Python http.server | Locked ✅ (v2.4.1) |
| Local LLM | Qwen2.5-7B-Instruct, vLLM + xgrammar, flattened + reasoning-first schema | **Stretch goal — built last, optional** |
| Embedding fallback (SigLIP2 + FAISS) | **Removed entirely** | Cut |
| Audio transcription | Whisper-small, faster-whisper INT8 | Locked scope, built after core visual pipeline |
| Hardware | Primary: RTX 4060. Backup: RX 6700S (no YOLO unless ROCm verified) | Locked |
| Entering/leaving tracking | Not built | Locked — proven fragile |
| Above/inside/behind spatial | Not built | Locked — 2D-unreliable |
| **Parse Lens** (live dependency tree) | **Rejected** | Cut — research: high demo risk |
| **Click-to-Query** (visual query builder) | **Rejected** | Cut — research: low differentiation |
| **Cascade Vocabulary Fallback** | **Rejected** | Cut — Session 3: confidence already >> threshold |
| **Voice Query Input** | **Rejected** | Cut — mic failure risk |
| **Performance Telemetry** | **Rejected** | Cut — judges don't care |
| **Export Report** | **Rejected** | Cut — no time to download during demo |
| **Next.js 14 frontend** | **Replaced by HTML v2** | Cut in v2.4.1 for demo reliability |

---

## 3-10. Unchanged from v2.2

Sections 3 through 10 (Rule-Based Parser, LLM Stretch Goal, Parser Internals, Spatial Scope, Coverage List, No-Match Diagnosis, Live Ingestion, Open Items) remain **identical** to `03_Architecture_Final_v2.2.md`. No changes needed — the backend architecture is locked and stable.

**Reference:** See `03_Architecture_Final_v2.2.md` for full text of sections 3-10.

---

## 11. Frontend Architecture (v2.4.1 — HTML v2)

### 11.1 Directory Structure
```
fresh_clone/
├── engine/              ← Python backend (locked, no changes)
├── backend/
├── tests/
├── ui/
│   └── gradio_app.py    ← Legacy Gradio UI (retained for debugging)
├── frontend/            ← ★ NEW: HTML v2 frontend
│   ├── index.html       ← Semantic HTML shell, 11 sections
│   ├── styles.css       ← Dark luxury editorial theme + component CSS
│   ├── app.js           ← Vanilla JS: API client, DOM interaction,
│   │                      canvas particles, drag-drop upload, polling,
│   │                      score bars, 6s clip playback, history, presets
│   ├── bridge_server.py ← FastAPI middleware (port 8000)
│   └── README.md        ← Setup instructions
├── start_dev.py         ← Cross-platform launcher (Bridge + static server)
└── start_dev.bat / .sh  ← Platform wrappers
```

### 11.2 Data Flow
```
User → Browser (index.html + app.js) → Static Server (port 3000)
                                          │
                                          ↓
                              FastAPI Bridge (port 8000)
                                          │
                        ┌─────────────────┴─────────────────┐
                        ↓                                   ↓
                 Auto-discovery: find engine/          MOCK mode
                        ↓                                   │
                 Real Backend (Python) → Qdrant → Results  │
                        ↓                                   │
                 Score Breakdown computed                   │
                        ↓                                   │
                 JSON response → Frontend renders           │
                        │                                   │
                 /video/{filename} ← FileResponse           │
                        │                                   │
                 Video player loads & seeks                 │
```

### 11.3 Mock Fallback
If bridge cannot find the backend:
- Serves synthetic data for all endpoints
- Frontend still renders correctly
- Allows UI development without GPU backend

### 11.4 Design Tokens
| Token | Value | Usage |
|---|---|---|
| `--bg` | `#000000` | Page background |
| `--text-primary` | `#f5f3ef` | Headlines, body |
| `--text-muted` | `#8a8275` | Secondary text |
| `--text-dim` | `#5a544d` | Tertiary text, labels |
| `--accent` | `#c4b8a5` | Buttons, highlights, filled score bars |
| `--border` | `rgba(255,255,255,0.05)` | Dividers, card borders |
| `--font-headline` | `Playfair Display` | Hero, section titles |
| `--font-body` | `Inter` | Paragraphs, descriptions |
| `--font-mono` | `JetBrains Mono` | Logs, scores, timestamps |

### 11.5 Bridge API Endpoints (v2.4.1)

| Endpoint | Method | Description |
|---|---|---|
| `/health` | GET | Returns `{status: "ok", mode: "connected" \| "mock"}` |
| `/scenarios` | GET | Returns 5 investigation presets |
| `/query` | POST | Accepts query string + collection, returns results with score_breakdown + diagnosis |
| `/vocab/check` | POST | Accepts query text, returns OOV warnings with quality-gated suggestions |
| `/ingest/start` | POST | Accepts `UploadFile` multipart, saves temp, spawns LiveIngestor thread |
| `/ingest/status/{job_id}` | GET | Returns job state: phase, progress_pct, message, stats, top_classes, elapsed_seconds, collection_name |
| `/video/{filename:path}` | GET | Searches multiple dirs for video file, returns `FileResponse` with MIME detection |

### 11.6 Video Serving Architecture
The `/video/{filename}` endpoint resolves the video file through a
priority search order:
1. Active ingestion job's stored temp path (exact basename or stem match)
2. `BACKEND_PATH/temp_frames/`
3. `BACKEND_PATH/`
4. `BACKEND_PATH/outputs/`
5. `tempfile.gettempdir()`
6. `VIDEO_SEARCH_PATHS` environment variable paths
7. Stem-only scan of all above directories (handles video_id without extension)

MIME types are detected via a hardcoded map for `.mp4`, `.mov`, `.avi`,
`.mkv`, `.webm`, `.m4v`, `.wmv`, `.flv`.

### 11.7 Ingestion State Machine
```
[queued] → [scene_detection] → [extraction] → [detection]
     → [color] → [spatial] → [indexing] → [complete]
```
Each phase yields:
- `progress_pct`: 0–100 (asymptotic formula from live_ingestor)
- `message`: human-readable log line
- `stats`: frame counts, object counts, collection name (on complete)
- `top_classes`: top-10 detected classes with counts (on complete, v2.4.1)
- `elapsed_seconds`: live timer since upload start (v2.4.1)

### 11.8 6-Second Clip Playback Flow
1. User clicks result card → `playResult(idx)` called
2. `clipStart = max(0, result.timestamp - 3)`
3. `clipEnd = result.timestamp + 3`
4. `video.src = /video/{result.video_id}`
5. On `loadedmetadata`: `video.currentTime = clipStart`, `video.play()`
6. `timeupdate` listener: if `currentTime >= clipEnd`, `video.pause()`
7. UI shows "6s Clip" badge, clip info (`"10.0s (−3s to +3s)"`), and
   "▶ Play Clip" button that re-seeks to `clipStart` and plays.
8. Result jump list below player lists all matches; clicking any item
   triggers the same 6-second playback for that result.

---

## 12. Parser Preprocessing Layer (v2.4.1 — NEW)

Before spaCy dependency parsing, the query string passes through a
lightweight pre-processing layer:

### 12.1 Negation Normalization
```python
# "person with no helmet" → "person without helmet"
# "person having no helmet" → "person without helmet"
# "person wearing no helmet" → "person without helmet"
replacements = [
    (r'\bwith no\b', 'without'),
    (r'\bhaving no\b', 'without'),
    (r'\bwearing no\b', 'without'),
]
```

### 12.2 Color+Object Compound Splitting
```python
# "redshirt" → "red shirt"
# "bluecar" → "blue car"
# "blackjacket" → "black jacket"
# Only splits when the color substring is in COLOR_VOCAB
# and the remainder is a known object class
```

### 12.3 Synonym Expansion
```python
SYNONYM_MAP.update({
    "woman": "person",
    "man": "person",
    "lady": "person",
    "gentleman": "person",
})
```

### 12.4 Vocabulary Suggestion Quality Gate
```python
# difflib.get_close_matches returns candidates
# Filter: SequenceMatcher(token, suggestion).ratio() >= 0.70
# Rejects: "kurta" → "curtain" (ratio ~0.33)
# Accepts: "backpak" → "backpack" (ratio ~0.86)
# Accepts: "helmmet" → "helmet" (ratio ~0.86)
```

**Location:** `backend/query/query_parser.py` (preprocessing) +
`backend/vision/vocabulary.py` (synonyms) +
`frontend/bridge_server.py` (vocab suggestion gate)

---

## 13. What This Document Still Leaves Open

The exact tokenization/normalization details (casing, punctuation handling)
and the precise synonym lookup table contents are left to the implementing
team to finalize during the stress-test week — the structural approach
above is fixed; the exact word lists are expected to grow through testing.

The Query History Panel, Vocabulary Coverage Indicator, and their exact
HTML/CSS styling and placement within the layout are left to the
implementing team.

---

## 14. Git State (Verified 2026-08-04)

```
Repository:  https://github.com/bhumeshtiruveedhula1/Ask-N-Seek
Branch:      integration/part3 (primary)
Commit:      37a4fa3
Message:     chore(frontend): remove tracked Next.js source files
Tests:       103/103 passing
Frontend:    HTML v2 + FastAPI bridge, 5 files in fresh_clone/frontend/
Status:      Local and remote in sync ✅
```
