"""
app/main.py — FastAPI application for the Skye drone education agent.

Endpoints:
    GET /health
    GET /check?lat=&lon=&session_id=&flight_time=&planned_altitude_ft=&radius_m=
    GET /rules?query=&session_id=
    GET /check/stream, GET /rules/stream — same parameters, Server-Sent Events
        (event types are documented in app/composer.py)
"""
from __future__ import annotations

import datetime as dt
import json
import logging
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator, Optional

import httpx
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from app import composer
from app.providers import faa_class_airspace, faa_facility_map, http_client as provider_http, weather as weather_provider
from app.rules.chroma_store import get_store
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
    provider_http.set_http_client(http_client)

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

    provider_http.set_http_client(None)
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
        "(FAA airspace and facility map, NSUFR, live FAA TFRs, weather, USGS protected areas, "
        "population exposure, USGS water) and returns a structured briefing. "
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
    return await composer.check_location(
        lat=lat,
        lon=lon,
        session_id=session_id,
        flight_time=_parse_flight_time(flight_time),
        planned_altitude_ft=planned_altitude_ft,
        radius_m=radius_m,
    )


@app.get(
    "/check/stream",
    summary="Location flight check (streamed)",
    description="Same as /check, streamed as Server-Sent Events. The final `done` event carries the CheckResponse.",
)
async def check_stream(
    lat: float = Query(..., ge=-90, le=90),
    lon: float = Query(..., ge=-180, le=180),
    session_id: Optional[str] = Query(None),
    flight_time: Optional[str] = Query(None),
    planned_altitude_ft: Optional[int] = Query(None, ge=1),
    radius_m: Optional[float] = Query(None, ge=1, le=5000),
):
    return _sse(composer.check_location_stream(
        lat=lat,
        lon=lon,
        session_id=session_id,
        flight_time=_parse_flight_time(flight_time),
        planned_altitude_ft=planned_altitude_ft,
        radius_m=radius_m,
    ))


def _parse_flight_time(flight_time: Optional[str]) -> Optional[dt.datetime]:
    if not flight_time:
        return None
    try:
        return dt.datetime.fromisoformat(flight_time.replace("Z", "+00:00"))
    except ValueError:
        raise HTTPException(status_code=422, detail=f"Invalid flight_time format: {flight_time!r}")


log = logging.getLogger("skye.stream")


def _sse(events: AsyncIterator[tuple[str, dict[str, Any]]]) -> StreamingResponse:
    """Encode composer stream events as Server-Sent Events; failures become an `error` event."""
    async def body():
        try:
            async for event, data in events:
                yield f"event: {event}\ndata: {json.dumps(data, default=str)}\n\n"
        except Exception as exc:
            log.exception("stream failed")
            yield f"event: error\ndata: {json.dumps({'message': str(exc)})}\n\n"

    return StreamingResponse(
        body(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
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


@app.get(
    "/rules/stream",
    summary="Drone rules question (streamed)",
    description="Same as /rules, streamed as Server-Sent Events. The final `done` event carries the RulesResponse.",
)
async def rules_stream(
    query: str = Query(..., min_length=3),
    session_id: Optional[str] = Query(None),
):
    return _sse(composer.ask_rules_stream(query=query, session_id=session_id))
