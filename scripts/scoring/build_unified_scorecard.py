"""
Build materialized view mv_unified_scorecard.

Scores ALL 146,863 F7 employers using signal-strength scoring:
each factor is NULL if no data exists, and the final score is
the average of non-null factors (0-10 scale) with a coverage
percentage.

7 Factors (each 0-10):
  1. OSHA Safety Violations     (requires OSHA match)
  2. NLRB Election Activity     (requires NLRB match)
  3. Wage Theft Violations      (requires WHD match)
  4. Government Contracts       (requires federal contractor flag)
  5. Union Proximity            (always available - from F7 group data)
  6. Financial / Industry       (requires NAICS for BLS projections)
  7. Employer Size              (always available)

Run:     py scripts/scoring/build_unified_scorecard.py
Refresh: py scripts/scoring/build_unified_scorecard.py --refresh
"""
import sys
import os
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
from db_config import get_connection


MV_SQL = """
CREATE MATERIALIZED VIEW mv_unified_scorecard AS
WITH
-- ================================================================
-- Pre-aggregation CTEs
-- ================================================================

-- OSHA: aggregate violations across all matched establishments per F7 employer
osha_agg AS (
    SELECT
        m.f7_employer_id,
        COUNT(DISTINCT m.establishment_id) AS estab_count,
        SUM(COALESCE(vs.total_violations, 0)) AS total_violations,
        SUM(COALESCE(vs.willful_count, 0)) AS willful_count,
        SUM(COALESCE(vs.repeat_count, 0)) AS repeat_count,
        SUM(COALESCE(vs.serious_count, 0)) AS serious_count,
        SUM(COALESCE(vs.total_penalties, 0)) AS total_penalties,
        MAX(o.last_inspection_date) AS latest_inspection,
        MAX(o.naics_code) AS osha_naics
    FROM osha_f7_matches m
    JOIN osha_establishments o ON o.establishment_id = m.establishment_id
    LEFT JOIN (
        SELECT establishment_id,
               SUM(CASE WHEN violation_type = 'W' THEN violation_count ELSE 0 END) AS willful_count,
               SUM(CASE WHEN violation_type = 'R' THEN violation_count ELSE 0 END) AS repeat_count,
               SUM(CASE WHEN violation_type = 'S' THEN violation_count ELSE 0 END) AS serious_count,
               SUM(violation_count) AS total_violations,
               SUM(total_penalties) AS total_penalties
        FROM osha_violation_summary
        GROUP BY establishment_id
    ) vs ON o.establishment_id = vs.establishment_id
    GROUP BY m.f7_employer_id
),

-- OSHA industry averages for normalization
osha_avgs AS (
    SELECT naics_prefix, avg_violations_per_estab
    FROM ref_osha_industry_averages
),

-- NLRB: aggregate elections per F7 employer
nlrb_agg AS (
    SELECT
        p.matched_employer_id AS f7_employer_id,
        COUNT(DISTINCT e.case_number) AS election_count,
        SUM(CASE WHEN e.union_won THEN 1 ELSE 0 END) AS win_count,
        MAX(e.election_date) AS latest_election,
        SUM(COALESCE(e.eligible_voters, 0)) AS total_eligible
    FROM nlrb_participants p
    JOIN nlrb_elections e ON p.case_number = e.case_number
    WHERE p.matched_employer_id IS NOT NULL
      AND p.participant_type = 'Employer'
    GROUP BY p.matched_employer_id
),

-- WHD: aggregate wage theft cases per F7 employer
whd_agg AS (
    SELECT
        wm.f7_employer_id,
        COUNT(*) AS case_count,
        SUM(COALESCE(wc.total_violations, 0)) AS total_violations,
        SUM(COALESCE(wc.backwages_amount, 0)) AS total_backwages,
        SUM(COALESCE(wc.civil_penalties, 0)) AS total_penalties,
        SUM(COALESCE(wc.employees_violated, 0)) AS total_employees_violated,
        bool_or(wc.flsa_repeat_violator) AS any_repeat_violator,
        MAX(wc.findings_end_date) AS latest_finding
    FROM whd_f7_matches wm
    JOIN whd_cases wc ON wc.case_id = wm.case_id
    GROUP BY wm.f7_employer_id
),

-- Union proximity: canonical group stats per employer
union_prox AS (
    SELECT
        e.employer_id,
        e.canonical_group_id,
        g.member_count,
        g.is_cross_state,
        g.consolidated_workers
    FROM f7_employers_deduped e
    LEFT JOIN employer_canonical_groups g ON g.group_id = e.canonical_group_id
),

-- BLS projections by NAICS 2-digit (direct + composite codes)
bls_proj AS (
    SELECT matrix_code, employment_change_pct
    FROM bls_industry_projections
),

-- ================================================================
-- Raw factor scores (one row per F7 employer)
-- ================================================================
raw_scores AS (
    SELECT
        eds.employer_id,
        eds.employer_name,
        eds.state,
        eds.city,
        eds.naics,
        eds.naics_detailed,
        eds.latest_unit_size,
        eds.latest_union_fnum,
        eds.latest_union_name,
        eds.is_historical,
        eds.canonical_group_id,
        eds.is_canonical_rep,
        eds.source_count,
        eds.has_osha,
        eds.has_nlrb,
        eds.has_whd,
        eds.has_990,
        eds.has_sam,
        eds.has_sec,
        eds.has_gleif,
        eds.has_mergent,
        eds.is_public,
        eds.is_federal_contractor,
        eds.federal_obligations,
        eds.federal_contract_count,
        eds.ein,
        eds.ticker,
        eds.corporate_family_id,

        -- ============================================================
        -- Factor 1: OSHA Safety (0-10), NULL if no OSHA data
        -- Temporal decay (10yr half-life) on most recent inspection.
        -- Normalized by industry average.
        -- ============================================================
        CASE WHEN eds.has_osha AND oa.f7_employer_id IS NOT NULL THEN
            LEAST(10,
                -- Base from decayed industry-normalized ratio (0-7)
                CASE
                    WHEN COALESCE(oa.total_violations, 0) = 0 THEN 0
                    WHEN (oa.total_violations::float
                          * exp(-LN(2)/10 * GREATEST(0, (CURRENT_DATE - COALESCE(oa.latest_inspection, CURRENT_DATE))::float / 365.25))
                          / GREATEST(COALESCE(
                                oa4.avg_violations_per_estab,
                                oa2.avg_violations_per_estab,
                                2.23), 0.01)
                         ) / GREATEST(oa.estab_count, 1) >= 3.0 THEN 7
                    WHEN (oa.total_violations::float
                          * exp(-LN(2)/10 * GREATEST(0, (CURRENT_DATE - COALESCE(oa.latest_inspection, CURRENT_DATE))::float / 365.25))
                          / GREATEST(COALESCE(
                                oa4.avg_violations_per_estab,
                                oa2.avg_violations_per_estab,
                                2.23), 0.01)
                         ) / GREATEST(oa.estab_count, 1) >= 2.0 THEN 5
                    WHEN (oa.total_violations::float
                          * exp(-LN(2)/10 * GREATEST(0, (CURRENT_DATE - COALESCE(oa.latest_inspection, CURRENT_DATE))::float / 365.25))
                          / GREATEST(COALESCE(
                                oa4.avg_violations_per_estab,
                                oa2.avg_violations_per_estab,
                                2.23), 0.01)
                         ) / GREATEST(oa.estab_count, 1) >= 1.0 THEN 3
                    ELSE 1
                END
                +
                -- Severity bonus: willful*2 + repeat, decayed, capped at 3
                LEAST(3, ROUND(
                    (COALESCE(oa.willful_count, 0) * 2 + COALESCE(oa.repeat_count, 0))::float
                    * exp(-LN(2)/10 * GREATEST(0, (CURRENT_DATE - COALESCE(oa.latest_inspection, CURRENT_DATE))::float / 365.25))
                )::int)
            )
        END AS score_osha,

        -- ============================================================
        -- Factor 2: NLRB Activity (0-10), NULL if no NLRB data
        -- Based on election count, win rate, and recency.
        -- ============================================================
        CASE WHEN eds.has_nlrb AND na.f7_employer_id IS NOT NULL THEN
            LEAST(10,
                -- Base from election activity (0-7)
                CASE
                    WHEN na.election_count >= 3 THEN 7
                    WHEN na.election_count = 2 THEN 5
                    WHEN na.election_count = 1 AND na.win_count > 0 THEN 4
                    WHEN na.election_count = 1 THEN 3
                    ELSE 1
                END
                +
                -- Recency bonus: +3 if election within 3 years, +1 if within 7
                CASE
                    WHEN na.latest_election >= CURRENT_DATE - INTERVAL '3 years' THEN 3
                    WHEN na.latest_election >= CURRENT_DATE - INTERVAL '7 years' THEN 1
                    ELSE 0
                END
            )
        END AS score_nlrb,

        -- ============================================================
        -- Factor 3: Wage Theft (0-10), NULL if no WHD data
        -- Based on violation severity, backwages, repeat status.
        -- Temporal decay (7yr half-life) on latest finding.
        -- ============================================================
        CASE WHEN eds.has_whd AND wa.f7_employer_id IS NOT NULL THEN
            LEAST(10, ROUND((
                CASE
                    WHEN wa.any_repeat_violator THEN 8
                    WHEN wa.total_penalties > 100000 THEN 7
                    WHEN wa.total_backwages > 500000 THEN 6
                    WHEN wa.total_penalties > 10000 OR wa.total_violations > 10 THEN 5
                    WHEN wa.total_backwages > 50000 THEN 4
                    WHEN wa.total_violations > 0 THEN 2
                    ELSE 1
                END
                * exp(-LN(2)/7 * GREATEST(0, (CURRENT_DATE - COALESCE(wa.latest_finding, CURRENT_DATE))::float / 365.25))
            )::numeric)::int)
        END AS score_whd,

        -- ============================================================
        -- Factor 4: Government Contracts (0-10), NULL if not contractor
        -- Based on federal obligation amounts.
        -- ============================================================
        CASE WHEN eds.is_federal_contractor THEN
            CASE
                WHEN COALESCE(eds.federal_obligations, 0) > 5000000 THEN 10
                WHEN COALESCE(eds.federal_obligations, 0) > 1000000 THEN 7
                WHEN COALESCE(eds.federal_obligations, 0) > 100000 THEN 4
                WHEN COALESCE(eds.federal_obligations, 0) > 0 THEN 2
                ELSE 1
            END
        END AS score_contracts,

        -- ============================================================
        -- Factor 5: Union Proximity (0-10), always available
        -- Canonical group size, cross-state reach.
        -- ============================================================
        CASE
            WHEN up.is_cross_state AND COALESCE(up.member_count, 0) >= 5 THEN 10
            WHEN up.is_cross_state THEN 8
            WHEN COALESCE(up.member_count, 0) >= 5 THEN 7
            WHEN COALESCE(up.member_count, 0) >= 3 THEN 5
            WHEN COALESCE(up.member_count, 0) = 2 THEN 3
            ELSE 1
        END AS score_union_proximity,

        -- ============================================================
        -- Factor 6: Financial / Industry Viability (0-10)
        -- NULL only if no NAICS code (no BLS lookup possible).
        -- BLS industry growth (0-7 base) + public/nonprofit boost.
        -- ============================================================
        CASE WHEN eds.naics IS NOT NULL THEN
            LEAST(10,
                -- BLS industry growth base (0-7)
                CASE
                    WHEN COALESCE(bp.employment_change_pct, bp_alias.employment_change_pct) > 10 THEN 7
                    WHEN COALESCE(bp.employment_change_pct, bp_alias.employment_change_pct) > 5 THEN 5
                    WHEN COALESCE(bp.employment_change_pct, bp_alias.employment_change_pct) > 0 THEN 3
                    WHEN COALESCE(bp.employment_change_pct, bp_alias.employment_change_pct) IS NOT NULL THEN 1
                    ELSE 2  -- no BLS data for this NAICS
                END
                +
                -- Public company boost (more leverage, more data)
                CASE WHEN eds.is_public THEN 2 ELSE 0 END
                +
                -- Nonprofit data availability boost
                CASE WHEN eds.has_990 THEN 1 ELSE 0 END
            )
        END AS score_financial,

        -- ============================================================
        -- Factor 7: Employer Size (0-10), always available
        -- Sweet spot 50-500. Same tiers as current scorecard.
        -- ============================================================
        CASE
            WHEN COALESCE(eds.latest_unit_size, 0) BETWEEN 50 AND 250 THEN 10
            WHEN COALESCE(eds.latest_unit_size, 0) BETWEEN 251 AND 500 THEN 8
            WHEN COALESCE(eds.latest_unit_size, 0) BETWEEN 25 AND 49 THEN 6
            WHEN COALESCE(eds.latest_unit_size, 0) BETWEEN 501 AND 1000 THEN 4
            ELSE 2
        END AS score_size,

        -- ============================================================
        -- Metadata for display
        -- ============================================================
        oa.estab_count AS osha_estab_count,
        oa.total_violations AS osha_total_violations,
        oa.total_penalties AS osha_total_penalties,
        oa.latest_inspection AS osha_latest_inspection,
        ROUND(exp(-LN(2)/10 * GREATEST(0,
            (CURRENT_DATE - COALESCE(oa.latest_inspection, CURRENT_DATE))::float / 365.25
        ))::numeric, 4) AS osha_decay_factor,

        na.election_count AS nlrb_election_count,
        na.win_count AS nlrb_win_count,
        na.latest_election AS nlrb_latest_election,
        na.total_eligible AS nlrb_total_eligible,

        wa.case_count AS whd_case_count,
        wa.total_backwages AS whd_total_backwages,
        wa.total_penalties AS whd_total_penalties,
        wa.latest_finding AS whd_latest_finding,
        wa.any_repeat_violator AS whd_repeat_violator,

        COALESCE(bp.employment_change_pct, bp_alias.employment_change_pct) AS bls_growth_pct

    FROM mv_employer_data_sources eds

    -- OSHA aggregate
    LEFT JOIN osha_agg oa ON oa.f7_employer_id = eds.employer_id
    LEFT JOIN osha_avgs oa4 ON oa4.naics_prefix = LEFT(COALESCE(oa.osha_naics, eds.naics), 4)
    LEFT JOIN osha_avgs oa2 ON oa2.naics_prefix = LEFT(COALESCE(oa.osha_naics, eds.naics), 2)
        AND oa4.naics_prefix IS NULL

    -- NLRB aggregate
    LEFT JOIN nlrb_agg na ON na.f7_employer_id = eds.employer_id

    -- WHD aggregate
    LEFT JOIN whd_agg wa ON wa.f7_employer_id = eds.employer_id

    -- Union proximity
    LEFT JOIN union_prox up ON up.employer_id = eds.employer_id

    -- BLS projections (direct NAICS 2-digit + composite alias)
    LEFT JOIN bls_proj bp ON bp.matrix_code = LEFT(eds.naics, 2) || '0000'
    LEFT JOIN bls_proj bp_alias ON bp_alias.matrix_code = CASE LEFT(eds.naics, 2)
        WHEN '31' THEN '31-330' WHEN '32' THEN '31-330' WHEN '33' THEN '31-330'
        WHEN '44' THEN '44-450' WHEN '45' THEN '44-450'
        WHEN '48' THEN '48-490' WHEN '49' THEN '48-490'
        ELSE NULL
    END AND bp.matrix_code IS NULL
)

-- ================================================================
-- Final: compute derived fields from raw factor scores
-- ================================================================
SELECT
    rs.*,

    -- Count of non-null factors
    (CASE WHEN rs.score_osha IS NOT NULL THEN 1 ELSE 0 END
     + CASE WHEN rs.score_nlrb IS NOT NULL THEN 1 ELSE 0 END
     + CASE WHEN rs.score_whd IS NOT NULL THEN 1 ELSE 0 END
     + CASE WHEN rs.score_contracts IS NOT NULL THEN 1 ELSE 0 END
     + 1  -- union proximity always present
     + CASE WHEN rs.score_financial IS NOT NULL THEN 1 ELSE 0 END
     + 1  -- size always present
    ) AS factors_available,

    7 AS factors_total,

    -- Unified score: average of all non-null factors (0-10 scale)
    ROUND((
        COALESCE(rs.score_osha, 0) + COALESCE(rs.score_nlrb, 0)
        + COALESCE(rs.score_whd, 0) + COALESCE(rs.score_contracts, 0)
        + rs.score_union_proximity + COALESCE(rs.score_financial, 0)
        + rs.score_size
    )::numeric / (
        CASE WHEN rs.score_osha IS NOT NULL THEN 1 ELSE 0 END
        + CASE WHEN rs.score_nlrb IS NOT NULL THEN 1 ELSE 0 END
        + CASE WHEN rs.score_whd IS NOT NULL THEN 1 ELSE 0 END
        + CASE WHEN rs.score_contracts IS NOT NULL THEN 1 ELSE 0 END
        + 1  -- union proximity
        + CASE WHEN rs.score_financial IS NOT NULL THEN 1 ELSE 0 END
        + 1  -- size
    ), 2) AS unified_score,

    -- Coverage percentage
    ROUND(100.0 * (
        CASE WHEN rs.score_osha IS NOT NULL THEN 1 ELSE 0 END
        + CASE WHEN rs.score_nlrb IS NOT NULL THEN 1 ELSE 0 END
        + CASE WHEN rs.score_whd IS NOT NULL THEN 1 ELSE 0 END
        + CASE WHEN rs.score_contracts IS NOT NULL THEN 1 ELSE 0 END
        + 1 + CASE WHEN rs.score_financial IS NOT NULL THEN 1 ELSE 0 END + 1
    )::numeric / 7, 1) AS coverage_pct,

    -- Score tier classification
    CASE
        WHEN (
            COALESCE(rs.score_osha, 0) + COALESCE(rs.score_nlrb, 0)
            + COALESCE(rs.score_whd, 0) + COALESCE(rs.score_contracts, 0)
            + rs.score_union_proximity + COALESCE(rs.score_financial, 0)
            + rs.score_size
        )::numeric / (
            CASE WHEN rs.score_osha IS NOT NULL THEN 1 ELSE 0 END
            + CASE WHEN rs.score_nlrb IS NOT NULL THEN 1 ELSE 0 END
            + CASE WHEN rs.score_whd IS NOT NULL THEN 1 ELSE 0 END
            + CASE WHEN rs.score_contracts IS NOT NULL THEN 1 ELSE 0 END
            + 1 + CASE WHEN rs.score_financial IS NOT NULL THEN 1 ELSE 0 END + 1
        ) >= 7.0 THEN 'TOP'
        WHEN (
            COALESCE(rs.score_osha, 0) + COALESCE(rs.score_nlrb, 0)
            + COALESCE(rs.score_whd, 0) + COALESCE(rs.score_contracts, 0)
            + rs.score_union_proximity + COALESCE(rs.score_financial, 0)
            + rs.score_size
        )::numeric / (
            CASE WHEN rs.score_osha IS NOT NULL THEN 1 ELSE 0 END
            + CASE WHEN rs.score_nlrb IS NOT NULL THEN 1 ELSE 0 END
            + CASE WHEN rs.score_whd IS NOT NULL THEN 1 ELSE 0 END
            + CASE WHEN rs.score_contracts IS NOT NULL THEN 1 ELSE 0 END
            + 1 + CASE WHEN rs.score_financial IS NOT NULL THEN 1 ELSE 0 END + 1
        ) >= 5.0 THEN 'HIGH'
        WHEN (
            COALESCE(rs.score_osha, 0) + COALESCE(rs.score_nlrb, 0)
            + COALESCE(rs.score_whd, 0) + COALESCE(rs.score_contracts, 0)
            + rs.score_union_proximity + COALESCE(rs.score_financial, 0)
            + rs.score_size
        )::numeric / (
            CASE WHEN rs.score_osha IS NOT NULL THEN 1 ELSE 0 END
            + CASE WHEN rs.score_nlrb IS NOT NULL THEN 1 ELSE 0 END
            + CASE WHEN rs.score_whd IS NOT NULL THEN 1 ELSE 0 END
            + CASE WHEN rs.score_contracts IS NOT NULL THEN 1 ELSE 0 END
            + 1 + CASE WHEN rs.score_financial IS NOT NULL THEN 1 ELSE 0 END + 1
        ) >= 3.5 THEN 'MEDIUM'
        ELSE 'LOW'
    END AS score_tier

FROM raw_scores rs
"""


INDEX_SQL = [
    "CREATE UNIQUE INDEX IF NOT EXISTS idx_mv_us_employer_id ON mv_unified_scorecard (employer_id)",
    "CREATE INDEX IF NOT EXISTS idx_mv_us_state ON mv_unified_scorecard (state)",
    "CREATE INDEX IF NOT EXISTS idx_mv_us_unified_score ON mv_unified_scorecard (unified_score DESC NULLS LAST)",
    "CREATE INDEX IF NOT EXISTS idx_mv_us_naics ON mv_unified_scorecard (naics)",
    "CREATE INDEX IF NOT EXISTS idx_mv_us_score_tier ON mv_unified_scorecard (score_tier)",
    "CREATE INDEX IF NOT EXISTS idx_mv_us_factors ON mv_unified_scorecard (factors_available)",
]


def _print_stats(cur):
    """Print verification stats."""
    cur.execute("SELECT COUNT(*) FROM mv_unified_scorecard")
    total = cur.fetchone()[0]
    print(f"  Total rows: {total:,}")

    cur.execute("SELECT COUNT(*) FROM f7_employers_deduped")
    f7_total = cur.fetchone()[0]
    if total != f7_total:
        print(f"  WARNING: MV rows ({total:,}) != f7_employers_deduped ({f7_total:,})")
    else:
        print(f"  OK: Matches f7_employers_deduped count ({f7_total:,})")

    # Score distribution
    cur.execute("""
        SELECT
            MIN(unified_score) AS min_score,
            ROUND(AVG(unified_score)::numeric, 2) AS avg_score,
            MAX(unified_score) AS max_score,
            ROUND(STDDEV(unified_score)::numeric, 2) AS stddev_score
        FROM mv_unified_scorecard
    """)
    row = cur.fetchone()
    print(f"\n  Score range: {row[0]} - {row[2]}, avg={row[1]}, stddev={row[3]}")

    # Tier distribution
    print("\n  Score tiers:")
    cur.execute("""
        SELECT score_tier, COUNT(*) AS cnt
        FROM mv_unified_scorecard
        GROUP BY score_tier
        ORDER BY CASE score_tier
            WHEN 'TOP' THEN 1 WHEN 'HIGH' THEN 2
            WHEN 'MEDIUM' THEN 3 WHEN 'LOW' THEN 4
        END
    """)
    for row in cur.fetchall():
        pct = 100.0 * row[1] / total if total > 0 else 0
        print(f"    {row[0]:8s}: {row[1]:>7,} ({pct:5.1f}%)")

    # Factor availability
    print("\n  Factor availability:")
    for col in ['score_osha', 'score_nlrb', 'score_whd', 'score_contracts',
                'score_union_proximity', 'score_financial', 'score_size']:
        cur.execute(f"SELECT COUNT(*) FROM mv_unified_scorecard WHERE {col} IS NOT NULL")
        cnt = cur.fetchone()[0]
        # Also get average when available
        cur.execute(f"SELECT ROUND(AVG({col})::numeric, 2) FROM mv_unified_scorecard WHERE {col} IS NOT NULL")
        avg_val = cur.fetchone()[0]
        pct = 100.0 * cnt / total if total > 0 else 0
        print(f"    {col:25s}: {cnt:>7,} ({pct:5.1f}%)  avg={avg_val}")

    # Coverage distribution
    print("\n  Factors available distribution:")
    cur.execute("""
        SELECT factors_available, COUNT(*) AS cnt
        FROM mv_unified_scorecard
        GROUP BY factors_available
        ORDER BY factors_available
    """)
    for row in cur.fetchall():
        pct = 100.0 * row[1] / total if total > 0 else 0
        print(f"    {row[0]}/7 factors: {row[1]:>7,} ({pct:5.1f}%)")

    return total


def create_mv(conn):
    """Drop and recreate the materialized view."""
    cur = conn.cursor()

    print("Dropping old MV if exists...")
    cur.execute("DROP MATERIALIZED VIEW IF EXISTS mv_unified_scorecard CASCADE")
    conn.commit()

    print("Creating mv_unified_scorecard...")
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

    print("Refreshing mv_unified_scorecard CONCURRENTLY...")
    t0 = time.time()
    cur.execute("REFRESH MATERIALIZED VIEW CONCURRENTLY mv_unified_scorecard")
    elapsed = time.time() - t0
    print(f"  Refreshed in {elapsed:.1f}s")

    print("\nVerification:")
    _print_stats(cur)


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Create/refresh unified scorecard MV")
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
