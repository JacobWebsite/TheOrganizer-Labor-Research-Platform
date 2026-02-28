"""
Load CBP .dat pipe-delimited files into Postgres.

Usage:
  python scripts/etl/newsrc_load_cbp.py
  python scripts/etl/newsrc_load_cbp.py --truncate
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
    ap = argparse.ArgumentParser(description="Load CBP dat files")
    ap.add_argument("--source-root", default=str(DEFAULT_SOURCE_ROOT))
    ap.add_argument("--truncate", action="store_true")
    return ap.parse_args()


def load_one(conn, path: Path, table: str, truncate: bool):
    with open(path, "r", encoding="utf-8", errors="replace", newline="") as stream:
        first_line = stream.readline()
        if not first_line:
            return
        if first_line.startswith("#"):
            first_line = first_line[1:]
        header = next(csv.reader([first_line], delimiter="|"))
        cols = create_table_for_header(conn, table, header, truncate=truncate)
        replay = HeaderInjectStream(first_line, stream)
        copy_stream_to_table(conn, table, cols, replay, delimiter="|")
        with conn.cursor() as cur:
            cur.execute(f"UPDATE {table} SET _source_file = %s WHERE _source_file IS NULL", [path.name])
        conn.commit()
    print(f"[ok] {path} -> {table}")


def main():
    args = parse_args()
    root = Path(args.source_root)

    file_map = {
        root / "CBP2023" / "CBP2023.dat": "newsrc_cbp2023_raw",
        root / "CB2300CBP" / "CB2300CBP.dat": "newsrc_cb2300cbp_raw",
    }

    conn = get_connection()
    try:
        for i, (path, table) in enumerate(file_map.items()):
            if not path.exists():
                print(f"[skip] missing {path}")
                continue
            load_one(conn, path, table, truncate=args.truncate and i == 0)
    finally:
        conn.close()

    print("Done.")


if __name__ == "__main__":
    main()
