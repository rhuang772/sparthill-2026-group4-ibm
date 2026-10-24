"""
tests/test_chroma.py — study guide corpus parsing and the Chroma rules store.

The store is built in a temporary directory so the real .chroma/ is untouched.
Embeddings use Chroma's default local model (no network once it is cached).
"""
import re

import pytest

from app.config import settings
from app.rules import chroma_store
from app.rules.chroma_store import StudyGuideStore
from app.rules.study_guide import MAX_CHARS, SECTIONS, SOURCE_URL, corpus_fingerprint, load_chunks
from app.tools.chroma_tool import search_rules


@pytest.fixture(scope="module")
def chunks():
    return load_chunks(settings.RULES_CORPUS_DIR)


@pytest.fixture(scope="module")
def store(tmp_path_factory):
    s = StudyGuideStore(path=str(tmp_path_factory.mktemp("chroma")), collection="test_study_guide")
    s.ensure_seeded()
    return s


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

def test_every_section_with_text_produces_chunks(chunks):
    found = {(c["metadata"]["chapter"], c["metadata"]["section"]) for c in chunks}
    expected = {
        (name.removeprefix("chapter").removesuffix(".txt"), heading.rstrip("."))
        for name, sections in SECTIONS.items() for heading, _ in sections
    }
    # "Uncontrolled Airspace" is a heading directly followed by "Class G Airspace"
    assert expected - found == {("2", "Uncontrolled Airspace")}


def test_rule_ids_unique(chunks):
    ids = [c["rule_id"] for c in chunks]
    assert len(ids) == len(set(ids))


def test_chunks_fit_embedding_window(chunks):
    for c in chunks:
        body = c["text"].split("\n", 1)[1]
        assert 0 < len(body) <= MAX_CHARS, c["rule_id"]


def test_page_headers_and_captions_removed(chunks):
    for c in chunks:
        assert "Systems Study Guide" not in c["text"], c["rule_id"]
        assert not re.search(r"^Figure \d+-\d+\.", c["text"], re.M), c["rule_id"]
        assert "[Figure" not in c["text"], c["rule_id"]


def test_citation_and_pages(chunks):
    by_id = {c["rule_id"]: c for c in chunks}
    class_b = by_id["sg-2-class-b-airspace-1"]
    assert "authorization from ATC" in class_b["text"]
    assert class_b["metadata"]["page_start"] == 5
    assert "Chapter 2" in class_b["metadata"]["citation"]
    assert class_b["metadata"]["source_url"] == SOURCE_URL
    assert class_b["metadata"]["dummy"] is False
    assert by_id["sg-3b-visibility-1"]["metadata"]["page_end"] == 28


def test_fingerprint_changes_with_text(chunks):
    edited = [dict(chunks[0], text=chunks[0]["text"] + " edited")] + chunks[1:]
    assert corpus_fingerprint(edited) != corpus_fingerprint(chunks)


# ---------------------------------------------------------------------------
# Store
# ---------------------------------------------------------------------------

def test_store_holds_every_chunk(store, chunks):
    assert store.count() == len(chunks)


def test_ensure_seeded_is_idempotent(store, chunks):
    store.ensure_seeded()
    assert store.count() == len(chunks)


@pytest.mark.parametrize("query, tags, expected_section", [
    ("authorization to fly near the busiest airports", ["laanc"], "Class B Airspace"),
    ("do I need ATC authorization in uncontrolled airspace", ["uncontrolled_airspace"], "Class G Airspace"),
    ("what is class G airspace", [], "Class G Airspace"),
    ("temporary flight restriction purposes", ["tfr"], "Temporary Flight Restrictions (TFR)"),
    ("sudden change in wind speed and direction near the ground", ["wind"], "Low-Level Wind Shear"),
    ("frost on the drone before takeoff", [], "Dew and Frost"),
    ("how to read a METAR wind group", ["metar"], "Aviation Routine Weather Report (METAR)"),
])
def test_retrieval_finds_expected_section(store, query, tags, expected_section):
    results = store.query(query, tags=tags, k=4)
    assert expected_section in [r["metadata"]["section"] for r in results]


def test_tag_filter_only_returns_tagged_chunks(store):
    results = store.query("restrictions", tags=["thunderstorm"], k=10)
    assert results
    assert all("thunderstorm" in r["metadata"]["tags"] for r in results)


def test_unknown_tag_falls_back_to_unfiltered(store):
    assert len(store.query("airspace classes", tags=["no_such_tag"], k=3)) == 3


def test_k_cap(store):
    assert len(store.query("weather", k=3)) == 3


def test_no_coordinates_in_documents(store):
    coord = re.compile(r"\b\d{1,3}\.\d{4,}\b")  # e.g. 37.6213
    for chunk in store.query("airspace", k=store.count()):
        assert not coord.search(chunk["text"]), chunk["rule_id"]


def test_search_rules_tool_wrapper(store, monkeypatch):
    monkeypatch.setattr(chroma_store, "_store", store)
    results = search_rules("visibility and ceiling", tags=["visibility"], k=20)
    assert 1 <= len(results) <= 10
    assert {"rule_id", "text", "metadata", "distance"} <= set(results[0])
    assert results[0]["metadata"]["citation"]
