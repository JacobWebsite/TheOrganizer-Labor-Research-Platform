-- IRS Business Master File Table
CREATE TABLE IF NOT EXISTS irs_bmf (
    ein TEXT PRIMARY KEY,
    org_name TEXT NOT NULL,
    state TEXT,
    city TEXT,
    zip_code TEXT,

    -- Tax classification fields
    ntee_code TEXT,                    -- National Taxonomy (J40 = labor unions)
    subsection_code TEXT,              -- 03=501(c)(3), 05=501(c)(5) labor orgs
    ruling_date DATE,                  -- When exempt status granted
    deductibility_code TEXT,           -- Contribution deductibility
    foundation_code TEXT,              -- Private foundation classification

    -- Optional financial fields
    income_amount NUMERIC,
    asset_amount NUMERIC,

    -- Metadata
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Indexes for future matching (Claude will use these)
CREATE INDEX IF NOT EXISTS idx_bmf_ein ON irs_bmf(ein);
CREATE INDEX IF NOT EXISTS idx_bmf_state ON irs_bmf(state) WHERE state IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_bmf_ntee ON irs_bmf(ntee_code) WHERE ntee_code IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_bmf_subsection ON irs_bmf(subsection_code) WHERE subsection_code IS NOT NULL;

-- Full-text search on organization name
CREATE INDEX IF NOT EXISTS idx_bmf_name_trgm
    ON irs_bmf USING gin(org_name gin_trgm_ops);

COMMENT ON TABLE irs_bmf IS 'IRS Business Master File - all tax-exempt orgs (~1.8M)';
COMMENT ON COLUMN irs_bmf.ein IS 'Employer Identification Number (tax ID)';
COMMENT ON COLUMN irs_bmf.ntee_code IS 'National Taxonomy code (J40=labor unions, J=employment-related)';
COMMENT ON COLUMN irs_bmf.subsection_code IS 'Tax code section (05=501(c)(5) labor organizations)';
