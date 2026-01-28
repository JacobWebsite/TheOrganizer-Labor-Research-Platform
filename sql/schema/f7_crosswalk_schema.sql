-- F-7 and Crosswalk Schema for PostgreSQL
-- Database: olms_multiyear
-- Run with: psql -U postgres -d olms_multiyear -f f7_crosswalk_schema.sql

-- ============================================================
-- F-7 EMPLOYER TABLES
-- ============================================================

DROP TABLE IF EXISTS f7_union_employer_relations CASCADE;
DROP TABLE IF EXISTS f7_employers CASCADE;

CREATE TABLE f7_employers (
    employer_id TEXT PRIMARY KEY,
    employer_name TEXT,
    city TEXT,
    state TEXT,
    street TEXT,
    zip TEXT,
    latest_notice_date TEXT,
    latest_unit_size INTEGER,
    latest_union_fnum INTEGER,
    latest_union_name TEXT,
    naics TEXT,
    healthcare_related INTEGER,
    filing_count INTEGER,
    potentially_defunct INTEGER,
    latitude REAL,
    longitude REAL,
    geocode_status TEXT,
    data_quality_flag TEXT
);

CREATE TABLE f7_union_employer_relations (
    id SERIAL PRIMARY KEY,
    employer_id TEXT REFERENCES f7_employers(employer_id),
    union_file_number INTEGER,
    bargaining_unit_size INTEGER,
    notice_date TEXT
);

-- ============================================================
-- CROSSWALK TABLES
-- ============================================================

DROP TABLE IF EXISTS crosswalk_unions_master CASCADE;
DROP TABLE IF EXISTS crosswalk_sector_lookup CASCADE;
DROP TABLE IF EXISTS crosswalk_affiliation_sector_map CASCADE;
DROP TABLE IF EXISTS crosswalk_f7_only_unions CASCADE;

CREATE TABLE crosswalk_sector_lookup (
    sector_code TEXT PRIMARY KEY,
    sector_name TEXT,
    description TEXT,
    f7_expected INTEGER,
    governing_law TEXT
);

CREATE TABLE crosswalk_affiliation_sector_map (
    aff_abbr TEXT PRIMARY KEY,
    aff_name TEXT,
    sector_code TEXT,
    notes TEXT
);

CREATE TABLE crosswalk_unions_master (
    id SERIAL PRIMARY KEY,
    union_name TEXT,
    aff_abbr TEXT,
    f_num REAL,
    members TEXT,
    yr_covered REAL,
    city TEXT,
    state TEXT,
    source_year INTEGER,
    sector TEXT,
    f7_union_name TEXT,
    f7_employer_count REAL,
    f7_total_workers REAL,
    f7_states TEXT,
    has_f7_employers INTEGER,
    match_status TEXT
);

CREATE TABLE crosswalk_f7_only_unions (
    f_num INTEGER PRIMARY KEY,
    union_name TEXT,
    employer_count INTEGER,
    total_workers INTEGER,
    likely_reason TEXT
);

-- ============================================================
-- INDEXES
-- ============================================================

CREATE INDEX idx_f7_employers_state ON f7_employers(state);
CREATE INDEX idx_f7_employers_city ON f7_employers(city);
CREATE INDEX idx_f7_employers_naics ON f7_employers(naics);
CREATE INDEX idx_f7_employers_union_fnum ON f7_employers(latest_union_fnum);
CREATE INDEX idx_f7_employers_geocode ON f7_employers(geocode_status);
CREATE INDEX idx_f7_employers_latlon ON f7_employers(latitude, longitude);

CREATE INDEX idx_f7_relations_employer ON f7_union_employer_relations(employer_id);
CREATE INDEX idx_f7_relations_union ON f7_union_employer_relations(union_file_number);

CREATE INDEX idx_crosswalk_unions_fnum ON crosswalk_unions_master(f_num);
CREATE INDEX idx_crosswalk_unions_aff ON crosswalk_unions_master(aff_abbr);
CREATE INDEX idx_crosswalk_unions_sector ON crosswalk_unions_master(sector);
CREATE INDEX idx_crosswalk_unions_has_f7 ON crosswalk_unions_master(has_f7_employers);

-- Verify creation
SELECT 'Tables created successfully' as status;
