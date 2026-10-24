"""
app/repetition.py — in-process session state for repetition control.

Keyed by session_id (str).  All state is lost on restart — no persistence.
TTL for cached fact-bundles: 10 minutes (configurable via FACT_TTL_S).

Public API:
    get_context(session_id)  -> RepetitionContext
    record_answer(session_id, fact_hash, answer_summary, new_concepts)

RepetitionContext is injected into the system prompt to prevent:
  - Re-defining terms the user already knows
  - Re-stating the same fact set verbatim
"""
from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from typing import Optional

FACT_TTL_S = 600  # 10 minutes
MAX_SUMMARIES = 3

# Rotating pool of "new tip" seeds to vary repeated answers
_TIP_POOL = [
    "Remind the user to check B4UFLY before every flight, even if they checked recently.",
    "Suggest the user review the pre-flight checklist: battery, firmware, weather, NOTAM.",
    "Mention that Remote ID is now required for most drone operations.",
    "Note that local parks and land managers may have additional rules not covered here.",
    "Remind the user that TFRs can appear with little notice; always check on the day of flight.",
]


@dataclass
class _SessionState:
    concepts_explained: set[str] = field(default_factory=set)
    answer_summaries: list[str] = field(default_factory=list)   # last MAX_SUMMARIES
    last_fact_hash: Optional[str] = None
    last_fact_ts: float = 0.0
    flight_check_count: int = 0
    repeat_count: int = 0   # consecutive repeats of the same fact hash


@dataclass
class RepetitionContext:
    """Snapshot passed to the composer for prompt injection."""
    concepts_explained: set[str]
    last_summaries: list[str]
    is_repeat: bool
    repeat_count: int
    tip: Optional[str]   # only set on a repeat


# Module-level store (in-process only)
_store: dict[str, _SessionState] = {}


def _get_or_create(session_id: str) -> _SessionState:
    if session_id not in _store:
        _store[session_id] = _SessionState()
    return _store[session_id]


def get_context(session_id: str) -> RepetitionContext:
    state = _get_or_create(session_id)
    return RepetitionContext(
        concepts_explained=set(state.concepts_explained),
        last_summaries=list(state.answer_summaries),
        is_repeat=False,
        repeat_count=state.repeat_count,
        tip=None,
    )


def check_and_update(
    session_id: str,
    fact_hash: str,
) -> RepetitionContext:
    """Check whether this fact-hash is a repeat (within TTL) and return context."""
    state = _get_or_create(session_id)
    now = time.monotonic()

    is_repeat = (
        state.last_fact_hash == fact_hash
        and (now - state.last_fact_ts) < FACT_TTL_S
    )

    if is_repeat:
        state.repeat_count += 1
    else:
        state.repeat_count = 0

    tip: Optional[str] = None
    if is_repeat:
        tip = _TIP_POOL[state.repeat_count % len(_TIP_POOL)]

    return RepetitionContext(
        concepts_explained=set(state.concepts_explained),
        last_summaries=list(state.answer_summaries),
        is_repeat=is_repeat,
        repeat_count=state.repeat_count,
        tip=tip,
    )


def record_answer(
    session_id: str,
    fact_hash: str,
    answer_summary: str,
    new_concepts: list[str] | None = None,
) -> None:
    """Update session state after an answer is produced."""
    state = _get_or_create(session_id)
    now = time.monotonic()

    state.last_fact_hash = fact_hash
    state.last_fact_ts = now
    state.flight_check_count += 1

    # Rolling window of last MAX_SUMMARIES summaries
    state.answer_summaries.append(answer_summary)
    if len(state.answer_summaries) > MAX_SUMMARIES:
        state.answer_summaries.pop(0)

    # Accumulate concepts
    if new_concepts:
        state.concepts_explained.update(new_concepts)


def make_fact_hash(data: dict) -> str:
    """Stable hash of a dict of tool results for repeat-detection."""
    import json
    serialized = json.dumps(data, sort_keys=True, default=str)
    return hashlib.sha256(serialized.encode()).hexdigest()[:16]
