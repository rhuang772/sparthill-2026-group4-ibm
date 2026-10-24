"""
scripts/airspace_harness.py — replay a frontend map pin against the backend
and report the airspace type the backend returns (FAA Class Airspace + UAS Facility Map).

Sends the same request BriefingPage.tsx sends (GET /check?lat=&lon=...) through
FastAPI's TestClient. OpenAI is stubbed; the stub captures the pre-run tool
results the backend hands to the model, which is where the airspace class lives
(CheckResponse itself only carries the LLM-written markdown).

Usage:
    python scripts/airspace_harness.py                       # default pin: 37.3625, -121.9290
    python scripts/airspace_harness.py --lat 37.36 --lon -121.93
    python scripts/airspace_harness.py --live-faa            # query FAA ArcGIS instead of downloaded data
    python scripts/airspace_harness.py --expect C            # exit 1 unless the backend reports Class C
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

DEFAULT_LAT = 37.3625
DEFAULT_LON = -121.9290


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--lat", type=float, default=DEFAULT_LAT)
    p.add_argument("--lon", type=float, default=DEFAULT_LON)
    p.add_argument("--live-faa", action="store_true", help="Query the real FAA UAS Facility Map")
    p.add_argument("--expect", help="Expected airspace class (e.g. C); exit 1 on mismatch")
    return p.parse_args()


def _openai_stub(captured: list[list[dict]]) -> MagicMock:
    message = MagicMock()
    message.content = "stubbed answer"
    message.tool_calls = None
    message.model_dump.return_value = {"role": "assistant", "content": "stubbed answer"}
    choice = MagicMock(message=message, finish_reason="stop")

    def _create(**kwargs):
        captured.append(kwargs["messages"])
        return MagicMock(choices=[choice])

    client = MagicMock()
    client.chat.completions.create.side_effect = _create
    return client


def main() -> int:
    args = _parse_args()
    # Settings are read at import time, so flags must be set before importing app.
    os.environ["USE_LIVE_FAA"] = "true" if args.live_faa else "false"

    from fastapi.testclient import TestClient
    from app.main import app

    captured: list[list[dict]] = []
    params = {"lat": args.lat, "lon": args.lon}

    with TestClient(app) as client, patch("app.composer._get_client", return_value=_openai_stub(captured)):
        r = client.get("/check", params=params)

    print(f"GET /check?lat={args.lat}&lon={args.lon}  ->  HTTP {r.status_code}")
    if r.status_code != 200:
        print(r.text)
        return 1

    body = r.json()
    tool_results = {
        m["tool_call_id"].removeprefix("prerun_"): json.loads(m["content"])
        for m in captured[0]
        if m.get("role") == "tool"
    }

    air = tool_results.get("get_airspace", {})
    cls = air.get("class_airspace") or {}
    fac = air.get("facility_map") or {}
    mode = "live FAA ArcGIS" if args.live_faa else "downloaded GeoJSON"

    def _layer(layer: dict) -> str:
        floor = "surface" if layer["floor_ft"] == 0 else f"{layer['floor_ft']:g} ft {layer['floor_ref']}"
        return f"Class {layer['airspace_class']} from {floor} — {layer['name']} (hours {layer['hours']})"

    print(f"\nget_airspace ({mode})")
    print(f"  airspace_class : {air.get('airspace_class')}  (source: {air.get('airspace_class_source')})")
    print(f"  controlled     : {air.get('controlled')}")
    print(f"  status         : {air.get('status')}")
    for note in air.get("notes", []):
        print(f"  note           : {note}")

    print(f"\n  FAA Class Airspace  status={cls.get('status')}"
          + (f"  error={cls['error']}" if cls.get("error") else ""))
    for layer in cls.get("surface_layers", []):
        print(f"    surface   : {_layer(layer)}")
    for layer in cls.get("overlying_layers", []):
        print(f"    overlying : {_layer(layer)}")

    fac_src = "fixture" if fac.get("fixture") else mode
    print(f"\n  FAA UAS Facility Map ({fac_src})  status={fac.get('status')}  in_grid={fac.get('in_grid')}")
    if fac.get("in_grid"):
        print(f"    class {fac.get('airspace_class')}, LAANC ceiling {fac.get('ceiling_ft')} ft, "
              f"{fac.get('airport_icao')} {fac.get('airport_name') or ''}".rstrip())

    print(f"\nresponse: mock_data={body['mock_data']} sources_failed={body['sources_failed']}")

    if args.expect:
        got = air.get("airspace_class")
        ok = got == args.expect.upper()
        print(f"\nexpect Class {args.expect.upper()}: {'PASS' if ok else 'FAIL'} (backend reported {got or 'unconfirmed'})")
        return 0 if ok else 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
