# Memory Index

## Project
- **Location:** `C:\Users\jakew\.local\bin\Labor Data Project_real`
- **DB:** PostgreSQL `olms_multiyear`, localhost, user `postgres`
- **Stack:** FastAPI (port 8001) + React 19/Vite 7/Tailwind 4 (frontend/)
- **Python:** 3.14 (`py` command), Windows with Git Bash
- **API start:** `py -m uvicorn api.main:app --reload --port 8001`
- **Frontend start:** `cd frontend && VITE_DISABLE_AUTH=true npx vite`

## Context System (Three-Tier)
- **Tier 1 (auto-loaded):** Root `CLAUDE.md` (~434 lines) -- full constitution
- **Tier 1.5:** This file -- slim index only (budget: <150 lines)
- **Tier 2:** `.claude/agents/` -- 9 domain specialists (~1,740 lines total)
- **Tier 3:** `.claude/specs/` -- 12 on-demand reference specs (~2,120 lines total)
- **Shared (multi-AI):** `Start each AI/` -- slimmed-down context for Codex/Gemini
- **Skills:** `.claude/skills/` -- 6 user-invoked (start, ship, debug, schema-check, rebuild-mvs, union-research)
- **Napkin:** `.claude/napkin.md` -- live correction log, rotate to canonical when confirmed

## Current Status (2026-03-12)
- **All phases through R3:** DONE
- **Roadmap audit (2026-03-06):** 15 more tasks found already done but unmarked. Roadmap updated.
  - Newly marked: 0-2, 0-3, 1-1, 1-2, 1-8, 1-10, 1-14, 1-15, 3-3, 3-8, 3-8b, 3-11, 4-3, 7-1, 7-4
- **Total:** ~66/83 tasks DONE, ~10 REMOVED, ~7 remaining open
- **Remaining open tasks:** 0-1 (credential rotation), 2-11 (launch strategy), 3-1 (Form 5500), 5-2/5-3/5-5/5-6/5-7 (new data sources), 7-2/7-3 (union file cleanup), 7-7 (union explorer cleanup), 8-1 through 8-8 (long-term)
- **Task 3-12 (census tract):** DONE -- 85,396 tracts loaded, 120,929 employers backfilled (98.8%)
- **Task 3-13 (blended demographics):** DONE -- V5 Gate v1 pipeline deployed. Beats M3b on all 5 acceptance criteria on fresh 208-company holdout.
- **Task 4-9 (research benchmark):** DONE -- 30 methods compared on 997 companies + Gate v1 validated on 208 fresh holdout
- **Tests:** 1260 backend (0 fail, 3 skip), 264 frontend
- **Campaign outcomes table:** Not yet created -- run `py scripts/etl/create_campaign_outcomes.py`

## Completed Phase Details
- Audit Batch 2 + Phase R2 + Pillar Weights + Batch 4 -> `memory/batch_details_2026_03.md`
- Phase 3 Batch 5 (ACS, O*NET, LODES, RPE) -> `memory/phase3_batch5_details.md`
- Phase 4 Matching Quality (score_eligible, corroboration, cross-validation) -> `memory/phase4_matching_details.md`
- RPE Validation + Mergent Import + Quality Score + Regression -> `memory/analysis_results.md`
- Batch (7-4, 7-1, 6-1, 6-2, 5-1): stale flags, hierarchy, CSV export, print, NLRB sync -> `memory/batch_2026_03_03.md`
- Phase R3 gap analysis (gold standard questions vs research tool) -> session notes in PROJECT_STATE.md
- BLS datasets (OES, SOII, JOLTS, NCS) + ACS insurance -> `memory/session_2026_03_04_bls_datasets.md`
- R3-1 ActionLog collapse -> `memory/r3_actionlog.md`
- Tasks 6-4, 6-5, 7-6 (signal count, verified badge, covered workers) -> `memory/session_2026_03_05_frontend_fixes.md`
- Quick-win batch (4-4, R3-5, R3-7, 3-7) -> `memory/session_2026_03_05_quick_wins.md`
- R3 tools batch (R3-2, R3-3, R3-4, R3-8) -> `memory/session_2026_03_05_r3_tools.md`
- Codex batch (R3-6, 6-3, 6-6, 4-8) -> verified merge, all tests pass
- Task 3-12 (census tract demographics) -> `memory/session_2026_03_06_tract_demographics.md`
- Union fixes (local numbers, 70M dedup, __pycache__) -> `memory/session_2026_03_06_union_fixes.md`
- News monitoring planning (Task 8-6) -> `memory/session_2026_03_06_news_monitoring.md`
- Union web scraper consolidated docs created -> `docs/UNION_WEB_SCRAPER.md`
- Scraper tiered extraction upgrade (all 9 phases) -> `memory/session_2026_03_06_scraper_upgrade.md`
- Union explorer fixes (hooks error, NHQ membership) -> `memory/session_2026_03_07_union_explorer_fixes.md`
- Full pipeline run + WP employer cleanup -> `memory/session_2026_03_07_pipeline_run.md`
- CBA Tool Phases 1-4 (batch, OCR, frontend, re-process) -> `memory/session_2026_03_07_cba_tool.md`
- Task 3-12 data load + Task 3-13 blended demographics prototype -> `memory/session_2026_03_07_blended_demographics.md`
- Demographics methodology comparison (6 methods, 10 EEO-1 companies, M1 wins) -> `memory/session_2026_03_08_demographics_comparison.md`
- V5 Demographics Pipeline execution (4 runs, Gate v1 deployed, all criteria pass) -> `memory/session_2026_03_09_v5_demographics.md`

## Active Decisions
- D5: Industry Growth weight 3x? (Open)
- D11: Scoring framework -- implemented batch 3 (stability zeroed, dynamic denominator). Weight rebalancing deferred.
- D12: Union Proximity weight (Open)

## Deferred (do NOT prompt)
- Phase 2 remaining re-runs (SAM/WHD/990/SEC with RapidFuzz)
- Phase 2.4 grouping quality, 2.5 master dedup

## Key References
- **Roadmap:** `COMPLETE_PROJECT_ROADMAP_2026_03.md` (supersedes Feb 26 roadmap)
- **Document index:** `DOCUMENT_INDEX.md` -- master catalog of all project documentation
- **Audit findings:** `.claude/specs/audit-findings.md`
- **Schema:** `.claude/specs/database-schema.md`
- **All docs indexed in:** Root `CLAUDE.md` Section 11 (Files That Matter)

## Critical Reminders
- `db_config.py` at project root -- 500+ imports, never move
- `f7_employer_id` is TEXT everywhere
- `master_employers` PK is `master_id` NOT `id`, name is `display_name` NOT `name`
- `zip_county_crosswalk` column is `zip_code` NOT `zip`
- Windows cp1252 -- use ASCII in print(), no Unicode arrows
- Do NOT pipe Python through grep on Windows
- Commit only when explicitly asked
- `information_schema.columns` does NOT include MVs -- use `pg_attribute`
- MV final SELECT uses `r.*` -- don't re-select columns already in raw_scores passthrough (causes duplicate column error)
- Mergent xlsx files have .csv extension -- openpyxl needs temp rename. Dirs 37+ have Sales/Employee/NAICS cols; dirs 1-36 have shorter column set
- `f7_employers_deduped` size column is `latest_unit_size` NOT `company_size`
- `osha_establishments` city/state/zip columns are `site_city`, `site_state`, `site_zip` (not plain `city`/`state`/`zip`)
- `sam_entities` location columns are `physical_city`, `physical_state`, `physical_zip`
- After corroboration, low-confidence matches may be score_eligible=TRUE -- tests must account for this
- SQL WHERE clause must come AFTER all JOINs (including LEFT JOINs)
- `mv_unified_scorecard` tier column is `score_tier` NOT `tier`
- `unions_master` has `is_likely_inactive` (BOOLEAN) and `parent_fnum` (VARCHAR) columns
- `unions_master.desig_name` has codes: NHQ/FED=national, DC/JC/CONF/D/C/SC/SA/BCTC=intermediate, LU/BR/etc=local
- Most NHQ unions have `desig_name = NULL` not `'NHQ'` -- use `MAX(members)` per affiliation to find authoritative NHQ membership
- NLRB sync script: `py scripts/etl/sync_nlrb_sqlite.py path.db --commit [--phase X]`
- OES `i_group` is VARCHAR(40) not 20 (value "cross-industry, ownership" = 26 chars)
- SOII industry codes: `623100` (nursing care) not `623110`; `623000` (nursing + residential)
- BLS tab-delimited files have `\r\n` line endings -- always `rstrip('\r\n')`
- JOLTS primary data file: `jt.data.1.AllItems.txt` (others are subsets)
- `osha_violation_summary` joins on `establishment_id` (NOT `activity_nr`)
- `naics_codes_reference` titles have trailing "T" artifact on levels 2-5 (strip before display)
- CorpWatch relationships: `source_cw_id` = parent, `target_cw_id` = child (not the reverse)
- `nyc_debarment_list` uses `prosecuting_agency` (not `agency`), no `reason` column
- `_safe_dict` converts dates to ISO strings -- compare with `str()` or `.isoformat()`, not `date` objects
- Stale `__pycache__` can silently serve old API code even with `--reload` -- clear cache dirs when API responses don't match source code
- `web_union_employers` has unique constraint `uq_web_employer_profile_name` on (web_profile_id, employer_name_clean) -- all INSERTs must use ON CONFLICT
- `web_union_pages` and `web_union_pdf_links` tables exist (scraper upgrade 2026-03-06)
- `fetch_union_sites.py` `fetch_page()` returns 4 values: (text, success, error, final_url)
- Scraper pipeline: `py scripts/scraper/run_extraction_pipeline.py` -- 6 stages with skip flags
- Gemini fallback: max_output_tokens=4096 (was 1024, caused truncated JSON)
- CBA batch process: `py scripts/cba/batch_process.py` -- inbox `data/cba_inbox/`, processed `data/cba_processed/`
- CBA reprocess: `py scripts/cba/process_contract.py --reprocess <cba_id>` (no --pdf/--employer/--union needed)
- CBA view rebuild: must DROP VIEW before CREATE when adding columns (CREATE OR REPLACE fails on column order change)
- CBA data: 4 contracts, 267 provisions, 14-category taxonomy, all rule-engine-extracted
- `web_union_employers.validated` BOOLEAN column -- TRUE=real employer, FALSE=noise, NULL=unreviewed
- WP employer cleanup: `py scripts/scraper/clean_wp_employers.py [--apply] [--delete]`
- Scraper pipeline results (2026-03-07): 2,208 raw employers, 1,522 validated, 87/103 profiles, 37K pages
- **IPUMS EDUC codes:** 00=N/A, 01-05=No HS, 06=HS/GED, 07-08=Some college, 10=Bachelor's, 11=Graduate+ (06 is NOT Masters!)
- **IPUMS HISPAN codes:** 0=Not Hispanic, 1=Mexican, 2=Puerto Rican, 3=Cuban, 4=Other Hispanic (Hispanic = codes 1-4, NOT code 2!)
- **BUG:** `api/routers/profile.py` `_blend_demographics()` uses `hispanic IN ('1','2')` -- compares Mexican vs PR, not Hispanic vs Not Hispanic. Fix pending.
- LODES OD files on disk: `New Data sources 2_27/LODES_bulk_2022/{state}_od_main_JT00_2022.csv.gz` -- all 50 states
- LODES OD industry: only 3 sectors (SI01=Goods, SI02=Trade, SI03=Services) -- cannot isolate specific NAICS
- Census API key: registered at api.census.gov
- EEO-1 CSV encoding is cp1252 (not UTF-8) -- `open(..., encoding='cp1252')`
- BDS-HC files have suppressed values ('D', 'S') -- must try/except int() parsing
- LODES `pct_minority` is 0-1 proportion, NOT 0-100 percentage
- **Demographics V5 winner:** Gate v1 (learned routing between Expert A/B/D + OOF calibration). Race MAE 5.18 on fresh holdout, beats M3b baseline (5.23) on all criteria. API endpoint uses V5 with 60/40 blend fallback.
- Demographics comparison scripts: `scripts/analysis/demographics_comparison/` (~25 files, 997+208 companies, 30 methods + Gate v1)
- Project Catalog (785 files cataloged, drift checker) -> `memory/session_2026_03_12_project_catalog.md`
- V5 Gate v1 model files: `gate_v1.pkl`, `calibration_v1.json` in demographics_comparison dir
- DB tables: `pums_metro_demographics` (6,538 rows), `bds_hc_estimated_benchmarks` (630 rows)
- BDS nudge is net negative (+0.045 MAE) -- recommend disabling in production
- sklearn 1.7+ removed `multi_class` param from LogisticRegression
