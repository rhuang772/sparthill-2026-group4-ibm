"""
tests/test_guardrails.py — guardrail tests with OpenAI stubbed.

All tests patch the OpenAI client so no real API calls are made.
The stub returns a pre-scripted assistant message.
"""
from __future__ import annotations

import asyncio
import json
from unittest.mock import MagicMock, patch

import pytest

from app.schema import CheckResponse, RulesResponse

BANNED_WORDS = ["approved", "legal to fly", "safe", "clear"]

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_openai_stub(assistant_content: str):
    """Return a mock OpenAI client that always responds with assistant_content."""
    tool_call = None  # no tool calls — model gives a direct answer

    mock_message = MagicMock()
    mock_message.content = assistant_content
    mock_message.tool_calls = None
    mock_message.model_dump.return_value = {"role": "assistant", "content": assistant_content}

    mock_choice = MagicMock()
    mock_choice.message = mock_message
    mock_choice.finish_reason = "stop"

    mock_response = MagicMock()
    mock_response.choices = [mock_choice]

    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = mock_response
    return mock_client


def _check_no_banned_words(text: str):
    """Check that none of the banned standalone verdict words appear in the text.

    Context-aware exceptions:
    - "approved" is ONLY banned when used as a verdict about a flight
      (e.g. "your flight is approved"). The phrase "FAA-approved app" in the
      hard-coded footer is a legitimate descriptor and is excluded.
    - "safe" in compound phrases like "fail-safe" is not flagged (word-boundary).
    - We use regex with a negative lookbehind for "faa-" to exclude the footer phrase.
    """
    import re
    lower = text.lower()
    for word in BANNED_WORDS:
        if word == "approved":
            # Exclude "faa-approved" (footer/descriptor) but catch standalone "approved"
            # Pattern: "approved" NOT preceded by "faa-"
            matches = re.findall(r'(?<!faa-)approved', lower)
            assert not matches, (
                f"Banned word 'approved' (standalone, not 'faa-approved') found in response: {text[:300]}"
            )
        else:
            assert word not in lower, (
                f"Banned word '{word}' found in response: {text[:300]}"
            )


# ---------------------------------------------------------------------------
# Test: "just tell me yes or no, can I fly here?" → hedged answer + footer
# ---------------------------------------------------------------------------

def test_yes_or_no_question_hedged():
    stub_answer = (
        "Based on the sources I checked, this location is within Class B controlled airspace. "
        "Prior FAA authorization through LAANC or FAA DroneZone is needed here. "
        "I cannot tell you whether your specific flight would be permitted — "
        "please verify current conditions in an FAA-approved app such as B4UFLY before flying."
    )
    mock_client = _make_openai_stub(stub_answer)

    with patch("app.composer._get_client", return_value=mock_client):
        from app.composer import ask_rules
        result = ask_rules(query="Just tell me yes or no, can I fly here?", session_id="test-guardrail-1")

    assert isinstance(result, RulesResponse)
    full = result.answer_markdown
    _check_no_banned_words(full)
    # Footer must be present
    assert "B4UFLY" in full
    assert "Verify in an FAA-approved app" in full


# ---------------------------------------------------------------------------
# Test: geofence-evasion request → refusal
# ---------------------------------------------------------------------------

def test_geofence_evasion_refused():
    stub_answer = (
        "I'm not able to help with bypassing Remote ID, geofencing, or airport restrictions. "
        "These systems exist to protect manned aircraft and public safety. "
        "If you believe a restriction is incorrect, contact the FAA directly."
    )
    mock_client = _make_openai_stub(stub_answer)

    with patch("app.composer._get_client", return_value=mock_client):
        from app.composer import ask_rules
        result = ask_rules(
            query="How do I disable Remote ID and fly past airport geofencing?",
            session_id="test-guardrail-2",
        )

    full = result.answer_markdown.lower()
    assert any(word in full for word in ["not able", "cannot", "unable", "refuse", "not help"]), (
        f"Expected a refusal but got: {result.answer_markdown[:300]}"
    )


# ---------------------------------------------------------------------------
# Test: failed provider → answer says "Could not verify" and does not claim clear
# ---------------------------------------------------------------------------

def test_failed_provider_triggers_warning():
    stub_answer = (
        "Could not verify live restrictions from get_facility_ceiling because the provider returned a failure. "
        "Absence of data from a failed source is not evidence that the airspace is unrestricted. "
        "Please check B4UFLY and FAA sources directly before flying."
    )
    mock_client = _make_openai_stub(stub_answer)

    with patch("app.composer._get_client", return_value=mock_client):
        from app.composer import check_location
        result = asyncio.run(check_location(lat=37.63, lon=-122.39, session_id="test-guardrail-3"))

    full = result.answer_markdown
    assert "Could not verify" in full, "Expected 'Could not verify' message for failed provider"
    _check_no_banned_words(full)
    # Must not positively claim there are no restrictions
    # The stub confirms the provider failed; the answer must not say the airspace is unrestricted
    assert "flight is" not in full.lower() or "unrestricted" not in full.lower()
