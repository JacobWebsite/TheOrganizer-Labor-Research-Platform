# Parallel PR Bundle Plan

Objective: minimize merge conflicts with in-flight Phase 1 implementation.

## Bundle 1: Frontend Safety
- Files:
  - `files/js/detail.js`
  - `files/js/modals.js`
  - `files/js/scorecard.js`
  - `tests/test_frontend_xss_regressions.py`
  - `scripts/analysis/prioritize_innerhtml_api_risk.py`
  - `docs/PARALLEL_INNERHTML_API_RISK_PRIORITY.md`
- Notes:
  - Keep isolated to frontend JS and static regression checks.

## Bundle 2: Password Bug Tooling + Targeted Fixes
- Files:
  - `scripts/analysis/find_literal_password_bug.py`
  - `scripts/analysis/fix_literal_password_bug.py`
  - `docs/PARALLEL_PHASE1_PASSWORD_AUDIT.md`
  - 20 patched scripts in batch/discovery/etl/import
- Notes:
  - Separate tooling from bulk script edits if needed for easier review.

## Bundle 3: API Contract and Scorecard Parity
- Files:
  - `api/routers/organizing.py` (adds `federal_contract_count` in list payload)
  - `tests/test_scorecard_contract_field_parity.py`
- Notes:
  - Small API surface change with direct compatibility test.

## Bundle 4: Validation/Drift/Perf Instrumentation
- Files:
  - `scripts/analysis/check_frontend_api_alignment.py`
  - `scripts/analysis/check_router_docs_drift.py`
  - `scripts/analysis/benchmark_endpoints.py`
  - `scripts/analysis/capture_query_plans.py`
  - `scripts/analysis/phase1_merge_validator.py`
  - `docs/PARALLEL_FRONTEND_API_AUDIT.md`
  - `docs/PARALLEL_ROUTER_DOCS_DRIFT.md`
  - `docs/PARALLEL_QUERY_PLAN_BASELINE.md`
  - `docs/PHASE1_MERGE_VALIDATION_REPORT.md`

## Bundle 5: Phase 3 Scaffolding
- Files:
  - `src/python/matching/name_normalization.py`
  - `src/python/matching/integration_stubs.py`
  - `src/python/matching/__init__.py`
  - `tests/test_name_normalization.py`
  - `docs/PHASE3_NORMALIZATION_INTEGRATION_CHECKLIST.md`

## Recommended Commit Sequence
1. Bundle 1
2. Bundle 3
3. Bundle 2
4. Bundle 4
5. Bundle 5

## Rebase/Merge Tips
- Re-run `scripts/analysis/phase1_merge_validator.py` after each rebase.
- If conflicts occur in `files/js/scorecard.js`, preserve:
  - `breakdown.geographic` mini-score key
  - precomputed `nlrbDescription` and sanitized sector stats block.

