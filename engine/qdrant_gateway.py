"""
engine/qdrant_gateway.py — Qdrant client factory for Odysseus Part 3.

Controls whether the stub in-memory client or a real Qdrant connection is used.
To swap in the real collection, set USE_STUB_QDRANT = false in .env (or config.py):

    # TODO: SWAP FOR ACHILLES — set USE_STUB_QDRANT = False in .env
    USE_STUB_QDRANT = false
    QDRANT_HOST     = <real host>
    QDRANT_PORT     = 6333
    QDRANT_COLLECTION = video_objects

No other file needs to change.
"""

from __future__ import annotations

import logging

import config

logger = logging.getLogger(__name__)


def get_qdrant_client():
    """
    Return a Qdrant client.

    - USE_STUB_QDRANT=True  (default) → in-memory QdrantClient with seeded stub data
    - USE_STUB_QDRANT=False            → real QdrantClient(host, port, api_key)
    """
    if config.USE_STUB_QDRANT:
        logger.debug("qdrant_gateway: using in-memory stub client.")
        from engine.stub_data import get_stub_client
        return get_stub_client()

    logger.info(
        "qdrant_gateway: connecting to real Qdrant at %s:%d.",
        config.QDRANT_HOST, config.QDRANT_PORT,
    )
    from qdrant_client import QdrantClient
    return QdrantClient(
        host=config.QDRANT_HOST,
        port=config.QDRANT_PORT,
        api_key=config.QDRANT_API_KEY or None,
        timeout=10,
    )


def get_collection_name() -> str:
    """Return the Qdrant collection name appropriate for the current mode."""
    if config.USE_STUB_QDRANT:
        return config.STUB_COLLECTION
    return config.QDRANT_COLLECTION


def make_judge_collection_name() -> str:
    """
    Return a unique ephemeral collection name for a judge/evaluator session.

    Format: judge_session_<uuid4>
    Example: judge_session_3f2a1b4c-...

    Each call returns a new UUID — callers are responsible for creating the
    collection and passing the name to seed_stub_collection() / upsert().
    """
    import uuid
    return f"{config.JUDGE_SESSION_PREFIX}{uuid.uuid4()}"


def drop_old_judge_sessions(client) -> list[str]:
    """
    Drop ALL judge_session_* collections from the given Qdrant client.

    Call this once on app startup to clean up sessions from previous runs.
    Qdrant in-memory has no per-collection created_at metadata, so we drop
    all judge sessions unconditionally (acceptable for demo/eval use).

    Returns
    -------
    list[str]
        Names of collections that were dropped.
    """
    existing = [c.name for c in client.get_collections().collections]
    dropped  = []
    for name in existing:
        if name.startswith(config.JUDGE_SESSION_PREFIX):
            try:
                client.delete_collection(name)
                dropped.append(name)
                logger.info("qdrant_gateway: dropped judge session collection %r", name)
            except Exception as exc:  # noqa: BLE001
                logger.warning("qdrant_gateway: failed to drop %r — %s", name, exc)
    if not dropped:
        logger.debug("qdrant_gateway: no judge session collections to drop.")
    return dropped
