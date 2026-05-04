# Release Checklist

Run this checklist before any deploy or beta launch. If a step fails, do not ship.

## Deployment hygiene

- [ ] **Critical routes present in running API.**
  ```
  py scripts/maintenance/check_critical_routes.py
  ```
  Manifest: `config/critical_routes.txt`. Add new BL-BLOCK or beta-critical routes here as they ship. **Why this exists:** R7-6 caught the family-rollup endpoint absent from `:8001` in production despite being in the codebase. Starbucks 0-elections regression went unnoticed for ~24 hours.

- [ ] **Critical MVs present with non-trivial row counts.**
  ```
  py scripts/maintenance/check_critical_mvs.py
  ```
  Manifest: `config/critical_mvs.txt`. **Why this exists:** 2026-04-30 incident -- `mv_target_scorecard` silently disappeared between R7 baseline (2026-04-25, 5.38M rows) and the next verification run. API returned 503 on every `/api/targets/scorecard*` call; master scoring was dead in the UI; no alert fired. The route check above is "is the code mounted"; this is "is the data behind the API actually present."

- [ ] **F7 orphan rate within tolerance.**
  ```
  py scripts/maintenance/check_orphan_rate.py
  ```
  Default ceiling: 67.0% (R7-era regression number). Override with `--max-orphan-pct N`. **Why this exists:** Splink retirement (2026-04) pushed F7 orphan rate from R6 baseline 64.7% to 68.1% before the problem was noticed; current state ~65.2% is within 0.5pp of R6. This gate prevents future matching deactivations from silently pushing orphans back toward R7 levels (recommendation #5 from `Open Problems/F7 Orphan Rate Regression.md`).

- [ ] **API is reachable.** `curl http://localhost:8001/api/health` returns `{"status":"ok","db":true}`.

- [ ] **Frontend builds clean.** `cd frontend && npx vite build` exits 0.

## Data sanity

- [ ] **Backend tests pass.** `py -m pytest tests/ -x -q`
- [ ] **Frontend tests pass.** `cd frontend && npx vitest run`
- [ ] **Demographics plausibility holds.** R7-1 (the 145M NY hospitals bug) is now bounded by `api/services/demographics_bounds.py`; tests in `tests/test_demographics_bounds.py` enforce it.

## What to add here next

When a regression like R7-6 (deploy drift), R7-1 (data overflow), or R7-15 (route 404) is fixed, add a checklist item that would have caught it. The whole point of this file is to convert audit findings into pre-deploy gates.
