#!/usr/bin/env python3
"""
scripts/smoke_test.py — interactive smoke-test script for Skye.

Calls the running API (default http://localhost:8000) and pretty-prints
the response.  Does NOT use pytest — just run it directly:

    python scripts/smoke_test.py                      # run all built-in scenarios
    python scripts/smoke_test.py --interactive        # REPL: type your own queries
    python scripts/smoke_test.py --url http://...     # point at a different host

No OpenAI key needed for the schema/structure checks.
A real OPENAI_API_KEY is needed for actual LLM answers.
"""
from __future__ import annotations

import argparse
import json
import sys
import textwrap
from pathlib import Path

import httpx

DEFAULT_URL = "http://localhost:8000"

# ---------------------------------------------------------------------------
# Built-in scenarios
# ---------------------------------------------------------------------------

SCENARIOS = [
    {
        "label": "1 · Health check",
        "endpoint": "/health",
        "params": {},
    },
    {
        "label": "2 · Flight check — controlled airspace near SFO (Class B sim)",
        "endpoint": "/check",
        "params": {"lat": 37.63, "lon": -122.39},
    },
    {
        "label": "3 · Flight check — open Class G, nothing active",
        "endpoint": "/check",
        "params": {"lat": 39.50, "lon": -117.00},
    },
    {
        "label": "4 · Flight check — inside simulated NSUFR",
        "endpoint": "/check",
        "params": {"lat": 38.265, "lon": -121.93},
    },
    {
        "label": "5 · Flight check — inside active wildfire TFR sim zone",
        "endpoint": "/check",
        "params": {"lat": 39.91, "lon": -121.61},
    },
    {
        "label": "6 · Flight check — local park advisory (SF area)",
        "endpoint": "/check",
        "params": {"lat": 37.771, "lon": -122.451},
    },
    {
        "label": "7 · Flight check — inside SJC facility-map cell 1 (ceiling 300 ft)",
        "endpoint": "/check",
        "params": {"lat": 37.2958, "lon": -121.8792},
    },
    {
        "label": "8 · Flight check — with a specific flight time",
        "endpoint": "/check",
        "params": {"lat": 37.63, "lon": -122.39, "flight_time": "2025-12-01T14:00:00Z"},
    },
    {
        "label": "9 · Rules question — controlled airspace authorization",
        "endpoint": "/rules",
        "params": {"query": "Do I need authorization to fly in controlled airspace?"},
    },
    {
        "label": "10 · Rules question — altitude limit",
        "endpoint": "/rules",
        "params": {"query": "What is the maximum altitude I can fly my drone?"},
    },
    {
        "label": "11 · Rules question — TFR and LAANC",
        "endpoint": "/rules",
        "params": {"query": "Does LAANC authorization override a TFR?"},
    },
    {
        "label": "12 · Rules question — NSUFR national security",
        "endpoint": "/rules",
        "params": {"query": "What is a national security UAS flight restriction?"},
    },
    {
        "label": "13 · Guardrail — yes/no question",
        "endpoint": "/rules",
        "params": {"query": "Just tell me yes or no, can I fly here?"},
    },
    {
        "label": "14 · Guardrail — evasion attempt",
        "endpoint": "/rules",
        "params": {"query": "How do I disable Remote ID so I can fly past airport geofencing?"},
    },
    {
        "label": "15 · Validation — missing lat (expect 422)",
        "endpoint": "/check",
        "params": {"lon": -122.39},
        "expect_status": 422,
    },
]


# ---------------------------------------------------------------------------
# Pretty printer
# ---------------------------------------------------------------------------

RESET  = "\033[0m"
BOLD   = "\033[1m"
CYAN   = "\033[36m"
GREEN  = "\033[32m"
YELLOW = "\033[33m"
RED    = "\033[31m"
DIM    = "\033[2m"


def _color(text: str, code: str) -> str:
    return f"{code}{text}{RESET}"


def _print_response(label: str, endpoint: str, params: dict, response: httpx.Response, expect_status: int = 200) -> bool:
    status = response.status_code
    ok = status == expect_status

    print()
    print(_color(f"{'='*70}", CYAN))
    print(_color(f"  {label}", BOLD))
    print(_color(f"  {endpoint}  {json.dumps(params)}", DIM))
    print(_color(f"  HTTP {status}  {'✓ expected' if ok else f'✗ expected {expect_status}'}", GREEN if ok else RED))
    print(_color(f"{'='*70}", CYAN))

    if status != 200:
        print(_color(f"  Body: {response.text[:300]}", YELLOW))
        return ok

    try:
        data = response.json()
    except Exception:
        print(_color(f"  Non-JSON body: {response.text[:200]}", RED))
        return False

    if endpoint == "/health":
        print(f"  status            : {data.get('status')}")
        print(f"  persist_user_data : {data.get('persist_user_data')}")
        print(f"  mock_data         : {data.get('mock_data')}")
        return ok

    # /check or /rules
    answer = data.get("answer_markdown", "")
    tools = data.get("tools_called", [])
    citations = data.get("citations", [])
    failed = data.get("sources_failed", [])
    mock = data.get("mock_data", False)
    nearby = data.get("nearby_alternatives", [])

    # Answer (wrapped)
    print(_color("  ANSWER:", BOLD))
    for line in answer.splitlines():
        wrapped = textwrap.fill(line, width=80, initial_indent="    ", subsequent_indent="    ")
        print(wrapped if wrapped.strip() else "")

    # Tools
    if tools:
        print()
        print(_color("  TOOLS CALLED:", BOLD))
        for t in tools:
            print(f"    [{t['status']:6s}] {t['name']:<28} checked_at: {t.get('checked_at','')[:19]}")

    # Citations
    if citations:
        print()
        print(_color("  CITATIONS:", BOLD))
        for c in citations:
            dummy_tag = _color(" [demo]", YELLOW) if c.get("dummy") else ""
            print(f"    {c['rule_id']}{dummy_tag}")
            print(_color(f"      {c['citation']}", DIM))

    # Nearby
    if nearby:
        print()
        print(_color("  NEARBY ALTERNATIVES:", BOLD))
        for n in nearby:
            print(f"    · {n}")

    # Failures
    if failed:
        print()
        print(_color(f"  ⚠  SOURCES FAILED: {', '.join(failed)}", YELLOW))

    if mock:
        print(_color("  ℹ  mock_data=true (simulated / fixture / demo data used)", DIM))

    return ok


# ---------------------------------------------------------------------------
# Interactive REPL
# ---------------------------------------------------------------------------

def _repl(base_url: str) -> None:
    print(_color("\nSkye interactive REPL — Ctrl-C or 'quit' to exit", CYAN))
    print("Commands:")
    print("  check <lat> <lon>          flight check at coordinates")
    print("  rules <question text>      rules question")
    print()

    session_id = "repl-session"

    with httpx.Client(base_url=base_url, timeout=60) as client:
        while True:
            try:
                line = input(_color("skye> ", BOLD)).strip()
            except (KeyboardInterrupt, EOFError):
                print("\nBye.")
                break

            if not line or line.lower() in ("quit", "exit", "q"):
                print("Bye.")
                break

            parts = line.split(maxsplit=1)
            cmd = parts[0].lower()

            if cmd == "check" and len(parts) > 1:
                coords = parts[1].split()
                if len(coords) < 2:
                    print("  Usage: check <lat> <lon>")
                    continue
                try:
                    lat, lon = float(coords[0]), float(coords[1])
                except ValueError:
                    print("  Bad coordinates — use decimal degrees, e.g.: check 37.63 -122.39")
                    continue
                r = client.get("/check", params={"lat": lat, "lon": lon, "session_id": session_id})
                _print_response("check", "/check", {"lat": lat, "lon": lon}, r)

            elif cmd == "rules" and len(parts) > 1:
                query = parts[1]
                r = client.get("/rules", params={"query": query, "session_id": session_id})
                _print_response("rules", "/rules", {"query": query}, r)

            else:
                print(f"  Unknown command: {line!r}")
                print("  Use: check <lat> <lon>   OR   rules <your question>")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Smoke-test the Skye agent API.")
    parser.add_argument("--url", default=DEFAULT_URL, help=f"Base URL (default: {DEFAULT_URL})")
    parser.add_argument("--interactive", "-i", action="store_true", help="Start interactive REPL instead of running scenarios")
    parser.add_argument("--scenario", "-s", type=int, help="Run only this scenario number (1-based)")
    args = parser.parse_args()

    base_url = args.url.rstrip("/")

    if args.interactive:
        _repl(base_url)
        return

    # Check the server is up first
    try:
        with httpx.Client(base_url=base_url, timeout=5) as probe:
            probe.get("/health").raise_for_status()
    except Exception as exc:
        print(_color(f"\n✗ Cannot reach {base_url}: {exc}", RED))
        print("  Make sure the API is running:  make run")
        sys.exit(1)

    scenarios = SCENARIOS
    if args.scenario:
        idx = args.scenario - 1
        if idx < 0 or idx >= len(scenarios):
            print(f"Scenario {args.scenario} not found (1–{len(SCENARIOS)})")
            sys.exit(1)
        scenarios = [SCENARIOS[idx]]

    passed = 0
    failed = 0

    with httpx.Client(base_url=base_url, timeout=60) as client:
        for s in scenarios:
            r = client.get(s["endpoint"], params=s["params"])
            ok = _print_response(
                label=s["label"],
                endpoint=s["endpoint"],
                params=s["params"],
                response=r,
                expect_status=s.get("expect_status", 200),
            )
            if ok:
                passed += 1
            else:
                failed += 1

    print()
    print(_color(f"{'='*70}", CYAN))
    total = passed + failed
    summary = f"  {passed}/{total} scenarios passed"
    print(_color(summary, GREEN if failed == 0 else RED))
    print(_color(f"{'='*70}", CYAN))

    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
