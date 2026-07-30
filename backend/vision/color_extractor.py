"""
color_extractor.py — Center-Weighted Crop + k-means + CIELAB Color Naming
==========================================================================
Architecture ref : 03_Architecture_Final.md §2 (Color extraction row)
TRD ref          : TRD-Build-Plan-Achilles.md §PART 2

Rule: center-weighted crop (inner 50% of bbox) → k-means (k=3) →
      find cluster with most pixels → nearest CIELAB name from curated palette.

This avoids background contamination from the bbox edges.
Color is always a string from CIELAB_PALETTE (or "unknown" on failure).
"""

from __future__ import annotations

import numpy as np

try:
    import cv2
    _CV2_OK = True
except ImportError:
    _CV2_OK = False

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
) -> str:
    """
    Extract dominant color name from the center-weighted crop of a bbox.

    Parameters
    ----------
    frame_bgr : H×W×3 uint8 BGR image (the full frame).
    bbox      : (x1, y1, x2, y2) pixel coordinates.
    k         : number of k-means clusters (default 3).

    Returns
    -------
    str  : colour name from CIELAB_PALETTE, or "unknown" on failure.
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

        # Center-weighted crop: inner 50% of the bbox (25% margin each side)
        cx_margin = max(1, int(bw * 0.25))
        cy_margin = max(1, int(bh * 0.25))
        crop = frame_bgr[
            y1 + cy_margin : y2 - cy_margin,
            x1 + cx_margin : x2 - cx_margin,
        ]

        if crop.size == 0:
            return "unknown"

        # Downsample to 32x32 before k-means — eliminates large pixel arrays, ~100x faster
        crop = cv2.resize(crop, (32, 32), interpolation=cv2.INTER_AREA)

        # Flatten to Nx3
        pixels = crop.reshape(-1, 3).astype(np.float32)

        # k-means
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

        # Convert to LAB
        dominant_lab = _bgr_to_lab(dominant_bgr.reshape(1, 3))[0]

        return _nearest_lab_name(dominant_lab)

    except Exception:
        return "unknown"
