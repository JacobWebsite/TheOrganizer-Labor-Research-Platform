# Code Review Request — Sprint 6: Frontend Split + Score Explanations

## Context
This is a labor relations research platform (FastAPI + vanilla JS). Sprint 6 split a 10,506-line monolithic HTML file into CSS + 10 JS files, added server-side score explanations to the API, and added a public-sector coverage banner. **No functional changes** — the split is purely mechanical.

## Architecture Decision
- **Plain `<script>` tags (NOT ES modules)** — the file had 103 inline `onclick=` handlers. ES modules would break all of them. With plain scripts, all functions remain global.
- **Load order constraint:** config.js -> utils.js -> maps.js -> territory.js -> search.js -> deepdive.js -> detail.js -> scorecard.js -> modals.js -> app.js
- All state variables are global `let`/`var` declarations.

## What Changed

### Files Created (11 new files)
| File | Lines | Purpose |
|------|-------|---------|
| `files/css/organizer.css` | 228 | All custom CSS (Tailwind via CDN) |
| `files/js/config.js` | 30 | API_BASE + all global state variables |
| `files/js/utils.js` | 197 | Pure utility functions (formatNumber, escapeHtml, etc.) |
| `files/js/maps.js` | 212 | Leaflet map init + interaction |
| `files/js/territory.js` | 671 | Territory mode (union selector, dashboard, KPIs, charts) |
| `files/js/search.js` | 935 | Search mode (typeahead, search, results, pagination) |
| `files/js/deepdive.js` | 356 | Deep dive employer profile |
| `files/js/detail.js` | 1,352 | Employer/union detail panel + OSHA/NLRB rendering |
| `files/js/scorecard.js` | 816 | Organizing scorecard modal |
| `files/js/modals.js` | 2,606 | All other modals (11 modals total) |
| `files/js/app.js` | 1,010 | Mode switching, init, exports, URL state, keyboard shortcuts |

### Files Modified
| File | Change |
|------|--------|
| `files/organizer_v5.html` | 10,506 -> 2,139 lines (markup only, no inline JS) |
| `api/routers/organizing.py` | +~140 lines: 10 score explanation helpers + `_build_explanations()` + `float()` fix for Decimal |

### Bugs Fixed During Split
1. **`decimal.Decimal + float` TypeError** — PostgreSQL returns `Decimal` from `SUM()`; Python 3 doesn't mix with `float`. Fixed with `float()` wrapping at lines 436, 441.
2. **Duplicate `let` declarations** — 4 scorecard variables were in both `scorecard.js` and `modals.js`. Since plain `<script>` tags share global scope, duplicate `let` causes `SyntaxError` that kills the entire file. Removed from `modals.js`.

## Review Focus Areas

Please check for:

1. **Cross-file dependencies** — Are there any functions called in one file that are defined in a later-loading file? (Would cause `ReferenceError` at runtime.)

2. **Duplicate declarations** — Any `let`/`const`/`function` declared in multiple files? (Would cause `SyntaxError` in global scope.)

3. **State variable completeness** — Are all state variables from the original monolith present in `config.js`? Any module-scoped state that should be global?

4. **XSS via innerHTML** — `escapeHtml()` is used throughout but check for any raw string interpolation into `innerHTML` without escaping.

5. **API error handling** — Are all `fetch()` calls wrapped in try/catch? Do they handle non-200 responses?

6. **Score explanation helpers** (organizing.py lines 101-238) — Do the explanation strings match the actual scoring logic (lines 13-94)?

7. **The `_build_explanations()` function** (line 216) — Does it correctly read from the row dict? Any potential `KeyError`?

8. **Frontend fallback** — `getScoreReason()` in scorecard.js checks `item.score_explanations[type]` first, falls back to client-side logic. Is the fallback correct?

9. **The `renderTrendsChart(financials)` call** at detail.js line 1055 — `financials` is not defined in scope. This is a pre-existing bug from the monolith (should be `detail.financials` or similar). Flag it.

## Files

### api/routers/organizing.py (score explanation helpers only, lines 97-238)
```python
# ---------------------------------------------------------------------------
# Score explanation helpers (plain-language reasons for each score component)
# ---------------------------------------------------------------------------

def _explain_size(emp_count):
    """Human-readable explanation for the size score."""
    if not emp_count or emp_count <= 0:
        return "No employee data available"
    if 50 <= emp_count <= 250:
        return f"{emp_count:,} employees -- in the 50-250 organizing sweet spot"
    elif 250 < emp_count <= 500:
        return f"{emp_count:,} employees -- mid-size, feasible target"
    elif 25 <= emp_count < 50:
        return f"{emp_count:,} employees -- small but organizable"
    elif 500 < emp_count <= 1000:
        return f"{emp_count:,} employees -- large, requires more resources"
    else:
        return f"{emp_count:,} employees -- very {'large' if emp_count > 1000 else 'small'} unit"

def _explain_osha(total_violations, osha_ratio):
    if total_violations == 0:
        return "No OSHA violations on record"
    ratio_str = ""
    if osha_ratio and osha_ratio > 0:
        ratio_str = f" ({osha_ratio:.1f}x industry average)"
    return f"{total_violations} violations{ratio_str}"

def _explain_geographic(state, is_rtw, win_rate):
    parts = []
    if state:
        parts.append(state)
    if is_rtw is not None:
        parts.append("right-to-work state" if is_rtw else "non-RTW state")
    if win_rate is not None:
        parts.append(f"{win_rate:.0f}% NLRB win rate")
    return ", ".join(parts) if parts else "Geographic data unavailable"

def _explain_contracts(federal_amt, count):
    federal_amt = federal_amt or 0
    count = count or 0
    if federal_amt <= 0:
        return "No federal contracts on record"
    if federal_amt >= 1_000_000:
        return f"${federal_amt / 1_000_000:.1f}M across {count} federal contract{'s' if count != 1 else ''}"
    elif federal_amt >= 1_000:
        return f"${federal_amt / 1_000:.0f}K across {count} federal contract{'s' if count != 1 else ''}"
    return f"${federal_amt:,.0f} in {count} federal contract{'s' if count != 1 else ''}"

def _explain_nlrb(predicted_pct):
    if predicted_pct is None:
        return "No NLRB prediction available (using blended rate)"
    return f"{predicted_pct:.0f}% predicted win rate"

def _explain_industry_density(score):
    if score is None: score = 0
    if score >= 10: return "15%+ union density in sector (very high)"
    elif score >= 8: return "10-15% union density in sector (high)"
    elif score >= 6: return "5-10% union density in sector (moderate)"
    elif score >= 4: return "2-5% union density in sector (low)"
    elif score >= 2: return "Under 2% union density (very low)"
    return "Density data unavailable"

def _explain_company_unions(score):
    if score is None: score = 0
    if score >= 15: return "Multiple related locations with union presence"
    elif score >= 10: return "Related location has union representation"
    elif score >= 5: return "Same-sector employer has nearby union"
    return "No related union presence detected"

def _explain_projections(score):
    if score is None: score = 0
    if score >= 8: return "Industry projected for strong growth (BLS)"
    elif score >= 5: return "Industry projected for moderate growth (BLS)"
    elif score >= 3: return "Industry projected for slow growth (BLS)"
    return "Industry growth data unavailable"

def _explain_similarity(score):
    if score is None: score = 0
    if score >= 8: return "Very similar to successfully organized employers"
    elif score >= 5: return "Moderately similar to organized employers"
    elif score >= 3: return "Some similarity to organized employers"
    return "Low similarity to organized employers"

def _build_explanations(row, is_rtw=None, win_rate=None):
    return {
        'size': _explain_size(row.get('employee_count')),
        'osha': _explain_osha(
            row.get('total_violations'),
            float(row['osha_industry_ratio']) if row.get('osha_industry_ratio') is not None else None
        ),
        'geographic': _explain_geographic(
            row.get('site_state'), is_rtw, win_rate
        ),
        'contracts': _explain_contracts(
            float(row['federal_obligations']) if row.get('federal_obligations') else 0,
            row.get('federal_contract_count', 0)
        ),
        'nlrb': _explain_nlrb(
            float(row['nlrb_predicted_win_pct']) if row.get('nlrb_predicted_win_pct') else None
        ),
        'industry_density': _explain_industry_density(row.get('score_industry_density')),
        'company_unions': _explain_company_unions(row.get('score_company_unions')),
        'projections': _explain_projections(row.get('score_projections')),
        'similarity': _explain_similarity(row.get('score_similarity')),
    }
```

### Decimal fix (organizing.py lines 431-443)
```python
# NY/NYC state contracts (detail-only, not in MV contract score)
cur.execute("""
    SELECT COALESCE(SUM(current_amount), 0) as total FROM ny_state_contracts
    WHERE vendor_name ILIKE %s
""", [f"%{estab_name[:15]}%"])
ny_funding = float(cur.fetchone()['total'] or 0)  # <-- float() added
cur.execute("""
    SELECT COALESCE(SUM(current_amount), 0) as total FROM nyc_contracts
    WHERE vendor_name ILIKE %s
""", [f"%{estab_name[:15]}%"])
nyc_funding = float(cur.fetchone()['total'] or 0)  # <-- float() added

federal_funding = float(mv['federal_obligations'] or 0)
federal_count = mv['federal_contract_count'] or 0
```

### HTML script tags (organizer_v5.html lines 2127-2138)
```html
<!-- External JS files (load order matters) -->
<script src="/files/js/config.js"></script>
<script src="/files/js/utils.js"></script>
<script src="/files/js/maps.js"></script>
<script src="/files/js/territory.js"></script>
<script src="/files/js/search.js"></script>
<script src="/files/js/deepdive.js"></script>
<script src="/files/js/detail.js"></script>
<script src="/files/js/scorecard.js"></script>
<script src="/files/js/modals.js"></script>
<script src="/files/js/app.js"></script>
```

### config.js (30 lines — all global state)
```javascript
const API_BASE = (window.LABOR_API_BASE || window.location.origin) + '/api';

let currentMode = 'employers';
let currentResults = [];
let selectedItem = null;
let currentPage = 1;
let totalPages = 1;
let detailMap = null;
let detailMarker = null;

let currentView = 'list';
let fullMap = null;
let markerClusterGroup = null;
let mapMarkers = new Map();

let comparisonItems = [null, null];

let currentAppMode = 'territory';
let territoryContext = { union: '', state: '', metro: '' };
let deepDiveReturnMode = 'territory';
let territoryMap = null;
let territoryMarkerCluster = null;
let territoryCharts = {};
let territoryDataCache = {};
```

### Additional module-scoped state in individual files
- `search.js:150` — `let selectedIndustry = null;`
- `search.js:422` — `let typeaheadFocusIndex = -1;`
- `deepdive.js:7` — `let deepDiveData = {};`
- `detail.js:309` — `let currentScorecardFlagSource = null;`
- `detail.js:421` — `let currentProjectionMatrixCode = null;`
- `detail.js:900` — `let trendsChart = null;`
- `scorecard.js:6-11` — `let scorecardResults, selectedScorecardItem, scorecardDataSource, currentSectorCities;`
- `app.js:874` — `let keyboardFocusIndex = -1;`

## Test Results
162/162 tests pass. All API endpoints returning 200. All 10 JS files loading successfully (verified via server logs).

---

## Review Response (Sprint 6.1 — Post-Review Fixes)

### Findings Accepted and Fixed

| # | Severity | Finding | Fix |
|---|----------|---------|-----|
| 1 | High | `renderTrendsChart(financials)` — `financials` undefined at detail.js:1055 | Changed to `renderTrendsChart(detail.financial_trends)`. API doesn't return multi-year financials, so function gracefully hides the section. |
| 2 | High | Scorecard field name mismatches: `breakdown.state_density` (should be `geographic`), `contracts.contract_count` (should be `federal_contract_count`) | Fixed field names in scorecard.js:528 and 544 to match API response. Also fixed "100-500" sweet spot label to "50-250". |
| 3 | Medium | `getSourceBadge()` defined in both utils.js and modals.js — later overrides earlier | Removed modals.js duplicate (line 1604). Callers all use the utils.js version now. |
| 4 | Medium | XSS — raw `${source}` in modals.js:1611 innerHTML | Fixed by removing duplicate `getSourceBadge()` (utils.js version uses static badge map, no raw interpolation). Also escaped `item.site_state`, `item.priority_tier`, `item.industry` in scorecard.js:389-394. |
| 5 | Medium | `getScoreReason()` fallback uses stale scoring model (100-500 sweet spot, wrong NLRB/OSHA buckets) | Updated to match current backend: 50-250 sweet spot, NLRB based on predicted win %, OSHA based on industry ratio. |

### Findings Accepted, Deferred

| # | Severity | Finding | Rationale |
|---|----------|---------|-----------|
| 6 | Low | Score explanation helpers don't fully describe sub-factor contributions (willful/repeat for OSHA, state density for geographic) | Explanations are intentionally simplified for end-user readability. Adding every sub-factor would make them cluttered. |
| 7 | Low | Inconsistent `response.ok` checks in some fetch paths | Real but low-impact for internal research tool. Will address in a future error-handling pass. |

### Findings Rejected

None — all findings were valid.
