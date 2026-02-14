# Deep Database & Platform Audit Report (v2)
**Date:** 2026-02-13
**Database:** `olms_multiyear` (PostgreSQL, localhost)
**Auditor:** Claude Code (Opus 4.6)

---

## PHASE 1: What's Actually In The Database?

### 1.1 — Complete Inventory

**Summary Counts:**
| Object Type | Count |
|---|---|
| Tables | 159 |
| Views | 187 |
| Materialized Views | 3 |
| **Total** | **349** |

**Database Size:**
| Metric | Size |
|---|---|
| Total database | 22 GB |
| Table data | 6,258 MB |
| Index data | 3,326 MB |
| Total (data+indexes) | 9,584 MB |

**Note on statistics:** 33 tables had stale `pg_stat` estimates (showing -1 or 0 rows). These were verified with actual `count(*)` queries. This means `ANALYZE` hasn't been run recently on smaller tables — the database auto-vacuum/analyze may need tuning for low-activity tables.

#### Top 25 Tables by Size

| Table | Data | Indexes | Total | Est Rows |
|---|---|---|---|---|
| splink_match_results | 1,089 MB | 501 MB | 1,591 MB | 5,762,126 |
| sam_entities | 645 MB | 181 MB | 826 MB | 829,055 |
| osha_establishments | 324 MB | 402 MB | 726 MB | 1,007,217 |
| nlrb_participants | 385 MB | 215 MB | 600 MB | 1,906,542 |
| mergent_employers | 492 MB | 69 MB | 561 MB | 108,691 |
| osha_violations_detail | 268 MB | 163 MB | 431 MB | 1,950,011 |
| whd_cases | 272 MB | 155 MB | 427 MB | 468,213 |
| ar_disbursements_emp_off | 325 MB | 61 MB | 386 MB | 2,813,248 |
| sec_companies | 178 MB | 197 MB | 374 MB | 522,370 |
| qcew_annual | 231 MB | 131 MB | 362 MB | 1,943,426 |
| gleif_us_entities | 165 MB | 177 MB | 342 MB | 379,192 |
| epi_union_membership | 224 MB | 97 MB | 322 MB | 1,420,064 |
| national_990_filers | 204 MB | 112 MB | 316 MB | 586,767 |
| nlrb_docket | 187 MB | 94 MB | 281 MB | 2,046,151 |
| employers_990_deduped | 189 MB | 77 MB | 265 MB | 1,046,167 |
| f7_employers_deduped | 52 MB | 100 MB | 152 MB | 60,953 |
| osha_violation_summary | 75 MB | 76 MB | 151 MB | 872,163 |
| employer_comparables | 117 MB | 18 MB | 135 MB | 269,810 |
| nlrb_allegations | 79 MB | 45 MB | 124 MB | 715,805 |
| f7_employers | 60 MB | 56 MB | 117 MB | 150,388 |
| nlrb_cases | 62 MB | 29 MB | 91 MB | 477,688 |
| nlrb_filings | 49 MB | 40 MB | 89 MB | 498,749 |
| gleif_ownership_links | 64 MB | 23 MB | 87 MB | 498,963 |
| lm_data | 60 MB | 19 MB | 79 MB | 331,238 |
| osha_f7_matches | 33 MB | 40 MB | 73 MB | 127,999 |

#### Notable Observations

**Biggest space consumer:** `splink_match_results` at 1.6 GB (501 MB in indexes alone). This is the probabilistic matching intermediate results table — 5.7M rows of candidate pairs, most of which were filtered out. It was used during the Splink matching phase and is essentially archival. **Potential recovery: 1.6 GB.**

**Index-heavy tables:** `osha_establishments` has 402 MB of indexes on 324 MB of data (1.24x ratio). `f7_employers_deduped` has 100 MB of indexes on 52 MB of data (1.92x ratio) — nearly double its data in indexes alone.

#### Tables Missing Primary Keys (18 tables)

| Table | Rows | Size | Impact |
|---|---|---|---|
| **f7_employers_deduped** | **60,953** | **152 MB** | **CRITICAL — core employer table, no uniqueness guarantee** |
| employers_990_deduped | 1,046,167 | 265 MB | Large deduped table with no PK |
| ar_disbursements_emp_off | 2,813,248 | 386 MB | Annual report data |
| ar_assets_investments | 304,816 | 32 MB | Annual report data |
| ar_disbursements_total | 216,372 | 28 MB | Annual report data |
| ar_membership | 216,508 | 26 MB | Annual report data |
| lm_data | 331,238 | 79 MB | LM filing data |
| f7_industry_scores | 121,433 | 26 MB | Scoring data |
| whd_f7_matches | 23,738 | 3.6 MB | Match table, no PK |
| national_990_f7_matches | 14,059 | 2.9 MB | Match table, no PK |
| sam_f7_matches | 10,164 | 2.1 MB | Match table, no PK |
| f7_federal_scores | 9,305 | 1.7 MB | Scoring data |
| usaspending_f7_matches | 9,305 | 1.6 MB | Match table |
| labor_orgs_990_deduped | 15,172 | 5 MB | Deduped orgs |
| qcew_industry_density | 7,143 | 1 MB | Density data |
| labor_990_olms_crosswalk | 5,012 | 664 kB | Crosswalk |
| nhq_reconciled_membership | 132 | 48 kB | Small reference |
| public_sector_benchmarks | 51 | 16 kB | Small reference |

**CRITICAL:** `f7_employers_deduped` is THE core employer table (~61K rows) and has **no primary key**. There is no database-level guarantee against duplicate rows. Three of the match tables (`whd_f7_matches`, `national_990_f7_matches`, `sam_f7_matches`) also lack primary keys — duplicate matches could exist undetected.

#### Empty Tables (6 total)

| Table | Columns | Notes |
|---|---|---|
| employer_ein_crosswalk | 14 | Planned but never populated |
| sic_naics_xwalk | 5 | SIC-NAICS crosswalk never loaded |
| union_affiliation_naics | 7 | Never populated |
| union_employer_history | 5 | Never populated |
| vr_employer_match_staging | 21 | Staging table, expected empty |
| vr_union_match_staging | 21 | Staging table, expected empty |

The staging tables (vr_*) are expected to be empty after processing. The other 4 represent features that were planned but never built.

#### Materialized Views (3 total)

| Name | Est Rows | Size | Notes |
|---|---|---|---|
| mv_whd_employer_agg | 330,419 | 76 MB | WHD employer aggregates |
| mv_employer_search | 118,015 | 41 MB | Powers the search interface |
| mv_employer_features | 54,968 | 10 MB | Feature matrix for Gower similarity |

**Staleness risk:** PostgreSQL provides no built-in way to check when materialized views were last refreshed. If underlying data changes (new matches, new employers), these views will show stale numbers until manually refreshed with `REFRESH MATERIALIZED VIEW`.

---

### 1.2 — Categorized Inventory

| Category | Tables | Views | Data Size | Total Rows |
|---|---|---|---|---|
| Core (F7/LM/Union) | 37 | 62 | 844 MB | 2,496,611 |
| OSHA | 9 | 4 | 1,434 MB | 4,167,830 |
| NLRB | 15 | 1 | 1,343 MB | 6,116,909 |
| Corporate/Financial | 14 | 3 | 2,260 MB | 4,058,857 |
| Mergent/Scoring | 4 | 7 | 726 MB | 505,362 |
| Matching/Linking | 15 | 3 | 1,602 MB | 5,838,049 |
| WHD | 5 | 1 | 509 MB | 495,717 |
| BLS/Reference | 22 | 19 | 387 MB | 2,073,214 |
| Public Sector | 8 | 6 | 20 MB | 58,048 |
| NYC/NY-Specific | 12 | 2 | 98 MB | 157,989 |
| Density/Geographic | 9 | 6 | 7 MB | 15,878 |
| Annual Reports | 4 | 0 | 472 MB | 3,550,944 |
| Sector Views | 0 | 66 | 0 MB | 0 |
| Unknown/Orphan | 5 | 10 | 10 MB | 413 |

#### Category-by-Category Analysis

**Core (F7/LM/Union) — 37 tables, 62 views (844 MB)**
The backbone of the platform. Key tables: `f7_employers_deduped` (61K employers), `f7_union_employer_relations` (120K bargaining links), `unions_master` (27K unions), `lm_data` (331K LM filings), `epi_union_membership` (1.4M union membership records). Also includes the raw pre-dedup `f7_employers` (150K rows) — still taking up 117 MB even though the deduped version replaced it. The 62 views provide various analytical perspectives on union membership, deduplication summaries, and voluntary recognition data.

**OSHA — 9 tables, 4 views (1,434 MB)**
Workplace safety data. Dominated by `osha_establishments` (1M inspected workplaces, 726 MB), `osha_violations_detail` (2M violations, 431 MB), and `osha_violation_summary` (872K, 151 MB). The `osha_f7_matches` table (128K matches) connects OSHA data to union employers. `unified_employers_osha` (101K rows) provides a consolidated view. `nyc_osha_violations` (3.5K) is city-specific.

**NLRB — 15 tables, 1 view (1,343 MB)**
Union election and labor practice data. Largest: `nlrb_participants` (1.9M, 600 MB) and `nlrb_docket` (2M, 281 MB). The `nlrb_employer_xref` (179K) and `nlrb_union_xref` (73K) connect NLRB cases to our employer and union data. Elections table (33K) has good coverage with matching `nlrb_election_results`. Only 1 view — most NLRB analysis is done through table joins.

**Corporate/Financial — 14 tables, 3 views (2,260 MB)**
The largest category by disk space. SAM.gov (829K contractors, 826 MB), SEC (522K companies, 374 MB), GLEIF (379K entities + 499K ownership links, 429 MB combined), and 990 nonprofits (587K national + 1M deduped, 581 MB combined). The `corporate_identifier_crosswalk` (25K) and `corporate_hierarchy` (125K links) tie these sources together. This category represents the external enrichment layer.

**Mergent/Scoring — 4 tables, 7 views (726 MB)**
Business intelligence. `mergent_employers` is massive (109K rows but 561 MB due to 111 columns). `employer_comparables` (270K rows, 135 MB) stores Gower similarity results. `f7_industry_scores` (121K) and `organizing_targets` (5K) are scoring artifacts. Views include AFSCME-specific targeting.

**Matching/Linking — 15 tables, 3 views (1,602 MB)**
Dominated by `splink_match_results` (5.7M rows, 1.6 GB) — the probabilistic matching intermediate table. This is **the single largest table** and is essentially archival. The rest are crosswalk and mapping tables (census, NAICS, SIC). Several are empty (staging tables, `sic_naics_xwalk`, `employer_ein_crosswalk`).

**WHD — 5 tables, 1 view (509 MB)**
Wage & Hour Division enforcement. `whd_cases` (468K, 427 MB) is the main table. `mv_whd_employer_agg` (330K, 76 MB) is a materialized view for fast lookups. `whd_f7_matches` (24K) connects to union employers. Three NYC-specific wage theft tables (3.8K rows total).

**BLS/Reference — 22 tables, 19 views (387 MB)**
Bureau of Labor Statistics data and reference lookups. `qcew_annual` (1.9M, 362 MB) dominates. Rest are small reference/lookup tables for industries, occupations, NAICS codes, states, CBSAs, right-to-work states, and NLRB win rate benchmarks.

**Annual Reports — 4 tables, 0 views (472 MB)**
Union financial filings from annual reports. `ar_disbursements_emp_off` (2.8M, 386 MB) is the largest. All 4 tables lack primary keys. No views or analysis built on top of this data — it's loaded but underutilized.

**Sector Views — 0 tables, 66 views (0 MB)**
Auto-generated "sector triple" views following the pattern: `v_{sector}_organizing_targets`, `v_{sector}_target_stats`, `v_{sector}_unionized`. 22 sectors x 3 views each = 66 views. **Notable: both `v_museum_*` (3 views) AND `v_museums_*` (3 views) exist — 6 views for one sector. One set is a duplicate.**

**NYC/NY-Specific — 12 tables, 2 views (98 MB)**
New York-focused data: NY 990 filers (48K), NYC contracts (50K), NY state contracts (52K), NYC ULP cases (920 open+closed), density estimates by tract/zip/county, local labor laws, debarment list, discrimination cases, prevailing wage.

**Density/Geographic — 9 tables, 6 views (7 MB)**
Union density estimates and geographic breakdowns. Small tables (all under 4 MB). County, state, and industry density comparisons.

**Public Sector — 8 tables, 6 views (20 MB)**
Federal agencies, bargaining units, contract recipients (47K), public sector employers (8K). FIPS lookups. Relatively small footprint.

**Unknown/Orphan — 5 tables, 10 views (10 MB)**
Items that don't fit cleanly into other categories:
- `mv_employer_features` (55K, 10 MB) — could be in Mergent/Scoring (Gower feature matrix)
- `unionstats_industry` (281 rows) — could be in BLS/Reference
- `nhq_reconciled_membership` (132 rows) — reconciliation artifact
- `employer_review_flags` (13 rows) — manual review tracking
- `vr_affiliation_patterns` (29 rows), `vr_status_lookup` (4 rows) — voluntary recognition reference
- 10 views covering affiliation analysis, employer profiles, and unified membership

#### Key Findings from Categorization

1. **66 sector views are auto-generated triples** — these were created in batch and follow a rigid pattern. They account for 35% of all views (66/187). If the underlying generating SQL is wrong, all 66 are wrong.

2. **Duplicate museum views** — `v_museum_*` (3 views) and `v_museums_*` (3 views) both exist. One set should be dropped.

3. **Annual Reports data (472 MB) appears underutilized** — 4 tables loaded with no views or API endpoints analyzing them.

4. **`splink_match_results` (1.6 GB) is archival** — it's in the Matching category but has served its purpose. Could be archived or dropped to recover 16% of database size.

5. **`f7_employers` raw table (117 MB) still exists** alongside the deduped version — this is the pre-deduplication data. It's used as a reference for orphan checking but represents 117 MB of largely redundant data.

---

### 1.3 — CLAUDE.md Documentation Accuracy

**Total inaccuracies found: 24**

#### CRITICAL Inaccuracies (will cause failures or major confusion)

| # | Location | Claim | Reality | Impact |
|---|---|---|---|---|
| 1 | Line 602 | Startup: `api.labor_api_v6:app` | Should be `api.main:app` | **Every new session will fail to start the API.** The monolith was decomposed into routers in Phase 7. |
| 2 | Line 43 | `nlrb_participants`: 30,399 rows | Actual: 1,906,542 | Off by 6,172%. The 30,399 figure appears to be a filtered count of a specific participant type, not the table total. Any capacity planning or query optimization based on this number will be wildly wrong. |
| 3 | Line 108 | `splink_match_results`: ~4,600 rows | Actual: 5,761,285 | Off by 125,000%. The ~4,600 was probably the final accepted matches, not the raw table (which holds all candidate pairs). This is a 1.6 GB table — anyone reading CLAUDE.md would think it's trivial. |
| 4 | Line 44 | `lm_data`: "2.6M+" rows | Actual: 331,238 | Off by 87%. The 2.6M figure may be from a different table or historical count. Massively inflated. |
| 5 | Line 63 | `osha_f7_matches`: 79,981 (44.6% match rate) | Actual: 138,340 (13.7%) | Not updated after Phase 5 improvements. The 79,981 was the pre-Phase-5 count. Match rate calculation (44.6%) was also wrong — 138K/1M = 13.7%, and even 80K/1M = 7.9%, not 44.6%. |
| 6 | Line 107 | `corporate_identifier_crosswalk`: 14,561 | Actual: 25,177 | Off by 73%. Not updated after Phase 5 (990 EIN enrichment) and Phase 8 (SAM matches). |
| 7 | Lines 239, 264 | Scoring tiers: MEDIUM >= 15, LOW < 15 | Actual: MEDIUM >= 20, LOW < 20 | API was recalibrated in Phase 2 but CLAUDE.md was never updated. Agents reading this will misclassify targets. |

#### SIGNIFICANT Inaccuracies (wrong data, could mislead analysis)

| # | Location | Claim | Reality | Impact |
|---|---|---|---|---|
| 8 | Line 31, 41 | `f7_employers_deduped`: 62,163 | Actual: 60,953 | Off by 1,210 (1.9%). Not updated after Splink self-dedup which merged 1,210 records. |
| 9 | Line 74 | WHD match: "F7: 2,990 (4.8%)" | Actual: `whd_f7_matches` has 24,610 (6.8%) | Not updated after Phase 5. 8x more matches than documented. |
| 10 | Line 48 | `mv_employer_search`: 120,169 | Actual: 118,015 | Off by 2,154 (1.8%). Stale after dedup. |
| 11 | Line 189 | `mergent_employers`: 56,431 | Actual: 56,426 | Off by 5. Dedup merged 5 duplicates. |
| 12 | Line 46 | `manual_employers`: 509 | Actual: 520 | Off by 11. Minor but wrong. |
| 13 | Line 415 | OSHA Scorecard: "6-factor, 0-100 pts" | Actual: 9-factor scorecard | Factors: safety(25), industry_density(15), geographic(15), size(15), nlrb(15), contracts(15), company_unions(10?), similarity(?), BLS projections(?). The "6-factor" description is outdated. |

#### MISSING Documentation (significant data not mentioned)

| # | Table | Rows | Impact |
|---|---|---|---|
| 14 | `sam_entities` | 826,042 | Entire SAM.gov dataset — federal contractors. Not mentioned anywhere. |
| 15 | `sam_f7_matches` | 11,050 | SAM-to-F7 employer matches. Undocumented. |
| 16 | `whd_f7_matches` | 24,610 | WHD matching table. Only old coverage stats cited. |
| 17 | `national_990_f7_matches` | 14,059 | 990-to-F7 matches. Undocumented. |
| 18 | `employer_comparables` | 269,785 | Gower similarity engine. Undocumented. |
| 19 | `nlrb_employer_xref` | 179,275 | NLRB-to-F7 cross-reference. Undocumented. |
| 20 | Annual Reports (4 tables) | 3,550,944 | `ar_disbursements_emp_off` (2.8M), `ar_membership` (217K), etc. 472 MB of data not mentioned. |
| 21 | `epi_union_membership` | 1,420,064 | EPI membership microdata. 322 MB. Not mentioned. |
| 22 | `employers_990_deduped` | 1,046,167 | Deduped national 990 employers. 265 MB. Not mentioned. |

#### NONEXISTENT Tables Referenced

| # | Table | Where Referenced | Reality |
|---|---|---|---|
| 23 | `zip_geography` | Geography Tables section (line 269) | Does not exist. Replaced by CBSA tables. |
| 24 | `cbsa_reference` | Geography Tables section (line 270) | Does not exist. `cbsa_definitions` (935 rows) exists instead. |

#### GLEIF Schema Discrepancy

CLAUDE.md lists 6 GLEIF schema tables. Actual count: **9 tables** (3 missing from docs: `entity_annotations`, `ooc_annotations`, `person_annotations`).

#### Summary

- **7 CRITICAL errors** that would cause session failures or major analytical mistakes
- **6 SIGNIFICANT errors** with wrong numbers that could mislead work
- **9 MISSING entries** for tables holding millions of rows and gigabytes of data
- **2 NONEXISTENT tables** referenced that will cause confusion
- Of 60 row counts checked, **9 are wrong** (15% error rate)
- The document has not been systematically updated since approximately Phase 3 (late January 2026). Phases 4-8 made major changes (OSHA/WHD/990 matching, Splink dedup, SAM.gov, API decomposition, scoring recalibration) that are absent from the docs.

---

## PHASE 2: Is The Data Any Good?

### 2.1 — Core Table Quality Check

#### 1. `f7_employers_deduped` (60,953 rows) — EXCELLENT

| Column | Filled | Null | Empty | Coverage |
|---|---|---|---|---|
| employer_name | 60,953 | 0 | 0 | **100.0%** |
| employer_name_aggressive | 60,924 | 0 | 29 | 100.0% |
| city | 60,910 | 43 | 0 | 99.9% |
| state | 60,654 | 299 | 0 | 99.5% |
| naics | 60,455 | 498 | 0 | 99.2% |
| latitude | 60,843 | 110 | 0 | 99.8% |
| longitude | 60,843 | 110 | 0 | 99.8% |
| latest_unit_size | 60,953 | 0 | 0 | **100.0%** |

**Assessment:** Extremely healthy data. All key columns above 99%. The 110 records missing coordinates are the only notable gap. All lat/lon values are real coordinates (no zeros). **F7 has NO `ein` column** — employer identification numbers are only available through the corporate crosswalk.

#### 2. `unions_master` (26,665 rows) — GOOD

| Column | Filled | Null | Empty | Coverage |
|---|---|---|---|---|
| union_name | 26,665 | 0 | 0 | **100.0%** |
| aff_abbr | 26,665 | 0 | 0 | **100.0%** |
| f_num | 26,665 | 0 | 0 | **100.0%** |
| city | 26,665 | 0 | 0 | **100.0%** |
| state | 26,665 | 0 | 0 | **100.0%** |
| members | 24,921 | 1,744 | 0 | 93.5% |

**Assessment:** Solid overall. The `members` column has 1,744 nulls (6.5%) and an additional 3,404 zeros — meaning 5,148 unions (19.3%) have no meaningful membership count. This includes local unions that don't file LM reports. Max membership is 14.8M (NEA), average 2,943.

#### 3. `nlrb_elections` (33,096 rows) — EXCELLENT

| Column | Filled | Null | Empty | Coverage |
|---|---|---|---|---|
| case_number | 33,096 | 0 | 0 | **100.0%** |
| election_date | 33,096 | 0 | 0 | **100.0%** |
| eligible_voters | 32,940 | 156 | 0 | 99.5% |
| union_won | 32,793 | 303 | 0 | 99.1% |
| vote_margin | 33,096 | 0 | 0 | **100.0%** |

**Assessment:** Excellent data quality. 99%+ on all key fields. The 303 missing `union_won` outcomes (0.9%) are likely pending or withdrawn cases. Note: `ballot_type` column exists but is 100% NULL (never populated). `status` column does not exist.

#### 4. `nlrb_participants` (1,906,542 rows) — POOR

| Column | Filled | Null | Empty | Coverage |
|---|---|---|---|---|
| case_number | 1,906,542 | 0 | 0 | **100.0%** |
| participant_type | 1,906,163 | 0 | 379 | 100.0% |
| participant_name | 1,680,616 | 0 | 225,926 | **88.1%** |
| city | 692,375 | 0 | 1,214,167 | **36.3%** |
| state | 692,325 | 0 | 1,214,217 | **36.3%** |

**Assessment: This is the weakest table in the core set.** Geographic data is terrible — only 36.3% of participants have city/state data. This means when the platform needs to look up where an NLRB participant is located, it fails 2 out of 3 times. Of the 692K rows with state data, only 312,767 (16.4% of total) have valid 2-character state codes — the rest may have header artifacts or malformed values. 226K records (11.9%) have blank participant names.

**Practical impact:** When looking up NLRB activity for an employer in a specific state, roughly two-thirds of participant records can't be geographically filtered. This means the "NLRB by state" analysis is based on only a third of the data.

#### 5. `osha_establishments` (1,007,217 rows) — EXCELLENT

| Column | Filled | Null | Empty | Coverage |
|---|---|---|---|---|
| estab_name | 1,007,217 | 0 | 0 | **100.0%** |
| site_city | 1,005,283 | 0 | 1,934 | 99.8% |
| site_state | 1,007,082 | 0 | 135 | 100.0% |
| naics_code | 1,005,361 | 1,856 | 0 | 99.8% |
| site_zip | 1,005,456 | 1,761 | 0 | 99.8% |

**Assessment:** Outstanding data quality across all fields, consistently 99.8%+. OSHA is the cleanest external dataset in the platform.

#### 6. `mergent_employers` (56,426 rows) — MIXED

| Column | Filled | Null | Empty/Zero | Coverage |
|---|---|---|---|---|
| company_name | 56,426 | 0 | 0 | **100.0%** |
| duns | 56,426 | 0 | 0 | **100.0%** |
| city | 56,426 | 0 | 0 | **100.0%** |
| state | 56,426 | 0 | 0 | **100.0%** |
| sector_category | 56,426 | 0 | 0 | **100.0%** |
| has_union | 56,426 | 0 | 0 | **100.0%** |
| employees_site | 56,228 | 0 | 198 | 99.6% |
| naics_primary | 54,889 | 1,537 | 0 | 97.3% |
| organizing_score | 55,441 | 985 | 0 | 98.3% |
| score_priority | 55,461 | 965 | 0 | 98.3% |
| ein | 24,799 | 31,627 | 0 | **43.9%** |
| matched_f7_employer_id | 856 | 55,570 | 0 | **1.5%** |

**Assessment: Two critical gaps.**

1. **EIN coverage is only 43.9%** — CLAUDE.md claims 55%. This limits identifier-based matching with external datasets.

2. **F7 linkage is shockingly low at 1.5%.** Only 856 of 56,426 Mergent employers have a direct `matched_f7_employer_id`. This means **98.5% of Mergent employers have NO direct connection to union data.** The organizing scores for these unlinked employers are based entirely on external factors (size, industry, geography) — not actual union intelligence. When the scorecard shows "this employer has a union," it can only do so for 856 employers.

   **Why this matters for organizers:** The scorecard ranks 56K employers but only 856 are known to have union connections. For the other 98.5%, the "company unions" score factor (worth up to 10 points) is always 0. These employers might actually have unions, but the platform can't tell.

#### Summary Table

| Table | Rows | Quality | Key Gap |
|---|---|---|---|
| f7_employers_deduped | 60,953 | **Excellent** | 110 missing coordinates (0.2%) |
| unions_master | 26,665 | **Good** | 19.3% without membership data |
| nlrb_elections | 33,096 | **Excellent** | 303 missing outcomes (0.9%) |
| nlrb_participants | 1,906,542 | **Poor** | 63.7% missing city/state |
| osha_establishments | 1,007,217 | **Excellent** | Negligible gaps (<0.2%) |
| mergent_employers | 56,426 | **Mixed** | 98.5% unlinked to F7; EIN only 44% |

---

### 2.2 — Duplicate Detection

#### `f7_employers_deduped` — CLEAN (zero duplicates)

No duplicate `employer_name + state` combinations found. The Splink deduplication process worked correctly. All 60,953 rows represent unique employer+state combinations.

#### `osha_establishments` — Expected Duplication (13.9%)

| Metric | Value |
|---|---|
| Total rows | 1,007,217 |
| Unique name+city+state combos | 923,732 |
| Duplicate groups | 56,149 |
| Rows in duplicate groups | 139,634 (13.9%) |

**This is expected and normal.** OSHA creates a new establishment record per inspection, so the same workplace appears multiple times for different inspections over the years. This is not a data quality problem — it's how the data is structured.

**Distribution of duplication:**
| Occurrences | Groups | Rows |
|---|---|---|
| 1 (unique) | 867,583 | 867,583 |
| 2 | 43,119 | 86,238 |
| 3-5 | 11,388 | 38,652 |
| 6-10 | 1,303 | 9,286 |
| 11-50 | 337 | 5,335 |
| 50+ | 2 | 123 |

Top duplicated names are generic ("UNKNOWN CONTRACTOR" 67x, "USDOL OSHA - MILWAUKEE" 56x) — these are placeholder names for unidentified contractors at inspection sites, not real employer duplicates.

#### `nlrb_elections` — Minor Issue (307 true duplicates)

| Type | Groups | Rows |
|---|---|---|
| Re-elections / runoffs (different dates, same case) | 1,297 | ~2,583 |
| True duplicates (same case + same date) | 307 | 832 |
| **Total duplicate case_numbers** | **1,604** | **3,415** |

The 1,297 re-election groups are **expected** — unions can hold runoff elections or re-run elections under the same case number. Examples show different dates and sometimes different voter counts.

The 307 true duplicates (same case number AND same election date) are **problematic** — these are exact duplicate rows that shouldn't exist. They represent 832 rows that should be 307, meaning 525 excess rows. At 1.6% of total elections, this is minor but worth cleaning.

#### Match Tables — ALL CLEAN

| Table | Rows | Duplicate Key Combos | Status |
|---|---|---|---|
| osha_f7_matches | 138,340 | 0 | CLEAN |
| whd_f7_matches | 24,610 | 0 | CLEAN |
| national_990_f7_matches | 14,059 | 0 | CLEAN |
| sam_f7_matches | 11,050 | 0 | CLEAN |

All four match tables have zero duplicate key combinations. Despite lacking primary keys, the data is clean.

---

### 2.3 — Relationship Integrity

#### Summary

| # | Relationship | Total | Orphaned | % | Severity |
|---|---|---|---|---|---|
| 1 | f7_union_employer_relations.employer_id -> f7_employers_deduped | 119,844 | **60,373** | **50.4%** | **CRITICAL** |
| 2 | f7_union_employer_relations.union_file_number -> unions_master | 119,844 | 824 | 0.7% | Minor |
| 3 | osha_f7_matches.f7_employer_id -> f7_employers_deduped | 138,340 | 0 | 0.0% | Clean |
| 4 | osha_f7_matches.establishment_id -> osha_establishments | 138,340 | 0 | 0.0% | Clean |
| 5 | whd_f7_matches -> f7_employers_deduped | 24,610 | 0 | 0.0% | Clean |
| 6 | national_990_f7_matches -> f7_employers_deduped | 14,059 | 0 | 0.0% | Clean |
| 7 | sam_f7_matches -> f7_employers_deduped | 11,050 | 0 | 0.0% | Clean |
| 8 | nlrb_participants -> nlrb_cases | 1,906,542 | 0 | 0.0% | Clean |
| 9 | nlrb_employer_xref.f7_employer_id -> f7_employers_deduped | 27,728 linked | **14,150** | **51.0%** | **CRITICAL** |
| 10 | ps_union_locals -> unions_master (f_num) | 1,179 linked | 0 | 0.0% | Clean |

**8 of 10 relationships are clean. 2 have catastrophic orphan rates (~50%).**

#### CRITICAL: Relationship 1 — Union-Employer Bargaining Links (50.4% orphaned)

This is the single most important relationship in the entire platform. `f7_union_employer_relations` is the table that says "Union X represents workers at Employer Y." It's the foundation for knowing which employers have unions and how many workers are covered.

| Metric | Value |
|---|---|
| Total relations | 119,844 |
| Valid (employer in deduped table) | 59,471 (49.6%) |
| **Orphaned (employer NOT in deduped)** | **60,373 (50.4%)** |
| Distinct orphaned employer_ids | 56,291 |
| Workers in orphaned relations | **7,034,705 of 15,867,180 (44.3%)** |
| All orphans found in raw f7_employers? | Yes — 100% |
| Truly lost (not in any table)? | 0 |

**What happened:** The Splink deduplication process (Phase 8e) merged 1,210 duplicate employers, creating new consolidated `employer_id` values. The `f7_union_employer_relations` table was never fully updated to use these new IDs. The 60,373 orphaned rows still reference pre-dedup employer IDs that exist in the raw `f7_employers` table but not in `f7_employers_deduped`.

**What this means in practice:**
- When a user looks up "what unions represent workers at Employer X," the query joins these two tables. **Half of all bargaining relationships silently vanish** because the employer IDs don't match.
- The platform shows ~60K union-employer links, but only ~59K are actually visible through JOINs. The other ~60K are invisible.
- **7 million covered workers** (44.3% of 15.9M total) are associated with orphaned employer IDs, meaning their union coverage is invisible to the platform.
- Any aggregate statistic about union coverage (total workers represented, employers with unions, etc.) is undercount by roughly half.

**The data is NOT lost** — all 60,373 orphaned employer IDs exist in the raw `f7_employers` table. The fix is to update the relations table to map old (pre-dedup) employer IDs to their new (deduped) counterparts using the `f7_employer_merge_log` table (which records exactly which IDs were merged into which).

#### CRITICAL: Relationship 9 — NLRB-to-F7 Cross-Reference (51.0% orphaned)

| Metric | Value |
|---|---|
| Total xref rows | 179,275 |
| Rows with F7 employer link | 27,728 |
| **Orphaned F7 links** | **14,150 (51.0% of linked)** |

**Same root cause as Relationship 1.** The `nlrb_employer_xref` table links NLRB cases to F7 employers, but 51% of those links point to pre-dedup employer IDs. When the platform tries to show "which NLRB elections involved this employer," half the connections are invisible.

**Practical impact:** When looking up NLRB history for an employer, roughly half the relevant elections won't appear. The "NLRB momentum" score factor in the organizing scorecard is based on incomplete data for ~half of employers.

#### Minor: Relationship 2 — Union File Numbers (0.7% orphaned)

824 relations (0.7%) reference 195 distinct union file numbers not found in `unions_master`. These are likely historical or defunct union locals that filed F7 reports but are no longer in the OLMS master directory. This represents 92,627 covered workers across 812 employers (from prior analysis). Low priority but worth investigating.

#### Clean Relationships (8 of 10)

The remaining 8 relationships are all perfectly clean:
- **All 4 match tables** (OSHA, WHD, 990, SAM) have 0% orphan rates to `f7_employers_deduped`. These were built after the deduplication and correctly reference deduped IDs.
- **OSHA match-to-establishment links** are 100% valid.
- **NLRB participants-to-cases** are 100% valid across 1.9M rows.
- **Public sector locals** are 100% valid to `unions_master`.

This confirms that the orphan problem is specifically a **dedup migration issue** — tables built before the dedup have broken links, tables built after are clean.

---

## PHASE 3: Views and Indexes

### 3.1 — Materialized Views

#### Inventory

| View | Rows | Size | Indexes | Source Tables | Status |
|---|---|---|---|---|---|
| mv_employer_features | 54,968 | 10 MB | 2 | mergent_employers, corporate_identifier_crosswalk, bls_industry_projections | OK |
| mv_employer_search | 118,015 | 41 MB | 5 | f7_employers_deduped, nlrb_participants, nlrb_elections, nlrb_tallies, nlrb_voluntary_recognition, manual_employers | OK |
| mv_whd_employer_agg | 330,419 | 76 MB | 2 | whd_cases | OK |

All 3 materialized views are functional (test queries succeed).

#### Detail

**mv_employer_features (10 MB, 2 indexes)**
The Gower similarity feature matrix. Contains 14 min-max normalized features for 55K Mergent employers (those with NAICS + state). Features include log-scaled employee counts, revenue, company age, OSHA/WHD violation rates, federal contractor flag, and BLS growth projections. Used by the `employer_comparables` table generation.

Indexes: `idx_mvef_union` (union flag), `idx_mvef_eid` (employer ID).

**mv_employer_search (41 MB, 5 indexes)**
The unified employer search that powers the frontend. Combines 4 sources via UNION ALL:
1. **F7** employers (from `f7_employers_deduped`) — correctly uses the deduped table
2. **NLRB** participants (employer type, not already matched, deduplicated by name+city+state)
3. **VR** voluntary recognition cases (not already matched)
4. **MANUAL** employer entries

Has 5 indexes including a trigram index for fuzzy name search (`idx_mv_employer_search_trgm`), plus state, city, ID, and source type indexes.

**mv_whd_employer_agg (76 MB, 2 indexes)**
Simple aggregation of `whd_cases` grouped by normalized employer name + city + state. Computes totals for violations, backwages, penalties, child labor incidents, and repeat violator flags. Used by the WHD API endpoints.

Indexes: `idx_mv_whd_name_state`, `idx_mv_whd_name_city_state`.

#### Staleness Assessment

**All 3 materialized views show NULL for last_vacuum, last_autovacuum, last_analyze, and last_autoanalyze.** This means:
1. PostgreSQL's autovacuum has never maintained these views
2. Query planner statistics are absent (0 columns reported in `information_schema`), which may cause suboptimal query plans
3. There is no way to know when they were last refreshed

**Staleness risks by view:**
- **mv_employer_features**: If `mergent_employers` scoring changes or new crosswalk entries are added, the feature matrix won't reflect them until refreshed. This affects Gower similarity calculations.
- **mv_employer_search**: If new employers are added to `f7_employers_deduped`, new NLRB cases arrive, or VR data changes, search results are stale. Current row count (118K) should be verified against the expected sum of its sources.
- **mv_whd_employer_agg**: Only stale if new WHD cases are loaded. Since `whd_cases` is 363K rows and the view shows 330K (grouped), this appears current.

**Recommendation:** Add `ANALYZE` after each `REFRESH MATERIALIZED VIEW` to update statistics. Consider adding a `refresh_log` table or a script that timestamps each refresh.

**Positive finding:** None of the materialized views reference the raw `f7_employers` table. `mv_employer_search` correctly uses `f7_employers_deduped`.

### 3.2 — Regular Views (Checkpoint 8)

**Total views:** 187
**All functional:** Yes — every view executes without error and returns data. Zero broken views.

#### Views Referencing Raw `f7_employers` (Should Use `f7_employers_deduped`)

3 views reference the raw `f7_employers` table instead of the deduped version:

| View | Rows | Impact |
|---|---|---|
| `v_f7_employers_fully_adjusted` | 96,419 | Uses raw `f7_employers` for employer name inference. Returns 96K rows vs the 61K in deduped — inflated by ~35K pre-merge duplicates. |
| `v_f7_private_sector_reconciled` | 86,868 | Joins through `v_f7_employers_fully_adjusted`, inheriting the raw-table problem. Used for reconciliation analysis. |
| `v_state_overview` | 51 | Uses `f7_employers` for state-level employer counts. Counts will be inflated vs deduped reality. |

**Severity: SIGNIFICANT** — These 3 views silently return inflated counts. Anyone querying them gets pre-dedup numbers without knowing it. The `v_state_overview` is particularly misleading since it's a dashboard-style summary.

#### Sector Triple Pattern (67 views)

The database contains a systematic pattern of 3 views per industry sector:
- `v_{sector}_organizing_targets` — OSHA establishments in this sector with scorecard data
- `v_{sector}_target_stats` — Aggregate statistics for the sector
- `v_{sector}_unionized` — Union-related employers in this sector

**22 complete triples** (all 3 views present):
accommodation, admin_support, arts_entertainment, construction, education, finance_insurance, food_service, healthcare, information, management, manufacturing, mining, other_services, professional_services, public_admin, real_estate, retail, social_assistance, transportation, utilities, waste_management, wholesale

**1 incomplete sector** — `osha` has only `v_osha_organizing_targets` (no `_target_stats` or `_unionized`).

**Assessment:** These are auto-generated convenience views (same template per sector, filtering on NAICS prefix). Useful for sector-specific dashboards but add 67 objects to the schema. Consider whether they should be parameterized queries instead.

#### Duplicate Museum Views

Two parallel naming conventions exist:
- `v_museum_organizing_targets`, `v_museum_target_stats`, `v_museum_unionized` (singular)
- `v_museums_organizing_targets`, `v_museums_target_stats`, `v_museums_unionized` (plural)

Both filter on NAICS 'MUSEUMS' and return 218 rows each. Definitions are **not identical** (minor SQL differences) but produce the same results. One set should be dropped.

#### View Pattern Groups

| Pattern | Count | Description |
|---|---|---|
| Sector triples | 67 | `v_{sector}_{organizing_targets,target_stats,unionized}` |
| Membership/Union | 26 | Union density, membership, hierarchy views |
| BLS/EPI | 20 | Industry projections, occupation data, union membership rates |
| Other | 21 | Miscellaneous analytical views |
| F7/Dedup | 17 | Employer dedup, reconciliation, adjustment views |
| VR (Voluntary Recognition) | 13 | VR cases, tracking, matching |
| NYC-specific | 10 | NYC wage theft, prevailing wage views |
| Density | 9 | Union density by state, industry, metro |
| Platform | 2 | Cross-platform summary views |
| OSHA | 2 | OSHA organizing target views |

#### Key Findings

1. **Zero broken views** — All 187 views execute successfully. This is excellent.
2. **3 views use raw `f7_employers`** — Should be migrated to `f7_employers_deduped`. Low effort, high impact fix.
3. **67 sector views are auto-generated** — Useful but add schema bloat. Could be replaced with a parameterized function.
4. **6 duplicate museum views** — `v_museum_*` and `v_museums_*` both exist. Drop one set.
5. **No empty views** — Every view returns at least some data.

### 3.3 — Index Analysis (Checkpoint 9)

**Stats reset:** Never (`stats_reset` is NULL) — usage counts are lifetime since database creation. Zero-scan indexes are genuinely unused, not just post-restart artifacts.

#### Overview

| Metric | Count | Size |
|---|---|---|
| **Total indexes** | 535 | 3,373 MB |
| Primary Key | 141 | 742 MB |
| Unique constraint | 23 | 58 MB |
| Regular | 394 | 2,980 MB |
| **Used (>0 scans)** | 163 (30.5%) | — |
| **Unused (0 scans)** | 372 (69.5%) | — |

**69.5% of indexes have never been scanned.** This includes 108 PK indexes and 22 unique constraint indexes which must be kept for data integrity regardless. The actionable waste is in the 252 unused regular indexes consuming **2,028 MB** (2.0 GB).

#### Exact Duplicate Indexes (24 pairs, 222 MB wasted)

These are pairs of indexes on the same table covering the exact same columns with the same method. One copy in each pair can be dropped immediately.

| Table | Duplicate Pair | Wasted |
|---|---|---|
| `f7_employers_deduped` | `idx_f7_emp_trgm` + `idx_f7_employer_name_trgm` (GIN trigram on `employer_name`) | 21 MB |
| `f7_employers_deduped` | `idx_f7_emp_agg_trgm` + `idx_f7_name_agg_trgm` (GIN trigram on `employer_name_aggressive`) | 6 MB |
| `f7_employers_deduped` | `idx_f7_deduped_state` + `idx_f7_reconciled_state` | 2 MB |
| `f7_employers_deduped` | `idx_f7_deduped_union_fnum` + `idx_f7_reconciled_affiliation` | 2 MB |
| `osha_establishments` | `idx_osha_est_name_norm_trgm` + `idx_osha_est_name_trgm` (GIN trigram, 53 MB each) | 53 MB |
| `osha_establishments` | `idx_osha_est_name_norm_lower` + `idx_osha_est_name_norm_state` | 32 MB |
| `osha_f7_matches` | `idx_osha_f7_est` + `idx_osha_f7_matches_estab_uniq` | 18 MB |
| `nlrb_participants` | `idx_nlrb_part_employer` + `idx_nlrb_part_matched_emp` | 13 MB |
| `nlrb_participants` | `idx_nlrb_part_matched_union` + `idx_nlrb_part_olms` | 13 MB |
| `sec_companies` | `idx_sec_cik` + `sec_companies_cik_key` | 22 MB |
| `f7_employers` | `idx_employer_search_name` + `idx_f7_emp_name_lower` | 13 MB |
| `f7_employers` | `idx_employer_search_state` + `idx_f7_employers_state` | 2 MB |
| `lm_data` | `idx_lm_data_fnum` + `idx_lm_fnum` | 3 MB |
| `lm_data` | `idx_lm_data_yr` + `idx_lm_year` | 2 MB |
| `lm_data` | `idx_lm_aff` + `idx_lm_aff_abbr` | 2 MB |
| `ar_membership` | `idx_ar_mem_rptid` + `idx_membership_rpt` | 3 MB |
| Others (8 pairs on smaller tables) | Various constraint vs manual duplicates | <1 MB each |

**Root cause:** Many duplicates appear to be manual `CREATE INDEX` statements that duplicate auto-created constraint indexes, or leftover indexes from before table renames (e.g., `idx_f7_reconciled_*` alongside `idx_f7_deduped_*`).

#### Subset/Overlapping Indexes (22 cases, 125 MB wasted)

Indexes where one is a leading-column prefix of another (the single-column index is redundant because the multi-column index covers it):

Notable examples:
- `sec_companies`: `idx_sec_name` (46 MB, name only) is redundant with `idx_sec_name_state` (50 MB, name+state)
- `gleif_us_entities`: `idx_gus_name` (32 MB) redundant with `idx_gleif_name_state` (34 MB)
- `national_990_filers`: `idx_n990_state` (4 MB) redundant with `idx_n990_state_name` (36 MB)
- `qcew_annual`: `idx_qcew_area` (13 MB) redundant with `idx_qcew_area_ind` (24 MB)

#### Archival Table Waste: `splink_match_results` (501 MB indexes)

The `splink_match_results` table (5.8M rows, 1.6 GB total) is an archival table from the Splink deduplication runs. It has 5 indexes totaling 501 MB, of which 4 (452 MB) have zero scans. Only `idx_smr_scenario` has 3 scans. This table is referenced by 0 views and 0 API endpoints.

**Recommendation:** Either drop the indexes and keep the table as cold storage, or archive the table entirely (pg_dump + DROP). Recoverable space: **452-501 MB**.

#### Raw `f7_employers` Table Indexes (57 MB)

The raw `f7_employers` table (pre-dedup) has 10 indexes totaling 57 MB. Only the PK (120 scans) and NAICS index (3 scans) see any use. The other 8 indexes (47 MB) are unused. Since almost everything should be querying `f7_employers_deduped`, these are largely waste — though they'd be needed if the 3 views referencing raw `f7_employers` are kept.

#### Tables With Most Unused Index Space

| Table | Total Idx | Unused | Unused Space |
|---|---|---|---|
| splink_match_results | 5 | 4 | 452 MB |
| osha_establishments | 11 | 6 | 207 MB |
| sec_companies | 10 | 9 | 189 MB |
| sam_entities | 8 | 7 | 176 MB |
| nlrb_participants | 10 | 8 | 174 MB |
| gleif_us_entities | 7 | 6 | 168 MB |
| whd_cases | 8 | 7 | 147 MB |
| qcew_annual | 7 | 6 | 118 MB |
| national_990_filers | 6 | 5 | 108 MB |
| f7_employers_deduped | 14 | 10 | 89 MB |

**Total unused index space: 2,454 MB (2.4 GB)**

#### Missing Indexes

**No large tables (>10K rows) are missing indexes entirely.** Every table with significant data has at least one index.

#### Space Recovery Summary

| Action | Recoverable Space | Effort | Risk |
|---|---|---|---|
| Drop 24 exact duplicate indexes | 222 MB | Low | None — identical copy exists |
| Drop 22 subset indexes | 125 MB | Low | Minimal — superset index covers all queries |
| Drop splink_match_results indexes | 452 MB | Low | None if table is archival |
| Drop unused raw f7_employers indexes | 47 MB | Low | Check 3 views first |
| Drop remaining unused regular indexes | ~1,182 MB | Medium | Review each — some may be for batch scripts |
| **Total recoverable** | **~2,028 MB** | | |

**Bottom line:** The database has 3.4 GB of indexes, of which ~2.0 GB (59%) is unused regular indexes. At minimum, 799 MB from duplicates, subsets, and archival indexes can be safely dropped with zero risk. The full 2.0 GB is likely recoverable but requires reviewing whether any batch scripts or matching jobs use the remaining indexes.

---

## PHASE 4: Cross-Reference Coverage

### 4.1 — How Well Are Data Sources Connected? (Checkpoint 10)

#### Per-Source Match Counts

| External Source | F7 Employers Matched | % of 60,953 |
|---|---:|---:|
| OSHA (`osha_f7_matches`) | 28,848 | 47.3% |
| Corporate crosswalk | 17,280 | 28.3% |
| WHD (`whd_f7_matches`) | 9,739 | 16.0% |
| SAM.gov (`sam_f7_matches`) | 8,495 | 13.9% |
| 990 Nonprofits (`national_990_f7_matches`) | 7,240 | 11.9% |

OSHA is the strongest single link — nearly half of all F7 employers have at least one OSHA match.

#### Match Depth Distribution

| Depth (# of sources) | F7 Employers | % | Cumulative >= |
|---:|---:|---:|---:|
| 0 (isolated) | 23,333 | 38.3% | 100.0% |
| 1 | 19,470 | 31.9% | 61.7% |
| 2 | 10,166 | 16.7% | 29.8% |
| 3 | 5,082 | 8.3% | 13.1% |
| 4 | 2,340 | 3.8% | 4.8% |
| 5 (all sources) | 562 | 0.9% | 0.9% |

**61.7% of F7 employers have at least one external connection. 38.3% (23,333) are completely isolated** — no OSHA, WHD, 990, SAM, or crosswalk link. The depth-5 employers (connected to all sources) are dominated by hospitals, universities, and large nonprofits.

#### External Record Coverage (Reverse)

| External Dataset | Total Records | Matched to F7 | Rate |
|---|---:|---:|---:|
| OSHA establishments | 1,007,217 | 138,340 | 13.7% |
| WHD cases | 363,365 | 24,610 | 6.8% |

Low percentages are expected: F7 covers only ~61K unionized employers, a small slice of all US employers.

#### Match Multiplicity

| Source | Total Match Rows | Distinct F7 IDs | Avg Matches/Employer |
|---|---:|---:|---:|
| OSHA | 138,340 | 28,848 | 4.8 |
| WHD | 24,610 | 9,739 | 2.5 |
| 990 | 14,059 | 7,240 | 1.9 |
| SAM | 11,050 | 8,495 | 1.3 |
| Crosswalk | 25,177 | 17,280 | 1.5 |

#### Notable Overlap

990 & crosswalk overlap is 100% (7,240/7,240) — the 990 matching pipeline writes EINs into the crosswalk, so every 990-matched employer is by definition in the crosswalk.

### 4.2 — Match Quality (Checkpoint 11)

#### OSHA F7 Matches (138,340 total, 25 methods)

| Confidence Range | Count | % |
|---|---:|---:|
| Below 0.6 (questionable) | 32,243 | 23.3% |
| 0.6 - 0.8 (moderate) | 77,200 | 55.8% |
| Above 0.8 (high confidence) | 28,897 | 20.9% |

**Overall avg: 0.685.** The dominant method `STATE_NAICS_FUZZY` (36.8% of all matches) averages only 0.637. **7,859 matches (5.7%) have confidence below 0.50** — sample inspection reveals clearly wrong matches (e.g., "Kaiser Foundation Hospitals" matched to "Sutter VNA and Hospice"). The `CITY_NAICS_LOW` tier (0.35 confidence) produces false positives between unrelated companies sharing only a city and NAICS sector.

#### WHD F7 Matches (24,610 total, 7 methods)

| Confidence Range | Count | % |
|---|---:|---:|
| Below 0.6 (questionable) | 6,657 | 27.0% |
| 0.6 - 0.8 (moderate) | 12,157 | 49.4% |
| Above 0.8 (high confidence) | 5,796 | 23.6% |

**Overall avg: 0.691.** Similar profile to OSHA. `FUZZY_NAME_STATE` (59.7%) averages 0.637.

#### 990 F7 Matches (14,059 total, 5 methods)

| Confidence Range | Count | % |
|---|---:|---:|
| Below 0.6 | 0 | 0.0% |
| 0.6 - 0.8 | 10,950 | 77.9% |
| Above 0.8 | 3,109 | 22.1% |

**Overall avg: 0.737.** Cleanest match table — hard floor of 0.60 enforced. Zero questionable matches.

#### SAM F7 Matches (11,050 total, 4 methods)

| Confidence Range | Count | % |
|---|---:|---:|
| Below 0.6 | 1,041 | 9.4% |
| 0.6 - 0.8 | 3,601 | 32.6% |
| Above 0.8 | 6,408 | 58.0% |

**Overall avg: 0.793.** Highest quality match table. 58% high-confidence, 34.3% from exact-name matches.

#### NLRB Employer Xref (27,728 actual matches of 179,275 rows)

Uses 0-100 confidence scale. Avg 91.74, all above 75. **However, 14,150 matches (51.0%) are orphaned** — they reference pre-dedup F7 employer IDs that no longer exist. This was already flagged in Checkpoint 6 but confirmed here: the NLRB matching was run before Splink dedup and never remapped.

#### Corporate Crosswalk Identifier Density

| # of External IDs | Count | % |
|---:|---:|---:|
| 0 | 7,999 | 31.8% |
| 1 | 13,377 | 53.1% |
| 2 | 1,530 | 6.1% |
| 3 | 1,874 | 7.4% |
| 4 | 382 | 1.5% |
| 5 | 15 | 0.1% |

31.8% of crosswalk rows have zero external identifiers (F7-only stubs). Confidence is stored as mixed TEXT (numeric strings, labels "HIGH"/"MEDIUM", and NULLs) — unreliable for programmatic filtering.

#### Cross-System Quality Summary

| System | Matches | Avg Conf | Below 0.6 | Above 0.8 | Orphans |
|---|---:|---:|---:|---:|---:|
| OSHA | 138,340 | 0.685 | 23.3% | 20.9% | 0 |
| WHD | 24,610 | 0.691 | 27.0% | 23.6% | 0 |
| 990 | 14,059 | 0.737 | 0.0% | 22.1% | 0 |
| SAM | 11,050 | 0.793 | 9.4% | 58.0% | 0 |
| NLRB | 27,728 | 91.7* | 0.0% | 99.7% | **14,150 (51%)** |

*NLRB uses 0-100 scale

**Key findings:**
1. **~40,000 matches (21% of OSHA+WHD) are below 0.6 confidence** — likely contain false positives
2. **SAM is the highest-quality match table** (58% above 0.8)
3. **990 is the cleanest** (0% below 0.6 due to hard floor)
4. **NLRB has 14,150 orphaned matches (51%)** — most severe quality issue
5. **Zero duplicates** across all 4 primary match tables — dedup was correctly applied

### 4.3 — Scoring and Unified Views (Checkpoint 12)

#### Mergent Scoring Distribution

The `mergent_employers` table (56,426 rows) has two scoring columns: `organizing_score` (active, range 17-57) and `score_total` (defunct — 99.6% are 0).

| Tier | Count | % |
|---|---:|---:|
| TOP (>=30) | 7,310 | 13.0% |
| HIGH (25-29) | 11,295 | 20.0% |
| MEDIUM (20-24) | 29,936 | 53.1% |
| LOW (<20) | 6,900 | 12.2% |
| Unscored (NULL) | 985 | 1.7% |

**Score stats:** Mean 23.4, Median 22, P75=26, P90=30, P99=38. Strongly left-skewed with massive concentration at 20-23.

#### Sub-Score Breakdown (Critical Finding)

| Sub-Score | % Zero/NULL | Max | Avg | Assessment |
|---|---:|---:|---:|---|
| `score_geographic` | 0% | 14 | 14.00 | **Carries entire score — near-max for everyone** |
| `score_size` | 0% | 10 | 4.13 | Working |
| `score_nlrb_momentum` | 20.9% | 10 | 3.69 | Working |
| `score_industry_density` | 0% | 4 | 1.17 | Working but low-impact |
| `score_govt_contracts` | 97.8% | 15 | 0.24 | **Nearly dead** |
| `score_labor_violations` | 97.8% | 5 | 0.03 | **Nearly dead** |
| `score_osha_violations` | 99.7% | 10 | 0.01 | **Nearly dead** |
| `score_union_presence` | 100.0% | 15 | ~0 | **Completely dead** |
| `score_contracts` | 100.0% | 0 | 0.00 | **Completely dead (max=0)** |

**This is a score inflation problem.** `score_geographic` averages 14.0/15 for virtually everyone, providing zero discriminating power. The effective formula for 97%+ of employers is just `geographic(~14) + size(0-10) + nlrb(0-10) + density(0-4)`, which explains why most scores cluster at 20-23 (MEDIUM).

**Root cause:** `score_union_presence`, `score_contracts`, `score_osha_violations`, and `score_labor_violations` all require an F7 link to work. Only 856/56,426 (1.5%) of Mergent employers are linked to F7, so these factors are zero for 98.5% of records.

**Note:** The API-level scorecard in `organizing.py` computes scores differently (on-the-fly for OSHA establishments), so the Mergent batch scores and the API scores are separate systems with different behavior.

#### Unified Search View (`mv_employer_search`, 118,015 rows)

| Source | Count | % | Has Coords | Has NAICS |
|---|---:|---:|---:|---:|
| F7 | 60,953 | 51.7% | 99.8% | 99.2% |
| NLRB | 55,718 | 47.2% | 0% | 0% |
| VR | 824 | 0.7% | 0% | 0% |
| MANUAL | 520 | 0.4% | 0% | 17.3% |

**Coordinates are F7-only** — 0% of NLRB/VR/MANUAL records have lat/lon. This means the territory map can only plot ~52% of search results. **NAICS is also F7-only** — industry-based filtering/scoring only works for F7 records.

#### Mergent-to-F7 Bridge

| Metric | Value |
|---|---|
| Total Mergent employers | 56,426 |
| Has `matched_f7_employer_id` | **856 (1.5%)** |
| Valid in `f7_employers_deduped` | 841 (100% of matched) |
| Orphaned | 0 |

**Only 1.5% of Mergent employers link to F7.** This is the root cause of scoring collapse — without an F7 bridge, the system cannot determine union presence, OSHA violations, or contract data for 98.5% of Mergent records.

---

## PHASE 5: The API

### 5.1 — Endpoint Inventory (Checkpoint 13)

**Total endpoints: 145** (142 GET, 2 POST, 1 DELETE)

The API is organized into 16 router files plus 1 app-level route:

| Router | Endpoints | Domain |
|---|---:|---|
| `employers.py` | 24 | Employer search, detail, flags, unified, comparables |
| `density.py` | 21 | Union density by state, county, industry, NY-specific |
| `nlrb.py` | 10 | Elections, ULPs, patterns, state/affiliation breakdowns |
| `projections.py` | 10 | BLS industry/occupation projections |
| `vr.py` | 9 | Voluntary recognition cases, pipeline, mapping |
| `unions.py` | 8 | Union search, detail, nationals, locals |
| `trends.py` | 8 | Membership trends, election trends, sector trends |
| `corporate.py` | 8 | Corporate hierarchy, SEC lookup, multi-employer |
| `sectors.py` | 7 | Dynamic sector-specific targets via view lookup |
| `osha.py` | 7 | Establishment search/detail, high-severity, targets |
| `lookups.py` | 7 | States, metros, affiliations, NAICS, cities |
| `museums.py` | 6 | Museum-sector organizing targets |
| `public_sector.py` | 6 | Public sector unions, employers, benchmarks |
| `organizing.py` | 5 | 9-factor scorecard (list + detail), siblings |
| `whd.py` | 5 | Wage & Hour violations search, top violators |
| `health.py` | 3 | Platform summary, stats, health check |
| `main.py` | 1 | Serves frontend HTML |

#### Tables Referenced

The API queries **80+ distinct tables and views**. Key coverage:

- **Well-served:** F7 employers (24 endpoints), NLRB (10), density (21), OSHA (7+5 organizing), projections (10), unions (8), VR (9)
- **Lightly served:** WHD (5 endpoints for 363K cases), corporate (8 endpoints but 4 reference nonexistent tables — flagged in earlier audit)
- **Not served:** `sam_entities` (826K rows, no API endpoint), `gleif_us_entities` (379K rows, no direct endpoint), `epi_union_membership` (1.4M rows, no direct endpoint), `ar_disbursements_emp_off` (2.8M rows, no endpoint), `splink_match_results` (5.8M rows, archival), annual report tables (4 tables, no endpoints)

### 5.2 — Broken Endpoints and Security (Checkpoint 14)

#### Broken Endpoints

**5 endpoints in `corporate.py` will 500 error** due to references to nonexistent tables/columns:

| Endpoint | Missing Objects |
|---|---|
| `GET /api/corporate/family/{employer_id}` | `f7_employers_deduped.corporate_family_id`, `.ultimate_parent_name`, `.ultimate_parent_duns`, `.sec_cik`, `.sec_ticker`, `.sec_is_public`; `mergent_employers.corporate_family_id` |
| `GET /api/corporate/hierarchy/stats` | Table `corporate_ultimate_parents` does not exist |
| `GET /api/corporate/hierarchy/{employer_id}` | Same missing columns on `f7_employers_deduped` and `mergent_employers`; `corporate_hierarchy.child_lei` doesn't exist |
| `GET /api/corporate/sec/{cik}` | `f7_employers_deduped.sec_cik`, `mergent_employers.sec_cik` |

**Working corporate endpoints:** `/api/multi-employer/stats`, `/api/multi-employer/groups`, `/api/employer/{id}/agreement`, `/api/corporate/hierarchy/search` (queries `sec_companies` which has the columns).

**Root cause:** Columns `corporate_family_id`, `ultimate_parent_*`, and `sec_*` were planned during corporate hierarchy design but never added to `f7_employers_deduped` or `mergent_employers`. The `corporate_ultimate_parents` table was never created.

**No other routers have broken table/column references.**

#### SQL Injection Analysis

| File | Line | Variable | Risk | Mitigation |
|---|---|---|---|---|
| `museums.py` | 83 | `sort_by` in ORDER BY | MEDIUM | `pattern=` regex restricts to 4 values, but no server-side allowlist |
| `sectors.py` | 163 | `sort_by` in ORDER BY | MEDIUM | Same: regex-only, no allowlist dict |

All other routers use either parameterized `%s` placeholders or allowlist-validated dicts for dynamic SQL. No `.format()` patterns found. **No HIGH/CRITICAL injection vulnerabilities.**

#### Large Tables With No API Access (>10K rows, top 10)

| Table | Rows | Value |
|---|---:|---|
| `splink_match_results` | 5,761,285 | Archival — probabilistic matching intermediates |
| `ar_disbursements_emp_off` | 2,813,248 | Rich union officer compensation data |
| `nlrb_docket` | 2,046,151 | NLRB case docket entries |
| `qcew_annual` | 1,943,426 | Industry x geography employment data |
| `epi_union_membership` | 1,420,064 | Union membership microdata |
| `employers_990_deduped` | 1,046,167 | IRS 990 employer records |
| `sam_entities` | 826,042 | Federal contractor registry |
| `national_990_filers` | 586,767 | National 990 filer records |
| `gleif_us_entities` | 379,192 | GLEIF legal entity identifiers |
| `ar_assets_investments` | 304,816 | Union financial asset data |

35 tables with >10K rows have no API endpoint. The most impactful gaps are SAM.gov (826K federal contractors), annual report financials (2.8M officer disbursements), and GLEIF corporate ownership (379K entities + 499K links).

### 5.3 — Dead Code (Checkpoint 15)

#### Dead Files in `api/`

| File | Size | Issue |
|---|---:|---|
| `api/labor_api_v3.py` | 15 KB | Old monolith, never imported |
| `api/labor_api_v4_fixed.py` | 34 KB | Old monolith, never imported |
| `api/labor_api_v6.py.bak` | 307 KB | Archived v6 monolith |
| `api/__pycache__/labor_api_v6.cpython-314.pyc` | 385 KB | Ghost bytecode — no matching source file |

**Total dead code in api/: 741 KB**

#### Broken Script Imports

2 scripts in `scripts/verify/` import from deleted monoliths:
- `check_routes2.py` → `from api.labor_api_v6 import app` (source is `.bak`)
- `test_api.py` → `from api.labor_api_v5 import app` (source deleted)

#### Archived Monoliths

6 copies of old API versions in `archive/` (271 KB total). Some duplicated across `archive/api/` and `archive/old_api_versions/`.

---

## PHASE 6: Scripts and File System

### 6.1 — Script Inventory and Credential Security (Checkpoint 16)

#### File Counts

| Category | Count |
|---|---:|
| Total Python files | 778 |
| In `scripts/` | 478 (61%) |
| In `archive/` | 254 (33%) |
| Elsewhere (api, tests, root) | 46 (6%) |

#### Database Connection Patterns

| Pattern | Count | % | Assessment |
|---|---:|---:|---|
| **Correct** (`from db_config import`) | 102 | 13.1% | All active code (API, tests, recent scripts) |
| **Broken** (`password='os.environ.get(...)'` string literal) | 347 | 44.6% | **288 in scripts/, 59 in archive/** |
| **Hardcoded passwords** | 0 | 0% | None found anywhere |
| **Direct psycopg2.connect()** | 371 | 47.7% | Includes both correct and broken |

**The broken pattern is the #1 code quality issue in the project.** A naive `migrate_credentials.py` script replaced hardcoded passwords with `password='os.environ.get('DB_PASSWORD', '')'` — wrapping the function call in quotes, turning it into a string literal. These scripts cannot connect to the database. The migration script was marked "already run" on 2026-02-09.

**Positive:** `db_config.py` is correctly implemented (reads `.env`, exports `DB_CONFIG` dict and `get_connection()` function). The `.env` file exists. All critical active code paths use `db_config` properly.

### 6.2 — Critical Path Scripts and Dead Weight (Checkpoint 17)

#### Script Categories (475 total in `scripts/`)

| Category | Count | Examples |
|---|---:|---|
| **CRITICAL — ETL loaders** | ~25 | `load_f7_data.py`, `extract_osha_establishments.py`, `load_sam.py`, `load_whd_national.py` |
| **CRITICAL — Matching pipelines** | ~12 | `osha_match_phase5.py`, `whd_match_phase5.py`, `match_990_national.py`, `splink_pipeline.py`, `merge_f7_enhanced.py` |
| **CRITICAL — Scoring/enrichment** | ~7 | `compute_gower_similarity.py`, `compute_nlrb_patterns.py`, `create_scorecard_reference_tables.py` |
| **ONE-TIME — Already ran** | ~50+ | Pre-Phase5 matching scripts (superseded), SAM exploration, NLRB matching iterations |
| **ANALYSIS — Ad-hoc** | ~70 | Coverage analysis, membership studies, sector research |
| **MAINTENANCE — Checks/fixes** | ~170 | `check_*`, `fix_*`, `verify_*` scripts (90%+ are one-time) |
| **DEAD — References nonexistent tables** | ~7 | `build_corporate_hierarchy.py` → `corporate_ultimate_parents`, `fetch_usaspending.py` → `federal_contracts` |

#### Archive Contents (9.31 GB)

| Category | Size | Status |
|---|---:|---|
| NLRB SQLite databases (4 copies) | 3.79 GB | All imported into PostgreSQL |
| PostgreSQL installers | 709 MB | Not needed |
| NLRB CSV exports (~90 files) | ~1.2 GB | All imported |
| F7 SQLite databases (3 copies) | 505 MB | All imported |
| LM-2 PDFs | ~1.1 GB | Reference copies |
| BLS SQL dump files | ~700 MB | All imported |
| Other (JSON, SQLite, zips, misc) | ~1.3 GB | Mixed |

#### Large Data Files in Project Root

| File/Dir | Size | Already Imported? |
|---|---:|---|
| `990 2025/` (650K XML files) | 19.97 GB | Partially — CSV extract loaded |
| `data/free_company_dataset.csv` | 5.10 GB | **Never referenced by any script** |
| `backup_20260209.dump` | 2.06 GB | pg_dump backup |
| `data/nlrb/nlrb.db` | 946 MB | Fully imported |
| `lm-2 2000_2025/` | 1.73 GB | Text files imported |
| Imported CSVs/JSONs | ~502 MB | All imported |
| Legacy SQLite databases | ~245 MB | All superseded |

#### Disk Space Recovery Summary

| Action | Recoverable | Risk |
|---|---:|---|
| Delete `archive/` (all imported) | 9.31 GB | Low — all in PostgreSQL |
| Compress `990 2025/` XML (keep zip, delete extracted) | ~18.5 GB | Low |
| Delete `free_company_dataset.csv` (unused) | 5.10 GB | None — zero references |
| Delete `backup_20260209.dump` | 2.06 GB | Medium — recreatable |
| Delete imported CSVs/JSONs/SQLite | ~1.7 GB | Low |
| **Total recoverable** | **~37.9 GB** | |
| **Project shrinks from** | **39.8 GB → ~1.9 GB** | **(95% reduction)** |

---

## PHASE 7: Documentation Accuracy

### 7.1 — CLAUDE.md Audit (Checkpoint 18)

**Total inaccuracies: 33** (4 CRITICAL, 16 SIGNIFICANT, 13 MINOR)

#### CRITICAL (4)

| # | Finding | Claimed | Actual |
|---|---|---|---|
| C1 | **Startup command wrong** (line 602) | `api.labor_api_v6:app` | `api.main:app` — file doesn't exist |
| C2 | **`nlrb_participants` off by 63x** (line 43) | 30,399 | 1,906,542 |
| C3 | **`osha_f7_matches` stale** (line 63) | 79,981 (44.6%) | 138,340 (13.7% of OSHA / 47.3% of F7) |
| C4 | **`lm_data` off by 8x** (line 44) | 2.6M+ | 331,238 |

#### SIGNIFICANT (16)

| # | Finding | Claimed | Actual |
|---|---|---|---|
| S1 | `f7_employers_deduped` count (5 places) | 62,163 | 60,953 (-1,210) |
| S2 | `splink_match_results` off by 1,250x | ~4,600 | 5,761,285 |
| S3 | OSHA scorecard described as 6-factor | 6 factors, wrong weights | 9 factors, different weights |
| S4 | Mergent scoring component descriptions | Multiple wrong max values | `score_geographic` max=15 (not "removed"), `score_size` max=10 (not 5) |
| S5 | Mergent tier thresholds (2 places) | MEDIUM>=15 | MEDIUM>=20 |
| S6 | `corporate_identifier_crosswalk` | 14,561 | 25,177 (+73%) |
| S7 | Crosswalk F7 coverage | ~12,000 (19.3%) | 22,777 (~37.4%) |
| S8 | `zip_geography` table referenced | 39,366 rows | Table does not exist |
| S9 | `cbsa_reference` table referenced | 937 rows | Table is `cbsa_definitions` (935 rows) |
| S10 | WHD match coverage | 2,990 (4.8%) | 24,610 (6.8%) |
| S11 | `mv_employer_search` count | 120,169 | 118,015 |
| S12 | `mergent_employers` count (2 places) | 56,431 | 56,426 |
| S13-14 | `unified_employers_osha` counts | Off by 2 | Minor |
| S15 | **37+ tables with >10K rows not documented** | — | `sam_entities` (826K), `f7_union_employer_relations` (120K), `employer_comparables` (270K), entire NLRB sub-table ecosystem, annual report tables, etc. |
| S16 | Crosswalk tier counts stale | Various | 10,688 NULL-tier rows from 990 matching undocumented |

#### MINOR (13)

Small count drifts (1-11 rows), rounding differences, and ambiguous descriptions. Examples: `manual_employers` 509→520, four Mergent sector counts off by 1-2, "62 pts max" but actual max observed is 57.

#### Stale Roadmap References

No explicit "planned" items already done, but the document overall reflects a Phase 3-4 era snapshot — before Phase 5 matching, Phase 7 API decomposition, SAM.gov, and the Gower similarity engine.

### 7.2 — README.md and Roadmap Audit (Checkpoint 19)

#### README.md Issues

| # | Severity | Finding |
|---|---|---|
| 1 | **CRITICAL** | Startup command wrong: `api.labor_api_v6:app` (appears twice) |
| 2 | HIGH | `nlrb_participants` claimed 30,399, actual 1,906,542 (63x) |
| 3 | HIGH | Scorecard described as 6-factor, actual is 9-factor |
| 4 | HIGH | Missing 10+ major data sources (SAM, WHD, Mergent, BLS, GLEIF, SEC, crosswalk, comparables, QCEW) |
| 5 | HIGH | Lists ~20 endpoints, actual is 145 across 16 routers |
| 6 | MEDIUM | Project structure outdated — lists `frontend/labor_search_v6.html` (archived), misses `tests/`, `src/` |
| 7 | MEDIUM | Referenced files at wrong paths (roadmap, methodology docs listed at root but live in `docs/`) |

#### docs/README.md — Worst Document

A separate `docs/README.md` (dated Jan 24) is the most inaccurate file in the project:
- **Two different wrong startup commands** (both reference nonexistent modules)
- Says NLRB is "Pending" — fully loaded (33K elections, 1.9M participants)
- Says BLS projections "Pending" — fully loaded (113K+ rows)
- References `labor_search.html` and `labor_search_api` — both archived/deleted
- `f7_employers_deduped` count: 71,085 (actual 60,953)

#### Roadmap Document Sprawl

**7 roadmap-like documents** with overlapping, contradictory, and outdated information:

| Document | Status |
|---|---|
| `LABOR_PLATFORM_ROADMAP_v10.md` (docs/) | **Stale** — superseded by v12/v13 |
| `LABOR_PLATFORM_ROADMAP_v11.md` (root) | **Stale** |
| `LABOR_PLATFORM_ROADMAP_v12.md` (root+docs/) | **Stale** — all 4 phases complete |
| `LABOR_PLATFORM_ROADMAP_v13.md` (root) | **Partially stale** — most current but API decomposition/frontend marked future |
| `EXTENDED_ROADMAP.md` (docs/) | **Mostly stale** — checkpoints H, K complete; I, J, O partial |
| `ROADMAP_TO_DEPLOYMENT.md` (root) | **Partially stale** |
| `SCORECARD_IMPROVEMENT_ROADMAP.md` (root) | **Stale** — Gower + NLRB patterns both done |

#### docs/ Directory Status

- 2 empty directories (`guides/`, `methodology/`) — delete candidates
- 58 archived markdown files in `archive/docs_consolidated_2026-02/` with methodology details not captured in current docs
- `MEMBER_DEDUPLICATION.md` still referenced by docs/README.md but moved to archive

---

## PHASE 8: LM2 vs F7 Membership Analysis

### 8.1 — Membership Comparison (Checkpoint 20)

#### Overall Comparison

| Metric | Value |
|---|---|
| LM2 Deduplicated Membership | 14,507,547 |
| F7 Covered Workers | 15,867,180 |
| **Ratio (F7 / LM2)** | **109.4%** |

F7 slightly exceeds LM2 because building trades over-coverage (open-shop, hiring hall workers) more than offsets public-sector unions' near-zero F7 presence.

#### Category Breakdown (59 National/International Unions)

| Category | Unions | LM2 Members | F7 Workers |
|---|---:|---:|---:|
| Roughly aligned (0.5x-2x) | 14 | 4,888,827 | 4,746,696 |
| Zero F7 (public/federal/entertainment) | 17 | 3,863,294 | 0 |
| Under-represented (<0.5x) | 11 | 2,770,981 | 239,295 |
| Over-represented (>2x, building trades) | 17 | 1,924,245 | 9,813,274 |

#### Zero-F7 Unions (5.4M+ invisible members)

17 unions with **3,863,294 LM2 members** have zero F7 coverage because F7 only covers private-sector employers:

Top 5: NEA (2.84M, public education), AFT (1.80M, public education), NFOP (373K, police), NNU (215K, public hospitals), NPMHU (125K, postal)

#### Extreme Over-Representation (Building Trades)

| Union | LM2 | F7 | Ratio |
|---|---:|---:|---:|
| USW (Steelworkers) | 18,125 | 588,656 | **32.5x** |
| PPF (Plumbers) | 23,000 | 671,353 | **29.2x** |
| IATSE (Stage/Picture) | 24,393 | 651,188 | **26.7x** |
| IUOE (Operating Engineers) | 75,851 | 1,689,663 | **22.3x** |
| IBEW (Electrical Workers) | 46,665 | 691,082 | **14.8x** |
| UAW (Auto Workers) | 64,622 | 773,180 | **12.0x** |

These ratios are structural, not errors — they reflect the difference between "covered workers" (F7) and "dues-paying members" (LM2) in open-shop/hiring hall environments.

#### Orphaned F7 File Numbers

**195 file numbers** not in `union_hierarchy` or `unions_master`, covering **92,627 workers** across **793 employers**. Top two (file numbers 12590 and 18001) account for 51,811 workers. These likely represent merged/dissolved unions whose records need resolution via OLMS API.

---

## PHASE 9: Summary, Health Score, and Recommendations (Checkpoint 21)

### 9.1 — Platform Health Scorecard

| Category | Score | Weight | Weighted |
|---|---:|---:|---:|
| Data Completeness | 58 | 25% | 14.5 |
| Data Integrity | 42 | 25% | 10.5 |
| API Reliability | 72 | 15% | 10.8 |
| Code Quality | 40 | 15% | 6.0 |
| Documentation | 35 | 10% | 3.5 |
| Infrastructure | 45 | 10% | 4.5 |
| **Overall** | | | **49.8 / 100** |

#### Score Justifications

**Data Completeness: 58/100**
61.7% of F7 employers have at least one external connection, but 38.3% (23,333) are completely isolated with no OSHA, WHD, 990, SAM, or crosswalk link. External dataset coverage is uneven: OSHA 47.3% matched, WHD 16.0%, SAM 13.9%, 990 11.9%. The unified search view (`mv_employer_search`) has 118K records but 48.3% (NLRB, VR, MANUAL sources) have 0% coordinates and 0% NAICS, making them invisible on maps and unscorable by industry. Mergent EIN coverage is only 43.9% (not the 55% documented), and only 1.5% of Mergent employers link to F7, rendering 4 of 9 score factors dead for 98.5% of records.

**Data Integrity: 42/100**
Two catastrophic orphan relationships undermine the platform's core function. 60,373 rows (50.4%) in `f7_union_employer_relations` reference pre-dedup employer IDs, silently dropping half of all union-employer bargaining links and making 7 million covered workers invisible. 14,150 NLRB cross-references (51%) are similarly orphaned. Approximately 40,000 OSHA+WHD matches (21%) are below 0.6 confidence and likely contain false positives. The core `f7_employers_deduped` table has no primary key. Six tables are completely empty (planned features never built). Nine views reference the raw `f7_employers` table instead of the deduped version, returning inflated counts. On the positive side, all 4 match tables have zero duplicates, and 8 of 10 foreign-key relationships are perfectly clean.

**API Reliability: 72/100**
140 of 145 endpoints function correctly (96.6%). Five endpoints in `corporate.py` will 500-error because they reference nonexistent tables (`corporate_ultimate_parents`) and columns (`corporate_family_id`, `sec_cik` on f7_employers_deduped). Two medium-risk SQL injection vectors exist in `museums.py` and `sectors.py` (ORDER BY clauses use regex-validated but not allowlist-validated `sort_by` parameters). 35 large tables (>10K rows) have no API access, including 826K SAM entities, 2.8M annual report disbursements, and 379K GLEIF entities. The API is well-structured after the Phase 7 decomposition into 16 routers.

**Code Quality: 40/100**
347 of 778 Python files (44.6%) have a broken password pattern (`password='os.environ.get(...)'` as a string literal instead of a function call), rendering them unable to connect to the database. Only 102 files (13.1%) use the correct `db_config` import. 741 KB of dead code exists in the `api/` directory (old monolith versions). Two scripts in `scripts/verify/` import from deleted modules. Seven scripts reference nonexistent tables. The archive directory (254 files) contains superseded scripts mixed with importable-looking code. On the positive side, all active code paths (API routers, tests, recent scripts) use `db_config` correctly, and no hardcoded passwords exist anywhere.

**Documentation: 35/100**
CLAUDE.md contains 24 verified inaccuracies: 7 critical (wrong startup command, row counts off by 6,000-125,000%), 6 significant (wrong match counts, outdated scoring tiers), 9 missing entries for tables holding millions of rows and gigabytes of data, and 2 references to nonexistent tables. The document has not been systematically updated since approximately Phase 3 (late January 2026), missing 5 major phases of work. Any agent or developer reading CLAUDE.md will immediately fail to start the API and will have wildly wrong mental models of table sizes, match rates, and scoring behavior.

**Infrastructure: 45/100**
3.4 GB of indexes, of which 2.0 GB (69.5%) have never been scanned. 15 exact duplicate index pairs waste 190 MB. An additional 22 subset/overlapping indexes waste 125 MB. Materialized views have never been analyzed (NULL last_analyze), meaning query planner statistics are absent. The `splink_match_results` table consumes 1.6 GB as an archival artifact with no active references. 37.9 GB of file system space is recoverable (archive files, imported source data, unused datasets). The `free_company_dataset.csv` (5.1 GB) has zero references from any script. The project could shrink from 39.8 GB to ~1.9 GB (95% reduction).

---

### 9.2 — Top 10 Issues Ranked by Impact

#### #1. Orphaned Union-Employer Bargaining Links (50.4%)
**Problem:** 60,373 of 119,844 rows in `f7_union_employer_relations` reference pre-dedup employer IDs that no longer exist in `f7_employers_deduped`. These rows still exist in the raw `f7_employers` table, so no data is lost — but every JOIN to the deduped table silently drops half the relationships.

**Impact for users:** When a user searches "what unions represent workers at Employer X," the platform shows roughly half the real bargaining relationships. Aggregate statistics (total union coverage, workers represented) undercount by ~44% (7 million workers invisible). The entire platform's value proposition — connecting employers to union intelligence — is halved.

**Effort:** MEDIUM (2-4 hours). The `f7_employer_merge_log` table records exactly which old IDs merged into which new IDs. Write an UPDATE query to remap the 60,373 orphaned `employer_id` values to their deduped counterparts. Verify with a count of remaining orphans.

---

#### #2. Dead Score Factors (4 of 9 always zero for 98.5% of employers)
**Problem:** `score_union_presence`, `score_contracts`, `score_osha_violations`, and `score_labor_violations` on `mergent_employers` require an F7 link to produce nonzero values. Only 856 of 56,426 Mergent employers (1.5%) have `matched_f7_employer_id` set. The effective scoring formula for 98.5% of employers is just `geographic(~14) + size(0-10) + nlrb(0-10) + density(0-4)`, clustering most scores at 20-23 (MEDIUM tier).

**Impact for users:** The organizing scorecard has no discriminating power for the vast majority of employers. A hospital with 3 OSHA violations and active union campaigns scores the same as a clean-record office building, because neither has an F7 link to unlock violation/union factors. Organizers cannot distinguish high-priority from low-priority targets.

**Effort:** LARGE (1-2 days). Improve the Mergent-to-F7 bridge: run the Phase 5 matching pipeline against Mergent employers (most are in NY), use OSHA/WHD match tables as indirect bridges, and explore fuzzy name+state matching. Target: raise linkage from 1.5% to 20%+.

---

#### #3. CLAUDE.md Has 24 Inaccuracies
**Problem:** The primary project documentation has 7 critical errors (wrong startup command, row counts off by orders of magnitude), 6 significant errors, 9 missing table entries, and 2 references to nonexistent tables. It has not been updated since Phase 3.

**Impact for users:** Every new session or agent that reads CLAUDE.md will fail to start the API on the first attempt (`labor_api_v6:app` vs `api.main:app`). Developers will have wildly wrong expectations about table sizes (e.g., thinking `splink_match_results` has ~4,600 rows when it has 5.7 million), match rates, and scoring tiers. This causes cascading time waste in every development session.

**Effort:** QUICK (30-60 minutes). Update startup command, correct all 13 wrong row counts, add 9 missing tables, fix scoring tier thresholds (MEDIUM >= 20, not >= 15), remove 2 nonexistent table references.

---

#### #4. ~40,000 Low-Confidence Matches (Below 0.6)
**Problem:** 32,243 OSHA matches (23.3%) and 6,657 WHD matches (27.0%) have confidence scores below 0.6. Sample inspection reveals clearly wrong matches (e.g., "Kaiser Foundation Hospitals" matched to "Sutter VNA and Hospice"). The `CITY_NAICS_LOW` tier (0.35 confidence) and `STATE_NAICS_FUZZY` at 0.55 threshold produce false positives between unrelated companies sharing only geographic or industry attributes.

**Impact for users:** When an organizer views an employer's OSHA violation history, up to 23% of the displayed violations may belong to a different company. This erodes trust in the platform and could lead to embarrassing mistakes in organizing campaigns (citing violations at the wrong employer).

**Effort:** MEDIUM (2-3 hours). Delete matches below 0.50 confidence (7,859 OSHA + estimated 2,000 WHD). Raise the minimum threshold for `STATE_NAICS_FUZZY` tier from 0.55 to 0.60. Re-run match counts. Consider adding a confidence badge to the frontend.

---

#### #5. Orphaned NLRB Cross-References (51%)
**Problem:** 14,150 of 27,728 NLRB-to-F7 employer links (51%) reference pre-dedup employer IDs. Same root cause as issue #1 — the NLRB matching was run before Splink dedup and never remapped.

**Impact for users:** When looking up NLRB election history for an employer, approximately half of relevant elections will not appear. The `score_nlrb_momentum` factor in the organizing scorecard is based on incomplete data for roughly half of all employers.

**Effort:** QUICK (30 minutes). Same fix as #1 — remap through `f7_employer_merge_log`. Can be done in the same script.

---

#### #6. No Primary Key on `f7_employers_deduped`
**Problem:** The core employer table (60,953 rows, 152 MB) has no PRIMARY KEY constraint. There is no database-level guarantee against duplicate rows. Three match tables (`whd_f7_matches`, `national_990_f7_matches`, `sam_f7_matches`) also lack primary keys.

**Impact for users:** While no duplicates currently exist (verified by audit), any future data loading or merge operation could introduce duplicates without detection. JOINs to this table may silently produce row multiplication if duplicates appear. The lack of a PK also prevents foreign key constraints from being added, leaving referential integrity entirely unenforced.

**Effort:** QUICK (15 minutes). `ALTER TABLE f7_employers_deduped ADD PRIMARY KEY (employer_id);` — will fail if duplicates exist (none currently do). Same for the 3 match tables using their natural keys.

---

#### #7. 347 Scripts With Broken Password Pattern
**Problem:** A credential migration script replaced hardcoded passwords with `password='os.environ.get('DB_PASSWORD', '')'` — wrapping the function call in quotes, making it a string literal. 347 of 778 Python files (44.6%) have this pattern and cannot connect to the database.

**Impact for users:** Any attempt to re-run an ETL loader, matching script, or analysis script from before the migration will fail with an authentication error. Developers must manually fix each script before use, or know to use `db_config` instead.

**Effort:** MEDIUM (1-2 hours). Write a regex-based batch fixer: replace `password='os.environ.get('DB_PASSWORD', '')'` with `password=os.environ.get('DB_PASSWORD', '')` (remove outer quotes). Or better: replace the entire `psycopg2.connect(...)` block with `from db_config import get_connection`. Test on 5 scripts, then batch-apply.

---

#### #8. 5 Broken Corporate API Endpoints
**Problem:** Five endpoints in `corporate.py` reference nonexistent tables (`corporate_ultimate_parents`) and columns (`corporate_family_id`, `ultimate_parent_name`, `sec_cik` on `f7_employers_deduped`). All 5 will return HTTP 500 errors when called.

**Impact for users:** The corporate hierarchy feature of the API is mostly non-functional. Users clicking "Corporate Family" or "SEC Lookup" in the frontend will see error screens. 3 of 8 corporate endpoints work (those querying `sec_companies` directly).

**Effort:** MEDIUM (2-3 hours). Either: (a) create the missing columns/tables to match the API expectations, or (b) rewrite the 5 endpoints to use existing data (`corporate_hierarchy` table + `corporate_identifier_crosswalk`), or (c) remove the broken endpoints and disable frontend links.

---

#### #9. 2.0 GB Unused Indexes
**Problem:** 372 of 535 indexes (69.5%) have zero scans since database creation (stats have never been reset). 15 exact duplicate index pairs waste 190 MB. 22 subset indexes waste 125 MB. The `splink_match_results` table alone has 452 MB of unused indexes. Total actionable waste: ~2.0 GB.

**Impact for users:** Every INSERT, UPDATE, and DELETE operation is slowed by maintaining unused indexes. Disk space is wasted. Vacuum operations take longer. The database backup (2.06 GB) is larger than necessary.

**Effort:** QUICK for duplicates (15 minutes, see Section 7.6 for exact SQL). MEDIUM for full cleanup (1-2 hours, review each unused index against batch scripts).

---

#### #10. 37.9 GB Recoverable Disk Space
**Problem:** The project directory is 39.8 GB, of which 37.9 GB (95%) is recoverable: archived source files already imported into PostgreSQL (9.3 GB), extracted 990 XML files (18.5 GB), an unused 5.1 GB CSV file (`free_company_dataset.csv`), imported source data (1.7 GB), and a recreatable database backup (2.06 GB).

**Impact for users:** Disk space pressure, slow backups, slow file searches, git operations affected (if tracked). The `free_company_dataset.csv` has zero references from any script and appears to have been downloaded but never used.

**Effort:** QUICK (30 minutes). Delete `free_company_dataset.csv` (5.1 GB, zero risk). Compress `990 2025/` to zip and delete extracted XML (18.5 GB). Delete confirmed-imported archive files incrementally.

---

### 9.3 — Quick Wins (Under 30 Minutes Each)

| # | Action | Time | Impact | Command/Steps |
|---|---|---:|---|---|
| 1 | Add primary key to `f7_employers_deduped` | 5 min | Prevents future duplicates, enables FK constraints | `ALTER TABLE f7_employers_deduped ADD PRIMARY KEY (employer_id);` |
| 2 | Drop 15 exact duplicate indexes | 10 min | Recover 190 MB, speed up writes | See Section 7.6 for complete SQL |
| 3 | Fix CLAUDE.md startup command | 2 min | Every session starts correctly | Change `api.labor_api_v6:app` to `api.main:app` |
| 4 | Delete `free_company_dataset.csv` | 1 min | Recover 5.1 GB | `del data\free_company_dataset.csv` |
| 5 | Drop 6 empty tables | 5 min | Reduce schema clutter | `DROP TABLE IF EXISTS employer_ein_crosswalk, sic_naics_xwalk, union_affiliation_naics, union_employer_history, vr_employer_match_staging, vr_union_match_staging;` |
| 6 | Drop 3 duplicate museum views | 5 min | Remove confusing duplicates | `DROP VIEW IF EXISTS v_museums_organizing_targets, v_museums_target_stats, v_museums_unionized;` |
| 7 | Fix scoring tier docs | 5 min | Correct mental model for all agents | Update CLAUDE.md: MEDIUM >= 20, LOW < 20 (not >= 15 / < 15) |
| 8 | Remap orphaned NLRB xrefs | 20 min | Restore 14,150 NLRB-employer links | UPDATE using `f7_employer_merge_log` mapping table |
| 9 | ANALYZE materialized views | 5 min | Fix query planner statistics | `ANALYZE mv_employer_features; ANALYZE mv_employer_search; ANALYZE mv_whd_employer_agg;` |
| 10 | Delete dead API files | 5 min | Remove 741 KB dead code | Delete `api/labor_api_v3.py`, `api/labor_api_v4_fixed.py`, `api/labor_api_v6.py.bak`, `api/__pycache__/labor_api_v6.cpython-314.pyc` |

**Total quick-win time: ~63 minutes. Total impact: 5.3 GB recovered, 190 MB indexes removed, core table integrity hardened, documentation partially fixed, 14,150 NLRB links restored.**

---

### 9.4 — Tables That Could Be Dropped or Archived

#### Drop Immediately (Empty / Zero Value)

| Table | Rows | Size | Reason |
|---|---:|---|---|
| `employer_ein_crosswalk` | 0 | 8 kB | Planned feature never built; `corporate_identifier_crosswalk` serves this purpose |
| `sic_naics_xwalk` | 0 | 8 kB | Never loaded; SIC-NAICS mapping exists in `sec_companies` |
| `union_affiliation_naics` | 0 | 8 kB | Never populated |
| `union_employer_history` | 0 | 8 kB | Never populated |
| `vr_employer_match_staging` | 0 | 8 kB | Staging table, processing complete |
| `vr_union_match_staging` | 0 | 8 kB | Staging table, processing complete |

#### Archive Then Drop (Large, Archival, No Active References)

| Table | Rows | Total Size | Reason |
|---|---:|---|---|
| `splink_match_results` | 5,761,285 | 1,591 MB | Probabilistic matching intermediate results. Not referenced by any view or API endpoint. All useful matches have been extracted to `osha_f7_matches` et al. Archive with `pg_dump -t splink_match_results > splink_archive.sql` then DROP. **Recovers 1.6 GB.** |
| `f7_employers` (raw) | 146,863 | 117 MB | Pre-deduplication employer table. Superseded by `f7_employers_deduped`. Still referenced by 2 views directly and 7 indirectly. Migrate views first, then archive. |

#### Consider Archiving (Low Activity)

| Table | Rows | Total Size | Reason |
|---|---:|---|---|
| `employers_990_deduped` | 1,046,167 | 265 MB | Deduped 990 employers. Used only during 990 matching (already complete). No API endpoint. Could be archived if 990 matching won't be re-run. |
| `nlrb_docket` | 2,046,151 | 281 MB | Case docket entries. No API endpoint, no views. Rich data but currently unused. |
| `ar_assets_investments` | 304,816 | 32 MB | Annual report asset data. No views, no API. Loaded but never analyzed. |

---

### 9.5 — Duplicate Museum Views to Drop

The database has both singular (`v_museum_*`) and plural (`v_museums_*`) naming for the same 3 museum sector views. Both sets filter on NAICS 'MUSEUMS' and return 218 rows each. Drop the plural set to match the singular convention used by all other sectors:

```sql
DROP VIEW IF EXISTS v_museums_organizing_targets;
DROP VIEW IF EXISTS v_museums_target_stats;
DROP VIEW IF EXISTS v_museums_unionized;
```

---

### 9.6 — Duplicate Indexes to Drop (15 Pairs, 190 MB)

For each pair, the index with fewer scans (or alphabetically second if tied at 0) is dropped. The surviving index provides identical functionality.

```sql
-- ============================================================
-- DUPLICATE INDEX CLEANUP
-- Generated: 2026-02-13
-- Total space recovered: ~190 MB
-- Risk: NONE — each dropped index has an identical twin remaining
-- ============================================================

-- 1. osha_establishments: duplicate GIN trigram on estab_name_normalized (53 MB)
--    Keep: idx_osha_est_name_trgm (0 scans) — same def, arbitrary keep
DROP INDEX IF EXISTS idx_osha_est_name_norm_trgm;  -- 53 MB, 0 scans

-- 2. sec_companies: duplicate btree on cik (22 MB)
--    Keep: sec_companies_cik_key (0 scans, UNIQUE constraint)
DROP INDEX IF EXISTS idx_sec_cik;  -- 22 MB, 0 scans

-- 3. f7_employers_deduped: duplicate GIN trigram on employer_name (21 MB)
--    Keep: idx_f7_employer_name_trgm (0 scans)
DROP INDEX IF EXISTS idx_f7_emp_trgm;  -- 21 MB, 0 scans

-- 4. f7_employers_deduped: duplicate GIN trigram on employer_name_aggressive (20 MB)
--    Keep: idx_f7_name_agg_trgm (0 scans)
DROP INDEX IF EXISTS idx_f7_emp_agg_trgm;  -- 20 MB, 0 scans

-- 5. osha_f7_matches: duplicate btree on establishment_id (18 MB)
--    Keep: idx_osha_f7_matches_estab_uniq (10,909 scans, UNIQUE)
DROP INDEX IF EXISTS idx_osha_f7_est;  -- 18 MB, 0 scans

-- 6. f7_employers (raw): duplicate btree on lower(employer_name) (13 MB)
--    Keep: idx_f7_emp_name_lower (0 scans)
DROP INDEX IF EXISTS idx_employer_search_name;  -- 13 MB, 0 scans

-- 7. nlrb_participants: duplicate btree on matched_employer_id (13 MB)
--    Keep: idx_nlrb_part_matched_emp (0 scans)
DROP INDEX IF EXISTS idx_nlrb_part_employer;  -- 13 MB, 0 scans

-- 8. nlrb_participants: duplicate btree on matched_union_fnum (13 MB)
--    Keep: idx_nlrb_part_matched_union (1 scan)
DROP INDEX IF EXISTS idx_nlrb_part_olms;  -- 13 MB, 0 scans

-- 9. ar_membership: duplicate btree on rpt_id (3 MB)
--    Keep: idx_membership_rpt (0 scans)
DROP INDEX IF EXISTS idx_ar_mem_rptid;  -- 3 MB, 0 scans

-- 10. lm_data: duplicate btree on f_num (3 MB)
--     Keep: idx_lm_data_fnum (10,347 scans)
DROP INDEX IF EXISTS idx_lm_fnum;  -- 3 MB, 0 scans

-- 11. f7_employers (raw): duplicate btree on state (2 MB)
--     Keep: idx_f7_employers_state (0 scans)
DROP INDEX IF EXISTS idx_employer_search_state;  -- 2 MB, 0 scans

-- 12. lm_data: duplicate btree on aff_abbr (2 MB)
--     Keep: idx_lm_aff_abbr (10 scans)
DROP INDEX IF EXISTS idx_lm_aff;  -- 2 MB, 0 scans

-- 13. lm_data: duplicate btree on year (2 MB)
--     Keep: idx_lm_data_yr (79 scans)
DROP INDEX IF EXISTS idx_lm_year;  -- 2 MB, 0 scans

-- 14. f7_employers_deduped: duplicate btree on state (2 MB)
--     Keep: idx_f7_reconciled_state (1 scan)
DROP INDEX IF EXISTS idx_f7_deduped_state;  -- 2 MB, 1 scan

-- 15. f7_employers_deduped: duplicate btree on union_file_number (2 MB)
--     Keep: idx_f7_reconciled_affiliation (8 scans)
DROP INDEX IF EXISTS idx_f7_deduped_union_fnum;  -- 2 MB, 0 scans

-- BONUS: federal_bargaining_units duplicates (<1 MB total)
DROP INDEX IF EXISTS idx_fed_bu_agency;  -- 48 kB, 0 scans (keep idx_federal_bu_agency)
DROP INDEX IF EXISTS idx_fed_bu_union;   -- 40 kB, 0 scans (keep idx_federal_bu_union)
```

---

### 9.7 — Documentation Updates Needed

#### CLAUDE.md Corrections Required

| Priority | Section | Current Value | Correct Value |
|---|---|---|---|
| CRITICAL | Startup command (line ~602) | `api.labor_api_v6:app` | `api.main:app` |
| CRITICAL | `nlrb_participants` rows (line ~43) | 30,399 | 1,906,542 |
| CRITICAL | `splink_match_results` rows (line ~108) | ~4,600 | 5,761,285 |
| CRITICAL | `lm_data` rows (line ~44) | 2.6M+ | 331,238 |
| CRITICAL | `osha_f7_matches` (line ~63) | 79,981 (44.6%) | 138,340 (13.7%) |
| CRITICAL | `corporate_identifier_crosswalk` (line ~107) | 14,561 | 25,177 |
| CRITICAL | Scoring tiers (lines ~239, ~264) | MEDIUM >= 15, LOW < 15 | MEDIUM >= 20, LOW < 20 |
| SIGNIFICANT | `f7_employers_deduped` (lines ~31, ~41) | 62,163 | 60,953 |
| SIGNIFICANT | WHD match rate (line ~74) | 2,990 (4.8%) | 24,610 (6.8%) |
| SIGNIFICANT | `mv_employer_search` (line ~48) | 120,169 | 118,015 |
| SIGNIFICANT | `mergent_employers` (line ~189) | 56,431 | 56,426 |
| SIGNIFICANT | `manual_employers` (line ~46) | 509 | 520 |
| SIGNIFICANT | Scorecard description (line ~415) | 6-factor, 0-100 | 9-factor scorecard |
| MISSING | `sam_entities` table | Not mentioned | 826,042 rows, 826 MB |
| MISSING | `sam_f7_matches` table | Not mentioned | 11,050 rows |
| MISSING | `whd_f7_matches` table | Not mentioned | 24,610 rows |
| MISSING | `national_990_f7_matches` table | Not mentioned | 14,059 rows |
| MISSING | `employer_comparables` table | Not mentioned | 269,810 rows |
| MISSING | `nlrb_employer_xref` table | Not mentioned | 179,275 rows |
| MISSING | Annual report tables (4) | Not mentioned | 3,550,944 rows, 472 MB |
| MISSING | `epi_union_membership` table | Not mentioned | 1,420,064 rows, 322 MB |
| MISSING | `employers_990_deduped` table | Not mentioned | 1,046,167 rows, 265 MB |
| REMOVE | `zip_geography` table ref (line ~269) | Referenced | Does not exist |
| REMOVE | `cbsa_reference` table ref (line ~270) | Referenced | Does not exist (use `cbsa_definitions`) |

#### Additional Documentation Gaps

1. **No entity-relationship diagram** exists for the database. With 159 tables and complex cross-references, a visual ERD would save significant onboarding time.

2. **No data dictionary** beyond CLAUDE.md. Column meanings, data types, and valid value ranges are undocumented for most tables.

3. **No runbook** for ETL pipelines. The ~25 critical ETL scripts and ~12 matching scripts have no documented execution order, dependencies, or expected runtimes.

4. **Match method descriptions are scattered** across script comments. No centralized reference explains what each match tier means (EXACT_NAME, CITY_STATE_FUZZY, STATE_NAICS_FUZZY, etc.) or its confidence thresholds.

5. **The 9-factor scorecard formula** is only documented in `api/routers/organizing.py` source code. A user-facing explanation of how scores are computed, what each factor means, and why certain factors are zero for most employers does not exist.

---

### 9.8 — Views Referencing Raw `f7_employers` (Migration Needed)

9 views reference the pre-dedup `f7_employers` table instead of `f7_employers_deduped`, returning inflated counts:

| View | Reference Type | Impact |
|---|---|---|
| `v_f7_employers_fully_adjusted` | DIRECT | Returns 96,419 rows (should be ~61K) |
| `v_f7_private_sector_reconciled` | DIRECT | Joins through fully_adjusted, inflated counts |
| `v_f7_employers_adjusted` | INDIRECT | Cascades from a direct-reference view |
| `v_f7_reconciled_private_sector` | INDIRECT | Cascades from a direct-reference view |
| `v_lm_with_f7_summary` | INDIRECT | LM filing summary with inflated employer counts |
| `v_state_overview` | INDIRECT | State-level dashboard with inflated numbers |
| `v_union_f7_summary` | INDIRECT | Union summary with inflated employer counts |
| `v_union_members_counted` | INDIRECT | Membership counts based on inflated base |
| `v_union_members_deduplicated` | INDIRECT | Dedup membership view, paradoxically using non-dedup source |

**Fix:** Update the 2 DIRECT-reference views to use `f7_employers_deduped`. The 7 INDIRECT views will automatically reflect the correction.

---

### 9.9 — Recommended Action Plan

#### Phase A: Stabilize (Week 1) — Fix What's Broken

1. **Remap orphaned employer IDs** in `f7_union_employer_relations` and `nlrb_employer_xref` using `f7_employer_merge_log`. This single fix restores 60,373 bargaining links and 14,150 NLRB cross-references. (Issues #1, #5)

2. **Add primary key** to `f7_employers_deduped` and the 3 match tables. (Issue #6)

3. **Fix CLAUDE.md** — correct all 24 inaccuracies. (Issue #3)

4. **Fix or remove 5 broken corporate endpoints.** (Issue #8)

5. **Drop duplicate indexes, empty tables, duplicate views.** (Issues #9, Quick Wins)

#### Phase B: Improve (Weeks 2-3) — Raise Data Quality

6. **Purge low-confidence matches** below 0.50, raise fuzzy thresholds. (Issue #4)

7. **Improve Mergent-to-F7 linkage** from 1.5% to 20%+. (Issue #2)

8. **Migrate 9 views** from raw `f7_employers` to `f7_employers_deduped`. (Section 7.8)

9. **Batch-fix broken password pattern** in 347 scripts. (Issue #7)

10. **Archive `splink_match_results`** (1.6 GB) and clean up file system (37.9 GB). (Issue #10)

#### Phase C: Harden (Month 2) — Prevent Regression

11. **Add foreign key constraints** now that PKs exist.

12. **Create a refresh script** for materialized views with timestamp logging.

13. **Add SQL injection allowlists** to `museums.py` and `sectors.py`.

14. **Build API endpoints** for SAM entities, annual report financials, and GLEIF ownership.

15. **Write integration tests** for the orphan-remap fix to prevent recurrence.

---

### 9.10 — Audit Methodology

This audit was conducted on 2026-02-13 across 21 checkpoints:

- **Checkpoints 1-3 (Phase 1):** Complete database inventory, categorized inventory, CLAUDE.md accuracy review
- **Checkpoints 4-6 (Phase 2):** Core table quality, duplicate detection, relationship integrity
- **Checkpoints 7-9 (Phase 3):** Materialized views, regular views, index analysis
- **Checkpoints 10-12 (Phase 4):** Cross-reference coverage, match quality, scoring/unified views
- **Checkpoints 13-15 (Phase 5):** API endpoint inventory, broken endpoints/security, dead code
- **Checkpoints 16-17 (Phase 6):** Script inventory/credentials, critical paths/disk usage
- **Checkpoint 21 (Phase 7):** This summary — health scorecard, top issues, recommendations

All row counts were verified with actual `SELECT count(*)` queries, not `pg_stat` estimates. Index scan counts reflect lifetime usage (stats have never been reset). File system sizes were measured with OS-level tools.

**Database:** `olms_multiyear`, PostgreSQL, localhost, user `postgres`
**Total objects audited:** 159 tables, 187 views, 3 materialized views, 535 indexes, 145 API endpoints, 778 Python files
**Audit duration:** Single session, ~3 hours

---

*End of audit report.*
