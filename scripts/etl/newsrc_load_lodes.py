"""
Load LODES bulk .csv.gz files into Postgres.

Usage:
  python scripts/etl/newsrc_load_lodes.py
  python scripts/etl/newsrc_load_lodes.py --truncate
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
    open_gzip_text,
)


PATTERNS = {
    "wac": re.compile(r"^[a-z]{2}_wac_"),
    "rac": re.compile(r"^[a-z]{2}_rac_"),
    "od": re.compile(r"^[a-z]{2}_od_(main|aux)_"),
    "xwalk": re.compile(r"^[a-z]{2}_xwalk\.csv\.gz$"),
}


def parse_args():
    ap = argparse.ArgumentParser(description="Load LODES .csv.gz files")
    ap.add_argument("--source-root", default=str(DEFAULT_SOURCE_ROOT))
    ap.add_argument("--subdir", default="LODES_bulk_2022")
    ap.add_argument("--truncate", action="store_true")
    return ap.parse_args()


def classify(name: str) -> str | None:
    for key, rx in PATTERNS.items():
        if rx.search(name):
            return key
    return None


def main():
    args = parse_args()
    src = Path(args.source_root) / args.subdir
    files = sorted(src.glob("*.csv.gz"))
    if not files:
        raise SystemExit(f"No .csv.gz files found in {src}")

    table_map = {
        "wac": "newsrc_lodes_wac_2022",
        "rac": "newsrc_lodes_rac_2022",
        "od": "newsrc_lodes_od_2022",
        "xwalk": "newsrc_lodes_xwalk_2022",
    }

    conn = get_connection()
    created = {}
    columns = {}
    counts = {v: 0 for v in table_map.values()}
    errors = []
    try:
        for p in files:
            kind = classify(p.name)
            if not kind:
                continue
            table = table_map[kind]
            try:
                with open_gzip_text(p) as stream:
                    first_line = stream.readline()
                    if not first_line:
                        continue
                    header = next(csv.reader([first_line]))
                    if table not in created:
                        cols = create_table_for_header(conn, table, header, truncate=args.truncate and table not in created)
                        columns[table] = cols
                        created[table] = True
                    replay = HeaderInjectStream(first_line, stream)
                    copy_stream_to_table(conn, table, columns[table], replay, delimiter=",")
                    with conn.cursor() as cur:
                        cur.execute(f"UPDATE {table} SET _source_file = %s WHERE _source_file IS NULL", [p.name])
                    conn.commit()
                counts[table] += 1
                print(f"[ok] {p.name} -> {table}")
            except Exception as exc:
                conn.rollback()
                errors.append(p.name)
                print(f"[ERR] {p.name}: {exc}")
    finally:
        conn.close()

    print("Done.")
    for tbl, n in counts.items():
        print(f"  {tbl}: files={n}")
    if errors:
        print(f"  ERRORS: {len(errors)} files skipped (corrupt/truncated gz)")


if __name__ == "__main__":
    main()
