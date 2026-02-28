"""
Load Form 5500 bulk files from New Data sources bundle into Postgres.

Only loads the main F_5500 filings (not SF, not schedule files) since those
contain the sponsor/plan data needed by the curated layer. Different years
have different column counts (130-140), so we scan all files first to build
a superset schema.

Usage:
  python scripts/etl/newsrc_load_form5500.py
  python scripts/etl/newsrc_load_form5500.py --truncate
"""
from __future__ import annotations

import argparse
import csv
import io
import os
import re
import sys
import zipfile
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

# Only load main F_5500 filings (not F_5500_SF, F_SCH_C/H/I/R)
MAIN_FILING_RE = re.compile(r"^F_5500_\d{4}_All\.zip$", re.IGNORECASE)


def parse_args():
    ap = argparse.ArgumentParser(description="Load Form 5500 bulk zip CSVs")
    ap.add_argument("--source-root", default=str(DEFAULT_SOURCE_ROOT))
    ap.add_argument("--subdir", default="Form5500_bulk")
    ap.add_argument("--table", default="newsrc_form5500_all")
    ap.add_argument("--truncate", action="store_true")
    return ap.parse_args()


def _read_zip_header(zip_path: Path) -> list[str]:
    """Read CSV header from the first CSV entry in a zip file."""
    with zipfile.ZipFile(zip_path, "r") as zf:
        for name in zf.namelist():
            if name.lower().endswith(".csv"):
                with zf.open(name, "r") as raw:
                    ts = io.TextIOWrapper(raw, encoding="utf-8", errors="replace", newline="")
                    line = ts.readline()
                    if line:
                        return next(csv.reader([line]))
    return []


def main():
    args = parse_args()
    src = Path(args.source_root) / args.subdir
    zips = sorted(p for p in src.glob("*.zip") if MAIN_FILING_RE.match(p.name))
    if not zips:
        raise SystemExit(f"No main F_5500 zip files found in {src}")

    print(f"Found {len(zips)} main F_5500 zip files")

    # Phase 1: Scan all files to build superset header
    print("Scanning all files for column union...")
    all_raw_cols: list[str] = []
    seen_cols: set[str] = set()
    file_headers: dict[str, list[str]] = {}

    for zp in zips:
        raw_header = _read_zip_header(zp)
        file_headers[zp.name] = raw_header
        for col in raw_header:
            sanitized = sanitize_column_names([col])[0]
            if sanitized not in seen_cols:
                seen_cols.add(sanitized)
                all_raw_cols.append(col)

    superset_header = all_raw_cols
    print(f"  Superset: {len(superset_header)} columns")

    # Phase 2: Create table with superset schema
    conn = get_connection()
    loaded = 0

    try:
        if args.truncate:
            with conn.cursor() as cur:
                cur.execute(f"DROP TABLE IF EXISTS {quote_ident(args.table)}")
            conn.commit()

        create_table_for_header(conn, args.table, superset_header, truncate=False)

        # Phase 3: Load each zip
        for zp in zips:
            raw_header = file_headers[zp.name]
            if not raw_header:
                continue
            file_cols = sanitize_column_names(raw_header)

            with zipfile.ZipFile(zp, "r") as zf:
                for name in zf.namelist():
                    if not name.lower().endswith(".csv"):
                        continue
                    with zf.open(name, "r") as raw:
                        stream = io.TextIOWrapper(raw, encoding="utf-8", errors="replace", newline="")
                        first_line = stream.readline()
                        if not first_line:
                            continue
                        replay = HeaderInjectStream(first_line, stream)
                        copy_stream_to_table(conn, args.table, file_cols, replay, delimiter=",")

                        with conn.cursor() as cur:
                            cur.execute(
                                f"UPDATE {quote_ident(args.table)} SET _source_file = %s WHERE _source_file IS NULL",
                                [f"{zp.name}:{name}"],
                            )
                        conn.commit()
            loaded += 1
            print(f"[ok] {zp.name}  cols={len(file_cols)}")
    finally:
        conn.close()

    print(f"Done. zip_files={loaded} table={args.table}")


if __name__ == "__main__":
    main()
