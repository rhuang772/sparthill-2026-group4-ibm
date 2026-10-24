"""
tests/test_api.py — API integration tests using FastAPI's TestClient.

OpenAI calls are stubbed so no real API key is required.
"""
from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import app

pytestmark = pytest.mark.usefixtures("offline_providers")

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


# ---------------------------------------------------------------------------
# Streaming endpoints
# ---------------------------------------------------------------------------

def _chunk(content=None, tool_calls=None):
    delta = SimpleNamespace(content=content, tool_calls=tool_calls)
    return SimpleNamespace(choices=[SimpleNamespace(delta=delta)])


def _tool_call_delta(index, id=None, name=None, arguments=None):
    return SimpleNamespace(index=index, id=id, function=SimpleNamespace(name=name, arguments=arguments))


def _make_async_stream_stub(*rounds):
    """Each round is a list of chunks returned by one streamed completion."""
    async def stream(chunks):
        for c in chunks:
            yield c

    mock_client = MagicMock()
    mock_client.chat.completions.create = AsyncMock(side_effect=[stream(r) for r in rounds])
    return mock_client


def _parse_sse(text):
    events = []
    for block in text.strip().split("\n\n"):
        lines = dict(line.split(": ", 1) for line in block.splitlines())
        events.append((lines["event"], json.loads(lines["data"])))
    return events


def test_rules_stream_tokens_then_done(client):
    stub = _make_async_stream_stub([_chunk("Controlled airspace "), _chunk("needs LAANC.")])
    with patch("app.composer._get_async_client", return_value=stub):
        r = client.get("/rules/stream", params={"query": "controlled airspace authorization"})
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/event-stream")

    events = _parse_sse(r.text)
    names = [e for e, _ in events]
    assert names[-1] == "done"
    streamed = "".join(d["text"] for e, d in events if e == "token")
    done = events[-1][1]
    assert streamed == done["answer_markdown"]
    assert done["answer_markdown"].startswith("Controlled airspace needs LAANC.")
    assert "B4UFLY" in done["answer_markdown"]


def test_rules_stream_runs_tool_calls(client):
    tool_round = [
        _chunk("Let me check. "),
        _chunk(tool_calls=[_tool_call_delta(0, id="call_1", name="search_rules", arguments='{"query":')]),
        _chunk(tool_calls=[_tool_call_delta(0, arguments=' "laanc"}')]),
    ]
    answer_round = [_chunk("LAANC gives authorization.")]
    stub = _make_async_stream_stub(tool_round, answer_round)
    fake_chunks = [{"rule_id": "r1", "text": "...", "metadata": {"citation": "FAA-G-8082-22"}}]
    with patch("app.composer._get_async_client", return_value=stub), \
         patch("app.composer.search_rules", return_value=fake_chunks):
        r = client.get("/rules/stream", params={"query": "what is laanc"})

    events = _parse_sse(r.text)
    names = [e for e, _ in events]
    assert "reset" in names
    tool_events = [d for e, d in events if e == "tool"]
    assert [t["state"] for t in tool_events] == ["running", "done"]
    assert tool_events[0]["name"] == "search_rules"

    done = events[-1][1]
    assert done["answer_markdown"].startswith("LAANC gives authorization.")
    assert done["citations"][0]["citation"] == "FAA-G-8082-22"
    second_call_msgs = stub.chat.completions.create.call_args_list[1].kwargs["messages"]
    assert second_call_msgs[-1]["role"] == "tool"


def test_check_stream_reports_prerun_tools(client):
    stub = _make_async_stream_stub([_chunk("Class B airspace.")])
    with patch("app.composer._get_async_client", return_value=stub):
        r = client.get("/check/stream", params={"lat": 37.63, "lon": -122.39})
    assert r.status_code == 200

    events = _parse_sse(r.text)
    tool_names = {d["name"] for e, d in events if e == "tool"}
    assert {"get_airspace", "get_tfrs", "get_weather"} <= tool_names
    done = events[-1]
    assert done[0] == "done"
    for key in ["answer_markdown", "citations", "tools_called", "sources_failed",
                "data_freshness", "nearby_alternatives", "mock_data"]:
        assert key in done[1]


def test_stream_error_becomes_error_event(client):
    stub = MagicMock()
    stub.chat.completions.create = AsyncMock(side_effect=RuntimeError("boom"))
    with patch("app.composer._get_async_client", return_value=stub):
        r = client.get("/rules/stream", params={"query": "altitude limit"})
    events = _parse_sse(r.text)
    assert events[-1] == ("error", {"message": "boom"})
