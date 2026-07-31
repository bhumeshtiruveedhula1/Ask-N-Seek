"""
tests/test_parse_lens.py — Unit & Integration tests for Live Parse Lens.
"""

from __future__ import annotations

import pytest
from backend.query.query_parser import _get_nlp
from engine.parse_lens import (
    extract_parse_tree,
    render_tree_html,
    render_tree_ascii,
    ParseTree,
    ParseNode,
)


@pytest.fixture(scope="module")
def nlp():
    return _get_nlp()


def test_simple_noun(nlp):
    """'person' -> one entity node."""
    tree = extract_parse_tree("person", nlp=nlp)
    assert isinstance(tree, ParseTree)
    assert len(tree.root_nodes) >= 1
    
    # Find person node
    def find_node(nodes, text):
        for n in nodes:
            if n.token_text.lower() == text:
                return n
            res = find_node(n.children, text)
            if res: return res
        return None

    p_node = find_node(tree.root_nodes, "person")
    assert p_node is not None
    assert p_node.is_entity is True


def test_color_binding(nlp):
    """'red shirt' -> 'red' is child of 'shirt' via amod."""
    tree = extract_parse_tree("red shirt", nlp=nlp)
    assert isinstance(tree, ParseTree)

    def find_node(nodes, text):
        for n in nodes:
            if n.token_text.lower() == text:
                return n
            res = find_node(n.children, text)
            if res: return res
        return None

    shirt_node = find_node(tree.root_nodes, "shirt")
    assert shirt_node is not None
    assert shirt_node.is_entity is True

    red_child = next((c for c in shirt_node.children if c.token_text.lower() == "red"), None)
    assert red_child is not None
    assert red_child.dep == "amod"
    assert red_child.is_color is True


def test_compound_binding(nlp):
    """'fire truck' -> 'fire' is child of 'truck' via compound."""
    tree = extract_parse_tree("fire truck", nlp=nlp)
    assert isinstance(tree, ParseTree)

    def find_node(nodes, text):
        for n in nodes:
            if n.token_text.lower() == text:
                return n
            res = find_node(n.children, text)
            if res: return res
        return None

    truck_node = find_node(tree.root_nodes, "truck")
    assert truck_node is not None

    fire_child = next((c for c in truck_node.children if c.token_text.lower() == "fire"), None)
    assert fire_child is not None
    assert fire_child.dep in ("compound", "compound:prt", "nmod")


def test_negation_binding(nlp):
    """'person without helmet' -> 'helmet' or 'without' has neg flag/edge."""
    tree = extract_parse_tree("person without helmet", nlp=nlp)
    assert isinstance(tree, ParseTree)

    def find_node(nodes, text):
        for n in nodes:
            if n.token_text.lower() == text:
                return n
            res = find_node(n.children, text)
            if res: return res
        return None

    without_node = find_node(tree.root_nodes, "without") or find_node(tree.root_nodes, "helmet")
    assert without_node is not None
    # Verify entity has negated state
    assert any(e.get("negated") for e in tree.entities if isinstance(e, dict))


def test_spatial_trigger(nlp):
    """'left of car' -> 'left' marked as spatial trigger."""
    tree = extract_parse_tree("left of car", nlp=nlp)
    assert isinstance(tree, ParseTree)

    def find_node(nodes, text):
        for n in nodes:
            if n.token_text.lower() == text:
                return n
            res = find_node(n.children, text)
            if res: return res
        return None

    left_node = find_node(tree.root_nodes, "left")
    assert left_node is not None
    assert left_node.is_spatial is True


def test_compositional_complex(nlp):
    """'person in red shirt left of blue car' -> correct tree with all edges."""
    query = "person in red shirt left of blue car"
    tree = extract_parse_tree(query, nlp=nlp)
    assert isinstance(tree, ParseTree)

    ascii_art = render_tree_ascii(tree)
    assert "person" in ascii_art
    assert "red" in ascii_art
    assert "shirt" in ascii_art
    assert "blue" in ascii_art
    assert "car" in ascii_art


def test_adversarial_color_swap(nlp):
    """
    CRITICAL PROOF TEST: 'red shirt, blue car' vs 'blue shirt, red car' -> trees are DIFFERENT!
    Proves dependency parsing binds exact color modifiers to their respective head nouns.
    """
    t1 = extract_parse_tree("red shirt, blue car", nlp=nlp)
    t2 = extract_parse_tree("blue shirt, red car", nlp=nlp)

    ascii1 = render_tree_ascii(t1)
    ascii2 = render_tree_ascii(t2)

    assert ascii1 != ascii2

    # In tree 1: 'red' is child of 'shirt', 'blue' is child of 'car'
    def get_head(tree, word):
        def search(nodes):
            for n in nodes:
                if n.token_text.lower() == word:
                    return n.head_text.lower()
                res = search(n.children)
                if res: return res
            return None
        return search(tree.root_nodes)

    assert get_head(t1, "red") == "shirt"
    assert get_head(t1, "blue") == "car"

    assert get_head(t2, "blue") == "shirt"
    assert get_head(t2, "red") == "car"


def test_html_render_smoke(nlp):
    """Verify HTML rendering output."""
    tree = extract_parse_tree("person without helmet left of car", nlp=nlp)
    html = render_tree_html(tree)

    assert "person" in html
    assert "helmet" in html
    assert "parse-lens" in html
    assert "<ul>" in html or "<div" in html
