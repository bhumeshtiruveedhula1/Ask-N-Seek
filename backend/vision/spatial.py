"""
spatial.py -- Left/Right Spatial Relations Between Detected Objects
==================================================================
Architecture ref : 03_Architecture_Final.md §2 (Spatial relations row) + §6
TRD ref          : TRD-Build-Plan-Achilles.md §PART 2

LOCKED RULES (do NOT deviate):
  - Left/right ONLY -- based on bbox centroid x-coordinates.
  - Top-4 confidence pairs only (to keep Qdrant payload small).
  - Proximity relations are NOT implemented per Architecture §6.
    There is no proximity filter in Qdrant; implementing without
    a real filter would produce falsely-labelled results.
  - Returns a list of SpatialRelation dicts -- empty list is valid.
"""

from __future__ import annotations

from typing import TypedDict


DetectionDict = TypedDict('DetectionDict', {
    'class':      str,
    'bbox':       tuple,    # x1, y1, x2, y2
    'confidence': float,
    'color':      str,
})


class SpatialRelation(TypedDict):
    subject: str          # class_name of the left object
    subject_idx: int      # index in detections list
    relation: str         # "left_of" | "right_of"
    object_: str          # class_name of the right object
    object_idx: int       # index in detections list


def _centroid_x(bbox: tuple[int, int, int, int]) -> float:
    x1, _, x2, _ = bbox
    return (x1 + x2) / 2.0


def compute_spatial_relations(
    detections: list[DetectionDict],
    top_k_pairs: int = 4,
) -> list[SpatialRelation]:
    """
    Compute left/right spatial relations for the top-k-confidence object pairs
    in a single frame.

    Algorithm:
      1. Select top_k_pairs objects by confidence score.
      2. For every ordered pair (A, B) among those objects where A != B:
           if centroid_x(A) < centroid_x(B)  →  A is "left_of" B
                                                 B is "right_of" A
      3. Return deduplicated list.

    Parameters
    ----------
    detections   : list of detection dicts (class_name, bbox, confidence, color).
    top_k_pairs  : number of highest-confidence objects to pair up (default 4).

    Returns
    -------
    list[SpatialRelation] — empty list if fewer than 2 detections.

    Note: proximity relations are intentionally absent per Architecture ss6.
    """
    if len(detections) < 2:
        return []

    # Select top-k by confidence
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

    return relations
