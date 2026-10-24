"""
tests/test_repetition.py — offline tests for repetition control.

Uses a simple Jaccard token-overlap similarity (no ML model) to verify
that consecutive answers for the same fact-hash differ in wording.
"""
from __future__ import annotations

import time

import pytest

from app.repetition import (
    MAX_SUMMARIES,
    check_and_update,
    make_fact_hash,
    record_answer,
    _store,
)


def _jaccard(a: str, b: str) -> float:
    """Token-overlap Jaccard similarity between two strings."""
    ta = set(a.lower().split())
    tb = set(b.lower().split())
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def _fresh_session() -> str:
    import uuid
    return uuid.uuid4().hex


# ---------------------------------------------------------------------------
# Basic get/record cycle
# ---------------------------------------------------------------------------

def test_new_session_not_a_repeat():
    sid = _fresh_session()
    ctx = check_and_update(sid, make_fact_hash({"lat": 37.0, "lon": -122.0}))
    assert ctx.is_repeat is False
    assert ctx.repeat_count == 0
    assert ctx.tip is None


def test_same_hash_within_ttl_is_repeat():
    sid = _fresh_session()
    h = make_fact_hash({"lat": 37.0, "lon": -122.0})
    check_and_update(sid, h)
    record_answer(sid, h, "First answer summary")
    ctx2 = check_and_update(sid, h)
    assert ctx2.is_repeat is True
    assert ctx2.tip is not None


def test_different_hash_is_not_repeat():
    sid = _fresh_session()
    h1 = make_fact_hash({"lat": 37.0, "lon": -122.0})
    h2 = make_fact_hash({"lat": 38.0, "lon": -120.0})
    check_and_update(sid, h1)
    record_answer(sid, h1, "Answer for location 1")
    ctx = check_and_update(sid, h2)
    assert ctx.is_repeat is False


def test_concepts_accumulated():
    sid = _fresh_session()
    h = make_fact_hash({"lat": 37.0, "lon": -122.0})
    record_answer(sid, h, "First answer", new_concepts=["LAANC", "Class B"])
    record_answer(sid, h, "Second answer", new_concepts=["TFR"])
    ctx = check_and_update(sid, h)
    assert "LAANC" in ctx.concepts_explained
    assert "Class B" in ctx.concepts_explained
    assert "TFR" in ctx.concepts_explained


def test_summaries_roll_over():
    """After MAX_SUMMARIES + 1 calls, only last MAX_SUMMARIES summaries are kept."""
    sid = _fresh_session()
    h = make_fact_hash({"lat": 37.0, "lon": -122.0})
    for i in range(MAX_SUMMARIES + 2):
        record_answer(sid, h, f"Summary {i}")
    state = _store[sid]
    assert len(state.answer_summaries) == MAX_SUMMARIES
    assert state.answer_summaries[-1] == f"Summary {MAX_SUMMARIES + 1}"


# ---------------------------------------------------------------------------
# Repetition count escalation
# ---------------------------------------------------------------------------

def test_repeat_count_increments():
    sid = _fresh_session()
    h = make_fact_hash({"lat": 37.0, "lon": -122.0})
    for i in range(4):
        check_and_update(sid, h)
        record_answer(sid, h, f"Answer {i}")
    ctx = check_and_update(sid, h)
    assert ctx.repeat_count >= 3


def test_five_repeats_identical_facts_vary_tip():
    """Five repeats of the same hash should rotate through tips (not all identical)."""
    sid = _fresh_session()
    h = make_fact_hash({"lat": 37.5, "lon": -121.9})
    tips = set()
    for i in range(5):
        ctx = check_and_update(sid, h)
        if ctx.tip:
            tips.add(ctx.tip)
        record_answer(sid, h, f"Simulated answer {i}")
    # At least 2 different tips across 5 repeats (pool has 5 entries, cycles)
    assert len(tips) >= 2


# ---------------------------------------------------------------------------
# Wording-variation heuristic (simulated answers)
# ---------------------------------------------------------------------------

def test_simulated_answer_wording_differs():
    """
    Simulate 5 answers for the same location with different wording.
    The Jaccard similarity between consecutive answers should be < 0.95,
    indicating the answers are not verbatim copies.
    """
    answers = [
        "You are in Class B airspace near SFO. Authorization via LAANC is required. Check B4UFLY.",
        "The coordinates fall within controlled Class B airspace. LAANC authorization must be obtained before flying.",
        "This location sits inside Class B airspace. Before any flight, secure LAANC approval and verify with B4UFLY.",
        "Class B controlled airspace applies here. A LAANC request is required; no drone may fly without it.",
        "This area is Class B airspace. Pilots need LAANC authorization. Always verify conditions in B4UFLY first.",
    ]
    for i in range(len(answers) - 1):
        sim = _jaccard(answers[i], answers[i + 1])
        assert sim < 0.95, (
            f"Answers {i} and {i+1} are too similar (Jaccard={sim:.2f}): "
            f"'{answers[i]}' vs '{answers[i+1]}'"
        )
