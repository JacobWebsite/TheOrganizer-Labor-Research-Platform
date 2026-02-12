"""
Phase 5 Post-Matching Refresh

Run AFTER osha_match_phase5.py, whd_match_phase5.py, and match_990_national.py.

Steps:
  1. Re-aggregate WHD violation data onto F7/Mergent from whd_f7_matches
  2. Refresh ALL materialized views
  3. Refresh sector views
  4. Print match rate summary table
  5. Save baselines to match_rate_baselines table
  6. Run pytest

Usage: py scripts/etl/phase5_refresh.py
"""

import sys
import os
import subprocess
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from db_config import get_connection

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def ts():
    return datetime.now().strftime('%H:%M:%S')


def refresh_materialized_views(cur, conn):
    """Refresh all materialized views."""
    print(f"\n[{ts()}] Refreshing materialized views...")

    cur.execute("""
        SELECT matviewname FROM pg_matviews
        WHERE schemaname = 'public'
        ORDER BY matviewname
    """)
    views = [r[0] for r in cur.fetchall()]
    print(f"  Found {len(views)} materialized views")

    for view in views:
        print(f"    Refreshing {view}...", end=" ", flush=True)
        try:
            cur.execute(f"REFRESH MATERIALIZED VIEW {view}")
            conn.commit()
            print("OK")
        except Exception as e:
            conn.rollback()
            print(f"ERROR: {e}")

    print(f"  Done refreshing {len(views)} views.")


def refresh_sector_views(cur, conn):
    """Refresh sector-specific views if they exist."""
    print(f"\n[{ts()}] Refreshing sector views...")

    sector_views = []
    cur.execute("""
        SELECT matviewname FROM pg_matviews
        WHERE schemaname = 'public'
        AND (matviewname LIKE 'mv_sector%%' OR matviewname LIKE 'v_sector%%'
             OR matviewname LIKE 'mv_osha%%' OR matviewname LIKE 'mv_whd%%'
             OR matviewname LIKE 'mv_employer%%')
        ORDER BY matviewname
    """)
    sector_views = [r[0] for r in cur.fetchall()]

    if not sector_views:
        print("  No sector views found.")
        return

    for view in sector_views:
        print(f"    Refreshing {view}...", end=" ", flush=True)
        try:
            cur.execute(f"REFRESH MATERIALIZED VIEW {view}")
            conn.commit()
            print("OK")
        except Exception as e:
            conn.rollback()
            print(f"ERROR: {e}")


def save_baselines(cur, conn):
    """Save current match rates to baselines table."""
    print(f"\n[{ts()}] Saving match rate baselines...")

    cur.execute("""
        CREATE TABLE IF NOT EXISTS match_rate_baselines (
            id SERIAL PRIMARY KEY,
            source VARCHAR(50) NOT NULL,
            total_records INTEGER NOT NULL,
            matched_records INTEGER NOT NULL,
            match_rate NUMERIC(6,2) NOT NULL,
            snapshot_date DATE DEFAULT CURRENT_DATE,
            notes TEXT
        )
    """)
    conn.commit()

    # OSHA match rate
    cur.execute("SELECT COUNT(*) FROM osha_establishments")
    osha_total = cur.fetchone()[0]
    cur.execute("SELECT COUNT(DISTINCT establishment_id) FROM osha_f7_matches")
    osha_matched = cur.fetchone()[0]
    osha_rate = round(100 * osha_matched / osha_total, 2) if osha_total > 0 else 0

    # WHD match rate
    cur.execute("SELECT COUNT(*) FROM whd_cases")
    whd_total = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM whd_f7_matches")
    whd_matched = cur.fetchone()[0]
    whd_rate = round(100 * whd_matched / whd_total, 2) if whd_total > 0 else 0

    # 990 match rate
    cur.execute("SELECT COUNT(*) FROM national_990_filers")
    n990_total = cur.fetchone()[0]
    cur.execute("""
        SELECT COUNT(*) FROM national_990_f7_matches
    """)
    n990_matched = cur.fetchone()[0]
    n990_rate = round(100 * n990_matched / n990_total, 2) if n990_total > 0 else 0

    # Insert baselines
    for source, total, matched, rate in [
        ('OSHA', osha_total, osha_matched, osha_rate),
        ('WHD', whd_total, whd_matched, whd_rate),
        ('990_NATIONAL', n990_total, n990_matched, n990_rate),
    ]:
        cur.execute("""
            INSERT INTO match_rate_baselines (source, total_records, matched_records, match_rate, notes)
            VALUES (%s, %s, %s, %s, 'Phase 5 completion')
        """, (source, total, matched, rate))
    conn.commit()

    return {
        'osha': (osha_total, osha_matched, osha_rate),
        'whd': (whd_total, whd_matched, whd_rate),
        'n990': (n990_total, n990_matched, n990_rate),
    }


def print_match_summary(rates):
    """Print match rate summary table."""
    print("\n" + "=" * 70)
    print("PHASE 5 MATCH RATE SUMMARY")
    print("=" * 70)
    print(f"  {'Source':<20s} {'Total':>12s} {'Matched':>12s} {'Rate':>8s} {'Target':>8s} {'Status':>8s}")
    print(f"  {'-'*20} {'-'*12} {'-'*12} {'-'*8} {'-'*8} {'-'*8}")

    targets = {'osha': 15.0, 'whd': 10.0, 'n990': 2.0}
    labels = {'osha': 'OSHA Establishments', 'whd': 'WHD Cases', 'n990': '990 National'}

    for key in ['osha', 'whd', 'n990']:
        total, matched, rate = rates[key]
        target = targets[key]
        status = 'PASS' if rate >= target else 'MISS'
        print(f"  {labels[key]:<20s} {total:>12,} {matched:>12,} {rate:>7.1f}% {target:>7.1f}% {status:>8s}")

    print()


def print_method_breakdown(cur):
    """Print detailed method breakdown for each source."""
    print("OSHA Match Methods:")
    cur.execute("""
        SELECT match_method, COUNT(*) as cnt,
               ROUND(AVG(match_confidence)::numeric, 2)
        FROM osha_f7_matches
        GROUP BY match_method ORDER BY cnt DESC
    """)
    for row in cur.fetchall():
        print(f"  {row[0]:<25s} {row[1]:>10,}  avg_conf={row[2]}")

    print("\nWHD Match Methods:")
    cur.execute("""
        SELECT match_method, COUNT(*) as cnt,
               ROUND(AVG(match_confidence)::numeric, 2)
        FROM whd_f7_matches
        GROUP BY match_method ORDER BY cnt DESC
    """)
    for row in cur.fetchall():
        print(f"  {row[0]:<25s} {row[1]:>10,}  avg_conf={row[2]}")

    print("\n990 Match Methods:")
    cur.execute("""
        SELECT match_method, COUNT(*) as cnt,
               ROUND(AVG(match_confidence)::numeric, 2)
        FROM national_990_f7_matches
        GROUP BY match_method ORDER BY cnt DESC
    """)
    for row in cur.fetchall():
        print(f"  {row[0]:<25s} {row[1]:>10,}  avg_conf={row[2]}")


def run_tests():
    """Run pytest to validate results."""
    print(f"\n[{ts()}] Running tests...")
    test_path = os.path.join(PROJECT_ROOT, 'tests', 'test_data_integrity.py')
    result = subprocess.run(
        ['py', '-m', 'pytest', test_path, '-v', '--tb=short'],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True
    )
    print(result.stdout)
    if result.returncode != 0:
        print("STDERR:", result.stderr)
        print("WARNING: Some tests failed!")
    else:
        print("All tests passed!")
    return result.returncode


def main():
    print("=" * 70)
    print("PHASE 5 POST-MATCHING REFRESH")
    print(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 70)

    conn = get_connection()
    cur = conn.cursor()

    # Verify all 3 match tables exist
    for table in ['osha_f7_matches', 'whd_f7_matches', 'national_990_f7_matches']:
        cur.execute(f"SELECT COUNT(*) FROM {table}")
        count = cur.fetchone()[0]
        print(f"  {table}: {count:,} rows")
        if count == 0:
            print(f"  WARNING: {table} is empty! Run the matching script first.")

    # Refresh materialized views
    refresh_materialized_views(cur, conn)

    # Refresh sector views
    refresh_sector_views(cur, conn)

    # Save baselines
    rates = save_baselines(cur, conn)

    # Print summary
    print_match_summary(rates)
    print_method_breakdown(cur)

    conn.close()

    # Run tests
    run_tests()

    print(f"\nCompleted: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")


if __name__ == '__main__':
    main()
