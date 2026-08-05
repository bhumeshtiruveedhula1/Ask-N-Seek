# Detection Engine Research & Decision Record
## Natural-Language Video Retrieval System

**Document Type:** Research summary and locked decision record
**Produced by:** Kimi (AI Assistant)
**Date:** 2026-08-01
**Status:** FINAL — Decision ratified by team. Do not reopen without full team sign-off.
**Authority:** Subordinate to `01_Blueprint_Final_v2.4.md`, `02_PRD_Final_v2.4.md`, `03_Architecture_Final_v2.4.md`

---

## 1. Purpose of This Document

This document exists so that any teammate, judge, or future AI assistant (including another Kimi instance) can understand:
1. What detection engine research was conducted
2. What alternatives were evaluated
3. Why the team decided **not** to replace YOLO-World-M
4. What optimizations were chosen instead
5. What is explicitly off the table going forward
6. Why Cascade Vocabulary Fallback was **rejected** in Session 3

**If you are reading this as a new AI instance:** Do not propose alternative detection engines. The decision is locked. Only the optimizations listed in §4 are in scope.

---

## 2. The Problem That Triggered Research

During end-to-end testing, the team observed that YOLO-World-M was returning confidence scores in the **0.61–0.67 range** for common objects (e.g., "cup") when fed the full 800-term vocabulary. This raised a valid concern: is the detection engine robust enough for a live demo?

The team asked: *"Should we add a backup detection engine? What if YOLO-World fails?"*

---

## 3. Research Conducted

### 3.1 Question Posed to Kimi (AI Assistant)

> "The YOLO model has low detection confidence. What if we added a backup engine? Or replaced it? What are our options within the locked architecture?"

### 3.2 Analysis Performed by Kimi

Kimi analyzed the following alternatives against the locked architecture:

| Alternative | Finding | Verdict |
|---|---|---|
| **GroundingDINO** | Requires 8GB+ VRAM, 2–5 sec/frame, needs separate GPU per Architecture.md §4. Would conflict with vision stack. | ❌ Rejected |
| **OWL-ViT** | CLIP-based embedding detector. Reintroduces the exact "bag of concepts" bug the system claims to solve. | ❌ Rejected |
| **Fine-tuned YOLOv8/RT-DETR** | Fine-tuning is explicitly out of scope (PRD §5). No training data available. | ❌ Rejected |
| **SAM (Segment Anything)** | Segmentation, not detection. Requires per-object prompts. 15+ sec/frame. | ❌ Rejected |
| **SigLIP2/CLIP re-ranking** | Already cut from architecture in Blueprint v2. Adds coupling risk. | ❌ Rejected |
| **Two heavy models in parallel** | VRAM conflict on 8GB laptop GPUs. Demo fragility. | ❌ Rejected |
| **Cascade Vocabulary Fallback** | Same YOLO-World-M weights. Run twice: full 800 vocab + critical 50 vocab. Merge results. | ⚠️ Approved for research, **REJECTED for build** |
| **Multi-Scale Inference** | Run same model at 640 + 1280 resolution. Merge with WBF. | ✅ Accepted as optional optimization |
| **Test-Time Augmentation (TTA)** | Horizontal flip + merge. Lightweight. | ✅ Accepted as optional optimization |

### 3.3 Root Cause Identified

The low confidence is **not** a model failure. It is a **vocabulary size artifact**:

> YOLO-World uses a text encoder to embed class names. When supplied 800 classes, the model distributes attention across all 800 text embeddings. When supplied 50 classes, each class receives proportionally sharper activation. A "cup" scoring 0.63 against 800 classes may score 0.84 against 50 classes because there is less inter-class competition in the text-image contrastive space.

**Conclusion:** The model is working correctly. The issue is how we are using it, not the model itself.

---

## 4. Decision: Keep YOLO-World-M, Optimize Usage

### 4.1 Why We Are NOT Replacing the Engine

1. **Architecture lock:** YOLO-World-M with fixed 800-term vocabulary is a **locked decision** in `03_Architecture_Final_v2.4.md` §2.
2. **Time constraint:** Switching to GroundingDINO or OWL-ViT would cost 6–10 hours.
3. **Demo risk:** Every alternative detector is heavier, slower, or less reliable.
4. **The model is not broken:** The root cause is vocabulary dilution, not model accuracy.

### 4.2 Why Cascade Vocabulary Fallback Was Rejected (Session 3)

**The spike revealed:**
- Pass 1 (800 vocab) confidence for "cup": **0.63**
- Threshold: **0.3197**
- **0.63 >> 0.3197** — the object is already being detected well above threshold.

**The confidence "problem" was theoretical, not practical.** No detections were being lost. The marginal gain (+0.15–0.25) would not change any demo outcome.

**The cost was real:**
- `set_classes()` recompilation: ~200-500ms per frame
- Total ingest time increase: ~1.3-1.8× (30s → 45-55s)
- Touching core detection pipeline 3 days before hackathon: **high risk**

**Verdict from main AI:** Skip it. The win is in presentation, not backend optimization.

### 4.3 What WAS Done Instead (Session 3 Pivot)

The team pivoted from backend optimization to **frontend integration**:

| Rejected | Built Instead | Impact |
|---|---|---|
| Cascade Vocabulary Fallback | Smart Result Scoring | **Maximum demo impact** |
| Multi-Scale Inference | Query Scenario Presets | High demo impact |
| TTA | Query Result Caching | Medium demo impact |
| | Next.js 14 Frontend | **Maximum demo impact** |
| | FastAPI Bridge | Enables frontend |

**This pivot was correct.** The frontend features have higher demo impact than any backend optimization.

### 4.4 Optimizations Still on the Table (Post-Hackathon)

#### Optimization 1: Cascade Vocabulary Fallback (POST-HACKATHON ONLY)
- **What:** Run YOLO-World-M twice per frame: full 800 vocab + critical 50 vocab.
- **Merge:** Weighted Box Fusion (WBF).
- **Cost:** ~1.3× ingest time.
- **Expected impact:** +0.15–0.25 confidence on critical classes.
- **When:** Only if real footage reveals a critical class scoring below 0.3197.

**Critical Vocabulary (50 terms):**
```
person, car, bicycle, motorcycle, bus, truck, backpack, handbag,
suitcase, umbrella, helmet, phone, laptop, cup, bottle, chair,
couch, bed, dining table, door, window, dog, cat, bird, horse,
knife, fork, spoon, bowl, banana, apple, sandwich, orange,
broccoli, carrot, clock, vase, scissors, teddy bear, hair drier,
toothbrush, book, keyboard, mouse, monitor, traffic light,
fire hydrant, stop sign, parking meter, bench
```

#### Optimization 2: Multi-Scale Inference (OPTIONAL)
- Run at imgsz=640 and imgsz=1280, merge with WBF.
- Cost: ~1.8× ingest time.
- Trigger: Only if Phase 1 is verified and merged.

#### Optimization 3: Test-Time Augmentation (OPTIONAL)
- Horizontal flip, run detection, remap boxes, merge.
- Cost: ~1.4× ingest time.
- Trigger: Only if Phase 1 is verified.

### 4.4 What Is NOT Being Done

The following are **explicitly not being implemented before the hackathon**:
- ❌ No second detection model (GroundingDINO, OWL-ViT, DETIC, SAM)
- ❌ No embedding-based re-ranking (SigLIP2, CLIP)
- ❌ No fine-tuning on custom data
- ❌ No real-time stream processing
- ❌ No online detection at query time (would destroy sub-second latency)
- ❌ No Cascade Vocabulary Fallback (rejected — see §4.2)

---

## 5. Qdrant Schema Change

One new payload field was added in Session 3:

```json
{
  "class": "cup",
  "confidence": 0.84,
  "detection_source": "full_primary",
  "bbox": [294.0, 487.0, 326.0, 536.0],
  "color": "black",
  "spatial_relations": [...],
  "video_id": "...",
  "timestamp": 5.0,
  "scene_id": 0,
  "frame_index": 42
}
```

`detection_source` values: `"full_primary"` (current), `"cascade_fallback"` (future)

The rule-based parser does **not** need to read this field. It is for debugging and future-proofing only.

---

## 6. Implementation Checklist (Post-Hackathon)

- [ ] Define `CRITICAL_VOCAB` constant (50 terms)
- [ ] Implement `detect_with_fallback(frame, full_vocab, critical_vocab)` wrapper
- [ ] Implement `merge_detections(dets_a, dets_b, iou_threshold=0.5)` with WBF
- [ ] Add `detection_source` field to Qdrant payload writer
- [ ] Test on 5 representative frames: compare confidence before/after
- [ ] Verify no regression on frames that already worked well
- [ ] (Optional) Implement multi-scale loop
- [ ] (Optional) Implement TTA horizontal flip

**Current status: ALL ITEMS PENDING.** Nothing implemented. All deferred to post-hackathon.

---

## 7. If a New AI Assistant Reads This

**Do not propose:**
- Replacing YOLO-World with another model
- Adding a "backup engine" that is a separate heavy model
- Any option marked ❌ in §3.2
- Cascade Vocabulary Fallback before the hackathon

**Do help with:**
- Post-hackathon implementation of `detect_with_fallback()`
- Post-hackathon `merge_detections()` function
- Debugging if detection confidence genuinely drops below 0.3197 on real footage

**If the user asks to reopen the engine decision:**
Refer them to this document and ask: *"Do you have full team sign-off to override Architecture_Final_v2.4.md §2?"* If yes, proceed with caution. If no, stay with the locked plan.

---

## 8. Sign-Off

| Role | Name/ID | Decision |
|---|---|---|
| AI Research & Analysis | Kimi | Recommend keep YOLO-World, optimize usage |
| Team Lead / Human | [Team member] | Ratified — do not replace engine |
| Architecture Authority | `03_Architecture_Final_v2.4.md` | Locked — YOLO-World-M remains |
| Session 3 Coordinator | Kimi (v2.4) | Cascade Fallback rejected; frontend pivot approved |

**This decision is final unless explicitly reopened by full team consensus.**

---

*Document produced by: Kimi (Moonshot AI)*
*Aligned with: Blueprint_Final_v2.4.md, PRD_Final_v2.4.md, Architecture_Final_v2.4.md*
*Next step: REHEARSAL. No more building.*
