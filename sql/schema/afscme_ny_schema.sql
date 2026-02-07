-- AFSCME NY Employer Matching Schema
-- Purpose: Match 990 employers with AFSCME representation in NY, integrate contract data

-- Enable trigram extension for fuzzy matching
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- ============================================================================
-- Table: employers_990 - IRS 990 employer data
-- ============================================================================
DROP TABLE IF EXISTS employer_990_matches CASCADE;
DROP TABLE IF EXISTS contract_employer_matches CASCADE;
DROP TABLE IF EXISTS organizing_targets CASCADE;
DROP TABLE IF EXISTS employers_990 CASCADE;

CREATE TABLE employers_990 (
    id SERIAL PRIMARY KEY,

    -- Identity
    ein VARCHAR(9),
    name TEXT NOT NULL,
    name_normalized TEXT,

    -- Location
    address_line1 TEXT,
    city TEXT,
    state CHAR(2),
    zip_code VARCHAR(10),

    -- Source tracking
    source_type VARCHAR(20) NOT NULL,  -- filer, grant_recipient, contractor, related_org
    source_ein VARCHAR(9),
    source_name TEXT,
    source_file TEXT,

    -- Financial indicators
    salaries_benefits DECIMAL(15,2),
    employee_count INTEGER,
    total_revenue DECIMAL(15,2),
    grant_amount DECIMAL(12,2),
    contractor_payment DECIMAL(12,2),

    -- Classification
    exempt_status VARCHAR(20),
    ntee_code VARCHAR(10),
    industry_category TEXT,

    -- AFSCME relevance scoring
    afscme_relevance_score NUMERIC(3,2) DEFAULT 0,  -- 0.00 to 1.00
    afscme_sector_match BOOLEAN DEFAULT FALSE,

    -- Metadata
    tax_year INTEGER,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Indexes for employers_990
CREATE INDEX idx_990emp_ein ON employers_990(ein);
CREATE INDEX idx_990emp_state ON employers_990(state);
CREATE INDEX idx_990emp_city_state ON employers_990(city, state);
CREATE INDEX idx_990emp_name_trgm ON employers_990 USING gin(name_normalized gin_trgm_ops);
CREATE INDEX idx_990emp_industry ON employers_990(industry_category);
CREATE INDEX idx_990emp_afscme_score ON employers_990(afscme_relevance_score DESC);
CREATE INDEX idx_990emp_source_type ON employers_990(source_type);

-- ============================================================================
-- Table: employer_990_matches - Link 990 employers to existing AFSCME employers
-- ============================================================================
CREATE TABLE employer_990_matches (
    id SERIAL PRIMARY KEY,
    employer_990_id INTEGER REFERENCES employers_990(id) ON DELETE CASCADE,

    -- Match to F7 employers (private sector)
    f7_employer_id VARCHAR(50),

    -- Match to public sector employers
    ps_employer_id INTEGER,

    -- Match metadata
    match_method VARCHAR(50),  -- ein_exact, name_city_exact, fuzzy_name_state, fuzzy_combined
    match_score NUMERIC(5,2),
    match_confidence VARCHAR(20),  -- HIGH, MEDIUM, LOW

    -- Verification
    verified BOOLEAN DEFAULT FALSE,
    verified_by VARCHAR(100),
    verified_at TIMESTAMP,

    -- Status
    match_status VARCHAR(30) DEFAULT 'MATCHED',  -- MATCHED, POTENTIAL, REJECTED

    created_at TIMESTAMP DEFAULT NOW(),

    CONSTRAINT unique_990_f7_match UNIQUE (employer_990_id, f7_employer_id),
    CONSTRAINT unique_990_ps_match UNIQUE (employer_990_id, ps_employer_id)
);

CREATE INDEX idx_emp990_matches_990id ON employer_990_matches(employer_990_id);
CREATE INDEX idx_emp990_matches_f7id ON employer_990_matches(f7_employer_id);
CREATE INDEX idx_emp990_matches_psid ON employer_990_matches(ps_employer_id);
CREATE INDEX idx_emp990_matches_status ON employer_990_matches(match_status);

-- ============================================================================
-- Table: ny_state_contracts - NY State contract awards from data.ny.gov
-- ============================================================================
DROP TABLE IF EXISTS ny_state_contracts CASCADE;

CREATE TABLE ny_state_contracts (
    id SERIAL PRIMARY KEY,

    -- Contract identity
    contract_number VARCHAR(100),
    contract_title TEXT,

    -- Vendor/Awardee
    vendor_name TEXT NOT NULL,
    vendor_name_normalized TEXT,
    vendor_ein VARCHAR(9),
    vendor_address TEXT,
    vendor_city TEXT,
    vendor_state CHAR(2),
    vendor_zip VARCHAR(10),

    -- Contract details
    agency_name TEXT,
    agency_code VARCHAR(20),
    contract_type VARCHAR(100),

    -- Financials
    original_amount DECIMAL(15,2),
    current_amount DECIMAL(15,2),

    -- Dates
    start_date DATE,
    end_date DATE,

    -- Classification
    contract_category TEXT,
    service_description TEXT,

    -- AFSCME relevance
    is_afscme_relevant BOOLEAN DEFAULT FALSE,

    -- Metadata
    data_source TEXT DEFAULT 'data.ny.gov',
    fiscal_year INTEGER,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_ny_contracts_vendor_trgm ON ny_state_contracts USING gin(vendor_name_normalized gin_trgm_ops);
CREATE INDEX idx_ny_contracts_ein ON ny_state_contracts(vendor_ein);
CREATE INDEX idx_ny_contracts_agency ON ny_state_contracts(agency_name);
CREATE INDEX idx_ny_contracts_category ON ny_state_contracts(contract_category);
CREATE INDEX idx_ny_contracts_afscme ON ny_state_contracts(is_afscme_relevant) WHERE is_afscme_relevant = TRUE;

-- ============================================================================
-- Table: nyc_contracts - NYC contract awards from Checkbook NYC
-- ============================================================================
DROP TABLE IF EXISTS nyc_contracts CASCADE;

CREATE TABLE nyc_contracts (
    id SERIAL PRIMARY KEY,

    -- Contract identity
    contract_id VARCHAR(100),
    document_id VARCHAR(100),

    -- Vendor/Awardee
    vendor_name TEXT NOT NULL,
    vendor_name_normalized TEXT,
    vendor_ein VARCHAR(9),
    vendor_address TEXT,
    vendor_city TEXT,
    vendor_zip VARCHAR(10),

    -- Contract details
    agency_name TEXT,
    agency_code VARCHAR(20),
    contract_type VARCHAR(100),
    purpose TEXT,

    -- Financials
    original_amount DECIMAL(15,2),
    current_amount DECIMAL(15,2),
    spent_amount DECIMAL(15,2),

    -- Dates
    start_date DATE,
    end_date DATE,
    registration_date DATE,

    -- Classification
    industry_type VARCHAR(100),
    award_method VARCHAR(100),

    -- AFSCME relevance
    is_afscme_relevant BOOLEAN DEFAULT FALSE,

    -- Metadata
    data_source TEXT DEFAULT 'checkbooknyc',
    fiscal_year INTEGER,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_nyc_contracts_vendor_trgm ON nyc_contracts USING gin(vendor_name_normalized gin_trgm_ops);
CREATE INDEX idx_nyc_contracts_ein ON nyc_contracts(vendor_ein);
CREATE INDEX idx_nyc_contracts_agency ON nyc_contracts(agency_name);
CREATE INDEX idx_nyc_contracts_industry ON nyc_contracts(industry_type);
CREATE INDEX idx_nyc_contracts_afscme ON nyc_contracts(is_afscme_relevant) WHERE is_afscme_relevant = TRUE;

-- ============================================================================
-- Table: contract_employer_matches - Link contracts to employers
-- ============================================================================
CREATE TABLE contract_employer_matches (
    id SERIAL PRIMARY KEY,

    -- Contract reference (one of these will be populated)
    ny_state_contract_id INTEGER REFERENCES ny_state_contracts(id) ON DELETE CASCADE,
    nyc_contract_id INTEGER REFERENCES nyc_contracts(id) ON DELETE CASCADE,

    -- Employer reference
    employer_990_id INTEGER REFERENCES employers_990(id) ON DELETE CASCADE,

    -- Match metadata
    match_method VARCHAR(50),
    match_score NUMERIC(5,2),

    created_at TIMESTAMP DEFAULT NOW(),

    CONSTRAINT at_least_one_contract CHECK (
        ny_state_contract_id IS NOT NULL OR nyc_contract_id IS NOT NULL
    )
);

CREATE INDEX idx_cem_ny_contract ON contract_employer_matches(ny_state_contract_id);
CREATE INDEX idx_cem_nyc_contract ON contract_employer_matches(nyc_contract_id);
CREATE INDEX idx_cem_employer ON contract_employer_matches(employer_990_id);

-- ============================================================================
-- Table: organizing_targets - Prioritized list of potential targets
-- ============================================================================
CREATE TABLE organizing_targets (
    id SERIAL PRIMARY KEY,

    -- Employer reference
    employer_990_id INTEGER REFERENCES employers_990(id) ON DELETE CASCADE,

    -- Denormalized employer info
    employer_name TEXT NOT NULL,
    city TEXT,
    state CHAR(2),
    ein VARCHAR(9),

    -- Size indicators
    employee_count INTEGER,
    total_revenue DECIMAL(15,2),
    salaries_benefits DECIMAL(15,2),

    -- Industry
    industry_category TEXT,
    afscme_sector_score NUMERIC(3,2),

    -- Existing union status
    has_existing_afscme_contract BOOLEAN DEFAULT FALSE,
    existing_union_f_num VARCHAR(20),
    existing_union_name TEXT,

    -- Government funding exposure
    ny_state_contract_count INTEGER DEFAULT 0,
    ny_state_contract_total DECIMAL(15,2) DEFAULT 0,
    nyc_contract_count INTEGER DEFAULT 0,
    nyc_contract_total DECIMAL(15,2) DEFAULT 0,
    total_govt_funding DECIMAL(15,2) DEFAULT 0,
    govt_funding_score NUMERIC(3,2) DEFAULT 0,

    -- Combined priority score
    priority_score NUMERIC(5,2),  -- 0-100
    priority_tier VARCHAR(20),    -- TOP, HIGH, MEDIUM, LOW

    -- Campaign tracking
    status VARCHAR(30) DEFAULT 'NEW',  -- NEW, RESEARCHING, CONTACTED, ACTIVE_CAMPAIGN, ORGANIZED, DECLINED
    assigned_organizer TEXT,
    notes TEXT,

    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),

    CONSTRAINT unique_target_employer UNIQUE (employer_990_id)
);

CREATE INDEX idx_targets_priority ON organizing_targets(priority_score DESC);
CREATE INDEX idx_targets_tier ON organizing_targets(priority_tier);
CREATE INDEX idx_targets_status ON organizing_targets(status);
CREATE INDEX idx_targets_industry ON organizing_targets(industry_category);
CREATE INDEX idx_targets_state ON organizing_targets(state);
CREATE INDEX idx_targets_not_organized ON organizing_targets(has_existing_afscme_contract) WHERE has_existing_afscme_contract = FALSE;

-- ============================================================================
-- Views for analysis
-- ============================================================================

-- Unorganized employers by industry
CREATE OR REPLACE VIEW v_afscme_targets_by_industry AS
SELECT
    ot.industry_category,
    COUNT(*) as employer_count,
    SUM(ot.employee_count) as total_employees,
    SUM(ot.total_govt_funding) as total_govt_funding,
    AVG(ot.priority_score) as avg_priority_score,
    COUNT(*) FILTER (WHERE ot.priority_tier = 'TOP') as top_tier_count,
    COUNT(*) FILTER (WHERE ot.priority_tier = 'HIGH') as high_tier_count
FROM organizing_targets ot
WHERE ot.has_existing_afscme_contract = FALSE
  AND ot.state = 'NY'
GROUP BY ot.industry_category
ORDER BY SUM(ot.employee_count) DESC NULLS LAST;

-- Top targets with contract details
CREATE OR REPLACE VIEW v_top_afscme_targets AS
SELECT
    ot.*,
    e990.address_line1,
    e990.zip_code,
    e990.source_type,
    e990.exempt_status
FROM organizing_targets ot
JOIN employers_990 e990 ON ot.employer_990_id = e990.id
WHERE ot.state = 'NY'
  AND ot.has_existing_afscme_contract = FALSE
  AND ot.priority_tier IN ('TOP', 'HIGH')
ORDER BY ot.priority_score DESC;

-- Geographic distribution of targets
CREATE OR REPLACE VIEW v_afscme_targets_by_city AS
SELECT
    ot.city,
    COUNT(*) as target_count,
    SUM(ot.employee_count) as total_employees,
    SUM(ot.total_govt_funding) as total_funding,
    ARRAY_AGG(DISTINCT ot.industry_category) FILTER (WHERE ot.industry_category IS NOT NULL) as industries,
    AVG(ot.priority_score) as avg_priority
FROM organizing_targets ot
WHERE ot.has_existing_afscme_contract = FALSE
  AND ot.state = 'NY'
GROUP BY ot.city
ORDER BY SUM(ot.employee_count) DESC NULLS LAST;

-- Summary statistics
CREATE OR REPLACE VIEW v_afscme_targeting_summary AS
SELECT
    COUNT(*) as total_990_employers,
    COUNT(*) FILTER (WHERE state = 'NY') as ny_employers,
    COUNT(DISTINCT industry_category) as industries,
    SUM(employee_count) FILTER (WHERE state = 'NY') as ny_total_employees,
    SUM(total_revenue) FILTER (WHERE state = 'NY') as ny_total_revenue,
    COUNT(*) FILTER (WHERE afscme_sector_match AND state = 'NY') as ny_afscme_sector_employers
FROM employers_990;

COMMENT ON TABLE employers_990 IS 'IRS 990 employer data for AFSCME organizing target analysis';
COMMENT ON TABLE ny_state_contracts IS 'NY State contract awards from data.ny.gov';
COMMENT ON TABLE nyc_contracts IS 'NYC contract awards from Checkbook NYC';
COMMENT ON TABLE organizing_targets IS 'Prioritized list of potential AFSCME organizing targets';
