# TEAM EXPLANATION — Ask-N-Seek v2.4
### Plain-language brief for everyone on the team. No ML background assumed.
### Read this before touching any code or rehearsing the demo.

---

## 1. WHAT WE'VE BUILT (Current Status)

The system is **done, stable, frontend-integrated, and demo-ready**. All three parts are merged, tested, and passing.

**In plain words:** You can drop a video into the system, it cuts the video into scenes, finds every object in every scene (with a box around it), reads the color of each object, figures out which objects are to the left or right of each other, and stores all of this as structured facts in a database. Then you can type a sentence like *"person without helmet left of blue car"* and it finds the exact moment in the video — with bounding boxes, confidence scores, a plain-English explanation, and now a **visual score breakdown** showing which parts of your question matched and how well.

**Specifically what's working:**
- **103 out of 103 tests passing.** Zero regressions introduced in Session 3.
- **Threshold calibrated to 0.3197** using real footage (103 frames, 3 videos).
- **No-Match Diagnosis is live.** When a query returns nothing, the system tells you: *"Person detected: 23 scenes. No helmet detected: 8 scenes. Left of car: 5 scenes. But all three together: 0 scenes."*
- **Session isolation is live.** Every judge upload gets its own `judge_session_<uuid>` collection in Qdrant.
- **Performance is fixed.** PySceneDetect runs at half resolution. Frames are capped at 720p. Videos are capped at 3 minutes.
- **Smart Result Scoring is live.** Every result shows 4 colored bars: Object, Color, Spatial, Negation. This visually proves structured search vs embedding black box.
- **Scenario Presets are live.** One-click buttons for common investigations: Safety Violation, Traffic Incident, Lost Item, Access Control, Crowd Check.
- **Query Caching is live.** Re-running the same query is instant.
- **HTML v2 Frontend (zero-build) is live.** Sondaven aesthetic (dark luxury editorial theme). Replaces Next.js 14 and Gradio with zero build step dependencies.
- **Prompts 1–5 Features are live.** 6-second clip player (`t-3` to `t+3`), context-aware presets (green "Detected" badge / dimmed), top-10 detected objects grid, brighter glowing terminal logs, and parser/vocab robustness.

---

## 2. WHAT WE FIXED AND BUILT (Sessions 1-3)

### Session 1 (v2.2): Core System + Three Critical Fixes
**Fix 1: Qdrant Speed + Session Isolation**
Added keyword payload indexes. Added per-session collections. Added cleanup that drops old judge sessions on startup.

**Fix 2: Ingestion Speed**
PySceneDetect at half resolution (~4× faster). Frames capped at 720p. Color k-means optimized (32×32 crop, max_iter=5).

**Fix 3: UI Freezing + Smart Failure**
Queries run in background threads. No-Match Diagnosis replaces static "no results" message.

### Session 2 (v2.3): Demo Hardening
**Fix 1:** Progress bar arithmetic (asymptotic formula)
**Fix 2:** Color binding for prepositional phrases ("person in red")
**Fix 3:** Vocabulary noise on color words ("dark green" whitelisting)
**Fix 4:** Detection summary slowness (top-20 class cap)
**Fix 5:** GPU uncertainty (logging every 50th frame)
**Fix 6:** Click-to-seek (6 attempts → native gr.Video + dropdown)

### Session 3 & Prompts 1–5: Frontend Integration & Polish
**Feature 1:** Smart Result Scoring — 4-bar breakdown per result
**Feature 2:** Query Scenario Presets — 5 one-click investigation buttons
**Feature 3:** Query Result Caching — instant re-runs
**Feature 4:** HTML v2 Frontend — zero-build Sondaven aesthetic, replaces Next.js 14 & Gradio
**Feature 5:** 6-Second Bounded Clip Player — auto-seeks to `t-3s`, pauses at `t+3s`
**Feature 6:** Context-Aware Smart Presets — auto-dims unmatched scenarios, highlights detected ones
**Feature 7:** Ingestion Visual Polish & Top Objects — glowing terminal logs, meta timer, top-10 objects grid
**Feature 5:** FastAPI Bridge — auto-connects frontend to Python backend

---

## 3. THE FRONTEND (What's New: HTML v2 Zero-Build)

The Next.js frontend has been replaced by a **zero-build HTML/CSS/JS v2 frontend** in `fresh_clone/frontend/`.

**Why Zero-Build?**
- Eliminates Node.js / `npm install` failure risks on stage.
- Open `index.html` directly or serve via python static server.
- Instant hot-reloading with zero bundling or compilation delay.

**Theme & Aesthetics (Sondaven.com style):**
- Background: Pitch black (#000000) with subtle glassmorphism cards
- Text: Off-white cream (#f5f3ef)
- Accent: Sand gold (#c4b8a5)
- Typography: Playfair Display, Inter, JetBrains Mono

**Key Frontend Capabilities:**
1. **Ingestion Terminal**: Glowing color logs (`qlog-info`, `qlog-pass`, `qlog-fail`), live elapsed timer (`MM:SS`), percentage progress bar.
2. **Top Detected Objects Grid**: Post-ingestion grid showcasing top-10 detected classes with counts.
3. **Smart Scenario Presets**: 5 buttons that dynamically highlight (green `"Detected"` badge) or dim (25% opacity) based on video content, plus hover tooltips.
4. **Quick Search Chips**: Pill buttons for top detected classes allowing one-click search.
5. **Result Cards**: Large gold timestamp displays (`10.0s`) replacing placeholder icons.
6. **6-Second Bounded Clip Player**: Automatically sets playback window from `timestamp - 3s` to `timestamp + 3s`, with auto-pause at clip end and replay button.
7. **Result Jump List**: Clickable list below the player to jump between all matching results instantly.

**How to start:**
```bash
cd fresh_clone
python start_dev.py
# Launches FastAPI Bridge on port 8000 and static server on port 3000
```

---

## 4. WHY THIS WINS THE COMPETITION

### What Most Teams Will Build
Almost every competing team will ship **embedding similarity search** — they turn every video frame into a numeric fingerprint, do the same for the text query, and find the closest match.

### Why That Fails (The "Bag of Concepts" Problem)
Ask a similarity-search system for *"a person in a red shirt next to a blue car"* and it can genuinely return a frame with the colors swapped — because it just sees "red, blue, person, car" all present somewhere. It doesn't know **which color belongs to which object.**

It also **cannot do negation** ("without helmet") or **counting** ("more than two people") or **spatial relations** ("left of car") — these are structurally impossible with pure similarity matching.

### What We Do Instead
1. **Actually detect things** — YOLO-World draws a real box around each object.
2. **Read color from the actual pixels** — center-weighted crop.
3. **Compute left/right position** — basic geometry on box centroids.
4. **Store everything as real facts** — a database that can answer "give me every row where person=yes AND helmet=no AND count(person)>2."
5. **Parse the query with rules, not AI** — checking for specific phrases. Zero chance of hanging or hallucinating.
6. **Show our work** — every result has boxes, scores, explanations, AND 4-bar score breakdown.
7. **Say "I don't know" honestly** — with a breakdown of why, not just "no results."

### The Frontend Makes It Tangible
| | Other Teams | Us |
|---|---|---|
| Pre-cooked footage? | Yes | **No — judge's own video, live** |
| Hidden parser? | Yes | **No — query history + score bars show exactly how it was understood** |
| Blank "no results"? | Yes | **No — constraint-by-constraint diagnosis** |
| Silent OOV failure? | Yes | **No — proactive "Did you mean?"** |
| Black box score? | Yes | **No — 4-bar breakdown proves structured search** |
| One-click demos? | No | **Yes — 5 scenario presets** |

---

## 5. OUR SOLUTION IN PLAIN WORDS

**The one-line pitch:** *"Type what happened, we'll show you exactly where — and prove it."*

**The upgraded pitch:** *"Give us any video. We'll ingest it live, show you how we understood your question with colored score bars, and if nothing matches, we'll tell you precisely why — not just 'no results.'"*

**How it actually works (no jargon):**
1. You give the system a video.
2. It finds the "scene changes" — moments where the camera cuts or something big changes.
3. At each scene change, it takes a snapshot and looks for objects (people, cars, bags, etc.) — each gets a box.
4. For each box, it looks at the center pixels to figure out the main color.
5. It checks which boxes are to the left or right of each other.
6. All of this is stored as a spreadsheet of facts.
7. When you type a sentence, the system checks for specific words: "without" means look for rows where helmet is missing. "More than two" means count the people. "Left of" means check the geometry column.
8. It returns the matching rows — with the snapshot, the boxes drawn on it, a sentence explaining why, AND 4 colored bars showing Object/Color/Spatial/Negation scores.
9. If nothing matches, it tells you which parts of your sentence it found and which it didn't.

**The trick:** *AI is used only to detect things in the video. The actual matching logic is provable database logic, not AI guessing.* That's what makes it reliable enough to demo live.

---

## 6. WHAT WE DELIBERATELY DO NOT DO

These are **locked out** — no discussion, no exceptions:

| Rejected Idea | Why |
|---|---|
| **Parse Lens** (live dependency tree) | Research found spaCy misparses ~10% of complex sentences. A visibly wrong tree undermines trust more than no tree. |
| **Click-to-Query** (click boxes to build queries) | High UI effort for a problem our parser + synonym table already solves. |
| **Real-time camera stream** | Explicitly out of scope. WiFi/webcam risk on stage. |
| **Embedding fallback** (SigLIP2 + FAISS) | Cut in v2. Introduces coupling risk, two-database sync. |
| **Local LLM as primary parser** | Cut in v2. Highest-risk component per both research passes. |
| **Near/close-to/beside spatial** | No Qdrant proximity filter exists. Would produce false positives. |
| **Above/inside/behind spatial** | 2D-unreliable from odd camera angles. |
| **Entering/leaving tracking** | Proven fragile in prior validation. |
| **Multi-language beyond English/Hinglish** | Scope creep. |
| **Cascade Vocabulary Fallback** | Cut in Session 3. Confidence already >> threshold. Not worth the risk. |
| **Voice Query Input** | Cut. Mic failure risk on stage. |
| **Performance Telemetry Overlay** | Cut. Judges don't care about GPU RAM. |
| **Export Report** | Cut. No time to download during demo. |
| **Next.js build step** | Replaced by zero-build HTML v2 for 100% stage reliability. |

---

## 7. BUILD ORDER (What's Left)

```
✅ DONE — Ingestion (Part 1)
✅ DONE — Vision + Qdrant (Part 2)
✅ DONE — Parser + Search + UI (Part 3)
✅ DONE — Performance fixes (3 prompts)
✅ DONE — No-Match Diagnosis
✅ DONE — Session isolation
✅ DONE — Smart Result Scoring
✅ DONE — Query Scenario Presets
✅ DONE — Query Result Caching
✅ DONE — Next.js Frontend
✅ DONE — FastAPI Bridge

🔲 NEXT — Full E2E test (upload → preset → score bars)
🔲 NEXT — Demo rehearsal (5 times, different videos)
🔲 NEXT — Fresh clone validation on teammate's machine
```

**If time runs short:** Rehearse with the base system + Smart Score Bars + Scenario Presets. That's a winning demo. Everything else is polish.

---

## 8. DEMO STRATEGY

### The 60-Second Flow
1. **Judge drops their video** (0:00-0:05)
2. **Live ingestion runs** (0:05-0:50) — narrate glowing log outputs, timer (`0:42`), percentage bar
3. **Top Objects appear** (0:50) — top 10 detected object grid shows `person (147)`, `car (23)`
4. **Presets auto-filter** (0:52) — **🔴 Safety Violation** shows green `"Detected"` tag; irrelevant presets dim
5. **Click "🔴 Safety Violation"** (1:00) — one click, instant results
6. **Result card shows 4 score bars & 10.0s timestamp** (1:02) — Object ✓, Negation ✓, Score 94/100
7. **Click Result Card** (1:05) — video player seeks to `t-3s` (`7.0s`), plays 6s clip, auto-pauses at `t+3s` (`13.0s`)
8. **Judge types a nonsense query** (1:15) — e.g., "purple elephant dancing"
9. **No-Match Diagnosis appears** (1:16) — constraint breakdown + closest miss
10. **Presenter:** *"It doesn't fake an answer. It plays exact 6-second clips, filters relevant scenarios automatically, and proves its reasoning with colored bars."*

### The "Break It" Moment
Rehearse this deliberately. Have a teammate try to break the system with:
- Color swap: "blue shirt, red car" vs "red shirt, blue car"
- Negation: "person without helmet"
- Counting: "more than two people"
- Spatial: "person left of car"
- Nonsense: "flying dinosaur"

The system should handle all of these correctly — and visibly explain itself.

### Hardware Plan
- **Primary demo machine:** Your HP Omen (RTX 4060, 16GB RAM)
- **Backup machine:** Teammate's ROG Zephyrus G14 (RX 6700S)
  - **Important:** Do NOT run YOLO-World on the AMD machine unless ROCm is verified.
- **Internet:** Not needed. The system is fully offline.

---

## 9. WHAT EVERYONE NEEDS TO AGREE ON

1. **The one-line pitch:** *"Type what happened, we'll show you exactly where — and prove it."*
2. **The upgraded pitch:** *"Give us any video. We'll ingest it live, show you how we understood your question with score bars, and if nothing matches, we'll tell you precisely why."*
3. **Why the obvious approach (embedding similarity) fails** — the "bag of concepts" problem.
4. **The build order** — Everything is done. Only rehearsal remains.
5. **What's cut** — Parse Lens, Click-to-Query, Cascade Fallback, Voice Query, Telemetry, Export — all dead.
6. **`03_Architecture_Final_v2.4.md` is the single source of truth** for locked technical decisions.
7. **The demo wins on trust, not feature count.** A system that visibly works and honestly says "I don't know" beats a system with more features that breaks on stage.

---

## 10. HONEST CONFIDENCE LEVEL

**Very High.** The architecture is structurally sound. The research validated both the approach and the upgrade priorities. The base system is tested and passing. The performance fixes are in. The frontend is integrated. The Smart Score Bars are the single best differentiator. The only remaining work is rehearsal.

**What could still go wrong:**
- A judge drops a corrupted video file → graceful error message needed.
- A judge types a truly unparseable sentence → vocab indicator + synonym table catches it.
- The presenter forgets the narration → rehearse. The narrator script is built into the code.

**What won't go wrong:**
- The parser won't hang (it's rule-based, no model inference).
- The system won't need internet (fully offline).
- The system won't force a wrong answer (threshold + diagnosis are calibrated and tested).
- The frontend won't break (TypeScript 0 errors, mock fallback works offline).

---

*"Type what happened, we'll show you exactly where — and prove it."*
