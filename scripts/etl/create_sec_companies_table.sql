-- SEC EDGAR Companies Table (Phase 4 Block A, ETL scope)
CREATE EXTENSION IF NOT EXISTS pg_trgm;

CREATE TABLE IF NOT EXISTS sec_companies (
    cik TEXT PRIMARY KEY,
    company_name TEXT NOT NULL,
    ein TEXT,
    state TEXT,
    sic_code TEXT,
    naics_code TEXT,
    business_address TEXT,
    mailing_address TEXT,
    source_file TEXT,
    last_filing_date DATE,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_sec_companies_ein
    ON sec_companies(ein) WHERE ein IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_sec_companies_name
    ON sec_companies(company_name);

CREATE INDEX IF NOT EXISTS idx_sec_companies_state
    ON sec_companies(state) WHERE state IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_sec_companies_sic
    ON sec_companies(sic_code) WHERE sic_code IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_sec_companies_name_trgm
    ON sec_companies USING gin (company_name gin_trgm_ops);

COMMENT ON TABLE sec_companies IS 'SEC EDGAR public companies (~300K+ entities from submissions bulk data)';
COMMENT ON COLUMN sec_companies.cik IS 'Central Index Key (SEC entity identifier)';
COMMENT ON COLUMN sec_companies.ein IS 'Employer Identification Number from SEC submissions metadata when present';
