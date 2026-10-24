"""
tests/test_judge.py — the answer reviewer (app/judge.py). The judge model is stubbed;
these tests pin down that code, not the model, decides what counts as verified.
"""
from __future__ import annotations

import datetime as dt
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app import judge
from app.config import settings
from app.main import app
from app.providers.base import WeatherResult

NOW = dt.datetime(2026, 10, 24, 16, 0, tzinfo=dt.timezone.utc)

CHUNK = {
    "rule_id": "sg-3a-wind-1",
    "text": "Strong, gusty winds make it harder to keep a small unmanned aircraft stable.",
    "metadata": {"citation": "FAA-G-8082-22, Chapter 3, “Wind”, p. 3-4"},
}
WEATHER_OK = WeatherResult(checked_at=NOW, status="ok", gusts_mph=17.2, wind_mph=6.9)
WEATHER_FAILED = WeatherResult(checked_at=NOW, status="failed", error="Open-Meteo unavailable")


def _stub(claims=None, content=None, raises=None):
    client = MagicMock()
    if raises:
        client.chat.completions.create.side_effect = raises
    else:
        msg = MagicMock()
        msg.content = content if content is not None else json.dumps({"claims": claims})
        client.chat.completions.create.return_value.choices = [MagicMock(message=msg)]
    return client


def _review(answer, claims=None, chunks=(CHUNK,), tools=(("get_weather", WEATHER_OK),), **stub):
    with patch("app.judge._get_client", return_value=_stub(claims, **stub)):
        return judge.review_answer(answer, list(chunks), list(tools))


def _source(review, source_id):
    return next(s for s in review.sources if s.source_id == source_id)


def test_claims_with_verbatim_quotes_verify_their_sources():
    review = _review("Gusts reach 17.2 mph (get_weather). Gusty winds make drones harder to keep stable (sg-3a-wind-1).", [
        {"claim": "Gusts reach 17.2 mph", "cited_as": "get_weather", "source_id": "get_weather",
         "verdict": "consistent", "evidence": '"gusts_mph":17.2'},
        {"claim": "Gusty winds make drones harder to keep stable", "cited_as": "sg-3a-wind-1",
         "source_id": "sg-3a-wind-1", "verdict": "consistent",
         "evidence": "Strong, gusty winds make it harder to keep a small unmanned aircraft stable"},
    ])
    assert review.verdict == "verified"
    assert _source(review, "get_weather").status == "verified"
    assert _source(review, "sg-3a-wind-1").status == "verified"
    assert review.issues == []


def test_consistent_without_a_real_quote_is_not_verified():
    review = _review("Gusts reach 17.2 mph.", [
        {"claim": "Gusts reach 17.2 mph", "cited_as": None, "source_id": "get_weather",
         "verdict": "consistent", "evidence": "wind gusts around seventeen mph"},
    ])
    assert review.claims[0].status == "unverified"
    assert _source(review, "get_weather").status == "unverified"
    assert review.verdict == "unverified"


def test_missing_evidence_is_not_verified():
    review = _review("Gusts reach 17.2 mph.", [
        {"claim": "Gusts reach 17.2 mph", "source_id": "get_weather", "verdict": "consistent", "evidence": None},
    ])
    assert review.claims[0].status == "unverified"
    assert review.verdict != "verified"


def test_cited_rule_id_never_retrieved_is_flagged_even_if_judge_approves():
    """The live-test case: a citation the model invented, with no search_rules call."""
    answer = "Strong gusts can affect stability (rule_id: weather_rules_guide, citation: FAA-G-8082-22)."
    review = _review(answer, [
        {"claim": "Strong gusts can affect stability", "cited_as": "weather_rules_guide",
         "source_id": "get_weather", "verdict": "consistent", "evidence": '"gusts_mph":17.2'},
    ], chunks=())
    assert review.verdict == "issues"
    assert sum("weather_rules_guide" in i for i in review.issues) == 1
    assert review.claims[0].status == "not_retrieved"


def test_unknown_sg_rule_id_is_caught_without_the_judge():
    review = _review("See sg-9z-made-up-1 for details.", raises=RuntimeError("judge down"))
    assert review.verdict == "issues"
    assert any("sg-9z-made-up-1" in i for i in review.issues)
    assert all(s.status != "verified" for s in review.sources)


def test_failed_tool_is_never_verified():
    review = _review("Gusts are unknown.", [
        {"claim": "Open-Meteo is unavailable", "source_id": "get_weather", "verdict": "consistent",
         "evidence": "Open-Meteo unavailable"},
    ], tools=(("get_weather", WEATHER_FAILED),))
    assert _source(review, "get_weather").status == "failed"
    assert review.claims[0].status == "unverified"
    assert review.verdict == "unverified"


def test_inconsistent_claim_is_an_issue():
    review = _review("Gusts reach 40 mph.", [
        {"claim": "Gusts reach 40 mph", "source_id": "get_weather", "verdict": "inconsistent",
         "evidence": '"gusts_mph": 17.2'},
    ])
    assert review.verdict == "issues"
    assert _source(review, "get_weather").status == "inconsistent"


def test_unsupported_claim_is_an_issue():
    review = _review("Overcast means the clouds are low.", [
        {"claim": "Overcast means the clouds are low", "source_id": None, "verdict": "unsupported"},
    ])
    assert review.verdict == "issues"
    assert review.claims[0].status == "unsupported"


def test_judge_failure_verifies_nothing():
    review = _review("Gusts reach 17.2 mph.", raises=RuntimeError("timeout"))
    assert review.verdict == "unverified"
    assert review.error
    assert all(s.status in ("unused", "failed") for s in review.sources)


def test_malformed_judge_output_verifies_nothing():
    review = _review("Gusts reach 17.2 mph.", content="not json")
    assert review.verdict == "unverified"
    assert review.error


def test_judge_cannot_point_at_a_source_that_does_not_exist():
    review = _review("Gusts reach 17.2 mph.", [
        {"claim": "Gusts reach 17.2 mph", "source_id": "nws_forecast", "verdict": "consistent",
         "evidence": '"gusts_mph":17.2'},
    ])
    assert review.claims[0].status == "unsupported"
    assert review.verdict == "issues"


def test_study_guide_citation_matches_a_retrieved_chunk():
    review = _review("Gusty winds make drones harder to keep stable (FAA-G-8082-22, Chapter 3).", [
        {"claim": "Gusty winds make drones harder to keep stable", "cited_as": "FAA-G-8082-22, Chapter 3",
         "source_id": "sg-3a-wind-1", "verdict": "consistent",
         "evidence": "gusty winds make it harder to keep a small unmanned aircraft stable"},
    ])
    assert review.claims[0].status == "verified"
    assert review.verdict == "verified"


def test_review_markdown_lists_issues_and_failed_sources():
    review = _review("Gusts are 40 mph.", [
        {"claim": "Gusts are 40 mph", "source_id": "get_weather", "verdict": "inconsistent",
         "evidence": '"gusts_mph":17.2'},
    ], tools=(("get_weather", WEATHER_OK), ("get_tfrs", {"status": "failed"})))
    md = judge.review_markdown(review)
    assert "Answer review" in md
    assert "conflicts with get_weather" in md
    assert "lookup failed: get_tfrs" in md


# ---------------------------------------------------------------------------
# Wired into the API
# ---------------------------------------------------------------------------

def _stream_stub(text):
    async def stream():
        delta = MagicMock(content=text, tool_calls=None)
        yield MagicMock(choices=[MagicMock(delta=delta)])

    client = MagicMock()
    client.chat.completions.create = AsyncMock(return_value=stream())
    return client


def _async_judge_stub(claims):
    msg = MagicMock(content=json.dumps({"claims": claims}))
    client = MagicMock()
    client.chat.completions.create = AsyncMock(return_value=MagicMock(choices=[MagicMock(message=msg)]))
    return client


@pytest.fixture
def review_on(monkeypatch):
    monkeypatch.setattr(settings, "ENABLE_ANSWER_REVIEW", True)


def test_rules_stream_sends_review_before_footer(review_on):
    answer = "See rule_id: invented_rule for details."
    claims = [{"claim": "See invented_rule", "cited_as": "invented_rule", "source_id": None,
               "verdict": "unsupported"}]
    with TestClient(app) as client, \
         patch("app.composer._get_async_client", return_value=_stream_stub(answer)), \
         patch("app.judge._get_async_client", return_value=_async_judge_stub(claims)):
        r = client.get("/rules/stream", params={"query": "altitude limit"})

    blocks = [b for b in r.text.strip().split("\n\n")]
    events = [(b.split("\n")[0][7:], json.loads(b.split("\n", 1)[1][6:])) for b in blocks]
    names = [e for e, _ in events]
    assert names.index("review") < names.index("done")

    done = events[-1][1]
    assert done["review"]["verdict"] == "issues"
    md = done["answer_markdown"]
    assert md.index("Answer review") < md.index("B4UFLY")
    assert "invented_rule" in md
    assert "".join(d["text"] for e, d in events if e == "token") == md
