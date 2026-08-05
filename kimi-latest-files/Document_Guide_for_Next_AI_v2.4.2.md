# EXISTING DOCUMENTS — WHAT TO USE FOR NEXT AI
## v2.4.2 files are canonical. v2.4.1 and below are OUTDATED for git state.

---

## GIVE THESE TO YOUR FRIEND'S KIMI (In Order)

### 1. NEW — Session 4 Handoff (Download from this chat)
| File | Why | Status |
|---|---|---|
| `Master_Handoff_Report_v2.4.2.md` | Full context of Session 4: corruption incident, clean rebuild, current verified state | ✅ NEW — supersedes v2.4 |
| `Kickoff_Guide_for_Next_AI_v2.4.2.md` | Execution coordinator rules + how to pull from git + verification checklist | ✅ NEW — supersedes v2.4.1 |
| `Quick_Start_Card_v2.4.2.md` | One-page cheat sheet for immediate pull-and-run (updated for stable_merge @ 20a8744) | ✅ NEW — supersedes v2.4.1 |

### 2. CANONICAL — v2.4.1 Documents (Unchanged, Still Valid)
| File | Purpose | Status |
|---|---|---|
| `01_Blueprint_Final_v2.4.1.md` | One-page why/what + v2.4.1 wins | ✅ Still valid |
| `02_PRD_Final_v2.4.1.md` | Functional requirements + HTML v2 scope | ✅ Still valid |
| `03_Architecture_Final_v2.4.1.md` | Locked technical decisions + HTML v2 stack | ✅ Still valid |
| `Upgrade_Report_v2.4.md` | Why upgrades were chosen + what was built in Sessions 1-3 | ✅ Unchanged (historical) |
| `Team_Explanation_v2.4.md` | Plain-language brief for team | ✅ Unchanged (core still valid) |
| `Detection_Engine_Decision_Record_v2.4.md` | Cascade research + skip decision + frontend pivot | ✅ Unchanged (decisions still locked) |

### 3. DO NOT GIVE (Outdated)
| File | Why | Status |
|---|---|---|
| `Master_Handoff_Report_v2.4.md` | Missing corruption incident and rebuild details | ❌ Outdated |
| `Master_Handoff_Report_v2.4.1.md` | Did not exist (v2.4.1 was docs only, no handoff update) | ❌ N/A |
| `Quick_Start_Card_v2.4.1.md` | References old commit 29ceb5e, missing rebuild info | ❌ Outdated |
| `Document_Guide_for_Next_AI_v2.4.1.md` | Points to v2.4.1 as canonical | ❌ Outdated |
| `Kickoff_Guide_for_Next_AI.md` (old) | Missing git state, corruption context, verification checklist | ❌ Outdated |
| Any v2.3 or below files | Superseded | ❌ Outdated |

---

## TOTAL PACKAGE FOR NEXT AI

**Minimum viable handoff:**
1. `Master_Handoff_Report_v2.4.2.md` (current state + corruption context)
2. `Kickoff_Guide_for_Next_AI_v2.4.2.md` (execution rules + git commands)
3. `Quick_Start_Card_v2.4.2.md` (immediate pull-and-run)
4. `01_Blueprint_Final_v2.4.1.md` (what we built and why it wins)
5. `03_Architecture_Final_v2.4.1.md` (locked decisions)
6. Git repo URL + branch: `https://github.com/bhumeshtiruveedhula1/Ask-N-Seek`, branch `stable_merge`

**Full handoff (recommended):**
All 3 v2.4.2 docs + 6 v2.4.1 docs + git repo access.

---

## GIT STATE (Verified 2026-08-04)

```
Repository:  https://github.com/bhumeshtiruveedhula1/Ask-N-Seek
Branch:      stable_merge (primary)
Commit:      20a8744
Message:     feat(frontend): rebuild HTML v2 with Prompts 1-5 features
Tests:       103/103 passing
Frontend:    HTML v2 + FastAPI bridge, 5 files in fresh_clone/frontend/
             (index.html, app.js, styles.css, bridge_server.py, README.md)
Status:      Local and remote in sync ✅
```

---

## WHAT THE NEXT AI SHOULD KNOW FIRST

1. **Pull `stable_merge`** — this is the primary branch with all v2.4.2 work
2. **Run `python start_dev.py`** — opens Bridge (port 8000) + static server (port 3000)
3. **Frontend is HTML v2, NOT Next.js** — `fresh_clone/frontend/`, zero build step
4. **Do not change architecture** — all backend decisions locked in v2.2 docs, frontend stack locked in v2.4.1
5. **Backend is DONE** — 103/103 tests, no more backend work
6. **Frontend was corrupted and rebuilt** — the rebuild is clean, all features present
7. **Next priority is REHEARSAL** — not building, not UI, not features
