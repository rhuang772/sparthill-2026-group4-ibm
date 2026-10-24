"""
tests/test_api.py — API integration tests using FastAPI's TestClient.

OpenAI calls are stubbed so no real API key is required.
"""
from __future__ import annotations

import asyncio
import json
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app import main as app_main
from app import composer
from app.main import app
from app.schema import BackendBriefingAssessment
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
        return BackendBriefingAssessment(
            status="caution",
            summary="FAA airspace data was unavailable.",
            section_summaries={
                "airspace": "Airspace data was unavailable.",
                "conditions": "Weather was retrieved.",
                "restrictions": "TFR status is uncertain.",
                "nearby_risks": "Water data was unavailable.",
            },
        )

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
    assert "## Where you are / airspace\nAirspace data was unavailable." in data["answer_markdown"]
    assert data["flight_assessment"] == "caution"
    assert data["assessment_summary"] == "FAA airspace data was unavailable."
    assert data["section_summaries"]["airspace"] == "Airspace data was unavailable."


def test_briefing_facts_use_exact_provider_values():
    facts = app_main._briefing_facts(
        {
            "weather_current": {
                "temperature_f": 68.4,
                "wind_mph": 7.2,
                "gusts_mph": 12.6,
                "wind_direction_deg": 315,
                "weather_description": "Partly cloudy",
                "observed_at": "2026-10-24T18:00:00Z",
            },
            "weather_forecast": {
                "hours": [{
                    "time": "2026-10-25T15:00:00+00:00",
                    "temperature_f": 69.5,
                    "wind_mph": 8.1,
                    "wind_direction_deg": 270,
                    "gusts_mph": 13.2,
                    "weather_description": "Partly cloudy",
                }],
                "summary": {
                    "min_temperature_f": 66.1,
                    "max_temperature_f": 70.8,
                    "max_wind_mph": 8.3,
                    "max_wind_mph_120m": 14.1,
                    "max_gusts_mph": 16.5,
                    "min_visibility_m": 10000,
                    "total_precipitation_in": 0,
                    "max_precipitation_probability_pct": 10,
                },
                "fetched_at": "2026-10-24T18:01:00Z",
            },
            "faa_height_limit": {
                "status": "limited",
                "max_altitude_ft": 100,
                "limiting_airport": "Test Airport (TST)",
                "map_effective": "2026-01-01",
                "airspace_classes": ["C"],
                "radius_m": 1000,
            },
            "tfr": {"status": "clear", "data_fetched_at": "2026-10-24T18:00:00Z"},
            "water": {
                "water_found": True,
                "point_over_water": False,
                "nearest_distance_m": 25,
                "risk": "high",
                "water_bodies": [
                    {
                        "name": "Coyote Creek",
                        "kind": "stream",
                        "layer": "flowline",
                        "distance_m": 25,
                    },
                    {
                        "name": None,
                        "kind": "reservoir",
                        "layer": "waterbody",
                        "distance_m": 82.5,
                    },
                ],
                "fetched_at": "2026-10-24T18:00:00Z",
            },
            "population_risk": {
                "status": "moderate",
                "features_found": 3,
                "features": [
                    {"name": "Lincoln Elementary", "kind": "school"},
                    {"name": "Willow Park", "kind": "park"},
                    {"name": "Community Play Area", "kind": "playground"},
                ],
                "fetched_at": "2026-10-24T18:00:00Z",
            },
            "park_risk": {
                "features": [{"name": "Test Preserve"}],
                "fetched_at": "2026-10-24T18:00:00Z",
            },
        },
        planned_altitude_ft=80,
    )

    facts_by_label = {fact["label"]: fact["value"] for fact in facts}
    assert "68.4 °F" in facts_by_label["Current conditions"]
    assert "7.2 mph from NW (315°)" in facts_by_label["Current conditions"]
    assert "69.5 °F" in facts_by_label["Forecast at 2026-10-25T15:00:00+00:00"]
    assert "8.1 mph from W (270°)" in facts_by_label["Forecast at 2026-10-25T15:00:00+00:00"]
    assert "16.5 mph" in facts_by_label["Planned flight weather (1-hour window)"]
    assert facts_by_label["Airspace classes reported"].startswith("Class C")
    assert "within 1000 m" in facts_by_label["Airspace classes reported"]
    assert "does not confirm the exact airspace class at the pin" in facts_by_label["Airspace classes reported"]
    assert "100 ft AGL" in facts_by_label["FAA facility-map ceiling"]
    assert "Planned altitude: 80 ft AGL" in facts_by_label["FAA facility-map ceiling"]
    assert "not an authorization grant" in facts_by_label["FAA facility-map ceiling"]
    assert "Coyote Creek (stream, 25 m)" in facts_by_label["Water nearby"]
    assert "Unnamed water feature (reservoir, 82.5 m)" in facts_by_label["Water nearby"]
    assert "Lincoln Elementary (school)" in facts_by_label["Population context"]
    assert "Willow Park (park)" in facts_by_label["Population context"]
    assert "Community Play Area (playground)" in facts_by_label["Population context"]
    assert "This is not a population count." in facts_by_label["Population context"]


def test_briefing_facts_label_empty_height_limit_classes_as_assumed_class_g():
    facts = app_main._briefing_facts(
        {
            "faa_height_limit": {
                "status": "clear",
                "airspace_classes": [],
                "radius_m": 1000,
            },
        },
        planned_altitude_ft=None,
    )

    class_fact = next(fact for fact in facts if fact["label"] == "Airspace classes reported")
    assert "Assumed Class G" in class_fact["value"]
    assert "unverified fallback" in class_fact["value"]
    assert "does not confirm the exact airspace class at the pin" in class_fact["value"]
    assert "Verify the exact class in B4UFLY" in class_fact["value"]


def test_backend_assessment_sends_all_api_results_to_openai(monkeypatch):
    response_content = json.dumps({
        "status": "caution",
        "summary": "The TFR source could not be verified.",
        "section_summaries": {
            "airspace": "Airspace could not be confirmed.",
            "conditions": "Wind may affect handling.",
            "restrictions": "The TFR source could not be verified.",
            "nearby_risks": "Nearby mapped features need review.",
        },
    })
    mock_client = _make_openai_stub(response_content)
    monkeypatch.setattr(composer.settings, "OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(composer, "_get_client", lambda: mock_client)
    results = {
        "weather_current": {"temperature_f": 65},
        "weather_forecast": {"summary": {"max_wind_mph": 20}},
        "faa_height_limit": {"status": "limited", "max_altitude_ft": 100},
        "tfr": {"status": "unknown"},
        "water": {"risk": "moderate"},
        "population_risk": {"status": "high"},
        "park_risk": {"status": "restricted"},
    }

    assessment = asyncio.run(composer.compose_backend_briefing(
        {"lat": 37.63, "lon": -122.39, "planned_altitude_ft": 120},
        results,
    ))

    assert assessment.status == "caution"
    assert assessment.summary == "The TFR source could not be verified."
    assert assessment.section_summaries.airspace == "Airspace could not be confirmed."
    request = mock_client.chat.completions.create.call_args.kwargs
    assert request["response_format"] == {"type": "json_object"}
    sent_payload = json.loads(request["messages"][1]["content"])
    assert sent_payload["backend_results"] == results
    assert sent_payload["flight_plan"]["planned_altitude_ft"] == 120


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
