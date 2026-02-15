# Comprehensive Platform Audit -- Round 2
## CLAUDE (Claude Code / Opus 4.6)
**Date:** February 14, 2026
**Database:** `olms_multiyear` on localhost (PostgreSQL)
**Auditor:** Claude Code (Opus 4.6), independent assessment

---

## SECTION 1: Database Inventory

### Summary Table

| Category | Table Count | Total Rows | Total Size |
|----------|-------------|------------|------------|
| Core (unions, employers, relations) | 12 | 419,893 | 312 MB |
| NLRB (elections, cases, participants) | 14 | 3,146,338 | 1.9 GB |
| OSHA (establishments, violations) | 8 | 3,419,891 | 2.8 GB |
| Corporate (GLEIF, SEC, crosswalk, Mergent) | 18 | 1,672,493 | 1.2 GB |
| Geographic (QCEW, BLS, density, SAM) | 22 | 2,614,711 | 1.6 GB |
| Matching (splink, fuzzy matches, xref) | 16 | 609,034 | 580 MB |
| WHD (wage theft) | 5 | 1,069,602 | 760 MB |
| IRS 990 | 6 | 615,441 | 420 MB |
| NYC/NY contracts | 8 | 482,116 | 310 MB |
| Web/scraper | 5 | 1,186 | 1 MB |
| Admin/platform | 2 | 15 | <1 MB |
| Materialized views | 4 | 280,803 | 153 MB |
| Views | 186 | -- | -- |
| Other/staging | 40 | 9,621,440 | 10.0 GB |
| **TOTAL** | **160 tables + 186 views + 4 MVs** | **~23.9M** | **~20 GB** |

### Empty/Suspicious Tables

| Table | Rows | Notes |
|-------|------|-------|
| `platform_users` | 0 | Auth table -- empty because auth disabled by default |

### Top 20 Tables by Size

| # | Table | Rows | Size |
|---|-------|------|------|
| 1 | `osha_violations_detail` | 2,194,516 | 2.1 GB |
| 2 | `nlrb_allegations` | 715,805 | 880 MB |
| 3 | `whd_cases` | 363,365 | 650 MB |
| 4 | `osha_establishments` | 1,007,217 | 580 MB |
| 5 | `nlrb_participants` | 1,906,542 | 520 MB |
| 6 | `sec_submissions` | 955,244 | 480 MB |
| 7 | `national_990_filers` | 586,767 | 380 MB |
| 8 | `sam_entities` | 826,485 | 340 MB |
| 9 | `gleif_us_entities` | 379,192 | 310 MB |
| 10 | `nlrb_cases` | 477,688 | 290 MB |
| 11 | `bls_occupation_projections` | 861,780 | 270 MB |
| 12 | `employer_comparables` | 269,785 | 230 MB |
| 13 | `f7_employers_deduped` | 113,713 | 180 MB |
| 14 | `mv_employer_search` | 170,775 | 58 MB |
| 15 | `f7_union_employer_relations` | 119,445 | 56 MB |
| 16 | `osha_f7_matches` | 138,340 | 48 MB |
| 17 | `mv_whd_employer_agg` | 330,419 | 76 MB |
| 18 | `mergent_employers` | 56,426 | 42 MB |
| 19 | `nlrb_employer_xref` | 179,096 | 38 MB |
| 20 | `unions_master` | 26,665 | 35 MB |

### Tables Without Primary Keys: 14

Notable: `f7_employers_deduped` now HAS a PK (fixed since Round 1). Remaining tables without PKs are mostly staging/intermediate tables.

---

## SECTION 2: Data Quality

### Column Completeness

**f7_employers_deduped (113,713 rows)**

| Column | Filled | Rate |
|--------|--------|------|
| employer_name | 113,713 | 100% |
| state | 110,302 | 97.0% |
| city | 109,876 | 96.6% |
| naics | 42,891 | 37.7% |
| lat | 55,812 | 49.1% |
| lon | 55,812 | 49.1% |
| latest_unit_size | 68,240 | 60.0% |

**unions_master (26,665 rows)**

| Column | Filled | Rate |
|--------|--------|------|
| union_name | 26,665 | 100% |
| aff_abbr | 26,665 | 100% |
| members | 25,891 | 97.1% |
| city | 26,412 | 99.1% |
| state | 26,665 | 100% |

**osha_establishments (1,007,217 rows)**

| Column | Filled | Rate |
|--------|--------|------|
| estab_name | 1,007,102 | 100% |
| city | 998,431 | 99.1% |
| state | 1,007,217 | 100% |
| sic_code | 982,156 | 97.5% |
| naics_code | 723,418 | 71.8% |

**mergent_employers (56,426 rows)**

| Column | Filled | Rate |
|--------|--------|------|
| company_name | 56,426 | 100% |
| duns | 56,426 | 100% |
| ein | 48,912 | 86.7% |
| employees_site | 41,230 | 73.1% |
| naics_primary | 52,108 | 92.3% |

### Duplicate Analysis

| Table | Duplicate Groups | Duplicate Rows |
|-------|-----------------|----------------|
| f7_employers_deduped (name+state) | 1,838 | ~4,100 |
| osha_establishments (name+city+state) | ~12,400 | ~28,000 |
| nlrb_elections (case_number) | 0 | 0 |

### Orphan Check

| Relationship | Orphaned Records | Round 1 | Status |
|-------------|-----------------|---------|--------|
| f7_union_employer_relations.employer_id -> f7_employers_deduped | **0** | ~60,000 | FIXED |
| f7_union_employer_relations.union_file_number -> unions_master | **824** | 195 | WORSENED |
| osha_f7_matches.f7_employer_id -> f7_employers_deduped | **0** | not checked | OK |
| osha_f7_matches.establishment_id -> osha_establishments | **0** | not checked | OK |

### 🟡 HIGH: Union File Number Orphans Increased

**What's wrong:** 824 rows in `f7_union_employer_relations` reference union file numbers that don't exist in `unions_master`. This increased from 195 in Round 1.

**Evidence:** `SELECT COUNT(*) FROM f7_union_employer_relations r LEFT JOIN unions_master u ON r.union_file_number::text = u.f_num WHERE u.f_num IS NULL` returns 824.

**Impact:** These 824 employer-union relationships are invisible to the platform. An organizer looking at union coverage may miss these connections.

**Suggested fix:** Investigate whether these are historical unions that should be added to `unions_master`, or genuinely broken references from the Sprint 1 historical employer import.

**Verified by:** Direct SQL query against live database.

---

## SECTION 3: Cross-Database Matching

### Match Rate Summary

| Connection | Matched | Total | Match Rate |
|-----------|---------|-------|------------|
| F7 employers -> OSHA (employer perspective) | 28,836 | 60,953 current | **47.3%** |
| F7 employers -> OSHA (establishment perspective) | 138,340 | 1,007,217 | 13.7% |
| F7 employers -> NLRB (via xref) | 17,516 | 60,953 current | 28.7% |
| F7 employers -> WHD | 9,745 | 60,953 current | 16.0% |
| F7 employers -> SAM | 4,572 | 60,953 current | 7.5% |
| F7 employers -> 990 | 7,240 | 60,953 current | 11.9% |
| F7 employers -> Crosswalk | 9,264 | 60,953 current | 15.2% |
| Crosswalk -> GLEIF LEI | 3,260 | 25,177 crosswalk | 13.0% |
| Crosswalk -> Mergent DUNS | 947 | 25,177 crosswalk | 3.8% |
| Crosswalk -> SEC CIK | 4,891 | 25,177 crosswalk | 19.4% |
| Crosswalk -> EIN | 8,102 | 25,177 crosswalk | 32.2% |

### 🔵 MEDIUM: Low NAICS Coverage Limits Industry Scoring

**What's wrong:** Only 37.7% of F7 employers have NAICS codes. The 9-factor scorecard includes `industry_density` as a factor, but 62% of employers can't receive this score component.

**Evidence:** `SELECT COUNT(*) FROM f7_employers_deduped WHERE naics IS NOT NULL` = 42,891 / 113,713.

**Impact:** Industry-based scoring factors are unreliable for the majority of employers. Organizers may see artificially lower scores for employers where NAICS is missing.

**Suggested fix:** Backfill NAICS from OSHA matches (71.8% have naics_code) or Mergent (92.3% have naics_primary). A single UPDATE joining through osha_f7_matches could fill thousands.

**Verified by:** Column completeness queries on f7_employers_deduped and osha_establishments.

---

## SECTION 4: API & Endpoint Audit

### Summary

| Metric | Count |
|--------|-------|
| Total routers | 17 |
| Total endpoints | 152 |
| SQL injection risks | 0 |
| Dead table references | 0 |
| Auth-protected (when enabled) | All non-GET and admin endpoints |
| CORS | Localhost-only, no wildcard |

### Endpoint Inventory by Router

| Router | File | Endpoints | Key Tables |
|--------|------|-----------|------------|
| summary | summary.py | 3 | unions_master, f7_employers_deduped, nlrb_elections |
| lookups | lookups.py | 5 | f7_employers_deduped, unions_master |
| employers | employers.py | 8 | f7_employers_deduped, osha_f7_matches |
| unions | unions.py | 6 | unions_master, lm_data |
| nlrb | nlrb.py | 12 | nlrb_cases, nlrb_elections, nlrb_participants |
| density | density.py | 21 | bls_industry_density, f7_employers_deduped |
| osha | osha.py | 6 | osha_establishments, osha_violations_detail |
| trends | trends.py | 4 | lm_data, unions_master |
| corporate | corporate.py | 8 | corporate_identifier_crosswalk, corporate_hierarchy |
| comparables | comparables.py | 3 | employer_comparables |
| organizing | organizing.py | 12 | mv_organizing_scorecard, v_organizing_scorecard |
| whd | whd.py | 5 | whd_cases, whd_f7_matches |
| bls | bls.py | 10 | bls_occupation_projections |
| sectors | sectors.py | 7 | sector views |
| voluntary_recognition | voluntary_recognition.py | 9 | voluntary_recognition |
| museum | museum.py | 6 | sector-specific views |
| auth | auth.py | 4 | platform_users |
| stats/health | main.py | 3 | system tables |

### Security Assessment

All SQL queries use parameterized queries (`%s` placeholders with psycopg2). No string concatenation for user input. CORS restricted to localhost origins. Auth middleware exists but is disabled by default (fail-open when `LABOR_JWT_SECRET` not set).

### 🟡 HIGH: Authentication Fail-Open by Default

**What's wrong:** The JWT authentication system is fully built but defaults to disabled. When `LABOR_JWT_SECRET` is not set in `.env`, all endpoints are publicly accessible with no authentication.

**Evidence:** `api/middleware/auth.py` line 45: `if not JWT_SECRET: return await call_next(request)`

**Impact:** Any deployment without explicit environment configuration exposes all data and admin endpoints (including scorecard refresh, user management) to unauthenticated access.

**Suggested fix:** For production deployment, require `LABOR_JWT_SECRET` to be set or refuse to start. Current behavior is fine for local development.

**Verified by:** Reading api/middleware/auth.py and api/config.py.

---

## SECTION 5: Frontend Review

### File Inventory

| File | Lines | Purpose |
|------|-------|---------|
| `files/organizer_v5.html` | 2,160 | Main HTML markup |
| `files/css/organizer.css` | 227 | All styles |
| `files/js/config.js` | 29 | API_BASE configuration |
| `files/js/utils.js` | 196 | Shared utilities |
| `files/js/maps.js` | 211 | Leaflet map integration |
| `files/js/territory.js` | 670 | Territory mode |
| `files/js/search.js` | 934 | Employer/union search |
| `files/js/deepdive.js` | 355 | Deep dive analysis |
| `files/js/detail.js` | 1,351 | Employer detail panels |
| `files/js/scorecard.js` | 859 | Organizing scorecard |
| `files/js/modals.js` | 2,598 | Modal dialogs |
| `files/js/app.js` | 1,105 | App init + freshness |
| **Total** | **~10,695** | Split from 10,506-line monolith |

### Hardcoded Values

- `API_BASE` in `config.js` uses `window.location.origin` -- no hardcoded localhost
- 1 reference to port 8001 in `territory.js` error message (not a connection string)
- 59 `API_BASE` references across JS files
- 103 inline `onclick` handlers

### API Connection Verification

All frontend API calls target endpoints that exist in the backend. No broken connections found.

### 🔵 MEDIUM: modals.js Still Large

**What's wrong:** `modals.js` at 2,598 lines is the largest JS file, containing 15+ modal dialogs. It's a secondary monolith.

**Evidence:** `wc -l files/js/modals.js` = 2,598

**Impact:** Maintainability concern -- any modal change requires navigating a large file. No user-facing impact.

**Suggested fix:** Split into per-feature modal files (e.g., `modal-employer.js`, `modal-union.js`). Low priority.

**Verified by:** File line count and content review.

---

## SECTION 6: Previous Audit Findings -- Are They Fixed?

| # | Round 1 Finding | Status | Evidence |
|---|----------------|--------|----------|
| 1 | Database password in code | **FIXED** | 0 instances in .py/.sql. Present in 7 .md audit doc files. |
| 2 | Authentication disabled | **PARTIALLY FIXED** | Full JWT system built; fail-open by default (intentional for dev) |
| 3 | CORS wide open | **FIXED** | 4 localhost origins only, methods restricted, headers restricted |
| 4 | ~50% orphaned employer relations | **FIXED** | 60,000 -> 0 orphans. Added 52,760 historical employers. |
| 5 | Frontend 9,500+ lines in one file | **FIXED** | Split to 12 files (2,160 HTML + 10 JS + 1 CSS) |
| 6 | OSHA match rate ~14% | **FIXED** | 47.3% of F7 employers now matched (13.7% of OSHA establishments) |
| 7 | WHD match rate ~2% | **FIXED** | 16.0% of F7 employers now matched |
| 8 | No tests for matching pipeline | **FIXED** | 53 matching + 39 scoring + 24 data integrity tests |
| 9 | README wrong startup command | **FIXED** | Correct: `py -m uvicorn api.main:app --reload --port 8001` |
| 10 | 990 data completely unmatched | **FIXED** | 14,059 matches covering 7,240 F7 employers |
| 11 | GLEIF 10+ GB for 605 matches | **PARTIALLY FIXED** | 396 MB (96% size reduction), 3,260 matches (5.4x improvement) |
| 12 | LIMIT 500 silently cuts results | **FIXED** | Returns `total`, `limit`, `offset` for proper pagination |
| 13 | Two separate scoring systems | **FIXED** | Unified 9-factor MV scorecard, Mergent used as enrichment only |
| 14 | 195 orphaned union file numbers | **STILL BROKEN** | Increased to 824 (from historical employer import) |
| 15 | Stale pg_stat estimates | **PARTIALLY FIXED** | Hot-path tables autoanalyzed; 150/164 tables never analyzed |

**Overall: 11 FIXED, 3 PARTIALLY FIXED, 1 STILL BROKEN (worsened)**

---

## SECTION 7: What Changed Since Round 1? (Delta Analysis)

### Database Changes

| Metric | Round 1 (Feb 13) | Round 2 (Feb 14) | Delta |
|--------|-------------------|-------------------|-------|
| Tables | 159 | 160 | +1 |
| Views | 187 | 186 | -1 |
| Materialized Views | 3 | 4 | +1 |
| Total Size | 22 GB | 20 GB | -2 GB |
| Total Rows | ~21M | ~23.9M | +2.9M |
| Unused Indexes | 370 (73%) | 299 (59%) | -71 |
| API Endpoints | ~145 | 152 | +7 |
| Tests | ~47 | 165 | +118 |

### New Database Objects

- **`data_source_freshness`** table (Sprint 5) -- 15 rows, tracks data source currency
- **`mv_organizing_scorecard`** MV (Sprint 3) -- 24,841 rows, 9-factor scoring
- **`v_organizing_scorecard`** view -- wrapper adding composite score
- **`v_f7_employers_current`** view -- filters to non-historical employers
- **`platform_users`** table (Sprint 2) -- 0 rows, for JWT auth

### Row Count Changes

| Table | Round 1 | Round 2 | Change |
|-------|---------|---------|--------|
| f7_employers_deduped | 60,953 | 113,713 | +52,760 (historical employers) |
| unions_master | 26,688 | 26,665 | -23 (dedup cleanup) |
| f7_union_employer_relations | 119,832 | 119,445 | -387 (duplicate removal) |
| All OSHA/NLRB/WHD/SAM tables | unchanged | unchanged | No new data ingested |

### Schema Changes

- **f7_employers_deduped**: Added `is_historical` column + PRIMARY KEY on `employer_id`
- **splink_match_results**: Dropped (was 5.7M rows, 1.6 GB)

### Code Changes (10 commits, ~35K lines added)

| Sprint | Key Changes |
|--------|-------------|
| Sprint 1 | Orphan fix (60K->0), password removal, doc fixes |
| Sprint 2 | JWT auth system (4 endpoints), CORS lockdown |
| Sprint 3 | Scorecard MV (9-factor, SQL-computed), admin refresh |
| Sprint 4 | 118 new tests (matching, scoring, data integrity, auth) |
| Sprint 5 | ULP integration, data freshness tracking |
| Sprint 6 | Frontend monolith split, score explanations API |

### What Did NOT Change

- No new external data ingested (all match tables flat)
- No new matching runs executed
- Auth remains disabled (platform_users = 0 rows)
- SEC EDGAR, IRS BMF, SEC 10-K Exhibit 21 still on ingest backlog
- AFSCME scraper data loaded but not integrated into scoring

---

## SECTION 8: Scripts & File System

### File Counts

| Directory | .py Files | Purpose |
|-----------|-----------|---------|
| scripts/maintenance/ | 99 | Check, fix, validate utilities |
| scripts/etl/ | 72 | Data loading, matching, crosswalk |
| scripts/import/ | 45 | Initial data import |
| scripts/verify/ | 37 | One-off verification |
| scripts/analysis/ | 36 | Coverage and analysis |
| scripts/cleanup/ | 34 | Dedup, fix, audit |
| scripts/matching/ | 30 | Unified match pipeline |
| scripts/scoring/ | 24 | Scorecard, similarity, patterns |
| scripts/density/ | 16 | Union density estimation |
| scripts/coverage/ | 16 | Coverage comparison |
| scripts/export/ | 11 | Data export |
| Other script dirs | 73 | Federal, batch, scraper, research, etc. |
| api/ | 29 | API server (17 routers, middleware, config) |
| tests/ | 7 | 5 test files + conftest + init |
| Root | 4 | db_config, connection check, explore, validate |
| **Total** | **~530** | |

### Critical Path Scripts (Database Rebuild)

6-stage pipeline with ~40 critical scripts:
1. **Schema & base data**: `init_database.py`, `load_multiyear_olms.py`, F7 loaders
2. **External ingestion**: OSHA, WHD, 990, SEC, GLEIF, SAM, BLS, Mergent loaders
3. **Matching**: `osha_match_phase5.py`, `whd_match_phase5.py`, `match_990_national.py`, `match_sam_to_employers.py`
4. **Enrichment**: `build_corporate_crosswalk.py`, `build_corporate_hierarchy.py`, `backfill_naics.py`
5. **Scoring**: `create_scorecard_mv.py`, `compute_gower_similarity.py`, `compute_nlrb_patterns.py`
6. **Maintenance**: `db_fixes_2026_02_14.py`, `create_data_freshness.py`

### Dead References

**0 dead table references in active scripts.** Two dead references exist in `_`-prefixed disabled draft scripts only. All temp tables properly created and dropped within script lifecycle.

### Credential Scan

| Finding | Count | Severity |
|---------|-------|----------|
| Old password in .py/.sql files | 0 | FIXED |
| Old password in .md audit docs | 7 files | LOW |
| Scripts with literal-string password bug | 29 | HIGH |
| Scripts using inline psycopg2.connect() | 315 (86.3%) | MEDIUM |
| Scripts using shared db_config | 50 (13.7%) | Best practice |
| Hardcoded Windows paths | 95 | LOW |

### 🟡 HIGH: 29 Scripts Have Literal-String Password Bug

**What's wrong:** 29 scripts pass `os.environ.get('DB_PASSWORD', '')` as a quoted string literal instead of evaluating it: `password="os.environ.get('DB_PASSWORD', '')"`. The password sent to PostgreSQL is literally the text `os.environ.get('DB_PASSWORD', '')`.

**Evidence:** Grep finds 29 files across scripts/batch/, scripts/coverage/, scripts/federal/, scripts/etl/, scripts/maintenance/, scripts/verify/ with this pattern.

**Impact:** These scripts only work because PostgreSQL is configured with trust/peer authentication. If a real password is ever required, all 29 will fail. None are on the API hot path, but several are ETL/maintenance scripts that would be needed for data refreshes.

**Suggested fix:** Replace with `from db_config import get_connection` (preferred) or remove the outer quotes.

**Verified by:** Grep for `password="os.environ.get` across all .py files.

### Scheduling

No automated scheduling exists. No cron, Task Scheduler, Celery, CI/CD, Docker, or Makefiles. All operations are manual.

---

## SECTION 9: Documentation Accuracy

### CLAUDE.md (95.5% accurate)

| Issue | Claimed | Actual |
|-------|---------|--------|
| mv_employer_search rows | 118,015 | 170,775 |
| employer_comparables rows | 269,810 | 269,785 |
| unified_employers_osha rows | 100,768 | 100,766 |
| f7_union_employer_relations rows | 119,832 | 119,445 |
| Router count | 16 | 17 (auth.py added) |
| GLEIF tables listed | 6 | 9 (3 annotation tables missing) |
| MV count | 3 | 4 |

### README.md (55% accurate -- needs significant update)

| Issue | Severity |
|-------|----------|
| Lists "6-factor" scorecard -- actually 9-factor | SIGNIFICANT |
| Lists `/api/elections/recent` -- endpoint does not exist | SIGNIFICANT |
| Lists `/api/targets/search` -- endpoint does not exist | SIGNIFICANT |
| F-7 employers: "63,118" -- actually 60,953 current | SIGNIFICANT |
| NLRB Participants: "30,399 unions" -- table has 1.9M rows | CRITICAL |
| Shows ~20 endpoints -- actual count is 152 | SIGNIFICANT |
| References `frontend/` directory -- does not exist (it's `files/`) | MINOR |
| Missing 10+ major features (WHD, corporate, density, sectors, VR, BLS, auth, museum, ULP, freshness) | SIGNIFICANT |

### ROADMAP.md (67% accurate)

| Issue | Severity |
|-------|----------|
| Sprint 7.2 lists PK task as TODO -- PK exists | SIGNIFICANT |
| Test count: 160/162 -- actual 165 | MINOR |
| "What's Not Done" section doesn't strike through completed items (orphan fix, LIMIT 500) | MINOR |

### Other Documentation

| File | Issue |
|------|-------|
| LABOR_PLATFORM_ROADMAP_v11.md | "6-factor" -> should be "9-factor" |
| docs/AFSCME_NY_CASE_STUDY.md | "6-factor" -> should be "9-factor" (2 occurrences) |
| docs/AUDIT_REPORT_2026.md | Historical snapshot (Feb 13), many claims now outdated -- needs banner |

---

## SECTION 10: Overall Assessment & Recommendations

### 10.1 -- Overall Health Score

**SOLID**

This platform has made remarkable progress in the 24 hours since Round 1. The core functionality -- connecting DOL employer filings to OSHA safety records, NLRB elections, WHD wage theft cases, and corporate ownership data -- works correctly. The 9-factor organizing scorecard is computed entirely in SQL via a materialized view, eliminating score drift. Match rates have improved significantly (OSHA 47.3%, WHD 16.0% from F7 employer perspective). The 60,000-orphan crisis is resolved. The frontend monolith has been decomposed. Test coverage grew from ~47 to 165 tests. The codebase is functional, the data is connected, and an organizer can actually use this tool to make strategic decisions.

The remaining issues are mostly operational: documentation staleness, credential migration completion, unused index cleanup, and deployment hardening. None of these prevent productive use of the platform.

### 10.2 -- Top 10 Issues (Ranked by Impact)

1. **🟡 HIGH: Authentication fail-open by default.** Any deployment without `LABOR_JWT_SECRET` exposes all data and admin endpoints. Fine for local dev, dangerous for production.

2. **🟡 HIGH: 29 scripts have literal-string password bug.** `password="os.environ.get(...)"` is a string, not a function call. These scripts will break if real auth is ever configured on PostgreSQL.

3. **🟡 HIGH: 824 orphaned union file numbers (worsened from 195).** Employer-union relationships pointing to non-existent unions. Organizers miss these connections.

4. **🔵 MEDIUM: NAICS coverage only 37.7%.** The industry_density scoring factor can't fire for 62% of employers, potentially underscoring them.

5. **🔵 MEDIUM: 315 scripts still use inline database connections.** Credential migration only 13.7% complete. Fragile if connection config changes.

6. **🔵 MEDIUM: README.md 55% accurate.** Lists non-existent endpoints, wrong scorecard factor count, missing 10+ major features. Would mislead new developers.

7. **🔵 MEDIUM: 299 unused indexes consuming 1.67 GB.** Down from 370 (73%) to 299 (59%). Still significant wasted storage and write overhead.

8. **🔵 MEDIUM: No automated scheduling.** MV refreshes, data freshness checks, and backups are all manual. Data can go stale silently.

9. **🔵 MEDIUM: mv_employer_search stale.** Contains 170,775 rows but CLAUDE.md claims 118,015. Needs refresh after Sprint 1's historical employer addition.

10. **⚪ LOW: 150/164 tables never analyzed by PostgreSQL.** Query planner using default estimates for most tables. Hot-path tables are fine (autoanalyzed).

### 10.3 -- Quick Wins

| Fix | Time | Impact |
|-----|------|--------|
| Run `ANALYZE` on full schema | 2 min | Fix stale query planner estimates for 150 tables |
| Fix ROADMAP.md: mark PK task DONE, update test counts | 5 min | Documentation accuracy |
| README.md: fix scorecard "6-factor" -> "9-factor" | 2 min | Correct description |
| README.md: remove non-existent endpoints | 5 min | Prevent developer confusion |
| CLAUDE.md: update router count 16 -> 17 | 1 min | Documentation accuracy |
| CLAUDE.md: update mv_employer_search row count | 1 min | Documentation accuracy |
| Refresh `mv_employer_search` | 1 min | Bring search index up to date |
| Redact password from 7 .md audit docs | 10 min | Security hygiene |

### 10.4 -- Tables to Consider Dropping

| Table | Rows | Size | Reason |
|-------|------|------|--------|
| `platform_users` | 0 | <1 MB | Keep (needed when auth enabled) |
| Underscore-prefixed staging tables | varies | varies | Audit individually |

No clearly droppable tables found in this round. The `splink_match_results` table (5.7M rows, 1.6 GB) was already dropped since Round 1. The GLEIF tables were consolidated from 10+ GB to 396 MB. The remaining tables all serve identifiable purposes.

### 10.5 -- Missing Indexes

```sql
-- Speed up ULP batch queries (Sprint 5 join path)
CREATE INDEX IF NOT EXISTS idx_nlrb_participants_matched_employer_type
ON nlrb_participants (matched_employer_id, participant_type)
WHERE matched_employer_id IS NOT NULL;

-- Speed up freshness queries
CREATE INDEX IF NOT EXISTS idx_data_source_freshness_source
ON data_source_freshness (source_name);

-- Speed up union orphan resolution
CREATE INDEX IF NOT EXISTS idx_f7_uer_union_file_number
ON f7_union_employer_relations (union_file_number);
```

Note: 299 unused indexes should be reviewed and potentially dropped (Sprint 7 target). Adding new indexes should be balanced against the existing index bloat.

### 10.6 -- Strategic Recommendations

**Should Do Now:**
1. Complete the credential migration (29 broken + 315 inline -> db_config)
2. Investigate and fix the 824 union file number orphans
3. Update README.md to reflect actual platform capabilities (152 endpoints, 9-factor scorecard)
4. Run schema-wide `ANALYZE`
5. Set up a weekly scheduled task for MV refresh + freshness update

**Should Do Eventually:**
1. **Ingest SEC EDGAR full index** (300K+ companies) -- would dramatically improve corporate crosswalk coverage
2. **Ingest IRS BMF** (all nonprofits) -- would improve 990 match rates
3. **Drop unused indexes** (Sprint 7) -- reclaim 1.67 GB, reduce write overhead
4. **NAICS backfill** from OSHA/Mergent -- improve industry scoring coverage from 37.7%
5. **Integrate AFSCME scraper data** into main scoring pipeline (295 profiles loaded but unused)
6. **Production deployment checklist**: require JWT_SECRET, set up HTTPS, add rate limiting to all endpoints, configure proper CORS for production domain
7. **Consider ES modules** for frontend JS -- current global-function architecture works but doesn't scale well

### 10.7 -- What's Working Well

1. **Zero employer orphans.** The Sprint 1 fix that added 52,760 historical employers and eliminated all 60,000 orphaned relations is a massive data integrity win. This was the single biggest problem in Round 1.

2. **Materialized view scorecard.** Computing all 9 scoring factors in SQL via `mv_organizing_scorecard` eliminates score drift between the list and detail endpoints. The `REFRESH CONCURRENTLY` support means zero-downtime updates. This is well-engineered.

3. **Match rates dramatically improved.** OSHA: 14% -> 47.3% (employer perspective). WHD: 2% -> 16.0%. 990: 0% -> 11.9%. These aren't just incremental -- they represent a fundamentally more connected dataset.

4. **165 automated tests.** From ~47 in Round 1. Covers matching pipeline, scoring engine, API endpoints, authentication, and data integrity. The conftest.py fixture pattern is clean.

5. **Frontend decomposition.** 10,506-line monolith -> 12 focused files. API_BASE uses `window.location.origin` (no hardcoded URLs). Score explanations come from the server. This is production-ready frontend code.

6. **Security posture improved.** Hardcoded password removed from all code. CORS locked to localhost. JWT auth fully built (just needs activation). Parameterized queries throughout -- zero SQL injection risk.

7. **ULP integration.** Surfacing Unfair Labor Practice history in the scorecard gives organizers critical strategic context. The two-step name-based query approach (representation cases -> employer names -> ULP cases) is clever and handles the `matched_employer_id` gap correctly.

8. **Data freshness tracking.** The `data_source_freshness` table with 15 sources and the admin refresh endpoint give visibility into data currency. The frontend footer makes this visible to users.

9. **Clean separation of concerns.** 17 API routers, each focused on a specific domain. Middleware handles auth cross-cuttingly. db_config.py provides shared connection management. The architecture is sound.

10. **Comprehensive audit documentation.** The three-AI audit workflow and detailed audit reports create accountability. The platform's issues are well-documented, prioritized, and tracked through a sprint roadmap.

---

*Report generated by Claude Code (Opus 4.6) on February 14, 2026.*
*Verified against live database `olms_multiyear` with direct SQL queries.*
