"""
app/main.py — FastAPI application for the Skye drone education agent.

Endpoints:
    GET /health
    GET /check?lat=&lon=&session_id=&flight_time=&planned_altitude_ft=&radius_m=
    GET /briefing?lat=&lon=&start=&planned_altitude_ft=&radius_m=
    GET /rules?query=&session_id=

The backend data routes are also mounted under /api/*.
"""
from __future__ import annotations

import asyncio
import datetime as dt
import logging
from contextlib import asynccontextmanager
from typing import Optional

import httpx
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware

from app import composer
from app.providers import faa_class_airspace, faa_facility_map, weather as weather_provider
from app.rules.chroma_dummy import get_store
from app.schema import CheckResponse, RulesResponse
from backend.controller import (
    faa_router, park_router, population_router, router as backend_weather_router,
    tfr_router, water_router,
)
from backend.service.faa_service import FaaService
from backend.service.park_service import ParkService
from backend.service.population_service import PopulationService
from backend.service.tfr_service import TfrService
from backend.service.water_service import WaterService
from backend.service.weather_service import WeatherService

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Lifespan startup / shutdown
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Shared async HTTP client for all live providers
    http_client = httpx.AsyncClient()
    app.state.http_client = http_client
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

for backend_router in (
    backend_weather_router, faa_router, tfr_router, water_router,
    population_router, park_router,
):
    app.include_router(backend_router)


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


@app.get(
    "/briefing",
    response_model=CheckResponse,
    summary="Aggregated backend flight briefing",
    description=(
        "Fetches the backend weather, FAA height-limit, TFR, water, population, "
        "and protected-area data, then asks the server-side OpenAI client to "
        "summarize the results."
    ),
)
async def backend_briefing(
    request: Request,
    lat: float = Query(..., ge=-90, le=90),
    lon: float = Query(..., ge=-180, le=180),
    radius_m: float = Query(500, ge=1, le=5000),
    planned_altitude_ft: Optional[int] = Query(None, ge=1),
    start: Optional[dt.datetime] = Query(None, description="Planned flight start, ISO 8601"),
):
    start_at = start or dt.datetime.now(dt.timezone.utc)
    if start_at.tzinfo is None:
        start_at = start_at.replace(tzinfo=dt.timezone.utc)
    start_at = start_at.astimezone(dt.timezone.utc)
    end_at = start_at + dt.timedelta(hours=1)
    now = dt.datetime.now(dt.timezone.utc).isoformat()

    http_client = request.app.state.http_client
    sources = {
        "weather_current": (
            WeatherService(http_client).get_current(lat, lon),
            "observed_at",
            {"lat": lat, "lon": lon},
        ),
        "weather_forecast": (
            WeatherService(http_client).get_window(lat, lon, start_at, end_at),
            "fetched_at",
            {"lat": lat, "lon": lon, "start": start_at.isoformat(), "end": end_at.isoformat()},
        ),
        "faa_height_limit": (
            FaaService(http_client).get_height_limit(lat, lon, radius_m),
            None,
            {"lat": lat, "lon": lon, "radius_m": radius_m},
        ),
        "tfr": (
            TfrService(http_client).get_tfrs(lat, lon, radius_m, start_at, end_at),
            "data_fetched_at",
            {"lat": lat, "lon": lon, "radius_m": radius_m,
             "start": start_at.isoformat(), "end": end_at.isoformat()},
        ),
        "water": (
            WaterService(http_client).get_water(lat, lon, radius_m, include_flowlines=True),
            "fetched_at",
            {"lat": lat, "lon": lon, "radius_m": radius_m, "include_flowlines": True},
        ),
        "population_risk": (
            PopulationService(http_client).get_population_risk(lat, lon, radius_m),
            "fetched_at",
            {"lat": lat, "lon": lon, "radius_m": radius_m},
        ),
        "park_risk": (
            ParkService().get_parks(lat, lon, radius_m),
            "fetched_at",
            {"lat": lat, "lon": lon, "radius_m": radius_m},
        ),
    }

    async def collect(name: str, call, timestamp_field: Optional[str], args: dict):
        try:
            value = await call
            data = value.model_dump(mode="json")
            checked_at = data.get(timestamp_field) if timestamp_field else None
            data_freshness = checked_at or ""
            return name, data, str(data.get("status", "ok")), checked_at or now, data_freshness, args
        except Exception as exc:
            log.exception("Briefing data source %s failed", name)
            error = f"{type(exc).__name__}: {exc}"
            return name, {"status": "failed", "error": error}, "failed", now, "", args

    collected = await asyncio.gather(
        *(
            collect(name, call, timestamp_field, args)
            for name, (call, timestamp_field, args) in sources.items()
        )
    )
    results = {name: data for name, data, _, _, _, _ in collected}
    tools_called = [
        {
            "name": name,
            "args": args,
            "status": status,
            "checked_at": checked_at,
        }
        for name, _, status, checked_at, _, args in collected
    ]
    sources_failed = [name for name, _, status, _, _, _ in collected if status == "failed"]
    data_freshness = {
        name: timestamp
        for name, _, _, _, timestamp, _ in collected
        if timestamp
    }

    try:
        answer = await composer.compose_backend_briefing(
            {
                "lat": lat,
                "lon": lon,
                "start": start_at.isoformat(),
                "end": end_at.isoformat(),
                "planned_altitude_ft": planned_altitude_ft,
                "radius_m": radius_m,
            },
            results,
        )
    except Exception as exc:
        log.exception("Could not generate aggregated briefing")
        raise HTTPException(
            status_code=502,
            detail=f"Briefing generation failed: {exc}",
        ) from exc

    return CheckResponse(
        answer_markdown=answer,
        citations=[],
        tools_called=tools_called,
        sources_failed=sources_failed,
        data_freshness=data_freshness,
        nearby_alternatives=[],
        mock_data=False,
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
