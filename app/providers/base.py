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

class TFRArea(BaseModel):
    notam_id: str
    type: Optional[str] = None
    description: Optional[str] = None
    area_name: Optional[str] = None
    floor_ft: Optional[float] = None
    floor_datum: Optional[str] = None      # MSL | AGL
    ceiling_ft: Optional[float] = None
    ceiling_datum: Optional[str] = None
    effective: Optional[str] = None
    expires: Optional[str] = None
    time_status: str                       # active | scheduled | expired | outside_hours | unknown
    reaches_drone_altitudes: bool          # floor at or below 400 ft


class TFRResult(BaseResult):
    finding: Literal["restricted", "none_found", "unknown"] = "unknown"
    radius_m: float = 0
    window_start: Optional[str] = None
    window_end: Optional[str] = None
    tfrs: list[TFRArea] = Field(default_factory=list)
    tfrs_checked: int = 0
    unresolved_notams: list[str] = Field(default_factory=list)
    data_fetched_at: Optional[str] = None
    data_age_s: Optional[int] = None
    note: Optional[str] = None
    source: str = "FAA tfr.faa.gov"


# ---------------------------------------------------------------------------
# Protected areas (state/federal parks and preserves)
# ---------------------------------------------------------------------------

class ProtectedArea(BaseModel):
    feature_id: str
    name: str
    kind: str                              # state_park | nature_preserve
    designation: Optional[str] = None      # PAD-US Des_Tp code, e.g. SP, NP, NWR
    manager: Optional[str] = None
    gap_status: Optional[str] = None


class ParkResult(BaseResult):
    finding: Literal["protected_area", "none_found", "unknown"] = "unknown"
    radius_m: float = 0
    areas: list[ProtectedArea] = Field(default_factory=list)
    note: Optional[str] = None
    source: str = "USGS PAD-US"


# ---------------------------------------------------------------------------
# Population exposure (places where people gather)
# ---------------------------------------------------------------------------

class PopulationPlace(BaseModel):
    feature_id: str
    name: str
    kind: str                              # school | university | park | playground | entertainment ...
    distance_m: float
    lat: float
    lon: float
    weight: float
    address: Optional[str] = None


class PopulationResult(BaseResult):
    risk: Literal["low", "moderate", "high", "unknown"] = "unknown"
    score: float = 0                       # heuristic, not people per km²
    radius_m: float = 0
    places: list[PopulationPlace] = Field(default_factory=list)
    note: Optional[str] = None
    source: str = "Geoapify Places API"


# ---------------------------------------------------------------------------
# Water
# ---------------------------------------------------------------------------

class WaterBody(BaseModel):
    feature_id: Optional[str] = None
    name: Optional[str] = None
    kind: str
    layer: str                             # waterbody | flowline
    distance_m: float                      # 0 if the point is in this water
    nearest_lat: float
    nearest_lon: float
    contains_point: bool


class WaterResult(BaseResult):
    risk: Literal["high", "moderate", "none", "unknown"] = "unknown"
    radius_m: float = 0
    point_over_water: bool = False
    nearest_distance_m: Optional[float] = None
    water_bodies: list[WaterBody] = Field(default_factory=list)
    total_found: int = 0
    truncated: bool = False
    note: Optional[str] = None
    source: str = "USGS 3DHP"


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
    precipitation_probability_pct: Optional[float] = None   # forecasts only
    observed_at: Optional[str] = None       # current: observation time; forecast: forecast hour (UTC)
    forecast: bool = False                  # true when this is a forecast for a future time
    lat: Optional[float] = None
    lon: Optional[float] = None
    location_name: Optional[str] = None     # set when the location came from a place-name lookup
    note: Optional[str] = None
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
