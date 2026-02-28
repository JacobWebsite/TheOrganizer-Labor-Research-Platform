"""
Load USAspending "All Contracts Full" zip bundles into Postgres.

Usage:
  python scripts/etl/newsrc_load_usaspending.py
  python scripts/etl/newsrc_load_usaspending.py --truncate
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
    copy_stream_to_table,
    create_table_for_header,
    iter_zip_csv_entries,
)


def parse_args():
    ap = argparse.ArgumentParser(description="Load USAspending contract CSV zips")
    ap.add_argument("--source-root", default=str(DEFAULT_SOURCE_ROOT))
    ap.add_argument("--table", default="newsrc_usaspending_contracts_raw")
    ap.add_argument("--truncate", action="store_true")
    return ap.parse_args()


def fiscal_year_from_name(name: str) -> str | None:
    m = re.search(r"FY(\d{4})", name, flags=re.IGNORECASE)
    return m.group(1) if m else None


def main():
    args = parse_args()
    root = Path(args.source_root)
    zips = sorted(root.glob("FY*_All_Contracts_Full_*.zip"))
    if not zips:
        raise SystemExit(f"No USAspending full zip files found in {root}")

    conn = get_connection()
    created = False
    cols = []
    loaded_entries = 0
    try:
        for zip_path in zips:
            fy = fiscal_year_from_name(zip_path.name)
            for entry_name, stream in iter_zip_csv_entries(zip_path):
                first_line = stream.readline()
                if not first_line:
                    continue
                header = next(csv.reader([first_line]))
                if not created:
                    cols = create_table_for_header(conn, args.table, header, truncate=args.truncate)
                    created = True

                replay = HeaderInjectStream(first_line, stream)
                copy_stream_to_table(conn, args.table, cols, replay, delimiter=",")
                with conn.cursor() as cur:
                    src = f"{zip_path.name}:{entry_name}"
                    if fy:
                        src = f"FY{fy}:{src}"
                    cur.execute(f"UPDATE {args.table} SET _source_file = %s WHERE _source_file IS NULL", [src])
                conn.commit()
                loaded_entries += 1
                print(f"[ok] {zip_path.name} :: {entry_name}")
    finally:
        conn.close()

    print(f"Done. zip_files={len(zips)} csv_entries={loaded_entries}")


if __name__ == "__main__":
    main()
