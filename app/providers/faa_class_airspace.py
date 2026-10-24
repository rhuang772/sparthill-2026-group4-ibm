"""
app/providers/faa_class_airspace.py — FAA Class Airspace (B/C/D/E) boundary lookup.

load()                        — call at startup; loads data/class_airspace/*.geojson if present
get_class_airspace(lat, lon)  — which controlled airspace layers contain the point

When USE_LIVE_FAA=true:  queries the public FAA ArcGIS Class_Airspace service.
When USE_LIVE_FAA=false: uses the in-memory STRtree built from data/class_airspace/
                         (populate with scripts/fetch_facility_map.py --dataset class_airspace).
                         Points outside the downloaded bbox return status="failed",
                         because "no polygon found" would otherwise read as Class G.

A layer whose floor is 0 ft SFC starts at the ground ("surface layer"). If no B/C/D/E
layer starts at the ground, the point is Class G at the surface. Layers with a higher
floor are returned as overlying_layers (e.g. Class E from 700 ft).
"""
from __future__ import annotations

import datetime as dt
import json
from typing import Optional

from shapely.geometry import Point, shape
from shapely.strtree import STRtree

from app.config import settings
from app.providers.base import AirspaceLayer, ClassAirspaceResult

FAA_CLASS_AIRSPACE_URL = (
    "https://services6.arcgis.com/ssFJjBXIUyZDrSYZ/arcgis/rest/services"
    "/Class_Airspace/FeatureServer/0/query"
)
CONTROLLED_CLASSES = ("B", "C", "D", "E")
CLASS_WHERE = "CLASS IN ('B','C','D','E')"
_RESTRICTIVENESS = {c: i for i, c in enumerate(CONTROLLED_CLASSES)}   # lower = more restrictive

# ---------------------------------------------------------------------------
# Module-level state
# ---------------------------------------------------------------------------
_polygons: list = []
_tree: Optional[STRtree] = None
_features: list[dict] = []
_bbox: Optional[tuple[float, float, float, float]] = None   # west, south, east, north
_fetched_at: Optional[str] = None


def load() -> None:
    """Load data/class_airspace/*.geojson into an STRtree. No-op if nothing is downloaded."""
    global _polygons, _tree, _features, _bbox, _fetched_at

    _polygons, _tree, _features, _bbox, _fetched_at = [], None, [], None, None
    data_dir = settings.DATA_CLASS_AIRSPACE_DIR
    candidates = sorted(data_dir.glob("*.geojson")) if data_dir.exists() else []
    if not candidates:
        return

    meta_path = data_dir / "meta.json"
    if meta_path.exists():
        meta = json.loads(meta_path.read_text())
        _fetched_at = meta.get("fetched_at")
        if meta.get("bbox"):
            _bbox = tuple(float(v) for v in meta["bbox"].split(","))

    fc = json.loads(candidates[0].read_text())
    _features = [f for f in fc.get("features", []) if f.get("geometry")]
    _polygons = [shape(f["geometry"]) for f in _features]
    _tree = STRtree(_polygons)


def _to_layer(props: dict) -> AirspaceLayer:
    upper = props.get("UPPER_VAL")
    return AirspaceLayer(
        name=props.get("NAME") or "unnamed",
        airspace_class=props.get("CLASS"),
        local_type=props.get("LOCAL_TYPE"),
        airport_icao=props.get("ICAO_ID"),
        floor_ft=props.get("LOWER_VAL") or 0,
        floor_ref=props.get("LOWER_CODE"),
        # -9998 is the FAA sentinel for "up to the overlying airspace"
        ceiling_ft=None if upper in (None, -9998) else upper,
        ceiling_ref=props.get("UPPER_CODE"),
        hours=props.get("WKHR_CODE"),
    )


def _classify(props_list: list[dict], now: dt.datetime, **extra) -> ClassAirspaceResult:
    layers = [_to_layer(p) for p in props_list if p.get("CLASS") in CONTROLLED_CLASSES]
    surface = sorted((x for x in layers if x.floor_ft == 0),
                     key=lambda x: _RESTRICTIVENESS[x.airspace_class])
    overlying = sorted((x for x in layers if x.floor_ft > 0), key=lambda x: x.floor_ft)
    return ClassAirspaceResult(
        checked_at=now,
        surface_class=surface[0].airspace_class if surface else None,
        surface_layers=surface,
        overlying_layers=overlying,
        source_url=FAA_CLASS_AIRSPACE_URL,
        **extra,
    )


def _query_live(lat: float, lon: float, now: dt.datetime) -> ClassAirspaceResult:
    import httpx

    params = {
        "geometry": f"{lon},{lat}",
        "geometryType": "esriGeometryPoint",
        "inSR": "4326",
        "spatialRel": "esriSpatialRelIntersects",
        "where": CLASS_WHERE,
        "outFields": "*",
        "returnGeometry": "false",
        "f": "json",
    }
    with httpx.Client(timeout=10) as client:
        r = client.get(FAA_CLASS_AIRSPACE_URL, params=params)
    if r.status_code != 200:
        return ClassAirspaceResult(checked_at=now, status="failed",
                                   error=f"FAA ArcGIS returned HTTP {r.status_code}",
                                   source_url=FAA_CLASS_AIRSPACE_URL)
    data = r.json()
    if "error" in data:
        return ClassAirspaceResult(checked_at=now, status="failed",
                                   error=f"FAA ArcGIS error: {data['error']}",
                                   source_url=FAA_CLASS_AIRSPACE_URL)
    return _classify([f["attributes"] for f in data.get("features", [])], now)


def get_class_airspace(lat: float, lon: float) -> ClassAirspaceResult:
    now = dt.datetime.now(dt.timezone.utc)

    if settings.USE_LIVE_FAA:
        try:
            return _query_live(lat, lon, now)
        except Exception as exc:
            return ClassAirspaceResult(checked_at=now, status="failed",
                                       error=f"Live FAA Class Airspace query failed: {exc}",
                                       source_url=FAA_CLASS_AIRSPACE_URL)

    if _tree is None:
        load()
    if _tree is None:
        return ClassAirspaceResult(
            checked_at=now, status="failed",
            error="FAA Class Airspace data not downloaded (data/class_airspace/ is empty)",
        )
    if _bbox is not None:
        west, south, east, north = _bbox
        if not (west <= lon <= east and south <= lat <= north):
            return ClassAirspaceResult(
                checked_at=now, status="failed",
                error=f"Point is outside the downloaded FAA Class Airspace area {_bbox}",
            )

    pt = Point(lon, lat)
    hits = [_features[i]["properties"] for i in _tree.query(pt) if _polygons[i].contains(pt)]
    return _classify(hits, now, fetched_at=_fetched_at)
