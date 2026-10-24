"""
tests/test_weather.py — weather provider (current + forecast + geocoding) and the
get_weather agent tool. Open-Meteo is replaced with an httpx.MockTransport.
"""
from __future__ import annotations

import datetime as dt

import httpx
import pytest

from app import composer
from app.config import settings
from app.providers import weather

CURRENT = {
    "time": "2026-10-24T16:00", "temperature_2m": 60.0, "wind_speed_10m": 5.0,
    "wind_gusts_10m": 9.0, "wind_direction_10m": 180, "cloud_cover": 20,
    "relative_humidity_2m": 50, "is_day": 1, "weather_code": 1, "precipitation": 0.0,
}

GEOCODE = {"results": [
    {"name": "Springfield", "admin1": "Missouri", "country": "United States",
     "country_code": "US", "latitude": 37.2, "longitude": -93.3},
    {"name": "Springfield", "admin1": "Illinois", "country": "United States",
     "country_code": "US", "latitude": 39.8, "longitude": -89.6},
]}


def _hourly_for(request: httpx.Request) -> dict:
    stamp = request.url.params["start_hour"]
    return {"hourly": {
        "time": [stamp], "temperature_2m": [55.0], "wind_speed_10m": [18.0],
        "wind_gusts_10m": [31.0], "wind_direction_10m": [270], "cloud_cover": [90],
        "relative_humidity_2m": [80], "is_day": [1], "weather_code": [61],
        "precipitation": [0.1], "precipitation_probability": [70],
    }}


@pytest.fixture
def requests(monkeypatch):
    """Route weather's httpx.Client to a fake Open-Meteo; returns the request log."""
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if request.url.host.startswith("geocoding"):
            name = request.url.params["name"]
            return httpx.Response(200, json=GEOCODE if name == "Springfield" else {})
        if "hourly" in request.url.params:
            return httpx.Response(200, json=_hourly_for(request))
        return httpx.Response(200, json={"current": CURRENT})

    real_client = httpx.Client
    monkeypatch.setattr(weather.httpx, "Client",
                        lambda **kw: real_client(transport=httpx.MockTransport(handler), **kw))
    monkeypatch.setattr(settings, "USE_LIVE_WEATHER", True)
    return seen


def _in(hours: float) -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=hours)


def test_no_time_returns_current(requests):
    r = weather.get_weather(47.6, -122.3)
    assert r.status == "ok" and r.forecast is False
    assert r.wind_mph == 5.0
    assert "current" in requests[0].url.params


def test_future_time_returns_forecast_for_nearest_hour(requests):
    at = _in(26).replace(minute=40)
    r = weather.get_weather(47.6, -122.3, at)
    assert r.status == "ok" and r.forecast is True
    assert r.gusts_mph == 31.0
    assert r.precipitation_probability_pct == 70
    assert r.weather_description == "Slight rain"

    expected = (at + dt.timedelta(minutes=30)).replace(minute=0, second=0, microsecond=0)
    assert requests[0].url.params["start_hour"] == expected.strftime("%Y-%m-%dT%H:%M")
    assert requests[0].url.params["timezone"] == "GMT"
    assert r.observed_at == expected.strftime("%Y-%m-%dT%H:%MZ")


def test_naive_time_is_treated_as_utc(requests):
    at = _in(48).replace(minute=0, second=0, microsecond=0)
    weather.get_weather(47.6, -122.3, at.replace(tzinfo=None))
    assert requests[0].url.params["start_hour"] == at.strftime("%Y-%m-%dT%H:%M")


def test_far_forecast_gets_reliability_note(requests):
    assert weather.get_weather(47.6, -122.3, _in(24 * 5)).note
    assert weather.get_weather(47.6, -122.3, _in(24)).note is None


def test_beyond_horizon_and_past_fail_without_calling_api(requests):
    assert weather.get_weather(47.6, -122.3, _in(24 * 20)).status == "failed"
    assert weather.get_weather(47.6, -122.3, _in(-5)).status == "failed"
    assert requests == []


def test_geocode_uses_qualifier_to_pick_match(requests):
    lat, lon, label = weather.geocode("Springfield, Illinois")
    assert (lat, lon) == (39.8, -89.6)
    assert label == "Springfield, Illinois, United States"
    assert weather.geocode("Springfield")[0] == 37.2
    assert weather.geocode("Nowhereville") is None


def test_tool_dispatch_by_place_and_time(requests):
    at = _in(30).isoformat()
    r = composer._dispatch_tool("get_weather", {"place": "Springfield, Illinois", "time": at})
    assert r.status == "ok" and r.forecast is True
    assert r.location_name == "Springfield, Illinois, United States"
    assert (r.lat, r.lon) == (39.8, -89.6)


def test_tool_dispatch_errors_are_failed_results(requests):
    assert composer._dispatch_tool("get_weather", {})["status"] == "failed"
    assert composer._dispatch_tool("get_weather", {"place": "Nowhereville"})["status"] == "failed"
    assert composer._dispatch_tool("get_weather", {"lat": 1, "lon": 2, "time": "soon"})["status"] == "failed"


def test_weather_tool_available_to_agent():
    names = lambda tools: {t["function"]["name"] for t in tools}  # noqa: E731
    assert "get_weather" in names(composer._RULES_ONLY_TOOLS)
    assert "get_weather" in names(composer._LOCATION_AGENT_TOOLS)
