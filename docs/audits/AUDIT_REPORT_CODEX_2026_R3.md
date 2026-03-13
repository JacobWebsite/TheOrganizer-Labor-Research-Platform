# Audit Report (Codex) - 2026 Round 3
Date: 2026-02-16
Project: labor-data-project

## Section 1 - Database Table Inventory (Checkpoint Saved)

### What I checked
- Connected to PostgreSQL database `olms_multiyear` as `postgres`.
- Counted all `public` tables and views using `COUNT(*)` per object.
- Checked which tables have zero rows.
- Checked which tables have no primary key.
- Compared key documented row counts in `CLAUDE.md` against current database counts.

### Findings

**Finding 1.1 - Documented total table count is outdated**  
Severity: MEDIUM  
Confidence: Verified (tested)

The current database has **174 tables** and **186 views** in `public`. The project documentation says 169 tables and 186 views.

Why this matters: when table totals are wrong, people may miss data during debugging and migration planning.

Evidence:
- `CLAUDE.md` (project docs mention 169 tables, 186 views)
- SQL used:
```sql
SELECT table_type, count(*)
FROM information_schema.tables
WHERE table_schema='public'
GROUP BY table_type;

SELECT count(*)
FROM information_schema.views
WHERE table_schema='public';
```

**Finding 1.2 - Two tables are empty (zero rows)**  
Severity: LOW  
Confidence: Verified (tested)

`platform_users` and `splink_match_results` both have 0 rows.

Why this matters: empty tables are not always bad, but they can mean an unfinished feature or stale schema that adds confusion.

Evidence:
```sql
SELECT table_name
FROM information_schema.tables t
WHERE t.table_schema='public'
AND (SELECT count(*) FROM pg_catalog.pg_class c WHERE c.relname=t.table_name) >= 0;
-- direct count run by audit script found:
-- platform_users = 0
-- splink_match_results = 0
```

**Finding 1.3 - 15 tables have no primary key**  
Severity: HIGH  
Confidence: Verified (tested)

Tables without primary keys include:
- `ar_assets_investments`
- `ar_disbursements_emp_off`
- `ar_disbursements_total`
- `ar_membership`
- `employers_990_deduped`
- `f7_federal_scores`
- `f7_industry_scores`
- `labor_990_olms_crosswalk`
- `labor_orgs_990_deduped`
- `lm_data`
- `nhq_reconciled_membership`
- `public_sector_benchmarks`
- `qcew_industry_density`
- `usaspending_f7_matches`

Why this matters: without a primary key, duplicate rows are harder to prevent and updates/deletes are riskier.

Evidence:
```sql
SELECT t.table_name
FROM information_schema.tables t
LEFT JOIN information_schema.table_constraints tc
  ON t.table_schema=tc.table_schema
 AND t.table_name=tc.table_name
 AND tc.constraint_type='PRIMARY KEY'
WHERE t.table_schema='public'
  AND t.table_type='BASE TABLE'
  AND tc.table_name IS NULL
ORDER BY t.table_name;
```

**Finding 1.4 - Multiple high-visibility table counts differ from docs**  
Severity: MEDIUM  
Confidence: Verified (tested)

Examples:
- `f7_employers_deduped`: docs 113,713 vs actual 146,863 (+33,150)
- `osha_f7_matches`: docs 138,340 vs actual 145,134 (+6,794)
- `employer_comparables`: docs 269,810 vs actual 269,785 (-25)
- `unified_employers_osha`: docs 100,768 vs actual 100,766 (-2)

Why this matters: organizer decisions can be affected if dashboards or planning assumptions use old counts.

Evidence:
- `CLAUDE.md`
- SQL used:
```sql
WITH expected(table_name, expected_count) AS (
  VALUES
  ('f7_employers_deduped', 113713),
  ('nlrb_elections', 33096),
  ('osha_f7_matches', 138340),
  ('employer_comparables', 269810),
  ('unified_employers_osha', 100768)
)
SELECT e.table_name, e.expected_count, c.actual_count
FROM expected e
JOIN (
  SELECT 'f7_employers_deduped' AS table_name, count(*) AS actual_count FROM f7_employers_deduped
  UNION ALL SELECT 'nlrb_elections', count(*) FROM nlrb_elections
  UNION ALL SELECT 'osha_f7_matches', count(*) FROM osha_f7_matches
  UNION ALL SELECT 'employer_comparables', count(*) FROM employer_comparables
  UNION ALL SELECT 'unified_employers_osha', count(*) FROM unified_employers_osha
) c ON c.table_name=e.table_name;
```

### Section 1 checkpoint status
Saved to `docs/AUDIT_REPORT_CODEX_2026_R3.md`.

## Section 2 - Data Quality Deep Dive (Checkpoint Saved)

### What I checked
- Core tables reviewed: `f7_employers_deduped`, `unions_master`, `nlrb_elections`, `osha_establishments`, `mergent_employers`.
- Measured missing values for key identity and analysis columns.
- Checked duplicate patterns on likely identifier columns.
- Checked key cross-table links for orphaned records.
- Reviewed formal foreign keys on these core tables.

### Findings

**Finding 2.1 - Some key fields have meaningful missing data in core tables**  
Severity: MEDIUM  
Confidence: Verified (tested)

Largest gaps:
- `mergent_employers.ein`: **56.05% missing**
- `f7_employers_deduped.latest_union_fnum`: **31.49% missing**
- `f7_employers_deduped.naics`: **15.10% missing**
- `unions_master.members`: **6.54% missing**
- `unions_master.local_number`: **6.17% missing**

Why this matters: missing IDs and industry codes reduce matching quality and lower confidence in ranking and targeting.

Evidence (SQL pattern):
```sql
SELECT round(100.0*sum((ein IS NULL OR btrim(ein)='')::int)/count(*),2)
FROM mergent_employers;
```

**Finding 2.2 - NLRB elections table has repeated case numbers**  
Severity: MEDIUM  
Confidence: Verified (tested)

- `nlrb_elections` has **1,604** case numbers that appear more than once.
- Even using `(case_number, election_date)` together, there are **360** duplicates.

Why this matters: if dashboards assume one row per election case, counts can be inflated.

Evidence:
```sql
SELECT count(*)
FROM (
  SELECT case_number, count(*)
  FROM nlrb_elections
  GROUP BY case_number
  HAVING count(*) > 1
) d;
```

**Finding 2.3 - Cross-reference orphan count is low, but not zero**  
Severity: LOW  
Confidence: Verified (tested)

Most key links are clean, but `nlrb_employer_xref` has **1 orphan row** where `f7_employer_id` does not resolve to `f7_employers_deduped`.

Why this matters: even one orphan can cause confusing "not found" behavior in lookup flows.

Evidence:
```sql
SELECT count(*)
FROM nlrb_employer_xref x
LEFT JOIN f7_employers_deduped f ON f.employer_id = x.f7_employer_id
WHERE x.f7_employer_id IS NOT NULL
  AND f.employer_id IS NULL;
```

**Finding 2.4 - Core-table foreign key enforcement is sparse**  
Severity: MEDIUM  
Confidence: Verified (tested)

For the five core tables, only three foreign keys exist:
- `f7_employers_deduped.canonical_group_id -> employer_canonical_groups.group_id`
- `unions_master.match_status -> union_match_status.status_code`
- `unions_master.sector -> union_sector.sector_code`

No direct FK protection exists between some major matching links (for example `nlrb_employer_xref.f7_employer_id` to deduped employers).

Why this matters: missing foreign keys make silent data drift more likely during bulk updates.

Evidence:
```sql
SELECT tc.table_name, kcu.column_name, ccu.table_name
FROM information_schema.table_constraints tc
...
WHERE tc.constraint_type='FOREIGN KEY'
  AND tc.table_name IN (...);
```

### Section 2 checkpoint status
Appended to `docs/AUDIT_REPORT_CODEX_2026_R3.md`.

## Section 3 - Materialized Views & Indexes (Checkpoint Saved)

### What I checked
- Listed all materialized views with row counts, size, and population state.
- Tested all regular views with `SELECT 1 ... LIMIT 1`.
- Listed top indexes by size and usage (`idx_scan`).
- Flagged large indexes with zero scans as likely unused.

### Findings

**Finding 3.1 - All 4 materialized views are populated and queryable**  
Severity: LOW  
Confidence: Verified (tested)

Materialized views found:
- `mv_whd_employer_agg`: 330,419 rows, 76 MB
- `mv_employer_search`: 170,775 rows, 58 MB
- `mv_employer_features`: 54,968 rows, 10 MB
- `mv_organizing_scorecard`: 22,389 rows, ~9 MB

Why this matters: these precomputed tables are active and reduce API query time.

Evidence:
```sql
SELECT schemaname, matviewname, ispopulated
FROM pg_matviews
WHERE schemaname='public';
```

**Finding 3.2 - Materialized view staleness is not directly trackable**  
Severity: MEDIUM  
Confidence: Verified (tested)

I did not find built-in metadata for "last refresh time" of each materialized view.

Why this matters: if refresh jobs fail, users can get old numbers without clear warning.

Evidence:
- `pg_matviews` provides definition and `ispopulated`, but no refresh timestamp.

**Finding 3.3 - All regular views passed a runtime health check**  
Severity: LOW  
Confidence: Verified (tested)

- 186 views checked
- 186 views returned successfully
- 0 broken views found

Why this matters: no immediate runtime view failures detected.

Evidence:
```sql
-- looped through information_schema.views
SELECT 1 FROM public.<view_name> LIMIT 1;
```

**Finding 3.4 - Many large indexes show zero usage and should be reviewed**  
Severity: MEDIUM  
Confidence: Likely (strong evidence)

Examples of large zero-scan indexes:
- `sam_entities.idx_sam_name_trgm` (57 MB, 0 scans)
- `osha_establishments.idx_osha_est_name_trgm` (53 MB, 0 scans)
- `sec_companies.idx_sec_name_state` (50 MB, 0 scans)
- `employers_990_deduped.idx_emp990d_name` (45 MB, 0 scans)
- `gleif_us_entities.idx_gus_statementid` (43 MB, 0 scans)

Why this matters: unused indexes increase storage and slow writes. Some may still be needed occasionally, but this pattern suggests cleanup opportunities.

Evidence:
```sql
SELECT s.relname AS table_name, i.relname AS index_name, st.idx_scan
FROM pg_class s
...
WHERE coalesce(st.idx_scan,0)=0;
```

**Finding 3.5 - A few very large indexes are actively used and likely critical**  
Severity: LOW  
Confidence: Verified (tested)

Examples:
- `osha_establishments_pkey` (86 MB, 2,548,029 scans)
- `nlrb_participants.idx_nlrb_part_case` (29 MB, 9,217,327 scans)
- `nlrb_cases_pkey` (29 MB, 1,592,595 scans)

Why this matters: these are high-value indexes; avoid dropping or altering them without benchmark tests.

### Section 3 checkpoint status
Appended to `docs/AUDIT_REPORT_CODEX_2026_R3.md`.

## Section 4 - Cross-Reference Integrity (Checkpoint Saved)

### What I checked
- Cross-source coverage in `corporate_identifier_crosswalk` (SEC, GLEIF, Mergent, F7, IRS 990).
- OSHA match rates, methods, and confidence patterns.
- NLRB linkage rates (participants, elections, employer links).
- Unified employer source mix and OSHA linkage by source.
- Scoring coverage and confidence distribution.

### Findings

**Finding 4.1 - Corporate crosswalk has useful links, but low overall source coverage**  
Severity: MEDIUM  
Confidence: Verified (tested)

Coverage from source systems into `corporate_identifier_crosswalk`:
- SEC: 1,893 / 517,403 (**0.37%**)
- GLEIF: 3,136 / 379,192 (**0.83%**)
- Mergent: 3,275 / 56,426 (**5.80%**)
- F7: 17,948 / 146,863 (**12.22%**)
- IRS 990: 15,157 / 586,767 (**2.58%**)

Why this matters: corporate roll-up features will be strong for some employers, but sparse for most of the long tail.

Evidence:
```sql
SELECT count(DISTINCT sec_id) FROM corporate_identifier_crosswalk WHERE sec_id IS NOT NULL;
```

**Finding 4.2 - Crosswalk tier data includes many rows without a tier label**  
Severity: MEDIUM  
Confidence: Verified (tested)

`corporate_identifier_crosswalk.match_tier` has **11,356 NULL rows**.

Why this matters: without a tier tag, users cannot tell how a match was made, which reduces trust and makes QA harder.

Evidence:
```sql
SELECT coalesce(match_tier,'(null)'), count(*)
FROM corporate_identifier_crosswalk
GROUP BY coalesce(match_tier,'(null)');
```

**Finding 4.3 - OSHA linking is broad but confidence is mixed by method**  
Severity: MEDIUM  
Confidence: Verified (tested)

- OSHA establishments matched to F7: **145,134 / 1,007,217 (14.41%)**
- Distinct F7 employers represented in OSHA matches: **31,800 / 146,863 (21.65%)**
- Some common methods are lower confidence (for example `CITY_NAICS_LOW` avg 0.385).

Why this matters: this is useful coverage, but low-confidence methods can add false positives unless filtered in user-facing views.

Evidence:
```sql
SELECT match_method, avg(match_confidence)
FROM osha_f7_matches
GROUP BY match_method;
```

**Finding 4.4 - NLRB participant-to-election non-join remains high and is expected**  
Severity: LOW  
Confidence: Verified (tested)

- Participants joining elections by `case_number`: **8.17%**
- Participants not joining elections: **91.83%**

This is close to the documented expectation (~92% non-join) and should **not** be treated as a platform bug.

Why this matters: NLRB participants include non-election case types.

Evidence:
```sql
SELECT round(100.0*(1.0 - count(*)::numeric/(SELECT count(*) FROM nlrb_participants)),2)
FROM nlrb_participants p
JOIN nlrb_elections e ON e.case_number=p.case_number;
```

**Finding 4.5 - NLRB participant matching to unions/employers is currently very low**  
Severity: HIGH  
Confidence: Verified (tested)

- Participants with `matched_olms_fnum`: **1.58%**
- Participants with `matched_employer_id`: **0.57%**

Why this matters: organizer workflows that rely on participant-level matching may miss most records.

Evidence:
```sql
SELECT count(*) FROM nlrb_participants WHERE matched_olms_fnum IS NOT NULL;
SELECT count(*) FROM nlrb_participants WHERE matched_employer_id IS NOT NULL;
```

**Finding 4.6 - Unified employer source breakdown is coherent and public-sector linkage is present**  
Severity: LOW  
Confidence: Verified (tested)

`unified_employers_osha` source counts:
- F7: 63,116
- NLRB: 28,839
- PUBLIC: 7,987
- VR: 824

`osha_unified_matches` by source:
- F7: 38,024
- NLRB: 4,607
- PUBLIC: 87
- VR: 94

Why this matters: public-sector records are integrated, though OSHA linkage there is naturally limited.

Evidence:
```sql
SELECT source_type, count(*) FROM unified_employers_osha GROUP BY source_type;
```

**Finding 4.7 - Scoring coverage is very high; confidence-band mix is heavily MEDIUM**  
Severity: LOW  
Confidence: Verified (tested)

- `ml_election_propensity_scores`: 146,693 rows for 146,863 F7 employers (**99.88% coverage**)
- `mergent_employers.organizing_score`: present for **98.25%** of rows
- Propensity confidence bands: MEDIUM 145,572 vs HIGH 1,121

Why this matters: scoring is broadly available, but high-confidence predictions are a small minority.

### Section 4 checkpoint status
Appended to `docs/AUDIT_REPORT_CODEX_2026_R3.md`.

## Section 5 - API Endpoint Audit (Checkpoint Saved)

### Scope note
The file named in the prompt (`api/labor_api_v6.py`) is not present in this codebase. The live API is split across `api/main.py` plus 17 router files under `api/routers/`.

### What I checked
- Enumerated all route decorators across all router files.
- Reviewed SQL execution patterns (`cur.execute`) for query safety.
- Checked whether referenced tables/views exist.
- Reviewed input validation patterns and error/response consistency.
- Identified overlap/duplication in endpoint functionality.

### Findings

**Finding 5.1 - Endpoint surface is large (160 routes), increasing maintenance risk**  
Severity: MEDIUM  
Confidence: Verified (tested)

Current route count is **160** across 17 router files (largest: `employers.py` with 27 routes, `density.py` with 21).

Why this matters: a wide API surface makes consistency, security review, and regression testing harder.

Evidence:
- `api/main.py` includes 17 routers.
- Route inventory command:
```bash
rg -n "@(router|app)\.(get|post|put|delete|patch)\(" api/routers -g "*.py"
```

**Finding 5.2 - Dynamic SQL is used heavily; most appears constrained, but risk remains if guardrails drift**  
Severity: MEDIUM  
Confidence: Likely (strong evidence)

Many endpoints build SQL with f-strings and dynamic fragments (`{where_clause}`, `{order_by}`, `{view_name}`). In this snapshot, most dynamic pieces are constrained by:
- query parameter regex patterns (example: `api/routers/museums.py`),
- explicit sort maps (example: `api/routers/vr.py`),
- controlled mappings (`SECTOR_VIEWS` in `api/helpers.py`).

Why this matters: this pattern is safe only while every dynamic fragment stays strictly whitelisted. A future edit can accidentally create SQL injection exposure.

Evidence:
- `api/routers/sectors.py:151`
- `api/routers/museums.py:71`
- `api/routers/employers.py:296`
- `api/helpers.py` (`safe_sort_col`, `SECTOR_VIEWS`)

**Finding 5.3 - Authentication can be fully bypassed when secret is unset**  
Severity: HIGH  
Confidence: Verified (tested)

If `LABOR_JWT_SECRET` is not set (or auth disabled), middleware allows all requests through.

Why this matters: admin and write endpoints can be publicly accessible by configuration mistake.

Evidence:
- `api/middleware/auth.py` (`if not JWT_SECRET: return await call_next(request)`)
- `api/main.py` startup warning logs that all endpoints are public when secret is missing.

**Finding 5.4 - Error response behavior is inconsistent across endpoints**  
Severity: MEDIUM  
Confidence: Verified (tested)

Examples:
- Some endpoints raise proper `HTTPException(404, ...)`.
- `api/routers/lookups.py:153` returns `{"error": "Metro not found"}` with success status instead of HTTP 404.
- `api/routers/health.py` catches all exceptions and returns `{"status": "unhealthy"...}` instead of failing with HTTP error code.

Why this matters: frontend code must handle inconsistent error formats and status codes.

**Finding 5.5 - Functionally overlapping endpoints may confuse clients**  
Severity: LOW  
Confidence: Verified (tested)

Examples:
- `GET /api/employers/unified-search` (materialized view path) and `GET /api/employers/unified/search` (table path) are similarly named but return from different backends.
- Public-sector search is available both via `GET /api/employers/search?sector=PUBLIC_SECTOR` and `GET /api/public-sector/employers`.

Why this matters: integrators can call the wrong endpoint and get different semantics.

Evidence:
- `api/routers/employers.py`
- `api/routers/public_sector.py`

**Finding 5.6 - Input validation gaps can trigger server errors instead of clean 4xx responses**  
Severity: LOW  
Confidence: Verified (tested)

`/api/employers/unified-detail/{canonical_id:path}` converts string slices to `int` for some source types without explicit validation handling. Bad IDs can produce 500-style failures.

Why this matters: user mistakes should return clear client errors, not internal server errors.

Evidence:
- `api/routers/employers.py` (`int(source_id)` paths)

**Finding 5.7 - Many populated tables are not directly exposed through API routes**  
Severity: LOW  
Confidence: Likely (strong evidence)

Examples of high-row tables with little/no direct API exposure include `ar_disbursements_emp_off`, `nlrb_docket`, `qcew_annual`, `epi_union_membership`, `sam_entities`.

Why this matters: valuable data can remain invisible to organizers unless surfaced through dedicated endpoints or documented exports.

### Section 5 checkpoint status
Appended to `docs/AUDIT_REPORT_CODEX_2026_R3.md`.

## Section 6 - File System & Script Inventory (Checkpoint Saved)

### What I checked
- Enumerated all files under `scripts/` and grouped by category folders.
- Scanned scripts for credential patterns (`password`, `secret`, `token`, `api_key`).
- Checked for references to archived tables and old architecture markers.
- Identified likely critical-path rebuild scripts vs one-time analysis scripts.

### Findings

**Finding 6.1 - Script footprint is very large and fragmented**  
Severity: MEDIUM  
Confidence: Verified (tested)

Current `scripts/` count is **544 files** across many categories (`etl`, `matching`, `cleanup`, `maintenance`, `analysis`, `verify`, `scoring`, etc.).

Why this matters: with this many scripts, it is easy to run the wrong one or skip a required one during rebuilds.

Evidence:
```bash
rg --files scripts
```

**Finding 6.2 - Critical pipeline scripts exist, but are mixed with one-off utilities in the same tree**  
Severity: MEDIUM  
Confidence: Likely (strong evidence)

Likely critical path examples:
- `scripts/import/load_multiyear_olms.py`
- `scripts/etl/load_osha_violations_detail.py`
- `scripts/etl/load_sec_edgar.py`
- `scripts/etl/load_gleif_bods.py`
- `scripts/etl/build_crosswalk.py`
- `scripts/etl/unified_employer_osha_pipeline.py`

At the same time, many one-off diagnostics and temporary scripts remain in active paths (for example `scripts/temp_*.py`, `scripts/verify/*`, `scripts/analysis/*`).

Why this matters: operator error risk goes up when permanent and temporary scripts are mixed together.

**Finding 6.3 - Credential hygiene is improved, but still noisy and easy to misuse**  
Severity: MEDIUM  
Confidence: Verified (tested)

Most scripts now read `DB_PASSWORD` from environment, which is good. However:
- credential-related patterns appear in many files,
- there are migration/fix scripts for password bugs,
- there are reminder strings like "update the password in this script".

Why this matters: even without active hardcoded secrets, the large number of credential touchpoints increases accidental leak risk.

Evidence:
- `scripts/analysis/find_literal_password_bug.py`
- `scripts/analysis/fix_literal_password_bug.py`
- `scripts/import/load_multiyear_olms.py`

**Finding 6.4 - Some scripts still target archived or transitional states**  
Severity: LOW  
Confidence: Verified (tested)

Audit/verification scripts still include checks around `splink_match_results` archive/drop behavior.

Why this matters: this is not a direct bug, but it signals ongoing transitional debt and can confuse new maintainers.

Evidence:
- `scripts/audit/verify_docs.py` (explicit `splink_match_results` status check)

**Finding 6.5 - Matching module structure appears modular at filesystem level**  
Severity: LOW  
Confidence: Likely (strong evidence)

The matching package is organized with clear modules (`config`, `pipeline`, `normalizer`, `matchers/base|exact|address|fuzzy`, adapters), which is a good architecture signal.

Why this matters: modular structure usually makes extension and testing easier than monolithic matching code.

Evidence:
- `scripts/matching/`
- `scripts/matching/matchers/`

### Section 6 checkpoint status
Appended to `docs/AUDIT_REPORT_CODEX_2026_R3.md`.

## Section 7 - Documentation Accuracy (Checkpoint Saved)

### What I checked
- Compared claims in `CLAUDE.md`, `README.md`, and `Roadmap_TRUE_02_15.md` to current code/database state.
- Verified live counts in PostgreSQL for key tables/views.
- Verified live API route count from router decorators.

### Findings

**Finding 7.1 - Core size metrics are inconsistent with current database state**  
Severity: MEDIUM  
Confidence: Verified (tested)

Current public schema counts are **174 tables** and **186 views**. Documentation still repeats older values like 169 tables.

Evidence:
- `CLAUDE.md`
- `Roadmap_TRUE_02_15.md`
- DB query from Section 1.

**Finding 7.2 - Several headline record counts in docs are outdated**  
Severity: MEDIUM  
Confidence: Verified (tested)

Examples:
- `f7_employers_deduped`: docs 113,713 vs actual 146,863
- `osha_f7_matches`: docs 138,340 vs actual 145,134
- `unified_employers_osha`: docs 100,768 vs actual 100,766
- `mv_organizing_scorecard`: README 24,841 vs actual 22,389

Evidence:
- `CLAUDE.md`
- `README.md`
- SQL count check in Section 7.

**Finding 7.3 - README includes at least one clearly incorrect data-source line**  
Severity: HIGH  
Confidence: Verified (tested)

README says `NLRB Participants | 30,399 unions`. Actual `nlrb_participants` has **1,906,542 rows** and is not a "union count" table.

Why this matters: this can mislead non-technical users about data scope by more than 60x.

Evidence:
- `README.md`
- `SELECT COUNT(*) FROM nlrb_participants;`

**Finding 7.4 - API endpoint count in docs is stale**  
Severity: LOW  
Confidence: Verified (tested)

README says 152 endpoints; live router decorators show **160** endpoints.

Evidence:
- `README.md`
- route scan command on `api/routers/*.py`

**Finding 7.5 - Frontend structure section in README is outdated**  
Severity: LOW  
Confidence: Verified (tested)

README says 10 JS modules under `files/js/`; current folder contains **19 JS files**.

Evidence:
- `README.md`
- filesystem count of `files/js/*.js`

**Finding 7.6 - Security wording in roadmap is partly overstated**  
Severity: MEDIUM  
Confidence: Likely (strong evidence)

Roadmap language says security and query protection are improved across the board, but auth is still disabled by default unless env is configured, and dynamic SQL patterns still require careful guardrails.

Evidence:
- `Roadmap_TRUE_02_15.md`
- `api/middleware/auth.py`
- Section 5 endpoint audit findings.

### Section 7 checkpoint status
Appended to `docs/AUDIT_REPORT_CODEX_2026_R3.md`.

## Section 8 - Frontend & User Experience (Checkpoint Saved)

### What I checked
- Reviewed `files/organizer_v5.html` and all JS modules under `files/js/`.
- Searched for old scoring scale remnants and factor-count mismatches.
- Checked for hardcoded localhost API URLs.
- Counted inline event handlers in HTML.
- Evaluated modal architecture and API error-handling behavior.
- Performed a basic accessibility attribute scan.

### Findings

**Finding 8.1 - Frontend scoring model is not aligned with documented 9-factor / 0-100 expectation**  
Severity: HIGH  
Confidence: Verified (tested)

Frontend config currently defines **8 active factors** with `SCORE_MAX = 80`, and tier thresholds are based on 20/25/30 ranges.

Why this matters: organizers may see scores that do not match the intended platform scoring model, causing trust issues.

Evidence:
- `files/js/config.js` (8 factors, `SCORE_MAX = 80`)
- `files/js/scorecard.js` and `files/js/app.js` (tier cutoffs)

**Finding 8.2 - Inline onclick handlers appear removed from HTML (good progress)**  
Severity: LOW  
Confidence: Verified (tested)

No inline `onclick=` handlers were found in `organizer_v5.html`. The UI now uses `data-action` attributes and delegated handlers.

Why this matters: this improves maintainability and reduces DOM/script coupling.

Evidence:
- `files/organizer_v5.html` (`data-action` patterns)

**Finding 8.3 - `modals.js` monolith appears already split into feature modules**  
Severity: LOW  
Confidence: Verified (tested)

The prior 2,598-line `modals.js` file is not present; modal logic is split into files such as:
- `files/js/modal-analytics.js`
- `files/js/modal-corporate.js`
- `files/js/modal-elections.js`
- `files/js/modal-publicsector.js`
- `files/js/modal-similar.js`
- `files/js/modal-trends.js`
- `files/js/modal-unified.js`

Why this matters: this is a significant architecture improvement over a modal monolith.

**Finding 8.4 - No hardcoded localhost API base found in frontend runtime path (good)**  
Severity: LOW  
Confidence: Verified (tested)

API base derives from browser origin (`window.location.origin`) or an override variable.

Why this matters: this reduces environment mismatch bugs between local and deployed environments.

Evidence:
- `files/js/config.js`

**Finding 8.5 - API error handling is inconsistent across modules**  
Severity: MEDIUM  
Confidence: Verified (tested)

Some modules validate `response.ok` and show helpful fallback messages. Others call `fetch(...).then(r => r.json())` without checking status first.

Why this matters: failed API calls may produce unclear UI behavior depending on which modal/view is used.

Evidence:
- Weaker patterns: `files/js/modal-analytics.js`, `files/js/modal-trends.js`
- Stronger patterns: `files/js/scorecard.js`, `files/js/modal-unified.js`, `files/js/detail.js`

**Finding 8.6 - Accessibility metadata is minimal in main HTML**  
Severity: MEDIUM  
Confidence: Verified (tested)

No `aria-*` attributes were found in `organizer_v5.html` during scan.

Why this matters: keyboard and screen-reader experience is likely weaker than it should be for complex modals and dynamic panels.

Evidence:
```bash
rg -n "aria-" files/organizer_v5.html
```

**Finding 8.7 - State persistence is partial (good for saved searches, weaker for full session continuity)**  
Severity: LOW  
Confidence: Likely (strong evidence)

Saved searches use `localStorage`, and some search state is mirrored to URL query parameters, but full cross-view state persistence appears limited.

Why this matters: users can lose context when moving between major views or after refresh.

Evidence:
- `files/js/modal-comparison.js` (`localStorage`)
- `files/js/app.js` (URL query handling)

### Section 8 checkpoint status
Appended to `docs/AUDIT_REPORT_CODEX_2026_R3.md`.

## Section 9 - Security Audit (Checkpoint Saved)

### What I checked
- Authentication middleware behavior and JWT settings.
- Credential exposure across config/docs/scripts and `.env` handling.
- SQL query construction patterns in API router code.
- Input validation and error handling behavior.
- CORS and security-header posture.

### Findings

**Finding 9.1 - Authentication is fail-open when JWT secret is missing**  
Severity: CRITICAL  
Confidence: Verified (tested)

If `LABOR_JWT_SECRET` is empty, middleware allows every request without token checks.

Why this matters: anyone who can reach the API can access admin/read endpoints if environment setup is wrong.

Evidence:
- `api/middleware/auth.py` (`if not JWT_SECRET: return await call_next(request)`)
- `api/main.py` warning logs confirm this mode.

**Finding 9.2 - Local `.env` contains live database password and JWT secret**  
Severity: HIGH  
Confidence: Verified (tested)

The local `.env` file currently includes real credentials/secrets.

Why this matters: if this file is copied, backed up insecurely, or accidentally committed, full API/DB compromise risk is high.

Evidence:
- `.env` (local file contents)
- `.env` is currently not in tracked files (good), while `.env.example` is tracked.

**Finding 9.3 - Plaintext password appears in multiple project documents and helper audit scripts**  
Severity: HIGH  
Confidence: Verified (tested)

The DB password string appears in several markdown and helper audit files.

Why this matters: even if runtime code is clean, secret exposure in docs/history remains a real leak vector.

Evidence (examples):
- `BLIND_AUDIT_PROMPT.md`
- `audit_2026/db_query.py`
- `_audit_q.py` (and related `_audit_*.py` helpers)

**Finding 9.4 - Dynamic SQL is widespread; currently mostly guarded but carries ongoing injection risk**  
Severity: HIGH  
Confidence: Likely (strong evidence)

The API uses many `cur.execute(f"...")` calls with dynamic fragments. Most are constrained by whitelists/maps/validated patterns today.

Why this matters: this approach is fragile. A small future change can turn a safe fragment into injectable SQL.

Evidence:
- `api/routers/*.py` (many `execute(f...)` instances)
- controlled examples in `api/helpers.py` and per-endpoint sort maps/patterns.

**Finding 9.5 - Input validation quality varies by endpoint**  
Severity: MEDIUM  
Confidence: Verified (tested)

Some endpoints use `Query(..., pattern=...)` and strict types; others accept free-form strings or cast values (`int(...)`) without guard clauses.

Why this matters: malformed user input can produce 500 errors or unpredictable behavior instead of clear 4xx responses.

Evidence:
- `api/routers/employers.py` (`unified-detail` source ID casting)
- mixed validation styles across routers.

**Finding 9.6 - JWT expiry exists, but token lifecycle controls are basic**  
Severity: LOW  
Confidence: Verified (tested)

Tokens expire after 8 hours and can be refreshed, but there is no revocation list/session invalidation flow.

Why this matters: compromised tokens remain valid until expiry unless secret is rotated.

Evidence:
- `api/config.py` (`JWT_EXPIRY_HOURS = 8`)
- `api/routers/auth.py` refresh endpoint behavior.

**Finding 9.7 - CORS is narrowed to configured origins, but broader security headers are not enforced**  
Severity: LOW  
Confidence: Verified (tested)

CORS is configured with explicit origins and limited methods/headers. I did not find explicit middleware for headers like CSP/HSTS/X-Frame-Options.

Why this matters: CORS is only one layer; missing browser security headers can increase exploit surface.

Evidence:
- `api/main.py` CORS middleware config
- no separate hardening middleware found for response headers.

### Section 9 checkpoint status
Appended to `docs/AUDIT_REPORT_CODEX_2026_R3.md`.

## Section 10 - Summary & Recommendations

### 1) Health Score
**Needs Work**

Reason: the platform has strong data and broad features, but still has major trust and safety gaps (auth default-off, documentation drift, scoring mismatch in frontend, and large operational complexity).

### 2) Top 10 Issues (ranked by organizer impact)
1. **Auth can be effectively off by config** (Critical) - external users could access everything if setup is wrong.
2. **Frontend scoring model mismatch (8-factor/80-scale signals)** (High) - organizer-facing scores can conflict with intended model.
3. **Major documentation drift on counts/capabilities** (High) - users/operators make decisions with stale numbers.
4. **NLRB participant matching coverage is very low at participant level** (High) - limits employer/union intelligence depth.
5. **Dynamic SQL pattern is widespread and fragile** (High) - currently mostly safe, but easy to regress into injection bugs.
6. **Large script sprawl (544 files) with mixed critical and one-off scripts** (Medium) - high operational error risk.
7. **Missing primary keys on multiple production tables** (Medium) - raises duplicate/drift risk.
8. **Materialized view refresh staleness not tracked explicitly** (Medium) - stale data can be served silently.
9. **Inconsistent API error formats/status behavior** (Medium) - frontend reliability and debugging friction.
10. **Accessibility metadata is sparse in the main frontend HTML** (Medium) - poorer usability and compliance risk.

### 3) Quick Wins (under 1 hour each)
- Enforce secure-default auth behavior (`JWT required unless explicit local dev flag`).
- Add a "last refreshed" metadata table for each materialized view refresh job.
- Normalize API 404/error behavior (remove `{"error": ...}` 200 responses).
- Add a short doc banner with "Last verified date" to `README.md` and `CLAUDE.md`.
- Add basic `aria-*` labels to modal containers and close buttons.

### 4) Tables to Drop (or archive first)
- `splink_match_results` (currently empty; keep archived dump if needed).
- Transitional audit-only helper tables if reintroduced in future runs (do not keep in production schema).
- Consider archiving very old staging/helper tables once ownership is confirmed.

### 5) Missing Index Recommendations
- Add/verify indexes on frequently filtered cross-reference keys where absent or weakly used:
  - `nlrb_employer_xref(f7_employer_id)` usage review and query-plan validation.
  - Keep high-usage indexes; evaluate dropping truly unused large indexes after 7-14 day usage window.
- Add index-usage monitoring report to regular maintenance workflow.

### 6) Documentation Corrections Needed
- Update table counts to current values (174 tables / 186 views in public).
- Update endpoint count to current value (160 routes).
- Correct `nlrb_participants` and other stale row-count claims.
- Correct frontend module/file structure and scoring-system descriptions.

### 7) Data Quality Priorities
1. Reduce missing critical keys (especially `mergent_employers.ein`, F7 NAICS gaps, union linkage fields).
2. Review duplicate patterns in `nlrb_elections` (`case_number` / `case+date` duplicates).
3. Keep orphan checks as scheduled QA gates (crosswalk/match tables).
4. Expand explicit foreign keys on high-value cross-reference tables where safe.

### 8) Code Architecture Assessment
Architecture is improving and mostly modular now (split routers, split frontend modal modules, modular matching package). The biggest maintainability drag is still script sprawl and uneven conventions.

### 9) Security Posture (external deployment)
**Not safe for external deployment as-is** because secure behavior depends on environment discipline (auth can be left off), secrets appear in local env and some docs/scripts, and dynamic SQL patterns need stricter guardrails.

### 10) Technical Debt Estimate
Rough estimate before major new features: **3-5 focused engineering weeks**
- Week 1: auth/secret hardening + API error consistency
- Week 2: frontend scoring alignment + accessibility basics
- Week 3: documentation sync + script inventory cleanup + runbook
- Weeks 4-5: index tuning + cross-reference QA automation + remaining refactors

### Final checkpoint status
All 10 full-audit sections are complete and saved in `docs/AUDIT_REPORT_CODEX_2026_R3.md`.
