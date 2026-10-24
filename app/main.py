"""
app/main.py — FastAPI application for the Skye drone education agent.

Endpoints:
    GET /health
    GET /check?lat=&lon=&session_id=&flight_time=&planned_altitude_ft=&radius_m=
    GET /rules?query=&session_id=
"""
from __future__ import annotations

import datetime as dt
from contextlib import asynccontextmanager
from typing import Optional

import httpx
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from app import composer
from app.providers import faa_class_airspace, faa_facility_map, weather as weather_provider
from app.rules.chroma_dummy import get_store
from app.schema import CheckResponse, RulesResponse


# ---------------------------------------------------------------------------
# Lifespan startup / shutdown
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Shared async HTTP client for all live providers
    http_client = httpx.AsyncClient()
    faa_facility_map.set_http_client(http_client)
    weather_provider.set_http_client(http_client)

    # Load offline GeoJSON fallback into memory (used when USE_LIVE_FAA=false)
    try:
        faa_facility_map.load()
    except Exception as exc:
        print(f"[startup] Warning: could not load facility map: {exc}")
    try:
        faa_class_airspace.load()
    except Exception as exc:
        print(f"[startup] Warning: could not load class airspace: {exc}")

    # Ensure Chroma rules corpus is seeded
    try:
        get_store().ensure_seeded()
    except Exception as exc:
        print(f"[startup] Warning: could not seed Chroma: {exc}")

    yield

    await http_client.aclose()


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

# Allow the Vite dev server (any localhost port) and production origin to call the API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000", "http://localhost:4173"],
    allow_methods=["GET"],
    allow_headers=["*"],
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
async def check(
    lat: float = Query(..., ge=-90, le=90, description="Latitude in decimal degrees"),
    lon: float = Query(..., ge=-180, le=180, description="Longitude in decimal degrees"),
    session_id: Optional[str] = Query(None, description="Optional session ID for repetition control"),
    flight_time: Optional[str] = Query(
        None,
        description="ISO 8601 planned flight time, e.g. 2025-06-01T14:00:00Z",
    ),
    planned_altitude_ft: Optional[int] = Query(
        None, ge=1, description="Planned altitude in feet AGL (from the flight plan form)"
    ),
    radius_m: Optional[float] = Query(
        None, ge=1, le=5000, description="Flight area radius in metres (from the flight plan form)"
    ),
):
    ft: Optional[dt.datetime] = None
    if flight_time:
        try:
            ft = dt.datetime.fromisoformat(flight_time.replace("Z", "+00:00"))
        except ValueError:
            raise HTTPException(status_code=422, detail=f"Invalid flight_time format: {flight_time!r}")

    return await composer.check_location(
        lat=lat,
        lon=lon,
        session_id=session_id,
        flight_time=ft,
        planned_altitude_ft=planned_altitude_ft,
        radius_m=radius_m,
    )


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
