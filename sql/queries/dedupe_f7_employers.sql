-- CHECKPOINT 4: F-7 Historical Data Deduplication
-- Logic: Keep only most recent notice per employer+city+state+union, filter to last 5 years
-- Run with: psql -U postgres -d olms_multiyear -f dedupe_f7_employers.sql

\echo '=== Step 1: Check current F-7 data stats ==='
SELECT 
    COUNT(*) as total_records,
    COUNT(DISTINCT employer_name || COALESCE(city,'') || COALESCE(state,'') || COALESCE(latest_union_fnum::text,'')) as unique_combinations,
    MIN(latest_notice_date) as earliest_date,
    MAX(latest_notice_date) as latest_date
FROM f7_employers;

\echo ''
\echo '=== Step 2: Preview deduplication - how many records will remain? ==='
SELECT 
    COUNT(*) as records_after_dedupe,
    (SELECT COUNT(*) FROM f7_employers) as records_before,
    (SELECT COUNT(*) FROM f7_employers) - COUNT(*) as records_removed
FROM (
    SELECT DISTINCT ON (
        LOWER(TRIM(employer_name)), 
        LOWER(TRIM(COALESCE(city, ''))), 
        COALESCE(state, ''),
        COALESCE(latest_union_fnum::text, LOWER(TRIM(latest_union_name)))
    )
    employer_id
    FROM f7_employers
    WHERE latest_notice_date >= '2020-01-01'
    ORDER BY 
        LOWER(TRIM(employer_name)), 
        LOWER(TRIM(COALESCE(city, ''))), 
        COALESCE(state, ''),
        COALESCE(latest_union_fnum::text, LOWER(TRIM(latest_union_name))),
        latest_notice_date DESC
) deduped;

\echo ''
\echo '=== Step 3: Create deduplicated table ==='
DROP TABLE IF EXISTS f7_employers_deduped;

CREATE TABLE f7_employers_deduped AS
SELECT *
FROM f7_employers
WHERE employer_id IN (
    SELECT DISTINCT ON (
        LOWER(TRIM(employer_name)), 
        LOWER(TRIM(COALESCE(city, ''))), 
        COALESCE(state, ''),
        COALESCE(latest_union_fnum::text, LOWER(TRIM(latest_union_name)))
    )
    employer_id
    FROM f7_employers
    WHERE latest_notice_date >= '2020-01-01'
    ORDER BY 
        LOWER(TRIM(employer_name)), 
        LOWER(TRIM(COALESCE(city, ''))), 
        COALESCE(state, ''),
        COALESCE(latest_union_fnum::text, LOWER(TRIM(latest_union_name))),
        latest_notice_date DESC
);

\echo ''
\echo '=== Step 4: Add indexes to deduplicated table ==='
CREATE INDEX idx_f7_deduped_name ON f7_employers_deduped (LOWER(employer_name));
CREATE INDEX idx_f7_deduped_state ON f7_employers_deduped (state);
CREATE INDEX idx_f7_deduped_union_fnum ON f7_employers_deduped (latest_union_fnum);
CREATE INDEX idx_f7_deduped_notice_date ON f7_employers_deduped (latest_notice_date);

\echo ''
\echo '=== Step 5: Verify deduplicated table ==='
SELECT 
    COUNT(*) as total_records,
    MIN(latest_notice_date) as earliest_date,
    MAX(latest_notice_date) as latest_date,
    COUNT(DISTINCT state) as states_covered
FROM f7_employers_deduped;

\echo ''
\echo '=== Step 6: Sample comparison - Starbucks before/after ==='
\echo 'BEFORE (original table):'
SELECT employer_name, city, state, latest_unit_size, latest_notice_date, latest_union_name
FROM f7_employers
WHERE employer_name ILIKE '%starbucks%'
ORDER BY latest_notice_date DESC
LIMIT 10;

\echo ''
\echo 'AFTER (deduplicated table):'
SELECT employer_name, city, state, latest_unit_size, latest_notice_date, latest_union_name
FROM f7_employers_deduped
WHERE employer_name ILIKE '%starbucks%'
ORDER BY latest_notice_date DESC
LIMIT 10;

\echo ''
\echo '=== Step 7: Records removed by year ==='
SELECT 
    EXTRACT(YEAR FROM latest_notice_date)::int as year,
    COUNT(*) as records_removed
FROM f7_employers
WHERE employer_id NOT IN (SELECT employer_id FROM f7_employers_deduped)
GROUP BY 1
ORDER BY 1;
