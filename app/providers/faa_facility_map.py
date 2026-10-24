"""
app/providers/faa_facility_map.py — cached FAA UAS Facility Map lookup.

Uses real FAA property names from config.py (PROP_* constants).

load()                          — call at startup; falls back to fixture if cache missing
get_facility_ceiling(lat, lon)  — point-in-polygon lookup via shapely STRtree

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

_FAA_UASFM_SOURCE = "https://uat.arcgis.com/arcgis/rest/services/FederalAviationAdministration/UASFM/FeatureServer/0"

# ---------------------------------------------------------------------------
# Module-level state
# ---------------------------------------------------------------------------
_polygons: list = []        # shapely geometries, index-aligned with _features
_tree: Optional[STRtree] = None
_features: list[dict] = []  # raw GeoJSON feature dicts
_fetched_at: Optional[str] = None
_using_fixture: bool = False


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


def get_facility_ceiling(lat: float, lon: float) -> FacilityCeilingResult:
    """Return facility-map ceiling for the given point."""
    now = dt.datetime.now(dt.timezone.utc)

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
            return FacilityCeilingResult(
                checked_at=now,
                status=status,      # type: ignore[arg-type]
                fixture=_using_fixture,
                in_grid=True,
                ceiling_ft=props.get(PROP_CEILING),
                airport_faaid=props.get(PROP_APT1_FAAID),
                airport_icao=props.get(PROP_APT1_ICAO),
                airport_name=props.get(PROP_APT1_NAME),
                airspace_class=props.get(PROP_AIRSPACE_1),
                laanc_enabled=bool(props.get(PROP_APT1_LAANC, 0)),
                enabled_types=props.get(PROP_APT1_ENABLED),
                map_effective=props.get(PROP_MAP_EFF),
                fetched_at=_fetched_at or props.get(PROP_LAST_EDIT),
                source_url=_FAA_UASFM_SOURCE,
                region=props.get(PROP_REGION),
            )

    # No cell found — MISS (does NOT mean Class G)
    return FacilityCeilingResult(
        checked_at=now,
        status=status,      # type: ignore[arg-type]
        fixture=_using_fixture,
        in_grid=False,
        source_url=_FAA_UASFM_SOURCE,
    )
