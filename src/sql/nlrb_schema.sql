-- ============================================================================
-- NLRB Case Data Integration Schema
-- For PostgreSQL olms_multiyear database
-- ============================================================================

-- ============================================================================
-- CORE TABLES
-- ============================================================================

-- Main case/filing table
DROP TABLE IF EXISTS nlrb_cases CASCADE;
CREATE TABLE nlrb_cases (
    case_number VARCHAR(20) PRIMARY KEY,
    case_name TEXT,
    case_type VARCHAR(10) NOT NULL,
    city VARCHAR(100),
    state CHAR(2),
    date_filed DATE,
    date_closed DATE,
    status VARCHAR(50),
    reason_closed VARCHAR(255),
    region_assigned VARCHAR(100),
    num_eligible_voters INTEGER,
    num_voters_on_petition INTEGER,
    certified_representative TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_nlrb_cases_type ON nlrb_cases(case_type);
CREATE INDEX idx_nlrb_cases_state ON nlrb_cases(state);
CREATE INDEX idx_nlrb_cases_date ON nlrb_cases(date_filed);
CREATE INDEX idx_nlrb_cases_status ON nlrb_cases(status);

-- Case type lookup
DROP TABLE IF EXISTS nlrb_case_types CASCADE;
CREATE TABLE nlrb_case_types (
    case_type VARCHAR(10) PRIMARY KEY,
    type_name VARCHAR(100) NOT NULL,
    category VARCHAR(50),
    description TEXT
);

INSERT INTO nlrb_case_types VALUES
('RC', 'Representation - Certification', 'Representation', 'Union seeks certification as bargaining representative'),
('RD', 'Representation - Decertification', 'Representation', 'Employees seek to remove union'),
('RM', 'Representation - Employer Petition', 'Representation', 'Employer questions union majority status'),
('UC', 'Unit Clarification', 'Representation', 'Clarify scope of existing bargaining unit'),
('UD', 'Union Deauthorization', 'Representation', 'Employees seek to remove union security clause'),
('AC', 'Amendment of Certification', 'Representation', 'Amend existing certification'),
('CA', 'ULP - Against Employer', 'Unfair Labor Practice', 'Union/employee charges employer violated NLRA'),
('CB', 'ULP - Against Union', 'Unfair Labor Practice', 'Employer/employee charges union violated NLRA'),
('CC', 'ULP - Secondary Boycott', 'Unfair Labor Practice', 'Charges of illegal secondary boycott'),
('CD', 'ULP - Jurisdictional Dispute', 'Unfair Labor Practice', 'Dispute between unions over work assignment'),
('CE', 'ULP - Dues/Fees', 'Unfair Labor Practice', 'Illegal dues or fees charged'),
('CG', 'ULP - Discrimination', 'Unfair Labor Practice', 'Discrimination for filing charges'),
('CP', 'ULP - Picketing', 'Unfair Labor Practice', 'Illegal recognitional or organizational picketing'),
('WH', 'Beck Rights', 'Other', 'Objection to agency fee usage');

-- ============================================================================
-- PARTICIPANTS TABLE
-- ============================================================================

DROP TABLE IF EXISTS nlrb_participants CASCADE;
CREATE TABLE nlrb_participants (
    participant_id SERIAL PRIMARY KEY,
    case_number VARCHAR(20) REFERENCES nlrb_cases(case_number),
    participant_name TEXT,
    role_type VARCHAR(50),           -- Petitioner, Employer, Charging Party, etc.
    subtype VARCHAR(200),            -- Union, Employer, Individual, Legal Representative
    address TEXT,
    city VARCHAR(100),
    state VARCHAR(30),
    zip VARCHAR(50),
    phone VARCHAR(50),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_nlrb_part_case ON nlrb_participants(case_number);
CREATE INDEX idx_nlrb_part_name ON nlrb_participants(participant_name);
CREATE INDEX idx_nlrb_part_type ON nlrb_participants(role_type, subtype);
CREATE INDEX idx_nlrb_part_state ON nlrb_participants(state);

-- ============================================================================
-- ELECTIONS TABLE
-- ============================================================================

DROP TABLE IF EXISTS nlrb_elections CASCADE;
CREATE TABLE nlrb_elections (
    election_id INTEGER PRIMARY KEY,
    case_number VARCHAR(20) REFERENCES nlrb_cases(case_number),
    voting_unit_id INTEGER,
    election_date DATE,
    tally_type VARCHAR(50),
    ballot_type VARCHAR(50),
    unit_size INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_nlrb_elect_case ON nlrb_elections(case_number);
CREATE INDEX idx_nlrb_elect_date ON nlrb_elections(election_date);

-- ============================================================================
-- TALLIES TABLE
-- ============================================================================

DROP TABLE IF EXISTS nlrb_tallies CASCADE;
CREATE TABLE nlrb_tallies (
    tally_id SERIAL PRIMARY KEY,
    election_id INTEGER REFERENCES nlrb_elections(election_id),
    option TEXT,                     -- Union name or "Against"
    votes INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_nlrb_tally_elect ON nlrb_tallies(election_id);

-- ============================================================================
-- ELECTION RESULTS TABLE
-- ============================================================================

DROP TABLE IF EXISTS nlrb_election_results CASCADE;
CREATE TABLE nlrb_election_results (
    election_id INTEGER PRIMARY KEY REFERENCES nlrb_elections(election_id),
    total_ballots_counted INTEGER,
    void_ballots INTEGER,
    challenged_ballots INTEGER,
    challenges_determinative VARCHAR(10),
    runoff_required VARCHAR(10),
    union_certified TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ============================================================================
-- ALLEGATIONS TABLE (ULP cases)
-- ============================================================================

DROP TABLE IF EXISTS nlrb_allegations CASCADE;
CREATE TABLE nlrb_allegations (
    allegation_id SERIAL PRIMARY KEY,
    case_number VARCHAR(20) REFERENCES nlrb_cases(case_number),
    allegation_text TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_nlrb_alleg_case ON nlrb_allegations(case_number);

-- ============================================================================
-- VOTING UNITS TABLE
-- ============================================================================

DROP TABLE IF EXISTS nlrb_voting_units CASCADE;
CREATE TABLE nlrb_voting_units (
    voting_unit_id INTEGER PRIMARY KEY,
    case_number VARCHAR(20) REFERENCES nlrb_cases(case_number),
    unit_id VARCHAR(50),
    description TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_nlrb_vu_case ON nlrb_voting_units(case_number);

-- ============================================================================
-- CROSSWALK TABLES - Link NLRB to OLMS/F7
-- ============================================================================

-- Union name matching table
DROP TABLE IF EXISTS nlrb_union_xref CASCADE;
CREATE TABLE nlrb_union_xref (
    xref_id SERIAL PRIMARY KEY,
    nlrb_name VARCHAR(500) NOT NULL,
    nlrb_name_normalized VARCHAR(500),
    olms_f_num INTEGER,                      -- Links to lm_data.f_num
    olms_union_name VARCHAR(500),
    aff_abbr VARCHAR(50),
    match_confidence NUMERIC(5,2),           -- 0-100
    match_method VARCHAR(50),                -- 'exact', 'affiliation+local', 'fuzzy', 'manual'
    verified BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_nlrb_ux_nlrb ON nlrb_union_xref(nlrb_name);
CREATE INDEX idx_nlrb_ux_fnum ON nlrb_union_xref(olms_f_num);
CREATE INDEX idx_nlrb_ux_aff ON nlrb_union_xref(aff_abbr);
CREATE UNIQUE INDEX idx_nlrb_ux_unique ON nlrb_union_xref(nlrb_name, olms_f_num);

-- Employer name matching table
DROP TABLE IF EXISTS nlrb_employer_xref CASCADE;
CREATE TABLE nlrb_employer_xref (
    xref_id SERIAL PRIMARY KEY,
    nlrb_name VARCHAR(500) NOT NULL,
    nlrb_city VARCHAR(100),
    nlrb_state CHAR(2),
    f7_employer_id VARCHAR(20),              -- Links to f7_employers.employer_id
    f7_employer_name VARCHAR(500),
    match_confidence NUMERIC(5,2),
    match_method VARCHAR(50),
    verified BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_nlrb_ex_nlrb ON nlrb_employer_xref(nlrb_name);
CREATE INDEX idx_nlrb_ex_f7 ON nlrb_employer_xref(f7_employer_id);
CREATE INDEX idx_nlrb_ex_state ON nlrb_employer_xref(nlrb_state);

-- ============================================================================
-- ANALYTICAL VIEWS
-- ============================================================================

-- Election outcomes with union details
CREATE OR REPLACE VIEW v_nlrb_election_outcomes AS
SELECT 
    e.election_id,
    e.case_number,
    c.case_name,
    c.city,
    c.state,
    e.election_date,
    e.unit_size,
    er.total_ballots_counted,
    er.union_certified,
    CASE WHEN er.union_certified IS NOT NULL AND er.union_certified != '' 
         THEN 'Won' ELSE 'Lost' END as outcome,
    ux.olms_f_num,
    ux.aff_abbr
FROM nlrb_elections e
JOIN nlrb_cases c ON e.case_number = c.case_number
LEFT JOIN nlrb_election_results er ON e.election_id = er.election_id
LEFT JOIN nlrb_participants p ON e.case_number = p.case_number 
    AND p.role_type = 'Petitioner' AND p.subtype = 'Union'
LEFT JOIN nlrb_union_xref ux ON p.participant_name = ux.nlrb_name;

-- Union win rates
CREATE OR REPLACE VIEW v_nlrb_union_win_rates AS
SELECT 
    ux.olms_f_num,
    ux.aff_abbr,
    MAX(ux.olms_union_name) as union_name,
    COUNT(*) as total_elections,
    SUM(CASE WHEN er.union_certified IS NOT NULL AND er.union_certified != '' 
             THEN 1 ELSE 0 END) as wins,
    ROUND(100.0 * SUM(CASE WHEN er.union_certified IS NOT NULL AND er.union_certified != '' 
                           THEN 1 ELSE 0 END) / NULLIF(COUNT(*), 0), 1) as win_rate,
    SUM(e.unit_size) as total_workers_in_elections,
    MIN(e.election_date) as first_election,
    MAX(e.election_date) as last_election
FROM nlrb_elections e
JOIN nlrb_cases c ON e.case_number = c.case_number
LEFT JOIN nlrb_election_results er ON e.election_id = er.election_id
LEFT JOIN nlrb_participants p ON e.case_number = p.case_number 
    AND p.role_type = 'Petitioner' AND p.subtype = 'Union'
LEFT JOIN nlrb_union_xref ux ON p.participant_name = ux.nlrb_name
WHERE ux.olms_f_num IS NOT NULL
GROUP BY ux.olms_f_num, ux.aff_abbr;

-- ULP case counts by employer
CREATE OR REPLACE VIEW v_nlrb_employer_ulp_summary AS
SELECT 
    ex.f7_employer_id,
    ex.f7_employer_name,
    ex.nlrb_state as state,
    COUNT(DISTINCT c.case_number) as total_cases,
    SUM(CASE WHEN c.case_type = 'CA' THEN 1 ELSE 0 END) as employer_ulp_cases,
    SUM(CASE WHEN c.case_type = 'CB' THEN 1 ELSE 0 END) as union_ulp_cases,
    MIN(c.date_filed) as first_case,
    MAX(c.date_filed) as last_case
FROM nlrb_cases c
JOIN nlrb_participants p ON c.case_number = p.case_number
    AND p.subtype = 'Employer'
LEFT JOIN nlrb_employer_xref ex ON p.participant_name = ex.nlrb_name 
    AND p.state = ex.nlrb_state
WHERE c.case_type IN ('CA', 'CB', 'CC', 'CD', 'CE', 'CG', 'CP')
GROUP BY ex.f7_employer_id, ex.f7_employer_name, ex.nlrb_state;

-- Case summary by year and type
CREATE OR REPLACE VIEW v_nlrb_case_trends AS
SELECT 
    EXTRACT(YEAR FROM c.date_filed)::INTEGER as year,
    c.case_type,
    ct.type_name,
    ct.category,
    COUNT(*) as case_count
FROM nlrb_cases c
LEFT JOIN nlrb_case_types ct ON c.case_type = ct.case_type
WHERE c.date_filed IS NOT NULL
GROUP BY EXTRACT(YEAR FROM c.date_filed), c.case_type, ct.type_name, ct.category
ORDER BY year DESC, case_count DESC;

-- ============================================================================
-- COMMENTS
-- ============================================================================

COMMENT ON TABLE nlrb_cases IS 'NLRB case filings (RC, CA, CB, etc.) - 498K records';
COMMENT ON TABLE nlrb_participants IS 'Case participants (unions, employers, individuals) - 1.9M records';
COMMENT ON TABLE nlrb_elections IS 'Union representation elections - 33K records';
COMMENT ON TABLE nlrb_union_xref IS 'Crosswalk linking NLRB union names to OLMS file numbers';
COMMENT ON TABLE nlrb_employer_xref IS 'Crosswalk linking NLRB employers to F-7 employer records';
