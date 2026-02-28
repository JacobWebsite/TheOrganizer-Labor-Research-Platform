"""
Load Census Annual Business Survey (ABS) CSV files into Postgres.

Source: ABS_latest_state_local/csv/ folder containing 17 CSV files.
Filename pattern: ABS_{year}_{dataset}_{geo_level}.csv
  - dataset: abscs (size), abscb (characteristics), abscbo (owner demographics), absmcb (micro characteristics)
  - geo_level: us, state, county, msa_micro, congressional_district

All files go into a single table ``newsrc_abs_raw`` with metadata columns
parsed from the filename: abs_vintage, abs_dataset, abs_geo_level.

Because files have different schemas (10-13 columns depending on dataset and
geo_level), the table is created with the union of ALL headers across all files.
Each file only COPYs its own columns.

Usage:
  python scripts/etl/newsrc_load_abs.py
  python scripts/etl/newsrc_load_abs.py --truncate
"""
from __future__ import annotations

import argparse
import csv
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from db_config import get_connection

from newsrc_common import (
    DEFAULT_SOURCE_ROOT,
    HeaderInjectStream,
    create_table_for_header,
    copy_stream_to_table,
    sanitize_column_names,
    quote_ident,
)

TABLE = "newsrc_abs_raw"

# Pattern: ABS_2023_abscs_state.csv
FILENAME_RE = re.compile(
    r"ABS_(\d{4})_([a-z]+)_(.+)\.csv$", re.IGNORECASE
)


def parse_args():
    ap = argparse.ArgumentParser(description="Load ABS CSV files")
    ap.add_argument("--source-root", default=str(DEFAULT_SOURCE_ROOT))
    ap.add_argument("--table", default=TABLE)
    ap.add_argument("--truncate", action="store_true")
    return ap.parse_args()


def parse_filename_meta(fname: str) -> dict:
    """Extract vintage, dataset, geo_level from ABS filename."""
    m = FILENAME_RE.search(fname)
    if not m:
        return {"abs_vintage": None, "abs_dataset": None, "abs_geo_level": None}
    return {
        "abs_vintage": m.group(1),
        "abs_dataset": m.group(2),
        "abs_geo_level": m.group(3),
    }


def _read_header(path: Path) -> list[str]:
    """Read and return the CSV header from a file."""
    with open(path, "r", encoding="utf-8-sig", errors="replace", newline="") as f:
        first_line = f.readline()
        if not first_line:
            return []
        return next(csv.reader([first_line]))


def main():
    args = parse_args()
    root = Path(args.source_root)
    csv_dir = root / "ABS_latest_state_local" / "csv"
    if not csv_dir.is_dir():
        raise SystemExit(f"ABS csv directory not found: {csv_dir}")

    files = sorted(csv_dir.glob("ABS_*.csv"))
    if not files:
        raise SystemExit(f"No ABS CSV files found in {csv_dir}")

    # Phase 1: Scan all files to build the superset of columns
    print(f"Scanning {len(files)} files for column union...")
    all_raw_cols: list[str] = []
    seen_cols: set[str] = set()
    file_headers: dict[str, list[str]] = {}  # path.name -> raw header

    for p in files:
        raw_header = _read_header(p)
        file_headers[p.name] = raw_header
        for col in raw_header:
            sanitized = sanitize_column_names([col])[0]
            if sanitized not in seen_cols:
                seen_cols.add(sanitized)
                all_raw_cols.append(col)

    # Add metadata columns
    extra_cols = ["abs_vintage", "abs_dataset", "abs_geo_level"]
    superset_header = all_raw_cols + extra_cols
    print(f"  Superset: {len(superset_header)} columns (from {len(all_raw_cols)} data + {len(extra_cols)} metadata)")

    # Phase 2: Create table with superset schema
    conn = get_connection()
    loaded = 0

    try:
        # DROP existing table when --truncate since schema may have changed
        # (ABS files have varying columns; table must match the superset)
        if args.truncate:
            with conn.cursor() as cur:
                cur.execute(f"DROP TABLE IF EXISTS {quote_ident(args.table)}")
            conn.commit()

        all_cols = create_table_for_header(conn, args.table, superset_header, truncate=False)

        # Phase 3: Load each file using only its own columns
        for p in files:
            meta = parse_filename_meta(p.name)
            raw_header = file_headers[p.name]
            if not raw_header:
                continue

            # Get the sanitized column names for THIS file only
            file_cols = sanitize_column_names(raw_header)

            with open(p, "r", encoding="utf-8-sig", errors="replace", newline="") as stream:
                first_line = stream.readline()
                if not first_line:
                    continue

                replay = HeaderInjectStream(first_line, stream)
                copy_stream_to_table(conn, args.table, file_cols, replay, delimiter=",")

                # Set metadata columns for rows just loaded
                with conn.cursor() as cur:
                    cur.execute(
                        f"""UPDATE {quote_ident(args.table)}
                            SET _source_file = %s,
                                abs_vintage = %s,
                                abs_dataset = %s,
                                abs_geo_level = %s
                            WHERE _source_file IS NULL""",
                        [p.name, meta["abs_vintage"], meta["abs_dataset"], meta["abs_geo_level"]],
                    )
                conn.commit()
            loaded += 1
            print(f"[ok] {p.name}  dataset={meta['abs_dataset']}  geo={meta['abs_geo_level']}  cols={len(file_cols)}")
    finally:
        conn.close()

    print(f"Done. files={loaded} table={args.table}")


if __name__ == "__main__":
    main()
