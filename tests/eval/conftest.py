"""
tests/eval/conftest.py — fixtures for the LLM evals (real OpenAI calls, real providers).
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from tests.eval.agent_calls import AgentClient, Recorder

REPORTS_DIR = Path(__file__).parent / "reports"


@pytest.fixture(scope="session")
def agent():
    """AgentClient over the real app, recording search_rules and get_airspace results."""
    from fastapi.testclient import TestClient

    from app import composer
    from app.main import app

    recorder = Recorder()
    search_rules = composer.search_rules
    get_airspace = composer.faa_airspace.get_airspace

    def recording_search_rules(*args, **kwargs):
        result = search_rules(*args, **kwargs)
        recorder.retrieved.extend(result)
        return result

    def recording_get_airspace(*args, **kwargs):
        result = get_airspace(*args, **kwargs)
        recorder.airspace = result.model_dump(mode="json")
        return result

    with pytest.MonkeyPatch.context() as mp, TestClient(app) as client:
        mp.setattr(composer, "search_rules", recording_search_rules)
        mp.setattr(composer.faa_airspace, "get_airspace", recording_get_airspace)
        yield AgentClient(client, recorder)


def write_report(name: str, summary: dict[str, Any], rows: list[dict[str, Any]]) -> Path:
    REPORTS_DIR.mkdir(exist_ok=True)
    path = REPORTS_DIR / f"{name}.json"
    path.write_text(json.dumps({"summary": summary, "cases": rows}, indent=2, default=str))
    return path
