"""
Load SBA PPP public CSV shards into Postgres.

Usage:
  python scripts/etl/newsrc_load_ppp.py
  python scripts/etl/newsrc_load_ppp.py --truncate
"""
from __future__ import annotations

import argparse
import csv
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from db_config import get_connection

from newsrc_common import DEFAULT_SOURCE_ROOT, HeaderInjectStream, copy_stream_to_table, create_table_for_header


def parse_args():
    ap = argparse.ArgumentParser(description="Load PPP shard CSVs")
    ap.add_argument("--source-root", default=str(DEFAULT_SOURCE_ROOT))
    ap.add_argument("--table", default="newsrc_ppp_public_raw")
    ap.add_argument("--truncate", action="store_true")
    return ap.parse_args()


def main():
    args = parse_args()
    root = Path(args.source_root)
    files = sorted(root.glob("public_*_240930.csv"))
    if not files:
        raise SystemExit(f"No PPP shard files found in {root}")

    conn = get_connection()
    created = False
    cols = []
    try:
        for p in files:
            with open(p, "r", encoding="utf-8", errors="replace", newline="") as stream:
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
                    cur.execute(f"UPDATE {args.table} SET _source_file = %s WHERE _source_file IS NULL", [p.name])
                conn.commit()
            print(f"[ok] {p.name}")
    finally:
        conn.close()

    print(f"Done. files={len(files)} table={args.table}")


if __name__ == "__main__":
    main()
