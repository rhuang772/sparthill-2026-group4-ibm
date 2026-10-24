"""
app/providers/faa_facility_map.py — cached FAA UAS Facility Map lookup.

Uses real FAA property names from config.py (PROP_* constants).

load()                          — call at startup; falls back to fixture if cache missing
get_facility_ceiling(lat, lon)  — point-in-polygon lookup (offline STRtree or live ArcGIS)

When USE_LIVE_FAA=true:  queries the real public FAA ArcGIS endpoint by point bbox.
When USE_LIVE_FAA=false: uses the in-memory STRtree built from data/uasfm/ or the
                          2-cell SJC fixture (status="stale").

A HIT means "inside a LAANC-eligible grid cell with ceiling X ft AGL."
A MISS means only "no facility-map cell found here" — not that airspace is Class G.
Ceiling 0 means no routine authorization in that cell.
"""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from typing import Optional

from shapely.geometry import Point, shape
from shapely.strtree import STRtree

from app.config import (
    PROP_APT1_ENABLED, PROP_APT1_FAAID, PROP_APT1_ICAO, PROP_APT1_LAANC,
    PROP_APT1_NAME, PROP_AIRSPACE_1, PROP_CEILING, PROP_LAST_EDIT,
    PROP_MAP_EFF, PROP_REGION, settings,
)
from app.providers.base import FacilityCeilingResult

# Real public FAA UAS Facility Map — ArcGIS Feature Service (no auth required)
FAA_UASFM_URL = (
    "https://services6.arcgis.com/ssFJjBXIUyZDrSYZ/arcgis/rest/services"
    "/FAA_UAS_FacilityMap_Data/FeatureServer/0/query"
)
_FAA_UASFM_SOURCE = FAA_UASFM_URL

# ---------------------------------------------------------------------------
# Module-level state
# ---------------------------------------------------------------------------
_polygons: list = []        # shapely geometries, index-aligned with _features
_tree: Optional[STRtree] = None
_features: list[dict] = []  # raw GeoJSON feature dicts
_fetched_at: Optional[str] = None
_using_fixture: bool = False

# Shared async client (injected at startup for the live FAA ArcGIS path)
_http_client = None


def set_http_client(client) -> None:
    """Inject the shared httpx.AsyncClient created by the lifespan."""
    global _http_client
    _http_client = client


def load() -> None:
    """Load the facility map GeoJSON into memory and build the STRtree.

    Search order:
    1. data/uasfm/*.geojson  (real downloaded data)
    2. fixtures/uasfm_sample.geojson  (2-cell SJC sample; sets status stale)
    """
    global _polygons, _tree, _features, _fetched_at, _using_fixture

    geojson_path: Optional[Path] = None
    _using_fixture = False

    # Try real cached data first
    data_dir = settings.DATA_UASFM_DIR
    if data_dir.exists():
        candidates = sorted(data_dir.glob("*.geojson"))
        if candidates:
            geojson_path = candidates[0]
            meta_path = data_dir / "meta.json"
            if meta_path.exists():
                try:
                    _fetched_at = json.loads(meta_path.read_text())["fetched_at"]
                except Exception:
                    pass

    # Fall back to fixture
    if geojson_path is None:
        geojson_path = settings.UASFM_SAMPLE_PATH
        _using_fixture = True

    fc = json.loads(geojson_path.read_text())
    _features = fc.get("features", [])
    _polygons = [shape(f["geometry"]) for f in _features]
    _tree = STRtree(_polygons)


def _props_to_result(
    props: dict,
    now: dt.datetime,
    status: str,
    fixture: bool,
    fetched_at: Optional[str],
) -> FacilityCeilingResult:
    """Convert a GeoJSON feature's properties dict into a FacilityCeilingResult."""
    return FacilityCeilingResult(
        checked_at=now,
        status=status,      # type: ignore[arg-type]
        fixture=fixture,
        in_grid=True,
        ceiling_ft=props.get(PROP_CEILING),
        airport_faaid=props.get(PROP_APT1_FAAID),
        airport_icao=props.get(PROP_APT1_ICAO),
        airport_name=props.get(PROP_APT1_NAME),
        airspace_class=props.get(PROP_AIRSPACE_1),
        laanc_enabled=bool(props.get(PROP_APT1_LAANC, 0)),
        enabled_types=props.get(PROP_APT1_ENABLED),
        map_effective=props.get(PROP_MAP_EFF),
        fetched_at=fetched_at or props.get(PROP_LAST_EDIT),
        source_url=_FAA_UASFM_SOURCE,
        region=props.get(PROP_REGION),
    )


def _query_live(lat: float, lon: float, now: dt.datetime) -> FacilityCeilingResult:
    """Query the real FAA ArcGIS endpoint for a single point.

    Uses a tiny bbox (≈55 m × 55 m) around the point so the spatial query
    returns only cells that actually contain it.  The first feature returned
    is used (cells don't overlap).
    """
    # 0.0005 degrees ≈ 55 m — small enough to avoid returning neighbours
    delta = 0.0005
    import json as _json

    params = {
        "geometry": _json.dumps({
            "xmin": lon - delta, "ymin": lat - delta,
            "xmax": lon + delta, "ymax": lat + delta,
        }),
        "geometryType": "esriGeometryEnvelope",
        "inSR": "4326",
        "spatialRel": "esriSpatialRelIntersects",
        "outFields": "*",
        "f": "geojson",
        "resultRecordCount": 1,
        "where": "1=1",
    }

    if _http_client is None:
        # Fallback to a synchronous httpx call if the async client isn't set yet
        import httpx as _httpx
        with _httpx.Client(timeout=10) as sync_client:
            r = sync_client.get(FAA_UASFM_URL, params=params)
    else:
        # Run async client in current event loop or a new one
        import asyncio as _asyncio

        async def _fetch():
            return await _http_client.get(FAA_UASFM_URL, params=params)

        try:
            loop = _asyncio.get_event_loop()
            if loop.is_running():
                # Inside FastAPI's running loop — use a thread executor
                import concurrent.futures as _cf
                import httpx as _httpx
                with _httpx.Client(timeout=10) as sync_client:
                    r = sync_client.get(FAA_UASFM_URL, params=params)
            else:
                r = loop.run_until_complete(_fetch())
        except RuntimeError:
            import httpx as _httpx
            with _httpx.Client(timeout=10) as sync_client:
                r = sync_client.get(FAA_UASFM_URL, params=params)

    if r.status_code != 200:
        return FacilityCeilingResult(
            checked_at=now,
            status="failed",
            error=f"FAA ArcGIS returned HTTP {r.status_code}",
            source_url=_FAA_UASFM_SOURCE,
        )

    data = r.json()
    if "error" in data:
        return FacilityCeilingResult(
            checked_at=now,
            status="failed",
            error=f"FAA ArcGIS error: {data['error']}",
            source_url=_FAA_UASFM_SOURCE,
        )

    features = data.get("features", [])
    if not features:
        return FacilityCeilingResult(
            checked_at=now,
            status="ok",
            in_grid=False,
            source_url=_FAA_UASFM_SOURCE,
        )

    props = features[0].get("properties", {})
    return _props_to_result(props, now, status="ok", fixture=False, fetched_at=None)


def get_facility_ceiling(lat: float, lon: float) -> FacilityCeilingResult:
    """Return facility-map ceiling for the given point.

    USE_LIVE_FAA=true  → live FAA ArcGIS spatial query (real data, status="ok")
    USE_LIVE_FAA=false → in-memory STRtree from downloaded GeoJSON or fixture
    """
    now = dt.datetime.now(dt.timezone.utc)

    if settings.USE_LIVE_FAA:
        try:
            return _query_live(lat, lon, now)
        except Exception as exc:
            return FacilityCeilingResult(
                checked_at=now,
                status="failed",
                error=f"Live FAA query failed: {exc}",
                source_url=_FAA_UASFM_SOURCE,
            )

    # --- Offline STRtree path ---
    if _tree is None:
        try:
            load()
        except Exception as exc:
            return FacilityCeilingResult(
                checked_at=now,
                status="failed",
                error=f"Could not load facility map: {exc}",
            )

    status: str = "stale" if _using_fixture else "ok"
    pt = Point(lon, lat)   # shapely uses (x=lon, y=lat)

    candidate_indices = _tree.query(pt)
    for idx in candidate_indices:
        if _polygons[idx].contains(pt):
            props = _features[idx]["properties"]
            return _props_to_result(props, now, status, _using_fixture, _fetched_at)

    # No cell found — MISS (does NOT mean Class G)
    return FacilityCeilingResult(
        checked_at=now,
        status=status,      # type: ignore[arg-type]
        fixture=_using_fixture,
        in_grid=False,
        source_url=_FAA_UASFM_SOURCE,
    )
