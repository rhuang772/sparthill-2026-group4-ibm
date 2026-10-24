"""
tests/eval/test_coordinates_eval.py — score the coordinates feature (/check, /check/stream).

For each pin in datasets/coordinate_cases.json (Class B, C, D, G and an unconfirmed point,
using the downloaded FAA airspace data) the briefing is checked against the exact
get_airspace result the agent was given:

    consistency        judge: stated class, authorization and LAANC ceiling match get_airspace
    notes_relayed      judge: share of get_airspace.notes relayed
    confusing_terms    judge: wording that could throw off a beginner (high severity fails the case)
    keyword flags      regex: verdict phrases (fail), banned words and raw data fields (reported)
    faithfulness       judge, only when the agent retrieved or cited study-guide articles:
                       rule claims vs the retrieved chunks

Pins alternate between /check and /check/stream. The other providers (TFR, parks,
population, water, weather) run live, as in production.

Run: RUN_LLM_EVALS=1 pytest tests/eval/test_coordinates_eval.py -s   (or `make eval`)
Report: tests/eval/reports/coordinates_eval.json
"""
from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from statistics import mean

import pytest

from app.config import settings
from tests.eval import judge
from tests.eval.conftest import write_report
from tests.eval.judge import requires_llm

CASES = json.loads((Path(__file__).parent / "datasets" / "coordinate_cases.json").read_text())
ENDPOINTS = ["/check", "/check/stream"]

CASE_MIN_FAITHFULNESS = 0.6
MIN_MEAN_CONSISTENCY = 0.9
MIN_MEAN_NOTES_RELAYED = 0.6
MIN_MEAN_FAITHFULNESS = 0.8

RESULTS: dict[str, dict] = {}


@requires_llm
@pytest.mark.parametrize("index", range(len(CASES)), ids=[c["id"] for c in CASES])
def test_coordinate_briefing(agent, index):
    case = CASES[index]
    endpoint = ENDPOINTS[index % len(ENDPOINTS)]
    run = agent.check(case["params"], endpoint)

    assert run.airspace is not None, "get_airspace was not called"
    assert run.airspace["airspace_class"] == case["expected_class"], (
        f"airspace data changed: expected {case['expected_class']}, got {run.airspace['airspace_class']}")

    other_sources = {t["name"]: t["status"] for t in run.response["tools_called"] if t["name"] != "get_airspace"}
    uses_articles = bool(run.retrieved) or judge.cites_study_guide(run.answer)

    with ThreadPoolExecutor(2) as pool:
        air_job = pool.submit(judge.airspace_consistency, run.answer, run.airspace, other_sources)
        faith_job = pool.submit(judge.faithfulness, run.answer, run.unique_retrieved) if uses_articles else None
        air = air_job.result()
        faith = faith_job.result() if faith_job else None

    flags = judge.keyword_flags(run.answer)
    high = [t for t in air.get("confusing_terms", []) if t.get("severity") == "high"]
    RESULTS[case["id"]] = {
        "id": case["id"],
        "endpoint": endpoint,
        "description": case["description"],
        "expected_class": case["expected_class"],
        "stated_class": air.get("stated_airspace_class"),
        "class_consistent": air.get("class_consistent"),
        "authorization_consistent": air.get("authorization_consistent"),
        "ceiling_consistent": air.get("ceiling_consistent"),
        "consistency": air["consistency"],
        "notes_relayed": air["notes_relayed"],
        "notes": air.get("notes", []),
        "contradictions": air.get("contradictions", []),
        "confusing_terms": air.get("confusing_terms", []),
        "keyword_flags": flags,
        "uses_articles": uses_articles,
        "retrieved": sorted(run.retrieved_ids),
        "faithfulness": faith.score if faith else None,
        "claims": faith.claims if faith else [],
        "other_sources": other_sources,
        "rationale": air.get("rationale"),
        "answer": run.answer,
    }

    if run.streamed_text is not None:
        assert run.streamed_text == run.response["answer_markdown"], \
            "streamed tokens do not add up to the final answer"
    assert air.get("class_consistent"), (
        f"briefing says {air.get('stated_airspace_class')!r}, get_airspace says {case['expected_class']!r}: "
        f"{air.get('rationale')}")
    assert air.get("authorization_consistent"), f"authorization guidance is wrong: {air.get('rationale')}"
    assert not air.get("contradictions"), f"contradicts get_airspace: {air['contradictions']}"
    assert not flags["verdict_phrases"], f"verdict wording: {flags['verdict_phrases']}"
    assert not high, f"misleading wording: {high}"
    if faith:
        assert not faith.contradicted, f"contradicts retrieved articles: {faith.contradicted}"
        assert faith.score >= CASE_MIN_FAITHFULNESS, (
            f"faithfulness {faith.score:.2f} < {CASE_MIN_FAITHFULNESS}; unsupported: {faith.unsupported}")


@requires_llm
def test_coordinates_aggregate():
    missing = [c["id"] for c in CASES if c["id"] not in RESULTS]
    assert not missing, f"no result recorded for: {missing}"
    rows = [RESULTS[c["id"]] for c in CASES]
    faith_rows = [r["faithfulness"] for r in rows if r["faithfulness"] is not None]

    summary = {
        "judge_model": judge.JUDGE_MODEL,
        "agent_model": settings.OPENAI_MODEL,
        "n": len(rows),
        "consistency": round(mean(r["consistency"] for r in rows), 3),
        "class_accuracy": round(mean(bool(r["class_consistent"]) for r in rows), 3),
        "notes_relayed": round(mean(r["notes_relayed"] for r in rows), 3),
        "cases_using_articles": len(faith_rows),
        "faithfulness": round(mean(faith_rows), 3) if faith_rows else None,
        "confusing_terms": sum(len(r["confusing_terms"]) for r in rows),
        "forbidden_word_cases": sum(bool(r["keyword_flags"]["forbidden_words"]) for r in rows),
        "raw_data_token_cases": sum(bool(r["keyword_flags"]["raw_data_tokens"]) for r in rows),
    }
    path = write_report("coordinates_eval", summary, rows)

    print(f"\n\nCoordinates eval ({len(rows)} pins) — report: {path}")
    print(f"{'id':34} {'endpoint':14} {'want':>4} {'said':>11} {'cons':>5} {'notes':>5} {'faith':>5}  flags")
    for r in rows:
        faith = f"{r['faithfulness']:.2f}" if r["faithfulness"] is not None else "  -  "
        terms = [f"{t['term']} ({t['severity']})" for t in r["confusing_terms"]]
        words = r["keyword_flags"]["forbidden_words"] + r["keyword_flags"]["raw_data_tokens"]
        print(f"{r['id']:34} {r['endpoint']:14} {str(r['expected_class']):>4} {str(r['stated_class']):>11} "
              f"{r['consistency']:5.2f} {r['notes_relayed']:5.2f} {faith:>5}  {words + terms}")
    for key, value in summary.items():
        print(f"{key}: {value}")

    assert summary["consistency"] >= MIN_MEAN_CONSISTENCY
    assert summary["notes_relayed"] >= MIN_MEAN_NOTES_RELAYED
    if summary["faithfulness"] is not None:
        assert summary["faithfulness"] >= MIN_MEAN_FAITHFULNESS
