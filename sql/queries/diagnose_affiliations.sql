-- CHECKPOINT 1: Diagnose Affiliation Coverage Issues
-- Run with: psql -U postgres -d olms_multiyear -f diagnose_affiliations.sql

\echo '=== 1. Affiliations in LM data vs Crosswalk ==='
-- What affiliations exist in LM data?
SELECT aff_abbr, COUNT(*) as unions_2024, SUM(members) as total_members
FROM lm_data 
WHERE yr_covered = 2024 AND aff_abbr IS NOT NULL
GROUP BY aff_abbr
ORDER BY total_members DESC
LIMIT 30;

\echo ''
\echo '=== 2. Affiliations in LM but NOT in crosswalk mapping ==='
SELECT DISTINCT l.aff_abbr, COUNT(*) as union_count, SUM(l.members) as total_members
FROM lm_data l
LEFT JOIN crosswalk_affiliation_sector_map a ON l.aff_abbr = a.aff_abbr
WHERE l.yr_covered = 2024 AND l.aff_abbr IS NOT NULL AND a.aff_abbr IS NULL
GROUP BY l.aff_abbr
ORDER BY total_members DESC;

\echo ''
\echo '=== 3. CWA specifically - is it in the data? ==='
SELECT aff_abbr, COUNT(*) as count, SUM(members) as members
FROM lm_data 
WHERE yr_covered = 2024 AND (aff_abbr LIKE '%CWA%' OR union_name LIKE '%COMMUNICATION%')
GROUP BY aff_abbr;

\echo ''
\echo '=== 4. Sample CWA locals ==='
SELECT f_num, union_name, aff_abbr, city, state, members
FROM lm_data 
WHERE yr_covered = 2024 AND union_name LIKE '%COMMUNICATION%'
ORDER BY members DESC
LIMIT 10;

\echo ''
\echo '=== 5. What is in the crosswalk_affiliation_sector_map? ==='
SELECT aff_abbr, aff_name, sector_code
FROM crosswalk_affiliation_sector_map
ORDER BY aff_abbr
LIMIT 60;

\echo ''
\echo '=== 6. F-7 employers with NO affiliation match ==='
SELECT COUNT(*) as total_employers,
       SUM(CASE WHEN affiliation IS NULL THEN 1 ELSE 0 END) as no_affiliation,
       ROUND(100.0 * SUM(CASE WHEN affiliation IS NULL THEN 1 ELSE 0 END) / COUNT(*), 1) as pct_no_match
FROM v_employer_search;

\echo ''
\echo '=== 7. Sample F-7 employers with no affiliation ==='
SELECT employer_name, city, state, bargaining_unit_size, 
       union_file_number, union_name_f7, union_name_lm
FROM v_employer_search
WHERE affiliation IS NULL
ORDER BY bargaining_unit_size DESC NULLS LAST
LIMIT 15;

\echo ''
\echo '=== 8. Check if union file numbers match between F-7 and LM ==='
-- How many F-7 union file numbers exist in LM data?
SELECT 
    COUNT(DISTINCT e.latest_union_fnum) as f7_union_fnums,
    COUNT(DISTINCT CASE WHEN l.f_num IS NOT NULL THEN e.latest_union_fnum END) as matched_in_lm,
    COUNT(DISTINCT CASE WHEN l.f_num IS NULL THEN e.latest_union_fnum END) as not_in_lm
FROM f7_employers e
LEFT JOIN (SELECT DISTINCT f_num FROM lm_data WHERE yr_covered = 2024) l 
    ON e.latest_union_fnum::text = l.f_num;

\echo ''
\echo '=== 9. Sample F-7 unions NOT in LM data ==='
SELECT DISTINCT e.latest_union_fnum, e.latest_union_name, COUNT(*) as employer_count
FROM f7_employers e
LEFT JOIN lm_data l ON e.latest_union_fnum::text = l.f_num AND l.yr_covered = 2024
WHERE l.f_num IS NULL AND e.latest_union_fnum IS NOT NULL
GROUP BY e.latest_union_fnum, e.latest_union_name
ORDER BY employer_count DESC
LIMIT 20;
