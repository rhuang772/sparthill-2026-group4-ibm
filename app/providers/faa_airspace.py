"""
app/providers/faa_airspace.py — combined FAA airspace lookup.

get_airspace(lat, lon) -> FaaAirspaceResult

Merges two FAA datasets into one answer:
  - Class Airspace (faa_class_airspace): which class starts at the ground. No B/C/D/E
    layer at the surface means Class G. This is the primary source of airspace_class.
  - UAS Facility Map (faa_facility_map): LAANC grid ceiling near airports. Used for the
    authorization ceiling, and as the class fallback when Class Airspace is unavailable.

airspace_class is None only when neither source can say what the class is.
"""
from __future__ import annotations

import datetime as dt

from app.providers import faa_class_airspace, faa_facility_map
from app.providers.base import FaaAirspaceResult


def get_airspace(lat: float, lon: float) -> FaaAirspaceResult:
    now = dt.datetime.now(dt.timezone.utc)
    cls = faa_class_airspace.get_class_airspace(lat, lon)
    fm = faa_facility_map.get_facility_ceiling(lat, lon)
    notes: list[str] = []

    if cls.status != "failed":
        airspace_class = cls.surface_class or "G"
        source = "faa_class_airspace"
        if fm.in_grid and fm.airspace_class and fm.airspace_class != airspace_class:
            notes.append(
                f"FAA Class Airspace says Class {airspace_class} at the surface but the "
                f"UAS Facility Map cell lists Class {fm.airspace_class}; follow the more restrictive."
            )
    elif fm.in_grid and fm.airspace_class:
        airspace_class = fm.airspace_class
        source = "faa_facility_map"
        notes.append(f"FAA Class Airspace unavailable ({cls.error}); class taken from the UAS Facility Map.")
    else:
        airspace_class = None
        source = None
        notes.append(f"FAA Class Airspace unavailable ({cls.error}) and no UAS Facility Map cell here; "
                     "airspace class could not be confirmed.")

    if any(layer.hours == "NOTAM" for layer in cls.surface_layers):
        notes.append("This surface area is part-time (hours set by NOTAM); it may be a different class "
                     "when the tower is closed.")
    if any(layer.floor_ref == "MSL" for layer in cls.overlying_layers):
        notes.append("An overlying layer has a floor in feet MSL (above sea level); on high ground it "
                     "may be within 400 ft of the surface.")

    return FaaAirspaceResult(
        checked_at=now,
        status="failed" if airspace_class is None else ("stale" if "stale" in (cls.status, fm.status) else "ok"),
        fixture=fm.fixture,
        airspace_class=airspace_class,
        airspace_class_source=source,
        controlled=None if airspace_class is None else airspace_class != "G",
        class_airspace=cls,
        facility_map=fm,
        notes=notes,
        error=None if airspace_class is not None else "airspace class could not be determined",
    )
