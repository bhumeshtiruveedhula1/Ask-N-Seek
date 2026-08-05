"""
engine/qdrant_gateway.py — DEPRECATED (replaced by engine/storage.py SQLite backend)

Kept ONLY to prevent ImportError in test_integration.py which imports
get_qdrant_client and get_collection_name for legacy contract tests.

All functions return safe no-op stubs. No Qdrant server is ever contacted.
Storage is handled entirely by engine/storage.py (SQLite, zero-config, persistent).
"""

from __future__ import annotations

import logging

import config

logger = logging.getLogger(__name__)


class _NoOpQdrantStub:
    """
    Minimal stub that satisfies the method-existence checks in test_integration.py
    (has_scroll, has_query_points / has_search, has_upsert).

    Never contacts a real Qdrant server. Returns empty results for all queries.
    """

    def scroll(self, collection_name: str = "", limit: int = 10, **_kwargs):
        return [], None

    def search(self, collection_name: str = "", **_kwargs):
        return []

    def query_points(self, collection_name: str = "", **_kwargs):
        return []

    def upsert(self, collection_name: str = "", points=None, **_kwargs):
        return None

    def create_collection(self, collection_name: str = "", **_kwargs):
        return None

    def delete_collection(self, collection_name: str = "", **_kwargs):
        return None

    def get_collections(self, **_kwargs):
        class _R:
            collections = []
        return _R()


_STUB_CLIENT = _NoOpQdrantStub()


def get_qdrant_client() -> _NoOpQdrantStub:
    """
    DEPRECATED — returns a no-op stub.
    All real search/ingest is handled by engine/storage.py (SQLite).
    """
    logger.debug("qdrant_gateway.get_qdrant_client(): returning no-op stub (SQLite backend active)")
    return _STUB_CLIENT


def get_collection_name() -> str:
    """
    DEPRECATED — returns the stub collection name constant.
    Collection concept no longer applies; video_id is the key in SQLite.
    """
    return config.STUB_COLLECTION


def cleanup_judge_sessions() -> None:
    """DEPRECATED — no-op. No Qdrant collections to clean up."""
    logger.debug("qdrant_gateway.cleanup_judge_sessions(): no-op (SQLite backend active)")
