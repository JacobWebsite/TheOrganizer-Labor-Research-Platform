"""
Fetch TIGER 2022 NY geography shapefiles and NYC NTA boundaries for the
LODES commute-shed mapping analysis.

Outputs everything to:
  New Data sources 2_27/tiger_2022_ny/
    tl_2022_36_tract/      (~4,900 tract polygons)
    tl_2022_36_county/     (62 NY county polygons)
    tl_2022_36_cousub/     (towns/villages/townships)
    nynta2020.geojson      (~260 NYC Neighborhood Tabulation Areas)

No postgres load; geopandas reads the shapefiles directly.

Usage:
  py scripts/etl/load_tiger_geography_ny.py
"""
from __future__ import annotations

import io
import os
import sys
import zipfile
from pathlib import Path
from urllib.request import Request, urlopen

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from newsrc_common import DEFAULT_SOURCE_ROOT  # noqa: E402


TARGETS = [
    (
        "tl_2022_36_tract",
        "https://www2.census.gov/geo/tiger/TIGER2022/TRACT/tl_2022_36_tract.zip",
    ),
    (
        "tl_2022_36_county",
        "https://www2.census.gov/geo/tiger/TIGER2022/COUNTY/tl_2022_us_county.zip",
    ),
    (
        "tl_2022_36_cousub",
        "https://www2.census.gov/geo/tiger/TIGER2022/COUSUB/tl_2022_36_cousub.zip",
    ),
]

NTA_GEOJSON_URL = (
    "https://data.cityofnewyork.us/api/geospatial/9nt8-h7nd?method=export&format=GeoJSON"
)


def download(url: str, timeout: int = 120) -> bytes:
    req = Request(url, headers={"User-Agent": "LaborDataTerminal/1.0 (LODES analysis)"})
    print(f"  GET {url}")
    with urlopen(req, timeout=timeout) as resp:
        return resp.read()


def extract_zip(blob: bytes, dest_dir: Path):
    dest_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(io.BytesIO(blob)) as zf:
        zf.extractall(dest_dir)


def main():
    out_root = Path(DEFAULT_SOURCE_ROOT) / "tiger_2022_ny"
    out_root.mkdir(parents=True, exist_ok=True)

    for name, url in TARGETS:
        dest = out_root / name
        shp = dest / f"{name}.shp"
        if shp.exists():
            print(f"[skip] {name} already present")
            continue
        blob = download(url)
        extract_zip(blob, dest)
        print(f"[ok]   {name} -> {dest}")

    nta_dest = out_root / "nynta2020.geojson"
    if nta_dest.exists():
        print("[skip] nynta2020.geojson already present")
    else:
        blob = download(NTA_GEOJSON_URL)
        nta_dest.write_bytes(blob)
        print(f"[ok]   nynta2020.geojson -> {nta_dest} ({len(blob):,} bytes)")

    print("\nContents of tiger_2022_ny/:")
    for p in sorted(out_root.rglob("*")):
        if p.is_file() and p.suffix.lower() in (".shp", ".geojson"):
            print(f"  {p.relative_to(out_root)}  ({p.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()
