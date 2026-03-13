# Project Catalog

> Last updated: 2026-03-12 | Total cataloged files: ~755 code/config files + ~229 docs
> Cross-references: [PIPELINE_MANIFEST.md](PIPELINE_MANIFEST.md) (pipeline run order), [DOCUMENT_INDEX.md](DOCUMENT_INDEX.md) (documentation catalog)

---

## Summary Dashboard

| Layer | Files | Description | Key Entry Points |
|-------|-------|-------------|-----------------|
| Scripts: ETL | 76 | Data loading & transformation | `scripts/etl/newsrc_run_all.py` |
| Scripts: Matching | 36 | Record linkage across sources | `scripts/matching/run_deterministic.py` |
| Scripts: Scoring | 14 | Scorecard & MV computation | `scripts/scoring/refresh_all.py` |
| Scripts: Analysis (General) | 86 | Ad-hoc analysis & audits | -- |
| Scripts: Analysis (Demographics) | 88 + 24 reports | Demographics estimation model | `scripts/analysis/demographics_comparison/run_v10.py` |
| Scripts: CBA | 15 | Contract parsing pipeline | `scripts/cba/process_contract.py` |
| Scripts: Research | 6 | AI research agent | `scripts/research/agent.py` |
| Scripts: Scraper | 15 | Union website scraping | `scripts/scraper/run_extraction_pipeline.py` |
| Scripts: Maintenance | 17 | Data quality & monitoring | `scripts/maintenance/check_doc_consistency.py` |
| Scripts: Setup/Performance | 2 | Initialization & profiling | `scripts/setup/init_database.py` |
| API | 43 | FastAPI backend (port 8001) | `api/main.py` |
| Frontend | 126 src + 38 test | React 19 + Vite + Tailwind | `frontend/src/App.jsx` |
| Shared Libraries | 10 | Python packages (matching, CBA, NLRB) | `src/python/matching/name_normalization.py` |
| Backend Tests | 84 | pytest suite (~1135 tests) | `tests/conftest.py` |
| SQL Schemas | 40 | DDL + query files | `sql/f7_schema.sql` |
| Config | 17 | CBA rules, extraction specs | `config/` |
| AI Agent Infrastructure | 36 | Agents, specs, skills | `.claude/agents/`, `.claude/specs/` |
| Documentation | 229 | Reports, audits, research | `docs/` |
| Root Scripts | 24 | Ad-hoc utilities + db_config | `db_config.py` |
| Data | 14 dirs | Raw & processed data files | `data/` |
| Legacy Demographics | 5 | Early model prototype | `demographic estimate model/` |
| Archive | 4,196 | Superseded code & data | `archive/` (not cataloged) |

---

## Scripts: ETL (76 files)

### Government Data Sources (20 files)

| Script | Description | Source |
|--------|-------------|--------|
| `scripts/etl/load_osha_violations.py` | Load OSHA violation records from SQLite | OSHA |
| `scripts/etl/load_osha_violations_detail.py` | Load individual violation records with case numbers | OSHA |
| `scripts/etl/load_whd_national.py` | Load 363K wage theft cases into whd_cases | WHD |
| `scripts/etl/load_sam.py` | Load 826K federal contractor entities | SAM.gov |
| `scripts/etl/clean_nlrb_participants.py` | Remove literal CSV header text from NLRB city/state/zip | NLRB |
| `scripts/etl/sync_nlrb_sqlite.py` | Sync NLRB data from SQLite to PostgreSQL | NLRB |
| `scripts/etl/create_campaign_outcomes.py` | Create campaign_outcomes table | NLRB |
| `scripts/etl/_fetch_usaspending_api.py` | Fetch federal contract recipients via paginated API | USASpending |
| `scripts/etl/_match_usaspending.py` | Match USASpending recipients to F7 + update crosswalk | USASpending |
| `scripts/etl/load_onet_data.py` | Load O*NET 30.2 data from MySQL dump into PostgreSQL | O*NET |
| `scripts/etl/fetch_qcew.py` | Download and load BLS QCEW annual data | BLS QCEW |
| `scripts/etl/_integrate_qcew.py` | Integrate QCEW with F7 employers for density scoring | BLS QCEW |
| `scripts/etl/load_oes_wages.py` | Load OES Occupational Employment and Wage Statistics | BLS OES |
| `scripts/etl/load_bls_jolts.py` | Load BLS Job Openings and Labor Turnover Survey data | BLS JOLTS |
| `scripts/etl/load_bls_ncs.py` | Load BLS National Compensation Survey data | BLS NCS |
| `scripts/etl/load_bls_soii.py` | Load BLS Survey of Occupational Injuries and Illnesses | BLS SOII |
| `scripts/etl/load_bls_projections.py` | Load BLS 2024-2034 industry/occupation projections | BLS |
| `scripts/etl/download_bls_union_tables.py` | Download BLS union membership HTML tables | BLS |
| `scripts/etl/parse_bls_union_tables.py` | Parse BLS HTML tables into database | BLS |
| `scripts/etl/bls_tsv_helpers.py` | Shared helpers for loading BLS tab-delimited data files | BLS |

### Census & Demographics (14 files)

| Script | Description | Source |
|--------|-------------|--------|
| `scripts/etl/create_state_industry_estimates.py` | Create 459 state x industry union density estimates | BLS/Census |
| `scripts/etl/download_acs_tract_demographics.py` | Download ACS 5-year tract-level demographics from Census API | ACS |
| `scripts/etl/load_census_rpe.py` | Load Census RPE ratios at national/state/county level | Census |
| `scripts/etl/load_cps_table11.py` | Load CPS Table 11 -- occupation by sex/race/ethnicity | CPS |
| `scripts/etl/lodes_curate_demographics.py` | Curate LODES WAC demographic columns | LODES |
| `scripts/etl/lodes_curate_industry_demographics.py` | Curate LODES industry-weighted demographics | LODES |
| `scripts/etl/newsrc_load_lodes.py` | Load LODES bulk .csv.gz files into Postgres | LODES |
| `scripts/etl/newsrc_load_abs.py` | Load Census Annual Business Survey CSV files | ABS |
| `scripts/etl/newsrc_load_cbp.py` | Load CBP pipe-delimited files into Postgres | CBP |
| `scripts/etl/newsrc_load_form5500.py` | Load Form 5500 bulk files into Postgres | Form 5500 |
| `scripts/etl/newsrc_load_ppp.py` | Load SBA PPP public CSV shards into Postgres | PPP |
| `scripts/etl/newsrc_load_usaspending.py` | Load USAspending All Contracts Full zip bundles | USAspending |
| `scripts/etl/newsrc_build_acs_profiles.py` | Build ACS occupation x demographic profiles from IPUMS | IPUMS ACS |
| `scripts/etl/parse_oews_employment_matrix.py` | Parse BLS occupation-industry staffing patterns (67,699 rows) | BLS OEWS |

### Corporate & Financial (10 files)

| Script | Description | Source |
|--------|-------------|--------|
| `scripts/etl/load_sec_edgar.py` | Load 517K SEC company records from submissions.zip | SEC |
| `scripts/etl/sec_edgar_full_index.py` | Alternative SEC loader from bulk submissions | SEC |
| `scripts/etl/load_sec_xbrl.py` | Load SEC XBRL financial data from companyfacts.zip | SEC XBRL |
| `scripts/etl/load_gleif_bods.py` | Restore GLEIF pgdump (52.7M rows) + extract US entities | GLEIF |
| `scripts/etl/extract_gleif_us_optimized.py` | Optimized US entity extraction from GLEIF | GLEIF |
| `scripts/etl/load_corpwatch.py` | Load CorpWatch API CSV data into PostgreSQL | CorpWatch |
| `scripts/etl/load_national_990.py` | Load 586K IRS 990 nonprofit filers (dedup by EIN) | IRS 990 |
| `scripts/etl/irs_bmf_loader.py` | Load IRS Business Master File (small test batches) | IRS BMF |
| `scripts/etl/load_bmf_bulk.py` | Bulk load 2M+ IRS BMF records (full production) | IRS BMF |
| `scripts/etl/load_mergent_al_fl.py` | Load ~14K D&B employers from Mergent Intellect exports | Mergent |

### Master Employer Seeding (8 files)

| Script | Description | Source |
|--------|-------------|--------|
| `scripts/etl/seed_master_chunked.py` | Seed master_employers from F7/SAM/Mergent/BMF (chunked) | Multiple |
| `scripts/etl/seed_master_from_sources.py` | Seed master_employers with EIN/name dedup | Multiple |
| `scripts/etl/seed_master_form5500.py` | Seed master_employer_source_ids from Form 5500 | Form 5500 |
| `scripts/etl/seed_master_nlrb.py` | Seed master_employers from unmatched NLRB participants | NLRB |
| `scripts/etl/seed_master_osha.py` | Seed master_employers from OSHA (non-union only) | OSHA |
| `scripts/etl/seed_master_ppp.py` | Seed master_employer_source_ids from PPP loans | PPP |
| `scripts/etl/seed_master_whd.py` | Seed master_employers from WHD cases | WHD |
| `scripts/etl/dedup_master_employers.py` | Resumable, batch-safe dedup for master_employers | Internal |

### New Source Orchestration (6 files)

| Script | Description | Source |
|--------|-------------|--------|
| `scripts/etl/newsrc_run_all.py` | Orchestrator for loading all new data sources | Multiple |
| `scripts/etl/newsrc_curate_all.py` | Build curated (typed, aggregated) tables from raw staging | Internal |
| `scripts/etl/newsrc_stage_to_raw.py` | Stage "New Data sources" files into canonical data/raw | File system |
| `scripts/etl/newsrc_manifest.py` | Build manifest and coverage report for new data sources | File system |
| `scripts/etl/newsrc_drop_raw_tables.py` | Drop raw newsrc_* staging tables to reclaim disk space | Internal |
| `scripts/etl/newsrc_common.py` | Shared helpers for loading new bulk data sources | Library |

### Geocoding & Industry (9 files)

| Script | Description | Source |
|--------|-------------|--------|
| `scripts/etl/geocode_batch_prep.py` | Export records needing geocoding to Census-compatible CSV | Internal |
| `scripts/etl/geocode_batch_run.py` | Submit geocoding batches to Census Bureau API | Census |
| `scripts/etl/backfill_census_tracts.py` | Backfill census_tract for already-geocoded employers | Internal |
| `scripts/etl/infer_naics.py` | Infer missing F7 NAICS from OSHA/WHD matches | Internal |
| `scripts/etl/infer_naics_keywords.py` | Infer missing NAICS from employer-name keyword patterns | Internal |
| `scripts/etl/infer_naics_round2.py` | Infer missing NAICS -- Round 2 | Internal |
| `scripts/etl/calculate_occupation_similarity.py` | Compute cosine similarity between occupations (8,731 pairs) | BLS |
| `scripts/etl/compute_industry_occupation_overlap.py` | Pre-compute weighted Jaccard industry overlap (130K pairs) | BLS |
| `scripts/etl/update_normalization.py` | Apply cleanco normalization to GLEIF/SEC name columns | Internal |

### Infrastructure (6 files)

| Script | Description | Source |
|--------|-------------|--------|
| `scripts/etl/build_crosswalk.py` | Build corporate_identifier_crosswalk (SEC/GLEIF/Mergent/F7) | Multiple |
| `scripts/etl/setup_afscme_scraper.py` | Create scraper tables + load AFSCME directory + OLMS matching | AFSCME |
| `scripts/etl/bulk_load_cbas.py` | Bulk load CBA contract files into database | CBA PDFs |
| `scripts/etl/migrate_scraper_schema.py` | Idempotent schema migration for union web scraper | Internal |
| `scripts/etl/flag_stale_unions.py` | Flag stale union records in unions_master | Internal |
| `scripts/etl/relink_orphan_locals.py` | Find locals where parent_fnum IS NULL but intermediate exists | Internal |

### ETL SQL Files (3 files)

| File | Description |
|------|-------------|
| `scripts/etl/create_irs_bmf_table.sql` | Schema DDL for IRS BMF table |
| `scripts/etl/create_master_employers.sql` | Schema DDL for master_employers table |
| `scripts/etl/create_sec_companies_table.sql` | Schema DDL for sec_companies table |

---

## Scripts: Matching (36 files)

### Core Pipeline (11 files)

| Script | Description | Role |
|--------|-------------|------|
| `scripts/matching/run_deterministic.py` | CLI for 6-tier deterministic matching | Entry point |
| `scripts/matching/deterministic_matcher.py` | Core v4 batch-optimized matching engine | Engine |
| `scripts/matching/splink_pipeline.py` | Splink probabilistic matching (DuckDB backend) | Fuzzy matching |
| `scripts/matching/splink_integrate.py` | Integrate Splink results into crosswalk | Integration |
| `scripts/matching/splink_config.py` | Splink model configuration and parameters | Config |
| `scripts/matching/train_adaptive_fuzzy_model.py` | Train/calibrate adaptive Splink fuzzy model | Training |
| `scripts/matching/create_unified_match_log.py` | Create/reset unified_match_log table | Setup |
| `scripts/matching/create_nlrb_bridge.py` | Create v_nlrb_employer_history view (13K rows) | View builder |
| `scripts/matching/resolve_historical_employers.py` | Identify historical F7 employers matching current ones | Resolution |
| `scripts/matching/backfill_name_columns.py` | Backfill normalized name columns on f7_employers_deduped | Data prep |
| `scripts/matching/build_employer_groups.py` | Canonical employer grouping (16,786 groups, 66,859 employers) | Grouping |

### Source Adapters (8 files)

| Script | Description | Role |
|--------|-------------|------|
| `scripts/matching/adapters/__init__.py` | Source adapters package | Package |
| `scripts/matching/adapters/osha_adapter.py` | OSHA source adapter for deterministic matching | Adapter |
| `scripts/matching/adapters/whd_adapter.py` | WHD source adapter for deterministic matching | Adapter |
| `scripts/matching/adapters/n990_adapter.py` | 990 source adapter for deterministic matching | Adapter |
| `scripts/matching/adapters/sam_adapter.py` | SAM source adapter for deterministic matching | Adapter |
| `scripts/matching/adapters/sec_adapter_module.py` | SEC EDGAR adapter for deterministic matching | Adapter |
| `scripts/matching/adapters/bmf_adapter_module.py` | IRS BMF adapter for deterministic matching | Adapter |
| `scripts/matching/adapters/corpwatch_adapter.py` | CorpWatch adapter for deterministic matching | Adapter |

### Matcher Implementations (5 files)

| Script | Description | Role |
|--------|-------------|------|
| `scripts/matching/matchers/__init__.py` | Matcher implementations package | Package |
| `scripts/matching/matchers/base.py` | Abstract BaseMatcher + MatchResult dataclasses | Base class |
| `scripts/matching/matchers/exact.py` | EIN exact, normalized name+state, aggressive (Tiers 1,2,4) | Exact matching |
| `scripts/matching/matchers/address.py` | Fuzzy name + street number + city + state (Tier 3) | Address matching |
| `scripts/matching/matchers/fuzzy.py` | pg_trgm similarity >= 0.4, composite scoring (Tier 5) | Fuzzy matching |

### Framework & Utilities (12 files)

| Script | Description | Role |
|--------|-------------|------|
| `scripts/matching/__init__.py` | Unified Employer Matching Module | Package |
| `scripts/matching/__main__.py` | Entry point for running matching module as script | Entry point |
| `scripts/matching/config.py` | MatchConfig dataclass -- scenario definitions | Config |
| `scripts/matching/normalizer.py` | Wrapper around name_normalization.py | Normalization |
| `scripts/matching/pipeline.py` | Older 4-tier MatchPipeline orchestrator | Legacy pipeline |
| `scripts/matching/cli.py` | Alternative CLI for matching module | CLI |
| `scripts/matching/differ.py` | Diff report generation -- compares matching runs | Reporting |
| `scripts/matching/match_quality_report.py` | Generate match quality metrics from unified_match_log | QA |
| `scripts/matching/match_nlrb_ulp.py` | Match NLRB ULP charged parties to f7_employers_deduped | Matching |
| `scripts/matching/normalize_match_methods.py` | Normalize match_method values to UPPER case | Cleanup |
| `scripts/matching/corroborate_matches.py` | Corroborate low-confidence matches via city/ZIP/NAICS | Validation |
| `scripts/matching/add_score_eligible.py` | Add score_eligible BOOLEAN column to legacy match tables | Migration |

---

## Scripts: Scoring (14 files)

Listed in MV dependency order.

| Script | Description | Creates/Refreshes | Depends On |
|--------|-------------|-------------------|------------|
| `scripts/scoring/compute_nlrb_patterns.py` | NLRB historical success pattern scoring | ref_nlrb_*_win_rates | NLRB tables |
| `scripts/scoring/update_whd_scores.py` | Update labor violation scores from WHD + NYC data | WHD scores | WHD matching |
| `scripts/scoring/compute_wage_outliers.py` | Compute QCEW wage outlier flags for employers | Wage outlier flags | QCEW |
| `scripts/scoring/create_scorecard_mv.py` | Create/refresh mv_organizing_scorecard (212K rows) | mv_organizing_scorecard | All matching |
| `scripts/scoring/compute_gower_similarity.py` | Gower distance -- top-5 comparable employers (269K) | employer_comparables | mv_organizing_scorecard |
| `scripts/scoring/build_employer_data_sources.py` | Build mv_employer_data_sources (146,863 rows) | mv_employer_data_sources | All matching + groups |
| `scripts/scoring/build_unified_scorecard.py` | Build mv_unified_scorecard (146,863 rows, 10 factors) | mv_unified_scorecard | mv_employer_data_sources |
| `scripts/scoring/build_target_data_sources.py` | Build mv_target_data_sources for non-union employers | mv_target_data_sources | master_employers |
| `scripts/scoring/build_target_scorecard.py` | Build mv_target_scorecard (4.4M rows, 8 signals) | mv_target_scorecard | mv_target_data_sources |
| `scripts/scoring/rebuild_search_mv.py` | Rebuild mv_employer_search (107K rows) | mv_employer_search | f7 + groups |
| `scripts/scoring/create_research_enhancements.py` | Create research_score_enhancements table | research_score_enhancements | Research runs |
| `scripts/scoring/refresh_all.py` | Orchestrate full MV rebuild chain in dependency order | All MVs | All scoring |
| `scripts/scoring/score_change_report.py` | Snapshot before rebuild, compare after | Report only | Any MV |
| `scripts/scoring/_pipeline_lock.py` | Advisory lock utility for pipeline scripts | Library | -- |

---

## Scripts: Analysis -- General (86 files)

### Audit & Data Quality (24 files)

| Script | Description | Category |
|--------|-------------|----------|
| `scripts/analysis/audit_990_matches.py` | Audit 990 match quality | Matching QA |
| `scripts/analysis/audit_api_performance.py` | Audit API endpoint performance | Performance |
| `scripts/analysis/audit_employer_groups.py` | Audit employer canonical groups | Matching QA |
| `scripts/analysis/audit_sam_matches.py` | Audit SAM match quality | Matching QA |
| `scripts/analysis/audit_trigram_quality.py` | Audit trigram matching quality | Matching QA |
| `scripts/analysis/audit_whd_matches.py` | Audit WHD match quality | Matching QA |
| `scripts/analysis/check_frontend_api_alignment.py` | Quick static audit for frontend/API field alignment | API QA |
| `scripts/analysis/check_js_innerhtml_safety.py` | Scoped JS safety check for innerHTML patterns | Security |
| `scripts/analysis/check_relation_dupes.py` | Check f7_union_employer_relations for duplicates | Data quality |
| `scripts/analysis/check_router_docs_drift.py` | Compare documented router endpoints vs current code | Doc QA |
| `scripts/analysis/fact_check_specs.py` | Verify 10 critical claims in agents/ and specs/ | Doc QA |
| `scripts/analysis/find_literal_password_bug.py` | Scan repo for literal-string DB password bug patterns | Security |
| `scripts/analysis/fix_literal_password_bug.py` | Auto-fix quoted-literal DB password bugs | Security |
| `scripts/analysis/flag_associations.py` | Flag association-like F7 records | Data quality |
| `scripts/analysis/flag_junk_records.py` | Flag junk/placeholder records in f7_employers_deduped | Data quality |
| `scripts/analysis/prioritize_innerhtml_api_risk.py` | Prioritize XSS paths from API JSON to innerHTML | Security |
| `scripts/analysis/run_ci_checks.py` | Run CI-style checks for parallel hardening lane | CI |
| `scripts/analysis/smoke_migrated_scopes.py` | Smoke checks for migrated scopes | Migration QA |
| `scripts/analysis/migrate_to_db_config_connection.py` | Migrate psycopg2.connect to db_config.get_connection | Migration |
| `scripts/analysis/rollback_db_config_migration.py` | Rollback helper for db_config migration backups | Migration |
| `scripts/analysis/rollback_password_fix.py` | Rollback helper for password-fix backups | Migration |
| `scripts/analysis/build_release_gate_summary.py` | Build release-gate summary from key reports | Release |
| `scripts/analysis/benchmark_endpoints.py` | Simple API endpoint benchmark utility | Performance |
| `scripts/analysis/capture_query_plans.py` | Capture EXPLAIN plans for slow-endpoint queries | Performance |

### Coverage & Statistics (9 files)

| Script | Description | Category |
|--------|-------------|----------|
| `scripts/analysis/analyze_coverage.py` | Analyze data coverage statistics | Coverage |
| `scripts/analysis/complete_coverage.py` | Complete coverage analysis | Coverage |
| `scripts/analysis/corrected_coverage.py` | Corrected coverage calculations | Coverage |
| `scripts/analysis/final_coverage.py` | Final coverage report | Coverage |
| `scripts/analysis/create_coverage_tables.py` | Create coverage reference tables | Coverage |
| `scripts/analysis/match_coverage_by_state.py` | Match coverage breakdown by state | Coverage |
| `scripts/analysis/score_validation_set.py` | Generate score validation test set across tiers/industries | Scoring |
| `scripts/analysis/validate_pillar_weights.py` | Validate pillar weights via logistic regression | Scoring |
| `scripts/analysis/validate_rpe_estimates.py` | Dual RPE Validation: NLRB Elections + 990 Self-Reported | Scoring |

### Matching & Grouping Analysis (10 files)

| Script | Description | Category |
|--------|-------------|----------|
| `scripts/analysis/matching_analysis.py` | General matching analysis | Matching |
| `scripts/analysis/compare_lm2_vs_f7.py` | Compare LM2 membership vs F7 employer data | Matching |
| `scripts/analysis/compare_splink_vs_rapidfuzz.py` | Compare Splink vs RapidFuzz batch matching on 5K OSHA | Matching |
| `scripts/analysis/diagnose_search_dedup.py` | Diagnostic queries for search dedup investigation | Matching |
| `scripts/analysis/validate_splink_retune.py` | Validate retuned Splink model on OSHA sample | Matching |
| `scripts/analysis/measure_score_eligible_impact.py` | Measure impact of score_eligible on employer tiers | Matching |
| `scripts/analysis/misclass_sweep.py` | Identify f7_employers_deduped misclassifications | Data quality |
| `scripts/analysis/multi_employer_analysis.py` | Multi-employer agreement analysis | Research |
| `scripts/analysis/multi_employer_final.py` | Multi-employer final analysis | Research |
| `scripts/analysis/multi_employer_fix.py` | Multi-employer fix implementation | Research |

### Investigation Reports (21 files)

| Script | Description | Category |
|--------|-------------|----------|
| `scripts/analysis/investigate_active_unions.py` | I18 -- Active Unions filed LM in last 3 years | Investigation |
| `scripts/analysis/investigate_corporate_hierarchy.py` | I20 -- Corporate Hierarchy coverage | Investigation |
| `scripts/analysis/investigate_enforcement_bias.py` | I12 -- Geographic Enforcement Bias | Investigation |
| `scripts/analysis/investigate_geocoding_gap.py` | I11 -- Geocoding Gap by Score Tier | Investigation |
| `scripts/analysis/investigate_legacy_matches.py` | I14 -- Legacy Match Quality Audit | Investigation |
| `scripts/analysis/investigate_mel_ro.py` | I19 -- Mel-Ro Construction OSHA Match Spot Check | Investigation |
| `scripts/analysis/investigate_missing_linkages.py` | I15 -- Missing Source ID Linkages Root Cause | Investigation |
| `scripts/analysis/investigate_orphaned_relations.py` | Investigate 60,373 orphaned relations rows | Investigation |
| `scripts/analysis/investigate_score_distribution.py` | I17 -- Score Distribution After Phase 1 Fixes | Investigation |
| `scripts/analysis/phase1_merge_validator.py` | Run core Phase 1 validation checks | Validation |
| `scripts/analysis/run_phase_1b.py` | Phase 1B Investigation Sprint Runner | Validation |
| `scripts/analysis/verify_completed_investigations.py` | Re-run key SQL queries from completed investigations | Verification |
| `scripts/analysis/verify_missing_unions.py` | Diagnostic script for orphan file numbers | Verification |
| `scripts/analysis/linkage_analysis.py` | Linkage analysis | Research |
| `scripts/analysis/show_crosswalk_detail.py` | Show detailed info for one-to-many crosswalk cases | Research |
| `scripts/analysis/multi_employer_fix_v2.py` | Multi-employer fix v2 | Research |
| `scripts/analysis/multi_employer_handler.py` | Multi-Employer Agreement Handler | Research |
| `scripts/analysis/demo_blend_prototype.py` | Prototype: blended workplace demographics estimate | Research |
| `scripts/analysis/research_diagnostic.py` | Research Agent diagnostic report | Research |
| `scripts/analysis/research_dossier_audit.py` | Research dossier completeness audit | Research |
| `scripts/analysis/research_gap_analysis.py` | Research web search gap analysis | Research |

### Sector & Membership Analysis (14 files)

| Script | Description | Category |
|--------|-------------|----------|
| `scripts/analysis/analyze_chapters.py` | Analyze chapters/specialized units causing over-counting | Membership |
| `scripts/analysis/analyze_deduplication.py` | Estimate deduplicated membership via hierarchy analysis | Membership |
| `scripts/analysis/analyze_deduplication_v2.py` | Corrected dedup analysis using TRIM on desig_name | Membership |
| `scripts/analysis/analyze_hierarchy_deep.py` | Deep dive into union hierarchy and double-counting | Membership |
| `scripts/analysis/analyze_membership_duplication.py` | Analyze membership duplication in union data | Membership |
| `scripts/analysis/analyze_remaining_overcount.py` | Analyze remaining over-count in deduped membership | Membership |
| `scripts/analysis/sector_analysis_1.py` | Sector analysis part 1 | Sector |
| `scripts/analysis/sector_analysis_2.py` | Sector analysis part 2 | Sector |
| `scripts/analysis/sector_analysis_3.py` | Sector analysis part 3 | Sector |
| `scripts/analysis/sector_final_summary.py` | Sector final summary | Sector |
| `scripts/analysis/teacher_sector_check.py` | Teacher sector classification check | Sector |
| `scripts/analysis/va_sector_check.py` | VA sector classification check | Sector |
| `scripts/analysis/federal_deep_dive.py` | Federal employer deep dive | Federal |
| `scripts/analysis/federal_final_verification.py` | Federal classification final verification | Federal |

### Geocoding & Schedule 13 (8 files)

| Script | Description | Category |
|--------|-------------|----------|
| `scripts/analysis/analyze_geocoding.py` | Analyze geocoding results | Geocoding |
| `scripts/analysis/analyze_geocoding2.py` | Geocoding analysis part 2 | Geocoding |
| `scripts/analysis/federal_misclass_check.py` | Federal misclassification check | Data quality |
| `scripts/analysis/tool_effectiveness.py` | Analyze research tool effectiveness from research_actions | Research |
| `scripts/analysis/analyze_schedule13.py` | Analyze Schedule 13 data | Schedule 13 |
| `scripts/analysis/analyze_schedule13_cp2.py` | Schedule 13 checkpoint 2 analysis | Schedule 13 |
| `scripts/analysis/analyze_schedule13_cp3.py` | Schedule 13 checkpoint 3 analysis | Schedule 13 |
| `scripts/analysis/analyze_schedule13_total.py` | Schedule 13 total analysis | Schedule 13 |

---

## Scripts: Analysis -- Demographics Comparison (88 scripts + 24 reports)

### Shared Modules (17 files)

| Script | Description | Version/Phase |
|--------|-------------|---------------|
| `scripts/analysis/demographics_comparison/__init__.py` | Package init | All |
| `scripts/analysis/demographics_comparison/config.py` | Configuration for demographics methodology comparison | All |
| `scripts/analysis/demographics_comparison/data_loaders.py` | Data loaders for demographics comparison | All |
| `scripts/analysis/demographics_comparison/eeo1_parser.py` | Parse EEO-1 CSV into ground truth demographic dicts | All |
| `scripts/analysis/demographics_comparison/metrics.py` | Comparison metrics for demographics estimation | All |
| `scripts/analysis/demographics_comparison/classifiers.py` | 5-dimensional company classification | All |
| `scripts/analysis/demographics_comparison/methodologies.py` | Six estimation methodologies (V1 originals) | V1 |
| `scripts/analysis/demographics_comparison/methodologies_v3.py` | V3: 9 new methods + inherited originals | V3 |
| `scripts/analysis/demographics_comparison/methodologies_v4.py` | V4: 7 new methods | V4 |
| `scripts/analysis/demographics_comparison/methodologies_v5.py` | V5: smoothed IPF, routing fixes, Expert models | V5 |
| `scripts/analysis/demographics_comparison/methodologies_v6.py` | V6: industry-LODES IPF, QCEW-adaptive | V6 |
| `scripts/analysis/demographics_comparison/cached_loaders.py` | Dict-cached wrappers around data_loaders | V1 |
| `scripts/analysis/demographics_comparison/cached_loaders_v2.py` | Extended cached loaders for V2 methods | V2 |
| `scripts/analysis/demographics_comparison/cached_loaders_v3.py` | Extended cached loaders for V3 methods | V3 |
| `scripts/analysis/demographics_comparison/cached_loaders_v4.py` | Extended cached loaders for V4 methods | V4 |
| `scripts/analysis/demographics_comparison/cached_loaders_v5.py` | Extended cached loaders for V5 methods | V5 |
| `scripts/analysis/demographics_comparison/cached_loaders_v6.py` | Extended cached loaders for V6 methods | V6 |

### Version-Specific Runners (12 files)

| Script | Description | Version/Phase |
|--------|-------------|---------------|
| `scripts/analysis/demographics_comparison/run_comparison.py` | Run all 6 methods against EEO-1 ground truth | V1 |
| `scripts/analysis/demographics_comparison/run_comparison_200.py` | Run 6 methods on 200 companies | V1 |
| `scripts/analysis/demographics_comparison/run_comparison_200_v2.py` | Run 11 methods (M1-M5 + M1b-M5b + M7) | V2 |
| `scripts/analysis/demographics_comparison/run_comparison_400_v3.py` | Run 14 methods (V1 + V2 + V3) | V3 |
| `scripts/analysis/demographics_comparison/run_comparison_all_v4.py` | Run ~23 methods (V1-V4) on all companies | V4 |
| `scripts/analysis/demographics_comparison/run_comparison_v5_run1.py` | Run V4+V5 methods on all 997 companies | V5 |
| `scripts/analysis/demographics_comparison/run_ablation_v6.py` | V6 Ablation Study Runner | V6 |
| `scripts/analysis/demographics_comparison/run_v9_1_partial_lock.py` | V9.1 Partial-Lock IPF: lock small race, scale White/Black | V9.1 |
| `scripts/analysis/demographics_comparison/run_v9_2.py` | V9.2: Training Expansion + County Diversity Calibration | V9.2 |
| `scripts/analysis/demographics_comparison/run_v9_best_of_ipf.py` | V9 best-of-expert + IPF experiment | V9 |
| `scripts/analysis/demographics_comparison/v9_best_of_ipf_claude.py` | V9: Best-of-Expert Per-Category + IPF Normalization | V9 |
| `scripts/analysis/demographics_comparison/run_v10.py` | **V10 Demographics Model** (current production) | V10 |

### Holdout Selectors (10 files)

| Script | Description | Version/Phase |
|--------|-------------|---------------|
| `scripts/analysis/demographics_comparison/select_companies.py` | Scan EEO-1 data, filter candidates, group by 7 axes | V1 |
| `scripts/analysis/demographics_comparison/select_200.py` | Stratified sampling: select 200 EEO-1 companies | V1 |
| `scripts/analysis/demographics_comparison/select_holdout_200.py` | Select holdout 200 excluding original 200 | V2 |
| `scripts/analysis/demographics_comparison/select_400.py` | Select 400 training excluding prior sets | V3 |
| `scripts/analysis/demographics_comparison/select_holdout_v3.py` | Select fresh holdout 200 for V3 | V3 |
| `scripts/analysis/demographics_comparison/build_fresh_holdout_v5.py` | Select fresh holdout for V5 final validation | V5 |
| `scripts/analysis/demographics_comparison/select_permanent_holdout.py` | Select 400 permanent holdout from full pool | V6+ |
| `scripts/analysis/demographics_comparison/select_permanent_holdout_100.py` | Select 1,000 permanent holdout, stratified | V8+ |
| `scripts/analysis/demographics_comparison/select_test_holdout_1000.py` | Select 1,000 stratified test holdout | V8+ |
| `scripts/analysis/demographics_comparison/select_v10_holdout.py` | Select V10 sealed holdout (1,000) + training set | V10 |

### Tuning & Testing (21 files)

| Script | Description | Version/Phase |
|--------|-------------|---------------|
| `scripts/analysis/demographics_comparison/compute_m3f_threshold.py` | Find optimal minority threshold for M3f via 5-fold CV | V4 |
| `scripts/analysis/demographics_comparison/compute_optimal_dampening.py` | Per-NAICS-group optimal dampening exponents for M3c | V3 |
| `scripts/analysis/demographics_comparison/compute_optimal_weights.py` | Per-NAICS-group optimal ACS/LODES weights for M1b | V2 |
| `scripts/analysis/demographics_comparison/compute_optimal_weights_v3.py` | Per-NAICS-group optimal weights for M1c and M5c | V3 |
| `scripts/analysis/demographics_comparison/debug_m4_family.py` | Debug: why M4c and M4d produce identical output | V4 |
| `scripts/analysis/demographics_comparison/test_dampening_grid.py` | Gender calibration and dampening optimization | V9.1 |
| `scripts/analysis/demographics_comparison/test_expert_combos.py` | Test all promising expert combinations | V9 |
| `scripts/analysis/demographics_comparison/test_g_clamp_blend.py` | V9: Expert G Two+ Clamp & D+G Blend re-evaluation | V9 |
| `scripts/analysis/demographics_comparison/test_hispanic_calibration.py` | Analyze Hispanic bias patterns and test calibration | V9.2 |
| `scripts/analysis/demographics_comparison/test_hispanic_scaling.py` | Test simple scaling corrections for Hispanic | V9.2 |
| `scripts/analysis/demographics_comparison/test_hispanic_v2.py` | Hispanic estimation v2: weight optimization + blending | V9.2 |
| `scripts/analysis/demographics_comparison/test_hybrid_d_occ.py` | V9 Hybrid: Expert D base + Occupation-chain adjustment | V9 |
| `scripts/analysis/demographics_comparison/test_improved_hispanic.py` | Improved Hispanic using industry-specific LODES | V9 |
| `scripts/analysis/demographics_comparison/test_manual_adjustment.py` | Manual county-diversity adjustments to reduce tail rates | V9 |
| `scripts/analysis/demographics_comparison/test_v11_signals.py` | Test V11 signal candidates vs V10 baseline | V11 |
| `scripts/analysis/demographics_comparison/test_v11_extended_signals.py` | V11: Tract Education + Company Size + Occupation Profile | V11 |
| `scripts/analysis/demographics_comparison/tune_v9_2_dampening.py` | Fine-grained dampening search for V9.2 | V9.2 |
| `scripts/analysis/demographics_comparison/push_p30_v9_2.py` | Push P>30pp from 6.3% to <6.0% -- targeted tuning | V9.2 |
| `scripts/analysis/demographics_comparison/push_p30_v9_2b.py` | Push P>30pp attempt 2: category-specific dampening | V9.2 |
| `scripts/analysis/demographics_comparison/push_p30_v9_2c.py` | Push P>30pp attempt 3: tier-specific race dampening | V9.2 |
| `scripts/analysis/demographics_comparison/push_p30_v9_2d.py` | Push P>30pp attempt 4: fine-grained search around optimal | V9.2 |

### Data Builders (11 files)

| Script | Description | Version/Phase |
|--------|-------------|---------------|
| `scripts/analysis/demographics_comparison/build_abs_owner_density.py` | Build ABS minority-owner density table from Census county data | V8 |
| `scripts/analysis/demographics_comparison/build_all_companies.py` | Merge 4 JSON company files into all_companies_v4.json | V4 |
| `scripts/analysis/demographics_comparison/build_expanded_training_v6.py` | Build expanded EEO-1 training set for Gate V2 | V6 |
| `scripts/analysis/demographics_comparison/build_gate_training_data.py` | Build gate training data from V4 results + DB features | V4 |
| `scripts/analysis/demographics_comparison/build_lodes_tract_table.py` | ETL: create cur_lodes_tract_metrics from LODES WAC CSV | V5 |
| `scripts/analysis/demographics_comparison/build_occ_chain_table.py` | Build precomputed occupation-chain demographics table | V9 |
| `scripts/analysis/demographics_comparison/build_sld_transit_table.py` | Build SLD transit score table from EPA Smart Location DB | V8 |
| `scripts/analysis/demographics_comparison/build_zip_tract_crosswalk.py` | Build zip_tract_crosswalk from LODES tract data | V5 |
| `scripts/analysis/demographics_comparison/recover_naics.py` | Recover NAICS codes for EEO-1 companies missing them | V4 |
| `scripts/analysis/demographics_comparison/load_bds_hc_benchmarks.py` | Parse BDS-HC bracket data into benchmark percentages | V7 |
| `scripts/analysis/demographics_comparison/load_pums_metro.py` | Aggregate PUMS ACS microdata into metro x industry table | V5 |

### Evaluation & Validation (12 files)

| Script | Description | Version/Phase |
|--------|-------------|---------------|
| `scripts/analysis/demographics_comparison/evaluate_gate_v0.py` | Evaluate Gate v0 vs M8 on 200-company holdout | V5 |
| `scripts/analysis/demographics_comparison/evaluate_expert_g_solo.py` | Evaluate Expert G solo on permanent holdout | V8.5 |
| `scripts/analysis/demographics_comparison/validate_v5_final.py` | V5 Final Validation: Gate v1 + Expert models on holdout | V5 |
| `scripts/analysis/demographics_comparison/validate_v6_final.py` | V6 Final Validation: full pipeline with dimension-specific | V6 |
| `scripts/analysis/demographics_comparison/verify_v9_2_7of7.py` | Verify and report 7/7 V9.2 configuration | V9.2 |
| `scripts/analysis/demographics_comparison/analyze_per_dimension_ceiling.py` | Analyze per-dimension expert selection ceiling | V8.5 |
| `scripts/analysis/demographics_comparison/analyze_tails.py` | Tail error distribution by sector/region/county/state | V9.1 |
| `scripts/analysis/demographics_comparison/analyze_tails_bias.py` | Signed bias per race category for every bucket/tier | V9.1 |
| `scripts/analysis/demographics_comparison/gen_v10_error_report.py` | Generate V10 error distribution data for report | V10 |
| `scripts/analysis/demographics_comparison/estimate_confidence.py` | V10 Confidence: GREEN/YELLOW/RED tier classifier | V10 |
| `scripts/analysis/demographics_comparison/bds_hc_check.py` | BDS-HC plausibility check | V7 |
| `scripts/analysis/demographics_comparison/floor_analysis.py` | Floor analysis: theoretical best for demographics estimation | V10+ |

### Gate Training (3 files)

| Script | Description | Version/Phase |
|--------|-------------|---------------|
| `scripts/analysis/demographics_comparison/train_v5_gate.py` | Train Gate v0: logistic regression routing model | V5 |
| `scripts/analysis/demographics_comparison/train_gate_v1.py` | Train Gate v1: routing model using OOF predictions | V5 |
| `scripts/analysis/demographics_comparison/train_gate_v2.py` | Train Gate V2: GradientBoosting on expanded training set | V6 |

### Report Generators (3 files)

| Script | Description | Version/Phase |
|--------|-------------|---------------|
| `scripts/analysis/demographics_comparison/generate_oof_predictions_v5.py` | Generate out-of-fold predictions for Expert A/B/D | V5 |
| `scripts/analysis/demographics_comparison/generate_report_v3.py` | Auto-generate METHODOLOGY_REPORT_V3.md from CSV | V3 |
| `scripts/analysis/demographics_comparison/generate_report_v4.py` | Auto-generate METHODOLOGY_REPORT_V4.md from CSV | V4 |

### Reports & Results (24 files)

| File | Description | Version |
|------|-------------|---------|
| `scripts/analysis/demographics_comparison/METHODOLOGY_REPORT_V2.md` | V2 methodology report | V2 |
| `scripts/analysis/demographics_comparison/METHODOLOGY_REPORT_V3.md` | V3 methodology report | V3 |
| `scripts/analysis/demographics_comparison/METHODOLOGY_REPORT_V4.md` | V4 methodology report | V4 |
| `scripts/analysis/demographics_comparison/V5_PROPOSAL.md` | V5 proposal | V5 |
| `scripts/analysis/demographics_comparison/V5_REVISION_PLAN.md` | V5 revision plan | V5 |
| `scripts/analysis/demographics_comparison/V5_COMPLETE_RESULTS.md` | V5 complete results (30 methods, 997 training + 208 holdout) | V5 |
| `scripts/analysis/demographics_comparison/V5_FINAL_REPORT.md` | V5 final validation summary | V5 |
| `scripts/analysis/demographics_comparison/HOLDOUT_VALIDATION_REPORT.md` | Holdout validation report | V5 |
| `scripts/analysis/demographics_comparison/Version 5 revision suggestions_codex.md` | Codex V5 revision suggestions | V5 |
| `scripts/analysis/demographics_comparison/GATE_V0_EVALUATION.md` | Gate v0 evaluation (rejected) | V5 |
| `scripts/analysis/demographics_comparison/V6_ABLATION_REPORT.md` | V6 ablation study results | V6 |
| `scripts/analysis/demographics_comparison/V6_FINAL_REPORT.md` | V6 final report (7/7 criteria) | V6 |
| `scripts/analysis/demographics_comparison/V6_RUN1_CHECKPOINT.md` | V6 run 1 checkpoint | V6 |
| `scripts/analysis/demographics_comparison/V6_RUN2_CHECKPOINT.md` | V6 run 2 checkpoint | V6 |
| `scripts/analysis/demographics_comparison/V7_ERROR_DISTRIBUTION.md` | V7 error distribution analysis | V7 |
| `scripts/analysis/demographics_comparison/V7_RECOMMENDATIONS.md` | V7 recommendations | V7 |
| `scripts/analysis/demographics_comparison/V8_FULL_SUMMARY.md` | V8 full summary (4/7 criteria) | V8 |
| `scripts/analysis/demographics_comparison/V8.5_ARCHITECTURE_ANALYSIS.md` | V8.5 architecture analysis (87% dimension disagreement) | V8.5 |
| `scripts/analysis/demographics_comparison/V9_TWO_MODEL_PROPOSAL.md` | V9 two-model architecture proposal | V9 |
| `scripts/analysis/demographics_comparison/V9_BEST_OF_IPF_RESULTS.md` | V9 best-of-IPF results | V9 |
| `scripts/analysis/demographics_comparison/CODEX_V9_BEST_OF_IPF_SUMMARY.md` | Codex V9 best-of-IPF summary | V9 |
| `scripts/analysis/demographics_comparison/V9_1_METHODOLOGY_AND_RESULTS.md` | V9.1 full methodology and results | V9.1 |
| `scripts/analysis/demographics_comparison/V9_2_FULL_REPORT.md` | V9.2 full report (7/7 criteria) | V9.2 |
| `scripts/analysis/demographics_comparison/V10_ERROR_DISTRIBUTION.md` | V10 error distribution with per-dimension breakdowns | V10 |

---

## Scripts: CBA Pipeline (18 files)

Numbered stages 01-11 form the sequential processing pipeline.

| Script | Description | Stage |
|--------|-------------|-------|
| `scripts/cba/__init__.py` | CBA package init | -- |
| `scripts/cba/01_extract_text.py` | Extract text from CBA PDF and store in database | 01 |
| `scripts/cba/02_extract_parties.py` | Extract party names, dates, and metadata | 02 |
| `scripts/cba/03_find_articles.py` | Find article/section headings, break into labeled chunks | 03 |
| `scripts/cba/04_tag_category.py` | Tag provisions by category using rule engine | 04 |
| `scripts/cba/05_parse_toc.py` | Parse Table of Contents (3-tier: explicit, dotted, heuristic) | 05 |
| `scripts/cba/06_split_sections.py` | Split full contract text into sections using parsed TOC | 06 |
| `scripts/cba/07_extract_page_images.py` | Extract PDF pages as PNG images (pdfplumber) | 07 |
| `scripts/cba/08_enrich_sections.py` | Enrich sections with structured attributes (Pass 3) | 08 |
| `scripts/cba/09_decompose_contract.py` | Orchestrator for progressive contract decomposition | 09 |
| `scripts/cba/10_link_provisions_sections.py` | Link provisions to containing sections via section_id FK | 10 |
| `scripts/cba/11_extract_values.py` | Extract structured values (dollars, percentages, day counts) | 11 |
| `scripts/cba/process_contract.py` | Orchestrator: run full CBA rule-engine pipeline | Orchestrator |
| `scripts/cba/batch_process.py` | Batch processor for CBA PDFs | Batch |
| `scripts/cba/rule_engine.py` | Core rule-based matching engine for provision categorization | Engine |
| `scripts/cba/models.py` | Shared dataclasses for the CBA rule-engine pipeline | Models |
| `scripts/cba/review_provisions.py` | Interactive review CLI for extracted provisions | Review |
| `scripts/cba/audit_coverage.py` | Coverage audit for CBA cross-contract comparison | Audit |

---

## Scripts: Research Agent (6 files)

| Script | Description | Role |
|--------|-------------|------|
| `scripts/research/__init__.py` | Research Agent package | Package |
| `scripts/research/agent.py` | Research Agent (Phase 5.8) -- main orchestrator | Core |
| `scripts/research/auto_grader.py` | Research Agent Auto-Grader (Phase 5.3/5.7) | Grading |
| `scripts/research/batch_research.py` | Batch research runner for Phase 2.7 backfill | Batch |
| `scripts/research/employer_lookup.py` | Auto-lookup employer_id from f7_employers_deduped | Utility |
| `scripts/research/tools.py` | Research Agent internal tool definitions | Tools |

---

## Scripts: Web Scraper (15 files)

Pipeline steps run sequentially; specialized scripts run ad-hoc.

| Script | Description | Pipeline Step |
|--------|-------------|---------------|
| `scripts/scraper/fetch_union_sites.py` | Fetch union web pages via Crawl4AI (rate-limited) | 1 |
| `scripts/scraper/discover_pages.py` | Page discovery for union web scraper | 1.5 |
| `scripts/scraper/extract_union_data.py` | Heuristic extraction of employers, contracts, membership | 2 |
| `scripts/scraper/extract_wordpress.py` | WordPress REST API extraction | 2b |
| `scripts/scraper/extract_gemini_fallback.py` | Gemini API fallback for profiles with 0 employers | 2c |
| `scripts/scraper/parse_structured.py` | Shared HTML parser for tiered extraction | 2 (lib) |
| `scripts/scraper/fix_extraction.py` | Remove boilerplate false positives | 3 |
| `scripts/scraper/clean_wp_employers.py` | Clean up noise from wp_api extracted employers | 3b |
| `scripts/scraper/match_web_employers.py` | 5-tier employer matching against F7 + OSHA | 4 |
| `scripts/scraper/run_extraction_pipeline.py` | Master pipeline script for tiered extraction | Orchestrator |
| `scripts/scraper/export_html.py` | Generate browsable HTML data viewer | Reporting |
| `scripts/scraper/extraction_report.py` | Validation reporting for extraction pipeline | Reporting |
| `scripts/scraper/fetch_summary.py` | Status report on scraping progress | Monitoring |
| `scripts/scraper/read_profiles.py` | Batch inspect raw scraped text | Utility |
| `scripts/scraper/extract_ex21.py` | Extract SEC Exhibit 21 subsidiary data | Special |

---

## Scripts: Maintenance (19 files)

### Data Quality (6 files)

| Script | Description | Schedule/Trigger |
|--------|-------------|-----------------|
| `scripts/maintenance/create_data_freshness.py` | Track 15 data source freshness -- UPSERT refresh | Monthly |
| `scripts/maintenance/coverage_qa.py` | Monthly factor coverage QA by state and industry | Monthly |
| `scripts/maintenance/check_doc_consistency.py` | Check documentation consistency against live database | Monthly |
| `scripts/maintenance/generate_db_inventory.py` | Generate database inventory report for PROJECT_STATE.md | Before doc updates |
| `scripts/maintenance/generate_project_metrics.py` | Generate comprehensive project metrics report | Monthly |
| `scripts/maintenance/backup_labor_data.py` | Database backup script | Daily (Task Scheduler) |
| `scripts/maintenance/backup_database.bat` | Windows batch file for scheduled DB backup | Daily (Task Scheduler) |
| `scripts/maintenance/check_catalog_coverage.py` | Check PROJECT_CATALOG.md coverage against filesystem | After file changes |

### Match Cleanup (7 files)

| Script | Description | Schedule/Trigger |
|--------|-------------|-----------------|
| `scripts/maintenance/fix_dangling_matches.py` | Mark dangling unified_match_log rows as orphaned | After matching |
| `scripts/maintenance/fix_signatories_and_groups.py` | Flag signatory entries, merge split canonical groups | As needed |
| `scripts/maintenance/rebuild_legacy_tables.py` | Rebuild legacy match tables from unified_match_log | After matching |
| `scripts/maintenance/reject_low_fuzzy.py` | Supersede active fuzzy matches below similarity threshold | After matching |
| `scripts/maintenance/reject_low_trigram.py` | Reject low-quality trigram matches | After matching |
| `scripts/maintenance/reject_stale_osha.py` | Reject stale OSHA matches with name similarity < 0.80 | After matching |
| `scripts/maintenance/reject_stale_splink_all.py` | Reject stale Splink matches with similarity < 0.80 | After matching |

### Resolution & Cleanup (4 files)

| Script | Description | Schedule/Trigger |
|--------|-------------|-----------------|
| `scripts/maintenance/resolve_duplicate_matches.py` | Resolve duplicate match entries | As needed |
| `scripts/maintenance/resolve_missing_unions.py` | Resolve orphaned union file numbers in relations | After union data changes |
| `scripts/maintenance/drop_orphan_industry_views.py` | Drop orphaned industry-specific views (one-time) | One-time |
| `scripts/maintenance/drop_unused_db_objects.py` | Drop confirmed-unused database objects | One-time |

---

## Scripts: Setup & Performance (2 files)

| Script | Description | Role |
|--------|-------------|------|
| `scripts/setup/init_database.py` | Database initialization and verification | Setup |
| `scripts/performance/profile_matching.py` | Profile matching pipeline and DB query performance | Profiling |

---

## API Layer (43 files)

### Core (8 files)

| File | Description |
|------|-------------|
| `api/__init__.py` | API package init |
| `api/main.py` | FastAPI app entry point (port 8001) |
| `api/config.py` | Application configuration from .env |
| `api/database.py` | Database connection pool singleton |
| `api/dependencies.py` | Shared FastAPI dependencies (auth, authz) |
| `api/helpers.py` | Shared helper functions and constants |
| `api/data_source_catalog.py` | Canonical data source inventory |
| `api/match_labels.py` | Human-readable match provenance labels |

### Middleware (4 files)

| File | Description |
|------|-------------|
| `api/middleware/__init__.py` | Middleware package init |
| `api/middleware/auth.py` | JWT authentication middleware |
| `api/middleware/logging.py` | Structured request logging |
| `api/middleware/rate_limit.py` | In-memory sliding window rate limiter |

### Models (2 files)

| File | Description |
|------|-------------|
| `api/models/__init__.py` | Models package init |
| `api/models/schemas.py` | Pydantic request/response validation models |

### Services (2 files)

| File | Description |
|------|-------------|
| `api/services/__init__.py` | Services package init |
| `api/services/demographics_v5.py` | V5 Demographics Estimation API Service |

### Routers (27 files)

| Router | Prefix | Key Endpoints | Description |
|--------|--------|---------------|-------------|
| `api/routers/__init__.py` | -- | -- | Package init |
| `api/routers/auth.py` | `/api/auth` | login, register, refresh | Authentication |
| `api/routers/employers.py` | `/api/employers` | search, detail, flags, NAICS, comparables | Employer search & detail |
| `api/routers/unions.py` | `/api/unions` | list, detail, hierarchy, financials | Union explorer |
| `api/routers/scorecard.py` | `/api/scorecard` | list, detail, export | Organizing scorecard |
| `api/routers/target_scorecard.py` | `/api/target-scorecard` | list, detail, signals | Non-union target scorecard |
| `api/routers/demographics.py` | `/api/demographics` | state, industry, company | ACS workforce demographics |
| `api/routers/density.py` | `/api/density` | industry, state, county | BLS union density |
| `api/routers/nlrb.py` | `/api/nlrb` | elections, docket, history | NLRB data |
| `api/routers/osha.py` | `/api/osha` | violations, summary | OSHA violations |
| `api/routers/whd.py` | `/api/whd` | cases, summary | Wage & Hour cases |
| `api/routers/corporate.py` | `/api/corporate` | hierarchy, family, SEC | Corporate relationships |
| `api/routers/research.py` | `/api/research` | runs, dossier, facts, tools | Research agent |
| `api/routers/cba.py` | `/api/cba` | contracts, provisions, sections | CBA search & detail |
| `api/routers/campaigns.py` | `/api/campaigns` | outcomes, trends | Campaign outcomes |
| `api/routers/master.py` | `/api/master` | search, detail | Master employer |
| `api/routers/profile.py` | `/api/profile` | detail, related | Employer profile |
| `api/routers/organizing.py` | `/api/organizing` | capacity, targets | Organizing capacity |
| `api/routers/projections.py` | `/api/projections` | industry, occupation | BLS projections |
| `api/routers/public_sector.py` | `/api/public-sector` | agencies, unions | Public sector unions |
| `api/routers/sectors.py` | `/api/sectors` | overview, detail | Multi-sector targets |
| `api/routers/museums.py` | `/api/museums` | list, unionization | Museum sector |
| `api/routers/trends.py` | `/api/trends` | membership, elections | Historical trends |
| `api/routers/lookups.py` | `/api/lookups` | states, NAICS, unions | Reference dropdowns |
| `api/routers/vr.py` | `/api/vr` | list, detail | Voluntary recognition |
| `api/routers/health.py` | `/api/health` | ping, status | Health check |
| `api/routers/system.py` | `/api/system` | admin, refresh, freshness | System admin |

---

## Frontend (126 source + 38 test files)

### App Shell (3 files)

| File | Description | Feature |
|------|-------------|---------|
| `frontend/src/App.jsx` | Root component with routing | Shell |
| `frontend/src/main.jsx` | React entry point | Shell |
| `frontend/src/index.css` | Global styles + Tailwind | Shell |

### UI Primitives (8 files)

| File | Description | Feature |
|------|-------------|---------|
| `frontend/src/components/ui/badge.jsx` | Badge component | UI |
| `frontend/src/components/ui/button.jsx` | Button component | UI |
| `frontend/src/components/ui/card.jsx` | Card component | UI |
| `frontend/src/components/ui/input.jsx` | Input component | UI |
| `frontend/src/components/ui/label.jsx` | Label component | UI |
| `frontend/src/components/ui/select.jsx` | Select component | UI |
| `frontend/src/components/ui/skeleton.jsx` | Loading skeleton component | UI |
| `frontend/src/lib/utils.js` | Tailwind class merge utility | UI |

### Shared Components (17 files)

| File | Description | Feature |
|------|-------------|---------|
| `frontend/src/shared/components/Breadcrumbs.jsx` | Navigation breadcrumbs | Shared |
| `frontend/src/shared/components/CollapsibleCard.jsx` | Expandable card container | Shared |
| `frontend/src/shared/components/CommandPalette.jsx` | Command palette (Ctrl+K) | Shared |
| `frontend/src/shared/components/ConfidenceDots.jsx` | Confidence indicator dots | Shared |
| `frontend/src/shared/components/DataSourceBadge.jsx` | Data source badge | Shared |
| `frontend/src/shared/components/ErrorBoundary.jsx` | React error boundary | Shared |
| `frontend/src/shared/components/ErrorPage.jsx` | Error page component | Shared |
| `frontend/src/shared/components/HelpSection.jsx` | Help section component | Shared |
| `frontend/src/shared/components/Layout.jsx` | Page layout with sidebar + nav | Shared |
| `frontend/src/shared/components/MiniStat.jsx` | Mini statistic card | Shared |
| `frontend/src/shared/components/NavBar.jsx` | Top navigation bar | Shared |
| `frontend/src/shared/components/NotFound.jsx` | 404 page component | Shared |
| `frontend/src/shared/components/PageSkeleton.jsx` | Full page loading skeleton | Shared |
| `frontend/src/shared/components/ProtectedRoute.jsx` | Auth-gated route wrapper | Shared |
| `frontend/src/shared/components/ScoreGauge.jsx` | Score gauge visualization | Shared |
| `frontend/src/shared/components/SidebarTOC.jsx` | Sidebar table of contents | Shared |
| `frontend/src/shared/components/SourceAttribution.jsx` | Source attribution label | Shared |

### API Hooks (12 files)

| File | Description | Feature |
|------|-------------|---------|
| `frontend/src/shared/api/client.js` | Axios client with interceptors | API |
| `frontend/src/shared/api/queryClient.js` | TanStack Query client config | API |
| `frontend/src/shared/api/admin.js` | Admin API hooks | API |
| `frontend/src/shared/api/campaigns.js` | Campaign API hooks | API |
| `frontend/src/shared/api/cba.js` | CBA API hooks | API |
| `frontend/src/shared/api/employers.js` | Employer API hooks | API |
| `frontend/src/shared/api/lookups.js` | Lookup API hooks | API |
| `frontend/src/shared/api/profile.js` | Profile API hooks | API |
| `frontend/src/shared/api/research.js` | Research API hooks | API |
| `frontend/src/shared/api/scorecard.js` | Scorecard API hooks | API |
| `frontend/src/shared/api/targets.js` | Target scorecard API hooks | API |
| `frontend/src/shared/api/unions.js` | Union API hooks | API |

### Shared Hooks, Stores, Constants (4 files)

| File | Description | Feature |
|------|-------------|---------|
| `frontend/src/shared/hooks/useAuth.js` | Authentication hook | Auth |
| `frontend/src/shared/hooks/useCollapsibleState.js` | Collapsible state hook | UI |
| `frontend/src/shared/stores/authStore.js` | Zustand auth store | Auth |
| `frontend/src/shared/constants/sourceColors.js` | Source color definitions | Theme |

### Feature: Search (8 files)

| File | Description | Feature |
|------|-------------|---------|
| `frontend/src/features/search/SearchPage.jsx` | Main search page | Search |
| `frontend/src/features/search/SearchBar.jsx` | Search input with autocomplete | Search |
| `frontend/src/features/search/SearchFilters.jsx` | Filter controls | Search |
| `frontend/src/features/search/ResultsTable.jsx` | Search results table | Search |
| `frontend/src/features/search/SearchResultCard.jsx` | Individual result card | Search |
| `frontend/src/features/search/EmptyState.jsx` | Empty state component | Search |
| `frontend/src/features/search/SourceBadge.jsx` | Source badge for results | Search |
| `frontend/src/features/search/useSearchState.js` | Search state management | Search |

### Feature: Employer Profile (23 files)

| File | Description | Feature |
|------|-------------|---------|
| `frontend/src/features/employer-profile/EmployerProfilePage.jsx` | Main employer profile page | Profile |
| `frontend/src/features/employer-profile/BasicProfileView.jsx` | Basic profile summary view | Profile |
| `frontend/src/features/employer-profile/ProfileHeader.jsx` | Profile header section | Profile |
| `frontend/src/features/employer-profile/ProfileActionButtons.jsx` | Action buttons (flag, research) | Profile |
| `frontend/src/features/employer-profile/ScorecardSection.jsx` | Scorecard factor display | Profile |
| `frontend/src/features/employer-profile/WorkforceDemographicsCard.jsx` | Demographics visualization | Profile |
| `frontend/src/features/employer-profile/DataProvenanceCard.jsx` | Data source provenance card | Profile |
| `frontend/src/features/employer-profile/ResearchInsightsCard.jsx` | Research insights display | Profile |
| `frontend/src/features/employer-profile/ResearchNotesCard.jsx` | Research notes display | Profile |
| `frontend/src/features/employer-profile/CorporateHierarchyCard.jsx` | Corporate hierarchy view | Profile |
| `frontend/src/features/employer-profile/GovernmentContractsCard.jsx` | Government contracts card | Profile |
| `frontend/src/features/employer-profile/FinancialDataCard.jsx` | Financial data display | Profile |
| `frontend/src/features/employer-profile/UnionRelationshipsCard.jsx` | Union relationships view | Profile |
| `frontend/src/features/employer-profile/NlrbSection.jsx` | NLRB elections section | Profile |
| `frontend/src/features/employer-profile/OshaSection.jsx` | OSHA violations section | Profile |
| `frontend/src/features/employer-profile/NycEnforcementSection.jsx` | NYC enforcement section | Profile |
| `frontend/src/features/employer-profile/OccupationSection.jsx` | Occupation data section | Profile |
| `frontend/src/features/employer-profile/WhdCard.jsx` | WHD cases card | Profile |
| `frontend/src/features/employer-profile/ComparablesCard.jsx` | Comparable employers card | Profile |
| `frontend/src/features/employer-profile/CrossReferencesSection.jsx` | Cross-reference section | Profile |
| `frontend/src/features/employer-profile/FlagModal.jsx` | Flag employer modal | Profile |
| `frontend/src/features/employer-profile/SignalInventory.jsx` | Signal inventory section | Profile |
| `frontend/src/features/employer-profile/CampaignOutcomeCard.jsx` | Campaign outcome card | Profile |

### Feature: Research (12 files)

| File | Description | Feature |
|------|-------------|---------|
| `frontend/src/features/research/ResearchPage.jsx` | Main research page | Research |
| `frontend/src/features/research/ResearchResultPage.jsx` | Research result detail | Research |
| `frontend/src/features/research/CompareRunsPage.jsx` | Compare research runs | Research |
| `frontend/src/features/research/ResearchRunsTable.jsx` | Research runs list table | Research |
| `frontend/src/features/research/ResearchFilters.jsx` | Research filter controls | Research |
| `frontend/src/features/research/DossierHeader.jsx` | Dossier header component | Research |
| `frontend/src/features/research/DossierSection.jsx` | Dossier section component | Research |
| `frontend/src/features/research/FactRow.jsx` | Fact row with review controls | Research |
| `frontend/src/features/research/ActionLog.jsx` | Research action log | Research |
| `frontend/src/features/research/NewResearchModal.jsx` | New research request modal | Research |
| `frontend/src/features/research/PriorityReviewCard.jsx` | Priority review card | Research |
| `frontend/src/features/research/useResearchState.js` | Research state management | Research |

### Feature: Scorecard & Targets (9 files)

| File | Description | Feature |
|------|-------------|---------|
| `frontend/src/features/scorecard/TargetsPage.jsx` | Targets page | Scorecard |
| `frontend/src/features/scorecard/TargetsTable.jsx` | Targets list table | Scorecard |
| `frontend/src/features/scorecard/TargetsFilters.jsx` | Target filter controls | Scorecard |
| `frontend/src/features/scorecard/TargetStats.jsx` | Target statistics summary | Scorecard |
| `frontend/src/features/scorecard/QualityIndicator.jsx` | Quality indicator component | Scorecard |
| `frontend/src/features/scorecard/UnifiedScorecardPage.jsx` | Unified scorecard page | Scorecard |
| `frontend/src/features/scorecard/UnifiedScorecardTable.jsx` | Unified scorecard table | Scorecard |
| `frontend/src/features/scorecard/CompareEmployersPage.jsx` | Compare employers page | Scorecard |
| `frontend/src/features/scorecard/useTargetsState.js` | Targets state management | Scorecard |

### Feature: Union Explorer (17 files)

| File | Description | Feature |
|------|-------------|---------|
| `frontend/src/features/union-explorer/UnionsPage.jsx` | Main unions page | Unions |
| `frontend/src/features/union-explorer/UnionProfilePage.jsx` | Union profile page | Unions |
| `frontend/src/features/union-explorer/UnionProfileHeader.jsx` | Union profile header | Unions |
| `frontend/src/features/union-explorer/UnionResultsTable.jsx` | Union search results table | Unions |
| `frontend/src/features/union-explorer/UnionFilters.jsx` | Union filter controls | Unions |
| `frontend/src/features/union-explorer/UnionEmployersTable.jsx` | Union employers table | Unions |
| `frontend/src/features/union-explorer/UnionFinancialsSection.jsx` | Union financials section | Unions |
| `frontend/src/features/union-explorer/UnionHealthSection.jsx` | Union health indicators | Unions |
| `frontend/src/features/union-explorer/UnionElectionsSection.jsx` | Union elections section | Unions |
| `frontend/src/features/union-explorer/UnionDisbursementsSection.jsx` | Union disbursements section | Unions |
| `frontend/src/features/union-explorer/AffiliationTree.jsx` | Affiliation hierarchy tree | Unions |
| `frontend/src/features/union-explorer/SisterLocalsSection.jsx` | Sister locals section | Unions |
| `frontend/src/features/union-explorer/MembershipSection.jsx` | Membership data section | Unions |
| `frontend/src/features/union-explorer/OrganizingCapacitySection.jsx` | Organizing capacity section | Unions |
| `frontend/src/features/union-explorer/ExpansionTargetsSection.jsx` | Expansion targets section | Unions |
| `frontend/src/features/union-explorer/NationalUnionsSummary.jsx` | National unions summary | Unions |
| `frontend/src/features/union-explorer/useUnionsState.js` | Unions state management | Unions |

### Feature: CBA (4 files)

| File | Description | Feature |
|------|-------------|---------|
| `frontend/src/features/cba/CBADashboard.jsx` | CBA dashboard page | CBA |
| `frontend/src/features/cba/CBASearch.jsx` | CBA search interface | CBA |
| `frontend/src/features/cba/CBADetail.jsx` | CBA detail view | CBA |
| `frontend/src/features/cba/CBACompare.jsx` | CBA comparison view | CBA |

### Feature: Admin (8 files)

| File | Description | Feature |
|------|-------------|---------|
| `frontend/src/features/admin/SettingsPage.jsx` | Admin settings page | Admin |
| `frontend/src/features/admin/HealthStatusCard.jsx` | System health status card | Admin |
| `frontend/src/features/admin/DataFreshnessCard.jsx` | Data freshness card | Admin |
| `frontend/src/features/admin/MatchQualityCard.jsx` | Match quality summary card | Admin |
| `frontend/src/features/admin/MatchReviewCard.jsx` | Match review interface | Admin |
| `frontend/src/features/admin/PlatformStatsCard.jsx` | Platform statistics card | Admin |
| `frontend/src/features/admin/RefreshActionsCard.jsx` | MV refresh actions card | Admin |
| `frontend/src/features/admin/UserRegistrationCard.jsx` | User registration card | Admin |

### Feature: Auth (1 file)

| File | Description | Feature |
|------|-------------|---------|
| `frontend/src/features/auth/LoginPage.jsx` | Login page | Auth |

### Config (2 files)

| File | Description | Feature |
|------|-------------|---------|
| `frontend/vite.config.js` | Vite build configuration | Config |
| `frontend/eslint.config.js` | ESLint configuration | Config |

### Frontend Tests (38 files)

| Test File | Tests | Feature |
|-----------|-------|---------|
| `frontend/__tests__/setup.js` | Test setup (mocks, providers) | Setup |
| `frontend/__tests__/ActionLog.test.jsx` | Research action log tests | Research |
| `frontend/__tests__/AffiliationTree.test.jsx` | Affiliation tree tests | Unions |
| `frontend/__tests__/CampaignOutcome.test.jsx` | Campaign outcome card tests | Profile |
| `frontend/__tests__/CompareEmployers.test.jsx` | Compare employers page tests | Scorecard |
| `frontend/__tests__/DataProvenanceCard.test.jsx` | Data provenance card tests | Profile |
| `frontend/__tests__/EmployerProfilePage.test.jsx` | Employer profile page tests | Profile |
| `frontend/__tests__/ErrorBoundary.test.jsx` | Error boundary tests | Shared |
| `frontend/__tests__/FactRow.test.jsx` | Fact row tests | Research |
| `frontend/__tests__/Layout.test.jsx` | Layout component tests | Shared |
| `frontend/__tests__/LoginPage.test.jsx` | Login page tests | Auth |
| `frontend/__tests__/MatchReviewCard.test.jsx` | Match review card tests | Admin |
| `frontend/__tests__/NavBar.test.jsx` | NavBar component tests | Shared |
| `frontend/__tests__/NlrbDocket.test.jsx` | NLRB docket section tests | Profile |
| `frontend/__tests__/NycEnforcementSection.test.jsx` | NYC enforcement section tests | Profile |
| `frontend/__tests__/OccupationSection.test.jsx` | Occupation section tests | Profile |
| `frontend/__tests__/ProfileActionButtons.test.jsx` | Profile action buttons tests | Profile |
| `frontend/__tests__/ProfileCards.test.jsx` | Profile cards integration tests | Profile |
| `frontend/__tests__/ProtectedRoute.test.jsx` | Protected route tests | Auth |
| `frontend/__tests__/ResearchInsightsCard.test.jsx` | Research insights card tests | Profile |
| `frontend/__tests__/ResearchPage.test.jsx` | Research page tests | Research |
| `frontend/__tests__/ResearchResult.test.jsx` | Research result tests | Research |
| `frontend/__tests__/ResultsTable.test.jsx` | Results table tests | Search |
| `frontend/__tests__/ScorecardSection.test.jsx` | Scorecard section tests | Profile |
| `frontend/__tests__/SearchBar.test.jsx` | Search bar tests | Search |
| `frontend/__tests__/SearchEnhancements.test.jsx` | Search enhancement tests | Search |
| `frontend/__tests__/SearchFilters.test.jsx` | Search filter tests | Search |
| `frontend/__tests__/SearchPage.test.jsx` | Search page tests | Search |
| `frontend/__tests__/SettingsPage.test.jsx` | Settings page tests | Admin |
| `frontend/__tests__/SourceAttribution.test.jsx` | Source attribution tests | Shared |
| `frontend/__tests__/TargetsPage.test.jsx` | Targets page tests | Scorecard |
| `frontend/__tests__/TargetsTable.test.jsx` | Targets table tests | Scorecard |
| `frontend/__tests__/UnifiedScorecardPage.test.jsx` | Unified scorecard tests | Scorecard |
| `frontend/__tests__/UnionDisbursementsSection.test.jsx` | Union disbursements tests | Unions |
| `frontend/__tests__/UnionProfilePage.test.jsx` | Union profile tests | Unions |
| `frontend/__tests__/UnionsPage.test.jsx` | Unions page tests | Unions |
| `frontend/__tests__/WorkforceDemographicsCard.test.jsx` | Workforce demographics tests | Profile |
| `frontend/__tests__/profile-hooks.test.js` | Profile hooks tests | Profile |

---

## Shared Libraries (11 files)

### src/python/matching/ (3 files)

| File | Description |
|------|-------------|
| `src/python/matching/__init__.py` | Matching utilities package |
| `src/python/matching/name_normalization.py` | **Single source of truth** for name normalization (3 levels + phonetic) |
| `src/python/matching/integration_stubs.py` | Integration stubs for adopting canonical normalization |

### src/python/cba_tool/ (5 files)

| File | Description |
|------|-------------|
| `src/python/cba_tool/__init__.py` | CBA extraction tooling package |
| `src/python/cba_tool/cba_analyzer.py` | CBA contract analyzer |
| `src/python/cba_tool/cba_processor.py` | CBA document processor |
| `src/python/cba_tool/langextract_processor.py` | LangExtract-based processor |
| `src/python/cba_tool/test_processor.py` | CBA processor tests |

### src/python/nlrb/ (1 file)

| File | Description |
|------|-------------|
| `src/python/nlrb/load_nlrb_data.py` | NLRB data loading utilities |

### src/ root (2 files)

| File | Description |
|------|-------------|
| `src/__init__.py` | Top-level source package |
| `src/python/__init__.py` | Python source modules package |

---

## Backend Tests (84 files)

### Test Infrastructure (2 files)

| Test File | Tests | Domain |
|-----------|-------|--------|
| `tests/__init__.py` | Package init | Infrastructure |
| `tests/conftest.py` | Shared test fixtures for platform test suite | Infrastructure |

### API & Auth Tests (5 files)

| Test File | Tests | Domain |
|-----------|-------|--------|
| `tests/test_api.py` | API integration tests | API |
| `tests/test_api_errors.py` | API error handling tests | API |
| `tests/test_auth.py` | Authentication endpoint tests | Auth |
| `tests/test_csv_export.py` | Unified scorecard CSV export tests | API |
| `tests/test_frontend_xss_regressions.py` | Static XSS regression guards | Security |

### Matching Tests (12 files)

| Test File | Tests | Domain |
|-----------|-------|--------|
| `tests/test_matching.py` | Matching pipeline tests | Matching |
| `tests/test_matching_pipeline.py` | Deterministic matching regression tests | Matching |
| `tests/test_phase3_matching.py` | Phase 3 matching overhaul regression | Matching |
| `tests/test_phase4_integration.py` | Phase 4 integration tests | Matching |
| `tests/test_name_normalization.py` | Name normalization tests | Matching |
| `tests/test_match_method_normalization.py` | Match method normalization tests | Matching |
| `tests/test_match_labels.py` | Match label utilities tests | Matching |
| `tests/test_employer_groups.py` | Employer canonical grouping regression | Matching |
| `tests/test_corroboration.py` | Match corroboration system tests | Matching |
| `tests/test_score_eligible.py` | score_eligible column and filtering tests | Matching |
| `tests/test_employer_linkage_retry.py` | Employer linkage retry tests | Matching |
| `tests/test_resolve_duplicates.py` | Duplicate resolution tests | Matching |

### Scoring Tests (9 files)

| Test File | Tests | Domain |
|-----------|-------|--------|
| `tests/test_scoring.py` | Scoring engine tests | Scoring |
| `tests/test_unified_scorecard.py` | mv_unified_scorecard MV and API tests | Scoring |
| `tests/test_target_scorecard.py` | mv_target_scorecard MV and API tests | Scoring |
| `tests/test_weighted_scorecard.py` | Weighted unified scorecard model tests | Scoring |
| `tests/test_employer_data_sources.py` | mv_employer_data_sources tests | Scoring |
| `tests/test_score_versioning.py` | Score version tracking tests | Scoring |
| `tests/test_naics_hierarchy_scoring.py` | Hierarchical NAICS similarity tests | Scoring |
| `tests/test_temporal_decay.py` | Temporal decay tests | Scoring |
| `tests/test_scorecard_contract_field_parity.py` | Contract-field parity tests | Scoring |

### Research Tests (8 files)

| Test File | Tests | Domain |
|-----------|-------|--------|
| `tests/test_auto_grader.py` | Auto-grader tests | Research |
| `tests/test_employer_lookup.py` | Employer lookup tests | Research |
| `tests/test_research_dedup.py` | Research dedup logic tests | Research |
| `tests/test_research_enhancements.py` | Research-to-scorecard feedback loop tests | Research |
| `tests/test_research_new_sources.py` | New research tool integrations tests | Research |
| `tests/test_research_scraper.py` | Research agent employer scraper tests | Research |
| `tests/test_contradiction_detection.py` | Contradiction resolution tests | Research |
| `tests/test_cross_validation.py` | Research cross-validation vs DB tests | Research |

### CBA Tests (7 files)

| Test File | Tests | Domain |
|-----------|-------|--------|
| `tests/test_cba.py` | CBA router endpoint tests | CBA |
| `tests/test_cba_article_finder.py` | CBA article/section finder tests | CBA |
| `tests/test_cba_party_extractor.py` | CBA party/metadata extractor tests | CBA |
| `tests/test_cba_rule_engine.py` | CBA rule engine tests | CBA |
| `tests/test_cba_section_splitter.py` | CBA section splitter tests | CBA |
| `tests/test_cba_toc_parser.py` | CBA TOC parser tests (27 tests) | CBA |
| `tests/test_parse_structured.py` | Scraper parse_structured tests (no DB) | CBA/Scraper |

### Data Integration Tests (12 files)

| Test File | Tests | Domain |
|-----------|-------|--------|
| `tests/test_data_integrity.py` | Data integrity validation tests | Data |
| `tests/test_campaign_outcomes.py` | Campaign outcomes tests | Data |
| `tests/test_nlrb_docket.py` | NLRB docket integration tests | Data |
| `tests/test_nlrb_sync.py` | NLRB SQLite sync tests | Data |
| `tests/test_onet_loader.py` | O*NET data loading tests | Data |
| `tests/test_newsrc_curated.py` | Curated transform table tests | Data |
| `tests/test_newsrc_loaders.py` | New source data loader tests | Data |
| `tests/test_occupation_integration.py` | Occupation similarity integration tests | Data |
| `tests/test_lodes_demographics.py` | LODES workplace demographics tests | Data |
| `tests/test_tract_demographics.py` | Census tract demographics tests | Data |
| `tests/test_rpe_estimates.py` | RPE workforce size estimation tests | Data |
| `tests/test_stale_unions.py` | Stale union flagging tests | Data |

### Router/Feature Tests (17 files)

| Test File | Tests | Domain |
|-----------|-------|--------|
| `tests/test_demographics_wiring.py` | ACS demographics API wiring tests | Router |
| `tests/test_density.py` | Density router endpoint tests | Router |
| `tests/test_lookups.py` | Lookups router endpoint tests | Router |
| `tests/test_projections.py` | Projections router endpoint tests | Router |
| `tests/test_public_sector.py` | Public sector router tests | Router |
| `tests/test_sectors.py` | Sectors router endpoint tests | Router |
| `tests/test_museums.py` | Museums router endpoint tests | Router |
| `tests/test_trends.py` | Trends router endpoint tests | Router |
| `tests/test_vr.py` | VR router endpoint tests | Router |
| `tests/test_corporate.py` | Corporate router endpoint tests | Router |
| `tests/test_master_employers.py` | Master employer tests | Router |
| `tests/test_search_dedup.py` | Search dedup in mv_employer_search tests | Router |
| `tests/test_workforce_profile.py` | Workforce profile tests | Router |
| `tests/test_fact_review.py` | Fact review API endpoint tests | Router |
| `tests/test_hitl_review.py` | HITL review UX tests | Router |
| `tests/test_nyc_enforcement.py` | NYC/NYS enforcement integration tests | Router |
| `tests/test_occupation_section.py` | Occupation section tests | Router |

### Union Tests (6 files)

| Test File | Tests | Domain |
|-----------|-------|--------|
| `tests/test_union_disbursements.py` | Union disbursements tests | Union |
| `tests/test_union_health.py` | Union health composite indicators tests | Union |
| `tests/test_union_hierarchy.py` | Union hierarchy endpoint tests | Union |
| `tests/test_union_membership_history.py` | Union membership history tests | Union |
| `tests/test_union_organizing_capacity.py` | Union organizing capacity tests | Union |
| `tests/test_missing_unions_resolution.py` | Missing unions resolution tests | Union |

### Other Tests (6 files)

| Test File | Tests | Domain |
|-----------|-------|--------|
| `tests/test_phase1_regression_guards.py` | Phase 1 regression guards | Regression |
| `tests/test_db_config_migration_guard.py` | db_config migration scope guard | Regression |
| `tests/test_similarity_fallback.py` | Similarity fallback + nearest-unionized tests | Feature |
| `tests/test_splink_disambiguate.py` | Splink disambiguation tests | Feature |
| `tests/test_tool_effectiveness.py` | Tool effectiveness API and pruning tests | Feature |
| `tests/test_system_data_freshness.py` | System data freshness tests | Feature |

---

## Database Schemas (40 SQL files)

### Schema Definitions (13 files)

| File | Description |
|------|-------------|
| `sql/f7_schema.sql` | Core F7 employer/union tables |
| `sql/schema/f7_schema.sql` | F7 schema (detailed version) |
| `sql/schema/f7_crosswalk_schema.sql` | Corporate crosswalk schema |
| `sql/schema/bls_phase1_schema.sql` | BLS data tables |
| `sql/schema/nlrb_schema_phase1.sql` | NLRB tables |
| `sql/schema/afscme_ny_schema.sql` | AFSCME NY directory tables |
| `sql/schema/schema_v4_employer_search.sql` | Employer search MV |
| `sql/schema/unionstats_schema.sql` | Union statistics tables |
| `sql/schema/vr_schema.sql` | Voluntary recognition tables |
| `sql/schema/cba_extraction_schema.sql` | CBA extraction tables |
| `sql/schema/cba_improvement_migration.sql` | CBA improvement migration |
| `sql/schema/cba_phase4_migration.sql` | CBA phase 4 migration |
| `sql/schema/cba_sections_migration.sql` | CBA sections + page_images tables |
| `sql/schema/cba_comparison_migration.sql` | CBA comparison tables migration |

### Query Files (23 files)

| File | Description |
|------|-------------|
| `sql/queries/BLS_INTEGRATION_QUERIES.sql` | BLS integration queries |
| `sql/queries/check_columns.sql` | Column verification queries |
| `sql/queries/check_db.sql` | Database health check queries |
| `sql/queries/check_lm_columns.sql` | LM column verification |
| `sql/queries/create_search_views.sql` | Search view creation |
| `sql/queries/dedupe_f7_employers.sql` | F7 employer deduplication |
| `sql/queries/diagnose_affiliations.sql` | Affiliation diagnosis |
| `sql/queries/diagnose_f7_matching.sql` | F7 matching diagnosis |
| `sql/queries/diagnose_local_numbers.sql` | Local number diagnosis |
| `sql/queries/fix_affiliations.sql` | Affiliation fixes |
| `sql/queries/fix_employer_view_v2.sql` | Employer view fix v2 |
| `sql/queries/fix_employer_view_v3.sql` | Employer view fix v3 |
| `sql/queries/fix_union_local_view.sql` | Union local view fix |
| `sql/queries/fix_union_local_view_v2.sql` | Union local view fix v2 |
| `sql/queries/fix_views.sql` | View fixes |
| `sql/queries/fix_views_v2.sql` | View fixes v2 |
| `sql/queries/insert_statements_2024.sql` | 2024 insert statements |
| `sql/queries/patch_v4_abc.sql` | V4 patch A/B/C |
| `sql/queries/patch_v4_fix.sql` | V4 patch fix |
| `sql/queries/test_views.sql` | View testing |
| `sql/queries/update_views_deduped.sql` | Deduped view updates |
| `sql/queries/vr_views_5a.sql` | VR views 5a |
| `sql/queries/vr_views_5b.sql` | VR views 5b |

### Other SQL Files (5 files)

| File | Description |
|------|-------------|
| `sql/create_research_agent_tables.sql` | Research agent tables |
| `sql/deduplication_views.sql` | Deduplication views |
| `sql/f7_indexes.sql` | F7 index definitions |
| `src/sql/nlrb_schema.sql` | NLRB schema (src location) |
| `scripts/load_teamsters_official.sql` | Teamsters official data load SQL |

---

## Configuration & Infrastructure

### CBA Configuration (17 files)

| File | Description |
|------|-------------|
| `config/cba_extraction_classes.json` | CBA extraction class definitions |
| `config/cba_few_shot_specs.json` | CBA few-shot extraction specs |
| `config/cba_system_prompt.md` | CBA LLM system prompt |
| `config/cba_rules/childcare.json` | CBA rule: childcare provisions |
| `config/cba_rules/grievance.json` | CBA rule: grievance procedures |
| `config/cba_rules/healthcare.json` | CBA rule: healthcare benefits |
| `config/cba_rules/job_security.json` | CBA rule: job security provisions |
| `config/cba_rules/leave.json` | CBA rule: leave policies |
| `config/cba_rules/management_rights.json` | CBA rule: management rights |
| `config/cba_rules/other.json` | CBA rule: miscellaneous provisions |
| `config/cba_rules/pension.json` | CBA rule: pension/retirement |
| `config/cba_rules/scheduling.json` | CBA rule: scheduling provisions |
| `config/cba_rules/seniority.json` | CBA rule: seniority provisions |
| `config/cba_rules/technology.json` | CBA rule: technology provisions |
| `config/cba_rules/training.json` | CBA rule: training provisions |
| `config/cba_rules/union_security.json` | CBA rule: union security clauses |
| `config/cba_rules/wages.json` | CBA rule: wage provisions |

### Root Configuration (12 files)

| File | Description |
|------|-------------|
| `.env` | Database credentials + JWT secret (never commit) |
| `.env.example` | Environment variable template |
| `.gitignore` | Git ignore rules |
| `.dockerignore` | Docker ignore rules |
| `pyproject.toml` | Python project metadata |
| `requirements.txt` | Python dependencies |
| `Dockerfile` | Docker container definition |
| `docker-compose.yml` | Docker Compose services |
| `nginx.conf` | Nginx reverse proxy configuration |
| `start-claude.bat` | Start Claude Code in project context |
| `start-cba-search.bat` | Start CBA search UI |
| `cba_search.html` | Standalone CBA search UI (served at /cba-search) |

---

## AI Agent Infrastructure (36 files)

### Domain Agents (9 files)

| File | Description |
|------|-------------|
| `.claude/agents/api.md` | API domain agent spec |
| `.claude/agents/cba.md` | CBA domain agent spec |
| `.claude/agents/database.md` | Database domain agent spec |
| `.claude/agents/etl.md` | ETL domain agent spec |
| `.claude/agents/frontend.md` | Frontend domain agent spec |
| `.claude/agents/maintenance.md` | Maintenance domain agent spec |
| `.claude/agents/matching.md` | Matching domain agent spec |
| `.claude/agents/research.md` | Research domain agent spec |
| `.claude/agents/scoring.md` | Scoring domain agent spec |

### On-Demand Specs (12 files)

| File | Description |
|------|-------------|
| `.claude/specs/api-endpoints.md` | API endpoint inventory |
| `.claude/specs/audit-findings.md` | Audit findings reference |
| `.claude/specs/corporate-crosswalk.md` | Corporate crosswalk spec |
| `.claude/specs/data-reconciliation.md` | Data reconciliation spec |
| `.claude/specs/database-schema.md` | Database schema reference |
| `.claude/specs/density-methodology.md` | Density methodology spec |
| `.claude/specs/matching-pipeline.md` | Matching pipeline spec |
| `.claude/specs/pipeline-manifest.md` | Pipeline manifest spec |
| `.claude/specs/redesign-spec.md` | Frontend redesign spec |
| `.claude/specs/roadmap.md` | Roadmap spec |
| `.claude/specs/scoring-system.md` | Scoring system spec |
| `.claude/specs/unified-scorecard-guide.md` | Unified scorecard guide |

### Skills (15 files)

| File | Description |
|------|-------------|
| `.claude/skills/debug/SKILL.md` | Debug skill |
| `.claude/skills/rebuild-mvs/SKILL.md` | MV rebuild skill |
| `.claude/skills/schema-check/SKILL.md` | Schema check skill |
| `.claude/skills/ship/SKILL.md` | Ship/deploy skill |
| `.claude/skills/start/SKILL.md` | Session start skill |
| `.claude/skills/union-research/SKILL.md` | Union research skill |
| `.claude/skills/wrapup/SKILL.md` | Session wrapup skill |
| `.claude/skills/union-research/references/employer-research.md` | Employer research reference |
| `.claude/skills/union-research/references/federal-sector.md` | Federal sector reference |
| `.claude/skills/union-research/references/industry-research.md` | Industry research reference |
| `.claude/skills/union-research/references/news-sources.md` | News sources reference |
| `.claude/skills/union-research/references/nlrb-research.md` | NLRB research reference |
| `.claude/skills/union-research/references/public-sector-sources.md` | Public sector sources reference |
| `.claude/skills/union-research/references/verification-queries.md` | Verification queries reference |
| `.claude/skills/union-research/references/worker-centers.md` | Worker centers reference |

---

## Data Directories (14 dirs)

| Directory | Contents | Source |
|-----------|----------|--------|
| `data/bls/` | BLS union membership and OEWS data | BLS |
| `data/bmf_bulk/` | IRS Business Master File bulk extracts | IRS |
| `data/cba_inbox/` | Incoming CBA PDF files for processing | User upload |
| `data/cba_processed/` | Processed CBA output files | Pipeline |
| `data/cbas/` | CBA contract archive | Various |
| `data/coverage/` | Coverage analysis output | Analysis |
| `data/crosswalk/` | Corporate crosswalk intermediate files | Pipeline |
| `data/f7/` | OLMS F7 employer data files | OLMS |
| `data/naics_crosswalks/` | NAICS industry classification crosswalks | Census |
| `data/nlrb/` | NLRB election and case data + exports/ | NLRB |
| `data/olms/` | OLMS LM-2 financial filings | OLMS |
| `data/raw/` | Raw downloads: CBP, Form 5500, IPUMS ACS, LODES | Multiple |
| `data/sec/` | SEC EDGAR data + companyfacts | SEC |
| `data/unionstats/` | UnionStats.com demographic/MSA/occupation/state data | UnionStats |

---

## Root-Level Scripts (24 .py files)

| Script | Description |
|--------|-------------|
| `db_config.py` | **Critical:** Shared database connection module (500+ imports) |
| `export_ny_deduped.py` | Export deduplicated NY employer-union list (collapsed) |
| `import_mergent.py` | Import Mergent company data into master_employers |
| `socrata_catalog.py` | Socrata open data catalog browser |
| `search_lib.py` | Search library utilities |
| `deactivate_fuzzy.py` | Count active fuzzy matches below 0.85 |
| `compare_ids.py` | Compare identifier sets |
| `check_bias_naics.py` | Check NAICS-related bias |
| `check_compound_signal.py` | Check compound signal combinations |
| `check_f7_sources.py` | Check F7 data sources |
| `check_factor_counts.py` | Check individual scoring factor counts |
| `check_fnum_types.py` | Check file number types |
| `check_mv_time.py` | Check materialized view refresh timing |
| `check_similarity_join.py` | Check similarity join performance |
| `list_all_tables.py` | List all database tables |
| `list_models.py` | List database models |
| `list_mvs.py` | List materialized views |
| `list_newsrc_tables.py` | List new source staging tables |
| `map_langextract.py` | Map LangExtract results |
| `inspect_langextract.py` | Inspect LangExtract output |
| `test_langextract_minimal.py` | Minimal LangExtract test |
| `test_pg_greatest.py` | Test PostgreSQL GREATEST function |
| `test_processor.py` | Test CBA processor |
| `test_similarity_agg.py` | Test similarity aggregation |

---

## Legacy Demographics Model (5 files)

Early prototype, superseded by `scripts/analysis/demographics_comparison/`.

| Script | Description |
|--------|-------------|
| `demographic estimate model/classifiers.py` | 5-dimensional company classification (V1) |
| `demographic estimate model/compute_optimal_weights.py` | Per-NAICS-group optimal ACS/LODES weights |
| `demographic estimate model/config.py` | Configuration for demographics comparison |
| `demographic estimate model/data_loaders.py` | Data loaders for demographics comparison |
| `demographic estimate model/methodologies.py` | Six estimation methodologies (V1) |

---

## Appendix A: Pipeline Run Order

Preserved from PIPELINE_MANIFEST.md:

```
1.   ETL: Load/refresh source data (OSHA, WHD, SAM, SEC, 990, BLS, GLEIF)
2.   Matching: py scripts/matching/run_deterministic.py all
3.   Matching: py scripts/matching/splink_pipeline.py (optional fuzzy)
3.5  Matching: py scripts/matching/backfill_name_columns.py
4.   Matching: py scripts/matching/build_employer_groups.py
4.5  Scoring: py scripts/scoring/build_employer_data_sources.py --refresh
4.6  Scoring: py scripts/scoring/build_unified_scorecard.py --refresh
4.7  Scoring: py scripts/scoring/rebuild_search_mv.py
5.   Scoring: py scripts/scoring/compute_nlrb_patterns.py
6.   Scoring: py scripts/scoring/create_scorecard_mv.py --refresh
7.   Scoring: py scripts/scoring/compute_gower_similarity.py --refresh-view
8.   Maintenance: py scripts/maintenance/create_data_freshness.py --refresh
```

## Appendix B: MV Dependency Chain

```
create_scorecard_mv.py               # OSHA-based organizing scorecard
  -> compute_gower_similarity.py     # Gower distance, employer_comparables
    -> build_employer_data_sources.py # 13-source flag MV
      -> build_unified_scorecard.py   # 10-factor union reference scorecard
        -> build_target_data_sources.py  # Non-union source flags
          -> build_target_scorecard.py   # Non-union 8-signal scorecard
            -> rebuild_search_mv.py      # Unified search index
```
