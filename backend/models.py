from pydantic import BaseModel

class Weather(BaseModel):
    lat: float
    lon: float
    observed_at: str
    temperature_f: float
    wind_mph: float
    gusts_mph: float
    wind_direction_deg: float      # direction the wind comes FROM, 0-360
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
    
class WeatherHour(BaseModel):
    time: str                                  # UTC, start of the hour
    temperature_f: float | None
    wind_mph: float | None                     # at 10 m
    wind_mph_120m: float | None                # at ~400 ft, close to max drone altitude
    gusts_mph: float | None
    wind_direction_deg: float | None
    cloud_cover_pct: float | None
    pressure_hpa: float | None
    relative_humidity_pct: float | None
    visibility_m: float | None
    is_day: bool | None
    weather_code: int | None
    weather_description: str
    precipitation_in: float | None
    precipitation_probability_pct: float | None
    rain_in: float | None
    showers_in: float | None
    snowfall_in: float | None


class WeatherSummary(BaseModel):
    hours: int
    min_temperature_f: float | None
    max_temperature_f: float | None
    max_wind_mph: float | None
    max_wind_mph_120m: float | None
    max_gusts_mph: float | None
    min_visibility_m: float | None
    total_precipitation_in: float
    max_precipitation_probability_pct: float | None
    worst_weather_code: int | None             # highest WMO code, a rough severity measure
    worst_weather_description: str | None


class WeatherForecast(BaseModel):
    lat: float
    lon: float
    window_start: str
    window_end: str
    hours: list[WeatherHour]
    summary: WeatherSummary
    fetched_at: str
    note: str | None
    source: str = "open-meteo"
    
class HeightLimit(BaseModel):
    lat: float
    lon: float
    radius_m: float
    status: str                      # "limited" or "unknown"
    max_altitude_ft: int | None      # lowest ceiling in the area, AGL; None if unknown
    limiting_airport: str | None     # airport behind the lowest ceiling
    airports: list[str]              # all airports with cells in the area
    airspace_classes: list[str]      # e.g. ["C"]
    laanc_available: bool            # at least one airport in the area supports LAANC
    cells_checked: int
    map_effective: str | None        # MAP_EFF of the data
    source: str = "FAA UAS Facility Map"
    
class TfrItem(BaseModel):
    notam_id: str
    type: str | None
    description: str | None
    time_status: str
    area_name: str | None
    floor_ft: float | None
    floor_datum: str | None          # "MSL" or "AGL"
    ceiling_ft: float | None
    ceiling_datum: str | None
    effective: str | None
    expires: str | None
    time_status: str                 # "active", "scheduled", "expired", "unknown"
    reaches_drone_altitudes: bool    # floor at or below 400 ft


class TfrResult(BaseModel):
    lat: float
    lon: float
    radius_m: float
    window_start: str              # UTC, ISO 8601
    window_end: str
    status: str                      # "restricted", "clear", or "unknown"
    tfrs: list[TfrItem]
    tfrs_checked: int
    unresolved_notams: list[str]     # TFRs whose details couldn't be loaded
    data_fetched_at: str | None
    data_age_seconds: int | None
    stale: bool
    note: str | None
    source: str = "FAA tfr.faa.gov"
    
class WaterBody(BaseModel):
    feature_id: str | None
    name: str | None
    kind: str                      # from the layer's type label, or "waterbody" / "flowline"
    layer: str                     # "waterbody" or "flowline"
    distance_m: float              # 0 if the point is in this water
    nearest_lat: float
    nearest_lon: float
    contains_point: bool


class WaterResult(BaseModel):
    lat: float
    lon: float
    radius_m: float
    water_found: bool
    point_over_water: bool
    nearest_distance_m: float | None
    risk: str                      # "high", "moderate" or "none"
    water_bodies: list[WaterBody]  # nearest first
    total_found: int
    truncated: bool
    fetched_at: str
    note: str | None
    source: str = "USGS 3DHP_all"


class PopulationFeature(BaseModel):
    feature_id: str
    name: str
    kind: str
    distance_m: float
    lat: float
    lon: float
    weight: float
    osm_type: str
    tags: dict[str, str]


class PopulationResult(BaseModel):
    lat: float
    lon: float
    radius_m: float
    status: str  # "low", "moderate", "high"; "unknown" is used if data is unavailable
    score: float  # heuristic score, not people per square kilometer
    features: list[PopulationFeature]
    features_found: int
    fetched_at: str
    note: str | None
    source: str = "OpenStreetMap Overpass API"