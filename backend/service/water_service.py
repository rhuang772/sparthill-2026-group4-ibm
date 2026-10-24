import asyncio
import logging
import math
import time
from datetime import datetime, timezone

import httpx

from models import WaterBody, WaterResult

log = logging.getLogger("water")


class WaterUnavailable(Exception):
    """The USGS service failed or returned bad data."""


BASE = "https://hydro.nationalmap.gov/arcgis/rest/services/3DHP_all/FeatureServer"
LAYERS = {"waterbody": 60, "flowline": 50}     # layer IDs from data.gov catalog entries
PAGE = 1000
MAX_PAGES = 4
SIMPLIFY_DEG = 0.00003                         # ~3 m, shrinks big lake outlines

CACHE_TTL_S = 86400
CACHE_MAX = 500
HIGH_RISK_M = 100
MAX_RESULTS = 25

_cache: dict = {}


def _prop(props: dict, *names):
    low = {k.lower(): v for k, v in props.items()}
    for n in names:
        v = low.get(n)
        if v not in (None, "", " "):
            return v
    return None


def _split(geom: dict):
    """GeoJSON geometry -> (polygons, lines). A polygon is a list of rings."""
    t, c = geom.get("type"), geom.get("coordinates")
    if t == "Polygon":
        return [c], []
    if t == "MultiPolygon":
        return list(c), []
    if t == "LineString":
        return [], [c]
    if t == "MultiLineString":
        return [], list(c)
    return [], []


def _nearest(pts):
    """Closest point on a polyline to the origin. Returns (dist, (x, y))."""
    if len(pts) == 1:
        return math.hypot(*pts[0]), pts[0]
    best = (math.inf, None)
    for a, b in zip(pts, pts[1:]):
        ax, ay = a
        bx, by = b
        dx, dy = bx - ax, by - ay
        seg2 = dx * dx + dy * dy
        t = 0.0 if seg2 == 0 else max(0.0, min(1.0, -(ax * dx + ay * dy) / seg2))
        nx, ny = ax + t * dx, ay + t * dy
        d = math.hypot(nx, ny)
        if d < best[0]:
            best = (d, (nx, ny))
    return best


def _in_ring(pts) -> bool:
    """Is the origin inside this ring? (ray casting)"""
    inside, j = False, len(pts) - 1
    for i in range(len(pts)):
        xi, yi = pts[i]
        xj, yj = pts[j]
        if (yi > 0) != (yj > 0) and 0 < (xj - xi) * (-yi) / (yj - yi) + xi:
            inside = not inside
        j = i
    return inside


def _analyze_layer(features: list, layer: str, lat: float, lon: float, radius_m: float):
    ky = 111_320.0
    kx = 111_320.0 * max(math.cos(math.radians(lat)), 0.01)

    def xy(c):
        return ((c[0] - lon) * kx, (c[1] - lat) * ky)

    out = []
    for f in features:
        polys, lines = _split(f.get("geometry") or {})
        props = f.get("properties") or {}

        best, contains = (math.inf, None), False
        for poly in polys:
            rings = [[xy(c) for c in ring] for ring in poly if ring]
            if not rings or len(rings[0]) < 3:
                continue
            if _in_ring(rings[0]) and not any(_in_ring(h) for h in rings[1:]):
                contains = True
            for ring in rings:
                cand = _nearest(ring)
                if cand[0] < best[0]:
                    best = cand
        for line in lines:
            pts = [xy(c) for c in line]
            if not pts:
                continue
            cand = _nearest(pts)
            if cand[0] < best[0]:
                best = cand
        if best[1] is None and not contains:
            continue

        if contains:
            dist, near_lat, near_lon = 0.0, lat, lon
        else:
            dist = best[0]
            near_lat, near_lon = lat + best[1][1] / ky, lon + best[1][0] / kx
        if dist > radius_m:
            continue

        label = _prop(props, "featuretypelabel", "featuretype_label", "ftype_label")
        out.append(WaterBody(
            feature_id=str(_prop(props, "id3dhp", "objectid", "permanent_identifier") or "") or None,
            name=_prop(props, "gnisidlabel", "gnis_name", "gnisname", "name"),
            kind=str(label).lower() if label else layer,
            layer=layer,
            distance_m=round(dist, 1),
            nearest_lat=round(near_lat, 6), nearest_lon=round(near_lon, 6),
            contains_point=contains,
        ))
    return out


class WaterService:
    def __init__(self, client: httpx.AsyncClient):
        self.client = client

    async def layer_fields(self, layer_id: int) -> list[str]:
        try:
            r = await self.client.get(f"{BASE}/{layer_id}", params={"f": "json"}, timeout=15)
            r.raise_for_status()
            return [f["name"] for f in r.json().get("fields", [])]
        except (httpx.HTTPError, ValueError, KeyError, TypeError) as e:
            raise WaterUnavailable(f"layer info failed: {e!r}") from e

    async def _query_layer(self, layer_id: int, lat: float, lon: float, radius_m: float):
        """Returns (features, truncated)."""
        base = {
            "where": "1=1",
            "geometry": f"{lon},{lat}",               # lon first
            "geometryType": "esriGeometryPoint",
            "inSR": 4326, "outSR": 4326,
            "spatialRel": "esriSpatialRelIntersects",
            "distance": max(radius_m, 1),
            "units": "esriSRUnit_Meter",
            "outFields": "*",
            "returnGeometry": "true",
            "maxAllowableOffset": SIMPLIFY_DEG,
            "f": "geojson",
            "resultRecordCount": PAGE,
        }
        feats, offset = [], 0
        try:
            for _ in range(MAX_PAGES):
                r = await self.client.get(f"{BASE}/{layer_id}/query",
                                          params={**base, "resultOffset": offset}, timeout=25)
                r.raise_for_status()
                body = r.json()
                if "error" in body:                    # ArcGIS reports errors with HTTP 200
                    raise WaterUnavailable(str(body["error"]))
                batch = body.get("features", [])
                feats += batch
                if len(batch) < PAGE:
                    return feats, False
                offset += PAGE
            return feats, True
        except (httpx.HTTPError, ValueError, KeyError, TypeError) as e:
            raise WaterUnavailable(f"layer {layer_id} query failed: {e!r}") from e

    async def fetch_raw(self, lat: float, lon: float, radius_m: float) -> dict:
        lid = LAYERS["waterbody"]
        feats, truncated = await self._query_layer(lid, round(lat, 4), round(lon, 4), radius_m)
        return {
            "fields": await self.layer_fields(lid),
            "count": len(feats), "truncated": truncated,
            "geometry_types": sorted({(f.get("geometry") or {}).get("type") for f in feats}),
            "sample_properties": [f.get("properties") for f in feats[:3]],
        }

    async def get_water(self, lat: float, lon: float, radius_m: float,
                        include_flowlines: bool = False) -> WaterResult:
        lat, lon = round(lat, 4), round(lon, 4)
        radius = max(int(radius_m), 1)
        key = (lat, lon, radius, include_flowlines)
        hit = _cache.get(key)
        if hit and time.time() - hit["at"] < CACHE_TTL_S:
            return hit["result"]

        layers = ["waterbody"] + (["flowline"] if include_flowlines else [])
        results = await asyncio.gather(
            *(self._query_layer(LAYERS[n], lat, lon, radius) for n in layers))

        bodies, truncated_layers = [], []
        for name, (feats, truncated) in zip(layers, results):
            bodies += _analyze_layer(feats, name, lat, lon, radius)
            if truncated:
                truncated_layers.append(name)
        bodies.sort(key=lambda b: b.distance_m)

        over = any(b.contains_point for b in bodies)
        nearest = bodies[0].distance_m if bodies else None
        if over or (nearest is not None and nearest <= HIGH_RISK_M):
            risk = "high"
        elif bodies:
            risk = "moderate"
        else:
            risk = "none"

        notes = []
        if not bodies:
            notes.append("No water found in this radius in the USGS data. Coverage of bays, "
                         "coastline and small ponds may be incomplete, so this is not proof there is none.")
        if truncated_layers:
            notes.append("Too many features in this radius for: " + ", ".join(truncated_layers) +
                         ". Nearer water may be missing. Try a smaller radius.")
        if len(bodies) > MAX_RESULTS:
            notes.append(f"Showing the nearest {MAX_RESULTS} of {len(bodies)} water features.")

        result = WaterResult(
            lat=lat, lon=lon, radius_m=radius,
            water_found=bool(bodies), point_over_water=over,
            nearest_distance_m=nearest, risk=risk,
            water_bodies=bodies[:MAX_RESULTS], total_found=len(bodies),
            truncated=len(bodies) > MAX_RESULTS,
            fetched_at=datetime.now(timezone.utc).isoformat(),
            note=" ".join(notes) or None,
        )
        if len(_cache) >= CACHE_MAX:
            _cache.pop(next(iter(_cache)))
        _cache[key] = {"at": time.time(), "result": result}
        return result