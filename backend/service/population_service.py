import math
import os
from datetime import datetime, timezone
from typing import Any
from pathlib import Path
from dotenv import load_dotenv

import httpx

from models import PopulationFeature, PopulationResult
import logging

logger = logging.getLogger(__name__)

env_path = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(env_path)

GEOAPIFY_API_KEY = os.getenv("GEOAPIFY_API_KEY")

if not GEOAPIFY_API_KEY:
    raise RuntimeError("GEOAPIFY_API_KEY is not configured")


class PopulationUnavailable(Exception):
    """Geoapify failed, is not configured, or returned an unexpected response."""


class PopulationService:
    URL = "https://api.geoapify.com/v2/places"
    TIMEOUT_SECONDS = 8.0
    DEFAULT_LIMIT = 50

    # Geoapify categories are hierarchical. These rules intentionally map
    # returned categories to transparent app heuristics, not measured population.
    CATEGORY_RULES = (
        ("education.school", "school", 3.0),
        ("education.college", "college", 3.0),
        ("education.university", "university", 4.0),
        ("education", "education", 3.0),
        ("leisure.playground", "playground", 2.0),
        ("leisure.park", "park", 2.0),
        ("activity.community_center", "community_center", 3.0),
        ("entertainment", "entertainment", 2.0),
    )

    # Search only for categories relevant to the first-pass ground-risk estimate.
    CATEGORIES = ",".join(
        [
            "education",
            "education.university",
            "leisure.park",
            "leisure.playground",
            #"activity.community_center",
            "entertainment",
        ]
    )

    def __init__(self, client: httpx.AsyncClient, api_key: str | None = None):
        self.client = client
        self.api_key = api_key or os.getenv("GEOAPIFY_API_KEY")

    @staticmethod
    def _distance_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        """Great-circle distance between two coordinates, in meters."""
        earth_radius_m = 6_371_000
        p1, p2 = math.radians(lat1), math.radians(lat2)
        dlat = math.radians(lat2 - lat1)
        dlon = math.radians(lon2 - lon1)
        a = (
            math.sin(dlat / 2) ** 2
            + math.cos(p1) * math.cos(p2) * math.sin(dlon / 2) ** 2
        )
        return 2 * earth_radius_m * math.asin(min(1.0, math.sqrt(a)))

    @classmethod
    def _classify(cls, score: float, feature_count: int) -> str:
        # Initial heuristic thresholds. Validate/tune these against real examples.
        if feature_count == 0:
            return "low"
        if score >= 8:
            return "high"
        if score >= 3:
            return "moderate"
        return "low"

    async def _query_features(
        self, lat: float, lon: float, radius_m: float
    ) -> list[dict[str, Any]]:
        if not self.api_key:
            raise PopulationUnavailable(
                "GEOAPIFY_API_KEY is not configured in the server environment"
            )

        params = {
            "categories": self.CATEGORIES,
            "filter": f"circle:{lon},{lat},{radius_m}",
            "bias": f"proximity:{lon},{lat}",
            "limit": self.DEFAULT_LIMIT,
            "lang": "en",
            "apiKey": self.api_key,
        }
        print("DEBUG FULL URL:", self.client.build_request("GET", self.URL, params=params).url)

        try:
            response = await self.client.get(
                self.URL,
                params=params,
                headers={"Accept": "application/json"},
                timeout=self.TIMEOUT_SECONDS,
            )
            response.raise_for_status()
            body = response.json()
        except httpx.HTTPStatusError as exc:
            # Keep the upstream status in server logs; don't return the API key
            # or raw upstream response to the client.
            status = exc.response.status_code
            raise PopulationUnavailable(
                f"Geoapify returned HTTP {status}"
            ) from exc
        except (httpx.HTTPError, ValueError) as exc:
            raise PopulationUnavailable(
                f"Geoapify request failed: {type(exc).__name__}"
            ) from exc
        except Exception:
            logger.exception("Unexpected error calling Geoapify")
            raise

        if not isinstance(body, dict) or not isinstance(body.get("features"), list):
            raise PopulationUnavailable("Geoapify returned an unexpected response")

        return body["features"]

    @classmethod
    def _classify_feature(cls, categories: list[str]) -> tuple[str, float] | None:
        # Prefer the most specific matching category. Some records can have
        # multiple categories, so inspect all returned categories.
        matches: list[tuple[int, str, float]] = []
        for category in categories:
            for prefix, kind, weight in cls.CATEGORY_RULES:
                if category == prefix or category.startswith(prefix + "."):
                    matches.append((len(prefix), kind, weight))
        if not matches:
            return None
        _, kind, weight = max(matches, key=lambda item: item[0])
        return kind, weight

    async def get_population_risk(
        self, lat: float, lon: float, radius_m: float
    ) -> PopulationResult:
        elements = await self._query_features(lat, lon, radius_m)

        features_by_id: dict[str, PopulationFeature] = {}
        for element in elements:
            properties = element.get("properties") or {}
            geometry = element.get("geometry") or {}
            coordinates = geometry.get("coordinates") or []
            categories = properties.get("categories") or []

            if not isinstance(categories, list):
                continue
            classified = self._classify_feature([str(value) for value in categories])
            if classified is None:
                continue
            kind, base_weight = classified

            # Geoapify normally includes lat/lon in properties; GeoJSON Point
            # coordinates are [longitude, latitude] and serve as a fallback.
            feature_lon = properties.get("lon")
            feature_lat = properties.get("lat")
            if (feature_lon is None or feature_lat is None) and len(coordinates) >= 2:
                feature_lon, feature_lat = coordinates[0], coordinates[1]
            if feature_lon is None or feature_lat is None:
                continue

            feature_lat, feature_lon = float(feature_lat), float(feature_lon)
            distance_m = self._distance_m(lat, lon, feature_lat, feature_lon)
            # The API filter should constrain the radius; verify locally too.
            if distance_m > radius_m:
                continue

            proximity_weight = base_weight * (
                1.0 - 0.5 * distance_m / max(radius_m, 1.0)
            )
            place_id = str(properties.get("place_id") or "")
            if not place_id:
                place_id = f"{feature_lat:.6f},{feature_lon:.6f}:{','.join(categories)}"

            name = properties.get("name") or properties.get("address_line1") or f"Unnamed {kind.replace('_', ' ')}"
            address = properties.get("formatted") or properties.get("address_line2") or ""
            tags = {"categories": ",".join(str(c) for c in categories)}
            if address:
                tags["address"] = str(address)

            features_by_id[place_id] = PopulationFeature(
                feature_id=place_id,
                name=str(name),
                kind=kind,
                distance_m=round(distance_m, 1),
                lat=feature_lat,
                lon=feature_lon,
                weight=round(proximity_weight, 2),
                osm_type="geoapify",
                tags=tags,
            )

        features = sorted(features_by_id.values(), key=lambda feature: feature.distance_m)
        score = round(sum(feature.weight for feature in features), 2)
        status = self._classify(score, len(features))

        return PopulationResult(
            lat=lat,
            lon=lon,
            radius_m=radius_m,
            status=status,
            score=score,
            features=features,
            features_found=len(features),
            fetched_at=datetime.now(timezone.utc).isoformat(),
            note=(
                "This is a geographic-context heuristic based on nearby places "
                "returned by Geoapify, not a census population estimate or live "
                "crowd count. Place coverage may be incomplete; a low score does "
                "not guarantee that an area is unpopulated or safe to fly."
            ),
            source="Geoapify Places API",
        )
