# FULL_AUDIT_CODEX_2026-02-26

## 1) Executive Summary
The platform is functional and substantial, but there is still drift between scoring specification, implemented scoring math, and organizer-facing explanation text. Priority-tier outputs can be driven by only 3-4 factors, and top-ranked employers often lack OSHA/WHD/contracts evidence. The NLRB nearby 25-mile component remains unimplemented in scoring SQL. Similarity is computed but set to weight 0 in weighted score, while explanation text still advertises 2x similarity weight. Matching quality remains mixed: high-confidence exact-style matches are often plausible, but low/mid-confidence fuzzy lanes still contain clear false positives. Frontend architecture is generally solid (TanStack Query + centralized API client + error boundary), but explanatory copy and semantics need alignment with backend behavior. Security posture for admin endpoints is fail-closed when auth is disabled, but `.env` currently has `DISABLE_AUTH=true` and plaintext secrets. Deployment artifacts are usable baseline infrastructure, not turnkey for clean-room rebuilds of full production data pipelines.

## 2) Shared Overlap Zone (OQ1-OQ10)

### OQ1: Priority Tier Spot Check (5 Employers)
Source evidence: `docs/audit_artifacts_round3/oq1_priority_samples_2026-02-26.csv`

1. First Student, Inc (IL), `9653fdb31c7d1624`, score `10.00`, factors `3`.
   - Drivers: `score_nlrb=10`, `score_union_proximity=10`, `score_size=10`.
   - Assessment: plausible target, but max score from only 3 factors is fragile.
2. Dignity Health Mercy Medical Center Merced (CA), `c62f188545b9fcbd`, score `9.85`, factors `4`.
   - Drivers: NLRB + proximity + size + growth.
3. Alta Bates Summit Medical Center (CA), `f9180dffbc3d2d1d`, score `9.85`, factors `4`.
   - Same pattern.
4. Columbia Memorial Hospital (OR), `b8e61dd23de1f9d1`, score `9.84`, factors `4`.
   - NLRB is null; still near-top tier.
5. ROBERT WOOD JOHNSON (NJ), `b35bb589dd6b4188`, score `9.84`, factors `4`.
   - Strong score with limited factor diversity.

### OQ2: Match Accuracy Spot Check (20 Matches)
Source evidence: `docs/audit_artifacts_round3/oq2_match_samples_2026-02-26.csv`

- OSHA sample contained several clear false positives in low-confidence fuzzy rows.
- NLRB sample was mostly plausible/correct in high-confidence rows.
- WHD/SAM sample included multiple clear mismatches in low-confidence fuzzy rows.
- Splink near 0.70 sample was mostly plausible in the selected rows.

### OQ3: React Frontend ↔ API Contract (5 Features)
1. Employer search: frontend uses `/api/employers/unified-search` with `name`; API contract matches.
2. Employer profile: hooks and endpoints align for core cards.
3. Scoring breakdown: explanation text and true weighting drift (similarity shown as weighted but disabled in score math).
4. Union profile: financial/membership cards align with endpoint structure.
5. Targets page: `/api/master/non-union-targets` and `/api/master/stats` contract aligns.

### OQ4: Data Freshness and View Staleness
- `data_source_freshness` exists and populates correctly from maintenance script.
- `data_freshness` table does not exist.
- Organizing MV refresh uses `CONCURRENTLY`.
- View probe run found no broken public views/materialized views (`ok 130, bad 0`).

### OQ5: Incomplete Source Re-runs Impact
- `run_deterministic.py` has batch/checkpoint resume (`--batch N/M`, checkpoint JSON).
- WHD/SAM reruns are operable in batches, but no robust automated OOM recovery strategy beyond chunking/manual rerun control.

### OQ6: Scoring Factors Current State (All 8)
- OSHA: implemented with normalization + decay + severity bonus.
- NLRB: own-history/ULP logic present; nearby 25-mile momentum not implemented (explicit TODO).
- WHD: tiered + decay present.
- Contracts: federal-obligations-only tiers (not full federal+state+local design).
- Density semantics differ from spec (proxy via union proximity/grouping behavior).
- Size: linear ramp to 500 and plateau, no high-end taper.
- Similarity: computed but excluded from weighted score/factors_available.
- Growth vs financial: financial no longer direct growth alias; separate logic exists.

### OQ7: Test Suite Reality Check
- Backend tests: `914 passed, 3 skipped, 1 warning`.
- Coverage command unavailable because `pytest-cov` missing.
- Frontend tests failed to start in this environment (`spawn EPERM`).

### OQ8: Database Cleanup Opportunity
- Large cleanup signal: many objects have zero/low code references (heuristic scan).
- Sector API still depends on generated dynamic views and returns "not yet created" when absent.

### OQ9: Single Biggest Problem
Ranking trust drift before organizer use: score semantics, missing key factor implementation, and explanation mismatch can produce high-confidence-looking outputs with weak underlying evidence diversity.

### OQ10: Previous Audit Follow-Up
- Multiple prior items are partially addressed (NAICS scripts, cleanup scripts, geocoding scripts, comparables linkage).
- Key unresolved items remain (NLRB nearby implementation and weighting/explanation parity).

## 3) Investigation Areas

### Area 1: Scoring Pipeline
Key findings in `scripts/scoring/build_unified_scorecard.py`:
- NLRB nearby TODO not implemented.
- Similarity factor computed but weight 0 in final weighted score.
- Priority/Strong enforce `factors_available >= 3`.
- Contracts factor is federal-only.
- Weighted denominator uses `NULLIF` guard.

### Area 2: React Frontend Architecture
- 97 JS/JSX files, ~7359 LOC; largest component ~209 LOC.
- Single Zustand store (`authStore`) plus URL/query-hook state.
- Central API client and TanStack Query pattern is broadly consistent.
- Error boundary present globally.

### Area 3: API Endpoint Audit
Full inventory artifacts:
- `docs/audit_artifacts_round3/endpoint_inventory_2026-02-26.txt`
- `docs/audit_artifacts_round3/endpoint_auth_matrix_2026-02-26.json`
- `docs/audit_artifacts_round3/endpoint_auth_matrix_2026-02-26.csv`

Expanded metrics:
- Total routes: `193`
- `require_admin`: `9`
- `require_auth`: `3`
- Dynamic SQL f-string routes: `49`
- Dynamic SQL routes without explicit auth dependency: `47`

### Area 4: Test Coverage Deep Dive
- Test files: 50
- Tests discovered: 917
- Total asserts: 1736
- Status-code-only asserts: 256
- Skip usage: 52
- Artifact: `docs/audit_artifacts_round3/test_quality_scan_2026-02-26.json`

### Area 5: Deployment Readiness
- Docker artifacts are functional baseline, not stubs.
- Compose defaults include `DISABLE_AUTH=true`.
- `.env` includes plaintext credentials/API key; `.env` is gitignored.
- Hardcoded local paths still present across ETL and analysis scripts.

### Area 6: Code Quality and Maintenance
- Heuristic DB object scan indicates substantial legacy/low-reference footprint.
- Pipeline ordering docs include stale paths in places; actual script locations differ for two stages.
- Scripts with destructive rebuild behavior can race if run concurrently.

## 4) Bug List
1. Similarity weight drift: score math disables similarity while explanations claim 2x.
2. NLRB nearby 25-mile factor remains unimplemented.
3. Contracts factor semantics narrower than spec (federal-only behavior).
4. Legacy `/api/employers/search` can return broad sets when filters are missing/mistyped.
5. Active `DISABLE_AUTH=true` with local plaintext secrets in `.env`.
6. Hardcoded local paths reduce portability.

## 5) Architecture Concerns
- Spec/implementation/frontend explanation drift.
- Priority ranking can be dominated by limited factors.
- Dynamic sector-view infrastructure introduces runtime partial availability.
- Large dynamic SQL surface area with mostly public endpoints.

## 6) Missing Test Coverage (Top Gaps)
1. End-to-end scoring spec parity tests across all factors.
2. Regression tests for explanation-to-weight parity.
3. NLRB nearby momentum behavior tests.
4. Match precision acceptance tests by source/method/confidence.
5. Legacy search param mismatch regression.
6. Auth-mode integration tests for disabled-auth safety behavior.
7. MV refresh observability tests.
8. Pipeline race-order tests.
9. Portable ETL execution tests without machine-specific paths.
10. Reliable frontend integration test execution in CI/dev.

## 7) Deployment Blockers
- Scoring trust/parity issues.
- Auth disabled by default in active local config/compose defaults.
- Secret handling practices in env files.
- Incomplete high-confidence rerun QA for certain sources.
- Coverage tooling gap (`pytest-cov` missing).
- Frontend test runtime failure in current environment.

## 8) Recommended Priority List (Top 10)
1. Align scoring code/spec/frontend explanations.
2. Implement or de-scope NLRB nearby 25-mile factor consistently.
3. Resolve similarity-weight mismatch decisively.
4. Expand match-quality QA and thresholds by source.
5. Harden legacy search endpoint behavior or retire it.
6. Make auth-enabled mode the default for deployable environments.
7. Remove hardcoded local paths from active scripts.
8. Add coverage tooling and gate critical files.
9. Add MV refresh metadata/observability.
10. Fix frontend test execution path.

## 9) Expansion Addendum (Requested Follow-Up)

### A) Endpoint Matrix Expansion
Completed with per-route auth/query/dynamic-sql metadata and summary metrics.

### B) Match Sampling Expansion
Completed stratified sample:
- Artifact: `docs/audit_artifacts_round3/oq2_stratified_samples_2026-02-26.csv`
- Rows: 65
- Heuristic summary: likely_correct 34, plausible 2, uncertain 22, likely_wrong 7

### C) DB Dependency/Orphan Expansion
Completed heuristic object-reference scan:
- Artifact: `docs/audit_artifacts_round3/db_object_reference_scan_2026-02-26.json`
- Public objects scanned: 322
- Zero refs: 151
- Low refs (<=2): 34

### D) Pipeline Run-Order/Race Expansion
Completed script dependency scan artifact:
- `docs/audit_artifacts_round3/pipeline_dependency_scan_2026-02-26.json`

Notable operational risk:
- `build_employer_groups.py` rebuild flow uses delete/reset style writes.
- `compute_gower_similarity.py` truncates and rebuilds comparables.
- Running these concurrently with scoring builds can create transient inconsistency windows.

### E) Test-Quality Expansion
Completed static test-quality scan artifact:
- `docs/audit_artifacts_round3/test_quality_scan_2026-02-26.json`

## 10) Notes
No production code logic was changed as part of this audit. Only analysis outputs/artifacts were added.
