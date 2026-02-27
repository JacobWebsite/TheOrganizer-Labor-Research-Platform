"""
Build materialized view mv_target_scorecard.

Signal inventory for non-union employers with >= 1 data source.
No composite score -- discovery is filter-driven (state, industry, size, enforcement flags).
Default sort is by signal count, then alphabetically.

All JOINs go through master_employer_source_ids instead of F7 match tables.

Run:     py scripts/scoring/build_target_scorecard.py
Refresh: py scripts/scoring/build_target_scorecard.py --refresh
"""
import argparse
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
from db_config import get_connection


MV_SQL = """
CREATE MATERIALIZED VIEW mv_target_scorecard AS
WITH
-- OSHA aggregation via master_employer_source_ids
osha_agg AS (
    SELECT
        sid.master_id,
        COUNT(DISTINCT sid.source_id) AS estab_count,
        SUM(COALESCE(vs.total_violations, 0)) AS total_violations,
        SUM(COALESCE(vs.willful_count, 0)) AS willful_count,
        SUM(COALESCE(vs.repeat_count, 0)) AS repeat_count,
        SUM(COALESCE(vs.serious_count, 0)) AS serious_count,
        SUM(COALESCE(vs.total_penalties, 0)) AS total_penalties,
        MAX(oe.last_inspection_date) AS latest_inspection,
        MAX(oe.naics_code) AS osha_naics
    FROM master_employer_source_ids sid
    JOIN osha_establishments oe ON oe.establishment_id = sid.source_id
    LEFT JOIN (
        SELECT
            establishment_id,
            SUM(CASE WHEN violation_type = 'W' THEN violation_count ELSE 0 END) AS willful_count,
            SUM(CASE WHEN violation_type = 'R' THEN violation_count ELSE 0 END) AS repeat_count,
            SUM(CASE WHEN violation_type = 'S' THEN violation_count ELSE 0 END) AS serious_count,
            SUM(violation_count) AS total_violations,
            SUM(total_penalties) AS total_penalties
        FROM osha_violation_summary
        GROUP BY establishment_id
    ) vs ON vs.establishment_id = oe.establishment_id
    WHERE sid.source_system = 'osha'
    GROUP BY sid.master_id
),
osha_avgs AS (
    SELECT naics_prefix, avg_violations_per_estab
    FROM ref_osha_industry_averages
),
-- WHD aggregation via master_employer_source_ids
whd_agg AS (
    SELECT
        sid.master_id,
        COUNT(*) AS case_count,
        SUM(COALESCE(wc.total_violations, 0)) AS total_violations,
        SUM(COALESCE(wc.backwages_amount, 0)) AS total_backwages,
        SUM(COALESCE(wc.civil_penalties, 0)) AS total_penalties,
        SUM(COALESCE(wc.employees_violated, 0)) AS total_employees_violated,
        BOOL_OR(wc.flsa_repeat_violator) AS any_repeat_violator,
        MAX(wc.findings_end_date) AS latest_finding
    FROM master_employer_source_ids sid
    JOIN whd_cases wc ON wc.case_id = sid.source_id
    WHERE sid.source_system = 'whd'
    GROUP BY sid.master_id
),
-- NLRB aggregation via master_employer_source_ids
-- Elections: employer participants with election records
nlrb_elections_agg AS (
    SELECT
        sid.master_id,
        COUNT(DISTINCT e.case_number) AS election_count,
        SUM(CASE WHEN e.union_won THEN 1 ELSE 0 END) AS win_count,
        SUM(CASE WHEN e.union_won THEN 0 ELSE 1 END) AS loss_count,
        MAX(e.election_date) AS latest_election,
        SUM(COALESCE(e.eligible_voters, 0)) AS total_eligible,
        MAX(
            exp(-LN(2)/7 * GREATEST(0, (CURRENT_DATE - COALESCE(e.election_date, CURRENT_DATE))::float / 365.25))
        ) AS latest_decay_factor
    FROM master_employer_source_ids sid
    JOIN nlrb_participants p ON p.case_number = sid.source_id
    JOIN nlrb_elections e ON e.case_number = p.case_number
    WHERE sid.source_system = 'nlrb'
      AND p.participant_type = 'Employer'
    GROUP BY sid.master_id
),
-- ULP charges: charged party/respondent in CA cases
nlrb_ulp_agg AS (
    SELECT
        sid.master_id,
        COUNT(DISTINCT p.case_number) AS ulp_count,
        MAX(c.latest_date) AS latest_ulp,
        MAX(
            exp(-LN(2)/7 * GREATEST(0, (CURRENT_DATE - COALESCE(c.latest_date, CURRENT_DATE))::float / 365.25))
        ) AS ulp_decay_factor
    FROM master_employer_source_ids sid
    JOIN nlrb_participants p ON p.case_number = sid.source_id
    JOIN nlrb_cases c ON c.case_number = p.case_number
    WHERE sid.source_system = 'nlrb'
      AND p.participant_type = 'Charged Party / Respondent'
      AND p.case_number ~ '-CA-'
    GROUP BY sid.master_id
),
nlrb_agg AS (
    SELECT
        COALESCE(ea.master_id, ua.master_id) AS master_id,
        COALESCE(ea.election_count, 0) AS election_count,
        COALESCE(ea.win_count, 0) AS win_count,
        COALESCE(ea.loss_count, 0) AS loss_count,
        ea.latest_election,
        COALESCE(ea.total_eligible, 0) AS total_eligible,
        COALESCE(ea.latest_decay_factor, 1.0) AS latest_decay_factor,
        COALESCE(ua.ulp_count, 0) AS ulp_count,
        ua.latest_ulp,
        COALESCE(ua.ulp_decay_factor, 1.0) AS ulp_decay_factor
    FROM nlrb_elections_agg ea
    FULL OUTER JOIN nlrb_ulp_agg ua ON ea.master_id = ua.master_id
),
-- Financial: 990 filers matched by EIN
financial_990 AS (
    SELECT
        m.master_id,
        MAX(f.total_revenue) AS latest_revenue,
        MAX(f.total_assets) AS latest_assets,
        MAX(f.total_expenses) AS latest_expenses,
        MAX(f.total_employees) AS n990_employees
    FROM mv_target_data_sources m
    JOIN national_990_filers f ON f.ein = m.ein
    WHERE m.ein IS NOT NULL
      AND f.total_revenue IS NOT NULL
    GROUP BY m.master_id
),
-- BLS industry projections
bls_proj AS (
    SELECT matrix_code, employment_change_pct
    FROM bls_industry_projections
),
-- BLS state union density (latest year)
state_density AS (
    SELECT state, union_density_pct
    FROM bls_state_density
    WHERE year = (SELECT MAX(year) FROM bls_state_density)
),
-- BLS national industry density (latest year, NAICS-mapped)
industry_density AS (
    SELECT industry_code, union_density_pct
    FROM bls_national_industry_density
    WHERE year = (SELECT MAX(year) FROM bls_national_industry_density)
),
-- Raw signal computation
raw_signals AS (
    SELECT
        tds.master_id,
        tds.display_name,
        tds.canonical_name,
        tds.city,
        tds.state,
        tds.zip,
        tds.naics,
        tds.employee_count,
        tds.ein,
        tds.is_public,
        tds.is_federal_contractor,
        tds.is_nonprofit,
        tds.source_origin,
        tds.data_quality_score,
        tds.source_count,
        tds.has_osha,
        tds.has_whd,
        tds.has_nlrb,
        tds.has_990,
        tds.has_sam,
        tds.has_sec,
        tds.has_mergent,

        -- SIGNAL: OSHA (0-10) -- industry-normalized violations with temporal decay
        CASE
            WHEN tds.has_osha AND oa.master_id IS NOT NULL THEN LEAST(
                10,
                GREATEST(
                    0,
                    ROUND(
                        ((
                            COALESCE(oa.total_violations, 0)::numeric
                            / GREATEST(COALESCE(oa4.avg_violations_per_estab, oa2.avg_violations_per_estab, 2.23), 0.1)
                        )
                        * exp(-LN(2)/5 * GREATEST(0, (CURRENT_DATE - COALESCE(oa.latest_inspection, CURRENT_DATE))::float / 365.25)))::numeric,
                        2
                    )
                )
                + CASE WHEN COALESCE(oa.willful_count, 0) + COALESCE(oa.repeat_count, 0) > 0 THEN 1 ELSE 0 END
            )
        END AS signal_osha,

        -- SIGNAL: WHD (0-10) -- case count tiers with temporal decay
        CASE
            WHEN tds.has_whd AND wa.master_id IS NOT NULL THEN
                ROUND(
                    (
                        CASE
                            WHEN COALESCE(wa.case_count, 0) = 0 THEN 0
                            WHEN wa.case_count = 1 THEN 5
                            WHEN wa.case_count BETWEEN 2 AND 3 THEN 7
                            ELSE 10
                        END
                        * exp(-LN(2)/5 * GREATEST(0, (CURRENT_DATE - COALESCE(wa.latest_finding, CURRENT_DATE))::float / 365.25))
                    )::numeric,
                    2
                )
        END AS signal_whd,

        -- SIGNAL: NLRB (0-10) -- election + ULP activity with decay
        -- Reframed: elections = organizing attempts at this employer; ULP = anti-union behavior
        CASE
            WHEN na.master_id IS NOT NULL THEN
                LEAST(
                    10,
                    GREATEST(
                        0,
                        ROUND(
                            (
                                (COALESCE(na.election_count, 0) * 2 + COALESCE(na.win_count, 0))
                                * na.latest_decay_factor
                                + CASE
                                    WHEN na.ulp_count = 0 THEN 0
                                    WHEN na.ulp_count = 1 THEN 2
                                    WHEN na.ulp_count BETWEEN 2 AND 3 THEN 4
                                    WHEN na.ulp_count BETWEEN 4 AND 9 THEN 6
                                    ELSE 8
                                  END * na.ulp_decay_factor
                            )::numeric,
                            2
                        )
                    )
                )
        END AS signal_nlrb,

        -- SIGNAL: Federal Contracts (0-10) -- binary presence, no obligation amounts
        CASE
            WHEN tds.is_federal_contractor THEN 5
        END AS signal_contracts,

        -- SIGNAL: Financial (0-10) -- 990 nonprofit health + public company flag
        CASE
            WHEN f990.latest_revenue IS NOT NULL THEN LEAST(10, GREATEST(0,
                CASE
                    WHEN f990.latest_revenue >= 10000000 THEN 6
                    WHEN f990.latest_revenue >= 1000000 THEN 4
                    WHEN f990.latest_revenue >= 100000 THEN 2
                    ELSE 0
                END
                + CASE
                    WHEN COALESCE(f990.latest_assets, 0) > COALESCE(f990.latest_expenses, 1) * 2 THEN 2
                    WHEN COALESCE(f990.latest_assets, 0) > COALESCE(f990.latest_expenses, 1) THEN 1
                    ELSE 0
                END
                + CASE
                    WHEN f990.latest_revenue / NULLIF(GREATEST(COALESCE(tds.employee_count, 1), 1), 0) >= 50000 THEN 2
                    WHEN f990.latest_revenue / NULLIF(GREATEST(COALESCE(tds.employee_count, 1), 1), 0) >= 20000 THEN 1
                    ELSE 0
                END
            ))
            WHEN tds.is_public THEN 7
        END AS signal_financial,

        -- SIGNAL: Industry Growth (0-10) -- BLS employment projections
        CASE
            WHEN tds.naics IS NOT NULL THEN
                LEAST(
                    10,
                    GREATEST(
                        0,
                        ROUND((((COALESCE(bp.employment_change_pct, bp2.employment_change_pct, 0) + 10)::numeric / 20) * 10), 2)
                    )
                )
        END AS signal_industry_growth,

        -- SIGNAL: Union Density (0-10) -- NEW: industry x state union density
        -- High density = workers have union exposure, familiar with unions
        CASE
            WHEN sd.union_density_pct IS NOT NULL OR id.union_density_pct IS NOT NULL THEN
                LEAST(
                    10,
                    GREATEST(
                        0,
                        ROUND(
                            (COALESCE(sd.union_density_pct, 0) * 0.5 + COALESCE(id.union_density_pct, 0) * 0.5)::numeric / 4,
                            2
                        )
                    )
                )
        END AS signal_union_density,

        -- SIGNAL: Size (0-10, weight=0, filter dimension only)
        CASE
            WHEN tds.employee_count IS NULL THEN NULL
            WHEN tds.employee_count < 15 THEN 0
            WHEN tds.employee_count >= 500 THEN 10
            ELSE ROUND((((tds.employee_count - 15)::numeric / 485) * 10), 2)
        END AS signal_size,

        -- Raw detail columns for drilldown
        oa.estab_count AS osha_estab_count,
        oa.total_violations AS osha_total_violations,
        oa.total_penalties AS osha_total_penalties,
        oa.latest_inspection AS osha_latest_inspection,
        ROUND(
            exp(-LN(2)/5 * GREATEST(0, (CURRENT_DATE - COALESCE(oa.latest_inspection, CURRENT_DATE))::float / 365.25))::numeric,
            4
        ) AS osha_decay_factor,

        na.election_count AS nlrb_election_count,
        na.win_count AS nlrb_win_count,
        na.loss_count AS nlrb_loss_count,
        na.latest_election AS nlrb_latest_election,
        na.total_eligible AS nlrb_total_eligible,
        ROUND(COALESCE(na.latest_decay_factor, 1.0)::numeric, 4) AS nlrb_decay_factor,
        na.ulp_count AS nlrb_ulp_count,
        na.latest_ulp AS nlrb_latest_ulp,

        wa.case_count AS whd_case_count,
        wa.total_backwages AS whd_total_backwages,
        wa.total_penalties AS whd_total_penalties,
        wa.latest_finding AS whd_latest_finding,
        wa.any_repeat_violator AS whd_repeat_violator,

        COALESCE(bp.employment_change_pct, bp2.employment_change_pct) AS bls_growth_pct,
        sd.union_density_pct AS state_union_density_pct,
        id.union_density_pct AS industry_union_density_pct,

        f990.latest_revenue AS n990_revenue,
        f990.latest_assets AS n990_assets,
        f990.latest_expenses AS n990_expenses

    FROM mv_target_data_sources tds
    LEFT JOIN osha_agg oa ON oa.master_id = tds.master_id
    LEFT JOIN osha_avgs oa4 ON oa4.naics_prefix = LEFT(COALESCE(oa.osha_naics, tds.naics), 4)
    LEFT JOIN osha_avgs oa2 ON oa2.naics_prefix = LEFT(COALESCE(oa.osha_naics, tds.naics), 2) AND oa4.naics_prefix IS NULL
    LEFT JOIN nlrb_agg na ON na.master_id = tds.master_id
    LEFT JOIN whd_agg wa ON wa.master_id = tds.master_id
    LEFT JOIN bls_proj bp ON bp.matrix_code = LEFT(tds.naics, 2) || '0000'
    LEFT JOIN bls_proj bp2 ON bp2.matrix_code = CASE LEFT(tds.naics, 2)
        WHEN '31' THEN '31-330' WHEN '32' THEN '31-330' WHEN '33' THEN '31-330'
        WHEN '44' THEN '44-450' WHEN '45' THEN '44-450'
        WHEN '48' THEN '48-490' WHEN '49' THEN '48-490'
        ELSE NULL
    END AND bp.matrix_code IS NULL
    LEFT JOIN state_density sd ON sd.state = tds.state
    LEFT JOIN industry_density id ON id.industry_code = CASE LEFT(tds.naics, 2)
        WHEN '11' THEN 'AGR_MIN' WHEN '21' THEN 'AGR_MIN'
        WHEN '23' THEN 'CONST'
        WHEN '31' THEN 'MFG' WHEN '32' THEN 'MFG' WHEN '33' THEN 'MFG'
        WHEN '42' THEN 'WHOLESALE'
        WHEN '44' THEN 'RETAIL' WHEN '45' THEN 'RETAIL'
        WHEN '48' THEN 'TRANS_UTIL' WHEN '49' THEN 'TRANS_UTIL'
        WHEN '22' THEN 'TRANS_UTIL'
        WHEN '51' THEN 'INFO'
        WHEN '52' THEN 'FINANCE' WHEN '53' THEN 'FINANCE'
        WHEN '54' THEN 'PROF_BUS' WHEN '55' THEN 'PROF_BUS' WHEN '56' THEN 'PROF_BUS'
        WHEN '61' THEN 'EDU_HEALTH' WHEN '62' THEN 'EDU_HEALTH'
        WHEN '71' THEN 'LEISURE' WHEN '72' THEN 'LEISURE'
        WHEN '81' THEN 'OTHER'
        WHEN '92' THEN 'PUBLIC_ADMIN'
        ELSE NULL
    END
    LEFT JOIN financial_990 f990 ON f990.master_id = tds.master_id
    WHERE tds.source_count >= 1
)
SELECT
    rs.*,
    -- Signal inventory columns
    (CASE WHEN rs.signal_osha IS NOT NULL THEN 1 ELSE 0 END
     + CASE WHEN rs.signal_whd IS NOT NULL THEN 1 ELSE 0 END
     + CASE WHEN rs.signal_nlrb IS NOT NULL THEN 1 ELSE 0 END
     + CASE WHEN rs.signal_contracts IS NOT NULL THEN 1 ELSE 0 END
     + CASE WHEN rs.signal_financial IS NOT NULL THEN 1 ELSE 0 END
     + CASE WHEN rs.signal_industry_growth IS NOT NULL THEN 1 ELSE 0 END
     + CASE WHEN rs.signal_union_density IS NOT NULL THEN 1 ELSE 0 END
     + CASE WHEN rs.signal_size IS NOT NULL THEN 1 ELSE 0 END
    ) AS signals_present,

    -- Enforcement flags
    (rs.signal_osha IS NOT NULL OR rs.signal_whd IS NOT NULL OR rs.signal_nlrb IS NOT NULL) AS has_enforcement,
    (CASE WHEN rs.signal_osha IS NOT NULL THEN 1 ELSE 0 END
     + CASE WHEN rs.signal_whd IS NOT NULL THEN 1 ELSE 0 END
     + CASE WHEN rs.signal_nlrb IS NOT NULL THEN 1 ELSE 0 END
    ) AS enforcement_count,

    -- Recent violation flag (2-year window)
    CASE WHEN COALESCE(rs.osha_latest_inspection, '1900-01-01'::date) >= (CURRENT_DATE - INTERVAL '2 years')
         OR COALESCE(rs.whd_latest_finding, '1900-01-01'::date) >= (CURRENT_DATE - INTERVAL '2 years')
         OR COALESCE(rs.nlrb_latest_ulp, '1900-01-01'::date) >= (CURRENT_DATE - INTERVAL '2 years')
        THEN TRUE ELSE FALSE
    END AS has_recent_violations,

    -- Future-ready pillar columns
    CASE WHEN rs.signal_osha IS NOT NULL OR rs.signal_whd IS NOT NULL OR rs.signal_nlrb IS NOT NULL THEN
        ROUND(
            (COALESCE(rs.signal_osha, 0) + COALESCE(rs.signal_whd, 0) + COALESCE(rs.signal_nlrb, 0))::numeric
            / GREATEST(1,
                CASE WHEN rs.signal_osha IS NOT NULL THEN 1 ELSE 0 END
                + CASE WHEN rs.signal_whd IS NOT NULL THEN 1 ELSE 0 END
                + CASE WHEN rs.signal_nlrb IS NOT NULL THEN 1 ELSE 0 END
            ),
            2
        )
    END AS pillar_anger,

    CASE WHEN rs.signal_contracts IS NOT NULL OR rs.signal_financial IS NOT NULL OR rs.signal_union_density IS NOT NULL THEN
        ROUND(
            (COALESCE(rs.signal_contracts, 0) + COALESCE(rs.signal_financial, 0) + COALESCE(rs.signal_union_density, 0))::numeric
            / GREATEST(1,
                CASE WHEN rs.signal_contracts IS NOT NULL THEN 1 ELSE 0 END
                + CASE WHEN rs.signal_financial IS NOT NULL THEN 1 ELSE 0 END
                + CASE WHEN rs.signal_union_density IS NOT NULL THEN 1 ELSE 0 END
            ),
            2
        )
    END AS pillar_leverage,

    -- pillar_stability: NULL until turnover/sentiment data arrives
    NULL::numeric(5,2) AS pillar_stability

FROM raw_signals rs
"""


INDEX_SQL = [
    "CREATE UNIQUE INDEX IF NOT EXISTS idx_mv_ts_master_id ON mv_target_scorecard (master_id)",
    "CREATE INDEX IF NOT EXISTS idx_mv_ts_state ON mv_target_scorecard (state)",
    "CREATE INDEX IF NOT EXISTS idx_mv_ts_naics ON mv_target_scorecard (naics)",
    "CREATE INDEX IF NOT EXISTS idx_mv_ts_signals_present ON mv_target_scorecard (signals_present DESC)",
    "CREATE INDEX IF NOT EXISTS idx_mv_ts_has_enforcement ON mv_target_scorecard (master_id) WHERE has_enforcement",
    "CREATE INDEX IF NOT EXISTS idx_mv_ts_has_recent ON mv_target_scorecard (master_id) WHERE has_recent_violations",
    "CREATE INDEX IF NOT EXISTS idx_mv_ts_employee_count ON mv_target_scorecard (employee_count) WHERE employee_count IS NOT NULL",
    "CREATE INDEX IF NOT EXISTS idx_mv_ts_federal ON mv_target_scorecard (master_id) WHERE is_federal_contractor",
    "CREATE INDEX IF NOT EXISTS idx_mv_ts_source_count ON mv_target_scorecard (source_count DESC)",
    "CREATE INDEX IF NOT EXISTS idx_mv_ts_display_name ON mv_target_scorecard (display_name)",
]


def _print_stats(cur):
    cur.execute("SELECT COUNT(*) FROM mv_target_scorecard")
    total = cur.fetchone()[0]
    print(f"  Total rows: {total:,}")

    # Signal coverage
    print("\n  Signal coverage:")
    for col in ['signal_osha', 'signal_whd', 'signal_nlrb', 'signal_contracts',
                'signal_financial', 'signal_industry_growth', 'signal_union_density', 'signal_size']:
        cur.execute(f"SELECT COUNT(*) FROM mv_target_scorecard WHERE {col} IS NOT NULL")
        cnt = cur.fetchone()[0]
        pct = 100.0 * cnt / total if total > 0 else 0
        cur.execute(f"SELECT ROUND(AVG({col})::numeric, 2) FROM mv_target_scorecard WHERE {col} IS NOT NULL")
        avg = cur.fetchone()[0]
        print(f"    {col:25s}: {cnt:>10,} ({pct:5.1f}%) avg={avg}")

    # Signal count distribution
    print("\n  Signals present distribution:")
    cur.execute("""
        SELECT signals_present, COUNT(*) AS cnt
        FROM mv_target_scorecard
        GROUP BY signals_present
        ORDER BY signals_present
    """)
    for row in cur.fetchall():
        pct = 100.0 * row[1] / total if total > 0 else 0
        print(f"    {row[0]} signals: {row[1]:>10,} ({pct:5.1f}%)")

    # Enforcement
    cur.execute("SELECT COUNT(*) FROM mv_target_scorecard WHERE has_enforcement")
    enf = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM mv_target_scorecard WHERE has_recent_violations")
    recent = cur.fetchone()[0]
    print(f"\n  Has enforcement signals: {enf:,} ({100.0*enf/total:.1f}%)")
    print(f"  Has recent violations: {recent:,} ({100.0*recent/total:.1f}%)")

    # Pillar coverage
    print("\n  Pillar coverage:")
    for col in ['pillar_anger', 'pillar_leverage']:
        cur.execute(f"SELECT COUNT(*), ROUND(AVG({col})::numeric, 2) FROM mv_target_scorecard WHERE {col} IS NOT NULL")
        cnt, avg = cur.fetchone()
        pct = 100.0 * cnt / total if total > 0 else 0
        print(f"    {col:20s}: {cnt:>10,} ({pct:5.1f}%) avg={avg}")

    return total


def create_mv(conn):
    cur = conn.cursor()

    print("Dropping old MV if exists...")
    cur.execute("DROP MATERIALIZED VIEW IF EXISTS mv_target_scorecard CASCADE")
    conn.commit()

    print("Creating mv_target_scorecard...")
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

    print("Refreshing mv_target_scorecard CONCURRENTLY...")
    t0 = time.time()
    cur.execute("REFRESH MATERIALIZED VIEW CONCURRENTLY mv_target_scorecard")
    print(f"  Refreshed in {time.time() - t0:.1f}s")

    print("\nVerification:")
    _print_stats(cur)


def main():
    parser = argparse.ArgumentParser(description="Create/refresh target scorecard MV")
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
