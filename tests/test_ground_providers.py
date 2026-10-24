"""
tests/test_ground_providers.py — offline tests for the TFR, park, population and water
providers. HTTP is served by httpx.MockTransport; nothing touches the network.
"""
from __future__ import annotations

import asyncio
import datetime as dt

import httpx
import pytest

from app.config import settings
from app.providers import http_client, park, population, tfr, water

# Point used throughout: San Jose, CA
LAT, LON = 37.30, -121.90


@pytest.fixture
def mock_http():
    """Install a MockTransport-backed shared client; the test sets the handler."""
    routes: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        for prefix, respond in routes.items():
            if str(request.url).startswith(prefix):
                return respond(request) if callable(respond) else respond
        return httpx.Response(404)

    http_client.set_http_client(httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    yield routes
    http_client.set_http_client(None)


# ---------------------------------------------------------------------------
# TFR
# ---------------------------------------------------------------------------

def _tfr_xml(effective: dt.datetime, expires: dt.datetime, floor_ft: int = 0) -> str:
    fmt = "%Y-%m-%dT%H:%M:%S"
    return f"""<XNOTAM-Update><Group><Add><Not>
      <dateEffective>{effective.strftime(fmt)}</dateEffective>
      <dateExpire>{expires.strftime(fmt)}</dateExpire>
      <codeTimeZone>UTC</codeTimeZone>
      <TfrNot><TFRAreaGroup>
        <aseTFRArea>
          <AseUid><codeId>A1</codeId></AseUid>
          <txtName>Stadium area</txtName>
          <valDistVerLower>{floor_ft}</valDistVerLower><codeDistVerLower>HEI</codeDistVerLower>
          <valDistVerUpper>3000</valDistVerUpper><codeDistVerUpper>ALT</codeDistVerUpper>
        </aseTFRArea>
        <abdMergedArea>
          <AbdUid><AseUid><codeId>A1</codeId></AseUid></AbdUid>
          <Avx><geoLat>37.29N</geoLat><geoLong>121.91W</geoLong></Avx>
          <Avx><geoLat>37.31N</geoLat><geoLong>121.91W</geoLong></Avx>
          <Avx><geoLat>37.31N</geoLat><geoLong>121.89W</geoLong></Avx>
          <Avx><geoLat>37.29N</geoLat><geoLong>121.89W</geoLong></Avx>
        </abdMergedArea>
      </TFRAreaGroup></TfrNot>
    </Not></Add></Group></XNOTAM-Update>"""


@pytest.fixture
def fresh_tfr_state(monkeypatch):
    monkeypatch.setattr(tfr, "_state", {"at": None, "tfrs": None, "unresolved": []})
    monkeypatch.setattr(tfr, "_detail_cache", {})


def _serve_tfr(routes, floor_ft: int = 0):
    now = dt.datetime.now(dt.timezone.utc)
    routes[tfr.LIST_URL] = httpx.Response(200, json=[
        {"notam_id": "6/1234", "type": "SECURITY", "description": "San Jose, CA stadium"},
    ])
    routes[tfr.DETAIL_URL.format("6_1234")] = httpx.Response(
        200, text=_tfr_xml(now - dt.timedelta(days=1), now + dt.timedelta(days=1), floor_ft))


def test_tfr_restricted_when_active_area_overlaps(mock_http, fresh_tfr_state):
    _serve_tfr(mock_http)
    result = asyncio.run(tfr.get_tfrs(LAT, LON, 100))
    assert result.status == "ok"
    assert result.finding == "restricted"
    assert result.tfrs[0].notam_id == "6/1234"
    assert result.tfrs[0].time_status == "active"
    assert result.tfrs[0].floor_datum == "AGL"


def test_tfr_expired_for_later_flight_window(mock_http, fresh_tfr_state):
    _serve_tfr(mock_http)
    later = dt.datetime.now(dt.timezone.utc) + dt.timedelta(days=3)
    result = asyncio.run(tfr.get_tfrs(LAT, LON, 100, start=later))
    assert result.finding == "none_found"
    assert result.tfrs[0].time_status == "expired"


def test_tfr_high_floor_does_not_restrict_drones(mock_http, fresh_tfr_state):
    _serve_tfr(mock_http, floor_ft=1000)
    result = asyncio.run(tfr.get_tfrs(LAT, LON, 100))
    assert result.finding == "none_found"
    assert result.tfrs[0].reaches_drone_altitudes is False


def test_tfr_far_away_point_has_no_hits(mock_http, fresh_tfr_state):
    _serve_tfr(mock_http)
    result = asyncio.run(tfr.get_tfrs(40.0, -100.0, 100))
    assert result.finding == "none_found"
    assert result.tfrs == []


def test_tfr_feed_down_is_failed(mock_http, fresh_tfr_state):
    mock_http[tfr.LIST_URL] = httpx.Response(503)
    result = asyncio.run(tfr.get_tfrs(LAT, LON, 100))
    assert result.status == "failed"
    assert result.finding == "unknown"


def test_tfr_unparseable_detail_is_unknown(mock_http, fresh_tfr_state):
    _serve_tfr(mock_http)
    mock_http[tfr.LIST_URL] = httpx.Response(200, json=[
        {"notam_id": "6/1234", "type": "SECURITY", "description": "San Jose, CA stadium"},
        {"notam_id": "6/9999", "type": "HAZARDS", "description": "broken"},
    ])
    mock_http[tfr.DETAIL_URL.format("6_9999")] = httpx.Response(200, text="<not-xml")
    result = asyncio.run(tfr.get_tfrs(40.0, -100.0, 100))
    assert result.finding == "unknown"
    assert result.unresolved_notams == ["6/9999"]


# ---------------------------------------------------------------------------
# Parks
# ---------------------------------------------------------------------------

def test_parks_excludes_local_civic_spaces(mock_http):
    mock_http[park.PAD_US_URL] = httpx.Response(200, json={"features": [
        {"attributes": {"OBJECTID": 1, "Unit_Nm": "Henry W. Coe State Park", "Des_Tp": "SP",
                        "Mang_Name": "SPR", "Gap_Sts": "2"}},
        {"attributes": {"OBJECTID": 2, "Unit_Nm": "Guadalupe River Park", "Des_Tp": "LP"}},
        {"attributes": {"OBJECTID": 3, "Unit_Nm": "Civic Center", "Des_Tp": "SP"}},
    ]})
    result = asyncio.run(park.get_parks(LAT, LON, 500))
    assert result.status == "ok"
    assert result.finding == "protected_area"
    assert [a.name for a in result.areas] == ["Henry W. Coe State Park"]
    assert result.areas[0].manager == "SPR"


def test_parks_none_found(mock_http):
    mock_http[park.PAD_US_URL] = httpx.Response(200, json={"features": []})
    result = asyncio.run(park.get_parks(LAT, LON))
    assert result.finding == "none_found"
    assert result.radius_m == park.DEFAULT_RADIUS_M


def test_parks_arcgis_error_is_failed(mock_http):
    mock_http[park.PAD_US_URL] = httpx.Response(200, json={"error": {"code": 400}})
    result = asyncio.run(park.get_parks(LAT, LON))
    assert result.status == "failed"
    assert result.finding == "unknown"


# ---------------------------------------------------------------------------
# Population
# ---------------------------------------------------------------------------

def _place(name: str, categories: list[str], lat: float, lon: float, place_id: str) -> dict:
    return {"properties": {"name": name, "categories": categories, "lat": lat, "lon": lon,
                           "place_id": place_id},
            "geometry": {"type": "Point", "coordinates": [lon, lat]}}


def test_population_without_key_is_failed(monkeypatch):
    monkeypatch.setattr(settings, "GEOAPIFY_API_KEY", "")
    result = asyncio.run(population.get_population_risk(LAT, LON))
    assert result.status == "failed"
    assert result.risk == "unknown"


def test_population_scores_nearby_places(mock_http, monkeypatch):
    monkeypatch.setattr(settings, "GEOAPIFY_API_KEY", "test-key")
    mock_http[population.GEOAPIFY_URL] = httpx.Response(200, json={"features": [
        _place("Lincoln High", ["education.school"], LAT, LON + 0.0005, "a"),
        _place("SJSU", ["education.university"], LAT + 0.0005, LON, "b"),
        _place("Far away mall", ["commercial"], LAT, LON, "c"),           # no matching rule
        _place("Out of radius", ["leisure.park"], LAT + 0.05, LON, "d"),
    ]})
    result = asyncio.run(population.get_population_risk(LAT, LON, 250))
    assert result.status == "ok"
    assert {p.kind for p in result.places} == {"school", "university"}
    assert result.risk == "moderate"
    assert result.places == sorted(result.places, key=lambda p: p.distance_m)


def test_population_http_error_hides_api_key(mock_http, monkeypatch):
    monkeypatch.setattr(settings, "GEOAPIFY_API_KEY", "secret-key")
    mock_http[population.GEOAPIFY_URL] = httpx.Response(401)
    result = asyncio.run(population.get_population_risk(LAT, LON))
    assert result.status == "failed"
    assert "401" in result.error
    assert "secret-key" not in result.error


# ---------------------------------------------------------------------------
# Water
# ---------------------------------------------------------------------------

def _square(lat: float, lon: float, half_deg: float) -> dict:
    ring = [[lon - half_deg, lat - half_deg], [lon + half_deg, lat - half_deg],
            [lon + half_deg, lat + half_deg], [lon - half_deg, lat + half_deg],
            [lon - half_deg, lat - half_deg]]
    return {"type": "Polygon", "coordinates": [ring]}


@pytest.fixture
def fresh_water_cache(monkeypatch):
    monkeypatch.setattr(water, "_cache", {})


def _water_layer(features: list) -> httpx.Response:
    return httpx.Response(200, json={"type": "FeatureCollection", "features": features})


def test_water_point_over_lake_is_high(mock_http, fresh_water_cache):
    lake = {"geometry": _square(LAT, LON, 0.001),
            "properties": {"gnis_name": "Lake Test", "featuretypelabel": "Lake/Pond"}}
    mock_http[f"{water.BASE_URL}/60/query"] = _water_layer([lake])
    mock_http[f"{water.BASE_URL}/50/query"] = _water_layer([])
    result = asyncio.run(water.get_water(LAT, LON, 500))
    assert result.status == "ok"
    assert result.risk == "high"
    assert result.point_over_water is True
    assert result.water_bodies[0].name == "Lake Test"
    assert result.water_bodies[0].kind == "lake/pond"


def test_water_creek_nearby_is_moderate(mock_http, fresh_water_cache):
    # ~300 m north of the point
    creek = {"geometry": {"type": "LineString",
                          "coordinates": [[LON - 0.01, LAT + 0.0027], [LON + 0.01, LAT + 0.0027]]},
             "properties": {"gnis_name": "Test Creek"}}
    mock_http[f"{water.BASE_URL}/60/query"] = _water_layer([])
    mock_http[f"{water.BASE_URL}/50/query"] = _water_layer([creek])
    result = asyncio.run(water.get_water(LAT, LON, 500))
    assert result.risk == "moderate"
    assert result.water_bodies[0].layer == "flowline"
    assert 250 < result.nearest_distance_m < 350


def test_water_none_found(mock_http, fresh_water_cache):
    mock_http[f"{water.BASE_URL}/60/query"] = _water_layer([])
    mock_http[f"{water.BASE_URL}/50/query"] = _water_layer([])
    result = asyncio.run(water.get_water(LAT, LON, 500))
    assert result.risk == "none"
    assert result.note


def test_water_service_down_is_failed(mock_http, fresh_water_cache):
    mock_http[f"{water.BASE_URL}/60/query"] = httpx.Response(503)
    mock_http[f"{water.BASE_URL}/50/query"] = httpx.Response(503)
    result = asyncio.run(water.get_water(LAT, LON, 500))
    assert result.status == "failed"
    assert result.risk == "unknown"
