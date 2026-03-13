-- ============================================================================
-- CBA Cross-Contract Comparison Migration
-- Adds section_id FK to provisions, extracted_values JSONB, and updated view.
-- Idempotent: safe to re-run.
-- Created: 2026-03-12
-- ============================================================================

-- ============================================================================
-- 1. section_id FK on cba_provisions (link provision to its structural section)
-- ============================================================================

ALTER TABLE cba_provisions ADD COLUMN IF NOT EXISTS section_id INTEGER
  REFERENCES cba_sections(section_id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS idx_cba_provisions_section ON cba_provisions(section_id);

-- ============================================================================
-- 2. extracted_values JSONB on cba_provisions (dollar amounts, percentages, etc.)
-- ============================================================================

ALTER TABLE cba_provisions ADD COLUMN IF NOT EXISTS extracted_values JSONB DEFAULT '{}'::jsonb;

CREATE INDEX IF NOT EXISTS idx_cba_provisions_values_gin ON cba_provisions USING gin(extracted_values);

-- ============================================================================
-- 3. Update cba_categories subcategories to match expanded provision_classes
-- ============================================================================

UPDATE cba_categories SET subcategories = ARRAY['employer_premium', 'employee_contribution', 'coverage_tiers', 'hmo_ppo', 'copay_deductible', 'dental_vision', 'prescription_drug', 'opt_out_waiver', 'retiree_health', 'health_fund', 'waiting_period']
WHERE category_name = 'healthcare';

UPDATE cba_categories SET subcategories = ARRAY['base_wage_rate', 'wage_increase', 'step_increase', 'cola', 'lump_sum', 'shift_differential', 'hazard_pay', 'lead_pay', 'bilingual_pay', 'wage_schedule_table']
WHERE category_name = 'wages';

UPDATE cba_categories SET subcategories = ARRAY['grievance_definition', 'grievance_steps', 'time_limits', 'arbitration_right', 'arbitrator_selection', 'arbitrator_authority', 'grievance_filing', 'union_right_grieve']
WHERE category_name = 'grievance';

UPDATE cba_categories SET subcategories = ARRAY['vacation_accrual', 'vacation_days', 'sick_leave', 'personal_days', 'holiday_list', 'holiday_pay', 'bereavement', 'fmla', 'parental_leave', 'union_leave', 'jury_duty', 'military_leave']
WHERE category_name = 'leave';

UPDATE cba_categories SET subcategories = ARRAY['pension_contribution', 'contribution_rate', 'vesting', 'retirement_eligibility', 'defined_benefit', '401k_match', 'pension_fund']
WHERE category_name = 'pension';

UPDATE cba_categories SET subcategories = ARRAY['seniority_definition', 'seniority_list', 'seniority_accrual', 'seniority_bidding', 'seniority_promotion', 'super_seniority', 'probationary_seniority']
WHERE category_name = 'seniority';

UPDATE cba_categories SET subcategories = ARRAY['management_rights_clause', 'management_enumerated', 'operational_discretion', 'not_limited_to']
WHERE category_name = 'management_rights';

UPDATE cba_categories SET subcategories = ARRAY['dues_deduction', 'agency_shop', 'membership_requirement', 'steward_rights', 'bulletin_board', 'union_access', 'bargaining_unit_info']
WHERE category_name = 'union_security';

UPDATE cba_categories SET subcategories = ARRAY['regular_hours', 'work_week', 'overtime_rate', 'overtime_after', 'overtime_distribution', 'mandatory_overtime', 'call_in_pay', 'schedule_posting', 'shift_assignment', 'rest_break', 'pyramiding']
WHERE category_name = 'scheduling';

UPDATE cba_categories SET subcategories = ARRAY['just_cause_exact', 'proper_cause', 'good_cause_discipline', 'progressive_discipline', 'discipline_steps', 'weingarten', 'layoff_order', 'recall_rights', 'bumping', 'subcontracting', 'probationary_period', 'personnel_file']
WHERE category_name = 'job_security';

UPDATE cba_categories SET subcategories = ARRAY['childcare_benefit', 'dcfsa', 'backup_childcare']
WHERE category_name = 'childcare';

UPDATE cba_categories SET subcategories = ARRAY['training_program', 'tuition_reimbursement', 'certification_pay', 'apprentice_ratio', 'training_time_paid']
WHERE category_name = 'training';

UPDATE cba_categories SET subcategories = ARRAY['electronic_monitoring', 'remote_work', 'technology_change', 'data_privacy', 'ai_provisions']
WHERE category_name = 'technology';

UPDATE cba_categories SET subcategories = ARRAY['no_strike', 'duration', 'successorship', 'separability', 'zipper_clause', 'safety_health', 'uniforms_tools']
WHERE category_name = 'other';

-- ============================================================================
-- 4. Updated search view with section breadcrumbs
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
    LEFT(e.naics, 2) as naics_2digit,
    s.section_num,
    s.section_title,
    s.section_level,
    ps.section_num AS parent_section_num,
    ps.section_title AS parent_section_title
FROM cba_provisions p
JOIN cba_documents d ON p.cba_id = d.cba_id
LEFT JOIN f7_employers_deduped e ON d.employer_id = e.employer_id
LEFT JOIN unions_master um ON d.f_num = um.f_num
LEFT JOIN cba_sections s ON p.section_id = s.section_id
LEFT JOIN cba_sections ps ON s.parent_section_id = ps.section_id;
