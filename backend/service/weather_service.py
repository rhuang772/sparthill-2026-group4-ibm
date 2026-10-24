import httpx

from models import Weather


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


class WeatherService:
    BASE_URL = "https://api.open-meteo.com/v1/forecast"

    def __init__(self, client: httpx.AsyncClient):
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