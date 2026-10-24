"""
app/providers/park.py — state/federal protected areas near a point (USGS PAD-US).

await get_parks(lat, lon, radius_m) -> ParkResult

Local civic spaces (PAD-US designation LP / LOTH, schools, plazas, centers) are
excluded; what remains are state parks, federal lands and preserves, whose land
managers often restrict or ban drone takeoff and landing.

finding:
  protected_area — at least one state/federal protected area within radius_m
  none_found     — none in PAD-US within radius_m
  unknown        — the PAD-US service could not be reached (status="failed")
"""
from __future__ import annotations

import datetime as dt
from typing import Optional

from app.providers import http_client
from app.providers.base import ParkResult, ProtectedArea

PAD_US_URL = "https://edits.nationalmap.gov/arcgis/rest/services/PAD-US/PAD_US_4_1/MapServer/0/query"
TIMEOUT_S = 5.0
DEFAULT_RADIUS_M = 500
_EXCLUDED_DESIGNATIONS = ("LP", "LOTH")        # local park, local other
_EXCLUDED_NAME_WORDS = ("school", "plaza", "center")
_PRESERVE_DESIGNATIONS = ("NP", "NW", "NWR")


def _to_area(attrs: dict) -> Optional[ProtectedArea]:
    name = str(attrs.get("Unit_Nm") or attrs.get("Loc_Nm") or attrs.get("State_Nm") or "Protected Land")
    designation = str(attrs.get("Des_Tp") or "").upper()
    if designation in _EXCLUDED_DESIGNATIONS or any(w in name.lower() for w in _EXCLUDED_NAME_WORDS):
        return None
    preserve = ("preserve" in name.lower() or "wilderness" in name.lower()
                or designation in _PRESERVE_DESIGNATIONS)
    return ProtectedArea(
        feature_id=str(attrs.get("OBJECTID", "unknown")),
        name=name,
        kind="nature_preserve" if preserve else "state_park",
        designation=designation or None,
        manager=str(attrs.get("Mang_Name") or "").upper() or None,
        gap_status=str(attrs.get("Gap_Sts") or "") or None,
    )


async def get_parks(lat: float, lon: float, radius_m: Optional[float] = None) -> ParkResult:
    now = dt.datetime.now(dt.timezone.utc)
    radius_m = radius_m or DEFAULT_RADIUS_M
    params = {
        "geometry": f"{lon},{lat}",
        "geometryType": "esriGeometryPoint",
        "inSR": "4326",
        "spatialRel": "esriSpatialRelIntersects",
        "distance": str(radius_m),
        "units": "esriSRUnit_Meter",
        "outSR": "4326",
        "outFields": "*",
        "returnGeometry": "false",
        "f": "json",
    }
    try:
        async with http_client.client() as c:
            r = await c.get(PAD_US_URL, params=params, timeout=TIMEOUT_S)
            r.raise_for_status()
            data = r.json()
        if "error" in data:                          # ArcGIS reports errors with HTTP 200
            raise ValueError(str(data["error"]))
    except Exception as exc:
        return ParkResult(checked_at=now, status="failed", radius_m=radius_m,
                          error=f"USGS PAD-US unavailable: {exc}")

    areas = [a for a in (_to_area(f.get("attributes") or {}) for f in data.get("features", [])) if a]
    return ParkResult(
        checked_at=now,
        finding="protected_area" if areas else "none_found",
        radius_m=radius_m,
        areas=areas,
        note=(f"Searched USGS PAD-US within {radius_m:g} m, excluding local civic spaces. "
              "City and county park drone rules are not covered; check with the land manager."),
    )
