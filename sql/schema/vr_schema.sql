-- ============================================================================
-- Voluntary Recognition Data Integration Schema
-- Labor Relations Research Platform - Phase 8A
-- Created: January 26, 2025
-- Run: psql -U postgres -d olms_multiyear -f vr_schema.sql
-- ============================================================================

-- ============================================================================
-- CHECKPOINT 1.1: CORE VR TABLE
-- ============================================================================

DROP TABLE IF EXISTS nlrb_voluntary_recognition CASCADE;
CREATE TABLE nlrb_voluntary_recognition (
    id SERIAL PRIMARY KEY,
    
    -- Case identification
    vr_case_number VARCHAR(50) UNIQUE NOT NULL,
    region INTEGER,
    regional_office TEXT,
    case_format VARCHAR(20),
    
    -- Location
    unit_city VARCHAR(100),
    unit_state CHAR(2),
    
    -- Dates
    date_vr_request_received DATE,
    date_voluntary_recognition DATE,
    date_vr_notice_sent DATE,
    date_notice_posted DATE,
    date_posting_closes DATE,
    date_r_case_petition_filed DATE,
    case_filed_date DATE,
    
    -- Employer information
    employer_name TEXT NOT NULL,
    employer_name_normalized VARCHAR(500),
    employer_name_upper VARCHAR(500),
    
    -- Union information
    union_name TEXT NOT NULL,
    union_name_normalized VARCHAR(500),
    extracted_affiliation VARCHAR(50),
    extracted_local_number VARCHAR(50),
    
    -- Unit details
    unit_description TEXT,
    num_employees INTEGER,
    
    -- Linkages
    r_case_number VARCHAR(30),
    notes TEXT,
    
    -- Employer matching results
    matched_employer_id VARCHAR(20),
    employer_match_confidence DECIMAL(3,2),
    employer_match_method VARCHAR(50),
    
    -- Union matching results  
    matched_union_fnum VARCHAR(20),
    union_match_confidence DECIMAL(3,2),
    union_match_method VARCHAR(50),
    
    -- Metadata
    data_quality_flags TEXT[],
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Indexes
CREATE INDEX idx_vr_case_number ON nlrb_voluntary_recognition(vr_case_number);
CREATE INDEX idx_vr_region ON nlrb_voluntary_recognition(region);
CREATE INDEX idx_vr_state ON nlrb_voluntary_recognition(unit_state);
CREATE INDEX idx_vr_city_state ON nlrb_voluntary_recognition(unit_city, unit_state);
CREATE INDEX idx_vr_employer_norm ON nlrb_voluntary_recognition(employer_name_normalized);
CREATE INDEX idx_vr_employer_upper ON nlrb_voluntary_recognition(employer_name_upper);
CREATE INDEX idx_vr_union_norm ON nlrb_voluntary_recognition(union_name_normalized);
CREATE INDEX idx_vr_affiliation ON nlrb_voluntary_recognition(extracted_affiliation);
CREATE INDEX idx_vr_date_request ON nlrb_voluntary_recognition(date_vr_request_received);
CREATE INDEX idx_vr_date_recognition ON nlrb_voluntary_recognition(date_voluntary_recognition);
CREATE INDEX idx_vr_matched_employer ON nlrb_voluntary_recognition(matched_employer_id);
CREATE INDEX idx_vr_matched_union ON nlrb_voluntary_recognition(matched_union_fnum);
CREATE INDEX idx_vr_r_case ON nlrb_voluntary_recognition(r_case_number);
CREATE INDEX idx_vr_employees ON nlrb_voluntary_recognition(num_employees) WHERE num_employees IS NOT NULL;

COMMENT ON TABLE nlrb_voluntary_recognition IS 'NLRB Voluntary Recognition cases (2007-2024) - union organizing without formal election';

-- ============================================================================
-- CHECKPOINT 1.2: LOOKUP TABLES
-- ============================================================================

DROP TABLE IF EXISTS vr_status_lookup CASCADE;
CREATE TABLE vr_status_lookup (
    status_code VARCHAR(30) PRIMARY KEY,
    status_name VARCHAR(100),
    description TEXT
);

INSERT INTO vr_status_lookup VALUES
('POSTED', 'Notice Posted', 'VR notice has been posted, waiting period active'),
('CLOSED', 'Posting Closed', 'Waiting period has ended, no election petition filed'),
('PETITION_FILED', 'Election Petition Filed', 'Employees filed for election during waiting period'),
('RECOGNIZED', 'Union Recognized', 'Employer has voluntarily recognized the union');

DROP TABLE IF EXISTS nlrb_regions CASCADE;
CREATE TABLE nlrb_regions (
    region_number INTEGER PRIMARY KEY,
    region_name VARCHAR(100),
    headquarters_city VARCHAR(100),
    headquarters_state CHAR(2),
    states_covered TEXT[]
);

INSERT INTO nlrb_regions VALUES
(1, 'Region 1 - Boston', 'Boston', 'MA', ARRAY['CT', 'MA', 'ME', 'NH', 'RI', 'VT']),
(2, 'Region 2 - New York', 'New York', 'NY', ARRAY['NY']),
(3, 'Region 3 - Buffalo', 'Buffalo', 'NY', ARRAY['NY']),
(4, 'Region 4 - Philadelphia', 'Philadelphia', 'PA', ARRAY['DE', 'PA']),
(5, 'Region 5 - Baltimore', 'Baltimore', 'MD', ARRAY['DC', 'MD', 'VA', 'WV']),
(6, 'Region 6 - Pittsburgh', 'Pittsburgh', 'PA', ARRAY['PA', 'WV']),
(7, 'Region 7 - Detroit', 'Detroit', 'MI', ARRAY['MI']),
(8, 'Region 8 - Cleveland', 'Cleveland', 'OH', ARRAY['OH']),
(9, 'Region 9 - Cincinnati', 'Cincinnati', 'OH', ARRAY['IN', 'KY', 'OH']),
(10, 'Region 10 - Atlanta', 'Atlanta', 'GA', ARRAY['AL', 'GA', 'NC', 'SC', 'TN']),
(11, 'Region 11 - Winston-Salem', 'Winston-Salem', 'NC', ARRAY['NC', 'SC', 'VA', 'WV']),
(12, 'Region 12 - Tampa', 'Tampa', 'FL', ARRAY['FL', 'PR', 'VI']),
(13, 'Region 13 - Chicago', 'Chicago', 'IL', ARRAY['IL']),
(14, 'Region 14 - St. Louis', 'St. Louis', 'MO', ARRAY['IL', 'MO', 'IN', 'KS']),
(15, 'Region 15 - New Orleans', 'New Orleans', 'LA', ARRAY['AL', 'FL', 'LA', 'MS']),
(16, 'Region 16 - Fort Worth', 'Fort Worth', 'TX', ARRAY['OK', 'TX']),
(17, 'Region 17 - Kansas City', 'Kansas City', 'KS', ARRAY['IA', 'KS', 'MO', 'NE']),
(18, 'Region 18 - Minneapolis', 'Minneapolis', 'MN', ARRAY['MN', 'ND', 'SD', 'WI']),
(19, 'Region 19 - Seattle', 'Seattle', 'WA', ARRAY['AK', 'ID', 'MT', 'OR', 'WA']),
(20, 'Region 20 - San Francisco', 'San Francisco', 'CA', ARRAY['CA', 'HI', 'NV']),
(21, 'Region 21 - Los Angeles', 'Los Angeles', 'CA', ARRAY['AZ', 'CA', 'HI', 'NV']),
(22, 'Region 22 - Newark', 'Newark', 'NJ', ARRAY['NJ']),
(24, 'Region 24 - San Juan', 'San Juan', 'PR', ARRAY['PR', 'VI']),
(25, 'Region 25 - Indianapolis', 'Indianapolis', 'IN', ARRAY['IN', 'KY']),
(26, 'Region 26 - Memphis', 'Memphis', 'TN', ARRAY['AR', 'MS', 'TN']),
(27, 'Region 27 - Denver', 'Denver', 'CO', ARRAY['CO', 'NM', 'UT', 'WY']),
(28, 'Region 28 - Phoenix', 'Phoenix', 'AZ', ARRAY['AZ', 'NM', 'NV', 'TX']),
(29, 'Region 29 - Brooklyn', 'Brooklyn', 'NY', ARRAY['NY']),
(30, 'Region 30 - Milwaukee', 'Milwaukee', 'WI', ARRAY['WI']),
(31, 'Region 31 - Los Angeles', 'Los Angeles', 'CA', ARRAY['CA']),
(32, 'Region 32 - Oakland', 'Oakland', 'CA', ARRAY['CA']);

COMMENT ON TABLE nlrb_regions IS 'NLRB regional office reference data';


-- Affiliation pattern matching table
DROP TABLE IF EXISTS vr_affiliation_patterns CASCADE;
CREATE TABLE vr_affiliation_patterns (
    id SERIAL PRIMARY KEY,
    affiliation_code VARCHAR(20) NOT NULL,
    pattern_regex TEXT NOT NULL,
    pattern_description TEXT,
    priority INTEGER DEFAULT 100
);

INSERT INTO vr_affiliation_patterns (affiliation_code, pattern_regex, pattern_description, priority) VALUES
('SEIU', 'SEIU|Service Employees International', 'Service Employees', 10),
('IBT', 'Teamsters|IBT|Brotherhood of Teamsters|I\.?B\.?T\.?', 'Teamsters', 10),
('UAW', 'UAW|United Auto|Automobile.*Workers', 'United Auto Workers', 10),
('CWA', 'CWA|Communications Workers', 'Communications Workers', 10),
('UNITE HERE', 'UNITE HERE|Unite Here|UNITE-HERE', 'UNITE HERE', 10),
('AFSCME', 'AFSCME', 'AFSCME', 10),
('UFCW', 'UFCW|United Food', 'Food & Commercial Workers', 10),
('USW', 'USW|United Steel|Steelworkers', 'Steelworkers', 10),
('IBEW', 'IBEW|Electrical Workers', 'Electrical Workers', 10),
('LIUNA', 'LIUNA|Laborers.*International', 'Laborers', 10),
('AFT', 'AFT|Federation of Teachers', 'Teachers', 10),
('OPEIU', 'OPEIU|Office.*Professional', 'Office & Professional', 10),
('IAM', 'IAM|Machinists', 'Machinists', 10),
('IUOE', 'IUOE|Operating Engineers', 'Operating Engineers', 10),
('TNG-CWA', 'NewsGuild|Newspaper Guild|TNG-CWA', 'NewsGuild/CWA', 10),
('RWDSU', 'RWDSU', 'Retail Workers', 10),
('ILWU', 'ILWU|Longshore.*Warehouse', 'Longshore Workers', 10),
('ILA', '\bILA\b|Longshoremen.*Association', 'Longshoremen ILA', 10),
('SMART', 'SMART|Sheet Metal', 'Sheet Metal Workers', 10),
('BCTGM', 'BCTGM|Bakery.*Confectionery', 'Bakery Workers', 10),
('NATCA', 'NATCA|Air Traffic Controllers', 'Air Traffic Controllers', 10),
('ALPA', 'ALPA|Airline Pilots', 'Airline Pilots', 10),
('AFA-CWA', 'AFA|Flight Attendants', 'Flight Attendants', 10),
('IFPTE', 'IFPTE|Professional.*Technical', 'Professional & Technical', 10),
('TWU', '\bTWU\b|Transport Workers', 'Transport Workers', 10),
('ATU', '\bATU\b|Amalgamated Transit', 'Transit Union', 10),
('NNU', 'NNU|National Nurses', 'National Nurses United', 10),
('AFL-CIO', 'AFL-?CIO', 'AFL-CIO affiliate (generic)', 50),
('INDEPENDENT', '.*', 'Independent/Unaffiliated', 999);

COMMENT ON TABLE vr_affiliation_patterns IS 'Regex patterns for extracting union affiliations from VR union names';


-- ============================================================================
-- CHECKPOINT 1.3: STAGING TABLES FOR MATCHING
-- ============================================================================

DROP TABLE IF EXISTS vr_employer_match_staging CASCADE;
CREATE TABLE vr_employer_match_staging (
    vr_id INTEGER PRIMARY KEY,
    employer_name_original TEXT,
    employer_name_normalized VARCHAR(500),
    unit_city VARCHAR(100),
    unit_state CHAR(2),
    match_1_employer_id VARCHAR(20),
    match_1_name VARCHAR(500),
    match_1_score DECIMAL(5,2),
    match_1_method VARCHAR(50),
    match_2_employer_id VARCHAR(20),
    match_2_name VARCHAR(500),
    match_2_score DECIMAL(5,2),
    match_2_method VARCHAR(50),
    match_3_employer_id VARCHAR(20),
    match_3_name VARCHAR(500),
    match_3_score DECIMAL(5,2),
    match_3_method VARCHAR(50),
    selected_match INTEGER,
    manual_review_needed BOOLEAN DEFAULT FALSE,
    review_notes TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);

DROP TABLE IF EXISTS vr_union_match_staging CASCADE;
CREATE TABLE vr_union_match_staging (
    vr_id INTEGER PRIMARY KEY,
    union_name_original TEXT,
    union_name_normalized VARCHAR(500),
    extracted_affiliation VARCHAR(50),
    extracted_local_number VARCHAR(50),
    match_1_fnum VARCHAR(20),
    match_1_name VARCHAR(500),
    match_1_score DECIMAL(5,2),
    match_1_method VARCHAR(50),
    match_2_fnum VARCHAR(20),
    match_2_name VARCHAR(500),
    match_2_score DECIMAL(5,2),
    match_2_method VARCHAR(50),
    match_3_fnum VARCHAR(20),
    match_3_name VARCHAR(500),
    match_3_score DECIMAL(5,2),
    match_3_method VARCHAR(50),
    selected_match INTEGER,
    manual_review_needed BOOLEAN DEFAULT FALSE,
    review_notes TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);

COMMENT ON TABLE vr_employer_match_staging IS 'Staging table for VR employer matching candidates';
COMMENT ON TABLE vr_union_match_staging IS 'Staging table for VR union matching candidates';


-- ============================================================================
-- CHECKPOINT 1.4: INTEGRATION VIEWS (Basic)
-- ============================================================================

CREATE OR REPLACE VIEW v_vr_by_year AS
SELECT 
    EXTRACT(YEAR FROM date_vr_request_received)::INTEGER as year,
    COUNT(*) as total_cases,
    SUM(CASE WHEN num_employees IS NOT NULL THEN num_employees ELSE 0 END) as total_employees,
    AVG(num_employees)::INTEGER as avg_unit_size,
    COUNT(DISTINCT unit_state) as states_covered,
    COUNT(CASE WHEN r_case_number IS NOT NULL THEN 1 END) as petitions_filed
FROM nlrb_voluntary_recognition
WHERE date_vr_request_received IS NOT NULL
GROUP BY EXTRACT(YEAR FROM date_vr_request_received)
ORDER BY year;

CREATE OR REPLACE VIEW v_vr_by_state AS
SELECT 
    unit_state as state,
    COUNT(*) as total_cases,
    SUM(CASE WHEN num_employees IS NOT NULL THEN num_employees ELSE 0 END) as total_employees,
    AVG(num_employees)::INTEGER as avg_unit_size,
    COUNT(CASE WHEN matched_employer_id IS NOT NULL THEN 1 END) as matched_employers,
    COUNT(CASE WHEN matched_union_fnum IS NOT NULL THEN 1 END) as matched_unions
FROM nlrb_voluntary_recognition
WHERE unit_state IS NOT NULL AND LENGTH(unit_state) = 2
GROUP BY unit_state
ORDER BY COUNT(*) DESC;

CREATE OR REPLACE VIEW v_vr_by_affiliation AS
SELECT 
    COALESCE(extracted_affiliation, 'UNKNOWN') as affiliation,
    COUNT(*) as total_cases,
    SUM(CASE WHEN num_employees IS NOT NULL THEN num_employees ELSE 0 END) as total_employees,
    AVG(num_employees)::INTEGER as avg_unit_size,
    COUNT(CASE WHEN matched_union_fnum IS NOT NULL THEN 1 END) as matched_to_olms,
    MIN(date_vr_request_received) as earliest_case,
    MAX(date_vr_request_received) as latest_case
FROM nlrb_voluntary_recognition
GROUP BY COALESCE(extracted_affiliation, 'UNKNOWN')
ORDER BY COUNT(*) DESC;

CREATE OR REPLACE VIEW v_vr_data_quality AS
SELECT 'Total Records' as metric, COUNT(*)::TEXT as value FROM nlrb_voluntary_recognition
UNION ALL SELECT 'With Employee Count', COUNT(*)::TEXT FROM nlrb_voluntary_recognition WHERE num_employees IS NOT NULL
UNION ALL SELECT 'With City/State', COUNT(*)::TEXT FROM nlrb_voluntary_recognition WHERE unit_city IS NOT NULL AND unit_state IS NOT NULL
UNION ALL SELECT 'With Recognition Date', COUNT(*)::TEXT FROM nlrb_voluntary_recognition WHERE date_voluntary_recognition IS NOT NULL
UNION ALL SELECT 'Linked to R Case', COUNT(*)::TEXT FROM nlrb_voluntary_recognition WHERE r_case_number IS NOT NULL
UNION ALL SELECT 'Employers Matched', COUNT(*)::TEXT FROM nlrb_voluntary_recognition WHERE matched_employer_id IS NOT NULL
UNION ALL SELECT 'Unions Matched', COUNT(*)::TEXT FROM nlrb_voluntary_recognition WHERE matched_union_fnum IS NOT NULL;

COMMENT ON VIEW v_vr_by_year IS 'Voluntary recognition cases aggregated by year';
COMMENT ON VIEW v_vr_by_state IS 'Voluntary recognition cases aggregated by state';
COMMENT ON VIEW v_vr_by_affiliation IS 'Voluntary recognition cases aggregated by union affiliation';
COMMENT ON VIEW v_vr_data_quality IS 'Data quality metrics for VR data';

-- Verification
SELECT 'VR SCHEMA CREATED SUCCESSFULLY' as status;
