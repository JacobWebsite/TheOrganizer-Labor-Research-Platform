-- ============================================================================
-- BLS INTEGRATION QUERIES
-- Example queries linking OLMS/NLRB data with BLS projections via crosswalks
-- Created: January 24, 2026
-- ============================================================================

-- ============================================================================
-- SECTION 1: BASIC CROSSWALK QUERIES
-- ============================================================================

-- 1.1 Find NAICS codes for a specific industry description
SELECT DISTINCT 
    industry_description,
    naics_code,
    naics_sector
FROM census_industry_naics_xwalk
WHERE industry_description ILIKE '%hospital%'
ORDER BY naics_sector;

-- 1.2 Find SOC codes for a specific occupation
SELECT DISTINCT
    occupation_title,
    soc_code,
    soc_major_group
FROM census_occupation_soc_xwalk
WHERE occupation_title ILIKE '%nurse%'
ORDER BY soc_code;

-- 1.3 Get all industries in a NAICS sector
SELECT DISTINCT 
    industry_description,
    naics_code,
    census_industry_code
FROM census_industry_naics_xwalk
WHERE naics_sector = 'Health Care and Social Assistance'
ORDER BY naics_code;

-- ============================================================================
-- SECTION 2: LINKING F-7 EMPLOYERS TO BLS PROJECTIONS
-- ============================================================================

-- 2.1 Find employment projections for industries with F-7 bargaining notices
-- (Requires F-7 employers to have NAICS codes - use for enriched data)
SELECT 
    bip.industry_title,
    bip.naics_code,
    bip.employment_2024,
    bip.employment_2034,
    bip.employment_change_percent,
    COUNT(DISTINCT fe.employer_id) as f7_employer_count
FROM bls_industry_projections bip
LEFT JOIN census_industry_naics_xwalk cix 
    ON bip.naics_code LIKE cix.naics_2digit || '%'
LEFT JOIN f7_employers fe 
    ON fe.naics_code LIKE cix.naics_2digit || '%'
WHERE bip.employment_change_percent > 10
GROUP BY bip.industry_title, bip.naics_code, bip.employment_2024, 
         bip.employment_2034, bip.employment_change_percent
ORDER BY bip.employment_change_percent DESC
LIMIT 20;

-- 2.2 Industries with high union density AND high growth projections
SELECT 
    bip.industry_title,
    bip.naics_code,
    bip.employment_change_percent as growth_pct,
    bus.value as union_rate_2024
FROM bls_industry_projections bip
JOIN bls_union_series bus ON bus.series_id LIKE 'LUU%'
JOIN bls_union_data bud ON bus.series_id = bud.series_id AND bud.year = 2024
WHERE bip.employment_change_percent > 5
  AND bud.value > 10
ORDER BY bip.employment_change_percent DESC;

-- ============================================================================
-- SECTION 3: OCCUPATION-BASED ANALYSIS
-- ============================================================================

-- 3.1 High-wage occupations with union representation
SELECT 
    bop.occupation_title,
    bop.soc_code,
    bop.median_wage_2024,
    bop.employment_2024,
    bop.employment_change_pct
FROM bls_occupation_projections bop
WHERE bop.median_wage_2024 > 80000
  AND bop.employment_change_pct > 5
ORDER BY bop.median_wage_2024 DESC
LIMIT 25;

-- 3.2 Find occupation projections for specific SOC major groups
SELECT 
    bop.occupation_title,
    bop.soc_code,
    bop.employment_2024,
    bop.employment_2034,
    bop.employment_change_pct,
    bop.median_wage_2024
FROM bls_occupation_projections bop
WHERE bop.soc_code LIKE '29-%'  -- Healthcare practitioners
ORDER BY bop.employment_change_pct DESC;

-- 3.3 Link census occupation codes to BLS projections
SELECT 
    cox.occupation_title as census_occupation,
    cox.soc_code,
    bop.occupation_title as bls_occupation,
    bop.employment_2024,
    bop.median_wage_2024
FROM census_occupation_soc_xwalk cox
JOIN bls_occupation_projections bop 
    ON cox.soc_code = bop.soc_code
WHERE cox.occupation_title ILIKE '%electrician%'
ORDER BY bop.employment_2024 DESC;

-- ============================================================================
-- SECTION 4: INDUSTRY-OCCUPATION MATRIX ANALYSIS
-- ============================================================================

-- 4.1 Top occupations in a specific industry
SELECT 
    biom.occupation_title,
    biom.soc_code,
    biom.employment_2024,
    biom.percent_of_industry,
    biom.percent_of_occupation
FROM bls_industry_occupation_matrix biom
WHERE biom.industry_title ILIKE '%construction%'
  AND biom.employment_2024 > 10000
ORDER BY biom.employment_2024 DESC
LIMIT 20;

-- 4.2 Industries where a specific occupation is concentrated
SELECT 
    biom.industry_title,
    biom.naics_code,
    biom.employment_2024,
    biom.percent_of_occupation
FROM bls_industry_occupation_matrix biom
WHERE biom.occupation_title ILIKE '%registered nurse%'
ORDER BY biom.percent_of_occupation DESC
LIMIT 15;

-- 4.3 Cross-industry occupation analysis
SELECT 
    biom.occupation_title,
    COUNT(DISTINCT biom.naics_code) as industry_count,
    SUM(biom.employment_2024) as total_employment,
    AVG(biom.percent_of_industry) as avg_industry_share
FROM bls_industry_occupation_matrix biom
GROUP BY biom.occupation_title
HAVING SUM(biom.employment_2024) > 100000
ORDER BY industry_count DESC
LIMIT 25;

-- ============================================================================
-- SECTION 5: UNION DENSITY TRENDS
-- ============================================================================

-- 5.1 Union membership trends by state (last 10 years)
SELECT 
    bus.state_name,
    bud.year,
    bud.value as union_rate
FROM bls_union_series bus
JOIN bls_union_data bud ON bus.series_id = bud.series_id
WHERE bus.state_name IS NOT NULL
  AND bus.data_type = 'Members'
  AND bud.year >= 2015
ORDER BY bus.state_name, bud.year;

-- 5.2 Industry union density comparison
SELECT 
    bus.industry_name,
    bud.year,
    bud.value as union_rate
FROM bls_union_series bus
JOIN bls_union_data bud ON bus.series_id = bud.series_id
WHERE bus.industry_name IS NOT NULL
  AND bus.data_type = 'Members'
  AND bud.year = 2024
ORDER BY bud.value DESC;

-- 5.3 Historical union density trend (national)
SELECT 
    bud.year,
    bud.value as national_union_rate
FROM bls_union_series bus
JOIN bls_union_data bud ON bus.series_id = bud.series_id
WHERE bus.series_id LIKE 'LUU%'
  AND bus.state_name IS NULL
  AND bus.industry_name IS NULL
  AND bus.occupation_name IS NULL
ORDER BY bud.year;

-- ============================================================================
-- SECTION 6: COMBINED OLMS + BLS ANALYSIS
-- ============================================================================

-- 6.1 Union locals by NAICS sector (via industry crosswalk)
-- Note: This requires union records to have industry codes
SELECT 
    cix.naics_sector,
    COUNT(DISTINCT u.union_file_number) as union_count,
    SUM(COALESCE(lm.member_total, 0)) as total_members
FROM census_industry_naics_xwalk cix
LEFT JOIN lm_data lm ON lm.naics_code LIKE cix.naics_2digit || '%'
LEFT JOIN unions u ON lm.union_file_number = u.file_number
GROUP BY cix.naics_sector
ORDER BY total_members DESC;

-- 6.2 F-7 employers in high-growth industries
SELECT 
    bip.industry_title,
    bip.employment_change_percent as projected_growth,
    COUNT(DISTINCT fe.employer_id) as bargaining_employers
FROM bls_industry_projections bip
CROSS JOIN f7_employers fe
WHERE bip.employment_change_percent > 15
GROUP BY bip.industry_title, bip.employment_change_percent
HAVING COUNT(DISTINCT fe.employer_id) > 0
ORDER BY bip.employment_change_percent DESC;

-- ============================================================================
-- SECTION 7: SUMMARY VIEWS (Already created in post-load)
-- ============================================================================

-- NAICS sector summary
SELECT * FROM v_naics_sector_summary ORDER BY total_mappings DESC;

-- SOC major group summary
SELECT * FROM v_soc_major_group_summary ORDER BY total_mappings DESC;

-- Full database integration summary
SELECT * FROM v_database_integration_summary;

-- ============================================================================
-- SECTION 8: DATA QUALITY CHECKS
-- ============================================================================

-- 8.1 Check crosswalk coverage
SELECT 
    'Industry Crosswalk' as table_name,
    COUNT(*) as total_records,
    COUNT(DISTINCT census_industry_code) as unique_census_codes,
    COUNT(DISTINCT naics_code) as unique_target_codes
FROM census_industry_naics_xwalk
UNION ALL
SELECT 
    'Occupation Crosswalk',
    COUNT(*),
    COUNT(DISTINCT census_occupation_code),
    COUNT(DISTINCT soc_code)
FROM census_occupation_soc_xwalk;

-- 8.2 Verify BLS data completeness
SELECT 
    'Union Series' as table_name, COUNT(*) as records FROM bls_union_series
UNION ALL SELECT 'Union Data', COUNT(*) FROM bls_union_data
UNION ALL SELECT 'Industry Projections', COUNT(*) FROM bls_industry_projections
UNION ALL SELECT 'Occupation Projections', COUNT(*) FROM bls_occupation_projections
UNION ALL SELECT 'Industry-Occupation Matrix', COUNT(*) FROM bls_industry_occupation_matrix
UNION ALL SELECT 'Industry Crosswalk', COUNT(*) FROM census_industry_naics_xwalk
UNION ALL SELECT 'Occupation Crosswalk', COUNT(*) FROM census_occupation_soc_xwalk;

-- ============================================================================
-- END OF QUERIES
-- ============================================================================
