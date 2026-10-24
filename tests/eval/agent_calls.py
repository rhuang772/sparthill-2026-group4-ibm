"""
tests/eval/agent_calls.py — call the real Skye agent through its HTTP endpoints.

Every agent entry point is reachable through one of four endpoints:
    /rules         -> composer.ask_rules
    /rules/stream  -> composer.ask_rules_stream
    /check         -> composer.check_location
    /check/stream  -> composer.check_location_stream

AgentClient wraps FastAPI's TestClient (so the app lifespan runs: HTTP clients, airspace
data and the Chroma store are set up exactly as in production) and records what the
agent saw during each call: every chunk returned by search_rules and the get_airspace
result handed to the model.
"""
from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from typing import Any, Iterable, Optional

FOOTER_MARKER = "\n\n---\n**Data sources checked:**"


@dataclass
class AgentRun:
    endpoint: str
    response: dict[str, Any]
    retrieved: list[dict[str, Any]]
    airspace: Optional[dict[str, Any]] = None
    events: list[tuple[str, dict[str, Any]]] = field(default_factory=list)
    streamed_text: Optional[str] = None

    @property
    def answer(self) -> str:
        """The model-written answer, without the hard-coded footer."""
        return self.response["answer_markdown"].split(FOOTER_MARKER)[0].strip()

    @property
    def retrieved_ids(self) -> set[str]:
        return {c["rule_id"] for c in self.retrieved}

    @property
    def unique_retrieved(self) -> list[dict[str, Any]]:
        seen: dict[str, dict[str, Any]] = {}
        for c in self.retrieved:
            seen.setdefault(c["rule_id"], c)
        return list(seen.values())


class Recorder:
    def __init__(self) -> None:
        self.retrieved: list[dict[str, Any]] = []
        self.airspace: Optional[dict[str, Any]] = None

    def reset(self) -> None:
        self.retrieved = []
        self.airspace = None


def parse_sse(lines: Iterable[str]) -> list[tuple[str, dict[str, Any]]]:
    events, name, data = [], None, []
    for line in lines:
        if line.startswith("event:"):
            name = line[len("event:"):].strip()
        elif line.startswith("data:"):
            data.append(line[len("data:"):].strip())
        elif not line and name:
            events.append((name, json.loads("\n".join(data))))
            name, data = None, []
    if name:
        events.append((name, json.loads("\n".join(data))))
    return events


def streamed_answer(events: list[tuple[str, dict[str, Any]]]) -> str:
    """What a client rendering the stream would show: tokens, cleared on each reset."""
    parts: list[str] = []
    for name, data in events:
        if name == "reset":
            parts.clear()
        elif name == "token":
            parts.append(data["text"])
    return "".join(parts)


class AgentClient:
    def __init__(self, client, recorder: Recorder) -> None:
        self._client = client
        self._rec = recorder

    def rules(self, query: str, endpoint: str = "/rules") -> AgentRun:
        return self._call(endpoint, {"query": query})

    def check(self, params: dict[str, Any], endpoint: str = "/check") -> AgentRun:
        return self._call(endpoint, params)

    def _call(self, path: str, params: dict[str, Any]) -> AgentRun:
        self._rec.reset()
        # A fresh session per call keeps repetition control from changing the answer.
        params = {**params, "session_id": f"eval-{uuid.uuid4().hex}"}

        if not path.endswith("/stream"):
            r = self._client.get(path, params=params)
            assert r.status_code == 200, f"{path} -> HTTP {r.status_code}: {r.text[:500]}"
            return AgentRun(path, r.json(), list(self._rec.retrieved), self._rec.airspace)

        with self._client.stream("GET", path, params=params) as r:
            assert r.status_code == 200, f"{path} -> HTTP {r.status_code}"
            events = parse_sse(r.iter_lines())
        errors = [d for e, d in events if e == "error"]
        assert not errors, f"{path} streamed an error event: {errors}"
        done = [d for e, d in events if e == "done"]
        assert len(done) == 1, f"{path} sent {len(done)} done events"
        return AgentRun(path, done[0], list(self._rec.retrieved), self._rec.airspace,
                        events, streamed_answer(events))
