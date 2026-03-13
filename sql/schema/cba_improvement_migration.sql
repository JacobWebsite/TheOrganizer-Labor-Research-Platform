-- ============================================================================
-- CBA Improvement Migration
-- Adds context columns, file hashing, processing status tracking
-- Idempotent: safe to re-run.
-- Created: 2026-03-07
-- NOTE: Must DROP VIEW first then CREATE (column order changes break CREATE OR REPLACE)
-- ============================================================================

-- ============================================================================
-- 1. Context columns on cba_provisions (Phase 1.4)
-- ============================================================================

ALTER TABLE cba_provisions ADD COLUMN IF NOT EXISTS context_before TEXT;
ALTER TABLE cba_provisions ADD COLUMN IF NOT EXISTS context_after TEXT;

-- ============================================================================
-- 2. File hash + processing status on cba_documents (Phase 2)
-- ============================================================================

ALTER TABLE cba_documents ADD COLUMN IF NOT EXISTS file_hash VARCHAR(64);
ALTER TABLE cba_documents ADD COLUMN IF NOT EXISTS processing_status VARCHAR(20) DEFAULT 'pending';
ALTER TABLE cba_documents ADD COLUMN IF NOT EXISTS processing_error TEXT;

CREATE INDEX IF NOT EXISTS idx_cba_docs_file_hash ON cba_documents(file_hash);

-- ============================================================================
-- 3. Update search view to include context columns
--    Must DROP first because column order changed (context_before/after added)
-- ============================================================================

DROP VIEW IF EXISTS v_cba_provision_search;
CREATE VIEW v_cba_provision_search AS
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
    p.context_before,
    p.context_after,
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
