"""
tests/test_providers.py — offline tests for provider modules.
"""
import pytest
from unittest.mock import patch

from app.providers.airhub_sim import AirHubError, AirHubSimulator, make_sim_client
from app.providers import airspace as airspace_mod
from app.providers.faa_facility_map import get_facility_ceiling, load
from app.providers.nsufr import get_nsufr
from app.providers.mock_osm import find_places


# ---------------------------------------------------------------------------
# Airspace wrapper
# ---------------------------------------------------------------------------

def test_airspace_ok_returns_class():
    result = airspace_mod.get_airspace(37.63, -122.39)
    # Sim zone: Class B around SFO-like coords
    assert result.status == "ok"
    assert result.airspace is not None
    assert result.airspace.airspace_class in ("B", "G")  # depends on exact sim zones


def test_airspace_maps_airhub_error_to_failed():
    """Force a 503 from the sim and confirm status='failed'."""
    sim, client = make_sim_client()
    sim.fail_next(1, 503)
    with patch.object(airspace_mod, "_client", client):
        result = airspace_mod.get_airspace(37.63, -122.39)
    assert result.status == "failed"
    assert result.error is not None


def test_get_advisories_returns_advisory_result():
    result = airspace_mod.get_advisories(37.77, -122.45, radius_km=5.0)
    assert result.status == "ok"
    assert isinstance(result.advisories, list)


# ---------------------------------------------------------------------------
# FAA Facility Map
# ---------------------------------------------------------------------------

def test_facility_map_hit_cell1():
    """Point inside cell 1: lon -121.88335 to -121.87502, lat 37.29167 to 37.30001."""
    load()
    result = get_facility_ceiling(37.2958, -121.8792)
    assert result.in_grid is True
    assert result.ceiling_ft == 300


def test_facility_map_hit_cell2():
    load()
    result = get_facility_ceiling(37.3958, -121.9375)
    assert result.in_grid is True
    assert result.ceiling_ft == 400


def test_facility_map_miss():
    load()
    result = get_facility_ceiling(40.0, -100.0)
    assert result.in_grid is False


def test_facility_map_missing_cache_falls_back_to_fixture(tmp_path, monkeypatch):
    """When data/uasfm/ has no .geojson, the provider falls back to the fixture with status stale."""
    import app.providers.faa_facility_map as fm_mod
    from app.config import settings

    # Point to an empty temp dir so no real cached data is found
    monkeypatch.setattr(settings, "DATA_UASFM_DIR", tmp_path)
    # Reset module state
    fm_mod._tree = None
    fm_mod._features = []
    fm_mod._polygons = []
    fm_mod._using_fixture = False

    result = get_facility_ceiling(37.2958, -121.8792)
    assert result.status == "stale"
    assert result.fixture is True
    assert result.in_grid is True   # still hits cell 1 from the fixture


# ---------------------------------------------------------------------------
# NSUFR
# ---------------------------------------------------------------------------

def test_nsufr_returns_fixture():
    result = get_nsufr(38.89, -77.03)
    assert result.status == "ok"
    assert result.fixture is True
    assert len(result.restrictions) >= 1
    assert result.restrictions[0].id == "NSUFR-SIM-001"


# ---------------------------------------------------------------------------
# Mock OSM
# ---------------------------------------------------------------------------

def test_find_places_returns_places():
    result = find_places(area=(37.7749, -122.4194), tags=["leisure"], radius_km=50.0)
    assert result.status == "ok"
    assert result.fixture is True
    assert len(result.places) >= 1


def test_find_places_miss_radius():
    # Very small radius — should find nothing near the ocean
    result = find_places(area=(0.0, 0.0), radius_km=1.0)
    assert result.places == []
