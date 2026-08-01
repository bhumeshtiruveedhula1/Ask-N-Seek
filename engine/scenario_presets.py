"""
engine/scenario_presets.py — One-click investigation scenario presets.

Used by bridge/main.py (/scenarios endpoint) and the Next.js frontend.
No dependencies. Safe to import in mock mode.
"""
from __future__ import annotations

SCENARIO_PRESETS: list[dict[str, str]] = [
    {"id": "safety_violation", "label": "🔴 Safety Violation", "query": "person without helmet"},
    {"id": "traffic_incident", "label": "🚗 Traffic Incident",  "query": "car left of person"},
    {"id": "lost_item",        "label": "🎒 Lost Item",         "query": "backpack without owner"},
    {"id": "access_control",   "label": "🚪 Access Control",    "query": "person without badge"},
    {"id": "crowd_check",      "label": "👥 Crowd Check",       "query": "more than two people"},
]


def get_scenarios() -> list[dict[str, str]]:
    """Return scenario presets for frontend buttons."""
    return list(SCENARIO_PRESETS)
