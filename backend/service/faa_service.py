import httpx

from backend.models import HeightLimit


class FaaUnavailable(Exception):
    """The FAA ArcGIS service failed or returned bad data."""


class FaaService:
    URL = ("https://services6.arcgis.com/ssFJjBXIUyZDrSYZ/arcgis/rest/services/"
           "FAA_UAS_FacilityMap_Data/FeatureServer/0/query")

    def __init__(self, client: httpx.AsyncClient):
        self.client = client

    async def _query_cells(self, lat: float, lon: float, radius_m: float) -> list[dict]:
        out_fields = ["CEILING", "UNIT", "MAP_EFF"]
        for i in range(1, 6):
            out_fields += [f"APT{i}_NAME", f"APT{i}_FAAID", f"APT{i}_LAANC", f"AIRSPACE_{i}"]

        base = {
            "where": "1=1",
            "geometry": f"{lon},{lat}",                  # lon first
            "geometryType": "esriGeometryPoint",
            "inSR": 4326,
            "spatialRel": "esriSpatialRelIntersects",
            "distance": max(radius_m, 1),                # some servers reject 0
            "units": "esriSRUnit_Meter",
            "outFields": ",".join(out_fields),
            "returnGeometry": "false",
            "f": "json",
            "resultRecordCount": 2000,
        }
        cells, offset = [], 0
        while True:
            r = await self.client.get(self.URL, params={**base, "resultOffset": offset}, timeout=15)
            r.raise_for_status()
            body = r.json()
            if "error" in body:                          # ArcGIS reports errors with HTTP 200
                raise FaaUnavailable(str(body["error"]))
            batch = [f["attributes"] for f in body["features"]]
            cells += batch
            if len(batch) < 2000:
                return cells
            offset += 2000

    async def get_height_limit(self, lat: float, lon: float, radius_m: float) -> HeightLimit:
        try:
            cells = await self._query_cells(lat, lon, radius_m)
        except FaaUnavailable:
            raise
        except (httpx.HTTPError, KeyError, ValueError, TypeError) as e:
            raise FaaUnavailable(str(e)) from e

        if not cells:
            return HeightLimit(
                lat=lat, lon=lon, radius_m=radius_m, status="unknown",
                max_altitude_ft=None, limiting_airport=None, airports=[],
                airspace_classes=[], laanc_available=False,
                cells_checked=0, map_effective=None,
            )

        lowest = min(cells, key=lambda c: c["CEILING"])
        airports, classes, laanc = [], [], False
        for c in cells:
            for i in range(1, 6):
                name = c.get(f"APT{i}_NAME")
                if name:
                    label = f'{name} ({c.get(f"APT{i}_FAAID")})'
                    if label not in airports:
                        airports.append(label)
                    laanc = laanc or c.get(f"APT{i}_LAANC") == 1
                cls = c.get(f"AIRSPACE_{i}")
                if cls and cls not in classes:
                    classes.append(cls)

        limiting = next(
            (f'{lowest[f"APT{i}_NAME"]} ({lowest[f"APT{i}_FAAID"]})'
             for i in range(1, 6) if lowest.get(f"APT{i}_NAME")),
            None,
        )

        return HeightLimit(
            lat=lat, lon=lon, radius_m=radius_m, status="limited",
            max_altitude_ft=int(lowest["CEILING"]),
            limiting_airport=limiting, airports=airports,
            airspace_classes=classes, laanc_available=laanc,
            cells_checked=len(cells), map_effective=lowest.get("MAP_EFF"),
        )