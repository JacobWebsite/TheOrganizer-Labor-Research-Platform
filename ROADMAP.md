# Project Roadmap
## Labor Relations Research Platform
**Date:** February 14, 2026
**Based on:** Three-Audit Comparison (Claude, Gemini, Codex) + actual platform state
**Supersedes:** ROADMAP_TO_DEPLOYMENT.md v3.0 (Feb 9, 2026)

---

## Current State Summary

### What's Done (Phases 0-7 of old roadmap)
- Phase 0: Credentials, .env, pyproject.toml, connection pooling, tests -- DONE
- Phase 1: NAICS 99.2%, geocoding 99.8%, hierarchy 100%, validation suite -- DONE
- Phase 2: Scorecard quick wins (OSHA normalization, geographic favorability, size refinement) -- DONE
- Phase 3: Gower similarity engine (54K x 989 refs, employer_comparables 270K rows) -- DONE
- Phase 4 (renumbered as Phase 5): Match rate improvements -- DONE (OSHA 13.7%, WHD 6.8%, 990 2.4%)
- Phase 5 (renumbered as Phase 7): API decomposition into 16 routers + middleware -- DONE
- Phase 6 (frontend): Territory mode, search, deep dive, export -- DONE (organizer_v5.html, ~9,500 lines)
- SAM.gov integration: 826K entities loaded, 11K matched -- DONE
- NLRB predicted win %: 56K employers scored -- DONE
- Web scraper pipeline: AFSCME 295 profiles, 160 employers extracted -- DONE
- GLEIF/SEC/Mergent/USASpending crosswalk: 25,177 rows -- DONE

### What's Not Done (identified by 3 auditors)
- 60,373 orphaned f7_union_employer_relations (50.4%) -- every query at half capacity
- Authentication disabled, CORS wide open
- Password exposed in code history
- ~~Zero tests for matching pipeline and scoring engine~~ FIXED (Sprint 4: 97 new tests)
- ~~Frontend is a 10K-line monolith~~ FIXED (Sprint 6: split into CSS + 10 JS files)
- LIMIT 500 pre-filter bug in scorecard
- No data freshness tracking
- No FMCS contract expiration data
- No ULP integration
- 73% of indexes never scanned (2.1 GB wasted)

### Completed Since Audit
- Sprint 1: Orphaned relations 60K->0, password removal, doc fixes
- Sprint 2: JWT auth, CORS, frontend URL, requirements.txt
- Sprint 3: Scorecard MV (LIMIT 500 fix), admin refresh, FK indexes
- Sprint 4: Test coverage (97 new tests: matching + scoring + data integrity)
- Sprint 6: Frontend split (10,506->2,139 HTML + 11 files), score explanations API, public-sector banner

### Platform Health: 68/100 (at audit) -> improved through Sprints 1-4, 6

---

## Sprint 1: Data Integrity & Security (Critical)
**Goal:** Fix the two issues that affect every output and every user.
**Effort:** 1-2 days

### 1.1 Fix 60,373 orphaned union-employer relations
**Flagged by:** Claude (#1), Codex (#2 High)
**Impact:** Every query, score, and search is working at 50% capacity. Single highest-impact fix.
**Status:** SCRIPT WRITTEN, AWAITING REVIEW

**Root cause (confirmed by investigation):**
- `f7_employers_deduped` was built with `WHERE latest_notice_date >= '2020-01-01'`
- 56,291 employer_ids exist in raw `f7_employers` but were excluded by the date filter
- ALL 60,373 orphans are pre-2020. Zero post-2020 orphans. Zero phantom IDs.
- The Splink merge log (21,608 entries) has zero overlap -- merges were properly repointed.

**Fix strategy (3-tier, in `scripts/etl/fix_orphaned_relations.py`):**
- Tier 1: Repoint 2,713 orphans with exact name+state match in deduped (3,031 relations)
- Tier 2: Repoint 818 more via normalized name matching (932 relations)
- Tier 3: INSERT remaining 52,760 historical employers into deduped table from raw f7_employers
- Projected result: 0 orphans remaining. Deduped table grows from 60,953 to ~117K.

Tasks:
- [x] Investigate root cause (investigation script + live SQL queries)
- [x] Write fix script with dry run mode
- [x] Verify dry run produces correct projected results
- [x] **REVIEW: Codex + Gemini reviewed. 5 findings addressed (see below).**
- [x] Execute: `py scripts/etl/fix_orphaned_relations.py --execute`
- [x] Verify orphan count = 0 (confirmed)
- [x] Refresh all materialized views (3/3)
- [x] Re-run test suite (47/47 pass)
- [x] Post-review cleanup: `py scripts/etl/post_orphan_fix_cleanup.py`
  - Added `is_historical` column (Gemini + Codex)
  - Created `v_f7_employers_current` view (60,953 post-2020 only)
  - Removed 387 duplicate relations (Codex finding #1)
  - Re-normalized 52,760 employer_name_aggressive with canonical normalizer (Codex finding #4)

**Scripts:**
- `scripts/etl/fix_orphaned_relations.py` (main fix, 3-tier)
- `scripts/etl/post_orphan_fix_cleanup.py` (review feedback fixes)

### 1.2 Rotate database password and remove from code
**Flagged by:** Claude (#2), Codex (#1 Critical)
**Status:** PASSWORD REMOVED FROM CODE. Rotation pending (manual step).

Tasks:
- [ ] Change PostgreSQL password (manual: `ALTER USER postgres PASSWORD 'new_password';`)
- [ ] Update .env file with new password
- [x] Fixed nlrb_win_rates.py -- now uses db_config.get_connection()
- [x] Removed hardcoded password from README.md
- [x] Scanned all .py files -- zero remaining hardcoded password instances
- [ ] Note: Password still in audit/comparison .md files (descriptive, not executable)

### 1.3 Fix README/CLAUDE.md startup command
**Flagged by:** Claude (#4), Codex
**Status:** DONE

Tasks:
- [x] CLAUDE.md already correct: `py -m uvicorn api.main:app --reload --port 8001`
- [x] README.md fixed: `api.labor_api_v6:app` -> `api.main:app`
- [x] README.md password removed from example code

---

## Sprint 2: Deployment Blockers (Critical) -- COMPLETE
**Goal:** Make the platform safe to share with others.
**Status:** DONE (Feb 14, 2026)

### 2.1 Enable JWT authentication
**Flagged by:** All three auditors
**Status:** DONE

Tasks:
- [x] JWT secret placeholder added to .env (uncomment to enable)
- [x] Created `api/routers/auth.py`: /api/auth/login, /api/auth/register, /api/auth/refresh, /api/auth/me
- [x] `platform_users` table auto-created on first auth request (bcrypt-hashed passwords)
- [x] First user can self-register as admin; subsequent registration requires admin token
- [x] Auth middleware updated: parses tokens on public paths (optional), rejects on protected paths
- [x] Sanitized error messages (no exception details leaked)
- [x] /api/health, /docs, /api/auth/login, /api/auth/register whitelisted from auth
- [x] 16 auth tests in tests/test_auth.py, all passing
- [x] All 47 existing tests still pass (auth disabled by default)

### 2.2 Restrict CORS
**Flagged by:** All three auditors
**Status:** DONE

Tasks:
- [x] Replaced `allow_origins=["*"]` with configurable list (ALLOWED_ORIGINS env var)
- [x] Default: localhost:8001, localhost:8080, 127.0.0.1:8001, 127.0.0.1:8080
- [x] `allow_headers` restricted to `["Authorization", "Content-Type"]`

### 2.3 Externalize frontend API URL
**Flagged by:** Codex
**Status:** DONE

Tasks:
- [x] Replaced hardcoded `http://localhost:8001/api` with `(window.LABOR_API_BASE || window.location.origin) + '/api'`
- [x] Configurable via `window.LABOR_API_BASE` for custom deployments
- [x] Removed hardcoded localhost reference in error messages

### 2.4 Create requirements.txt
**Flagged by:** Claude
**Status:** DONE

Tasks:
- [x] Created curated requirements.txt with direct dependencies only
- [x] Added `bcrypt>=4.0.0` to pyproject.toml dependencies
- [x] Both pyproject.toml and requirements.txt in sync

**New files:** `api/routers/auth.py`, `tests/test_auth.py`, `requirements.txt`
**Modified:** `api/main.py`, `api/config.py`, `api/middleware/auth.py`, `tests/conftest.py`, `files/organizer_v5.html`, `.env`, `pyproject.toml`
**Tests:** 63/63 pass (47 existing + 16 new auth tests)

---

## Sprint 3: Scoring & Performance Fixes (High) -- COMPLETE
**Goal:** Fix analytical bugs that cause organizers to miss targets.
**Status:** DONE (Feb 14, 2026)

### 3.1 Fix LIMIT 500 scoring pre-filter
**Flagged by:** Claude (unique catch)
**Impact:** Employers with mediocre violation counts but excellent scores on other factors never get evaluated.
**Status:** DONE -- fixed by replacing on-the-fly Python scoring with pre-computed materialized view.

Tasks:
- [x] Read api/routers/organizing.py scorecard endpoint (confirmed LIMIT 500 at line 228)
- [x] Replaced Python scoring with SQL materialized view (scores ALL 24,841 establishments)
- [x] Old endpoint scored max 500 by penalties; new MV scores all targets by all 9 factors
- [x] Before: 6,377 visible (25-5000 emp filter + LIMIT 500). After: 24,841 scored.

### 3.2 Cache scorecard results
**Flagged by:** Claude
**Impact:** Previously reloaded 138K records into memory per request.
**Status:** DONE

Tasks:
- [x] Created `scripts/scoring/create_scorecard_mv.py` (MV creation + refresh)
- [x] `mv_organizing_scorecard`: all 9 scoring factors as SQL CASE expressions
- [x] `v_organizing_scorecard`: wrapper view adding `organizing_score` total
- [x] 3 indexes: site_state, naics_code, employee_count
- [x] Scorecard list endpoint refactored to query MV (single SQL query, no Python scoring)
- [x] Added `POST /api/admin/refresh-scorecard` endpoint
- [x] MV stats: 24,841 rows, scores 10-78, avg 32.3. Created in 5.3s.
- [x] Tier distribution: TOP 14,184 / HIGH 6,049 / MEDIUM 3,436 / LOW 1,172

### 3.3 Fix 4 broken corporate endpoints
**Flagged by:** Claude audit
**Status:** DONE (already fixed in Sprint 1 audit remediation session, Feb 14)

Tasks:
- [x] corporate.py endpoints already updated to use corporate_hierarchy + corporate_identifier_crosswalk
- [x] No further changes needed

### 3.4 Add missing database indexes for foreign keys
**Flagged by:** Codex (6 specific FKs without indexes)
**Status:** DONE

Tasks:
- [x] Identified 5 FK columns without indexes (1 significant + 4 web scraper tables)
- [x] Created `idx_osha_unified_matches_employer_id` on `osha_unified_matches(unified_employer_id)`
- [x] Created 4 web scraper table indexes on `web_profile_id`
- [x] Key join tables (osha_f7_matches, whd_f7_matches, etc.) already well-indexed

**New files:** `scripts/scoring/create_scorecard_mv.py`
**Modified:** `api/routers/organizing.py` (scorecard list endpoint refactored, admin refresh added)
**DB objects:** `mv_organizing_scorecard` (MV), `v_organizing_scorecard` (view), 8 indexes
**Tests:** 63/63 pass

---

## Sprint 4: Test Coverage (High) -- COMPLETE
**Goal:** Add safety nets for the platform's intellectual core.
**Status:** DONE (Feb 14, 2026)
**Flagged by:** All three auditors

### 4.1 Matching pipeline tests
Tasks:
- [x] Test exact name+state matching produces expected results for known pairs
- [x] Test fuzzy matching with pg_trgm threshold boundaries (0.54 should fail, 0.56 should pass at 0.55 threshold)
- [x] Test address matching logic
- [x] Test that match tiers execute in correct order (exact before fuzzy)
- [x] Test that f7_employer_id is TEXT in all match tables
- [x] Regression test: match rates don't drop below thresholds (OSHA >= 13%, WHD >= 6%, 990 >= 2%)

**File:** `tests/test_matching.py` (51 tests)

### 4.2 Scoring engine tests
Tasks:
- [x] Test each of the 9 scoring factors in isolation
- [x] Test that total score = sum of factors
- [x] Test tier assignment (TOP >= 30, HIGH >= 25, MEDIUM >= 20, LOW < 20)
- [x] Test that unmatched employers cap at expected maximum (~50/100)
- [x] Test OSHA normalization against industry averages
- [x] Test geographic favorability (RTW states, NLRB win rates)

**File:** `tests/test_scoring.py` (39 tests)

### 4.3 Data integrity tests (expand existing)
Tasks:
- [x] Test orphaned relations count = 0 (after Sprint 1.1)
- [x] Test f7_employers_deduped has PRIMARY KEY
- [x] Test all match tables have correct PK types (TEXT for f7_employer_id)
- [x] Test materialized views are populated

**New files:** `tests/test_matching.py`, `tests/test_scoring.py`
**Modified:** `tests/test_data_integrity.py` (+7 tests)
**Tests:** 160/160 pass (30 API + 16 auth + 24 data integrity + 51 matching + 39 scoring)

---

## Sprint 5: New Data Sources (Medium)
**Goal:** Add the two highest-value datasets identified by auditors.
**Effort:** 5-7 days

### 5.1 FMCS contract expiration data
**Flagged by:** Gemini (unique catch, highest-priority new data source)
**Why:** When a union contract expires, that's a critical organizing moment. This is the #1 timing signal.

Tasks:
- [ ] Research FMCS data availability (fmcs.gov, bulk download or API)
- [ ] Create `fmcs_contract_expirations` table
- [ ] ETL script: `scripts/etl/load_fmcs.py`
- [ ] Match to F7 employers (name+state, EIN if available)
- [ ] Add API endpoint: `/api/organizing/expiring-contracts?months=6`
- [ ] Add to territory mode: "X contracts expiring in next 6 months"

### 5.2 ULP (Unfair Labor Practice) integration
**Flagged by:** Claude
**Why:** Every organizer needs to know which employers retaliate. #1 missing dataset for field use.
**Note:** NLRB ULP data partially exists (nyc_ulp_open/closed tables). Need national coverage.

Tasks:
- [ ] Check existing NLRB tables for ULP data (nlrb_allegations exists)
- [ ] Build national ULP view or table aggregating by employer
- [ ] Match ULP employers to F7 via existing nlrb_employer_xref
- [ ] Add ULP count to scorecard as factor or bonus
- [ ] Add to employer deep dive profile
- [ ] API endpoint: `/api/nlrb/ulp/employer/{id}`

### 5.3 Add data freshness tracking
**Flagged by:** Claude
**Why:** Organizers need to know if data is from 2025 or 2018.

Tasks:
- [ ] Create `data_source_freshness` table (source_name, last_updated, record_count, date_range)
- [ ] Populate for all current sources
- [ ] API endpoint: `/api/admin/data-freshness`
- [ ] Display in frontend footer or info panel

---

## Sprint 6: Frontend Improvements (Medium) -- COMPLETE
**Goal:** Make the frontend maintainable without a full rewrite.
**Status:** DONE (Feb 14, 2026)
**Flagged by:** All three auditors

### 6.1 Break up organizer_v5.html
**Approach:** Plain `<script>` tags (NOT ES modules). 103 inline `onclick=` handlers require global functions. Load order enforced by script tag sequence.

Tasks:
- [x] Extract CSS into `files/css/organizer.css` (228 lines)
- [x] Extract JS into 10 files (load order matters):
  - `files/js/config.js` (30 lines — API_BASE + all global state variables)
  - `files/js/utils.js` (197 lines — pure utilities: formatNumber, escapeHtml, etc.)
  - `files/js/maps.js` (212 lines — Leaflet map init + interaction)
  - `files/js/territory.js` (671 lines — territory mode: dropdowns, dashboard, KPIs, charts)
  - `files/js/search.js` (935 lines — search mode: typeahead, results, pagination)
  - `files/js/deepdive.js` (356 lines — deep dive employer profile)
  - `files/js/detail.js` (1,352 lines — employer/union detail panel + OSHA/NLRB rendering)
  - `files/js/scorecard.js` (816 lines — organizing scorecard modal)
  - `files/js/modals.js` (2,606 lines — 11 other modals)
  - `files/js/app.js` (1,010 lines — mode switching, init, exports, URL state)
- [x] HTML reduced from 10,506 to 2,139 lines (markup only)
- [x] All 3 modes tested and working (Territory, Search, Deep Dive)
- [x] All modals tested (Analytics, Scorecard, Corporate Family, Comparison, Elections, Public Sector, Trends)

### 6.2 Add plain-language score explanations
Tasks:
- [x] 10 explanation helpers added to `api/routers/organizing.py` (+~140 lines)
- [x] `_build_explanations(row)` generates dict for all 9 scoring factors from actual data
- [x] `score_explanations` added to scorecard list + detail API responses
- [x] Frontend `getScoreReason()` prefers server explanations, falls back to client-side logic
- [x] Fixed `decimal.Decimal + float` TypeError (PostgreSQL SUM returns Decimal)

### 6.3 Document F7 public-sector blind spot in UI
Tasks:
- [x] Blue info banner added to territory mode container
- [x] Explains private-sector coverage, notes 5.4M public-sector members tracked separately

**Bugs fixed during split:**
1. `decimal.Decimal + float` TypeError — `float()` wrapping at organizing.py lines 436, 441
2. Duplicate `let` declarations — 4 scorecard vars in both scorecard.js and modals.js (SyntaxError killed modals.js)

**New files:** `files/css/organizer.css`, `files/js/{config,utils,maps,territory,search,deepdive,detail,scorecard,modals,app}.js`
**Modified:** `files/organizer_v5.html` (10,506 -> 2,139), `api/routers/organizing.py` (+~140 lines)
**Review prompts:** `docs/review_codex.md` (code review), `docs/review_gemini.md` (architecture review)
**Tests:** 162/162 pass

---

## Sprint 7: Database Cleanup (Medium)
**Goal:** Recover wasted space and improve performance.
**Effort:** 1-2 days

### 7.1 Drop unused indexes
**Flagged by:** Claude audit
**Impact:** 2.1 GB wasted, 73% never scanned, 21 confirmed duplicates (176 MB).

Tasks:
- [ ] Query pg_stat_user_indexes for idx_scan = 0
- [ ] Identify 21 duplicate indexes
- [ ] DROP INDEX CONCURRENTLY for confirmed unused/duplicate
- [ ] Verify query performance doesn't regress
- [ ] VACUUM FULL on affected tables to reclaim space

### 7.2 Add primary key to f7_employers_deduped
**Flagged by:** Claude audit (#3 issue)
**Impact:** Core table with 60,953 rows has no PK.

Tasks:
- [ ] Verify employer_id is unique: SELECT COUNT(DISTINCT employer_id) = COUNT(*) FROM f7_employers_deduped
- [ ] ALTER TABLE f7_employers_deduped ADD PRIMARY KEY (employer_id)

### 7.3 Evaluate GLEIF data ROI
**Flagged by:** Claude (unique catch)
**Issue:** 10.6 GB for 605 matches. Half the database for almost no value.

Tasks:
- [ ] Assess: are the 605 GLEIF matches high-value? (major corporations?)
- [ ] Option A: Archive gleif schema tables to compressed dump, keep gleif_us_entities
- [ ] Option B: Keep as-is if the corporate hierarchy data (125K links) depends on it
- [ ] Decision: balance storage cost vs data value

### 7.4 Organize scripts directory
**Flagged by:** Claude, Codex
**Issue:** 785 .py files, many legacy/one-off.

Tasks:
- [ ] Create `archive/scripts/` for one-off and deprecated scripts
- [ ] Move scripts with broken password patterns to archive (or fix them)
- [ ] Keep `scripts/{etl,scoring,matching,scraper,validation,analysis}/` as active directories
- [ ] Update any references in documentation

---

## Sprint 8: Deployment Infrastructure (Low/When Ready)
**Goal:** Make the platform accessible to others.
**Effort:** 1-2 weeks

### 8.1 Docker setup
**Flagged by:** Claude, Gemini

Tasks:
- [ ] Dockerfile for API (Python 3.12, not 3.14)
- [ ] docker-compose.yml (API + PostgreSQL + nginx)
- [ ] Volume mount for .env and data directory
- [ ] Health check endpoint already exists

### 8.2 CI/CD pipeline
**Flagged by:** Claude, Gemini

Tasks:
- [ ] GitHub Actions workflow: test on push, lint on PR
- [ ] Run `py -m pytest tests/ -v` in CI
- [ ] Optional: deploy on merge to main (Railway/Render)

### 8.3 Database migration tooling
**Flagged by:** Gemini (unique catch)

Tasks:
- [ ] Evaluate Alembic for SQLAlchemy or raw SQL migrations
- [ ] Create initial migration from current schema
- [ ] Document: "how to add a new table" workflow

---

## Sprint 9: Polish & Accessibility (Low)
**Goal:** Quality-of-life improvements.
**Effort:** Ongoing

### 9.1 Accessibility (WCAG basics)
**Flagged by:** Claude, Codex
- [ ] Add aria-labels to interactive elements
- [ ] Keyboard navigation for modals and tables
- [ ] Color contrast check (score tiers especially)

### 9.2 Mobile responsive design
**Flagged by:** All three auditors
- [ ] Test on mobile viewport
- [ ] Collapse sidebar/nav on small screens
- [ ] Touch-friendly map controls

### 9.3 Score model versioning
**Flagged by:** Codex (unique catch)
- [ ] Add `score_version` column to materialized scorecard
- [ ] Track methodology changes in `score_versions` table
- [ ] Display: "Scored using methodology v2.1 (Feb 2026)"

### 9.4 Temporal scoring decay
**Flagged by:** Claude
- [ ] Weight recent violations more than old ones
- [ ] A 2025 violation matters more than a 2015 one

### 9.5 Evidence packet export
**Flagged by:** Codex (unique catch)
- [ ] Generate printable bundle: safety record + wage theft + elections + comparables
- [ ] Single downloadable PDF for campaign use

---

## Future Considerations (Post-Deployment)

### Data Sources to Evaluate
| Source | Champion | Value |
|--------|----------|-------|
| FMCS contract expirations | Gemini | Contract timing = #1 organizing signal |
| CPS microdata (IPUMS) | Roadmap v3 | Granular density at industry x geography x occupation |
| State PERB data (NY, CA, IL) | Roadmap v3 | Public employment relations boards |
| FEC/OpenSecrets PAC data | Gemini | Political contribution tracking |
| BLS OEWS staffing patterns | Roadmap v3 | Occupation mix comparison via cosine similarity |
| Company descriptions (embeddings) | Roadmap v3 | Sentence-BERT for nuanced employer similarity |
| News/media monitoring | Gemini | Real-time alerts for strikes, layoffs, closures |

### Architecture Evolution
| Decision | Current | Future |
|----------|---------|--------|
| Frontend | Plain `<script>` tags, 10 JS files + CSS | ES modules or React/Vue SPA (when team grows) |
| State management | Global `let` vars in config.js + module-scoped | Redux/Zustand (with framework migration) |
| Rate limiting | In-memory (leaks) | Redis-backed (multi-instance) |
| Matching strategy | Tiered (exact -> fuzzy) | Splink-first (Gemini suggestion) |
| Scoring | Heuristic (hand-tuned weights) | ML (logistic regression on NLRB outcomes) |
| SQL patterns | f-string assembly (safe but fragile) | Parameterized queries or SQLAlchemy Core |

### Predictive Model (When Ready)
**Prerequisites:** Sprints 1-4 complete, match rates improved, orphaned data fixed.
- Build features+outcome dataset from 33,096 NLRB elections
- Temporal split: pre-2022 train (~25K), 2022+ test (~8K)
- If AUC > 0.65: publish. If < 0.55: rebuild.
- Replace hand-picked weights with empirically optimal ones.

---

## Priority Summary

| Sprint | Priority | Effort | Key Metric |
|--------|----------|--------|------------|
| **1: Data Integrity & Security** | CRITICAL | 1-2 days | Orphaned relations -> 0, password rotated |
| **2: Deployment Blockers** | CRITICAL | 2-3 days | Auth enabled, CORS restricted |
| **3: Scoring & Performance** | HIGH | 2-3 days | LIMIT 500 bug fixed, scorecard cached |
| **4: Test Coverage** | HIGH | DONE | 97 tests: 51 matching + 39 scoring + 7 integrity |
| **5: New Data Sources** | MEDIUM | 5-7 days | FMCS + ULP integrated |
| **6: Frontend Improvements** | MEDIUM | DONE | 10,506 -> 2,139 HTML + 11 CSS/JS files |
| **7: Database Cleanup** | MEDIUM | 1-2 days | ~3.5 GB recovered, PK added |
| **8: Deployment Infrastructure** | LOW | 1-2 weeks | Docker + CI/CD |
| **9: Polish & Accessibility** | LOW | Ongoing | Mobile, a11y, versioning |

**If you had one focused week:** Sprints 1-3 resolve every Critical and most High items.
**If you had two weeks:** Add Sprint 4 (tests) and Sprint 5 (new data).
**If you had a month:** Complete through Sprint 7, start Sprint 8.

---

## Audit Methodology Note

This roadmap synthesizes findings from three independent AI audits:
- **Claude Code:** Most detailed (32 ranked items). Strongest on data quality and analytical bugs.
- **Gemini:** Most strategic/forward-looking. Best on new data sources and architecture vision.
- **Codex:** Most security-focused. Best on systematic risk reduction.

Where all three agreed, confidence is highest. Where only one flagged an issue, it may be a unique insight or an overreach. The unified priority list weights consensus heavily.

Full comparison: `three_audit_comparison.md`
Previous roadmap: `ROADMAP_TO_DEPLOYMENT.md` (Feb 9, 2026 -- many phases now complete)
Audit report: `docs/AUDIT_REPORT_2026.md`
