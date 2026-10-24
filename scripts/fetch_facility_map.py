"""
scripts/fetch_facility_map.py — one-time download of the FAA UAS Facility Map GeoJSON.

Downloads to data/uasfm/facility_map.geojson and writes data/uasfm/meta.json
with a fetched_at timestamp.  After downloading, restart the API — it will
automatically use the real data instead of the fixture.

URL NOTE: The ArcGIS endpoint below is publicly referenced in FAA documentation.
Verify this URL against the current FAA ArcGIS service directory before use:
  https://uat.arcgis.com/arcgis/rest/services/FederalAviationAdministration/UASFM/FeatureServer

The full dataset can be large (>100 MB). This script downloads the first page
(resultRecordCount=2000) by default. Increase or loop pages as needed.

Usage:
    python scripts/fetch_facility_map.py
    python scripts/fetch_facility_map.py --max-records 5000
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

FAA_UASFM_URL = (
    "https://uat.arcgis.com/arcgis/rest/services/"
    "FederalAviationAdministration/UASFM/FeatureServer/0/query"
)


def fetch(max_records: int = 2000) -> None:
    out_dir = settings.DATA_UASFM_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "facility_map.geojson"
    meta_path = out_dir / "meta.json"

    params = {
        "where": "1=1",
        "outFields": "*",
        "f": "geojson",
        "resultRecordCount": max_records,
    }

    print(f"Downloading FAA UAS Facility Map (up to {max_records} records)...")
    print(f"URL: {FAA_UASFM_URL}")

    try:
        with httpx.Client(timeout=60) as client:
            r = client.get(FAA_UASFM_URL, params=params)
            r.raise_for_status()
    except httpx.HTTPError as exc:
        print(f"\n⚠️  Download failed: {exc}")
        print("The API will fall back to fixtures/uasfm_sample.geojson (2 SJC cells, status='stale').")
        sys.exit(1)

    data = r.json()
    features = data.get("features", [])
    if not features:
        print("⚠️  Response contained no features. Check the URL and try again.")
        sys.exit(1)

    # Print property names of first record
    first_props = list(features[0].get("properties", {}).keys())
    print(f"\nFirst record property names ({len(first_props)} fields):")
    for name in first_props:
        print(f"  {name}")

    # Save
    out_path.write_text(json.dumps(data, indent=2))
    fetched_at = dt.datetime.now(dt.timezone.utc).isoformat()
    meta_path.write_text(json.dumps({"fetched_at": fetched_at, "record_count": len(features)}, indent=2))

    print(f"\n✅ Saved {len(features)} cells to {out_path}")
    print(f"   Metadata written to {meta_path}")
    print("\nRestart the API to use the real data.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Download FAA UAS Facility Map GeoJSON.")
    parser.add_argument("--max-records", type=int, default=2000, help="Maximum features to download.")
    args = parser.parse_args()
    fetch(args.max_records)
