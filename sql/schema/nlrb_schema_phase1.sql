-- ============================================================================
-- NLRB Integration Schema - Phase 1 Complete
-- Run: psql -U postgres -d olms_multiyear -f nlrb_schema_phase1.sql
-- Created: January 25, 2026
-- ============================================================================

-- ============================================================================
-- CHECKPOINT 1.1: CORE TABLES
-- ============================================================================

-- Cases master table (derived from case_number patterns)
DROP TABLE IF EXISTS nlrb_cases CASCADE;
CREATE TABLE nlrb_cases (
    case_number VARCHAR(20) PRIMARY KEY,
    region INTEGER,                        -- Extracted from case_number (01-34)
    case_type VARCHAR(10),                 -- RC, RM, RD, CA, CB, CD, etc.
    case_year INTEGER,                     -- Extracted year
    case_seq INTEGER,                      -- Sequential number
    earliest_date DATE,
    latest_date DATE,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Case type reference
DROP TABLE IF EXISTS nlrb_case_types CASCADE;
CREATE TABLE nlrb_case_types (
    case_type VARCHAR(10) PRIMARY KEY,
    case_category VARCHAR(50),             -- 'representation', 'unfair_labor_practice', 'other'
    description TEXT
);

INSERT INTO nlrb_case_types VALUES
('RC', 'representation', 'Petition for certification filed by union'),
('RM', 'representation', 'Petition for certification filed by employer'),
('RD', 'representation', 'Petition for decertification filed by employees'),
('CA', 'unfair_labor_practice', 'Charge against employer (Section 8a)'),
('CB', 'unfair_labor_practice', 'Charge against union (Section 8b)'),
('CD', 'unfair_labor_practice', 'Charge against union (Section 8b)(4)(D)'),
('CE', 'unfair_labor_practice', 'Charge against union/employer (Section 8e)'),
('CG', 'unfair_labor_practice', 'Charge against union (Section 8g)'),
('CP', 'unfair_labor_practice', 'Charge against union (Section 8b)(7)'),
('UC', 'other', 'Unit clarification'),
('UD', 'other', 'Unit deauthorization'),
('AC', 'other', 'Amendment of certification'),
('WH', 'other', 'Wage-Hour case');

-- Participants table
DROP TABLE IF EXISTS nlrb_participants CASCADE;
CREATE TABLE nlrb_participants (
    id SERIAL PRIMARY KEY,
    case_number VARCHAR(20) NOT NULL,
    participant_name TEXT,
    participant_type VARCHAR(50),          -- Petitioner, Employer, Charging Party, etc.
    participant_subtype VARCHAR(50),       -- Union, Employer, Individual
    address TEXT,
    address_1 TEXT,
    address_2 TEXT,
    city VARCHAR(100),
    state VARCHAR(10),
    zip VARCHAR(20),
    phone_number VARCHAR(50),
    created_at TIMESTAMP,
    -- Matching fields (populated later)
    matched_olms_fnum VARCHAR(20),         -- Link to OLMS union
    matched_employer_id INTEGER,           -- Link to F-7 employer
    match_confidence DECIMAL(3,2),
    match_method VARCHAR(50)
);

CREATE INDEX idx_nlrb_part_case ON nlrb_participants(case_number);
CREATE INDEX idx_nlrb_part_name ON nlrb_participants(participant_name);
CREATE INDEX idx_nlrb_part_type ON nlrb_participants(participant_type, participant_subtype);
CREATE INDEX idx_nlrb_part_state ON nlrb_participants(state);
CREATE INDEX idx_nlrb_part_olms ON nlrb_participants(matched_olms_fnum);
CREATE INDEX idx_nlrb_part_employer ON nlrb_participants(matched_employer_id);

COMMENT ON TABLE nlrb_participants IS 'NLRB case participants - employers, unions, individuals';

-- ============================================================================
-- CHECKPOINT 1.2: ELECTION TABLES
-- ============================================================================

-- Elections table
DROP TABLE IF EXISTS nlrb_elections CASCADE;
CREATE TABLE nlrb_elections (
    id SERIAL PRIMARY KEY,
    case_number VARCHAR(20) NOT NULL,
    election_type VARCHAR(50),
    election_date DATE,
    ballot_type VARCHAR(50),
    eligible_voters INTEGER,
    void_ballots INTEGER,
    challenges INTEGER,
    runoff_required BOOLEAN,
    created_at TIMESTAMP,
    -- Derived fields
    total_votes INTEGER,
    union_won BOOLEAN,
    vote_margin INTEGER
);

CREATE INDEX idx_nlrb_elec_case ON nlrb_elections(case_number);
CREATE INDEX idx_nlrb_elec_date ON nlrb_elections(election_date);
CREATE INDEX idx_nlrb_elec_won ON nlrb_elections(union_won);

-- Tallies (vote counts per union/choice)
DROP TABLE IF EXISTS nlrb_tallies CASCADE;
CREATE TABLE nlrb_tallies (
    id SERIAL PRIMARY KEY,
    case_number VARCHAR(20) NOT NULL,
    labor_org_name TEXT,                   -- Union name on ballot
    labor_org_number VARCHAR(50),          -- If available
    votes_for INTEGER,
    tally_type VARCHAR(50),                -- 'For', 'Against', 'No Union', etc.
    is_winner BOOLEAN,
    created_at TIMESTAMP,
    -- Matching fields
    matched_olms_fnum VARCHAR(20)
);

CREATE INDEX idx_nlrb_tally_case ON nlrb_tallies(case_number);
CREATE INDEX idx_nlrb_tally_union ON nlrb_tallies(labor_org_name);
CREATE INDEX idx_nlrb_tally_olms ON nlrb_tallies(matched_olms_fnum);

-- Bargaining units sought
DROP TABLE IF EXISTS nlrb_sought_units CASCADE;
CREATE TABLE nlrb_sought_units (
    id SERIAL PRIMARY KEY,
    case_number VARCHAR(20) NOT NULL,
    unit_description TEXT,
    included_classifications TEXT,
    excluded_classifications TEXT,
    num_employees INTEGER,
    created_at TIMESTAMP
);

CREATE INDEX idx_nlrb_sought_case ON nlrb_sought_units(case_number);

-- Voting units (actual units for elections)
DROP TABLE IF EXISTS nlrb_voting_units CASCADE;
CREATE TABLE nlrb_voting_units (
    id SERIAL PRIMARY KEY,
    case_number VARCHAR(20) NOT NULL,
    unit_description TEXT,
    included_job_classifications TEXT,
    excluded_job_classifications TEXT,
    unit_size INTEGER,
    created_at TIMESTAMP
);

CREATE INDEX idx_nlrb_voting_case ON nlrb_voting_units(case_number);

COMMENT ON TABLE nlrb_elections IS 'NLRB election records with outcomes';
COMMENT ON TABLE nlrb_tallies IS 'Vote counts by union/choice in NLRB elections';

-- ============================================================================
-- CHECKPOINT 1.3: ULP & DOCKET TABLES
-- ============================================================================

-- Allegations (Unfair Labor Practices)
DROP TABLE IF EXISTS nlrb_allegations CASCADE;
CREATE TABLE nlrb_allegations (
    id SERIAL PRIMARY KEY,
    case_number VARCHAR(20) NOT NULL,
    allegation_number INTEGER,
    section VARCHAR(50),                   -- NLRA Section (e.g., "8(a)(1)", "8(b)(3)")
    allegation_text TEXT,
    allegation_status VARCHAR(100),
    created_at TIMESTAMP
);

CREATE INDEX idx_nlrb_alleg_case ON nlrb_allegations(case_number);
CREATE INDEX idx_nlrb_alleg_section ON nlrb_allegations(section);

-- Filings
DROP TABLE IF EXISTS nlrb_filings CASCADE;
CREATE TABLE nlrb_filings (
    id SERIAL PRIMARY KEY,
    case_number VARCHAR(20) NOT NULL,
    filing_type VARCHAR(100),
    filing_date DATE,
    filed_by VARCHAR(200),
    filing_description TEXT,
    created_at TIMESTAMP
);

CREATE INDEX idx_nlrb_filing_case ON nlrb_filings(case_number);
CREATE INDEX idx_nlrb_filing_date ON nlrb_filings(filing_date);
CREATE INDEX idx_nlrb_filing_type ON nlrb_filings(filing_type);

-- Docket entries (case timeline)
DROP TABLE IF EXISTS nlrb_docket CASCADE;
CREATE TABLE nlrb_docket (
    id SERIAL PRIMARY KEY,
    case_number VARCHAR(20) NOT NULL,
    docket_entry TEXT,
    docket_date DATE,
    document_id VARCHAR(50),
    created_at TIMESTAMP
);

CREATE INDEX idx_nlrb_docket_case ON nlrb_docket(case_number);
CREATE INDEX idx_nlrb_docket_date ON nlrb_docket(docket_date);

COMMENT ON TABLE nlrb_allegations IS 'Unfair labor practice allegations by NLRA section';
COMMENT ON TABLE nlrb_filings IS 'Case filings with dates and filers';
COMMENT ON TABLE nlrb_docket IS 'Chronological case activity/timeline';

-- ============================================================================
-- CHECKPOINT 1.4: INTEGRATION VIEWS
-- ============================================================================

-- View: Election outcomes with union/employer matching
CREATE OR REPLACE VIEW v_nlrb_elections_full AS
SELECT 
    e.id as election_id,
    e.case_number,
    c.region,
    c.case_type,
    e.election_date,
    e.election_type,
    e.eligible_voters,
    e.total_votes,
    e.union_won,
    e.vote_margin,
    -- Employer info from participants
    emp.participant_name as employer_name,
    emp.city as employer_city,
    emp.state as employer_state,
    emp.matched_employer_id,
    -- Union info from tallies
    t.labor_org_name as union_name,
    t.votes_for as union_votes,
    t.matched_olms_fnum,
    -- F-7 employer link
    f7.employer_name as f7_employer_name,
    f7.latitude,
    f7.longitude,
    f7.naics,
    -- OLMS union link
    um.union_name as olms_union_name,
    um.aff_abbr,
    um.members as olms_members
FROM nlrb_elections e
JOIN nlrb_cases c ON e.case_number = c.case_number
LEFT JOIN nlrb_participants emp ON e.case_number = emp.case_number 
    AND emp.participant_type = 'Employer'
LEFT JOIN nlrb_tallies t ON e.case_number = t.case_number 
    AND t.is_winner = true
LEFT JOIN f7_employers_deduped f7 ON emp.matched_employer_id = f7.employer_id
LEFT JOIN unions_master um ON t.matched_olms_fnum = um.f_num;

-- View: ULP cases with parties
CREATE OR REPLACE VIEW v_nlrb_ulp_cases AS
SELECT 
    c.case_number,
    c.region,
    c.case_type,
    ct.description as case_type_desc,
    -- Charging party (who filed)
    cp.participant_name as charging_party,
    cp.participant_subtype as charging_party_type,
    -- Charged party (accused)
    chg.participant_name as charged_party,
    chg.participant_subtype as charged_party_type,
    chg.matched_olms_fnum as charged_union_fnum,
    chg.matched_employer_id as charged_employer_id,
    -- Allegations
    a.section as nlra_section,
    a.allegation_text,
    a.allegation_status,
    -- Dates
    c.earliest_date,
    c.latest_date
FROM nlrb_cases c
JOIN nlrb_case_types ct ON c.case_type = ct.case_type
LEFT JOIN nlrb_participants cp ON c.case_number = cp.case_number 
    AND cp.participant_type = 'Charging Party'
LEFT JOIN nlrb_participants chg ON c.case_number = chg.case_number 
    AND chg.participant_type = 'Charged Party'
LEFT JOIN nlrb_allegations a ON c.case_number = a.case_number
WHERE ct.case_category = 'unfair_labor_practice';

-- View: Union election win rates
CREATE OR REPLACE VIEW v_nlrb_union_win_rates AS
SELECT 
    COALESCE(t.matched_olms_fnum, 'UNMATCHED') as f_num,
    um.union_name,
    um.aff_abbr,
    COUNT(*) as total_elections,
    SUM(CASE WHEN e.union_won THEN 1 ELSE 0 END) as wins,
    SUM(CASE WHEN NOT e.union_won THEN 1 ELSE 0 END) as losses,
    ROUND(100.0 * SUM(CASE WHEN e.union_won THEN 1 ELSE 0 END) / 
        NULLIF(COUNT(*), 0), 1) as win_rate_pct,
    SUM(e.eligible_voters) as total_eligible_voters,
    MIN(e.election_date) as earliest_election,
    MAX(e.election_date) as latest_election
FROM nlrb_elections e
LEFT JOIN nlrb_tallies t ON e.case_number = t.case_number 
    AND t.tally_type = 'For'
LEFT JOIN unions_master um ON t.matched_olms_fnum = um.f_num
GROUP BY COALESCE(t.matched_olms_fnum, 'UNMATCHED'), um.union_name, um.aff_abbr
ORDER BY COUNT(*) DESC;

-- View: Employer NLRB activity
CREATE OR REPLACE VIEW v_nlrb_employer_activity AS
SELECT 
    p.matched_employer_id,
    f7.employer_name,
    f7.city,
    f7.state,
    f7.naics,
    f7.latitude,
    f7.longitude,
    -- Election stats
    COUNT(DISTINCT CASE WHEN ct.case_category = 'representation' 
        THEN p.case_number END) as election_cases,
    -- ULP stats  
    COUNT(DISTINCT CASE WHEN ct.case_category = 'unfair_labor_practice' 
        THEN p.case_number END) as ulp_cases,
    -- Win/loss
    SUM(CASE WHEN e.union_won THEN 1 ELSE 0 END) as union_wins,
    SUM(CASE WHEN e.union_won = false THEN 1 ELSE 0 END) as union_losses,
    -- Date range
    MIN(c.earliest_date) as first_case_date,
    MAX(c.latest_date) as last_case_date
FROM nlrb_participants p
JOIN nlrb_cases c ON p.case_number = c.case_number
JOIN nlrb_case_types ct ON c.case_type = ct.case_type
LEFT JOIN nlrb_elections e ON p.case_number = e.case_number
LEFT JOIN f7_employers_deduped f7 ON p.matched_employer_id = f7.employer_id
WHERE p.participant_type = 'Employer' 
  AND p.matched_employer_id IS NOT NULL
GROUP BY p.matched_employer_id, f7.employer_name, f7.city, f7.state, 
         f7.naics, f7.latitude, f7.longitude
ORDER BY COUNT(DISTINCT p.case_number) DESC;

-- View: Geographic election density
CREATE OR REPLACE VIEW v_nlrb_elections_by_state AS
SELECT 
    p.state,
    COUNT(DISTINCT e.case_number) as total_elections,
    SUM(CASE WHEN e.union_won THEN 1 ELSE 0 END) as union_wins,
    ROUND(100.0 * SUM(CASE WHEN e.union_won THEN 1 ELSE 0 END) / 
        NULLIF(COUNT(DISTINCT e.case_number), 0), 1) as win_rate_pct,
    SUM(e.eligible_voters) as total_eligible_voters,
    MIN(e.election_date) as earliest_election,
    MAX(e.election_date) as latest_election
FROM nlrb_elections e
JOIN nlrb_participants p ON e.case_number = p.case_number 
    AND p.participant_type = 'Employer'
WHERE p.state IS NOT NULL AND LENGTH(p.state) = 2
GROUP BY p.state
ORDER BY COUNT(DISTINCT e.case_number) DESC;

COMMENT ON VIEW v_nlrb_elections_full IS 'Complete election records with employer/union linkages';
COMMENT ON VIEW v_nlrb_ulp_cases IS 'Unfair labor practice cases with parties and allegations';
COMMENT ON VIEW v_nlrb_union_win_rates IS 'Election win rates by union';
COMMENT ON VIEW v_nlrb_employer_activity IS 'All NLRB activity by employer';
COMMENT ON VIEW v_nlrb_elections_by_state IS 'Election statistics by state';

-- ============================================================================
-- VERIFICATION QUERIES
-- ============================================================================

-- List all created tables
SELECT table_name, 
       (SELECT COUNT(*) FROM information_schema.columns WHERE table_name = t.table_name) as columns
FROM information_schema.tables t
WHERE table_schema = 'public' AND table_name LIKE 'nlrb_%'
ORDER BY table_name;

-- List all created views
SELECT table_name as view_name
FROM information_schema.views 
WHERE table_schema = 'public' AND table_name LIKE 'v_nlrb_%'
ORDER BY table_name;

SELECT 'PHASE 1 COMPLETE - Schema created successfully' as status;
SELECT 'Next: Run Phase 2 export scripts to extract data from SQLite' as next_step;
