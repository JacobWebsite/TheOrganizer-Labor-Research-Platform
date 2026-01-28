-- CHECKPOINT 3B: Fix union local view to show desig_num as local number
-- Run with: psql -U postgres -d olms_multiyear -f fix_union_local_view.sql

\echo '=== Recreating v_union_local_search with proper local numbers ==='

DROP VIEW IF EXISTS v_union_local_search CASCADE;

CREATE VIEW v_union_local_search AS
SELECT 
    l.f_num as file_number,
    l.union_name,
    l.aff_abbr as affiliation,
    a.aff_name as affiliation_name,
    -- Build a display name like "SEIU Local 1199" or "IBT Local 120"
    CASE 
        WHEN l.desig_num IS NOT NULL AND l.desig_num != '' 
        THEN COALESCE(l.aff_abbr, '') || ' ' || COALESCE(l.desig_name, 'Local') || ' ' || l.desig_num
        ELSE l.union_name
    END as local_display_name,
    l.desig_name,
    l.desig_num as local_number,
    l.city,
    l.state,
    l.members,
    l.total_assets,
    l.total_receipts,
    l.total_disbursements,
    l.yr_covered as fiscal_year,
    COALESCE(f7.employer_count, 0) as f7_employer_count,
    COALESCE(f7.total_workers, 0) as f7_total_workers
FROM lm_data l
LEFT JOIN crosswalk_affiliation_sector_map a ON l.aff_abbr = a.aff_abbr
LEFT JOIN (
    -- Aggregate F-7 employer data, filtered to last 5 years
    SELECT 
        latest_union_fnum,
        COUNT(*) as employer_count,
        SUM(latest_unit_size) as total_workers
    FROM f7_employers
    WHERE latest_notice_date >= '2020-01-01'  -- Last 5 years
    GROUP BY latest_union_fnum
) f7 ON l.f_num = f7.latest_union_fnum::text
WHERE l.yr_covered = 2024;

\echo ''
\echo '=== Test: SEIU locals with local numbers ==='
SELECT file_number, local_display_name, local_number, city, state, members, f7_employer_count
FROM v_union_local_search
WHERE affiliation = 'SEIU' AND members > 5000
ORDER BY members DESC
LIMIT 15;

\echo ''
\echo '=== Test: CWA locals with local numbers ==='
SELECT file_number, local_display_name, local_number, city, state, members
FROM v_union_local_search
WHERE affiliation = 'CWA' AND members > 1000
ORDER BY members DESC
LIMIT 15;

\echo ''
\echo '=== Test: IBT locals with local numbers ==='
SELECT file_number, local_display_name, local_number, city, state, members
FROM v_union_local_search
WHERE affiliation = 'IBT' AND members > 5000
ORDER BY members DESC
LIMIT 15;
