-- CHECKPOINT 3B: Diagnose local number availability
-- Run with: psql -U postgres -d olms_multiyear -f diagnose_local_numbers.sql

\echo '=== 1. LM data local number fields (desig_name + desig_num) ==='
SELECT desig_name, COUNT(*) as count
FROM lm_data 
WHERE yr_covered = 2024
GROUP BY desig_name
ORDER BY count DESC
LIMIT 15;

\echo ''
\echo '=== 2. Sample locals with desig_num ==='
SELECT f_num, union_name, aff_abbr, desig_name, desig_num, city, state, members
FROM lm_data 
WHERE yr_covered = 2024 AND desig_num IS NOT NULL AND desig_num != '' AND members > 10000
ORDER BY members DESC
LIMIT 20;

\echo ''
\echo '=== 3. SEIU locals - do they have meaningful desig_num? ==='
SELECT f_num, union_name, desig_name, desig_num, city, state, members
FROM lm_data 
WHERE yr_covered = 2024 AND aff_abbr = 'SEIU' AND members > 5000
ORDER BY members DESC
LIMIT 15;

\echo ''
\echo '=== 4. CWA locals - what local numbers? ==='
SELECT f_num, union_name, desig_name, desig_num, city, state, members
FROM lm_data 
WHERE yr_covered = 2024 AND aff_abbr = 'CWA' AND members > 1000
ORDER BY members DESC
LIMIT 15;

\echo ''
\echo '=== 5. IBT locals - what local numbers? ==='
SELECT f_num, union_name, desig_name, desig_num, city, state, members
FROM lm_data 
WHERE yr_covered = 2024 AND aff_abbr = 'IBT' AND members > 5000
ORDER BY members DESC
LIMIT 15;

\echo ''
\echo '=== 6. F-7 union names - can we parse local numbers from text? ==='
-- Check if local numbers appear in the F-7 union name field
SELECT latest_union_name, COUNT(*) as employer_count
FROM f7_employers
WHERE latest_union_name ~ '-[0-9]+' OR latest_union_name ~ 'Local [0-9]+'
GROUP BY latest_union_name
ORDER BY employer_count DESC
LIMIT 20;
