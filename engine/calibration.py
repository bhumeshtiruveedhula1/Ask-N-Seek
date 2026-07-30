"""
engine/calibration.py — Threshold calibration harness for Odysseus Part 3.

Milestone 1: Harness exists and runs against stub data. Threshold is placeholder 0.5.
Milestone 2: Run against real indexed footage. Lock threshold. Update threshold_config.json.

Calibration procedure (per spec):
    1. Run 10 VALID queries. Record best confidence score per query.
    2. Run 5 NONSENSE queries. Record best confidence score per query.
    3. threshold = max(nonsense_scores) + margin (default: 0.05)
    4. Save to threshold_config.json.
    5. If valid_min < threshold, emit a loud WARNING.

Run standalone:
    python -m engine.calibration --data-source stub
    python -m engine.calibration --data-source real --output threshold_config.json
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

from qdrant_client import QdrantClient

from config import (
    PLACEHOLDER_THRESHOLD,
    STUB_COLLECTION,
    THRESHOLD_CONFIG_PATH,
    QDRANT_COLLECTION,
)
from engine.search import search_structured
from engine.stub_data import get_stub_client
from engine.stub_parser import parse_query_stub

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Parser function pointer
# ---------------------------------------------------------------------------
# TODO: SWAP FOR ACHILLES — replace parse_query_stub with Achilles's parser:
#   from achilles.parser import parse_query as _achilles_parse
#   _PARSE_FN = _achilles_parse
# (Or set PARSER_MODULE / PARSER_FUNCTION in config.py and use parser_gateway)
_PARSE_FN = parse_query_stub


# ---------------------------------------------------------------------------
# Calibration query sets (top-level constants per spec)
# ---------------------------------------------------------------------------

# 10 valid queries — representative of real use cases
VALID_QUERIES: list[str] = [
    "person in red",
    "person without helmet",
    "two people",
    "person left of car",
    "red car",
    "person in blue",
    "bicycle",
    "dog",
    "bag",
    "person",
]

# 5 nonsense queries — should return 0 results (or very low confidence)
NONSENSE_QUERIES: list[str] = [
    "purple elephant dancing",
    "flying car",
    "invisible dinosaur",
    "alien in a rocket",
    "mermaid singing",
]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def calibrate_threshold(
    client: QdrantClient | None = None,
    collection_name: str = STUB_COLLECTION,
    margin: float = 0.05,
    save: bool = True,
    output_path: Path | None = None,
    parse_fn=None,
) -> float:
    """
    Run the calibration procedure and return the computed threshold.

    Parameters
    ----------
    client : QdrantClient | None
        Qdrant client to query. If None, uses the in-memory stub client.
    collection_name : str
        Collection to run queries against.
    margin : float
        Safety margin added to max(nonsense_scores). Default 0.05.
    save : bool
        If True, writes result to output_path (or THRESHOLD_CONFIG_PATH).
    output_path : Path | None
        Override the default threshold_config.json path.
    parse_fn : callable | None
        Parser function pointer. Defaults to _PARSE_FN (stub parser).
        Pass a real parser here for production calibration.

    Returns
    -------
    float
        Calibrated threshold value.
    """
    if client is None:
        client = get_stub_client()
    if parse_fn is None:
        parse_fn = _PARSE_FN
    if output_path is None:
        output_path = THRESHOLD_CONFIG_PATH

    logger.info("Starting threshold calibration (margin=%.2f, collection=%s).",
                margin, collection_name)

    # -----------------------------------------------------------------------
    # Run valid queries
    # -----------------------------------------------------------------------
    valid_scores: list[float] = []
    for query in VALID_QUERIES:
        filter_dict = parse_fn(query)
        results = search_structured(filter_dict, client, collection_name)
        best = results[0].confidence_score if results else 0.0
        valid_scores.append(best)
        logger.debug("VALID  '%s' → best=%.3f", query, best)

    # -----------------------------------------------------------------------
    # Run nonsense queries
    # -----------------------------------------------------------------------
    nonsense_scores: list[float] = []
    for query in NONSENSE_QUERIES:
        filter_dict = parse_fn(query)
        results = search_structured(filter_dict, client, collection_name)
        best = results[0].confidence_score if results else 0.0
        nonsense_scores.append(best)
        logger.debug("NONSENSE '%s' → best=%.3f", query, best)

    # -----------------------------------------------------------------------
    # Compute threshold
    # -----------------------------------------------------------------------
    nonsense_max = max(nonsense_scores) if any(s > 0 for s in nonsense_scores) else 0.0
    valid_min    = min(valid_scores) if valid_scores else 0.0
    threshold    = round(nonsense_max + margin, 4)

    logger.info(
        "Calibration: nonsense_max=%.3f, valid_min=%.3f, margin=%.2f → threshold=%.4f",
        nonsense_max, valid_min, margin, threshold,
    )

    # Loud warning if threshold is too aggressive
    if valid_min < threshold:
        msg = (
            f"\n{'='*60}\n"
            f"⚠️  WARNING: threshold may be too aggressive!\n"
            f"   valid_min  = {valid_min:.4f}\n"
            f"   threshold  = {threshold:.4f}\n"
            f"   Some VALID queries score BELOW the threshold.\n"
            f"   Explainability will suffer — consider reducing margin.\n"
            f"{'='*60}\n"
        )
        print(msg, file=sys.stderr)
        logger.warning(msg.strip())

    # -----------------------------------------------------------------------
    # Persist with exact required JSON shape
    # -----------------------------------------------------------------------
    calibration_data = {
        "threshold":     threshold,
        "calibrated_at": datetime.now(timezone.utc).isoformat(),
        "margin":        margin,
        "nonsense_max":  nonsense_max,
        "valid_min":     valid_min,
        # Extended fields (kept for traceability — not required by spec)
        "valid_scores":     valid_scores,
        "nonsense_scores":  nonsense_scores,
        "valid_queries":    VALID_QUERIES,
        "nonsense_queries": NONSENSE_QUERIES,
        "collection":       collection_name,
        "note": (
            "Milestone 2 stub run — recalibrate against real footage for production."
            if collection_name == STUB_COLLECTION
            else "Production calibration against real Qdrant collection."
        ),
    }

    if save:
        output_path = Path(output_path)
        output_path.write_text(json.dumps(calibration_data, indent=2), encoding="utf-8")
        logger.info("Saved threshold config → %s (threshold=%.4f)", output_path, threshold)

    return threshold


def load_or_default() -> float:
    """Alias for config.load_threshold() — kept for backward compatibility."""
    from config import load_threshold
    return load_threshold()


# ---------------------------------------------------------------------------
# CLI entry-point
# ---------------------------------------------------------------------------

def _build_cli() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m engine.calibration",
        description=(
            "Odysseus Part 3 — Threshold Calibration Harness\n"
            "Runs 10 valid + 5 nonsense queries against a Qdrant collection\n"
            "and writes threshold_config.json."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--data-source",
        choices=["stub", "real"],
        default="stub",
        help=(
            "stub: use in-memory stub data (default, always works).\n"
            "real: connect to real Qdrant using QDRANT_HOST/PORT in config.py."
        ),
    )
    parser.add_argument(
        "--output",
        default=str(THRESHOLD_CONFIG_PATH),
        help=f"Path to write threshold_config.json (default: {THRESHOLD_CONFIG_PATH})",
    )
    parser.add_argument(
        "--margin",
        type=float,
        default=0.05,
        help="Safety margin added to max(nonsense_scores). Default: 0.05",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable DEBUG logging.",
    )
    return parser


if __name__ == "__main__":
    args = _build_cli().parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)-8s %(name)s  %(message)s",
    )

    output_path = Path(args.output)

    if args.data_source == "stub":
        print(f"\n{'-'*50}")
        print("Data source: in-memory STUB (engine.stub_data)")
        print(f"{'-'*50}")
        client         = get_stub_client()
        collection     = STUB_COLLECTION

    else:  # real
        print(f"\n{'-'*50}")
        print("Data source: REAL Qdrant")
        print(f"   Collection : {QDRANT_COLLECTION}")
        print(f"{'-'*50}")
        import config as _cfg
        from qdrant_client import QdrantClient as _QC
        client     = _QC(
            host=_cfg.QDRANT_HOST,
            port=_cfg.QDRANT_PORT,
            api_key=_cfg.QDRANT_API_KEY or None,
            timeout=10,
        )
        collection = QDRANT_COLLECTION

    print("\nRunning calibration queries...\n")

    # Print per-query scores
    print(f"{'Query':<35} {'Best Score':>10}  Type")
    print("-" * 55)

    for q in VALID_QUERIES:
        fd      = _PARSE_FN(q)
        results = search_structured(fd, client, collection)
        score   = results[0].confidence_score if results else 0.0
        print(f"  {q:<33} {score:>10.3f}  [valid]")

    for q in NONSENSE_QUERIES:
        fd      = _PARSE_FN(q)
        results = search_structured(fd, client, collection)
        score   = results[0].confidence_score if results else 0.0
        print(f"  {q:<33} {score:>10.3f}  [nonsense]")

    print("-" * 55)

    t = calibrate_threshold(
        client=client,
        collection_name=collection,
        margin=args.margin,
        save=True,
        output_path=output_path,
    )

    print(f"\n{'='*50}")
    print(f"  Calibrated threshold : {t:.4f}")
    print(f"  Written to           : {output_path}")
    print(f"{'='*50}\n")

