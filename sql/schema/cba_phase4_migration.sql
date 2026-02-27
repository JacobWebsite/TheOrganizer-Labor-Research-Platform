-- ============================================================================
-- CBA Phase 4 Migration: Rule-Based Extraction Support
-- Adds cba_categories, cba_reviews tables and new columns to existing tables.
-- Idempotent: safe to re-run.
-- Created: 2026-02-25
-- ============================================================================

-- ============================================================================
-- 1. cba_categories — master list of valid topic buckets (14 rows)
-- ============================================================================

CREATE TABLE IF NOT EXISTS cba_categories (
    category_id   SERIAL PRIMARY KEY,
    category_name VARCHAR(50) UNIQUE NOT NULL,
    display_name  VARCHAR(100) NOT NULL,
    subcategories TEXT[],
    sort_order    INTEGER NOT NULL DEFAULT 0,
    description   TEXT
);

-- ============================================================================
-- 2. cba_reviews — human corrections log
-- ============================================================================

CREATE TABLE IF NOT EXISTS cba_reviews (
    review_id          SERIAL PRIMARY KEY,
    provision_id       INTEGER REFERENCES cba_provisions(provision_id) ON DELETE SET NULL,
    original_category  VARCHAR(50),
    corrected_category VARCHAR(50),
    original_class     VARCHAR(100),
    corrected_class    VARCHAR(100),
    reviewer           VARCHAR(100),
    notes              TEXT,
    review_action      VARCHAR(20) CHECK (review_action IN ('recategorize', 'delete', 'split', 'approve')),
    created_at         TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_cba_reviews_provision ON cba_reviews(provision_id);

-- ============================================================================
-- 3. Column additions to cba_documents
-- ============================================================================

ALTER TABLE cba_documents ADD COLUMN IF NOT EXISTS full_text TEXT;
ALTER TABLE cba_documents ADD COLUMN IF NOT EXISTS extraction_method VARCHAR(20) DEFAULT 'ai';
ALTER TABLE cba_documents ADD COLUMN IF NOT EXISTS structure_json JSONB;

-- ============================================================================
-- 4. Column additions to cba_provisions
-- ============================================================================

ALTER TABLE cba_provisions ADD COLUMN IF NOT EXISTS article_reference VARCHAR(200);
ALTER TABLE cba_provisions ADD COLUMN IF NOT EXISTS extraction_method VARCHAR(20) DEFAULT 'ai';
ALTER TABLE cba_provisions ADD COLUMN IF NOT EXISTS rule_name VARCHAR(100);

-- ============================================================================
-- 5. Mark existing AI-extracted data
-- ============================================================================

UPDATE cba_documents SET extraction_method = 'ai' WHERE extraction_method IS NULL;
UPDATE cba_provisions SET extraction_method = 'ai' WHERE extraction_method IS NULL;

-- ============================================================================
-- 6. Seed cba_categories with 14 rows (idempotent via ON CONFLICT)
-- ============================================================================

INSERT INTO cba_categories (category_name, display_name, subcategories, sort_order, description)
VALUES
    ('healthcare', 'Healthcare', ARRAY['Premiums', 'Coverage', 'Dental', 'Vision', 'Mental Health', 'Prescription', 'Opt-Out'], 1,
     'Medical, dental, vision, and prescription coverage including employee contributions and opt-out payments.'),
    ('wages', 'Wages', ARRAY['Base Rate', 'COLA', 'Differentials', 'Overtime', 'Premium Pay', 'Lump Sum'], 2,
     'Base wage rates, salary schedules, step increases, shift differentials, and premium pay.'),
    ('grievance', 'Grievance & Arbitration', ARRAY['Steps', 'Arbitration', 'Timelines', 'Remedies'], 3,
     'Grievance steps, timelines, arbitration rights, and remedies.'),
    ('leave', 'Leave', ARRAY['Vacation', 'Sick', 'Personal', 'Bereavement', 'Parental', 'Union Leave', 'FMLA'], 4,
     'Vacation, sick leave, personal days, holidays, parental leave, and FMLA provisions.'),
    ('pension', 'Pension & Retirement', ARRAY['Defined Benefit', '401k', 'Employer Match', 'Vesting'], 5,
     'Pension, annuity, retirement savings, employer contributions, and vesting schedules.'),
    ('seniority', 'Seniority', ARRAY['Layoff Order', 'Bidding', 'Recall', 'Promotion'], 6,
     'Definition and application of seniority for promotions, layoffs, recalls, and scheduling.'),
    ('management_rights', 'Management Rights', NULL, 7,
     'Reserved management authority, operational discretion, and limits on bargaining obligations.'),
    ('union_security', 'Union Security', ARRAY['Dues Checkoff', 'Agency Shop', 'Steward Rights', 'Union Access'], 8,
     'Dues deduction, agency fees, membership requirements, steward rights, and union access.'),
    ('scheduling', 'Scheduling & Overtime', ARRAY['Hours', 'Shifts', 'Overtime Rights', 'Call-In', 'Posting'], 9,
     'Regular hours, shifts, overtime eligibility, call-in guarantees, and schedule posting.'),
    ('job_security', 'Job Security & Discipline', ARRAY['Just Cause', 'Progressive Discipline', 'Probation', 'Subcontracting'], 10,
     'Just-cause standards, progressive discipline, layoff/recall procedures, subcontracting limits.'),
    ('childcare', 'Childcare', NULL, 11,
     'Childcare benefits, dependent care assistance, and related provisions.'),
    ('training', 'Training', ARRAY['Apprenticeship', 'Tuition', 'Certification'], 12,
     'Training programs, apprenticeship, tuition reimbursement, and certification requirements.'),
    ('technology', 'Technology', ARRAY['Surveillance', 'AI', 'Remote Work', 'Electronic Monitoring'], 13,
     'Technology provisions including surveillance, AI, remote work, and electronic monitoring.'),
    ('other', 'Other', NULL, 14,
     'Catch-all for provisions that do not fit other categories: duration, successorship, separability, etc.')
ON CONFLICT (category_name) DO NOTHING;
