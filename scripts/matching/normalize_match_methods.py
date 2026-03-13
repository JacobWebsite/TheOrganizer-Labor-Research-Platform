"""
Normalize match_method values to UPPER case across all match tables.

Fixes case-inconsistent values like 'name_state_exact' vs 'NAME_STATE_EXACT'.

Run:
    py scripts/matching/normalize_match_methods.py             # dry-run
    py scripts/matching/normalize_match_methods.py --commit    # apply changes
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from db_config import get_connection


TABLES = [
    "unified_match_log",
    "osha_f7_matches",
    "whd_f7_matches",
    "sam_f7_matches",
    "national_990_f7_matches",
]


def report_case_issues(conn):
    """Report rows with lowercase match_method values per table."""
    results = {}
    with conn.cursor() as cur:
        for table in TABLES:
            cur.execute(
                f"SELECT match_method, COUNT(*) AS cnt "
                f"FROM {table} "
                f"WHERE match_method != UPPER(match_method) "
                f"GROUP BY match_method ORDER BY cnt DESC"
            )
            rows = cur.fetchall()
            results[table] = rows
    return results


def normalize_table(conn, table, commit=False):
    """Normalize match_method to UPPER for a single table. Returns affected count."""
    with conn.cursor() as cur:
        cur.execute(
            f"SELECT COUNT(*) FROM {table} "
            f"WHERE match_method != UPPER(match_method)"
        )
        count = cur.fetchone()[0]

        if count > 0 and commit:
            cur.execute(
                f"UPDATE {table} SET match_method = UPPER(match_method) "
                f"WHERE match_method != UPPER(match_method)"
            )
            conn.commit()
        elif not commit:
            conn.rollback()

    return count


def main():
    parser = argparse.ArgumentParser(description="Normalize match_method to UPPER")
    parser.add_argument("--commit", action="store_true", help="Apply changes (default is dry-run)")
    args = parser.parse_args()

    conn = get_connection()

    print("=== Match Method Case Report ===\n")
    issues = report_case_issues(conn)

    total_affected = 0
    for table, rows in issues.items():
        if rows:
            print(f"  {table}:")
            for method, cnt in rows:
                print(f"    {method} -> {method.upper()}  ({cnt} rows)")
                total_affected += cnt
        else:
            print(f"  {table}: all UPPER (OK)")
    print()

    if total_affected == 0:
        print("Nothing to normalize.")
        conn.close()
        return

    if not args.commit:
        print(f"DRY RUN: {total_affected} rows would be updated. Use --commit to apply.")
        conn.close()
        return

    print(f"Normalizing {total_affected} rows across {len(TABLES)} tables...\n")
    for table in TABLES:
        count = normalize_table(conn, table, commit=True)
        if count:
            print(f"  {table}: {count} rows updated")

    # Verify
    print("\n=== Post-normalization verification ===\n")
    issues_after = report_case_issues(conn)
    remaining = sum(len(rows) for rows in issues_after.values())
    if remaining == 0:
        print("  All match_method values are UPPER. OK.")
    else:
        print(f"  WARNING: {remaining} distinct values still lowercase!")

    conn.close()


if __name__ == "__main__":
    main()
