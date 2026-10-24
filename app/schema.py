"""
app/schema.py — Pydantic request/response models for the FastAPI app.
"""
from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel

from app.judge import AnswerReview


class ToolCallRecord(BaseModel):
    name: str
    args: dict[str, Any]
    status: str
    checked_at: str


class Citation(BaseModel):
    rule_id: str
    citation: str
    source_url: str
    dummy: bool = False


class CheckResponse(BaseModel):
    """Response for GET /check — location-based flight briefing."""
    answer_markdown: str
    citations: list[Citation]
    tools_called: list[ToolCallRecord]
    sources_failed: list[str]
    data_freshness: dict[str, str]
    nearby_alternatives: list[str]
    mock_data: bool
    review: Optional[AnswerReview] = None   # None when ENABLE_ANSWER_REVIEW is false


class RulesResponse(BaseModel):
    """Response for GET /rules — plain-English rules question."""
    answer_markdown: str
    citations: list[Citation]
    tools_called: list[ToolCallRecord]
    mock_data: bool
    review: Optional[AnswerReview] = None
