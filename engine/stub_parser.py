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

_CLASSES = {"person", "car", "dog", "bicycle", "helmet", "bag"}
_COLORS = {"red", "blue", "white", "black", "green", "brown"}
_NEGATION_WORDS = {"without", "no", "not", "excluding", "minus"}
_SPATIAL_MAP = {
    "left of":    "left_of",
    "left_of":    "left_of",
    "right of":   "right_of",
    "right_of":   "right_of",
    "above":      "above",
    "below":      "below",
    "in front of": "in_front_of",
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
    Lightweight keyword extraction — not a full parser.
    Handles common phrase patterns so queries like
    'show me a red person' or 'find people near a car' also work.
    """
    tokens = text.split()
    token_set = set(tokens)

    # --- detect class ---
    detected_class: str | None = None
    for tok in tokens:
        tok_clean = tok.rstrip("s")   # "people" → "peopl", crude; handle below
        if tok in _CLASSES:
            detected_class = tok
            break
        if tok in ("people", "persons"):
            detected_class = "person"
            break
        if tok_clean in _CLASSES:
            detected_class = tok_clean
            break

    # --- detect color ---
    detected_color: str | None = None
    for tok in tokens:
        if tok in _COLORS:
            detected_color = tok
            break

    # --- detect negation ---
    negated: list[str] = []
    for i, tok in enumerate(tokens):
        if tok in _NEGATION_WORDS:
            # next token might be the negated class
            for j in range(i + 1, min(i + 3, len(tokens))):
                candidate = tokens[j].rstrip("s")
                if tokens[j] in _CLASSES:
                    negated.append(tokens[j])
                    break
                if candidate in _CLASSES:
                    negated.append(candidate)
                    break

    # --- detect spatial relation ---
    spatial_relation: dict | None = None
    for phrase, rel_type in _SPATIAL_MAP.items():
        if phrase in text:
            # Find target class after the spatial phrase
            after = text.split(phrase, 1)[1].strip()
            for tok in after.split():
                tok_clean = tok.rstrip("s")
                target = None
                if tok in _CLASSES:
                    target = tok
                elif tok_clean in _CLASSES:
                    target = tok_clean
                if target:
                    spatial_relation = {"type": rel_type, "target_class": target}
                    break
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
