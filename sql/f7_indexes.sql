-- ============================================================================
-- F-7 Integration Indexes
-- ============================================================================

-- F7 Employers indexes
CREATE INDEX idx_f7_employers_state ON f7_employers(state);
CREATE INDEX idx_f7_employers_city ON f7_employers(city);
CREATE INDEX idx_f7_employers_union_fnum ON f7_employers(latest_union_fnum);
CREATE INDEX idx_f7_employers_naics ON f7_employers(naics);
CREATE INDEX idx_f7_employers_geocoded ON f7_employers(geocode_status);
CREATE INDEX idx_f7_employers_defunct ON f7_employers(potentially_defunct);
CREATE INDEX idx_f7_employers_coords ON f7_employers(latitude, longitude) 
    WHERE latitude IS NOT NULL AND longitude IS NOT NULL;

-- Unions master indexes
CREATE INDEX idx_unions_master_sector ON unions_master(sector);
CREATE INDEX idx_unions_master_status ON unions_master(match_status);
CREATE INDEX idx_unions_master_state ON unions_master(state);
CREATE INDEX idx_unions_master_aff ON unions_master(aff_abbr);
CREATE INDEX idx_unions_master_has_f7 ON unions_master(has_f7_employers);

-- Union employer history indexes
CREATE INDEX idx_union_emp_hist_employer ON union_employer_history(employer_id);
CREATE INDEX idx_union_emp_hist_union ON union_employer_history(union_fnum);
CREATE INDEX idx_union_emp_hist_date ON union_employer_history(notice_date);

-- Table comments
COMMENT ON TABLE f7_employers IS 'F-7 bargaining notice employers with geocoded locations';
COMMENT ON TABLE unions_master IS 'Extended union metadata with sector classification and F-7 linkage';
COMMENT ON TABLE sector_lookup IS 'Sector classification explaining F-7 coverage';
COMMENT ON TABLE match_status_lookup IS 'Match status explaining why unions may/may not have F-7 records';
