"""
app/providers/airspace.py — thin wrapper over the AirHub simulator client.

get_airspace(lat, lon) -> AirspaceResult
get_advisories(lat, lon, radius_km) -> AdvisoryResult

AirHubError is caught and mapped to status="failed" so the agent loop
never sees an unhandled exception from this provider.
"""
from __future__ import annotations

import datetime as dt

from app.config import settings
from app.providers.airhub_sim import (
    AirHubClient, AirHubError, AirHubSimulator,
    SIM_API_KEY, SIM_CLIENT_ID, SIM_CLIENT_SECRET,
    DEFAULT_GRANTED, SANDBOX, make_sim_client,
)
from app.providers.base import (
    Advisory, AdvisoryResult, AirspaceDetail, AirspaceResult, FacilityMapDetail,
)

# ---------------------------------------------------------------------------
# Singleton client (built once at import time)
# ---------------------------------------------------------------------------

def _build_client():
    if settings.USE_SIM:
        _sim, client = make_sim_client()
        return client, True
    return (
        AirHubClient(
            api_key=settings.AIRHUB_API_KEY,
            client_id=settings.AIRHUB_CLIENT_ID,
            client_secret=settings.AIRHUB_CLIENT_SECRET,
            scopes=sorted(DEFAULT_GRANTED),
            base_url=settings.AIRHUB_BASE_URL,
        ),
        False,
    )


_client, _is_sim = _build_client()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_airspace(lat: float, lon: float) -> AirspaceResult:
    """Return airspace class, controlled flag, facility, and sim facility-map ceiling."""
    now = dt.datetime.now(dt.timezone.utc)
    try:
        data = _client.briefing_location(lat, lon)
    except AirHubError as exc:
        return AirspaceResult(
            checked_at=now,
            status="failed",
            simulated=_is_sim,
            error=f"AirHub {exc.status}: {exc.message}",
        )
    except Exception as exc:  # network errors etc.
        return AirspaceResult(
            checked_at=now,
            status="failed",
            simulated=_is_sim,
            error=str(exc),
        )

    raw_air = data.get("airspace", {})
    raw_fm = data.get("facility_map", {})

    return AirspaceResult(
        checked_at=now,
        status="ok",
        simulated=data.get("simulated", _is_sim),
        airspace=AirspaceDetail(
            airspace_class=raw_air.get("class", "G"),
            controlled=raw_air.get("controlled", False),
            facility=raw_air.get("facility"),
        ),
        facility_map=FacilityMapDetail(
            in_grid=raw_fm.get("in_grid", False),
            ceiling_ft=raw_fm.get("ceiling_ft"),
            facility=raw_fm.get("facility"),
        ),
        raw_advisories=data.get("advisories", []),
    )


def get_advisories(lat: float, lon: float, radius_km: float = 5.0) -> AdvisoryResult:
    """Return active advisories (NSUFR, TFR, local) near a point via bbox query."""
    now = dt.datetime.now(dt.timezone.utc)
    # Convert radius_km to rough degree delta (1 deg lat ≈ 111 km)
    delta = radius_km / 111.0
    try:
        data = _client.advisories_bbox(
            west=lon - delta, south=lat - delta,
            east=lon + delta, north=lat + delta,
        )
    except AirHubError as exc:
        return AdvisoryResult(
            checked_at=now,
            status="failed",
            simulated=_is_sim,
            error=f"AirHub {exc.status}: {exc.message}",
        )
    except Exception as exc:
        return AdvisoryResult(
            checked_at=now,
            status="failed",
            simulated=_is_sim,
            error=str(exc),
        )

    advisories = []
    for raw in data.get("advisories", []):
        advisories.append(Advisory(
            id=raw.get("id", "unknown"),
            type=raw.get("type", "unknown"),
            severity=raw.get("severity", "info"),
            name=raw.get("name", ""),
            description=raw.get("description", ""),
            source=raw.get("source", "airhub"),
            effective=raw.get("effective"),
        ))

    return AdvisoryResult(
        checked_at=now,
        status="ok",
        simulated=_is_sim,
        advisories=advisories,
    )
