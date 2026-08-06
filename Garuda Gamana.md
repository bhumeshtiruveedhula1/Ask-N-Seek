<!-- Header Wave -->
<img src="https://capsule-render.vercel.app/api?type=waving&color=0:000000,50:050211,100:00e5ff&height=200&section=header&text=Ask-N-Seek&fontSize=60&fontAlignY=35&desc=Type%20what%20happened.%20We'll%20show%20you%20exactly%20where.&descAlignY=55&descSize=20&fontColor=ffffff" width="100%"/>

<div align="center">

<!-- Animated Typing Text -->
<a href="https://github.com/VexedPainter/ask-n-seek">
  <img src="https://readme-typing-svg.demolab.com?font=Inter&weight=600&size=24&duration=3000&pause=1000&color=00e5ff&center=true&vCenter=true&lines=Advanced+Computer+Vision;Deep+Space+UI+%E2%9C%A8;Simulated+Action+Recognition;CPU-Optimized+OpenVINO" alt="Typing SVG" />
</a>

<br>

<p align="center">
  <img src="https://img.shields.io/badge/FastAPI-005571?style=for-the-badge&logo=fastapi&logoColor=white" />
  <img src="https://img.shields.io/badge/OpenVINO-2C2255?style=for-the-badge&logo=intel&logoColor=white" />
  <img src="https://img.shields.io/badge/SQLite-07405E?style=for-the-badge&logo=sqlite&logoColor=white" />
  <img src="https://img.shields.io/badge/Vanilla_JS-F7DF1E?style=for-the-badge&logo=javascript&logoColor=black" />
</p>

*An ultra-modern, CPU-optimized computer vision and natural language query engine.*

</div>

---

## ✧ The Vision

**Ask-N-Seek** bridges the gap between raw video footage and natural human inquiry. By leveraging an optimized, CPU-friendly OpenVINO YOLOv8n pipeline, it extracts object detections, color clusters, and spatial relations from any uploaded video. 

The intuitive, rule-based natural language parser translates plain English (*"person grabbing the blue car"*) into parameterized SQL constraints, instantly seeking your footage to the exact moment of interest and playing it back flawlessly.

<br>

## ✧ Advanced Engineering (Hackathon Highlights)

To bypass the need for heavy, slow, or multi-modal models (like Pose Estimation or Action Recognition networks), we engineered clever mathematical workarounds directly into the architecture:

### 1. The Negation Engine ("Ghost" Frames)
Standard models only detect *presence*, making it impossible to search for "No person" (e.g. when someone hides behind a tree) because the frame simply isn't recorded. 
**Our Solution:** The ingestion pipeline deliberately injects `__empty__` anchor rows into the database for frames with zero detections. The NLP parser translates negative phrases ("without a person", "zero people") into an SQL `NOT EXISTS` query, instantly locating the exact moment someone vanishes.

### 2. Action Simulation Engine
YOLOv8n is a static object detector—it knows nouns, but not verbs (like "touching" or "pulling").
**Our Solution:** We built a custom 2D bounding-box intersection calculator. When a person's bounding box aggressively overlaps with a car's box, they are tagged with a hidden `touching:car` spatial relation. The NLP engine intercepts verbs like `"grabbing"`, `"pulling"`, or `"barging at"` and maps them directly to this intersection constraint.

### 3. Smart Search Aggregation
Instead of flooding the UI with 30 individual results if an object is visible for 30 frames, the SQL aggregation engine automatically groups consecutive, identical hits into a unified **Time Range** (e.g., `00:05 - 00:08`). When clicked, the video automatically plays and dynamically pauses exactly when the event ends.

<br>

## ✧ Core Architecture

<table>
<tr>
<td valign="top" width="50%">

### 🧠 Inference & Processing
| Tech | Purpose |
|------|---------|
| **YOLOv8n** | Bounding box object detection |
| **OpenVINO** | CPU hardware acceleration |
| **Scikit-Learn** | K-Means color clustering |
| **OpenCV** | Frame extraction & manipulation |

</td>
<td valign="top" width="50%">

### ⚡ Backend & UI
| Tech | Purpose |
|------|---------|
| **FastAPI** | Asynchronous HTTP endpoints |
| **SQLite3** | Relational constraint engine |
| **Python `threading`** | Non-blocking background jobs |
| **HTML5 Canvas** | 800-particle Swirling Galaxy |

</td>
</tr>
</table>

---

## ✧ Premium Features

- 🌌 **Cosmos Aesthetics:** A fully custom, zero-build frontend (no node modules) featuring a deep-space glassmorphism UI and a highly optimized physics-based, 800-particle 3D Swirling Galaxy canvas background.
- 🎭 **Natural Language Parsing**: Translates human queries into strict database constraints (supports colors, classes, object exclusions, and spatial relations).
- ⚙️ **CPU-Optimized Ingestion**: Runs YOLOv8 inference through OpenVINO, capable of running smoothly on low-power Intel CPUs. Automatically filters low-confidence noise for pristine precision.
- 🩺 **Smart Vocabulary Diagnostics**: A transparent query system that actively catches non-COCO vocabulary (e.g., *"ghost"*, *"dragon"*) and gracefully returns custom error dialogues instead of crashing the database.

<br>

## ✧ Quick Start Guide

### 1. Requirements
- Python 3.10+
- Standard Intel x86 CPU (OpenVINO optimized)

### 2. Initialization
```bash
# Clone the repository
git clone https://github.com/VexedPainter/ask-n-seek.git
cd ask-n-seek

# Install dependencies
pip install fastapi uvicorn python-multipart requests scikit-learn ultralytics openvino
```

### 3. Ignite the Engine
```bash
# Start the FastAPI backend and integrated frontend
python -m uvicorn backend.main:app --port 8000
```
**Navigate to:** `http://localhost:8000`

---
<div align="center">

<img src="https://capsule-render.vercel.app/api?type=waving&color=0:00e5ff,50:050211,100:000000&height=120&section=footer" width="100%"/>

**Ask-N-Seek v1.5**

*Engineered for minimal footprint, designed for maximum elegance.*

<p>
  <img src="https://img.shields.io/badge/Made_by-VexedPainter-00e5ff?style=flat-square&logo=github&logoColor=black" />
</p>

</div>
