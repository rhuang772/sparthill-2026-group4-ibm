"""
app/providers/weather.py — synchronous Open-Meteo weather fetch.

get_weather(lat, lon) -> WeatherResult

Uses a fresh synchronous httpx.Client per call so it can be safely invoked
from within FastAPI's running async event loop (no asyncio.run / no await needed).

USE_LIVE_WEATHER=true (default): calls Open-Meteo (free, no key required).
USE_LIVE_WEATHER=false: returns status="failed" with a clear message so the agent
knows to omit weather from its briefing.
"""
from __future__ import annotations

import datetime as dt

import httpx

from app.config import settings
from app.providers.base import WeatherResult
from app.providers.weather_service import CURRENT_VARS, WEATHER_CODES, WeatherUnavailable

# Shared async client — kept for interface compatibility (main.py calls set_http_client).
# The actual weather fetch uses a sync client; this is not used for weather calls.
_http_client = None

OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"


def set_http_client(client) -> None:
    """Called once at startup with the app-wide AsyncClient (kept for interface compat)."""
    global _http_client
    _http_client = client


def get_weather(lat: float, lon: float) -> WeatherResult:
    """Fetch current weather conditions using a synchronous httpx.Client.

    Safe to call from any context including FastAPI's async event loop.
    """
    now = dt.datetime.now(dt.timezone.utc)

    if not settings.USE_LIVE_WEATHER:
        return WeatherResult(
            checked_at=now,
            status="failed",
            error="USE_LIVE_WEATHER=false — weather provider disabled.",
        )

    params = {
        "latitude": lat,
        "longitude": lon,
        "current": ",".join(CURRENT_VARS),
        "temperature_unit": "fahrenheit",
        "wind_speed_unit": "mph",
        "precipitation_unit": "inch",
    }

    try:
        with httpx.Client(timeout=10) as client:
            r = client.get(OPEN_METEO_URL, params=params)
            r.raise_for_status()
            cur = r.json()["current"]
            code = int(cur["weather_code"])
    except (httpx.HTTPError, KeyError, ValueError, TypeError) as exc:
        return WeatherResult(
            checked_at=now,
            status="failed",
            error=f"Open-Meteo unavailable: {exc}",
        )
    except Exception as exc:
        return WeatherResult(
            checked_at=now,
            status="failed",
            error=str(exc),
        )

    return WeatherResult(
        checked_at=now,
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
