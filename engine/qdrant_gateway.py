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
