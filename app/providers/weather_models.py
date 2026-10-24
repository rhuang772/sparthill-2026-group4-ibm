"""
app/providers/weather_models.py — Pydantic models for weather and FAA height-limit data.

Copied from new_apis/models.py; no references to new_apis remain.
"""
from __future__ import annotations

from pydantic import BaseModel


class Weather(BaseModel):
    lat: float
    lon: float
    observed_at: str
    temperature_f: float
    wind_mph: float
    gusts_mph: float
    wind_direction_deg: float      # direction the wind comes FROM, 0–360
    cloud_cover_pct: float
    pressure_hpa: float            # sea-level pressure
    relative_humidity_pct: float
    is_day: bool
    weather_code: int              # WMO code
    weather_description: str
    precipitation_in: float        # total
    rain_in: float
    showers_in: float
    snowfall_in: float
    source: str = "open-meteo"


class HeightLimit(BaseModel):
    lat: float
    lon: float
    radius_m: float
    status: str                      # "limited" | "unknown"
    max_altitude_ft: int | None      # lowest ceiling AGL; None if unknown
    limiting_airport: str | None     # airport behind the lowest ceiling
    airports: list[str]              # all airports with cells in the area
    airspace_classes: list[str]      # e.g. ["C"]
    laanc_available: bool            # at least one airport supports LAANC
    cells_checked: int
    map_effective: str | None        # MAP_EFF of the data
    source: str = "FAA UAS Facility Map"
