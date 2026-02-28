"""
Drop raw newsrc_* staging tables to reclaim disk space.

These tables have already been transformed into curated cur_* tables.
Source files remain on disk for future reloads if needed.

Safety checks:
  - Verifies each corresponding cur_* table exists and has rows > 0
  - Requires --confirm flag (dry-run by default)
  - Reports table sizes before and after

Usage:
  python scripts/etl/newsrc_drop_raw_tables.py            # dry run
  python scripts/etl/newsrc_drop_raw_tables.py --confirm   # actually drop
"""
from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from db_config import get_connection


# Raw table -> curated table that must exist before dropping
RAW_TO_CURATED = {
    "newsrc_usaspending_contracts_raw": "cur_usaspending_recipient_rollup",
    "newsrc_lodes_od_2022": "cur_lodes_geo_metrics",
    "newsrc_lodes_rac_2022": "cur_lodes_geo_metrics",
    "newsrc_ppp_public_raw": "cur_ppp_employer_rollup",
    "newsrc_cb2300cbp_raw": None,  # unused duplicate CBP variant
    "newsrc_cbp2023_raw": "cur_cbp_geo_naics",
    "newsrc_lodes_xwalk_2022": "cur_lodes_geo_metrics",
    "newsrc_lodes_wac_2022": "cur_lodes_geo_metrics",
    "newsrc_form5500_all": "cur_form5500_sponsor_rollup",
    "newsrc_abs_raw": "cur_abs_geo_naics",
    "newsrc_acs_occ_demo_profiles": "cur_acs_workforce_demographics",
}


def _table_exists(cur, table_name: str) -> bool:
    cur.execute(
        "SELECT EXISTS(SELECT 1 FROM pg_tables WHERE tablename = %s) AS e",
        [table_name],
    )
    return cur.fetchone()[0]


def _row_count(cur, table_name: str) -> int:
    cur.execute(f"SELECT COUNT(*) FROM {table_name}")
    return cur.fetchone()[0]


def _table_size(cur, table_name: str) -> str:
    cur.execute("SELECT pg_size_pretty(pg_total_relation_size(%s))", [table_name])
    return cur.fetchone()[0]


def _table_size_bytes(cur, table_name: str) -> int:
    cur.execute("SELECT pg_total_relation_size(%s)", [table_name])
    return cur.fetchone()[0]


def _db_size(cur) -> str:
    cur.execute("SELECT pg_size_pretty(pg_database_size(current_database()))")
    return cur.fetchone()[0]


def main():
    ap = argparse.ArgumentParser(description="Drop raw newsrc_* staging tables")
    ap.add_argument("--confirm", action="store_true", help="Actually drop tables (default is dry-run)")
    args = ap.parse_args()

    conn = get_connection()
    cur = conn.cursor()

    print(f"Database size before: {_db_size(cur)}")
    print()

    # Safety checks
    errors = []
    to_drop = []

    for raw_table, cur_table in RAW_TO_CURATED.items():
        if not _table_exists(cur, raw_table):
            print(f"  [skip] {raw_table} -- does not exist")
            continue

        size = _table_size(cur, raw_table)
        size_bytes = _table_size_bytes(cur, raw_table)

        # Check curated table exists and has rows
        if cur_table:
            if not _table_exists(cur, cur_table):
                errors.append(f"BLOCKED: {raw_table} -> curated table {cur_table} does not exist!")
                continue
            cnt = _row_count(cur, cur_table)
            if cnt == 0:
                errors.append(f"BLOCKED: {raw_table} -> curated table {cur_table} has 0 rows!")
                continue
            print(f"  {raw_table} ({size}) -> {cur_table} ({cnt:,} rows) -- OK")
        else:
            print(f"  {raw_table} ({size}) -> (no curated dependency) -- OK")

        to_drop.append((raw_table, size, size_bytes))

    print()

    if errors:
        print("ERRORS (these tables will NOT be dropped):")
        for e in errors:
            print(f"  {e}")
        print()

    if not to_drop:
        print("Nothing to drop.")
        conn.close()
        return

    total_bytes = sum(b for _, _, b in to_drop)
    total_pretty = f"{total_bytes / (1024**3):.1f} GB"
    print(f"Tables to drop: {len(to_drop)}, estimated space: {total_pretty}")

    if not args.confirm:
        print("\nDRY RUN -- pass --confirm to actually drop these tables.")
        conn.close()
        return

    print("\nDropping tables...")
    for raw_table, size, _ in to_drop:
        cur.execute(f"DROP TABLE IF EXISTS {raw_table}")
        conn.commit()
        print(f"  Dropped {raw_table} ({size})")

    print(f"\nDatabase size after drops: {_db_size(cur)}")
    print("\nNote: Run VACUUM FULL to reclaim disk space (this locks tables and may take a while).")
    print("  psql -c 'VACUUM FULL;' olms_multiyear")

    conn.close()


if __name__ == "__main__":
    main()
