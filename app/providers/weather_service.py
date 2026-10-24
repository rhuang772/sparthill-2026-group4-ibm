"""
app/providers/weather_service.py — async service classes for Open-Meteo and FAA ArcGIS.

Copied and fixed from new_apis/service.py; no references to new_apis remain.

Fixes applied vs original new_apis/service.py:
  1. Import from app.providers.weather_models (not relative new_apis.models)
  2. _query_cells: entire pagination loop is inside the try/except — httpx errors
     from pages 2+ now surface as FaaUnavailable instead of propagating unhandled.
  3. _query_cells: only AIRSPACE_1 is a real documented FAA field; the loop
     AIRSPACE_{i} for i=2–5 returned nulls and is removed.
  4. get_height_limit: CEILING can be None (cell with no authorization) — guarded
     before min() to avoid TypeError; int() cast moved inside the None guard.
  5. f-string key access `lowest[f"APT{i}_NAME"]` replaced with .get() to avoid
     KeyError when the field is absent.
"""
from __future__ import annotations

import httpx

from app.providers.weather_models import HeightLimit, Weather


class WeatherUnavailable(Exception):
    """The external weather provider failed or returned bad data."""


# WMO weather interpretation codes used by Open-Meteo
WEATHER_CODES: dict[int, str] = {
    0: "Clear sky", 1: "Mainly clear", 2: "Partly cloudy", 3: "Overcast",
    45: "Fog", 48: "Depositing rime fog",
    51: "Light drizzle", 53: "Moderate drizzle", 55: "Dense drizzle",
    56: "Light freezing drizzle", 57: "Dense freezing drizzle",
    61: "Slight rain", 63: "Moderate rain", 65: "Heavy rain",
    66: "Light freezing rain", 67: "Heavy freezing rain",
    71: "Slight snow", 73: "Moderate snow", 75: "Heavy snow", 77: "Snow grains",
    80: "Slight rain showers", 81: "Moderate rain showers", 82: "Violent rain showers",
    85: "Slight snow showers", 86: "Heavy snow showers",
    95: "Thunderstorm", 96: "Thunderstorm with slight hail", 99: "Thunderstorm with heavy hail",
}

CURRENT_VARS = [
    "temperature_2m", "wind_speed_10m", "wind_gusts_10m", "wind_direction_10m",
    "cloud_cover", "pressure_msl", "relative_humidity_2m", "is_day",
    "weather_code", "precipitation", "rain", "showers", "snowfall",
]


class WeatherService:
    BASE_URL = "https://api.open-meteo.com/v1/forecast"

    def __init__(self, client: httpx.AsyncClient) -> None:
        self.client = client

    async def get_current(self, lat: float, lon: float) -> Weather:
        params = {
            "latitude": lat,
            "longitude": lon,
            "current": ",".join(CURRENT_VARS),
            "temperature_unit": "fahrenheit",
            "wind_speed_unit": "mph",
            "precipitation_unit": "inch",
        }
        try:
            r = await self.client.get(self.BASE_URL, params=params, timeout=10)
            r.raise_for_status()
            cur = r.json()["current"]
            code = int(cur["weather_code"])
            return Weather(
                lat=lat, lon=lon,
                observed_at=cur["time"],
                temperature_f=cur["temperature_2m"],
                wind_mph=cur["wind_speed_10m"],
                gusts_mph=cur["wind_gusts_10m"],
                wind_direction_deg=cur["wind_direction_10m"],
                cloud_cover_pct=cur["cloud_cover"],
                pressure_hpa=cur["pressure_msl"],
                relative_humidity_pct=cur["relative_humidity_2m"],
                is_day=bool(cur["is_day"]),
                weather_code=code,
                weather_description=WEATHER_CODES.get(code, "Unknown"),
                precipitation_in=cur["precipitation"],
                rain_in=cur["rain"],
                showers_in=cur["showers"],
                snowfall_in=cur["snowfall"],
            )
        except (httpx.HTTPError, KeyError, ValueError, TypeError) as e:
            raise WeatherUnavailable(str(e)) from e


class FaaUnavailable(Exception):
    """The FAA ArcGIS service failed or returned bad data."""


class FaaService:
    URL = (
        "https://services6.arcgis.com/ssFJjBXIUyZDrSYZ/arcgis/rest/services/"
        "FAA_UAS_FacilityMap_Data/FeatureServer/0/query"
    )

    def __init__(self, client: httpx.AsyncClient) -> None:
        self.client = client

    async def _query_cells(self, lat: float, lon: float, radius_m: float) -> list[dict]:
        out_fields = [
            "CEILING", "UNIT", "MAP_EFF", "AIRSPACE_1",
            "APT1_NAME", "APT1_FAAID", "APT1_LAANC",
            "APT2_NAME", "APT2_FAAID", "APT2_LAANC",
            "APT3_NAME", "APT3_FAAID", "APT3_LAANC",
            "APT4_NAME", "APT4_FAAID", "APT4_LAANC",
            "APT5_NAME", "APT5_FAAID", "APT5_LAANC",
        ]
        base = {
            "where": "1=1",
            "geometry": f"{lon},{lat}",          # ArcGIS: lon first
            "geometryType": "esriGeometryPoint",
            "inSR": 4326,
            "spatialRel": "esriSpatialRelIntersects",
            "distance": radius_m,
            "units": "esriSRUnit_Meter",
            "outFields": ",".join(out_fields),
            "returnGeometry": "false",
            "f": "json",
            "resultRecordCount": 2000,
        }
        try:
            cells, offset = [], 0
            while True:
                r = await self.client.get(
                    self.URL, params={**base, "resultOffset": offset}, timeout=15
                )
                r.raise_for_status()
                body = r.json()
                if "error" in body:              # ArcGIS reports errors with HTTP 200
                    raise FaaUnavailable(str(body["error"]))
                batch = [f["attributes"] for f in body.get("features", [])]
                cells += batch
                if len(batch) < 2000:
                    return cells
                offset += 2000
        except (httpx.HTTPError, KeyError, ValueError, TypeError) as e:
            raise FaaUnavailable(str(e)) from e

    async def get_height_limit(self, lat: float, lon: float, radius_m: float) -> HeightLimit:
        try:
            cells = await self._query_cells(lat, lon, radius_m)
        except FaaUnavailable:
            raise

        if not cells:
            return HeightLimit(
                lat=lat, lon=lon, radius_m=radius_m, status="unknown",
                max_altitude_ft=None, limiting_airport=None, airports=[],
                airspace_classes=[], laanc_available=False,
                cells_checked=0, map_effective=None,
            )

        valid_cells = [c for c in cells if c.get("CEILING") is not None]
        if not valid_cells:
            lowest = cells[0]
            ceiling: int | None = None
        else:
            lowest = min(valid_cells, key=lambda c: c["CEILING"])
            ceiling = int(lowest["CEILING"])

        airports: list[str] = []
        classes: list[str] = []
        laanc = False

        for c in cells:
            for i in range(1, 6):
                name = c.get(f"APT{i}_NAME")
                if name:
                    label = f'{name} ({c.get(f"APT{i}_FAAID", "")})'
                    if label not in airports:
                        airports.append(label)
                    if c.get(f"APT{i}_LAANC") == 1:
                        laanc = True
            cls = c.get("AIRSPACE_1")           # only AIRSPACE_1 is a real field
            if cls and cls not in classes:
                classes.append(cls)

        limiting = next(
            (
                f'{lowest.get(f"APT{i}_NAME")} ({lowest.get(f"APT{i}_FAAID", "")})'
                for i in range(1, 6) if lowest.get(f"APT{i}_NAME")
            ),
            None,
        )

        return HeightLimit(
            lat=lat, lon=lon, radius_m=radius_m,
            status="limited",
            max_altitude_ft=ceiling,
            limiting_airport=limiting,
            airports=airports,
            airspace_classes=classes,
            laanc_available=laanc,
            cells_checked=len(cells),
            map_effective=lowest.get("MAP_EFF"),
        )
