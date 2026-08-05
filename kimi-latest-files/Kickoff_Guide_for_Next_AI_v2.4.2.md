# ASK-N-SEEK — KICKOFF GUIDE FOR NEXT AI
## How to Work With This Team + How to Pull and Verify From Git
## Read this FIRST before any document. This is our DNA.

---

## 1. WHO YOU ARE TALKING TO

**The human** is the team lead. He:
- Has impossibly high build velocity — he says this explicitly, believe it
- Does NOT want timelines or time estimates — he ignores them anyway
- Wants you to use your full intelligence — "don't think of going to space in a jet"
- Will tell you what to build, not ask for proposals — your job is execution
- Gets frustrated when you stop mid-task — **complete what you start**
- Uses Antigravity Claude Sonnet 4.6 as the main coding agent — you are the coordinator
- Has a UI/UX teammate handling frontend design — you handle backend logic + API contracts
- Wants to WIN the hackathon — everything serves the demo moment

**Your role:** Execution coordinator + backend architect guardian. NOT a product manager.

---

## 2. HOW TO PULL AND VERIFY THE CODEBASE (Do This First)

### Step 1: Clone and Checkout
```bash
git clone https://github.com/bhumeshtiruveedhula1/Ask-N-Seek.git
cd Ask-N-Seek
git checkout stable_merge
git log --oneline -5
# Expected:
# 308d5fb feat(phase7): typo auto-correction via difflib 0.70 ratio
# b4cdb2f feat(phase6): touching/near spatial relations, wearing->in
# deac856 fix(phase5): class-specific confidence gates, accessory NMS 0.40
# 20a8744 feat(frontend): rebuild HTML v2 with Prompts 1-5 features
# 29ceb5e fix: add core backend files
```

### Step 2: Verify Core Files Exist
```bash
ls config.py requirements.txt start_dev.py
ls tests/
ls frontend/index.html frontend/app.js frontend/styles.css frontend/bridge_server.py
```

### Step 3: Run Backend Tests (MANDATORY)
```bash
python -m pytest tests/ -q --tb=short
# Expected: 103 passed, 2 warnings
```

### Step 4: Verify Frontend Syntax
```bash
cd frontend
node --check app.js
# Expected: No output (exit code 0)
```

### Step 5: Verify Bridge Imports
```bash
python -c "import bridge_server as b; print('Bridge OK'); print('Mode:', 'connected' if not b.MOCK_MODE else 'MOCK')"
# Expected: Bridge OK, Mode: connected
```

### Step 6: Start System (Optional — for browser test)
```bash
cd ..
python start_dev.py
# Opens: Bridge http://localhost:8000, Frontend http://localhost:3000/index.html
```

**If ANY of Steps 3-5 fail → STOP. Report the error to the human immediately.**

---

## 3. HOW WE WORK (Our Rhythm)

### The "Antigravity" Workflow
1. **Human says what he wants** → usually a feature, fix, or question
2. **You read the actual code** — never trust documents alone. Verify with `git log`, `pytest`, `node --check`, raw file inspection
3. **You give honest assessment** — "Build it / Skip it / Build only if time" with evidence
4. **Human decides** → "Go" or "No"
5. **You write a complete prompt for Claude** — zero ambiguity, exact file paths, exact data contracts
6. **Claude builds** — you don't write the code, Claude does
7. **You verify** — pytest, `node --check`, browser test, API test
8. **You report back** — raw numbers, pass/fail, what changed

### Key Rules
- **Evidence over claims** — never say "it will work" without pytest output
- **Scope-locked** — if it's not in the canonical docs, say no
- **Honest confidence** — say when something is risky, proven, or unknown
- **Time-budget everything** — state estimate before building. If 2× over, stop and ask
- **Complete what you start** — the human's #1 frustration is stopping mid-task
- **Token efficiency** — Claude is precious. Don't burn turns on 5-minute tasks
- **NEVER use Python regex injection on JS files** — this caused the v2.4 corruption. Always write complete files.

---

## 4. THE HUMAN'S DECISION STYLE

### He will say things like:
- *"My build velocity is impossibly high"* → Means: don't worry about time, just build it right
- *"Don't think of going to space in a jet"* → Means: use your intelligence but stay grounded
- *"I want to win this hackathon"* → Means: every decision serves the demo moment
- *"Give me your thoughts"* → Means: honest assessment, not a sales pitch
- *"Just tell me yes or no"* → Means: he wants speed, not essays
- *"Complete it properly"* → Means: do NOT stop mid-task, ever

### He will NOT tolerate:
- Stopping mid-task and asking "should I continue?"
- Proposing alternative architectures (YOLO swap, LLM parser, etc.)
- Writing 4-hour plans before a 10-minute spike
- Feature creep — "while we're at it, let's also build..."
- Hiding behind "I think" without evidence
- Using Python scripts to inject code into JS files (caused corruption)

---

## 5. CLAUDE PROMPTING PATTERN

When the human says "give this to Claude," write prompts like this:

```
You are [task].
PROJECT: Ask-N-Seek
BRANCH: stable_merge
LOCKED: [list what NOT to change]

FILES TO READ FIRST:
1. [exact file path] — [why]
2. [exact file path] — [why]

TASK 1: [specific change]
[exact code snippet or contract]

TASK 2: [specific change]
[exact code snippet or contract]

DO NOT:
- [forbidden thing 1]
- [forbidden thing 2]
- Use Python regex injection on JS files
- Write partial file edits — write complete files only

VERIFICATION (MANDATORY):
- node --check app.js
- python -m pytest tests/ -q --tb=short
- [browser/API test if applicable]
```

**Key:** Give Claude exact file paths, exact function signatures, exact data contracts. Zero ambiguity. Claude is smart but not psychic.

**CRITICAL:** After Claude writes any JS file, you MUST run `node --check app.js` before declaring success. The previous AI skipped this and caused the corruption.

---

## 6. VERIFICATION CHECKLIST (Always Run)

After ANY Claude build:
```bash
# Backend tests
python -m pytest tests/ -q --tb=short
# Expected: 103 passed (or current count), 0 regressions

# Frontend syntax check
cd frontend && node --check app.js
# Expected: exit code 0

# Bridge API test
curl http://localhost:8000/health
# Expected: {"status":"ok","backend_mode":"connected"}

curl http://localhost:8000/scenarios
# Expected: JSON with 5 scenarios

# Frontend visual test
# Open http://localhost:3000
# Verify: upload works, presets render, search works, score bars appear
```

**If any check fails:** Paste the error back to Claude with "Fix without changing architecture."

---

## 7. WHAT'S NEXT (T-MINUS-HACKATHON)

### DO NOT BUILD ANYTHING NEW.

The system is structurally complete through Phase 7 (commit 308d5fb).

### What the human probably wants next:
1. **REHEARSAL** — Run the 60-second demo flow 5 times with different videos
2. **Edge case test list** — what to try during rehearsal
3. **Demo day checklist** — hardware, backup plans, error messages
4. **Fresh clone validation** — test on teammate's machine

### What he does NOT want:
- More backend features
- More spatial relations (behind/above/inside — locked out)
- More parser tweaks
- More vocabulary expansion
- Frontend polish beyond what's already there
- Cascade Vocabulary Fallback (rejected)
- Voice Query (rejected)
- Telemetry (rejected)
- Export Report (rejected)

---

## 8. THE ONE THING THAT WINS

**Smart Result Scoring bars + Scenario Presets + Live Ingestion + No-Match Diagnosis + 6s Clip Playback.**

That's the demo. That's the win. Everything else is noise.

The judge drops their video. You click "Safety Violation." Results appear with 4 colored bars proving the system understood their question. Then they type "purple elephant" and get an honest diagnosis.

**That's it. Rehearse that 5 times. Win.**

---

## 9. FILE REFERENCE (What to Read When)

| When human asks... | Read first |
|---|---|
| "What did we build?" | `01_Blueprint_Final_v2.4.1.md` |
| "What's the current state?" | `Master_Handoff_Report_v2.4.2.md` |
| "How do I run this?" | `Quick_Start_Card_v2.4.2.md` |
| "What are the locked decisions?" | `03_Architecture_Final_v2.4.1.md` |
| "What features are done?" | `Upgrade_Report_v2.4.md` |
| "Explain this to my team" | `Team_Explanation_v2.4.md` |
| "What are the requirements?" | `02_PRD_Final_v2.4.1.md` |
| "Why did we skip cascade fallback?" | `Detection_Engine_Decision_Record_v2.4.md` |
| "What docs are outdated?" | `Document_Guide_for_Next_AI_v2.4.2.md` |

---

## 10. FINAL WORD FROM ME TO YOU

I worked with this human through a corruption crisis. Here's what I learned:

**He is sharp.** He catches bullshit instantly. Don't bluff.
**He is fast.** He makes decisions in seconds, not hours. Keep up.
**He is loyal.** If you deliver, he trusts you. If you stop mid-task, he loses faith.
**He wants to win.** Not participate. Not learn. WIN.

The system is built. The code is passing. The frontend is rebuilt and clean.
The differentiation is real. The corruption is fixed.

**Your job now is to protect that win.** No more building. No more features.
Just rehearsal, validation, and making sure nothing breaks before demo day.

Good luck. You've got this.

---

*"Type what happened, we'll show you exactly where — and prove it."*
