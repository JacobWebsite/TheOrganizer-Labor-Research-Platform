# Project Metrics -- Labor Relations Research Platform

**Auto-generated:** 2026-02-22 09:36
**Script:** `py scripts/maintenance/generate_project_metrics.py`

---

## Database Overview

| Metric | Value |
|--------|-------|
| Database size | 9536 MB |
| Tables | 178 |
| Views | 123 |
| Materialized views | 6 |
| Indexes | 270 (2865 MB) |

## Materialized Views

| View | Rows |
|------|------|
| `mv_whd_employer_agg` | 330,419 |
| `mv_organizing_scorecard` | 212,441 |
| `mv_employer_data_sources` | 146,863 |
| `mv_unified_scorecard` | 146,863 |
| `mv_employer_search` | 107,025 |
| `mv_employer_features` | 54,968 |

## Top 30 Tables by Row Count (estimated)

| Table | Est. Rows |
|-------|-----------|
| `master_employer_source_ids` | 3,080,492 |
| `master_employers` | 2,928,028 |
| `ar_disbursements_emp_off` | 2,813,011 |
| `osha_violations_detail` | 2,244,955 |
| `nlrb_docket` | 2,046,151 |
| `irs_bmf` | 2,043,379 |
| `qcew_annual` | 1,943,426 |
| `nlrb_participants` | 1,906,537 |
| `unified_match_log` | 1,735,757 |
| `epi_union_membership` | 1,420,064 |
| `employers_990_deduped` | 1,046,167 |
| `osha_establishments` | 1,007,275 |
| `osha_violation_summary` | 872,163 |
| `sam_entities` | 826,042 |
| `nlrb_allegations` | 715,805 |
| `national_990_filers` | 586,767 |
| `sec_companies` | 517,403 |
| `gleif_ownership_links` | 498,963 |
| `nlrb_filings` | 498,749 |
| `nlrb_cases` | 477,688 |
| `gleif_us_entities` | 379,192 |
| `whd_cases` | 362,211 |
| `lm_data` | 331,238 |
| `mv_whd_employer_agg` | 330,419 |
| `ar_assets_investments` | 304,816 |
| `employer_comparables` | 269,785 |
| `ar_membership` | 216,508 |
| `ar_disbursements_total` | 216,372 |
| `mv_organizing_scorecard` | 212,441 |
| `union_names_crosswalk` | 171,481 |

## Unified Match Log Breakdown

**Total UML rows:** 1,738,115

| Source | Active | Rejected | Superseded | Total |
|--------|--------|----------|------------|-------|
| osha | 97,142 | 461,453 | 236,162 | 794,757 |
| sam | 28,816 | 219,175 | 52,358 | 300,349 |
| 990 | 20,215 | 131,294 | 94,531 | 246,040 |
| whd | 19,462 | 106,727 | 71,313 | 197,502 |
| crosswalk | 19,293 | 0 | 0 | 19,293 |
| nlrb | 13,031 | 4,485 | 0 | 17,516 |
| sec | 5,339 | 117,294 | 37,110 | 159,743 |
| gleif | 1,840 | 0 | 0 | 1,840 |
| mergent | 1,045 | 0 | 0 | 1,045 |
| bmf | 9 | 12 | 9 | 30 |

## Master Employers

**Total master_employers:** 3,026,290

| Source Origin | Count |
|-------------|-------|
| bmf | 2,027,342 |
| sam | 797,226 |
| f7 | 146,863 |
| mergent | 54,859 |

**Total master_employer_source_ids:** 3,080,492

| Source System | Count |
|-------------|-------|
| bmf | 2,043,779 |
| sam | 833,538 |
| f7 | 146,863 |
| mergent | 56,312 |

## Script Inventory

| Directory | Count |
|-----------|-------|
| `scripts/analysis` | 54 |
| `scripts/etl` | 28 |
| `scripts/maintenance` | 7 |
| `scripts/matching` | 19 |
| `scripts/matching/adapters` | 7 |
| `scripts/matching/matchers` | 5 |
| `scripts/ml` | 4 |
| `scripts/performance` | 1 |
| `scripts/scoring` | 7 |
| `scripts/scraper` | 8 |
| `scripts/setup` | 1 |
| **Total** | **141** |

## Tests

**Total tests collected:** 479
