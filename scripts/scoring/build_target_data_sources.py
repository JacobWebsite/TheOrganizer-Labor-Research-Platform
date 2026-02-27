"""
Build materialized view mv_target_data_sources.

Aggregates data source availability per non-union employer in master_employers.
Every non-union master row with data_quality_score >= 20 gets exactly one row
in the MV with boolean flags indicating which external data sources have matches
via master_employer_source_ids.

This is the foundation for the target scorecard (mv_target_scorecard).

Run:     py scripts/scoring/build_target_data_sources.py
Refresh: py scripts/scoring/build_target_data_sources.py --refresh
"""
import argparse
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
from db_config import get_connection
from scripts.scoring._pipeline_lock import pipeline_lock


MV_SQL = """
CREATE MATERIALIZED VIEW mv_target_data_sources AS
WITH
-- Pre-aggregate source systems per master_id
source_flags AS (
    SELECT
        master_id,
        bool_or(source_system = 'osha') AS has_osha,
        bool_or(source_system = 'whd') AS has_whd,
        bool_or(source_system = 'nlrb') AS has_nlrb,
        bool_or(source_system = '990') AS has_990,
        bool_or(source_system = 'sam') AS has_sam,
        bool_or(source_system = 'sec') AS has_sec,
        bool_or(source_system = 'gleif') AS has_gleif,
        bool_or(source_system = 'mergent') AS has_mergent,
        bool_or(source_system = 'bmf') AS has_bmf,
        bool_or(source_system = 'corpwatch') AS has_corpwatch,
        bool_or(source_system = 'f7') AS has_f7
    FROM master_employer_source_ids
    GROUP BY master_id
)
SELECT
    m.master_id,
    m.canonical_name,
    m.display_name,
    m.city,
    m.state,
    m.zip,
    m.naics,
    m.employee_count,
    m.employee_count_source,
    m.ein,
    m.is_public,
    m.is_federal_contractor,
    m.is_nonprofit,
    m.source_origin,
    m.data_quality_score,

    -- Source availability flags
    COALESCE(sf.has_osha, FALSE) AS has_osha,
    COALESCE(sf.has_whd, FALSE) AS has_whd,
    COALESCE(sf.has_nlrb, FALSE) AS has_nlrb,
    COALESCE(sf.has_990, FALSE) AS has_990,
    COALESCE(sf.has_sam, FALSE) AS has_sam,
    COALESCE(sf.has_sec, FALSE) AS has_sec,
    COALESCE(sf.has_gleif, FALSE) AS has_gleif,
    COALESCE(sf.has_mergent, FALSE) AS has_mergent,
    COALESCE(sf.has_bmf, FALSE) AS has_bmf,
    COALESCE(sf.has_corpwatch, FALSE) AS has_corpwatch,
    COALESCE(sf.has_f7, FALSE) AS has_f7,

    -- Source count (enforcement + data sources)
    (CASE WHEN COALESCE(sf.has_osha, FALSE) THEN 1 ELSE 0 END
     + CASE WHEN COALESCE(sf.has_whd, FALSE) THEN 1 ELSE 0 END
     + CASE WHEN COALESCE(sf.has_nlrb, FALSE) THEN 1 ELSE 0 END
     + CASE WHEN COALESCE(sf.has_990, FALSE) THEN 1 ELSE 0 END
     + CASE WHEN COALESCE(sf.has_sam, FALSE) THEN 1 ELSE 0 END
     + CASE WHEN COALESCE(sf.has_sec, FALSE) THEN 1 ELSE 0 END
     + CASE WHEN COALESCE(sf.has_gleif, FALSE) THEN 1 ELSE 0 END
     + CASE WHEN COALESCE(sf.has_mergent, FALSE) THEN 1 ELSE 0 END
     + CASE WHEN COALESCE(sf.has_bmf, FALSE) THEN 1 ELSE 0 END
     + CASE WHEN COALESCE(sf.has_corpwatch, FALSE) THEN 1 ELSE 0 END
    ) AS source_count

FROM master_employers m
LEFT JOIN source_flags sf ON sf.master_id = m.master_id
WHERE m.is_union = FALSE
  AND m.data_quality_score >= 20
"""


INDEX_SQL = [
    "CREATE UNIQUE INDEX IF NOT EXISTS idx_mv_tds_master_id ON mv_target_data_sources (master_id)",
    "CREATE INDEX IF NOT EXISTS idx_mv_tds_state ON mv_target_data_sources (state)",
    "CREATE INDEX IF NOT EXISTS idx_mv_tds_naics ON mv_target_data_sources (naics)",
    "CREATE INDEX IF NOT EXISTS idx_mv_tds_source_count ON mv_target_data_sources (source_count DESC)",
    "CREATE INDEX IF NOT EXISTS idx_mv_tds_source_origin ON mv_target_data_sources (source_origin)",
    "CREATE INDEX IF NOT EXISTS idx_mv_tds_employee_count ON mv_target_data_sources (employee_count) WHERE employee_count IS NOT NULL",
    "CREATE INDEX IF NOT EXISTS idx_mv_tds_has_osha ON mv_target_data_sources (master_id) WHERE has_osha",
    "CREATE INDEX IF NOT EXISTS idx_mv_tds_has_nlrb ON mv_target_data_sources (master_id) WHERE has_nlrb",
    "CREATE INDEX IF NOT EXISTS idx_mv_tds_has_whd ON mv_target_data_sources (master_id) WHERE has_whd",
    "CREATE INDEX IF NOT EXISTS idx_mv_tds_federal ON mv_target_data_sources (master_id) WHERE is_federal_contractor",
]


def _print_stats(cur):
    cur.execute("SELECT COUNT(*) FROM mv_target_data_sources")
    total = cur.fetchone()[0]
    print(f"  Total rows: {total:,}")

    cur.execute("SELECT COUNT(*) FROM master_employers WHERE is_union = FALSE AND data_quality_score >= 20")
    expected = cur.fetchone()[0]
    if total != expected:
        print(f"  WARNING: MV rows ({total:,}) != expected non-union masters ({expected:,})")
    else:
        print(f"  OK: Matches expected non-union master count ({expected:,})")

    print("\n  Source coverage:")
    for col in ['has_osha', 'has_whd', 'has_nlrb', 'has_990', 'has_sam',
                'has_sec', 'has_gleif', 'has_mergent', 'has_bmf', 'has_corpwatch']:
        cur.execute(f"SELECT COUNT(*) FROM mv_target_data_sources WHERE {col}")
        cnt = cur.fetchone()[0]
        pct = 100.0 * cnt / total if total > 0 else 0
        print(f"    {col:18s}: {cnt:>10,} ({pct:5.1f}%)")

    print("\n  Source count distribution:")
    cur.execute("""
        SELECT source_count, COUNT(*) AS cnt
        FROM mv_target_data_sources
        GROUP BY source_count
        ORDER BY source_count
    """)
    for row in cur.fetchall():
        pct = 100.0 * row[1] / total if total > 0 else 0
        print(f"    {row[0]} sources: {row[1]:>10,} ({pct:5.1f}%)")

    print("\n  Source origin distribution:")
    cur.execute("""
        SELECT source_origin, COUNT(*) AS cnt
        FROM mv_target_data_sources
        GROUP BY source_origin
        ORDER BY cnt DESC
    """)
    for row in cur.fetchall():
        pct = 100.0 * row[1] / total if total > 0 else 0
        print(f"    {row[0]:12s}: {row[1]:>10,} ({pct:5.1f}%)")

    cur.execute("SELECT COUNT(*) FROM mv_target_data_sources WHERE is_federal_contractor")
    fc = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM mv_target_data_sources WHERE is_nonprofit")
    np_cnt = cur.fetchone()[0]
    print(f"\n  Federal contractors: {fc:,}")
    print(f"  Nonprofits: {np_cnt:,}")

    return total


def create_mv(conn):
    cur = conn.cursor()

    print("Dropping old MV if exists...")
    cur.execute("DROP MATERIALIZED VIEW IF EXISTS mv_target_data_sources CASCADE")
    conn.commit()

    print("Creating mv_target_data_sources...")
    t0 = time.time()
    cur.execute(MV_SQL)
    conn.commit()
    print(f"  Created in {time.time() - t0:.1f}s")

    print("Creating indexes...")
    for sql in INDEX_SQL:
        cur.execute(sql)
    conn.commit()
    print("  Done.")

    print("\nVerification:")
    _print_stats(cur)


def refresh_mv(conn):
    conn.autocommit = True
    cur = conn.cursor()

    print("Refreshing mv_target_data_sources CONCURRENTLY...")
    t0 = time.time()
    cur.execute("REFRESH MATERIALIZED VIEW CONCURRENTLY mv_target_data_sources")
    print(f"  Refreshed in {time.time() - t0:.1f}s")

    print("\nVerification:")
    _print_stats(cur)


def main():
    parser = argparse.ArgumentParser(description="Create/refresh target data sources MV")
    parser.add_argument("--refresh", action="store_true", help="Refresh existing MV instead of recreating")
    args = parser.parse_args()

    conn = get_connection()
    conn.autocommit = False

    try:
        with pipeline_lock(conn, 'target_data_sources'):
            if args.refresh:
                refresh_mv(conn)
            else:
                create_mv(conn)
    except Exception as e:
        conn.rollback()
        print(f"ERROR: {e}")
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    main()
