# ASK-N-SEEK FRONTEND v2
## Sondaven.com Aesthetic Clone · Dark Cinematic · Premium Editorial

---

## What You Get

A complete, standalone frontend that clones the **sondaven.com** aesthetic:
- Pure black backgrounds with warm gold accents
- Playfair Display serif typography (huge, editorial)
- Animated particle system in hero
- Scroll-triggered fade reveals
- "Hold and move" draggable image gallery
- Full drag-and-drop upload with 6-phase progress
- Search with vocabulary warnings
- Results with bounding box overlays
- Video player with dropdown seek
- Diagnosis panel for no-match queries
- Session history sidebar

---

## Files

```
ask-n-seek-frontend-v2/
├── index.html          ← Main page (open this in browser)
├── styles.css          ← All styles (dark cinematic theme)
├── app.js              ← All JavaScript (particles, animations, API)
├── bridge_server.py    ← Python API bridge (optional)
└── README.md           ← This file
```

---

## Quick Start (No Build Step!)

### Option 1: Just Open the File (Static Demo)
```bash
# Simply double-click index.html
# OR serve with any static server:
python -m http.server 3000
# Then open http://localhost:3000
```

### Option 2: With API Bridge (Full Functionality)
```bash
# 1. Install dependencies
pip install fastapi uvicorn python-multipart

# 2. Start the bridge server
python bridge_server.py

# 3. In another terminal, serve the frontend
python -m http.server 3000

# 4. Open http://localhost:3000
```

---

## To Connect to Your Real Backend

Edit `bridge_server.py`:
```python
MOCK_MODE = False  # Change this
BACKEND_PATH = "C:/path/to/your/Ask-N-Seek"  # Update this
```

---

## Design System

| Element | Value |
|---------|-------|
| Background | `#000000` pure black |
| Surface | `#0a0a0a`, `#111111` |
| Text | `#ffffff` |
| Muted text | `rgba(255,255,255,0.5)` |
| Accent | `#c9a96e` warm gold |
| Display font | Playfair Display |
| Body font | Inter |
| Mono font | JetBrains Mono |

---

## Sections (matching sondaven.com structure)

1. **Hero** — Full-screen with animated particles, huge title
2. **Quote** — Italic editorial text, scroll reveal
3. **About** — Two-column grid with image
4. **Concept** — Full-bleed image with overlay text
5. **Upload** — Drag-drop zone with 6-phase progress
6. **Search** — Clean input with suggestion chips
7. **Results** — Card grid with bbox overlays
8. **Features** — Numbered stats (800+ classes, etc.)
9. **Pipeline** — Split layout with image + steps
10. **Interactive** — "Hold and move" draggable gallery
11. **Footer** — Brand + tagline

---

## Animations Included

- ✅ Floating particles (hero background)
- ✅ Scroll-triggered fade-up reveals
- ✅ Title character reveal animation
- ✅ Scroll line pulse animation
- ✅ Image hover zoom + grayscale removal
- ✅ Upload progress bar with glow dot
- ✅ Phase indicator state transitions
- ✅ Result card staggered entrance
- ✅ "Hold and move" drag with momentum
- ✅ Smooth scroll navigation
- ✅ History sidebar slide-in

---

## Keyboard Shortcuts

- `Enter` in search box → Submit query
- Click suggestion chip → Auto-fill + search
- Click result card → Play video at timestamp
- Click history item → Replay query

---

Built for Hackathon · Ask-N-Seek v2.3
