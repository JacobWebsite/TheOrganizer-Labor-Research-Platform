-- UnionStats and Industry Density Schema for PostgreSQL
-- Database: olms_multiyear
-- Run with: psql -U postgres -d olms_multiyear -f unionstats_schema.sql

-- ============================================================
-- STATE UNION DENSITY (1983-2024)
-- ============================================================

DROP TABLE IF EXISTS unionstats_state CASCADE;

CREATE TABLE unionstats_state (
    id SERIAL PRIMARY KEY,
    year INTEGER NOT NULL,
    state_census_code INTEGER,
    state TEXT NOT NULL,
    sector TEXT NOT NULL,  -- Total, Public, Private, Priv. Manufacturing, Priv. Construction
    observations INTEGER,
    employment_thousands REAL,
    members_thousands REAL,
    covered_thousands REAL,
    pct_members REAL,
    pct_covered REAL
);

-- ============================================================
-- INDUSTRY UNION DENSITY (by CIC code)
-- ============================================================

DROP TABLE IF EXISTS unionstats_industry CASCADE;

CREATE TABLE unionstats_industry (
    id SERIAL PRIMARY KEY,
    year INTEGER NOT NULL,
    cic_code INTEGER,  -- Census Industry Code (null for sector headers)
    industry TEXT NOT NULL,
    observations INTEGER,
    employment_thousands REAL,
    members_thousands REAL,
    covered_thousands REAL,
    pct_members REAL,
    pct_covered REAL,
    is_sector_header BOOLEAN DEFAULT FALSE  -- True for rows like "MINING", "UTILITIES"
);

-- ============================================================
-- INDEXES
-- ============================================================

CREATE INDEX idx_state_year ON unionstats_state(year);
CREATE INDEX idx_state_state ON unionstats_state(state);
CREATE INDEX idx_state_sector ON unionstats_state(sector);
CREATE INDEX idx_state_year_state ON unionstats_state(year, state);

CREATE INDEX idx_industry_year ON unionstats_industry(year);
CREATE INDEX idx_industry_cic ON unionstats_industry(cic_code);
CREATE INDEX idx_industry_year_cic ON unionstats_industry(year, cic_code);

-- Verify creation
SELECT 'UnionStats tables created successfully' as status;
