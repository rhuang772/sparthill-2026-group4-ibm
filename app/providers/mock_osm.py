"""
app/providers/mock_osm.py — MockOSMProvider backed by data/mock_osm.geojson.

find_places(area, tags, radius_km) -> PlaceResult

'area' is a (lat, lon) tuple for the center of the search.
'tags' is a list of OSM tag keys to filter on (e.g. ["leisure", "amenity"]).
Only features whose properties share ANY key in the tags list are returned.
If tags is empty, all features within radius are returned.
"""
from __future__ import annotations

import datetime as dt
import json
import math
from typing import Optional

from app.config import settings
from app.providers.base import Place, PlaceResult


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    a = (math.sin((p2 - p1) / 2) ** 2
         + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2)
    return 2 * 6371.0 * math.asin(math.sqrt(a))


def find_places(
    area: tuple[float, float],
    tags: Optional[list[str]] = None,
    radius_km: float = 10.0,
) -> PlaceResult:
    """Return mock OSM places within radius_km of area=(lat,lon)."""
    now = dt.datetime.now(dt.timezone.utc)

    try:
        fc = json.loads(settings.MOCK_OSM_PATH.read_text())
    except Exception as exc:
        return PlaceResult(
            checked_at=now,
            status="failed",
            error=f"Could not load mock OSM data: {exc}",
        )

    center_lat, center_lon = area
    tag_set = set(tags) if tags else set()
    places = []

    for feature in fc.get("features", []):
        geom = feature.get("geometry", {})
        if geom.get("type") != "Point":
            continue
        lon, lat = geom["coordinates"][0], geom["coordinates"][1]
        dist = _haversine_km(center_lat, center_lon, lat, lon)
        if dist > radius_km:
            continue

        props = feature.get("properties", {})
        if tag_set and not (tag_set & set(props.keys())):
            continue

        places.append(Place(
            name=props.get("name", "Unnamed"),
            lat=lat,
            lon=lon,
            tags={k: v for k, v in props.items() if k != "note"},
            distance_km=round(dist, 2),
        ))

    places.sort(key=lambda p: p.distance_km or 0)

    return PlaceResult(
        checked_at=now,
        status="ok",
        fixture=True,
        places=places,
    )
