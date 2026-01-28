-- ============================================================================
-- Patch A: Fix BLS Industry Density View
-- ============================================================================

-- Drop the broken view if it exists
DROP VIEW IF EXISTS v_bls_industry_density_summary;

-- Create corrected view using fips_code instead of area_code
CREATE OR REPLACE VIEW v_bls_industry_density_summary AS
SELECT DISTINCT
    bil.indy_code,
    bil.indy_text as industry_name,
    ns.naics_2digit,
    ns.sector_name as naics_sector_name,
    bud.year,
    bud.value as union_density_pct
FROM bls_industry_lookup bil
LEFT JOIN naics_sectors ns ON 
    CASE 
        WHEN bil.indy_code IN ('5000', '5100', '5200', '5300') THEN '33'  -- Manufacturing
        WHEN bil.indy_code = '4000' THEN '23'  -- Construction
        WHEN bil.indy_code = '6000' THEN '48'  -- Transportation
        WHEN bil.indy_code = '7000' THEN '51'  -- Information
        WHEN bil.indy_code = '8000' THEN '52'  -- Finance
        WHEN bil.indy_code = '9000' THEN '54'  -- Professional services
        WHEN bil.indy_code = '9200' THEN '56'  -- Admin/support
        WHEN bil.indy_code = '9300' THEN '61'  -- Education
        WHEN bil.indy_code = '9400' THEN '62'  -- Healthcare
        WHEN bil.indy_code = '9500' THEN '72'  -- Accommodation/food
        WHEN bil.indy_code = '9600' THEN '81'  -- Other services
        WHEN bil.indy_code = '9800' THEN '92'  -- Public admin
        ELSE NULL
    END = ns.naics_2digit
LEFT JOIN bls_union_series bus ON bus.indy_code = bil.indy_code AND bus.fips_code = '00'
LEFT JOIN bls_union_data bud ON bus.series_id = bud.series_id
WHERE bud.year >= 2015
ORDER BY bud.year DESC, bil.indy_code;

-- ============================================================================
-- Create BLS-NAICS mapping table for cleaner joins
-- ============================================================================

DROP TABLE IF EXISTS bls_naics_mapping CASCADE;
CREATE TABLE bls_naics_mapping (
    bls_indy_code VARCHAR(10) PRIMARY KEY,
    bls_indy_name VARCHAR(200),
    naics_2digit VARCHAR(2),
    naics_codes TEXT[],
    notes TEXT
);

INSERT INTO bls_naics_mapping VALUES
('1000', 'Agriculture and related', '11', ARRAY['11'], 'Agriculture, forestry, fishing'),
('2000', 'Mining', '21', ARRAY['21'], 'Mining, quarrying, oil/gas'),
('3000', 'Construction', '23', ARRAY['23'], 'Construction'),
('4000', 'Manufacturing', '31', ARRAY['31','32','33'], 'All manufacturing'),
('5000', 'Durable goods manufacturing', '33', ARRAY['33'], 'Durable goods'),
('5100', 'Nondurable goods manufacturing', '31', ARRAY['31','32'], 'Nondurable goods'),
('6000', 'Wholesale and retail trade', '42', ARRAY['42','44','45'], 'Trade'),
('6100', 'Wholesale trade', '42', ARRAY['42'], 'Wholesale'),
('6200', 'Retail trade', '44', ARRAY['44','45'], 'Retail'),
('7000', 'Transportation and utilities', '48', ARRAY['48','49','22'], 'Transport + utilities'),
('7100', 'Transportation and warehousing', '48', ARRAY['48','49'], 'Transportation'),
('7200', 'Utilities', '22', ARRAY['22'], 'Utilities'),
('8000', 'Information', '51', ARRAY['51'], 'Information'),
('8100', 'Finance', '52', ARRAY['52'], 'Finance and insurance'),
('8200', 'Professional and business services', '54', ARRAY['54','55','56'], 'Professional services'),
('9000', 'Education and health services', '61', ARRAY['61','62'], 'Education + health'),
('9100', 'Educational services', '61', ARRAY['61'], 'Education'),
('9200', 'Health care and social assistance', '62', ARRAY['62'], 'Healthcare'),
('9300', 'Leisure and hospitality', '71', ARRAY['71','72'], 'Leisure + hospitality'),
('9400', 'Arts, entertainment, recreation', '71', ARRAY['71'], 'Arts/entertainment'),
('9500', 'Accommodation and food services', '72', ARRAY['72'], 'Hotels/restaurants'),
('9600', 'Other services', '81', ARRAY['81'], 'Other services'),
('9700', 'Public administration', '92', ARRAY['92'], 'Government');

CREATE INDEX idx_bls_naics_mapping_naics ON bls_naics_mapping(naics_2digit);

-- ============================================================================
-- View: Latest union density by NAICS sector
-- ============================================================================

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

-- ============================================================================
-- View: Industry projections with NAICS mapping
-- ============================================================================

CREATE OR REPLACE VIEW v_naics_projections AS
SELECT 
    LEFT(bip.naics_code, 2) as naics_2digit,
    ns.sector_name,
    bip.naics_code,
    bip.title as industry_title,
    bip.employment_2024,
    bip.employment_2034,
    bip.employment_change,
    bip.percent_change
FROM bls_industry_projections bip
LEFT JOIN naics_sectors ns ON LEFT(bip.naics_code, 2) = ns.naics_2digit
WHERE bip.naics_code IS NOT NULL
ORDER BY bip.employment_change DESC;

-- ============================================================================
-- Verify the fixes
-- ============================================================================

-- Test density view
SELECT * FROM v_naics_union_density LIMIT 5;

-- Test projections view  
SELECT * FROM v_naics_projections LIMIT 5;

SELECT 'Patch A complete - BLS density views fixed' as status;
