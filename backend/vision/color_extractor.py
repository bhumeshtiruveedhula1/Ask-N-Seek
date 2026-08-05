"""
color_extractor.py — Class-Aware Crop + Outlier Rejection + k-means + CIELAB Color Naming
==========================================================================================
Architecture ref : 03_Architecture_Final.md §2 (Color extraction row)
TRD ref          : TRD-Build-Plan-Achilles.md §PART 2

Rule: class-aware crop (vehicles=bottom 60%, persons=body 30-80%, else center 50%)
      → outlier rejection (exclude near-neutral, very dark, overexposed pixels)
      → k-means (k=3) → find cluster with most valid pixels
      → nearest CIELAB name from curated palette.

Class-aware crop avoids: windshield glass on cars (reads black/gray instead of body
colour) and faces on people (reads skin tone instead of clothing colour).
Outlier rejection ensures the dominant colour reflects actual object colour, not
background contamination at bbox edges.
"""

from __future__ import annotations

import numpy as np

try:
    import cv2
    _CV2_OK = True
except ImportError:
    _CV2_OK = False

# ---------------------------------------------------------------------------
# Class-aware crop regions
# ---------------------------------------------------------------------------
# Vehicles: sample bottom 60% of bbox to avoid windshield glass (which reads
# as black/gray even on a red car).
VEHICLE_CLASSES: frozenset[str] = frozenset({
    "car", "truck", "bus", "motorcycle", "bicycle",
})

# Persons: sample middle body (skip top 30% = face/hair, skip bottom 20% = legs)
# so clothing colour is returned, not skin tone or shoe colour.
PERSON_CLASSES: frozenset[str] = frozenset({
    "person", "man", "woman", "child",
})

# ---------------------------------------------------------------------------
# CIELAB colour palette — (name, L, a, b) — curated for PS-relevance
# L: 0-100, a: -128..127, b: -128..127
# ---------------------------------------------------------------------------

_CIELAB_PALETTE: list[tuple[str, float, float, float]] = [
    # Achromatic
    ("white",       95.0,  0.0,   0.0),
    ("light gray",  75.0,  0.0,   0.0),
    ("gray",        55.0,  0.0,   0.0),
    ("dark gray",   35.0,  0.0,   0.0),
    ("black",       10.0,  0.0,   0.0),
    # Reds / oranges
    ("red",         40.0,  55.0,  37.0),
    ("dark red",    25.0,  40.0,  25.0),
    ("orange",      60.0,  28.0,  60.0),
    ("orange-red",  50.0,  45.0,  48.0),
    # Yellows
    ("yellow",      90.0, -10.0,  88.0),
    ("dark yellow", 70.0,  -5.0,  60.0),
    # Greens
    ("green",       50.0, -45.0,  40.0),
    ("light green", 70.0, -38.0,  35.0),
    ("dark green",  30.0, -30.0,  22.0),
    ("olive",       50.0, -10.0,  30.0),
    # Blues
    ("blue",        35.0,  15.0, -50.0),
    ("light blue",  60.0,  -5.0, -30.0),
    ("dark blue",   20.0,  10.0, -35.0),
    ("navy",        18.0,   5.0, -22.0),
    # Purples / pinks
    ("purple",      35.0,  35.0, -40.0),
    ("pink",        70.0,  30.0,   5.0),
    ("hot pink",    55.0,  52.0,  -5.0),
    # Browns / beiges
    ("brown",       38.0,  18.0,  25.0),
    ("beige",       82.0,   3.0,  18.0),
    ("tan",         68.0,   8.0,  22.0),
    # Metallic / misc
    ("silver",      80.0,  -1.0,  -2.0),
    ("gold",        75.0,   5.0,  50.0),
]

# Pre-compute palette as numpy array for vectorised nearest-neighbour
_PALETTE_NAMES: list[str] = [p[0] for p in _CIELAB_PALETTE]
_PALETTE_LAB: np.ndarray = np.array(
    [[p[1], p[2], p[3]] for p in _CIELAB_PALETTE], dtype=np.float32
)


def _bgr_to_lab(bgr_pixels: np.ndarray) -> np.ndarray:
    """Convert Nx3 BGR uint8/float32 array to Nx3 LAB (float32)."""
    if not _CV2_OK:
        raise ImportError("opencv-python required for color extraction")
    pixels = bgr_pixels.reshape(-1, 3).astype(np.uint8)
    n = len(pixels)
    # Process each pixel as a 1x1x3 image to guarantee correct conversion
    out = np.empty((n, 3), dtype=np.float32)
    for i in range(n):
        img_1x1 = pixels[i].reshape(1, 1, 3)
        lab_1x1 = cv2.cvtColor(img_1x1, cv2.COLOR_BGR2LAB)
        raw = lab_1x1[0, 0].astype(np.float32)
        # cv2 LAB encoding: L*[0..255]->scale to [0..100], a/b [0..255]->[-128..127]
        out[i] = [raw[0] * 100.0 / 255.0, raw[1] - 128.0, raw[2] - 128.0]
    return out


def _nearest_lab_name(lab: np.ndarray) -> str:
    """Find nearest palette colour to a given LAB triplet."""
    # Euclidean distance in LAB space — perceptually meaningful
    diffs = _PALETTE_LAB - lab
    dists = np.sum(diffs ** 2, axis=1)
    return _PALETTE_NAMES[int(np.argmin(dists))]


def extract_color(
    frame_bgr: np.ndarray,
    bbox: tuple[int, int, int, int],  # x1, y1, x2, y2
    k: int = 3,
    class_name: str | None = None,
) -> str:
    """
    Extract dominant color name from a class-aware crop of a bbox.

    Parameters
    ----------
    frame_bgr  : H×W×3 uint8 BGR image (the full frame).
    bbox       : (x1, y1, x2, y2) pixel coordinates.
    k          : number of k-means clusters (default 3).
    class_name : object class (e.g. "car", "person") for class-aware cropping.
                 Pass None for the legacy center-50% behaviour.

    Returns
    -------
    str  : colour name from CIELAB_PALETTE, or "unknown" on failure.

    Class-aware crop rules
    ----------------------
    - Vehicles : bottom 60% of bbox (skips windshield glass → reads body colour).
    - Persons  : middle body 30–80% (skips face/hair → reads clothing colour).
    - Default  : center 50% crop (25% margin each side).
    """
    try:
        x1, y1, x2, y2 = bbox
        # Clamp to frame bounds
        h, w = frame_bgr.shape[:2]
        x1, x2 = max(0, x1), min(w, x2)
        y1, y2 = max(0, y1), min(h, y2)

        bw, bh = x2 - x1, y2 - y1
        if bw < 4 or bh < 4:
            return "unknown"

        # ---- Class-aware crop selection -----------------------------------
        cls = (class_name or "").lower()

        if cls in VEHICLE_CLASSES:
            # Bottom 60% of bbox: skip windshield (top 40%)
            crop_y1 = y1 + int(bh * 0.4)
            crop = frame_bgr[crop_y1:y2, x1:x2]

        elif cls in PERSON_CLASSES:
            # Middle body: skip face (top 30%) and legs (bottom 20%)
            crop_y1 = y1 + int(bh * 0.3)
            crop_y2 = y2 - int(bh * 0.2)
            if crop_y2 <= crop_y1:
                crop_y2 = crop_y1 + 1  # guard against tiny bboxes
            crop = frame_bgr[crop_y1:crop_y2, x1:x2]

        else:
            # Default: center 50% crop (25% margin each side)
            cx_margin = max(1, int(bw * 0.25))
            cy_margin = max(1, int(bh * 0.25))
            crop = frame_bgr[
                y1 + cy_margin : y2 - cy_margin,
                x1 + cx_margin : x2 - cx_margin,
            ]

        if crop is None or crop.size == 0:
            return "unknown"

        # Downsample to 32x32 before k-means — ~100x faster, perceptually fine
        crop_resized = cv2.resize(crop, (32, 32), interpolation=cv2.INTER_AREA)

        # ---- Outlier rejection in LAB space --------------------------------
        # Exclude near-neutral (|a|+|b| < 15), very dark (L < 20), and
        # overexposed (L > 95) pixels — these are background/glass/highlight
        # contamination and skew the dominant-colour result.
        lab_img  = cv2.cvtColor(crop_resized, cv2.COLOR_BGR2LAB)
        lab_px   = lab_img.reshape(-1, 3).astype(np.float32)
        # cv2 LAB: L in [0,255], a/b in [0,255] (offset by 128)
        l_scaled = lab_px[:, 0] * 100.0 / 255.0   # [0, 100]
        a_center = lab_px[:, 1] - 128.0            # [-128, 127]
        b_center = lab_px[:, 2] - 128.0            # [-128, 127]

        valid_mask = (
            (l_scaled > 20) &
            (l_scaled < 95) &
            (np.abs(a_center) + np.abs(b_center) > 15)
        )
        valid_bgr_px = crop_resized.reshape(-1, 3)[valid_mask].astype(np.float32)

        # Fallback: if outlier rejection removed too many pixels, use all
        pixels = valid_bgr_px if len(valid_bgr_px) >= 10 else crop_resized.reshape(-1, 3).astype(np.float32)

        # ---- k-means on surviving pixels -----------------------------------
        n_pixels = len(pixels)
        k_actual = min(k, n_pixels)
        if k_actual < 1:
            return "unknown"

        criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 5, 1.0)
        _, labels, centers = cv2.kmeans(
            pixels, k_actual, None, criteria, 1, cv2.KMEANS_PP_CENTERS
        )

        # Find cluster with most pixels
        counts = np.bincount(labels.flatten(), minlength=k_actual)
        dominant_bgr = centers[int(np.argmax(counts))]

        # Convert to LAB and find nearest palette name
        dominant_lab = _bgr_to_lab(dominant_bgr.reshape(1, 3))[0]
        return _nearest_lab_name(dominant_lab)

    except Exception:
        return "unknown"
