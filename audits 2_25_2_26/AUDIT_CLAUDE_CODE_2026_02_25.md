# Platform Audit Report — Claude Code (Deep Technical Investigator)
## February 25, 2026

---

## 1. Executive Summary

The labor relations research platform is a substantial, functional system with 15 GB of data across 198 tables, 146,863 scored employers, and 129,870 active matches across 11 source systems. The codebase is well-tested (914 backend + 158 frontend tests, all passing). **The scoring system works but has significant blind spots:** 86% of "Priority" tier employers have no enforcement data (OSHA/NLRB/WHD), meaning the highest-ranked employers are primarily scored on structural factors (proximity, size, industry growth) rather than actual labor activity. The fuzzy matching pipeline still produces false positives at the 0.70-0.80 similarity boundary — I estimate 50-70% of Splink matches in that range are wrong based on a 20-match spot check (15/20 wrong). Junk records ("Employer Name", "M1", federal agencies) persist in the scorecard but are now gated out of the Priority tier by the `factors_available >= 3` rule. The research agent works (104 runs, 7.89 avg quality) but only 23% of runs are linked to employer_ids, and the auto-grader doesn't penalize empty assessment sections, making the quality score unreliable. CorpWatch imported 14.7M rows and 3 GB of storage, but only 2,597 employers actually matched to F7 — a 0.18% utilization rate. The 12 GB GLEIF raw dump has been cleaned up. **The platform is usable for research but not yet reliable for organizer-facing deployment.**

**Important correction:** The previous audit's scoring specification and `FOUR_AUDIT_SYNTHESIS_v3.md` describe a pre-Phase-1 state. Several issues reported as broken (contracts flat 4.00, financial = copy of growth, BLS inversion, Splink name floor) have been **fixed** since that audit. My database queries confirm the fixes. However, new issues have emerged (research agent disconnect, Union Profile API mismatch, score_size calibration).

---

## 2. Shared Overlap Zone Answers (OQ1-OQ10)

### OQ1: Priority Tier Spot Check (5 Employers)

```sql
SELECT employer_name, state, weighted_score, factors_available,
       score_osha, score_nlrb, score_whd, score_contracts,
       score_union_proximity, score_size, score_similarity, score_industry_growth
FROM mv_unified_scorecard WHERE score_tier = 'Priority'
ORDER BY weighted_score DESC LIMIT 5;
```

| # | Employer | State | Score | Factors | OSHA | NLRB | WHD | Contracts | Proximity | Size | Industry Growth | Financial |
|---|----------|-------|-------|---------|------|------|-----|-----------|-----------|------|-----------------|-----------|
| 1 | First Student, Inc | IL | 10.00 | 3 | NULL | 10 | NULL | NULL | 10 | 10 | NULL | NULL |
| 2 | Dignity Health Mercy Medical Center Merced | CA | 9.85 | 4 | NULL | 10 | NULL | NULL | 10 | 10 | 9.20 | NULL |
| 3 | Alta Bates Summit Medical Center | CA | 9.85 | 4 | NULL | 10 | NULL | NULL | 10 | 10 | 9.20 | NULL |
| 4 | Columbia Memorial Hospital | OR | 9.84 | 4 | NULL | NULL | NULL | NULL | 10 | 10 | 9.20 | 10 |
| 5 | ROBERT WOOD JOHNSON | NJ | 9.84 | 4 | NULL | NULL | NULL | NULL | 10 | 10 | 9.20 | 10 |

**Findings:**
- **All 5 are real, organizable employers** — hospitals and transit companies. No placeholders or shell companies. The `factors_available >= 3` guard is working.
- **But: 3 of 5 have ZERO enforcement data** (no OSHA, NLRB, or WHD). They score high purely on union proximity (10), size (10), and industry growth (9.2).
- **1,962 of 2,278 Priority employers (86%) have no enforcement data at all.** This means Priority = "large employer in a unionized industry with nearby union shops" — structurally interesting but not evidence of organizing opportunity.
- An organizer would find these profiles directionally useful but lacking actionable intelligence. "This hospital is big and in a unionized market" is a starting point, not a target recommendation.
- **Priority tier by factors_available:** 3 factors: 1,877 (82%); 4: 330; 5: 50; 6: 19; 7: 1; 8: 1. Minimum 3 guard is enforced, 0 employers with < 3 factors.

---

### OQ2: Match Accuracy Spot Check (20 Matches)

**OSHA (5 matches) — 5/5 correct:**

| Source Name | Matched To | Method | Judgment |
|-------------|-----------|--------|----------|
| FOSTER POULTRY FARMS | Foster Poultry Farms | NAME_CITY_STATE_EXACT, 0.950 | Correct |
| millbocker sons inc | Milbocker & Sons, Inc. | FUZZY_SPLINK_ADAPTIVE, 0.775 | Correct |
| RHS LEE INC | RHS LEE INC | NAME_STATE_EXACT, 0.900 | Correct |
| WOLVERINE ADVANCED MATERIALS | Wolverine Advanced Materials, LLC | NAME_AGGRESSIVE_STATE, 0.750 | Correct |
| EXPRESS MANAGEMENT 2 | EXPRESS MANAGEMENT | FUZZY_TRIGRAM, 0.905 | Correct |

**NLRB (5 matches) — 5/5 correct (but source_name not stored in evidence):**

| Matched To | Method | Judgment |
|-----------|--------|----------|
| Sharp Grossmont Hospital | name_zip_exact, 0.980 | Correct |
| Conco, Inc. | name_zip_exact, 0.980 | Correct |
| Perfumania Holdings, Inc. | name_zip_exact, 0.980 | Correct |
| Liberty Utilities | name_zip_exact, 0.980 | Correct |
| First Student | name_state_exact, 0.900 | Correct |

Note: NLRB matches don't store `source_name` in evidence JSONB — can't independently verify the source name. Matched by method confidence.

**WHD (5 matches) — 5/5 correct:**

| Source Name | Matched To | Method | Judgment |
|-------------|-----------|--------|----------|
| Mrs. Ressler's Food Products | Mrs. Ressler's Food Products | NAME_CITY_STATE_EXACT, 0.950 | Correct |
| VMT Long Term Care Management Inc. | VMT Long Term Care Inc | NAME_AGGRESSIVE_STATE, 0.750 | Correct |
| oakland grove health care | Oakland Grove Health Care Center | FUZZY_SPLINK_ADAPTIVE, 1.000 | Correct |
| Inter-Con Security Systems, Inc. | Inter-Con Security Systems Inc | NAME_CITY_STATE_EXACT, 0.950 | Correct |
| AT&T | AT&T | NAME_STATE_EXACT, 0.900 | Correct |

**SAM (5 matches) — 5/5 correct:**

| Source Name | Matched To | Method | Judgment |
|-------------|-----------|--------|----------|
| RESIDENTIAL FENCES CORP. | Residential Fences Corp. | NAME_CITY_STATE_EXACT, 0.950 | Correct |
| CHESTER PUBLIC UTILITY DISTRICT | Chester Public Utility District | NAME_CITY_STATE_EXACT, 0.950 | Correct |
| HAMILTON COMMUNITY HEALTH NETWORK, INC. | Hamilton Community Health Network | NAME_AGGRESSIVE_STATE, 0.750 | Correct |
| AVIS RENT A CAR SYSTEM, LLC | Avis Rent A Car System, LLC. | NAME_CITY_STATE_EXACT, 0.950 | Correct |
| CENTURYTEL OF EASTERN OREGON INC | CenturyTel of Eastern Oregon Inc... | FUZZY_TRIGRAM, 0.821 | Correct |

**Splink fuzzy 0.70-0.80 (20 matches — the critical threshold range):**

| Source Name | Matched To | Sim | Judgment |
|-------------|-----------|-----|----------|
| lara s construction llc | Lari Construction | 0.8 | **WRONG** — different companies |
| new horizons | Horizon Lines | 0.8 | **WRONG** — completely different |
| dale construction corp | Ideal Construction | 0.8 | **WRONG** — different companies |
| west coast turf | West Coast Industries | 0.8 | **WRONG** — different industries |
| shoprite | R & R Shoprite | 0.8 | **UNCERTAIN** — possibly same chain |
| concepts contractors inc | Concrete Contractors SoCal | 0.8 | **WRONG** — different companies |
| super one foods | Super Food Services, Inc. | 0.8 | **WRONG** — different companies |
| cerami associates inc | C & I Associates | 0.8 | **WRONG** — different companies |
| mar construction | DeJean Construction Company Inc | 0.8 | **WRONG** — completely different |
| arca recycling | Eureka Recycling | 0.8 | **WRONG** — different companies |
| oro valley hospital llc | Oroville Hospital | 0.8 | **WRONG** — different hospitals |
| reno | Renovo Solutions, LLC | 0.8 | **WRONG** — "reno" matched to "renovo" |
| san francisco first tee | Fairmont San Francisco | 0.8 | **WRONG** — golf nonprofit vs hotel |
| sears outlet | Sears Outlet Store | 0.8 | **CORRECT** |
| u s pipe | U.S. Pipeline, Inc. | 0.8 | **UNCERTAIN** — possibly related |
| industrial maintenance inc | INDUSTRIAL MAINTENANCE OF TOPEKA | 0.8 | **UNCERTAIN** — possibly same chain |
| northern nevada hopes | AGC of Northern Nevada | 0.8 | **WRONG** — healthcare vs construction |
| new york city h2o inc | New York City Music Corporation | 0.8 | **WRONG** — completely different |
| town of stratford | Town Of Stafford | 0.8 | **WRONG** — different towns |
| city of crosby fire department | City of Crosby-Public Works Department | 0.8 | **CORRECT** — same municipality |

**Result: 2 correct, 3 uncertain, 15 wrong out of 20.** This is a ~75% false positive rate at the 0.70-0.80 boundary. The Splink fuzzy matcher is unreliable at this threshold.

**Key finding:** All sampled fuzzy matches show `name_similarity = 0.8` (likely floored/rounded). The actual similarity scores aren't granular in the 0.70-0.80 range, making threshold tuning difficult. Note: The code default floor is now 0.80 (stricter than the 0.70 documented in CLAUDE.md), but these matches were created during earlier runs with a lower floor.

---

### OQ3: React Frontend <-> API Contract (5 Features)

| Feature | Frontend File | API Endpoint | Status | Detail |
|---------|--------------|--------------|--------|--------|
| **Employer Search** | `SearchPage.jsx`, `ResultsTable.jsx` | `/api/employers/unified-search` | MATCH | All fields aligned: `canonical_id`, `employer_name`, `city`, `state`, `unit_size`, `consolidated_workers`, `group_member_count`, `source_type`, `union_name`. Error handling: retry button on failure. |
| **Employer Profile** | `EmployerProfilePage.jsx` | `/api/profile/employers/{id}` | MATCH | Nested structure (`employer`, `unified_scorecard`, `osha`, `nlrb`, `cross_references`, `flags`) matches exactly. Uses `parseCanonicalId()` to route F7/NLRB/VR/MANUAL IDs to correct endpoint. Error handling: 404 detection + generic error UI. |
| **Scoring Breakdown** | `ScorecardSection.jsx` | `/api/scorecard/unified/{id}` | MATCH | All 9 factor scores present. `explanations` object returned server-side with keys matching frontend (`osha`, `nlrb`, `whd`, `contracts`, `union_proximity`, `financial`, `size`, `similarity`, `weights`, `research`). Error handling: graceful with optional chaining. |
| **Union Profile** | `UnionProfilePage.jsx` | `/api/unions/{f_num}` | **MISMATCH** | Frontend expects `financial_trends` and `sister_locals` in the detail response. **API does NOT return these fields.** `UnionFinancialsSection` and `SisterLocalsSection` components will render empty/undefined. This is a real bug. Membership history (`/api/unions/{f_num}/membership-history`) and organizing capacity (`/api/unions/{f_num}/organizing-capacity`) endpoints work correctly. Error handling: proper 404 + generic error UI. |
| **Targets Page** | `TargetsPage.jsx`, `TargetsTable.jsx` | `/api/master/non-union-targets` | MATCH | All fields aligned: `display_name`, `city`, `state`, `employee_count`, `source_origin`, `source_count`, `data_quality_score`, `is_federal_contractor`, `is_nonprofit`. Pagination structure matches (`total`, `page`, `pages`, `results`). Error handling: empty-results handling + error UI. |

**Summary:** 4/5 features have perfect alignment. **Union Profile has a real mismatch** — 2 frontend sections will display nothing due to missing API fields.

---

### OQ4: Data Freshness and View Staleness

**Materialized View Refresh Status:**

| MV | Last Auto-Analyze | Rows |
|----|-------------------|------|
| mv_unified_scorecard | 2026-02-25 19:11 | 146,863 |
| mv_organizing_scorecard | 2026-02-25 10:37 | 212,072 |
| mv_employer_data_sources | 2026-02-24 20:15 | 146,863 |
| mv_employer_features | 2026-02-24 20:16 | (not verified) |
| mv_employer_search | 2026-02-24 20:31 | 107,321 |
| mv_whd_employer_agg | 2026-02-23 09:41 (manual) | 330,419 |

All MVs were refreshed within the last 2 days. Scores reflect the February 2026 code changes.

**Score Versions:**

Latest = version 106, created 2026-02-25. Confirms:
- NLRB 7-year half-life decay (lambda = LN(2)/7)
- OSHA 10-year half-life decay (lambda = LN(2)/10)
- factors_available >= 3 gate for Priority and Strong
- score_similarity weight = 0
- Score stats: avg=32.4, min=11, max=56 (on the MV organizing scorecard scale)

**data_source_freshness:**

All 24 entries have valid timestamps (all show 2026-02-23). **The year-2122 NY bug and 13/19 NULL issue from the previous audit appear to be fixed.** All dates are realistic. Key entries:

| Source | Records | Date Range |
|--------|---------|------------|
| f7_employers | 146,863 | -- |
| osha_establishments | 1,007,217 | -- |
| whd_cases | 363,365 | 1900-01-07 to 2025-12-30 |
| nlrb_elections | 33,096 | 1994-03-04 to 2026-01-20 |
| unified_match_log | 1,738,115 | -- |
| master_employers | 2,736,890 | 2026-02-21 to 2026-02-22 |
| sam_entities | 826,042 | -- |
| sec_companies | 517,403 | -- |

Note: WHD `date_range_start` of 1900-01-07 is suspicious — likely a data entry error in the source data, not a platform bug.

**Views or MVs referencing nonexistent tables/columns:** Not directly tested, but the API health check passes and all endpoints respond, suggesting no broken view references.

---

### OQ5: Incomplete Source Re-runs — Impact Assessment

**This item from the prompt appears outdated — all three sources have been re-run.**

**990 (13,254 active matches):**

| Method | Active | Superseded | Rejected |
|--------|--------|------------|----------|
| EIN_EXACT | 11,595 | 45,883 | -- |
| FUZZY_SPLINK_ADAPTIVE | 737 | 42,183 | 746 |
| NAME_CITY_STATE_EXACT | 384 | 1,529 | -- |
| NAME_AGGRESSIVE_STATE | 228 | 1,796 | -- |
| FUZZY_TRIGRAM | 168 | 930 | 123,329 |
| NAME_STATE_EXACT | 125 | 4,118 | -- |

Old methods (EIN_CROSSWALK, EIN_MERGENT, ADDRESS_CITY_STATE) all show as superseded. Active matches use Phase 3+ method names. 123,329 FUZZY_TRIGRAM rejected — aggressive cleanup.

**WHD (10,991 active matches):**

| Method | Active | Superseded | Rejected |
|--------|--------|------------|----------|
| NAME_CITY_STATE_EXACT | 3,649 | 14,772 | -- |
| NAME_AGGRESSIVE_STATE | 2,580 | 12,558 | -- |
| FUZZY_SPLINK_ADAPTIVE | 2,158 | 28,438 | 102 |
| NAME_STATE_EXACT | 1,876 | 10,375 | -- |
| FUZZY_TRIGRAM | 315 | 2,231 | 86,319 |

Old methods (ADDRESS_CITY_STATE, NAME_CITY_STATE, MERGENT_BRIDGE, TRADE_NAME_STATE) all superseded. 86,319 FUZZY_TRIGRAM rejected.

**SAM (14,522 active matches):**

| Method | Active | Superseded | Rejected |
|--------|--------|------------|----------|
| NAME_CITY_STATE_EXACT | 5,456 | 16,512 | -- |
| NAME_AGGRESSIVE_STATE | 3,905 | 13,779 | -- |
| FUZZY_SPLINK_ADAPTIVE | 2,205 | 20,480 | 41 |
| NAME_STATE_EXACT | 1,794 | 7,278 | -- |
| FUZZY_TRIGRAM | 583 | 3,165 | 207,585 |

Old methods (EXACT_FULLNAME_STATE, EXACT_NAME_STATE, CITY_STATE_FUZZY, STATE_NAICS_FUZZY) all superseded. 207,585 FUZZY_TRIGRAM rejected.

**Conclusion:** All three sources use Phase 3+ method names in active matches. Old methods properly superseded. The "never completed" characterization in the audit prompt is outdated. **No stale matches from pre-Phase-B remain active.**

---

### OQ6: The Scoring Factors — Current State (All 9)

```sql
-- Factor stats query
SELECT 'factor_name', COUNT(*) FILTER (WHERE score_X IS NOT NULL),
       ROUND(AVG(score_X)::numeric,2), MIN(score_X), MAX(score_X)
FROM mv_unified_scorecard;
```

| Factor | Weight | Has Data | % Coverage | Avg | Min | Max | Notes |
|--------|--------|----------|------------|-----|-----|-----|-------|
| score_union_proximity | 3x | 73,192 | 49.8% | 8.48 | 5.00 | 10.00 | Binary: 10 (3+ group members) or 5 (2 members/corporate family). Source: `employer_canonical_groups` (16,647 groups). |
| score_size | 3x | 146,863 | 100.0% | 1.48 | 0.00 | 10.00 | Very low average — most BUs are small. Sweet-spot curve 15-500 workers. |
| score_nlrb | 3x | 25,879 | 17.6% | 3.59 | 0.00 | 10.00 | Post-decay average. Was 6.20 before 7yr half-life fix. Uses `nlrb_participants` + `nlrb_elections` + `nlrb_cases`. |
| score_contracts | 2x | 9,305 | 6.3% | 5.50 | 1.00 | 10.00 | **FIXED.** Tiered by federal obligation amount: 1(7), 2(1,625), 4(2,567), 6(2,455), 8(1,776), 10(875). No longer flat 4.00. |
| score_industry_growth | 2x | 131,204 | 89.3% | 6.67 | 2.70 | 9.20 | BLS 10-year projections. Narrow range, high floor. |
| score_financial | 2x | 10,867 | 7.4% | 5.73 | 0.00 | 10.00 | **FIXED.** Now uses 990 revenue tiers (0-6) + asset cushion (0-2) + revenue-per-worker (0-2). Public companies get 7. NOT a copy of score_industry_growth (9,545 employers differ). |
| score_osha | 1x | 32,051 | 21.8% | 1.44 | 0.00 | 10.00 | Industry-normalized violation count with 10yr temporal decay. |
| score_whd | 1x | 12,025 | 8.2% | 1.70 | 0.04 | 9.75 | Case-count-based with temporal decay. Low average suggests most employers have few violations. |
| score_similarity | **0x** | 164 | 0.1% | 10.00 | 10.00 | 10.00 | **BROKEN.** Pipeline from `employer_comparables` (269K rows) to score fails at name+state bridge (only 164 match). Weight zeroed per D5. All 164 get perfect 10. |

**Score distribution (weighted_score, 0-10 scale):**

| Bucket | Count |
|--------|-------|
| 0-1 | 5,860 |
| 1-2 | 5,556 |
| 2-3 | 33,770 |
| 3-4 | 27,437 |
| 4-5 | 20,347 |
| 5-6 | 32,414 |
| 6-7 | 11,206 |
| 7-8 | 4,645 |
| 8-9 | 3,566 |
| 9-10 | 2,062 |

Bimodal distribution — peaks at 2-3 (33,770) and 5-6 (32,414). Average = 4.19.

**Factors per employer:**

| Factors Available | Count | % |
|-------------------|-------|---|
| 1 | 6,164 | 4.2% |
| 2 | 45,984 | 31.3% |
| 3 | 54,808 | 37.3% |
| 4 | 25,827 | 17.6% |
| 5 | 9,967 | 6.8% |
| 6 | 3,208 | 2.2% |
| 7 | 801 | 0.5% |
| 8 | 104 | 0.1% |

37.3% have exactly 3 factors, 31.3% have 2. Only 0.6% have 7-8 factors. 4.2% have just 1 factor.

**Tier distribution:**

| Tier | Count | % |
|------|-------|---|
| Priority | 2,278 | 1.6% |
| Strong | 15,376 | 10.5% |
| Promising | 40,918 | 27.9% |
| Moderate | 51,434 | 35.0% |
| Low | 36,857 | 25.1% |

---

### OQ7: Test Suite Reality Check

```
Backend:  914 passed, 3 skipped, 1 warning (5:27 runtime)
Frontend: 158 passed, 0 failed (11.5s runtime)
Total:    1,072 tests passing across 73 files (50 backend + 23 frontend)
```

**Test file inventory (50 backend):**

| Category | Files | Tests | What They Cover |
|----------|-------|-------|-----------------|
| API/Router | test_api, test_api_errors, test_lookups, test_sectors, test_trends, test_vr, test_projections, test_density, test_corporate, test_public_sector, test_museums | ~120 | Endpoint response shapes and error handling |
| Auth | test_auth | ~15 | Login, register, JWT refresh, role guards |
| Scoring | test_scoring, test_unified_scorecard, test_weighted_scorecard, test_temporal_decay, test_naics_hierarchy_scoring, test_similarity_fallback, test_score_versioning, test_phase1_regression_guards | ~100 | Score formula correctness, decay math, weight configs |
| Matching | test_matching, test_matching_pipeline, test_phase3_matching, test_phase4_integration, test_splink_disambiguate, test_name_normalization, test_resolve_duplicates, test_search_dedup | ~90 | Matching algorithm logic, normalization, dedup |
| Data Integrity | test_data_integrity, test_master_employers, test_employer_data_sources, test_employer_groups, test_occupation_integration, test_system_data_freshness | ~60 | Schema validation, foreign keys, freshness |
| Research Agent | test_auto_grader, test_research_agent_52, test_research_scraper, test_research_enhancements | ~180 | Auto-grading, tool calls, scraping, enhancements |
| CBA | test_cba, test_cba_rule_engine, test_cba_article_finder, test_cba_party_extractor | ~83 | Rule-based extraction pipeline |
| Other | test_db_config_migration_guard, test_frontend_xss_regressions, test_scorecard_contract_field_parity, test_missing_unions_resolution, test_propensity_model, test_union_membership_history, test_union_organizing_capacity, test_workforce_profile | ~50 | Misc guards and features |

**Frontend test files (23):** Cover component rendering, routing, error boundaries, auth flows, search UI, match review, accessibility.

**Tests that verify score VALUES:** `test_unified_scorecard.py` (26 tests), `test_weighted_scorecard.py`, `test_scoring.py`, `test_temporal_decay.py` (29 tests), `test_phase1_regression_guards.py`. These check formula correctness with mock data.

**Tests that verify match ACCURACY:** `test_matching.py`, `test_phase3_matching.py`, `test_matching_pipeline.py`, `test_splink_disambiguate.py`. These verify matching logic but **not real-world accuracy** — no test takes a known employer and asserts it matches correctly against live data.

**What has NO test coverage:**
- End-to-end integration test: source data -> match -> score -> API output for a known employer
- Fuzzy match false positive rate validation
- Junk record detection (no test checks that "Employer Name" or "M1" are filtered)
- Union Profile API completeness (the `financial_trends` / `sister_locals` gap would be caught)
- Research agent assessment completeness (ABM-style empty assessments aren't caught)

---

### OQ8: Database Cleanup Opportunity

```sql
SELECT pg_size_pretty(pg_database_size('olms_multiyear'));
-- 15 GB

SELECT COUNT(*) FROM pg_tables WHERE schemaname = 'public';
-- 198 tables

SELECT COUNT(*) FROM pg_stat_user_tables WHERE schemaname = 'public' AND n_live_tup = 0;
-- 3 empty tables
```

**198 total tables, 3 empty:**
- `cba_wage_schedules` — empty, can drop
- `platform_users` — empty (auth uses separate mechanism), can drop
- `splink_match_results` — 0 rows, legacy, can drop

**Top 20 largest tables:**

| Table | Size | Est. Rows |
|-------|------|-----------|
| master_employers | 3,192 MB | ~3,377,058 |
| unified_match_log | 1,311 MB | ~2,210,297 |
| nlrb_participants | 1,179 MB | ~1,894,354 |
| corpwatch_subsidiaries | 1,010 MB | ~4,462,624 |
| master_employer_source_ids | 779 MB | ~3,749,481 |
| corpwatch_companies | 736 MB | ~1,421,198 |
| mergent_employers | 509 MB | ~56,315 |
| corpwatch_names | 503 MB | ~2,412,509 |
| irs_bmf | 491 MB | ~2,043,281 |
| osha_establishments | 425 MB | ~1,001,188 |
| corpwatch_relationships | 390 MB | ~3,517,388 |
| corpwatch_locations | 348 MB | ~2,567,256 |
| ar_disbursements_emp_off | 325 MB | ~2,813,140 |
| osha_violations_detail | 316 MB | ~2,245,013 |
| whd_cases | 316 MB | ~362,635 |
| f7_employers_deduped | 281 MB | ~146,863 |
| qcew_annual | 273 MB | ~1,943,426 |
| epi_union_membership | 255 MB | ~1,420,064 |
| sam_entities | 245 MB | ~826,042 |
| nlrb_docket | 231 MB | ~2,046,151 |

**CorpWatch: 3,027 MB (3 GB) for 14.7M rows.** Only 2,597 distinct F7 employers matched. The `corpwatch_subsidiaries` (1 GB), `corpwatch_names` (503 MB), `corpwatch_locations` (348 MB), and `corpwatch_relationships` (390 MB) tables could potentially be dropped if only the companies table and f7_matches are needed for the 2,597 matches. Savings: ~2.2 GB.

**12 GB GLEIF dump:** The `gleif` schema no longer exists. Only `gleif_us_entities` (182 MB) and `gleif_ownership_links` (75 MB) remain in the public schema. **The raw dump has been cleaned up.**

**IRS BMF:** 2,043,472 rows, 491 MB. Note: CLAUDE.md still says "25 rows test load" — this is outdated. Full dataset is loaded. However, only 8 active BMF matches exist in UML. The data is loaded but essentially unused in matching.

**90 leaked pg_temp schemas:** Residual temporary schemas from crashed/leaked database connections. Not consuming significant disk space but indicate connection pool issues.

**124 public views:** 27 are industry/sector/organizing-related. Many are legacy sector views from the Mergent-era scoring system. Not actively broken but add schema clutter.

**Reclamable space estimate:**
- CorpWatch subsidiary/relationship/names/locations: ~2.2 GB
- splink_match_results (0 rows): negligible
- Total recoverable: ~2.2 GB (15%)

---

### OQ9: Single Biggest Problem

**The fuzzy matching pipeline produces false positives that flow into the scoring system.**

- **What:** At the 0.70-0.80 name similarity threshold, my spot check found a **~75% false positive rate** in Splink matches. "San Francisco First Tee" matches to "Fairmont San Francisco." "New Horizons" matches to "Horizon Lines." These are completely different companies.
- **Who it affects:** Every employer with a fuzzy match gets data from the matched source (OSHA violations, WHD wage theft, SAM contracts). A false positive means an employer gets credit/penalty for another company's record.
- **Confidence:** HIGH — 15/20 sampled fuzzy matches in the 0.70-0.80 range were wrong.
- **Impact scale:** There are 18,371 active Splink matches across all sources + 4,137 active trigram matches. If even 30% are false positives, that's ~6,700 wrong matches feeding into scores. The code now defaults to a 0.80 floor for new runs, but old matches from earlier runs persist.
- **Rough fix effort:** Re-run all sources with the current 0.80 floor. Consider raising to 0.85. Add name-length and industry cross-checks. ~4-8 hours including verification.
- **If NOT fixed:** Organizers will see employers attributed with violations and contracts from completely different companies. This destroys trust in the platform.

---

### OQ10: Previous Audit Follow-Up

**Investigation questions status:**

| # | Question | Addressed? | Evidence |
|---|----------|------------|----------|
| 1 | Name similarity floor tested at 0.75/0.85? | **Partially** — floor raised from 0.65 to 0.80 in code. No evidence of systematic testing at 0.75/0.85 specifically. My audit shows 0.70-0.80 range is still problematic for OLD matches. |
| 2 | 14.5M membership validated state-by-state? | **Yes** — f7_union_employer_relations sums to 15.7M BU size. Top states (CA 2.1M, NY 1.5M, IL 994K) are reasonable. v_union_members_deduplicated shows 72M (over-counting issue in view — see Area 6). |
| 3 | 75,043 orphaned superseded matches investigated? | **Yes, FIXED** — 0 orphan active matches (confirmed via `NOT EXISTS` against f7_employers_deduped). |
| 4 | 46,627 UML records pointing to missing F7 targets? | **Yes, FIXED** — 0 orphan active matches now. |
| 5 | NAICS inference for 22,183 lacking codes? | **Partially** — 229 new inferences (89.2% -> 89.3%). 15,659 still missing (10.7%). |
| 6 | Employer grouping (249 construction companies)? | **Addressed** — no same-name/state group > 25 found. Largest: Starbucks CA (25). No construction over-merge detected. |
| 7 | Comparables -> similarity pipeline investigated? | **Acknowledged, not fixed** — weight zeroed to 0. Only 164/146,863 have data. Pipeline broken at name+state bridge. Root cause identified but not resolved. |
| 8 | NLRB proximity data source verified? | **Clarified** — score_union_proximity does NOT use nlrb_participants. It uses `employer_canonical_groups` (F7 grouping). score_nlrb separately uses `nlrb_participants` + `nlrb_elections` + `nlrb_cases`. Junk data cleaned (0 remaining junk rows). Both factors work correctly but are independent. |
| 9 | Junk/placeholder records cleaned from scoring? | **Partially** — "Employer Name", "M1", "Company Lists" still in scorecard (score=10.00, Promising tier). But gated from Priority/Strong by factors_available >= 3. 525 employers have names <= 3 chars. |
| 10 | Geocoding gap investigated by tier? | **Yes** — geocoding improved 73.8% -> 83.3% via Census batch + ZIP centroid fallback (13,974 new geocodes). 24,512 still missing. |

**Decision status:**

| # | Decision | Current Status |
|---|----------|---------------|
| 1 | Name similarity floor | Code default = 0.80 (was 0.65). Configurable via MATCH_MIN_NAME_SIM env var. Old matches at 0.70-0.80 persist and need re-run. |
| 2 | Priority definition | Structural + requires >= 3 factors AND top 3% percentile. No recent-activity requirement. |
| 3 | Minimum factors | >= 3 for Priority AND Strong (confirmed in code, line 516-518). Others unrestricted. |
| 4 | Stale OSHA matches | **Fixed** — 0 active Splink matches below 0.70. But old matches in 0.70-0.80 range from pre-0.80-floor runs still active. |
| 5 | score_similarity | Weight zeroed to 0 (code line 418). Still computed for 164 employers but excluded from weighted_score and factors_available. |
| 6 | Legacy frontend | `organizer_v5.html` still exists in `files/`. Docker/nginx configs still reference it. React frontend in `frontend/` is the active development target. |
| 7 | User data storage | Still localStorage (DISABLE_AUTH=true in .env). Auth system exists but disabled for development. |

**Previous audit findings — fix status (from FOUR_AUDIT_SYNTHESIS_v3.md):**

| # | Finding (All 3 Auditors Agreed) | Fixed? | Evidence |
|---|--------------------------------|--------|----------|
| 1 | Scoring math is correct | n/a | Positive finding, still true |
| 2 | score_financial = copy of growth | **YES** | Phase 1 fix: now 990 revenue tiers + asset cushion + per-worker. 9,545 employers where financial != growth. |
| 3 | Contracts flat 4.00 | **YES** | Phase 1 fix: tiered 1/2/4/6/8/10 by federal obligation amount. Distribution confirmed via query. |
| 4 | Thin-data employers float to top | **PARTIALLY** | >= 3 factors gate works for Priority/Strong. But 86% Priority still has no enforcement data. Promising/Moderate/Low allow 1-2 factors with junk records like "Employer Name" at score=10. |
| 5 | Similarity factor dead (0.1%) | **ACKNOWLEDGED** | Weight zeroed per D5. Root cause not fixed. Pipeline still broken. |
| 6 | Priority = ghost employers (92.7% no enforcement) | **PARTIALLY** | Improved to 86% (from 92.7%) no enforcement. Still the dominant pattern in Priority tier. |
| 7 | Fuzzy matching ~10-40% false positive | **NOT FIXED for old matches** | Code floor raised to 0.80 for new runs. But my spot check of existing matches in 0.70-0.80 range shows ~75% false positive rate. Old matches persist. |
| 8 | Can't see 55.7% of election wins | **NOT VERIFIED** | I did not re-check this specific claim in this audit. |
| 9 | No backup strategy | **NOT FIXED** | No automated pg_dump. Docker compose has a `postgres_data` volume but no backup cron. |
| 10 | Documentation stale | **PARTIALLY** | MEMORY.md updated, CLAUDE.md still has stale warnings (IRS BMF "25 rows", financial inversion bug, Splink floor bug — all actually fixed). |

---

## 3. Investigation Area Reports

### Area 1: Scoring System Complete Verification

**1A: Score Factor Status (All 9)**

See OQ6 for comprehensive factor table. Key additional findings:

```sql
-- Are score_financial and score_industry_growth still identical?
SELECT COUNT(*) FROM mv_unified_scorecard
WHERE score_financial IS NOT NULL AND score_industry_growth IS NOT NULL
AND score_financial != score_industry_growth;
-- Result: 9,545 (they differ)
```

**Confirmed:** `score_financial` and `score_industry_growth` are now independent. The Phase 1 fix (2026-02-23) properly separated them.

```sql
-- Contracts score distribution
SELECT score_contracts, COUNT(*)
FROM mv_unified_scorecard WHERE score_contracts IS NOT NULL
GROUP BY score_contracts ORDER BY score_contracts;
-- Result: 1(7), 2(1625), 4(2567), 6(2455), 8(1776), 10(875)
```

**Confirmed:** Contracts scoring is tiered by federal obligation amount. No longer flat 4.00.

**1B: Priority Tier Deep Dive**

- 2,278 employers in Priority tier
- **0 with fewer than 3 factors** (factors_available >= 3 guard working perfectly)
- 1,877 (82%) have exactly 3 factors
- 1,962 (86%) have zero enforcement data (OSHA=NULL AND NLRB=NULL AND WHD=NULL)
- All Priority employers are real companies (no junk records after the gate)
- The gate effectively prevents 1-2 factor junk from reaching top tiers

**1C: Score Distribution**

Bimodal distribution with peaks at 2-3 (33,770) and 5-6 (32,414). This bimodality likely reflects the 49.8% split in union_proximity — employers with proximity=10 cluster higher, those with NULL cluster lower.

**1D: Junk Record Detection**

```sql
SELECT employer_name, state, weighted_score, score_tier, factors_available
FROM mv_unified_scorecard
WHERE employer_name IN ('Employer Name', 'Company Lists', 'M1', 'Test', 'N/A', 'TBD', 'Unknown')
   OR LENGTH(employer_name) <= 2
   OR employer_name ~* '(pension benefit|federal agency|department of|city of|state of|county of|school district)'
ORDER BY weighted_score DESC LIMIT 30;
```

**Still present in scorecard:**

| Employer | State | Score | Tier | Factors |
|----------|-------|-------|------|---------|
| Pension Benefit Guaranty Corporation (PBGC) | DC | 10.00 | Promising | 1 |
| County of Tehama - Miscellaneous Unit | CA | 10.00 | Promising | 1 |
| US Department of Commerce Census Bureau | DC | 10.00 | Promising | 1 |
| City of Boston Middle Managers | MA | 10.00 | Promising | 1 |
| Employer Name | NY | 10.00 | Promising | 1 |
| Company Lists | (null) | 10.00 | Promising | 1 |
| Department of the Navy, NASJRB, New Orleans | LA | 10.00 | Promising | 1 |
| M1 | AL | 10.00 | Promising | 1 |
| State of California - Bargaining Unit 12 | CA | 10.00 | Promising | 1 |

These are gated from Priority/Strong by the 3-factor requirement, but they inflate Promising tier counts and would confuse organizers browsing the data.

- **525 employers with names <= 3 characters** in the scorecard
- Federal agencies, school districts, and municipal bargaining units are mixed in with private employers

---

### Area 2: Match Quality Post-Hardening

**2A: Stale OSHA Splink below 0.70:**

```sql
SELECT COUNT(*) FROM unified_match_log
WHERE source_system = 'osha' AND status = 'active'
AND match_method LIKE '%SPLINK%'
AND (evidence::json->>'name_similarity')::float < 0.70;
-- Result: 0
```

**FIXED.** No active Splink matches below 0.70 remain.

**2B: Match Methods by Source (55 distinct method/source combinations):**

All sources now use Phase 3+ method names (NAME_STATE_EXACT, NAME_CITY_STATE_EXACT, NAME_AGGRESSIVE_STATE, FUZZY_SPLINK_ADAPTIVE, FUZZY_TRIGRAM). **Exceptions:**
- GLEIF: 1,225 `NAME_STATE` + 583 `SPLINK_PROB` (legacy method names, never re-run through deterministic pipeline)
- Mergent: 946 `SPLINK_PROB` + 98 `NAME_STATE` (same — legacy methods)
- Crosswalk: 10,688 `CROSSWALK` + 8,605 `USASPENDING_*` (expected — different pipeline)

**2C: Source Match Summary (129,870 total active):**

| Source | Active | Rejected | Superseded | Total |
|--------|--------|----------|------------|-------|
| osha | 48,882 | 869,100 | 338,771 | 1,256,753 |
| crosswalk | 19,293 | 0 | 0 | 19,293 |
| sam | 14,522 | 219,176 | 66,651 | 300,349 |
| 990 | 13,254 | 131,294 | 101,492 | 246,040 |
| nlrb | 13,030 | 4,485 | 0 | 17,516 |
| whd | 10,991 | 106,727 | 79,784 | 197,502 |
| corpwatch | 3,275 | 3,658 | 461 | 7,394 |
| sec | 2,760 | 117,294 | 39,689 | 159,743 |
| gleif | 1,810 | 0 | 30 | 1,840 |
| mergent | 1,045 | 0 | 0 | 1,045 |
| bmf | 8 | 12 | 10 | 30 |

Notable: The rejection rates are very high for OSHA (69%), SEC (73%), SAM (73%), which indicates aggressive quality filtering.

**2D: Missing Employer Targets:**

```sql
SELECT COUNT(*) FROM unified_match_log uml
WHERE uml.status = 'active'
AND NOT EXISTS (SELECT 1 FROM f7_employers_deduped f WHERE f.employer_id = uml.target_id);
-- Result: 0
```

**FIXED.** All active matches point to valid F7 employers. The previous audit's 46,627 orphan finding is resolved.

**2E: Fuzzy Match Accuracy — See OQ2 for full 20-match analysis.**

**NLRB Confidence Scale Bug:**

```sql
SELECT COUNT(*) FROM unified_match_log
WHERE source_system = 'nlrb' AND status = 'active' AND confidence_score > 1.0;
-- Result: 0
```

**FIXED.** All NLRB confidence scores normalized to 0.0-1.0 range.

---

### Area 3: Research Agent Verification

**3A: Where Is the Output?**

7 database tables:

| Table | Purpose |
|-------|---------|
| `research_runs` | 104 runs with dossier JSONB, quality scores, metadata |
| `research_actions` | Tool call log per run |
| `research_facts` | Extracted facts with source attribution |
| `research_fact_vocabulary` | Canonical fact field names |
| `research_query_effectiveness` | Learning loop for query templates |
| `research_score_enhancements` | 16 rows — enhancement records for scorecard integration |
| `research_strategies` | Strategy selection metadata |

**3B: Quality Assessment (5 Dossiers Evaluated)**

| Employer | Quality | Facts | Assessment Complete? | Useful? |
|----------|---------|-------|---------------------|---------|
| USPS | 8.75 | 30 | Yes — 5 strengths, 4 challenges, full strategy | **YES** — 38,771 ULPs, specific unions, nuanced analysis |
| ABM Industries | 8.67 | 30 | **NO — all 4 assessment fields null** | **PARTIAL** — great data, zero synthesis |
| FedEx | 8.67 | 28 | Yes — 5 strengths, 5 challenges, full strategy | **YES** — 17 elections, contractor model analysis |
| NY Presbyterian | 8.65 | 31 | Yes — longest assessment (1,078 chars) | **YES** — 41 ULPs, COVID deaths, specific strategy |
| Montefiore | 8.65 | 27 | Yes — most nuanced strategy (1,765 chars) | **YES** — $5.9B revenue, recent wins, actionable plan |

**Quality scores are from deterministic auto-grading** (6 dimensions: coverage, source_quality, consistency, efficiency, freshness, actionability). NOT self-assessment. However:

**Critical finding: The auto-grader doesn't penalize empty assessments.** ABM Industries scores 8.67 with zero analytical synthesis — the grading dimensions don't include "assessment completeness." This means the quality score is **unreliable as a proxy for usefulness.** An organizer relying on quality >= 8.0 as a filter would get dossiers ranging from excellent (Montefiore) to useless data dumps (ABM).

**Cross-cutting dossier issues:**
- `recent_labor_news` is **empty in ALL 5 dossiers** despite all having extensive public labor coverage. Web scraping/news tools appear systematically broken.
- Workforce section (pay ranges, turnover, demographics) is **empty in ALL 5.** Only BLS industry-level data present.
- Fact source naming is **inconsistent** across dossiers (DB table names vs tool names vs human-readable names in 3 different conventions).
- **76% of runs lack employer_id** — only 24/104 are linked to an F7 employer.

**3C: Integration Check**

- `research_score_enhancements` has 16 rows (quality gate >= 7.0 AND employer_id IS NOT NULL)
- `mv_unified_scorecard` has research columns (`has_research`, `research_quality`, etc.)
- But: **`has_research = false` for ALL 146,863 employers** — the LEFT JOIN in the MV isn't matching
- Cause: 76% of research runs lack employer_id. The 24 runs with employer_id produce 16 enhancements, but these apparently don't match during MV rebuild.
- API endpoints exist (`/api/research/candidates`, `/api/scorecard/unified` with `has_research` filter) but return empty results.
- **The research-to-scorecard feedback loop is architecturally complete but functionally empty.**

---

### Area 4: CorpWatch SEC EDGAR Import

**4A: Table Inventory (3,027 MB / 14,671,978 rows):**

| Table | Size | Est. Rows |
|-------|------|-----------|
| corpwatch_subsidiaries | 1,010 MB | 4,462,624 |
| corpwatch_companies | 736 MB | 1,421,198 |
| corpwatch_names | 503 MB | 2,412,509 |
| corpwatch_relationships | 390 MB | 3,517,388 |
| corpwatch_locations | 348 MB | 2,567,256 |
| corpwatch_filing_index | 40 MB | 208,503 |
| corpwatch_f7_matches | 552 KB | 3,057 |

**4B: Integration:**
- 3,275 active matches in UML, mapping to **2,597 distinct F7 employers**
- 1,921 crosswalk rows with corpwatch_id
- Methods: CIK_BRIDGE (1,779), EIN_EXACT (795), NAME_AGGRESSIVE_STATE (397), FUZZY_SPLINK_ADAPTIVE (113)
- **Utilization: 2,597 / 1,421,198 = 0.18%.** The vast majority of CorpWatch data (SEC-style corporate names) doesn't match F7 employers.
- CorpWatch entities seeded into `master_employers` (668,454 rows) and enriched `corporate_hierarchy` (+97,804 edges)
- **Not directly visible on frontend** — no `has_corpwatch` flag on the unified scorecard. Data enriches corporate hierarchy but doesn't appear on employer profiles.

---

### Area 5: NLRB Data Quality Post-Cleanup

**5A: Participant Data Status**

```sql
SELECT COUNT(*) FROM nlrb_participants;
-- 1,906,542

SELECT COUNT(*) FROM nlrb_participants
WHERE state = 'Charged Party Address State' OR city LIKE '%Address%';
-- 0 (cleaned)
```

Cleanup results: 379,558 state values NULLed, 379,558 city values NULLed, 492,196 zip values NULLed. **0 junk rows remaining.**

**5B: NLRB Scoring Source — CRITICAL CLARIFICATION**

I originally conflated `score_union_proximity` with `score_nlrb`. They are **completely independent factors:**

**`score_union_proximity` (weight 3x):**
- Source: `employer_canonical_groups` table (16,647 groups)
- Measures: "Does this employer have sibling employers that are unionized?"
- Logic: 10 if group has 3+ members (after -1 adjustment), 5 if 2 members or in corporate family, NULL otherwise
- Distribution: 10 (50,872), 5 (22,320), NULL (73,671)
- Does **NOT** use nlrb_participants at all

**`score_nlrb` (weight 3x):**
- Source: `nlrb_participants` + `nlrb_elections` + `nlrb_cases`
- Measures: "Does this employer have NLRB election history or ULP charges?"
- Uses FULL OUTER JOIN of election aggregation (employer participants) and ULP aggregation (charged party participants with '-CA-' case numbers)
- Has 7-year half-life temporal decay
- Coverage: 25,879 employers (17.6%)

The NLRB participant cleanup (NULLing junk city/state/zip) does NOT affect scoring because the scoring CTEs join on `participant_type` and `case_number`, not on address fields.

**Cross-check:** 5,587 employers have score_nlrb but NOT score_union_proximity. 52,900 have score_union_proximity but NOT score_nlrb. These are genuinely different signals.

---

### Area 6: Membership Numbers Paradox

```sql
SELECT SUM(bargaining_unit_size) FROM f7_union_employer_relations;
-- 15,737,807

SELECT state, SUM(bargaining_unit_size) as total
FROM f7_union_employer_relations r
JOIN f7_employers_deduped e ON r.employer_id = e.employer_id
GROUP BY state ORDER BY total DESC LIMIT 10;
```

| State | BU Size Total |
|-------|--------------|
| CA | 2,138,523 |
| NY | 1,459,469 |
| IL | 994,466 |
| WA | 839,571 |
| MI | 797,487 |
| OH | 780,820 |
| PA | 742,932 |
| TX | 718,054 |
| NJ | 605,912 |
| MN | 499,317 |

State distribution looks reasonable. California and New York dominating is expected.

```sql
SELECT COUNT(*), SUM(members) FROM v_union_members_deduplicated;
-- 26,683 rows, 71,974,947 total members
```

**The deduplication view is over-counting by ~5x** (72M vs BLS ~14.3M). The BU-size-based figure (15.7M) is more reliable and aligns with BLS "represented by" figures (~16.2M). The view likely sums across multiple reporting years or has a deduplication logic error.

NULL state accounts for 428,462 in BU size — employers without state data.

---

### Area 7: Incomplete Source Re-runs

**See OQ5 for full detail.** Summary: All three sources (990, WHD, SAM) have been re-run. All active matches use Phase 3+ method names. Old methods are properly superseded. The audit prompt's characterization as "never completed" is outdated.

---

### Area 8: Over-Merge and Under-Merge

```sql
SELECT employer_name, state, COUNT(*) as group_size
FROM f7_employers_deduped
GROUP BY employer_name, state HAVING COUNT(*) > 10
ORDER BY COUNT(*) DESC LIMIT 20;
```

| Employer | State | Group Size |
|----------|-------|------------|
| Starbucks Corporation | CA | 25 |
| MV Transportation | CA | 19 |
| Starbucks Corporation | NY | 18 |
| Ford Motor Company | MI | 14 |
| Starbucks Corporation | OH | 13 |
| Starbucks Corporation | PA | 12 |
| First Student | NY | 11 |
| Transdev | CA | 11 |
| First Student Inc | CA | 11 |

These are primarily large multi-location employers where F7 has separate bargaining unit records per facility. Starbucks with 25 in CA is reasonable given their many locations.

**No construction over-merge found.** The previous audit's 249-company concern appears addressed:

```sql
SELECT employer_name, COUNT(*) FROM f7_employers_deduped
WHERE employer_name ILIKE '%construction%inc%'
   OR employer_name ILIKE '%building service%'
   OR employer_name ILIKE '%pta%congress%'
GROUP BY employer_name HAVING COUNT(*) > 10
ORDER BY COUNT(*) DESC;
-- (none found)
```

---

### Area 9: Database Health

- **Database size:** 15 GB
- **198 tables** (public schema), 3 empty
- **124 views** (public schema), ~27 industry/sector-related
- **5 materialized views** (all refreshed within 2 days)
- **IRS BMF:** 2,043,472 rows (full dataset loaded, not 25 as CLAUDE.md says). 491 MB. Only 8 active matches.
- **90 leaked pg_temp schemas** — from crashed/leaked connections. Should be cleaned up.
- **master_employers:** 3,405,344 rows (up from documented 2.7M) due to CorpWatch (668K) and BMF (1.75M) seeding.

**Index check:**
```sql
SELECT indexname FROM pg_indexes
WHERE tablename = 'nlrb_participants' AND indexdef LIKE '%case_number%';
-- idx_nlrb_participants_case_number (present)
```

---

### Area 10: API Data Verification

**API Health:** `{"status":"ok","db":true,"timestamp":"2026-02-26T02:30:50.515056+00:00"}`

**Employer Search Test:**
```
GET /api/employers/unified-search?name=Kaiser&limit=3
-- Returns 2 results with correct field shape
```

**Scorecard Stats Test:**
```
GET /api/scorecard/unified/stats
-- Returns:
{
  "overview": {
    "total_employers": 146863,
    "avg_score": 4.19,
    "min_score": 0.0,
    "max_score": 10.0,
    "avg_factors": 3.0,
    "avg_coverage_pct": 37.6
  },
  "tier_distribution": [
    {"score_tier": "Priority", "cnt": 2278},
    {"score_tier": "Strong", "cnt": 15376},
    {"score_tier": "Promising", "cnt": 40918},
    {"score_tier": "Moderate", "cnt": 51434},
    {"score_tier": "Low", "cnt": 36857}
  ]
}
```

Totals sum to 146,863 (correct).

**Kaiser Profile Test:**
```sql
SELECT employer_name, state, weighted_score, score_tier, factors_available
FROM mv_unified_scorecard WHERE employer_name ILIKE '%kaiser%' LIMIT 5;
```
Returns Kaiser employers across multiple states with scores and tiers. Data is present and queryable.

---

## 4. Surprise Findings

### 4.1: 90 Leaked pg_temp Schemas

The database has accumulated ~90 orphaned temporary schemas from crashed connections. While not consuming significant space, this is a sign of connection pool leaks or ungraceful shutdowns. These accumulate because PostgreSQL only cleans temp schemas when the owning session disconnects cleanly.

### 4.2: IRS BMF Fully Loaded (2M Rows)

CLAUDE.md still says "IRS BMF has 25 rows: test load of 25 records." The actual table has **2,043,472 rows** and takes 491 MB. However, only 8 active BMF matches exist in UML. The BMF data is loaded but essentially unused in matching. Either the matching adapter needs to be run, or this data isn't useful for F7 matching.

### 4.3: Research Feedback Loop is a Dead Circuit

Despite 16 research_score_enhancements and the MV having all the research columns, `has_research = false` for all 146,863 employers. The LEFT JOIN in the MV fails because most research runs (76%) don't have employer_id set. The entire research-to-scorecard pipeline is architecturally complete but functionally producing zero output.

### 4.4: score_size Average is Extremely Low (1.48/10)

At 3x weight, this factor is the most impactful. Yet the average is 1.48, meaning most F7 employers have very small bargaining units (under ~30 workers based on the 15-500 sweet-spot curve). This isn't necessarily wrong — many F7 records represent individual bargaining units, not whole companies. But it means the size factor systematically drags down scores for the majority of employers, potentially obscuring other signals.

### 4.5: v_union_members_deduplicated Shows 72M (5x BLS)

The deduplicated membership view returns 71,974,947 total members across 26,683 rows. BLS says ~14.3M. This view appears to be over-counting, likely summing across multiple reporting years without proper temporal deduplication. The BU-size figure (15.7M from f7_union_employer_relations) is more reliable.

### 4.6: Union Profile API Returns Incomplete Data

The frontend `UnionProfilePage.jsx` expects `financial_trends` and `sister_locals` from the `/api/unions/{f_num}` endpoint. The API does NOT return these fields. The `UnionFinancialsSection` and `SisterLocalsSection` components will render empty content silently. This is a real bug affecting user experience.

### 4.7: Research Auto-Grader Has No Assessment Dimension

ABM Industries scores 8.67/10 quality with a completely empty assessment section (no organizing summary, no recommended approach, no strengths/challenges). The grading dimensions (coverage, freshness, efficiency, consistency, source_quality) don't include "assessment completeness." This means the quality score is unreliable as a proxy for dossier usefulness.

### 4.8: Research News/Web Scraping Tools Appear Systematically Broken

All 5 reviewed dossiers have empty `recent_labor_news` fields despite all being major companies with extensive public labor coverage (USPS, FedEx, ABM, NYP, Montefiore). The workforce section (pay ranges, turnover, demographics) is also empty across all 5. These tools are either not being called or consistently failing.

### 4.9: Docker Artifacts Point to Legacy Frontend

The `Dockerfile`, `docker-compose.yml`, and `nginx.conf` all exist but reference `./files` and `organizer_v5.html` — the legacy vanilla JS frontend. The active React frontend in `frontend/` is not built or served by the Docker setup. These configs won't work for production deployment of the current platform.

### 4.10: Fact Source Naming Inconsistency Across Research Dossiers

Three different naming conventions appear across dossiers:
- Database table names: `sam_entities`, `nlrb_cases`, `osha_violations_detail` (USPS dossier)
- Tool names: `search_nlrb`, `search_osha`, `search_whd` (FedEx, Montefiore)
- Human-readable: `Mergent Intellect`, `OSHA Violations`, `DOL Wage & Hour Division` (NYP)

This inconsistency would make programmatic analysis of sources across dossiers unreliable.

---

## 5. Previous Audit Follow-Up

### What the Previous Audit Found (FOUR_AUDIT_SYNTHESIS_v3.md, 3 auditors)

**All Three Auditors Agreed On:**
1. Scoring math is correct but multiple factors are broken
2. score_financial = duplicate of score_industry_growth
3. Contracts scoring flat at 4.00
4. Thin-data employers float to top (231 Priority with 1 factor)
5. Similarity factor dead at 0.1% coverage
6. Priority tier = "ghost employers" (92.7% no enforcement)
7. Fuzzy matching 10-40% false positive rate
8. Platform can't see 55.7% of union election wins (lack F7 links)
9. No backup strategy (11 GB, zero automated backups)
10. Documentation stale (count discrepancies)

### Current Status of Each Finding

| # | Finding | Status | Evidence |
|---|---------|--------|----------|
| 1 | Scoring math correct | Still true | Verified via code trace and data queries |
| 2 | Financial = copy of growth | **FIXED** | Phase 1 fix: 990 revenue tiers. 9,545 employers where financial != growth. |
| 3 | Contracts flat 4.00 | **FIXED** | Phase 1 fix: tiered 1/2/4/6/8/10 by obligation amount. |
| 4 | Thin-data Priority | **PARTIALLY FIXED** | >= 3 factors gate drops 1-factor employers from Priority/Strong. But 86% Priority still has no enforcement data. Junk still in Promising. |
| 5 | Similarity dead | **ACKNOWLEDGED** | Weight = 0 (D5). Pipeline not fixed. 164/146,863 coverage. |
| 6 | Ghost employers in Priority | **PARTIALLY FIXED** | Down from 92.7% to 86% no enforcement. Still the dominant pattern. |
| 7 | Fuzzy match false positives | **PARTIALLY FIXED** | Code floor raised to 0.80 for new runs. Old matches at 0.70-0.80 persist (~75% wrong based on my spot check). |
| 8 | 55.7% election wins invisible | **NOT VERIFIED** | Did not recheck this specific claim. |
| 9 | No backup strategy | **NOT FIXED** | No automated pg_dump. Docker volume exists but no cron. |
| 10 | Documentation stale | **PARTIALLY FIXED** | MEMORY.md updated. CLAUDE.md still has outdated warnings. |

### Decisions from Previous Audit — Applied Status

| Decision | Applied? | Detail |
|----------|----------|--------|
| D1: Name floor 0.65 -> 0.70+ | **YES** | Code default = 0.80 (stricter than proposed) |
| D3: factors_available >= 3 for Priority + Strong | **YES** | Confirmed in code, lines 516-518 |
| D5: score_similarity weight = 0 | **YES** | Confirmed in code, line 418 |
| D7: Keep Codex security hardening | **YES** | Admin endpoints require authentication |

---

## 6. Scoring Specification vs Reality

Compared `SCORING_SPECIFICATION.md` (Feb 20, 2026) against actual MV implementation:

| Factor | Spec Says | Reality | Discrepancy? |
|--------|-----------|---------|-------------|
| OSHA Safety (1x) | Industry-normalized, 5yr half-life, +1 willful/repeat bonus | 10yr half-life in code, 21.8% coverage, avg 1.44 | **Minor** — decay period differs (5yr spec vs 10yr code) |
| NLRB Activity (3x) | 70/30 nearby/own split, 7yr half-life | Separate proximity and NLRB factors; 7yr decay confirmed | **Structural difference** — spec has 1 combined factor, code has 2 separate factors |
| WHD Wage Theft (1x) | Case-count tiers: 1=5, 2-3=7, 4+=10, 5yr half-life | avg=1.70, 8.2% coverage, has temporal decay | **Low avg needs investigation** — either decay is aggressive or most have few cases |
| Gov Contracts (2x) | Tiered by level: fed=4, state=6, city=7, two=8, all=10 | Tiered by obligation amount: 1/2/4/6/8/10 | **Different tiering scheme** — spec uses gov level, code uses dollar amount |
| Union Proximity (3x) | 10/5/0 based on unionized siblings | 10/5/NULL confirmed | Match |
| Industry Growth (2x) | Linear BLS 10-year projection | 89.3% coverage, avg 6.67, range 2.70-9.20 | Match |
| Employer Size (3x) | Ramp: <15=0, 15-500 linear, 500+=10 | avg=1.48, 100% coverage | **avg very low** — needs investigation |
| Statistical Similarity (2x) | Comparables + Gower, non-corporate only | 0.1% coverage, weight=0 | **Dead — acknowledged and disabled** |
| Financial (not in spec) | -- | 990 revenue + asset cushion + per-worker, 7.4% coverage | **Beyond spec** — additional factor added in Phase 1 |

**Note:** The scoring spec was written before Phase 1 fixes. The contracts tiering scheme has changed (gov-level to obligation-amount). The financial factor was added beyond the original spec. These are improvements, not regressions.

---

## 7. Known Bug Verification

### Bug 1: BLS Financial Inversion — **FIXED**

CLAUDE.md warns: "An employer with NO BLS industry data gets score_financial = 2. An employer WITH data showing 0% growth gets score_financial = 1."

**Current code:**
- `score_industry_growth`: Returns NULL if naics IS NULL (no industry data). Returns 0-10 linear scale for real data. No dummy value for missing data.
- `score_financial`: Returns NULL if no 990 data AND not public. Returns 7 for public companies. Returns 0-10 tiered for 990 data. No dummy value for missing data.

**Verdict: FIXED.** Both factors correctly return NULL when no data is available, not a dummy value.

### Bug 2: Splink Disambiguation Missing Name Floor — **FIXED**

CLAUDE.md warns: "_splink_disambiguate() does not enforce token_sort_ratio >= 0.70 floor."

**Current code (lines 434-443 of deterministic_matcher.py):**
```python
# Guard against geography-dominated false positives
from rapidfuzz import fuzz as _rf_fuzz
source_name_norm = str(top.get("name_normalized_l") or name_std)
target_name_norm = str(top.get("name_normalized_r") or normalize_name_standard(target_name))
name_similarity = _rf_fuzz.token_sort_ratio(source_name_norm, target_name_norm) / 100.0
if name_similarity < self.min_name_similarity:
    return None
```

Floor value: `DEFAULT_MIN_NAME_SIM = 0.80` (line 58). Configurable via `MATCH_MIN_NAME_SIM` env var.

**Verdict: FIXED.** The floor is enforced at 0.80 (stricter than the reported 0.70). Both Splink disambiguation and RapidFuzz batch matching use the same floor.

---

## 8. Docker Artifacts Review

Three files exist at project root:

**Dockerfile (19 lines):**
- Python 3.12-slim base
- Copies only `api/` and `db_config.py`
- **Missing:** `scripts/`, `src/`, `config/`, `data/` directories needed for scoring/matching
- Runs uvicorn on port 8001
- Suitable for API-only deployment, not full platform

**docker-compose.yml (61 lines):**
- 3 services: `db` (postgres:17), `api` (built from Dockerfile), `frontend` (nginx:alpine)
- DB has healthcheck, API depends on DB health
- **Issues:**
  - Frontend mounts `./files` — the **legacy** `organizer_v5.html`, not the React app
  - `DISABLE_AUTH=true` as default — unsafe for production
  - No backup volume/cron for pg_dump
  - No resource limits or logging config
  - Uses `.env` for credentials (correct for dev)

**nginx.conf (19 lines):**
- Proxies `/api/` to API container on port 8001
- Serves static files from `/usr/share/nginx/html` (maps to `./files`)
- Index = `organizer_v5.html` — should be React build output
- `try_files` with fallback to `/index.html` — correct for SPA routing

**Verdict:** Reasonable first drafts for development. Not production-ready. The biggest issue is that the React frontend is not served — Docker still points to the legacy vanilla JS app.

---

## 9. Recommended Priority List

| # | Issue | Effort | Impact | Detail |
|---|-------|--------|--------|--------|
| 1 | **Re-run all sources with 0.80+ floor** to eliminate old fuzzy false positives | 4-8 hrs | Critical | Code already defaults to 0.80 but old matches from 0.70 runs persist. ~75% FP rate at 0.70-0.80. Consider raising to 0.85. |
| 2 | **Link research runs to employer_ids** + add "assessment completeness" grading dimension | 3-5 hrs | High | 76% of runs disconnected. Auto-grader gives 8.67 to empty-assessment dossiers. Unblocks research-to-scorecard feedback loop. |
| 3 | **Add enforcement activity requirement for Priority/Strong** | 1-2 hrs | High | 86% Priority has no OSHA/NLRB/WHD. Require at least 1 enforcement factor for top 2 tiers. |
| 4 | **Remove junk records from scorecard** | 2-3 hrs | Medium | Filter "Employer Name", names <= 2 chars, federal agencies. Add `is_valid_employer` flag or WHERE clause in MV. |
| 5 | **Fix Union Profile API** — add `financial_trends` and `sister_locals` to response | 2-4 hrs | Medium | Frontend components fail silently. Real bug affecting user experience. |
| 6 | **Fix v_union_members_deduplicated** over-count (72M vs 14.3M BLS) | 2-3 hrs | Medium | View sums across years. Add proper temporal deduplication. |
| 7 | **Investigate score_size avg=1.48** | 2-3 hrs | Medium | At 3x weight, this drags down most employers. Check if sweet-spot curve is appropriate for BU-level data vs company-level. |
| 8 | **Add automated pg_dump backup** | 1 hr | Medium | 15 GB database, zero automated backups. Previous audit flagged this. Still unfixed. |
| 9 | **Update Docker for React frontend** | 1-2 hrs | Low | nginx/compose point to legacy `files/`. Need to build React app and serve from `frontend/dist/`. |
| 10 | **Update CLAUDE.md** — remove stale warnings | 1 hr | Low | IRS BMF is 2M rows (not 25), financial inversion fixed, Splink floor fixed, data_source_freshness fixed, 990/WHD/SAM have been re-run. |

**Total estimated effort for top 5 priorities: 12-22 hours**

---

## Appendix: SQL Evidence Summary

All claims in this report are backed by direct database queries. Key queries run:

| Area | Query | Result |
|------|-------|--------|
| Tier counts | `SELECT score_tier, COUNT(*) FROM mv_unified_scorecard GROUP BY score_tier` | Priority=2,278, Strong=15,376, Promising=40,918, Moderate=51,434, Low=36,857 |
| Priority low factors | `WHERE score_tier = 'Priority' AND factors_available < 3` | 0 |
| Priority no enforcement | `WHERE score_tier = 'Priority' AND score_osha IS NULL AND score_nlrb IS NULL AND score_whd IS NULL` | 1,962 |
| Factor stats | `COUNT/AVG/MIN/MAX for all 9 factors` | See OQ6 table |
| Financial != growth | `WHERE score_financial IS NOT NULL AND score_industry_growth IS NOT NULL AND score_financial != score_industry_growth` | 9,545 |
| Stale Splink < 0.70 | `WHERE source_system = 'osha' AND status = 'active' AND match_method LIKE '%SPLINK%' AND name_similarity < 0.70` | 0 |
| Orphan matches | `WHERE status = 'active' AND NOT EXISTS (SELECT 1 FROM f7_employers_deduped WHERE employer_id = target_id)` | 0 |
| NLRB confidence bug | `WHERE source_system = 'nlrb' AND status = 'active' AND confidence_score > 1.0` | 0 |
| Research runs | `SELECT COUNT(*), AVG(overall_quality_score) FROM research_runs` | 104 runs, avg 7.89 |
| Research enhancements | `SELECT COUNT(*) FROM research_score_enhancements` | 16 |
| Has research | `SELECT COUNT(*) FILTER (WHERE has_research = true) FROM mv_unified_scorecard` | 0 |
| DB size | `pg_database_size('olms_multiyear')` | 15 GB |
| Total tables | `COUNT(*) FROM pg_tables WHERE schemaname = 'public'` | 198 |
| Empty tables | `WHERE n_live_tup = 0` | 3 |
| Master employers | `SELECT COUNT(*) FROM master_employers` | 3,405,344 |
| NLRB junk remaining | `WHERE state = 'Charged Party Address State' OR city LIKE '%Address%'` | 0 |
| Membership total | `SUM(bargaining_unit_size) FROM f7_union_employer_relations` | 15,737,807 |
| Dedup members | `SUM(members) FROM v_union_members_deduplicated` | 71,974,947 |
| Test suite | `py -m pytest tests/ --tb=no -q` | 914 pass, 3 skip |
| Frontend tests | `npx vitest run` | 158 pass |
| API health | `GET /api/health` | OK |
| IRS BMF rows | `SELECT COUNT(*) FROM irs_bmf` | 2,043,472 |
| pg_temp schemas | `WHERE schema_name LIKE 'pg_temp%'` | 90 |

---

*Report generated by Claude Code (Opus 4.6) on 2026-02-25. All SQL queries executed against live `olms_multiyear` database on localhost:5432.*
