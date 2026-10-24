"""
tests/eval/test_rules_eval.py — score the rules feature (/rules, /rules/stream) on 25 questions.

Each question in datasets/rules_questions.json names the study-guide chunks a correct answer
should come from (reference_ids) and the key facts it should convey. Questions alternate
between the plain and streamed endpoints so both agent entry points are scored.

Per question:
    retrieval_recall   share of reference chunks the agent retrieved with search_rules
    faithfulness       share of the answer's factual claims supported by the retrieved chunks (judge)
    coverage           share of key facts from the reference articles the answer conveys (judge)
    alignment          1-5, how well the answer resonates with the reference articles (judge)
    relevance          1-5, how directly it answers the question (judge)

Run: RUN_LLM_EVALS=1 pytest tests/eval/test_rules_eval.py -s   (or `make eval`)
Report: tests/eval/reports/rules_eval.json
"""
from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from statistics import mean

import pytest

from app.config import settings
from app.rules.study_guide import load_chunks
from tests.eval import judge
from tests.eval.conftest import write_report
from tests.eval.judge import requires_llm

CASES = json.loads((Path(__file__).parent / "datasets" / "rules_questions.json").read_text())
CHUNKS = {c["rule_id"]: c for c in load_chunks(settings.RULES_CORPUS_DIR)}
ENDPOINTS = ["/rules", "/rules/stream"]

CASE_MIN_FAITHFULNESS = 0.6
MIN_MEAN_FAITHFULNESS = 0.85
MIN_MEAN_COVERAGE = 0.6
MIN_MEAN_ALIGNMENT = 3.5
MIN_RETRIEVAL_HIT_RATE = 0.8

RESULTS: dict[str, dict] = {}


def test_dataset_is_well_formed():
    assert len(CASES) == 25
    assert len({c["id"] for c in CASES}) == len(CASES)
    for case in CASES:
        missing = [i for i in case["reference_ids"] if i not in CHUNKS]
        assert not missing, f"{case['id']}: reference chunks not in corpus: {missing}"
        assert case["key_facts"], f"{case['id']}: no key facts"


@requires_llm
@pytest.mark.parametrize("index", range(len(CASES)), ids=[c["id"] for c in CASES])
def test_rules_question(agent, index):
    case = CASES[index]
    endpoint = ENDPOINTS[index % len(ENDPOINTS)]
    run = agent.rules(case["question"], endpoint)
    references = [CHUNKS[i] for i in case["reference_ids"]]

    with ThreadPoolExecutor(2) as pool:
        faith_job = pool.submit(judge.faithfulness, run.answer, run.unique_retrieved)
        align_job = pool.submit(judge.reference_alignment, case["question"], run.answer,
                                references, case["key_facts"])
        faith, align = faith_job.result(), align_job.result()

    hits = sorted(set(case["reference_ids"]) & run.retrieved_ids)
    RESULTS[case["id"]] = {
        "id": case["id"],
        "endpoint": endpoint,
        "question": case["question"],
        "retrieved": sorted(run.retrieved_ids),
        "reference_hits": hits,
        "retrieval_recall": len(hits) / len(case["reference_ids"]),
        "faithfulness": faith.score,
        "claims": faith.claims,
        "coverage": align["coverage"],
        "key_facts": align.get("key_facts", []),
        "alignment": align.get("alignment"),
        "relevance": align.get("relevance"),
        "conflicts": align.get("conflicts", []),
        "rationale": align.get("rationale"),
        "cites_study_guide": judge.cites_study_guide(run.answer),
        "answer": run.answer,
    }

    assert run.retrieved, "agent answered without calling search_rules"
    if run.streamed_text is not None:
        assert run.streamed_text == run.response["answer_markdown"], \
            "streamed tokens do not add up to the final answer"
    assert not faith.contradicted, f"answer contradicts its retrieved chunks: {faith.contradicted}"
    assert faith.score >= CASE_MIN_FAITHFULNESS, (
        f"faithfulness {faith.score:.2f} < {CASE_MIN_FAITHFULNESS}; unsupported: {faith.unsupported}")


@requires_llm
def test_rules_aggregate():
    missing = [c["id"] for c in CASES if c["id"] not in RESULTS]
    assert not missing, f"no result recorded for: {missing}"
    rows = [RESULTS[c["id"]] for c in CASES]

    def summarize(subset):
        return {
            "n": len(subset),
            "faithfulness": round(mean(r["faithfulness"] for r in subset), 3),
            "coverage": round(mean(r["coverage"] for r in subset), 3),
            "alignment": round(mean(r["alignment"] or 0 for r in subset), 2),
            "relevance": round(mean(r["relevance"] or 0 for r in subset), 2),
            "retrieval_hit_rate": round(mean(bool(r["reference_hits"]) for r in subset), 3),
            "retrieval_recall": round(mean(r["retrieval_recall"] for r in subset), 3),
            "citation_rate": round(mean(r["cites_study_guide"] for r in subset), 3),
        }

    summary = {"judge_model": judge.JUDGE_MODEL, "agent_model": settings.OPENAI_MODEL,
               "overall": summarize(rows)}
    for ep in ENDPOINTS:
        summary[ep] = summarize([r for r in rows if r["endpoint"] == ep])
    path = write_report("rules_eval", summary, rows)

    print(f"\n\nRules eval ({len(rows)} questions) — report: {path}")
    print(f"{'id':32} {'endpoint':14} {'recall':>6} {'faith':>6} {'cover':>6} {'align':>5} {'rel':>4}")
    for r in rows:
        print(f"{r['id']:32} {r['endpoint']:14} {r['retrieval_recall']:6.2f} {r['faithfulness']:6.2f} "
              f"{r['coverage']:6.2f} {r['alignment'] or 0:5} {r['relevance'] or 0:4}")
    for key, value in summary.items():
        print(f"{key}: {value}")

    overall = summary["overall"]
    assert overall["faithfulness"] >= MIN_MEAN_FAITHFULNESS
    assert overall["coverage"] >= MIN_MEAN_COVERAGE
    assert overall["alignment"] >= MIN_MEAN_ALIGNMENT
    assert overall["retrieval_hit_rate"] >= MIN_RETRIEVAL_HIT_RATE
