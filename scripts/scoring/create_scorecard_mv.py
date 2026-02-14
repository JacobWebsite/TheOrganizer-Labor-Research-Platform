"""
Create materialized view mv_organizing_scorecard.

Pre-computes all 9 scoring factors for every OSHA establishment,
eliminating the LIMIT 500 pre-filter bug and per-request computation.

Run: py scripts/scoring/create_scorecard_mv.py
Refresh: py scripts/scoring/create_scorecard_mv.py --refresh
"""
import sys
import os
import time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
from db_config import get_connection


MV_SQL = """
CREATE MATERIALIZED VIEW mv_organizing_scorecard AS
WITH
-- Reference data CTEs
industry_density AS (
    SELECT naics_2digit, union_density_pct
    FROM v_naics_union_density
),
rtw_states AS (
    SELECT state FROM ref_rtw_states
),
nlrb_state_rates AS (
    SELECT state, win_rate_pct FROM ref_nlrb_state_win_rates
),
nlrb_us_rate AS (
    SELECT win_rate_pct FROM ref_nlrb_state_win_rates WHERE state = 'US'
),
state_members AS (
    SELECT state, members_total FROM epi_state_benchmarks
),
osha_industry_avgs AS (
    SELECT naics_prefix, avg_violations_per_estab FROM ref_osha_industry_averages
),
bls_proj AS (
    SELECT matrix_code, employment_change_pct FROM bls_industry_projections
),
nlrb_industry AS (
    SELECT naics_2, win_rate_pct FROM ref_nlrb_industry_win_rates
),
nlrb_us_industry AS (
    SELECT win_rate_pct FROM ref_nlrb_industry_win_rates WHERE naics_2 = 'US'
),
-- F7 match set (powers score_company_unions) -- 1 row per establishment
f7_matches AS (
    SELECT DISTINCT establishment_id
    FROM osha_f7_matches
),
-- Federal contracts (powers score_contracts) -- 1 row per establishment (max obligations)
fed_contracts AS (
    SELECT establishment_id,
           MAX(federal_obligations) AS federal_obligations,
           MAX(federal_contract_count) AS federal_contract_count
    FROM (
        SELECT DISTINCT m.establishment_id,
               c.federal_obligations,
               c.federal_contract_count
        FROM osha_f7_matches m
        JOIN corporate_identifier_crosswalk c ON c.f7_employer_id = m.f7_employer_id
        WHERE c.is_federal_contractor = TRUE
    ) sub
    GROUP BY establishment_id
),
-- Similarity + NLRB predicted (powers score_similarity, score_nlrb) -- 1 row per establishment (best scores)
mergent_data AS (
    SELECT establishment_id,
           MAX(similarity_score) AS similarity_score,
           MAX(nlrb_predicted_win_pct) AS nlrb_predicted_win_pct
    FROM (
        SELECT m.establishment_id,
               me.similarity_score,
               me.nlrb_predicted_win_pct
        FROM osha_f7_matches m
        JOIN mergent_employers me ON me.matched_f7_employer_id = m.f7_employer_id
        WHERE me.similarity_score IS NOT NULL OR me.nlrb_predicted_win_pct IS NOT NULL
    ) sub
    GROUP BY establishment_id
)

SELECT
    t.establishment_id,
    t.estab_name,
    t.site_address,
    t.site_city,
    t.site_state,
    t.site_zip,
    t.naics_code,
    t.employee_count,
    t.total_inspections,
    t.last_inspection_date,
    t.willful_count,
    t.repeat_count,
    t.serious_count,
    t.total_violations,
    t.total_penalties,
    t.accident_count,
    t.fatality_count,
    t.risk_level,

    -- Factor 1: Company unions (20 pts)
    CASE WHEN fm.establishment_id IS NOT NULL THEN 20 ELSE 0 END AS score_company_unions,

    -- Factor 2: Industry density (10 pts)
    CASE
        WHEN COALESCE(id.union_density_pct, 0) > 20 THEN 10
        WHEN COALESCE(id.union_density_pct, 0) > 10 THEN 8
        WHEN COALESCE(id.union_density_pct, 0) > 5 THEN 5
        ELSE 2
    END AS score_industry_density,

    -- Factor 3: Geographic favorability (10 pts)
    LEAST(10,
        -- NLRB win rate component (0-4)
        CASE
            WHEN COALESCE(nsr.win_rate_pct, (SELECT win_rate_pct FROM nlrb_us_rate)) >= 85 THEN 4
            WHEN COALESCE(nsr.win_rate_pct, (SELECT win_rate_pct FROM nlrb_us_rate)) >= 75 THEN 3
            WHEN COALESCE(nsr.win_rate_pct, (SELECT win_rate_pct FROM nlrb_us_rate)) >= 65 THEN 2
            WHEN COALESCE(nsr.win_rate_pct, (SELECT win_rate_pct FROM nlrb_us_rate)) >= 55 THEN 1
            ELSE 0
        END
        +
        -- State density component (0-3)
        CASE
            WHEN COALESCE(sm.members_total, 0) > 1000000 THEN 3
            WHEN COALESCE(sm.members_total, 0) > 500000 THEN 2
            WHEN COALESCE(sm.members_total, 0) > 200000 THEN 1
            ELSE 0
        END
        +
        -- Non-RTW bonus (0-3)
        CASE WHEN rtw.state IS NULL THEN 3 ELSE 0 END
    ) AS score_geographic,

    -- Factor 4: Size (10 pts)
    CASE
        WHEN COALESCE(t.employee_count, 0) BETWEEN 50 AND 250 THEN 10
        WHEN COALESCE(t.employee_count, 0) BETWEEN 251 AND 500 THEN 8
        WHEN COALESCE(t.employee_count, 0) BETWEEN 25 AND 49 THEN 6
        WHEN COALESCE(t.employee_count, 0) BETWEEN 501 AND 1000 THEN 4
        ELSE 2
    END AS score_size,

    -- Factor 5: OSHA violations normalized (10 pts)
    LEAST(10,
        -- Base from ratio (0-7)
        CASE
            WHEN COALESCE(t.total_violations, 0) = 0 THEN 0
            WHEN COALESCE(t.total_violations, 0)::float / GREATEST(
                COALESCE(oa4.avg_violations_per_estab, oa2.avg_violations_per_estab, oaall.avg_violations_per_estab, 2.23), 0.01
            ) >= 3.0 THEN 7
            WHEN COALESCE(t.total_violations, 0)::float / GREATEST(
                COALESCE(oa4.avg_violations_per_estab, oa2.avg_violations_per_estab, oaall.avg_violations_per_estab, 2.23), 0.01
            ) >= 2.0 THEN 5
            WHEN COALESCE(t.total_violations, 0)::float / GREATEST(
                COALESCE(oa4.avg_violations_per_estab, oa2.avg_violations_per_estab, oaall.avg_violations_per_estab, 2.23), 0.01
            ) >= 1.5 THEN 4
            WHEN COALESCE(t.total_violations, 0)::float / GREATEST(
                COALESCE(oa4.avg_violations_per_estab, oa2.avg_violations_per_estab, oaall.avg_violations_per_estab, 2.23), 0.01
            ) >= 1.0 THEN 3
            ELSE 1
        END
        +
        -- Severity bonus (0-3)
        LEAST(3, COALESCE(t.willful_count, 0) * 2 + COALESCE(t.repeat_count, 0))
    ) AS score_osha,

    -- OSHA industry ratio (for display)
    ROUND(
        COALESCE(t.total_violations, 0)::numeric / GREATEST(
            COALESCE(oa4.avg_violations_per_estab, oa2.avg_violations_per_estab, oaall.avg_violations_per_estab, 2.23), 0.01
        ), 2
    ) AS osha_industry_ratio,

    -- Factor 6: NLRB (10 pts)
    CASE
        WHEN md.nlrb_predicted_win_pct >= 82 THEN 10
        WHEN md.nlrb_predicted_win_pct >= 78 THEN 8
        WHEN md.nlrb_predicted_win_pct >= 74 THEN 5
        WHEN md.nlrb_predicted_win_pct >= 70 THEN 3
        WHEN md.nlrb_predicted_win_pct IS NOT NULL THEN 1
        ELSE
            -- Fallback: blended state + industry rate
            CASE
                WHEN (COALESCE(nsr.win_rate_pct, (SELECT win_rate_pct FROM nlrb_us_rate)) * 0.6
                    + COALESCE(ni.win_rate_pct, (SELECT win_rate_pct FROM nlrb_us_industry)) * 0.4) >= 82 THEN 10
                WHEN (COALESCE(nsr.win_rate_pct, (SELECT win_rate_pct FROM nlrb_us_rate)) * 0.6
                    + COALESCE(ni.win_rate_pct, (SELECT win_rate_pct FROM nlrb_us_industry)) * 0.4) >= 78 THEN 8
                WHEN (COALESCE(nsr.win_rate_pct, (SELECT win_rate_pct FROM nlrb_us_rate)) * 0.6
                    + COALESCE(ni.win_rate_pct, (SELECT win_rate_pct FROM nlrb_us_industry)) * 0.4) >= 74 THEN 5
                WHEN (COALESCE(nsr.win_rate_pct, (SELECT win_rate_pct FROM nlrb_us_rate)) * 0.6
                    + COALESCE(ni.win_rate_pct, (SELECT win_rate_pct FROM nlrb_us_industry)) * 0.4) >= 70 THEN 3
                ELSE 1
            END
    END AS score_nlrb,

    -- Factor 7: Contracts (10 pts)
    CASE
        WHEN COALESCE(fc.federal_obligations, 0) > 5000000 THEN 10
        WHEN COALESCE(fc.federal_obligations, 0) > 1000000 THEN 7
        WHEN COALESCE(fc.federal_obligations, 0) > 100000 THEN 4
        WHEN COALESCE(fc.federal_obligations, 0) > 0 THEN 2
        ELSE 0
    END AS score_contracts,

    -- Factor 8: Projections (10 pts)
    CASE
        WHEN COALESCE(bp.employment_change_pct, bp_alias.employment_change_pct, 0) > 10 THEN 10
        WHEN COALESCE(bp.employment_change_pct, bp_alias.employment_change_pct, 0) > 5 THEN 7
        WHEN COALESCE(bp.employment_change_pct, bp_alias.employment_change_pct, 0) > 0 THEN 4
        ELSE 2
    END AS score_projections,

    -- Factor 9: Similarity (10 pts)
    CASE
        WHEN md.similarity_score >= 0.80 THEN 10
        WHEN md.similarity_score >= 0.60 THEN 7
        WHEN md.similarity_score >= 0.40 THEN 4
        WHEN md.similarity_score IS NOT NULL THEN 1
        ELSE 0
    END AS score_similarity,

    -- Metadata
    fm.establishment_id IS NOT NULL AS has_f7_match,
    fc.establishment_id IS NOT NULL AS has_federal_contracts,
    fc.federal_obligations,
    fc.federal_contract_count,
    md.nlrb_predicted_win_pct,
    md.similarity_score

FROM v_osha_organizing_targets t

-- Factor 2: Industry density
LEFT JOIN industry_density id ON id.naics_2digit = LEFT(t.naics_code, 2)

-- Factor 3: Geographic
LEFT JOIN rtw_states rtw ON rtw.state = t.site_state
LEFT JOIN nlrb_state_rates nsr ON nsr.state = t.site_state
LEFT JOIN state_members sm ON sm.state = t.site_state

-- Factor 5: OSHA industry averages (4-digit, then 2-digit, then overall)
LEFT JOIN osha_industry_avgs oa4 ON oa4.naics_prefix = LEFT(t.naics_code, 4)
LEFT JOIN osha_industry_avgs oa2 ON oa2.naics_prefix = LEFT(t.naics_code, 2) AND oa4.naics_prefix IS NULL
LEFT JOIN osha_industry_avgs oaall ON oaall.naics_prefix = 'ALL' AND oa4.naics_prefix IS NULL AND oa2.naics_prefix IS NULL

-- Factor 6: NLRB industry rates
LEFT JOIN nlrb_industry ni ON ni.naics_2 = LEFT(t.naics_code, 2)

-- Factor 8: BLS projections (direct, then alias for composite NAICS)
LEFT JOIN bls_proj bp ON bp.matrix_code = LEFT(t.naics_code, 2) || '0000'
LEFT JOIN bls_proj bp_alias ON bp_alias.matrix_code = CASE LEFT(t.naics_code, 2)
    WHEN '31' THEN '31-330' WHEN '32' THEN '31-330' WHEN '33' THEN '31-330'
    WHEN '44' THEN '44-450' WHEN '45' THEN '44-450'
    WHEN '48' THEN '48-490' WHEN '49' THEN '48-490'
    ELSE NULL
END AND bp.matrix_code IS NULL

-- Factors 1, 7, 9: F7 match, contracts, similarity
LEFT JOIN f7_matches fm ON fm.establishment_id = t.establishment_id
LEFT JOIN fed_contracts fc ON fc.establishment_id = t.establishment_id
LEFT JOIN mergent_data md ON md.establishment_id = t.establishment_id
"""


TOTAL_SCORE_SQL = """
-- Add the total organizing_score as a generated-like column via a wrapper view
CREATE OR REPLACE VIEW v_organizing_scorecard AS
SELECT *,
    (score_company_unions + score_industry_density + score_geographic +
     score_size + score_osha + score_nlrb + score_contracts +
     score_projections + score_similarity) AS organizing_score
FROM mv_organizing_scorecard
"""


INDEX_SQL = [
    "CREATE UNIQUE INDEX IF NOT EXISTS idx_mv_scorecard_estab_id ON mv_organizing_scorecard (establishment_id)",
    "CREATE INDEX IF NOT EXISTS idx_mv_scorecard_state ON mv_organizing_scorecard (site_state)",
    "CREATE INDEX IF NOT EXISTS idx_mv_scorecard_naics ON mv_organizing_scorecard (naics_code)",
    "CREATE INDEX IF NOT EXISTS idx_mv_scorecard_employees ON mv_organizing_scorecard (employee_count)",
]


def create_mv(conn):
    """Drop and recreate the materialized view."""
    cur = conn.cursor()
    print("Dropping old MV if exists...")
    cur.execute("DROP VIEW IF EXISTS v_organizing_scorecard CASCADE")
    cur.execute("DROP MATERIALIZED VIEW IF EXISTS mv_organizing_scorecard CASCADE")
    conn.commit()

    print("Creating mv_organizing_scorecard...")
    t0 = time.time()
    cur.execute(MV_SQL)
    conn.commit()
    elapsed = time.time() - t0
    print(f"  Created in {elapsed:.1f}s")

    cur.execute("SELECT COUNT(*) FROM mv_organizing_scorecard")
    count = cur.fetchone()[0]
    print(f"  Rows: {count:,}")

    print("Creating wrapper view v_organizing_scorecard...")
    cur.execute(TOTAL_SCORE_SQL)
    conn.commit()

    print("Creating indexes...")
    for sql in INDEX_SQL:
        cur.execute(sql)
    conn.commit()
    print("  Done.")

    # Stats
    cur.execute("""
        SELECT
            MIN(score_company_unions + score_industry_density + score_geographic +
                score_size + score_osha + score_nlrb + score_contracts +
                score_projections + score_similarity) AS min_score,
            AVG(score_company_unions + score_industry_density + score_geographic +
                score_size + score_osha + score_nlrb + score_contracts +
                score_projections + score_similarity) AS avg_score,
            MAX(score_company_unions + score_industry_density + score_geographic +
                score_size + score_osha + score_nlrb + score_contracts +
                score_projections + score_similarity) AS max_score
        FROM mv_organizing_scorecard
    """)
    row = cur.fetchone()
    print(f"  Scores: min={row[0]}, avg={row[1]:.1f}, max={row[2]}")


def refresh_mv(conn):
    """Refresh the existing materialized view (CONCURRENTLY to avoid blocking reads)."""
    # REFRESH CONCURRENTLY cannot run inside a transaction block
    conn.autocommit = True
    cur = conn.cursor()
    print("Refreshing mv_organizing_scorecard CONCURRENTLY...")
    t0 = time.time()
    cur.execute("REFRESH MATERIALIZED VIEW CONCURRENTLY mv_organizing_scorecard")
    elapsed = time.time() - t0

    cur.execute("SELECT COUNT(*) FROM mv_organizing_scorecard")
    count = cur.fetchone()[0]
    print(f"  Refreshed in {elapsed:.1f}s ({count:,} rows)")


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Create/refresh scorecard materialized view")
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
