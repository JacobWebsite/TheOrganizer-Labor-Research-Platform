"""
Build materialized view mv_employer_data_sources.

Aggregates data source availability per F7 employer, providing the
foundation for the E3 unified scorecard. Every f7_employers_deduped
row gets exactly one row in the MV with boolean flags indicating
which external data sources have matches.

Run:     py scripts/scoring/build_employer_data_sources.py
Refresh: py scripts/scoring/build_employer_data_sources.py --refresh
"""
import sys
import os
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
from db_config import get_connection


MV_SQL = """
CREATE MATERIALIZED VIEW mv_employer_data_sources AS
WITH
-- Pre-aggregate unified_match_log by (target_id, source_system) for active matches
uml_sources AS (
    SELECT target_id,
           bool_or(source_system = 'nlrb') AS has_nlrb,
           bool_or(source_system = 'sec') AS has_sec,
           bool_or(source_system = 'gleif') AS has_gleif,
           bool_or(source_system = 'mergent') AS has_mergent
    FROM unified_match_log
    WHERE status = 'active'
      AND source_system IN ('nlrb', 'sec', 'gleif', 'mergent')
    GROUP BY target_id
),
-- Legacy match tables: one boolean per F7 employer
osha_matched AS (
    SELECT DISTINCT f7_employer_id FROM osha_f7_matches
),
whd_matched AS (
    SELECT DISTINCT f7_employer_id FROM whd_f7_matches
),
n990_matched AS (
    SELECT DISTINCT f7_employer_id FROM national_990_f7_matches
),
sam_matched AS (
    SELECT DISTINCT f7_employer_id FROM sam_f7_matches
)

SELECT
    -- Core identity
    e.employer_id,
    e.employer_name,
    e.state,
    e.city,
    e.naics,
    e.naics_detailed,
    e.latest_unit_size,
    e.latest_union_fnum,
    e.latest_union_name,
    e.is_historical,
    e.canonical_group_id,
    e.is_canonical_rep,

    -- Source availability flags
    (om.f7_employer_id IS NOT NULL) AS has_osha,
    COALESCE(u.has_nlrb, FALSE) AS has_nlrb,
    (wm.f7_employer_id IS NOT NULL) AS has_whd,
    (nm.f7_employer_id IS NOT NULL) AS has_990,
    (sm.f7_employer_id IS NOT NULL) AS has_sam,
    COALESCE(u.has_sec, FALSE) AS has_sec,
    COALESCE(u.has_gleif, FALSE) AS has_gleif,
    COALESCE(u.has_mergent, FALSE) AS has_mergent,

    -- Source count
    (CASE WHEN om.f7_employer_id IS NOT NULL THEN 1 ELSE 0 END
     + CASE WHEN COALESCE(u.has_nlrb, FALSE) THEN 1 ELSE 0 END
     + CASE WHEN wm.f7_employer_id IS NOT NULL THEN 1 ELSE 0 END
     + CASE WHEN nm.f7_employer_id IS NOT NULL THEN 1 ELSE 0 END
     + CASE WHEN sm.f7_employer_id IS NOT NULL THEN 1 ELSE 0 END
     + CASE WHEN COALESCE(u.has_sec, FALSE) THEN 1 ELSE 0 END
     + CASE WHEN COALESCE(u.has_gleif, FALSE) THEN 1 ELSE 0 END
     + CASE WHEN COALESCE(u.has_mergent, FALSE) THEN 1 ELSE 0 END
    ) AS source_count,

    -- Corporate crosswalk (denormalized)
    cw.corporate_family_id,
    cw.sec_cik,
    cw.gleif_lei,
    cw.mergent_duns,
    cw.ein,
    cw.ticker,
    cw.is_public,
    cw.is_federal_contractor,
    cw.federal_obligations,
    cw.federal_contract_count

FROM f7_employers_deduped e

LEFT JOIN osha_matched om ON om.f7_employer_id = e.employer_id
LEFT JOIN whd_matched wm ON wm.f7_employer_id = e.employer_id
LEFT JOIN n990_matched nm ON nm.f7_employer_id = e.employer_id
LEFT JOIN sam_matched sm ON sm.f7_employer_id = e.employer_id
LEFT JOIN uml_sources u ON u.target_id = e.employer_id

-- Corporate crosswalk: pick the best row per employer (highest federal_obligations)
LEFT JOIN LATERAL (
    SELECT corporate_family_id, sec_cik, gleif_lei, mergent_duns,
           ein, ticker, is_public, is_federal_contractor,
           federal_obligations, federal_contract_count
    FROM corporate_identifier_crosswalk
    WHERE f7_employer_id = e.employer_id
    ORDER BY federal_obligations DESC NULLS LAST
    LIMIT 1
) cw ON TRUE
"""


INDEX_SQL = [
    "CREATE UNIQUE INDEX IF NOT EXISTS idx_mv_eds_employer_id ON mv_employer_data_sources (employer_id)",
    "CREATE INDEX IF NOT EXISTS idx_mv_eds_state ON mv_employer_data_sources (state)",
    "CREATE INDEX IF NOT EXISTS idx_mv_eds_source_count ON mv_employer_data_sources (source_count)",
    "CREATE INDEX IF NOT EXISTS idx_mv_eds_naics ON mv_employer_data_sources (naics)",
    "CREATE INDEX IF NOT EXISTS idx_mv_eds_has_osha ON mv_employer_data_sources (employer_id) WHERE has_osha",
]


def _print_stats(cur):
    """Print verification stats."""
    cur.execute("SELECT COUNT(*) FROM mv_employer_data_sources")
    total = cur.fetchone()[0]
    print(f"  Total rows: {total:,}")

    cur.execute("SELECT COUNT(*) FROM f7_employers_deduped")
    f7_total = cur.fetchone()[0]
    if total != f7_total:
        print(f"  WARNING: MV rows ({total:,}) != f7_employers_deduped ({f7_total:,})")
    else:
        print(f"  OK: Matches f7_employers_deduped count ({f7_total:,})")

    # Source distribution
    print("\n  Source coverage:")
    for col in ['has_osha', 'has_nlrb', 'has_whd', 'has_990', 'has_sam',
                'has_sec', 'has_gleif', 'has_mergent']:
        cur.execute(f"SELECT COUNT(*) FROM mv_employer_data_sources WHERE {col}")
        cnt = cur.fetchone()[0]
        pct = 100.0 * cnt / total if total > 0 else 0
        print(f"    {col:15s}: {cnt:>7,} ({pct:5.1f}%)")

    # Source count distribution
    print("\n  Source count distribution:")
    cur.execute("""
        SELECT source_count, COUNT(*) AS cnt
        FROM mv_employer_data_sources
        GROUP BY source_count
        ORDER BY source_count
    """)
    for row in cur.fetchall():
        pct = 100.0 * row[1] / total if total > 0 else 0
        print(f"    {row[0]} sources: {row[1]:>7,} ({pct:5.1f}%)")

    # Crosswalk coverage
    cur.execute("SELECT COUNT(*) FROM mv_employer_data_sources WHERE corporate_family_id IS NOT NULL")
    cw_cnt = cur.fetchone()[0]
    print(f"\n  Corporate crosswalk: {cw_cnt:,} employers ({100.0*cw_cnt/total:.1f}%)")

    cur.execute("SELECT COUNT(*) FROM mv_employer_data_sources WHERE is_public")
    pub_cnt = cur.fetchone()[0]
    print(f"  Public companies: {pub_cnt:,}")

    cur.execute("SELECT COUNT(*) FROM mv_employer_data_sources WHERE is_federal_contractor")
    fc_cnt = cur.fetchone()[0]
    print(f"  Federal contractors: {fc_cnt:,}")

    return total


def create_mv(conn):
    """Drop and recreate the materialized view."""
    cur = conn.cursor()

    print("Dropping old MV if exists...")
    cur.execute("DROP MATERIALIZED VIEW IF EXISTS mv_employer_data_sources CASCADE")
    conn.commit()

    print("Creating mv_employer_data_sources...")
    t0 = time.time()
    cur.execute(MV_SQL)
    conn.commit()
    elapsed = time.time() - t0
    print(f"  Created in {elapsed:.1f}s")

    print("Creating indexes...")
    for sql in INDEX_SQL:
        cur.execute(sql)
    conn.commit()
    print("  Done.")

    print("\nVerification:")
    _print_stats(cur)


def refresh_mv(conn):
    """Refresh the existing materialized view (CONCURRENTLY)."""
    conn.autocommit = True
    cur = conn.cursor()

    print("Refreshing mv_employer_data_sources CONCURRENTLY...")
    t0 = time.time()
    cur.execute("REFRESH MATERIALIZED VIEW CONCURRENTLY mv_employer_data_sources")
    elapsed = time.time() - t0
    print(f"  Refreshed in {elapsed:.1f}s")

    print("\nVerification:")
    _print_stats(cur)


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Create/refresh employer data sources MV")
    parser.add_argument("--refresh", action="store_true", help="Refresh existing MV instead of recreating")
    args = parser.parse_args()

    conn = get_connection()
    conn.autocommit = False

    try:
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
