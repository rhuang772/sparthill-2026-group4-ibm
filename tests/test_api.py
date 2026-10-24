"""
tests/test_api.py — API integration tests using FastAPI's TestClient.

OpenAI calls are stubbed so no real API key is required.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app import main as app_main
from app.main import app
from backend.service.faa_service import FaaService
from backend.service.park_service import ParkService
from backend.service.population_service import PopulationService
from backend.service.tfr_service import TfrService
from backend.service.water_service import WaterService
from backend.service.weather_service import WeatherService

# ---------------------------------------------------------------------------
# OpenAI stub (same helper as test_guardrails.py)
# ---------------------------------------------------------------------------

def _make_openai_stub(content: str):
    mock_message = MagicMock()
    mock_message.content = content
    mock_message.tool_calls = None
    mock_message.model_dump.return_value = {"role": "assistant", "content": content}

    mock_choice = MagicMock()
    mock_choice.message = mock_message
    mock_choice.finish_reason = "stop"

    mock_response = MagicMock()
    mock_response.choices = [mock_choice]

    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = mock_response
    return mock_client


STUB_ANSWER = (
    "Based on the sources checked, this location appears to be in Class B controlled airspace. "
    "Prior FAA authorization through LAANC is needed before flying here. "
    "Verify in an FAA-approved app such as B4UFLY before flying."
)

# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def test_health_endpoint(client):
    r = client.get("/health")
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "ok"
    assert data["persist_user_data"] is False
    assert "mock_data" in data


def test_check_returns_full_schema(client):
    mock_client = _make_openai_stub(STUB_ANSWER)
    with patch("app.composer._get_client", return_value=mock_client):
        r = client.get("/check", params={"lat": 37.63, "lon": -122.39})
    assert r.status_code == 200
    data = r.json()
    # All required keys
    for key in ["answer_markdown", "citations", "tools_called", "sources_failed",
                "data_freshness", "nearby_alternatives", "mock_data"]:
        assert key in data, f"Missing key: {key}"


def test_check_mock_data_true_with_simulator(client):
    """mock_data should be True because the sim and fixture providers are used."""
    mock_client = _make_openai_stub(STUB_ANSWER)
    with patch("app.composer._get_client", return_value=mock_client):
        r = client.get("/check", params={"lat": 37.63, "lon": -122.39})
    assert r.status_code == 200
    # mock_data is set by the footer / _LoopResult based on provider flags
    # Even without tool calls, footer is always appended
    assert "B4UFLY" in r.json()["answer_markdown"]


def test_check_missing_lat_returns_422(client):
    r = client.get("/check", params={"lon": -122.39})
    assert r.status_code == 422


def test_check_missing_lon_returns_422(client):
    r = client.get("/check", params={"lat": 37.63})
    assert r.status_code == 422


def test_check_out_of_range_lat_returns_422(client):
    r = client.get("/check", params={"lat": 200.0, "lon": -122.39})
    assert r.status_code == 422


def test_briefing_aggregates_backend_sources(client, monkeypatch):
    class FakeResult:
        status = "ok"

        def model_dump(self, mode):
            return {
                "status": self.status,
                "observed_at": "2026-10-24T18:00:00+00:00",
                "fetched_at": "2026-10-24T18:00:00+00:00",
                "data_fetched_at": "2026-10-24T18:00:00+00:00",
            }

    async def success(*args, **kwargs):
        return FakeResult()

    async def fail(*args, **kwargs):
        raise RuntimeError("upstream unavailable")

    for service, method in (
        (WeatherService, "get_current"),
        (WeatherService, "get_window"),
        (FaaService, "get_height_limit"),
        (TfrService, "get_tfrs"),
        (WaterService, "get_water"),
        (PopulationService, "get_population_risk"),
        (ParkService, "get_parks"),
    ):
        monkeypatch.setattr(service, method, success)

    monkeypatch.setattr(WaterService, "get_water", fail)
    composed = {}

    async def compose(flight_plan, results):
        composed["flight_plan"] = flight_plan
        composed["results"] = results
        return STUB_ANSWER

    monkeypatch.setattr(app_main.composer, "compose_backend_briefing", compose)

    r = client.get(
        "/briefing",
        params={
            "lat": 37.63,
            "lon": -122.39,
            "radius_m": 250,
            "planned_altitude_ft": 100,
            "start": "2026-10-25T15:00:00Z",
        },
    )

    assert r.status_code == 200
    data = r.json()
    assert len(data["tools_called"]) == 7
    assert data["sources_failed"] == ["water"]
    assert composed["flight_plan"]["planned_altitude_ft"] == 100
    assert set(composed["results"]) == {
        "weather_current",
        "weather_forecast",
        "faa_height_limit",
        "tfr",
        "water",
        "population_risk",
        "park_risk",
    }
    assert composed["results"]["water"]["status"] == "failed"
    assert data["answer_markdown"] == STUB_ANSWER


def test_rules_returns_full_schema(client):
    mock_client = _make_openai_stub("Controlled airspace requires LAANC authorization. Verify in B4UFLY.")
    with patch("app.composer._get_client", return_value=mock_client):
        r = client.get("/rules", params={"query": "controlled airspace authorization"})
    assert r.status_code == 200
    data = r.json()
    for key in ["answer_markdown", "citations", "tools_called", "mock_data"]:
        assert key in data, f"Missing key: {key}"


def test_rules_missing_query_returns_422(client):
    r = client.get("/rules")
    assert r.status_code == 422


def test_rules_too_short_query_returns_422(client):
    r = client.get("/rules", params={"query": "hi"})
    assert r.status_code == 422


def test_footer_always_present(client):
    """The hard-coded footer (B4UFLY reminder) must appear in every response."""
    mock_client = _make_openai_stub("Some answer about drone rules.")
    with patch("app.composer._get_client", return_value=mock_client):
        r = client.get("/rules", params={"query": "altitude limit for drones"})
    assert r.status_code == 200
    assert "B4UFLY" in r.json()["answer_markdown"]
