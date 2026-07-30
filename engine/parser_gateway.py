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


def _normalise_parse_result(result) -> dict:
    """
    Convert Achilles's ParseResult dataclass to the Odysseus stub dict shape.

    BRANCH A: qdrant_filter empty + unresolved_tokens non-empty
              → {"status": "no_match", "filters": {}}
    BRANCH B: qdrant_filter non-empty (unresolved_tokens may still be present)
              → {"status": "match", "filters": <qdrant_filter>}
    """
    # Handle plain dict (stub parser or already-normalised result)
    if isinstance(result, dict):
        return result

    # Achilles ParseResult dataclass — extract via attribute access
    qdrant_filter = getattr(result, "qdrant_filter", {}) or {}
    unresolved    = getattr(result, "unresolved_tokens", []) or []

    # BRANCH A: no usable filter, content words unresolved → short-circuit
    if not qdrant_filter and unresolved:
        logger.debug(
            "parser_gateway: BRANCH A — empty filter + unresolved=%s → no_match",
            unresolved,
        )
        return {"status": "no_match", "filters": {}}

    # BRANCH B: at least one filter constraint present → proceed to Qdrant
    logger.debug(
        "parser_gateway: BRANCH B — filter=%s  unresolved=%s → match",
        list(qdrant_filter.keys()), unresolved,
    )
    return {"status": "match", "filters": qdrant_filter}


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
