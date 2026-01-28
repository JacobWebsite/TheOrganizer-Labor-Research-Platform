-- ============================================================================
-- F-7 Employer Data Integration Schema
-- For PostgreSQL olms_multiyear database
-- ============================================================================

-- ============================================================================
-- LOOKUP TABLES
-- ============================================================================

-- Sector classification lookup
DROP TABLE IF EXISTS union_sector CASCADE;
CREATE TABLE union_sector (
    sector_code VARCHAR(30) PRIMARY KEY,
    sector_name VARCHAR(100) NOT NULL,
    description TEXT,
    f7_expected BOOLEAN NOT NULL DEFAULT TRUE,
    governing_law VARCHAR(100)
);

INSERT INTO union_sector (sector_code, sector_name, description, f7_expected, governing_law) VALUES
('PRIVATE', 'Private Sector', 'Private sector workers covered by NLRA', TRUE, 'National Labor Relations Act (NLRA)'),
('FEDERAL', 'Federal Government', 'Federal government employees', FALSE, 'Federal Service Labor-Management Relations Act (FSLMRA)'),
('RAILROAD_AIRLINE_RLA', 'Railroad/Airline (RLA)', 'Railroad and airline workers', FALSE, 'Railway Labor Act (RLA)'),
('PUBLIC_SECTOR', 'State/Local Government', 'State and local government employees', FALSE, 'State labor relations laws (varies)'),
('OTHER', 'Other/Unclassified', 'Unions not clearly classified into other sectors', TRUE, 'Varies'),
('UNKNOWN', 'Unknown', 'Affiliation not recognized', TRUE, 'Unknown');

-- Match status lookup
DROP TABLE IF EXISTS union_match_status CASCADE;
CREATE TABLE union_match_status (
    status_code VARCHAR(30) PRIMARY KEY,
    status_name VARCHAR(100) NOT NULL,
    description TEXT,
    action_required TEXT
);

INSERT INTO union_match_status (status_code, status_name, description, action_required) VALUES
('MATCHED', 'Matched', 'Union has both LM filings and F7 employer records', 'None - data is complete'),
('FEDERAL_NO_F7_EXPECTED', 'Federal - No F7 Expected', 'Federal employee union - F7 system does not apply', 'None - expected behavior'),
('RLA_NO_F7_EXPECTED', 'RLA - No F7 Expected', 'Railroad/Airline union under Railway Labor Act', 'None - expected behavior'),
('PUBLIC_SECTOR_NO_F7_EXPECTED', 'Public Sector - No F7 Expected', 'State/local government union - limited F7 coverage', 'None - expected behavior'),
('LIKELY_TERMINATED', 'Likely Terminated', 'No LM filing since 2015 - union likely dissolved or merged', 'Flag as inactive'),
('ACTIVE_NO_F7_INVESTIGATE', 'Active - Investigate', 'Recent LM filing but no F7 employers - may be parent union or voluntary recognition', 'Review for parent/local relationship');

-- ============================================================================
-- F-7 EMPLOYERS TABLE
-- Deduplicated employer records from F-7 bargaining notices with geocoding
-- ============================================================================

DROP TABLE IF EXISTS f7_employers CASCADE;
CREATE TABLE f7_employers (
    employer_id VARCHAR(20) PRIMARY KEY,        -- MD5 hash of normalized name+city+state
    employer_name VARCHAR(500) NOT NULL,
    street VARCHAR(500),
    city VARCHAR(100),
    state CHAR(2),
    zip VARCHAR(20),
    
    -- Latest filing information
    latest_notice_date DATE,
    latest_unit_size INTEGER,
    latest_union_fnum INTEGER,                  -- Links to lm_data.f_num
    latest_union_name VARCHAR(500),
    
    -- Classification
    naics VARCHAR(10),                          -- Industry code
    healthcare_related BOOLEAN DEFAULT FALSE,
    
    -- Status flags
    filing_count INTEGER DEFAULT 1,             -- Number of F-7 filings for this employer
    potentially_defunct BOOLEAN DEFAULT FALSE,  -- No filing in 10+ years
    data_quality_flag VARCHAR(50),              -- 'placeholder_value', 'suspicious_unit_size', etc.
    
    -- Geocoding
    latitude NUMERIC(11,8),
    longitude NUMERIC(11,8),
    geocode_status VARCHAR(20),                 -- 'geocoded', 'failed', NULL
    
    -- Metadata
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Indexes for common queries
CREATE INDEX idx_f7_employers_state ON f7_employers(state);
CREATE INDEX idx_f7_employers_city_state ON f7_employers(city, state);
CREATE INDEX idx_f7_employers_union_fnum ON f7_employers(latest_union_fnum);
CREATE INDEX idx_f7_employers_naics ON f7_employers(naics);
CREATE INDEX idx_f7_employers_geocoded ON f7_employers(latitude, longitude) WHERE latitude IS NOT NULL;
CREATE INDEX idx_f7_employers_defunct ON f7_employers(potentially_defunct);
CREATE INDEX idx_f7_employers_healthcare ON f7_employers(healthcare_related) WHERE healthcare_related = TRUE;
CREATE INDEX idx_f7_employers_notice_date ON f7_employers(latest_notice_date);

-- ============================================================================
-- UNION MASTER TABLE (Extended union metadata)
-- Combines LM filing data with F-7 linkage and sector classification
-- ============================================================================

DROP TABLE IF EXISTS unions_master CASCADE;
CREATE TABLE unions_master (
    f_num INTEGER PRIMARY KEY,                  -- OLMS file number (links to lm_data)
    union_name VARCHAR(500),
    aff_abbr VARCHAR(50),                       -- Affiliation abbreviation
    
    -- Latest LM filing info
    members INTEGER,
    yr_covered INTEGER,
    city VARCHAR(100),
    state CHAR(2),
    source_year INTEGER,                        -- Year of source LM data
    
    -- Sector classification
    sector VARCHAR(30) REFERENCES union_sector(sector_code),
    
    -- F-7 linkage summary
    f7_union_name VARCHAR(500),                 -- Union name as it appears in F-7 data
    f7_employer_count INTEGER DEFAULT 0,
    f7_total_workers INTEGER DEFAULT 0,
    f7_states TEXT,                             -- Comma-separated list of states with employers
    has_f7_employers BOOLEAN DEFAULT FALSE,
    
    -- Match status
    match_status VARCHAR(30) REFERENCES union_match_status(status_code),
    
    -- Metadata
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Indexes
CREATE INDEX idx_unions_master_aff ON unions_master(aff_abbr);
CREATE INDEX idx_unions_master_sector ON unions_master(sector);
CREATE INDEX idx_unions_master_status ON unions_master(match_status);
CREATE INDEX idx_unions_master_state ON unions_master(state);
CREATE INDEX idx_unions_master_has_f7 ON unions_master(has_f7_employers) WHERE has_f7_employers = TRUE;

-- ============================================================================
-- VIEWS
-- ============================================================================

-- View: F-7 employers with full union details
CREATE OR REPLACE VIEW v_f7_employers_full AS
SELECT 
    e.*,
    um.aff_abbr,
    um.members as union_members,
    um.sector,
    us.sector_name,
    us.governing_law
FROM f7_employers e
LEFT JOIN unions_master um ON e.latest_union_fnum = um.f_num
LEFT JOIN union_sector us ON um.sector = us.sector_code;

-- View: Geocoded employers only (for mapping)
CREATE OR REPLACE VIEW v_f7_employers_geocoded AS
SELECT *
FROM f7_employers
WHERE latitude IS NOT NULL AND longitude IS NOT NULL;

-- View: Active employers (not defunct)
CREATE OR REPLACE VIEW v_f7_employers_active AS
SELECT *
FROM f7_employers
WHERE potentially_defunct = FALSE;

-- View: Union summary with F-7 employer counts
CREATE OR REPLACE VIEW v_union_f7_summary AS
SELECT 
    um.f_num,
    um.union_name,
    um.aff_abbr,
    um.members,
    um.sector,
    us.sector_name,
    um.match_status,
    ms.status_name,
    um.f7_employer_count,
    um.f7_total_workers,
    um.f7_states,
    um.has_f7_employers
FROM unions_master um
LEFT JOIN union_sector us ON um.sector = us.sector_code
LEFT JOIN union_match_status ms ON um.match_status = ms.status_code;

-- View: State-level F-7 employer summary
CREATE OR REPLACE VIEW v_f7_state_summary AS
SELECT 
    state,
    COUNT(*) as employer_count,
    SUM(latest_unit_size) as total_workers,
    SUM(CASE WHEN potentially_defunct THEN 1 ELSE 0 END) as defunct_count,
    SUM(CASE WHEN latitude IS NOT NULL THEN 1 ELSE 0 END) as geocoded_count,
    SUM(CASE WHEN healthcare_related THEN 1 ELSE 0 END) as healthcare_count,
    COUNT(DISTINCT latest_union_fnum) as union_count
FROM f7_employers
WHERE state IS NOT NULL
GROUP BY state
ORDER BY employer_count DESC;

-- View: Sector summary statistics
CREATE OR REPLACE VIEW v_sector_summary AS
SELECT 
    us.sector_code,
    us.sector_name,
    us.governing_law,
    us.f7_expected,
    COUNT(um.f_num) as union_count,
    SUM(um.members) as total_members,
    SUM(um.f7_employer_count) as total_employers,
    SUM(um.f7_total_workers) as total_f7_workers
FROM union_sector us
LEFT JOIN unions_master um ON us.sector_code = um.sector
GROUP BY us.sector_code, us.sector_name, us.governing_law, us.f7_expected
ORDER BY union_count DESC;

-- View: Match status summary
CREATE OR REPLACE VIEW v_match_status_summary AS
SELECT 
    ms.status_code,
    ms.status_name,
    ms.description,
    COUNT(um.f_num) as union_count,
    SUM(um.members) as total_members,
    SUM(um.f7_employer_count) as employer_count
FROM union_match_status ms
LEFT JOIN unions_master um ON ms.status_code = um.match_status
GROUP BY ms.status_code, ms.status_name, ms.description
ORDER BY union_count DESC;

-- View: Join lm_data with F-7 employer counts
CREATE OR REPLACE VIEW v_lm_with_f7_summary AS
SELECT 
    l.rpt_id,
    l.f_num,
    l.union_name,
    l.aff_abbr,
    l.state,
    l.city,
    l.members,
    l.ttl_assets,
    l.ttl_receipts,
    l.yr_covered,
    um.sector,
    um.match_status,
    um.f7_employer_count,
    um.f7_total_workers,
    um.has_f7_employers
FROM lm_data l
LEFT JOIN unions_master um ON l.f_num = um.f_num;

-- ============================================================================
-- COMMENTS
-- ============================================================================

COMMENT ON TABLE f7_employers IS 'Deduplicated F-7 bargaining notice employers with geocoding (150K+ records)';
COMMENT ON TABLE unions_master IS 'Master union list combining LM filings with F-7 linkage and sector classification';
COMMENT ON TABLE union_sector IS 'Lookup table for union sector classifications (PRIVATE, FEDERAL, RLA, etc.)';
COMMENT ON TABLE union_match_status IS 'Lookup table explaining why unions may/may not have F-7 employer records';

COMMENT ON COLUMN f7_employers.employer_id IS 'MD5 hash of normalized (employer_name, city, state)';
COMMENT ON COLUMN f7_employers.latest_union_fnum IS 'Links to lm_data.f_num and unions_master.f_num';
COMMENT ON COLUMN f7_employers.potentially_defunct IS 'TRUE if no F-7 filing in 10+ years';
COMMENT ON COLUMN unions_master.f_num IS 'OLMS file number - primary key linking to lm_data';
COMMENT ON COLUMN unions_master.sector IS 'Classification explaining governing labor law';
COMMENT ON COLUMN unions_master.match_status IS 'Explains presence/absence of F-7 employer records';
