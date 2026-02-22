# Audit Report (Codex) - 2026 Round 4 (Working, Point-by-Point)
Date started: 2026-02-19
Project: labor-data-project
Prompt source: `INDEPENDENT_AI_AUDIT_PROMPT_2026-02-18.md`
Status: IN PROGRESS

## How This Report Is Being Updated
This report is intentionally broken into parts and updated after each completed point.

For every point, I use this exact structure:
- **What I investigated**
- **What the documentation claims**
- **What I actually observed**
- **Severity:** CRITICAL / HIGH / MEDIUM / LOW
- **Recommended action**

## Audit Parts
1. Part A - Setup and baseline verification
2. Part B - Area 1: Documentation vs Reality
3. Part C - Area 2: Matching Pipeline
4. Part D - Area 3: Scoring System
5. Part E - Area 4: Data Gaps and Missing Connections
6. Part F - Area 5: API and Frontend
7. Part G - Area 6: Infrastructure and Code Health
8. Part H - Findings Outside the Audit Scope
9. Part I - Final deliverable sections

## Point Log

### Point A1 - Required starting documents are present and readable
- **What I investigated**
Verified that the four required starting documents named in the audit prompt exist in the project root and can be read.

- **What the documentation claims**
The prompt says to start by reading these four files: `PROJECT_STATE.md`, `CLAUDE.md`, `UNIFIED_ROADMAP_2026_02_17.md`, `PIPELINE_MANIFEST.md`.

- **What I actually observed**
All four files are present in `C:\Users\jakew\Downloads\labor-data-project` and discoverable by shell listing/search.

Command evidence:
```powershell
Get-ChildItem -Path 'C:\Users\jakew\Downloads\labor-data-project' -Name
rg --files 'C:\Users\jakew\Downloads\labor-data-project' | rg -n "PROJECT_STATE|CLAUDE\.md|UNIFIED_ROADMAP|PIPELINE_MANIFEST"
```

- **Severity:** LOW
- **Recommended action**
Proceed to systematic claim-by-claim verification across those files; do not treat their statements as facts until verified.

### Point B1 - Test status in `PROJECT_STATE.md` does not match current test reality
- **What I investigated**
Verified the explicit test-count and expected-failure claim in `PROJECT_STATE.md` by running the project test suite.

- **What the documentation claims**
`PROJECT_STATE.md` says: "380 tests. All should pass except `test_expands_hospital_abbreviation`."

- **What I actually observed**
Current test run collected **441** tests, not 380, and there are **2 failures**, not one:
1. `tests/test_employer_data_sources.py::TestMVDataIntegrity::test_osha_count_matches_legacy_table`
2. `tests/test_matching.py::TestNormalizerAggressive::test_expands_hospital_abbreviation`

Executed command:
```powershell
python -m pytest tests/ -q
```

Observed summary:
```text
collected 441 items
2 failed, 439 passed
```

- **Severity:** HIGH
- **Recommended action**
Update `PROJECT_STATE.md` test section immediately to current totals/failures and stop using stale numbers as release-readiness signals.

### Point B2 - `PROJECT_STATE.md` has internal status contradictions about Phase B4
- **What I investigated**
Compared the top-level "Last manually updated" status line to the detailed Phase B status table inside the same file.

- **What the documentation claims**
Top line claims: "B4 OSHA all 4 batches DONE".
Later section claims: "B4 | IN PROGRESS" and references batch-by-batch continuation steps.

- **What I actually observed**
Both statements are present simultaneously in `PROJECT_STATE.md`, so the document is internally inconsistent and cannot be treated as a reliable single source of truth for B4 status.

Evidence snippets:
- Header text includes "B4 OSHA all 4 batches DONE"
- Section 6 table includes "B4 | IN PROGRESS"
- Follow-up run instructions still tell user to run batches 2-4

- **Severity:** MEDIUM
- **Recommended action**
Normalize all B4 references to one explicit state with timestamp and evidence link (checkpoint file + row deltas) and remove obsolete interim notes.

### Point B3 - Database inventory counts in `PROJECT_STATE.md` are partially stale
- **What I investigated**
Validated Section 2 inventory/table-count claims from `PROJECT_STATE.md` against live PostgreSQL counts.

- **What the documentation claims**
`PROJECT_STATE.md` lists:
- Tables: 178
- Views: 186
- Materialized views: 6
- Database size: 20 GB
- `unified_match_log` top-table row count: 265,526

- **What I actually observed**
Live DB returned:
- Tables: 174 (not 178)
- Views: 186 (matches)
- Materialized views: 6 (matches)
- Database size: 19 GB (not 20 GB)
- `unified_match_log`: 1,160,702 rows (not 265,526)

Executed checks:
```powershell
# via db_config.get_connection(), queried information_schema/pg_catalog + direct COUNT(*)
tables=174
views=186
matviews=6
db_size_pretty=19 GB
unified_match_log=1160702
```

- **Severity:** HIGH
- **Recommended action**
Regenerate Section 2 via one canonical script and write a timestamped snapshot so all inventory/table numbers are synchronized in one pass.

### Point B4 - `CLAUDE.md` test-status claim is stale
- **What I investigated**
Verified top-level `CLAUDE.md` test claim and tests-directory claim against actual test execution.

- **What the documentation claims**
`CLAUDE.md` states:
- "Last Updated: 2026-02-17 (Phase B in progress, 380 tests passing)"
- "`tests/` # 380 automated tests"

- **What I actually observed**
Current run executes **441** tests with **2 failures** (not 380 passing).

Executed command:
```powershell
python -m pytest tests/ -q
```

Observed summary:
```text
collected 441 items
2 failed, 439 passed
```

- **Severity:** HIGH
- **Recommended action**
Update `CLAUDE.md` test metadata to reflect real current totals and failing test names.

### Point B5 - Multiple `CLAUDE.md` core table counts are stale (some materially)
- **What I investigated**
Cross-checked explicitly documented table counts in `CLAUDE.md` against live `COUNT(*)` results.

- **What the documentation claims**
Examples in `CLAUDE.md`:
- `osha_f7_matches`: 145,134
- `whd_f7_matches`: 26,312
- `national_990_f7_matches`: 14,428
- `sam_f7_matches`: 15,010
- `unified_match_log`: 265,526
- `mv_employer_search`: 118,015

- **What I actually observed**
Live DB counts:
- `osha_f7_matches`: 175,685
- `whd_f7_matches`: 27,121
- `national_990_f7_matches`: 14,610
- `sam_f7_matches`: 16,030
- `unified_match_log`: 1,160,702
- `mv_employer_search`: 170,775

Executed check method:
```powershell
# via db_config.get_connection(); direct SELECT COUNT(*) on each listed table/view
```

- **Severity:** HIGH
- **Recommended action**
Treat `CLAUDE.md` row counts as historical unless auto-generated; move volatile counts to generated inventory outputs.

### Point B6 - `CLAUDE.md` contains conflicting scorecard system references
- **What I investigated**
Checked scorecard sections in `CLAUDE.md` for consistency about which view is "current unified" and what row counts it reports.

- **What the documentation claims**
`CLAUDE.md` states both:
- "Current unified scorecard: `mv_organizing_scorecard` ..."
- Legacy section says `mv_organizing_scorecard` was superseded and references old 22,389-row state.

- **What I actually observed**
Live DB has:
- `mv_unified_scorecard` with 146,863 rows and `unified_score` column (current unified design).
- `mv_organizing_scorecard` with 195,164 rows and legacy OSHA-oriented columns.

This means the document mixes legacy and current scorecard narratives, which can misdirect implementation work.

Evidence checks:
```powershell
SELECT COUNT(*) FROM mv_unified_scorecard;      -- 146863
SELECT COUNT(*) FROM mv_organizing_scorecard;   -- 195164
# schema probe shows unified_score exists in mv_unified_scorecard
```

- **Severity:** HIGH
- **Recommended action**
Rewrite scorecard section with explicit "current vs legacy" split and remove contradictory "current unified = mv_organizing_scorecard" language.

### Point B7 - `CLAUDE.md` overstates orphan-relations total while fixing status is directionally correct
- **What I investigated**
Validated the orphan-resolution claim for `f7_union_employer_relations`.

- **What the documentation claims**
`CLAUDE.md` says orphan issue is fixed and "All 119,832 relations resolve via JOIN."

- **What I actually observed**
Join check confirms **0 orphans** (fix status is true), but total current relations are **119,445**, not 119,832.

Executed check:
```powershell
SELECT COUNT(*) FILTER (WHERE fed.employer_id IS NULL) AS orphaned, COUNT(*) AS total
FROM f7_union_employer_relations rel
LEFT JOIN f7_employers_deduped fed ON fed.employer_id = rel.employer_id;
-- orphaned=0, total=119445
```

- **Severity:** MEDIUM
- **Recommended action**
Keep the fix note but update totals to current state and add date-stamped source query.

### Point B8 - `unified_match_log` growth is mostly rejected/superseded history, not active coverage
- **What I investigated**
Broke down `unified_match_log` by `status` and `source_system` to explain why row count is much larger than older documentation.

- **What the documentation claims**
`CLAUDE.md` describes `unified_match_log` as 265,526 central audit entries.

- **What I actually observed**
Current total is 1,160,702 with status mix:
- `active`: 215,574
- `rejected`: 554,541
- `superseded`: 390,587

Largest driver is OSHA history:
- OSHA `rejected`: 461,453
- OSHA `superseded`: 236,162
- OSHA `active`: 97,142

This indicates large historical/audit accumulation from reruns, not just active-link growth.

- **Severity:** MEDIUM
- **Recommended action**
Documentation should distinguish `unified_match_log_total` from `active_matches` and publish both by source.

### Point C1 - OSHA rerun checkpoint is internally consistent and matches OSHA active log count
- **What I investigated**
Validated `checkpoints/osha_rerun.json` totals against live `unified_match_log` OSHA status counts.

- **What the documentation claims**
Recent docs describe OSHA batch rerun completion with high/medium active matches and rejected low-confidence outcomes.

- **What I actually observed**
Checkpoint math is internally coherent:
- 4 batches cover exactly 1,007,217 records.
- Batch `matched` sum: 406,559.
- `HIGH+MEDIUM` sum: 97,142.
- `LOW` sum: 309,417.
- `HIGH+MEDIUM+LOW` equals total `matched` (406,559).

Live DB alignment:
- `unified_match_log` for OSHA `active` = 97,142 (exactly matches checkpoint HIGH+MEDIUM total).
- OSHA `rejected` = 461,453 and `superseded` = 236,162 are also present as historical audit states.

- **Severity:** LOW
- **Recommended action**
Keep using checkpoint + status-band validation as a quality gate for future source reruns.

### Point C2 - Current OSHA match table appears to mix legacy and new pipeline outputs
- **What I investigated**
Compared `osha_f7_matches` contents to OSHA entries in `unified_match_log` and inspected method distributions.

- **What the documentation claims**
Current system narrative implies unified deterministic pipeline outputs should reflect current active matching state.

- **What I actually observed**
`osha_f7_matches` has 175,685 rows (distinct establishments), while OSHA `active` in `unified_match_log` is 97,142.
`osha_f7_matches` includes large volumes of methods not central to the described current deterministic rerun methods (for example `STATE_NAICS_FUZZY`, `STREET_NUM_ZIP`, `ADDRESS_CITY_STATE`, `MERGENT_BRIDGE`).

Top `osha_f7_matches` methods by count include:
- `FUZZY_SPLINK_ADAPTIVE`: 51,302
- `STATE_NAICS_FUZZY`: 36,903
- `FUZZY_TRIGRAM`: 15,018
- `NAME_AGGRESSIVE_STATE`: 13,408
- `STREET_NUM_ZIP`: 12,484

This suggests the active OSHA-facing table is aggregating across multiple matching regimes and may not represent only the latest deterministic high/medium set.

- **Severity:** HIGH
- **Recommended action**
Define one canonical publication rule for `osha_f7_matches` (for example only current-run accepted records), or expose version/run metadata so downstream consumers can filter reliably.

### Point D1 - Unified scoring code does implement missing-factor exclusion (with caveats)
- **What I investigated**
Read `scripts/scoring/build_unified_scorecard.py` and validated score/coverage behavior against `mv_unified_scorecard` data.

- **What the documentation claims**
Unified score uses signal-strength logic: missing factors are excluded rather than treated as zero.

- **What I actually observed**
Code behavior matches this principle for optional factors:
- Optional factor scores (`score_osha`, `score_nlrb`, `score_whd`, `score_contracts`, `score_financial`) are `NULL` when unavailable.
- Denominator for `unified_score` counts only non-null optional factors plus two always-available factors (`union_proximity`, `size`).
- `factors_total` is 7, `factors_available` ranges 2..7, and `coverage_pct` ranges 28.6..100.0.

Consistency spot-checks:
- `NOT has_osha AND score_osha IS NOT NULL` = 0
- `NOT has_whd AND score_whd IS NOT NULL` = 0
- `NOT is_federal_contractor AND score_contracts IS NOT NULL` = 0

Caveat found:
- `has_nlrb AND score_nlrb IS NULL` = 3,996 (flag/data mismatch exists for NLRB path).

- **Severity:** MEDIUM
- **Recommended action**
Keep the scoring formula, but resolve upstream data-source flag mismatches (especially NLRB) before treating coverage metrics as authoritative.

### Point D2 - Unified score outputs are stale relative to current OSHA match table
- **What I investigated**
Compared OSHA source coverage in `mv_employer_data_sources` / `mv_unified_scorecard` against current `osha_f7_matches` distinct employer coverage.

- **What the documentation claims**
Current unified scorecard is presented as the active comprehensive scoring layer for all F7 employers.

- **What I actually observed**
Coverage mismatch is substantial:
- `mv_employer_data_sources` employers with `has_osha=true`: 32,774
- `mv_unified_scorecard` employers with `has_osha=true`: 32,774
- Distinct `f7_employer_id` in `osha_f7_matches`: 42,976

Difference: **10,202** employers with OSHA matches are not reflected as `has_osha` in current unified score outputs.

Given `build_employer_data_sources.py` directly sources `has_osha` from `SELECT DISTINCT f7_employer_id FROM osha_f7_matches`, this pattern strongly indicates stale materialized views after OSHA match-table changes.

- **Severity:** HIGH
- **Recommended action**
Refresh `mv_employer_data_sources` and dependent `mv_unified_scorecard` after each matching rerun, and add a freshness check that fails when source-table distinct counts diverge from MV flags.

### Point E1 - Missing-union gap metrics are currently accurate and still unresolved
- **What I investigated**
Recomputed missing unions by joining `f7_union_employer_relations.union_file_number` to `unions_master.f_num` (cast to common text type).

- **What the documentation claims**
Known issue: 166 missing unions covering 61,743 workers.

- **What I actually observed**
Live query results match that claim:
- Missing relation rows: 577
- Distinct missing union file numbers: 166
- Affected employers: 544
- Affected workers: 61,743

Baseline context:
- Total relations: 119,445
- Total workers across relations: 15,737,807

Largest missing union by workers is `12590` (38,192 workers).

- **Severity:** HIGH
- **Recommended action**
Keep this as an active blocker; prioritize resolving top-mass missing unions first (starting with `12590`) because impact is concentrated.

### Point E2 - OLMS annual-report tables remain largely disconnected from active product paths
- **What I investigated**
Searched active API/scoring/SQL code for references to `ar_membership`, `ar_disbursements_total`, `ar_assets_investments`, `ar_disbursements_emp_off`, and checked materialized view definitions for usage.

- **What the documentation claims**
The audit prompt flags these OLMS annual-report tables as loaded but not integrated.

- **What I actually observed**
References are present in `scripts/analysis/*` ad-hoc scripts, but no active API/scoring integrations were found in `api/`, `scripts/scoring/`, or materialized view definitions.
This supports the claim that these datasets exist but are not yet connected to user-facing scoring/search flows.

- **Severity:** MEDIUM
- **Recommended action**
Define a minimum integration slice (for example one membership-trend feature and one representational-spend feature) with explicit downstream API exposure.

### Point F1 - Live API surface is larger than “~160 endpoints” and currently at 174 `/api/*` routes
- **What I investigated**
Enumerated registered FastAPI routes from `api.main:app` directly in-process.

- **What the documentation claims**
The audit prompt references “~160 endpoints” as a status expectation.

- **What I actually observed**
Current route registry shows:
- Total routes: 179
- API routes (`/api/*`): 174 unique paths

So current API surface exceeds the rough 160-endpoint expectation.

- **Severity:** LOW
- **Recommended action**
Publish an auto-generated route inventory in docs to prevent stale endpoint-count claims.

### Point F2 - Auth hardening exists, but local default still disables auth
- **What I investigated**
Checked router dependencies for `require_auth`/`require_admin`, and observed runtime auth mode from environment.

- **What the documentation claims**
Security hardening was completed; API should enforce auth by default unless explicitly disabled.

- **What I actually observed**
Protected dependencies are present in write/admin routes (for example employer flags and admin refresh/review endpoints), but local `.env` currently sets `DISABLE_AUTH=true`, and runtime logs warn auth is disabled.
This means local operation remains unauthenticated unless config is changed.

- **Severity:** MEDIUM
- **Recommended action**
Use environment-specific defaults: `DISABLE_AUTH=false` outside explicit local-dev sessions, and add startup logging that clearly marks insecure mode.

### Point G1 - Script inventory documentation is internally inconsistent with current filesystem
- **What I investigated**
Compared script-count claims in `PIPELINE_MANIFEST.md` and `PROJECT_STATE.md` against actual `scripts/` directory contents.

- **What the documentation claims**
Examples:
- `PIPELINE_MANIFEST.md`: "Active scripts: 120", "Total active pipeline scripts: 69", Stage counts including matching (29), scoring (4), maintenance (2), scraper (7), analysis (51).
- `PROJECT_STATE.md`: Stage 3 says 8 scripts (4 scoring + 4 ML).

- **What I actually observed**
Filesystem counts (non-`__init__.py`) show drift:
- Total Python files under `scripts/`: 125
- `analysis`: 52 (not 51)
- `scoring`: 6 (not 4)
- `maintenance`: 3 (not 2)
- `scraper`: 8 (not 7)
- `matching`: 27 (not 29)
- `ml`: 3 + package `__init__.py` (not 4 executable scripts)

Additional mismatch:
- `scripts/scoring/` currently has 6 files (`build_employer_data_sources.py`, `build_unified_scorecard.py`, `compute_gower_similarity.py`, `compute_nlrb_patterns.py`, `create_scorecard_mv.py`, `update_whd_scores.py`).

This indicates the manifest is not a reliable exact inventory in its current state.

- **Severity:** MEDIUM
- **Recommended action**
Generate manifest counts automatically from filesystem + an explicit allowlist of "active pipeline scripts" to eliminate manual count drift.

### Point F3 - Frontend contains stale hard-coded scorecard row-count copy
- **What I investigated**
Checked `files/organizer_v5.html` UI text around scorecard refresh/admin controls against live scorecard row counts.

- **What the documentation claims**
Frontend text says: "Refresh the organizing scorecard materialized view (24,841 rows)."

- **What I actually observed**
Live DB row counts are much higher:
- `mv_organizing_scorecard`: 195,164 rows
- `mv_unified_scorecard`: 146,863 rows

So user-facing copy is stale and can mislead operators about whether refreshes are complete or data changed as expected.

- **Severity:** LOW
- **Recommended action**
Replace static row-count text with a dynamic API-backed value, or remove explicit row count from the UI copy.

### Point B9 - `UNIFIED_ROADMAP_2026_02_17.md` is now a historical snapshot, not current state
- **What I investigated**
Cross-checked roadmap "current state/problems" numbers against live DB and API behavior.

- **What the documentation claims**
Roadmap claims include:
- 359 tests passing
- scorecard rows 22,389
- materialized views = 4
- `unified_match_log` 265,526
- critical orphan/employer-link issues and broken corporate hierarchy endpoints

- **What I actually observed**
Current state differs materially:
- tests: 441 collected, 2 failing
- `mv_unified_scorecard`: 146,863 rows; `mv_organizing_scorecard`: 195,164 rows
- materialized views: 6
- `unified_match_log`: 1,160,702
- `f7_union_employer_relations` orphaned employer links: 0 (join-resolved)
- corporate hierarchy endpoint check (`/api/corporate/hierarchy/stats`) returns 200 in test client

The roadmap is still useful as planning history, but no longer reliable as a current-state source.

- **Severity:** HIGH
- **Recommended action**
Relabel roadmap status sections explicitly as dated (2026-02-17 snapshot) and point day-to-day reality checks to generated current-state artifacts.

### Point F4 - Auth enforcement works when enabled, but current local mode bypasses it
- **What I investigated**
Exercised API endpoints in FastAPI `TestClient` under both auth modes.

- **What the documentation claims**
Auth should be enforced unless `DISABLE_AUTH=true` is explicitly set.

- **What I actually observed**
With `DISABLE_AUTH=true`:
- `/api/admin/match-quality` returns 200 unauthenticated.

With `DISABLE_AUTH=false` (no token):
- `/api/admin/match-quality` returns 401
- `/api/employers/flags` returns 401
- `/api/scorecard/unified/stats` returns 401

So enforcement logic functions, but effective security posture depends entirely on environment setting.

- **Severity:** MEDIUM
- **Recommended action**
Treat `DISABLE_AUTH=true` as short-lived local-debug mode only and gate it behind an explicit local profile.

### Point F5 - Legacy scorecard detail endpoint is functionally broken for all current list IDs
- **What I investigated**
Exercised legacy scorecard list/detail flow and traced request handling in `api/routers/scorecard.py` and `api/routers/organizing.py`.

- **What the documentation claims**
The API namespace includes `/api/scorecard/` list and `/api/scorecard/{estab_id}` detail as backward-compatible scorecard endpoints.

- **What I actually observed**
List endpoint works and returns hashed `establishment_id` values, but detail endpoint rejects those IDs and returns 404:
- `/api/scorecard/?limit=1` -> returns `establishment_id` like `3f7b485458ba2be7204e9d99ceb0bf15`
- `/api/scorecard/3f7b485458ba2be7204e9d99ceb0bf15` -> 404

Root cause in code:
- `api/routers/scorecard.py` wrapper enforces numeric-only `estab_id` via regex (`^\d+$`) before delegating.
- `mv_organizing_scorecard.establishment_id` values are all non-numeric hashes (195,164/195,164 non-numeric).
- Underlying `api/routers/organizing.py::get_scorecard_detail` correctly accepts string IDs and queries by `mv.establishment_id = %s`.

This directly breaks legacy scorecard detail views in OSHA-mode frontend paths that call `/api/scorecard/{estabId}`.

- **Severity:** HIGH
- **Recommended action**
Remove numeric-only gate in `api/routers/scorecard.py` passthrough endpoint so it forwards hashed IDs to `get_scorecard_detail`.

### Point F6 - Frontend-to-API route wiring is broadly consistent after normalization
- **What I investigated**
Parsed frontend JS API calls and compared them to registered FastAPI route paths after normalizing `/api` prefix and path-param names.

- **What the documentation claims**
Route coverage concerns exist in docs (about endpoint counts/presence).

- **What I actually observed**
After normalization, frontend references map to registered API paths except one intentionally dynamic generic path pattern (`/${endpoint}`) in search utility code.
No broad missing-route wiring issue was found.

- **Severity:** LOW
- **Recommended action**
Keep this check as a CI lint step to catch future route drift automatically.

### Point F7 - Key API smoke tests are broadly healthy, with one notable 404 regression path
- **What I investigated**
Ran a targeted smoke suite against high-value API endpoints (scorecard, corporate hierarchy, employers detail, unions, NLRB, WHD, density, projections, public-sector).

- **What the documentation claims**
Recent notes claim major endpoint breakages were fixed (especially corporate hierarchy).

- **What I actually observed**
Most tested endpoints returned 200, including:
- `/api/corporate/hierarchy/stats`
- `/api/corporate/family/{employer_id}`
- `/api/employers/{employer_id}/matches`
- `/api/scorecard/unified*` endpoints
- `/api/admin/match-quality` (slow but successful)

The notable failing path was legacy scorecard detail (`/api/scorecard/{estab_id}`), covered in Point F5.

- **Severity:** LOW
- **Recommended action**
Keep an automated smoke suite for top organizer/admin paths and include status+latency assertions.

### Point E3 - 990/SAM “low match rate” interpretation depends heavily on denominator choice
- **What I investigated**
Recomputed 990 and SAM match coverage for both all F7 employers and current-only (non-historical) F7 employers.

- **What the documentation claims**
Low match-rate figures are often cited (for example ~12% for 990 and ~7.5% for SAM).

- **What I actually observed**
Current distinct matched employers:
- `national_990_f7_matches`: 7,781 distinct F7 employers
- `sam_f7_matches`: 12,255 distinct F7 employers

Coverage by denominator:
- 990 vs all F7 (146,863): **5.30%**
- SAM vs all F7 (146,863): **8.34%**
- 990 vs current F7 (67,552): **10.78%**
- SAM vs current F7 (67,552): **14.45%**

So “low rate” conclusions can shift materially depending on whether historical F7 employers are included.

- **Severity:** MEDIUM
- **Recommended action**
Standardize one published denominator convention (all F7 vs current F7) and report both where strategic interpretation differs.

### Point G2 - `.pytest_cache` directory has permission/access anomaly affecting test hygiene
- **What I investigated**
Followed up on pytest warnings about cache write failures during full test runs.

- **What the documentation claims**
No explicit claim, but test workflow assumes normal local pytest cache behavior.

- **What I actually observed**
Pytest emitted warnings that it could not create cache files under `.pytest_cache`.
Direct filesystem checks show access-denied behavior on that path in this environment:
- `Get-ChildItem ... .pytest_cache` -> access denied
- `icacls ... .pytest_cache` -> access denied

This does not block test execution, but it degrades test tooling reliability (cache, lastfailed, nodeids).

- **Severity:** LOW
- **Recommended action**
Repair permissions on `.pytest_cache` or recreate it with normal ACLs to restore predictable pytest cache behavior.

## Working Queue (Next Points)
- Point I2: Refresh final deliverable sections with newest API and infrastructure findings.

### Point B10 - Cross-document contradiction matrix (PROJECT_STATE vs CLAUDE vs ROADMAP vs live)
- **What I investigated**
Built a consolidated contradiction matrix using exact claims from `PROJECT_STATE.md`, `CLAUDE.md`, and `UNIFIED_ROADMAP_2026_02_17.md`, then verified each against live DB/API checks.

- **What the documentation claims**
Representative contradictory/stale claims include:
1. `PROJECT_STATE.md`: "380 tests. All should pass except ...".
2. `CLAUDE.md`: "380 tests passing".
3. `UNIFIED_ROADMAP_2026_02_17.md`: "Automated tests 359 passing".
4. `UNIFIED_ROADMAP_2026_02_17.md`: "Materialized views | 4".
5. `PROJECT_STATE.md`: "`unified_match_log` | 265,526".
6. `CLAUDE.md`: "`unified_match_log` | 265,526".
7. `UNIFIED_ROADMAP_2026_02_17.md`: "Scorecard rows | 22,389".
8. `UNIFIED_ROADMAP_2026_02_17.md`: F7 relation orphan crisis still active.
9. `PROJECT_STATE.md`: B4 "all 4 batches DONE" while Section 6 still says B4 "IN PROGRESS".
10. `UNIFIED_ROADMAP_2026_02_17.md`: API endpoints "~160 across 17 routers".

- **What I actually observed**
Live evidence:
1. Tests: 441 collected, 2 failed, 439 passed.
2. Materialized views: 6.
3. `unified_match_log`: 1,160,702 total (`active` 215,574; `rejected` 554,541; `superseded` 390,587).
4. Scorecard rows: `mv_organizing_scorecard` 195,164 and `mv_unified_scorecard` 146,863.
5. F7 relation employer orphans: 0.
6. Missing unions: 166 FNUMs, 577 relation rows, 61,743 workers impacted.
7. API routes: 174 `/api/*` routes.
8. B4 status in `PROJECT_STATE.md`: internally contradictory (DONE in header, IN PROGRESS in phase table).

Matrix summary by contradiction type:
- Test count/status drift: 3 docs impacted.
- Inventory/schema count drift: 3 docs impacted.
- Match-log volume drift: 2 docs impacted.
- Scorecard coverage/row-count drift: 2 docs impacted.
- Status contradiction within single doc: `PROJECT_STATE.md`.
- Old-problem narrative still present after fixes: roadmap orphan/corporate-hierarchy sections.

- **Severity:** HIGH
- **Recommended action**
Create one generated "current-state checksum" artifact (tests, route count, table/view/mv counts, key row counts, orphan/missing-union metrics) and reference it from all human docs; forbid manual entry of volatile counts.

## Point I1 - Draft Final Deliverable Sections (Based on Verified Findings So Far)

### Section 1: What Is Actually Working Well
1. OSHA rerun checkpoint accounting is coherent and aligns with live active log totals.
   Evidence: `checkpoints/osha_rerun.json` sums (`HIGH+MEDIUM=97,142`) match OSHA `unified_match_log` active count (`97,142`).
2. Missing-employer orphan issue in `f7_union_employer_relations` appears resolved.
   Evidence: join check returned orphaned employer links = 0.
3. Unified scorecard code path does exclude missing optional factors instead of forcing zero.
   Evidence: denominator counts only non-null optional factors + always-available factors; `factors_available` observed 2..7 and `coverage_pct` 28.6..100.0.
4. Auth enforcement logic works when enabled.
   Evidence: with `DISABLE_AUTH=false`, tested protected endpoints return 401 without token.
5. Corporate hierarchy and unified scorecard stats endpoints are operational.
   Evidence: test-client calls to `/api/corporate/hierarchy/stats` and `/api/scorecard/unified/stats` returned 200 in enabled local API context.
6. Frontend API wiring is mostly aligned to registered backend routes.
   Evidence: normalized comparison of frontend API references against FastAPI route registry found no systemic missing endpoint mappings.

### Section 2: Where Documentation Contradicts Reality
1. `PROJECT_STATE.md` test section claims 380 tests with one expected failure.
   Observation: `pytest` collected 441 tests with 2 failures.
2. `PROJECT_STATE.md` marks B4 OSHA rerun both DONE and IN PROGRESS in different sections.
   Observation: internal contradiction in same document.
3. `PROJECT_STATE.md` inventory/table numbers are stale (for example `unified_match_log` 265,526).
   Observation: live `unified_match_log` is 1,160,702; tables count is 174 not 178.
4. `CLAUDE.md` still reports many stale row counts (`osha_f7_matches`, `whd_f7_matches`, `sam_f7_matches`, `mv_employer_search`, `unified_match_log`).
   Observation: all differ from current live counts.
5. `CLAUDE.md` scorecard narrative is internally inconsistent ("current unified scorecard = mv_organizing_scorecard" while also describing supersession).
   Observation: current unified data is in `mv_unified_scorecard` (146,863 rows), while `mv_organizing_scorecard` is legacy/parallel (195,164 rows).
6. `UNIFIED_ROADMAP_2026_02_17.md` "current state" numbers are now historical (tests, rows, matviews, match-log size, broken-endpoint status).
   Observation: multiple core metrics and statuses no longer match live system.
7. Frontend UI text hard-codes obsolete scorecard row count ("24,841 rows").
   Observation: live scorecard views contain 146,863 and 195,164 rows.
8. Roadmap/current-doc narratives still describe corporate hierarchy and legacy scorecard endpoint issues as resolved at a high level, but legacy `/api/scorecard/{estab_id}` detail path currently fails for list-returned IDs.
   Observation: list endpoint returns hashed IDs while wrapper endpoint rejects non-numeric input.
9. Pipeline docs imply post-matching score inputs are refreshed in order, but current source-flag MVs are stale for major sources (OSHA/SEC).
   Observation: `mv_employer_data_sources` materially diverges from current OSHA table and SEC active-log coverage.

### Section 3: The Three Most Important Things to Fix
1. Legacy scorecard detail endpoint is broken for all current list IDs (HIGH).
   Problem: `/api/scorecard/{estab_id}` rejects non-numeric IDs while list data provides hashed non-numeric IDs.
   Why it matters: OSHA-mode scorecard detail in frontend can fail even when list data loads, breaking a core research workflow.
   Required fix: remove numeric-only gate in scorecard wrapper and pass through IDs to organizing detail handler.
2. Legacy match-table sync logic is structurally inconsistent with rerun truth (HIGH).
   Problem: adapter/rerun code creates drift by (a) collapsing 990 writes via wrong dedupe key, (b) upsert-only writes that keep stale old rows, and (c) missing freshness-update semantics.
   Why it matters: organizer-facing table-backed features can diverge from active rerun outcomes even when matching runs complete successfully.
   Required fix: make legacy writes source-key-faithful, add stale-row reconciliation, and publish robust freshness metadata.
3. NLRB availability flags and NLRB scoring inputs are inconsistent (HIGH).
   Problem: 3,996 employers are flagged `has_nlrb=true` but cannot be scored because no corresponding `nlrb_participants.matched_employer_id` rows exist.
   Why it matters: score coverage is overstated and NLRB signal is silently dropped for thousands of employers.
   Required fix: align NLRB flag and scoring pipelines to one linkage source and enforce integrity checks.

### Section 4: Things Nobody Knew to Ask About
1. Script manifest count drift is now structural, not incidental.
   Observation: `PIPELINE_MANIFEST.md` and `PROJECT_STATE.md` stage totals do not reconcile with actual `scripts/` filesystem layout.
2. API surface has grown to 174 `/api/*` routes while docs still cite ~160.
   Observation: route inventory should be generated automatically to prevent operational blind spots.
3. Security posture can flip from enforced to open by one env flag (`DISABLE_AUTH`) with local default still permissive.
   Observation: this is documented, but risk remains high for accidental insecure run mode outside intended local use.
4. Test tooling hygiene is degraded by `.pytest_cache` access-control anomalies.
   Observation: pytest passes/fails still run, but cache write paths produce warnings and denied-access behavior.
5. A specific adapter implementation (`n990_adapter.write_legacy`) silently drops valid source rows due to incorrect dedupe keying before upsert.
   Observation: dedupe key uses `(target_id, ein)` instead of source identifier (`n990_id`), distorting legacy-table sync.

## Point I2 - Final sections refreshed after contradiction-matrix pass
- **What I investigated**
Reconciled the draft final sections (`Section 1-4`) against newly added contradiction-matrix evidence and API findings.

- **What the documentation claims**
Final deliverable should summarize verified strengths, contradictions, top fixes, and out-of-scope findings.

- **What I actually observed**
Draft final sections now reflect:
- latest live counts (tests, MVs, scorecard rows, match-log totals),
- confirmed API behavior (including scorecard detail regression),
- cross-document drift patterns across all three core docs.

- **Severity:** LOW
- **Recommended action**
Continue adding findings in point-log format, then promote these sections into a clean final report version once investigation depth is sufficient.

### Point C3 - Non-OSHA rerun state is inconsistent between `unified_match_log` and source match tables
- **What I investigated**
Checked rerun evidence for 990/SAM/WHD/SEC/BMF using `unified_match_log` (`run_id`, `created_at`, status counts) and compared that with source `*_f7_matches` table update timestamps and distinct-employer coverage.

- **What the documentation claims**
`PROJECT_STATE.md` header indicates mixed rerun state ("BMF+SEC+990 re-run partial, WHD+SAM need re-run"), while other notes indicate further rerun progress.

- **What I actually observed**
`unified_match_log` shows fresh Feb 18 runs for 990/SAM/WHD/SEC/BMF:
- `det-990-20260218-205339`
- `det-sam-20260218-205338`
- `det-whd-20260218-205337`
- `det-sec-20260218-205336`
- `det-bmf-20260218-195316`

But legacy/source match tables for 990/SAM/WHD were last updated on Feb 17:
- `national_990_f7_matches` max `created_at`: 2026-02-17 07:35:13
- `sam_f7_matches` max `created_at`: 2026-02-17 07:35:32
- `whd_f7_matches` max `created_at`: 2026-02-17 07:34:59

Distinct-target divergences are material:
- 990: active log distinct targets 14,940 vs table distinct F7 7,781
- SAM: 13,475 vs 12,255
- WHD: 15,141 vs 11,297
- OSHA also diverges (31,459 active-log targets vs 42,976 table distinct F7), but in opposite direction

This indicates split truth sources: rerun activity is recorded in the audit log, but source match tables are not consistently synchronized.

- **Severity:** HIGH
- **Recommended action**
Adopt one canonical downstream source (active-log projection or synchronized source match tables), and add a post-rerun parity gate that fails when distinct-target counts diverge beyond a defined threshold.

### Point D3 - NLRB availability flag and NLRB scoring input are out of sync for 3,996 employers
- **What I investigated**
Traced why `mv_unified_scorecard` contains `has_nlrb = true` but `score_nlrb IS NULL` for many rows.

- **What the documentation claims**
Unified scorecard uses source-availability flags and should score factors when data is present.

- **What I actually observed**
Mismatch is real and structural:
- `has_nlrb=true` employers: 7,561
- Of these, 3,996 have `score_nlrb IS NULL`
- These same 3,996 all have active NLRB entries in `unified_match_log`
- But they have **zero** rows in `nlrb_participants` with `matched_employer_id = employer_id`

So NLRB flagging and NLRB score aggregation use different linkage sources:
- Flag source: `unified_match_log` (via `mv_employer_data_sources`)
- Score source: `nlrb_participants` joined to `nlrb_elections` in `build_unified_scorecard.py`

For 3,996 employers, those linkage sets do not intersect, producing false-positive availability flags and suppressed NLRB scores.

- **Severity:** HIGH
- **Recommended action**
Unify NLRB linkage source for both `has_nlrb` and score computation (prefer one canonical match source), then add an integrity check: `has_nlrb=true` should imply score input row existence unless explicitly exempted.

### Point E4 - Legacy match-table sync logic has structural drift bugs (confirmed in adapter code)
- **What I investigated**
Read deterministic runner + adapter write paths to explain why source match tables diverge from `unified_match_log` active state after reruns.

- **What the documentation claims**
Reruns should refresh matching state, and legacy tables are described as backward-compatible outputs.

- **What I actually observed**
Three structural issues in current write logic:
1. `n990_adapter.write_legacy` deduplicates by `(f7_employer_id, ein)` before insert, not by source record (`n990_id`), even though table upsert key is `ON CONFLICT (n990_id)`.
   Impact: many distinct 990 source matches can be dropped before write, suppressing legacy coverage.
2. Legacy table writers (`*_f7_matches`) only perform upserts for current quality matches; they do not remove old rows when a source record no longer matches in current run.
   Impact: stale matches persist, so table state cannot represent current active log truth.
3. Table `created_at` timestamps are not updated on conflict updates.
   Impact: `MAX(created_at)` is not a reliable rerun freshness indicator.

Code evidence:
- `scripts/matching/run_deterministic.py`: writes only HIGH/MEDIUM to legacy tables; no stale-row cleanup pass.
- `scripts/matching/adapters/n990_adapter.py`: harmful dedupe block keyed on `(target_id, ein)`.
- `scripts/matching/adapters/sam_adapter.py`, `scripts/matching/adapters/whd_adapter.py`: upsert-only behavior.

- **Severity:** HIGH
- **Recommended action**
Refactor legacy writes to be source-key faithful and rerun-consistent:
1. Remove harmful pre-dedup in 990 adapter (or dedupe by source id only).
2. Add per-source stale-row reconciliation (delete or supersede) so legacy tables reflect current accepted matches.
3. Add explicit `updated_at` columns (or write-run metadata) for reliable freshness auditing.

### Point E5 - NLRB xref “orphan link” framing is stale; current issue is mostly null-link coverage, not broken non-null links
- **What I investigated**
Recomputed `nlrb_employer_xref` linkage quality by separating null links from true non-null orphan links.

- **What the documentation claims**
Roadmap-era language describes substantial orphan-link problems in NLRB cross-reference.

- **What I actually observed**
Current `nlrb_employer_xref` breakdown:
- total rows: 179,275
- `f7_employer_id IS NULL`: 161,759
- non-null links: 17,516
- true non-null orphans (non-null ID missing in `f7_employers_deduped`): **1**
- non-null resolved links: 17,515

So the dominant gap is unmatched/null linkage coverage, not broken foreign-key-like links among non-null IDs.

- **Severity:** MEDIUM
- **Recommended action**
Update documentation wording: distinguish “unmatched (null)” from “orphaned (non-null broken)” links so remediation work targets the correct problem.

## Working Queue (Next Points)
- Point I4: refresh final top-3 priorities after adding E4 adapter-sync findings.

## Point I4 - Final priorities refreshed after E4/E5 matching-pipeline deep dive
- **What I investigated**
Re-evaluated priority ordering after identifying adapter-level sync defects and clarifying NLRB xref failure mode.

- **What the documentation claims**
Top priorities should reflect highest-impact issues for organizer-facing correctness and trust.

- **What I actually observed**
Top-priority set remains stable, with stronger evidence behind pipeline correctness risks:
- scorecard detail path break (F5),
- legacy sync defects (E4),
- NLRB flag/score mismatch (D3).
NLRB xref issue (E5) is reframed as low match coverage/null-link gap rather than widespread broken non-null links.

- **Severity:** LOW
- **Recommended action**
Keep priority ordering, but re-scope NLRB xref remediation toward match coverage expansion.

### Point G3 - MV freshness ordering is broken: `mv_employer_data_sources` is stale vs current OSHA/SEC linkage state
- **What I investigated**
Compared `mv_employer_data_sources` flags against current source tables/logs to identify which refresh step is stale.

- **What the documentation claims**
Pipeline ordering shows `build_employer_data_sources` then `build_unified_scorecard` after matching updates.

- **What I actually observed**
Flag parity is uneven:
- `has_whd`: matches table exactly (11,297)
- `has_990`: matches table exactly (7,781)
- `has_sam`: off by 1 (12,254 vs 12,255)
- `has_osha`: major mismatch (32,774 vs 42,976 distinct in `osha_f7_matches`)
- `has_sec`: major mismatch (1,612 in MV vs 2,749 distinct active SEC targets in `unified_match_log`)

Additional OSHA inconsistencies:
- 13,846 employers present in `osha_f7_matches` are `has_osha=false` in MV.
- 3,644 MV rows have `has_osha=true` but no current `osha_f7_matches` row.

This pattern strongly indicates `mv_employer_data_sources` was not rebuilt after the latest OSHA/SEC changes (or is built from mixed stale/current sources), and `mv_unified_scorecard` inherited stale source flags.

- **Severity:** HIGH
- **Recommended action**
Enforce refresh dependency after matching reruns:
1. refresh/rebuild `mv_employer_data_sources`
2. then refresh/rebuild `mv_unified_scorecard`
3. run automated parity checks (`has_*` counts vs canonical source counts) before marking rerun complete.

### Point F8 - Frontend default flow routes users directly into the broken legacy scorecard detail path
- **What I investigated**
Traced `files/js/scorecard.js` selection/detail code to determine whether the F5 endpoint bug affects default user behavior.

- **What the documentation claims**
Frontend unified scorecard is wired up, while legacy scorecard remains available for backward compatibility.

- **What I actually observed**
Frontend code defaults to OSHA mode:
- `scorecardDataSource` initialized as `'osha'`.

In non-unified and non-sector mode, detail fetch uses:
- ```${API_BASE}/scorecard/${estabId}```

This is exactly the endpoint path identified in F5 as broken for hashed IDs.
Therefore, default scorecard flow can hit the 404 path unless users explicitly switch to unified mode.

Code evidence:
- `files/js/scorecard.js`: default source declaration and detail fetch branch for OSHA mode.

- **Severity:** HIGH
- **Recommended action**
Fix the backend endpoint (F5) and, as defense-in-depth, prefer unified detail endpoint when available or add frontend fallback to `/api/organizing/scorecard/{estabId}`.

## Working Queue (Next Points)
- Point I5: refresh final contradiction and top-fixes sections with G3/E4 evidence (adapter logic + MV freshness).

## Point I5 - Final sections refreshed with G3/E4 evidence
- **What I investigated**
Integrated latest adapter and MV-freshness findings into draft final deliverable sections.

- **What the documentation claims**
Final sections should track verified highest-impact contradictions and risks.

- **What I actually observed**
Sections now explicitly include:
- stale `mv_employer_data_sources` parity drift (OSHA/SEC),
- adapter-level row-loss risk in 990 legacy writer,
- reinforced priority on pipeline truth-source consistency.

- **Severity:** LOW
- **Recommended action**
Proceed to final-clean report generation once no further critical findings are emerging from additional spot checks.

## Working Queue (Next Points)
- Point H1: add a dedicated “Findings Outside the Audit Scope” subsection with the strongest cross-cutting findings discovered so far.

## Point I3 - Final top priorities refreshed after C3/D3
- **What I investigated**
Re-ranked Section 3 priorities using newly verified high-impact findings from C3 and D3.

- **What the documentation claims**
Top three fixes should reflect highest real-world impact on organizer-facing decisions and platform trust.

- **What I actually observed**
Section 3 now prioritizes:
1. Legacy scorecard detail endpoint break.
2. Split truth between rerun log state and source match tables.
3. NLRB flag/score pipeline mismatch affecting 3,996 employers.

- **Severity:** LOW
- **Recommended action**
Keep reranking as additional high-severity findings are verified; freeze priorities only when final audit pass is complete.

## Working Queue (Next Points)
- Point E4: investigate why 990/SAM/WHD source tables are not synchronized to latest Feb 18 run_ids (code-path check in deterministic runner/adapters).

### Point H1 - Findings Outside the Audit Scope (explicitly cataloged)
- **What I investigated**
Collected cross-cutting issues discovered opportunistically that are not confined to any single audit area.

- **What the documentation claims**
Outside-scope findings should be reported explicitly.

- **What I actually observed**
Outside-scope findings identified:
1. Test tooling filesystem anomaly:
   `.pytest_cache` access-control behavior causes cache write warnings and weakens test-run ergonomics.
2. Documentation governance gap:
   Volatile operational numbers are manually duplicated across multiple docs and repeatedly drift out of sync.
3. Script inventory governance gap:
   Manifest/stage counts no longer reconcile with filesystem reality.
4. API inventory governance gap:
   Route surface (174 `/api/*` paths) has no generated authoritative artifact in docs.

- **Severity:** MEDIUM
- **Recommended action**
Ship a generated telemetry bundle (script inventory, route inventory, key DB metrics, test summary) and consume it from docs/UI to eliminate manual drift.

## Working Queue (Current)
- Point I6: consolidate duplicate historical queue blocks and produce a clean final-cut audit document from the working log.
