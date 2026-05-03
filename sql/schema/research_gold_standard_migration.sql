-- ============================================================================
-- RESEARCH GOLD STANDARD MIGRATION
-- Created: 2026-03-16
-- Purpose: Section-level review for gold standard research reports.
--          Adds review tracking per section (approve/reject/correct) and
--          gold standard designation to research_runs.
-- ============================================================================

-- 1. Add gold standard columns to research_runs
ALTER TABLE research_runs
    ADD COLUMN IF NOT EXISTS is_gold_standard BOOLEAN DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS gold_standard_at TIMESTAMP;

CREATE INDEX IF NOT EXISTS idx_research_runs_gold ON research_runs(is_gold_standard)
    WHERE is_gold_standard = TRUE;

-- 2. Section-level review table
CREATE TABLE IF NOT EXISTS research_section_reviews (
    id              SERIAL PRIMARY KEY,
    run_id          INTEGER NOT NULL REFERENCES research_runs(id) ON DELETE CASCADE,
    section_name    VARCHAR(50) NOT NULL,           -- identity, labor, workforce, etc.
    review_action   VARCHAR(20) NOT NULL
                    CHECK (review_action IN ('approve', 'reject', 'correct')),
    reviewer_notes  TEXT,                           -- correction instructions or comments
    corrected_content JSONB,                        -- optional: corrected section data
    reviewer        VARCHAR(100) DEFAULT 'admin',
    reviewed_at     TIMESTAMP DEFAULT NOW(),

    UNIQUE(run_id, section_name)
);

CREATE INDEX IF NOT EXISTS idx_section_reviews_run ON research_section_reviews(run_id);
