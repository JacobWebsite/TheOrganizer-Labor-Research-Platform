-- CHECKPOINT 3: Diagnose F-7 to LM Matching Issues
-- Run with: psql -U postgres -d olms_multiyear -f diagnose_f7_matching.sql

\echo '=== 1. F-7 employers by union_file_number status ==='
SELECT 
    CASE 
        WHEN latest_union_fnum IS NULL THEN 'NULL file number'
        ELSE 'Has file number'
    END as status,
    COUNT(*) as employer_count,
    ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER(), 1) as pct
FROM f7_employers
GROUP BY 1;

\echo ''
\echo '=== 2. Of those WITH file numbers, how many match LM 2024? ==='
SELECT 
    CASE WHEN l.f_num IS NOT NULL THEN 'Matched LM 2024' ELSE 'No LM 2024 match' END as status,
    COUNT(*) as employer_count
FROM f7_employers e
LEFT JOIN (SELECT DISTINCT f_num FROM lm_data WHERE yr_covered = 2024) l 
    ON e.latest_union_fnum::text = l.f_num
WHERE e.latest_union_fnum IS NOT NULL
GROUP BY 1;

\echo ''
\echo '=== 3. What about matching ANY year of LM data? ==='
SELECT 
    CASE WHEN l.f_num IS NOT NULL THEN 'Matched LM (any year)' ELSE 'No LM match ever' END as status,
    COUNT(*) as employer_count
FROM f7_employers e
LEFT JOIN (SELECT DISTINCT f_num FROM lm_data) l 
    ON e.latest_union_fnum::text = l.f_num
WHERE e.latest_union_fnum IS NOT NULL
GROUP BY 1;

\echo ''
\echo '=== 4. Sample F-7 with NULL file number - what union names do they have? ==='
SELECT latest_union_name, COUNT(*) as employer_count, SUM(latest_unit_size) as total_workers
FROM f7_employers
WHERE latest_union_fnum IS NULL
GROUP BY latest_union_name
ORDER BY employer_count DESC
LIMIT 25;

\echo ''
\echo '=== 5. Can we parse affiliation from union name text? ==='
-- Test pattern matching on union names without file numbers
SELECT 
    CASE 
        WHEN latest_union_name ILIKE '%SEIU%' OR latest_union_name ILIKE '%SERVICE EMPLOYEE%' THEN 'SEIU'
        WHEN latest_union_name ILIKE '%TEAMSTER%' OR latest_union_name ILIKE '%IBT%' THEN 'IBT'
        WHEN latest_union_name ILIKE '%UFCW%' OR latest_union_name ILIKE '%FOOD%COMMERCIAL%' THEN 'UFCW'
        WHEN latest_union_name ILIKE '%AFSCME%' OR latest_union_name ILIKE '%STATE%COUNTY%MUNICIPAL%' THEN 'AFSCME'
        WHEN latest_union_name ILIKE '%UAW%' OR latest_union_name ILIKE '%AUTO WORKER%' THEN 'UAW'
        WHEN latest_union_name ILIKE '%CWA%' OR latest_union_name ILIKE '%COMMUNICATION%WORKER%' THEN 'CWA'
        WHEN latest_union_name ILIKE '%IBEW%' OR latest_union_name ILIKE '%ELECTRICAL WORKER%' THEN 'IBEW'
        WHEN latest_union_name ILIKE '%USW%' OR latest_union_name ILIKE '%STEELWORKER%' THEN 'USW'
        WHEN latest_union_name ILIKE '%OPERATING ENGINEER%' OR latest_union_name ILIKE '%IUOE%' THEN 'IUOE'
        WHEN latest_union_name ILIKE '%SAG%' OR latest_union_name ILIKE '%AFTRA%' OR latest_union_name ILIKE '%SCREEN ACTOR%' THEN 'SAGAFTRA'
        WHEN latest_union_name ILIKE '%APWU%' OR latest_union_name ILIKE '%POSTAL WORKER%' THEN 'APWU'
        WHEN latest_union_name ILIKE '%AFGE%' OR latest_union_name ILIKE '%GOVERNMENT EMPLOYEE%' THEN 'AFGE'
        WHEN latest_union_name ILIKE '%UNITE HERE%' OR latest_union_name ILIKE '%HOTEL%' THEN 'UNITHE'
        WHEN latest_union_name ILIKE '%NURSE%' THEN 'NNU'
        WHEN latest_union_name ILIKE '%CARPENTER%' THEN 'CJA'
        WHEN latest_union_name ILIKE '%LABORER%' OR latest_union_name ILIKE '%LIUNA%' THEN 'LIUNA'
        WHEN latest_union_name ILIKE '%MACHINIST%' OR latest_union_name ILIKE '%IAM%' THEN 'IAM'
        WHEN latest_union_name ILIKE '%PLUMBER%' OR latest_union_name ILIKE '%PIPEFITTER%' THEN 'PPF'
        WHEN latest_union_name ILIKE '%AFT%' OR latest_union_name ILIKE '%TEACHER%' THEN 'AFT'
        WHEN latest_union_name ILIKE '%NEA%' OR latest_union_name ILIKE '%EDUCATION ASSOC%' THEN 'NEA'
        WHEN latest_union_name ILIKE '%FIREFIGHTER%' OR latest_union_name ILIKE '%IAFF%' THEN 'IAFF'
        WHEN latest_union_name ILIKE '%OPEIU%' OR latest_union_name ILIKE '%OFFICE%PROFESSIONAL%' THEN 'OPEIU'
        ELSE 'UNKNOWN'
    END as parsed_affiliation,
    COUNT(*) as employer_count
FROM f7_employers
WHERE latest_union_fnum IS NULL
GROUP BY 1
ORDER BY employer_count DESC;

\echo ''
\echo '=== 6. F-7 historical data - date range and duplicates ==='
SELECT 
    MIN(latest_notice_date) as earliest_notice,
    MAX(latest_notice_date) as latest_notice,
    COUNT(*) as total_employers,
    COUNT(DISTINCT employer_name || COALESCE(city,'') || COALESCE(state,'')) as unique_name_city_state
FROM f7_employers;

\echo ''
\echo '=== 7. How many F-7 employers have identical name+unit_size (potential dupes)? ==='
SELECT COUNT(*) as duplicate_groups, SUM(cnt) as total_records
FROM (
    SELECT employer_name, latest_unit_size, COUNT(*) as cnt
    FROM f7_employers
    WHERE employer_name IS NOT NULL
    GROUP BY employer_name, latest_unit_size
    HAVING COUNT(*) > 1
) dups;

\echo ''
\echo '=== 8. Sample duplicate employer names ==='
SELECT employer_name, latest_unit_size, COUNT(*) as occurrences,
       array_agg(DISTINCT city) as cities,
       array_agg(DISTINCT latest_notice_date ORDER BY latest_notice_date DESC) as notice_dates
FROM f7_employers
WHERE employer_name IS NOT NULL
GROUP BY employer_name, latest_unit_size
HAVING COUNT(*) > 3
ORDER BY COUNT(*) DESC
LIMIT 15;

\echo ''
\echo '=== 9. Check local number in union_name vs desig_num in LM ==='
-- LM data has desig_num (local designation number)
SELECT f_num, union_name, desig_name, desig_num, city, state
FROM lm_data
WHERE yr_covered = 2024 AND desig_num IS NOT NULL AND desig_num != ''
ORDER BY members DESC
LIMIT 15;
