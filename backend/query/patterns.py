"""
patterns.py -- All Pattern Tables for the Rule-Based Query Parser
=================================================================
Architecture ref : 03_Architecture_Final.md ss3
TRD ref          : TRD-Build-Plan-Achilles.md ssPART 3

Contains the LOCKED pattern sets (do not extend without team sign-off):
  - NEGATION_PHRASES     : surface strings triggering negation
  - NEGATION_SUFFIX_RE   : -less suffix regex
  - COUNTING_PATTERNS    : regex + (operator, count) parse result
  - SPATIAL_TRIGGERS     : ONLY left_of / right_of -- NO near/beside
  - NUMBER_WORDS         : word -> digit for counting patterns
  - COLOR_VOCAB          : recognised color strings (matches CIELAB palette names)
  - FUZZY_MIN_LEN        : minimum token length to allow fuzzy matching

Fuzzy matching rule (TRD verbatim):
  "Levenshtein-distance fuzzy matching is fine for typos on longer trigger
   phrases, but must be EXCLUDED for short, common trigger words (e.g. 'no')"
  => Any token with len <= FUZZY_MIN_LEN is matched ONLY by exact string.
"""

from __future__ import annotations

import re

# ---------------------------------------------------------------------------
# Fuzzy matching guard
# ---------------------------------------------------------------------------
FUZZY_MIN_LEN: int = 4        # tokens <= this length: exact match ONLY
FUZZY_MAX_DIST: int = 1       # Levenshtein distance allowed for longer tokens

# ---------------------------------------------------------------------------
# Negation
# ---------------------------------------------------------------------------

NEGATION_PHRASES: list[str] = [
    # Multi-word first (order matters for greedy matching)
    "not wearing",
    "doesn't have",
    "does not have",
    "isn't wearing",
    "is not wearing",
    "not have",
    "missing",
    "lacking",
    "without",
    "bina",
    "no",
    "not",
]

# -less suffix regex (helmetless, maskless, vestless ...)
NEGATION_SUFFIX_RE: re.Pattern = re.compile(
    r"\b(\w+)less\b", re.IGNORECASE
)

# spaCy dependency labels that signal negation on a head token
NEGATION_DEP_LABELS: set[str] = {"neg"}

# ---------------------------------------------------------------------------
# Counting
# ---------------------------------------------------------------------------

NUMBER_WORDS: dict[str, int] = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
    "a couple of": 2, "a couple": 2,
    "a few": 3,
    "several": 4,
    "two or more": 2,
    "a pair": 2,
    "a pair of": 2,
}

# Each tuple: (regex_pattern, operator_key, count_group_index or None)
# operator_key: "gt" | "gte" | "lt" | "lte" | "eq"
COUNTING_PATTERNS: list[tuple[re.Pattern, str, int | None]] = [
    # "more than N"
    (re.compile(r"\bmore\s+than\s+(\d+|[a-z]+)\b", re.I), "gt",  1),
    # "at least N"
    (re.compile(r"\bat\s+least\s+(\d+|[a-z]+)\b",  re.I), "gte", 1),
    # "exactly N"
    (re.compile(r"\bexactly\s+(\d+|[a-z]+)\b",     re.I), "eq",  1),
    # "fewer than N"
    (re.compile(r"\bfewer\s+than\s+(\d+|[a-z]+)\b",re.I), "lt",  1),
    # "less than N"
    (re.compile(r"\bless\s+than\s+(\d+|[a-z]+)\b", re.I), "lt",  1),
    # "N or more"
    (re.compile(r"\b(\d+|[a-z]+)\s+or\s+more\b",   re.I), "gte", 1),
    # "N or fewer"
    (re.compile(r"\b(\d+|[a-z]+)\s+or\s+fewer\b",  re.I), "lte", 1),
    # "two or more" (word form -- catch before generic N or more)
    (re.compile(r"\btwo\s+or\s+more\b",             re.I), "gte", None),  # count=2
    # "a couple of"
    (re.compile(r"\ba\s+couple\s+of\b",             re.I), "gte", None),  # count=2
    # "a couple"
    (re.compile(r"\ba\s+couple\b",                  re.I), "gte", None),  # count=2
    # "a few"
    (re.compile(r"\ba\s+few\b",                     re.I), "gte", None),  # count=3
    # "several"
    (re.compile(r"\bseveral\b",                     re.I), "gte", None),  # count=4
]

# Hardcoded counts for group-index=None patterns (same order as above):
_COUNTING_FIXED_COUNTS: dict[int, int] = {
    7: 2,   # two or more
    8: 2,   # a couple of
    9: 2,   # a couple
    10: 3,  # a few
    11: 4,  # several
}

def parse_count_token(raw: str | None, pattern_idx: int) -> int:
    """Convert a regex capture group string to an integer count."""
    if raw is None:
        return _COUNTING_FIXED_COUNTS.get(pattern_idx, 1)
    raw = raw.strip().lower()
    if raw.isdigit():
        return int(raw)
    return NUMBER_WORDS.get(raw, 1)


# ---------------------------------------------------------------------------
# Spatial  (left_of / right_of / near — Architecture_Final §6 + Bug 2b fix)
# ---------------------------------------------------------------------------

SPATIAL_TRIGGERS: list[tuple[re.Pattern, str]] = [
    # LEFT / RIGHT — locked per Architecture_Final_v2.4.1 §6
    (re.compile(r"\bleft\s+of\b",              re.I), "left_of"),
    (re.compile(r"\bto\s+the\s+left\s+of\b",  re.I), "left_of"),
    (re.compile(r"\bon\s+the\s+left\s+of\b",   re.I), "left_of"),
    (re.compile(r"\bto\s+(?:its|the|a)\s+left\b",  re.I), "left_of"),
    (re.compile(r"\bright\s+of\b",             re.I), "right_of"),
    (re.compile(r"\bto\s+the\s+right\s+of\b", re.I), "right_of"),
    (re.compile(r"\bon\s+the\s+right\s+of\b",  re.I), "right_of"),
    (re.compile(r"\bto\s+(?:its|the|a)\s+right\b", re.I), "right_of"),

    # NEAR — re-enabled with relative diagonal threshold (Bug 2b fix)
    # spatial.py computes gap/diag < SPATIAL_NEAR_RATIO (default 0.15)
    (re.compile(r"\bnear\b",           re.I), "near"),
    (re.compile(r"\bnear\s+to\b",      re.I), "near"),
    (re.compile(r"\bnext\s+to\b",      re.I), "near"),
    (re.compile(r"\bbeside\b",         re.I), "near"),
    (re.compile(r"\bclose\s+to\b",     re.I), "near"),
]

# Still banned: touching/grabbing/holding/pulling/opening
# 2D IoU heuristics produce too many false positives on single-camera footage.
_BANNED_SPATIAL: list[str] = [
    "touching", "grabbing", "holding", "pulling", "opening",
]



# ---------------------------------------------------------------------------
# Color vocabulary (must match CIELAB palette names from color_extractor.py)
# ---------------------------------------------------------------------------

COLOR_VOCAB: frozenset[str] = frozenset([
    "white", "light gray", "gray", "dark gray", "black",
    "red", "dark red", "orange", "orange-red",
    "yellow", "dark yellow",
    "green", "light green", "dark green", "olive",
    "blue", "light blue", "dark blue", "navy",
    "purple", "pink", "hot pink",
    "brown", "beige", "tan",
    "silver", "gold",
])

# Aliases users commonly type that map to COLOR_VOCAB entries
COLOR_ALIASES: dict[str, str] = {
    "grey":        "gray",
    "grey":        "gray",
    "light grey":  "light gray",
    "dark grey":   "dark gray",
    "crimson":     "red",
    "scarlet":     "red",
    "maroon":      "dark red",
    "amber":       "orange",
    "khaki":       "tan",
    "ivory":       "white",
    "cream":       "beige",
    "violet":      "purple",
    "lavender":    "purple",
    "magenta":     "pink",
    "teal":        "green",
    "cyan":        "light blue",
    "indigo":      "dark blue",
    "charcoal":    "dark gray",
    "golden":      "gold",
}


def resolve_color(raw: str) -> str | None:
    """Resolve a raw color string to a canonical COLOR_VOCAB entry, or None."""
    raw_l = raw.lower().strip()
    if raw_l in COLOR_VOCAB:
        return raw_l
    if raw_l in COLOR_ALIASES:
        return COLOR_ALIASES[raw_l]
    return None
