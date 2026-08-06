"""
test_baseline_pipeline.py — Negation-Aware + Temporal Conversational NLP Pipeline.

Pipeline: User Query
    -> spaCy Dependency Parsing (entities + negations + temporal direction)
    -> Parametrized SQL Generator (NOT IN negation + timestamp window injection)
    -> SQLite Execution
    -> Structured JSON + XAI Explanation

Zero black-box LLM or external API dependencies.
"""

from __future__ import annotations

import json
import sqlite3
import time
from typing import Any, Dict, List, Tuple

import spacy

DB_PATH = "video_metadata.db"


# ---------------------------------------------------------------------------
# Database Setup
# ---------------------------------------------------------------------------

def setup_sample_database(db_path: str = DB_PATH) -> None:
    """Initialize database and seed sample records if missing."""
    conn = sqlite3.connect(db_path)
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS detections (
            id           TEXT PRIMARY KEY,
            frame_id     INTEGER NOT NULL,
            timestamp_ms REAL NOT NULL,
            object_class TEXT NOT NULL,
            color        TEXT,
            confidence   REAL DEFAULT 0.0
        );
        CREATE INDEX IF NOT EXISTS idx_cls     ON detections(object_class);
        CREATE INDEX IF NOT EXISTS idx_cls_col ON detections(object_class, color);
        CREATE INDEX IF NOT EXISTS idx_frame   ON detections(frame_id);
        CREATE INDEX IF NOT EXISTS idx_ts      ON detections(timestamp_ms);
    """)

    count = conn.execute("SELECT COUNT(*) FROM detections").fetchone()[0]
    if count == 0:
        sample_rows = [
            # frame 10 @ 5s:  red car  -> first red car (highest conf)
            ("d01", 10,  5000.0,  "car",     "red",   0.96),
            # frame 20 @ 10s: red person + helmet -> excluded for no-helmet queries
            ("d02", 20,  10000.0, "person",  "red",   0.91),
            ("d03", 20,  10000.0, "helmet",  None,    0.87),
            # frame 35 @ 17.5s: red car -> second red car (AFTER frame 10)
            ("d04", 35,  17500.0, "car",     "red",   0.88),
            # frame 50 @ 25s: blue person
            ("d05", 50,  25000.0, "person",  "blue",  0.93),
            # frame 65 @ 32.5s: red car -> third red car (AFTER frame 35)
            ("d06", 65,  32500.0, "car",     "red",   0.84),
            # frame 80 @ 40s: red car -> fourth red car
            ("d07", 80,  40000.0, "car",     "red",   0.82),
            # frame 95 @ 47.5s: red person
            ("d08", 95,  47500.0, "person",  "red",   0.79),
        ]
        conn.executemany(
            "INSERT OR IGNORE INTO detections "
            "(id, frame_id, timestamp_ms, object_class, color, confidence) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            sample_rows,
        )
        conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# Step 1: Negation-Aware spaCy Entity Extraction
# ---------------------------------------------------------------------------

# Temporal keywords → SQL operator
_TEMPORAL_FORWARD  = {"after", "next", "then", "following", "later", "beyond"}
_TEMPORAL_BACKWARD = {"before", "previous", "prior", "earlier", "preceding"}


def extract_entities_spacy(query: str) -> Dict[str, Any]:
    """
    Parse query using spaCy dependency trees.

    Extracts:
      object_class      — core noun (e.g. "car")
      color             — adjectival/compound modifier (e.g. "red")
      excluded_objects  — objects negated via `neg` dep or NEGATION_PREPS
      temporal_direction — ">" (after/next/then) or "<" (before/previous)
                           None if no temporal keyword found.

    Returns
    -------
    {
        "object_class": str | None,
        "color": str | None,
        "excluded_objects": list[str],
        "temporal_direction": ">" | "<" | None
    }
    """
    nlp = spacy.load("en_core_web_sm")
    doc = nlp(query)

    object_class: str | None    = None
    color: str | None           = None
    excluded_objects: list[str] = []
    temporal_direction: str | None = None

    # Tokens that trigger negation via preposition
    NEGATION_PREPS = {"without", "no", "lacking", "missing", "excluding"}

    # ── Temporal detection: raw token scan (direction words can appear anywhere) ─
    query_lower = query.lower()
    # Check forward keywords first ("after that" is more common than "before")
    for kw in _TEMPORAL_FORWARD:
        if kw in query_lower.split():
            temporal_direction = ">"
            break
    if temporal_direction is None:
        for kw in _TEMPORAL_BACKWARD:
            if kw in query_lower.split():
                temporal_direction = "<"
                break

    # ── Pass 1: walk dependency tree ──────────────────────────────────────────
    for token in doc:

        # ── Core subject noun ──────────────────────────────────────────────────
        if token.pos_ in ("NOUN", "PROPN") and not object_class:
            object_class = token.lemma_.lower()
            for child in token.children:
                if child.dep_ in ("amod", "compound") and child.pos_ in ("ADJ", "NOUN"):
                    color = child.text.lower()
                    break

        # ── `neg` dep: "not wearing a helmet" ─────────────────────────────────
        if token.dep_ == "neg":
            head = token.head
            for desc in head.subtree:
                if (
                    desc.dep_ in ("dobj", "attr", "nsubj", "pobj", "nsubjpass")
                    and desc.pos_ in ("NOUN", "PROPN")
                    and desc != head
                ):
                    excl = desc.lemma_.lower()
                    if excl not in excluded_objects:
                        excluded_objects.append(excl)

        # ── prep + pobj: "person without a helmet" ────────────────────────────
        if token.dep_ == "prep" and token.text.lower() in NEGATION_PREPS:
            for child in token.children:
                if child.dep_ == "pobj" and child.pos_ in ("NOUN", "PROPN"):
                    excl = child.lemma_.lower()
                    if excl not in excluded_objects:
                        excluded_objects.append(excl)

    # ── Pass 2: flat-token fallback (skips temporal keyword tokens) ───────────
    SKIP_TOKENS = _TEMPORAL_FORWARD | _TEMPORAL_BACKWARD | {"that", "it", "this"}
    if not object_class or not color:
        content_tokens = [
            t for t in doc
            if not t.is_stop and not t.is_punct
            and t.pos_ not in ("VERB", "AUX", "ADV", "PART")
            and t.lemma_.lower() not in excluded_objects
            and t.text.lower() not in SKIP_TOKENS
        ]
        text_vals = [t.text.lower() for t in content_tokens]
        remaining = [t for t in text_vals if t != (object_class or "")]

        if not color and len(remaining) >= 1:
            color = remaining[0]
        if not object_class and len(text_vals) >= 1:
            object_class = text_vals[-1]
        if color and color == object_class:
            color = None

    return {
        "object_class":      object_class,
        "color":             color,
        "excluded_objects":  excluded_objects,
        "temporal_direction": temporal_direction,
    }


# ---------------------------------------------------------------------------
# Step 2: Negation-Aware Parametrized SQL Generator
# ---------------------------------------------------------------------------

def generate_sql_query(
    entities: Dict[str, Any],
    last_match_timestamp: float | None = None,
) -> Tuple[str, List[Any]]:
    """
    Build a fully parametrized SQL query from the entity dict.

    Handles:
      - Color filter           : AND color = ?
      - Negation subqueries    : AND frame_id NOT IN (SELECT frame_id ...)
      - Temporal window filter : AND timestamp_ms > ? / < ?
                                 (only when temporal_direction + last_match_timestamp exist)

    Parameters
    ----------
    entities : dict
        Output of extract_entities_spacy().
    last_match_timestamp : float | None
        timestamp_ms of the top result from the previous search.
        Required for temporal queries to function.

    Returns
    -------
    (sql_string, params_list)
    """
    params: List[Any] = []

    sql_parts = [
        "SELECT frame_id, timestamp_ms, confidence",
        "FROM detections",
        "WHERE object_class = ?",
    ]
    params.append(entities.get("object_class"))

    # Color filter
    if entities.get("color"):
        sql_parts.append("AND color = ?")
        params.append(entities["color"])

    # Negation subqueries
    for excl_cls in entities.get("excluded_objects", []):
        sql_parts.append(
            "AND frame_id NOT IN ("
            "SELECT frame_id FROM detections WHERE object_class = ?"
            ")"
        )
        params.append(excl_cls)

    # ── Temporal window injection ──────────────────────────────────────────
    # Appends AND timestamp_ms > ? (or <) only when both pieces are present:
    #   1. entities["temporal_direction"] is set by the NLP parser
    #   2. last_match_timestamp is provided by the caller from session state
    temporal_dir = entities.get("temporal_direction")
    if temporal_dir and last_match_timestamp is not None:
        op = ">" if temporal_dir == ">" else "<"
        sql_parts.append(f"AND timestamp_ms {op} ?")
        params.append(last_match_timestamp)

    sql_parts.append("ORDER BY confidence DESC LIMIT 5;")
    sql = "\n    ".join(sql_parts)
    return sql, params


# ---------------------------------------------------------------------------
# Step 3: XAI Explanation Formatter
# ---------------------------------------------------------------------------

def format_xai_explanation(
    entities: Dict[str, Any],
    last_match_timestamp: float | None = None,
) -> List[str]:
    """
    Convert parsed entities to UI-ready Explainable AI strings.

    Format:
        ✔ Object: <object_class>
        ✔ Color: <color>             (if present)
        ❌ Excluded: <class>          (one per excluded object)
        ⏩ After: HH:MM:SS           (temporal forward filter)
        ⏪ Before: HH:MM:SS          (temporal backward filter)
    """
    lines: List[str] = []

    if entities.get("object_class"):
        lines.append(f"✔ Object: {entities['object_class']}")
    if entities.get("color"):
        lines.append(f"✔ Color: {entities['color']}")
    for excl in entities.get("excluded_objects", []):
        lines.append(f"❌ Excluded: {excl}")

    # Temporal context line
    if entities.get("temporal_direction") and last_match_timestamp is not None:
        total_s = int(last_match_timestamp / 1000)
        h, rem = divmod(total_s, 3600)
        m, s   = divmod(rem, 60)
        ts_str = f"{h:02d}:{m:02d}:{s:02d}"
        if entities["temporal_direction"] == ">":
            lines.append(f"⏩ After: {ts_str} (from last result)")
        else:
            lines.append(f"⏪ Before: {ts_str} (from last result)")

    if not lines:
        lines.append("⚠ No entities extracted — query could not be parsed.")

    return lines


# ---------------------------------------------------------------------------
# Main Pipeline Executor
# ---------------------------------------------------------------------------

def execute_pipeline(
    query: str,
    db_path: str = DB_PATH,
    last_match_timestamp: float | None = None,
) -> Dict[str, Any]:
    """
    Run the full pipeline and return a structured JSON-serializable summary.

    Parameters
    ----------
    query : str
        Natural language query from the user.
    db_path : str
        Path to the SQLite database file.
    last_match_timestamp : float | None
        timestamp_ms of the top result from the PREVIOUS search.
        When set and the query contains a temporal keyword, the SQL will
        include AND timestamp_ms > ? (or <) to window the results.

    Output keys
    -----------
        input_query               original user query string
        extracted_entities        object_class, color, excluded_objects, temporal_direction
        generated_sql             human-readable parametrized SQL
        sql_params                ordered list of bound parameters
        match_count               rows returned
        execution_latency_ms      wall-clock time from parse to DB return
        returned_timestamps_ms    list of matching timestamp_ms values
        last_match_timestamp_ms   timestamp_ms of the top result (None if no results)
        raw_results               full row data for each match
        xai_explanation           list of UI-ready explanation strings
    """
    setup_sample_database(db_path)

    t_start = time.perf_counter()

    # Step 1 ── Entity extraction (includes temporal_direction)
    entities = extract_entities_spacy(query)

    # Step 2 ── SQL generation (injects timestamp window if needed)
    sql, params = generate_sql_query(entities, last_match_timestamp=last_match_timestamp)

    # Step 3 ── Execute against SQLite
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(sql, params).fetchall()
    conn.close()

    t_end = time.perf_counter()
    latency_ms = round((t_end - t_start) * 1000, 3)

    # Step 4 ── Capture top result timestamp for next conversational turn
    top_timestamp: float | None = rows[0]["timestamp_ms"] if rows else None

    # Step 5 ── XAI formatting (includes temporal context)
    xai = format_xai_explanation(entities, last_match_timestamp=last_match_timestamp)

    return {
        "input_query":             query,
        "extracted_entities":      entities,
        "generated_sql":           sql,
        "sql_params":              params,
        "match_count":             len(rows),
        "execution_latency_ms":    latency_ms,
        "returned_timestamps_ms":  [r["timestamp_ms"] for r in rows],
        "last_match_timestamp_ms": top_timestamp,
        "raw_results":             [dict(r) for r in rows],
        "xai_explanation":         xai,
    }


# ---------------------------------------------------------------------------
# Live Temporal Conversation Test (runs without Streamlit UI)
# ---------------------------------------------------------------------------

def run_live_temporal_test(db_path: str = DB_PATH) -> None:
    """
    Simulate a two-step conversational search and assert temporal SQL correctness.

    Step 1: "red car"  — baseline search, captures last_match_timestamp_ms.
    Step 2: "red car after that" — temporal follow-up using Step 1's timestamp.
    Step 3: Assert SQL for Step 2 contains 'AND timestamp_ms > ?'.
    """
    setup_sample_database(db_path)
    separator = "=" * 62

    print(f"\n{separator}")
    print("  LIVE TEMPORAL CONVERSATION TEST")
    print(separator)

    # ── Step 1 ──────────────────────────────────────────────────────────────
    print("\n[STEP 1] Query: 'red car'")
    step1 = execute_pipeline("red car", db_path=db_path, last_match_timestamp=None)
    print(json.dumps(step1, indent=2))

    saved_ts = step1["last_match_timestamp_ms"]
    print(f"\n  >> last_match_timestamp_ms saved from Step 1: {saved_ts} ms")

    assert saved_ts is not None, "FAIL: Step 1 returned no results — cannot test temporal filter"
    assert step1["match_count"] > 0, "FAIL: Step 1 match_count is 0"

    # ── Step 2 ──────────────────────────────────────────────────────────────
    print(f"\n{separator}")
    print("[STEP 2] Follow-up query: 'red car after that'")
    print(f"         Using last_match_timestamp={saved_ts} ms as the temporal anchor")
    step2 = execute_pipeline(
        "red car after that",
        db_path=db_path,
        last_match_timestamp=saved_ts,
    )
    print(json.dumps(step2, indent=2))

    # ── Step 3 — Assertions ──────────────────────────────────────────────────
    print(f"\n{separator}")
    print("[STEP 3] Assertions")

    # 3a. temporal_direction must be ">"
    assert step2["extracted_entities"]["temporal_direction"] == ">", \
        f"FAIL: expected temporal_direction='>' got {step2['extracted_entities']['temporal_direction']!r}"
    print("  [PASS] temporal_direction == '>'")

    # 3b. SQL must contain the temporal clause
    assert "AND timestamp_ms > ?" in step2["generated_sql"], \
        f"FAIL: 'AND timestamp_ms > ?' not found in SQL:\n{step2['generated_sql']}"
    print("  [PASS] SQL contains 'AND timestamp_ms > ?'")

    # 3c. The anchor timestamp must appear in sql_params
    assert saved_ts in step2["sql_params"], \
        f"FAIL: saved timestamp {saved_ts} not in sql_params {step2['sql_params']}"
    print(f"  [PASS] Anchor timestamp {saved_ts} ms is in sql_params")

    # 3d. All Step 2 results must have timestamp > anchor
    for ts in step2["returned_timestamps_ms"]:
        assert ts > saved_ts, \
            f"FAIL: result timestamp {ts} ms is NOT after anchor {saved_ts} ms"
    print(f"  ✔ All {step2['match_count']} result(s) have timestamp_ms > {saved_ts} ms")

    print(f"\n{separator}")
    print("  ALL TEMPORAL ASSERTIONS PASSED ✅")
    print(separator)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    # Original regression tests
    baseline_queries = [
        "red car",
        "red person without a helmet",
        "person not wearing a helmet",
    ]
    for q in baseline_queries:
        print("\n" + "=" * 60)
        print(f"  Query: {q!r}")
        print("=" * 60)
        print(json.dumps(execute_pipeline(q), indent=2))

    # Temporal conversation test
    run_live_temporal_test()
