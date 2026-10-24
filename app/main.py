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
from app.schema import BriefingSectionSummaries, CheckResponse, RulesResponse
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

_WIND_DIRECTIONS = ("N", "NE", "E", "SE", "S", "SW", "W", "NW")


def _display_number(value: object, suffix: str) -> str | None:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return None
    return f"{value:g}{suffix}"


def _wind_direction(degrees: object) -> str | None:
    if not isinstance(degrees, (int, float)) or isinstance(degrees, bool):
        return None
    direction = _WIND_DIRECTIONS[round(degrees / 45) % len(_WIND_DIRECTIONS)]
    return f"from {direction} ({degrees:g}°)"


def _briefing_facts(results: dict, planned_altitude_ft: Optional[int]) -> list[dict[str, str]]:
    """Build factual display lines directly from provider results, without AI rewriting."""
    facts: list[dict[str, str]] = []

    def add(
        section: str,
        label: str,
        value: str,
        source: str,
        checked_at: object = None,
    ) -> None:
        fact = {"section": section, "label": label, "value": value, "source": source}
        if isinstance(checked_at, str) and checked_at:
            fact["checked_at"] = checked_at
        facts.append(fact)

    def source_data(name: str, section: str, label: str, source: str) -> dict:
        data = results.get(name, {})
        if data.get("status") == "failed":
            add(section, label, "Could not verify: source unavailable.", source)
            return {}
        return data

    current = source_data("weather_current", "conditions", "Current weather", "Open-Meteo")
    if current:
        conditions = []
        temp = _display_number(current.get("temperature_f"), " °F")
        wind = _display_number(current.get("wind_mph"), " mph")
        gusts = _display_number(current.get("gusts_mph"), " mph")
        direction = _wind_direction(current.get("wind_direction_deg"))
        description = current.get("weather_description")
        if temp:
            conditions.append(f"Temperature {temp}")
        if wind:
            conditions.append(f"wind {wind}{f' {direction}' if direction else ''}")
        if gusts:
            conditions.append(f"gusts {gusts}")
        if description:
            conditions.append(str(description))
        add(
            "conditions",
            "Current conditions",
            "; ".join(conditions) if conditions else "No current weather values returned.",
            "Open-Meteo",
            current.get("observed_at"),
        )

    forecast = source_data("weather_forecast", "conditions", "Planned flight weather", "Open-Meteo forecast")
    if forecast:
        summary = forecast.get("summary") or {}
        conditions = []
        minimum = _display_number(summary.get("min_temperature_f"), " °F")
        maximum = _display_number(summary.get("max_temperature_f"), " °F")
        if minimum and maximum:
            conditions.append(f"temperature {minimum} to {maximum}")
        for key, label, suffix in (
            ("max_wind_mph", "max wind at 10 m", " mph"),
            ("max_wind_mph_120m", "max wind at 120 m", " mph"),
            ("max_gusts_mph", "max gusts", " mph"),
            ("max_precipitation_probability_pct", "max precipitation probability", "%"),
            ("total_precipitation_in", "total precipitation", " in"),
        ):
            value = _display_number(summary.get(key), suffix)
            if value:
                conditions.append(f"{label} {value}")
        visibility = summary.get("min_visibility_m")
        if isinstance(visibility, (int, float)) and not isinstance(visibility, bool):
            conditions.append(f"minimum visibility {visibility:g} m")
        if summary.get("worst_weather_description"):
            conditions.append(f"forecast condition {summary['worst_weather_description']}")
        add(
            "conditions",
            "Planned flight weather (1-hour window)",
            "; ".join(conditions) if conditions else "No forecast values returned.",
            "Open-Meteo",
            forecast.get("fetched_at"),
        )
        for hour in forecast.get("hours") or []:
            hour_conditions = []
            for key, label, suffix in (
                ("temperature_f", "temperature", " °F"),
                ("wind_mph", "wind", " mph"),
                ("gusts_mph", "gusts", " mph"),
                ("visibility_m", "visibility", " m"),
                ("precipitation_probability_pct", "precipitation probability", "%"),
                ("precipitation_in", "precipitation", " in"),
            ):
                value = _display_number(hour.get(key), suffix)
                if value:
                    hour_conditions.append(f"{label} {value}")
            direction = _wind_direction(hour.get("wind_direction_deg"))
            if direction:
                for index, condition in enumerate(hour_conditions):
                    if condition.startswith("wind "):
                        hour_conditions[index] = f"{condition} {direction}"
                        break
            if hour.get("weather_description"):
                hour_conditions.append(f"condition {hour['weather_description']}")
            hour_time = hour.get("time") or "planned hour"
            add(
                "conditions",
                f"Forecast at {hour_time}",
                "; ".join(hour_conditions) if hour_conditions else "No hourly values returned.",
                "Open-Meteo",
                forecast.get("fetched_at"),
            )

    ceiling = source_data(
        "faa_height_limit", "airspace", "FAA facility-map ceiling", "FAA UAS Facility Map"
    )
    if ceiling:
        classes = ceiling.get("airspace_classes")
        radius_m = ceiling.get("radius_m")
        radius_description = (
            f"{radius_m:g} m"
            if isinstance(radius_m, (int, float)) and not isinstance(radius_m, bool)
            else "the queried radius"
        )
        if isinstance(classes, list) and classes:
            class_names = ", ".join(f"Class {class_name}" for class_name in classes)
            class_value = f"{class_names} reported in facility-map cells within {radius_description}."
        elif isinstance(classes, list):
            class_value = (
                f"Assumed Class G because no airspace classes were reported in "
                f"facility-map cells within {radius_description}. This is an "
                "unverified fallback."
            )
        else:
            class_value = (
                f"Airspace class could not be confirmed from facility-map cells "
                f"within {radius_description}."
            )
        class_value += (
            " This radius-based result does not confirm the exact airspace class "
            "at the pin. Verify the exact class in B4UFLY."
        )
        add("airspace", "Airspace classes reported", class_value, "FAA UAS Facility Map")

        max_altitude = ceiling.get("max_altitude_ft")
        if ceiling.get("status") == "limited" and isinstance(max_altitude, (int, float)):
            value = f"{max_altitude:g} ft AGL"
            if ceiling.get("limiting_airport"):
                value += f"; limiting airport: {ceiling['limiting_airport']}"
            value += "; ceiling is a map limit, not an authorization grant."
        else:
            value = "No cell/ceiling confirmed for this location."
        if ceiling.get("status") == "unknown":
            value += " Authorization ceiling is unknown."
        if ceiling.get("map_effective"):
            value += f" Map effective: {ceiling['map_effective']}."
        if planned_altitude_ft is not None:
            value += f" Planned altitude: {planned_altitude_ft} ft AGL."
        add("airspace", "FAA facility-map ceiling", value, "FAA UAS Facility Map")

    tfr = source_data("tfr", "restrictions", "Temporary flight restrictions", "FAA TFR feed")
    if tfr:
        tfr_status = tfr.get("status")
        if tfr_status == "restricted":
            active = [
                f"{item.get('notam_id', 'TFR')} ({item.get('time_status', 'unknown')})"
                for item in tfr.get("tfrs", [])
                if item.get("time_status") in ("active", "unknown")
                and item.get("reaches_drone_altitudes")
            ]
            value = "Relevant restriction reported"
            if active:
                value += ": " + ", ".join(active)
        elif tfr_status == "clear":
            value = "No relevant TFR identified in this query."
        else:
            value = "Could not confirm TFR status."
        add("restrictions", "Temporary flight restrictions", value, "FAA TFR feed", tfr.get("data_fetched_at"))

    water = source_data("water", "nearby_risks", "Water nearby", "USGS 3DHP")
    if water:
        distance = _display_number(water.get("nearest_distance_m"), " m")
        water_bodies = water.get("water_bodies") or []
        water_features = []
        for feature in water_bodies:
            if not isinstance(feature, dict):
                continue
            name = feature.get("name") or "Unnamed water feature"
            kind = feature.get("kind")
            layer = feature.get("layer")
            feature_type = str(kind or layer or "water feature").replace("_", " ")
            feature_distance = _display_number(feature.get("distance_m"), " m")
            detail = f"{name} ({feature_type}"
            if feature_distance:
                detail += f", {feature_distance}"
            water_features.append(detail + ")")

        if water.get("point_over_water"):
            value = "The coordinate is over mapped water."
        elif water.get("water_found") and distance:
            value = f"Nearest mapped water is {distance} away."
        else:
            value = "No water feature found in the queried radius."
        if water_features:
            value += f" Mapped water features: {', '.join(water_features)}."
        if water.get("truncated"):
            value += (
                f" Showing {len(water_features)} of "
                f"{water.get('total_found', 'the returned')} mapped features."
            )
        value += f" Reported risk: {water.get('risk', 'unknown')}."
        add("nearby_risks", "Water nearby", value, "USGS 3DHP", water.get("fetched_at"))

    population = source_data(
        "population_risk", "nearby_risks", "Population context", "Geoapify / population context"
    )
    if population:
        features = population.get("features") or []
        feature_details = []
        for feature in features:
            if not isinstance(feature, dict):
                continue
            name = feature.get("name")
            kind = feature.get("kind")
            if name and kind:
                feature_details.append(f"{name} ({str(kind).replace('_', ' ')})")
            elif name:
                feature_details.append(str(name))
            elif kind:
                feature_details.append(str(kind).replace("_", " "))
        feature_list = (
            f" Mapped places: {', '.join(feature_details)}."
            if feature_details
            else ""
        )
        add(
            "nearby_risks",
            "Population context",
            f"{population.get('status', 'unknown').capitalize()} heuristic; "
            f"{population.get('features_found', 0)} mapped features in the query radius."
            f"{feature_list} This is not a population count.",
            "Geoapify / population context",
            population.get("fetched_at"),
        )

    parks = source_data("park_risk", "nearby_risks", "Protected areas", "USGS PAD-US")
    if parks:
        features = parks.get("features") or []
        names = [str(feature.get("name")) for feature in features if feature.get("name")]
        value = (
            f"{len(names)} mapped protected area(s): {', '.join(names)}."
            if names
            else "No protected area found in this query."
        )
        value += " Check the land manager for site-specific rules."
        add("nearby_risks", "Protected areas", value, "USGS PAD-US", parks.get("fetched_at"))

    return facts


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
        assessment = await composer.compose_backend_briefing(
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
        answer_markdown=(
            "## Where you are / airspace\n" + assessment.section_summaries.airspace
            + "\n\n## Conditions for the planned flight\n" + assessment.section_summaries.conditions
            + "\n\n## Restrictions\n" + assessment.section_summaries.restrictions
            + "\n\n## Nearby risks\n" + assessment.section_summaries.nearby_risks
            + "\n\n---\n**Before flying:** Verify current conditions in B4UFLY, check NOTAMs, "
            "and follow land-manager and local rules. This educational briefing is not FAA authorization."
        ),
        citations=[],
        tools_called=tools_called,
        sources_failed=sources_failed,
        data_freshness=data_freshness,
        nearby_alternatives=[],
        mock_data=False,
        flight_assessment=assessment.status,
        assessment_summary=assessment.summary,
        flight_facts=_briefing_facts(results, planned_altitude_ft),
        section_summaries=assessment.section_summaries,
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
