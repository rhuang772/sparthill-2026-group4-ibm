"""
tests/test_faa_airspace.py — combined FAA airspace lookup (Class Airspace + Facility Map).

Uses synthetic square polygons loaded into faa_class_airspace's in-memory state, and a
stubbed facility-map lookup, so no network or downloaded data is needed.
"""
from __future__ import annotations

import pytest
from shapely.geometry import box, mapping
from shapely.strtree import STRtree

from app.providers import faa_airspace, faa_class_airspace
from app.providers.base import FacilityCeilingResult

INSIDE = (37.05, -121.95)     # inside every synthetic layer
OUTSIDE_LAYERS = (37.5, -121.5)
OUTSIDE_BBOX = (34.05, -118.25)


def _feature(cls, local_type, floor, floor_code="SFC", hours="H24"):
    return {
        "type": "Feature",
        "geometry": mapping(box(-122.0, 37.0, -121.9, 37.1)),
        "properties": {"NAME": f"TEST {local_type}", "CLASS": cls, "LOCAL_TYPE": local_type,
                       "LOWER_VAL": floor, "LOWER_CODE": floor_code, "UPPER_VAL": -9998,
                       "WKHR_CODE": hours},
    }


@pytest.fixture
def class_layers(monkeypatch):
    """Install synthetic Class Airspace features; returns a setter for the feature list."""
    monkeypatch.setattr(faa_class_airspace.settings, "USE_LIVE_FAA", False, raising=False)

    def _install(features):
        from shapely.geometry import shape
        polygons = [shape(f["geometry"]) for f in features]
        monkeypatch.setattr(faa_class_airspace, "_features", features)
        monkeypatch.setattr(faa_class_airspace, "_polygons", polygons)
        monkeypatch.setattr(faa_class_airspace, "_tree", STRtree(polygons))
        monkeypatch.setattr(faa_class_airspace, "_bbox", (-123.0, 36.0, -121.0, 38.0))

    return _install


@pytest.fixture
def facility(monkeypatch):
    """Stub the facility-map lookup; default is a miss."""
    result = {"value": FacilityCeilingResult(in_grid=False)}
    monkeypatch.setattr(faa_airspace.faa_facility_map, "get_facility_ceiling",
                        lambda lat, lon: result["value"])

    def _set(**kwargs):
        result["value"] = FacilityCeilingResult(**kwargs)

    return _set


def test_surface_class_c_wins_over_e2(class_layers, facility):
    class_layers([_feature("E", "CLASS_E2", 0), _feature("C", "CLASS_C", 0),
                  _feature("E", "CLASS_E5", 700)])
    r = faa_airspace.get_airspace(*INSIDE)
    assert r.airspace_class == "C"
    assert r.airspace_class_source == "faa_class_airspace"
    assert r.controlled is True
    assert [l.local_type for l in r.class_airspace.surface_layers] == ["CLASS_C", "CLASS_E2"]
    assert [l.floor_ft for l in r.class_airspace.overlying_layers] == [700]


def test_only_overlying_layers_is_class_g(class_layers, facility):
    class_layers([_feature("E", "CLASS_E5", 700), _feature("B", "CLASS_B", 2500, "MSL")])
    r = faa_airspace.get_airspace(*INSIDE)
    assert r.airspace_class == "G"
    assert r.controlled is False
    assert r.status == "ok"
    assert any("MSL" in n for n in r.notes)


def test_no_layers_inside_downloaded_area_is_class_g(class_layers, facility):
    class_layers([_feature("C", "CLASS_C", 0)])
    r = faa_airspace.get_airspace(*OUTSIDE_LAYERS)
    assert r.airspace_class == "G"


def test_part_time_surface_area_noted(class_layers, facility):
    class_layers([_feature("D", "CLASS_D", 0, hours="NOTAM")])
    r = faa_airspace.get_airspace(*INSIDE)
    assert r.airspace_class == "D"
    assert any("part-time" in n for n in r.notes)


def test_outside_bbox_is_unconfirmed_not_g(class_layers, facility):
    class_layers([_feature("C", "CLASS_C", 0)])
    r = faa_airspace.get_airspace(*OUTSIDE_BBOX)
    assert r.airspace_class is None
    assert r.controlled is None
    assert r.status == "failed"
    assert r.class_airspace.status == "failed"


def test_falls_back_to_facility_map_when_class_airspace_unavailable(class_layers, facility):
    class_layers([_feature("C", "CLASS_C", 0)])
    facility(in_grid=True, airspace_class="D", ceiling_ft=200, airport_icao="KTST")
    r = faa_airspace.get_airspace(*OUTSIDE_BBOX)
    assert r.airspace_class == "D"
    assert r.airspace_class_source == "faa_facility_map"
    assert r.facility_map.ceiling_ft == 200


def test_disagreement_between_sources_is_noted(class_layers, facility):
    class_layers([_feature("D", "CLASS_D", 0)])
    facility(in_grid=True, airspace_class="C", ceiling_ft=0)
    r = faa_airspace.get_airspace(*INSIDE)
    assert r.airspace_class == "D"
    assert any("more restrictive" in n for n in r.notes)


def test_not_downloaded_is_failed(monkeypatch, tmp_path):
    monkeypatch.setattr(faa_class_airspace.settings, "USE_LIVE_FAA", False, raising=False)
    monkeypatch.setattr(faa_class_airspace.settings, "DATA_CLASS_AIRSPACE_DIR", tmp_path, raising=False)
    for name in ("_tree", "_features", "_polygons", "_bbox", "_fetched_at"):
        monkeypatch.setattr(faa_class_airspace, name, None)
    r = faa_class_airspace.get_class_airspace(*INSIDE)
    assert r.status == "failed"
    assert "not downloaded" in r.error
