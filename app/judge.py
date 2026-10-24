"""
app/judge.py — answer reviewer: an LLM-as-judge that checks Skye's answer against the
sources the agent actually used, run after every answer.

review_answer(answer, rule_chunks, tool_outputs) -> AnswerReview

The judge model only proposes. Python decides what counts as verified, and fails closed:

- A source is "verified" only if it was actually retrieved or called (status ok or stale),
  the judge checked at least one claim against it, and every one of those claims was
  judged consistent with a quote that really appears in the source text.
- A claim the judge marks consistent without a quote found in that source is downgraded
  to "unverified".
- A cited rule ID that was never retrieved is flagged as not retrieved, whatever the
  judge says. The answer is scanned for these with a pattern match as well, so this
  check works even if the judge misses the citation.
- Failed tools are never verified. If the judge call fails or returns malformed output,
  nothing is verified.

Overall verdict: "verified" (all checks passed and at least one source verified),
"issues" (a citation was not retrieved, or a claim is inconsistent or unsupported),
"unverified" (the review could not be completed or nothing could be checked).
"""
from __future__ import annotations

import datetime as dt
import json
import logging
import re
from typing import Any, Literal, Optional

from openai import AsyncOpenAI, OpenAI
from pydantic import BaseModel, Field

from app.config import settings
from app.providers.base import BaseResult

log = logging.getLogger("skye.judge")

MAX_SOURCE_CHARS = 8000
MAX_ISSUES_SHOWN = 5

# Study-guide rule IDs (sg-3a-wind-1) and explicit "rule_id: X" citations
_RULE_ID_PATTERNS = [
    re.compile(r"\bsg-[a-z0-9]+(?:-[a-z0-9]+)+\b", re.IGNORECASE),
    re.compile(r"rule[_ ]id\s*[:=]\s*[`\"']?([\w.-]+)", re.IGNORECASE),
]


# ---------------------------------------------------------------------------
# Result models
# ---------------------------------------------------------------------------

ClaimStatus = Literal["verified", "inconsistent", "unsupported", "unverified", "not_retrieved"]
SourceStatus = Literal["verified", "inconsistent", "unverified", "unused", "failed"]


class ClaimCheck(BaseModel):
    claim: str
    source_id: Optional[str] = None        # source it was checked against
    cited_as: Optional[str] = None         # how the answer cited it, if it did
    status: ClaimStatus
    evidence: Optional[str] = None         # quote found in the source (verified claims only)
    reason: Optional[str] = None


class SourceCheck(BaseModel):
    source_id: str
    kind: Literal["rule", "tool"]
    label: str
    status: SourceStatus
    claims_checked: int = 0


class AnswerReview(BaseModel):
    verdict: Literal["verified", "issues", "unverified"]
    checked_at: dt.datetime
    sources: list[SourceCheck] = Field(default_factory=list)
    claims: list[ClaimCheck] = Field(default_factory=list)
    issues: list[str] = Field(default_factory=list)
    error: Optional[str] = None


# ---------------------------------------------------------------------------
# Sources
# ---------------------------------------------------------------------------

class _Source:
    def __init__(self, source_id: str, kind: str, label: str, content: str, usable: bool):
        self.source_id = source_id
        self.kind = kind
        self.label = label
        self.content = content
        self.usable = usable                 # False for failed tools: never verifiable
        self.norm = _normalize(content)


def _normalize(text: str) -> str:
    return " ".join(re.sub(r"[^a-z0-9.]+", " ", text.lower()).split())


def _tool_json(result: Any) -> str:
    if isinstance(result, BaseResult):
        return result.model_dump_json()
    return json.dumps(result, default=str)


def _tool_status(result: Any) -> str:
    if isinstance(result, BaseResult):
        return result.status
    if isinstance(result, dict):
        return str(result.get("status", "ok"))
    return "ok"


def _build_sources(rule_chunks: list[dict[str, Any]], tool_outputs: list[tuple[str, Any]]) -> list[_Source]:
    sources: list[_Source] = []
    seen_rules: set[str] = set()
    for chunk in rule_chunks:
        rid = chunk.get("rule_id", "")
        if not rid or rid in seen_rules:
            continue
        seen_rules.add(rid)
        citation = (chunk.get("metadata") or {}).get("citation", "")
        sources.append(_Source(rid, "rule", citation or rid, chunk.get("text", ""), usable=True))

    by_tool: dict[str, list[Any]] = {}
    for name, result in tool_outputs:
        if name != "search_rules":
            by_tool.setdefault(name, []).append(result)
    for name, results in by_tool.items():
        content = "\n".join(_tool_json(r) for r in results)[:MAX_SOURCE_CHARS]
        usable = any(_tool_status(r) in ("ok", "stale") for r in results)
        sources.append(_Source(name, "tool", name, content, usable=usable))
    return sources


def _match_source(ref: Optional[str], sources: list[_Source]) -> Optional[_Source]:
    if not ref:
        return None
    key = ref.strip().strip("`\"'()[]").lower()
    for s in sources:
        if key == s.source_id.lower():
            return s
    for s in sources:                         # e.g. "get_weather (checked_at …)"
        if s.source_id.lower() in key:
            return s
    for s in sources:                         # e.g. "FAA-G-8082-22, Chapter 3"
        if s.kind == "rule" and len(key) >= 6 and (key in s.label.lower() or s.label.lower() in key):
            return s
    return None


def _cited_rule_ids(answer: str) -> set[str]:
    found: set[str] = set()
    for pattern in _RULE_ID_PATTERNS:
        for m in pattern.finditer(answer):
            found.add((m.group(1) if m.groups() else m.group(0)).strip(".,;:").lower())
    return found


# ---------------------------------------------------------------------------
# Judge call
# ---------------------------------------------------------------------------

_JUDGE_PROMPT = """You review a drone flight assistant's answer against the sources it was given. \
You do not rewrite the answer. You check it.

Break the answer into atomic factual claims: statements about rules, airspace, restrictions, \
weather readings or other data. Skip greetings, questions to the user, and generic advice \
such as "check B4UFLY before flying".

For each claim:
- cited_as: the source the answer itself cites for it, copied exactly as written \
(a rule_id, citation text or tool name), or null if the answer cites nothing for it.
- source_id: the id from the SOURCES list that you checked the claim against, or null if \
no source addresses it. Only use ids from the list.
- verdict:
    "consistent": the source states it or directly implies it
    "inconsistent": the source says something incompatible with it
    "unsupported": no listed source addresses it
- evidence: for "consistent" and "inconsistent", a short passage copied VERBATIM from that \
source's content. For JSON tool output, copy the key and value, e.g. "gusts_mph": 17.2. \
Never paraphrase the evidence. If you cannot quote the source, the verdict is "unsupported".
- reason: one short sentence.

Judge only from the SOURCES content, never from your own knowledge.

Return JSON:
{"claims": [{"claim": "...", "cited_as": "..." | null, "source_id": "..." | null, \
"verdict": "consistent" | "inconsistent" | "unsupported", "evidence": "..." | null, "reason": "..."}]}"""


_client: Optional[OpenAI] = None
_async_client: Optional[AsyncOpenAI] = None


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(api_key=settings.OPENAI_API_KEY)
    return _client


def _get_async_client() -> AsyncOpenAI:
    global _async_client
    if _async_client is None:
        _async_client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
    return _async_client


def _judge_request(answer: str, sources: list[_Source]) -> dict[str, Any]:
    payload = {
        "answer": answer,
        "sources": [{"id": s.source_id, "kind": s.kind, "label": s.label, "content": s.content}
                    for s in sources],
    }
    return {
        "model": settings.REVIEW_MODEL or settings.OPENAI_MODEL,
        "temperature": 0,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": _JUDGE_PROMPT},
            {"role": "user", "content": json.dumps(payload, indent=1)},
        ],
    }


# ---------------------------------------------------------------------------
# Deciding what is verified (code, not the model)
# ---------------------------------------------------------------------------

def _decide(answer: str, sources: list[_Source], raw_claims: Any, error: Optional[str]) -> AnswerReview:
    now = dt.datetime.now(dt.timezone.utc)
    claims: list[ClaimCheck] = []
    issues: list[str] = []
    source_ids = {s.source_id.lower() for s in sources if s.kind == "rule"}

    # Rule IDs cited in the answer that were never retrieved; independent of the judge
    missing_ids = sorted(_cited_rule_ids(answer) - source_ids)
    for rid in missing_ids:
        issues.append(f'The answer cites "{rid}", which was not among the retrieved rule excerpts.')

    if error is None and not isinstance(raw_claims, list):
        error = "Reviewer returned malformed output."

    for raw in raw_claims if error is None else []:
        if not isinstance(raw, dict) or not raw.get("claim"):
            continue
        text = str(raw["claim"])
        cited_as = raw.get("cited_as") or None
        verdict = raw.get("verdict")
        evidence = raw.get("evidence") or None
        reason = raw.get("reason") or None
        source = _match_source(raw.get("source_id"), sources)
        cited = _match_source(cited_as, sources)

        if cited_as and cited is None and _looks_like_rule_id(cited_as, sources):
            status: ClaimStatus = "not_retrieved"
            reason = f'cites "{cited_as}", which was not retrieved'
        elif verdict == "inconsistent" and source is not None and _quote_in(evidence, source):
            status = "inconsistent"
        elif verdict == "consistent" and source is not None and source.usable and _quote_in(evidence, source):
            status = "verified"
        elif verdict == "consistent" and source is not None and not source.usable:
            status = "unverified"
            reason = f"{source.source_id} failed, so it cannot confirm anything"
        elif verdict == "unsupported" or source is None:
            status = "unsupported"
        else:
            status = "unverified"
            reason = "the reviewer's quote was not found in the source"

        claims.append(ClaimCheck(
            claim=text, source_id=source.source_id if source else None, cited_as=cited_as,
            status=status, evidence=evidence if status in ("verified", "inconsistent") else None,
            reason=reason,
        ))

    for c in claims:
        if c.status == "not_retrieved":
            if not any(rid in (c.cited_as or "").lower() for rid in missing_ids):
                issues.append(f'"{_short(c.claim)}" cites "{c.cited_as}", which was not retrieved.')
        elif c.status == "inconsistent":
            issues.append(f'"{_short(c.claim)}" conflicts with {c.source_id}.')
        elif c.status == "unsupported":
            issues.append(f'"{_short(c.claim)}" is not supported by any source checked.')

    checks: list[SourceCheck] = []
    for s in sources:
        mine = [c for c in claims if c.source_id == s.source_id]
        if not s.usable:
            st: SourceStatus = "failed"
        elif not mine:
            st = "unused"
        elif any(c.status == "inconsistent" for c in mine):
            st = "inconsistent"
        elif all(c.status == "verified" for c in mine):
            st = "verified"
        else:
            st = "unverified"
        checks.append(SourceCheck(source_id=s.source_id, kind=s.kind, label=s.label,
                                  status=st, claims_checked=len(mine)))

    if error is not None:
        verdict_out = "issues" if issues else "unverified"
    elif issues:
        verdict_out = "issues"
    elif any(c.status == "verified" for c in checks) and all(c.status == "verified" for c in claims):
        verdict_out = "verified"
    else:
        verdict_out = "unverified"

    return AnswerReview(verdict=verdict_out, checked_at=now, sources=checks, claims=claims,
                        issues=issues, error=error)


def _quote_in(evidence: Optional[str], source: _Source) -> bool:
    quote = _normalize(evidence or "")
    return len(quote) >= 3 and quote in source.norm


def _looks_like_rule_id(ref: str, sources: list[_Source]) -> bool:
    """A citation that names a rule chunk (not a tool or the study guide title)."""
    ref = ref.strip().lower()
    if any(s.kind == "tool" and s.source_id in ref for s in sources):
        return False
    return bool(_cited_rule_ids(ref) or "rule" in ref or re.fullmatch(r"[a-z0-9]+(?:_[a-z0-9]+)+", ref))


def _short(text: str, n: int = 90) -> str:
    return text if len(text) <= n else text[: n - 1] + "…"


# ---------------------------------------------------------------------------
# Public entry points
# ---------------------------------------------------------------------------

def _parse(content: Optional[str]) -> tuple[Any, Optional[str]]:
    try:
        return json.loads(content or "").get("claims"), None
    except (json.JSONDecodeError, AttributeError) as exc:
        return None, f"Reviewer returned malformed output: {exc}"


def review_answer(answer: str, rule_chunks: list[dict[str, Any]],
                  tool_outputs: list[tuple[str, Any]]) -> AnswerReview:
    sources = _build_sources(rule_chunks, tool_outputs)
    try:
        resp = _get_client().chat.completions.create(**_judge_request(answer, sources))
        raw, error = _parse(resp.choices[0].message.content)
    except Exception as exc:
        log.warning("answer review failed: %s", exc)
        raw, error = None, f"Reviewer unavailable: {exc}"
    return _decide(answer, sources, raw, error)


async def review_answer_async(answer: str, rule_chunks: list[dict[str, Any]],
                              tool_outputs: list[tuple[str, Any]]) -> AnswerReview:
    sources = _build_sources(rule_chunks, tool_outputs)
    try:
        resp = await _get_async_client().chat.completions.create(**_judge_request(answer, sources))
        raw, error = _parse(resp.choices[0].message.content)
    except Exception as exc:
        log.warning("answer review failed: %s", exc)
        raw, error = None, f"Reviewer unavailable: {exc}"
    return _decide(answer, sources, raw, error)


def review_markdown(review: AnswerReview) -> str:
    """Short section appended to the answer so the user sees the result."""
    lines = ["\n\n---", "**Answer review** (automated check of this answer against its sources):"]
    verified = [s.label if s.kind == "tool" else s.source_id for s in review.sources if s.status == "verified"]
    if review.verdict == "verified":
        lines.append(f"- ✅ Claims checked against: {', '.join(verified)}.")
    elif review.error and not review.issues:
        lines.append("- ⚠️ The review could not be completed, so no sources were verified.")
    else:
        if verified:
            lines.append(f"- Checked against: {', '.join(verified)}.")
        for issue in review.issues[:MAX_ISSUES_SHOWN]:
            lines.append(f"- ⚠️ {issue}")
        if len(review.issues) > MAX_ISSUES_SHOWN:
            lines.append(f"- ⚠️ {len(review.issues) - MAX_ISSUES_SHOWN} more issue(s) found.")
        if not review.issues:
            lines.append("- ⚠️ Some claims could not be matched to a source, so they are unverified.")
    failed = [s.label for s in review.sources if s.status == "failed"]
    if failed:
        lines.append(f"- ⚠️ Not verified because the lookup failed: {', '.join(failed)}.")
    return "\n".join(lines)
