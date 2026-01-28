-- Labor Relations Platform - Search Views
-- Database: olms_multiyear
-- Run with: psql -U postgres -d olms_multiyear -f create_search_views.sql

-- ============================================================
-- VIEW 1: Employer Search View
-- Combines F-7 employers with union info and affiliations
-- ============================================================

DROP VIEW IF EXISTS v_employer_search CASCADE;

CREATE VIEW v_employer_search AS
SELECT 
    e.employer_id,
    e.employer_name,
    e.city,
    e.state,
    e.street,
    e.zip,
    e.naics,
    e.latest_unit_size as bargaining_unit_size,
    e.latest_notice_date,
    e.filing_count,
    e.healthcare_related,
    e.potentially_defunct,
    e.latitude,
    e.longitude,
    e.geocode_status,
    e.latest_union_fnum as union_file_number,
    e.latest_union_name as union_name_f7,
    -- Join to get canonical union info from LM data
    lm.union_name as union_name_lm,
    lm.aff_abbr as affiliation,
    -- Join to get affiliation full name
    aff.aff_name as affiliation_name
FROM f7_employers e
LEFT JOIN (
    SELECT DISTINCT ON (f_num) 
        f_num, union_name, aff_abbr
    FROM lm_data 
    WHERE yr_covered = 2024
    ORDER BY f_num, rpt_id DESC
) lm ON e.latest_union_fnum::text = lm.f_num
LEFT JOIN crosswalk_affiliation_sector_map aff ON lm.aff_abbr = aff.aff_abbr;

-- ============================================================
-- VIEW 2: Union Local Search View
-- Shows locals with their employer counts and LM financials
-- ============================================================

DROP VIEW IF EXISTS v_union_local_search CASCADE;

CREATE VIEW v_union_local_search AS
SELECT 
    lm.f_num as file_number,
    lm.union_name,
    lm.aff_abbr as affiliation,
    aff.aff_name as affiliation_name,
    lm.city,
    lm.state,
    lm.members,
    lm.ttl_assets as total_assets,
    lm.ttl_receipts as total_receipts,
    lm.ttl_disbursements as total_disbursements,
    lm.yr_covered as fiscal_year,
    -- Count employers from F-7
    COALESCE(emp.employer_count, 0) as f7_employer_count,
    COALESCE(emp.total_workers, 0) as f7_total_workers
FROM lm_data lm
LEFT JOIN crosswalk_affiliation_sector_map aff ON lm.aff_abbr = aff.aff_abbr
LEFT JOIN (
    SELECT 
        latest_union_fnum,
        COUNT(DISTINCT employer_id) as employer_count,
        SUM(latest_unit_size) as total_workers
    FROM f7_employers
    GROUP BY latest_union_fnum
) emp ON lm.f_num = emp.latest_union_fnum::text
WHERE lm.yr_covered = 2024;

-- ============================================================
-- VIEW 3: Union LM Detail View
-- Full LM financial data for detailed union search
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
-- VIEW 4: Affiliation Summary View
-- Aggregated stats by national union affiliation
-- ============================================================

DROP VIEW IF EXISTS v_affiliation_summary CASCADE;

CREATE VIEW v_affiliation_summary AS
WITH union_aff AS (
    SELECT DISTINCT f_num, aff_abbr
    FROM lm_data
    WHERE yr_covered = 2024 AND aff_abbr IS NOT NULL
)
SELECT 
    a.aff_abbr as affiliation,
    a.aff_name as affiliation_name,
    COUNT(DISTINCT lm.f_num) as local_count,
    SUM(lm.members) as total_members,
    SUM(lm.ttl_assets) as total_assets,
    SUM(lm.ttl_receipts) as total_receipts,
    COUNT(DISTINCT e.employer_id) as f7_employer_count,
    SUM(e.latest_unit_size) as f7_total_workers
FROM crosswalk_affiliation_sector_map a
LEFT JOIN lm_data lm ON a.aff_abbr = lm.aff_abbr AND lm.yr_covered = 2024
LEFT JOIN f7_employers e ON lm.f_num = e.latest_union_fnum::text
GROUP BY a.aff_abbr, a.aff_name
ORDER BY total_members DESC NULLS LAST;

-- ============================================================
-- VIEW 5: State Density with Employer Counts
-- Combines density data with F-7 employer presence
-- ============================================================

DROP VIEW IF EXISTS v_state_overview CASCADE;

CREATE VIEW v_state_overview AS
SELECT 
    s.state,
    s.sector,
    s.pct_members as union_density,
    s.members_thousands * 1000 as union_members,
    s.employment_thousands * 1000 as total_employment,
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

-- ============================================================
-- INDEXES for search performance
-- ============================================================

-- May already exist, so use IF NOT EXISTS pattern via DO block
DO $$
BEGIN
    -- Employer search indexes
    IF NOT EXISTS (SELECT 1 FROM pg_indexes WHERE indexname = 'idx_f7_emp_name_trgm') THEN
        CREATE INDEX idx_f7_emp_name_lower ON f7_employers(LOWER(employer_name));
    END IF;
    
    -- LM data indexes for search
    IF NOT EXISTS (SELECT 1 FROM pg_indexes WHERE indexname = 'idx_lm_union_name_lower') THEN
        CREATE INDEX idx_lm_union_name_lower ON lm_data(LOWER(union_name));
    END IF;
    
    IF NOT EXISTS (SELECT 1 FROM pg_indexes WHERE indexname = 'idx_lm_aff_abbr') THEN
        CREATE INDEX idx_lm_aff_abbr ON lm_data(aff_abbr);
    END IF;
    
    IF NOT EXISTS (SELECT 1 FROM pg_indexes WHERE indexname = 'idx_lm_state') THEN
        CREATE INDEX idx_lm_state ON lm_data(state);
    END IF;
END $$;

-- ============================================================
-- Verify views created
-- ============================================================

SELECT 'Views created:' as status;
SELECT table_name as view_name 
FROM information_schema.views 
WHERE table_schema = 'public' AND table_name LIKE 'v_%'
ORDER BY table_name;
