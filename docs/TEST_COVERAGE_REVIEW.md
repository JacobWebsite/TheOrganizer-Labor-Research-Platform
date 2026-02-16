# Test Coverage Review (Focused Task 5)

I reviewed the full `tests/` folder.

Important note:
- The instruction says "165 tests", but the current tree has 119 explicit `def test_*` functions.
- This means the 165 number is outdated.

## 1) What the current tests actually cover

### API behavior
- `tests/test_api.py`: core endpoint smoke tests, scorecard endpoints, siblings/comparables, NLRB patterns, basic error paths.
- `tests/test_auth.py`: register/login/refresh/me flows, role checks, auth-disabled behavior.

### Data integrity and DB regression checks
- `tests/test_data_integrity.py`: row-count thresholds, match-rate floors, orphan checks, materialized view checks, schema expectations.
- `tests/test_phase3_matching.py`, `tests/test_phase4_integration.py`, `tests/test_occupation_integration.py`, `tests/test_similarity_fallback.py`, `tests/test_temporal_decay.py`, `tests/test_score_versioning.py`, `tests/test_employer_groups.py`: mostly DB-schema and DB-content regression checks.

### Scoring and matching logic
- `tests/test_scoring.py`: helper scoring functions and scorecard shape/range checks.
- `tests/test_matching.py`: normalizer, address helpers, fuzzy score math, match dataclass behavior, some DB match-rate checks.
- `tests/test_naics_hierarchy_scoring.py`, `tests/test_propensity_model.py`: feature/scoring math and model table checks.

### Frontend static safety checks
- `tests/test_frontend_xss_regressions.py`: string-based checks for specific sanitized patterns in frontend JS files.

## 2) What is NOT covered

### Endpoint coverage gaps
- Frontend references many endpoints, but only a subset is tested.
- Large areas with little/no API test coverage include:
- Most `public-sector` endpoints.
- Most corporate/unified/detail variants.
- Many trends and analytics routes.
- Route-level authorization matrix coverage is very thin outside auth module.

### Matching pipeline behavior gaps
- No robust tests for tie-breaking correctness across multiple close candidates.
- No tests for city/state collision edge cases in batch mode.
- No tests for malformed scenario config (bad table/column names).
- No tests for failure metrics when a matcher tier throws errors.

### Frontend behavior gaps
- No browser/UI integration tests for user flows.
- No tests for inline `onclick` behavior and event wiring.
- No tests for mixed 8-factor vs 9-factor score display consistency.

### Security coverage gaps
- Dynamic SQL safety checks are not covered in matching pipeline files.
- No tests ensuring dangerous config filter strings are rejected.

## 3) Tests that may pass but test the wrong thing

1) `tests/test_name_normalization.py` tests `src/python/matching/name_normalization.py`, not the active matcher normalizer path used in `scripts/matching/normalizer.py`.
- Risk: suite passes while production matching behavior still regresses.

2) Several tests validate only "key exists" and status code, not content correctness.
- Example pattern in `tests/test_api.py`: many checks only require 200 + minimal keys.
- Risk: logically wrong responses can still pass.

3) Some static frontend tests assert exact source-code strings.
- `tests/test_frontend_xss_regressions.py`
- Risk: harmless refactors can break tests, while real XSS in other code paths is missed.

## 4) Fragile tests that depend on specific data

Many tests are environment/data fragile:
- Hard-coded row-count thresholds in `tests/test_data_integrity.py`, `tests/test_phase4_integration.py`, `tests/test_scoring.py`.
- Assumes large, specific production-like DB content exists.
- Some tests can skip if tables are missing, which hides real regressions.

Also:
- Tests require PostgreSQL with specific schema and data volume.
- In this environment, pytest could not be run (`pytest`/`py -m pytest` unavailable earlier), so runtime health of the suite could not be verified.

## 5) Tests that should be added

1) Endpoint contract tests from OpenAPI schema
- Validate full response schema, not only key presence.

2) Full route authorization tests
- Verify public vs protected behavior for all routers when auth is enabled.

3) Matching correctness tests with synthetic fixtures
- Tie-breaks, unicode edge cases, city/state collisions, and bad-config rejection.

4) SQL-safety tests
- Assert scenario configs cannot inject unsafe `source_filter/target_filter`.

5) Frontend integration tests
- Playwright/Cypress flows for search, scorecard, deep dive, and modal errors.

6) Cross-layer scoring consistency tests
- Ensure backend factor list, frontend factor list, and docs all agree (8 vs 9 factor issue).

## Bottom line

The test suite is useful for regression alarms on data and major API paths, but it is not broad enough for:
- complete endpoint coverage,
- strong security validation,
- frontend behavior confidence,
- and robust matching correctness under edge conditions.
