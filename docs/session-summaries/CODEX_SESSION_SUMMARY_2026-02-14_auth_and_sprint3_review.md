# Codex Session Summary - February 14, 2026

## Scope
Reviewed:
- `api/routers/auth.py`
- `api/middleware/auth.py`
- `tests/test_auth.py`
- CORS changes in `api/main.py`
- Sprint 3 scorecard architecture (`api/routers/organizing.py`, `scripts/scoring/create_scorecard_mv.py`)

---

## Auth Review Findings

### High Severity
1. First-user registration race condition in `api/routers/auth.py` (`COUNT(*)` then `INSERT` without lock/serialization) can allow multiple unauthenticated bootstrap accounts.
2. Auth is fail-open when `LABOR_JWT_SECRET` is unset (`api/middleware/auth.py` bypasses enforcement), enabling full access if misconfigured.

### Medium Severity
3. JWT secret strength is not enforced (presence only, no minimum length/entropy checks).
4. Middleware trusts token claims without checking user existence/role freshness in DB (deleted/role-changed users retain access until token expiry).

### Low Severity
5. Duplicate-registration race can surface as 500 instead of clean 409 due to unique-constraint collision path.

### Notes
- bcrypt usage is generally correct (`hashpw` + `gensalt`, `checkpw`).
- Parsing optional bearer tokens on public paths is acceptable with current behavior, but only if public handlers never grant privilege from optional identity state.
- CORS settings in `api/main.py` looked restrictive and did not introduce a direct auth bypass in this diff.

### Auth Test Gaps
- No concurrency test for first-user registration.
- No secret-strength enforcement tests.
- No deprovisioned-user token behavior test.

---

## Sprint 3 Architecture Review Findings

### High Severity
1. List/detail score drift is already present:
   - List endpoint uses MV (`v_organizing_scorecard`).
   - Detail endpoint recomputes with different rules (fuzzy union fallback, NLRB fallback differences, NY/NYC contracts inclusion).
2. Potential duplicate-row risk in MV due to joins on non-guaranteed one-row-per-establishment CTEs (`f7_matches`, `mergent_data`).

### Medium Severity
3. `/api/admin/refresh-scorecard` has no explicit admin role check in the route.
4. Refresh is non-concurrent and can block readers (`REFRESH MATERIALIZED VIEW` without `CONCURRENTLY`).

---

## Answers to Sprint Questions
1. MV + wrapper view pattern is valid. Keep it unless you need indexed ordering/filtering on total score; then store total in MV or add expression index.
2. Detail endpoint should read base 9 factors from MV for consistency, then add detail-only context/augmentation separately.
3. OSHA hierarchical fallback can be cleaner via `LATERAL` selection of best available prefix row.
4. `REFRESH MATERIALIZED VIEW CONCURRENTLY` is recommended for uptime, but needs a unique index and non-transactional execution pattern.
5. Yes, score drift risk is high today due to logic divergence.
6. 24,841 rows may be fine, but validate:
   - population alignment with `v_osha_organizing_targets`
   - `COUNT(*) == COUNT(DISTINCT establishment_id)` in MV.

---

## Suggested Next Checks
1. `SELECT COUNT(*), COUNT(DISTINCT establishment_id) FROM mv_organizing_scorecard;`
2. Compare MV row population against intended `v_osha_organizing_targets` filter scope.
3. Enforce/admin-check protect `POST /api/admin/refresh-scorecard`.
4. Refactor detail endpoint to consume MV base scores.
5. Add concurrency-safe bootstrap registration logic and tests.
