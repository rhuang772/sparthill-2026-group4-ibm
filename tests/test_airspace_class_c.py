"""
tests/test_airspace_class_c.py — verify Class C airspace detection near SJC.

Three test modes:
  - Fixture (always runs): forces the 2-cell SJC fixture, ignoring data/uasfm/. The
    exact requested coordinate (37.362934, -121.927722) falls between the two sample
    cells and is not covered, so in_grid=False. A point inside cell 2 is used instead.
  - Downloaded (runs when data/uasfm/*.geojson exists): the requested coordinate is
    Class C (KSJC) in the real downloaded facility map.
  - Live (USE_LIVE_FAA=true): queries the real FAA ArcGIS endpoint. The requested
    coordinate is inside a real Class C cell (ceiling 0 ft, KSJC).

Run live tests:
    USE_LIVE_FAA=true pytest tests/test_airspace_class_c.py -v
"""
import os
import pytest

from app.config import settings
from app.providers import faa_facility_map
from app.providers.faa_facility_map import get_facility_ceiling, load

# The coordinate under test — 37.362934, -121.927722 is Class C (KSJC) per real FAA data.
REQUESTED_LAT = 37.362934
REQUESTED_LON = -121.927722

LIVE = os.environ.get("USE_LIVE_FAA", "false").lower() == "true"


# ---------------------------------------------------------------------------
# Offline fixture tests (always run, USE_LIVE_FAA=false)
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _load_fixture(monkeypatch, tmp_path):
    """Load the 2-cell SJC fixture (ignoring any downloaded data) with USE_LIVE_FAA off."""
    monkeypatch.setattr("app.providers.faa_facility_map.settings",
                        _patched_settings(use_live=False, data_dir=tmp_path / "no-uasfm"))
    load()
    yield
    # Force the next caller to reload with the real settings.
    faa_facility_map._tree = None


def _patched_settings(use_live: bool, data_dir=None):
    from app.config import settings as real_settings
    import types
    # Copy only plain instance attributes to avoid Pydantic class-level descriptor warnings
    s = types.SimpleNamespace(**real_settings.model_dump())
    s.USE_LIVE_FAA = use_live
    if data_dir is not None:
        s.DATA_UASFM_DIR = data_dir
    return s


# ---- Cell 2: ceiling 400 ft, Class C (inside fixture) ----------------------

CELL2_LAT = 37.396
CELL2_LON = -121.937


def test_class_c_detected_cell2():
    """A point inside the fixture Class C cell returns airspace_class='C'."""
    result = get_facility_ceiling(CELL2_LAT, CELL2_LON)
    assert result.airspace_class == "C", (
        f"Expected 'C', got {result.airspace_class!r}. "
        f"status={result.status}, in_grid={result.in_grid}, ceiling_ft={result.ceiling_ft}"
    )


def test_class_c_in_grid_cell2():
    result = get_facility_ceiling(CELL2_LAT, CELL2_LON)
    assert result.in_grid is True


def test_class_c_ceiling_400_cell2():
    result = get_facility_ceiling(CELL2_LAT, CELL2_LON)
    assert result.ceiling_ft == 400


def test_class_c_airport_sjc_cell2():
    result = get_facility_ceiling(CELL2_LAT, CELL2_LON)
    assert result.airport_icao == "KSJC"
    assert result.airport_faaid == "SJC"


def test_class_c_laanc_enabled_cell2():
    result = get_facility_ceiling(CELL2_LAT, CELL2_LON)
    assert result.laanc_enabled is True


# ---- Requested coordinate: between fixture cells (offline = miss) ----------

def test_requested_coordinate_not_in_fixture():
    """
    37.362934, -121.927722 falls between the two SJC sample cells in the
    offline fixture.  With USE_LIVE_FAA=false this returns in_grid=False.

    This is a fixture coverage gap — the real FAA dataset has Class C here
    (see TestDownloadedData and TestLiveFAA below).
    """
    result = get_facility_ceiling(REQUESTED_LAT, REQUESTED_LON)
    assert result.in_grid is False, (
        f"Point ({REQUESTED_LAT}, {REQUESTED_LON}) is inside a loaded fixture cell "
        f"(airspace_class={result.airspace_class!r}). "
        "fixtures/uasfm_sample.geojson may have changed — update this assertion."
    )


# ---------------------------------------------------------------------------
# Downloaded FAA data tests (only run when data/uasfm/*.geojson exists)
# Populate with: python scripts/fetch_facility_map.py --bbox -122.7,37.1,-121.6,38.1 --max-records 50000
# ---------------------------------------------------------------------------

HAS_DOWNLOADED_DATA = any(settings.DATA_UASFM_DIR.glob("*.geojson"))


@pytest.mark.skipif(not HAS_DOWNLOADED_DATA, reason="no downloaded facility map in data/uasfm/")
class TestDownloadedData:
    """Offline lookup against the real downloaded FAA UAS Facility Map."""

    @pytest.fixture(autouse=True)
    def _use_downloaded(self, monkeypatch):
        monkeypatch.setattr("app.providers.faa_facility_map.settings",
                            _patched_settings(use_live=False))
        load()

    def test_downloaded_class_c(self):
        result = get_facility_ceiling(REQUESTED_LAT, REQUESTED_LON)
        assert result.airspace_class == "C", (
            f"Expected Class C from downloaded data, got {result.airspace_class!r}. "
            f"in_grid={result.in_grid}. Does the download cover SJC?"
        )

    def test_downloaded_airport_sjc(self):
        result = get_facility_ceiling(REQUESTED_LAT, REQUESTED_LON)
        assert result.airport_icao == "KSJC"

    def test_downloaded_not_fixture(self):
        result = get_facility_ceiling(REQUESTED_LAT, REQUESTED_LON)
        assert result.fixture is False
        assert result.status == "ok"


# ---------------------------------------------------------------------------
# Live FAA tests (only run when USE_LIVE_FAA=true)
# Network required — skipped by default in CI.
# ---------------------------------------------------------------------------

@pytest.mark.skipif(not LIVE, reason="USE_LIVE_FAA not set — skipping live FAA tests")
class TestLiveFAA:
    """Query the real FAA ArcGIS endpoint for 37.362934, -121.927722."""

    @pytest.fixture(autouse=True)
    def _use_live(self, monkeypatch):
        monkeypatch.setattr("app.providers.faa_facility_map.settings",
                            _patched_settings(use_live=True))

    def test_live_class_c(self):
        """Real FAA data: 37.362934, -121.927722 must be Class C."""
        result = get_facility_ceiling(REQUESTED_LAT, REQUESTED_LON)
        assert result.airspace_class == "C", (
            f"Expected Class C from FAA ArcGIS, got {result.airspace_class!r}. "
            f"status={result.status}, error={result.error!r}"
        )

    def test_live_in_grid(self):
        result = get_facility_ceiling(REQUESTED_LAT, REQUESTED_LON)
        assert result.in_grid is True

    def test_live_airport_sjc(self):
        result = get_facility_ceiling(REQUESTED_LAT, REQUESTED_LON)
        assert result.airport_icao == "KSJC"

    def test_live_not_fixture(self):
        """Live result must not be marked as fixture data."""
        result = get_facility_ceiling(REQUESTED_LAT, REQUESTED_LON)
        assert result.fixture is False

    def test_live_status_ok(self):
        result = get_facility_ceiling(REQUESTED_LAT, REQUESTED_LON)
        assert result.status == "ok"

    def test_live_ceiling_is_integer(self):
        """Ceiling must be a non-negative integer (0 = no routine auth, still valid)."""
        result = get_facility_ceiling(REQUESTED_LAT, REQUESTED_LON)
        assert isinstance(result.ceiling_ft, int)
        assert result.ceiling_ft >= 0
