import pytest
from airhub_sim import (AirHubClient, AirHubError, AirHubSimulator, SIM_API_KEY, SIM_CLIENT_ID,
                        SIM_CLIENT_SECRET, make_sim_client)


def test_controlled_airspace_has_ceiling():
    _, c = make_sim_client()
    b = c.briefing_location(37.63, -122.39)
    assert b["airspace"]["class"] == "B" and b["facility_map"]["in_grid"]
    assert b["facility_map"]["ceiling_ft"] in (0, 100, 200)


def test_open_class_g_is_not_in_grid():
    _, c = make_sim_client()
    b = c.briefing_location(39.5, -117.0)
    assert b["airspace"]["class"] == "G" and not b["facility_map"]["in_grid"] and b["advisories"] == []


def test_nsufr_and_active_tfr_reported():
    _, c = make_sim_client()
    assert any(a["type"] == "nsufr" for a in c.briefing_location(38.265, -121.93)["advisories"])
    assert any(a["type"] == "tfr" for a in c.briefing_location(39.91, -121.61)["advisories"])


def test_expired_tfr_not_reported_as_active():
    _, c = make_sim_client()
    assert c.briefing_location(36.0, -115.0)["advisories"] == []


def test_token_cached_then_refreshed_after_expiry():
    sim, c = make_sim_client()
    c.briefing_location(37, -122); c.briefing_location(38, -122)
    assert sim.token_requests == 1
    sim.expire_all_tokens()
    c.briefing_location(37, -122)
    assert sim.token_requests == 2


def test_ungranted_scope_rejected_at_token():
    sim = AirHubSimulator()
    c = AirHubClient(SIM_API_KEY, SIM_CLIENT_ID, SIM_CLIENT_SECRET, ["operation:create"], transport=sim.transport())
    with pytest.raises(AirHubError) as e:
        c.briefing_location(37, -122)
    assert e.value.status == 403


def test_missing_scope_for_endpoint_is_403():
    sim = AirHubSimulator()
    c = AirHubClient(SIM_API_KEY, SIM_CLIENT_ID, SIM_CLIENT_SECRET, ["advisory:read"], transport=sim.transport())
    with pytest.raises(AirHubError) as e:
        c.briefing_location(37, -122)
    assert e.value.status == 403


def test_bad_api_key_and_bad_credentials():
    sim = AirHubSimulator()
    with pytest.raises(AirHubError) as e:
        AirHubClient("nope", SIM_CLIENT_ID, SIM_CLIENT_SECRET, ["advisory:read"], transport=sim.transport()).advisories_bbox(0, 0, 1, 1)
    assert e.value.status == 401
    with pytest.raises(AirHubError) as e:
        AirHubClient(SIM_API_KEY, SIM_CLIENT_ID, "wrong", ["advisory:read"], transport=sim.transport()).advisories_bbox(0, 0, 1, 1)
    assert e.value.status == 401


def test_upstream_failure_surfaces_as_error():
    sim, c = make_sim_client()
    sim.fail_next(1, 503)
    with pytest.raises(AirHubError) as e:
        c.briefing_location(37, -122)
    assert e.value.status == 503
    assert c.briefing_location(37, -122)   # recovers


def test_bbox_and_geojson_advisories_agree():
    _, c = make_sim_client()
    by_bbox = {a["id"] for a in c.advisories_bbox(-122.0, 38.0, -121.8, 38.5)["advisories"]}
    poly = {"type": "Polygon", "coordinates": [[[-122.0, 38.0], [-121.8, 38.0], [-121.8, 38.5], [-122.0, 38.5], [-122.0, 38.0]]]}
    by_geo = {a["id"] for a in c.advisories_geojson(poly)["advisories"]}
    assert by_bbox == by_geo and "SIM-NSUFR-1" in by_bbox


def test_area_briefing_merges_points():
    _, c = make_sim_client()
    poly = {"type": "Polygon", "coordinates": [[[-122.42, 37.60], [-122.36, 37.60], [-122.36, 37.64], [-122.42, 37.64], [-122.42, 37.60]]]}
    d = c.briefing_area(poly)
    assert d["controlled"] and d["min_ceiling_ft"] is not None


def test_bad_inputs_are_400():
    _, c = make_sim_client()
    with pytest.raises(AirHubError) as e:
        c.briefing_location(123, -122)
    assert e.value.status == 400
