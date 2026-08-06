"""
engine/session_db.py — Lightweight SQLite session memory for the Chat Engine.

Each chat session is keyed by session_id (= video_id from the frontend).
Stores the rolling active_filters dict, the timestamp of the last successful
match (for temporal follow-up queries), and a clarification-pending flag.

Schema
------
sessions (
    session_id              TEXT  PRIMARY KEY,
    active_filters          TEXT  DEFAULT '{}',
    last_matched_timestamp  REAL  DEFAULT NULL,
    awaiting_clarification  INTEGER DEFAULT 0,
    updated_at              TEXT  DEFAULT CURRENT_TIMESTAMP
)

100% offline -- no external dependencies beyond Python stdlib.
"""
from __future__ import annotations

import json
import logging
import os
import sqlite3
from typing import Any

logger = logging.getLogger(__name__)

_ENGINE_DIR   = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_ENGINE_DIR)
_DB_PATH      = os.path.join(_PROJECT_ROOT, "chat_sessions.db")


def _get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(_DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def _init_db() -> None:
    conn = _get_conn()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS sessions (
            session_id              TEXT    PRIMARY KEY,
            active_filters          TEXT    NOT NULL DEFAULT '{}',
            last_matched_timestamp  REAL    DEFAULT NULL,
            awaiting_clarification  INTEGER NOT NULL DEFAULT 0,
            updated_at              TEXT    NOT NULL DEFAULT (DATETIME('now'))
        )
    """)
    conn.commit()
    conn.close()


def get_session(session_id: str) -> dict[str, Any]:
    """Return session state dict; fresh defaults if session does not exist yet."""
    _init_db()
    conn = _get_conn()
    row = conn.execute(
        "SELECT active_filters, last_matched_timestamp, awaiting_clarification "
        "FROM sessions WHERE session_id = ?",
        (session_id,),
    ).fetchone()
    conn.close()

    if row is None:
        return {"active_filters": {}, "last_matched_timestamp": None, "awaiting_clarification": False}

    return {
        "active_filters":         json.loads(row["active_filters"] or "{}"),
        "last_matched_timestamp": row["last_matched_timestamp"],
        "awaiting_clarification": bool(row["awaiting_clarification"]),
    }


def update_session(
    session_id: str,
    active_filters: dict | None = None,
    last_matched_timestamp: float | None = None,
    awaiting_clarification: bool | None = None,
) -> None:
    """Upsert session; None for any arg means keep existing value."""
    _init_db()
    conn = _get_conn()
    row = conn.execute(
        "SELECT active_filters, last_matched_timestamp, awaiting_clarification "
        "FROM sessions WHERE session_id = ?",
        (session_id,),
    ).fetchone()

    if row is None:
        ex_f, ex_ts, ex_aw = {}, None, False
    else:
        ex_f  = json.loads(row["active_filters"] or "{}")
        ex_ts = row["last_matched_timestamp"]
        ex_aw = bool(row["awaiting_clarification"])

    new_f  = active_filters          if active_filters          is not None else ex_f
    new_ts = last_matched_timestamp  if last_matched_timestamp  is not None else ex_ts
    new_aw = awaiting_clarification  if awaiting_clarification  is not None else ex_aw

    conn.execute(
        """
        INSERT INTO sessions
            (session_id, active_filters, last_matched_timestamp,
             awaiting_clarification, updated_at)
        VALUES (?, ?, ?, ?, DATETIME('now'))
        ON CONFLICT(session_id) DO UPDATE SET
            active_filters         = excluded.active_filters,
            last_matched_timestamp = excluded.last_matched_timestamp,
            awaiting_clarification = excluded.awaiting_clarification,
            updated_at             = DATETIME('now')
        """,
        (session_id, json.dumps(new_f), new_ts, int(new_aw)),
    )
    conn.commit()
    conn.close()
    logger.debug("session_db: updated session=%s", session_id)


def clear_session(session_id: str) -> None:
    """Delete all state for the given session (new video = fresh context)."""
    _init_db()
    conn = _get_conn()
    conn.execute("DELETE FROM sessions WHERE session_id = ?", (session_id,))
    conn.commit()
    conn.close()
    logger.info("session_db: cleared session=%s", session_id)


def clear_filters_only(session_id: str) -> None:
    """Reset active_filters to {} while keeping last_matched_timestamp."""
    session = get_session(session_id)
    update_session(
        session_id,
        active_filters={},
        awaiting_clarification=False,
        last_matched_timestamp=session.get("last_matched_timestamp"),
    )
