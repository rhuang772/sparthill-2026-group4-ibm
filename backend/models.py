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
    status: str                      # "restricted", "clear", or "unknown"
    tfrs: list[TfrItem]
    tfrs_checked: int
    unresolved_notams: list[str]     # TFRs whose details couldn't be loaded
    data_fetched_at: str | None
    data_age_seconds: int | None
    stale: bool
    note: str | None
    source: str = "FAA tfr.faa.gov"