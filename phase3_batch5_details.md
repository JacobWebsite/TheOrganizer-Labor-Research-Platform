# Phase 3 Batch 5 Details (2026-03-02)

- **3-10:** ACS demographics wired end-to-end (API fallback: NAICS 4->2->state-wide, `useEmployerDemographics` hook, frontend tests)
- **3-8b:** O*NET 30.2 loaded (13 tables, 709K rows from MySQL dumps). API enriches occupations with top_skills, knowledge, work_context, job_zone. Frontend OccupationSection shows expandable O*NET details.
- **3-12:** LODES WAC demographics aggregated to county (3,029 counties, race/sex/education). ZIP-county crosswalk (39K ZIPs). API endpoint + frontend LODES section in WorkforceDemographicsCard. `demo_total_jobs` column = WAC C000 sum (proper denominator).
- **3-11:** Census RPE loaded (2,055 NAICS codes from EC2200BASIC.zip). RPE CTE added to both `build_unified_scorecard.py` and `build_target_scorecard.py`. Size COALESCE chain: company_size > f7_unit_size > ppp_2020 > rpe_estimate. `size_source='rpe_estimate'` tracked. ProfileHeader shows "(RPE est.)" label.
- **New tables:** `census_rpe_ratios` (261,853 -- national+state+county), `zip_county_crosswalk` (39,366), 13 `onet_*` tables (709K total)
- **New columns:** `cur_lodes_geo_metrics`: 15 demographic columns + `demo_total_jobs`
- **New tests:** test_demographics_wiring.py (11), test_onet_loader.py (17), test_lodes_demographics.py (10), test_rpe_estimates.py (23), WorkforceDemographicsCard.test.jsx (11), OccupationSection.test.jsx (12)
- **Key gotcha:** Census NAICS uses combined ranges (31-33, 44-45, 48-49) at 2-digit level -- no standalone "31" code. LODES `total_jobs` != WAC C000 (sector sum vs actual total).
- **MV rebuilt** -- RPE active in both scorecards. 122 target employers gained size from RPE (990 revenue only path).
- **Task 3-11 remains OPEN** -- ongoing tuning tool, not a one-shot task
