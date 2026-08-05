"""
engine/parser_gateway.py — Dynamic parser dispatch for Odysseus Part 3.

Routes all parse_query() calls through the configured module/function.
To swap in Achilles's real parser, update config.py or .env only:

    PARSER_MODULE   = "backend.query.query_parser"
    PARSER_FUNCTION = "parse_query"

No other file needs to change.

=== Output shape normalisation (Step 4.3 — 2026-07-29) ===

Achilles's real parse_query() returns a ParseResult dataclass:

    ParseResult(
        raw_query         : str
        objects           : list[ObjectSpec]   # [{class_name, color, negated, ...}]
        spatial           : list[SpatialSpec]  # [{subject, relation, object_}]
        qdrant_filter     : dict               # Qdrant-ready must/must_not/spatial/counts
        unresolved_tokens : list[str]          # content words not matched to any vocab
    )

Odysseus's stub expects:

    {"status": "match" | "no_match", "filters": {...}}

This gateway normalises the two shapes and enforces the short-circuit rule:

  BRANCH A — short-circuit to no_match (never calls Qdrant):
    Condition: qdrant_filter is empty (no must/must_not/spatial/counts)
               AND unresolved_tokens is non-empty
    Rationale: the query had content words but none matched the vocabulary.
               There is no filter to run; returning results would be nonsense.

  BRANCH B — proceed to Qdrant:
    Condition: qdrant_filter is non-empty (at least one constraint present)
               unresolved_tokens may or may not be non-empty — e.g. spatial
               trigger words like "left" do not resolve to vocab nouns and
               will appear in unresolved_tokens even on a valid spatial query.
    Returns:  {"status": "match", "filters": <qdrant_filter dict>}

  BRANCH C — stub parser path (USE_STUB_QDRANT / fallback):
    Condition: configured parser returns a plain dict directly
               (engine.stub_parser.parse_query_stub)
    Returns:  the dict unchanged (already in {status, filters} shape)
"""

from __future__ import annotations

import dataclasses
import importlib
import logging

import config

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Bug 3 fix: Spatial subject sanitizer
# ---------------------------------------------------------------------------
# spaCy binds prepositions to the nearest noun, so "person in red shirt left
# of car" produces subject='shirt'. Since clothing always moves with the
# person who wears it, we redirect the spatial subject to 'person' whenever
# a person object is present in the same query.
_CLOTHING_ITEMS: frozenset[str] = frozenset({
    "shirt", "jacket", "coat", "suit", "dress", "skirt", "pants", "trousers",
    "shorts", "jeans", "hoodie", "sweater", "uniform", "hat", "cap", "helmet",
    "hardhat", "visor", "gloves", "boots", "shoes", "sneakers", "sandals",
    "belt", "tie", "scarf", "mask", "apron", "vest", "robe", "gown", "raincoat",
    "jumpsuit", "overalls", "leggings", "stockings", "socks", "swimsuit",
    "backpack", "bag", "handbag", "purse",
})


def _sanitize_spatial_subject(parse_result) -> None:
    """
    If spatial subject is a clothing/accessory item and 'person' is also in
    the query objects, redirect spatial subject to 'person'. Mutates in place.
    """
    spatial = getattr(parse_result, "spatial", None)
    if not spatial:
        return
    objects = getattr(parse_result, "objects", []) or []
    has_person = any(o.get("class_name") == "person" for o in objects)
    if not has_person:
        return
    for sp in spatial:
        if sp.get("subject") in _CLOTHING_ITEMS:
            sp["subject"] = "person"
            logger.debug(
                "parser_gateway: sanitized spatial subject → person (was clothing item)"
            )


def _sanitize_person_color(parse_result) -> None:
    """
    Strip color from 'person' when another object in the same query claims the
    same color. The color scanner sometimes binds to 'person' (leftmost noun)
    even when the color belongs to a vehicle or object further right.
    Only strips when another object shares the SAME color — leaves it alone if
    person is the sole colored object (e.g. 'person in red' is still valid).
    Mutates parse_result.objects in place.
    """
    objs = getattr(parse_result, "objects", None)
    if not objs or len(objs) < 2:
        return
    # Find person
    person_idx = None
    for i, obj in enumerate(objs):
        if obj.get("class_name") == "person":
            person_idx = i
            break
    if person_idx is None:
        return
    person_color = objs[person_idx].get("color")
    if not person_color:
        return
    # Strip only if another object shares the same color
    for i, obj in enumerate(objs):
        if i != person_idx and obj.get("color") == person_color:
            objs[person_idx]["color"] = None
            logger.debug(
                "parser_gateway: stripped color '%s' from person (shared with %s)",
                person_color, obj.get("class_name"),
            )
            return


def _normalise_parse_result(result) -> dict:
    """
    Convert Achilles's ParseResult dataclass → stub-flat dict shape.

    Output contract (matches search_structured's expected input):
        {
            "status":  "match" | "no_match",
            "filters": {
                "class":            str | None,      # primary positive class
                "color":            str | None,      # primary color attribute
                "negated":          list[str],        # classes that must NOT appear
                "spatial_relation": dict | None,      # {type, target_class}
                "count_constraint": dict | None,      # {class, op, value}
            }
        }

    Branch A: no objects resolved + unresolved_tokens non-empty → no_match
    Branch B: at least one object resolved → match, extract fields
    Branch C: plain dict (stub parser) → pass through unchanged
    """
    # Branch C: stub parser already returns plain dict — pass through unchanged
    if isinstance(result, dict):
        return result

    # Achilles ParseResult dataclass — extract via attribute access
    objects    = getattr(result, "objects",           []) or []
    spatial    = getattr(result, "spatial",           []) or []
    unresolved = getattr(result, "unresolved_tokens", []) or []

    # Branch A: nothing was resolved → no_match
    if not objects and unresolved:
        logger.debug(
            "parser_gateway: BRANCH A — no objects, unresolved=%s → no_match",
            unresolved,
        )
        return {"status": "no_match", "filters": {}}

    # Branch B: build stub-flat filters from ParseResult fields
    # Sanitize BEFORE selecting primary — these mutate result.objects in place.
    _sanitize_spatial_subject(result)
    _sanitize_person_color(result)

    # ── Pick primary object: most constrained wins ─────────────────────────
    # "person near red car" → search for red car, not generic person.
    # The frame with a red car also contains the person, so results are correct.
    # All person-roles (post SYNONYM_MAP at ingest) treated as person for selection.
    _PERSON_CLASSES = {
        "person", "man", "woman", "child", "people", "pedestrian",
        "firefighter", "traffic warden", "police", "officer", "soldier",
        "worker", "construction worker", "chef", "doctor", "nurse",
        "patient", "student", "teacher",
    }

    candidates = [o for o in objects if not o.get("negated")]
    if not candidates:
        candidates = list(objects)  # all negated — use all as fallback

    primary = None
    if len(candidates) == 1:
        primary = candidates[0]
    else:
        # Prefer: colored non-person, non-clothing object ("person near red car" → red car)
        for o in candidates:
            if (o.get("color")
                    and o.get("class_name") not in _PERSON_CLASSES
                    and o.get("class_name") not in _CLOTHING_ITEMS):
                primary = o
                break
        # Fallback: any non-person, non-clothing candidate ("person left of car" → car)
        if primary is None:
            for o in candidates:
                if (o.get("class_name") not in _PERSON_CLASSES
                        and o.get("class_name") not in _CLOTHING_ITEMS):
                    primary = o
                    break
        # Final fallback: first candidate ("person without helmet" → person)
        if primary is None:
            primary = candidates[0]

    class_filter = primary.get("class_name") if primary else None
    color_filter = primary.get("color")       if primary else None



    # Negated classes: all objects where negated=True
    negated_classes = [
        o["class_name"] for o in objects
        if o.get("negated") and o.get("class_name")
    ]

    # Spatial relation: first spatial spec if present
    spatial_relation = None
    if spatial:

        sp = spatial[0]
        sp_subject = sp.get("subject", "")   # e.g. "person" in "person near car"
        sp_object  = sp.get("object_", "")   # e.g. "car"
        spatial_relation = {
            "type":         sp.get("relation"),
            "target_class": sp_object,
        }
        # ── Spatial target swap ─────────────────────────────────────────
        # When gateway promotes sp_object (car) to primary for Qdrant search,
        # the spatial filter must point to sp_subject (person) — not car→car.
        # Without this swap, _has_spatial_relation checks car.near(car) which
        # never matches, so ALL candidate frames leak through unfiltered.
        if class_filter == sp_object and sp_subject and sp_subject != sp_object:
            spatial_relation["target_class"] = sp_subject

    # Count constraint: primary object's count fields if present
    count_constraint = None
    if primary.get("count_op") is not None:
        count_constraint = {
            "class": primary.get("class_name"),
            "op":    primary["count_op"],
            "value": primary.get("count_val"),
        }

    filters = {
        "class":            class_filter,
        "color":            color_filter,
        "negated":          negated_classes,
        "spatial_relation": spatial_relation,
        "count_constraint": count_constraint,
    }

    logger.debug(
        "parser_gateway: BRANCH B — class=%s color=%s negated=%s spatial=%s count=%s",
        class_filter, color_filter, negated_classes, spatial_relation, count_constraint,
    )
    return {"status": "match", "filters": filters}


def parse_query(query: str) -> dict:
    """
    Gateway function. Routes to the parser configured in config.py.

    Currently: engine.stub_parser.parse_query_stub (returns plain dict)
    After Achilles swap: set PARSER_MODULE=backend.query.query_parser
                             PARSER_FUNCTION=parse_query in .env

    Returns
    -------
    dict
        Normalised shape: {"status": "match"|"no_match", "filters": {...}}
    """
    module_path = config.PARSER_MODULE
    func_name   = config.PARSER_FUNCTION

    # TODO: SWAP FOR ACHILLES — set PARSER_MODULE / PARSER_FUNCTION in .env
    try:
        module = importlib.import_module(module_path)
        fn     = getattr(module, func_name)
    except (ImportError, AttributeError) as exc:
        logger.error(
            "parser_gateway: failed to load %s.%s — %s. "
            "Falling back to stub parser.",
            module_path, func_name, exc,
        )
        from engine.stub_parser import parse_query_stub
        return parse_query_stub(query)

    logger.debug("parser_gateway: dispatching to %s.%s", module_path, func_name)
    raw_result = fn(query)
    return _normalise_parse_result(raw_result)
