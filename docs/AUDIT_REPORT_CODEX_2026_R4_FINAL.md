# Audit Report (Codex) - 2026 Round 4 (Final Cut)
Date: 2026-02-19
Project: labor-data-project
Prompt: `INDEPENDENT_AI_AUDIT_PROMPT_2026-02-18.md`

## Scope and method
- Read and cross-checked: `PROJECT_STATE.md`, `CLAUDE.md`, `UNIFIED_ROADMAP_2026_02_17.md`, `PIPELINE_MANIFEST.md`.
- Verified claims with live PostgreSQL queries via `db_config.get_connection()`.
- Ran test suite with `python -m pytest tests/ -q`.
- Enumerated FastAPI routes from `api.main:app` and exercised critical endpoints with `TestClient`.
- Traced scoring/matching/frontend code paths for root cause where mismatches appeared.

## Findings

### Finding 1 - Test status in docs is stale and contradictory
- **What I investigated**
Compared documented test status in core docs to live test run.
- **What the documentation claims**
`PROJECT_STATE.md` and `CLAUDE.md` describe 380 tests (with one expected failure). `UNIFIED_ROADMAP_2026_02_17.md` references 359 passing.
- **What I actually observed**
`python -m pytest tests/ -q` collected 441 tests: 439 passed, 2 failed.
- **Severity:** HIGH
- **Recommended action**
Stop hand-maintaining test totals in multiple docs. Publish one generated test summary artifact and link to it.

### Finding 2 - `PROJECT_STATE.md` has internal Phase B4 status conflict
- **What I investigated**
Compared B4 status claims inside the same file.
- **What the documentation claims**
Header indicates B4 all batches done; Section 6 marks B4 in progress.
- **What I actually observed**
Both claims coexist in current file.
- **Severity:** MEDIUM
- **Recommended action**
Keep one timestamped status source per phase and archive superseded session notes.

### Finding 3 - Core inventory counts are stale in docs
- **What I investigated**
Validated table/view/MV/count metrics against live DB.
- **What the documentation claims**
Examples: materialized views=4 (roadmap), `unified_match_log`=265,526 (PROJECT_STATE/CLAUDE), scorecard rows=22,389 (roadmap).
- **What I actually observed**
Live DB: tables=174, views=186, materialized views=6, `unified_match_log`=1,160,702, `mv_organizing_scorecard`=195,164, `mv_unified_scorecard`=146,863.
- **Severity:** HIGH
- **Recommended action**
Generate a daily current-state checksum (counts + key health metrics) and reference it from all docs.

### Finding 4 - Legacy scorecard detail endpoint is broken for current IDs
- **What I investigated**
Tested `/api/scorecard/` list and `/api/scorecard/{estab_id}` detail; traced `api/routers/scorecard.py`.
- **What the documentation claims**
Legacy scorecard namespace is backward-compatible.
- **What I actually observed**
List returns non-numeric hashed `establishment_id`, but detail endpoint hard-rejects non-numeric IDs and returns 404.
- **Severity:** HIGH
- **Recommended action**
Remove numeric regex guard in scorecard wrapper and pass through string IDs to organizing detail handler.

### Finding 5 - Default frontend scorecard flow hits the broken legacy detail path
- **What I investigated**
Traced `files/js/scorecard.js` selection/detail logic.
- **What the documentation claims**
Frontend unified scorecard wiring is complete.
- **What I actually observed**
Default source is OSHA mode; detail fetch path is `${API_BASE}/scorecard/${estabId}`, which is the broken endpoint from Finding 4.
- **Severity:** HIGH
- **Recommended action**
Fix backend endpoint and add frontend fallback to unified/organizing detail endpoint.

### Finding 6 - Matching reruns have split truth sources
- **What I investigated**
Compared `unified_match_log` run evidence vs source match tables for 990/SAM/WHD/OSHA.
- **What the documentation claims**
Reruns are described as partial/complete in session notes.
- **What I actually observed**
Fresh Feb 18 run_ids exist in `unified_match_log`, but `national_990_f7_matches`, `sam_f7_matches`, `whd_f7_matches` max `created_at` remains Feb 17 and diverges from active-log distinct coverage.
- **Severity:** HIGH
- **Recommended action**
Define one canonical downstream truth source and enforce parity gates after reruns.

### Finding 7 - Adapter write logic causes legacy-table drift
- **What I investigated**
Reviewed runner and adapters: `run_deterministic.py`, `adapters/n990_adapter.py`, `adapters/sam_adapter.py`, `adapters/whd_adapter.py`.
- **What the documentation claims**
Legacy tables are backward-compatible outputs of deterministic reruns.
- **What I actually observed**
`n990_adapter.write_legacy` dedupes by `(f7_employer_id, ein)` before upsert on `n990_id`, which drops valid source rows. Writers are upsert-only and do not reconcile stale rows.
- **Severity:** HIGH
- **Recommended action**
Use source-key-faithful writes, add stale-row reconciliation, and add reliable refresh metadata.

### Finding 8 - `mv_employer_data_sources` is stale against current OSHA/SEC state
- **What I investigated**
Compared MV flags to source table/log distinct counts.
- **What the documentation claims**
Pipeline sequence implies post-match MV refresh.
- **What I actually observed**
Major parity failure: `has_osha` 32,774 in MV vs 42,976 in `osha_f7_matches`; `has_sec` 1,612 in MV vs 2,749 active SEC targets in log.
- **Severity:** HIGH
- **Recommended action**
Enforce refresh order: `mv_employer_data_sources` then `mv_unified_scorecard`, with automated parity checks.

### Finding 9 - NLRB flag and score pipelines are inconsistent
- **What I investigated**
Investigated `has_nlrb=true` with `score_nlrb IS NULL`.
- **What the documentation claims**
Availability flags should reflect factor score availability.
- **What I actually observed**
3,996 employers have active NLRB log links and `has_nlrb=true` but zero `nlrb_participants.matched_employer_id` rows, so no NLRB score can be computed.
- **Severity:** HIGH
- **Recommended action**
Use one canonical NLRB linkage source for both flags and scoring; add integrity checks.

### Finding 10 - Missing unions issue remains real and concentrated
- **What I investigated**
Recomputed missing union-file-number links against `unions_master`.
- **What the documentation claims**
Current issue: 166 missing unions covering 61,743 workers.
- **What I actually observed**
Confirmed: 166 missing FNUMs, 577 affected relation rows, 544 employers, 61,743 workers. Largest concentration includes FNUM `12590`.
- **Severity:** HIGH
- **Recommended action**
Prioritize remaps by worker impact; track resolved coverage per batch.

### Finding 11 - F7 employer-orphan issue is resolved, but roadmap still treats it as active
- **What I investigated**
Checked `f7_union_employer_relations` joins against `f7_employers_deduped`.
- **What the documentation claims**
Roadmap critical section still frames this as an active 50% orphan crisis.
- **What I actually observed**
Employer-link orphans are 0 in current state.
- **Severity:** MEDIUM
- **Recommended action**
Relabel roadmap as dated snapshot and move active issue tracking to generated status artifacts.

### Finding 12 - NLRB xref problem is mostly null-link coverage, not broken non-null links
- **What I investigated**
Separated null links from true non-null broken links in `nlrb_employer_xref`.
- **What the documentation claims**
Roadmap-era language emphasizes orphaned link breakage.
- **What I actually observed**
`nlrb_employer_xref`: 161,759 null links, 17,516 non-null links, only 1 non-null orphan.
- **Severity:** MEDIUM
- **Recommended action**
Reframe remediation toward coverage expansion (null reduction), not orphan repair.

### Finding 13 - API endpoint surface is larger than documented
- **What I investigated**
Enumerated registered API routes from FastAPI app.
- **What the documentation claims**
Roadmap references ~160 endpoints.
- **What I actually observed**
Current `/api/*` route count is 174.
- **Severity:** LOW
- **Recommended action**
Auto-generate route inventory into docs.

### Finding 14 - API smoke checks are mostly healthy, with one major path failure
- **What I investigated**
Smoke-tested critical endpoints (scorecard, hierarchy, employers, unions, NLRB, WHD, density, projections).
- **What the documentation claims**
Recent fixes restored key API functionality.
- **What I actually observed**
Most tested endpoints returned 200. Major exception remains legacy scorecard detail path (Finding 4).
- **Severity:** LOW
- **Recommended action**
Keep endpoint smoke tests in CI with status and latency thresholds.

### Finding 15 - Security enforcement works when enabled, but local default remains permissive
- **What I investigated**
Exercised protected endpoints under `DISABLE_AUTH=true` and `DISABLE_AUTH=false`.
- **What the documentation claims**
Auth hardening is complete with default enforcement unless explicitly disabled.
- **What I actually observed**
Enforcement works when enabled (401 without token), but local `.env` uses `DISABLE_AUTH=true`.
- **Severity:** MEDIUM
- **Recommended action**
Treat auth-disabled mode as explicit local-debug profile only.

### Finding 16 - Script manifest counts no longer reconcile with filesystem
- **What I investigated**
Compared `PIPELINE_MANIFEST.md` counts vs actual `scripts/` file counts.
- **What the documentation claims**
Exact script totals by stage and overall active counts.
- **What I actually observed**
Multiple stage totals and aggregate counts are inconsistent with current files.
- **Severity:** MEDIUM
- **Recommended action**
Generate stage counts from filesystem and annotate with allowlisted active scripts.

### Finding 17 - 990/SAM match-rate interpretation varies materially by denominator
- **What I investigated**
Calculated match coverage against all F7 vs current-only F7.
- **What the documentation claims**
Common references cite low rates (for example ~12% and ~7.5%).
- **What I actually observed**
Coverage shifts significantly by denominator (example: 990 at 5.30% all-F7 vs 10.78% current-F7).
- **Severity:** MEDIUM
- **Recommended action**
Publish both denominators and standardize which one is used in decision dashboards.

### Finding 18 - `.pytest_cache` access anomaly affects test hygiene
- **What I investigated**
Followed pytest warnings and path ACL behavior.
- **What the documentation claims**
No explicit claim.
- **What I actually observed**
Cache write warnings and access-denied behavior on `.pytest_cache` path in this environment.
- **Severity:** LOW
- **Recommended action**
Repair/recreate cache path permissions.

## Findings Outside the Audit Scope
- Manual-metric governance is the root cause of repeated doc drift across all major status artifacts.
- Lack of generated operational telemetry (tests/routes/key counts) increases AI-session compounding error risk.
- Adapter-level legacy sync defects are architectural, not one-off data issues.

## Section 1: What Is Actually Working Well
1. OSHA batch checkpoint accounting is internally consistent and aligns with active-log HIGH+MEDIUM totals.
2. F7 employer-link orphan issue in `f7_union_employer_relations` is resolved (0 orphans).
3. Unified scoring formula does exclude missing optional factors from denominator.
4. Corporate hierarchy and unified scorecard stats endpoints respond successfully in smoke tests.
5. Auth enforcement logic works when `DISABLE_AUTH=false`.

## Section 2: Where Documentation Contradicts Reality
1. Test totals/status differ across docs and all are stale vs live run.
2. B4 status is internally contradictory in `PROJECT_STATE.md`.
3. Match-log, scorecard, and MV counts are stale in multiple docs.
4. Roadmap still frames resolved orphan/hierarchy issues as active current-state problems.
5. Endpoint count in roadmap is below current registered route surface.
6. Manifest/script counts drift from filesystem reality.
7. Frontend hard-coded row-count text is obsolete.

## Section 3: The Three Most Important Things to Fix
1. Legacy scorecard detail endpoint break (`/api/scorecard/{estab_id}` with hashed IDs).
2. Legacy match-table sync architecture drift (adapter write logic + stale-row reconciliation gap).
3. NLRB flag/score mismatch (3,996 employers flagged but unscorable).

## Section 4: Things Nobody Knew to Ask About
1. `n990_adapter.write_legacy` uses a wrong dedupe key that can silently drop valid source rows before upsert.
2. `mv_employer_data_sources` stale parity drift (OSHA/SEC) can invalidate coverage perceptions even when raw matches changed.
3. NLRB xref issue is primarily null-link coverage, not non-null orphan breakage.
4. Test tooling path permissions can degrade local QA signal quality.
