-- Quick diagnostic to check database state
-- Run: psql -U postgres -d olms_multiyear -f check_db.sql

\echo '=== Checking tables ==='
SELECT 'f7_employers_deduped' as table_name, COUNT(*) as rows FROM f7_employers_deduped
UNION ALL
SELECT 'lm_data', COUNT(*) FROM lm_data
UNION ALL
SELECT 'crosswalk_affiliation_sector_map', COUNT(*) FROM crosswalk_affiliation_sector_map;

\echo ''
\echo '=== Checking views ==='
SELECT viewname FROM pg_views WHERE schemaname = 'public' AND viewname LIKE 'v_%';

\echo ''
\echo '=== Quick test of v_employer_search ==='
SELECT COUNT(*) as total FROM v_employer_search;

\echo ''
\echo '=== Quick test of v_union_local_search ==='
SELECT COUNT(*) as total FROM v_union_local_search;

\echo ''
\echo '=== Quick test of v_affiliation_summary ==='
SELECT COUNT(*) as total FROM v_affiliation_summary;
