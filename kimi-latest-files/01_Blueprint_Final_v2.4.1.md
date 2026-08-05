# BLUEPRINT — Natural-Language Video Retrieval (Hybrid Plan, LOCKED v2.4.1)
### Base: Team Aadhavaan v3 (grounded detection + structured filtering)
### Validated via two independent adversarial passes (Gemini + Perplexity)
### v2 change: local LLM demoted to last-priority stretch goal; rule-based
###   query parser is primary, required component.
### v2.2 change: No-Match Diagnosis built and stable; performance fixes applied;
###   three upgrades approved for build (Live Ingestion, Query History, Vocab
###   Indicator); Parse Lens and Click-to-Query explicitly cut per research.
### v2.3 change: Demo hardening — 7 commits fixing all demo-breaking bugs.
### v2.4 change: Frontend integration — Next.js 14, Smart Result Scoring,
###   Scenario Presets, Query Caching. System complete. Demo-ready.
### v2.4.1 change: Frontend pivoted from Next.js to HTML/CSS/JS v2 (sondaven
###   aesthetic) for zero-build demo reliability. Real ingestion wired in bridge.
###   Parser robustness, 6s clip playback, context-aware presets, top-10 objects,
###   elapsed timer, score bar micro-labels. 103/103 tests passing.

## What we're building
A system where a user types a plain-language description of an event —
including compositional, negated, counting, or left/right spatial details
("a person without a helmet, to the left of the white car") — and gets
back the exact timestamped clip(s) from recorded video, with a visible,
provable reason for every match, across a corpus of multiple video files
at once.

## What changed in v2.4.1 (and why)

**Frontend pivot: Next.js 14 → HTML/CSS/JS v2.**
The Next.js frontend (built in Session 3) was presentation-complete but its
FastAPI Bridge `/ingest/start` endpoint was stubbed — it returned a static
JSON job ID without ever calling `LiveIngestor`. The Next.js `useIngestion`
hook faked progress with a client-side `setInterval` loop. For hackathon
demo reliability, we pivoted to a zero-build HTML/CSS/JS frontend
(`ask-n-seek-frontend-v2`, sondaven.com aesthetic) with a Python FastAPI
bridge (`frontend/bridge_server.py`) that runs `LiveIngestor` in a real
background thread. No Node.js, no npm install, no build step. Opens in
any browser instantly.

**Built and stable: Real ingestion in HTML frontend.**
`POST /ingest/start` accepts multipart file upload, saves to temp path,
spawns `threading.Thread` running `LiveIngestor.ingest()`, polls real
progress every 800ms. Frontend shows live progress bar, elapsed timer,
percentage, phase labels, and terminal-style logs.

**Built and stable: Top-10 Detected Objects grid.**
After ingestion completes, the frontend renders a compact grid of the
most frequently detected classes (e.g., "person · 147", "car · 23").
This immediately proves to the judge that the system understood their video.

**Built and stable: 6-Second Clip Playback.**
Clicking a result card seeks the video player to `timestamp - 3` seconds
and auto-pauses at `timestamp + 3` seconds. A "▶ Play Clip" button
re-seeks to the same window. The judge sees exactly the moment, not
the full video.

**Built and stable: Context-Aware Scenario Presets.**
The 5 formal scenario preset buttons are now dimmed (25% opacity) when
the uploaded video does not contain the classes required for that preset.
Relevant presets show a green "Detected" badge. Hovering reveals a tooltip
with detected counts (e.g., "person: 147 detected / helmet: not detected").

**Built and stable: Quick Search Chips.**
Below the formal presets, pill-shaped chips for the top 5 detected classes
allow one-click search without typing.

**Built and stable: Score Bar Micro-Labels.**
When a query does not include a color, spatial, or negation constraint,
the corresponding score bar shows "No [X] constraint" instead of a
bare "0/20". When the constraint is present but unsatisfied, it shows
"Not detected". This prevents judges from thinking the system is broken.

**Built and stable: Brighter Terminal Logs + Elapsed Timer.**
Ingestion logs use full-brightness hex colors with subtle glow text-shadow.
A live elapsed timer (MM:SS) and large percentage number render next to
the progress bar.

**Built and stable: Parser Robustness Improvements.**
- Pre-processing normalizes "with no" / "having no" / "wearing no" → "without"
- Color+object compounds are split before spaCy sees them: "redshirt" → "red shirt"
- Synonym map expanded: woman, man, lady, gentleman → "person"
- Vocabulary suggestion quality gate: `SequenceMatcher.ratio >= 0.70` rejects
  false suggestions like "kurta → curtain" and "giving → railing"

## Base architecture
Grounded object/attribute detection (YOLO-World, fixed vocabulary) +
structured database filtering (Qdrant) — not embedding similarity. This
is what lets the system answer negation, counting, and spatial queries
*correctly*, by construction, instead of guessing.

## Build priority order (revised v2.4.1)
1. ✅ Ingestion — PySceneDetect + keyframe extraction. (DONE)
2. ✅ Vision pipeline — YOLO-World detection, CIELAB color, left/right
   spatial relations, Qdrant structured storage. (DONE)
3. ✅ Rule-based query parser (required) — pattern-matches negation,
   counting, spatial, and compositional phrasing. (DONE)
4. ✅ Templated explanation generation — fills structured facts into a
   plain-English sentence. (DONE)
5. ✅ Explainability UI — bounding boxes, confidence, live processing log,
   diagnosis. (DONE)
6. ✅ Threshold calibration — 0.3197. (DONE)
7. ✅ Live Judge-Video Ingestion Mode — streaming progress, auto-trigger,
   per-session collection, demo narrator. (DONE)
8. ✅ Query History / Replay Panel — session-level query log, click to
   re-run. (DONE)
9. ✅ Vocabulary Coverage Indicator — proactive OOV suggestion. (DONE)
10. ✅ Smart Result Scoring — 4-bar per-result breakdown. (DONE)
11. ✅ Query Scenario Presets — 5 one-click investigation buttons. (DONE)
12. ✅ Query Result Caching — instant re-runs. (DONE)
13. ✅ HTML/CSS/JS Frontend v2 — sondaven aesthetic, zero build. (DONE)
14. ✅ FastAPI Bridge (frontend/bridge_server.py) — real ingestion thread. (DONE)
15. ✅ 6-Second Clip Playback — t-3 to t+3 auto-seek and pause. (DONE)
16. ✅ Context-Aware Presets + Quick Chips — relevance filtering. (DONE)
17. ✅ Top-10 Objects Grid — post-ingestion summary. (DONE)
18. ✅ Parser Robustness — compounds, synonyms, suggestion quality. (DONE)
19. Audio (Whisper transcript search) — built after the above works.
20. **Local LLM upgrade (stretch goal, last)** — only if time remains.

## Why this wins
Almost every competing team will ship plain visual-similarity search and
hit the well-known "bag of concepts" wall on compositional queries. We
differentiate on:
1. **Grounded, not global** — real detected objects and attributes, not
   a vague "these concepts are somewhere in the frame."
2. **Logically complete on the queries that matter** — negation,
   counting, and left/right spatial are deterministic filters, guaranteed
   correct, not embedding guesses.
3. **Reliable by construction** — the highest-risk component (free-form
   language understanding) is deliberately kept off the critical path.
4. **Visibly honest** — every result shows its evidence; the system says
   "no confident match" with a full constraint breakdown AND 4-bar score
   breakdown instead of forcing a wrong answer.
5. **Unscripted proof** — the judge can drop their own video and watch it
   being dissected live. No cherry-picking possible.
6. **Professional presentation** — dark luxury editorial frontend
   looks like a product, not a hackathon project. **Zero build step**
   means it works on any machine, any browser, instantly.
7. **Effortless demo flow** — Scenario Presets let the judge click once
   and see results. Context-aware dimming proves the system understands
   what is actually in their video.
8. **Exact moment playback** — 6-second clip playback shows the judge
   precisely where the match occurred, not a vague timestamp.

## One-line pitch
*"Type what happened. We'll show you exactly where — and prove it."*

## Upgraded pitch
*"Give us any video. We'll ingest it live, show you how we understood
your question with colored score bars, play the exact 6-second clip
where it happened, and if nothing matches, we'll tell you precisely why."*
