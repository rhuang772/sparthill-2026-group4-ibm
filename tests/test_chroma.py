"""
tests/test_chroma.py — offline tests for the Chroma rules store.
"""
import re

import pytest

from app.rules.chroma_dummy import DummyRulesStore
from app.tools.chroma_tool import search_rules


@pytest.fixture(scope="module")
def store():
    s = DummyRulesStore()
    s.ensure_seeded()
    return s


def test_collection_has_10_docs(store):
    assert store._col.count() == 10


def test_all_expected_rule_ids_present(store):
    expected = {
        "controlled-airspace-auth",
        "facility-map-ceiling",
        "altitude-400",
        "authorization-not-override",
        "prohibited-restricted",
        "nsufr-99-7",
        "weather-minimums",
        "yield-to-aircraft",
        "part-108-pending",
        "section-2209-pending",
    }
    results = store.query("drone rules", tags=[], k=10)
    found_ids = {r["rule_id"] for r in results}
    assert expected == found_ids


def test_tag_filtered_retrieval_laanc(store):
    results = store.query("controlled airspace authorization", tags=["laanc"], k=4)
    ids = [r["rule_id"] for r in results]
    assert "controlled-airspace-auth" in ids


def test_tag_filtered_retrieval_tfr(store):
    results = store.query("temporary flight restriction", tags=["tfr"], k=4)
    ids = [r["rule_id"] for r in results]
    assert "authorization-not-override" in ids


def test_tag_filtered_retrieval_altitude(store):
    results = store.query("altitude limit", tags=["altitude"], k=4)
    ids = [r["rule_id"] for r in results]
    assert "altitude-400" in ids


def test_tag_filtered_retrieval_nsufr(store):
    results = store.query("national security restriction", tags=["nsufr"], k=4)
    ids = [r["rule_id"] for r in results]
    assert "nsufr-99-7" in ids


def test_no_coordinates_in_documents(store):
    """Embedded rule texts must never contain lat/lon coordinate patterns."""
    results = store.query("authorization requirements", tags=[], k=10)
    coord_pattern = re.compile(r"\b\d{1,3}\.\d{4,}\b")  # e.g. 37.6213
    for chunk in results:
        text = chunk["text"]
        assert not coord_pattern.search(text), (
            f"Rule '{chunk['rule_id']}' contains what looks like a coordinate: "
            f"{coord_pattern.search(text).group()}"
        )


def test_dummy_flag_set(store):
    results = store.query("airspace", tags=[], k=10)
    for chunk in results:
        assert chunk["metadata"]["dummy"] is True


def test_search_rules_tool_wrapper(store):
    """The chroma_tool wrapper returns results in the same format."""
    results = search_rules("weather visibility minimums", tags=["weather"], k=2)
    assert isinstance(results, list)
    assert len(results) >= 1
    assert results[0]["rule_id"] == "weather-minimums"


def test_empty_query_returns_results(store):
    results = store.query("drone", k=4)
    assert len(results) >= 1


def test_k_cap(store):
    results = store.query("rules", k=3)
    assert len(results) <= 3
