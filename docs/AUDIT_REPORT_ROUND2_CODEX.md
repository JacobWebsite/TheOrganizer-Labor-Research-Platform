# AUDIT_REPORT_ROUND2_CODEX

Audit date: February 15, 2026
Auditor: CODEX
Database: `olms_multiyear` on localhost
Method: Live SQL against production-local database using credentials from `.env`; direct source inspection for code/files.

## SECTION 1: Database Inventory (What's Actually In There?)

### Inventory Summary

| Category | Table Count | Total Rows | Total Size |
|----------|-------------|------------|------------|
| Core (unions, employers, relations) | 22 | 1,918,898 | 440.86 MB |
| NLRB (elections, cases, participants) | 16 | 5,864,438 | 1.21 GB |
| OSHA (establishments, violations) | 9 | 4,473,178 | 1.30 GB |
| Corporate (GLEIF, SEC, crosswalk) | 28 | 54,506,731 | 13.58 GB |
| Geographic (QCEW, BLS, density) | 30 | 2,193,046 | 408.38 MB |
| Matching (splink, fuzzy matches) | 14 | 1,235,800 | 424.11 MB |
| Other/Unknown | 50 | 6,467,448 | 2.45 GB |
| **TOTAL** | **169** | **76,659,539** | **19.81 GB (table storage); database reports 20 GB total** |

Notes:
- Category assignment is by table-name heuristics for this section.
- Counts are exact `COUNT(*)` values for all base tables (no planner estimates).

### Relation Totals
- Base tables: 169
- Views: 186
- Materialized views: 4
- Database size: 20 GB

### Top 20 Tables by Size

| Table | Rows | Size |
|------|------:|------:|
| `gleif.entity_statement` | 5,667,010 | 2443 MB |
| `gleif.ooc_statement` | 5,758,526 | 2374 MB |
| `gleif.ooc_annotations` | 10,783,856 | 2224 MB |
| `gleif.entity_annotations` | 5,667,010 | 1216 MB |
| `gleif.person_statement` | 2,826,102 | 1097 MB |
| `gleif.entity_addresses` | 6,706,686 | 912 MB |
| `gleif.entity_identifiers` | 6,706,686 | 833 MB |
| `public.sam_entities` | 826,042 | 826 MB |
| `gleif.ooc_interests` | 5,748,906 | 818 MB |
| `gleif.person_annotations` | 2,826,102 | 643 MB |
| `public.osha_establishments` | 1,007,217 | 641 MB |
| `public.nlrb_participants` | 1,906,542 | 574 MB |
| `public.mergent_employers` | 56,426 | 552 MB |
| `public.osha_violations_detail` | 2,245,020 | 431 MB |
| `public.whd_cases` | 363,365 | 427 MB |
| `public.ar_disbursements_emp_off` | 2,813,248 | 386 MB |
| `public.qcew_annual` | 1,943,426 | 348 MB |
| `public.epi_union_membership` | 1,420,064 | 312 MB |
| `public.national_990_filers` | 586,767 | 312 MB |
| `public.gleif_us_entities` | 379,192 | 310 MB |

### Empty Tables

| Table | Size |
|------|------|
| `public.platform_users` | 40 kB |

### Suspicious/Experimental Tables (name-pattern scan)
No base tables matched the configured suspicious prefixes (`temp_`, `test_`, `backup_`, `old_`, `tmp_`, `staging_`, `scratch_`).

### Evidence (Section 1)
- Script run: `python` inline script saved output to `docs/audit_artifacts_round2/section1_inventory.json`
- Core queries executed:
  - `SELECT ... FROM information_schema.tables WHERE table_type = 'BASE TABLE' ...`
  - `SELECT count(*) FROM schema.table` (executed per base table)
  - `SELECT pg_total_relation_size('schema.table'::regclass)`
  - `SELECT pg_database_size(current_database())`
  - `SELECT ... FROM pg_matviews`

### [?? HIGH] Storage Concentration in GLEIF Tables

**What's wrong:** A small set of GLEIF tables dominates storage footprint (multi-GB each), significantly outweighing core organizing tables.
**Evidence:** Top table sizes show 7 of top 10 are `gleif.*` and total Corporate category size is 13.58 GB.
**Impact:** Infrastructure cost and maintenance burden are high relative to directly organizer-facing datasets; backups/restores and vacuum/analyze windows are longer.
**Suggested fix:** Partition/archive low-value GLEIF sub-tables and keep only columns/rows used by active matching workflows (4-12 hours analysis + migration).
**Verified by:** `docs/audit_artifacts_round2/section1_inventory.json`

### [?? MEDIUM] Empty Auth Table Indicates Inactive User Layer

**What's wrong:** `public.platform_users` exists but has zero rows.
**Evidence:** Exact row count was 0 from `SELECT count(*) FROM public.platform_users`.
**Impact:** If auth is expected in production, there are no active user records; this can indicate disabled or untested login path.
**Suggested fix:** Verify intended auth mode; if enabled, bootstrap at least one admin user and test login flow end-to-end (30-60 minutes).
**Verified by:** `docs/audit_artifacts_round2/section1_inventory.json`
## SECTION 2: Data Quality (Is the Data Actually Good?)

Schema note for reproducibility:
- Prompt-specified columns were checked first; where absent, I used direct schema equivalents:
  - `f7_employers_deduped.lat/lon` mapped to `latitude/longitude`
  - `osha_establishments.city/state` mapped to `site_city/site_state`
- In `nlrb_elections`, columns `employer_name`, `city`, `state`, `votes_for`, `votes_against` do not exist in this table.

### Completeness: `public.f7_employers_deduped` (113,713 rows)

| Column Checked | Actual Column Used | Filled | Null | Empty String | % Filled |
|---|---|---:|---:|---:|---:|
| employer_name | employer_name | 113,713 | 0 | 0 | 100.00% |
| city | city | 111,267 | 2,446 | 0 | 97.85% |
| state | state | 110,961 | 2,752 | 0 | 97.58% |
| naics | naics | 107,414 | 6,299 | 0 | 94.46% |
| lat | latitude | 99,546 | 14,167 | 0 | 87.54% |
| lon | longitude | 99,546 | 14,167 | 0 | 87.54% |
| latest_unit_size | latest_unit_size | 113,713 | 0 | 0 | 100.00% |

### Completeness: `public.unions_master` (26,665 rows)

| Column Checked | Actual Column Used | Filled | Null | Empty String | % Filled |
|---|---|---:|---:|---:|---:|
| union_name | union_name | 26,665 | 0 | 0 | 100.00% |
| aff_abbr | aff_abbr | 26,665 | 0 | 0 | 100.00% |
| members | members | 24,921 | 1,744 | 0 | 93.46% |
| city | city | 26,665 | 0 | 0 | 100.00% |
| state | state | 26,665 | 0 | 0 | 100.00% |

### Completeness: `public.osha_establishments` (1,007,217 rows)

| Column Checked | Actual Column Used | Filled | Null | Empty String | % Filled |
|---|---|---:|---:|---:|---:|
| estab_name | estab_name | 1,007,217 | 0 | 0 | 100.00% |
| city | site_city | 1,005,283 | 0 | 1,934 | 99.81% |
| state | site_state | 1,007,082 | 0 | 135 | 99.99% |
| sic_code | sic_code | 233,442 | 773,775 | 0 | 23.18% |
| naics_code | naics_code | 1,005,361 | 1,856 | 0 | 99.82% |

### Completeness: `public.nlrb_elections` (33,096 rows)

| Column Checked | Actual Column Used | Filled | Null | Empty String | % Filled |
|---|---|---:|---:|---:|---:|
| eligible_voters | eligible_voters | 32,940 | 156 | 0 | 99.53% |
| union_won | union_won | 32,793 | 303 | 0 | 99.08% |

Missing from this table: `employer_name`, `city`, `state`, `votes_for`, `votes_against`.

### Completeness: `public.mergent_employers` (56,426 rows)

| Column Checked | Actual Column Used | Filled | Null | Empty String | % Filled |
|---|---|---:|---:|---:|---:|
| company_name | company_name | 56,426 | 0 | 0 | 100.00% |
| duns | duns | 56,426 | 0 | 0 | 100.00% |
| ein | ein | 24,799 | 31,627 | 0 | 43.95% |
| employees_site | employees_site | 56,426 | 0 | 0 | 100.00% |
| naics_primary | naics_primary | 54,889 | 1,537 | 0 | 97.28% |

### Duplicate Checks

| Duplicate Definition | Duplicate Groups | Rows in Duplicate Groups | Duplicate Rows Beyond First |
|---|---:|---:|---:|
| `f7_employers_deduped` by `(employer_name, state)` | 1,840 | 3,872 | 2,032 |
| `osha_establishments` by `(estab_name, site_city, site_state)` | 56,149 | 139,634 | 83,485 |
| `nlrb_elections` by `(case_number)` | 1,604 | 3,415 | 1,811 |

### Relationship Integrity (Orphan Checks)

| Relationship Checked | Mapping Used | Orphaned Rows | Total Referencing Rows | Orphan % |
|---|---|---:|---:|---:|
| `f7_union_employer_relations.employer_id -> f7_employers_deduped.employer_id` | direct | 0 | 119,445 | 0.00% |
| `f7_union_employer_relations.f_num -> unions_master.f_num` | `union_file_number -> f_num` | 824 | 119,445 | 0.69% |
| `nlrb_participants.case_number -> nlrb_elections.case_number` | direct | 1,760,408 | 1,906,542 | 92.34% |
| `osha_f7_matches.employer_id -> f7_employers_deduped.employer_id` | `f7_employer_id -> employer_id` | 0 | 138,340 | 0.00% |
| `osha_f7_matches.establishment_id -> osha_establishments.establishment_id` | direct | 0 | 138,340 | 0.00% |

### [?? CRITICAL] NLRB Participant Records Are Largely Unlinked to Election Records

**What's wrong:** Most `nlrb_participants` rows reference `case_number` values that do not exist in `nlrb_elections`.
**Evidence:** Orphan query found 1,760,408 orphaned rows out of 1,906,542 references (92.34%).
**Impact:** Organizer workflows relying on participant details linked to election outcomes will silently miss data, causing incomplete campaign intelligence.
**Suggested fix:** Normalize `case_number` formats across both tables (trim, uppercase, standard delimiters) and rebuild linkage keys; add referential checks in ingestion (6-12 hours for remediation + backfill).
**Verified by:** `docs/audit_artifacts_round2/section2_data_quality.json`

### [?? HIGH] NLRB Elections Table Missing Core Employer/Location Fields Required by Audit Spec

**What's wrong:** `public.nlrb_elections` does not contain `employer_name`, `city`, `state`, `votes_for`, or `votes_against` columns.
**Evidence:** Schema inspection via `information_schema.columns` returned only 13 columns, none of the five fields above.
**Impact:** Frontend/API paths expecting election-level employer geography or direct for/against vote columns cannot source them from this table, increasing risk of broken joins or misleading summaries.
**Suggested fix:** Document canonical source table(s) for those fields and expose a unified election view with stable columns consumed by API/frontend (3-6 hours).
**Verified by:** `docs/audit_artifacts_round2/section2_data_quality.json`

### [?? MEDIUM] Significant Duplicate Keys in OSHA and F7 Name+Location Groupings

**What's wrong:** There are substantial duplicate groups for key name/location combinations in both OSHA establishments and F7 employers.
**Evidence:** `osha_establishments` has 56,149 duplicate `(estab_name, site_city, site_state)` groups; `f7_employers_deduped` has 1,840 duplicate `(employer_name, state)` groups.
**Impact:** Search and matching can overcount establishments/employers or produce ambiguous results where one entity appears multiple times.
**Suggested fix:** Add deterministic dedupe keys (source ID + normalized name + geography window), and expose de-duplicated search views for consumer endpoints (4-8 hours).
**Verified by:** `docs/audit_artifacts_round2/section2_data_quality.json`

### Evidence (Section 2)
- Artifact file: `docs/audit_artifacts_round2/section2_data_quality.json`
- Representative executed queries:
  - `SELECT count(*) FILTER (WHERE col IS NULL) ...`
  - `SELECT ... GROUP BY ... HAVING count(*) > 1`
  - `LEFT JOIN` orphan checks with explicit `::text` normalization for mapped key types
## SECTION 3: Cross-Database Matching (Does the Linking Actually Work?)

### Match Rate Summary

| Connection | Matched | Total | Match Rate |
|-----------|---------:|------:|-----------:|
| F7 employers ? OSHA | 28,848 | 113,713 | 25.37% |
| F7 employers ? NLRB | 5,548 | 113,713 | 4.88% |
| F7 employers ? Crosswalk | 17,280 | 113,713 | 15.20% |
| NLRB elections ? Known union | 29,577 | 33,096 | 89.37% |
| Public sector locals ? unions_master | 1,179 | 1,520 | 77.57% |

### Detailed Results

1. F7 employer ? OSHA (`public.osha_f7_matches`)
- Distinct matched F7 employers: 28,848 / 113,713 (25.37%)
- Average `match_confidence`: 0.6850
- Matched OSHA establishments: 138,340 / 1,007,217 (13.73%)
- Unmatched OSHA establishments: 868,877

2. F7 employer ? NLRB
- Direct `employer_id` is not present in `public.nlrb_elections`.
- Proxy linkage used: `public.nlrb_participants.matched_employer_id` bridged by `case_number`.
- Distinct F7 employers linked via bridge: 5,548 / 113,713 (4.88%)
- Distinct NLRB elections linked back to known F7 employer: 10,679 / 33,096 (32.27%)

3. Corporate identifier crosswalk (`public.corporate_identifier_crosswalk`)
- F7 employers present in crosswalk: 17,280 / 113,713 (15.20%)
- Identifier coverage within crosswalked employers:
  - GLEIF identifier: 1,913
  - Mergent DUNS: 1,045
  - SEC CIK: 650
  - EIN: 7,720
- Employers with >1 external identifier: 1,400 (8.10% of crosswalked employers)

4. Public sector coverage
- Public sector locals linked to `unions_master`:
  - Mapping used: `ps_union_locals.f_num -> unions_master.f_num`
  - 1,179 / 1,520 locals linked (77.57%)
- Public sector employers with bargaining unit data:
  - Mapping used: `ps_bargaining_units.employer_id -> ps_employers.id`
  - 420 / 7,987 employers (5.26%)

5. Unified employer view
- View used: `public.v_employer_search` (schema has this view, not `mv_employer_search` for this check)
- Total employers in unified view: 113,740
- With coordinates: 99,571 (87.54%)
- With NAICS: 107,440 (94.46%)
- No explicit source column found in this view among typical names (`source`, `data_source`, etc.), so per-source mix could not be directly enumerated from this view.

### [?? HIGH] NLRB Employer Linkage to F7 Is Very Low

**What's wrong:** Only 4.88% of F7 employers can be linked to NLRB via available bridge keys.
**Evidence:** 5,548 distinct `matched_employer_id` values out of 113,713 F7 employers.
**Impact:** Organizers researching employer election history will often see no NLRB context even when activity may exist under alternate naming/keys.
**Suggested fix:** Add deterministic election-employer bridge table keyed by normalized employer identity and geography, then promote it to API-level join path (1-2 days).
**Verified by:** `docs/audit_artifacts_round2/section3_matching.json`

### [?? HIGH] OSHA Establishment Coverage Remains Limited

**What's wrong:** Only 13.73% of OSHA establishments are linked to F7 employers.
**Evidence:** 138,340 matched establishments out of 1,007,217 total; 868,877 unmatched.
**Impact:** Safety-risk intelligence is fragmented for most establishments, reducing confidence in organizing target prioritization.
**Suggested fix:** Expand multi-pass matching (EIN + address-normalized + parent rollup), and queue low-confidence buckets for review (1-3 days incremental pipeline work).
**Verified by:** `docs/audit_artifacts_round2/section3_matching.json`

### [?? MEDIUM] Crosswalk Coverage Is Sparse and Multi-ID Depth Is Low

**What's wrong:** Only 15.20% of F7 employers are in the corporate crosswalk, and only 8.10% of crosswalked employers have more than one external identifier.
**Evidence:** 17,280/113,713 crosswalked; 1,400 with >1 identifier.
**Impact:** Corporate-family and external-data enrichment will frequently be unavailable or shallow for organizer research.
**Suggested fix:** Prioritize EIN+DUNS enrichment for high-value F7 employers and enforce identifier normalization at ingest (1 day for targeted batch + QC).
**Verified by:** `docs/audit_artifacts_round2/section3_matching.json`

### Evidence (Section 3)
- Artifact file: `docs/audit_artifacts_round2/section3_matching.json`
- Representative executed queries:
  - `SELECT count(DISTINCT f7_employer_id) FROM public.osha_f7_matches`
  - `SELECT avg(match_confidence) FROM public.osha_f7_matches`
  - `SELECT count(DISTINCT matched_employer_id) FROM public.nlrb_participants`
  - `SELECT count(DISTINCT case_number) FROM public.nlrb_participants WHERE matched_olms_fnum IS NOT NULL`
  - `SELECT count(DISTINCT employer_id) FROM public.corporate_identifier_crosswalk`
  - `SELECT count(*) FROM public.ps_union_locals l JOIN public.unions_master u ON l.f_num::text = u.f_num::text`
## SECTION 4: API & Endpoint Audit (Does the Website Backend Work?)

Scope note:
- Prompt references `api/labor_api_v6.py`, but this repo’s active API is modular FastAPI (`api/main.py` + `api/routers/*.py`).
- Audit performed against the active app (`api.main:app`).

### Endpoint Inventory

- Total registered API/frontend endpoints: **152** routes.
- Full inventory table (every endpoint with method, router module/function, description, routed tables):
  - `docs/audit_artifacts_round2/section4_endpoint_inventory.csv`
- Structured route metadata and SQL scan:
  - `docs/audit_artifacts_round2/section4_api_inventory_refined.json`

Sample inventory rows (full list is in CSV above):

| Method | Path | Router | Description |
|---|---|---|---|
| GET | `/api/health` | `api.routers.health` | Health check |
| GET | `/api/employers/search` | `api.routers.employers` | Search employers |
| GET | `/api/unions/search` | `api.routers.unions` | Search unions |
| GET | `/api/nlrb/elections/search` | `api.routers.nlrb` | Search NLRB elections with filters |
| GET | `/api/osha/establishments/search` | `api.routers.osha` | Search OSHA establishments |
| GET | `/api/organizing/scorecard` | `api.routers.organizing` | Organizing scorecard |
| GET | `/api/corporate/family/{employer_id}` | `api.routers.corporate` | Corporate family tree |
| POST | `/api/auth/login` | `api.routers.auth` | JWT login |

### Endpoint Smoke Tests

Executed using `fastapi.testclient.TestClient` against local app with real DB connection.

- Smoke-tested endpoints: 46
- Passed: 41
- Failed: 5
- Artifact: `docs/audit_artifacts_round2/section4_endpoint_smoketest.json`

Failed routes:
- `GET /api/density/by-govt-level` ? 500
- `GET /api/density/by-county` ? 500
- `GET /api/density/county-summary` ? 500
- `GET /api/auth/me` ? 400 (expected when auth disabled; not treated as runtime bug)
- `GET /api/employers/unified/sources` ? 422 (validation error due missing required query params; not treated as runtime bug)

### Security / Safety Review

- Auth middleware is present but fail-open when `LABOR_JWT_SECRET` is unset (`api/middleware/auth.py`, `api/main.py`).
- Current run logs confirm `LABOR_JWT_SECRET` is not set, so non-public endpoints are effectively open.
- CORS is **not** wide-open in default config: explicit localhost origins only (`api/config.py`).
- SQL query construction uses many `execute(f"...")` calls, but the reviewed dynamic parts are mostly controlled (`where_clause` from hardcoded conditions + parameterized values, validated sort/view whitelists).

### Count Summary (Required)

| Metric | Count |
|---|---:|
| Total endpoints | 152 |
| Confirmed working (smoke-tested 2xx) | 41 |
| Probably broken (500 in smoke tests) | 3 |
| Security risks identified | 1 high-risk active config issue |

### [?? CRITICAL] Multiple Density Endpoints Crash at Runtime Due to Cursor Type Mismatch

**What's wrong:** Endpoints in `density.py` index DB rows like tuples (`row[0]`) even though the DB layer uses `RealDictCursor` (dict-style rows). This causes runtime exceptions and HTTP 500s.
**Evidence:**
- `GET /api/density/by-govt-level` returned 500 with `KeyError: 0` during smoke test.
- Code uses tuple indexing at `api/routers/density.py:212` and also in other endpoints (`api/routers/density.py:363`, `api/routers/density.py:593`).
**Impact:** Organizers cannot use key density dashboards/reports; this breaks decision support for geography-based targeting.
**Suggested fix:** Replace positional indexing with named keys (e.g., `stats['avg_federal']`, `total_row['count']`) consistently across density router; add regression tests for these endpoints (2-4 hours).
**Verified by:** `docs/audit_artifacts_round2/section4_endpoint_smoketest.json`, `api/routers/density.py:212`, `api/routers/density.py:363`, `api/routers/density.py:593`, `api/database.py`

### [?? CRITICAL] Authentication Is Disabled in Current Runtime Configuration

**What's wrong:** JWT auth middleware is configured to no-op when `LABOR_JWT_SECRET` is empty; current environment has it unset.
**Evidence:** Startup warning emitted: "authentication is DISABLED. All API endpoints are publicly accessible."; logic in `api/middleware/auth.py` returns early when secret missing.
**Impact:** Any user on an allowed origin can access sensitive research APIs without authentication.
**Suggested fix:** Set a 32+ char `LABOR_JWT_SECRET` in `.env`, enforce non-empty secret in non-dev startup, and add deployment guard failing boot when missing (30-60 minutes).
**Verified by:** `api/main.py`, `api/middleware/auth.py`, runtime logs during Section 4 tests

### [?? MEDIUM] Extensive Dynamic SQL via f-strings Increases Review Burden and Future Injection Risk

**What's wrong:** Many router queries use dynamic SQL strings (`execute(f"...")`), relying on manual safeguards per endpoint.
**Evidence:** Static scan found frequent f-string execute usage across routers (see `section4_api_inventory_refined.json` `sql_safety_scan`).
**Impact:** Current code appears mostly safe where inspected, but this pattern is brittle and can regress into injection vulnerabilities during future edits.
**Suggested fix:** Standardize helper utilities for safe WHERE/ORDER composition (`safe_sort_col`, strict view whitelists, psycopg SQL identifiers) and add lint checks for unsafe patterns (4-8 hours).
**Verified by:** `docs/audit_artifacts_round2/section4_api_inventory_refined.json`, `api/routers/sectors.py`, `api/helpers.py`

### Evidence (Section 4)
- Route extraction from `api.main:app` (FastAPI runtime routes)
- Smoke test artifact: `docs/audit_artifacts_round2/section4_endpoint_smoketest.json`
- Full endpoint inventory: `docs/audit_artifacts_round2/section4_endpoint_inventory.csv`
- Static SQL/config scan: `docs/audit_artifacts_round2/section4_api_inventory_refined.json`
## SECTION 5: Frontend Review (What Does the User Actually See?)

### Frontend File Inventory

Artifacts:
- `docs/audit_artifacts_round2/section5_frontend_summary.json`
- `docs/audit_artifacts_round2/section5_frontend_api_scan.json`

Core app inventory (HTML/JS/CSS used by main UI):

| File | Type | Lines |
|---|---|---:|
| `files/organizer_v5.html` | HTML | 2,098 |
| `files/css/organizer.css` | CSS | 204 |
| `files/js/config.js` | JS | 24 |
| `files/js/utils.js` | JS | 176 |
| `files/js/maps.js` | JS | 180 |
| `files/js/territory.js` | JS | 599 |
| `files/js/search.js` | JS | 892 |
| `files/js/deepdive.js` | JS | 334 |
| `files/js/detail.js` | JS | 1,229 |
| `files/js/scorecard.js` | JS | 774 |
| `files/js/modals.js` | JS | 2,378 |
| `files/js/app.js` | JS | 1,017 |
| **Core total** |  | **10,695** |

Additional frontend/support pages in `files/`:
- `files/api_map.html` (935 lines)
- `files/test_api.html` (51 lines)
- `files/afscme_scraper_data.html` (1,771 lines, data artifact page)

### API Connections From Frontend

- `fetch()` calls found: 78
- Unique `/api/...` path literals found in frontend sources: 144
- Unmatched frontend API paths against live OpenAPI route list: **0**

Result: no broken frontend?API path wiring was found in static endpoint mapping.

### Hardcoded Values / Deployment Risks

Hardcoded localhost values were found in auxiliary HTML tools:
- `files/test_api.html:10` uses `const API_BASE = 'http://localhost:8001/api';`
- `files/api_map.html:806`, `files/api_map.html:933`, `files/api_map.html:957` reference `http://localhost:8001` directly.

Main app configuration is deployment-aware:
- `files/js/config.js:3` sets `API_BASE = (window.LABOR_API_BASE || window.location.origin) + '/api'`

This supports both same-origin deployment and explicit override via `window.LABOR_API_BASE`.

### Environment Config Pattern

- No separate frontend env file/build-time env system detected (plain script tags, non-module JS).
- Runtime override mechanism exists (`window.LABOR_API_BASE`), which is adequate for static hosting if injected before app scripts.

### Usability / Accessibility Quick Findings

- `organizer_v5.html` contains many inline handlers (`onclick`/`onchange`): 68 total (59 `onclick`, 9 `onchange`). This is maintainability risk and can complicate keyboard/accessibility enhancements.
- Several controls are icon-heavy; while many have visible labels or titles, there is limited explicit ARIA labeling pattern in the markup.

### [?? MEDIUM] Auxiliary Frontend Tools Hardcode Localhost API URLs

**What's wrong:** `test_api.html` and `api_map.html` are pinned to `http://localhost:8001`.
**Evidence:** Literal URL references at `files/test_api.html:10`, `files/api_map.html:806`, `files/api_map.html:933`, `files/api_map.html:957`.
**Impact:** These tools fail outside local dev and may confuse organizers/devs validating deployment health.
**Suggested fix:** Reuse the same runtime base pattern as main app (`window.LABOR_API_BASE || window.location.origin`) in these files (15-30 minutes).
**Verified by:** `docs/audit_artifacts_round2/section5_frontend_api_scan.json`, `files/test_api.html`, `files/api_map.html`

### [? LOW] Frontend Interaction Layer Relies Heavily on Inline Event Attributes

**What's wrong:** The main HTML uses 68 inline event handlers.
**Evidence:** Static count from `files/organizer_v5.html` (`onclick=59`, `onchange=9`).
**Impact:** Harder to maintain/test and makes progressive accessibility improvements more error-prone.
**Suggested fix:** Gradually migrate to delegated JS event listeners in `app.js`/module files as touch points are edited (incremental, 1-2 hours per area).
**Verified by:** `files/organizer_v5.html`

### Evidence (Section 5)
- API path cross-check artifact: `docs/audit_artifacts_round2/section5_frontend_api_scan.json`
- File/line inventory artifact: `docs/audit_artifacts_round2/section5_frontend_summary.json`
- Main config check: `files/js/config.js:3`
## SECTION 6: Previous Audit Findings — Are They Fixed?

Evidence artifacts used:
- `docs/audit_artifacts_round2/section2_data_quality.json`
- `docs/audit_artifacts_round2/section3_matching.json`
- `docs/audit_artifacts_round2/section4_api_inventory_refined.json`
- `docs/audit_artifacts_round2/section6_db_checks.json`

### Round 1 Findings Status Table

| # | Round 1 Finding | Status | Evidence |
|---|---|---|---|
| 1 | Database password in code (`Juniordog33!`) | **FIXED** | Code scan across `*.py`/`*.sql` found no `Juniordog33!` literal. |
| 2 | Authentication disabled by default | **STILL BROKEN** | `api/middleware/auth.py` bypasses auth when `LABOR_JWT_SECRET` unset; runtime warning confirms auth disabled (`api/main.py`). |
| 3 | CORS wide open | **FIXED** | `api/config.py` defaults `ALLOWED_ORIGINS` to localhost allowlist (not `*`), and `api/main.py` uses that list. |
| 4 | ~50% orphaned `f7_union_employer_relations.employer_id` | **FIXED** | Current orphan check: `0` orphan employer refs (`section2_data_quality.json`, `section6_db_checks.json`). |
| 5 | Frontend 9,500+ lines in one file | **FIXED** | Frontend is split: `organizer_v5.html` + 10 JS + CSS (`section5_frontend_summary.json`). |
| 6 | OSHA match rate ~14% (low coverage) | **STILL BROKEN** | OSHA establishment coverage remains low: `13.73%` matched, `868,877` unmatched establishments (`section3_matching.json`). |
| 7 | WHD match rate ~2% | **STILL BROKEN** | Current Mergent WHD-linked coverage `2.47%` (`1,396 / 56,426`) in `section6_db_checks.json`; still near prior ~2%. |
| 8 | No tests for matching pipeline | **FIXED** | `tests/test_matching.py` exists and covers normalization/tier logic; additional matching references across tests. |
| 9 | README startup command wrong (nonexistent file) | **FIXED** | `README.md` now uses valid startup command: `py -m uvicorn api.main:app --reload --port 8001`. |
| 10 | 990 filer data unmatched | **STILL BROKEN** | `national_990_filers` has `586,767` rows, but `mergent_employers.matched_990_id` only `69` (`0.12%`); linkage remains minimal (`section6_db_checks.json`). |
| 11 | GLEIF 10+ GB for very few matches | **PARTIALLY FIXED** | GLEIF still ~`12 GB`, but LEI-linked employers improved to `1,913` (from prior 605 claim). Storage issue persists (`section6_db_checks.json`). |
| 12 | Silent `LIMIT 500` truncation | **PARTIALLY FIXED** | No hardcoded `LIMIT 500` literals found; many endpoints expose `limit` query + return `total/limit`. But some capped endpoints (e.g., lookups) still truncate without explicit truncation messaging (`api/routers/lookups.py`, router scans). |
| 13 | Two scoring systems not unified (0-100 vs 0-62) | **STILL BROKEN** | Frontend still contains dual score logic: sector `0-62` and OSHA `0-100` (`files/js/scorecard.js:315`, `files/js/scorecard.js:330`); docs also reflect mixed scales (`README.md`, `CLAUDE.md`). |
| 14 | 195 orphaned F7 union file numbers | **STILL BROKEN** | Current orphan union-file refs are `824` (`f7_union_employer_relations.union_file_number -> unions_master.f_num`) (`section2_data_quality.json`, `section6_db_checks.json`). |
| 15 | Stale `pg_stat` estimates / no recent ANALYZE | **STILL BROKEN** | `pg_stat_user_tables`: `170/173` tables have `last_analyze IS NULL`; `159/173` have no autoanalyze (`section6_db_checks.json`). |

### [?? CRITICAL] Auth Remains Fail-Open in Current Runtime

**What's wrong:** API auth is still disabled when `LABOR_JWT_SECRET` is absent, and current runtime is in that state.
**Evidence:** `AuthMiddleware` early-returns without checks when secret missing; startup warning logged in Section 4 and route scans.
**Impact:** Organizer-facing data APIs are publicly accessible without login in current configuration.
**Suggested fix:** Require non-empty `LABOR_JWT_SECRET` in production startup path and fail fast if missing (30-60 minutes).
**Verified by:** `api/middleware/auth.py`, `api/main.py`, `docs/audit_artifacts_round2/section4_endpoint_smoketest.json`

### [?? HIGH] Legacy Linkage Debt Persists (WHD, 990, OSHA Coverage)

**What's wrong:** Cross-source linkage for several high-value datasets remains low despite improvements elsewhere.
**Evidence:** OSHA establishment match `13.73%`; Mergent WHD-linked coverage `2.47%`; Mergent 990 matched `0.12%`.
**Impact:** Organizers still miss major enforcement and nonprofit context for many employers.
**Suggested fix:** Prioritize enrichment sprints for WHD/990 matching using EIN + normalized names + geo constraints, with explicit match-quality metrics in CI (1-2 weeks).
**Verified by:** `docs/audit_artifacts_round2/section3_matching.json`, `docs/audit_artifacts_round2/section6_db_checks.json`

### [?? MEDIUM] Data Integrity Improved on Employer Links but Union-File Orphans Worsened

**What's wrong:** Employer ID orphans in F7 relations are resolved, but union-file-number orphan count remains nontrivial and exceeds Round 1 count.
**Evidence:** employer orphan count `0`; union-file orphans `824`.
**Impact:** Union-relationship analytics can still under-link locals to canonical union profiles.
**Suggested fix:** Normalize/pad `union_file_number` formats and add referential QC checks in ingest jobs (4-8 hours).
**Verified by:** `docs/audit_artifacts_round2/section2_data_quality.json`, `docs/audit_artifacts_round2/section6_db_checks.json`
## SECTION 7: What Changed Since Round 1? (Delta Analysis)

Baseline used (Round 1, Feb 13, 2026):
- `docs/AUDIT_REPORT_2026.md` reports **159 tables, 187 views, 3 materialized views, 22 GB**.

Current (Round 2, Feb 15, 2026):
- **169 tables, 186 views, 4 materialized views, 20 GB** (`section1_inventory.json`).

### High-Level Delta

| Metric | Round 1 | Current | Delta |
|---|---:|---:|---:|
| Tables | 159 | 169 | +10 |
| Views | 187 | 186 | -1 |
| Materialized Views | 3 | 4 | +1 |
| Database Size | 22 GB | 20 GB | -2 GB |

### New/Added Objects (Confirmed)

- New materialized view present now: `public.mv_organizing_scorecard` (24,841 rows).
- New base tables present now: `public.platform_users`, `public.data_source_freshness`.
- Large GLEIF raw-table footprint now present in dedicated schema (`gleif.*`, 9 base tables totaling ~12 GB), including:
  - `gleif.entity_statement`, `gleif.ooc_statement`, `gleif.ooc_annotations`, `gleif.entity_annotations`, etc.

### Removed Objects Since Round 1 (Confirmed)

Round 1 listed 6 empty tables; all are now absent:
- `public.employer_ein_crosswalk`
- `public.sic_naics_xwalk`
- `public.union_affiliation_naics`
- `public.union_employer_history`
- `public.vr_employer_match_staging`
- `public.vr_union_match_staging`

Additionally, major archival/intermediate table no longer present:
- `public.splink_match_results` (was 1.6 GB in Round 1 report)

### Major Row-Count Changes (Round 1 ? Current)

| Table/View | Round 1 | Current | Change |
|---|---:|---:|---:|
| `f7_employers_deduped` | 60,953 | 113,713 | +52,760 (+86.6%) |
| `mergent_employers` | 108,691 | 56,426 | -52,265 (-48.1%) |
| `osha_violations_detail` | 1,950,011 | 2,245,020 | +295,009 (+15.1%) |
| `whd_cases` | 468,213 | 363,365 | -104,848 (-22.4%) |
| `mv_employer_search` | 118,015 | 170,775 | +52,760 (+44.7%) |
| `corporate_identifier_crosswalk` | 25,177 | 25,177 | 0 |
| `national_990_filers` | 586,767 | 586,767 | 0 |

### Recently Modified Files / Features Since Round 1

From git history since 2026-02-13:
- Sprint 6 frontend split and review fixes (`files/organizer_v5.html`, `files/js/*`, `files/css/organizer.css`, `api/routers/organizing.py`).
- Sprint 5 additions: ULP integration + data freshness tracking (`api/routers/organizing.py`, `scripts/maintenance/create_data_freshness.py`, `files/js/app.js`, `files/js/scorecard.js`).
- Sprints 1-4 remediation: auth, scorecard MV, orphan-fix scripts, and expanded tests (`api/middleware/auth.py`, `api/routers/auth.py`, `tests/test_auth.py`, `tests/test_matching.py`, `tests/test_scoring.py`).

### [?? MEDIUM] Significant Schema/Object Churn Since Round 1 Requires Documentation Refresh

**What's wrong:** Core object counts and major tables changed materially (new MV, dropped staging/legacy tables, large GLEIF schema footprint), but this level of change can outpace docs/onboarding references.
**Evidence:** Count deltas (+10 tables, -1 view, +1 matview), removal of Round 1 empty tables, addition of `mv_organizing_scorecard`, and major row-count shifts above.
**Impact:** Engineers and auditors may rely on outdated table availability/count assumptions, causing false alarms or missed regressions.
**Suggested fix:** Publish a dated schema delta changelog after each sprint (auto-generated from `information_schema` diff) and link it from `README.md` + `CLAUDE.md` (2-4 hours initial setup).
**Verified by:** `docs/AUDIT_REPORT_2026.md`, `docs/audit_artifacts_round2/section1_inventory.json`, git log since 2026-02-13

### Evidence (Section 7)
- Baseline report: `docs/AUDIT_REPORT_2026.md`
- Current inventory: `docs/audit_artifacts_round2/section1_inventory.json`
- Delta checks for specific tables/matviews executed live in Section 7 queries
- Code-change timeline: `git log --since="2026-02-13" --name-only`
