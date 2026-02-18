# Pipeline Manifest — Labor Relations Research Platform

**Last updated:** 2026-02-16
**Active scripts:** 120 (down from 530+ before reorganization)

## How to Use This Document

This lists every active script in the platform's data pipeline. Scripts are organized by stage. Within each stage, run order matters where noted. If a script isn't listed here, it's archived and not part of the active system.

All scripts are run from the project root: `C:\Users\jakew\Downloads\labor-data-project`

---

## Stage 1: ETL — Loading Raw Data

These scripts load external data into PostgreSQL. Run them when new source data is available.

| Script | What It Does | Source Data | Run When |
|--------|-------------|-------------|----------|
| `scripts/etl/load_osha_violations.py` | Loads OSHA violation records from SQLite | OSHA enforcement SQLite DB | New OSHA data available |
| `scripts/etl/load_osha_violations_detail.py` | Loads individual violation records with case numbers | OSHA enforcement SQLite DB | Same as above |
| `scripts/etl/load_whd_national.py` | Loads 363K wage theft cases into `whd_cases` | WHD WHISARD CSV | New WHD data available |
| `scripts/etl/load_sam.py` | Loads 826K federal contractor entities | SAM.gov monthly extract ZIP | Monthly refresh |
| `scripts/etl/load_sec_edgar.py` | Loads 517K SEC company records | SEC submissions.zip | Annual or when SEC updates |
| `scripts/etl/sec_edgar_full_index.py` | Alternative SEC loader from bulk submissions | SEC bulk data | Annual |
| `scripts/etl/load_national_990.py` | Loads 586K IRS 990 nonprofit filers (dedup by EIN) | national_990_extract.csv | When 990 data refreshed |
| `scripts/etl/irs_bmf_loader.py` | Loads ~1.8M tax-exempt orgs from IRS BMF | IRS BMF database | Phase 4 or refresh |
| `scripts/etl/load_gleif_bods.py` | Restores GLEIF pgdump (52.7M rows) + extracts US entities | GLEIF pgdump.sql.gz | Initial load |
| `scripts/etl/extract_gleif_us_optimized.py` | Optimized US entity extraction (use instead of above for extraction only) | gleif schema in DB | After GLEIF dump restored |
| `scripts/etl/update_normalization.py` | Applies cleanco normalization to GLEIF/SEC name columns | GLEIF + SEC tables | After loading GLEIF/SEC |
| `scripts/etl/fetch_qcew.py` | Downloads BLS QCEW annual data (2020-2023) | BLS QCEW CSV downloads | Annually |
| `scripts/etl/_integrate_qcew.py` | Integrates QCEW with F7 employers for density scoring | qcew_annual table | After QCEW loaded |
| `scripts/etl/download_bls_union_tables.py` | Downloads BLS union membership HTML tables | BLS news releases | Annually (January) |
| `scripts/etl/parse_bls_union_tables.py` | Parses BLS HTML tables into database | Downloaded HTML | After download_bls_union_tables.py |
| `scripts/etl/create_state_industry_estimates.py` | Creates 459 state x industry density estimates | BLS national + state density tables | After BLS tables loaded |
| `scripts/etl/load_bls_projections.py` | Loads BLS 2024-2034 industry/occupation projections | BLS projection Excel files | When new projections available |
| `scripts/etl/parse_oews_employment_matrix.py` | Parses BLS occupation-industry staffing patterns (67,699 rows) | BLS OEWS CSV files | Phase 4 |
| `scripts/etl/calculate_occupation_similarity.py` | Computes cosine similarity between occupations (8,731 pairs) | bls_industry_occupation_matrix | After OEWS loaded |
| `scripts/etl/compute_industry_occupation_overlap.py` | Pre-computes weighted Jaccard industry overlap (130K pairs) | bls_industry_occupation_matrix | Phase 5.4c |
| `scripts/etl/build_crosswalk.py` | Builds corporate identifier crosswalk (SEC/GLEIF/Mergent/F7) + hierarchy | SEC, GLEIF, Mergent, F7 tables | After all source data loaded |
| `scripts/etl/_fetch_usaspending_api.py` | Fetches federal contract recipients via paginated API | USASpending API | Phase 4 or refresh |
| `scripts/etl/_match_usaspending.py` | Matches USASpending recipients to F7 + updates crosswalk | federal_contract_recipients | After _fetch_usaspending_api.py |
| `scripts/etl/setup_afscme_scraper.py` | Creates web scraper tables + loads AFSCME directory + OLMS matching | AFSCME CSV directory | Phase 7 (web intelligence) |

---

## Stage 2: Matching — Connecting Data Sources

These scripts link records across databases. Run after ETL is complete. Order matters.

### Core Matching Pipeline

| Script | What It Does | Depends On | Run When |
|--------|-------------|------------|----------|
| `scripts/matching/run_deterministic.py` | **Main CLI** — runs 6-tier deterministic matching. Usage: `py scripts/matching/run_deterministic.py osha\|whd\|990\|sam\|sec\|all [--dry-run] [--limit N] [--skip-fuzzy]` | All ETL complete | After loading/refreshing any source |
| `scripts/matching/deterministic_matcher.py` | Core v3 batch-optimized matching engine. In-memory indexes for exact tiers, batched SQL for fuzzy | Imported by run_deterministic.py | Not run directly |
| `scripts/matching/splink_pipeline.py` | Splink probabilistic matching (DuckDB backend). Scenarios: mergent_to_f7, gleif_to_f7, f7_self_dedup | Splink library, DuckDB | After deterministic matching for high-confidence fuzzy |
| `scripts/matching/splink_integrate.py` | Integrates Splink results into corporate_identifier_crosswalk | splink_pipeline.py output | After splink_pipeline.py |
| `scripts/matching/create_unified_match_log.py` | Creates/resets unified_match_log table (audit trail for all matches) | Database | Once during setup (idempotent) |
| `scripts/matching/create_nlrb_bridge.py` | Creates v_nlrb_employer_history view (13K rows, 5.5K employers) | NLRB tables matched | After NLRB matching |
| `scripts/matching/resolve_historical_employers.py` | Identifies historical F7 employers matching current ones | Name normalization, F7 data | Phase 3 |
| `scripts/matching/build_employer_groups.py` | Canonical employer grouping (16,209 groups, 40,304 employers) | f7_employers_deduped | Phase 3 |
| `scripts/matching/match_quality_report.py` | Generates match quality metrics from unified_match_log | unified_match_log populated | After any matching run |

### Matching Framework (imported, not run directly)

| Script | What It Does |
|--------|-------------|
| `scripts/matching/config.py` | MatchConfig dataclass — scenario definitions, source/target tables, column mappings |
| `scripts/matching/normalizer.py` | Wrapper around name_normalization.py — standard/aggressive/fuzzy levels |
| `scripts/matching/pipeline.py` | Older 4-tier MatchPipeline orchestrator (used by CLI for single-match testing) |
| `scripts/matching/cli.py` | Alternative CLI for matching module (`python -m scripts.matching run/test`) |
| `scripts/matching/differ.py` | Diff report generation — compares matching runs |

### Source Adapters (scripts/matching/adapters/)

Each adapter loads unmatched records from one source and normalizes them for the deterministic matcher.

| Adapter | Source Table | Match Table |
|---------|-------------|-------------|
| `osha_adapter.py` | osha_establishments | osha_f7_matches |
| `whd_adapter.py` | whd_cases | whd_f7_matches |
| `n990_adapter.py` | national_990_filers | national_990_f7_matches |
| `sam_adapter.py` | sam_entities | sam_f7_matches |
| `sec_adapter_module.py` | sec_companies | unified_match_log |
| `bmf_adapter_module.py` | irs_bmf | unified_match_log |

### Matcher Classes (scripts/matching/matchers/)

| Matcher | Tier | Method |
|---------|------|--------|
| `base.py` | — | Abstract BaseMatcher + MatchResult dataclasses |
| `exact.py` | 1, 2, 4 | EIN exact, normalized name+state, aggressive name+state |
| `address.py` | 3 | Fuzzy name + street number + city + state |
| `fuzzy.py` | 5 | pg_trgm similarity >= 0.4, composite JW+token_set+ratio |

### Shared Library

| Script | What It Does |
|--------|-------------|
| `src/python/matching/name_normalization.py` | **Single source of truth** for name normalization. 3 levels + soundex + metaphone + phonetic similarity. 30+ abbreviation mappings. Imported by all matching code. |

---

## Stage 3: Scoring — Computing Scores

These scripts build the organizing scorecard and related analysis. Run after matching is stable.

| Script | What It Does | Depends On | Run When |
|--------|-------------|------------|----------|
| `scripts/scoring/compute_nlrb_patterns.py` | Analyzes 33K NLRB elections for win patterns by industry/size/state. Creates ref_nlrb_industry_win_rates, ref_nlrb_size_win_rates. | NLRB tables | Before scorecard build |
| `scripts/scoring/update_whd_scores.py` | Updates labor violation scores using WHD + NYC Comptroller data | WHD matching complete | Before scorecard build |
| `scripts/scoring/create_scorecard_mv.py` | **Creates/refreshes mv_organizing_scorecard** (22,389 rows, 9 factors, temporal decay). Use `--refresh` for concurrent update. Auto-inserts score_versions. | All matching + NLRB patterns | After matching stabilizes. `py scripts/scoring/create_scorecard_mv.py [--refresh]` |
| `scripts/scoring/build_employer_data_sources.py` | **Creates/refreshes mv_employer_data_sources** (146,863 rows). Aggregates source availability per F7 employer (8 boolean flags + corporate crosswalk). Foundation for E3 unified scorecard. Use `--refresh` for concurrent update. | All matching complete, employer groups built | After matching stabilizes. `py scripts/scoring/build_employer_data_sources.py [--refresh]` |
| `scripts/scoring/build_unified_scorecard.py` | **Creates/refreshes mv_unified_scorecard** (146,863 rows). Signal-strength scoring: 7 factors (OSHA, NLRB, WHD, contracts, union proximity, financial, size), each 0-10. Missing factors excluded. Unified score = avg of available factors. Use `--refresh` for concurrent update. | mv_employer_data_sources, all matching, BLS projections | After data sources MV built. `py scripts/scoring/build_unified_scorecard.py [--refresh]` |
| `scripts/scoring/compute_gower_similarity.py` | Gower distance similarity — finds top-5 comparable employers per employer (269K comparables). 14 features including occupation overlap. | mv_organizing_scorecard, industry_occupation_overlap | After scorecard built. `py scripts/scoring/compute_gower_similarity.py [--refresh-view]` |

### ML Pipeline (scripts/ml/)

| Script | What It Does | Depends On | Run When |
|--------|-------------|------------|----------|
| `scripts/ml/create_propensity_tables.py` | Creates ml_model_versions + ml_election_propensity_scores tables | Database | Once during Phase 5.5 setup |
| `scripts/ml/feature_engineering.py` | Feature engineering for propensity model (log transforms, cyclical month, one-hot, temporal split) | Imported by train script | Not run directly |
| `scripts/ml/train_propensity_model.py` | Trains propensity models (Model A AUC=0.72, Model B AUC=0.53). Scores 146K employers. | NLRB elections, OSHA matches, feature_engineering.py | Phase 5.5. `py scripts/ml/train_propensity_model.py [--dry-run] [--score-only]` |

---

## Stage 4: Maintenance — Periodic Tasks

| Script | What It Does | Schedule |
|--------|-------------|----------|
| `scripts/maintenance/create_data_freshness.py` | Tracks 15 data sources: record counts, date ranges, last-updated timestamps. UPSERT refresh. | Monthly. `py scripts/maintenance/create_data_freshness.py --refresh` |
| `scripts/maintenance/fix_signatories_and_groups.py` | Flags signatory entries as excluded, merges split canonical groups | As needed. `--dry-run` flag available |
| `scripts/scoring/create_scorecard_mv.py --refresh` | Concurrent refresh of organizing scorecard (zero downtime) | After any data update. Also via `POST /api/admin/refresh-scorecard` |
| `scripts/maintenance/create_data_freshness.py --refresh` | Refresh data source freshness tracking | After any ETL run. Also via `POST /api/admin/refresh-freshness` |

---

## Stage 5: Web Scraping Pipeline (scripts/scraper/)

Sequential pipeline for extracting data from union websites.

| Step | Script | What It Does | Run When |
|------|--------|-------------|----------|
| 1 | `scripts/etl/setup_afscme_scraper.py` | Creates tables, loads CSV directory, matches OLMS | Once for setup |
| 2 | `scripts/scraper/fetch_union_sites.py` | Fetches union web pages via Crawl4AI (rate-limited) | `--limit N` for test runs |
| 3 | `scripts/scraper/extract_union_data.py` | Heuristic extraction of employers, contracts, membership | After fetching |
| 4 | `scripts/scraper/fix_extraction.py` | Removes boilerplate false positives | After extraction |
| 5 | `scripts/scraper/match_web_employers.py` | 5-tier employer matching against F7 + OSHA | After extraction |
| 6 | `scripts/scraper/export_html.py` | Generates browsable HTML data viewer | Ad-hoc reporting |
| — | `scripts/scraper/fetch_summary.py` | Status report on scraping progress | Monitoring |
| — | `scripts/scraper/read_profiles.py` | Utility to inspect raw scraped text | Manual inspection |

---

## Utility Scripts

| Script | What It Does | Run When |
|--------|-------------|----------|
| `scripts/setup/init_database.py` | Database initialization and schema setup | Once during initial setup |
| `scripts/performance/profile_matching.py` | Performance profiling for matching pipeline queries | Ad-hoc bottleneck analysis |
| `db_config.py` (root) | Shared database connection module. `from db_config import get_connection, DB_CONFIG` | Imported by all scripts |

---

## Typical Full Pipeline Run Order

```
1.  ETL: Load/refresh source data (OSHA, WHD, SAM, SEC, 990, BLS, GLEIF)
2.  Matching: py scripts/matching/run_deterministic.py all
3.  Matching: py scripts/matching/splink_pipeline.py (optional fuzzy)
4.  Matching: py scripts/matching/build_employer_groups.py
4.5 Scoring: py scripts/scoring/build_employer_data_sources.py --refresh
4.6 Scoring: py scripts/scoring/build_unified_scorecard.py --refresh
5.  Scoring: py scripts/scoring/compute_nlrb_patterns.py
6.  Scoring: py scripts/scoring/create_scorecard_mv.py --refresh
7.  Scoring: py scripts/scoring/compute_gower_similarity.py --refresh-view
8.  ML: py scripts/ml/train_propensity_model.py --score-only
9.  Maintenance: py scripts/maintenance/create_data_freshness.py --refresh
```

---

## Directory Structure

```
scripts/
├── etl/           (24 scripts) — Stage 1: Data loading
├── matching/      (29 scripts) — Stage 2: Record linkage
│   ├── adapters/  (7 files)   — Source-specific data loaders
│   └── matchers/  (5 files)   — Matching algorithm implementations
├── scoring/        (4 scripts) — Stage 3: Score computation
├── ml/             (4 scripts) — Stage 3: Machine learning models
├── maintenance/    (2 scripts) — Stage 4: Periodic refresh
├── scraper/        (7 scripts) — Stage 5: Web intelligence
├── analysis/      (51 scripts) — Ad-hoc analysis templates (not pipeline)
├── setup/          (1 script)  — Database initialization
└── performance/    (1 script)  — Performance profiling
```

**Total active pipeline scripts:** 69 (excluding analysis templates)
**Total including analysis:** 120
