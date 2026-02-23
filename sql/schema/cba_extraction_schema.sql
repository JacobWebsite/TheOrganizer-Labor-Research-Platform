-- ============================================================================
-- Labor Relations Platform - CBA Extraction & Search Schema
-- Supports Collective Bargaining Agreement (CBA) storage, AI extraction,
-- and source-grounded provision tracking.
-- Created: February 22, 2026
-- ============================================================================

-- ============================================================================
-- 1. CBA DOCUMENTS
-- Tracks the physical files and their provenance
-- ============================================================================

DROP TABLE IF EXISTS cba_documents CASCADE;
CREATE TABLE cba_documents (
    cba_id SERIAL PRIMARY KEY,
    employer_id TEXT REFERENCES f7_employers_deduped(employer_id), -- Link to platform employer
    f_num VARCHAR(20),                                               -- Link to unions_master
    
    -- Metadata from Source
    employer_name_raw VARCHAR(255),
    union_name_raw VARCHAR(255),
    local_number VARCHAR(50),
    
    -- File Info
    source_name VARCHAR(100),         -- e.g., 'SeeThroughNY', 'NJ PERC', 'OLMS'
    source_url TEXT,                  -- Original URL of the document
    file_path TEXT,                   -- Local storage path
    file_format VARCHAR(10),          -- 'PDF', 'DOCX', 'HTML'
    is_scanned BOOLEAN DEFAULT FALSE, -- Result of document assessment
    page_count INTEGER,
    
    -- Contract Dates
    effective_date DATE,
    expiration_date DATE,
    is_current BOOLEAN DEFAULT TRUE,
    
    -- Assessment & Processing
    structure_quality VARCHAR(20),    -- 'well-organized', 'wall-of-text', 'scanned'
    ocr_status VARCHAR(20),           -- 'pending', 'completed', 'failed', 'not_needed'
    extraction_status VARCHAR(20),    -- 'pending', 'in_progress', 'completed', 'failed'
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_cba_docs_fnum ON cba_documents(f_num);
CREATE INDEX idx_cba_docs_employer ON cba_documents(employer_id);
CREATE INDEX idx_cba_docs_source ON cba_documents(source_name);
CREATE INDEX idx_cba_docs_dates ON cba_documents(effective_date, expiration_date);

-- ============================================================================
-- 2. CBA PROVISIONS (Extraction Classes)
-- Stores individual clauses extracted via LangExtract
-- ============================================================================

DROP TABLE IF EXISTS cba_provisions CASCADE;
CREATE TABLE cba_provisions (
    provision_id SERIAL PRIMARY KEY,
    cba_id INTEGER REFERENCES cba_documents(cba_id) ON DELETE CASCADE,
    
    -- Classification (The Taxonomy)
    category VARCHAR(50),             -- 'ECONOMIC', 'WORKPLACE', 'UNION_RIGHTS', etc.
    provision_class VARCHAR(100),     -- 'wage_base_rate', 'grievance_steps', 'just_cause'
    
    -- Extracted Content
    provision_text TEXT,              -- The actual extracted language
    summary TEXT,                     -- AI-generated summary/interpretation
    
    -- Source Grounding (LangExtract Data)
    page_start INTEGER,
    page_end INTEGER,
    char_start INTEGER,
    char_end INTEGER,
    
    -- Legal Force (Arold et al. Methodology)
    modal_verb VARCHAR(20),           -- 'shall', 'may', 'will', 'must', 'shall not'
    legal_weight NUMERIC(3,2),        -- 0.00 (permissive) to 1.00 (mandatory)
    
    -- Metadata
    confidence_score NUMERIC(3,2),
    model_version VARCHAR(50),
    is_human_verified BOOLEAN DEFAULT FALSE,
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_cba_provisions_cba_id ON cba_provisions(cba_id);
CREATE INDEX idx_cba_provisions_class ON cba_provisions(provision_class);
CREATE INDEX idx_cba_provisions_category ON cba_provisions(category);
CREATE INDEX idx_cba_provisions_modal ON cba_provisions(modal_verb);

-- Full-text search index for provision text
CREATE INDEX idx_cba_provisions_fts ON cba_provisions USING GIN (to_tsvector('english', provision_text));

-- ============================================================================
-- 3. WAGE SCHEDULES (Specialized Extraction)
-- Specifically for structured wage tables
-- ============================================================================

DROP TABLE IF EXISTS cba_wage_schedules CASCADE;
CREATE TABLE cba_wage_schedules (
    wage_id SERIAL PRIMARY KEY,
    cba_id INTEGER REFERENCES cba_documents(cba_id) ON DELETE CASCADE,
    provision_id INTEGER REFERENCES cba_provisions(provision_id),
    
    job_classification VARCHAR(255),
    step_name VARCHAR(50),            -- 'Step 1', 'Start', 'Year 5', etc.
    hourly_rate NUMERIC(10,2),
    annual_salary NUMERIC(12,2),
    
    effective_date DATE,
    longevity_years INTEGER,          -- Years of service required for this rate
    
    is_entry_level BOOLEAN DEFAULT FALSE,
    is_max_rate BOOLEAN DEFAULT FALSE,
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_cba_wages_cba_id ON cba_wage_schedules(cba_id);
CREATE INDEX idx_cba_wages_job ON cba_wage_schedules(job_classification);

-- ============================================================================
-- 4. SEARCH VIEWS
-- ============================================================================

CREATE OR REPLACE VIEW v_cba_provision_search AS
SELECT 
    p.provision_id,
    d.cba_id,
    d.employer_id,
    COALESCE(e.employer_name, d.employer_name_raw) as employer_name,
    COALESCE(um.union_name, d.union_name_raw) as union_name,
    um.aff_abbr,
    d.source_name,
    p.category,
    p.provision_class,
    p.provision_text,
    p.modal_verb,
    p.page_start,
    d.effective_date,
    d.expiration_date,
    e.state,
    e.city,
    LEFT(e.naics, 2) as naics_2digit
FROM cba_provisions p
JOIN cba_documents d ON p.cba_id = d.cba_id
LEFT JOIN f7_employers_deduped e ON d.employer_id = e.employer_id
LEFT JOIN unions_master um ON d.f_num = um.f_num;

-- ============================================================================
-- COMMENTS
-- ============================================================================

COMMENT ON TABLE cba_documents IS 'Primary metadata for CBA contract files and their processing status';
COMMENT ON TABLE cba_provisions IS 'Individual contract provisions extracted with source grounding offsets';
COMMENT ON TABLE cba_wage_schedules IS 'Structured wage data parsed from complex contract tables';
COMMENT ON COLUMN cba_provisions.modal_verb IS 'The primary modal verb determining legal force (shall, may, etc.)';
COMMENT ON COLUMN cba_provisions.char_start IS 'LangExtract character offset start for source grounding';
