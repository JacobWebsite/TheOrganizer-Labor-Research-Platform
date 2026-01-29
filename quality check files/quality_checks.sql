-- ============================================================================
-- LABOR RELATIONS PLATFORM - DATA QUALITY CHECKS
-- Run against: PostgreSQL olms_multiyear database
-- Created: January 28, 2026
-- ============================================================================

-- ============================================================================
-- SECTION 1: EMPLOYER DATA QUALITY
-- ============================================================================

-- 1.1 Overall Employer Health Dashboard
SELECT 
    '=== EMPLOYER QUALITY DASHBOARD ===' as section;

SELECT 
    COUNT(*) as total_employers,
    COUNT(DISTINCT employer_id) as unique_employer_ids,
    COUNT(*) - COUNT(DISTINCT employer_id) as duplicate_ids,
    ROUND(100.0 * COUNT(DISTINCT employer_id) / COUNT(*), 2) as uniqueness_pct,
    SUM(CASE WHEN naics IS NULL OR naics = '' THEN 1 ELSE 0 END) as missing_naics,
    ROUND(100.0 * SUM(CASE WHEN naics IS NOT NULL AND naics != '' THEN 1 ELSE 0 END) / COUNT(*), 1) as naics_coverage_pct,
    SUM(CASE WHEN latitude IS NULL THEN 1 ELSE 0 END) as missing_geocode,
    ROUND(100.0 * SUM(CASE WHEN latitude IS NOT NULL THEN 1 ELSE 0 END) / COUNT(*), 1) as geocode_coverage_pct,
    SUM(CASE WHEN state IS NULL OR state = '' THEN 1 ELSE 0 END) as missing_state,
    SUM(CASE WHEN latest_union_name IS NULL OR latest_union_name = '' THEN 1 ELSE 0 END) as no_union_link,
    COUNT(DISTINCT state) as states_represented,
    SUM(latest_unit_size) as total_workers_covered
FROM f7_employers_deduped;

-- 1.2 Potential Duplicate Employers (same name + city + state)
SELECT 
    '=== POTENTIAL DUPLICATE EMPLOYERS ===' as section;

SELECT 
    UPPER(TRIM(employer_name)) as norm_name,
    UPPER(TRIM(city)) as norm_city,
    UPPER(TRIM(state)) as norm_state,
    COUNT(*) as duplicate_count,
    SUM(latest_unit_size) as total_workers,
    ARRAY_AGG(employer_id) as employer_ids
FROM f7_employers_deduped
WHERE employer_name IS NOT NULL
GROUP BY UPPER(TRIM(employer_name)), UPPER(TRIM(city)), UPPER(TRIM(state))
HAVING COUNT(*) > 1
ORDER BY COUNT(*) DESC
LIMIT 50;

-- 1.3 Invalid or Suspicious State Codes
SELECT 
    '=== INVALID STATE CODES ===' as section;

SELECT 
    state,
    COUNT(*) as employer_count,
    SUM(latest_unit_size) as workers
FROM f7_employers_deduped
WHERE state IS NULL 
   OR state = ''
   OR LENGTH(state) != 2
   OR state !~ '^[A-Z]{2}$'
   OR state NOT IN (
       'AL','AK','AZ','AR','CA','CO','CT','DE','FL','GA',
       'HI','ID','IL','IN','IA','KS','KY','LA','ME','MD',
       'MA','MI','MN','MS','MO','MT','NE','NV','NH','NJ',
       'NM','NY','NC','ND','OH','OK','OR','PA','RI','SC',
       'SD','TN','TX','UT','VT','VA','WA','WV','WI','WY',
       'DC','PR','VI','GU','AS','MP'
   )
GROUP BY state
ORDER BY COUNT(*) DESC;

-- 1.4 Employers with Suspiciously Large Worker Counts
SELECT 
    '=== OUTLIER WORKER COUNTS (>50K) ===' as section;

SELECT 
    employer_id,
    employer_name,
    city,
    state,
    naics,
    latest_unit_size as workers,
    latest_union_name,
    f7_notices
FROM f7_employers_deduped
WHERE latest_unit_size > 50000
ORDER BY latest_unit_size DESC
LIMIT 30;

-- 1.5 NAICS Distribution and Gaps
SELECT 
    '=== NAICS CODE DISTRIBUTION ===' as section;

SELECT 
    COALESCE(naics, 'MISSING') as naics_code,
    CASE naics
        WHEN '11' THEN 'Agriculture'
        WHEN '21' THEN 'Mining'
        WHEN '22' THEN 'Utilities'
        WHEN '23' THEN 'Construction'
        WHEN '31' THEN 'Manufacturing'
        WHEN '42' THEN 'Wholesale Trade'
        WHEN '44' THEN 'Retail Trade'
        WHEN '48' THEN 'Transportation'
        WHEN '51' THEN 'Information'
        WHEN '52' THEN 'Finance/Insurance'
        WHEN '53' THEN 'Real Estate'
        WHEN '54' THEN 'Professional Services'
        WHEN '55' THEN 'Management'
        WHEN '56' THEN 'Admin Services'
        WHEN '61' THEN 'Education'
        WHEN '62' THEN 'Healthcare'
        WHEN '71' THEN 'Arts/Entertainment'
        WHEN '72' THEN 'Accommodation/Food'
        WHEN '81' THEN 'Other Services'
        WHEN '92' THEN 'Public Admin'
        ELSE 'Unknown/Missing'
    END as industry_name,
    COUNT(*) as employers,
    SUM(latest_unit_size) as workers,
    ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER(), 2) as pct_of_employers
FROM f7_employers_deduped
GROUP BY naics
ORDER BY COUNT(*) DESC;

-- 1.6 Geocoding Failures by State
SELECT 
    '=== GEOCODING GAPS BY STATE ===' as section;

SELECT 
    state,
    COUNT(*) as total_employers,
    SUM(CASE WHEN latitude IS NULL THEN 1 ELSE 0 END) as missing_geocode,
    ROUND(100.0 * SUM(CASE WHEN latitude IS NULL THEN 1 ELSE 0 END) / COUNT(*), 1) as missing_pct
FROM f7_employers_deduped
WHERE state IS NOT NULL AND state != ''
GROUP BY state
HAVING SUM(CASE WHEN latitude IS NULL THEN 1 ELSE 0 END) > 0
ORDER BY SUM(CASE WHEN latitude IS NULL THEN 1 ELSE 0 END) DESC
LIMIT 20;

-- ============================================================================
-- SECTION 2: UNION DATA QUALITY
-- ============================================================================

-- 2.1 Union Health Dashboard
SELECT 
    '=== UNION QUALITY DASHBOARD ===' as section;

SELECT 
    COUNT(*) as total_unions,
    COUNT(DISTINCT f_num) as unique_file_numbers,
    SUM(members) as raw_total_members,
    SUM(CASE WHEN members < 0 THEN 1 ELSE 0 END) as negative_member_count,
    SUM(CASE WHEN members > 1000000 THEN 1 ELSE 0 END) as over_1m_members,
    SUM(CASE WHEN aff_abbr IS NULL OR aff_abbr = '' THEN 1 ELSE 0 END) as missing_affiliation,
    SUM(CASE WHEN sector IS NULL OR sector = '' THEN 1 ELSE 0 END) as missing_sector,
    COUNT(DISTINCT aff_abbr) as unique_affiliations,
    COUNT(DISTINCT sector) as unique_sectors
FROM unions_master;

-- 2.2 Hierarchy Level Distribution
SELECT 
    '=== UNION HIERARCHY DISTRIBUTION ===' as section;

SELECT 
    COALESCE(hierarchy_level, 'UNCLASSIFIED') as level,
    COUNT(*) as unions,
    SUM(members) as raw_members,
    SUM(CASE WHEN count_members THEN members ELSE 0 END) as counted_members,
    ROUND(AVG(members), 0) as avg_members,
    MAX(members) as max_members
FROM union_hierarchy
GROUP BY hierarchy_level
ORDER BY SUM(members) DESC;

-- 2.3 Sector Classification Check
SELECT 
    '=== SECTOR CLASSIFICATION ===' as section;

SELECT 
    COALESCE(sector, 'MISSING') as sector,
    COUNT(*) as unions,
    SUM(members) as members,
    ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER(), 2) as pct_of_unions
FROM unions_master
GROUP BY sector
ORDER BY SUM(members) DESC;

-- 2.4 Unions with Suspicious Member Counts
SELECT 
    '=== MEMBER COUNT OUTLIERS ===' as section;

-- Negative members (should be 0)
SELECT 
    'NEGATIVE MEMBERS' as issue,
    f_num,
    union_name,
    aff_abbr,
    members,
    sector
FROM unions_master
WHERE members < 0
LIMIT 20;

-- Extremely large locals (>100K members in a single local)
SELECT 
    'VERY LARGE LOCALS (>100K)' as issue,
    f_num,
    union_name,
    aff_abbr,
    members,
    sector
FROM unions_master
WHERE members > 100000
  AND union_name NOT ILIKE '%national%'
  AND union_name NOT ILIKE '%international%'
  AND union_name NOT ILIKE '%federation%'
ORDER BY members DESC
LIMIT 20;

-- 2.5 Orphan Unions (no parent affiliation linkable)
SELECT 
    '=== ORPHAN UNIONS (NO CLEAR AFFILIATION) ===' as section;

SELECT 
    f_num,
    union_name,
    aff_abbr,
    members,
    sector,
    yr_covered
FROM unions_master
WHERE (aff_abbr IS NULL OR aff_abbr = '' OR aff_abbr = 'IND')
  AND members > 1000
ORDER BY members DESC
LIMIT 30;

-- 2.6 Stale Union Data (no recent filing)
SELECT 
    '=== STALE UNIONS (NO FILING SINCE 2020) ===' as section;

SELECT 
    aff_abbr,
    COUNT(*) as stale_unions,
    SUM(members) as members_at_risk,
    MAX(yr_covered) as last_filing_year
FROM unions_master
WHERE yr_covered < 2020
GROUP BY aff_abbr
HAVING COUNT(*) > 5
ORDER BY SUM(members) DESC
LIMIT 20;

-- 2.7 Duplicate File Numbers
SELECT 
    '=== DUPLICATE FILE NUMBERS ===' as section;

SELECT 
    f_num,
    COUNT(*) as records,
    ARRAY_AGG(DISTINCT union_name) as union_names,
    ARRAY_AGG(DISTINCT yr_covered) as years
FROM unions_master
GROUP BY f_num
HAVING COUNT(*) > 1
ORDER BY COUNT(*) DESC
LIMIT 20;

-- ============================================================================
-- SECTION 3: CROSS-DATASET VALIDATION
-- ============================================================================

-- 3.1 F-7 to OLMS Match Rate
SELECT 
    '=== F-7 TO OLMS MATCH RATE ===' as section;

SELECT 
    COUNT(*) as total_f7_employers,
    SUM(CASE WHEN latest_union_name IS NOT NULL AND latest_union_name != '' THEN 1 ELSE 0 END) as matched_to_union,
    ROUND(100.0 * SUM(CASE WHEN latest_union_name IS NOT NULL AND latest_union_name != '' THEN 1 ELSE 0 END) / COUNT(*), 2) as match_rate_pct,
    SUM(latest_unit_size) as total_workers,
    SUM(CASE WHEN latest_union_name IS NOT NULL THEN latest_unit_size ELSE 0 END) as matched_workers,
    ROUND(100.0 * SUM(CASE WHEN latest_union_name IS NOT NULL THEN latest_unit_size ELSE 0 END) / NULLIF(SUM(latest_unit_size), 0), 2) as worker_match_rate_pct
FROM f7_employers_deduped;

-- 3.2 OSHA to F-7 Match Summary
SELECT 
    '=== OSHA TO F-7 MATCH SUMMARY ===' as section;

SELECT 
    COUNT(DISTINCT f7_employer_id) as f7_employers_with_osha,
    (SELECT COUNT(*) FROM f7_employers_deduped) as total_f7_employers,
    ROUND(100.0 * COUNT(DISTINCT f7_employer_id) / (SELECT COUNT(*) FROM f7_employers_deduped), 2) as osha_coverage_pct,
    COUNT(*) as total_osha_matches,
    ROUND(AVG(match_confidence), 3) as avg_match_confidence
FROM osha_f7_matches;

-- 3.3 OSHA Match Quality by Method
SELECT 
    '=== OSHA MATCH QUALITY BY METHOD ===' as section;

SELECT 
    match_method,
    COUNT(*) as matches,
    COUNT(DISTINCT f7_employer_id) as unique_f7_employers,
    ROUND(AVG(match_confidence), 3) as avg_confidence,
    MIN(match_confidence) as min_confidence,
    MAX(match_confidence) as max_confidence
FROM osha_f7_matches
GROUP BY match_method
ORDER BY COUNT(*) DESC;

-- 3.4 NLRB Elections Coverage
SELECT 
    '=== NLRB ELECTION COVERAGE ===' as section;

SELECT 
    COUNT(*) as total_elections,
    COUNT(DISTINCT employer_name) as unique_employers,
    SUM(CASE WHEN union_won THEN 1 ELSE 0 END) as union_wins,
    ROUND(100.0 * SUM(CASE WHEN union_won THEN 1 ELSE 0 END) / NULLIF(COUNT(*), 0), 2) as win_rate_pct,
    SUM(eligible_voters) as total_eligible_voters,
    MIN(election_date) as earliest_election,
    MAX(election_date) as latest_election
FROM nlrb_elections;

-- 3.5 Voluntary Recognition Coverage
SELECT 
    '=== VOLUNTARY RECOGNITION COVERAGE ===' as section;

SELECT 
    COUNT(*) as total_vr_cases,
    COUNT(DISTINCT employer_name) as unique_employers,
    SUM(num_employees) as total_workers,
    SUM(CASE WHEN matched_employer_id IS NOT NULL THEN 1 ELSE 0 END) as matched_to_f7,
    ROUND(100.0 * SUM(CASE WHEN matched_employer_id IS NOT NULL THEN 1 ELSE 0 END) / NULLIF(COUNT(*), 0), 2) as f7_match_rate
FROM nlrb_voluntary_recognition;

-- ============================================================================
-- SECTION 4: BLS BENCHMARK ALIGNMENT
-- ============================================================================

-- 4.1 Private Sector Alignment
SELECT 
    '=== PRIVATE SECTOR BLS ALIGNMENT ===' as section;

WITH private_sector AS (
    SELECT 
        SUM(latest_unit_size) as platform_workers
    FROM f7_employers_deduped
    WHERE sector = 'PRIVATE' OR sector IS NULL  -- Assume NULL = private
)
SELECT 
    platform_workers,
    7200000 as bls_private_sector_benchmark,
    ROUND(100.0 * platform_workers / 7200000, 1) as coverage_pct,
    CASE 
        WHEN platform_workers BETWEEN 6480000 AND 7920000 THEN 'WITHIN 10% - OK'
        WHEN platform_workers BETWEEN 5760000 AND 8640000 THEN 'WITHIN 20% - REVIEW'
        ELSE 'OUTSIDE RANGE - INVESTIGATE'
    END as status
FROM private_sector;

-- 4.2 Federal Sector Alignment (from FLRA data if exists)
SELECT 
    '=== FEDERAL SECTOR BLS ALIGNMENT ===' as section;

-- Check if we have federal data
SELECT 
    sector,
    COUNT(*) as units,
    SUM(members) as members
FROM unions_master
WHERE sector = 'FEDERAL'
GROUP BY sector;

-- 4.3 Member Count Reconciliation Summary
SELECT 
    '=== MEMBER COUNT RECONCILIATION ===' as section;

SELECT 
    'Raw OLMS Total' as category,
    SUM(members) as members
FROM unions_master
UNION ALL
SELECT 
    'Deduplicated (count_members=TRUE)' as category,
    SUM(members) as members
FROM union_hierarchy
WHERE count_members = TRUE
UNION ALL
SELECT 
    'BLS Benchmark (2024)' as category,
    14300000 as members;

-- ============================================================================
-- SECTION 5: DATA FRESHNESS
-- ============================================================================

-- 5.1 Data Freshness by Source
SELECT 
    '=== DATA FRESHNESS ===' as section;

SELECT 'OLMS LM Filings' as source, MAX(yr_covered) as most_recent_year, COUNT(*) as records
FROM unions_master
UNION ALL
SELECT 'F-7 Employers', EXTRACT(YEAR FROM MAX(created_at))::int, COUNT(*)
FROM f7_employers_deduped
UNION ALL
SELECT 'NLRB Elections', EXTRACT(YEAR FROM MAX(election_date))::int, COUNT(*)
FROM nlrb_elections
UNION ALL
SELECT 'OSHA Establishments', EXTRACT(YEAR FROM MAX(last_inspection_date))::int, COUNT(*)
FROM osha_establishments
UNION ALL
SELECT 'Voluntary Recognition', EXTRACT(YEAR FROM MAX(date_received))::int, COUNT(*)
FROM nlrb_voluntary_recognition;

-- 5.2 Filing Year Distribution
SELECT 
    '=== UNION FILING YEAR DISTRIBUTION ===' as section;

SELECT 
    yr_covered,
    COUNT(*) as unions_filed,
    SUM(members) as members_reported
FROM unions_master
WHERE yr_covered >= 2018
GROUP BY yr_covered
ORDER BY yr_covered DESC;

-- ============================================================================
-- SECTION 6: AFFILIATION-LEVEL ANALYSIS
-- ============================================================================

-- 6.1 Top Affiliations by Members
SELECT 
    '=== TOP AFFILIATIONS BY MEMBERS ===' as section;

SELECT 
    aff_abbr,
    COUNT(*) as locals,
    SUM(members) as total_members,
    ROUND(AVG(members), 0) as avg_members_per_local,
    SUM(f7_employer_count) as employers_covered
FROM unions_master
WHERE aff_abbr IS NOT NULL AND aff_abbr != ''
GROUP BY aff_abbr
ORDER BY SUM(members) DESC
LIMIT 25;

-- 6.2 Affiliations with Data Quality Issues
SELECT 
    '=== AFFILIATIONS WITH QUALITY ISSUES ===' as section;

SELECT 
    aff_abbr,
    COUNT(*) as total_locals,
    SUM(CASE WHEN members = 0 THEN 1 ELSE 0 END) as zero_member_locals,
    SUM(CASE WHEN members < 0 THEN 1 ELSE 0 END) as negative_member_locals,
    SUM(CASE WHEN f7_employer_count = 0 THEN 1 ELSE 0 END) as no_employers,
    ROUND(100.0 * SUM(CASE WHEN f7_employer_count = 0 THEN 1 ELSE 0 END) / COUNT(*), 1) as pct_no_employers
FROM unions_master
WHERE aff_abbr IS NOT NULL AND aff_abbr != ''
GROUP BY aff_abbr
HAVING SUM(CASE WHEN members = 0 THEN 1 ELSE 0 END) > 5
    OR SUM(CASE WHEN members < 0 THEN 1 ELSE 0 END) > 0
    OR (SUM(CASE WHEN f7_employer_count = 0 THEN 1 ELSE 0 END)::float / COUNT(*)) > 0.5
ORDER BY COUNT(*) DESC
LIMIT 20;

-- ============================================================================
-- SECTION 7: GEOGRAPHIC COVERAGE
-- ============================================================================

-- 7.1 State Coverage Summary
SELECT 
    '=== STATE COVERAGE SUMMARY ===' as section;

SELECT 
    e.state,
    COUNT(DISTINCT e.employer_id) as employers,
    SUM(e.latest_unit_size) as workers,
    COUNT(DISTINCT u.f_num) as unions_present,
    SUM(CASE WHEN e.latitude IS NOT NULL THEN 1 ELSE 0 END) as geocoded,
    ROUND(100.0 * SUM(CASE WHEN e.latitude IS NOT NULL THEN 1 ELSE 0 END) / COUNT(*), 1) as geocode_pct
FROM f7_employers_deduped e
LEFT JOIN unions_master u ON e.latest_f_num = u.f_num
WHERE e.state IS NOT NULL AND LENGTH(e.state) = 2
GROUP BY e.state
ORDER BY SUM(e.latest_unit_size) DESC;

-- 7.2 States with Coverage Gaps
SELECT 
    '=== STATES WITH LOW COVERAGE ===' as section;

WITH state_stats AS (
    SELECT 
        state,
        COUNT(*) as employers,
        SUM(latest_unit_size) as workers,
        ROUND(100.0 * SUM(CASE WHEN latitude IS NOT NULL THEN 1 ELSE 0 END) / COUNT(*), 1) as geocode_pct,
        ROUND(100.0 * SUM(CASE WHEN naics IS NOT NULL THEN 1 ELSE 0 END) / COUNT(*), 1) as naics_pct
    FROM f7_employers_deduped
    WHERE state IS NOT NULL
    GROUP BY state
)
SELECT *
FROM state_stats
WHERE geocode_pct < 70 OR naics_pct < 70
ORDER BY workers DESC;

-- ============================================================================
-- SECTION 8: SUMMARY QUALITY SCORECARD
-- ============================================================================

SELECT 
    '=== QUALITY SCORECARD SUMMARY ===' as section;

WITH metrics AS (
    SELECT 
        -- Employer metrics
        (SELECT ROUND(100.0 * SUM(CASE WHEN naics IS NOT NULL THEN 1 ELSE 0 END) / COUNT(*), 1) 
         FROM f7_employers_deduped) as employer_naics_pct,
        (SELECT ROUND(100.0 * SUM(CASE WHEN latitude IS NOT NULL THEN 1 ELSE 0 END) / COUNT(*), 1) 
         FROM f7_employers_deduped) as employer_geocode_pct,
        (SELECT ROUND(100.0 * SUM(CASE WHEN latest_union_name IS NOT NULL THEN 1 ELSE 0 END) / COUNT(*), 1) 
         FROM f7_employers_deduped) as employer_union_match_pct,
        -- Union metrics
        (SELECT ROUND(100.0 * SUM(CASE WHEN aff_abbr IS NOT NULL AND aff_abbr != '' THEN 1 ELSE 0 END) / COUNT(*), 1) 
         FROM unions_master) as union_affiliation_pct,
        (SELECT ROUND(100.0 * SUM(CASE WHEN sector IS NOT NULL THEN 1 ELSE 0 END) / COUNT(*), 1) 
         FROM unions_master) as union_sector_pct,
        -- Cross-dataset
        (SELECT ROUND(100.0 * COUNT(DISTINCT f7_employer_id) / (SELECT COUNT(*) FROM f7_employers_deduped), 1) 
         FROM osha_f7_matches) as osha_match_pct
)
SELECT 
    'Employer NAICS Coverage' as metric, employer_naics_pct as value, 
    CASE WHEN employer_naics_pct >= 80 THEN '✅ GOOD' 
         WHEN employer_naics_pct >= 60 THEN '⚠️ FAIR' 
         ELSE '❌ POOR' END as status,
    80 as target
FROM metrics
UNION ALL
SELECT 'Employer Geocoding', employer_geocode_pct, 
    CASE WHEN employer_geocode_pct >= 75 THEN '✅ GOOD' 
         WHEN employer_geocode_pct >= 60 THEN '⚠️ FAIR' 
         ELSE '❌ POOR' END,
    75
FROM metrics
UNION ALL
SELECT 'Employer-Union Match', employer_union_match_pct, 
    CASE WHEN employer_union_match_pct >= 90 THEN '✅ GOOD' 
         WHEN employer_union_match_pct >= 75 THEN '⚠️ FAIR' 
         ELSE '❌ POOR' END,
    90
FROM metrics
UNION ALL
SELECT 'Union Affiliation Coverage', union_affiliation_pct, 
    CASE WHEN union_affiliation_pct >= 90 THEN '✅ GOOD' 
         WHEN union_affiliation_pct >= 75 THEN '⚠️ FAIR' 
         ELSE '❌ POOR' END,
    90
FROM metrics
UNION ALL
SELECT 'Union Sector Classification', union_sector_pct, 
    CASE WHEN union_sector_pct >= 95 THEN '✅ GOOD' 
         WHEN union_sector_pct >= 85 THEN '⚠️ FAIR' 
         ELSE '❌ POOR' END,
    95
FROM metrics
UNION ALL
SELECT 'OSHA-F7 Linkage', osha_match_pct, 
    CASE WHEN osha_match_pct >= 40 THEN '✅ GOOD' 
         WHEN osha_match_pct >= 25 THEN '⚠️ FAIR' 
         ELSE '❌ POOR' END,
    40
FROM metrics;

-- ============================================================================
-- END OF QUALITY CHECKS
-- ============================================================================

SELECT '=== QUALITY CHECKS COMPLETE ===' as section;
