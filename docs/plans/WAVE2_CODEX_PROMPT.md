# Codex Prompt: Code Review of 5.2 (NAICS Hierarchy) + 5.3 (Score Versioning)

**When to send:** Now (Wave 2)

---

TASK: Code review the hierarchical NAICS similarity integration (5.2) and score version tracking system (5.3) for the organizing scorecard.

CONTEXT:
Phase 5 Wave 1 added three features to the scoring system:
- 5.1 Temporal decay on OSHA violations (already reviewed by you — CRITICAL finding fixed)
- 5.2 Hierarchical NAICS similarity replacing binary 2-digit matching in Factor 2
- 5.3 Score version tracking table with auto-recording on every MV create/refresh

The MV produces 22,389 rows in 8.5s. 306 tests pass.

REVIEW CHECKLIST:

**5.2 NAICS Hierarchy:**
1. SIMILARITY GRADIENT: Are the weights (6-digit=1.0, 5=0.85, 4=0.65, 3=0.45, 2=0.25) reasonable? Is there a gap between levels that could cause cliff effects?
2. LATERAL JOIN: The NAICS similarity uses a LATERAL subquery with ORDER BY + LIMIT 1. Is this the most efficient approach for 22K rows x 459 state-industry rows? Could a materialized lookup or hash join be faster?
3. NAICS NORMALIZATION: The SQL uses `regexp_replace(COALESCE(t.naics_code::text, ''), '[^0-9]', '', 'g')` repeatedly. This is computed multiple times per row in the CASE ladder. Is this a performance concern?
4. BLEND FORMULA: `national * (1 - similarity) + state * similarity`. When similarity=0 (no match), it falls back to pure national. When similarity=1, pure state. Is this mathematically correct for partial matches?
5. NULL HANDLING: What happens when naics_code is NULL, site_state is NULL, or estimated_state_industry_density has no matching state?
6. TEST COVERAGE: The test uses inline CTEs that mirror the MV SQL. Are the tests actually testing the MV or just testing themselves? Is there a risk of the test diverging from the MV?

**5.3 Score Versioning:**
1. SCHEMA: Is the `score_versions` table schema sufficient for audit/comparison needs? Missing anything?
2. AUTO-INSERT: Versions are auto-inserted on both create_mv() and refresh_mv(). Is there a risk of version inflation (e.g., accidental double-refresh)?
3. API ENDPOINT: `GET /api/admin/score-versions` returns version history. Does it have proper auth checks?
4. FACTOR_WEIGHTS JSONB: The `CURRENT_FACTOR_WEIGHTS` dict is defined in Python and inserted as JSONB. If someone changes the MV SQL without updating the Python dict, versions will record stale metadata. Is this a maintenance risk?
5. REFRESH ENDPOINT: The `/api/admin/refresh-scorecard` endpoint now also inserts a version row, but uses a simplified `factor_weights` (`{"refresh_source": "api"}`). Should this match the full dict from the script?

---

## FILE 1: scripts/scoring/create_scorecard_mv.py (534 lines)

```python
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


# -- Score versioning --
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
    "similarity": {"max": 10, "source": "gower_distance"},
}

CURRENT_DECAY_PARAMS = {
    "osha": {"half_life_years": 10, "lambda_expr": "LN(2)/10", "applied_to": "violation_count_and_severity"},
    "nlrb": {"half_life_years": 7, "lambda_expr": "LN(2)/7", "applied_in": "detail_endpoint_only",
             "note": "MV excludes F7-matched rows; NLRB routes through F7"},
}


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
    LEFT JOIN LATERAL (
        SELECT
            s.estimated_density,
            CASE
                WHEN regexp_replace(COALESCE(t.naics_code::text, ''), '[^0-9]', '', 'g') = '' THEN 0.0
                WHEN LENGTH(regexp_replace(COALESCE(t.naics_code::text, ''), '[^0-9]', '', 'g')) >= 6
                 AND LENGTH(s.industry_code_norm) >= 6
                 AND LEFT(regexp_replace(COALESCE(t.naics_code::text, ''), '[^0-9]', '', 'g'), 6) = LEFT(s.industry_code_norm, 6) THEN 1.0
                WHEN LENGTH(regexp_replace(COALESCE(t.naics_code::text, ''), '[^0-9]', '', 'g')) >= 5
                 AND LENGTH(s.industry_code_norm) >= 5
                 AND LEFT(regexp_replace(COALESCE(t.naics_code::text, ''), '[^0-9]', '', 'g'), 5) = LEFT(s.industry_code_norm, 5) THEN 0.85
                WHEN LENGTH(regexp_replace(COALESCE(t.naics_code::text, ''), '[^0-9]', '', 'g')) >= 4
                 AND LENGTH(s.industry_code_norm) >= 4
                 AND LEFT(regexp_replace(COALESCE(t.naics_code::text, ''), '[^0-9]', '', 'g'), 4) = LEFT(s.industry_code_norm, 4) THEN 0.65
                WHEN LENGTH(regexp_replace(COALESCE(t.naics_code::text, ''), '[^0-9]', '', 'g')) >= 3
                 AND LENGTH(s.industry_code_norm) >= 3
                 AND LEFT(regexp_replace(COALESCE(t.naics_code::text, ''), '[^0-9]', '', 'g'), 3) = LEFT(s.industry_code_norm, 3) THEN 0.45
                WHEN LENGTH(regexp_replace(COALESCE(t.naics_code::text, ''), '[^0-9]', '', 'g')) >= 2
                 AND LENGTH(s.industry_code_norm) >= 2
                 AND LEFT(regexp_replace(COALESCE(t.naics_code::text, ''), '[^0-9]', '', 'g'), 2) = LEFT(s.industry_code_norm, 2) THEN 0.25
                ELSE 0.0
            END AS naics_similarity
        FROM state_industry_density s
        WHERE s.state = t.site_state
        ORDER BY naics_similarity DESC, COALESCE(s.year, 0) DESC, s.industry_code_norm
        LIMIT 1
    ) sb ON TRUE
),
[... rest of CTEs unchanged from prior review ...]

SELECT
    [... columns ...]

    -- Factor 2: Industry density with hierarchical NAICS blend (10 pts)
    CASE
        WHEN t.naics_code IS NULL THEN 2
        WHEN COALESCE(idb.blended_density_pct, 0) > 20 THEN 10
        WHEN COALESCE(idb.blended_density_pct, 0) > 10 THEN 8
        WHEN COALESCE(idb.blended_density_pct, 0) > 5 THEN 5
        ELSE 2
    END AS score_industry_density,

    [... Factor 5 OSHA with decay (reviewed in Round 1) ...]

    -- Factor 6: NLRB (10 pts)
    -- Blended state + industry rate (no decay -- population averages)
    -- NOTE: Employer-specific NLRB decay applied in detail endpoint only.
    CASE
        WHEN (...blended rate...) >= 82 THEN 10
        WHEN (...) >= 78 THEN 8
        WHEN (...) >= 74 THEN 5
        WHEN (...) >= 70 THEN 3
        ELSE 1
    END AS score_nlrb,

    [... Factors 7-9 unchanged ...]

    -- Temporal decay factors (for transparency / API)
    ROUND(osha_decay.val::numeric, 4) AS osha_decay_factor,
    1.0::numeric AS nlrb_decay_factor,
    NULL::date AS last_election_date,

FROM v_osha_organizing_targets t
CROSS JOIN LATERAL (
    SELECT exp(-LN(2)/10 * GREATEST(0, (CURRENT_DATE - COALESCE(t.last_inspection_date, CURRENT_DATE))::float / 365.25)) AS val
) osha_decay
LEFT JOIN industry_density_blend idb ON idb.establishment_id = t.establishment_id
[... other JOINs ...]
WHERE fm.establishment_id IS NULL
"""

# Python functions: _ensure_score_versions_table, _record_version, create_mv, refresh_mv
# (see full file above)
```

## FILE 2: tests/test_naics_hierarchy_scoring.py (282 lines)

12 tests using inline CTE helper `_run_factor2()` that mirrors the MV SQL.
Tests: 6-digit exact, 5/4/3/2-digit partial, no-match, NULL NAICS, state density, fallback to national, blend weights, MV integration (non-default scores, range check).

## FILE 3: tests/test_score_versioning.py (142 lines)

12 tests: table exists, columns, at least one version, row_count, JSONB validity, score_stats keys/values, ordering, API endpoint (GET + limit param).

## FILE 4: API changes in api/routers/organizing.py

New endpoint: `GET /api/admin/score-versions` (admin-only, returns version history with limit param).
Modified: `POST /api/admin/refresh-scorecard` now auto-inserts a score_versions row after refresh.

OUTPUT: Return findings as: CRITICAL (must fix), IMPORTANT (should fix), SUGGESTION (nice to have).
