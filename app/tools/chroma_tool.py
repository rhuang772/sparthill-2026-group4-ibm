"""
app/tools/chroma_tool.py — OpenAI function-calling wrapper for the Chroma rules store.

Exports:
  SEARCH_RULES_SCHEMA  — JSON schema dict for the OpenAI 'tools' list
  search_rules(query, tags, k) -> list[dict]  — callable dispatcher
"""
from __future__ import annotations

from typing import Any

from app.rules.chroma_dummy import get_store

# ---------------------------------------------------------------------------
# OpenAI function schema
# ---------------------------------------------------------------------------

SEARCH_RULES_SCHEMA: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "search_rules",
        "description": (
            "Search the local FAA rules corpus for relevant regulation chunks. "
            "Use semantic terms only — NEVER include coordinates, lat/lon values, "
            "or addresses in the query. Use tags to narrow the search to specific "
            "rule categories (e.g. 'laanc', 'tfr', 'altitude', 'nsufr')."
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
                        "Optional list of rule-category tags to filter results. "
                        "Known tags: controlled_airspace, laanc, uasfm, ceiling, "
                        "altitude, tfr, notam, stadium, sua, prohibited_area, "
                        "nsufr, military, weather, traffic, pending."
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
