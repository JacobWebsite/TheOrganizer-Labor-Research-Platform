"""
Build materialized view mv_unified_scorecard with 8-factor weighted scoring.

Run:     py scripts/scoring/build_unified_scorecard.py
Refresh: py scripts/scoring/build_unified_scorecard.py --refresh
"""
import argparse
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from db_config import get_connection


MV_SQL = """
CREATE MATERIALIZED VIEW mv_unified_scorecard AS
WITH
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
        SELECT
            establishment_id,
            SUM(CASE WHEN violation_type = 'W' THEN violation_count ELSE 0 END) AS willful_count,
            SUM(CASE WHEN violation_type = 'R' THEN violation_count ELSE 0 END) AS repeat_count,
            SUM(CASE WHEN violation_type = 'S' THEN violation_count ELSE 0 END) AS serious_count,
            SUM(violation_count) AS total_violations,
            SUM(total_penalties) AS total_penalties
        FROM osha_violation_summary
        GROUP BY establishment_id
    ) vs ON vs.establishment_id = o.establishment_id
    GROUP BY m.f7_employer_id
),
osha_avgs AS (
    SELECT naics_prefix, avg_violations_per_estab
    FROM ref_osha_industry_averages
),
nlrb_elections_agg AS (
    SELECT
        p.matched_employer_id AS f7_employer_id,
        COUNT(DISTINCT e.case_number) AS election_count,
        SUM(CASE WHEN e.union_won THEN 1 ELSE 0 END) AS win_count,
        SUM(CASE WHEN e.union_won THEN 0 ELSE 1 END) AS loss_count,
        MAX(e.election_date) AS latest_election,
        SUM(COALESCE(e.eligible_voters, 0)) AS total_eligible,
        MAX(
            exp(-LN(2)/7 * GREATEST(0, (CURRENT_DATE - COALESCE(e.election_date, CURRENT_DATE))::float / 365.25))
        ) AS latest_decay_factor
    FROM nlrb_participants p
    JOIN nlrb_elections e ON e.case_number = p.case_number
    WHERE p.participant_type = 'Employer'
      AND p.matched_employer_id IS NOT NULL
    GROUP BY p.matched_employer_id
),
nlrb_ulp_agg AS (
    SELECT
        p.matched_employer_id AS f7_employer_id,
        COUNT(DISTINCT p.case_number) AS ulp_count,
        MAX(c.latest_date) AS latest_ulp,
        MAX(
            exp(-LN(2)/7 * GREATEST(0, (CURRENT_DATE - COALESCE(c.latest_date, CURRENT_DATE))::float / 365.25))
        ) AS ulp_decay_factor
    FROM nlrb_participants p
    JOIN nlrb_cases c ON c.case_number = p.case_number
    WHERE p.participant_type = 'Charged Party / Respondent'
      AND p.case_number ~ '-CA-'
      AND p.matched_employer_id IS NOT NULL
    GROUP BY p.matched_employer_id
),
nlrb_agg AS (
    SELECT
        COALESCE(ea.f7_employer_id, ua.f7_employer_id) AS f7_employer_id,
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
    FULL OUTER JOIN nlrb_ulp_agg ua ON ea.f7_employer_id = ua.f7_employer_id
),
whd_agg AS (
    SELECT
        wm.f7_employer_id,
        COUNT(*) AS case_count,
        SUM(COALESCE(wc.total_violations, 0)) AS total_violations,
        SUM(COALESCE(wc.backwages_amount, 0)) AS total_backwages,
        SUM(COALESCE(wc.civil_penalties, 0)) AS total_penalties,
        SUM(COALESCE(wc.employees_violated, 0)) AS total_employees_violated,
        BOOL_OR(wc.flsa_repeat_violator) AS any_repeat_violator,
        MAX(wc.findings_end_date) AS latest_finding
    FROM whd_f7_matches wm
    JOIN whd_cases wc ON wc.case_id = wm.case_id
    GROUP BY wm.f7_employer_id
),
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
bls_proj AS (
    SELECT matrix_code, employment_change_pct
    FROM bls_industry_projections
),
financial_990 AS (
    SELECT
        m.f7_employer_id,
        MAX(f.total_revenue) AS latest_revenue,
        MAX(f.total_assets) AS latest_assets,
        MAX(f.total_expenses) AS latest_expenses,
        MAX(f.total_employees) AS n990_employees
    FROM national_990_f7_matches m
    JOIN national_990_filers f ON f.id = m.n990_id
    WHERE f.total_revenue IS NOT NULL
    GROUP BY m.f7_employer_id
),
feature_bridge AS (
    SELECT DISTINCT ON (LOWER(TRIM(employer_name)), state)
        LOWER(TRIM(employer_name)) AS employer_name_norm,
        state,
        employer_id AS feature_employer_id
    FROM mv_employer_features
    WHERE employer_name IS NOT NULL
      AND state IS NOT NULL
    ORDER BY LOWER(TRIM(employer_name)), state, employer_id
),
similarity_agg AS (
    SELECT
        eds.employer_id,
        COUNT(*) FILTER (WHERE COALESCE(cf.is_union, 0) > 0) AS unionized_comparable_count,
        MIN(ec.gower_distance)::numeric AS best_distance
    FROM mv_employer_data_sources eds
    JOIN feature_bridge fb
      ON fb.employer_name_norm = LOWER(TRIM(eds.employer_name))
     AND fb.state = eds.state
    JOIN employer_comparables ec ON ec.employer_id = fb.feature_employer_id
    JOIN mv_employer_features cf ON cf.employer_id = ec.comparable_employer_id
    GROUP BY eds.employer_id
),
raw_scores AS (
    SELECT
        eds.employer_id,
        eds.employer_name,
        eds.state,
        eds.city,
        eds.naics,
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

        CASE
            WHEN eds.has_osha AND oa.f7_employer_id IS NOT NULL THEN LEAST(
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
        END AS score_osha,

        -- TODO: nearby 25-mile momentum requires geocoded employer locations. Keep current own-history model.
        -- Election component: wins*2 + elections - losses, with 7yr decay
        -- ULP component: 1 charge=2, 2-3=4, 4-9=6, 10+=8, with 7yr decay
        CASE
            WHEN eds.has_nlrb AND na.f7_employer_id IS NOT NULL THEN
                LEAST(
                    10,
                    GREATEST(
                        0,
                        ROUND(
                            (
                                -- Election score
                                (COALESCE(na.win_count, 0) * 2 + COALESCE(na.election_count, 0) - COALESCE(na.loss_count, 0))
                                * na.latest_decay_factor
                                -- ULP boost
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
        END AS score_nlrb,

        CASE
            WHEN eds.has_whd AND wa.f7_employer_id IS NOT NULL THEN
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
        END AS score_whd,

        CASE
            WHEN eds.is_federal_contractor AND COALESCE(eds.federal_obligations, 0) > 0 THEN
                CASE
                    WHEN eds.federal_obligations >= 100000000 THEN 10
                    WHEN eds.federal_obligations >= 10000000 THEN 8
                    WHEN eds.federal_obligations >= 1000000 THEN 6
                    WHEN eds.federal_obligations >= 100000 THEN 4
                    ELSE 2
                END
            WHEN eds.is_federal_contractor THEN 1
        END AS score_contracts,

        CASE
            WHEN up.member_count IS NULL AND eds.corporate_family_id IS NULL THEN NULL
            WHEN GREATEST(COALESCE(up.member_count, 1) - 1, 0) >= 2 THEN 10
            WHEN GREATEST(COALESCE(up.member_count, 1) - 1, 0) = 1 OR eds.corporate_family_id IS NOT NULL THEN 5
            ELSE 0
        END AS score_union_proximity,

        CASE
            WHEN eds.naics IS NOT NULL THEN
                LEAST(
                    10,
                    GREATEST(
                        0,
                        ROUND((((COALESCE(bp.employment_change_pct, bp_alias.employment_change_pct, 0) + 10)::numeric / 20) * 10), 2)
                    )
                )
        END AS score_industry_growth,

        CASE
            WHEN COALESCE(eds.company_size, eds.latest_unit_size) IS NULL THEN NULL
            WHEN COALESCE(eds.company_size, eds.latest_unit_size) < 15 THEN 0
            WHEN COALESCE(eds.company_size, eds.latest_unit_size) >= 500 THEN 10
            ELSE ROUND((((COALESCE(eds.company_size, eds.latest_unit_size) - 15)::numeric / 485) * 10), 2)
        END AS score_size,

        sa.unionized_comparable_count,
        sa.best_distance,

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
        COALESCE(bp.employment_change_pct, bp_alias.employment_change_pct) AS bls_growth_pct,

        f990.latest_revenue AS n990_revenue,
        f990.latest_assets AS n990_assets,
        f990.latest_expenses AS n990_expenses
    FROM mv_employer_data_sources eds
    LEFT JOIN osha_agg oa ON oa.f7_employer_id = eds.employer_id
    LEFT JOIN osha_avgs oa4 ON oa4.naics_prefix = LEFT(COALESCE(oa.osha_naics, eds.naics), 4)
    LEFT JOIN osha_avgs oa2 ON oa2.naics_prefix = LEFT(COALESCE(oa.osha_naics, eds.naics), 2) AND oa4.naics_prefix IS NULL
    LEFT JOIN nlrb_agg na ON na.f7_employer_id = eds.employer_id
    LEFT JOIN whd_agg wa ON wa.f7_employer_id = eds.employer_id
    LEFT JOIN union_prox up ON up.employer_id = eds.employer_id
    LEFT JOIN bls_proj bp ON bp.matrix_code = LEFT(eds.naics, 2) || '0000'
    LEFT JOIN bls_proj bp_alias ON bp_alias.matrix_code = CASE LEFT(eds.naics, 2)
        WHEN '31' THEN '31-330' WHEN '32' THEN '31-330' WHEN '33' THEN '31-330'
        WHEN '44' THEN '44-450' WHEN '45' THEN '44-450'
        WHEN '48' THEN '48-490' WHEN '49' THEN '48-490'
        ELSE NULL
    END AND bp.matrix_code IS NULL
    LEFT JOIN similarity_agg sa ON sa.employer_id = eds.employer_id
    LEFT JOIN financial_990 f990 ON f990.f7_employer_id = eds.employer_id
),
scored AS (
    SELECT
        rs.*,
        CASE
            WHEN rs.score_union_proximity >= 5 THEN NULL
            WHEN rs.unionized_comparable_count IS NULL THEN NULL
            ELSE LEAST(
                10,
                CASE rs.unionized_comparable_count
                    WHEN 5 THEN 10
                    WHEN 4 THEN 8
                    WHEN 3 THEN 6
                    WHEN 2 THEN 4
                    WHEN 1 THEN 2
                    ELSE 0
                END
                + CASE WHEN rs.best_distance IS NOT NULL AND rs.best_distance < 0.15 THEN 1 ELSE 0 END
            )
        END AS score_similarity,
        -- score_financial: 990 nonprofit health + public company signal
        -- Different from score_industry_growth (BLS employment projections)
        CASE
            WHEN rs.n990_revenue IS NOT NULL THEN LEAST(10, GREATEST(0,
                CASE
                    WHEN rs.n990_revenue >= 10000000 THEN 6
                    WHEN rs.n990_revenue >= 1000000 THEN 4
                    WHEN rs.n990_revenue >= 100000 THEN 2
                    ELSE 0
                END
                + CASE
                    WHEN COALESCE(rs.n990_assets, 0) > COALESCE(rs.n990_expenses, 1) * 2 THEN 2
                    WHEN COALESCE(rs.n990_assets, 0) > COALESCE(rs.n990_expenses, 1) THEN 1
                    ELSE 0
                END
                + CASE
                    WHEN rs.n990_revenue / NULLIF(GREATEST(COALESCE(rs.latest_unit_size, 1), 1), 0) >= 50000 THEN 2
                    WHEN rs.n990_revenue / NULLIF(GREATEST(COALESCE(rs.latest_unit_size, 1), 1), 0) >= 20000 THEN 1
                    ELSE 0
                END
            ))
            WHEN rs.is_public THEN 7
        END AS score_financial
    FROM raw_scores rs
),
-- NOTE: Research enhancements are shown on ALL employer profiles regardless
-- of union status. The is_union_reference flag is still used by the Gower
-- similarity pipeline but does not gate profile visibility.
research_enhanced AS (
    SELECT
        s.*,
        rse.run_id AS research_run_id,
        rse.run_quality AS research_quality,
        -- Use GREATEST: pick higher of DB score vs research score
        -- NULL-safe: GREATEST(NULL, 5) = 5
        GREATEST(s.score_osha, rse.score_osha) AS enh_score_osha,
        GREATEST(s.score_nlrb, rse.score_nlrb) AS enh_score_nlrb,
        GREATEST(s.score_whd, rse.score_whd) AS enh_score_whd,
        GREATEST(s.score_contracts, rse.score_contracts) AS enh_score_contracts,
        GREATEST(s.score_financial, rse.score_financial) AS enh_score_financial,
        COALESCE(s.score_size, rse.score_size) AS enh_score_size,
        -- Assessment fields
        rse.recommended_approach AS research_approach,
        rse.financial_trend AS research_trend,
        rse.source_contradictions AS research_contradictions,
        rse.score_stability AS rse_score_stability,
        rse.score_anger AS rse_score_anger,
        rse.turnover_rate_found,
        rse.sentiment_score_found,
        rse.revenue_per_employee_found,
        (rse.run_id IS NOT NULL) AS has_research
    FROM scored s
    LEFT JOIN research_score_enhancements rse
        ON rse.employer_id = s.employer_id
        -- No is_union_reference filter: show research on all employer profiles
),
strategic_pillars AS (
    SELECT
        s.*,
        -- PILLAR 1: ANGER (Motivation)
        -- Blends violations, ULP history, and research sentiment
        COALESCE(
            s.rse_score_anger,
            LEAST(10, 
                (COALESCE(s.enh_score_osha, 0) * 0.3)
                + (COALESCE(s.enh_score_whd, 0) * 0.3)
                + (CASE 
                    WHEN s.nlrb_ulp_count = 0 THEN 0
                    WHEN s.nlrb_ulp_count = 1 THEN 4
                    WHEN s.nlrb_ulp_count BETWEEN 2 AND 3 THEN 6
                    WHEN s.nlrb_ulp_count BETWEEN 4 AND 9 THEN 8
                    ELSE 10
                  END * 0.4)
                + COALESCE(s.sentiment_score_found, 0) -- Research bonus
            )
        ) AS score_anger,

        -- PILLAR 2: STABILITY (Winnability)
        -- High score = Low turnover / High stability. "Stability is required for a committee."
        COALESCE(
            s.rse_score_stability,
            CASE 
                WHEN s.turnover_rate_found IS NOT NULL THEN (10 - s.turnover_rate_found)
                -- If we have recent NLRB wins nearby, stability/momentum is higher (placeholder for momentum)
                ELSE 5.0 -- Baseline stability
            END
        ) AS score_stability,

        -- PILLAR 3: LEVERAGE (Power)
        -- Blends proximity, contracts, financials (RPE), and growth
        LEAST(10,
            (COALESCE(s.score_union_proximity, 0) * 0.3)
            + (COALESCE(s.enh_score_contracts, 0) * 0.2)
            + (COALESCE(s.enh_score_financial, 0) * 0.2)
            + (COALESCE(s.score_industry_growth, 0) * 0.15)
            + (COALESCE(s.enh_score_size, 0) * 0.15)
            + CASE WHEN s.revenue_per_employee_found > 500000 THEN 1 ELSE 0 END -- RPE Bonus
        ) AS score_leverage
    FROM research_enhanced s
),
weighted AS (
    SELECT
        s.*,
        (
            CASE WHEN s.score_union_proximity IS NOT NULL THEN 3 ELSE 0 END
            + CASE WHEN s.score_nlrb IS NOT NULL THEN 3 ELSE 0 END
            + CASE WHEN s.score_contracts IS NOT NULL THEN 2 ELSE 0 END
            + CASE WHEN s.score_industry_growth IS NOT NULL THEN 2 ELSE 0 END
            + CASE WHEN s.score_financial IS NOT NULL THEN 2 ELSE 0 END
            + CASE WHEN s.score_osha IS NOT NULL THEN 1 ELSE 0 END
            + CASE WHEN s.score_whd IS NOT NULL THEN 1 ELSE 0 END
            + CASE WHEN s.score_stability IS NOT NULL THEN 2 ELSE 0 END -- New stability weight
        ) AS total_weight,
        (
            CASE WHEN s.score_osha IS NOT NULL THEN 1 ELSE 0 END
            + CASE WHEN s.score_nlrb IS NOT NULL THEN 1 ELSE 0 END
            + CASE WHEN s.score_whd IS NOT NULL THEN 1 ELSE 0 END
            + CASE WHEN s.score_contracts IS NOT NULL THEN 1 ELSE 0 END
            + CASE WHEN s.score_union_proximity IS NOT NULL THEN 1 ELSE 0 END
            + CASE WHEN s.score_industry_growth IS NOT NULL THEN 1 ELSE 0 END
            + CASE WHEN s.score_financial IS NOT NULL THEN 1 ELSE 0 END
            + CASE WHEN s.score_size IS NOT NULL THEN 1 ELSE 0 END
            + CASE WHEN s.has_research THEN 1 ELSE 0 END
        ) AS factors_available,
        9 AS factors_total,
        ROUND(
            (
                (COALESCE(s.score_anger, 0) * 3)
                + (COALESCE(s.score_stability, 0) * 3)
                + (COALESCE(s.score_leverage, 0) * 4)
            )::numeric / 10,
            2
        ) AS weighted_score,
        -- Keep original weighted score for comparison
        ROUND(
            (
                COALESCE(s.score_union_proximity, 0) * 3
                + COALESCE(s.enh_score_nlrb, s.score_nlrb, 0) * 3
                + COALESCE(s.enh_score_contracts, s.score_contracts, 0) * 2
                + COALESCE(s.score_industry_growth, 0) * 2
                + COALESCE(s.enh_score_financial, s.score_financial, 0) * 2
                + COALESCE(s.enh_score_osha, s.score_osha, 0)
                + COALESCE(s.enh_score_whd, s.score_whd, 0)
            )::numeric
            / NULLIF(
                (
                    CASE WHEN s.score_union_proximity IS NOT NULL THEN 3 ELSE 0 END
                    + CASE WHEN COALESCE(s.enh_score_nlrb, s.score_nlrb) IS NOT NULL THEN 3 ELSE 0 END
                    + CASE WHEN COALESCE(s.enh_score_contracts, s.score_contracts) IS NOT NULL THEN 2 ELSE 0 END
                    + CASE WHEN s.score_industry_growth IS NOT NULL THEN 2 ELSE 0 END
                    + CASE WHEN COALESCE(s.enh_score_financial, s.score_financial) IS NOT NULL THEN 2 ELSE 0 END
                    + CASE WHEN COALESCE(s.enh_score_osha, s.score_osha) IS NOT NULL THEN 1 ELSE 0 END
                    + CASE WHEN COALESCE(s.enh_score_whd, s.score_whd) IS NOT NULL THEN 1 ELSE 0 END
                ),
                0
            ),
            2
        ) AS legacy_weighted_score
    FROM strategic_pillars s
),
ranked AS (
    SELECT
        w.*,
        w.weighted_score AS unified_score,
        ROUND(100.0 * w.factors_available::numeric / 9, 1) AS coverage_pct,
        PERCENT_RANK() OVER (ORDER BY w.weighted_score ASC NULLS FIRST) AS score_percentile
    FROM weighted w
)
SELECT
    r.*,
    -- Strategic Delta: how much the new model shifted the score vs the legacy heuristic
    ROUND((r.weighted_score - COALESCE(r.legacy_weighted_score, 0))::numeric, 2) AS strategic_delta,
    -- Flag columns (yes/no signals, NOT tier requirements per D2)
    CASE WHEN COALESCE(r.osha_latest_inspection, '1900-01-01'::date) >= (CURRENT_DATE - INTERVAL '2 years')
         OR COALESCE(r.whd_latest_finding, '1900-01-01'::date) >= (CURRENT_DATE - INTERVAL '2 years')
         OR COALESCE(r.nlrb_latest_ulp, '1900-01-01'::date) >= (CURRENT_DATE - INTERVAL '2 years')
        THEN TRUE ELSE FALSE
    END AS has_recent_violations,
    CASE WHEN r.score_contracts IS NOT NULL AND r.score_contracts > 0
        THEN TRUE ELSE FALSE
    END AS has_active_contracts,
    CASE
        -- Guardrail: min 3 factors for Priority AND Strong (D3)
        WHEN r.score_percentile >= 0.97 AND r.factors_available >= 3 THEN 'Priority'
        WHEN r.score_percentile >= 0.85 AND r.factors_available >= 3 THEN 'Strong'
        WHEN r.score_percentile >= 0.85 THEN 'Promising'
        WHEN r.score_percentile >= 0.60 THEN 'Promising'
        WHEN r.score_percentile >= 0.25 THEN 'Moderate'
        ELSE 'Low'
    END AS score_tier,
    CASE
        WHEN r.score_percentile >= 0.97 THEN 'TOP'
        WHEN r.score_percentile >= 0.85 THEN 'HIGH'
        WHEN r.score_percentile >= 0.60 THEN 'MEDIUM'
        ELSE 'LOW'
    END AS score_tier_legacy
FROM ranked r
"""


INDEX_SQL = [
    "CREATE UNIQUE INDEX IF NOT EXISTS idx_mv_us_employer_id ON mv_unified_scorecard (employer_id)",
    "CREATE INDEX IF NOT EXISTS idx_mv_us_state ON mv_unified_scorecard (state)",
    "CREATE INDEX IF NOT EXISTS idx_mv_us_unified_score ON mv_unified_scorecard (unified_score DESC NULLS LAST)",
    "CREATE INDEX IF NOT EXISTS idx_mv_us_weighted_score ON mv_unified_scorecard (weighted_score DESC NULLS LAST)",
    "CREATE INDEX IF NOT EXISTS idx_mv_us_naics ON mv_unified_scorecard (naics)",
    "CREATE INDEX IF NOT EXISTS idx_mv_us_score_tier ON mv_unified_scorecard (score_tier)",
    "CREATE INDEX IF NOT EXISTS idx_mv_us_factors ON mv_unified_scorecard (factors_available)",
    "CREATE INDEX IF NOT EXISTS idx_mv_us_has_research ON mv_unified_scorecard (has_research) WHERE has_research = TRUE",
    "CREATE INDEX IF NOT EXISTS idx_mv_us_strategic_delta ON mv_unified_scorecard (strategic_delta DESC NULLS LAST) WHERE strategic_delta IS NOT NULL",
]


def _print_stats(cur):
    cur.execute("SELECT COUNT(*) FROM mv_unified_scorecard")
    total = cur.fetchone()[0]
    print(f"  Total rows: {total:,}")

    cur.execute(
        """
        SELECT MIN(weighted_score), ROUND(AVG(weighted_score)::numeric, 2), MAX(weighted_score)
        FROM mv_unified_scorecard
        """
    )
    mn, avg, mx = cur.fetchone()
    print(f"  Weighted score range: {mn} - {mx}, avg={avg}")

    print("\n  Tier distribution:")
    cur.execute(
        """
        SELECT score_tier, COUNT(*) AS cnt
        FROM mv_unified_scorecard
        GROUP BY score_tier
        ORDER BY CASE score_tier
            WHEN 'Priority' THEN 1
            WHEN 'Strong' THEN 2
            WHEN 'Promising' THEN 3
            WHEN 'Moderate' THEN 4
            WHEN 'Low' THEN 5
            ELSE 6
        END
        """
    )
    for tier, cnt in cur.fetchall():
        pct = (100.0 * cnt / total) if total else 0
        print(f"    {tier:10s}: {cnt:>8,} ({pct:5.1f}%)")


def create_mv(conn):
    cur = conn.cursor()
    print("Dropping old MV if exists...")
    cur.execute("DROP MATERIALIZED VIEW IF EXISTS mv_unified_scorecard CASCADE")
    conn.commit()

    print("Creating mv_unified_scorecard...")
    t0 = time.time()
    cur.execute(MV_SQL)
    conn.commit()
    print(f"  Created in {time.time() - t0:.1f}s")

    print("Creating indexes...")
    for stmt in INDEX_SQL:
        cur.execute(stmt)
    conn.commit()
    print("  Done.")

    print("\nVerification:")
    _print_stats(cur)


def refresh_mv(conn):
    conn.autocommit = True
    cur = conn.cursor()
    print("Refreshing mv_unified_scorecard CONCURRENTLY...")
    t0 = time.time()
    cur.execute("REFRESH MATERIALIZED VIEW CONCURRENTLY mv_unified_scorecard")
    print(f"  Refreshed in {time.time() - t0:.1f}s")
    print("\nVerification:")
    _print_stats(cur)


def main():
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
    except Exception as exc:
        conn.rollback()
        print(f"ERROR: {exc}")
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    main()
