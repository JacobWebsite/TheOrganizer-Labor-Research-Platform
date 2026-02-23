# Test Coverage Gaps

## Scope
- scripts/matching/*.py
- scripts/scoring/*.py
- scripts/etl/*.py
- api/**/*.py

Total files analyzed: **107**
Files with convention-matched tests: **2**
Files without convention-matched tests: **105**

## Coverage Matrix
| File path | Has tests? | Test count | Priority |
|---|---|---:|---|
| scripts/matching/__init__.py | No | 0 | High |
| scripts/matching/__main__.py | No | 0 | High |
| scripts/matching/adapters/__init__.py | No | 0 | High |
| scripts/matching/adapters/bmf_adapter_module.py | No | 0 | High |
| scripts/matching/adapters/n990_adapter.py | No | 0 | High |
| scripts/matching/adapters/osha_adapter.py | No | 0 | High |
| scripts/matching/adapters/sam_adapter.py | No | 0 | High |
| scripts/matching/adapters/sec_adapter_module.py | No | 0 | High |
| scripts/matching/adapters/whd_adapter.py | No | 0 | High |
| scripts/matching/backfill_name_columns.py | No | 0 | High |
| scripts/matching/build_employer_groups.py | No | 0 | High |
| scripts/matching/cli.py | No | 0 | High |
| scripts/matching/config.py | No | 0 | High |
| scripts/matching/create_nlrb_bridge.py | No | 0 | High |
| scripts/matching/create_unified_match_log.py | No | 0 | High |
| scripts/matching/deterministic_matcher.py | No | 0 | High |
| scripts/matching/differ.py | No | 0 | High |
| scripts/matching/match_nlrb_ulp.py | No | 0 | High |
| scripts/matching/match_quality_report.py | No | 0 | High |
| scripts/matching/matchers/__init__.py | No | 0 | High |
| scripts/matching/matchers/address.py | No | 0 | High |
| scripts/matching/matchers/base.py | No | 0 | High |
| scripts/matching/matchers/exact.py | No | 0 | High |
| scripts/matching/matchers/fuzzy.py | No | 0 | High |
| scripts/matching/normalizer.py | No | 0 | High |
| scripts/matching/pipeline.py | No | 0 | High |
| scripts/matching/resolve_historical_employers.py | No | 0 | High |
| scripts/matching/run_deterministic.py | No | 0 | High |
| scripts/matching/splink_config.py | No | 0 | High |
| scripts/matching/splink_integrate.py | No | 0 | High |
| scripts/matching/splink_pipeline.py | No | 0 | High |
| scripts/matching/train_adaptive_fuzzy_model.py | No | 0 | High |
| scripts/scoring/build_employer_data_sources.py | No | 0 | High |
| scripts/scoring/build_unified_scorecard.py | No | 0 | High |
| scripts/scoring/compute_gower_similarity.py | No | 0 | High |
| scripts/scoring/compute_nlrb_patterns.py | No | 0 | High |
| scripts/scoring/create_scorecard_mv.py | No | 0 | High |
| scripts/scoring/rebuild_search_mv.py | No | 0 | High |
| scripts/scoring/update_whd_scores.py | No | 0 | High |
| scripts/etl/_fetch_usaspending_api.py | No | 0 | Medium |
| scripts/etl/_integrate_qcew.py | No | 0 | Medium |
| scripts/etl/_match_usaspending.py | No | 0 | Medium |
| scripts/etl/build_crosswalk.py | No | 0 | Medium |
| scripts/etl/bulk_load_cbas.py | No | 0 | Medium |
| scripts/etl/calculate_occupation_similarity.py | No | 0 | Medium |
| scripts/etl/compute_industry_occupation_overlap.py | No | 0 | Medium |
| scripts/etl/create_state_industry_estimates.py | No | 0 | Medium |
| scripts/etl/dedup_master_employers.py | No | 0 | Medium |
| scripts/etl/download_bls_union_tables.py | No | 0 | Medium |
| scripts/etl/extract_gleif_us_optimized.py | No | 0 | Medium |
| scripts/etl/fetch_qcew.py | No | 0 | Medium |
| scripts/etl/infer_naics.py | No | 0 | Medium |
| scripts/etl/infer_naics_keywords.py | No | 0 | Medium |
| scripts/etl/irs_bmf_loader.py | No | 0 | Medium |
| scripts/etl/load_bls_projections.py | No | 0 | Medium |
| scripts/etl/load_bmf_bulk.py | No | 0 | Medium |
| scripts/etl/load_gleif_bods.py | No | 0 | Medium |
| scripts/etl/load_national_990.py | No | 0 | Medium |
| scripts/etl/load_onet_data.py | No | 0 | Medium |
| scripts/etl/load_osha_violations.py | No | 0 | Medium |
| scripts/etl/load_osha_violations_detail.py | No | 0 | Medium |
| scripts/etl/load_sam.py | No | 0 | Medium |
| scripts/etl/load_sec_edgar.py | No | 0 | Medium |
| scripts/etl/load_whd_national.py | No | 0 | Medium |
| scripts/etl/parse_bls_union_tables.py | No | 0 | Medium |
| scripts/etl/parse_oews_employment_matrix.py | No | 0 | Medium |
| scripts/etl/sec_edgar_full_index.py | No | 0 | Medium |
| scripts/etl/seed_master_chunked.py | No | 0 | Medium |
| scripts/etl/seed_master_from_sources.py | No | 0 | Medium |
| scripts/etl/setup_afscme_scraper.py | No | 0 | Medium |
| scripts/etl/update_normalization.py | No | 0 | Medium |
| api/__init__.py | No | 0 | Medium |
| api/config.py | No | 0 | Medium |
| api/database.py | No | 0 | Medium |
| api/dependencies.py | No | 0 | Medium |
| api/helpers.py | No | 0 | Medium |
| api/main.py | No | 0 | Medium |
| api/middleware/__init__.py | No | 0 | Medium |
| api/middleware/auth.py | Yes | 22 | Low |
| api/middleware/logging.py | No | 0 | Medium |
| api/middleware/rate_limit.py | No | 0 | Medium |
| api/models/__init__.py | No | 0 | Medium |
| api/models/schemas.py | No | 0 | Medium |
| api/routers/__init__.py | No | 0 | High |
| api/routers/auth.py | Yes | 22 | Low |
| api/routers/cba.py | No | 0 | High |
| api/routers/corporate.py | No | 0 | High |
| api/routers/density.py | No | 0 | High |
| api/routers/employers.py | No | 0 | High |
| api/routers/health.py | No | 0 | High |
| api/routers/lookups.py | No | 0 | High |
| api/routers/master.py | No | 0 | High |
| api/routers/museums.py | No | 0 | High |
| api/routers/nlrb.py | No | 0 | High |
| api/routers/organizing.py | No | 0 | High |
| api/routers/osha.py | No | 0 | High |
| api/routers/profile.py | No | 0 | High |
| api/routers/projections.py | No | 0 | High |
| api/routers/public_sector.py | No | 0 | High |
| api/routers/research.py | No | 0 | High |
| api/routers/scorecard.py | No | 0 | High |
| api/routers/sectors.py | No | 0 | High |
| api/routers/system.py | No | 0 | High |
| api/routers/trends.py | No | 0 | High |
| api/routers/unions.py | No | 0 | High |
| api/routers/vr.py | No | 0 | High |
| api/routers/whd.py | No | 0 | High |

## Top 10 Files Needing Tests
1. `api/routers/__init__.py` (High) - Core matching/scoring logic without direct regression tests
1. `api/routers/cba.py` (High) - Core matching/scoring logic without direct regression tests
1. `api/routers/corporate.py` (High) - Core matching/scoring logic without direct regression tests
1. `api/routers/density.py` (High) - Core matching/scoring logic without direct regression tests
1. `api/routers/employers.py` (High) - Core matching/scoring logic without direct regression tests
1. `api/routers/health.py` (High) - Core matching/scoring logic without direct regression tests
1. `api/routers/lookups.py` (High) - Core matching/scoring logic without direct regression tests
1. `api/routers/master.py` (High) - Core matching/scoring logic without direct regression tests
1. `api/routers/museums.py` (High) - Core matching/scoring logic without direct regression tests
1. `api/routers/nlrb.py` (High) - Core matching/scoring logic without direct regression tests
