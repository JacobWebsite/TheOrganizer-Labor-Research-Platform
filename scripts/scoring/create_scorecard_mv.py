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
import json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
from db_config import get_connection


# ── Score versioning ──────────────────────────────────────────────────
# Every MV create/refresh records a version with algorithm parameters.

SCORE_VERSIONS_DDL = """
CREATE TABLE IF NOT EXISTS score_versions (
    version_id   SERIAL PRIMARY KEY,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    description  TEXT,
    row_count    INTEGER,
    factor_weights JSONB NOT NULL,
    decay_params   JSONB NOT NULL,
    score_stats    JSONB
)
"""

CURRENT_FACTOR_WEIGHTS = {
    "company_unions": {"max": 0, "note": "excluded - union shops filtered"},
    "industry_density": {"max": 10, "method": "hierarchical_naics_blend"},
    "geographic": {"max": 10, "components": ["nlrb_win_rate", "state_density", "rtw_bonus"]},
    "size": {"max": 10, "sweet_spot": "50-250"},
    "osha": {"max": 10, "method": "decayed_ratio + severity_bonus"},
    "nlrb": {"max": 10, "method": "blended_state_industry_fallback"},
    "contracts": {"max": 10, "source": "federal_obligations"},
    "projections": {"max": 10, "source": "bls_industry_projections"},
    "similarity": {"max": 10, "source": "gower_distance", "fallback": "industry_avg_similarity",
                    "fallback_cap": 5, "note": "industry-avg capped at 50% of employer-specific max"},
}

CURRENT_DECAY_PARAMS = {
    "osha": {"half_life_years": 10, "lambda_expr": "LN(2)/10", "applied_to": "violation_count_and_severity"},
    "nlrb": {"half_life_years": 7, "lambda_expr": "LN(2)/7", "applied_in": "detail_endpoint_only",
             "note": "MV excludes F7-matched rows; NLRB routes through F7"},
}


# The source view that feeds the MV. Includes all non-union OSHA establishments
# with significant violations. union_status='Y' (confirmed union) is excluded;
# statuses 'N' (non-union), 'A' (not available), 'B' (both/mixed) are included.
# NOTE: OSHA switched from N/Y to A/B codes around 2015-2016.
VIEW_SQL = """
CREATE OR REPLACE VIEW v_osha_organizing_targets AS
SELECT o.establishment_id,
    o.estab_name,
    o.site_address,
    o.site_city,
    o.site_state,
    o.site_zip,
    o.naics_code,
    o.employee_count,
    o.total_inspections,
    o.last_inspection_date,
    COALESCE(vs.willful_count, 0::bigint) AS willful_count,
    COALESCE(vs.repeat_count, 0::bigint) AS repeat_count,
    COALESCE(vs.serious_count, 0::bigint) AS serious_count,
    COALESCE(vs.total_violations, 0::bigint) AS total_violations,
    COALESCE(vs.total_penalties, 0::numeric) AS total_penalties,
    COALESCE(a.accident_count, 0::bigint) AS accident_count,
    COALESCE(a.fatality_count, 0::bigint) AS fatality_count,
    CASE
        WHEN COALESCE(vs.willful_count, 0::bigint) > 0 THEN 'CRITICAL'
        WHEN COALESCE(vs.repeat_count, 0::bigint) > 0 OR COALESCE(a.fatality_count, 0::bigint) > 0 THEN 'HIGH'
        WHEN COALESCE(vs.serious_count, 0::bigint) >= 5 THEN 'MODERATE'
        ELSE 'LOW'
    END AS risk_level
FROM osha_establishments o
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
LEFT JOIN (
    SELECT establishment_id,
        COUNT(*) AS accident_count,
        SUM(CASE WHEN is_fatality THEN 1 ELSE 0 END) AS fatality_count
    FROM osha_accidents
    GROUP BY establishment_id
) a ON o.establishment_id = a.establishment_id
WHERE o.union_status != 'Y'
AND (COALESCE(vs.willful_count, 0) > 0
     OR COALESCE(vs.repeat_count, 0) > 0
     OR COALESCE(vs.serious_count, 0) >= 3
     OR COALESCE(a.fatality_count, 0) > 0)
"""


MV_SQL = """
CREATE MATERIALIZED VIEW mv_organizing_scorecard AS
WITH
-- Reference data CTEs
industry_density AS (
    SELECT naics_2digit, union_density_pct
    FROM v_naics_union_density
),
-- State x industry density estimates (Phase 4) with normalized codes
state_industry_density AS (
    SELECT
        state,
        year,
        estimated_density::numeric AS estimated_density,
        regexp_replace(COALESCE(industry_code::text, ''), '[^0-9]', '', 'g') AS industry_code_norm
    FROM estimated_state_industry_density
),
-- Hierarchical NAICS blend: uses state-level density when available,
-- weighted by NAICS digit-match similarity (6-digit=1.0 down to 2-digit=0.25)
industry_density_blend AS (
    SELECT
        t.establishment_id,
        COALESCE(id.union_density_pct, 0)::numeric AS national_density_pct,
        sb.estimated_density AS state_density_pct,
        COALESCE(sb.naics_similarity, 0.0)::numeric AS naics_similarity,
        CASE
            WHEN sb.estimated_density IS NULL THEN COALESCE(id.union_density_pct, 0)::numeric
            ELSE
                (COALESCE(id.union_density_pct, 0)::numeric * (1 - COALESCE(sb.naics_similarity, 0.0)::numeric))
                + (sb.estimated_density * COALESCE(sb.naics_similarity, 0.0)::numeric)
        END AS blended_density_pct
    FROM v_osha_organizing_targets t
    LEFT JOIN industry_density id
        ON id.naics_2digit = LEFT(t.naics_code, 2)
    CROSS JOIN LATERAL (
        SELECT regexp_replace(COALESCE(t.naics_code::text, ''), '[^0-9]', '', 'g') AS naics_norm
    ) tn
    LEFT JOIN LATERAL (
        SELECT
            s.estimated_density,
            CASE
                WHEN tn.naics_norm = '' THEN 0.0
                WHEN LENGTH(tn.naics_norm) >= 6
                 AND LENGTH(s.industry_code_norm) >= 6
                 AND LEFT(tn.naics_norm, 6) = LEFT(s.industry_code_norm, 6) THEN 1.0
                WHEN LENGTH(tn.naics_norm) >= 5
                 AND LENGTH(s.industry_code_norm) >= 5
                 AND LEFT(tn.naics_norm, 5) = LEFT(s.industry_code_norm, 5) THEN 0.85
                WHEN LENGTH(tn.naics_norm) >= 4
                 AND LENGTH(s.industry_code_norm) >= 4
                 AND LEFT(tn.naics_norm, 4) = LEFT(s.industry_code_norm, 4) THEN 0.65
                WHEN LENGTH(tn.naics_norm) >= 3
                 AND LENGTH(s.industry_code_norm) >= 3
                 AND LEFT(tn.naics_norm, 3) = LEFT(s.industry_code_norm, 3) THEN 0.45
                WHEN LENGTH(tn.naics_norm) >= 2
                 AND LENGTH(s.industry_code_norm) >= 2
                 AND LEFT(tn.naics_norm, 2) = LEFT(s.industry_code_norm, 2) THEN 0.25
                ELSE 0.0
            END AS naics_similarity
        FROM state_industry_density s
        WHERE s.state = t.site_state
        ORDER BY naics_similarity DESC, COALESCE(s.year, 0) DESC, s.industry_code_norm
        LIMIT 1
    ) sb ON TRUE
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
),
-- NOTE: NLRB employer-specific decay is NOT applied in the MV because the
-- WHERE clause (fm.establishment_id IS NULL) excludes F7-matched rows, and
-- NLRB data routes through osha_f7_matches->nlrb_participants which requires
-- an F7 match. Employer-specific NLRB decay is applied in the detail endpoint.
nlrb_recent_placeholder AS (
    SELECT NULL::bigint AS establishment_id, NULL::date AS last_election_date
    WHERE FALSE
),
-- Industry-average similarity scores (powers Factor 9 fallback for unmatched establishments)
-- Computed from mergent_employers similarity_score grouped by NAICS 2-digit sector.
-- Bridges the gap: MV rows lack F7 matches so md.similarity_score is always NULL.
industry_avg_similarity AS (
    SELECT LEFT(me.naics_primary, 2) AS naics_2,
           AVG(me.similarity_score)::numeric AS avg_similarity,
           COUNT(*) AS sample_size
    FROM mergent_employers me
    WHERE me.has_union IS NOT TRUE
      AND me.similarity_score IS NOT NULL
      AND me.naics_primary IS NOT NULL
    GROUP BY LEFT(me.naics_primary, 2)
    HAVING COUNT(*) >= 10
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

    -- Factor 1: Company unions -- REMOVED: union shops now excluded from MV entirely
    -- Kept as 0 for schema compatibility
    0 AS score_company_unions,

    -- Factor 2: Industry density with hierarchical NAICS blend (10 pts)
    -- Uses state-level density when available, weighted by NAICS digit-match similarity
    CASE
        WHEN t.naics_code IS NULL THEN 2
        WHEN COALESCE(idb.blended_density_pct, 0) > 20 THEN 10
        WHEN COALESCE(idb.blended_density_pct, 0) > 10 THEN 8
        WHEN COALESCE(idb.blended_density_pct, 0) > 5 THEN 5
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

    -- Factor 5: OSHA violations with temporal decay (10 pts)
    -- Half-life: 10 years. Recent violations weigh more than old ones.
    -- decay = exp(-LN(2)/10 * years_since_last_inspection)
    LEAST(10,
        -- Base from decayed ratio (0-7)
        CASE
            WHEN COALESCE(t.total_violations, 0) = 0 THEN 0
            WHEN COALESCE(t.total_violations, 0)::float * osha_decay.val / GREATEST(
                COALESCE(oa4.avg_violations_per_estab, oa2.avg_violations_per_estab, oaall.avg_violations_per_estab, 2.23), 0.01
            ) >= 3.0 THEN 7
            WHEN COALESCE(t.total_violations, 0)::float * osha_decay.val / GREATEST(
                COALESCE(oa4.avg_violations_per_estab, oa2.avg_violations_per_estab, oaall.avg_violations_per_estab, 2.23), 0.01
            ) >= 2.0 THEN 5
            WHEN COALESCE(t.total_violations, 0)::float * osha_decay.val / GREATEST(
                COALESCE(oa4.avg_violations_per_estab, oa2.avg_violations_per_estab, oaall.avg_violations_per_estab, 2.23), 0.01
            ) >= 1.5 THEN 4
            WHEN COALESCE(t.total_violations, 0)::float * osha_decay.val / GREATEST(
                COALESCE(oa4.avg_violations_per_estab, oa2.avg_violations_per_estab, oaall.avg_violations_per_estab, 2.23), 0.01
            ) >= 1.0 THEN 3
            ELSE 1
        END
        +
        -- Severity bonus with decay (0-3)
        LEAST(3, ROUND(
            (COALESCE(t.willful_count, 0) * 2 + COALESCE(t.repeat_count, 0))::float * osha_decay.val
        )::int)
    ) AS score_osha,

    -- OSHA industry ratio with temporal decay (for display)
    ROUND((
        COALESCE(t.total_violations, 0)::float * osha_decay.val / GREATEST(
            COALESCE(oa4.avg_violations_per_estab, oa2.avg_violations_per_estab, oaall.avg_violations_per_estab, 2.23), 0.01
        )
    )::numeric, 2) AS osha_industry_ratio,

    -- Factor 6: NLRB (10 pts)
    -- Blended state + industry rate (no decay -- population averages, not employer-specific)
    -- NOTE: Employer-specific NLRB decay (half-life 7yr) is applied in the detail
    -- endpoint for establishments that DO have F7 matches + NLRB election history.
    -- In the MV, all rows lack F7 matches (by design), so only the fallback applies.
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
    -- Primary: employer-specific Gower similarity (via F7 match path)
    -- Fallback: industry-average similarity by NAICS sector (for unmatched MV rows)
    CASE
        WHEN md.similarity_score >= 0.80 THEN 10
        WHEN md.similarity_score >= 0.60 THEN 7
        WHEN md.similarity_score >= 0.40 THEN 4
        WHEN md.similarity_score IS NOT NULL THEN 1
        -- Industry-average fallback (reduced by 50% since it's population-level, not employer-specific)
        WHEN ias.avg_similarity >= 0.90 THEN 5
        WHEN ias.avg_similarity >= 0.80 THEN 3
        WHEN ias.avg_similarity IS NOT NULL THEN 1
        ELSE 0
    END AS score_similarity,

    -- Temporal decay factors (for transparency / API)
    ROUND(osha_decay.val::numeric, 4) AS osha_decay_factor,
    -- NLRB decay always 1.0 in MV (no employer-specific NLRB data for unmatched rows)
    1.0::numeric AS nlrb_decay_factor,
    NULL::date AS last_election_date,

    -- Metadata
    fm.establishment_id IS NOT NULL AS has_f7_match,
    fc.establishment_id IS NOT NULL AS has_federal_contracts,
    fc.federal_obligations,
    fc.federal_contract_count,
    md.nlrb_predicted_win_pct,
    COALESCE(md.similarity_score, ias.avg_similarity) AS similarity_score,
    CASE
        WHEN md.similarity_score IS NOT NULL THEN 'employer'
        WHEN ias.avg_similarity IS NOT NULL THEN 'industry_avg'
        ELSE NULL
    END AS similarity_source

FROM v_osha_organizing_targets t

-- Temporal decay: OSHA half-life 10 years. lambda = LN(2)/10
-- Uses CURRENT_DATE, so scores are date-sensitive — refresh daily or weekly.
CROSS JOIN LATERAL (
    SELECT exp(-LN(2)/10 * GREATEST(0, (CURRENT_DATE - COALESCE(t.last_inspection_date, CURRENT_DATE))::float / 365.25)) AS val
) osha_decay

-- Factor 2: Industry density (hierarchical NAICS blend)
LEFT JOIN industry_density_blend idb ON idb.establishment_id = t.establishment_id

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

-- Factors 7, 9: contracts, similarity
LEFT JOIN f7_matches fm ON fm.establishment_id = t.establishment_id
LEFT JOIN fed_contracts fc ON fc.establishment_id = t.establishment_id
LEFT JOIN mergent_data md ON md.establishment_id = t.establishment_id
-- Factor 9 fallback: industry-average similarity for unmatched establishments
LEFT JOIN industry_avg_similarity ias ON ias.naics_2 = LEFT(t.naics_code, 2)

-- Exclude establishments already matched to F7 (union shops are not organizing targets)
WHERE fm.establishment_id IS NULL
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


def _ensure_score_versions_table(cur):
    """Create the score_versions table if it doesn't exist."""
    cur.execute(SCORE_VERSIONS_DDL)


def _record_version(cur, description, row_count):
    """Insert a score_versions row and return the version_id."""
    # Get score stats
    cur.execute("""
        SELECT
            MIN(score_company_unions + score_industry_density + score_geographic +
                score_size + score_osha + score_nlrb + score_contracts +
                score_projections + score_similarity) AS min_score,
            ROUND(AVG(score_company_unions + score_industry_density + score_geographic +
                score_size + score_osha + score_nlrb + score_contracts +
                score_projections + score_similarity)::numeric, 1) AS avg_score,
            MAX(score_company_unions + score_industry_density + score_geographic +
                score_size + score_osha + score_nlrb + score_contracts +
                score_projections + score_similarity) AS max_score,
            ROUND(AVG(osha_decay_factor)::numeric, 3) AS avg_osha_decay
        FROM mv_organizing_scorecard
    """)
    stats_row = cur.fetchone()
    score_stats = {
        "min_score": int(stats_row[0]) if stats_row[0] is not None else None,
        "avg_score": float(stats_row[1]) if stats_row[1] is not None else None,
        "max_score": int(stats_row[2]) if stats_row[2] is not None else None,
        "avg_osha_decay": float(stats_row[3]) if stats_row[3] is not None else None,
    }

    cur.execute("""
        INSERT INTO score_versions (description, row_count, factor_weights, decay_params, score_stats)
        VALUES (%s, %s, %s, %s, %s)
        RETURNING version_id, created_at
    """, (
        description,
        row_count,
        json.dumps(CURRENT_FACTOR_WEIGHTS),
        json.dumps(CURRENT_DECAY_PARAMS),
        json.dumps(score_stats),
    ))
    vid, created = cur.fetchone()
    return vid, created, score_stats


def create_mv(conn):
    """Drop and recreate the materialized view."""
    cur = conn.cursor()

    print("Ensuring score_versions table...")
    _ensure_score_versions_table(cur)
    conn.commit()

    print("Dropping old MV if exists...")
    cur.execute("DROP VIEW IF EXISTS v_organizing_scorecard CASCADE")
    cur.execute("DROP MATERIALIZED VIEW IF EXISTS mv_organizing_scorecard CASCADE")
    conn.commit()

    print("Creating/updating v_osha_organizing_targets...")
    cur.execute(VIEW_SQL)
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

    # Record version
    vid, created, stats = _record_version(cur, "MV full rebuild", count)
    conn.commit()
    print(f"  Score version: v{vid} ({created})")
    print(f"  Scores: min={stats['min_score']}, avg={stats['avg_score']}, max={stats['max_score']}")


def refresh_mv(conn):
    """Refresh the existing materialized view (CONCURRENTLY to avoid blocking reads)."""
    # REFRESH CONCURRENTLY cannot run inside a transaction block
    conn.autocommit = True
    cur = conn.cursor()

    _ensure_score_versions_table(cur)

    print("Refreshing mv_organizing_scorecard CONCURRENTLY...")
    t0 = time.time()
    cur.execute("REFRESH MATERIALIZED VIEW CONCURRENTLY mv_organizing_scorecard")
    elapsed = time.time() - t0

    cur.execute("SELECT COUNT(*) FROM mv_organizing_scorecard")
    count = cur.fetchone()[0]
    print(f"  Refreshed in {elapsed:.1f}s ({count:,} rows)")

    vid, created, stats = _record_version(cur, "MV concurrent refresh", count)
    print(f"  Score version: v{vid} ({created})")
    print(f"  Scores: min={stats['min_score']}, avg={stats['avg_score']}, max={stats['max_score']}")


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
