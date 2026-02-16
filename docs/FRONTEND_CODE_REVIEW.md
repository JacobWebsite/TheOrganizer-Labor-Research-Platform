# Frontend Architecture Review (Focused Task 4)

This review covers all files under `files/` (24 files total), including:
- HTML: `files/organizer_v5.html`, `files/api_map.html`, `files/test_api.html`, `files/afscme_scraper_data.html`
- JS: `files/js/*.js`
- CSS: `files/css/organizer.css`

## 1) Data flow map: which JS file talks to which API endpoints

Main rule:
- `API_BASE` is defined in `files/js/config.js:3` as `(window.LABOR_API_BASE || window.location.origin) + '/api'`.

Primary API consumers:
- `files/js/app.js`: summary, lookups, admin freshness/refresh, basic health checks.
- `files/js/search.js`: generic search endpoints via `/${endpoint}` plus stats breakdown.
- `files/js/detail.js`: employer detail, OSHA, NLRB, projections, flags, unified detail, union detail.
- `files/js/scorecard.js`: organizing scorecard list/detail + sector endpoints.
- `files/js/territory.js`: lookups, unions/national, organizing scorecard, trends, elections, density, WHD.
- `files/js/deepdive.js`: scorecard detail + siblings + NLRB election lookup.
- `files/js/modal-unified.js`: unified employer search/detail.
- `files/js/modal-elections.js`: NLRB election search.
- `files/js/modal-publicsector.js`: public sector parent unions, employer types, locals, employers.
- `files/js/modal-corporate.js`: corporate family.
- `files/js/modal-trends.js`: trends endpoints.
- `files/js/modal-analytics.js`: summary/trends/NLRB dashboard data.
- `files/js/modal-similar.js`: unions national + employer similar lookups.
- `files/js/uniondive.js`: union detail.

## 2) Scoring references: are all places using unified 9-factor model?

No. Frontend is mixed between 8-factor and 9-factor logic.

Evidence:
- `files/js/config.js:5` says "8 active factors".
- `files/js/config.js:16` sets `SCORE_MAX` to 80.
- But `files/js/scorecard.js:243` still maps `company_unions` in sector results.
- `files/js/scorecard.js:522` renders "Company Union Shops" as a factor row.

Impact:
- Users can see conflicting score explanations across pages.
- Some screens assume 80-point max while backend/tests also reference 90-point totals.

## 3) Hardcoded URLs (especially localhost)

Findings:
- `files/test_api.html:10` hardcodes `http://localhost:8001/api`.
- Main app code mostly uses `API_BASE` from `window.location.origin`, which is good.
- External CDN URLs are hardcoded in `files/organizer_v5.html` (Tailwind, Leaflet, Chart.js, Google Fonts). This is normal but creates runtime dependency on public CDNs.

## 4) `modals.js` split points

The large monolith appears already split into:
- `modal-analytics.js`
- `modal-comparison.js`
- `modal-corporate.js`
- `modal-elections.js`
- `modal-publicsector.js`
- `modal-similar.js`
- `modal-trends.js`
- `modal-unified.js`

So the "2,598-line modals.js" issue is already partially resolved.

Next natural split points still needed:
- Move API calls into a shared service layer (`apiClient.js`) to remove repeated fetch/error code.
- Move all HTML template builders into separate render modules.
- Move modal state handling into per-modal state objects to reduce global variable coupling.

## 5) Inline `onclick` handlers count

Count found: 67 inline `onclick=` handlers across `files/`.

Largest concentrations:
- `files/js/detail.js`: 17
- `files/api_map.html`: 12
- `files/js/territory.js`: 7
- `files/afscme_scraper_data.html`: 6
- `files/js/search.js`: 6

Risk:
- Harder to maintain and test.
- More XSS surface if templated values are not escaped consistently.

## 6) Error handling: what user sees when API calls fail

Mixed quality:
- Good: many modules show clear user messages in UI (example: `files/js/scorecard.js:161`, `files/js/territory.js:334`, `files/js/deepdive.js:69`).
- Weak: many failures only log to console and do not show user-facing errors.
- Weak: no single global error strategy, so behavior is inconsistent between pages/modals.

Net effect:
- Some failures are visible and recoverable.
- Other failures look like “empty data” with no explanation.

## 7) CSS/styling approach maintainability

Current approach is mixed:
- Tailwind utility classes in HTML/JS template strings.
- Custom stylesheet in `files/css/organizer.css`.
- Many inline style snippets generated from JS templates.

Pros:
- Fast to build features.
- Visual system is mostly consistent.

Cons:
- Styling rules are scattered across HTML, CSS, and JS strings.
- Refactors are harder because styles are not centralized.
- Dynamic template styles are hard to lint and test.

## Practical recommendations

1) Pick one score model and enforce it in `config.js`, `scorecard.js`, glossary, and backend response contracts.
2) Replace inline `onclick` with delegated event listeners.
3) Add a shared fetch wrapper that handles `response.ok`, retries, and user-safe error messages.
4) Keep `API_BASE` pattern; remove localhost-only test page from production bundles.
5) Continue modal modularization by separating API, state, and rendering layers.
6) Standardize styling boundaries: utility classes for layout, CSS file for reusable component styles, minimal inline style generation.
