-- ============================================================================
-- VR Integration Views - Checkpoint 5A
-- Core views for VR data with employer/union linkages
-- Run: psql -U postgres -d olms_multiyear -f vr_views_5a.sql
-- ============================================================================

-- ============================================================================
-- VIEW: Full VR cases with all linkages
-- ============================================================================
DROP VIEW IF EXISTS v_vr_cases_full CASCADE;
CREATE OR REPLACE VIEW v_vr_cases_full AS
SELECT 
    vr.id,
    vr.vr_case_number,
    vr.region,
    nr.region_name,
    vr.unit_city,
    vr.unit_state,
    vr.date_vr_request_received,
    vr.date_voluntary_recognition,
    vr.date_vr_notice_sent,
    EXTRACT(YEAR FROM vr.date_vr_request_received)::int as vr_year,
    
    -- Employer info
    vr.employer_name,
    vr.employer_name_normalized,
    vr.matched_employer_id,
    vr.employer_match_confidence,
    vr.employer_match_method,
    f7.employer_name as f7_employer_name,
    f7.city as f7_city,
    f7.state as f7_state,
    f7.naics as f7_naics,
    f7.latitude as f7_latitude,
    f7.longitude as f7_longitude,
    
    -- Union info
    vr.union_name,
    vr.union_name_normalized,
    vr.extracted_affiliation,
    vr.extracted_local_number,
    vr.matched_union_fnum,
    vr.union_match_confidence,
    vr.union_match_method,
    um.union_name as olms_union_name,
    um.aff_abbr as olms_aff_abbr,
    um.members as olms_members,
    um.city as olms_city,
    um.state as olms_state,
    
    -- Unit info
    vr.unit_description,
    vr.num_employees,
    
    -- Linkages
    vr.r_case_number,
    vr.notes
    
FROM nlrb_voluntary_recognition vr
LEFT JOIN nlrb_regions nr ON vr.region = nr.region_number
LEFT JOIN f7_employers_deduped f7 ON vr.matched_employer_id = f7.employer_id
LEFT JOIN unions_master um ON vr.matched_union_fnum = um.f_num;

COMMENT ON VIEW v_vr_cases_full IS 'Complete VR cases with employer and union linkages';

-- ============================================================================
-- VIEW: VR cases for map display (with coordinates)
-- ============================================================================
DROP VIEW IF EXISTS v_vr_map_data CASCADE;
CREATE OR REPLACE VIEW v_vr_map_data AS
SELECT 
    vr.id,
    vr.vr_case_number,
    vr.employer_name_normalized as employer_name,
    vr.unit_city as city,
    vr.unit_state as state,
    vr.extracted_affiliation as affiliation,
    vr.num_employees,
    vr.date_vr_request_received,
    EXTRACT(YEAR FROM vr.date_vr_request_received)::int as year,
    -- Use F7 coordinates if matched, otherwise NULL
    f7.latitude,
    f7.longitude,
    CASE WHEN f7.latitude IS NOT NULL THEN 'geocoded' ELSE 'no_coords' END as geo_status
FROM nlrb_voluntary_recognition vr
LEFT JOIN f7_employers_deduped f7 ON vr.matched_employer_id = f7.employer_id;

COMMENT ON VIEW v_vr_map_data IS 'VR cases with coordinates for map display';

-- ============================================================================
-- VIEW: VR by year with match rates
-- ============================================================================
DROP VIEW IF EXISTS v_vr_yearly_summary CASCADE;
CREATE OR REPLACE VIEW v_vr_yearly_summary AS
SELECT 
    EXTRACT(YEAR FROM date_vr_request_received)::int as year,
    COUNT(*) as total_cases,
    SUM(COALESCE(num_employees, 0)) as total_employees,
    AVG(num_employees)::int as avg_unit_size,
    COUNT(DISTINCT unit_state) as states_active,
    COUNT(matched_employer_id) as employers_matched,
    COUNT(matched_union_fnum) as unions_matched,
    ROUND(100.0 * COUNT(matched_employer_id) / COUNT(*), 1) as employer_match_pct,
    ROUND(100.0 * COUNT(matched_union_fnum) / COUNT(*), 1) as union_match_pct,
    COUNT(r_case_number) as petitions_filed
FROM nlrb_voluntary_recognition
WHERE date_vr_request_received IS NOT NULL
GROUP BY EXTRACT(YEAR FROM date_vr_request_received)
ORDER BY year;

COMMENT ON VIEW v_vr_yearly_summary IS 'VR cases by year with match rates';

-- ============================================================================
-- VIEW: VR by state with match rates
-- ============================================================================
DROP VIEW IF EXISTS v_vr_state_summary CASCADE;
CREATE OR REPLACE VIEW v_vr_state_summary AS
SELECT 
    unit_state as state,
    COUNT(*) as total_cases,
    SUM(COALESCE(num_employees, 0)) as total_employees,
    AVG(num_employees)::int as avg_unit_size,
    COUNT(matched_employer_id) as employers_matched,
    COUNT(matched_union_fnum) as unions_matched,
    ROUND(100.0 * COUNT(matched_employer_id) / COUNT(*), 1) as employer_match_pct,
    ROUND(100.0 * COUNT(matched_union_fnum) / COUNT(*), 1) as union_match_pct,
    MIN(date_vr_request_received) as earliest_case,
    MAX(date_vr_request_received) as latest_case
FROM nlrb_voluntary_recognition
WHERE unit_state IS NOT NULL AND LENGTH(unit_state) = 2
GROUP BY unit_state
ORDER BY COUNT(*) DESC;

COMMENT ON VIEW v_vr_state_summary IS 'VR cases by state with match rates';

-- ============================================================================
-- VIEW: VR by affiliation with OLMS linkage
-- ============================================================================
DROP VIEW IF EXISTS v_vr_affiliation_summary CASCADE;
CREATE OR REPLACE VIEW v_vr_affiliation_summary AS
SELECT 
    vr.extracted_affiliation as affiliation,
    COUNT(*) as total_cases,
    SUM(COALESCE(vr.num_employees, 0)) as total_employees,
    AVG(vr.num_employees)::int as avg_unit_size,
    COUNT(vr.matched_union_fnum) as unions_matched,
    ROUND(100.0 * COUNT(vr.matched_union_fnum) / COUNT(*), 1) as match_pct,
    COUNT(DISTINCT vr.matched_union_fnum) as unique_locals,
    MIN(vr.date_vr_request_received) as earliest_case,
    MAX(vr.date_vr_request_received) as latest_case,
    -- OLMS totals for matched unions
    SUM(DISTINCT um.members) as olms_total_members
FROM nlrb_voluntary_recognition vr
LEFT JOIN unions_master um ON vr.matched_union_fnum = um.f_num
GROUP BY vr.extracted_affiliation
ORDER BY COUNT(*) DESC;

COMMENT ON VIEW v_vr_affiliation_summary IS 'VR cases by union affiliation with OLMS data';

-- ============================================================================
-- VIEW: New employers (in VR but not matched to F7)
-- ============================================================================
DROP VIEW IF EXISTS v_vr_new_employers CASCADE;
CREATE OR REPLACE VIEW v_vr_new_employers AS
SELECT 
    vr.id,
    vr.vr_case_number,
    vr.employer_name_normalized as employer_name,
    vr.unit_city as city,
    vr.unit_state as state,
    vr.extracted_affiliation as union_affiliation,
    vr.union_name_normalized as union_name,
    vr.num_employees,
    vr.date_vr_request_received,
    vr.date_voluntary_recognition,
    EXTRACT(YEAR FROM vr.date_vr_request_received)::int as year
FROM nlrb_voluntary_recognition vr
WHERE vr.matched_employer_id IS NULL
ORDER BY vr.num_employees DESC NULLS LAST, vr.date_vr_request_received DESC;

COMMENT ON VIEW v_vr_new_employers IS 'Employers with VR but not yet in F7 data (new organizing)';

-- Verify views created
SELECT 'Checkpoint 5A Views Created' as status;
SELECT table_name as view_name
FROM information_schema.views 
WHERE table_schema = 'public' 
  AND (table_name LIKE 'v_vr_%')
ORDER BY table_name;
