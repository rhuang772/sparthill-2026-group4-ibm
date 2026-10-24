"""
tests/conftest.py

Adds app/providers to sys.path so that tests/test_airhub_sim.py can use
    from airhub_sim import ...
without any modification to the original test file.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "app" / "providers"))


@pytest.fixture(autouse=True)
def no_answer_review(monkeypatch):
    """The answer reviewer calls OpenAI; tests that need it stub it and re-enable it."""
    from app.config import settings
    monkeypatch.setattr(settings, "ENABLE_ANSWER_REVIEW", False)


@pytest.fixture
def offline_providers(monkeypatch):
    """Stub the live TFR, park, population and water providers with failed results."""
    from app.providers import park, population, tfr, water
    from app.providers.base import ParkResult, PopulationResult, TFRResult, WaterResult

    def failing(model):
        async def fake(*args, **kwargs):
            return model(status="failed", error="offline test stub")
        return fake

    monkeypatch.setattr(tfr, "get_tfrs", failing(TFRResult))
    monkeypatch.setattr(park, "get_parks", failing(ParkResult))
    monkeypatch.setattr(population, "get_population_risk", failing(PopulationResult))
    monkeypatch.setattr(water, "get_water", failing(WaterResult))
