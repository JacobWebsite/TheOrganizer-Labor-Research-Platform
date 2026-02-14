# Independent Platform Audit - Codex
## Date: February 14, 2026

## Executive Summary
The platform is substantive and real: it has a broad integrated dataset, a modular FastAPI structure, and a working end-to-end workflow from ingestion to interface. Runtime validation is stronger than expected: `python -m pytest -q tests/test_api.py tests/test_data_integrity.py` passed (47/47), and the database is populated at scale (for example: 1,007,217 OSHA establishments, 363,365 WHD cases, 60,953 deduped F-7 employers, 26,665 unions, and 14,507,549 deduplicated members).

The biggest strengths are data breadth and practical utility for target discovery, especially the combined OSHA/NLRB/WHD/F-7 views and working scorecard/search flows. The biggest risks are security posture and maintainability: auth is effectively off by default, CORS is fully open, there is widespread dynamic SQL assembly, many scripts still have broken credential patterns, and the frontend is a 9,972-line single HTML file with heavy inline JS.

The product is useful as a research system now, but not yet production-ready for union staff access on a public or shared deployment. The fastest path to safe adoption is: lock down API auth/CORS/secrets, reduce SQL-construction risk, simplify and harden scoring/matching explainability, and make organizer workflows explicit (territory queue, evidence packet, freshness/confidence indicators).

## Audit Findings by Area
### 1. Project Organization
What works:
- Clear top-level separation (`api/`, `scripts/`, `sql/`, `files/`, `tests/`).
- API is router-based and discoverable (`api/main.py`, `api/routers/*.py`).
- Core docs exist and are detailed.

Risks:
- `scripts/` is very large (488 Python files) with mixed archival/active utilities and inconsistent quality.
- `frontend/` is effectively unused (no HTML files); active UI lives in `files/organizer_v5.html`.
- SQL assets include destructive schema scripts (`DROP TABLE`) and legacy references to `f7_employers`, while active code targets `f7_employers_deduped` (`sql/schema/f7_schema.sql`, `sql/queries/create_search_views.sql`).
- README startup command is stale (`README.md` points to `api.labor_api_v6`, active entry is `api.main`).

Should improve:
- Introduce lifecycle labels (`active`, `legacy`, `archive`) for scripts/SQL and enforce via directory or naming convention.
- Move frontend to modular source structure and generate artifact into `files/`.

### 2. Database Design
What works:
- Large, functioning schema (342 public tables reported).
- Core PK usage is broad (144 PK constraints).
- High-value match/materialized tables exist and are populated (`mv_employer_search`, `mv_whd_employer_agg`, `osha_f7_matches`).

Risks:
- Referential integrity is partial for schema size (26 FK constraints only).
- 6 foreign keys appear without prefix indexes, which will hurt joins/updates as volume grows (`employer_comparables`, `osha_unified_matches`, `web_union_*` profile links).
- Significant orphaning remains in historical relations: `f7_union_employer_relations` orphan rate is 50.38% (60,373 / 119,844).
- Multiple zero-row tables appear in live DB stats, which increases schema noise and maintenance burden.

Should improve:
- Add missing FK-supporting indexes.
- Separate historical-vs-current relationship tables or include explicit validity windows so joins do not silently drop history.

### 3. Entity Matching
What works:
- Matching module is well-structured (`scripts/matching/`) with tiered matching classes and scenario config.
- Normalization stack is thoughtful (standard/aggressive/fuzzy plus `cleanco`).
- Match confidence fields and low-confidence flags exist in production tables (`osha_f7_matches.low_confidence`, `whd_f7_matches.low_confidence`).

Risks:
- Some matching scripts still contain broken credential literals, indicating inconsistent script reliability.
- Match-method sprawl is large in OSHA (`match_method` includes many variants), which complicates quality calibration and governance.
- Low-confidence share remains material: OSHA low-confidence 23.3% (32,243), WHD low-confidence 27.0% (6,657).

Should improve:
- Standardize match taxonomy into canonical families + confidence thresholds.
- Surface confidence/method in API/frontend by default for analyst trust and review triage.

### 4. Scoring Systems
What works:
- Scorecards are implemented and operational (OSHA organizing endpoint + sector score views).
- Multi-factor decomposition is exposed via API (`/api/organizing/scorecard`, `/api/organizing/scorecard/{id}`).

Risks:
- Methodology drift across docs and code is likely; docs describe multiple score formulations (6/8/9-factor variants).
- Some scoring logic is hardcoded and heuristic-heavy in endpoint code (`api/routers/organizing.py`), making A/B validation difficult.
- Sector view generation uses dynamic SQL with direct interpolated sector/view names in scripts (`scripts/scoring/create_sector_views.py`), acceptable for internal admin scripts but risky if reused.

Should improve:
- Version scoring models explicitly (`score_model_version`) and persist per-employer factor snapshots.
- Add calibration tests against observed outcomes with locked backtest windows.

### 5. API Design & Security
What works:
- API modularization is in place (144 API routes).
- Parameterized SQL values are used in most query predicates.
- Pagination exists for many list endpoints.
- Middleware for auth/rate-limit/logging exists.

Risks:
- Auth defaults to disabled when `LABOR_JWT_SECRET` is unset (`api/config.py:18`, `api/middleware/auth.py:43`).
- CORS allows all origins (`api/main.py:44`).
- Token error details are echoed (`Invalid token: {exc}`) which can leak internals (`api/middleware/auth.py:66`).
- In-memory IP limiter is not process-safe/distributed-safe and trusts `X-Forwarded-For` directly (`api/middleware/rate_limit.py`).
- Extensive dynamic SQL assembly with interpolated clauses appears across routers (`api/routers/employers.py`, `api/routers/sectors.py`, `api/routers/nlrb.py`, `api/routers/vr.py`, `api/routers/whd.py`, etc.).

Should improve:
- Fail-closed auth in non-dev environments.
- Restrict CORS per environment.
- Replace dynamic clause interpolation with query builders/strict allowlists everywhere.

### 6. Data Quality
What works:
- Deduplicated member total computes to 14,507,549 (aligns with claimed ~14.5M).
- Match-rate improvements are real in live DB: OSHA 13.73%, WHD 6.77%, national 990 2.40%.
- NLRB xref orphaning is resolved (0% orphan in `nlrb_employer_xref`).

Risks:
- F7 relation orphaning is still high for historical links (50.38%), and easy to misread in analysis if not handled intentionally.
- Cross-source coverage remains uneven (example: `mergent_employers` with F7 link is 1.52%).
- Public-sector bargaining-unit linkage remains shallow (5.26% of `ps_employers` linked in `ps_bargaining_units`).

Should improve:
- Create explicit quality dashboards for match confidence, stale source dates, and unresolved high-impact gaps per source.

### 7. Frontend & UX
What works:
- Rich functionality in a single artifact (`files/organizer_v5.html`): scorecard, deep dive, public sector, elections, trends, export.
- Escaping helper is widely used before HTML injection.

Risks:
- Monolith size (9,972 lines) increases defect risk and slows iteration.
- Hardcoded API host (`const API_BASE = 'http://localhost:8001/api';`), blocking straightforward deployment.
- Heavy `innerHTML` and inline `onclick` usage across the file; maintainability and event hygiene are weak.
- Accessibility/mobile gaps: almost no responsive media queries except print; little semantic/accessibility signaling.

Should improve:
- Externalize API base to config/env.
- Split UI into modules/components and add keyboard/screen-reader/mobile acceptance criteria.

### 8. Testing
What works:
- Tests run and pass against live environment (47/47).
- Includes both API integration and data integrity checks.

Risks:
- Tests are integration-heavy and depend on local DB state; limited isolation/reproducibility.
- Low direct unit coverage for matching/scoring core logic.
- No explicit security tests for auth-required behavior in production mode.
- Warning indicates cache filesystem issue (`.pytest_cache` path conflict), minor but signals environment rough edges.

Should improve:
- Add deterministic unit tests for `scripts/matching/*` and scoring functions.
- Add auth/CORS/rate-limit behavior tests for production profile.

### 9. Documentation
What works:
- Documentation depth is high and includes methodology rationale.
- Roadmap and session logs provide clear historical context.

Risks:
- Inconsistencies exist between docs and live code/entrypoints (for example startup command drift in README).
- Methodology docs can lag current implementation due rapid iteration and multiple scoring revisions.

Should improve:
- Add a single “source of truth” runbook for current startup, deployment profile, data refresh cadence, and score model version.

### 10. Security & Deployment
What works:
- `.env` usage exists, and shared DB config helper is present.
- Middleware scaffolding for auth/rate-limit/logging is implemented.

Risks:
- Plaintext DB password in `.env` (`.env:5`).
- Script-level credential anti-patterns persist (31+ scripts with literal `os.environ.get(...)` strings in password fields; one script has default fallback `Juniordog33!` in code: `scripts/scoring/nlrb_win_rates.py:9`).
- Open CORS + auth disabled by default is not safe for shared deployment.
- Frontend assumes localhost API endpoint.

Should improve:
- Secrets rotation + secret manager + pre-commit secret scanning.
- Production/development config separation enforced at startup.

## Prioritized Improvements
### 🔴 Critical
1. Enforce authentication by default in non-dev environments.
- What's wrong: API accepts unrestricted access when JWT secret is absent.
- Why it matters: Any exposed instance is immediately open to unauthorized use/data scraping.
- What to do: Add environment guard (`ENV=prod` => fail startup if no JWT secret), require auth on all `/api/*` except health/docs.
- Effort: 1-2 days.

2. Remove hardcoded/plaintext credential exposure patterns.
- What's wrong: Real password present in `.env`; script defaults still include fallback secrets.
- Why it matters: Secret leakage risk and inconsistent runtime behavior.
- What to do: Rotate DB creds, remove insecure defaults, adopt secret manager/env injection only, add repo secret scanner in CI.
- Effort: 1-2 days.

3. Lock CORS and sanitize auth error leakage.
- What's wrong: `allow_origins=["*"]` and detailed token decode errors.
- Why it matters: Broader attack surface and potential internal disclosure.
- What to do: restrict origins per environment and return generic 401 messages.
- Effort: <1 day.

### 🟠 High
1. Reduce dynamic SQL construction risk across routers.
- What's wrong: Many endpoints interpolate SQL fragments (`where_clause`, `order_by`, view names).
- Why it matters: Even with current allowlists, this pattern is fragile and hard to audit.
- What to do: centralize query builders/validated clause generators; eliminate raw interpolated SQL where possible.
- Effort: 4-7 days.

2. Stabilize schema integrity around historical/current relations.
- What's wrong: 50.38% orphan rate in `f7_union_employer_relations` against deduped current employers.
- Why it matters: Silent analytic errors for anyone joining without history awareness.
- What to do: split relation table into `current` and `historical` views/tables with explicit join guidance and enforced FK strategy.
- Effort: 3-5 days.

3. Add missing FK-supporting indexes.
- What's wrong: 6 FKs detected without prefix indexes.
- Why it matters: avoid table scans/lock amplification on updates/joins as data grows.
- What to do: create indexes for flagged FK columns and validate query plans.
- Effort: <1 day.

4. Externalize frontend API base and deployment config.
- What's wrong: UI hardcodes `http://localhost:8001/api`.
- Why it matters: blocks normal hosted deployment and encourages ad-hoc edits.
- What to do: configurable API base via env-injected script or relative path strategy.
- Effort: <1 day.

### 🟡 Medium
1. Refactor `organizer_v5.html` into modular frontend.
- What's wrong: 9,972-line single-file app with extensive inline handlers.
- Why it matters: slows feature delivery and increases regression probability.
- What to do: split into modules (data, view, charts, map, modals), keep generated build output in `files/`.
- Effort: 1-2 weeks.

2. Create score model versioning and explainability audit trail.
- What's wrong: scoring logic spans docs, API code, and scripts with potential drift.
- Why it matters: organizers need stable, defensible rankings.
- What to do: store per-run factor snapshots and model version IDs; expose in API and UI.
- Effort: 3-5 days.

3. Expand tests for matching/scoring internals.
- What's wrong: limited unit-level safeguards for match precision/recall regressions.
- Why it matters: pipeline changes can silently degrade target quality.
- What to do: fixture-based unit tests for normalization tiers, thresholds, and score computations.
- Effort: 3-5 days.

### 🟢 Low
1. Clean up legacy/duplicate SQL and script inventory.
- What's wrong: mixed active/legacy assets increase cognitive load.
- Why it matters: onboarding and maintenance friction.
- What to do: archive or mark deprecated assets with clear status metadata.
- Effort: 2-3 days.

2. Improve accessibility and mobile behavior.
- What's wrong: minimal responsive rules and accessibility semantics.
- Why it matters: non-technical users in field contexts will struggle.
- What to do: add keyboard navigation, ARIA landmarks, screen-reader announcements, and responsive breakpoints.
- Effort: 1 week.

## Making This Usable for Unions
### What Unions Need
- Fast territory-centric target queues (by geography, sector, employer size).
- Evidence packets per target: safety, wage theft, election history, contract/government funding, comparables.
- Confidence/freshness indicators so staff can trust and defend decisions.
- Collaboration workflow: save lists, notes, status, ownership, export for campaigns.

### What's Missing
- Information gaps: contract expiration timing, richer public-sector case coverage, and stronger Mergent-F7 linkage.
- Workflow gaps: no campaign lifecycle tracking (research -> outreach -> petition -> election -> first contract).
- Usability gaps: monolithic UI, heavy dense tables, weak mobile/accessibility path.
- Trust gaps: confidence values exist in DB but are not consistently surfaced in user flow.
- Access gaps: auth/deployment posture not safe for union-wide access today.

### Must-Have vs Nice-to-Have
Must-have:
- Secure authenticated access.
- Territory workflow with save/share/export and confidence/freshness labels.
- Explainable score breakdown with auditable provenance.
- Data update cadence and visible “last refreshed” per source.

Nice-to-have:
- Advanced corporate hierarchy visualizations.
- Predictive propensity models beyond current heuristics.
- Deep cross-sector comparables and embedding-based similarity.

### Path to Adoption
- MVP unions can use: secure hosted app, stable scorecard, territory queue, target detail packet, export.
- Onboarding/training: 2-hour analyst training + one-page “how to build a target list” playbook.
- Freshness handling: publish refresh schedule and per-panel timestamps.
- Privacy/security: role-based access, audit logs, secret management, and origin-restricted API.
- Practical benchmark: this can outperform ad-hoc spreadsheet workflows once confidence/freshness and campaign workflow are first-class.

## Top 10 Actions (If You Could Only Do 10 Things)
1. Enforce production auth by default and block startup without JWT secret.
2. Restrict CORS to approved origins and remove verbose token error details.
3. Rotate DB credentials and remove all hardcoded/default secret fallbacks.
4. Add missing FK indexes and run plan checks on high-volume joins.
5. Implement explicit historical/current relation separation to resolve orphan-join ambiguity.
6. Standardize and expose match confidence/method in every target detail and export.
7. Externalize frontend API base and deployment config.
8. Refactor `files/organizer_v5.html` into maintainable modules.
9. Add unit/regression tests for matching tiers and scoring factor calculations.
10. Build organizer workflow layer: saved target lists, notes, status, owner, and “evidence packet” export.
