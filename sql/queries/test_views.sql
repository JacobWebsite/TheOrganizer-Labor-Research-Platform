-- ============================================================
-- CHECKPOINT 2: Test Search Views
-- Database: olms_multiyear
-- ============================================================

-- Test 1: Affiliation Summary
\echo '=== TEST 1: Top 10 Affiliations by Members ==='
SELECT affiliation, affiliation_name, 
       local_count, 
       total_members,
       f7_employer_count,
       f7_total_workers
FROM v_affiliation_summary
WHERE total_members > 0
ORDER BY total_members DESC
LIMIT 10;

-- Test 2: Search employers by affiliation
\echo ''
\echo '=== TEST 2: IBT (Teamsters) Employers in New York ==='
SELECT employer_name, city, state, bargaining_unit_size, union_name_lm
FROM v_employer_search
WHERE affiliation = 'IBT' AND state = 'NY'
ORDER BY bargaining_unit_size DESC NULLS LAST
LIMIT 10;

-- Test 3: Search union locals by state
\echo ''
\echo '=== TEST 3: SEIU Locals in California ==='
SELECT file_number, union_name, city, members, 
       f7_employer_count, f7_total_workers
FROM v_union_local_search
WHERE affiliation = 'SEIU' AND state = 'CA'
ORDER BY members DESC NULLS LAST
LIMIT 10;

-- Test 4: Union LM detail search
\echo ''
\echo '=== TEST 4: Largest Unions by Assets (2024) ==='
SELECT file_number, union_name, affiliation, state,
       members, total_assets, total_receipts,
       assets_per_member
FROM v_union_lm_detail
WHERE fiscal_year = 2024
ORDER BY total_assets DESC NULLS LAST
LIMIT 10;

-- Test 5: State overview with density
\echo ''
\echo '=== TEST 5: States by Union Density ==='
SELECT state, 
       ROUND(union_density * 100, 1) as density_pct,
       union_members::bigint as members,
       f7_employers,
       unions_with_employers
FROM v_state_overview
ORDER BY union_density DESC
LIMIT 10;

-- Test 6: Employer search by name pattern
\echo ''
\echo '=== TEST 6: Employers matching "hospital" ==='
SELECT employer_name, city, state, 
       bargaining_unit_size, affiliation, union_name_lm
FROM v_employer_search
WHERE LOWER(employer_name) LIKE '%hospital%'
ORDER BY bargaining_unit_size DESC NULLS LAST
LIMIT 10;

-- Test 7: Union local search by name
\echo ''
\echo '=== TEST 7: Locals matching "nurses" ==='
SELECT file_number, union_name, state, members,
       f7_employer_count, affiliation_name
FROM v_union_local_search
WHERE LOWER(union_name) LIKE '%nurse%'
ORDER BY members DESC NULLS LAST
LIMIT 10;

\echo ''
\echo '=== ALL TESTS COMPLETE ==='
