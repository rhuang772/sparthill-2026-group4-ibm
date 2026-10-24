"""
app/providers/tfr.py — FAA TFR fetch + parse.

Default: reads fixtures/tfr_active.json (fixture=True).
In-process cache with 60-minute TTL (lost on restart).
Live FAA XML fetch behind USE_LIVE_TFR=true (not implemented for MVP).

get_tfrs(lat, lon, flight_time) -> TFRResult
"""
from __future__ import annotations

import datetime as dt
import json
import time
from typing import Optional

from app.config import settings
from app.providers.base import TFRNotice, TFRResult

_CACHE_TTL_S = 3600  # 60 minutes

# ---------------------------------------------------------------------------
# In-process cache
# ---------------------------------------------------------------------------
_cached_data: Optional[dict] = None
_cache_loaded_at: float = 0.0


def _load_fixture() -> dict:
    fixture_path = settings.FIXTURES_DIR / "tfr_active.json"
    return json.loads(fixture_path.read_text())


def _get_raw() -> tuple[dict, float]:
    """Return (raw_data, cache_age_s).  Uses in-process cache with TTL."""
    global _cached_data, _cache_loaded_at

    now_ts = time.monotonic()
    age = now_ts - _cache_loaded_at

    if _cached_data is None or age >= _CACHE_TTL_S:
        if settings.USE_LIVE_TFR:
            # Live FAA XML fetch would go here; not implemented for MVP
            raise NotImplementedError("USE_LIVE_TFR=true but live TFR fetch is not yet implemented.")
        _cached_data = _load_fixture()
        _cache_loaded_at = now_ts
        age = 0.0

    return _cached_data, age


def get_tfrs(
    lat: float,
    lon: float,
    flight_time: Optional[dt.datetime] = None,
) -> TFRResult:
    """Return TFRs from the cache/fixture.

    If flight_time is provided, only TFRs whose effective window contains
    flight_time are returned.  If not provided, all stored TFRs are returned.
    """
    now = dt.datetime.now(dt.timezone.utc)

    try:
        raw, cache_age = _get_raw()
    except NotImplementedError as exc:
        return TFRResult(checked_at=now, status="failed", error=str(exc))
    except Exception as exc:
        return TFRResult(checked_at=now, status="failed", error=f"Could not load TFR fixture: {exc}")

    tfrs = []
    for t in raw.get("tfrs", []):
        # Time filter
        if flight_time is not None:
            start_str = t.get("effective_start")
            end_str = t.get("effective_end")
            if start_str and end_str:
                try:
                    start = dt.datetime.fromisoformat(start_str.replace("Z", "+00:00"))
                    end = dt.datetime.fromisoformat(end_str.replace("Z", "+00:00"))
                    if not (start <= flight_time <= end):
                        continue
                except ValueError:
                    pass  # unparseable dates — include the TFR to be safe

        tfrs.append(TFRNotice(
            id=t["id"],
            name=t["name"],
            description=t["description"],
            effective_start=t.get("effective_start"),
            effective_end=t.get("effective_end"),
            center_lat=t.get("center_lat"),
            center_lon=t.get("center_lon"),
            radius_nm=t.get("radius_nm"),
            source=t["source"],
        ))

    is_fixture = not settings.USE_LIVE_TFR
    status = "stale" if cache_age >= _CACHE_TTL_S else "ok"

    return TFRResult(
        checked_at=now,
        status=status,      # type: ignore[arg-type]
        fixture=is_fixture,
        tfrs=tfrs,
        cache_age_s=cache_age,
    )
