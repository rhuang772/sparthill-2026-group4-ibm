"""
scripts/fetch_facility_map.py — one-time download of FAA airspace GeoJSON.

Datasets (--dataset):
  facility_map    FAA UAS Facility Map grid cells  -> data/uasfm/facility_map.geojson
  class_airspace  FAA Class B/C/D/E boundaries     -> data/class_airspace/class_airspace.geojson

Each download also writes meta.json with fetched_at, record_count and bbox. After
downloading, restart the API — it will automatically use the real data.

The full datasets are large. Use --bbox to limit to a region; Class Airspace lookups
outside the downloaded bbox are reported as failed rather than as Class G.

Usage:
    python scripts/fetch_facility_map.py --bbox -122.7,37.1,-121.6,38.1 --max-records 50000
    python scripts/fetch_facility_map.py --dataset class_airspace --bbox -122.7,37.1,-121.6,38.1
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path

# Add project root to path so app.config is importable when run as a script
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx

from app.config import settings
from app.providers.faa_class_airspace import CLASS_WHERE, FAA_CLASS_AIRSPACE_URL

FAA_UASFM_URL = (
    "https://services6.arcgis.com/ssFJjBXIUyZDrSYZ/arcgis/rest/services"
    "/FAA_UAS_FacilityMap_Data/FeatureServer/0/query"
)

DATASETS = {
    "facility_map": {
        "label": "FAA UAS Facility Map", "url": FAA_UASFM_URL, "where": "1=1",
        "out_dir": settings.DATA_UASFM_DIR, "filename": "facility_map.geojson",
    },
    "class_airspace": {
        "label": "FAA Class Airspace (B/C/D/E)", "url": FAA_CLASS_AIRSPACE_URL, "where": CLASS_WHERE,
        "out_dir": settings.DATA_CLASS_AIRSPACE_DIR, "filename": "class_airspace.geojson",
    },
}


def fetch(dataset: str = "facility_map", max_records: int = 2000, bbox: str | None = None) -> None:
    ds = DATASETS[dataset]
    out_dir = ds["out_dir"]
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / ds["filename"]
    meta_path = out_dir / "meta.json"

    params = {
        "where": ds["where"],
        "outFields": "*",
        "outSR": "4326",
        "f": "geojson",
    }
    if bbox:
        west, south, east, north = (float(v) for v in bbox.split(","))
        params.update({
            "geometry": json.dumps({"xmin": west, "ymin": south, "xmax": east, "ymax": north}),
            "geometryType": "esriGeometryEnvelope",
            "inSR": "4326",
            "spatialRel": "esriSpatialRelIntersects",
        })

    print(f"Downloading {ds['label']} (up to {max_records} records"
          f"{f', bbox {bbox}' if bbox else ''})...")
    print(f"URL: {ds['url']}")

    features: list[dict] = []
    try:
        with httpx.Client(timeout=60) as client:
            while len(features) < max_records:
                page = {**params, "resultOffset": len(features),
                        "resultRecordCount": min(2000, max_records - len(features))}
                r = client.get(ds["url"], params=page)
                r.raise_for_status()
                data = r.json()
                if "error" in data:
                    raise httpx.HTTPError(f"ArcGIS error: {data['error']}")
                batch = data.get("features", [])
                features.extend(batch)
                print(f"  fetched {len(features)} features")
                if not batch or not data.get("properties", {}).get("exceededTransferLimit"):
                    break
    except httpx.HTTPError as exc:
        print(f"\n⚠️  Download failed: {exc}")
        sys.exit(1)

    if not features:
        print("⚠️  Response contained no features. Check the URL and try again.")
        sys.exit(1)

    out_path.write_text(json.dumps({"type": "FeatureCollection", "features": features}))
    fetched_at = dt.datetime.now(dt.timezone.utc).isoformat()
    meta_path.write_text(json.dumps(
        {"fetched_at": fetched_at, "record_count": len(features), "bbox": bbox}, indent=2,
    ))

    print(f"\n✅ Saved {len(features)} features to {out_path}")
    print(f"   Metadata written to {meta_path}")
    print("\nRestart the API to use the real data.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Download FAA airspace GeoJSON.")
    parser.add_argument("--dataset", choices=sorted(DATASETS), default="facility_map")
    parser.add_argument("--max-records", type=int, default=2000, help="Maximum features to download.")
    parser.add_argument("--bbox", help="Limit to west,south,east,north in degrees, e.g. -122.7,37.1,-121.6,38.1")
    args = parser.parse_args()
    fetch(args.dataset, args.max_records, args.bbox)
