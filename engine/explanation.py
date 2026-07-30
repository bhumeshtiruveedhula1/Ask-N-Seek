"""
engine/explanation.py — Templated explanation generator for Odysseus Part 3.

Generates a human-readable explanation string from a Result's explanation_facts.
NO model call, NO inference — pure string formatting from structured data.

Output format:
    "Matched because: {facts}. Confidence: {score:.2f}."

Fact ordering (set by _build_facts in search.py, mirrored here):
    1. {class} detected
    2. no {negated_class} detected
    3. {color} color confirmed
    4. {relation} {target_class}          (spatial)
    5. count satisfied: {op} {val} {cls}  (count constraint)

Edge cases:
    - Empty facts       → "Matched because: object detected. Confidence: {score:.2f}."
    - Confidence == 1.0 → shown as "1.00" (not "1.0")
    - Fact > 80 chars   → truncated with "…" to prevent UI overflow
"""

from __future__ import annotations

from engine.search import Result

_MAX_FACT_LEN: int = 80


def _truncate(fact: str) -> str:
    """Truncate a single fact string to _MAX_FACT_LEN characters."""
    if len(fact) <= _MAX_FACT_LEN:
        return fact
    return fact[: _MAX_FACT_LEN - 1] + "…"


def generate_explanation(result: Result) -> str:
    """
    Generate a templated explanation string for a search result.

    Facts are sourced only from result.explanation_facts — this function
    NEVER hallucinate information not already present in structured data.

    Parameters
    ----------
    result : Result
        A result from search_structured().

    Returns
    -------
    str
        Human-readable explanation, e.g.:
        "Matched because: person detected, no helmet detected, red color confirmed.
         Confidence: 0.89."
    """
    score = result.confidence_score
    facts = result.explanation_facts

    # Defensive: handle None, non-list, or empty
    if not isinstance(facts, list):
        facts = []

    # Filter out empty/whitespace-only strings and truncate long ones
    cleaned = [_truncate(f) for f in facts if isinstance(f, str) and f.strip()]

    if not cleaned:
        # Edge case: no facts → generic fallback (never return empty string)
        return f"Matched because: object detected. Confidence: {score:.2f}."

    facts_str = ", ".join(cleaned)
    return f"Matched because: {facts_str}. Confidence: {score:.2f}."
