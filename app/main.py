"""
app/main.py — FastAPI application for the Skye drone education agent.

Endpoints:
    GET /health
    GET /check?lat=&lon=&session_id=&flight_time=
    GET /rules?query=&session_id=
"""
from __future__ import annotations

import datetime as dt
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import JSONResponse

from app import composer
from app.providers import faa_facility_map
from app.rules.chroma_dummy import get_store
from app.schema import CheckResponse, RulesResponse


# ---------------------------------------------------------------------------
# Lifespan startup
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Load facility map into memory
    try:
        faa_facility_map.load()
    except Exception as exc:
        print(f"[startup] Warning: could not load facility map: {exc}")

    # Ensure Chroma is seeded
    try:
        get_store().ensure_seeded()
    except Exception as exc:
        print(f"[startup] Warning: could not seed Chroma: {exc}")

    yield


app = FastAPI(
    title="Skye — Drone Flight Education Agent",
    description=(
        "Teaches new US drone users where they can fly, why restrictions exist, "
        "and what to check. Skye NEVER says a flight is 'approved', 'legal', 'safe', "
        "or 'clear'. Always verify in an FAA-approved app (e.g. B4UFLY) before flying."
    ),
    version="0.1.0",
    lifespan=lifespan,
)


# ---------------------------------------------------------------------------
# /health
# ---------------------------------------------------------------------------

@app.get("/health", summary="Health check")
def health():
    """Returns service status. No user data is persisted."""
    from app.config import settings
    return {
        "status": "ok",
        "persist_user_data": False,
        "mock_data": settings.USE_SIM,
        "note": (
            "No user data is persisted. Session state is in-process memory only "
            "and is lost on restart."
        ),
    }


# ---------------------------------------------------------------------------
# /check — location-based flight briefing
# ---------------------------------------------------------------------------

@app.get(
    "/check",
    response_model=CheckResponse,
    summary="Location flight check",
    description=(
        "Provide lat/lon from a map pin. Skye automatically calls all location providers "
        "(AirHub sim, FAA facility map, NSUFR, TFR) and returns a structured briefing. "
        "Does NOT return a verdict — reports what sources say and reminds you to verify in B4UFLY."
    ),
)
def check(
    lat: float = Query(..., ge=-90, le=90, description="Latitude in decimal degrees"),
    lon: float = Query(..., ge=-180, le=180, description="Longitude in decimal degrees"),
    session_id: Optional[str] = Query(None, description="Optional session ID for repetition control"),
    flight_time: Optional[str] = Query(
        None,
        description="ISO 8601 planned flight time, e.g. 2025-06-01T14:00:00Z",
    ),
):
    ft: Optional[dt.datetime] = None
    if flight_time:
        try:
            ft = dt.datetime.fromisoformat(flight_time.replace("Z", "+00:00"))
        except ValueError:
            raise HTTPException(status_code=422, detail=f"Invalid flight_time format: {flight_time!r}")

    return composer.check_location(lat=lat, lon=lon, session_id=session_id, flight_time=ft)


# ---------------------------------------------------------------------------
# /rules — plain-English rules question
# ---------------------------------------------------------------------------

@app.get(
    "/rules",
    response_model=RulesResponse,
    summary="Drone rules question",
    description=(
        "Ask a plain-English drone regulation question. Skye searches the local FAA rules "
        "corpus (ChromaDB) and returns an explanation with citations. "
        "No location tools are called."
    ),
)
def rules(
    query: str = Query(..., min_length=3, description="Your rules question, e.g. 'Do I need authorization in Class C airspace?'"),
    session_id: Optional[str] = Query(None, description="Optional session ID for repetition control"),
):
    return composer.ask_rules(query=query, session_id=session_id)
