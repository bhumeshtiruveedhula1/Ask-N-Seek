# PRODUCT REQUIREMENTS DOCUMENT — Hybrid Plan, LOCKED v2.4.1
### Base: Team Aadhavaan v3 | Validated via two independent adversarial
### passes (Gemini + Perplexity) | Rule-based parser is primary;
### local LLM demoted to last-priority stretch goal; embedding
### fallback removed entirely.
### v2.2: No-Match Diagnosis built; performance fixes applied;
###   Live Ingestion, Query History, Vocab Indicator approved;
###   Parse Lens and Click-to-Query explicitly rejected.
### v2.3: Demo hardening — 7 commits, all bugs fixed.
### v2.4: Frontend integration — Next.js 14, Smart Result Scoring,
###   Scenario Presets, Query Caching.
### v2.4.1: Frontend pivoted to HTML/CSS/JS v2 for zero-build reliability.
###   Real ingestion wired in bridge. Parser robustness, 6s clip playback,
###   context-aware presets, quick chips, top-10 objects, elapsed timer,
###   score bar micro-labels. 103/103 tests passing.

---

## 1. Problem Statement

Given recorded video footage, build a natural-language frontend that lets
a user describe an event or scene in plain language and retrieve the
exact matching video segment(s) — including compositional, negated,
counting, and left/right spatial queries — without relying on manual
tagging, and without depending on an external API or an unreliable AI
model on the critical path.

## 2. Users & Use Cases

| User | Use case |
|---|---|
| Security/surveillance reviewer | "Show me every clip where someone enters through the back door without a badge visible." |
| Campus safety officer | "Find the moment more than two people were visible in the parking lot." |
| Media/archive researcher | "Find where the speaker mentions 'budget cuts.'" (audio, built after core visual pipeline) |
| Hackathon judge (live demo) | Uploads their own unseen clip, asks an adversarial compositional/negation/spatial query, expects a correct, explained answer within seconds. |

## 3. Core Functional Requirements

### FR1 — Ingestion
- Accept one or more video files (upload, or a live judge-provided clip).
- PySceneDetect for scene-boundary timestamps, seek-based keyframe
  extraction (timestamp-then-seek pattern — never hold the full decoded
  frame sequence in memory).
- **Performance guardrails (v2.2):** PySceneDetect runs with
  `downscale_factor=2`. Extracted frames are resized to max 720p height.
  Input videos exceeding 3 minutes are auto-trimmed with a logged warning.

### FR2 — Visual Understanding
- Object/person/attribute detection via YOLO-World against the fixed
  vocabulary.
- Color via center-weighted crop → k-means → nearest CIELAB name.
  **Performance guardrail (v2.2):** center-weighted crop is downsampled
  to 32×32 pixels before k-means. `max_iter=5`, `attempts=1`.
- Left/right spatial relations only, top-4-confidence pairs per frame.
- Above/inside/behind and entering/leaving: out of scope.

### FR3 — Query Understanding
- Accept natural language queries, including:
  - Compositional queries ("person in red shirt near a blue car")
  - Negation ("without a helmet," "no bag", "with no helmet", "having no helmet")
  - Counting ("more than two people," "exactly one car")
  - Left/right spatial relations
  - Temporal reasoning (before/after only)
  - Code-mixed / Hinglish queries (best-effort)
- **Primary, required parser: rule-based / dependency-parse-based
  attribute binding — not flat keyword extraction.**
- **Pre-processing layer (v2.4.1):**
  - Normalize "with no" / "having no" / "wearing no" → "without"
  - Split color+object compounds: "redshirt" → "red shirt", "bluecar" → "blue car"
  - Synonym expansion: woman, man, lady, gentleman → "person"
- **Known accepted ceiling (v2.2):** The parser handles straightforward
  negation via surface phrase matching + proximity heuristics.
  Complex conjunctions may bind negation incorrectly. Accepted boundary.
- **Spatial scope, locked:** only "left of" / "right of" phrasing is
  recognized. "Near," "close to," "beside," and "next to" are explicitly
  NOT parser trigger phrases.
- Curated synonym lookup table maps common terms onto the fixed
  vocabulary.
- **Coverage & testing requirement:** a minimum enumerated pattern list
  and a 50-80 query stress test — see Architecture.md §7.
- **Vocabulary suggestion quality gate (v2.4.1):** Suggestions must pass
  `SequenceMatcher.ratio >= 0.70` to prevent false matches like
  "kurta → curtain" or "giving → railing".
- **Stretch goal, built last, optional: local LLM parser** (Qwen2.5-7B-
  Instruct, structured output via vLLM + xgrammar backend, flattened schema,
  reasoning-first field) — only after everything else is proven stable.
  Does not change anything downstream if added later.

### FR4 — Retrieval (Primary and Only Path — Structured)
- Query → structured Qdrant filter → payload-filtered search →
  confidence-weighted rerank → grouped by source video.
- **No embedding-based fallback search.**
- **Performance guardrail (v2.2):** Qdrant collections must have
  explicit `keyword` payload indexes on `class_name`, `color`, and
  `spatial_relations`.

### FR5 — Explainability (demo-critical)
- Every returned result must show: bounding box(es), confidence scores,
  and a short natural-language explanation.
- **Primary, required: templated explanation generation.**
- **Required (v2.2): No-Match Diagnosis.**
- **Required (v2.4): Smart Result Scoring.** Every result must show a
  4-bar score breakdown: Object (0-40), Color (0-20), Spatial (0-20),
  Negation (0-20), Total (0-100). This visually proves structured
  search vs embedding black box.
- **Required (v2.4.1): Score Bar Micro-Labels.** When a query does not
  include a constraint (e.g., no color specified), the bar shows
  "No color constraint" instead of bare "0/20". When the constraint is
  present but unsatisfied, shows "Not detected".
- A live, scrolling processing log should visualize each pipeline step.
- **Required (v2.4.1): Brighter terminal-style logs** with full-opacity
  color coding and subtle glow for visibility in dark demo rooms.

### FR6 — Graceful Failure
- If no confident match exists, the system says so explicitly.
- Threshold calibrated empirically: **0.3197** (margin = 0.05,
  max near-miss = 0.2697, min valid = 0.3263).

### FR7 — Multi-Video Corpus Support
- Results must be diverse across source files.
- **Session isolation (v2.2):** Judge-uploaded videos into per-session
  collections (`judge_session_<uuid>`).

### FR8 — Live/Unseen Demo Support
- The system must support ingesting and querying a video the judges
  themselves provide, on the spot.
- **Live Ingestion Mode (v2.2 upgrade):** Auto-trigger ingestion with
  streaming progress log. Estimated latency: 20-40s for 3-min 720p.
- **Required (v2.4.1): Real ingestion in HTML frontend.** The bridge
  must instantiate `LiveIngestor` in a background thread and stream
  real progress. No mock timers.

### FR9 — Audio Understanding (built after core visual pipeline)
- Whisper-small transcript search. Not core MVP.

### FR10 — Query History Panel (v2.2 upgrade)
- Visible session panel logging every query, parsed filter, result count.
- Each entry clickable to re-run.

### FR11 — Vocabulary Coverage Indicator (v2.2 upgrade)
- Proactive "Did you mean?" when judge types OOV term.
- **Required (v2.4.1): Quality-gated suggestions.** False suggestions
  (e.g., "kurta → curtain") are worse than no suggestion. Use
  `SequenceMatcher.ratio >= 0.70` as acceptance gate.

### FR12 — Smart Result Scoring (v2.4 upgrade)
- Every result shows a 4-bar score breakdown proving structured search.
- Object (0-40), Color (0-20), Spatial (0-20), Negation (0-20).
- Total 0-100. Rendered as colored progress bars in result cards.

### FR13 — Query Scenario Presets (v2.4 upgrade)
- 5 one-click investigation scenario buttons.
- Pre-fill query box and auto-submit.
- Safety Violation, Traffic Incident, Lost Item, Access Control, Crowd Check.
- **Required (v2.4.1): Context-aware relevance.** Presets are dimmed
  when the uploaded video does not contain the required classes.
  Relevant presets show a "Detected" badge. Hover tooltip shows counts.
- **Required (v2.4.1): Quick Search Chips.** Pill-shaped chips for the
  top 5 detected classes allow one-click search without typing.

### FR14 — Query Result Caching (v2.4 upgrade)
- In-memory cache for query results. Instant re-runs.
- Auto-clear on new video ingestion.

### FR15 — HTML/CSS/JS Frontend v2 (v2.4.1 upgrade)
- Modern web frontend replacing Gradio for demo purposes.
- **Zero build step.** Pure HTML5, CSS3, Vanilla JS. No Node.js, no npm,
  no build pipeline. Opens in any browser instantly.
- Dark luxury editorial theme (black #000000, cream #f5f3ef, sand #c4b8a5).
- 11 sections including interactive demo workbench.
- FastAPI bridge (`frontend/bridge_server.py`) auto-connects to
  Python backend. Runs on port 8000.
- Static file server (`python -m http.server 3000`) serves the frontend.
- Cross-platform launcher (`start_dev.py`) opens both services.

### FR16 — 6-Second Clip Playback (v2.4.1 upgrade)
- Clicking a result card seeks the video player to `timestamp - 3`
  seconds and auto-pauses at `timestamp + 3` seconds.
- A "▶ Play Clip" button re-seeks to the same window.
- A styled result jump list below the player lists all matches with
  timestamps. Clicking any item plays that 6-second clip.

### FR17 — Top-10 Detected Objects Grid (v2.4.1 upgrade)
- After ingestion completes, render a compact grid of the most
  frequently detected classes with counts (e.g., "person · 147").
- Proves to the judge that the system understood their video.

### FR18 — Ingestion Visual Polish (v2.4.1 upgrade)
- Live elapsed timer (MM:SS) and large percentage number next to
  the progress bar.
- Phase labels (Scene Detection, Keyframes, YOLO, Color, Spatial,
  Qdrant Indexing, Complete) with active-state highlighting.
- Collection badge with glowing green ready dot and gold left border.

## 4. Non-Functional Requirements

| Requirement | Target |
|---|---|
| Hardware | Primary: RTX 4060 (8GB), 16GB RAM. Backup: RX 6700S — YOLO-World NOT on AMD unless ROCm verified. |
| Query latency (core system, no LLM) | Sub-second — rule-based parsing + Qdrant payload-filter search. |
| Ingestion latency (3-min 720p, RTX 4060) | 20-40 seconds end-to-end. |
| Query latency (if LLM stretch goal) | 8-11 seconds per round-trip. |
| Reliability | No crashes on adversarial/edge-case queries; graceful "no confident match" with diagnosis. |
| Internet dependency | **None, at any point.** |
| Explainability | Every result visually justified — boxes, scores, explanation, diagnosis, **score bars**, **6s clip playback**. |
| Demo safety | Hard caps: max video duration 180s, max frame height 720px. |
| Frontend | **HTML/CSS/JS v2, zero build step.** TypeScript not required. Mock fallback works offline. |
| Browser compatibility | Chrome, Edge, Firefox, Safari — any modern browser. |

## 5. Explicitly Out of Scope / Rejected Scope

- Real-time live camera stream ingestion
- Multi-language support beyond English + best-effort Hinglish
- Fine-tuning any model on custom data
- Persistent multi-object tracking / re-identification
- Above/inside/behind spatial relations
- **Embedding-based fallback search (SigLIP2 + FAISS)** — rejected.
- **Local LLM as required component** — rejected as primary.
- **Parse Lens** — rejected.
- **Click-to-Query** — rejected.
- **Cascade Vocabulary Fallback** — rejected in Session 3.
- **Voice Query Input** — rejected in Session 3.
- **Performance Telemetry** — rejected in Session 3.
- **Export Report** — rejected in Session 3.
- User accounts, auth, persistence beyond demo session
- Mobile app / non-browser frontend
- **Next.js 14 frontend** — replaced by HTML v2 in v2.4.1 for demo reliability.

## 6. Success Criteria

- A judge can upload their own video live and get a correct, explained
  answer to a compositional, negated, counting, or left/right spatial
  query within the first ten seconds of watching.
- The system visibly and correctly says "no confident match" with a
  constraint-by-constraint diagnosis at least once during the demo.
- **No part of the live demo depends on internet access or an external API.**
- **The system shows Smart Result Scoring bars on every result,** proving
  structured search vs embedding black box.
- **The demo includes at least one Scenario Preset click** showing
  effortless one-click investigation.
- **The demo includes at least one 6-second clip playback** showing the
  exact moment of the match.
- The demo survives a fresh clone / fresh environment run.
- The system ingests a judge-provided 3-minute video in under 60 seconds.
- **The frontend opens in any browser with zero build step.**
