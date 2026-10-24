"""
app/schema.py — Pydantic request/response models for the FastAPI app.
"""
from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


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


class BriefingSectionSummaries(BaseModel):
    airspace: str
    conditions: str
    restrictions: str
    nearby_risks: str


class BackendBriefingAssessment(BaseModel):
    status: Literal["go", "caution", "no_go"]
    summary: str
    section_summaries: BriefingSectionSummaries


class BriefingFact(BaseModel):
    section: Literal["airspace", "conditions", "restrictions", "nearby_risks"]
    label: str
    value: str
    source: str
    checked_at: Optional[str] = None


class CheckResponse(BaseModel):
    """Response for GET /check — location-based flight briefing."""
    answer_markdown: str
    citations: list[Citation]
    tools_called: list[ToolCallRecord]
    sources_failed: list[str]
    data_freshness: dict[str, str]
    nearby_alternatives: list[str]
    mock_data: bool
    flight_assessment: Optional[Literal["go", "caution", "no_go"]] = None
    assessment_summary: Optional[str] = None
    flight_facts: list[BriefingFact] = Field(default_factory=list)
    section_summaries: Optional[BriefingSectionSummaries] = None


class RulesResponse(BaseModel):
    """Response for GET /rules — plain-English rules question."""
    answer_markdown: str
    citations: list[Citation]
    tools_called: list[ToolCallRecord]
    mock_data: bool
