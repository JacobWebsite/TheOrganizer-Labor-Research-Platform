-- ============================================================================
-- Patch A Fixed: Correct column names for BLS tables
-- ============================================================================

-- Fix the density view
DROP VIEW IF EXISTS v_bls_industry_density_summary CASCADE;

CREATE OR REPLACE VIEW v_bls_industry_density_summary AS
SELECT DISTINCT
    bil.indy_code,
    bil.indy_name as industry_name,
    ns.naics_2digit,
    ns.sector_name as naics_sector_name,
    bud.year,
    bud.value as union_density_pct
FROM bls_industry_lookup bil
LEFT JOIN naics_sectors ns ON 
    CASE 
        WHEN bil.indy_code IN ('5000', '5100', '5200', '5300') THEN '33'
        WHEN bil.indy_code = '4000' THEN '23'
        WHEN bil.indy_code = '6000' THEN '48'
        WHEN bil.indy_code = '7000' THEN '51'
        WHEN bil.indy_code = '8000' THEN '52'
        WHEN bil.indy_code = '9000' THEN '54'
        WHEN bil.indy_code = '9200' THEN '56'
        WHEN bil.indy_code = '9300' THEN '61'
        WHEN bil.indy_code = '9400' THEN '62'
        WHEN bil.indy_code = '9500' THEN '72'
        WHEN bil.indy_code = '9600' THEN '81'
        WHEN bil.indy_code = '9800' THEN '92'
        ELSE NULL
    END = ns.naics_2digit
LEFT JOIN bls_union_series bus ON bus.indy_code = bil.indy_code AND bus.fips_code = '00'
LEFT JOIN bls_union_data bud ON bus.series_id = bud.series_id
WHERE bud.year >= 2015
ORDER BY bud.year DESC, bil.indy_code;

-- Recreate the v_naics_union_density view with correct BLS mapping table
DROP VIEW IF EXISTS v_naics_union_density CASCADE;

CREATE OR REPLACE VIEW v_naics_union_density AS
SELECT 
    bnm.naics_2digit,
    ns.sector_name,
    bnm.bls_indy_code,
    bnm.bls_indy_name,
    bud.year,
    bud.value as union_density_pct
FROM bls_naics_mapping bnm
JOIN naics_sectors ns ON bnm.naics_2digit = ns.naics_2digit
JOIN bls_union_series bus ON bus.indy_code = bnm.bls_indy_code AND bus.fips_code = '00'
JOIN bls_union_data bud ON bus.series_id = bud.series_id
WHERE bud.year = (SELECT MAX(year) FROM bls_union_data)
ORDER BY bud.value DESC;

-- Fix projections view with correct column names
DROP VIEW IF EXISTS v_naics_projections CASCADE;

CREATE OR REPLACE VIEW v_naics_projections AS
SELECT 
    LEFT(bip.naics_code, 2) as naics_2digit,
    ns.sector_name,
    bip.naics_code,
    bip.industry_title,
    bip.employment_2024,
    bip.employment_2034,
    bip.employment_change,
    bip.employment_change_pct as percent_change
FROM bls_industry_projections bip
LEFT JOIN naics_sectors ns ON LEFT(bip.naics_code, 2) = ns.naics_2digit
WHERE bip.naics_code IS NOT NULL
ORDER BY bip.employment_change DESC;

-- Verify
SELECT 'v_naics_union_density' as view_name, COUNT(*) as rows FROM v_naics_union_density
UNION ALL
SELECT 'v_naics_projections', COUNT(*) FROM v_naics_projections;
