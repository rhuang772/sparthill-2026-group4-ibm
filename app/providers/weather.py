"""
app/providers/weather.py — synchronous Open-Meteo weather fetch.

get_weather(lat, lon, at=None) -> WeatherResult
geocode(place) -> (lat, lon, display_name) | None

at=None (or within 30 minutes of now) returns current conditions; a later time up to
16 days ahead returns the hourly forecast for the nearest hour. Naive datetimes are
treated as UTC.

Uses a fresh synchronous httpx.Client per call so it can be safely invoked
from within FastAPI's running async event loop (no asyncio.run / no await needed).

USE_LIVE_WEATHER=true (default): calls Open-Meteo (free, no key required).
USE_LIVE_WEATHER=false: returns status="failed" with a clear message so the agent
knows to omit weather from its briefing.
"""
from __future__ import annotations

import datetime as dt
from typing import Optional

import httpx

from app.config import settings
from app.providers.base import WeatherResult
from app.providers.weather_service import CURRENT_VARS, WEATHER_CODES, WeatherUnavailable

# Shared async client — kept for interface compatibility (main.py calls set_http_client).
# The actual weather fetch uses a sync client; this is not used for weather calls.
_http_client = None

OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"
GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"

FORECAST_DAYS = 16                       # Open-Meteo's forecast horizon
CURRENT_TOLERANCE = dt.timedelta(minutes=30)

HOURLY_VARS = [
    "temperature_2m", "wind_speed_10m", "wind_gusts_10m", "wind_direction_10m",
    "cloud_cover", "relative_humidity_2m", "is_day", "weather_code",
    "precipitation", "precipitation_probability",
]

_UNITS = {
    "temperature_unit": "fahrenheit",
    "wind_speed_unit": "mph",
    "precipitation_unit": "inch",
}


def set_http_client(client) -> None:
    """Called once at startup with the app-wide AsyncClient (kept for interface compat)."""
    global _http_client
    _http_client = client


def geocode(place: str) -> Optional[tuple[float, float, str]]:
    """Look up a place name ("Seattle" or "Springfield, Illinois").

    Open-Meteo matches on the name only, so anything after the first comma is used
    to pick among the matches by region or country.
    """
    name, _, qualifier = place.partition(",")
    with httpx.Client(timeout=10) as client:
        r = client.get(GEOCODING_URL, params={"name": name.strip(), "count": 10, "language": "en"})
        r.raise_for_status()
        results = r.json().get("results") or []
    if not results:
        return None

    qualifier = qualifier.strip().lower()
    best = results[0]
    if qualifier:
        for res in results:
            region = " ".join(str(res.get(k, "")) for k in ("admin1", "country", "country_code")).lower()
            if qualifier in region:
                best = res
                break
    label = ", ".join(str(best[k]) for k in ("name", "admin1", "country") if best.get(k))
    return float(best["latitude"]), float(best["longitude"]), label


def get_weather(lat: float, lon: float, at: Optional[dt.datetime] = None) -> WeatherResult:
    """Current conditions, or the forecast for the hour nearest `at`.

    Safe to call from any context including FastAPI's async event loop.
    """
    now = dt.datetime.now(dt.timezone.utc)
    base = {"checked_at": now, "lat": lat, "lon": lon}

    if not settings.USE_LIVE_WEATHER:
        return WeatherResult(
            **base,
            status="failed",
            error="USE_LIVE_WEATHER=false — weather provider disabled.",
        )

    if at is not None and at.tzinfo is None:
        at = at.replace(tzinfo=dt.timezone.utc)
    if at is None or abs(at - now) <= CURRENT_TOLERANCE:
        return _current(lat, lon, base)
    if at < now:
        return WeatherResult(**base, status="failed",
                             error="Past weather is not available; only current conditions and forecasts.")
    if at > now + dt.timedelta(days=FORECAST_DAYS):
        return WeatherResult(**base, status="failed",
                             error=f"Forecasts only cover the next {FORECAST_DAYS} days.",
                             note="Check the forecast again closer to the flight date.")
    return _forecast(lat, lon, at, now, base)


def _current(lat: float, lon: float, base: dict) -> WeatherResult:
    params = {"latitude": lat, "longitude": lon, "current": ",".join(CURRENT_VARS), **_UNITS}
    try:
        with httpx.Client(timeout=10) as client:
            r = client.get(OPEN_METEO_URL, params=params)
            r.raise_for_status()
            cur = r.json()["current"]
            code = int(cur["weather_code"])
    except (httpx.HTTPError, KeyError, ValueError, TypeError) as exc:
        return WeatherResult(**base, status="failed", error=f"Open-Meteo unavailable: {exc}")
    except Exception as exc:
        return WeatherResult(**base, status="failed", error=str(exc))

    return WeatherResult(
        **base,
        status="ok",
        temperature_f=cur["temperature_2m"],
        wind_mph=cur["wind_speed_10m"],
        gusts_mph=cur["wind_gusts_10m"],
        wind_direction_deg=cur["wind_direction_10m"],
        cloud_cover_pct=cur["cloud_cover"],
        relative_humidity_pct=cur["relative_humidity_2m"],
        is_day=bool(cur["is_day"]),
        weather_code=code,
        weather_description=WEATHER_CODES.get(code, "Unknown"),
        precipitation_in=cur["precipitation"],
        observed_at=cur["time"],
        source="open-meteo",
    )


def _forecast(lat: float, lon: float, at: dt.datetime, now: dt.datetime, base: dict) -> WeatherResult:
    hour = (at.astimezone(dt.timezone.utc) + dt.timedelta(minutes=30)).replace(
        minute=0, second=0, microsecond=0)
    stamp = hour.strftime("%Y-%m-%dT%H:%M")
    params = {
        "latitude": lat, "longitude": lon, "hourly": ",".join(HOURLY_VARS),
        "timezone": "GMT", "start_hour": stamp, "end_hour": stamp, **_UNITS,
    }
    try:
        with httpx.Client(timeout=10) as client:
            r = client.get(OPEN_METEO_URL, params=params)
            r.raise_for_status()
            hourly = r.json()["hourly"]
            row = {k: hourly[k][0] for k in ["time", *HOURLY_VARS]}
            code = int(row["weather_code"])
    except (httpx.HTTPError, KeyError, IndexError, ValueError, TypeError) as exc:
        return WeatherResult(**base, status="failed", error=f"Open-Meteo forecast unavailable: {exc}")
    except Exception as exc:
        return WeatherResult(**base, status="failed", error=str(exc))

    note = None
    if hour - now > dt.timedelta(days=3):
        note = "Forecasts more than 3 days out are less reliable. Check again closer to the flight."
    return WeatherResult(
        **base,
        status="ok",
        forecast=True,
        temperature_f=row["temperature_2m"],
        wind_mph=row["wind_speed_10m"],
        gusts_mph=row["wind_gusts_10m"],
        wind_direction_deg=row["wind_direction_10m"],
        cloud_cover_pct=row["cloud_cover"],
        relative_humidity_pct=row["relative_humidity_2m"],
        is_day=None if row["is_day"] is None else bool(row["is_day"]),
        weather_code=code,
        weather_description=WEATHER_CODES.get(code, "Unknown"),
        precipitation_in=row["precipitation"],
        precipitation_probability_pct=row["precipitation_probability"],
        observed_at=f"{row['time']}Z",
        note=note,
        source="open-meteo",
    )
