# Independent Platform Audit — Claude Code (Opus 4.6)
## Date: 2026-02-14

---

## Executive Summary

The Labor Relations Research Platform is an ambitious and technically impressive project that integrates data from 10+ federal government sources into a unified system for union organizing intelligence. The breadth of data — 14.5M deduplicated union members, 1M+ OSHA inspections, 363K wage theft cases, 33K NLRB elections, 826K SAM.gov federal contractors — represents a genuinely novel research capability that doesn't exist anywhere else in the labor movement. The 5-tier entity matching pipeline, membership deduplication methodology (validated within 1.4% of BLS benchmarks), and 9-factor organizing scorecard demonstrate serious analytical thinking about what makes an employer a viable organizing target.

However, the platform has significant structural problems that would prevent production deployment. The most critical: **50.4% of union-employer bargaining relationships (60,373 rows) are silently dropped** because `f7_union_employer_relations` references pre-deduplication employer IDs that don't exist in `f7_employers_deduped`. This means the platform's core value proposition — linking unions to employers — is operating at half capacity in any query that JOINs through these tables. Additionally, the database carries 319 unused indexes consuming 2.6 GB, CORS is wide open (`allow_origins=["*"]`), authentication is disabled by default, and the entire frontend is a single 10,506-line HTML file with zero accessibility compliance. Database credentials appear in plaintext in at least one committed Python script.

The path forward is clear: fix the orphaned relations data integrity issue (immediate ~50% improvement in union-employer coverage), lock down security for multi-user deployment, break the frontend monolith into components, and add the workflow features (campaign tracking, ULP filing, geocoded mapping) that would make this indispensable rather than merely interesting to union organizers.

---

## Audit Findings by Area

### 1. Project Organization & Architecture

**What's Working Well:**
- The API decomposition (Phase 7) is clean: 16 router files organized by domain, 3 middleware layers, shared helpers. A new developer can find the OSHA endpoints in `api/routers/osha.py` without guessing.
- Scripts are organized by function: `scripts/etl/` (data loading), `scripts/scoring/` (matching), `scripts/analysis/` (research), `scripts/scraper/` (web crawling).
- Shared database configuration via `db_config.py` with `.env` file support.
- `.gitignore` properly excludes `.env`, `__pycache__`, data directories, and large files.

**What's Broken or Risky:**
- **785 Python scripts** with no clear indication of which are current vs. deprecated. Many appear to be one-off analysis scripts that were never cleaned up.
- **`frontend/` directory exists but is empty** — the actual frontend is `files/organizer_v5.html`, which is confusing for new developers.
- **16 markdown files in the project root** including 4 versions of the roadmap (`v10`, `v11`, `v12`, `v13`), creating clutter and confusion about which is current.
- **README.md has the wrong startup command**: says `py -m uvicorn api.labor_api_v6:app` but the correct command is `py -m uvicorn api.main:app --reload --port 8001`. A new developer following the README would get an import error immediately.
- **No `requirements.txt` or `pyproject.toml`** — dependencies aren't pinned. The project uses Python 3.14 (bleeding edge) with at least psycopg2, fastapi, uvicorn, splink, crawl4ai, rapidfuzz, numpy, and others, but there's no manifest.
- **Project root doubles as working directory** — data files, scripts, SQL, docs, and config all share the top level.

**Recommendations:**
- Create a `requirements.txt` with pinned versions (1 hour).
- Archive old roadmap versions into `docs/archive/` (15 minutes).
- Fix README.md startup command (5 minutes).
- Move or delete the empty `frontend/` directory (5 minutes).
- Add a `scripts/deprecated/` folder and move one-off analysis scripts there (2 hours).

---

### 2. Database Design

**What's Working Well:**
- Comprehensive schema: 342 tables and 187 views covering unions, employers, OSHA, WHD, NLRB, BLS, SAM, Mergent, GLEIF, SEC, and web scraper data.
- `corporate_identifier_crosswalk` table is a smart design — a single table linking employer IDs across all data sources (EIN, DUNS, CIK, LEI, UEI, CAGE code).
- Materialized views for expensive aggregations (e.g., `mv_employer_features` for Gower similarity).
- pg_trgm GIN indexes on name columns for fuzzy matching performance.
- Match tables track `match_tier` and `similarity_score` for auditability.

**What's Broken or Risky:**
- **`f7_employers_deduped` has no PRIMARY KEY.** This is the core table (60,953 rows) that everything references. Without a PK, there's no guarantee of uniqueness and no efficient point lookups.
- **60,373 orphaned rows in `f7_union_employer_relations`** (50.4% of 119,770 total). These rows reference `employer_id` values from the pre-deduplication stage that don't exist in `f7_employers_deduped`. Any `INNER JOIN` silently drops half the bargaining links. This is the single most damaging data quality issue in the platform.
- **14 tables lack primary keys** including several core tables.
- **No foreign key constraints enforced anywhere.** Referential integrity is maintained by convention, not by the database. When matching scripts update IDs, nothing prevents orphaned references.
- **319 indexes never scanned** (of 437 total, 73%) consuming 2.6 GB. Includes 21 confirmed duplicate indexes (176 MB). Total recoverable space: ~3.5 GB.
- **GLEIF data consumes 10.6 GB (53% of the database)** but contributes only 605 employer matches via Splink. The ROI is extremely poor.
- **Naming inconsistencies:** `osha_f7_matches` vs `whd_f7_matches` vs `national_990_f7_matches` (why "national_" prefix on only one?). `employer_id` in some tables is TEXT (hex hashes), INTEGER in others.
- **No `updated_at` timestamps** on match tables or crosswalk — no way to know when data was last refreshed.
- **pg_stat_user_tables shows 0 rows for many tables** — `ANALYZE` hasn't been run recently, meaning the query planner is likely making suboptimal choices.

**Recommendations:**
- Add PRIMARY KEY to `f7_employers_deduped` on `employer_id` (30 minutes).
- Fix the 60,373 orphaned relations — map pre-dedup IDs to post-dedup IDs using the Splink merge mapping (2-4 hours).
- Run `ANALYZE` on all tables (5 minutes).
- Drop the 319 unused indexes to reclaim 2.6 GB (1 hour with verification).
- Add `created_at`/`updated_at` columns to match tables (1 hour).
- Consider archiving or removing GLEIF data if 605 matches don't justify 10.6 GB (30 minutes).

---

### 3. Entity Matching Pipeline

**What's Working Well:**
- **5-tier cascade design is sound:** EIN exact match → normalized name+state → address → aggressive name → fuzzy trigram. Each tier has decreasing confidence and is tracked separately.
- **Composite fuzzy scoring** (0.35 JaroWinkler + 0.35 token_set_ratio + 0.30 fuzz.ratio) is well-calibrated — JW catches prefix similarity, token_set handles word reordering, fuzz.ratio catches overall similarity.
- **pg_trgm candidate retrieval before scoring** is the correct architecture — GIN index filters candidates, then Python-side scoring ranks them. This avoids the O(n*m) cross-join that killed the v1 SAM matching.
- **`strip_facility_markers()` PL/pgSQL function** handles real-world naming chaos (STORE #123, WAREHOUSE, DBA suffixes) effectively.
- **Match tier tracking** allows downstream consumers to filter by confidence level.
- **cleanco normalization** for international corporate suffixes doubled GLEIF match rates.

**What's Broken or Risky:**
- **Match rates are still low:** OSHA 13.7%, WHD 6.8%, 990 2.4%. This is partly structural (F7 only covers ~61K unionized employers, while OSHA has 1M+ establishments, most non-union), but it means 86% of OSHA establishments and 93% of WHD cases can't be linked to union intelligence.
- **Confidence scores are low even for matches:** Only 23-27% of OSHA matches and 20% of WHD matches are in the highest confidence tier (exact EIN or name+address). The remaining 73-80% are fuzzy matches that need human review.
- **No quality gates or automated alerting.** If a matching run produces garbage (like the Tier D 0.40 threshold incident that produced 155K false positives including USPS→UPS), nothing catches it until manual review.
- **Scores are not persisted.** The organizing scorecard is computed on-the-fly in Python on every API request. This means: (a) no historical tracking, (b) no batch analysis, (c) repeated expensive computation.
- **Global state pollution in pg_trgm threshold:** `SET pg_trgm.similarity_threshold = 0.55` affects the entire database session. If another query runs in the same connection pool slot, it inherits the modified threshold.
- **Address matching silently fails on PO boxes, suites, and rural routes.** The `normalize_address()` function handles common abbreviations but doesn't standardize these formats.
- **No match review workflow.** Fuzzy matches at 0.55-0.70 similarity need human verification, but there's no mechanism for an analyst to review, confirm, or reject matches.
- **Mergent bridge is NY-only** (1,226 rows, all New York state), severely limiting its value for national matching.

**Recommendations:**
- Add quality gates: reject any matching run where false positive rate exceeds a threshold (4 hours).
- Persist scorecard results to a `scorecard_cache` table with timestamps (4 hours).
- Add a `match_review` table and simple UI for human verification of fuzzy matches (1-2 days).
- Set pg_trgm threshold per-query with `SET LOCAL` instead of `SET` to avoid connection pool contamination (30 minutes).
- Add `updated_at` to match tables to track staleness (30 minutes).

---

### 4. Scoring & Target Identification

**What's Working Well:**
- **9-factor scorecard design is thoughtful.** The factors — union presence (20pts), industry density (10), geographic favorability (10), employer size (10), OSHA violations (10), NLRB history (10), government contracts (10), BLS projections (10), employer similarity (10) — cover the key dimensions an organizer would consider.
- **Union presence gets double weight (20 points)** — this correctly reflects that having an existing union relationship is the strongest indicator of organizing viability.
- **Size sweet spot (50-250 employees = max score)** matches real-world organizing wisdom: too small lacks resources, too large is harder to organize.
- **OSHA violation normalization against industry average** prevents overweighting industries that are inherently more inspected (construction, manufacturing).
- **Geographic score incorporates right-to-work state adjustment** — correctly penalizing states where organizing is legally harder.
- **NLRB predicted win % model** uses state (35%) + industry (35%) + size (20%) + trend (10%) — reasonable weightings.
- **Employer similarity via Gower distance** is clever — finding employers similar to already-organized ones is a genuine organizing heuristic.

**What's Broken or Risky:**
- **Unmatched OSHA establishments are capped at ~50/100.** An establishment without an F7 match loses the 20-point union factor, plus contracts (10), similarity (10), and NLRB (10) — a 50-point ceiling. Since 86% of OSHA establishments are unmatched, the vast majority of scorecard results are artificially compressed into the 0-50 range, making the scoring tiers less meaningful.
- **Score computation is O(n) per request with large pre-fetches.** The `_build_match_lookup()` function loads ALL 138K osha_f7_matches into a Python dict on every scorecard request. With 500 results per page, this is wildly inefficient.
- **Contract scoring uses ILIKE substring matching** (`ILIKE %{estab_name[:15]}%`) against NYC prevailing wage data. This is both a false-positive risk (short employer names match many contracts) and limited to NYC data only.
- **Scorecard list pre-filters with `LIMIT 500`** before scoring. This means the "top" organizing targets are the top 500 from the base query (sorted by violation count or other DB-level metric), not the top 500 by composite score. High-scoring employers outside the initial 500 are never evaluated.
- **Industry density data is from 12 BLS sectors** — very coarse. Healthcare, education, and government each get one density number, even though sub-industries vary dramatically (hospital nurses vs. home health aides).
- **No temporal weighting.** A violation from 2010 scores the same as one from 2025. Recent violations should matter more for organizing decisions.
- **Tier thresholds (TOP>=30, HIGH>=25, MEDIUM>=20, LOW<20) were recalibrated** but may still not reflect meaningful organizing distinctions. The gap between LOW (20) and TOP (30) is narrow.
- **Two separate scoring systems exist** (OSHA scorecard 0-100 and Mergent sector scorecard 0-62) but they're not unified. An organizer seeing a score of "45" can't tell which system generated it.

**Recommendations:**
- Cache scorecard results in a `scorecard_cache` table, recompute nightly or on data refresh (4 hours).
- Replace the `LIMIT 500` pre-filter with score-then-rank: compute scores for all candidates in a state/metro, then return top N (4 hours).
- Add temporal decay to violation scoring — recent violations weighted 2-3x more than old ones (2 hours).
- Unify the two scoring systems or clearly label which is which in the API response (2 hours).
- Replace ILIKE contract matching with a proper name-matching lookup table (2 hours).

---

### 5. API Design & Security

**What's Working Well:**
- **SQL injection is effectively mitigated.** 99%+ of queries use parameterized statements (`%s` placeholders with params tuples). The `safe_sort_col()` and `safe_order_dir()` helpers whitelist ORDER BY values. Sector view names are validated against the `SECTOR_VIEWS` dict.
- **16 well-organized router files** with clear domain separation.
- **ThreadedConnectionPool** (2-20 connections) with context manager for proper cleanup.
- **Rate limiting exists** (100 requests/60s per IP via sliding window).
- **JWT authentication framework exists** (disabled by default, enabled by setting `LABOR_JWT_SECRET`).
- **Health check endpoint** returns database connectivity status.

**What's Broken or Risky:**
- **CORS `allow_origins=["*"]`** — any website can make authenticated API requests on behalf of a user. This must be restricted before deployment.
- **Authentication is disabled by default.** Setting `LABOR_JWT_SECRET` to empty string makes the auth middleware a no-op. All 145+ endpoints are completely open.
- **No authorization layer.** Even when auth is enabled, JWT roles are set on `request.state` but never checked. Any authenticated user can access everything.
- **Rate limiter has a memory leak.** The `_requests` dict grows unbounded — IP addresses are added but empty lists are never pruned. Over days/weeks of operation, this would consume significant memory.
- **Rate limiter is spoofable via X-Forwarded-For header.** Attackers can rotate IPs trivially by sending different header values.
- **Auth middleware leaks exception details:** `content={"detail": f"Invalid token: {exc}"}` exposes internal error messages including stack traces.
- **No input validation on query parameters** beyond basic type coercion. String parameters aren't length-limited, which could enable DoS via extremely long search strings.
- **No HTTPS enforcement.** The API serves over HTTP with no redirect to HTTPS.
- **Pagination exists but max limit is 500**, and some endpoints default to returning all results if no limit is specified.
- **4 corporate.py endpoints reference nonexistent table/columns** (`corporate_ultimate_parents`, `corporate_family_id`) — these return 500 errors.
- **No API versioning.** Breaking changes would affect all consumers simultaneously.

**Recommendations:**
- Restrict CORS origins to specific frontend domain(s) (15 minutes).
- Enable auth and add role-based access control before any multi-user deployment (4-8 hours).
- Fix rate limiter memory leak by pruning stale IPs (30 minutes).
- Use the real client IP from a trusted proxy header, not raw X-Forwarded-For (1 hour).
- Sanitize exception messages in auth middleware (15 minutes).
- Remove or fix the 4 broken corporate endpoints (1 hour).
- Add input length validation on string parameters (2 hours).

---

### 6. Data Quality & Coverage

**What's Working Well:**
- **Membership deduplication is excellent.** 70.1M raw LM2 records deduplicated to 14.5M, within 1.4% of the BLS benchmark of 14.3M. The methodology (hierarchy-based dedup using federation/international/local classification) is well-documented and validated.
- **State-level validation:** 50/51 states within ±15% of EPI (Economic Policy Institute) benchmarks.
- **NLRB data quality is high:** 33,096 elections with 99.1% having outcomes.
- **Multiple validation checkpoints** in test_data_integrity.py verify key metrics on every test run.
- **Match tier tracking** provides transparency about confidence levels.

**What's Broken or Risky:**
- **F7 only covers private-sector employers.** Public-sector unions (NEA 2.8M, AFT 1.8M, NFOP 373K, NNU 215K, postal unions) have ~0% F7 coverage, meaning 5.4M+ members are invisible to the platform. This is a fundamental coverage gap, not a bug.
- **Building trades over-count by 10-32x.** F7 reports "covered workers" (open-shop, project-based), while LM2 reports dues-paying members. USW shows 32x, PPF 29x, IATSE 27x. The platform displays F7 numbers without this caveat.
- **195 orphaned F7 union file numbers** not in `union_hierarchy` or `unions_master`, covering 92,627 workers across 812 employers.
- **OSHA match rate of 13.7%** means 86.3% of workplace safety inspections can't be linked to union intelligence. Similarly for WHD (93.2% unmatched) and 990 filers (97.6% unmatched).
- **Low confidence match rates:** Only 23-27% of OSHA matches and ~20% of WHD matches are high-confidence (exact EIN or name+address). The rest are fuzzy.
- **No data freshness tracking.** There's no record of when each data source was last updated. OSHA data could be 6 months old and no one would know.
- **GLEIF data is 10.6 GB but only contributes 605 matches** — questionable value.
- **SAM.gov matching was in progress** at last session (10,164 matches of 826K entities). Status of Tier C/D completion is unclear.
- **`pg_stat_user_tables` shows 0 rows for many tables** — stale statistics mean the query planner can't optimize effectively.
- **NAICS codes are mostly 2-digit** on F7 data, limiting industry-level analysis precision.

**Recommendations:**
- Add a `data_freshness` table tracking source, last_updated, record_count for each dataset (2 hours).
- Document the F7 private-sector limitation prominently in the UI and documentation (1 hour).
- Add a caveat/footnote for building trades member counts explaining F7 vs LM2 semantics (1 hour).
- Run `ANALYZE` on all tables to update statistics (5 minutes).
- Resolve the 195 orphaned F7 union file numbers via OLMS API lookup (4 hours).
- Consider removing GLEIF data or archiving it to reduce DB size by 50% (30 minutes).

---

### 7. Frontend & User Experience

**What's Working Well:**
- **Three-mode design** (Territory / Search / Deep Dive) maps to real organizer workflows: "What's happening in my region?" → "Search for specific employers" → "Deep dive into one employer."
- **Territory mode makes 7 parallel API calls** for a rich dashboard: KPI cards, map, charts, tables.
- **Deep dive employer profile** includes scorecard breakdown, OSHA violations, NLRB predictions, election history, and similar employers — genuinely useful for organizing research.
- **Export functionality** includes print-to-PDF and CSV download for territory reports and employer profiles.
- **Welcome stats banner** shows platform-wide numbers to build confidence in data coverage.

**What's Broken or Risky:**
- **10,506-line single HTML file** (`files/organizer_v5.html`). This is unmaintainable. Any edit risks breaking unrelated functionality. No component reuse, no templating, no build system.
- **25+ global JavaScript variables** manage application state. No state management pattern, no isolation between modes.
- **40+ try-catch blocks silently swallow errors** — failed API calls show no error message to the user, just empty sections.
- **Zero accessibility compliance.** No ARIA labels, no keyboard navigation, no screen reader support, no color contrast verification. This would fail WCAG 2.1 Level A.
- **Not mobile responsive.** CSS uses fixed pixel widths in many places. Union organizers in the field (who may be on phones or tablets) can't use this.
- **XSS vulnerabilities in onclick handlers.** Employer names containing single quotes can break `onclick="fn('${escapeHtml(name)}')"` patterns. The `escapeHtml()` function was patched to escape single quotes as `&#39;` but this pattern is fragile.
- **Memory leaks ~20 MB** from Chart.js instances and DOM elements not being cleaned up when switching between modes.
- **All CDN dependencies loaded at runtime** (Chart.js, Leaflet) with no local fallback. If a CDN goes down, the app breaks.
- **Territory map is mostly empty** — scorecard targets have no lat/lon coordinates, so the map can only show state-level zoom, not pinpoint establishments.
- **No loading indicators on some API calls** — the UI appears frozen during long operations.
- **Race conditions on rapid mode switching** — clicking between modes before API calls complete can leave the UI in an inconsistent state.

**Recommendations:**
- Break the HTML file into a component-based framework (React, Vue, or even Web Components) as a medium-term project (2-3 weeks).
- In the short term: add proper error display for failed API calls, replacing silent catch blocks (1 day).
- Add geocoding (Google Maps or Census Geocoder API) to enable map-based visualization (2-3 days).
- Add basic ARIA labels and keyboard navigation for accessibility (2-3 days).
- Add viewport meta tag and responsive CSS breakpoints for mobile (1-2 days).
- Bundle CDN dependencies locally as fallback (2 hours).

---

### 8. Testing & Reliability

**What's Working Well:**
- **47 tests total** covering API endpoints and data integrity.
- **Data integrity tests** verify critical metrics: BLS alignment (14.3M ±5%), state coverage (45/51 states), crosswalk orphan rate (<40%), match rates (OSHA ≥13%, WHD ≥6%, 990 ≥2%).
- **Performance test** checks that all critical endpoints respond in <5 seconds.
- **Tests run against the real database**, catching real data quality issues.

**What's Broken or Risky:**
- **No test isolation.** Tests run against the production database with `autocommit=True`. Tests that write data would permanently modify production data. There's no transaction rollback, no test database, no mocking.
- **Assertions are extremely loose.** Most API tests check `status_code == 200` and the presence of a top-level key. They don't validate response schemas, data types, value ranges, or business logic. Example: the OSHA scorecard test checks that `score_breakdown` exists but not that individual scores are within valid ranges.
- **No integration tests.** The matching pipeline, scorecard computation, and data flow between components are untested.
- **No tests for the matching pipeline.** The 5-tier matching logic that produces the platform's core entity links has zero automated tests. A regression could silently corrupt matches.
- **No tests for the scoring engine.** The 9-factor scorecard in `organizing.py` has no unit tests for individual score factors.
- **No monitoring or alerting.** If the API goes down, a matching run produces garbage, or data gets corrupted, no one is notified.
- **No CI/CD pipeline.** Tests must be run manually. There's no pre-commit hook, no GitHub Actions, no automated gate.
- **Test file organization is minimal:** just `test_api.py` and `test_data_integrity.py`. No test utilities, no fixtures, no factories.
- **Flaky potential:** Tests depend on exact database state (e.g., expecting ~60,953 F7 employers ±500). A legitimate data refresh could break tests.

**Recommendations:**
- Add a test database or transaction-wrapped test fixtures to prevent production contamination (4 hours).
- Add unit tests for each scoring factor in organizing.py (1 day).
- Add integration tests for the matching pipeline with known-answer test cases (1 day).
- Add schema validation to API tests (e.g., with pydantic models or jsonschema) (4 hours).
- Set up GitHub Actions CI to run tests on every push (2 hours).
- Add basic uptime monitoring (even a cron job that hits /api/health) (1 hour).

---

### 9. Documentation

**What's Working Well:**
- **CLAUDE.md is comprehensive** (675 lines) — covers schema, API endpoints, scoring details, matching tiers, and development conventions.
- **METHODOLOGY_SUMMARY_v8.md** provides clear explanations of deduplication, matching, and validation methodologies.
- **SESSION_LOG_2026.md** provides detailed development history — useful for understanding why decisions were made.
- **The blind audit prompt itself** (`BLIND_AUDIT_PROMPT.md`) is excellent documentation of what the platform does and how to evaluate it.

**What's Broken or Risky:**
- **README.md has the wrong API startup command.** A new developer's first experience would be an error. This was identified in the previous audit (Feb 13) but apparently not fixed in README.
- **CLAUDE.md had 19 identified inaccuracies** (per Feb 13 audit) — wrong row counts, missing tables, incorrect scoring tiers. Some were remediated on Feb 14, but the doc is so large that drift is inevitable.
- **4 versions of the roadmap** in the project root (`v10`, `v11`, `v12`, `v13`). Only `v13` is current; the others are confusing.
- **No setup guide.** There's no step-by-step "here's how to set up this project from scratch" document covering: install Python 3.14, install PostgreSQL, create the database, load data, install dependencies, run the API.
- **No data refresh guide.** When OSHA publishes new inspection data or BLS releases new density figures, there's no documented procedure for updating the platform.
- **No API documentation beyond CLAUDE.md.** FastAPI auto-generates Swagger docs at `/docs`, but these lack descriptions, examples, and expected response shapes.
- **Code comments are sparse.** The scoring engine (organizing.py, 709 lines) has minimal inline comments explaining the business logic behind scoring decisions.

**Recommendations:**
- Fix README.md startup command immediately (5 minutes).
- Write a SETUP.md with step-by-step installation instructions (2-3 hours).
- Write a DATA_REFRESH.md documenting update procedures for each data source (4 hours).
- Archive old roadmap versions (15 minutes).
- Add docstrings and business logic comments to organizing.py scoring functions (2 hours).
- Add response examples to FastAPI endpoint decorators for auto-generated docs (4 hours).

---

### 10. Security & Deployment Readiness

**What's Working Well:**
- **`.env` file is properly gitignored** — database credentials aren't in version control (with one exception, see below).
- **`db_config.py` reads from environment** — the intended pattern is correct.
- **JWT authentication framework exists** and can be enabled by setting an environment variable.
- **Rate limiting exists** with configurable parameters.
- **SQL injection is mitigated** through consistent use of parameterized queries.

**What's Broken or Risky:**
- **Plaintext password in committed code.** `scripts/scoring/nlrb_win_rates.py` line 9 contains: `DB_PASSWORD = os.environ.get('DB_PASSWORD', 'Juniordog33!')`. This password is in git history even if the file is later changed.
- **BLIND_AUDIT_PROMPT.md contains the database password** in the example connection string. If this file is committed to a public repository, the password is exposed.
- **~259 scripts historically had broken password patterns** — string literal `'os.environ.get('DB_PASSWORD', '')'` instead of actual function call. Many were reportedly fixed on Feb 14, but the fix should be verified.
- **CORS allows all origins.** This is a deployment blocker for any multi-user environment.
- **No HTTPS.** The API serves over plain HTTP. All data (including any future auth tokens) would be transmitted in cleartext.
- **No CSRF protection.** Combined with open CORS, this enables cross-site request forgery.
- **Auth is disabled by default** with no warning in the startup logs.
- **Database connection uses `postgres` superuser** — should use a limited-privilege application user.
- **No secrets management.** Credentials are in a local `.env` file, which won't scale to server deployment.
- **No containerization.** No Dockerfile, no docker-compose.yml. Deployment to any server would require manual setup of Python 3.14, PostgreSQL, system dependencies.
- **Static files served from the API process.** In production, a reverse proxy (nginx) should serve static files.
- **No backup strategy documented.** A 20 GB database with months of matching results has no backup plan.

**This is NOT deployment-ready.** It is a local prototype. Deploying it for real users would require: HTTPS, auth, CORS lockdown, a non-superuser database role, containerization, a reverse proxy, secrets management, backups, and monitoring — minimum.

**Recommendations:**
- Rotate the database password immediately (it's been committed to code) (15 minutes).
- Create a Dockerfile and docker-compose.yml for reproducible deployment (4-8 hours).
- Set up a limited-privilege PostgreSQL role for the application (1 hour).
- Add HTTPS via reverse proxy (nginx or Caddy) for any non-local deployment (2-4 hours).
- Enable auth by default and require explicit opt-out in development mode (2 hours).
- Implement automated database backups (pg_dump cron job or managed backup) (2 hours).

---

## Prioritized Improvements

### CRITICAL — Fix This Week

| # | Finding | Impact | Fix | Effort |
|---|---------|--------|-----|--------|
| 1 | **60,373 orphaned f7_union_employer_relations (50.4%)** | Half of all union-employer links silently dropped in JOINs. The platform's core data relationship is broken at 50% capacity. | Map pre-dedup employer IDs to post-dedup IDs using the Splink merge mapping. Update all 60,373 rows to reference the correct deduplicated employer_id. | 4-6 hours |
| 2 | **Database password committed to git** | `nlrb_win_rates.py` and `BLIND_AUDIT_PROMPT.md` contain the plaintext password `Juniordog33!`. Anyone with repo access has DB credentials. | Rotate the password. Remove hardcoded password from nlrb_win_rates.py. Scrub from git history with `git filter-branch` or BFG Repo-Cleaner. | 2 hours |
| 3 | **f7_employers_deduped has no PRIMARY KEY** | Core table with 60,953 rows has no uniqueness constraint. Duplicate inserts, inefficient lookups, and broken referential integrity are all possible. | `ALTER TABLE f7_employers_deduped ADD PRIMARY KEY (employer_id);` | 30 minutes |
| 4 | **README.md has wrong startup command** | New developers can't start the application. First experience is an error. | Change `api.labor_api_v6:app` to `api.main:app` in README.md. | 5 minutes |

### HIGH — Fix Before Users Touch It (Next 2 Weeks)

| # | Finding | Impact | Fix | Effort |
|---|---------|--------|-----|--------|
| 5 | **CORS `allow_origins=["*"]`** | Any website can make API requests. Combined with no auth, this means any internet user can query the full database. | Restrict to specific frontend domain(s). For development, use `http://localhost:*`. | 30 minutes |
| 6 | **Authentication disabled by default** | All 145+ endpoints completely open. No access control whatsoever. | Enable JWT auth by default. Create a development mode that explicitly disables it. Add user registration/login flow. | 1-2 days |
| 7 | **No `requirements.txt`** | Cannot reproduce the environment. New developer setup is guesswork. Python 3.14 has breaking changes. | Generate `pip freeze > requirements.txt` and verify all dependencies are captured. | 1 hour |
| 8 | **Scorecard pre-loads 138K matches per request** | `_build_match_lookup()` loads entire osha_f7_matches table into memory on every scorecard API call. Slow and wasteful. | Cache the lookup dict in module scope with TTL, or move scoring to SQL/materialized view. | 4 hours |
| 9 | **4 broken corporate.py endpoints** | Reference nonexistent `corporate_ultimate_parents` table and `corporate_family_id` column. Return 500 errors. | Either create the missing table/column or remove the endpoints. | 1-2 hours |
| 10 | **Auth middleware leaks exception details** | `f"Invalid token: {exc}"` exposes internal error info to attackers. | Replace with generic "Authentication failed" message. Log the real error server-side. | 15 minutes |
| 11 | **Rate limiter memory leak** | `_requests` dict never prunes empty IP entries. Memory grows unbounded. | Add periodic cleanup of IPs with no recent requests (e.g., clear entries with empty or old-only timestamps). | 30 minutes |
| 12 | **Silent API error handling in frontend** | 40+ try-catch blocks swallow errors. Users see blank sections with no explanation. | Add user-visible error messages: "Failed to load OSHA data. Click to retry." | 1 day |

### MEDIUM — Plan for Next Development Cycle (Next Month)

| # | Finding | Impact | Fix | Effort |
|---|---------|--------|-----|--------|
| 13 | **No geocoding — map is effectively empty** | Territory mode map can't pinpoint establishments without lat/lon. Shows state-level zoom only. Defeats the purpose of geographic intelligence. | Add geocoding via Census Bureau Geocoder API (free, no API key needed) for OSHA establishments. Store lat/lon in the database. | 2-3 days |
| 14 | **10,506-line monolithic frontend** | Unmaintainable. Any change risks breaking unrelated features. No component reuse. | Migrate to a component framework (React or Vue). Start with the three mode containers as separate components. | 2-3 weeks |
| 15 | **No test isolation** | Tests run against production database with autocommit. Writes would permanently modify data. | Add transaction-wrapped test fixtures or a separate test database. | 4 hours |
| 16 | **No matching pipeline tests** | The platform's core value (entity matching) has zero automated tests. Regressions are invisible. | Write tests with known-answer test cases for each matching tier. | 1-2 days |
| 17 | **No scoring engine unit tests** | 9-factor scorecard logic untested. Scoring bugs affect all organizing recommendations. | Unit test each `_score_*()` function in organizing.py with boundary cases. | 1 day |
| 18 | **No data freshness tracking** | No way to know when data was last updated. Stale OSHA data could mislead organizers. | Add `data_freshness` table: source_name, last_updated, record_count, notes. | 2 hours |
| 19 | **319 unused indexes (2.6 GB)** | Waste disk space, slow INSERT/UPDATE operations, bloat backups. | Audit and drop. Run `SELECT ... FROM pg_stat_user_indexes WHERE idx_scan = 0` and verify each before dropping. | 2-4 hours |
| 20 | **F7 public-sector blind spot undocumented in UI** | 5.4M+ union members (NEA, AFT, postal, etc.) are invisible to the platform. Organizers may not realize this. | Add a prominent note in the UI: "This platform primarily covers private-sector employers. Public-sector union data has limited coverage." | 1 hour |
| 21 | **`LIMIT 500` pre-filter before scoring** | Scorecard returns the top 500 from the base query, not the top 500 by composite score. High-scoring employers outside the initial 500 are missed. | Score all candidates in the geographic scope, then rank by composite score, then paginate. | 4 hours |
| 22 | **No setup documentation** | New developers have no guide for setting up the project from scratch. | Write SETUP.md covering Python, PostgreSQL, dependencies, database creation, data loading, API startup. | 3 hours |

### LOW — When Time Allows

| # | Finding | Impact | Fix | Effort |
|---|---------|--------|-----|--------|
| 23 | **Zero accessibility (WCAG)** | Screen reader users, keyboard-only users cannot use the platform. May be legally required for union organizations receiving federal funds. | Add ARIA labels, keyboard navigation, focus management, color contrast. | 1-2 weeks |
| 24 | **Not mobile responsive** | Organizers in the field on phones/tablets can't use the tool. | Add viewport meta tag, responsive CSS with media queries, touch-friendly controls. | 1-2 weeks |
| 25 | **GLEIF data is 10.6 GB for 605 matches** | 53% of database for minimal value. | Archive to a separate schema or export and drop. Can always reimport if needed. | 1 hour |
| 26 | **CDN dependencies without fallback** | Chart.js and Leaflet loaded from CDN. If CDN is down, app breaks. | Bundle locally as fallback. Use `<script>` with CDN then local fallback pattern. | 2 hours |
| 27 | **No CI/CD pipeline** | Tests run manually. No automated gating on code changes. | Set up GitHub Actions with `pytest` on push/PR. | 2 hours |
| 28 | **No data refresh documentation** | When OSHA/BLS/NLRB publish new data, there's no procedure for updating. | Write DATA_REFRESH.md with step-by-step instructions per data source. | 4 hours |
| 29 | **Race conditions on rapid mode switching** | Clicking between Territory/Search/Deep Dive before API calls complete corrupts UI state. | Add request cancellation (AbortController) and loading locks per mode. | 4 hours |
| 30 | **No API versioning** | Breaking changes affect all consumers simultaneously. | Add `/api/v1/` prefix. Route current endpoints through it. | 2 hours |
| 31 | **Dockerization** | Can't deploy to any server without manual setup. | Create Dockerfile + docker-compose.yml (API + PostgreSQL + nginx). | 1 day |
| 32 | **Temporal scoring decay** | OSHA violations from 2010 score same as 2025. Stale violations mislead organizers. | Add time-weighted decay (e.g., violations lose 20% per year older than 3 years). | 2 hours |

---

## Making This Usable for Unions

### What Unions Need

Union organizers operate in a high-pressure, relationship-driven environment. They need:

1. **"Where should I go next?" intelligence.** The most common question is: "I have limited organizers and limited time. Which employers in my territory are the best use of our resources?" The scorecard addresses this, but only if it's trustworthy and well-calibrated.

2. **Employer background research.** Before approaching workers, organizers need to know: Does this employer have safety violations? Have workers tried to organize here before? What happened? Are they a government contractor (leverage point)? What are they paying? The deep dive profile partially delivers this.

3. **Geographic clustering.** Organizers work in territories. They need to see employers on a map, identify clusters, and plan routing. The territory mode exists but the map is effectively empty without geocoding.

4. **Competitive intelligence.** Which unions are already organizing in this area? What's their success rate? Are there employers where workers recently signed cards? NLRB election data provides some of this.

5. **Campaign tracking.** Once organizing begins, organizers need to track: contacts made, authorization cards signed, committee members identified, employer response (captive audience meetings, firings, ULPs filed). This is the workflow gap — the platform is purely research, not campaign management.

6. **Historical context.** "This employer defeated an organizing drive 3 years ago. What went wrong? How many votes did we lose by? Has the workforce turned over since then?" The NLRB election data provides partial answers.

7. **Legal context.** Unfair Labor Practice (ULP) filings are a critical organizing tool. Employers with pending ULPs may face pressure to settle, and ULP patterns indicate hostile employers where organizers need to be prepared for resistance.

### What's Missing

**Information Gaps:**
- **ULP (Unfair Labor Practice) data** — This is the #1 missing dataset. ULPs are filed when employers retaliate against organizing, and they're crucial for both identifying hostile employers and building legal cases. NLRB publishes this data but it's not yet integrated.
- **Geocoded locations** — Without lat/lon on OSHA establishments, the map feature is nearly useless. The Census Bureau Geocoder API is free and could geocode the 1M+ establishments.
- **Wage data** — BLS Quarterly Census of Employment and Wages (QCEW) data by area and industry could show where workers are underpaid relative to their region.
- **Real-time NLRB petitions** — Current petitions (not just completed elections) would show where organizing is actively happening right now.
- **Employer ownership chains** — Who owns this employer? What other facilities do they operate? SEC Exhibit 21 data (parent/subsidiary mapping) would enable this.
- **Worker demographics** — Census/ACS data on workforce demographics by geography and industry would help target messaging.

**Workflow Gaps:**
- **No campaign management.** The platform stops at "here's a good target." It doesn't help with: contact lists, card tracking, committee building, election logistics, first contract negotiations.
- **No collaboration features.** Organizers can't share notes, tag employers, or assign leads to team members.
- **No alerts.** When a new OSHA inspection happens at a target employer, or a new NLRB petition is filed nearby, organizers should be notified automatically.
- **No export to organizing tools.** Unions use specific software (Action Network, EveryAction, custom CRMs) for campaign management. Data should export to those formats.

**Usability Gaps:**
- **Technical vocabulary in the UI.** Terms like "pg_trgm similarity," "match tier," "Gower distance" mean nothing to organizers. The UI needs plain-language labels.
- **No onboarding flow.** A first-time user sees the full dashboard immediately. There should be a guided tour or contextual help.
- **Score interpretation is unclear.** A score of "42 out of 100" doesn't tell an organizer what to do. The UI should say: "This employer has strong safety violation patterns and no union presence — workers here may be receptive to organizing" rather than showing a raw number.
- **Print/PDF reports need union branding.** Reports shared with union leadership need to look professional, not like a database dump.

**Trust Gaps:**
- **Data dates aren't shown.** Organizers need to know: "Is this OSHA data from last month or 2020?" Every data point should show its source date.
- **Match confidence isn't visible.** When the platform links an OSHA establishment to a union employer, the organizer should see "high confidence match" vs. "possible match — verify manually."
- **No audit trail.** If a match or score changes, there's no record of what it was before.

**Access Gaps:**
- **Single-user local prototype.** Multiple organizers can't access this simultaneously from different locations.
- **No mobile access.** Field organizers are on phones, not desktops.
- **No offline capability.** Organizers in rural areas or employer parking lots may not have internet.

### Must-Have vs Nice-to-Have

**Must-have for launch (makes this a "we need this" tool):**
1. **Fix the orphaned relations** — the platform is working at 50% capacity.
2. **Geocoded map** — organizers think geographically. A map with pinned establishments is worth more than any table.
3. **ULP data integration** — this is the single most valuable missing dataset for organizing.
4. **Plain-language score explanations** — not just "42/100" but "This employer has X violations, is in a Y-density industry, and similar employers have been organized successfully."
5. **Data freshness indicators** — every data point shows its source date.
6. **Authentication and multi-user support** — organizers need individual logins and shared access.
7. **Mobile-responsive design** — field organizers are on phones.

**Nice-to-have (makes this polished but not essential for launch):**
1. Campaign tracking workflow
2. Automated alerts on NLRB/OSHA activity
3. Export to union CRM tools
4. Employer ownership chain visualization
5. Historical score trending
6. Collaboration features (notes, tags, assignments)
7. Offline capability
8. Accessibility compliance
9. Predictive modeling (which unorganized employers are most likely to see organizing activity)
10. Integration with BLS wage data for pay analysis

### Path to Adoption

**Minimum Viable Product (MVP) for Union Pilot:**
1. Fix orphaned relations (data integrity).
2. Add geocoding for map functionality.
3. Enable auth with simple username/password login.
4. Restrict CORS and deploy behind HTTPS.
5. Add plain-language score interpretations.
6. Deploy to a cloud server (DigitalOcean, AWS, or Heroku).
7. Provide a 1-page "Quick Start Guide" for organizers.

This MVP could be ready in **2-3 weeks** of focused development.

**Training and Onboarding:**
- A 30-minute video walkthrough of the three modes (Territory, Search, Deep Dive) would cover 90% of use cases.
- Embed contextual help tooltips (? icons) next to technical terms.
- Create 3-5 "How to use this for..." guides: "How to evaluate an employer," "How to compare employers in a metro area," "How to research a specific company."
- Assign a technical liaison within the union who can answer questions and report bugs.

**Data Freshness and Updates:**
- Establish a quarterly data refresh schedule aligned with government publication dates (OSHA publishes weekly, BLS publishes quarterly, NLRB is ongoing).
- Document the refresh procedure in DATA_REFRESH.md.
- Add automated freshness alerts: if data hasn't been refreshed in 90 days, show a warning banner.
- Long-term: automate the ETL pipeline with scheduled jobs (cron or Airflow).

**Privacy and Security Concerns:**
- Unions may worry that employer-side access to this tool could reveal organizing strategies. Restrict access to authorized union staff only.
- Some unions may not want their organizing research visible to other unions. Consider per-union data isolation or view restrictions.
- OSHA and NLRB data is public, but the aggregated intelligence is more sensitive than any single source. Treat the platform as confidential.
- Comply with any state-level data protection requirements.

**How This Compares to Current Tools:**
- Most unions currently use **manual research** — Googling employers, checking OSHA's public website, reading NLRB decision PDFs, asking colleagues. This platform automates and integrates what is currently a multi-hour manual process.
- **LaborStrong** and **UnionTrack** focus on membership management, not organizing intelligence. This fills a different niche.
- **The AFL-CIO Strategic Organizing Center** has internal tools, but they're not available to individual unions. This could serve independent unions or smaller federations.
- The closest comparable is the **MIT Living Wage Calculator** for wage data or **OSHA's own website** for safety data — but neither combines sources or provides organizing-specific scoring.

---

## Top 10 Actions (If You Could Only Do 10 Things)

1. **Fix the 60,373 orphaned f7_union_employer_relations rows.** This single fix immediately doubles the effective coverage of union-employer links across the platform. Every query, every score, every search result improves. (4-6 hours)

2. **Add geocoding to OSHA establishments.** Use the Census Bureau Geocoder API to add lat/lon to the 1M+ OSHA establishments. This makes the territory map functional and gives organizers the geographic intelligence they need. (2-3 days)

3. **Rotate the database password and remove from code.** The password `Juniordog33!` is in committed code. Rotate it, scrub git history, and verify all scripts use `db_config.py`. (2 hours)

4. **Enable authentication and restrict CORS.** Add user login, restrict API access to authenticated users, and lock down CORS to the frontend domain. This is the minimum for any multi-user deployment. (1-2 days)

5. **Add ULP (Unfair Labor Practice) data.** Scrape or download NLRB ULP filings and integrate into the platform. This is the single most valuable missing dataset for union organizers — it shows employer hostility and legal vulnerability. (3-5 days)

6. **Add plain-language score interpretations.** Replace raw "42/100" scores with explanatory text: "Strong organizing potential: high safety violation rate, growing industry, comparable employers have been organized successfully." (1-2 days)

7. **Add data freshness tracking and display.** Create a `data_freshness` table and show source dates in the UI. Organizers need to trust the data to act on it. (1 day)

8. **Cache scorecard results.** Move scoring to a nightly batch job that writes to a `scorecard_cache` table. Eliminates the per-request 138K-row pre-fetch and enables historical score tracking. (4-8 hours)

9. **Write a requirements.txt and SETUP.md.** Without these, no one else can run the platform. This is the minimum for the project to survive beyond its original developer. (2-3 hours)

10. **Make the frontend mobile-responsive.** Union organizers work in the field. If they can't pull up an employer profile on their phone in a parking lot before walking in to talk to workers, the tool isn't useful where it matters most. (1-2 weeks)

---

*Audit conducted by Claude Code (Opus 4.6) on 2026-02-14. Based on direct code review, database queries, and independent analysis of the complete codebase. No previous audit reports were consulted.*
