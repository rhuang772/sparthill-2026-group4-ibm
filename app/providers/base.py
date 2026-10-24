"""
app/providers/base.py — shared result models for all providers.

Every provider function returns a subclass of BaseResult, which carries:
  - checked_at: when the data was fetched
  - status: "ok" | "failed" | "stale"
  - simulated: True when the AirHub simulator was used
  - fixture: True when a local fixture file was used
"""
from __future__ import annotations

import datetime as dt
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field

ProviderStatus = Literal["ok", "failed", "stale"]


class BaseResult(BaseModel):
    checked_at: dt.datetime = Field(default_factory=lambda: dt.datetime.now(dt.timezone.utc))
    status: ProviderStatus = "ok"
    simulated: bool = False
    fixture: bool = False
    error: Optional[str] = None


# ---------------------------------------------------------------------------
# Airspace
# ---------------------------------------------------------------------------

class AirspaceDetail(BaseModel):
    airspace_class: str
    controlled: bool
    facility: Optional[str] = None


class FacilityMapDetail(BaseModel):
    in_grid: bool
    ceiling_ft: Optional[int] = None
    facility: Optional[str] = None


class AirspaceResult(BaseResult):
    airspace: Optional[AirspaceDetail] = None
    facility_map: Optional[FacilityMapDetail] = None
    raw_advisories: list[dict[str, Any]] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# FAA UAS Facility Map
# ---------------------------------------------------------------------------

class FacilityCeilingResult(BaseResult):
    in_grid: bool = False
    ceiling_ft: Optional[int] = None
    airport_name: Optional[str] = None
    airport_faaid: Optional[str] = None
    airport_icao: Optional[str] = None
    airspace_class: Optional[str] = None
    laanc_enabled: bool = False
    enabled_types: Optional[str] = None      # meaning unconfirmed; treat as informational
    map_effective: Optional[str] = None
    fetched_at: Optional[str] = None
    source_url: Optional[str] = None
    region: Optional[str] = None


# ---------------------------------------------------------------------------
# FAA Class Airspace (B/C/D/E boundaries)
# ---------------------------------------------------------------------------

class AirspaceLayer(BaseModel):
    name: str
    airspace_class: str
    local_type: Optional[str] = None       # e.g. CLASS_C, CLASS_E2, CLASS_E5
    airport_icao: Optional[str] = None
    floor_ft: float = 0
    floor_ref: Optional[str] = None        # SFC (above ground) | MSL (above sea level)
    ceiling_ft: Optional[float] = None     # None = up to overlying airspace
    ceiling_ref: Optional[str] = None
    hours: Optional[str] = None            # H24 = always; NOTAM = part-time, see NOTAMs


class ClassAirspaceResult(BaseResult):
    surface_class: Optional[str] = None    # most restrictive class starting at the ground; None = none found
    surface_layers: list[AirspaceLayer] = Field(default_factory=list)
    overlying_layers: list[AirspaceLayer] = Field(default_factory=list)
    fetched_at: Optional[str] = None
    source_url: Optional[str] = None


# ---------------------------------------------------------------------------
# Combined FAA airspace (Class Airspace + UAS Facility Map)
# ---------------------------------------------------------------------------

class FaaAirspaceResult(BaseResult):
    airspace_class: Optional[str] = None   # None = could not be determined
    airspace_class_source: Optional[str] = None   # faa_class_airspace | faa_facility_map
    controlled: Optional[bool] = None
    class_airspace: ClassAirspaceResult
    facility_map: FacilityCeilingResult
    notes: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Advisories (NSUFR, TFR, local)
# ---------------------------------------------------------------------------

class Advisory(BaseModel):
    id: str
    type: str                  # nsufr | tfr | local | airspace
    severity: str              # restricted | caution | info
    name: str
    description: str
    source: str
    effective: Optional[dict[str, str]] = None   # {start, end}


class AdvisoryResult(BaseResult):
    advisories: list[Advisory] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# NSUFR
# ---------------------------------------------------------------------------

class NSUFRRestriction(BaseModel):
    id: str
    name: str
    description: str
    center_lat: float
    center_lon: float
    radius_nm: float
    source: str


class NSUFRResult(BaseResult):
    restrictions: list[NSUFRRestriction] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# TFR
# ---------------------------------------------------------------------------

class TFRNotice(BaseModel):
    id: str
    name: str
    description: str
    effective_start: Optional[str] = None
    effective_end: Optional[str] = None
    center_lat: Optional[float] = None
    center_lon: Optional[float] = None
    radius_nm: Optional[float] = None
    source: str


class TFRResult(BaseResult):
    tfrs: list[TFRNotice] = Field(default_factory=list)
    cache_age_s: Optional[float] = None


# ---------------------------------------------------------------------------
# Weather
# ---------------------------------------------------------------------------

class WeatherResult(BaseResult):
    temperature_f: Optional[float] = None
    wind_mph: Optional[float] = None
    gusts_mph: Optional[float] = None
    wind_direction_deg: Optional[float] = None
    cloud_cover_pct: Optional[float] = None
    relative_humidity_pct: Optional[float] = None
    is_day: Optional[bool] = None
    weather_code: Optional[int] = None
    weather_description: Optional[str] = None
    precipitation_in: Optional[float] = None
    observed_at: Optional[str] = None
    source: str = "open-meteo"


# ---------------------------------------------------------------------------
# Mock OSM places
# ---------------------------------------------------------------------------

class Place(BaseModel):
    name: str
    lat: float
    lon: float
    tags: dict[str, str] = Field(default_factory=dict)
    distance_km: Optional[float] = None


class PlaceResult(BaseResult):
    places: list[Place] = Field(default_factory=list)
