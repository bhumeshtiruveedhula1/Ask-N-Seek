"""
engine/query_cache.py — In-process query result cache for Ask-N-Seek.

Eliminates redundant Qdrant searches when the same query + collection
is submitted more than once within the same Python process lifetime.

Design:
  - Key  : "{query.strip().lower()}|{collection_name}"
  - Value: the final 7-tuple yielded by process_query()
  - TTL  : none — cache lives until the process exits or a new video
           is ingested (cleared by _start_ingestion on completion).
  - Thread safety: dict is GIL-protected; reads/writes are atomic for CPython.
"""
from __future__ import annotations


class QueryCache:
    """Simple in-memory cache for query results (final yield tuples)."""

    def __init__(self) -> None:
        self._store: dict[str, tuple] = {}

    def _key(self, query: str, collection_name: str) -> str:
        return f"{query.strip().lower()}|{collection_name}"

    def get(self, query: str, collection_name: str) -> tuple | None:
        """Return cached final yield tuple, or None if not present."""
        return self._store.get(self._key(query, collection_name))

    def set(self, query: str, collection_name: str, value: tuple) -> None:
        """Store a final yield tuple under the (query, collection) key."""
        self._store[self._key(query, collection_name)] = value

    def clear(self) -> None:
        """Clear all cached entries (call when a new video is ingested)."""
        self._store.clear()

    def __len__(self) -> int:
        return len(self._store)
