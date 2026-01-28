-- Fix missing view and ROUND issue
-- Database: olms_multiyear

-- ============================================================
-- VIEW: Union LM Detail View (was missing)
-- ============================================================

DROP VIEW IF EXISTS v_union_lm_detail CASCADE;

CREATE VIEW v_union_lm_detail AS
SELECT 
    lm.rpt_id,
    lm.f_num as file_number,
    lm.union_name,
    lm.aff_abbr as affiliation,
    aff.aff_name as affiliation_name,
    lm.desig_name,
    lm.desig_num,
    lm.city,
    lm.state,
    lm.yr_covered as fiscal_year,
    lm.members,
    lm.ttl_assets as total_assets,
    lm.ttl_liabilities as total_liabilities,
    lm.ttl_receipts as total_receipts,
    lm.ttl_disbursements as total_disbursements,
    lm.begin_cash as cash_start,
    lm.end_cash as cash_end,
    -- Derived metrics
    CASE WHEN lm.ttl_assets > 0 
         THEN ROUND((lm.ttl_liabilities / lm.ttl_assets * 100)::numeric, 1) 
         ELSE NULL END as debt_ratio_pct,
    CASE WHEN lm.members > 0 
         THEN ROUND((lm.ttl_assets / lm.members)::numeric, 0) 
         ELSE NULL END as assets_per_member,
    CASE WHEN lm.members > 0 
         THEN ROUND((lm.ttl_receipts / lm.members)::numeric, 0) 
         ELSE NULL END as receipts_per_member
FROM lm_data lm
LEFT JOIN crosswalk_affiliation_sector_map aff ON lm.aff_abbr = aff.aff_abbr;

-- ============================================================
-- Fix v_state_overview to cast properly
-- ============================================================

DROP VIEW IF EXISTS v_state_overview CASCADE;

CREATE VIEW v_state_overview AS
SELECT 
    s.state,
    s.sector,
    s.pct_members as union_density,
    (s.members_thousands * 1000)::bigint as union_members,
    (s.employment_thousands * 1000)::bigint as total_employment,
    s.year as density_year,
    COALESCE(emp.employer_count, 0) as f7_employers,
    COALESCE(emp.union_count, 0) as unions_with_employers
FROM unionstats_state s
LEFT JOIN (
    SELECT 
        state,
        COUNT(DISTINCT employer_id) as employer_count,
        COUNT(DISTINCT latest_union_fnum) as union_count
    FROM f7_employers
    GROUP BY state
) emp ON s.state = emp.state
WHERE s.year = 2024 AND s.sector = 'Total';

-- Verify
SELECT 'Fixed views created:' as status;

-- Re-run the failed tests
\echo ''
\echo '=== TEST 4 (fixed): Largest Unions by Assets (2024) ==='
SELECT file_number, union_name, affiliation, state,
       members, total_assets, total_receipts,
       assets_per_member
FROM v_union_lm_detail
WHERE fiscal_year = 2024
ORDER BY total_assets DESC NULLS LAST
LIMIT 10;

\echo ''
\echo '=== TEST 5 (fixed): States by Union Density ==='
SELECT state, 
       ROUND((union_density * 100)::numeric, 1) as density_pct,
       union_members as members,
       f7_employers,
       unions_with_employers
FROM v_state_overview
ORDER BY union_density DESC
LIMIT 10;
