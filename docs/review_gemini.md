# Architecture Review Request — Sprint 6: Frontend Split + Score Explanations

## Context
Labor relations research platform (FastAPI + PostgreSQL + vanilla JS). A 10,506-line monolithic HTML file was split into CSS + 10 JS files. Server-side score explanations were added to the API. A public-sector coverage banner was added. **162/162 tests pass.**

## Key Architecture Decision: Plain Scripts vs ES Modules

We chose **plain `<script>` tags** over ES modules. The rationale:

- The monolith had **103 inline `onclick=` handlers** in the HTML markup (e.g., `onclick="selectItem(123)"`). ES modules scope functions to the module — all 103 handlers would break.
- Migrating to ES modules would require: (1) removing all inline handlers, (2) adding `addEventListener` calls in JS, (3) adding `export`/`import` for every cross-file reference. This is a separate sprint-sized effort.
- With plain scripts, all functions remain global. The split is purely mechanical — extract code blocks, load in order, done.

**Trade-off:** We retain global namespace pollution (~200 functions) and depend on load order. But the alternative (ES modules) would have been a functional rewrite, not a refactoring.

**Question for review:** Is this the right call given the constraints? Would a bundler (esbuild/Vite) be a better intermediate step?

---

## File Organization

### Before
```
files/organizer_v5.html     (10,506 lines — CSS + HTML + JS all inline)
```

### After
```
files/
  organizer_v5.html          (2,139 lines — markup only)
  css/
    organizer.css             (228 lines — all custom CSS)
  js/
    config.js                 (30 lines — API_BASE + global state)
    utils.js                  (197 lines — pure utilities)
    maps.js                   (212 lines — Leaflet map functions)
    territory.js              (671 lines — territory mode)
    search.js                 (935 lines — search + typeahead)
    deepdive.js               (356 lines — deep dive profiles)
    detail.js                 (1,352 lines — employer/union detail)
    scorecard.js              (816 lines — scorecard modal)
    modals.js                 (2,606 lines — 11 other modals)
    app.js                    (1,010 lines — glue, init, exports)
```

**Total JS:** 8,185 lines across 10 files (was 8,160 inline — 25 lines of comments added).

### Load order (strict dependency chain)
```
config.js    -- no deps, defines all shared state
utils.js     -- reads API_BASE from config
maps.js      -- calls utils (showError, etc.)
territory.js -- calls utils + maps
search.js    -- calls utils + maps
deepdive.js  -- calls utils, reads territoryContext from config
detail.js    -- calls utils + maps, reads state from config
scorecard.js -- calls utils + detail (selectItem)
modals.js    -- calls utils + maps + detail + scorecard + search + territory
app.js       -- orchestrates everything, calls into all above
```

### Review questions on file organization:

1. **`modals.js` is 2,606 lines** — it contains 11 separate modals. Should each modal be its own file? Or is grouping them acceptable since they share no state?

2. **`detail.js` is 1,352 lines** — it handles employer detail, union detail, OSHA rendering, NLRB rendering, BLS projections, flags, and scorecard flags. Is this too many concerns in one file?

3. **State management** — Global state is split between `config.js` (shared state) and individual files (module-scoped state like `let selectedIndustry` in search.js). Is this the right boundary? Module-scoped state in individual files:
   - `search.js` — `selectedIndustry`, `typeaheadFocusIndex`
   - `deepdive.js` — `deepDiveData`
   - `detail.js` — `currentScorecardFlagSource`, `currentProjectionMatrixCode`, `trendsChart`
   - `scorecard.js` — `scorecardResults`, `selectedScorecardItem`, `scorecardDataSource`, `currentSectorCities`
   - `app.js` — `keyboardFocusIndex`

---

## API Design: Score Explanations

### Current architecture
The `mv_organizing_scorecard` materialized view computes 9 scoring factors in SQL. The API reads from this view and returns numeric scores. The frontend reverse-engineers explanations from scores (e.g., `score >= 10` means "15%+ union density").

### What we added
Server-side explanation functions that generate plain-language strings from the **actual data**, not from the scores. Added to both the list endpoint (`/api/organizing/scorecard`) and detail endpoint (`/api/organizing/scorecard/{estab_id}`).

### Architecture pattern
```
PostgreSQL MV (scores) --> API (reads MV + generates explanations) --> Frontend (displays)
                                                                        |
                                                                        v
                                                               Falls back to client-side
                                                               getScoreReason() if no
                                                               server explanations
```

### 10 explanation helpers
```python
_explain_size(emp_count)           -> "150 employees -- in the 50-250 organizing sweet spot"
_explain_osha(violations, ratio)   -> "12 violations (2.3x industry average)"
_explain_geographic(state, rtw, wr)-> "NY, non-RTW state, 87% NLRB win rate"
_explain_contracts(amt, count)     -> "$2.1M across 3 federal contracts"
_explain_nlrb(predicted_pct)       -> "74% predicted win rate"
_explain_industry_density(score)   -> "15%+ union density in sector (very high)"
_explain_company_unions(score)     -> "Related location has union representation"
_explain_projections(score)        -> "Industry projected for strong growth (BLS)"
_explain_similarity(score)         -> "Very similar to successfully organized employers"
```

`_build_explanations(row, is_rtw, win_rate)` aggregates all 9 into a dict, added to each API response item as `score_explanations`.

### Review questions on API design:

4. **Should explanations live in the MV itself?** We could add computed text columns to the materialized view SQL. Pro: single source of truth. Con: MV refresh becomes heavier, text in DB is wasteful since it's derived from other columns.

5. **Explanation drift risk** — The explanation helpers read from the same row dict as the scoring SQL. But if the MV scoring logic changes and the explanation helpers aren't updated, they'll be out of sync. Should we add a test that validates explanation output against known score inputs?

6. **The `_explain_industry_density` and `_explain_company_unions` functions take a `score` parameter** (the computed score value, not the raw data). This means they're still reverse-engineering from scores, just server-side. Is this acceptable, or should they read raw data? The raw data isn't in the MV for these factors.

---

## Bugs Fixed

### 1. `decimal.Decimal + float` TypeError
PostgreSQL `COALESCE(SUM(current_amount), 0)` returns `decimal.Decimal`. The detail endpoint was doing `ny_funding + federal_funding` where `federal_funding` was already `float()`. Python 3 raises `TypeError` on mixed arithmetic.

**Fix:** `float()` wrapping at the query result level.

**Architectural question:** Should the database layer (`database.py`) handle Decimal->float conversion globally, or is per-query wrapping the right approach?

### 2. Duplicate `let` declarations across files
4 scorecard variables were declared with `let` in both `scorecard.js` and `modals.js`. Since plain `<script>` tags share global scope, duplicate `let` causes `SyntaxError` that prevents the entire file from loading.

**Fix:** Removed duplicates from `modals.js`.

**Architectural question:** This is a class of bug unique to the plain-scripts approach. With ES modules, each file has its own scope and this can't happen. Is there a lint rule or build step we should add to catch this?

---

## Pre-Existing Bug (Not Fixed This Sprint)

**`renderTrendsChart(financials)`** at `detail.js:1055` — `financials` is not defined in the calling scope. This was a bug in the original monolith that got carried over. The function exists at line 900 and expects financial data, but the call site passes an undefined variable.

---

## Overall Architecture Questions

7. **Caching strategy** — The frontend caches territory data in `territoryDataCache` (a plain JS object). There's no TTL or invalidation. Is this acceptable for a research tool, or should we add cache expiry?

8. **Error handling pattern** — Most `fetch()` calls follow `try/catch` with `showError()`. But some silently swallow errors (e.g., flag submission). Should we standardize?

9. **The HTML file is still 2,139 lines** — It contains all the markup for 3 modes + 11 modals + detail panels. Could this be further split (e.g., modal HTML as templates loaded on demand)?

10. **Static file serving** — FastAPI serves JS/CSS via `StaticFiles` mount. There's no versioning, minification, or cache busting. For a research tool with few users, is this fine? Or should we add `?v=hash` query params to script tags?

## Test Results
162/162 tests pass. The backend explanation helpers are covered by existing scorecard tests (they return the explanations in API responses). No dedicated unit tests for the explanation functions themselves.

---

## Review Response (Sprint 6.1 — Post-Review Fixes)

### Recommendations Accepted

| # | Recommendation | Action Taken |
|---|---------------|--------------|
| Plain scripts decision | Confirmed correct. ES modules would require rewriting all 103 inline handlers. | No change needed. |
| Explanation drift test | Good idea. | Deferred — explanations are intentionally looser than scores. A strict test would be brittle and create maintenance overhead for low risk. Will revisit if drift is observed. |
| Don't put explanations in MV | Agreed. | No change needed. |
| ESLint | Would catch duplicate declarations. | Deferred to Sprint 9 (Polish). Current plain-scripts approach is non-standard for ESLint configs. |

### Recommendations Rejected

| # | Recommendation | Rationale |
|---|---------------|-----------|
| Split modals.js into 11 files | Each extra file = another `<script>` tag + load-order dependency. 11 modals sharing zero state are well-partitioned internally. Grep works fine at 2,606 lines. Cost exceeds benefit. |
| Split detail.js into renderer files | Same reasoning. 1,352 lines of related rendering logic, not tangled spaghetti. |
| Raw data columns in MV for explanations | Adds MV query complexity for 3 helper functions. Current score-based explanations are directionally correct and sufficient for end users. |
| Global Decimal->float conversion in database layer | Only 2 occurrences across entire codebase. Abstraction for 2 lines is over-engineering. |
| HTML templates loaded via fetch | Adds async complexity, template-loading error handling, loading spinners for every modal open. Over-engineering for internal research tool. |
| "Refresh Data" button for cache | Territory data cache is already cleared on dropdown change. Manual refresh button adds UI clutter for minimal benefit. |

### Key Bugs Fixed (from concurrent Codex review)

1. `renderTrendsChart(financials)` — undefined variable at detail.js:1055
2. Scorecard field name mismatches (`state_density` -> `geographic`, `contract_count` -> `federal_contract_count`)
3. Duplicate `getSourceBadge()` function across utils.js and modals.js
4. XSS: raw string interpolation in `getSourceBadge()` and scorecard badge rendering
5. Stale `getScoreReason()` fallback logic (old scoring model ranges)
