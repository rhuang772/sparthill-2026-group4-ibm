"""
scripts/ground_risk_harness.py — run the park (USGS PAD-US) and population (Geoapify)
providers live against a single pin, without the agent or the API server.

Prints a readable summary of each result; --json prints the full result models.
The population check needs GEOAPIFY_API_KEY in .env (or the environment).

Usage:
    python scripts/ground_risk_harness.py                          # default pin: Henry W. Coe State Park
    python scripts/ground_risk_harness.py --lat 37.3352 --lon -121.8811 --radius 500
    python scripts/ground_risk_harness.py --only park              # or --only population
    python scripts/ground_risk_harness.py --json
    python scripts/ground_risk_harness.py --expect-park protected_area --expect-population high
"""
from __future__ import annotations

import argparse
import asyncio
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.providers import park, population  # noqa: E402
from app.providers.base import ParkResult, PopulationResult  # noqa: E402

DEFAULT_LAT = 37.1858
DEFAULT_LON = -121.4700


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--lat", type=float, default=DEFAULT_LAT)
    p.add_argument("--lon", type=float, default=DEFAULT_LON)
    p.add_argument("--radius", type=float, default=None,
                   help="Search radius in metres (default: each provider's own default)")
    p.add_argument("--only", choices=["park", "population"], help="Run just one provider")
    p.add_argument("--json", action="store_true", help="Print full result JSON")
    p.add_argument("--expect-park", choices=["protected_area", "none_found", "unknown"],
                   help="Exit 1 unless the park finding matches")
    p.add_argument("--expect-population", choices=["low", "moderate", "high", "unknown"],
                   help="Exit 1 unless the population risk matches")
    return p.parse_args()


async def _timed(coro):
    start = time.perf_counter()
    result = await coro
    return result, time.perf_counter() - start


def _print_park(r: ParkResult, secs: float) -> None:
    print(f"\n== Parks (USGS PAD-US) — {secs:.1f}s ==")
    print(f"status:  {r.status}")
    print(f"finding: {r.finding}   radius: {r.radius_m:g} m")
    if r.error:
        print(f"error:   {r.error}")
    for a in r.areas:
        print(f"  - {a.name}  [{a.kind}, designation={a.designation}, manager={a.manager}, gap={a.gap_status}]")
    if r.note:
        print(f"note:    {r.note}")


def _print_population(r: PopulationResult, secs: float) -> None:
    print(f"\n== Population (Geoapify) — {secs:.1f}s ==")
    print(f"status: {r.status}")
    print(f"risk:   {r.risk}   score: {r.score}   radius: {r.radius_m:g} m   places: {len(r.places)}")
    if r.error:
        print(f"error:  {r.error}")
    for p in r.places[:15]:
        print(f"  - {p.distance_m:>7.1f} m  {p.kind:<16} w={p.weight:<5} {p.name}")
    if len(r.places) > 15:
        print(f"  ... {len(r.places) - 15} more")


async def _run(args: argparse.Namespace) -> int:
    print(f"pin: {args.lat}, {args.lon}")
    run_park = args.only in (None, "park")
    run_pop = args.only in (None, "population")

    tasks = []
    if run_park:
        tasks.append(_timed(park.get_parks(args.lat, args.lon, args.radius)))
    if run_pop:
        tasks.append(_timed(population.get_population_risk(args.lat, args.lon, args.radius)))
    results = await asyncio.gather(*tasks)

    park_res = results.pop(0) if run_park else None
    pop_res = results.pop(0) if run_pop else None

    if park_res:
        print(park_res[0].model_dump_json(indent=2)) if args.json else _print_park(*park_res)
    if pop_res:
        print(pop_res[0].model_dump_json(indent=2)) if args.json else _print_population(*pop_res)

    ok = True
    if args.expect_park and park_res:
        got = park_res[0].finding
        ok &= got == args.expect_park
        print(f"\nexpect park {args.expect_park}: {'PASS' if got == args.expect_park else 'FAIL'} (got {got})")
    if args.expect_population and pop_res:
        got = pop_res[0].risk
        ok &= got == args.expect_population
        print(f"expect population {args.expect_population}: "
              f"{'PASS' if got == args.expect_population else 'FAIL'} (got {got})")
    return 0 if ok else 1


def main() -> int:
    return asyncio.run(_run(_parse_args()))


if __name__ == "__main__":
    sys.exit(main())
