from datetime import datetime, timedelta, timezone

import httpx

from backend.models import Weather, WeatherForecast, WeatherHour, WeatherSummary


class WeatherUnavailable(Exception):
    """The external weather provider failed or returned bad data."""


# WMO weather interpretation codes used by Open-Meteo
WEATHER_CODES = {
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

# If a request fails with a 502, try removing "visibility", "precipitation_probability"
# and "wind_speed_120m" first. Those names are from memory and untested.
HOURLY_VARS = [
    "temperature_2m", "wind_speed_10m", "wind_speed_120m", "wind_gusts_10m",
    "wind_direction_10m", "cloud_cover", "pressure_msl", "relative_humidity_2m",
    "visibility", "is_day", "weather_code", "precipitation",
    "precipitation_probability", "rain", "showers", "snowfall",
]


def _at(h: dict, key: str, i: int):
    """Value at index i of an hourly series, or None if the series is missing."""
    vals = h.get(key)
    return vals[i] if vals and i < len(vals) else None


def _nums(hours: list[WeatherHour], attr: str) -> list[float]:
    return [v for v in (getattr(x, attr) for x in hours) if v is not None]


def _summarize(hours: list[WeatherHour]) -> WeatherSummary:
    temps = _nums(hours, "temperature_f")
    codes = _nums(hours, "weather_code")
    worst = max(codes) if codes else None
    return WeatherSummary(
        hours=len(hours),
        min_temperature_f=min(temps) if temps else None,
        max_temperature_f=max(temps) if temps else None,
        max_wind_mph=max(_nums(hours, "wind_mph"), default=None),
        max_wind_mph_120m=max(_nums(hours, "wind_mph_120m"), default=None),
        max_gusts_mph=max(_nums(hours, "gusts_mph"), default=None),
        min_visibility_m=min(_nums(hours, "visibility_m"), default=None),
        total_precipitation_in=round(sum(_nums(hours, "precipitation_in")), 3),
        max_precipitation_probability_pct=max(_nums(hours, "precipitation_probability_pct"), default=None),
        worst_weather_code=worst,
        worst_weather_description=WEATHER_CODES.get(worst, "Unknown") if worst is not None else None,
    )


class WeatherService:
    BASE_URL = "https://api.open-meteo.com/v1/forecast"

    def __init__(self, client: httpx.AsyncClient):
        self.client = client

    # ───────────── Current conditions ─────────────

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

    # ───────────── Forecast for a flight window ─────────────

    async def get_window(self, lat: float, lon: float,
                         start: datetime, end: datetime) -> WeatherForecast:
        start_utc = start.astimezone(timezone.utc)
        end_utc = end.astimezone(timezone.utc)

        # Hourly data: include every hour that overlaps the window
        first = start_utc.replace(minute=0, second=0, microsecond=0)
        last_excl = end_utc.replace(minute=0, second=0, microsecond=0)
        if last_excl < end_utc:
            last_excl += timedelta(hours=1)

        params = {
            "latitude": lat,
            "longitude": lon,
            "hourly": ",".join(HOURLY_VARS),
            "start_date": first.date().isoformat(),
            "end_date": (last_excl - timedelta(hours=1)).date().isoformat(),
            "timezone": "GMT",
            "temperature_unit": "fahrenheit",
            "wind_speed_unit": "mph",
            "precipitation_unit": "inch",
        }
        try:
            r = await self.client.get(self.BASE_URL, params=params, timeout=15)
            r.raise_for_status()
            h = r.json()["hourly"]

            hours = []
            for i, t in enumerate(h["time"]):
                dt = datetime.fromisoformat(t).replace(tzinfo=timezone.utc)
                if not (first <= dt < last_excl):
                    continue
                code = _at(h, "weather_code", i)
                is_day = _at(h, "is_day", i)
                hours.append(WeatherHour(
                    time=dt.isoformat(),
                    temperature_f=_at(h, "temperature_2m", i),
                    wind_mph=_at(h, "wind_speed_10m", i),
                    wind_mph_120m=_at(h, "wind_speed_120m", i),
                    gusts_mph=_at(h, "wind_gusts_10m", i),
                    wind_direction_deg=_at(h, "wind_direction_10m", i),
                    cloud_cover_pct=_at(h, "cloud_cover", i),
                    pressure_hpa=_at(h, "pressure_msl", i),
                    relative_humidity_pct=_at(h, "relative_humidity_2m", i),
                    visibility_m=_at(h, "visibility", i),
                    is_day=None if is_day is None else bool(is_day),
                    weather_code=None if code is None else int(code),
                    weather_description=WEATHER_CODES.get(int(code), "Unknown") if code is not None else "Unknown",
                    precipitation_in=_at(h, "precipitation", i),
                    precipitation_probability_pct=_at(h, "precipitation_probability", i),
                    rain_in=_at(h, "rain", i),
                    showers_in=_at(h, "showers", i),
                    snowfall_in=_at(h, "snowfall", i),
                ))
        except (httpx.HTTPError, KeyError, ValueError, TypeError) as e:
            raise WeatherUnavailable(str(e)) from e

        if not hours:
            raise WeatherUnavailable("No forecast hours returned for the requested window")

        now = datetime.now(timezone.utc)
        note = None
        if start_utc > now + timedelta(days=3):
            note = "Forecasts more than a few days out are much less reliable. Recheck close to flight time."

        return WeatherForecast(
            lat=lat, lon=lon,
            window_start=start_utc.isoformat(), window_end=end_utc.isoformat(),
            hours=hours, summary=_summarize(hours),
            fetched_at=now.isoformat(), note=note,
        )