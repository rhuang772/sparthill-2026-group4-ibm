"""
tests/eval/judge.py — LLM-as-judge scoring for the Skye agent evals.

    faithfulness(answer, context, scope)              claims in the answer vs the chunks it retrieved
    reference_alignment(question, answer, refs, facts) answer vs the reference articles and key facts
    airspace_consistency(answer, airspace, sources)    briefing vs the get_airspace result
    keyword_flags(answer)                              deterministic scan for misleading wording

The judge model defaults to OPENAI_MODEL; override with EVAL_JUDGE_MODEL.
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from typing import Any, Optional

import pytest
from openai import OpenAI

from app.config import settings

JUDGE_MODEL = os.environ.get("EVAL_JUDGE_MODEL") or settings.OPENAI_MODEL

requires_llm = pytest.mark.skipif(
    os.environ.get("RUN_LLM_EVALS") != "1" or not settings.OPENAI_API_KEY,
    reason="LLM evals call OpenAI: set RUN_LLM_EVALS=1 and OPENAI_API_KEY (or run `make eval`)",
)

_client: Optional[OpenAI] = None


def _judge(system: str, payload: dict[str, Any]) -> dict[str, Any]:
    global _client
    if _client is None:
        _client = OpenAI(api_key=settings.OPENAI_API_KEY)
    resp = _client.chat.completions.create(
        model=JUDGE_MODEL,
        temperature=0,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": json.dumps(payload, indent=2, default=str)},
        ],
    )
    return json.loads(resp.choices[0].message.content)


def _excerpts(chunks: list[dict[str, Any]]) -> list[dict[str, str]]:
    return [{"rule_id": c["rule_id"], "citation": c["metadata"].get("citation", ""), "text": c["text"]}
            for c in chunks]


# ---------------------------------------------------------------------------
# Faithfulness
# ---------------------------------------------------------------------------

_FAITHFULNESS_PROMPT = """You grade the faithfulness of a drone flight assistant's answer to the source excerpts it retrieved.

Break the answer into atomic claims and give each a type:
- "rule": a general statement about aviation rules, airspace, or weather (e.g. "Class D extends to 2,500 ft above the airport", "a TFR is issued by NOTAM")
- "location": a statement reporting this specific location's lookup results (the airspace class at the pin, the LAANC ceiling here, TFRs or NSUFRs found, weather readings, parks, people or water nearby, timestamps, which sources failed)
- "advice": a to-do item, checklist entry, recommendation, or disclaimer (e.g. "check B4UFLY", "verify Remote ID")

Judge each claim using ONLY the excerpts, not your own knowledge:
- "supported": the excerpts state it or directly imply it
- "contradicted": the excerpts say something incompatible with it
- "unsupported": the excerpts do not address it

Return JSON:
{"claims": [{"claim": "<claim>", "type": "rule" | "location" | "advice", "verdict": "supported" | "unsupported" | "contradicted", "evidence": "<rule_id or null>"}]}"""


@dataclass
class Faithfulness:
    score: float
    claims: list[dict[str, Any]] = field(default_factory=list)

    @property
    def contradicted(self) -> list[str]:
        return [c["claim"] for c in self.claims if c["verdict"] == "contradicted"]

    @property
    def unsupported(self) -> list[str]:
        return [c["claim"] for c in self.claims if c["verdict"] == "unsupported"]


def faithfulness(answer: str, context: list[dict[str, Any]]) -> Faithfulness:
    """Share of the answer's general rule claims supported by the retrieved excerpts.

    Location results and advice are excluded: they come from the location tools or the
    fixed checklist, not from the retrieved articles.
    """
    out = _judge(_FAITHFULNESS_PROMPT, {"answer": answer, "excerpts": _excerpts(context)})
    claims = [c for c in out.get("claims", []) if c.get("type", "rule") == "rule"]
    if not claims:
        return Faithfulness(1.0, [])
    supported = sum(c.get("verdict") == "supported" for c in claims)
    return Faithfulness(supported / len(claims), claims)


# ---------------------------------------------------------------------------
# Alignment with the reference articles
# ---------------------------------------------------------------------------

_REFERENCE_PROMPT = """You compare a drone flight assistant's answer with the reference article(s) a correct answer should be based on.

1. For each key fact, decide whether the answer conveys it. Paraphrase is fine; numbers and conditions must match.
2. "alignment" (1-5): how well the answer resonates with the reference articles.
   5 = conveys the core of the articles accurately, nothing conflicting; 3 = partial or vague; 1 = off-topic or conflicting.
3. "relevance" (1-5): how directly the answer addresses the question.
4. "conflicts": statements in the answer that conflict with the reference articles.

Return JSON:
{"key_facts": [{"fact": "<fact>", "covered": true | false}], "alignment": <int>, "relevance": <int>, "conflicts": ["<statement>"], "rationale": "<one or two sentences>"}"""


def reference_alignment(question: str, answer: str, references: list[dict[str, Any]],
                        key_facts: list[str]) -> dict[str, Any]:
    out = _judge(_REFERENCE_PROMPT, {
        "question": question,
        "reference_articles": _excerpts(references),
        "key_facts": key_facts,
        "answer": answer,
    })
    facts = out.get("key_facts", [])
    out["coverage"] = sum(bool(f.get("covered")) for f in facts) / len(key_facts) if key_facts else 1.0
    return out


# ---------------------------------------------------------------------------
# Airspace consistency (coordinates feature)
# ---------------------------------------------------------------------------

_AIRSPACE_PROMPT = """You audit a drone pre-flight briefing against the FAA airspace lookup (get_airspace) the assistant was given.

How to read the lookup:
- airspace_class is the only valid airspace class at the pin. null means it could not be confirmed: the briefing must say so, point to B4UFLY, and must not assume Class G.
- controlled true (Class B, C, D or E at the surface) means FAA authorization (LAANC or ATC) is needed. Class G needs no authorization below 400 ft AGL.
- If facility_map.in_grid is true, facility_map.ceiling_ft is the highest altitude LAANC can authorize there; 0 means no routine authorization in that cell.
- Every entry in notes should be relayed in substance.
- Mentioning overlying layers (e.g. Class E from 700 ft) is fine when clearly described as above the pin, not as the class at the surface.
- other_sources lists the other lookups and their status; reporting them is expected and is not a contradiction.

Evaluate:
- stated_airspace_class: the class the briefing says applies at the pin: "B", "C", "D", "E", "G", "unconfirmed", "not_stated" or "conflicting".
- class_consistent: the stated class matches airspace_class (or the briefing says it is unconfirmed when airspace_class is null).
- authorization_consistent: what it says about needing authorization (LAANC/ATC) matches the lookup.
- ceiling_consistent: the LAANC ceiling is reported correctly; null when facility_map.in_grid is false.
- notes: for each lookup note, whether it was relayed.
- contradictions: statements that conflict with the lookup.
- confusing_terms: words or phrases that could mislead or throw off a beginner, such as verdict wording that implies permission ("approved", "legal to fly", "safe", "clear to fly", "good to go"), wrong or mixed-up airspace classes, jargon or acronyms that are never explained, raw data field names or values (in_grid, ceiling_ft, null, none_found), or alarmist language. severity "high" = could lead the reader to a wrong decision (e.g. thinking no authorization is needed); "medium" = would confuse; "low" = stylistic.

Return JSON:
{"stated_airspace_class": "<class>", "class_consistent": true | false, "authorization_consistent": true | false, "ceiling_consistent": true | false | null, "notes": [{"note": "<note>", "relayed": true | false}], "contradictions": ["<statement>"], "confusing_terms": [{"term": "<term>", "why": "<reason>", "severity": "high" | "medium" | "low"}], "rationale": "<one or two sentences>"}"""


def airspace_consistency(answer: str, airspace: dict[str, Any], other_sources: dict[str, str]) -> dict[str, Any]:
    fm = airspace.get("facility_map") or {}
    lookup = {
        "airspace_class": airspace.get("airspace_class"),
        "controlled": airspace.get("controlled"),
        "status": airspace.get("status"),
        "notes": airspace.get("notes", []),
        "surface_layers": [layer["name"] for layer in (airspace.get("class_airspace") or {}).get("surface_layers", [])],
        "overlying_layers": [
            {"name": layer["name"], "class": layer["airspace_class"], "floor_ft": layer["floor_ft"], "floor_ref": layer["floor_ref"]}
            for layer in (airspace.get("class_airspace") or {}).get("overlying_layers", [])
        ],
        "facility_map": {k: fm.get(k) for k in ("in_grid", "ceiling_ft", "airport_name", "airport_icao", "airspace_class")},
    }
    out = _judge(_AIRSPACE_PROMPT, {"get_airspace": lookup, "other_sources": other_sources, "briefing": answer})
    notes = out.get("notes", [])
    out["notes_relayed"] = sum(bool(n.get("relayed")) for n in notes) / len(notes) if notes else 1.0
    checks = [out.get("class_consistent"), out.get("authorization_consistent"), out.get("ceiling_consistent")]
    checks = [bool(c) for c in checks if c is not None]
    out["consistency"] = sum(checks) / len(checks) if checks else 0.0
    return out


# ---------------------------------------------------------------------------
# Deterministic keyword scan
# ---------------------------------------------------------------------------

# The system prompt bans these words outright; any use is reported.
FORBIDDEN_WORDS = re.compile(r"\b(approved|legal to fly|safe|clear)\b", re.IGNORECASE)
# Wording that reads as a go/no-go verdict; any use fails the case.
VERDICT_PHRASES = re.compile(
    r"\b(approved|legal to fly|safe to fly|clear(ed)? to fly|clear for (flight|flying)|good to go|free to fly)\b",
    re.IGNORECASE,
)
# Raw tool fields or values leaking into prose.
RAW_DATA_TOKENS = re.compile(
    r"\b(airspace_class|in_grid|ceiling_ft|facility_map|surface_class|overlying_layers|time_status|"
    r"reaches_drone_altitudes|none_found|protected_area|prerun_\w+|null)\b"
)


def keyword_flags(answer: str) -> dict[str, list[str]]:
    return {
        "forbidden_words": sorted({m.group(0).lower() for m in FORBIDDEN_WORDS.finditer(answer)}),
        "verdict_phrases": sorted({m.group(0).lower() for m in VERDICT_PHRASES.finditer(answer)}),
        "raw_data_tokens": sorted({m.group(0) for m in RAW_DATA_TOKENS.finditer(answer)}),
    }


def cites_study_guide(answer: str) -> bool:
    return bool(re.search(r"FAA-G-8082-22|study guide|\bsg-\d", answer, re.IGNORECASE))
