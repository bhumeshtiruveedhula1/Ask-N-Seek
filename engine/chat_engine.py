"""
engine/chat_engine.py  --  Stateful Chat Engine for Ask-N-Seek
===============================================================

Processes a natural-language message from the frontend chat UI and returns
a structured response that includes:
  - A human-readable reply string (with XAI tags)
  - A list of matched video timestamps for the frontend to render as chips
  - A language_detected field (always 'en' -- fully offline)

Pipeline Phases
---------------
A  Chit-Chat   -- greetings / FAQ -- instant, no search
B  Upload Gate -- politely refuse if no video uploaded yet
C  NLP Extract -- spaCy (en_core_web_sm) pulls nouns, colors,
                  negations, temporal direction keywords
D  Vague Guard -- noun found but zero modifiers -> ask for more detail
E  State Merge -- merge extracted entities into session active_filters
                  inject temporal WHERE clause if "after/before" present
F  Execute     -- call search_structured(), format XAI output

Everything is 100% offline. No external API calls anywhere.
All imports are from the stdlib or packages already in requirements.txt.
"""
from __future__ import annotations

import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Lazy-load spaCy once (expensive model load)
# ─────────────────────────────────────────────────────────────────────────────
_nlp = None

def _get_nlp():
    global _nlp
    if _nlp is None:
        try:
            import spacy
            _nlp = spacy.load("en_core_web_sm")
            logger.info("chat_engine: spaCy en_core_web_sm loaded")
        except Exception as exc:
            logger.warning("chat_engine: spaCy unavailable (%s) -- using regex fallback", exc)
            _nlp = False  # sentinel: tried and failed
    return _nlp if _nlp is not False else None


# ─────────────────────────────────────────────────────────────────────────────
# Vocabulary constants  (mirrors stub_parser + storage color families)
# ─────────────────────────────────────────────────────────────────────────────

# Map query color word -> canonical form used in storage
_COLOR_CANON: dict[str, str] = {
    "red":         "red",    "crimson":    "red",    "maroon":     "red",
    "dark red":    "red",    "orange-red": "red",    "scarlet":    "red",
    "blue":        "blue",   "navy":       "blue",   "dark blue":  "blue",
    "light blue":  "blue",   "azure":      "blue",   "cobalt":     "blue",
    "green":       "green",  "dark green": "green",  "olive":      "green",
    "light green": "green",
    "yellow":      "yellow", "gold":       "yellow",  "dark yellow": "yellow",
    # white family — silver stays SILVER so _COLOR_FAMILIES can expand correctly
    "white":       "white",  "ivory":      "white",  "cream":      "white",
    "pearl":       "white",  "off-white":  "white",
    # silver is its own canonical — expands to [silver, light gray, white] in storage
    "silver":      "silver", "chrome":     "silver",
    # black family
    "black":       "black",  "charcoal":   "black",
    "gray":        "gray",   "grey":       "gray",   "dark gray":  "gray",
    "light gray":  "gray",
    "brown":       "brown",  "beige":      "brown",  "tan":        "brown",
    "orange":      "orange",
    "purple":      "purple", "violet":     "purple", "lavender":   "purple",
    "pink":        "purple",
}

_VEHICLE_CLASSES = {
    "car", "vehicle", "truck", "bus", "van", "motorcycle", "bicycle",
    "sedan", "suv", "minivan", "jeep", "pickup", "auto",
}

_PERSON_CLASSES = {
    "person", "people", "man", "woman", "child", "pedestrian",
    "traffic warden", "warden", "guard", "officer", "worker",
    "thief", "suspect", "intruder", "individual",
}

# Spatial trigger words -> relation type stored in DB
_SPATIAL_TRIGGERS: dict[str, str] = {
    "next to":     "near",  "near":        "near",  "beside":   "near",
    "by":          "near",  "close to":    "near",  "adjacent": "near",
    "alongside":   "near",  "holding":     "near",  "touching": "near",
    "in front of": "near",  "behind":      "near",
    "left of":     "left_of",  "left":     "left_of",
    "right of":    "right_of", "right":    "right_of",
}

# Temporal keywords — ONLY standalone time-direction words
# NOTE: "next" removed — it conflicts with spatial phrase "next to"
_TEMPORAL_AFTER  = {"after", "then", "following", "later", "subsequently"}
_TEMPORAL_BEFORE = {"before", "previous", "prior", "earlier", "preceding"}

# Negation prepositions / auxiliaries
_NEGATION_WORDS = {"without", "no", "not", "excluding", "minus", "except"}

# Words that signal the user is continuing the previous search (not a new topic).
# When the message has ZERO new entities, we only run the stale filters if the
# user said something that clearly means "show me more" / "continue".
_CONTINUATION_WORDS = {
    "show", "more", "yes", "ok", "okay", "that", "those", "these",
    "again", "same", "continue", "go", "find", "search", "look",
    "all", "next", "list", "results",
}

# Chit-chat patterns (regex -> reply)
_CHITCHAT: list[tuple[re.Pattern, str]] = [
    # English greetings
    (re.compile(r"\b(hi|hello|hey|howdy|hiya)\b", re.I),
     "👋 Hi! I'm Ask-N-Seek — I search CCTV/video footage using plain English.\n\nHere's how it works:\n  1️⃣  Upload a video using the ⇪ button below\n  2️⃣  Ask me things like:\n       • 'person next to red car'\n       • 'person without helmet'\n       • 'blue truck after that'\n\nI'll show you the exact timestamps. Ready?"),
    # Kannada greetings
    (re.compile(r"\b(namaskara|namaskar|vandanegalu|shubhodaya|namaskaragalu)\b", re.I),
     "👋 Namaskara! Naan Ask-N-Seek — video footage-nalli objects search maadthene.\nUpload your video using ⇪ and ask me what you're looking for!"),
    # Hindi greetings
    (re.compile(r"\b(namaste|namasthe|haan|theek hai|shukriya|dhanyavaad|kripya)\b", re.I),
     "👋 Namaste! Main Ask-N-Seek hoon — apka video footage search karta hoon.\nVideo upload karein ⇪ button se, phir poochein kya dhundna hai!"),
    # Tamil greetings
    (re.compile(r"\b(vanakkam|nandri|romba nandri)\b", re.I),
     "👋 Vanakkam! Naan Ask-N-Seek — video footage-il objects search panren.\nUpload your video using ⇪ and ask me what you need!"),
    # English FAQ
    (re.compile(r"\b(how are you|how r u|how do you do)\b", re.I),
     "Running at full speed! 🚀 I'm indexing video detections in real-time.\nUpload your footage and I'll help you find exactly what you need."),
    (re.compile(r"\b(what can you do|what do you do|help|how do i use|how to use)\b", re.I),
     "Here's what I can find in your video:\n\n🔍  Objects    — 'show me all cars'\n🎨  Colors     — 'red car', 'blue truck'\n📍  Positions  — 'person next to car', 'near the truck'\n⛔  Negation   — 'person without helmet'\n⏱  Follow-up  — 'what happened after that?'\n\nJust upload a video first with the ⇪ button!"),
    (re.compile(r"\b(thank|thanks|thx|ty|shukriya|dhanyavaad|nandri)\b", re.I),
     "You're welcome! 😊 Ask me about another moment in the footage."),
    (re.compile(r"\b(bye|goodbye|see ya|cya)\b", re.I),
     "Goodbye! Come back when you have a video to analyze."),
    (re.compile(r"\bwhat (can|do) you do\b", re.I),
     "I can search your uploaded video for objects, people, colors, and spatial relationships. Try: 'person near red car', 'two people', 'person without helmet'."),
    (re.compile(r"\bhow (does this|do you) work\b", re.I),
     "I use YOLO-World object detection to index every frame of your video. Then I interpret your question and search the index for matching timestamps. All offline, no internet needed."),
    (re.compile(r"\b(clear|reset|start over|forget)\b", re.I),
     "__CLEAR_SESSION__"),  # Special sentinel handled below
]

# Vague single-noun queries that need clarification
_CLARIFICATION_TEMPLATE = (
    "I found '{noun}' in the video index. Could you give me more detail? "
    "For example: what color? Near what object? Any specific action? "
    "The more specific you are, the better I can pinpoint the right frames."
)


def _parse_clarification_response(message: str) -> dict:
    """
    When a clarification card button is clicked, the frontend sends a message
    like "color: Red" or "spatial: Yes — near person" or "vehicle: Near car".
    This function parses those structured responses and returns entity patches.

    Returns a dict compatible with _extract_entities output (all keys optional).
    """
    patches: dict[str, Any] = {}
    msg = message.strip().lower()

    # Pattern: "color: <value>"
    m = re.match(r"^color:\s*(.+)$", msg)
    if m:
        val = m.group(1).strip()
        if val != "skip":
            canon = _COLOR_CANON.get(val)
            if canon:
                patches["color"] = canon
        return patches

    # Pattern: "spatial: yes — near person" or "spatial: no — alone"
    m = re.match(r"^spatial:\s*(.+)$", msg)
    if m:
        val = m.group(1).strip()
        if "near person" in val or "yes" in val:
            patches["spatial_relation"] = {"type": "near", "target_class": "person"}
        elif "near car" in val:
            patches["spatial_relation"] = {"type": "near", "target_class": "car"}
        # "no — alone" or "skip" → no spatial filter added
        return patches

    # Pattern: "vehicle: near car" / "vehicle: near truck"
    m = re.match(r"^vehicle:\s*(.+)$", msg)
    if m:
        val = m.group(1).strip()
        for cls in ["car", "truck", "bus", "bike", "motorcycle"]:
            if cls in val:
                patches["spatial_relation"] = {"type": "near", "target_class": cls}
                break
        return patches

    # Pattern: "time: walking" / "time: running" — ignored for now (no DB field)
    # Pattern: "primary: Person" / "primary: Car" — from spatial-only guard
    m = re.match(r"^primary:\s*(.+)$", msg)
    if m:
        val = m.group(1).strip().lower()
        if val in ("any object", "skip"):
            pass  # no class filter — run with spatial only
        else:
            # Map button labels to canonical class names
            _PRIMARY_MAP = {
                "person": "person", "car": "car", "truck": "truck",
                "motorcycle": "motorcycle", "bicycle": "bicycle", "bike": "motorcycle",
            }
            patches["class"] = _PRIMARY_MAP.get(val, val)
        return patches

    return patches


def _extract_entities(message: str) -> dict[str, Any]:
    """
    Extract structured entities from the user message using spaCy when
    available, falling back to regex heuristics if spaCy is not loaded.

    Returns:
        {
            "class":            str | None,   # primary object class
            "color":            str | None,   # canonical color
            "negated":          list[str],     # excluded classes
            "spatial_relation": dict | None,   # {type, target_class}
            "temporal":         str | None,    # ">" or "<"
            "raw_nouns":        list[str],     # all nouns found (for vague check)
        }
    """
    msg_lower = message.strip().lower()
    msg_lower = re.sub(r"\s+", " ", msg_lower)

    entities: dict[str, Any] = {
        "class":            None,
        "color":            None,
        "negated":          [],
        "spatial_relation": None,
        "temporal":         None,
        "raw_nouns":        [],
        "action":           None,   # verb/action extracted from query (e.g. "sleeping", "running")
    }

    # ── A. Temporal direction ──────────────────────────────────────────────
    # CRITICAL: Only fire temporal if the keyword is standalone (not part of
    # a spatial phrase like "next to", "after the car"). We check that a
    # temporal word is not immediately followed by "to" on the same token.
    words = msg_lower.split()
    for i, w in enumerate(words):
        if w in _TEMPORAL_AFTER:
            # "next to" should NOT fire temporal
            next_word = words[i + 1] if i + 1 < len(words) else ""
            if next_word == "to":
                continue   # it's spatial, skip
            entities["temporal"] = ">"
            break
        elif w in _TEMPORAL_BEFORE:
            entities["temporal"] = "<"
            break

    # ── B. Color (multi-word first) ────────────────────────────────────────
    for phrase, canon in sorted(_COLOR_CANON.items(), key=lambda kv: -len(kv[0])):
        if phrase in msg_lower:
            entities["color"] = canon
            break

    # ── C. Negation (without X, no X, not X) ──────────────────────────────
    neg_pattern = re.compile(
        r"\b(?:without|no|not|excluding|minus|except)\s+(?:a\s+|an\s+|the\s+)?(\w+)"
    )
    for m in neg_pattern.finditer(msg_lower):
        neg_word = m.group(1).rstrip("s")
        if neg_word in (_VEHICLE_CLASSES | {"helmet", "bag", "backpack", "badge", "vest"}):
            entities["negated"].append(neg_word)

    # ── D. Spatial relation (longest phrase first) ─────────────────────────
    sorted_spatial = sorted(_SPATIAL_TRIGGERS.items(), key=lambda kv: -len(kv[0]))
    for phrase, rel_type in sorted_spatial:
        if phrase in msg_lower:
            after = msg_lower.split(phrase, 1)[1].strip()
            # Remove articles before scanning tokens
            after_clean = re.sub(r"\b(a|an|the|to)\b", "", after).strip()
            tokens_after = [t for t in after_clean.split() if t]
            # Priority 1: known vehicle/person class
            for tok in tokens_after:
                tok_c = tok.rstrip("s")
                if tok in (_VEHICLE_CLASSES | _PERSON_CLASSES):
                    entities["spatial_relation"] = {"type": rel_type, "target_class": tok}
                    break
                if tok_c in (_VEHICLE_CLASSES | _PERSON_CLASSES):
                    entities["spatial_relation"] = {"type": rel_type, "target_class": tok_c}
                    break
            # Priority 2: any noun word after spatial phrase (tree, gate, wall, door…)
            if not entities["spatial_relation"] and tokens_after:
                first_noun = tokens_after[0].rstrip("s")  # basic lemma
                if first_noun and len(first_noun) > 2:    # skip noise like "a", "to"
                    entities["spatial_relation"] = {"type": rel_type, "target_class": first_noun}
            if entities["spatial_relation"]:
                break

    # ── E. Primary class via spaCy ────────────────────────────────────────
    nlp = _get_nlp()
    all_known = _VEHICLE_CLASSES | _PERSON_CLASSES | {"helmet", "bag", "backpack", "badge"}
    found_nouns: list[str] = []

    if nlp:
        doc = nlp(message)
        # Collect all content nouns (not stop words, not punct)
        for token in doc:
            if token.pos_ in ("NOUN", "PROPN") and not token.is_stop:
                lemma = token.lemma_.lower()
                if lemma in all_known:
                    found_nouns.append(lemma)
        entities["raw_nouns"] = list(dict.fromkeys(found_nouns))  # deduplicate preserving order

        # ── Action / Verb extraction ──────────────────────────────────────────────
        # Maps verb lemmas to canonical action labels.
        # DB has no action column; this enriches XAI explanations.
        _ACTION_MAP: dict[str, str] = {
            "sleep": "sleeping",  "sleeping": "sleeping",
            "run":   "running",   "running":  "running",
            "walk":  "walking",   "walking":  "walking",
            "sit":   "sitting",   "sitting":  "sitting",
            "stand": "standing",  "standing": "standing",
            "fight": "fighting",  "fighting": "fighting",
            "carry": "carrying",  "carrying": "carrying",
            "hold":  "holding",   "holding":  "holding",
            "lie":   "lying",     "lying":    "lying",
            "jump":  "jumping",   "jumping":  "jumping",
            "crouch":"crouching", "crouching":"crouching",
            "fall":  "falling",   "falling":  "falling",
            "talk":  "talking",   "talking":  "talking",
            "work":  "working",   "working":  "working",
        }
        for token in doc:
            if token.pos_ == "VERB" or (token.dep_ in ("ROOT", "advcl") and token.pos_ == "VERB"):
                lemma = token.lemma_.lower()
                if lemma in _ACTION_MAP:
                    entities["action"] = _ACTION_MAP[lemma]
                    break
        # Also check raw message for gerund-style adjectives (e.g. "sleeping person")
        if not entities.get("action"):
            for tok in msg_lower.split():
                if tok in _ACTION_MAP:
                    entities["action"] = _ACTION_MAP[tok]
                    break

        # Primary class: prefer vehicle if a color was found (color->vehicle), else first noun
        if entities["color"] and entities.get("spatial_relation"):
            # "person next to red car" → primary = spatial target (car)
            target = entities["spatial_relation"].get("target_class", "")
            if target in _VEHICLE_CLASSES:
                entities["class"] = target
                entities["spatial_relation"]["target_class"] = "person"
            else:
                entities["class"] = found_nouns[0] if found_nouns else None
        elif entities["color"]:
            # Color found: look for a vehicle/object noun to attach to
            vehicle_nouns = [n for n in found_nouns if n in _VEHICLE_CLASSES]
            entities["class"] = vehicle_nouns[0] if vehicle_nouns else (found_nouns[0] if found_nouns else None)
        else:
            entities["class"] = found_nouns[0] if found_nouns else None
    else:
        # Regex fallback: scan tokens
        tokens = msg_lower.split()
        for tok in tokens:
            tok_c = tok.rstrip("s")
            if tok in all_known:
                found_nouns.append(tok)
                break
            if tok_c in all_known:
                found_nouns.append(tok_c)
                break
        entities["raw_nouns"] = found_nouns
        entities["class"]     = found_nouns[0] if found_nouns else None

    return entities


# ─────────────────────────────────────────────────────────────────────────────
# Phase E: State merge
# ─────────────────────────────────────────────────────────────────────────────

def _merge_filters(session_filters: dict, new_entities: dict, temporal_ts: float | None = None) -> dict:
    """
    Merge newly extracted entities into the session's existing active_filters.
    New values override old values; None values leave the existing value intact.

    IMPORTANT: temporal_direction and temporal_timestamp are ONE-SHOT filters.
    They apply only when explicitly stated in the current turn and are NEVER
    inherited from the persisted session. This prevents 'next to' or any
    non-temporal message from accidentally carrying forward a stale time filter.
    """
    # Start from session, but STRIP any stale temporal keys — they must not persist
    merged = {k: v for k, v in session_filters.items()
              if k not in ("temporal_direction", "temporal_timestamp")}

    if new_entities.get("class"):
        merged["class"] = new_entities["class"]
    if new_entities.get("color"):
        merged["color"] = new_entities["color"]
    if new_entities.get("negated"):
        existing_negated = merged.get("negated") or []
        merged["negated"] = list(set(existing_negated) | set(new_entities["negated"]))
    if new_entities.get("spatial_relation"):
        merged["spatial_relation"] = new_entities["spatial_relation"]
    # Persist action — used for XAI display even though DB cannot filter by action directly
    if new_entities.get("action"):
        merged["action"] = new_entities["action"]

    # Inject temporal WHERE only when EXPLICITLY stated this turn AND we have a ref timestamp
    if new_entities.get("temporal") and temporal_ts is not None:
        merged["temporal_direction"] = new_entities["temporal"]
        merged["temporal_timestamp"] = temporal_ts

    return merged


# ─────────────────────────────────────────────────────────────────────────────
# Phase F: Format XAI output
# ─────────────────────────────────────────────────────────────────────────────

def _format_xai_reply(filters: dict, results: list, query_text: str) -> str:
    """
    Build a human-readable reply with XAI explanation tags.

    Example output:
        Found 3 matches for "person next to red car"
        --- Applied Filters ---
        [OBJECT]  car
        [COLOR]   red
        [SPATIAL] near person
        --- Top Results ---
        1. 36.3s — confidence 0.53
        2. 33.3s — confidence 0.43
    """
    lines: list[str] = []

    count = len(results)
    if count == 0:
        lines.append(f'No confident matches found for "{query_text}".')
        lines.append("Try removing one constraint, or check if the object appears in the video.")
        return "\n".join(lines)

    lines.append(f'Found {count} match{"es" if count != 1 else ""} for "{query_text}"')
    lines.append("")
    lines.append("Applied filters:")

    if filters.get("class"):
        lines.append(f"  Object  : {filters['class']}")
    if filters.get("color"):
        lines.append(f"  Color   : {filters['color']}")
    if filters.get("negated"):
        lines.append(f"  Excluded: {', '.join(filters['negated'])}")
    if filters.get("spatial_relation"):
        sp = filters["spatial_relation"]
        lines.append(f"  Spatial : {sp.get('type','near').replace('_',' ')} {sp.get('target_class','')}")
    if filters.get("temporal_direction"):
        direction = "after" if filters["temporal_direction"] == ">" else "before"
        lines.append(f"  Temporal: {direction} {filters.get('temporal_timestamp', 0):.1f}s")
    if filters.get("action"):
        lines.append(f"  Action  : {filters['action']} (approximate — results show best visual match)")

    lines.append("")
    lines.append("Top results:")
    for i, r in enumerate(results[:5], 1):
        ts    = r.get("timestamp", 0)
        score = r.get("confidence_score", 0)
        lines.append(f"  {i}. {ts:.1f}s  (confidence {score:.2f})")

    return "\n".join(lines)


# ─────────────────────────────────────────────────────────────────────────────
# Main public API
# ─────────────────────────────────────────────────────────────────────────────

def process_chat(
    session_id: str,
    message: str,
    is_video_uploaded: bool,
    display_text: str | None = None,
) -> dict[str, Any]:
    """
    Process a single chat message and return a structured response.

    Parameters
    ----------
    session_id        : str        -- unique session key (= video_id from frontend)
    message           : str        -- raw user message (may be structured: "color: Red")
    is_video_uploaded : bool       -- True if a video has been ingested
    display_text      : str | None -- human-friendly label to show in XAI heading.
                                     If None, the raw message is used.
    """
    from engine.session_db import get_session, update_session, clear_session

    msg_clean    = message.strip()
    # The heading shown in XAI reply — use display_text if provided (e.g. "Red" not "color: Red")
    heading_text = (display_text or msg_clean).strip()

    # ── Phase A: Chit-Chat ─────────────────────────────────────────────────
    for pattern, reply in _CHITCHAT:
        if pattern.search(msg_clean):
            if reply == "__CLEAR_SESSION__":
                clear_session(session_id)
                return _ok_reply(
                    "Session cleared! Your search history has been reset. Start a new search.",
                    [], session_id, {}, False,
                )
            return _ok_reply(reply, [], session_id, {}, False)

    # ── Phase B: Upload Gate ───────────────────────────────────────────────
    if not is_video_uploaded:
        # Make the gate message context-aware: acknowledge what they asked
        # and guide them to upload rather than just saying "upload first"
        ents_preview = _extract_entities(msg_clean)
        if ents_preview.get("class") or ents_preview.get("color"):
            noun_hint = ents_preview.get("class") or ents_preview.get("color")
            gate_msg = (
                f"Got it — you're looking for '{noun_hint}' in the footage. "
                f"Click the ⇪ button in the chat bar below to upload your video, "
                f"and I'll search it right away!"
            )
        else:
            gate_msg = (
                "I need a video to search! Click the ⇪ button below the chat to upload "
                "your footage, then ask me anything."
            )
        return _ok_reply(gate_msg, [], session_id, {}, False)

    # ── Phase C: NLP Extraction ────────────────────────────────────────────
    entities = _extract_entities(msg_clean)

    # ── Clarification card response detection ─────────────────────────────────
    # Detect BEFORE anti-bleed so Skip/Any color still bypass it.
    _CLARIF_RE     = re.compile(r'^(color|spatial|vehicle|time):\\s*', re.I)
    is_clarif_resp = bool(_CLARIF_RE.match(msg_clean.strip()))

    clarif_patches = _parse_clarification_response(msg_clean)
    if clarif_patches:
        entities.update(clarif_patches)

    # Any clarification response clears awaiting flag
    if is_clarif_resp:
        update_session(session_id, awaiting_clarification=False)

    logger.debug("chat_engine entities=%s clarif=%s", entities, is_clarif_resp)

    # ── Phase C.5: Anti-bleed guard ────────────────────────────────────────
    # If the user typed something that produced ZERO entities AND it does not
    # look like a continuation ("show more", "yes", "search again" etc.),
    # do NOT silently re-run the stale session filters. That causes
    # "namaskara" or a random "1" to show old results.
    entities_empty = (
        not entities.get("class")
        and not entities.get("color")
        and not entities.get("spatial_relation")
        and not entities.get("temporal")
        and not entities.get("negated")
    )
    session = get_session(session_id)
    has_stale_filters = bool(session.get("active_filters", {}).get("class"))

    if entities_empty and not is_clarif_resp:
        words_in_msg    = set(msg_clean.lower().split())
        is_continuation = bool(words_in_msg & _CONTINUATION_WORDS)
        is_mid_session  = bool(session.get("awaiting_clarification"))
        if has_stale_filters and not is_continuation and not is_mid_session:
            saved_cls = session["active_filters"].get("class", "something")
            return _ok_reply(
                f"Hmm, I didn't catch that. 🤔 Are you still looking for '{saved_cls}'?\n"
                f"Say 'show more' or add a color/filter. Or ask me something new!",
                [], session_id, session["active_filters"], False,
            )
        elif not has_stale_filters and not is_continuation and not is_mid_session:
            return _ok_reply(
                "I didn't catch a search query. Try:\n"
                "  • 'person next to red car'\n"
                "  • 'person without helmet'\n"
                "  • 'blue truck'",
                [], session_id, {}, False,
            )

    # ── Phase D: Vague / Partial Intercept ─────────────────────────────────
    # Fire when query is EITHER:
    #   a) bare noun with zero modifiers (existing behaviour), OR
    #   b) noun + spatial BUT no color — ask for color to narrow search
    # Do NOT fire if we are already waiting for a clarification answer.
    has_color    = bool(entities.get("color"))
    has_spatial  = bool(entities.get("spatial_relation"))
    has_negation = bool(entities.get("negated"))
    has_temporal = bool(entities.get("temporal"))
    has_modifier = has_color or has_negation or has_spatial or has_temporal

    if entities.get("class") and not has_modifier and not session.get("awaiting_clarification"):
        # Phase D: First vague mention — save the class and ask structured follow-up questions
        noun = entities["class"]
        update_session(
            session_id,
            active_filters={"class": noun},
            awaiting_clarification=True,
        )
        # Context-aware questions depending on noun type
        if noun in _VEHICLE_CLASSES:
            questions = [
                {"id": "color",   "label": "Vehicle color?",    "options": ["Red", "Blue", "White", "Silver", "Black", "Gray", "Any color"]},
                {"id": "spatial", "label": "Near a person?",    "options": ["Yes — near person", "No — alone", "Skip"]},
            ]
        else:
            questions = [
                {"id": "color",   "label": "Clothing color?",   "options": ["Red", "Blue", "Black", "White", "Any color"]},
                {"id": "vehicle", "label": "Near a vehicle?",   "options": ["Near car", "Near truck", "Near bike", "Skip"]},
            ]
        return {
            "reply":                  f"Your search for '{noun}' is quite broad. Let me help narrow it down:",
            "clarification_type":     "structured",
            "questions":              questions,
            "results":                [],
            "language_detected":      "en",
            "session_id":             session_id,
            "filters_used":           {"class": noun},
            "awaiting_clarification": True,
        }

    # ── Phase D2: Partial Intercept — has spatial but no color ─────────────
    # e.g. "person near car" — we know spatial but not which car color.
    # Ask for color to reduce search noise BEFORE running.
    if (entities.get("class") and has_spatial and not has_color
            and not has_negation and not session.get("awaiting_clarification")):
        noun = entities["class"]
        sp   = entities["spatial_relation"]
        target = sp.get("target_class", "object") if sp else "object"
        # Save what we know so far
        update_session(
            session_id,
            active_filters={"class": noun, "spatial_relation": sp},
            awaiting_clarification=True,
        )
        questions = [
            {
                "id":      "color",
                "label":   f"Which color {target}?",
                "options": ["Red", "Blue", "White", "Silver", "Black", "Gray", "Any color"],
            },
        ]
        return {
            "reply":                  f"I can find '{noun}' near '{target}' — which color {target} are you looking for?",
            "clarification_type":     "structured",
            "questions":              questions,
            "results":                [],
            "language_detected":      "en",
            "session_id":             session_id,
            "filters_used":           {"class": noun, "spatial_relation": sp},
            "awaiting_clarification": True,
        }


    # If we were awaiting clarification and the user now provided details,
    # merge with the saved class from the previous turn
    if session.get("awaiting_clarification") and (has_modifier or entities.get("class")):
        update_session(session_id, awaiting_clarification=False)
        session = get_session(session_id)  # refresh

    # ── Phase E: State Merge ───────────────────────────────────────────────
    merged_filters = _merge_filters(
        session["active_filters"],
        entities,
        temporal_ts=session.get("last_matched_timestamp"),
    )
    logger.debug("chat_engine: merged filters: %s", merged_filters)

    # ── Phase F: Execute Search ────────────────────────────────────────────
    # Guard: if merged_filters has a spatial_relation but NO class, the user typed
    # something like "near to tree" with no primary subject. Rather than running
    # a bare spatial search that returns garbage, ask what they're looking for.
    if (not merged_filters.get("class") and merged_filters.get("spatial_relation")
            and not session.get("awaiting_clarification")):
        sp      = merged_filters["spatial_relation"]
        target  = sp.get("target_class", "object") if sp else "object"
        update_session(session_id, active_filters=merged_filters, awaiting_clarification=True)
        questions = [
            {
                "id":      "primary",
                "label":   f"What are you looking for near the {target}?",
                "options": ["Person", "Car", "Truck", "Motorcycle", "Any object"],
            },
        ]
        return {
            "reply":                  f"I see you're looking near '{target}' — but what object are you searching for?",
            "clarification_type":     "structured",
            "questions":              questions,
            "results":                [],
            "language_detected":      "en",
            "session_id":             session_id,
            "filters_used":           merged_filters,
            "awaiting_clarification": True,
        }

    if not merged_filters.get("class"):
        # Nothing useful to search -- prompt the user
        return _ok_reply(
            "I couldn't find a searchable object in your message. "
            "Try something like: 'person near red car' or 'two people'.",
            [], session_id, merged_filters, False,
        )

    try:
        from engine.search import search_structured

        # Build the filter_dict in the format search_structured expects
        filter_dict = {
            "status":  "match",
            "filters": {
                "class":            merged_filters.get("class"),
                "color":            merged_filters.get("color"),
                "negated":          merged_filters.get("negated", []),
                "spatial_relation": merged_filters.get("spatial_relation"),
                "count_constraint": merged_filters.get("count_constraint"),
                "video_id":         session_id,
            },
        }

        raw_results = search_structured(filter_dict)

        # Temporal post-filter (one-shot — applies this turn only, NOT saved to session)
        temporal_dir    = merged_filters.get("temporal_direction")
        temporal_ts_val = merged_filters.get("temporal_timestamp")
        if temporal_dir and temporal_ts_val is not None:
            if temporal_dir == ">":
                raw_results = [r for r in raw_results if r.timestamp > temporal_ts_val]
            elif temporal_dir == "<":
                raw_results = [r for r in raw_results if r.get("timestamp", 0) < temporal_ts_val]

        results = raw_results

        # Persist active_filters WITHOUT temporal keys (temporal is one-shot)
        filters_to_save = {k: v for k, v in merged_filters.items()
                           if k not in ("temporal_direction", "temporal_timestamp")}

        # Sort descending by confidence and cap at 20
        results.sort(key=lambda r: r.confidence_score, reverse=True)
        results = results[:20]

        # Save last matched timestamp for next follow-up query
        new_ts = results[0].timestamp if results else session.get("last_matched_timestamp")
        update_session(
            session_id,
            active_filters=filters_to_save,
            last_matched_timestamp=new_ts,
            awaiting_clarification=False,
        )

        # Serialize results into the shape the frontend chip renderer expects:
        # {start, end, explanation, confidence_score}
        serialized = []
        for r in results:
            clip_start = max(0.0, r.timestamp - 3.0)
            clip_end   = r.timestamp + 3.0
            serialized.append({
                "start":            clip_start,
                "end":              clip_end,
                "window":           clip_start,        # fallback alias (vexed chip renderer)
                "timestamp":        r.timestamp,
                "confidence_score": round(r.confidence_score, 4),
                "explanation":      _build_short_explanation(r, merged_filters),
                "video_id":         r.video_id,
            })

        xai_reply = _format_xai_reply(merged_filters, serialized, heading_text)
        return _ok_reply(xai_reply, serialized, session_id, merged_filters, False)


    except Exception as exc:
        logger.exception("chat_engine: search failed: %s", exc)
        return _ok_reply(
            f"Search encountered an error: {exc}. Please try again.",
            [], session_id, merged_filters, False,
        )


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _ok_reply(
    reply: str,
    results: list,
    session_id: str,
    filters_used: dict,
    awaiting_clarification: bool,
) -> dict:
    return {
        "reply":                  reply,
        "results":                results,
        "language_detected":      "en",
        "session_id":             session_id,
        "filters_used":           filters_used,
        "awaiting_clarification": awaiting_clarification,
    }


def _build_short_explanation(result, filters: dict) -> str:
    """One-line XAI explanation for a result chip."""
    cls   = filters.get("class", "object")
    color = filters.get("color", "")
    sp    = filters.get("spatial_relation")

    parts = [f"{color} {cls}".strip()]
    if sp:
        parts.append(f"{sp.get('type','near').replace('_',' ')} {sp.get('target_class','')}")
    if filters.get("negated"):
        parts.append(f"(no {', '.join(filters['negated'])})")

    return "Match: " + " | ".join(parts) + f" @ {result.timestamp:.1f}s"
