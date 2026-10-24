"""
app/tools/chroma_tool.py — OpenAI function-calling wrapper for the Chroma rules store.

Exports:
  SEARCH_RULES_SCHEMA  — JSON schema dict for the OpenAI 'tools' list
  search_rules(query, tags, k) -> list[dict]  — callable dispatcher
"""
from __future__ import annotations

from typing import Any

from app.rules.chroma_store import get_store

# ---------------------------------------------------------------------------
# OpenAI function schema
# ---------------------------------------------------------------------------

SEARCH_RULES_SCHEMA: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "search_rules",
        "description": (
            "Search the FAA Remote Pilot (Part 107) study guide: airspace classes and "
            "authorization, special use and other airspace, TFRs, NOTAMs, aviation weather "
            "reports and forecasts, and how weather affects small drones. "
            "Use semantic terms only — NEVER include coordinates, lat/lon values, "
            "or addresses in the query. Use tags to narrow the search (e.g. 'laanc', "
            "'tfr', 'wind', 'thunderstorm')."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": (
                        "Semantic search query using plain-English regulatory terms. "
                        "Example: 'controlled airspace authorization requirements'. "
                        "Do NOT include coordinates."
                    ),
                },
                "tags": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": (
                        "Optional list of topic tags; chunks matching any tag are returned. "
                        "Known tags: airspace, controlled_airspace, laanc, "
                        "uncontrolled_airspace, sua, prohibited_area, restricted_area, "
                        "military, other_airspace, national_security, nsufr, tfr, notam, "
                        "atc, operating_rules, charts, weather, weather_reports, metar, "
                        "forecast, taf, thunderstorm, performance, density_altitude, "
                        "pressure, wind, stability, moisture, clouds, icing, ceiling, "
                        "visibility."
                    ),
                    "default": [],
                },
                "k": {
                    "type": "integer",
                    "description": "Maximum number of rule chunks to return (default 4, max 10).",
                    "default": 4,
                },
            },
            "required": ["query"],
        },
    },
}


# ---------------------------------------------------------------------------
# Callable dispatcher
# ---------------------------------------------------------------------------

def search_rules(
    query: str,
    tags: list[str] | None = None,
    k: int = 4,
) -> list[dict[str, Any]]:
    """Query the local rules store. Returns a list of rule chunk dicts."""
    k = min(k, 10)
    return get_store().query(query_text=query, tags=tags or [], k=k)
