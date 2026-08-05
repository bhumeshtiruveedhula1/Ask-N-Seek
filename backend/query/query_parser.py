"""

query_parser.py -- Rule-Based Query Parser (Achilles Part 3) -- v2

==================================================================

Architecture ref : 03_Architecture_Final.md ss3 (Query parser row)

TRD ref          : TRD-Build-Plan-Achilles.md ssPART 3



Design principles (from TRD):

  1. spaCy dependency-parse-based attribute binding -- NOT flat keyword scan.

  2. Negation: surface phrases + -less suffix + spaCy neg dep.

     CRITICAL: negation scope is bounded to the immediately following noun,

     not the entire remainder of the sentence.

  3. Counting: 12 regex patterns.

  4. Spatial: left_of / right_of ONLY.

  5. Synonym lookup via SYNONYM_MAP.

  6. Fuzzy matching only for tokens >= FUZZY_MIN_LEN (4 chars), dist <= 2.

  7. Multi-word color phrases (dark blue, light gray) resolved as bigrams.

"""



from __future__ import annotations



import re

import logging

from dataclasses import dataclass, field

from typing import TypedDict, Optional



logger = logging.getLogger(__name__)



# ---------------------------------------------------------------------------

# Lazy spaCy load

# ---------------------------------------------------------------------------

_NLP = None



def _get_nlp():

    global _NLP

    if _NLP is None:

        try:

            import spacy

            _NLP = spacy.load("en_core_web_sm")

            logger.info("spaCy model loaded: en_core_web_sm")

        except OSError:

            raise RuntimeError(

                "spaCy model not found. Run: python -m spacy download en_core_web_sm"

            )

    return _NLP



# ---------------------------------------------------------------------------

# Local imports

# ---------------------------------------------------------------------------

from .patterns import (

    NEGATION_PHRASES, NEGATION_SUFFIX_RE, NEGATION_DEP_LABELS,

    COUNTING_PATTERNS, parse_count_token,

    SPATIAL_TRIGGERS,

    COLOR_VOCAB, resolve_color,

    FUZZY_MIN_LEN, FUZZY_MAX_DIST,

)

from backend.vision.vocabulary import VOCABULARY_SET, resolve_synonym

# ---------------------------------------------------------------------------
# PROMPT 5: Query pre-processing (Tasks 1 & 2)
# ---------------------------------------------------------------------------

# Task 2: Color prefixes for compound splitting ("redshirt" → "red shirt")
# Build from COLOR_VOCAB single-word entries only
_SINGLE_COLORS: tuple[str, ...] = tuple(sorted(
    [c for c in COLOR_VOCAB if " " not in c],
    key=len, reverse=True  # longest first to avoid partial matches
))

# Task 1: "with no X" / "having no X" / "wearing no X" → "without X"
_WITH_NO_RE = re.compile(
    r"\b(with|having|wearing)\s+no\s+",
    re.IGNORECASE,
)

# Fix 3A: bare "no" negation → "without" (e.g. "person no helmet")
# Pattern: noun/adjective SPACE "no" SPACE → noun SPACE "without" SPACE
# Anchored to word boundaries; excludes "no " at the start of a sentence
# ("no helmet" alone is parsed fine by spaCy; we only need to handle
# mid-phrase "X no Y" → "X without Y").
_BARE_NO_RE = re.compile(
    r"(?<=\w)\s+no\s+",
    re.IGNORECASE,
)

# Fix 3A: "lacking" → "without"
_LACKING_RE = re.compile(
    r"\blacking\s+",
    re.IGNORECASE,
)

# Task 3: "wearing" → "in" for positive garment color binding.
# "person wearing red shirt" → "person in red shirt" → color=red binds to person.
# NEGATIVE LOOKBEHIND: preserves "not wearing", "isn't wearing", "is not wearing"
# so negation phrases in NEGATION_PHRASES still trigger correctly.
_WEARING_RE = re.compile(
    r"(?<!not )(?<!isn't )(?<!is not )(?<!doesn't )\bwearing\b",
    re.IGNORECASE,
)

def _preprocess_query(query: str) -> str:
    """
    Normalise common user phrasings before spaCy parsing.

    Task 0 (Fix 3A): bare "no" and "lacking" negation:
            "person no helmet"     → "person without helmet"
            "person lacking helmet" → "person without helmet"

    Task 1: "with no"/"having no"/"wearing no" → "without "
            (belt-and-suspenders: spaCy negation already handles many,
             but pre-processing ensures the negation phrase triggers correctly)

    Task 2: Split color+object compounds:
            "redshirt" → "red shirt"
            "bluecar"  → "blue car"
            Only splits if remainder after color is a VOCABULARY_SET member.
    """
    # Task 0 (Fix 3A): normalize non-standard negation phrasings BEFORE spaCy.
    # Order matters: _WITH_NO_RE must run first to consume "with no"/"having no"
    # before _BARE_NO_RE sees the bare "no" residual.
    q = _WITH_NO_RE.sub("without ", query)    # "with no X" → "without X" (Task 1 kept here)
    q = _BARE_NO_RE.sub(" without ", q)       # "X no Y"    → "X without Y"
    q = _LACKING_RE.sub("without ", q)        # "lacking X" → "without X"

    # Task 3: "wearing" → "in" for garment color binding.
    # "person wearing red shirt" → "person in red shirt" so the spaCy color
    # binder picks up color=red on the "person" object via existing "in" logic.
    # Run AFTER negation normalization: "wearing no" already became "without",
    # and lookbehind guards "not wearing"/"isn't wearing" from being altered.
    q = _WEARING_RE.sub("in", q)              # "wearing X" → "in X" (positive only)

    # Task 2: split runtogethercolor+noun compounds, word by word
    tokens = q.split()
    new_tokens = []
    for tok in tokens:
        tok_l = tok.lower()
        split_done = False
        for color in _SINGLE_COLORS:
            if tok_l.startswith(color) and len(tok_l) > len(color):
                remainder = tok_l[len(color):]
                # Check remainder is a vocabulary word (or resolves to one)
                if remainder in VOCABULARY_SET or resolve_synonym(remainder) in VOCABULARY_SET:
                    new_tokens.append(color)
                    new_tokens.append(remainder)
                    split_done = True
                    break
        if not split_done:
            new_tokens.append(tok)
    return " ".join(new_tokens)







# ---------------------------------------------------------------------------

# Output types

# ---------------------------------------------------------------------------



class ObjectSpec(TypedDict):

    class_name:  str

    color:       Optional[str]

    negated:     bool

    count_op:    Optional[str]

    count_val:   Optional[int]





class SpatialSpec(TypedDict):

    subject:  str

    relation: str

    object_:  str





@dataclass

class ParseResult:

    raw_query:         str

    objects:           list[ObjectSpec]  = field(default_factory=list)

    spatial:           list[SpatialSpec] = field(default_factory=list)

    qdrant_filter:     dict              = field(default_factory=dict)

    unresolved_tokens: list[str]         = field(default_factory=list)

    warnings:          list[str]         = field(default_factory=list)



    def to_response(self) -> dict:

        """

        Odysseus contract wrapper.

        Returns {"status": "ok", "filters": <qdrant_filter_dict>,

                 "unresolved_tokens": [...]}.

        unresolved_tokens is [] on a fully-resolved query.

        When non-empty with filters=={}, Odysseus's gateway should skip

        the Qdrant call (empty filter would match everything).

        Does not modify qdrant_filter internals.

        """

        return {

            "status":            "ok",

            "filters":           self.qdrant_filter,

            "unresolved_tokens": self.unresolved_tokens,

        }



    def __repr__(self) -> str:

        return (

            f"ParseResult(\n"

            f"  objects={self.objects}\n"

            f"  spatial={self.spatial}\n"

            f"  qdrant_filter={self.qdrant_filter}\n"

            f")"

        )





# ---------------------------------------------------------------------------

# Fuzzy matching (Levenshtein)

# ---------------------------------------------------------------------------



def _levenshtein(a: str, b: str) -> int:

    if a == b: return 0

    la, lb = len(a), len(b)

    if la == 0: return lb

    if lb == 0: return la

    prev = list(range(lb + 1))

    for i, ca in enumerate(a):

        curr = [i + 1]

        for j, cb in enumerate(b):

            curr.append(min(prev[j] + (0 if ca == cb else 1),

                            curr[j] + 1, prev[j + 1] + 1))

        prev = curr

    return prev[lb]





# Tokens that are counting quantifiers — must NEVER be matched as vocabulary

# objects, even if they fuzzy-match a vocab term (e.g. 'couple' -> 'coupe').

_COUNT_QUANTIFIER_STOPWORDS: frozenset[str] = frozenset({

    "couple", "few", "several", "many", "some", "more", "less", "fewer",

    "least", "most", "exactly", "only", "than",

})





def _fuzzy_match_vocab(token: str) -> str | None:

    """

    Exact + synonym + plural stemming + fuzzy vocabulary lookup.



    CRITICAL rules:

    - Color words are EXCLUDED from object matching (they are attributes).

    - Fuzzy only for len >= 6, dist <= 1 (conservative to avoid

      false positives like wearing->earring, leave->leaf, black->back).

    - Plural stemming handles cars->car, workers->worker.

    """

    token_l = token.lower().strip()

    if not token_l:

        return None



    # 0a. Skip pure color words -- they are attributes, not objects

    if resolve_color(token_l) is not None:

        return None



    # 0b. Skip count quantifier words -- they are never vocabulary objects

    #     (e.g. 'couple' must not fuzzy-match 'coupe')

    if token_l in _COUNT_QUANTIFIER_STOPWORDS:

        return None



    # 1. Synonym lookup FIRST — handles lemma normalisation (e.g. spaCy

    #    lemmatizes 'glasses' -> 'glass'; synonym map sends 'glass' -> 'glasses')

    resolved = resolve_synonym(token_l)

    if resolved != token_l and resolved in VOCABULARY_SET:

        return resolved



    # 2. Direct vocabulary hit

    if token_l in VOCABULARY_SET:

        return token_l



    # 3. Synonym lookup for non-normalisation cases (token not in vocab)

    if resolved in VOCABULARY_SET:

        return resolved



    # 3. Simple plural / inflection stemming

    #    Handles: cars->car, workers->worker, people->person, motorcycles->motorcycle

    stems: list[str] = []

    if token_l.endswith("ies") and len(token_l) > 4:

        stems.append(token_l[:-3] + "y")      # cities->city

    if token_l.endswith("ves") and len(token_l) > 4:

        stems.append(token_l[:-3] + "f")      # knives->knife

    if token_l.endswith("es") and len(token_l) > 3:

        stems.append(token_l[:-2])             # buses->bus

    if token_l.endswith("s") and len(token_l) > 3:

        stems.append(token_l[:-1])             # cars->car

    if token_l.endswith("ing") and len(token_l) > 5:

        stems.append(token_l[:-3])             # standing->stand (rough)

        stems.append(token_l[:-3] + "e")      # running->rune? skip false cases handled by color guard



    for stem in stems:

        if stem in VOCABULARY_SET:

            return stem

        r = resolve_synonym(stem)

        if r in VOCABULARY_SET:

            return r



    # 4. Fuzzy Levenshtein -- ONLY for tokens with len >= 6, dist <= 1

    #    (conservative: prevents leave->leaf, black->back, wearing->earring)

    if len(token_l) >= 6:

        best_term: str | None = None

        best_dist: int = 1  # max allowed distance

        for term in VOCABULARY_SET:

            if abs(len(term) - len(token_l)) > best_dist:

                continue  # fast length-diff rejection

            d = _levenshtein(token_l, term)

            if d < best_dist or (d == best_dist and best_term is None):

                best_term, best_dist = term, d

        if best_term:

            logger.debug("Fuzzy: '%s' -> '%s' (dist=%d)", token_l, best_term, best_dist)

            return best_term



    return None





# ---------------------------------------------------------------------------

# Multi-word color resolution

# ---------------------------------------------------------------------------



def _resolve_color_bigram(tokens: list[str]) -> tuple[str | None, int]:

    """

    Try to match a 2-gram then 1-gram color from a token list.

    Returns (color_name, tokens_consumed) or (None, 0).

    """

    if len(tokens) >= 2:

        bigram = tokens[0] + " " + tokens[1]

        c = resolve_color(bigram)

        if c:

            return c, 2

    if tokens:

        c = resolve_color(tokens[0])

        if c:

            return c, 1

    return None, 0





# ---------------------------------------------------------------------------

# Negation: bounded scope

# ---------------------------------------------------------------------------



def _find_negation_spans(text_lower: str) -> list[tuple[int, int]]:

    """Return (start, end) char offsets of every negation trigger phrase."""

    spans: list[tuple[int, int]] = []

    for phrase in sorted(NEGATION_PHRASES, key=len, reverse=True):

        for m in re.finditer(r'\b' + re.escape(phrase) + r'\b', text_lower):

            spans.append((m.start(), m.end()))

    return spans





def _token_is_syntactically_negated(token) -> bool:

    """True if spaCy assigns a neg-dep child to this token or its head."""

    for child in token.children:

        if child.dep_ in NEGATION_DEP_LABELS:

            return True

    return False





def _negation_bounded_to_token(token, neg_spans: list[tuple[int,int]], doc) -> bool:

    """

    True if this token falls IMMEDIATELY after a negation phrase AND

    no other noun (vocabulary token) appears between the phrase end and this token.

    This bounds negation scope to the first noun after the trigger.

    """

    tok_start = token.idx

    for (neg_start, neg_end) in neg_spans:

        if neg_end > tok_start:

            continue  # negation phrase is AFTER the token

        # Check: is there any other vocabulary noun between neg_end and tok_start?

        gap_text = doc.text[neg_end:tok_start]

        intermediate_nouns = [

            w for w in gap_text.split()

            if _fuzzy_match_vocab(w) is not None and resolve_color(w) is None

        ]

        if len(intermediate_nouns) == 0:

            return True  # negation phrase directly precedes this token

    return False





# ---------------------------------------------------------------------------

# Core: spaCy object extraction with dependency-bound attributes

# ---------------------------------------------------------------------------



def _extract_objects_spacy(query: str) -> list[ObjectSpec]:

    """

    Extract objects with dependency-bound color and negation.



    Key design: color is bound via amod/compound dependency edge to the

    head noun, preventing "red shirt blue car" from swapping colours.

    Negation is bounded: only the FIRST noun after a negation trigger is

    marked negated, not everything downstream.

    """

    nlp = _get_nlp()

    doc = nlp(query)

    objects: list[ObjectSpec] = []

    seen_idx: set[int] = set()

    text_lower = query.lower()

    neg_spans = _find_negation_spans(text_lower)



    for token in doc:

        if token.i in seen_idx:

            continue



        lemma = token.lemma_.lower()

        surface = token.text.lower()



        # Check -less suffix FIRST (e.g. "helmetless")

        m_less = NEGATION_SUFFIX_RE.fullmatch(surface)

        if m_less:

            stem_canon = _fuzzy_match_vocab(m_less.group(1).lower())

            if stem_canon:

                seen_idx.add(token.i)

                objects.append(ObjectSpec(

                    class_name=stem_canon,

                    color=None,

                    negated=True,

                    count_op=None,

                    count_val=None,

                ))

                continue



        canon = _fuzzy_match_vocab(lemma) or _fuzzy_match_vocab(surface)

        if canon is None:

            continue

        seen_idx.add(token.i)



        # --- Color binding via dependency edges ---

        bound_color: str | None = None



        # (a) Direct amod/compound child of this token

        amod_children = [

            c for c in token.children

            if c.dep_ in ("amod", "compound", "nmod")

        ]

        for child in amod_children:

            child_tokens = [child.text.lower()]

            # Try to grab a preceding sibling for bigrams like "dark blue"

            if child.i > 0:

                prev_tok = doc[child.i - 1]

                child_tokens = [prev_tok.text.lower()] + child_tokens

            c, _ = _resolve_color_bigram(child_tokens)

            if c:

                bound_color = c

                break

            # single token fallback

            c = resolve_color(child.text.lower())

            if c:

                bound_color = c

                break



        # (a2) prep→pobj color binding: "person in red" / "car in dark blue"

        #      spaCy parse: person(ROOT)→in(prep)→red(pobj)

        if bound_color is None:

            for prep_child in token.children:

                if prep_child.dep_ != "prep":

                    continue

                for pobj in prep_child.children:

                    if pobj.dep_ != "pobj":

                        continue

                    # Try bigram: amod child of pobj + pobj (e.g. "dark" + "blue")

                    amod_of_pobj = [c for c in pobj.children if c.dep_ == "amod"]

                    if amod_of_pobj:

                        bigram = [amod_of_pobj[0].text.lower(), pobj.text.lower()]

                        c, _ = _resolve_color_bigram(bigram)

                        if c:

                            bound_color = c

                            break

                    # Single-word pobj color

                    c = resolve_color(pobj.text.lower())

                    if c:

                        bound_color = c

                        break

                if bound_color:

                    break



        # (b) Token is itself modified by a color in a prepositional / appositive chain

        if bound_color is None:

            # Look for amod on the same head

            for sibling in token.head.children:

                if sibling.i == token.i:

                    continue

                if sibling.dep_ in ("amod", "compound"):

                    # bigram: sibling-1 + sibling

                    sib_tokens = [sibling.text.lower()]

                    if sibling.i > 0:

                        sib_tokens = [doc[sibling.i-1].text.lower()] + sib_tokens

                    c, _ = _resolve_color_bigram(sib_tokens)

                    if c:

                        bound_color = c

                        break

                    c = resolve_color(sibling.text.lower())

                    if c:

                        bound_color = c

                        break



        # (c) Scan up to 2 tokens to the LEFT of this token for standalone colors

        if bound_color is None:

            left_window = [doc[i].text.lower() for i in range(max(0, token.i-2), token.i)]

            if left_window:

                c, _ = _resolve_color_bigram(left_window)

                if c:

                    bound_color = c

                elif left_window:

                    c = resolve_color(left_window[-1])

                    if c:

                        bound_color = c



        # --- Negation binding (bounded scope) ---

        negated = _token_is_syntactically_negated(token)

        if not negated:

            negated = _negation_bounded_to_token(token, neg_spans, doc)



        objects.append(ObjectSpec(

            class_name=canon,

            color=bound_color,

            negated=negated,

            count_op=None,

            count_val=None,

        ))



    return objects





# ---------------------------------------------------------------------------

# Counting extraction

# ---------------------------------------------------------------------------



def _extract_counts(query: str) -> list[tuple[str, str, int]]:

    """Return list of (class_name, operator, count) tuples."""

    results: list[tuple[str, str, int]] = []

    text_lower = query.lower()



    for idx, (pattern, operator, count_group) in enumerate(COUNTING_PATTERNS):

        for m in pattern.finditer(text_lower):

            raw_count = m.group(count_group) if count_group else None

            count = parse_count_token(raw_count, idx)



            # Find nearest vocab noun AFTER the match

            remainder = text_lower[m.end():].strip()

            words = remainder.split()

            for word in words[:6]:

                # Skip prepositions and short stop words

                if word in ("the", "a", "an", "of", "to", "in", "on", "at"):

                    continue

                c = _fuzzy_match_vocab(word)

                if c:

                    results.append((c, operator, count))

                    break



    return results





# ---------------------------------------------------------------------------

# Spatial extraction

# ---------------------------------------------------------------------------



def _extract_spatial(query: str) -> list[SpatialSpec]:

    """Detect left_of / right_of patterns."""

    results: list[SpatialSpec] = []

    text_lower = query.lower()



    for pattern, relation in SPATIAL_TRIGGERS:

        for m in pattern.finditer(text_lower):

            before = text_lower[:m.start()].strip()

            after  = text_lower[m.end():].strip()



            # Subject: last vocab noun before trigger

            subject = None

            for w in reversed(before.split()):

                if w in ("the", "a", "an", "of"): continue

                c = _fuzzy_match_vocab(w)

                if c:

                    subject = c

                    break



            # Object: first vocab noun after trigger

            obj = None

            for w in after.split():

                if w in ("the", "a", "an", "of"): continue

                c = _fuzzy_match_vocab(w)

                if c:

                    obj = c

                    break



            if subject and obj and subject != obj:

                results.append(SpatialSpec(

                    subject=subject,

                    relation=relation,

                    object_=obj,

                ))



    return results





# ---------------------------------------------------------------------------

# Qdrant filter builder

# ---------------------------------------------------------------------------



def _build_qdrant_filter(

    objects: list[ObjectSpec],

    spatial: list[SpatialSpec],

    count_specs: list[tuple[str, str, int]],

) -> dict:

    must:     list[dict] = []

    must_not: list[dict] = []



    for obj in objects:

        if obj["negated"]:

            must_not.append({"key": "detections[].class_name",

                             "match": {"value": obj["class_name"]}})

        else:

            must.append({"key": "detections[].class_name",

                         "match": {"value": obj["class_name"]}})

            if obj["color"]:

                must.append({"key": "detections[].color",

                             "match": {"value": obj["color"]}})



    counts_filter = [

        {"class_name": cls, "operator": op, "value": val}

        for cls, op, val in count_specs

    ]

    spatial_filter = [

        {"subject": s["subject"], "relation": s["relation"], "object": s["object_"]}

        for s in spatial

    ]



    result: dict = {}

    if must:          result["must"]    = must

    if must_not:      result["must_not"]= must_not

    if spatial_filter:result["spatial"] = spatial_filter

    if counts_filter: result["counts"]  = counts_filter

    return result





# ---------------------------------------------------------------------------

# Public QueryParser

# ---------------------------------------------------------------------------



class QueryParser:

    """

    Rule-based query parser. Thread-safe. Create once per process.

    """

    def __init__(self) -> None:

        _get_nlp()



    def parse(self, query: str) -> ParseResult:

        if not query or not query.strip():

            return ParseResult(raw_query=query)

        query = query.strip()
        query = _preprocess_query(query)
        objects     = _extract_objects_spacy(query)

        count_specs = _extract_counts(query)

        spatial     = _extract_spatial(query)



        # Merge count specs into matching objects (or append new)

        for cls, op, val in count_specs:

            merged = False

            for obj in objects:

                if obj["class_name"] == cls and obj["count_op"] is None:

                    obj["count_op"] = op

                    obj["count_val"] = val

                    merged = True

                    break

            if not merged:

                objects.append(ObjectSpec(

                    class_name=cls, color=None, negated=False,

                    count_op=op, count_val=val,

                ))



        qdrant_filter = _build_qdrant_filter(objects, spatial, count_specs)



        # Diagnostics: collect unresolved content words

        nlp = _get_nlp()

        doc = nlp(query)

        resolved = {o["class_name"] for o in objects}

        unresolved = []

        for tok in doc:

            if tok.is_stop or tok.is_punct or tok.pos_ in ("DET","ADP","CONJ","CCONJ","NUM"):

                continue

            if _fuzzy_match_vocab(tok.text.lower()): continue

            if resolve_color(tok.text.lower()): continue

            if tok.lemma_.lower() in resolved: continue

            unresolved.append(tok.text.lower())



        # PROMPT 5 Task 3: If no objects resolved but content words present → warning
        parse_warnings: list[str] = []
        if not objects and unresolved:
            vocab_sample = ", ".join(sorted(VOCABULARY_SET)[:8])
            parse_warnings.append(
                f"Could not find any known objects in query. Try: {vocab_sample} ..."
            )
            logger.info("Parser: no objects resolved for '%s', unresolved=%s", query, unresolved)

        return ParseResult(
            raw_query=query,
            objects=objects,
            spatial=spatial,
            qdrant_filter=qdrant_filter,
            unresolved_tokens=list(set(unresolved)),
            warnings=parse_warnings,
        )





# ---------------------------------------------------------------------------

# Module convenience

# ---------------------------------------------------------------------------

_PARSER_SINGLETON: QueryParser | None = None



def get_parser() -> QueryParser:

    global _PARSER_SINGLETON

    if _PARSER_SINGLETON is None:

        _PARSER_SINGLETON = QueryParser()

    return _PARSER_SINGLETON



def parse_query(query: str) -> ParseResult:

    return get_parser().parse(query)

