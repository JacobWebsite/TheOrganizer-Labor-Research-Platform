-- ============================================================================
-- Labor Relations Platform v4 - Employer Search Enhancement Schema
-- Adds NAICS mapping, SIC crosswalk, and search support tables
-- Created: January 24, 2026
-- ============================================================================

-- ============================================================================
-- NAICS LOOKUP TABLES
-- ============================================================================

-- NAICS 2-digit sector lookup
DROP TABLE IF EXISTS naics_sectors CASCADE;
CREATE TABLE naics_sectors (
    naics_2digit VARCHAR(2) PRIMARY KEY,
    sector_name VARCHAR(100) NOT NULL,
    description TEXT
);

INSERT INTO naics_sectors (naics_2digit, sector_name, description) VALUES
('11', 'Agriculture, Forestry, Fishing and Hunting', 'Crop production, animal production, forestry, logging, fishing, hunting, trapping'),
('21', 'Mining, Quarrying, and Oil and Gas Extraction', 'Oil/gas extraction, mining except oil/gas, support activities for mining'),
('22', 'Utilities', 'Electric power, natural gas, water, sewage, steam supply'),
('23', 'Construction', 'Building construction, heavy/civil engineering, specialty trade contractors'),
('31', 'Manufacturing (Food/Textiles)', 'Food, beverage, tobacco, textile, apparel, leather products'),
('32', 'Manufacturing (Wood/Paper/Chemicals)', 'Wood, paper, printing, petroleum, chemicals, plastics, rubber, nonmetallic minerals'),
('33', 'Manufacturing (Metals/Machinery/Electronics)', 'Primary metals, fabricated metals, machinery, computers, electronics, transportation equipment'),
('42', 'Wholesale Trade', 'Merchant wholesalers, electronic markets, agents and brokers'),
('44', 'Retail Trade (Motor Vehicles/Home)', 'Motor vehicles, furniture, electronics, building materials'),
('45', 'Retail Trade (Grocery/General)', 'Food/beverage stores, health stores, gasoline, clothing, general merchandise'),
('48', 'Transportation and Warehousing (Transport)', 'Air, rail, water, truck, transit, pipeline, scenic, postal'),
('49', 'Transportation and Warehousing (Support)', 'Couriers, warehousing, support activities'),
('51', 'Information', 'Publishing, motion pictures, broadcasting, telecommunications, data processing'),
('52', 'Finance and Insurance', 'Banks, credit unions, securities, insurance carriers, funds'),
('53', 'Real Estate and Rental and Leasing', 'Real estate, rental/leasing, lessors'),
('54', 'Professional, Scientific, and Technical Services', 'Legal, accounting, architecture, engineering, computer systems, consulting'),
('55', 'Management of Companies and Enterprises', 'Holding companies, corporate offices'),
('56', 'Administrative and Support and Waste Management', 'Office admin, facilities, employment services, security, janitorial, waste management'),
('61', 'Educational Services', 'Schools, colleges, training, educational support'),
('62', 'Health Care and Social Assistance', 'Hospitals, physicians, nursing care, social assistance'),
('71', 'Arts, Entertainment, and Recreation', 'Performing arts, museums, gambling, amusement, recreation'),
('72', 'Accommodation and Food Services', 'Hotels, restaurants, bars, food services'),
('81', 'Other Services (except Public Administration)', 'Repair, personal services, religious, civic, private households'),
('92', 'Public Administration', 'Executive, legislative, courts, public order, administration of programs');

-- Add index for fast lookups
CREATE INDEX idx_naics_sectors_name ON naics_sectors(sector_name);

-- ============================================================================
-- UNION AFFILIATION → NAICS MAPPING
-- Known patterns linking union affiliations to industries
-- ============================================================================

DROP TABLE IF EXISTS union_affiliation_naics CASCADE;
CREATE TABLE union_affiliation_naics (
    id SERIAL PRIMARY KEY,
    aff_abbr VARCHAR(50) NOT NULL,
    industry_pattern VARCHAR(200),
    naics_2digit VARCHAR(2) REFERENCES naics_sectors(naics_2digit),
    naics_codes TEXT[],                      -- Specific NAICS codes if known
    confidence VARCHAR(20) DEFAULT 'high',   -- high, medium, low
    description TEXT,
    UNIQUE(aff_abbr, naics_2digit)
);

-- Populate known union → industry mappings
INSERT INTO union_affiliation_naics (aff_abbr, industry_pattern, naics_2digit, naics_codes, confidence, description) VALUES
-- Healthcare unions
('SEIU', 'Healthcare', '62', ARRAY['621','622','623','624'], 'high', 'Service Employees - healthcare workers'),
('AFSCME', 'Healthcare (Public)', '62', ARRAY['622','623'], 'medium', 'Public sector healthcare facilities'),
('NNU', 'Nursing', '62', ARRAY['622110','621111'], 'high', 'National Nurses United'),
('AFT', 'Healthcare', '62', ARRAY['622'], 'medium', 'AFT healthcare locals'),

-- Building Services / Janitorial
('SEIU', 'Building Services', '56', ARRAY['561710','561720','561612'], 'high', 'Janitorial, security guards'),

-- Manufacturing
('UAW', 'Auto Manufacturing', '33', ARRAY['3361','3362','3363'], 'high', 'Motor vehicles and parts'),
('USW', 'Steel/Primary Metals', '33', ARRAY['3311','3312','3313'], 'high', 'Iron, steel, aluminum'),
('USW', 'Fabricated Metals', '33', ARRAY['332'], 'high', 'Fabricated metal products'),
('IAM', 'Aerospace', '33', ARRAY['3364','3365'], 'high', 'Aerospace products and parts'),
('IAM', 'Machinery', '33', ARRAY['333'], 'high', 'Industrial machinery'),
('UE', 'Electrical Equipment', '33', ARRAY['335'], 'high', 'Electrical equipment manufacturing'),

-- Food/Retail
('UFCW', 'Grocery Retail', '44', ARRAY['4451','4452','4453'], 'high', 'Grocery and food stores'),
('UFCW', 'Food Processing', '31', ARRAY['311'], 'high', 'Food manufacturing'),
('RWDSU', 'Retail', '44', ARRAY['44','45'], 'high', 'Retail workers'),

-- Transportation
('IBT', 'Trucking', '48', ARRAY['484'], 'high', 'Trucking'),
('IBT', 'Warehousing', '49', ARRAY['493'], 'high', 'Warehousing and storage'),
('IBT', 'Package Delivery', '49', ARRAY['492'], 'high', 'Couriers and messengers'),
('TWU', 'Transit', '48', ARRAY['4851','4852','4853'], 'high', 'Urban transit'),
('ATU', 'Transit', '48', ARRAY['4851','4852','4853'], 'high', 'Amalgamated Transit Union'),
('SMART-TD', 'Rail', '48', ARRAY['482'], 'high', 'Rail transportation'),
('BRS', 'Rail', '48', ARRAY['482'], 'high', 'Brotherhood of Railroad Signalmen'),
('BLET', 'Rail', '48', ARRAY['482'], 'high', 'Locomotive Engineers'),
('TCU', 'Rail', '48', ARRAY['482'], 'high', 'Transportation Communications'),

-- Construction
('IBEW', 'Electrical Construction', '23', ARRAY['238210'], 'high', 'Electrical contractors'),
('LIUNA', 'Construction', '23', ARRAY['236','237','238'], 'high', 'Construction laborers'),
('UA', 'Plumbing/Pipefitting', '23', ARRAY['238220'], 'high', 'Plumbers, pipefitters'),
('IUOE', 'Heavy Equipment', '23', ARRAY['237'], 'high', 'Operating engineers'),
('SMART', 'Sheet Metal', '23', ARRAY['238170'], 'high', 'Sheet metal workers'),
('UBC', 'Carpentry', '23', ARRAY['238350'], 'high', 'Carpenters'),
('BAC', 'Masonry', '23', ARRAY['238140'], 'high', 'Bricklayers'),
('OPCMIA', 'Cement/Plaster', '23', ARRAY['238310','238340'], 'high', 'Plasterers, cement masons'),
('IUPAT', 'Painting', '23', ARRAY['238320'], 'high', 'Painters'),
('HEAT', 'Insulation', '23', ARRAY['238310'], 'high', 'Heat and frost insulators'),
('IW', 'Iron/Steel', '23', ARRAY['238120'], 'high', 'Iron workers'),

-- Utilities/Energy
('IBEW', 'Utilities', '22', ARRAY['2211','2212'], 'high', 'Electric and gas utilities'),
('UWUA', 'Utilities', '22', ARRAY['2211','2212','2213'], 'high', 'Utility Workers'),

-- Communications/Tech
('CWA', 'Telecommunications', '51', ARRAY['517'], 'high', 'Wired and wireless carriers'),
('CWA', 'Broadcasting', '51', ARRAY['515'], 'medium', 'Radio/TV broadcasting'),

-- Hospitality
('UNITE HERE', 'Hotels', '72', ARRAY['7211','7212'], 'high', 'Hotels and motels'),
('UNITE HERE', 'Restaurants/Food Service', '72', ARRAY['7221','7222','7223'], 'high', 'Restaurants, caterers'),
('UNITE HERE', 'Gaming', '71', ARRAY['7132'], 'high', 'Casino hotels'),

-- Education
('AFT', 'Education', '61', ARRAY['6111','6112','6113'], 'high', 'Schools - AFT'),
('NEA', 'K-12 Education', '61', ARRAY['6111'], 'high', 'Elementary/secondary schools'),
('AAUP', 'Higher Education', '61', ARRAY['6113'], 'high', 'Colleges and universities'),

-- Government/Public Sector
('AFSCME', 'Public Administration', '92', ARRAY['921','922','923','924','925','926'], 'high', 'Government workers'),
('AFGE', 'Federal Government', '92', ARRAY['921'], 'high', 'Federal employees'),
('NFFE', 'Federal Government', '92', ARRAY['921'], 'high', 'Federal employees'),
('NTEU', 'Federal Government', '92', ARRAY['921'], 'high', 'Treasury employees'),

-- Entertainment
('SAG-AFTRA', 'Motion Pictures', '51', ARRAY['5121'], 'high', 'Motion picture/sound recording'),
('IATSE', 'Motion Pictures', '51', ARRAY['5121'], 'high', 'Theatrical stage employees'),
('DGA', 'Motion Pictures', '51', ARRAY['5121'], 'high', 'Directors Guild'),
('WGA', 'Motion Pictures', '51', ARRAY['5121'], 'high', 'Writers Guild'),

-- Postal/Delivery
('NALC', 'Postal', '49', ARRAY['491'], 'high', 'Letter carriers'),
('APWU', 'Postal', '49', ARRAY['491'], 'high', 'Postal workers'),
('NPMHU', 'Postal', '49', ARRAY['491'], 'high', 'Mail handlers'),

-- Maritime
('ILA', 'Ports/Stevedoring', '48', ARRAY['4883'], 'high', 'Longshoremen - East/Gulf'),
('ILWU', 'Ports/Stevedoring', '48', ARRAY['4883'], 'high', 'Longshoremen - West Coast'),
('SIU', 'Maritime', '48', ARRAY['4831','4832'], 'high', 'Seafarers'),
('MM&P', 'Maritime', '48', ARRAY['4831','4832'], 'high', 'Masters, Mates, Pilots'),
('AFA', 'Airlines', '48', ARRAY['4811'], 'high', 'Flight attendants'),
('ALPA', 'Airlines', '48', ARRAY['4811'], 'high', 'Airline pilots');

-- Index for fast lookups
CREATE INDEX idx_union_aff_naics_aff ON union_affiliation_naics(aff_abbr);
CREATE INDEX idx_union_aff_naics_naics ON union_affiliation_naics(naics_2digit);

-- ============================================================================
-- UNION → NAICS MAPPING TABLE (Derived from employer data)
-- ============================================================================

DROP TABLE IF EXISTS union_naics_mapping CASCADE;
CREATE TABLE union_naics_mapping (
    f_num VARCHAR(20) NOT NULL,
    naics_code VARCHAR(6) NOT NULL,
    naics_level INTEGER,                      -- 2, 3, 4, 5, or 6 digit
    source VARCHAR(50),                       -- 'employer_derived', 'affiliation_pattern', 'manual'
    confidence NUMERIC(3,2),                  -- 0.00 to 1.00
    employer_count INTEGER,                   -- How many employers with this NAICS
    worker_count INTEGER,                     -- Total workers in this NAICS
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (f_num, naics_code)
);

CREATE INDEX idx_union_naics_fnum ON union_naics_mapping(f_num);
CREATE INDEX idx_union_naics_code ON union_naics_mapping(naics_code);
CREATE INDEX idx_union_naics_source ON union_naics_mapping(source);

-- ============================================================================
-- SIC → NAICS CROSSWALK (For historical data)
-- ============================================================================

DROP TABLE IF EXISTS sic_naics_xwalk CASCADE;
CREATE TABLE sic_naics_xwalk (
    sic_code VARCHAR(4) NOT NULL,
    sic_description VARCHAR(200),
    naics_code VARCHAR(6) NOT NULL,
    naics_description VARCHAR(200),
    notes TEXT,
    PRIMARY KEY (sic_code, naics_code)
);

CREATE INDEX idx_sic_naics_sic ON sic_naics_xwalk(sic_code);
CREATE INDEX idx_sic_naics_naics ON sic_naics_xwalk(naics_code);

-- ============================================================================
-- EMPLOYER SEARCH INDEXES (Fuzzy matching support)
-- ============================================================================

-- Enable pg_trgm extension for fuzzy text search (run as superuser if needed)
-- CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- GIN trigram index for fast fuzzy employer name search
-- DROP INDEX IF EXISTS idx_f7_employer_name_trgm;
-- CREATE INDEX idx_f7_employer_name_trgm ON f7_employers_deduped USING GIN (employer_name gin_trgm_ops);

-- ============================================================================
-- ENHANCED VIEWS FOR SEARCH
-- ============================================================================

-- View: Employers with full NAICS sector info
CREATE OR REPLACE VIEW v_employers_with_naics AS
SELECT 
    e.employer_id,
    e.employer_name,
    e.city,
    e.state,
    e.zip,
    e.naics,
    LEFT(e.naics, 2) as naics_2digit,
    ns.sector_name as naics_sector_name,
    e.latest_unit_size,
    e.latest_union_fnum,
    e.latest_union_name,
    e.latest_notice_date,
    e.latitude,
    e.longitude,
    e.healthcare_related,
    e.potentially_defunct,
    um.aff_abbr,
    um.union_name as union_display_name,
    um.members as union_members,
    um.sector as union_sector
FROM f7_employers_deduped e
LEFT JOIN unions_master um ON e.latest_union_fnum::text = um.f_num
LEFT JOIN naics_sectors ns ON LEFT(e.naics, 2) = ns.naics_2digit;

-- View: Union summary with NAICS distribution
CREATE OR REPLACE VIEW v_union_naics_summary AS
SELECT 
    e.latest_union_fnum as f_num,
    um.union_name,
    um.aff_abbr,
    um.sector,
    LEFT(e.naics, 2) as naics_2digit,
    ns.sector_name as naics_sector_name,
    COUNT(*) as employer_count,
    SUM(e.latest_unit_size) as total_workers
FROM f7_employers_deduped e
JOIN unions_master um ON e.latest_union_fnum::text = um.f_num
LEFT JOIN naics_sectors ns ON LEFT(e.naics, 2) = ns.naics_2digit
WHERE e.naics IS NOT NULL AND e.naics != ''
GROUP BY e.latest_union_fnum, um.union_name, um.aff_abbr, um.sector, LEFT(e.naics, 2), ns.sector_name
ORDER BY SUM(e.latest_unit_size) DESC NULLS LAST;

-- View: National union with all industry coverage
CREATE OR REPLACE VIEW v_affiliation_industry_coverage AS
SELECT 
    um.aff_abbr,
    MAX(um.union_name) as example_union_name,
    COUNT(DISTINCT um.f_num) as local_count,
    SUM(um.members) as total_members,
    LEFT(e.naics, 2) as naics_2digit,
    ns.sector_name as naics_sector_name,
    COUNT(DISTINCT e.employer_id) as employer_count,
    SUM(e.latest_unit_size) as covered_workers
FROM unions_master um
LEFT JOIN f7_employers_deduped e ON um.f_num = e.latest_union_fnum::text
LEFT JOIN naics_sectors ns ON LEFT(e.naics, 2) = ns.naics_2digit
WHERE um.aff_abbr IS NOT NULL AND um.aff_abbr != ''
GROUP BY um.aff_abbr, LEFT(e.naics, 2), ns.sector_name
ORDER BY um.aff_abbr, SUM(e.latest_unit_size) DESC NULLS LAST;

-- View: Sector-level statistics
CREATE OR REPLACE VIEW v_sector_statistics AS
SELECT 
    us.sector_code,
    us.sector_name,
    us.governing_law,
    us.f7_expected,
    COUNT(DISTINCT um.f_num) as union_count,
    SUM(um.members) as total_members,
    SUM(um.f7_employer_count) as employer_count,
    SUM(um.f7_total_workers) as covered_workers
FROM union_sector us
LEFT JOIN unions_master um ON us.sector_code = um.sector
GROUP BY us.sector_code, us.sector_name, us.governing_law, us.f7_expected
ORDER BY SUM(um.members) DESC NULLS LAST;

-- View: BLS density with NAICS mapping for UI dropdowns
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
LEFT JOIN bls_union_series bus ON bus.indy_code = bil.indy_code AND bus.area_code = '00'
LEFT JOIN bls_union_data bud ON bus.series_id = bud.series_id
WHERE bud.year >= 2020
ORDER BY bud.year DESC, bil.indy_code;

-- ============================================================================
-- POPULATE UNION-NAICS MAPPINGS FROM EMPLOYER DATA
-- ============================================================================

-- Derive union → NAICS from F-7 employers
INSERT INTO union_naics_mapping (f_num, naics_code, naics_level, source, confidence, employer_count, worker_count)
SELECT 
    e.latest_union_fnum::text as f_num,
    LEFT(e.naics, 2) as naics_code,
    2 as naics_level,
    'employer_derived' as source,
    0.90 as confidence,
    COUNT(*) as employer_count,
    SUM(COALESCE(e.latest_unit_size, 0)) as worker_count
FROM f7_employers_deduped e
WHERE e.naics IS NOT NULL 
  AND LENGTH(e.naics) >= 2
  AND e.latest_union_fnum IS NOT NULL
GROUP BY e.latest_union_fnum::text, LEFT(e.naics, 2)
HAVING COUNT(*) >= 1
ON CONFLICT (f_num, naics_code) DO UPDATE SET
    employer_count = EXCLUDED.employer_count,
    worker_count = EXCLUDED.worker_count;

-- ============================================================================
-- COMMENTS
-- ============================================================================

COMMENT ON TABLE naics_sectors IS 'NAICS 2-digit sector lookup table with descriptions';
COMMENT ON TABLE union_affiliation_naics IS 'Known mappings between union affiliations and NAICS industries';
COMMENT ON TABLE union_naics_mapping IS 'Union-to-NAICS mappings derived from employer data';
COMMENT ON TABLE sic_naics_xwalk IS 'Standard Industrial Classification to NAICS crosswalk';
COMMENT ON VIEW v_employers_with_naics IS 'F-7 employers enriched with NAICS sector info and union details';
COMMENT ON VIEW v_union_naics_summary IS 'Union summary showing NAICS distribution of their employers';
COMMENT ON VIEW v_affiliation_industry_coverage IS 'National unions with their industry coverage across sectors';
COMMENT ON VIEW v_sector_statistics IS 'Summary statistics by union sector (PRIVATE, FEDERAL, etc.)';
