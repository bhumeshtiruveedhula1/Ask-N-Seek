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
# Color family expansion — maps canonical query color → all DB color values that should match.
# CRITICAL: these values MUST match what color_extractor.py's CIELAB palette stores.
# DB audit shows white/silver cars are stored as 'silver' or 'light gray' (L>=75 achromatic),
# and dark cars stored as 'black' or 'dark gray'.
# ---------------------------------------------------------------------------
_COLOR_FAMILIES: dict[str, list[str]] = {
    "blue":   ["blue", "dark blue", "light blue", "navy"],
    "red":    ["red", "dark red", "orange-red"],
    "green":  ["green", "light green", "dark green", "olive"],
    "yellow": ["yellow", "dark yellow", "gold"],
    "purple": ["purple", "pink", "hot pink"],
    "gray":   ["gray", "light gray", "dark gray", "charcoal"],
    # white cars → CIELAB stores as 'silver' (L~80) or 'light gray' (L~75)
    "white":  ["white", "silver", "light gray"],
    # black cars → CIELAB stores as 'black' (L~10) or 'dark gray' (L~35)
    "black":  ["black", "dark gray"],
    "orange": ["orange", "orange-red"],
    "brown":  ["brown", "beige", "tan"],
    # silver is its own family but overlaps with white/light gray
    "silver": ["silver", "light gray", "white"],
    "gold":   ["gold", "yellow"],
}

# ---------------------------------------------------------------------------
# Class family expansion — maps broad user-query class → all YOLO sub-labels.
# CRITICAL: YOLO-World detects 'sedan','minivan','jeep' NOT just 'car'.
# When user says "white car", class filter must also cover sedan/minivan etc.
# ---------------------------------------------------------------------------
_CLASS_FAMILIES: dict[str, list[str]] = {
    # ── Vehicles (unchanged) ─────────────────────────────────────────────────
    "car":        ["car", "sedan", "minivan", "suv", "jeep", "pickup",
                   "hatchback", "van", "coupe", "auto", "vehicle", "automobile"],
    "truck":      ["truck", "pickup", "lorry", "van", "cargo"],
    "bus":        ["bus", "minibus", "coach"],
    "motorcycle": ["motorcycle", "motorbike", "scooter", "bike"],
    "bicycle":    ["bicycle", "bike", "cycle"],
    # ── People (unchanged) ───────────────────────────────────────────────────
    "person":     ["person", "man", "woman", "child", "boy", "girl",
                   "pedestrian", "human", "people", "guard", "officer",
                   "worker", "warden", "suspect", "intruder"],
    # ── Fire safety ──────────────────────────────────────────────────────────
    "extinguisher":      ["extinguisher", "fire extinguisher"],
    "fire extinguisher": ["extinguisher", "fire extinguisher"],
    # ── Office / seminar hall / building objects ──────────────────────────────
    "chair":    ["chair", "seat", "stool", "armchair"],
    "bench":    ["bench", "seat"],
    "table":    ["table", "desk", "counter"],
    "bottle":   ["bottle", "water bottle", "flask"],
    "trash":    ["trashcan", "trash can", "bin", "dustbin", "garbage",
                 "waste bin", "rubbish bin", "trash bin"],
    "bin":      ["bin", "trashcan", "dustbin", "waste bin", "trash can"],
    "bucket":   ["bucket", "pail"],
    "fan":      ["fan", "electric fan", "ceiling fan"],
    "speaker":  ["speaker", "loudspeaker", "audio speaker"],
    "curtain":  ["curtain", "drape", "blind"],
    "window":   ["window", "glass window"],
    "stage":    ["stage", "platform", "podium", "dais"],
    # ── Personal items (common in offices/halls) ─────────────────────────────
    "bag":      ["bag", "backpack", "handbag", "suitcase", "luggage", "briefcase"],
    "phone":    ["phone", "mobile phone", "cell phone", "smartphone"],
    "laptop":   ["laptop", "notebook", "computer"],
}


# ---------------------------------------------------------------------------
# Connection
# ---------------------------------------------------------------------------

def get_conn() -> sqlite3.Connection:
    # check_same_thread=False: FastAPI dispatches requests across threads.
    # WAL mode: concurrent reads don't block writes.
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
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
            color             TEXT DEFAULT '',
            confidence        REAL DEFAULT 0.0,
            bbox              TEXT DEFAULT '[]',
            bbox_area         REAL DEFAULT 0.0,
            spatial_relations TEXT DEFAULT '[]'
        )
    """)
    # Indexes for the most common WHERE predicates
    conn.execute("CREATE INDEX IF NOT EXISTS idx_class    ON detections(class_name)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_color    ON detections(color)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_video    ON detections(video_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_ts       ON detections(timestamp)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_frame ON detections(video_id, frame_index)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_class  ON detections(video_id, class_name)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_conf   ON detections(confidence)")
    # Safe migration: add bbox_area column if missing (ALTER TABLE ADD COLUMN is idempotent with try/except)
    try:
        conn.execute("ALTER TABLE detections ADD COLUMN bbox_area REAL DEFAULT 0.0")
    except Exception:
        pass  # column already exists
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
    spatial_relation: Optional[Dict[str, Any]] = None,  # passed-through; used by search.py spatial filter
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
        # Expand broad class to all YOLO sub-labels (e.g. 'car' → sedan, minivan...)
        cls_family = _CLASS_FAMILIES.get(class_name, [class_name])
        placeholders_c = ",".join("?" * len(cls_family))
        sql += f" AND class_name IN ({placeholders_c})"
        params.extend(cls_family)

    if color:
        # Normalize case: 'Blue' -> 'blue', skip non-color values
        color_key = color.strip().lower()
        if color_key not in ('any color', 'any', 'skip', 'unknown', ''):
            family = _COLOR_FAMILIES.get(color_key, [color_key])
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

    # Confidence floor: ignore very low-confidence background detections
    sql += " AND confidence >= 0.30"
    sql += " ORDER BY confidence DESC LIMIT ?"
    params.append(limit)

    rows = conn.execute(sql, params).fetchall()
    conn.close()

    # ── NMS Frame-level deduplication ─────────────────────────────────────
    # Keep only the highest-confidence detection per (video_id, frame_index, class_name).
    # This prevents double-counting overlapping bounding boxes of the same object
    # detected multiple times in the same frame.
    seen_frame_cls: dict = {}
    for row in rows:
        r = dict(row)
        key = (r.get("video_id", ""), r.get("frame_index", 0), r.get("class_name", ""))
        if key not in seen_frame_cls or r["confidence"] > seen_frame_cls[key]["confidence"]:
            seen_frame_cls[key] = r
    deduped_rows = list(seen_frame_cls.values())
    # Re-sort by confidence after dedup
    deduped_rows.sort(key=lambda x: x.get("confidence", 0), reverse=True)

    results = []
    for row in deduped_rows:
        r = dict(row) if not isinstance(row, dict) else row
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
