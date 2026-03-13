# Session 2026-03-05: BLS Research Tool Gap Analysis

## Finding
4 BLS datasets loaded (2026-03-04) but completely unused by research tools in `scripts/research/tools.py`.

## Unused Datasets

### OES (Occupational Employment & Wage Statistics)
- Tables: `oes_occupation_wages` (414K), `mv_oes_area_wages` (224K filtered)
- Has: area-specific wages by occupation, percentiles (10th/25th/median/75th/90th)
- Should go in: `get_industry_profile()` -- currently only uses `bls_occupation_projections` for national wages

### SOII (Survey of Occupational Injuries & Illnesses)
- Tables: `bls_soii_data` (5.7M), `mv_soii_industry_rates` (45K filtered), plus 5 lookup tables + series
- Has: injury/illness rates by industry, annual trends
- Should go in: `get_industry_profile()` or complement `search_osha()` with industry-level safety benchmarks

### JOLTS (Job Openings & Labor Turnover Survey)
- Tables: `bls_jolts_data` (370K), `mv_jolts_industry_rates` (63K filtered), plus 5 lookup tables + series
- Has: quit rates, job openings, hires, separations by industry (national)
- Should go in: `get_industry_profile()` -- quit rates signal labor instability

### NCS (National Compensation Survey / Employee Benefits)
- Tables: `bls_ncs_data` (768K), `mv_ncs_benefits_access` (593K filtered), plus 6 lookup tables + series
- Has: healthcare, retirement, paid leave access/participation rates by industry
- Should go in: `get_industry_profile()` -- benefits gaps are organizing signals

## Also Partially Integrated
- **O*NET** (700K across 10 tables): Used by `api/routers/profile.py` for occupation enrichment, but NOT by any research tool
- **ACS insurance columns**: 6 new columns added to `cur_acs_workforce_demographics` but pipeline not re-run yet

## What Currently Works
- LODES (`search_lodes_workforce`) -- queries `cur_lodes_geo_metrics`, complete
- ACS (`search_acs_workforce`) -- queries `cur_acs_workforce_demographics`, complete (minus insurance)
- CBP (`search_cbp_context`) -- queries `cur_cbp_geo_naics`, complete

## Recommended Fix
Wire all 4 BLS datasets into `get_industry_profile()` (line 1181 of tools.py). Every dossier that calls industry profile would immediately get richer data. Use the pre-built MVs (`mv_soii_industry_rates`, `mv_jolts_industry_rates`, `mv_ncs_benefits_access`, `mv_oes_area_wages`) for clean queries.

## Tables Queried by get_industry_profile() Currently
- naics_codes_reference (NAICS hierarchy)
- naics_to_bls_industry (NAICS -> BLS mapping)
- bls_industry_occupation_matrix (top occupations)
- bls_occupation_projections (median wages, growth)
- bls_national_industry_density (union density)
- estimated_state_industry_density (state density)
- cur_cbp_geo_naics (establishment counts, employment, payroll)
- state_fips_map (state code lookup)
