# ASK-N-SEEK — QUICK START CARD (For Next AI)
## One-page cheat sheet. Read this first, then the full Master_Handoff_Report_v2.4.2.
## v2.4.2 update: Frontend rebuilt after corruption. stable_merge @ 20a8744.

---

## Pull & Run (30 seconds)

```bash
git clone https://github.com/bhumeshtiruveedhula1/Ask-N-Seek.git
cd Ask-N-Seek
git checkout stable_merge    # commit 20a8744 (latest)
pip install -r requirements.txt
python -m spacy download en_core_web_sm
python start_dev.py
# Opens: Bridge on http://localhost:8000, Frontend on http://localhost:3000/index.html
```

**No npm install. No Node.js. No build step.** The frontend is pure HTML/CSS/JS.

---

## What Works Right Now

| Feature | Status | How to Test |
|---|---|---|
| Live video ingestion | ✅ Real | Drop MP4 in upload zone, wait ~30–45s, see real progress |
| Object detection | ✅ | YOLO-World-M, 800+ classes |
| Color extraction | ✅ | Center-weighted crop + k-means |
| Spatial relations | ✅ | Left/right only |
| Query parsing | ✅ | spaCy dependency + preprocessing |
| Structured search | ✅ | Qdrant payload filters |
| No-Match Diagnosis | ✅ | Query "purple elephant" |
| Query History | ✅ | Sidebar shows all queries |
| Vocab Indicator | ✅ | Query "motercycle" (typo) — quality-gated suggestions |
| Video seek | ✅ | Click result card → 6-second clip (t-3 to t+3) |
| Threshold | ✅ | 0.3197 (hardcoded) |
| Query Caching | ✅ | Re-run same query → instant |
| Smart Result Scoring | ✅ | 4-bar breakdown per result card |
| Score Bar Micro-Labels | ✅ | "No color constraint" / "Not detected" labels |
| Scenario Presets | ✅ | 5 one-click buttons (context-aware: dimmed if class not detected) |
| Quick Search Chips | ✅ | Pill chips for top 5 detected classes |
| Top-10 Objects Grid | ✅ | Shows after ingestion (e.g., "person · 147") |
| Ingestion Stats Grid | ✅ | Scenes / Keyframes / Objects counts post-ingestion |
| Elapsed Timer + Percentage | ✅ | Live MM:SS timer + large % during ingestion |
| Bright Terminal Logs | ✅ | Full-color hex + glow text-shadow |
| HTML v2 Frontend | ✅ | Zero build, sondaven aesthetic, 11 sections |
| FastAPI Bridge | ✅ | Real ingestion thread, video serving, auto-discovery |

---

## The Corruption Incident (What Not To Do)

Previous AI used Python scripts to inject code into `app.js` using regex replacements.
On Windows CRLF files, `\n` in Python strings became real newlines in JS.
This broke string literals and regex patterns → `SyntaxError` at line 394.

**The fix:** Nuclear reset to clean `ask-n-seek-frontend-v2/` foundation, then clean
rebuild of all three frontend files (`app.js`, `index.html`, `styles.css`) in one shot.
No injection scripts. No regex patches. Complete file writes only.

**Never use Python regex injection on JS files again.**

---

## Locked Decisions (Do Not Change)

- YOLO-World-M (50MB) — **do not swap models**
- Rule-based parser — **do not add LLM**
- Qdrant payload filters — **no embedding fallback**
- Threshold 0.3197 — **do not recalibrate**
- Left/right spatial only
- Architecture doc is law: `03_Architecture_Final_v2.4.1.md`
- **HTML v2 frontend is locked** — do not revert to Next.js or Gradio for demo

---

## Next Priority

**REHEARSAL** — Run the 60-second flow 5 times with different videos.

The backend is done. The frontend is done. The win is in presentation now.

---

## Test Command

```bash
python -m pytest tests/ -q --tb=short
# Expected: 103 passed, 2 warnings
```

## Edge Case Validator

```bash
python edge_case_validator_kimi.py
# Expected: 7/7 PASS
```

## Bridge Verification

```bash
cd fresh_clone/frontend
python bridge_server.py
# In another terminal:
curl http://localhost:8000/health
# Expected: {"status":"ok","backend_mode":"connected"}
curl http://localhost:8000/scenarios
# Expected: 5 scenarios with correct labels and queries
```

## Frontend Syntax Check

```bash
cd fresh_clone/frontend
node --check app.js
# Expected: No output (exit code 0)
```

---

*"Type what happened, we'll show you exactly where — and prove it."*
