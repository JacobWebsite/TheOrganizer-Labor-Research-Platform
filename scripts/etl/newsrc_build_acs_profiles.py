"""
Build ACS occupation x demographic profiles from IPUMS fixed-width extract.

Input files expected in New Data sources 2_27:
  - usa_00001.dat (fixed-width data)
  - usa_00001.txt (IPUMS command/layout file)

Output:
  - CSV summary at data/raw/ipums_acs/acs_occ_demo_profiles.csv
  - Optional DB table: newsrc_acs_occ_demo_profiles

Usage:
  python scripts/etl/newsrc_build_acs_profiles.py
  python scripts/etl/newsrc_build_acs_profiles.py --max-lines 2000000
  python scripts/etl/newsrc_build_acs_profiles.py --skip-db
"""
from __future__ import annotations

import argparse
import csv
import os
import re
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from db_config import get_connection

from newsrc_common import DEFAULT_SOURCE_ROOT, PROJECT_ROOT


NEEDED_VARS = [
    "YEAR",
    "SAMPLE",
    "PERWT",
    "STATEFIP",
    "MET2013",
    "AGE",
    "SEX",
    "RACE",
    "HISPAN",
    "EDUC",
    "LABFORCE",
    "CLASSWKR",
    "OCCSOC",
    "INDNAICS",
]


def parse_args():
    ap = argparse.ArgumentParser(description="Build ACS occupation-demographic profiles from IPUMS fixed-width file")
    ap.add_argument("--source-root", default=str(DEFAULT_SOURCE_ROOT))
    ap.add_argument("--data-file", default="usa_00001.dat")
    ap.add_argument("--layout-file", default="usa_00001.txt")
    ap.add_argument("--max-lines", type=int, default=0, help="Limit lines for test run (0=all)")
    ap.add_argument("--skip-db", action="store_true")
    return ap.parse_args()


def parse_layout_specs(layout_path: Path):
    """
    Parse lines like:
      YEAR        1-4
      PERWT       160-169 (2)
    into zero-based slice specs.
    """
    specs = {}
    rx = re.compile(r"^\s*([A-Z0-9_]+)\s+(\d+)-(\d+)")
    with open(layout_path, "r", encoding="utf-8", errors="replace") as f:
        for line in f:
            m = rx.match(line)
            if not m:
                continue
            var = m.group(1)
            start = int(m.group(2)) - 1
            end = int(m.group(3))
            specs[var] = (start, end)
    return specs


def parse_val(line: str, spec):
    s, e = spec
    return line[s:e].strip()


def age_bucket(age: str) -> str:
    try:
        a = int(age)
    except Exception:
        return "unknown"
    if a < 25:
        return "u25"
    if a < 35:
        return "25_34"
    if a < 45:
        return "35_44"
    if a < 55:
        return "45_54"
    if a < 65:
        return "55_64"
    return "65p"


def main():
    args = parse_args()
    root = Path(args.source_root)
    data_path = root / args.data_file
    layout_path = root / args.layout_file
    # Handle nested directory case: usa_00001.dat/usa_00001.dat
    if data_path.is_dir() and (data_path / data_path.name).is_file():
        data_path = data_path / data_path.name
    if not data_path.exists() or not data_path.is_file():
        raise SystemExit(f"Missing data file: {data_path}")
    if not layout_path.exists():
        raise SystemExit(f"Missing layout file: {layout_path}")

    specs = parse_layout_specs(layout_path)
    missing = [v for v in NEEDED_VARS if v not in specs]
    if missing:
        raise SystemExit(f"Layout missing required vars: {missing}")

    agg = defaultdict(float)
    rows = 0
    kept = 0

    with open(data_path, "r", encoding="utf-8", errors="replace") as f:
        for line in f:
            rows += 1
            if args.max_lines and rows > args.max_lines:
                break
            if len(line) < 250:
                continue

            rec = {v: parse_val(line, specs[v]) for v in NEEDED_VARS}
            if rec["LABFORCE"] not in {"1", "2"}:
                continue
            if rec["OCCSOC"] in {"", "000000", "0000"}:
                continue

            try:
                w = float(rec["PERWT"]) / 100.0 if rec["PERWT"] else 0.0
            except Exception:
                w = 0.0
            if w <= 0:
                continue

            key = (
                rec["SAMPLE"],
                rec["YEAR"],
                rec["STATEFIP"],
                rec["MET2013"],
                rec["INDNAICS"],
                rec["OCCSOC"],
                rec["SEX"],
                rec["RACE"],
                rec["HISPAN"],
                age_bucket(rec["AGE"]),
                rec["EDUC"],
                rec["CLASSWKR"],
            )
            agg[key] += w
            kept += 1
            if kept % 2_000_000 == 0:
                print(f"processed rows={rows:,} kept={kept:,} groups={len(agg):,}")

    out_dir = PROJECT_ROOT / "data" / "raw" / "ipums_acs"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_csv = out_dir / "acs_occ_demo_profiles.csv"

    with open(out_csv, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow([
            "sample", "year", "statefip", "met2013", "indnaics", "occsoc",
            "sex", "race", "hispan", "age_bucket", "educ", "classwkr", "weighted_count",
        ])
        for k, v in agg.items():
            w.writerow([*k, round(v, 4)])

    print(f"Wrote {out_csv} groups={len(agg):,}")

    if args.skip_db:
        return

    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS newsrc_acs_occ_demo_profiles (
                    sample TEXT,
                    year TEXT,
                    statefip TEXT,
                    met2013 TEXT,
                    indnaics TEXT,
                    occsoc TEXT,
                    sex TEXT,
                    race TEXT,
                    hispan TEXT,
                    age_bucket TEXT,
                    educ TEXT,
                    classwkr TEXT,
                    weighted_count NUMERIC,
                    _loaded_at TIMESTAMP DEFAULT NOW()
                )
                """
            )
            cur.execute("TRUNCATE newsrc_acs_occ_demo_profiles")
            with open(out_csv, "r", encoding="utf-8", newline="") as fp:
                cur.copy_expert(
                    """
                    COPY newsrc_acs_occ_demo_profiles
                    (sample, year, statefip, met2013, indnaics, occsoc, sex, race, hispan,
                     age_bucket, educ, classwkr, weighted_count)
                    FROM STDIN WITH (FORMAT csv, HEADER true)
                    """,
                    fp,
                )
        conn.commit()
        print("Loaded newsrc_acs_occ_demo_profiles")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
