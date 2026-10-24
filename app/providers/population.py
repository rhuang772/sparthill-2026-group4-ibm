"""
app/providers/population.py — population exposure heuristic around a point (Geoapify Places).

await get_population_risk(lat, lon, radius_m) -> PopulationResult

Scores nearby places where people gather (schools, universities, parks, playgrounds,
entertainment venues), weighted by kind and distance. This is a geographic-context
heuristic, not a census estimate or a live crowd count.

risk: low | moderate | high, or unknown with status="failed" when Geoapify is
unreachable or GEOAPIFY_API_KEY is not set.
"""
from __future__ import annotations

import datetime as dt
import logging
import math
from typing import Any, Optional

import httpx

from app.config import settings
from app.providers import http_client
from app.providers.base import PopulationPlace, PopulationResult

log = logging.getLogger("population")

GEOAPIFY_URL = "https://api.geoapify.com/v2/places"
TIMEOUT_S = 8.0
LIMIT = 50
DEFAULT_RADIUS_M = 250

# Geoapify categories are hierarchical; the most specific matching prefix wins.
CATEGORY_RULES = (
    ("education.school", "school", 3.0),
    ("education.college", "college", 3.0),
    ("education.university", "university", 4.0),
    ("education", "education", 3.0),
    ("leisure.playground", "playground", 2.0),
    ("leisure.park", "park", 2.0),
    ("activity.community_center", "community_center", 3.0),
    ("entertainment", "entertainment", 2.0),
)
CATEGORIES = "education,education.university,leisure.park,leisure.playground,entertainment"

NOTE = (
    "Heuristic based on nearby places returned by Geoapify, not a census population estimate "
    "or live crowd count. Coverage may be incomplete; a low score does not mean nobody is there."
)


def _distance_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dlat, dlon = math.radians(lat2 - lat1), math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlon / 2) ** 2
    return 2 * 6_371_000 * math.asin(min(1.0, math.sqrt(a)))


def _classify_feature(categories: list[str]) -> Optional[tuple[str, float]]:
    matches = [(len(prefix), kind, weight)
               for category in categories
               for prefix, kind, weight in CATEGORY_RULES
               if category == prefix or category.startswith(prefix + ".")]
    if not matches:
        return None
    _, kind, weight = max(matches, key=lambda m: m[0])
    return kind, weight


def _risk(score: float, count: int) -> str:
    # Initial heuristic thresholds; tune against real examples.
    if count == 0 or score < 3:
        return "low"
    return "high" if score >= 8 else "moderate"


def _to_place(element: dict[str, Any], lat: float, lon: float, radius_m: float) -> Optional[PopulationPlace]:
    props = element.get("properties") or {}
    categories = props.get("categories") or []
    if not isinstance(categories, list):
        return None
    classified = _classify_feature([str(c) for c in categories])
    if classified is None:
        return None
    kind, base_weight = classified

    f_lat, f_lon = props.get("lat"), props.get("lon")
    coords = (element.get("geometry") or {}).get("coordinates") or []
    if (f_lat is None or f_lon is None) and len(coords) >= 2:
        f_lon, f_lat = coords[0], coords[1]
    if f_lat is None or f_lon is None:
        return None
    f_lat, f_lon = float(f_lat), float(f_lon)

    distance = _distance_m(lat, lon, f_lat, f_lon)
    if distance > radius_m:
        return None
    place_id = str(props.get("place_id") or "") or f"{f_lat:.6f},{f_lon:.6f}:{','.join(categories)}"
    return PopulationPlace(
        feature_id=place_id,
        name=str(props.get("name") or props.get("address_line1") or f"Unnamed {kind.replace('_', ' ')}"),
        kind=kind,
        distance_m=round(distance, 1),
        lat=f_lat,
        lon=f_lon,
        weight=round(base_weight * (1.0 - 0.5 * distance / max(radius_m, 1.0)), 2),
        address=props.get("formatted") or props.get("address_line2") or None,
    )


async def get_population_risk(lat: float, lon: float, radius_m: Optional[float] = None) -> PopulationResult:
    now = dt.datetime.now(dt.timezone.utc)
    radius_m = radius_m or DEFAULT_RADIUS_M

    if not settings.GEOAPIFY_API_KEY:
        return PopulationResult(checked_at=now, status="failed", radius_m=radius_m,
                                error="GEOAPIFY_API_KEY is not configured")

    params = {
        "categories": CATEGORIES,
        "filter": f"circle:{lon},{lat},{radius_m}",
        "bias": f"proximity:{lon},{lat}",
        "limit": LIMIT,
        "lang": "en",
        "apiKey": settings.GEOAPIFY_API_KEY,
    }
    try:
        async with http_client.client() as c:
            r = await c.get(GEOAPIFY_URL, params=params,
                            headers={"Accept": "application/json"}, timeout=TIMEOUT_S)
            r.raise_for_status()
            body = r.json()
        if not isinstance(body, dict) or not isinstance(body.get("features"), list):
            raise ValueError("unexpected response shape")
    except httpx.HTTPStatusError as exc:
        # Don't surface the request URL: it carries the API key.
        return PopulationResult(checked_at=now, status="failed", radius_m=radius_m,
                                error=f"Geoapify returned HTTP {exc.response.status_code}")
    except Exception as exc:
        log.warning("Geoapify request failed: %s", type(exc).__name__)
        return PopulationResult(checked_at=now, status="failed", radius_m=radius_m,
                                error=f"Geoapify request failed: {type(exc).__name__}")

    by_id: dict[str, PopulationPlace] = {}
    for element in body["features"]:
        place = _to_place(element, lat, lon, radius_m)
        if place is not None:
            by_id[place.feature_id] = place

    places = sorted(by_id.values(), key=lambda p: p.distance_m)
    score = round(sum(p.weight for p in places), 2)
    return PopulationResult(
        checked_at=now,
        risk=_risk(score, len(places)),
        score=score,
        radius_m=radius_m,
        places=places,
        note=NOTE,
    )
