-- ============================================================================
-- BLS Union Density Data - Schema Creation
-- Run this in PostgreSQL olms_multiyear database
-- ============================================================================

-- Drop existing tables if rebuilding
DROP TABLE IF EXISTS bls_union_data CASCADE;
DROP TABLE IF EXISTS bls_union_series CASCADE;
DROP TABLE IF EXISTS bls_fips_lookup CASCADE;
DROP TABLE IF EXISTS bls_industry_lookup CASCADE;
DROP TABLE IF EXISTS bls_occupation_lookup CASCADE;

-- ============================================================================
-- LOOKUP TABLES
-- ============================================================================

-- State/Region FIPS codes
CREATE TABLE bls_fips_lookup (
    fips_code VARCHAR(5) PRIMARY KEY,
    fips_name VARCHAR(100) NOT NULL,
    fips_type VARCHAR(20) DEFAULT 'state'
);

-- Industry codes (BLS supersector categories)
CREATE TABLE bls_industry_lookup (
    indy_code VARCHAR(5) PRIMARY KEY,
    indy_name VARCHAR(200) NOT NULL
);

-- Occupation codes
CREATE TABLE bls_occupation_lookup (
    occ_code VARCHAR(5) PRIMARY KEY,
    occ_name VARCHAR(200) NOT NULL
);

-- ============================================================================
-- SERIES DEFINITIONS TABLE
-- ============================================================================

CREATE TABLE bls_union_series (
    series_id VARCHAR(20) PRIMARY KEY,
    lfst_code VARCHAR(5),
    fips_code VARCHAR(5),
    series_title TEXT,
    tdata_code VARCHAR(5),
    pcts_code VARCHAR(5),
    earn_code VARCHAR(5),
    class_code VARCHAR(5),
    unin_code VARCHAR(5),
    indy_code VARCHAR(5),
    occupation_code VARCHAR(5),
    education_code VARCHAR(5),
    ages_code VARCHAR(5),
    race_code VARCHAR(5),
    orig_code VARCHAR(5),
    sexs_code VARCHAR(5),
    seasonal CHAR(1),
    footnote_codes VARCHAR(50),
    begin_year INTEGER,
    begin_period VARCHAR(5),
    end_year INTEGER,
    end_period VARCHAR(5),
    
    -- Derived classification fields (populated after load)
    data_type VARCHAR(20),
    geo_level VARCHAR(20),
    worker_class VARCHAR(50)
);

-- ============================================================================
-- TIME SERIES DATA TABLE
-- ============================================================================

CREATE TABLE bls_union_data (
    series_id VARCHAR(20) NOT NULL,
    year INTEGER NOT NULL,
    period VARCHAR(5) NOT NULL,
    value NUMERIC(15,2),
    footnote_codes VARCHAR(50),
    PRIMARY KEY (series_id, year, period)
);

-- ============================================================================
-- INDEXES
-- ============================================================================

CREATE INDEX idx_bls_series_fips ON bls_union_series(fips_code);
CREATE INDEX idx_bls_series_indy ON bls_union_series(indy_code);
CREATE INDEX idx_bls_series_occ ON bls_union_series(occupation_code);
CREATE INDEX idx_bls_series_unin ON bls_union_series(unin_code);
CREATE INDEX idx_bls_series_class ON bls_union_series(class_code);
CREATE INDEX idx_bls_series_data_type ON bls_union_series(data_type);

CREATE INDEX idx_bls_data_year ON bls_union_data(year);
CREATE INDEX idx_bls_data_series ON bls_union_data(series_id);

-- ============================================================================
-- COMMENTS
-- ============================================================================

COMMENT ON TABLE bls_fips_lookup IS 'BLS FIPS state/region codes';
COMMENT ON TABLE bls_industry_lookup IS 'BLS industry supersector codes';
COMMENT ON TABLE bls_occupation_lookup IS 'BLS occupation category codes';
COMMENT ON TABLE bls_union_series IS 'BLS union density series definitions (1,234 series)';
COMMENT ON TABLE bls_union_data IS 'BLS union density time series values (31,193 records, 1983-2024)';

COMMENT ON COLUMN bls_union_series.unin_code IS '0=all, 1=members, 2=represented, 3=non-union';
COMMENT ON COLUMN bls_union_series.class_code IS '16=all workers, 17=private, 03=government';
COMMENT ON COLUMN bls_union_series.data_type IS 'Derived: count, percent, or earnings';
COMMENT ON COLUMN bls_union_series.geo_level IS 'Derived: national or state';

-- ============================================================================
-- Verify creation
-- ============================================================================
SELECT 'Schema created successfully' as status;
SELECT table_name, 
       (SELECT COUNT(*) FROM information_schema.columns WHERE table_name = t.table_name) as columns
FROM information_schema.tables t
WHERE table_schema = 'public' 
  AND table_name LIKE 'bls_%'
ORDER BY table_name;
