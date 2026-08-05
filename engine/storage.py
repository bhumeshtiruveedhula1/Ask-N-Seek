"""
engine/storage.py — SQLite storage layer for Ask-N-Seek.

Replaces Qdrant. Stores structured detections (class, color, bbox,
spatial_relations) and searches with WHERE filters — no vectors, no
dummy embeddings, no connection issues.

DB location: <project_root>/asknseek.db
"""
from __future__ import annotations

import json
import logging
import os
import sqlite3
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Derive project root from this file's location:
#   engine/storage.py  →  engine/  →  fresh_clone/
_ENGINE_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_ENGINE_DIR)
DB_PATH = os.path.join(_PROJECT_ROOT, "asknseek.db")

# ---------------------------------------------------------------------------
# Color family expansion (mirrors search.py logic — keep in sync)
# ---------------------------------------------------------------------------
_COLOR_FAMILIES: dict[str, list[str]] = {
    "blue":   ["blue", "dark blue", "light blue", "navy"],
    "red":    ["red", "dark red", "orange-red"],
    "green":  ["green", "light green", "dark green", "olive"],
    "yellow": ["yellow", "dark yellow", "gold"],
    "purple": ["purple", "pink", "hot pink"],
    "gray":   ["gray", "light gray", "dark gray", "charcoal"],
    "black":  ["black"],
    "white":  ["white"],
    "orange": ["orange", "orange-red"],
    "brown":  ["brown", "beige", "tan"],
    "silver": ["silver"],
    "gold":   ["gold"],
}


# ---------------------------------------------------------------------------
# Connection
# ---------------------------------------------------------------------------

def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    # Enable WAL mode for better concurrent read performance
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


# ---------------------------------------------------------------------------
# Schema initialisation
# ---------------------------------------------------------------------------

def init_db() -> None:
    """Create tables and indexes if they don't already exist."""
    conn = get_conn()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS detections (
            id                TEXT PRIMARY KEY,
            video_id          TEXT NOT NULL,
            timestamp         REAL NOT NULL,
            scene_id          INTEGER DEFAULT 0,
            frame_index       INTEGER DEFAULT 0,
            class_name        TEXT NOT NULL,
            color             TEXT,
            confidence        REAL DEFAULT 0.0,
            bbox              TEXT DEFAULT '[]',
            spatial_relations TEXT DEFAULT '[]'
        )
    """)
    # Indexes for the most common WHERE predicates
    conn.execute("CREATE INDEX IF NOT EXISTS idx_class    ON detections(class_name)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_color    ON detections(color)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_video    ON detections(video_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_ts       ON detections(timestamp)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_frame    ON detections(video_id, frame_index)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_cls_col  ON detections(class_name, color)")
    conn.commit()
    conn.close()
    logger.debug("SQLite DB initialised at %s", DB_PATH)


# ---------------------------------------------------------------------------
# Write
# ---------------------------------------------------------------------------

def insert_detections(video_id: str, detections: List[Dict[str, Any]]) -> int:
    """
    Bulk-insert (or replace) detections for one video.

    Returns the number of rows inserted.
    """
    init_db()
    conn = get_conn()
    count = 0
    for d in detections:
        row_id = (
            d.get("id")
            or f"{video_id}_{d.get('timestamp', 0)}_{d.get('frame_index', 0)}_{count}"
        )
        conn.execute(
            """
            INSERT OR REPLACE INTO detections
              (id, video_id, timestamp, scene_id, frame_index,
               class_name, color, confidence, bbox, spatial_relations)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                row_id,
                video_id,
                float(d.get("timestamp", 0)),
                int(d.get("scene_id", 0)),
                int(d.get("frame_index", 0)),
                str(d.get("class_name", "unknown")),
                d.get("color") or None,
                float(d.get("confidence", 0.0)),
                json.dumps(d.get("bbox", [])),
                json.dumps(d.get("spatial_relations", [])),
            ),
        )
        count += 1
    conn.commit()
    conn.close()
    logger.info("Inserted %d detections for video_id=%s", count, video_id)
    return count


def delete_video(video_id: str) -> None:
    """Remove all detections for a given video."""
    init_db()
    conn = get_conn()
    conn.execute("DELETE FROM detections WHERE video_id = ?", (video_id,))
    conn.commit()
    conn.close()
    logger.info("Deleted all detections for video_id=%s", video_id)


# ---------------------------------------------------------------------------
# Read / Search
# ---------------------------------------------------------------------------

def search_detections(
    class_name: Optional[str] = None,
    color: Optional[str] = None,
    negated_classes: Optional[List[str]] = None,
    video_id: Optional[str] = None,
    limit: int = 500,
) -> List[Dict[str, Any]]:
    """
    Search detections with structured filters.

    Parameters
    ----------
    class_name      Primary class to filter on (e.g. "car").
    color           Color query — expanded via color-family matching.
    negated_classes Classes that must NOT appear in the same frame.
    video_id        Restrict to a single ingested video.
    limit           Max rows returned before Python-level grouping.

    Returns
    -------
    List of detection dicts with bbox and spatial_relations deserialized.
    """
    init_db()
    conn = get_conn()

    sql = "SELECT * FROM detections WHERE 1=1"
    params: list[Any] = []

    if video_id:
        sql += " AND video_id = ?"
        params.append(video_id)

    if class_name:
        sql += " AND class_name = ?"
        params.append(class_name)

    if color:
        family = _COLOR_FAMILIES.get(color, [color])
        placeholders = ",".join("?" * len(family))
        sql += f" AND color IN ({placeholders})"
        params.extend(family)

    # Negation: exclude frames (video_id + frame_index) that contain the
    # negated class anywhere in that frame — not just among the filtered rows.
    if negated_classes:
        for neg_cls in negated_classes:
            sql += (
                " AND (video_id, frame_index) NOT IN ("
                "  SELECT video_id, frame_index FROM detections"
                "  WHERE class_name = ? AND confidence >= 0.40"
                ")"
            )
            params.append(neg_cls)

    sql += " ORDER BY confidence DESC LIMIT ?"
    params.append(limit)

    rows = conn.execute(sql, params).fetchall()
    conn.close()

    results = []
    for row in rows:
        r = dict(row)
        # Deserialize JSON blobs
        r["bbox"] = json.loads(r["bbox"]) if r.get("bbox") else []
        r["spatial_relations"] = (
            json.loads(r["spatial_relations"]) if r.get("spatial_relations") else []
        )
        results.append(r)

    return results


def get_all_in_frames(
    video_id: str,
    frame_indices: List[int],
) -> Dict[int, List[Dict[str, Any]]]:
    """
    Fetch ALL detections (any class) in the given frames of a video.
    Used for negation checking — we need to see every object in a frame,
    not just the candidate class.

    Returns dict: frame_index → list[detection_dict]
    """
    if not frame_indices:
        return {}
    init_db()
    conn = get_conn()
    placeholders = ",".join("?" * len(frame_indices))
    sql = (
        f"SELECT * FROM detections WHERE video_id = ? "
        f"AND frame_index IN ({placeholders})"
    )
    rows = conn.execute(sql, [video_id] + list(frame_indices)).fetchall()
    conn.close()

    by_frame: Dict[int, List[Dict[str, Any]]] = {}
    for row in rows:
        r = dict(row)
        r["bbox"] = json.loads(r["bbox"]) if r.get("bbox") else []
        r["spatial_relations"] = (
            json.loads(r["spatial_relations"]) if r.get("spatial_relations") else []
        )
        by_frame.setdefault(r["frame_index"], []).append(r)
    return by_frame


# ---------------------------------------------------------------------------
# Metadata helpers
# ---------------------------------------------------------------------------

def get_videos() -> List[str]:
    """Return all video_ids that have been ingested."""
    init_db()
    conn = get_conn()
    rows = conn.execute(
        "SELECT DISTINCT video_id FROM detections ORDER BY rowid DESC"
    ).fetchall()
    conn.close()
    return [r[0] for r in rows]


def get_latest_video_id() -> Optional[str]:
    """Return the most-recently-ingested video_id, or None."""
    init_db()
    conn = get_conn()
    row = conn.execute(
        "SELECT video_id FROM detections ORDER BY rowid DESC LIMIT 1"
    ).fetchone()
    conn.close()
    return row[0] if row else None


def get_class_counts(video_id: Optional[str] = None) -> Dict[str, int]:
    """Return {class_name: count} ordered by count descending."""
    init_db()
    conn = get_conn()
    if video_id:
        rows = conn.execute(
            "SELECT class_name, COUNT(*) as cnt FROM detections "
            "WHERE video_id = ? GROUP BY class_name ORDER BY cnt DESC",
            (video_id,),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT class_name, COUNT(*) as cnt FROM detections "
            "GROUP BY class_name ORDER BY cnt DESC"
        ).fetchall()
    conn.close()
    return {r[0]: r[1] for r in rows}


def get_colors_for_class(
    class_name: str,
    video_id: Optional[str] = None,
) -> List[str]:
    """Return distinct colors stored for a given class."""
    init_db()
    conn = get_conn()
    if video_id:
        rows = conn.execute(
            "SELECT DISTINCT color FROM detections "
            "WHERE class_name = ? AND video_id = ? AND color IS NOT NULL",
            (class_name, video_id),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT DISTINCT color FROM detections "
            "WHERE class_name = ? AND color IS NOT NULL",
            (class_name,),
        ).fetchall()
    conn.close()
    return [r[0] for r in rows]
