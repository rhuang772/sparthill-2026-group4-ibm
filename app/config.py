"""
app/config.py — typed settings and FAA property name constants.
"""
from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # OpenAI
    OPENAI_API_KEY: str = ""
    OPENAI_MODEL: str = "gpt-4o"

    # AirHub / simulator
    USE_SIM: bool = True
    AIRHUB_API_KEY: str = "sim-api-key"
    AIRHUB_CLIENT_ID: str = "sim-client-id"
    AIRHUB_CLIENT_SECRET: str = "sim-client-secret"
    AIRHUB_BASE_URL: str = "https://airhub-api-sandbox.airspacelink.com"

    # Feature flags for live data sources (both off by default)
    USE_LIVE_TFR: bool = False
    USE_LIVE_NSUFR: bool = False

    # Paths
    BASE_DIR: Path = Path(__file__).resolve().parent.parent
    FIXTURES_DIR: Path = BASE_DIR / "fixtures"
    DATA_UASFM_DIR: Path = BASE_DIR / "data" / "uasfm"
    UASFM_SAMPLE_PATH: Path = FIXTURES_DIR / "uasfm_sample.geojson"
    MOCK_OSM_PATH: Path = BASE_DIR / "data" / "mock_osm.geojson"
    CHROMA_PATH: str = ".chroma"
    CHROMA_COLLECTION: str = "faa_rules_dummy"
    SEED_RULES_PATH: Path = BASE_DIR / "app" / "rules" / "seed_rules.json"


# ---------------------------------------------------------------------------
# FAA UAS Facility Map — real property names (from the official GeoJSON schema)
# Do NOT rename these; they must match the downloaded GeoJSON exactly.
# ---------------------------------------------------------------------------
PROP_CEILING = "CEILING"
PROP_UNIT = "UNIT"
PROP_APT1_FAAID = "APT1_FAAID"
PROP_APT1_ICAO = "APT1_ICAO"
PROP_APT1_NAME = "APT1_NAME"
PROP_APT1_LAANC = "APT1_LAANC"
PROP_AIRSPACE_1 = "AIRSPACE_1"
PROP_ARPT_COUNT = "ARPT_COUNT"
PROP_APT1_ENABLED = "APT1_Enabled"  # e.g. "107-AA,107-FC,44809-AA" — meaning UNCONFIRMED
PROP_MAP_EFF = "MAP_EFF"
PROP_LAST_EDIT = "LAST_EDIT"
PROP_LATITUDE = "LATITUDE"
PROP_LONGITUDE = "LONGITUDE"
PROP_GLOBALID = "GLOBALID"
PROP_OBJECTID = "OBJECTID"
PROP_REGION = "REGION"


settings = Settings()
