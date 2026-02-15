"""
Create F-7 Employer Schema in PostgreSQL
Adds tables for F-7 employer data, sector classification, and union match status
"""

import psycopg2
import os

from db_config import get_connection
DB_CONFIG = {
    'host': os.environ.get('DB_HOST', 'localhost'),
    'port': int(os.environ.get('DB_PORT', '5432')),
    'database': os.environ.get('DB_NAME', 'olms_multiyear'),
    'user': os.environ.get('DB_USER', 'postgres'),
    'password': os.environ.get('DB_PASSWORD', ''),
}

SCHEMA_SQL = """
-- ============================================================================
-- F-7 Employer Data Integration Schema
-- ============================================================================

-- Drop existing objects if they exist
DROP VIEW IF EXISTS v_match_status_summary CASCADE;
DROP VIEW IF EXISTS v_sector_summary CASCADE;
DROP VIEW IF EXISTS v_lm_with_f7_summary CASCADE;
DROP VIEW IF EXISTS v_union_f7_summary CASCADE;
DROP VIEW IF EXISTS v_f7_employers_active CASCADE;
DROP VIEW IF EXISTS v_f7_employers_geocoded CASCADE;
DROP VIEW IF EXISTS v_f7_employers_full CASCADE;
DROP VIEW IF EXISTS v_f7_state_summary CASCADE;
DROP TABLE IF EXISTS f7_employers CASCADE;
DROP TABLE IF EXISTS unions_master CASCADE;
DROP TABLE IF EXISTS union_match_status CASCADE;
DROP TABLE IF EXISTS union_sector CASCADE;

-- ============================================================================
-- LOOKUP TABLES
-- ============================================================================

-- Sector classification lookup
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
-- ============================================================================

CREATE TABLE f7_employers (
    employer_id VARCHAR(20) PRIMARY KEY,
    employer_name VARCHAR(500) NOT NULL,
    street VARCHAR(500),
    city VARCHAR(100),
    state CHAR(2),
    zip VARCHAR(20),
    latest_notice_date DATE,
    latest_unit_size INTEGER,
    latest_union_fnum INTEGER,                  -- Integer for F-7 data
    latest_union_name VARCHAR(500),
    naics VARCHAR(10),
    healthcare_related BOOLEAN DEFAULT FALSE,
    filing_count INTEGER DEFAULT 1,
    potentially_defunct BOOLEAN DEFAULT FALSE,
    data_quality_flag VARCHAR(50),
    latitude NUMERIC(11,8),
    longitude NUMERIC(11,8),
    geocode_status VARCHAR(20),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Indexes
CREATE INDEX idx_f7_employers_state ON f7_employers(state);
CREATE INDEX idx_f7_employers_city_state ON f7_employers(city, state);
CREATE INDEX idx_f7_employers_union_fnum ON f7_employers(latest_union_fnum);
CREATE INDEX idx_f7_employers_naics ON f7_employers(naics);
CREATE INDEX idx_f7_employers_geocoded ON f7_employers(latitude, longitude) WHERE latitude IS NOT NULL;
CREATE INDEX idx_f7_employers_defunct ON f7_employers(potentially_defunct);
CREATE INDEX idx_f7_employers_healthcare ON f7_employers(healthcare_related) WHERE healthcare_related = TRUE;
CREATE INDEX idx_f7_employers_notice_date ON f7_employers(latest_notice_date);

-- ============================================================================
-- UNION MASTER TABLE
-- Uses VARCHAR for f_num to match lm_data table
-- ============================================================================

CREATE TABLE unions_master (
    f_num VARCHAR(20) PRIMARY KEY,              -- VARCHAR to match lm_data.f_num
    union_name VARCHAR(500),
    aff_abbr VARCHAR(50),
    members INTEGER,
    yr_covered INTEGER,
    city VARCHAR(100),
    state CHAR(2),
    source_year INTEGER,
    sector VARCHAR(30) REFERENCES union_sector(sector_code),
    f7_union_name VARCHAR(500),
    f7_employer_count INTEGER DEFAULT 0,
    f7_total_workers INTEGER DEFAULT 0,
    f7_states TEXT,
    has_f7_employers BOOLEAN DEFAULT FALSE,
    match_status VARCHAR(30) REFERENCES union_match_status(status_code),
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
-- Note: Cast f_num for join between integer (f7) and varchar (unions_master)
CREATE OR REPLACE VIEW v_f7_employers_full AS
SELECT 
    e.*,
    um.aff_abbr,
    um.members as union_members,
    um.sector,
    us.sector_name,
    us.governing_law
FROM f7_employers e
LEFT JOIN unions_master um ON e.latest_union_fnum::text = um.f_num
LEFT JOIN union_sector us ON um.sector = us.sector_code;

-- View: Geocoded employers only
CREATE OR REPLACE VIEW v_f7_employers_geocoded AS
SELECT * FROM f7_employers
WHERE latitude IS NOT NULL AND longitude IS NOT NULL;

-- View: Active employers
CREATE OR REPLACE VIEW v_f7_employers_active AS
SELECT * FROM f7_employers
WHERE potentially_defunct = FALSE;

-- View: Union summary with F-7 counts
CREATE OR REPLACE VIEW v_union_f7_summary AS
SELECT 
    um.f_num, um.union_name, um.aff_abbr, um.members, um.sector,
    us.sector_name, um.match_status, ms.status_name,
    um.f7_employer_count, um.f7_total_workers, um.f7_states, um.has_f7_employers
FROM unions_master um
LEFT JOIN union_sector us ON um.sector = us.sector_code
LEFT JOIN union_match_status ms ON um.match_status = ms.status_code;

-- View: State-level F-7 summary
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

-- View: Sector summary
CREATE OR REPLACE VIEW v_sector_summary AS
SELECT 
    us.sector_code, us.sector_name, us.governing_law, us.f7_expected,
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
    ms.status_code, ms.status_name, ms.description,
    COUNT(um.f_num) as union_count,
    SUM(um.members) as total_members,
    SUM(um.f7_employer_count) as employer_count
FROM union_match_status ms
LEFT JOIN unions_master um ON ms.status_code = um.match_status
GROUP BY ms.status_code, ms.status_name, ms.description
ORDER BY union_count DESC;

-- View: LM data with F-7 summary (using VARCHAR f_num)
CREATE OR REPLACE VIEW v_lm_with_f7_summary AS
SELECT 
    l.rpt_id, l.f_num, l.union_name, l.aff_abbr, l.state, l.city,
    l.members, l.ttl_assets, l.ttl_receipts, l.yr_covered,
    um.sector, um.match_status, um.f7_employer_count, um.f7_total_workers, um.has_f7_employers
FROM lm_data l
LEFT JOIN unions_master um ON l.f_num = um.f_num;

-- ============================================================================
-- COMMENTS
-- ============================================================================

COMMENT ON TABLE f7_employers IS 'Deduplicated F-7 bargaining notice employers with geocoding (150K+ records)';
COMMENT ON TABLE unions_master IS 'Master union list combining LM filings with F-7 linkage and sector classification';
COMMENT ON TABLE union_sector IS 'Lookup table for union sector classifications (PRIVATE, FEDERAL, RLA, etc.)';
COMMENT ON TABLE union_match_status IS 'Lookup table explaining why unions may/may not have F-7 employer records';
"""

def main():
    print("Connecting to PostgreSQL...")
    conn = get_connection()
    conn.autocommit = True
    cursor = conn.cursor()
    
    print("Creating F-7 schema...")
    cursor.execute(SCHEMA_SQL)
    
    # Verify tables created
    cursor.execute("""
        SELECT table_name 
        FROM information_schema.tables 
        WHERE table_schema = 'public' 
        AND table_name IN ('f7_employers', 'unions_master', 'union_sector', 'union_match_status')
        ORDER BY table_name
    """)
    tables = cursor.fetchall()
    
    print("\n✅ Tables created:")
    for t in tables:
        print(f"   - {t[0]}")
    
    # Verify lookup data
    cursor.execute("SELECT COUNT(*) FROM union_sector")
    sector_count = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM union_match_status")
    status_count = cursor.fetchone()[0]
    
    print(f"\n✅ Lookup data loaded:")
    print(f"   - union_sector: {sector_count} records")
    print(f"   - union_match_status: {status_count} records")
    
    # List views
    cursor.execute("""
        SELECT table_name 
        FROM information_schema.views 
        WHERE table_schema = 'public' 
        AND (table_name LIKE 'v_f7%' OR table_name LIKE 'v_union%' OR table_name LIKE 'v_sector%' OR table_name LIKE 'v_match%' OR table_name LIKE 'v_lm_with%')
        ORDER BY table_name
    """)
    views = cursor.fetchall()
    
    print(f"\n✅ Views created:")
    for v in views:
        print(f"   - {v[0]}")
    
    cursor.close()
    conn.close()
    
    print("\n🎉 Schema creation complete!")
    print("\nNext step: Run the data loading script to populate f7_employers and unions_master")

if __name__ == "__main__":
    main()
