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
    # Health insurance (already in usa_00001 layout)
    "HCOVANY",
    "HCOVPRIV",
    "HINSCAID",
    "HINSCARE",
]

# Insurance vars that may or may not be in the layout
OPTIONAL_INSURANCE_VARS = ["HCOVPUB2", "HCOVSUB2"]


def parse_args():
    ap = argparse.ArgumentParser(description="Build ACS occupation-demographic profiles from IPUMS fixed-width file")
    ap.add_argument("--source-root", default=str(DEFAULT_SOURCE_ROOT))
    ap.add_argument("--data-file", default="usa_00001.dat")
    ap.add_argument("--layout-file", default="usa_00001.txt")
    ap.add_argument("--max-lines", type=int, default=0, help="Limit lines for test run (0=all)")
    ap.add_argument("--spill-keys", type=int, default=8_000_000,
                    help="Max in-memory groups before spilling to disk chunk (default 8M)")
    ap.add_argument("--skip-db", action="store_true")
    return ap.parse_args()


CSV_HEADER = [
    "sample", "year", "statefip", "met2013", "indnaics", "occsoc",
    "sex", "race", "hispan", "age_bucket", "educ", "classwkr", "weighted_count",
    "weighted_hcovany", "weighted_hcovpriv", "weighted_hinscaid",
    "weighted_hinscare", "weighted_hcovpub2", "weighted_hcovsub2",
]


def _spill_chunk(agg, out_dir: Path, chunk_idx: int) -> Path:
    """Write current accumulator to a numbered chunk CSV and clear it."""
    chunk_path = out_dir / f"acs_chunk_{chunk_idx:03d}.csv"
    with open(chunk_path, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        for k, vals in agg.items():
            w.writerow([*k] + [round(v, 4) for v in vals])
    print(f"  spilled chunk {chunk_idx} -> {chunk_path.name} ({len(agg):,} groups)")
    return chunk_path


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

    # Check optional insurance vars
    optional_found = [v for v in OPTIONAL_INSURANCE_VARS if v in specs]
    all_insurance_vars = ["HCOVANY", "HCOVPRIV", "HINSCAID", "HINSCARE"] + optional_found
    print(f"Insurance vars found: {all_insurance_vars}")

    out_dir = PROJECT_ROOT / "data" / "raw" / "ipums_acs"
    spill_dir = out_dir / "spill"
    spill_dir.mkdir(parents=True, exist_ok=True)
    # Wipe any pre-existing chunks from a prior run
    for old in spill_dir.glob("acs_chunk_*.csv"):
        old.unlink()

    # 7 accumulators: weighted_count + 6 insurance weighted sums
    agg = defaultdict(lambda: [0.0] * 7)
    rows = 0
    kept = 0
    chunk_idx = 0
    chunk_paths = []

    with open(data_path, "r", encoding="utf-8", errors="replace") as f:
        for line in f:
            rows += 1
            if args.max_lines and rows > args.max_lines:
                break
            if len(line) < 250:
                continue

            rec = {v: parse_val(line, specs[v]) for v in NEEDED_VARS}
            # Add optional insurance vars if present in layout
            for ov in optional_found:
                rec[ov] = parse_val(line, specs[ov])
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
            # Insurance flags (code "2" = has coverage, "1" = no coverage)
            has_any  = 1.0 if rec.get("HCOVANY") == "2" else 0.0
            has_priv = 1.0 if rec.get("HCOVPRIV") == "2" else 0.0
            has_caid = 1.0 if rec.get("HINSCAID") == "2" else 0.0
            has_care = 1.0 if rec.get("HINSCARE") == "2" else 0.0
            has_pub  = 1.0 if rec.get("HCOVPUB2", "1") == "2" else 0.0
            has_sub  = 1.0 if rec.get("HCOVSUB2", "1") == "2" else 0.0

            vals = agg[key]
            vals[0] += w
            vals[1] += w * has_any
            vals[2] += w * has_priv
            vals[3] += w * has_caid
            vals[4] += w * has_care
            vals[5] += w * has_pub
            vals[6] += w * has_sub
            kept += 1
            if kept % 2_000_000 == 0:
                print(f"processed rows={rows:,} kept={kept:,} groups={len(agg):,}")

            # Spill to disk when accumulator exceeds threshold
            if len(agg) >= args.spill_keys:
                chunk_paths.append(_spill_chunk(agg, spill_dir, chunk_idx))
                chunk_idx += 1
                agg.clear()

    # Final spill of remaining in-memory groups
    if agg:
        chunk_paths.append(_spill_chunk(agg, spill_dir, chunk_idx))
        chunk_idx += 1
        agg.clear()

    print(f"Spilled {len(chunk_paths)} chunk(s); total kept records={kept:,}")

    if args.skip_db:
        print("--skip-db set; chunks left at " + str(spill_dir))
        return

    conn = get_connection()
    try:
        with conn.cursor() as cur:
            # Final aggregated table
            cur.execute("DROP TABLE IF EXISTS newsrc_acs_occ_demo_profiles CASCADE")
            cur.execute(
                """
                CREATE TABLE newsrc_acs_occ_demo_profiles (
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
                    weighted_hcovany NUMERIC,
                    weighted_hcovpriv NUMERIC,
                    weighted_hinscaid NUMERIC,
                    weighted_hinscare NUMERIC,
                    weighted_hcovpub2 NUMERIC,
                    weighted_hcovsub2 NUMERIC,
                    _loaded_at TIMESTAMP DEFAULT NOW()
                )
                """
            )
            # Unlogged staging table for chunk COPY (faster, no WAL)
            cur.execute("DROP TABLE IF EXISTS staging_acs_chunks")
            cur.execute(
                """
                CREATE UNLOGGED TABLE staging_acs_chunks (
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
                    weighted_hcovany NUMERIC,
                    weighted_hcovpriv NUMERIC,
                    weighted_hinscaid NUMERIC,
                    weighted_hinscare NUMERIC,
                    weighted_hcovpub2 NUMERIC,
                    weighted_hcovsub2 NUMERIC
                )
                """
            )
            # Boost work_mem for the GROUP BY merge (Postgres caps at ~2GB-1)
            cur.execute("SET maintenance_work_mem = '1GB'")
            cur.execute("SET work_mem = '1GB'")

            for cp in chunk_paths:
                with open(cp, "r", encoding="utf-8", newline="") as fp:
                    cur.copy_expert(
                        """
                        COPY staging_acs_chunks
                        (sample, year, statefip, met2013, indnaics, occsoc, sex, race, hispan,
                         age_bucket, educ, classwkr, weighted_count,
                         weighted_hcovany, weighted_hcovpriv, weighted_hinscaid,
                         weighted_hinscare, weighted_hcovpub2, weighted_hcovsub2)
                        FROM STDIN WITH (FORMAT csv)
                        """,
                        fp,
                    )
                print(f"  COPY ok: {cp.name}")

            # Merge-aggregate chunks into final table (sums collapse partial group sums)
            cur.execute(
                """
                INSERT INTO newsrc_acs_occ_demo_profiles
                    (sample, year, statefip, met2013, indnaics, occsoc, sex, race, hispan,
                     age_bucket, educ, classwkr, weighted_count,
                     weighted_hcovany, weighted_hcovpriv, weighted_hinscaid,
                     weighted_hinscare, weighted_hcovpub2, weighted_hcovsub2)
                SELECT sample, year, statefip, met2013, indnaics, occsoc, sex, race, hispan,
                       age_bucket, educ, classwkr,
                       SUM(weighted_count),
                       SUM(weighted_hcovany), SUM(weighted_hcovpriv), SUM(weighted_hinscaid),
                       SUM(weighted_hinscare), SUM(weighted_hcovpub2), SUM(weighted_hcovsub2)
                FROM staging_acs_chunks
                GROUP BY 1,2,3,4,5,6,7,8,9,10,11,12
                """
            )
            cur.execute("DROP TABLE staging_acs_chunks")
            cur.execute("SELECT COUNT(*) FROM newsrc_acs_occ_demo_profiles")
            final_count = cur.fetchone()[0]
        conn.commit()
        print(f"Loaded newsrc_acs_occ_demo_profiles -> {final_count:,} groups")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
