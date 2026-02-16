# Codex Project Briefing — Labor Relations Research Platform
## Paste this at the start of any Codex session where you want it to review code

---

## What This Project Is

I'm building a research platform that pulls together data from multiple U.S. government databases to help unions make smarter decisions about organizing campaigns. Think of it as a search engine that connects the dots between employers, unions, safety violations, election results, and wage theft — all in one place.

**The goal:** When a union organizer wants to research a company, they can see everything — safety record, union election history, wage violations, government contracts, corporate family tree — in one dashboard instead of searching 10 different government websites.

---

## Tech Stack (What Everything Runs On)

- **Database:** PostgreSQL (called `olms_multiyear`), about 20 GB, ~161 tables, 186 views, 4 materialized views, ~23.9M records
- **Backend API:** Python with FastAPI, 152+ endpoints across 17 routers. Entry point: `api/main.py`. Start: `py -m uvicorn api.main:app --reload --port 8001`
- **Frontend:** HTML/JavaScript app — `organizer_v5.html` (2,300 lines markup) + 21 JS files + CSS
- **Data Processing:** Python scripts for importing, cleaning, and matching data
- **Matching Library:** `pg_trgm` (PostgreSQL extension for fuzzy text matching), plus Splink for probabilistic matching
- **Tests:** 240 passing (33 API + 16 auth + 25 data integrity + 53 matching + 39 scoring + 6 XSS + 24 name norm + 12 employer groups + 17 phase3 + 15 misc). Run: `py -m pytest tests/`

---

## The Core Tables (Where The Important Data Lives)

| Table Name | What It Holds | Row Count |
|------------|--------------|-----------|
| `unions_master` | Every union that files financial reports with the government | 26,665 |
| `f7_employers_deduped` | Employers with collective bargaining agreements (current + historical) | 146,863 |
| `f7_union_employer_relations` | Links between unions and employers (who represents who) | ~120,000 |
| `nlrb_elections` | Union election results (votes to form or remove a union) | 33,096 |
| `osha_establishments` | Workplaces tracked by OSHA (safety agency) | 1,007,217 |
| `osha_violations_detail` | Safety violations with penalty amounts | 2,245,020 |
| `osha_f7_matches` | Connections between OSHA workplaces and our employer list | ~145,000 |
| `whd_cases` | Wage theft cases (stolen wages, child labor, etc.) | 363,365 |
| `unified_match_log` | All matches across all sources in one table | ~258,000 |
| `employer_canonical_groups` | Canonical employer grouping (dedup by name+state) | 16,179 |
| `corporate_identifier_crosswalk` | Links between ID systems (SEC, DUNS, EIN, etc.) | 14,561 |
| `mv_employer_search` | Pre-built search index combining all employer sources | 120,169 |
| `mv_organizing_scorecard` | 8-factor employer organizing scores (**union shops excluded**) | 22,389 |
| `v_organizing_scorecard` | Wrapper view adding total `organizing_score` | 22,389 |
| `mergent_employers` | Private company data from a commercial database | ~200,000 |
| `data_source_freshness` | Tracks 15 data sources, ~7M records total | 15 |

---

## How Employer Matching Works (The Hardest Part)

The biggest technical challenge is connecting the same employer across different government databases. "Walmart" in the OSHA database might be "WAL-MART STORES INC" in the NLRB database and "Wal-Mart Associates, Inc." in the union filings.

**Current match rates (F7 employer perspective):** OSHA 28.0%, WHD 9.7%, 990 6.7%, SAM 10.2%, NLRB 8.2%. Overall: 42.6% of F7 employers matched to at least one source.

**Matching pipeline (Phase 3 — COMPLETE):**

1. **Canonical name normalization** — 3 levels: `name_standard` (basic cleanup), `name_aggressive` (strip suffixes, abbreviations), `name_fuzzy` (phonetic). Pre-computed on f7_employers_deduped (146K rows indexed).
2. **Deterministic matcher v3** — 6-tier cascade: exact name+state+city, exact name+state, aggressive+state, EIN, fuzzy (pg_trgm >= 0.65). In-memory indexes (108K+ keys). 868K OSHA records in ~20s.
3. **Probabilistic matching** — Splink for Mergent-to-F7, GLEIF-to-F7, F7 self-dedup.
4. **Unified match log** — All matches written to `unified_match_log` with source_system, match_tier, confidence_band (HIGH/MEDIUM/LOW), confidence_score, evidence JSONB, status.
5. **Match quality dashboard** — `GET /api/admin/match-quality`, `GET /api/admin/match-review`.

**Employer canonical grouping (NEW):**
- Groups employers by `(name_aggressive, UPPER(state))` — same real-world employer appearing as multiple rows gets one canonical representative
- 16,179 groups covering 40,304 employer rows. 403 cross-state groups.
- Canonical rep selected by: current (+100), not-excluded (+50), largest unit (+size/100), recent filing (+10)
- Consolidated workers = SUM of MAX(unit_size) per distinct union within group
- Script: `py scripts/matching/build_employer_groups.py [--dry-run]`

**When reviewing matching code, watch for:**
- Threshold values (too low = false matches, too high = missed matches)
- Whether geographic constraints are applied (matching by name alone produces lots of false positives)
- Proper text normalization before comparison
- Whether the code handles common edge cases: DBA names, abbreviations, parent vs. subsidiary names
- `f7_employer_id` is TEXT type — type mismatch in JOINs causes silent failures
- `psycopg2 %%` for pg_trgm `%` operator — must escape when params tuple is passed

---

## API Structure

The API (v7.1) has 17 routers under `api/routers/`. Entry point is `api/main.py`.

| File | What It Handles | Key Endpoints |
|------|----------------|---------------|
| `employers.py` | Employer search, profiles, comparables, related filings, employer groups | 26+ |
| `nlrb.py` | Union election data, case details | 10 |
| `osha.py` | Safety violations, establishment lookup | 7 |
| `unions.py` | Union profiles, financial data (with consolidated employer view) | 10 |
| `trends.py` | Historical membership trends | 8 |
| `corporate.py` | Corporate family trees | 8 |
| `whd.py` | Wage theft cases | 5 |
| `organizing.py` | Organizing target scoring, score explanations, match quality/review | 10+ |
| `public_sector.py` | Public employers and unions | 6 |
| `sectors.py` | Industry sector analysis | 7 |
| `auth.py` | JWT login, register, refresh, /me | 4 |
| `admin.py` | Scorecard refresh, data freshness, admin operations | 3+ |

**Authentication:** JWT auth enabled by default (`LABOR_JWT_SECRET` in `.env`). Set `DISABLE_AUTH=true` to bypass. First registered user bootstraps as admin. Login rate limiting (10/5min/IP).

**Frontend structure (Phase 2 — COMPLETE):**
The frontend was split from a 10,506-line monolith into:
- `files/organizer_v5.html` (~2,300 lines — markup only, zero inline handlers)
- `files/css/organizer.css` (227 lines)
- 21 JS files under `files/js/` loaded in strict order via plain `<script>` tags (NOT ES modules):
  `config.js` -> `utils.js` -> `maps.js` -> `territory.js` -> `search.js` -> `deepdive.js` -> `detail.js` -> `scorecard.js` -> 8x `modal-*.js` -> `uniondive.js` -> `glossary.js` -> `app.js`
- All functions are global (no import/export). Zero inline `onclick=` handlers — all use `data-action` event delegation.
- **5 app modes:** territory, search, deepdive, uniondive, admin. Wired via `setAppMode()` in app.js.
- **Key constraint:** Duplicate `let`/`const` declarations across files cause `SyntaxError` that kills the entire later file.

---

## The Organizing Scorecard (Key Feature)

The scorecard is a **materialized view** (`mv_organizing_scorecard`) with **22,389 rows** (down from 24,841 after removing union shops). A wrapper view (`v_organizing_scorecard`) adds the total `organizing_score`. Score range is 10-51, average 30.

**CRITICAL CHANGE (Feb 15, 2026): Union shops excluded from scorecard.**
- Establishments matched to F7 employers (already unionized) are now filtered out via `WHERE fm.establishment_id IS NULL`
- `score_company_unions` factor REMOVED (was giving 20pts to union shops only — backwards)
- 170 signatory pattern entries flagged as excluded (e.g., "All Signatories to SAG-AFTRA...")

**The 8 active scoring factors (each computed in SQL):**
1. Industry density — union membership rate in NAICS sector (10 pts)
2. Geographic favorability — state win rate + membership + non-RTW bonus (10 pts)
3. Establishment size — 50-250 employee sweet spot (10 pts)
4. OSHA violations — normalized against industry average (10 pts)
5. NLRB patterns — predicted win rate or blended state+industry rate (10 pts)
6. Government contracts — federal contract obligations (10 pts)
7. Industry growth — BLS employment projections (10 pts)
8. Union similarity — Gower distance to unionized employers (10 pts)

**Score tiers:** TOP >= 30, HIGH >= 25, MEDIUM >= 20, LOW < 20

**Admin refresh:** `POST /api/admin/refresh-scorecard` uses `REFRESH MATERIALIZED VIEW CONCURRENTLY` (requires autocommit via `get_raw_connection()`).

**When reviewing scorecard code, check:**
- That union shops (has_f7_match=TRUE) are excluded from the MV
- That the detail endpoint reads base scores from the MV (no score drift)
- That null/missing data is handled via COALESCE in SQL
- Frontend `SCORE_FACTORS` in config.js has 8 factors (company_unions removed)

---

## What I Need From You (Codex)

Your job is to be a **second pair of eyes on code** that Claude (my primary AI) writes. Specifically:

1. **Logic review** — Does the code actually do what it claims to do?
2. **Edge cases** — What inputs could break it? Empty results? NULL values? Very long strings?
3. **SQL safety** — Are queries properly parameterized (not vulnerable to injection)?
4. **Performance** — Will this be slow on large tables? Missing indexes? Unnecessary full table scans?
5. **Python best practices** — Proper error handling? Resource cleanup? Type issues?
6. **Cross-file JS issues** — Duplicate declarations, functions called before defined, XSS via raw innerHTML
7. **API/frontend alignment** — Do field names in JS match the API response keys?

**You do NOT need to:**
- Understand the full platform architecture (Claude handles that)
- Suggest major redesigns or new features
- Know the history of why things were built a certain way

## Previous Review History

**Sprint 6 review** (`docs/review_codex.md`): 7 issues found, 5 fixed (undefined variable, field mismatches, duplicate function, XSS, stale fallback). 2 deferred.

When reviewing future sprints, check `docs/review_codex.md` for the response table format we use.

---

## Completed Work (What's Already Built and Reviewed)

### Phase 1: Fix Broken (COMPLETE)
- 6 density endpoint crashes fixed (RealDictRow access by index -> by name)
- 29 literal-string password bugs fixed (migrated to `db_config.get_connection()`)
- Auth enforced by default (JWT secret in `.env`, `DISABLE_AUTH=true` to bypass)
- NAICS backfill from OSHA matches
- ANALYZE run on all tables
- README rewritten
- 824 orphan union file numbers tracked (195 from defunct unions)

### Phase 2: Frontend Cleanup (COMPLETE)
- Dual-score remnants fixed (unified `SCORE_FACTORS` + `SCORE_MAX` in config.js)
- modals.js split into 8 modal files
- 68 inline onclick handlers migrated to `data-action` event delegation
- 4-screen structure (territory, search, deepdive/uniondive, admin)
- Confidence/freshness indicators, metrics glossary

### Phase 3: Matching Overhaul (COMPLETE)
- `unified_match_log` (258K entries) — standardized match output
- Canonical name normalization (3 levels + phonetic)
- Deterministic matcher v3 (6-tier cascade, batch-optimized, 868K OSHA in ~20s)
- Splink pipeline v2 (Mergent, GLEIF, F7 self-dedup)
- Match quality dashboard + API
- NLRB bridge view (13K rows, 5.5K employers)
- Historical employer resolution (5,128 merge candidates)
- Employer canonical grouping (16,179 groups, 40K+ employers)
- Scorecard misclassification fix (union shops removed, signatories excluded)

### Next: Phase 4 (New Data Sources)
- SEC EDGAR full index (300K+ companies)
- IRS Business Master File (all nonprofits)
- CPS microdata via IPUMS
- OEWS staffing patterns
- BLOCKED until Phase 3 done (NOW DONE)

---

## Common Patterns You'll See

### Database queries use psycopg2 with parameterized queries:
```python
cur.execute("SELECT * FROM employers WHERE state = %s AND name ILIKE %s", (state, f"%{query}%"))
```

### RealDictCursor (pool default) — access by column name, not index:
```python
conn = get_connection()  # from db_config
cur = conn.cursor()  # RealDictCursor by default
row = cur.fetchone()
name = row['employer_name']  # CORRECT
# name = row[0]  # WRONG — causes crashes
```

### Dynamic WHERE clauses (safe pattern):
```python
conditions = []
params = []
if state:
    conditions.append("state = %s")
    params.append(state.upper())
where_clause = " AND ".join(conditions)
cur.execute(f"SELECT ... WHERE {where_clause}", params)
```

### Event delegation (frontend pattern):
```html
<button data-action="openDeepDive" data-action-arg="emp_123">View</button>
```
```javascript
// In app.js initEventListeners()
document.addEventListener('click', e => {
    const action = e.target.closest('[data-action]')?.dataset.action;
    if (action === 'openDeepDive') openDeepDive(e.target.dataset.actionArg);
});
```

---

## Current Roadmap (TRUE Roadmap — February 15, 2026)

**Source document:** `Roadmap_TRUE_02_15.md`

| Phase | Status | Weeks |
|-------|--------|-------|
| 1: Fix Broken | **COMPLETE** | Week 1 |
| 2: Frontend Cleanup | **COMPLETE** | Weeks 2-4 |
| 3: Matching Overhaul | **COMPLETE** | Weeks 3-7 |
| 4: New Data Sources | **NEXT** | Weeks 8-10 |
| 5: Scoring Evolution | Planned | Weeks 10-12 |
| 6: Deployment Prep | Planned | Weeks 11-14 |
| 7: Intelligence | Planned | Week 14+ |

**Critical path:** P1 -> P3 -> P4 -> P5 Advanced. P6 independent after P1.

---

*Last updated: February 15, 2026 (Phase 3 complete, scorecard misclassification fixed)*
*Context: This briefing was written so you can effectively review code without needing the full project history.*
