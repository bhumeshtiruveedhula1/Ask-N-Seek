"""
engine/parse_lens.py — Live Parse Lens (Transparent Query Workbench) for Ask-N-Seek.

Builds a real-time dependency-parse tree from spaCy doc to visualize how
the rule-based parser binds modifiers (colors, counts, negations, spatial relations)
to head nouns.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from backend.vision.vocabulary import VOCABULARY_SET, resolve_synonym
from backend.query.patterns import COLOR_VOCAB, resolve_color, NEGATION_PHRASES, SPATIAL_TRIGGERS
from backend.query.query_parser import _get_nlp, parse_query, _fuzzy_match_vocab

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------

@dataclass
class ParseNode:
    token_text: str
    token_lemma: str
    dep: str           # e.g. "amod", "compound", "neg", "ROOT", "pobj"
    head_text: str     # The token this node depends on
    children: list[ParseNode] = field(default_factory=list)
    is_entity: bool = False     # Is this token in fixed vocabulary?
    is_color: bool = False      # Is this token in color vocabulary?
    is_negation: bool = False   # Is this a negation trigger?
    is_spatial: bool = False    # Is this a spatial trigger (left/right)?


@dataclass
class ParseTree:
    query_text: str
    root_nodes: list[ParseNode]
    entities: list[dict]        # Objects extracted by parser
    unresolved: list[str]


# ---------------------------------------------------------------------------
# Parse Tree Extractor
# ---------------------------------------------------------------------------

def _is_negation_token(tok) -> bool:
    if tok.dep_ == "neg" or tok.text.lower() in ("no", "not", "without", "bina", "missing", "lacking"):
        return True
    if tok.text.lower().endswith("less") and len(tok.text) > 4:
        return True
    return False


def _is_spatial_token(tok) -> bool:
    t_low = tok.text.lower()
    return t_low in ("left", "right") or any(sp_name in t_low for sp_name in ("left_of", "right_of"))


def _build_node_recursive(tok, nlp_doc) -> ParseNode:
    t_text = tok.text
    t_lemma = tok.lemma_.lower()

    color_res = resolve_color(t_text.lower())
    is_color = color_res is not None
    
    vocab_res = _fuzzy_match_vocab(t_lemma) or _fuzzy_match_vocab(t_text)
    is_entity = (vocab_res is not None) and (not is_color)

    is_neg = _is_negation_token(tok)
    is_sp = _is_spatial_token(tok)

    children_nodes = [_build_node_recursive(child, nlp_doc) for child in tok.children]

    return ParseNode(
        token_text=t_text,
        token_lemma=t_lemma,
        dep=tok.dep_,
        head_text=tok.head.text,
        children=children_nodes,
        is_entity=is_entity,
        is_color=is_color,
        is_negation=is_neg,
        is_spatial=is_sp,
    )


def extract_parse_tree(
    query_text: str,
    nlp=None,
    vocab=None,
    color_vocab=None,
    spatial_triggers=None,
) -> ParseTree:
    """
    Walk spaCy Doc and build a tree representation mirroring the parser's dependency bindings.
    """
    if not query_text or not query_text.strip():
        return ParseTree(query_text=query_text, root_nodes=[], entities=[], unresolved=[])

    if nlp is None:
        nlp = _get_nlp()

    doc = nlp(query_text.strip())

    # Obtain structured parse result from query_parser
    parse_res = parse_query(query_text)
    entities = getattr(parse_res, "objects", []) or []
    if isinstance(entities, list) and entities and hasattr(entities[0], "__dict__"):
        entities = [dict(e) for e in entities]
    elif not entities and hasattr(parse_res, "qdrant_filter"):
        entities = parse_res.qdrant_filter.get("must", [])

    unresolved = getattr(parse_res, "unresolved_tokens", []) or []

    # Build node hierarchy starting from doc roots (token.head == token)
    root_tokens = [tok for tok in doc if tok.head.i == tok.i]
    root_nodes = [_build_node_recursive(rt, doc) for rt in root_tokens]

    tree = ParseTree(
        query_text=query_text,
        root_nodes=root_nodes,
        entities=entities,
        unresolved=unresolved,
    )

    ParseLensNarrator.on_tree_render(query_text, entities)

    return tree


# ---------------------------------------------------------------------------
# HTML Renderer
# ---------------------------------------------------------------------------

def _render_node_html(node: ParseNode) -> str:
    dep_class = ""
    if node.dep in ("amod", "nmod"):
        dep_class = "parse-node-amod"
    elif node.dep in ("compound", "compound:prt"):
        dep_class = "parse-node-compound"
    elif node.dep in ("neg",) or node.is_negation:
        dep_class = "parse-node-neg"
    elif node.is_spatial:
        dep_class = "parse-node-spatial"

    tag_class = ""
    if node.is_entity:
        tag_class += " parse-entity"
    elif node.is_color:
        tag_class += " parse-color"

    badge_dep = f'<span style="font-size:0.7rem;opacity:0.6;margin-left:6px;font-weight:normal;">[{node.dep}]</span>' if node.dep else ""
    head_rel = f' <span style="font-size:0.7rem;color:#64748b;">&rarr; {node.head_text}</span>' if node.dep and node.dep != "ROOT" else ""

    label_html = f'<span class="{tag_class.strip()}">{node.token_text}</span>{badge_dep}{head_rel}'

    children_html = ""
    if node.children:
        child_items = "".join(f"<li>{_render_node_html(child)}</li>" for child in node.children)
        children_html = f'<ul style="list-style:none;padding-left:14px;margin:4px 0 0;">{child_items}</ul>'

    return f"""
    <div class="{dep_class}" style="margin:3px 0;">
      {label_html}
      {children_html}
    </div>
    """


def render_tree_html(tree: ParseTree) -> str:
    """Render ParseTree into modern HTML representation."""
    if not tree.root_nodes:
        return '<div class="parse-lens"><em>Type a query to see the parse tree...</em></div>'

    roots_html = "".join(_render_node_html(r) for r in tree.root_nodes)

    # Entities summary bar
    ent_badges = []
    for e in tree.entities:
        if isinstance(e, dict):
            c_name = e.get("class_name") or e.get("class") or "object"
            col = e.get("color")
            neg = e.get("negated")
            label = f"{col + ' ' if col else ''}{c_name}{' (NEGATED)' if neg else ''}"
            b_bg = "#ef4444" if neg else "#10b981"
            ent_badges.append(
                f'<span style="background:rgba(16,185,129,0.15);color:{b_bg};border:1px solid {b_bg};padding:2px 8px;border-radius:12px;font-size:0.75rem;font-weight:600;">{label}</span>'
            )

    ent_summary = f'<div style="display:flex;gap:6px;flex-wrap:wrap;margin-bottom:10px;">{" ".join(ent_badges)}</div>' if ent_badges else ""

    return f"""
<div class="parse-lens" style="
    background: #0d0d20;
    border: 1px solid #1e1e3f;
    border-radius: 8px;
    padding: 14px 16px;
    color: #e2e8f0;
    font-family: 'JetBrains Mono', 'Fira Code', 'Courier New', monospace;
    font-size: 0.82rem;
    line-height: 1.6;
">
  <div style="font-size:0.75rem;color:#818cf8;font-weight:600;text-transform:uppercase;letter-spacing:0.8px;margin-bottom:8px;">
    🌿 Live Parse Lens — Dependency Tree
  </div>
  {ent_summary}
  <div>
    {roots_html}
  </div>
</div>
"""


# ---------------------------------------------------------------------------
# ASCII Renderer
# ---------------------------------------------------------------------------

def _render_node_ascii(node: ParseNode, prefix: str = "", is_last: bool = True) -> list[str]:
    lines = []
    connector = "└── " if is_last else "├── "
    dep_str = f" [{node.dep}]" if node.dep else ""
    head_str = f" → {node.head_text}" if node.head_text and node.dep != "ROOT" else ""
    flag_str = ""
    if node.is_entity:
        flag_str += " [ENTITY]"
    if node.is_color:
        flag_str += " [COLOR]"
    if node.is_spatial:
        flag_str += " [SPATIAL]"
    if node.is_negation:
        flag_str += " [NEG]"

    lines.append(f"{prefix}{connector}{node.token_text}{dep_str}{head_str}{flag_str}")

    child_prefix = prefix + ("    " if is_last else "│   ")
    for i, child in enumerate(node.children):
        c_last = (i == len(node.children) - 1)
        lines.extend(_render_node_ascii(child, child_prefix, c_last))

    return lines


def render_tree_ascii(tree: ParseTree) -> str:
    """Render ParseTree into monospace ASCII string."""
    if not tree.root_nodes:
        return "(empty tree)"

    lines = []
    for r in tree.root_nodes:
        dep_str = f" [{r.dep}]" if r.dep else ""
        lines.append(f"{r.token_text}{dep_str}")
        for i, child in enumerate(r.children):
            c_last = (i == len(r.children) - 1)
            lines.extend(_render_node_ascii(child, "", c_last))

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Presenter Narration Hook
# ---------------------------------------------------------------------------

class ParseLensNarrator:
    """Prints presenter lines about the parse lens to stdout."""
    @staticmethod
    def on_tree_render(query: str, entities: list):
        if len(entities) > 1:
            logger.info("🎤 NARRATOR: See how modifiers are bound to head nouns via dependency edges — not floating loose.")
        if any(e.get("negated") for e in entities if isinstance(e, dict)):
            logger.info("🎤 NARRATOR: The negation edge shows negated targets are marked as absent — a must_not filter in Qdrant.")
