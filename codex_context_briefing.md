# Codex Project Briefing — Labor Relations Research Platform
## Paste this at the start of any Codex session where you want it to review code

---

## What This Project Is

I'm building a research platform that pulls together data from multiple U.S. government databases to help unions make smarter decisions about organizing campaigns. Think of it as a search engine that connects the dots between employers, unions, safety violations, election results, and wage theft — all in one place.

**The goal:** When a union organizer wants to research a company, they can see everything — safety record, union election history, wage violations, government contracts, corporate family tree — in one dashboard instead of searching 10 different government websites.

---

## Tech Stack (What Everything Runs On)

- **Database:** PostgreSQL (called `olms_multiyear`), about 33GB, ~207 tables, ~13.5 million records
- **Backend API:** Python with FastAPI, about 142 endpoints (web addresses the frontend calls to get data)
- **Frontend:** HTML/JavaScript app — `organizer_v5.html` (markup) + 10 JS files + CSS (split in Sprint 6)
- **Data Processing:** Python scripts for importing, cleaning, and matching data
- **Matching Library:** `pg_trgm` (PostgreSQL extension for fuzzy text matching — finds similar-but-not-identical names)

---

## The Core Tables (Where The Important Data Lives)

When you see code referencing these table names, here's what they contain:

| Table Name | What It Holds | Row Count |
|------------|--------------|-----------|
| `unions_master` | Every union that files financial reports with the government | 26,665 |
| `f7_employers_deduped` | Employers that have collective bargaining agreements (current + historical) | 113,713 |
| `f7_union_employer_relations` | The links between unions and employers (who represents who) | ~120,000 |
| `nlrb_elections` | Union election results (votes to form or remove a union) | 33,096 |
| `osha_establishments` | Workplaces tracked by OSHA (safety agency) | 1,007,217 |
| `osha_violations_detail` | Safety violations with penalty amounts | 2,245,020 |
| `osha_f7_matches` | Connections we've built between OSHA workplaces and our employer list | ~80,000 |
| `whd_cases` | Wage theft cases (stolen wages, child labor, etc.) | 363,365 |
| `ps_employers` | Public sector employers (governments, school districts, etc.) | 7,987 |
| `corporate_hierarchy` | Corporate parent-child relationships | 125,120 |
| `corporate_identifier_crosswalk` | Links between different ID systems (SEC, DUNS, EIN, etc.) | 14,561 |
| `mv_employer_search` | A pre-built search index combining all employer sources | 120,169 |
| `mv_organizing_scorecard` | Materialized view: 9-factor employer organizing scores | 24,841 |
| `v_organizing_scorecard` | Wrapper view adding total `organizing_score` (sum of 9 factors) | 24,841 |
| `mergent_employers` | Private company data from a commercial database | ~200,000 |

---

## How Employer Matching Works (The Hardest Part)

The biggest technical challenge is connecting the same employer across different government databases. "Walmart" in the OSHA database might be "WAL-MART STORES INC" in the NLRB database and "Wal-Mart Associates, Inc." in the union filings.

**The matching approach uses multiple steps:**
1. **Exact match** on normalized names (lowercase, remove "inc", "llc", punctuation, etc.)
2. **Fuzzy match** using trigram similarity (a score from 0 to 1 measuring how similar two text strings look — we typically use 0.75-0.85 thresholds)
3. **Geographic verification** — names must match AND be in the same city/state
4. **Manual review flags** — humans can mark matches as correct, incorrect, or needing review

**When reviewing matching code, watch for:**
- Threshold values (too low = false matches, too high = missed matches)
- Whether geographic constraints are applied (matching by name alone produces lots of false positives)
- Proper text normalization before comparison
- Whether the code handles common edge cases: DBA names ("doing business as"), abbreviations, parent vs. subsidiary names

---

## API Structure

The API (v7.0) was decomposed from a monolith into 16 focused routers under `api/routers/`. Entry point is `api/main.py`. Start command: `py -m uvicorn api.main:app --reload --port 8001`.

| File | What It Handles | Endpoint Count |
|------|----------------|----------------|
| `employers.py` | Employer search, profiles, comparables | 24 |
| `nlrb.py` | Union election data, case details | 10 |
| `osha.py` | Safety violations, establishment lookup | 7 |
| `unions.py` | Union profiles, financial data | 8 |
| `trends.py` | Historical membership trends | 8 |
| `corporate.py` | Corporate family trees (uses `corporate_hierarchy` + `corporate_identifier_crosswalk`) | 8 |
| `whd.py` | Wage theft cases | 5 |
| `organizing.py` | Organizing target scoring | 5 |
| `public_sector.py` | Public employers and unions | 6 |
| `sectors.py` | Industry sector analysis | 7 |
| `auth.py` | JWT login, register, refresh, /me | 4 |
| `admin.py` | Scorecard refresh, admin operations | 1+ |

**Authentication:** JWT auth is available (disabled by default). Enable by setting `LABOR_JWT_SECRET` in `.env` (32+ chars). First registered user bootstraps as admin. Login rate limiting (10/5min/IP).

**Test suite:** 162 tests passing (30 API + 16 auth + 24 data integrity + 51 matching + 39 scoring). Run with `py -m pytest tests/`.

**Frontend structure (Sprint 6 split):**
The frontend was split from a 10,506-line monolith into:
- `files/organizer_v5.html` (2,139 lines — markup only)
- `files/css/organizer.css` (228 lines)
- 10 JS files under `files/js/` loaded in strict order via plain `<script>` tags (NOT ES modules):
  `config.js` -> `utils.js` -> `maps.js` -> `territory.js` -> `search.js` -> `deepdive.js` -> `detail.js` -> `scorecard.js` -> `modals.js` -> `app.js`
- All functions are global (no import/export). 103 inline `onclick=` handlers in HTML.
- Global state in `config.js`, module-scoped state (`let` vars) in individual files.
- **Key constraint:** Duplicate `let`/`const` declarations across files cause `SyntaxError` that kills the entire later file.

**Score explanations (Sprint 6):**
- 10 helper functions in `api/routers/organizing.py` (lines ~97-238) generate plain-language explanation strings
- `_build_explanations(row, is_rtw, win_rate)` aggregates all 9 into a dict
- API returns `score_explanations` in scorecard list + detail responses
- Frontend `getScoreReason()` in `scorecard.js` prefers server explanations, falls back to client-side logic

**Remaining known issues:**
- `f7_employers_deduped` has no primary key
- 73% of indexes never scanned (2.1 GB wasted space)
- F7 employer duplicates — multi-employer agreements (SAG-AFTRA) create duplicate rows with inflated worker counts
- F7 `unit_size` ≠ actual employees — misleading when sorted by "workers"

---

## The Organizing Scorecard (Key Feature)

The scorecard is now a **materialized view** (`mv_organizing_scorecard`) with 24,841 rows, computed entirely in SQL. A wrapper view (`v_organizing_scorecard`) adds the total `organizing_score` (sum of 9 factors). Score range is 10-78, average 32.3.

**The 9 scoring factors (each computed in SQL):**
1. OSHA violations (safety problems = worker dissatisfaction)
2. Industry union density (how unionized is this industry already?)
3. Geographic presence (are there unions nearby?)
4. Establishment size (bigger = more potential members)
5. NLRB momentum (recent election activity in the area)
6. Government contracts (leverage point — contractors must follow labor laws)
7. WHD wage violations (wage theft history)
8. Multi-establishment presence (employer has multiple locations)
9. Corporate complexity (depth of corporate hierarchy)

**Score tiers:** TOP >= 30, HIGH >= 25, MEDIUM >= 20, LOW < 20

**Admin refresh:** `POST /api/admin/refresh-scorecard` uses `REFRESH MATERIALIZED VIEW CONCURRENTLY` (requires autocommit via `get_raw_connection()`). The unique index on `establishment_id` enables concurrent refresh without locking.

**When reviewing scorecard code, check:**
- That the detail endpoint reads base scores from the MV (no score drift from recalculation)
- That null/missing data is handled via COALESCE in SQL
- That `get_raw_connection()` is used for REFRESH CONCURRENTLY (not the connection pool)

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
- Suggest major redesigns or new features (e.g., splitting modals.js into 11 files — we considered and rejected this)
- Know the history of why things were built a certain way

## Previous Review History

**Sprint 6 review** (`docs/review_codex.md`): You found 7 issues, 5 were fixed:
1. FIXED: `renderTrendsChart(financials)` — undefined variable at detail.js:1055
2. FIXED: Scorecard field mismatches (`state_density`→`geographic`, `contract_count`→`federal_contract_count`)
3. FIXED: Duplicate `getSourceBadge()` in utils.js and modals.js
4. FIXED: XSS raw innerHTML in scorecard.js
5. FIXED: Stale `getScoreReason()` fallback (old 100-500 sweet spot, wrong NLRB/OSHA buckets)
6. DEFERRED: Score explanation helpers not fully aligned with scoring sub-factors (intentionally simplified)
7. DEFERRED: Inconsistent `response.ok` checks in some fetch paths

When reviewing future sprints, check `docs/review_codex.md` for the response table format we use.

---

## Common Patterns You'll See

### Database queries use psycopg2 with parameterized queries:
```python
cur.execute("SELECT * FROM employers WHERE state = %s AND name ILIKE %s", (state, f"%{query}%"))
```

### Dynamic WHERE clauses (this pattern is safe — conditions are hardcoded, only values are parameters):
```python
conditions = []
params = []
if state:
    conditions.append("state = %s")
    params.append(state.upper())
where_clause = " AND ".join(conditions)
cur.execute(f"SELECT ... WHERE {where_clause}", params)
```

### Fuzzy matching with pg_trgm:
```python
cur.execute("""
    SELECT *, similarity(name_normalized, %s) as sim
    FROM employers
    WHERE similarity(name_normalized, %s) > 0.75
    ORDER BY sim DESC
""", (normalized_name, normalized_name))
```

---

*Last updated: February 14, 2026 (after Sprint 6 completion + review fixes)*
*Context: This briefing was written so you can effectively review code without needing the full project history.*
