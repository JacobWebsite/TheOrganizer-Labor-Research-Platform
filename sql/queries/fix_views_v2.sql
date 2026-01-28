-- Fix v_union_lm_detail - remove non-existent columns
-- Fix v_state_overview - state name mismatch

-- First check what cash columns exist
\echo '=== Checking lm_data columns ==='
SELECT column_name FROM information_schema.columns 
WHERE table_name = 'lm_data' 
AND (column_name LIKE '%cash%' OR column_name LIKE '%asset%' OR column_name LIKE '%receipt%')
ORDER BY column_name;

-- ============================================================
-- VIEW: Union LM Detail View (simplified - no cash columns)
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
-- State abbreviation lookup table
-- ============================================================

DROP TABLE IF EXISTS state_abbrev CASCADE;

CREATE TABLE state_abbrev (
    state_name TEXT PRIMARY KEY,
    state_abbr CHAR(2) NOT NULL
);

INSERT INTO state_abbrev (state_name, state_abbr) VALUES
('Alabama', 'AL'), ('Alaska', 'AK'), ('Arizona', 'AZ'), ('Arkansas', 'AR'),
('California', 'CA'), ('Colorado', 'CO'), ('Connecticut', 'CT'), ('Delaware', 'DE'),
('District of Columbia', 'DC'), ('Florida', 'FL'), ('Georgia', 'GA'), ('Hawaii', 'HI'),
('Idaho', 'ID'), ('Illinois', 'IL'), ('Indiana', 'IN'), ('Iowa', 'IA'),
('Kansas', 'KS'), ('Kentucky', 'KY'), ('Louisiana', 'LA'), ('Maine', 'ME'),
('Maryland', 'MD'), ('Massachusetts', 'MA'), ('Michigan', 'MI'), ('Minnesota', 'MN'),
('Mississippi', 'MS'), ('Missouri', 'MO'), ('Montana', 'MT'), ('Nebraska', 'NE'),
('Nevada', 'NV'), ('New Hampshire', 'NH'), ('New Jersey', 'NJ'), ('New Mexico', 'NM'),
('New York', 'NY'), ('North Carolina', 'NC'), ('North Dakota', 'ND'), ('Ohio', 'OH'),
('Oklahoma', 'OK'), ('Oregon', 'OR'), ('Pennsylvania', 'PA'), ('Rhode Island', 'RI'),
('South Carolina', 'SC'), ('South Dakota', 'SD'), ('Tennessee', 'TN'), ('Texas', 'TX'),
('Utah', 'UT'), ('Vermont', 'VT'), ('Virginia', 'VA'), ('Washington', 'WA'),
('West Virginia', 'WV'), ('Wisconsin', 'WI'), ('Wyoming', 'WY');

-- ============================================================
-- Fix v_state_overview to use abbreviation lookup
-- ============================================================

DROP VIEW IF EXISTS v_state_overview CASCADE;

CREATE VIEW v_state_overview AS
SELECT 
    s.state,
    sa.state_abbr,
    s.sector,
    s.pct_members as union_density,
    (s.members_thousands * 1000)::bigint as union_members,
    (s.employment_thousands * 1000)::bigint as total_employment,
    s.year as density_year,
    COALESCE(emp.employer_count, 0) as f7_employers,
    COALESCE(emp.union_count, 0) as unions_with_employers
FROM unionstats_state s
LEFT JOIN state_abbrev sa ON s.state = sa.state_name
LEFT JOIN (
    SELECT 
        state,
        COUNT(DISTINCT employer_id) as employer_count,
        COUNT(DISTINCT latest_union_fnum) as union_count
    FROM f7_employers
    GROUP BY state
) emp ON sa.state_abbr = emp.state
WHERE s.year = 2024 AND s.sector = 'Total';

-- ============================================================
-- Verify and test
-- ============================================================

\echo ''
\echo '=== v_union_lm_detail created - testing ==='
SELECT file_number, union_name, affiliation, state,
       members, total_assets, assets_per_member
FROM v_union_lm_detail
WHERE fiscal_year = 2024
ORDER BY total_assets DESC NULLS LAST
LIMIT 10;

\echo ''
\echo '=== v_state_overview fixed - testing ==='
SELECT state, state_abbr,
       ROUND((union_density * 100)::numeric, 1) as density_pct,
       union_members as members,
       f7_employers,
       unions_with_employers
FROM v_state_overview
ORDER BY union_density DESC
LIMIT 10;

\echo ''
\echo '=== ALL FIXES COMPLETE ==='
