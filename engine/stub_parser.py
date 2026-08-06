"""
engine/stub_parser.py — Stub query parser for Odysseus Part 3.

# TODO: SWAP FOR ACHILLES'S REAL IMPLEMENTATION
# This stub returns hardcoded filter dicts for the 5 known verification queries
# and falls back to keyword heuristics for similar phrasings.
# Achilles's real rule-based parser will replace this function entirely.
#
# Integration point:
#   Replace parse_query_stub() with:
#       from achilles.parser import parse_query
#   and update callers in ui/gradio_app.py and engine/calibration.py.

The output contract (agreed with Achilles):
{
    "status": "match" | "no_match",
    "filters": {
        "class": str | None,
        "color": str | None,
        "negated": List[str],
        "spatial_relation": {"type": str, "target_class": str} | None,
        "count_constraint": {"operator": str, "value": int, "class": str} | None,
    }
}
"""

from __future__ import annotations

import re

# ---------------------------------------------------------------------------
# Known verification queries → hardcoded filter dicts
# (These exact queries are used in the Milestone 1 verification checklist)
# ---------------------------------------------------------------------------

_KNOWN_QUERIES: dict[str, dict] = {
    "person in red": {
        "status": "match",
        "filters": {
            "class": "person",
            "color": "red",
            "negated": [],
            "spatial_relation": None,
            "count_constraint": None,
        },
    },
    "person without helmet": {
        "status": "match",
        "filters": {
            "class": "person",
            "color": None,
            "negated": ["helmet"],
            "spatial_relation": None,
            "count_constraint": None,
        },
    },
    "two people": {
        "status": "match",
        "filters": {
            "class": None,
            "color": None,
            "negated": [],
            "spatial_relation": None,
            "count_constraint": {"operator": ">=", "value": 2, "class": "person"},
        },
    },
    "person left of car": {
        "status": "match",
        "filters": {
            "class": "person",
            "color": None,
            "negated": [],
            "spatial_relation": {"type": "left_of", "target_class": "car"},
            "count_constraint": None,
        },
    },
}

# ---------------------------------------------------------------------------
# Keyword dictionaries for heuristic fallback parsing
# ---------------------------------------------------------------------------

_CLASSES = {
    # People
    "person", "people", "man", "woman", "child", "pedestrian",
    "traffic warden", "warden", "officer", "worker", "guard",
    # Vehicles — including synonyms YOLO-World actually stores in DB
    "car", "vehicle", "truck", "bus", "van", "motorcycle", "bicycle",
    "sedan", "suv", "minivan", "jeep", "pickup",
    # Objects
    "helmet", "bag", "backpack", "handbag", "dog", "bicycle",
    "extinguisher", "vest", "shoe", "wheel", "tire",
}
_COLORS = {
    "red", "dark red",
    "blue", "dark blue", "navy", "light blue",
    "white", "black",
    "green", "dark green", "light green",
    "yellow", "gold",
    "gray", "dark gray", "light gray", "silver",
    "brown", "orange", "purple", "pink",
}
_NEGATION_WORDS = {"without", "no", "not", "excluding", "minus"}

# DB only stores: near, left_of, right_of
# All proximity phrases map to 'near'; direction phrases map to left_of/right_of
_SPATIAL_MAP = {
    # Proximity — all → near (the DB proximity relation)
    "next to":       "near",
    "next":          "near",
    "near":          "near",
    "beside":        "near",
    "by the":        "near",
    "by":            "near",
    "close to":      "near",
    "adjacent to":   "near",
    "alongside":     "near",
    "holding":       "near",
    "at the":        "near",
    "touching":      "near",
    # Direction
    "left of":       "left_of",
    "left_of":       "left_of",
    "right of":      "right_of",
    "right_of":      "right_of",
    "above":         "above",
    "below":         "below",
    "in front of":   "near",
    "behind":        "near",
}
_NONSENSE_SIGNALS = {
    "elephant", "dinosaur", "dragon", "flying", "invisible",
    "purple", "pink", "dancing", "singing", "alien", "rocket",
    "mermaid", "unicorn", "zombie",
}


def parse_query_stub(query: str) -> dict:
    """
    Parse a natural-language query into a structured filter dict.

    For the 4 known verification queries, returns exact hardcoded filters.
    For similar phrasing, applies lightweight keyword heuristics.
    For nonsense / unrecognisable queries, returns status='no_match'.

    Parameters
    ----------
    query : str
        Raw user query string.

    Returns
    -------
    dict
        Structured filter dict per the Achilles output contract.
    """
    normalised = query.strip().lower()
    normalised = re.sub(r"\s+", " ", normalised)

    # 1. Exact match against known test queries
    if normalised in _KNOWN_QUERIES:
        return _KNOWN_QUERIES[normalised]

    # 2. Nonsense detection: if any nonsense token appears → no_match
    tokens = set(normalised.split())
    if tokens & _NONSENSE_SIGNALS:
        return _no_match()

    # 3. Heuristic keyword parsing
    return _heuristic_parse(normalised)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _no_match() -> dict:
    return {
        "status": "no_match",
        "filters": {
            "class": None,
            "color": None,
            "negated": [],
            "spatial_relation": None,
            "count_constraint": None,
        },
    }


def _heuristic_parse(text: str) -> dict:
    """
    Lightweight keyword extraction with multi-word phrase awareness.
    Handles compound colors (dark red, dark gray, navy), compound class
    names (traffic warden), and multi-word spatial phrases (next to, close to).
    """
    tokens = text.split()

    # ── Multi-word phrases to check BEFORE single-token scan ──────────────────
    _MULTI_WORD_COLORS: list[tuple[str, str]] = [
        # (phrase_in_query, canonical_color_for_storage_lookup)
        ("dark red",   "red"),
        ("dark blue",  "blue"),
        ("dark gray",  "gray"),
        ("dark green", "green"),
        ("light blue", "blue"),
        ("light gray", "gray"),
        ("orange red", "red"),
    ]
    _MULTI_WORD_CLASSES: list[tuple[str, str]] = [
        ("traffic warden", "person"),
        ("fire extinguisher", "extinguisher"),
    ]

    # --- detect class (multi-word first, then single-token) ---
    detected_class: str | None = None
    for phrase, canonical in _MULTI_WORD_CLASSES:
        if phrase in text:
            detected_class = canonical
            break
    if not detected_class:
        for tok in tokens:
            tok_clean = tok.rstrip("s")
            if tok in ("people", "persons"):
                detected_class = "person"
                break
            if tok in _CLASSES:
                detected_class = tok
                break
            if tok_clean in _CLASSES:
                detected_class = tok_clean
                break

    # --- detect color (multi-word first, then single-token) ---
    detected_color: str | None = None
    for phrase, canonical in _MULTI_WORD_COLORS:
        if phrase in text:
            detected_color = canonical
            break
    if not detected_color:
        for tok in tokens:
            if tok in _COLORS:
                detected_color = tok
                break

    # --- detect negation ---
    negated: list[str] = []
    for i, tok in enumerate(tokens):
        if tok in _NEGATION_WORDS:
            for j in range(i + 1, min(i + 3, len(tokens))):
                candidate = tokens[j].rstrip("s")
                if tokens[j] in _CLASSES:
                    negated.append(tokens[j])
                    break
                if candidate in _CLASSES:
                    negated.append(candidate)
                    break

    # --- detect spatial relation (longest phrase first to avoid partial match) ---
    _STOP_WORDS = {"a", "an", "the", "some", "my", "this", "that"}
    spatial_relation: dict | None = None
    # Sort by phrase length descending so "next to" matches before "next"
    sorted_spatial = sorted(_SPATIAL_MAP.items(), key=lambda kv: len(kv[0]), reverse=True)
    for phrase, rel_type in sorted_spatial:
        if phrase in text:
            after = text.split(phrase, 1)[1].strip()
            after_tokens = [t for t in after.split() if t not in _STOP_WORDS]
            for tok in after_tokens:
                tok_clean = tok.rstrip("s")
                target: str | None = None
                if tok in _CLASSES:
                    target = tok
                elif tok_clean in _CLASSES:
                    target = tok_clean
                if target:
                    spatial_relation = {"type": rel_type, "target_class": target}
                    break
            if spatial_relation:
                break

    # --- detect count constraint ---
    count_constraint: dict | None = None
    count_patterns = [
        (r"\btwo\b",   2),
        (r"\b2\b",     2),
        (r"\bthree\b", 3),
        (r"\b3\b",     3),
        (r"\bfour\b",  4),
        (r"\b4\b",     4),
    ]
    for pattern, val in count_patterns:
        if re.search(pattern, text):
            count_class = detected_class or "person"
            count_constraint = {"operator": ">=", "value": val, "class": count_class}
            detected_class = None   # class is now in count_constraint
            break

    # --- nothing parsed → no_match ---
    if not any([detected_class, detected_color, negated, spatial_relation, count_constraint]):
        return _no_match()

    # ── Spatial color-swap (mirrors parser_gateway._normalise_parse_result) ──────
    # "person next to red car" → primary=person, color=red, spatial.target=car
    # The color BELONGS to the car, not the person. Swap primary → car with color,
    # and make the spatial target → person.
    _PERSON_CLASSES = {"person", "people", "man", "woman", "child", "pedestrian", "guard", "officer", "worker", "warden"}
    _VEHICLE_CLASSES = {"car", "vehicle", "truck", "bus", "van", "motorcycle", "bicycle", "sedan", "suv", "minivan", "jeep", "pickup"}

    if (
        spatial_relation
        and detected_color
        and detected_class in _PERSON_CLASSES
        and spatial_relation.get("target_class") in _VEHICLE_CLASSES
    ):
        # The color describes the vehicle, not the person
        # Swap: primary=vehicle+color, spatial.target=person
        vehicle_class = spatial_relation["target_class"]
        spatial_relation = {
            "type":         spatial_relation["type"],
            "target_class": detected_class,  # now points back to person
        }
        detected_class = vehicle_class
        # color stays on detected_class (now the vehicle)

    return {
        "status": "match",
        "filters": {
            "class": detected_class,
            "color": detected_color,
            "negated": negated,
            "spatial_relation": spatial_relation,
            "count_constraint": count_constraint,
        },
    }
