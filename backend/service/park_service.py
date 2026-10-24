from datetime import datetime, timezone
import httpx
import logging

from models import ProtectedAreaFeature, ProtectedAreaResult

logger = logging.getLogger(__name__)

class ParkUnavailable(Exception):
    """Protected area service failed."""

class ParkService:
    BASE_URL = "https://edits.nationalmap.gov/arcgis/rest/services/PAD-US/PAD_US_4_1/MapServer/0/query"
    TIMEOUT_SECONDS = 5.0

    async def get_parks(self, lat: float, lon: float, radius_m: float = 500.0) -> ProtectedAreaResult:
        params = {
            "geometry": f"{lon},{lat}",
            "geometryType": "esriGeometryPoint",
            "inSR": "4326",
            "spatialRel": "esriSpatialRelIntersects",
            "distance": str(radius_m),
            "units": "esriSRUnit_Meter",
            "outSR": "4326",
            "outFields": "*",
            "f": "json"
        }

        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(self.BASE_URL, params=params, timeout=self.TIMEOUT_SECONDS)
                response.raise_for_status()
                data = response.json()
        except Exception as exc:
            raise ParkUnavailable(f"USGS official ArcGIS REST service failed: {exc}") from exc

        features: list[ProtectedAreaFeature] = []
        is_restricted = False

        for feat in data.get("features", []):
            attrs = feat.get("attributes", {})
            name = attrs.get("Unit_Nm") or attrs.get("Loc_Nm") or attrs.get("State_Nm") or "Protected Land"
            designation = str(attrs.get("Des_Tp") or "").upper()
            manager = str(attrs.get("Mang_Name") or "").upper()

            # EXCLUDE LOCAL/CIVIC SPACES ENTIRELY
            # PAD-US uses 'LP' (Local Park) and 'LOTH' (Local Other) for city parks, schools, plazas
            if designation in ["LP", "LOTH"] or "school" in name.lower() or "plaza" in name.lower() or "center" in name.lower():
                continue

            # Determine kind for state/federal protected areas
            kind = "state_park"
            if "preserve" in name.lower() or "wilderness" in name.lower() or designation in ["NP", "NW", "NWR"]:
                kind = "nature_preserve"

            is_restricted = True  # Anything left here is a legitimate state/federal park or preserve

            features.append(
                ProtectedAreaFeature(
                    feature_id=str(attrs.get("OBJECTID", "unknown")),
                    name=str(name),
                    kind=kind,
                    lat=lat,
                    lon=lon,
                    tags={
                        "designation": designation,
                        "manager": manager,
                        "gap_status": str(attrs.get("Gap_Sts", ""))
                    }
                )
            )

        status = "restricted" if features else "clear"
        risk_level = "high" if features else "none"

        return ProtectedAreaResult(
            lat=lat,
            lon=lon,
            radius_m=radius_m,
            status=status,
            risk_level=risk_level,
            features=features,
            features_found=len(features),
            fetched_at=datetime.now(timezone.utc).isoformat(),
            note=(
                f"Queried USGS PAD-US service within a {radius_m}m buffer (excluding local civic spaces). "
                "Verify specific local park rules regarding drone operations."
            ),
            source="USGS PAD-US Official (ArcGIS REST)"
        )