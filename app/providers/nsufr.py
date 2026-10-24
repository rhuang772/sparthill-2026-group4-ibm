"""
app/providers/nsufr.py — National Security UAS Flight Restriction lookup.

Default: reads fixtures/nsufr_hit.json (fixture=True).
Live: optional FAA ArcGIS point query when USE_LIVE_NSUFR=true (not implemented for MVP).

get_nsufr(lat, lon) -> NSUFRResult
"""
from __future__ import annotations

import datetime as dt
import json

from app.config import settings
from app.providers.base import NSUFRRestriction, NSUFRResult


def get_nsufr(lat: float, lon: float) -> NSUFRResult:
    """Return NSUFR restrictions near the given point (fixture-backed by default)."""
    now = dt.datetime.now(dt.timezone.utc)

    if settings.USE_LIVE_NSUFR:
        # Live FAA ArcGIS query would go here; not implemented for MVP
        return NSUFRResult(
            checked_at=now,
            status="failed",
            error="USE_LIVE_NSUFR=true but live NSUFR query is not yet implemented.",
        )

    # --- fixture path ---
    fixture_path = settings.FIXTURES_DIR / "nsufr_hit.json"
    try:
        raw = json.loads(fixture_path.read_text())
    except Exception as exc:
        return NSUFRResult(
            checked_at=now,
            status="failed",
            error=f"Could not load NSUFR fixture: {exc}",
        )

    restrictions = []
    for r in raw.get("restrictions", []):
        restrictions.append(NSUFRRestriction(
            id=r["id"],
            name=r["name"],
            description=r["description"],
            center_lat=r["center_lat"],
            center_lon=r["center_lon"],
            radius_nm=r["radius_nm"],
            source=r["source"],
        ))

    return NSUFRResult(
        checked_at=now,
        status="ok",
        fixture=True,
        restrictions=restrictions,
    )
