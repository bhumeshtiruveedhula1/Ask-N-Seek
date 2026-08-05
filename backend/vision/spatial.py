"""
spatial.py -- Left/Right Spatial Relations Between Detected Objects
=================================================================
Architecture ref : 03_Architecture_Final.md §2 (Spatial relations row) + §6
TRD ref          : TRD-Build-Plan-Achilles.md §PART 2

RELATIONS COMPUTED:
  - left_of  : centroid_x(A) < centroid_x(B) — top-4 confidence pairs
  - right_of : centroid_x(A) > centroid_x(B) — top-4 confidence pairs

LOCKED SCOPE (Architecture_Final_v2.4.1 §6):
  - ONLY left_of / right_of recognized.
  - touching / near: 2D IoU/edge-gap heuristics produce false positives
    from single camera angle; excluded from demo build.
  - Returns a list of SpatialRelation dicts -- empty list is valid.
"""

from __future__ import annotations

from typing import TypedDict

import config as _config


DetectionDict = TypedDict('DetectionDict', {
    'class':      str,
    'bbox':       tuple,    # x1, y1, x2, y2
    'confidence': float,
    # 'color' removed: color is Odysseus's Part 2 scope (contract reply 2026-07-29)
})


class SpatialRelation(TypedDict):
    subject: str          # class_name of the subject object
    subject_idx: int      # index in detections list
    relation: str         # "left_of" | "right_of"
    object_: str          # class_name of the object
    object_idx: int       # index in detections list


def _centroid_x(bbox: tuple[int, int, int, int]) -> float:
    x1, _, x2, _ = bbox
    return (x1 + x2) / 2.0


def _iou(box_a: tuple, box_b: tuple) -> float:
    """Intersection over Union for two (x1, y1, x2, y2) boxes. Retained for test compatibility."""
    x1 = max(box_a[0], box_b[0])
    y1 = max(box_a[1], box_b[1])
    x2 = min(box_a[2], box_b[2])
    y2 = min(box_a[3], box_b[3])
    inter = max(0, x2 - x1) * max(0, y2 - y1)
    area_a = (box_a[2] - box_a[0]) * (box_a[3] - box_a[1])
    area_b = (box_b[2] - box_b[0]) * (box_b[3] - box_b[1])
    union = area_a + area_b - inter
    return inter / union if union > 0 else 0.0


def _edge_gap(box_a: tuple, box_b: tuple) -> float:
    """Minimum edge-to-edge gap (pixels) between two bboxes. Retained for test compatibility."""
    h_gap = max(0.0, max(box_a[0] - box_b[2], box_b[0] - box_a[2]))
    v_gap = max(0.0, max(box_a[1] - box_b[3], box_b[1] - box_a[3]))
    return max(h_gap, v_gap)


def compute_spatial_relations(
    detections: list[DetectionDict],
    top_k_pairs: int = 4,
) -> list[SpatialRelation]:
    """
    Compute spatial relations for detected objects in a single frame.

    LOCKED SCOPE: left_of / right_of ONLY (Architecture_Final_v2.4.1 §6).
    touching / near removed — 2D IoU/edge-gap heuristics produce false positives
    from single camera angle footage and are excluded from the demo build.

    Parameters
    ----------
    detections   : list of detection dicts (class_name, bbox, confidence).
    top_k_pairs  : number of highest-confidence objects for left/right pairs (default 4).

    Returns
    -------
    list[SpatialRelation] — empty list if fewer than 2 detections.
    """
    if len(detections) < 2:
        return []

    # ── Left / Right ────────────────────────────────────────────────────────
    indexed = [(i, d) for i, d in enumerate(detections)]
    indexed_sorted = sorted(indexed, key=lambda x: x[1]["confidence"], reverse=True)
    top = indexed_sorted[:top_k_pairs]

    relations: list[SpatialRelation] = []

    for i in range(len(top)):
        idx_a, det_a = top[i]
        cx_a = _centroid_x(det_a["bbox"])

        for j in range(len(top)):
            if i == j:
                continue
            idx_b, det_b = top[j]
            cx_b = _centroid_x(det_b["bbox"])

            if cx_a < cx_b:
                relations.append(SpatialRelation(
                    subject=det_a['class'],
                    subject_idx=idx_a,
                    relation="left_of",
                    object_=det_b['class'],
                    object_idx=idx_b,
                ))
                # INVERSE: obj_b is right_of obj_a
                relations.append(SpatialRelation(
                    subject=det_b['class'],
                    subject_idx=idx_b,
                    relation="right_of",
                    object_=det_a['class'],
                    object_idx=idx_a,
                ))

    return relations
