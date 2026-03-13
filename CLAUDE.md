# Labor Relations Research Platform

> For detailed schema see `.claude/specs/database-schema.md`.
> For API endpoints see `.claude/specs/api-endpoints.md`.
> For project status see `Start each AI/PROJECT_STATE.md`.
> For the roadmap see `COMPLETE_PROJECT_ROADMAP_2026_03.md` (supersedes Feb 26 roadmap).
> Domain agents in `.claude/agents/`, on-demand specs in `.claude/specs/`.

---

## 1. Domain Context

This is a labor organizing data platform. Key distinction:

- **F7 employers = UNION reference data.** These employers already have union contracts/CBAs. They are NOT scoring targets. They are "training data" — what does an organized workplace look like?
- **The scorecard scores NON-UNION employers** as investigation targets for organizers. They are "candidates" — which unorganized workplaces share those characteristics?
- **We flag for investigation, not predict outcomes.** The score highlights structural signals (violations, NLRB activity, contracts, industry trends) — it does not predict whether a union drive will succeed.
- **F7 counts bargaining units, not members.** Closer to BLS "represented by" than membership. Not exhaustive. Don't obsess over matching BLS membership numbers — what matters is "this company has a union here."
- **Size is a filter dimension, not a scoring signal** — an organizer already knows what size shop they're looking for (weight = 0).
- Never conflate union reference employers with non-union scoring targets.

---

## 2. Workflow

- **Start coding promptly.** Do not spend more than 2-3 minutes on exploration/planning before writing code, unless the user explicitly asks for a plan first.
- **When presenting roadmaps or task lists, be comprehensive.** Include ALL remaining items. If unsure of scope, ask.
- **After implementing changes, run the full test suite** and report pass counts before committing. Do not commit with failing tests unless explicitly told to.
- **Commit only when explicitly asked.** Do not proactively commit.
- **Keep responses short and concise.** Use ASCII in print statements (not Unicode arrows) — Windows cp1252 crashes on them.

---

## 3. Database Conventions

### Connection
```python
from db_config import get_connection
conn = get_connection()
```
Credentials in `.env` at project root. `db_config.py` (project root, 500+ imports, never move) is the shared connection module. Never use inline `psycopg2.connect()`.

### Cursor Patterns
- **`get_connection()` returns plain psycopg2** — default cursor uses tuples (`row[0]`). Pass `cursor_factory=RealDictCursor` for dict access. Pool-based code uses RealDictCursor by default.
- **`SELECT EXISTS(...)` with RealDictCursor** — MUST alias: `SELECT EXISTS(...) AS e`.
- **`SELECT COUNT(*)` with RealDictCursor** — alias as `AS cnt` for clarity, or use `['count']`.
- **psycopg2 returns Decimal for DECIMAL columns** — wrap in `float()` before arithmetic with Python float literals.
- **psycopg2 auto-deserializes JSONB** — `json.loads()` on JSONB column fails because it's already a dict. Check `isinstance(val, dict)` first.

### Schema Safety
- **Always verify column names against the actual database** before writing queries. Run `\d table_name` or equivalent — do not rely on assumptions.
- **For materialized views, use `pg_attribute`** — `information_schema.columns` does NOT include MVs.
- **Before schema changes (DROP CASCADE, ALTER, column renames),** check for dependent MVs, FKs, and downstream tables. Rebuild affected MVs immediately after.
- **Never use `TRUNCATE ... CASCADE` on parent FK tables** — it cascades to child tables.
- **`REFRESH MATERIALIZED VIEW CONCURRENTLY` does NOT update SQL definition** — must DROP + CREATE if SQL changes.
- **`pg_type_typname_nsp_index` duplicate key on CREATE MV** — if DROP MV doesn't fully clean up, use `autocommit=True` for DROP, verify with SELECT, then CREATE in new connection.

### Check Constraints
- **`master_employer_source_ids.chk_master_source_system`** and **`master_employers.chk_master_source_origin`** have hardcoded allowed value lists. Adding a new source (e.g., 'corpwatch') requires `ALTER TABLE DROP CONSTRAINT` + recreate with new value. `seed_master()` now checks/updates at runtime.

### Type Gotchas
- **`f7_employer_id` is TEXT** everywhere. All match tables must use TEXT.
- **`union_file_number` is INTEGER** in `f7_union_employer_relations` but `f_num` is VARCHAR in `unions_master` — always CAST when joining.
- **`master_employers` PK is `master_id`, NOT `id`** — `me.id` doesn't exist. Name column is `display_name` not `name`.
- **`f7_employers_deduped.cbsa_code` is 100% NULL** — don't join on it.

### SQL Patterns
- **psycopg2 `%%` for pg_trgm `%` operator** — only when params tuple is passed. No params = use single `%`.
- **`ARRAY_AGG(... LIMIT N)` doesn't work in PostgreSQL** — use `(ARRAY_AGG(...))[1:N]`.
- **ON CONFLICT in execute_batch** — must deduplicate WITHIN the batch too, not just rely on ON CONFLICT.
- **DDL before DML** — CHECK constraint updates (ALTER TABLE) need `conn.autocommit=True`. Switch to `autocommit=False` for seed INSERT. Mixing DDL commits inside `autocommit=False` causes silent failures.
- **Large UPDATE on big tables (1.9M+ rows)** — self-join CTE takes 30+ min. Split into separate transactions; consider batched approach.
- **Large INSERT with CTE+DISTINCT ON+NOT EXISTS hangs** — break into staged approach: 1) CREATE TEMP TABLE, 2) INDEX it, 3) DELETE already-existing, 4) INSERT remainder.

---

## 4. Environment

- **Windows with Git Bash.** Python 3.14 (`py` command). Node.js for frontend.
- **`.env` file at project root** stores DB creds and JWT secret. The custom loader in `db_config.py` uses `setdefault` — shell env vars take precedence.
- **`DISABLE_AUTH=true` in `.env`** bypasses backend JWT auth. Frontend uses `VITE_DISABLE_AUTH=true` in `frontend/.env`.
- **Stale processes can hold ports.** Always check for zombie uvicorn/vite/node processes before debugging connection issues. Use `powershell -Command "Get-CimInstance Win32_Process -Filter \"CommandLine like '%uvicorn%'\""` to find them.
- **Windows cp1252 encoding** — Unicode arrows/symbols crash stdout. Use ASCII or set `PYTHONIOENCODING=utf-8`.
- **Do NOT pipe Python output through grep on Windows** — no SIGPIPE, Python hangs as zombie. Run Python directly.
- **`py -c` with `!` in passwords** — write to .py file instead of inline (bash interprets `!`).
- **Windows process killing** — `taskkill /PID` fails in Git Bash (path conversion). Use `powershell -Command "Stop-Process -Id PID -Force"`.
- **Python 3.14** — `\s` escape warnings. passlib incompatible with bcrypt 5.x.
- **Crawl4AI on Windows** — browser init prints Unicode arrows that crash cp1252 stdout. Redirect sys.stdout/stderr to UTF-8 `io.TextIOWrapper(io.BytesIO())` during `asyncio.run()`, restore after.

---

## 5. Key Commands

```bash
# Backend
cd "C:\Users\jakew\.local\bin\Labor Data Project_real"
py -m uvicorn api.main:app --reload --port 8001

# Frontend
cd frontend && VITE_DISABLE_AUTH=true npx vite
# (frontend/.env has VITE_DISABLE_AUTH=true)

# Tests
py -m pytest tests/ -x -q          # backend (~1135 tests)
cd frontend && npx vitest run       # frontend (~184 tests)

# MV rebuild (orchestrated)
py scripts/scoring/refresh_all.py              # full chain
py scripts/scoring/refresh_all.py --skip-gower # skip slow Gower step
py scripts/scoring/refresh_all.py --with-report # with score change report

# Auto-metrics
py scripts/maintenance/generate_project_metrics.py
```

---

## 6. Testing Protocol

### Backend
- **Command:** `py -m pytest tests/ -x -q`
- **Current count:** ~1135 tests passing, 0 failures, 3 skipped
- **Run after every code change.** Report exact pass count before committing.
- **Match rate tests are F7-only** — `osha_f7_matches`/`whd_f7_matches` track matches to F7 (union employers only). Rates are ~8.3%/~4.7%. Don't set thresholds expecting high rates.
- **`RESEARCH_SCRAPER_GOOGLE_FALLBACK=false`** — set in tests that mock DB to prevent real URL resolution (Tier 4 Google Search).
- **`_LOGIN_MAX=999`** — test fixture patches this in auth tests.

### Frontend
- **Command:** `cd frontend && npx vitest run`
- **Current count:** ~240 tests passing, 0 failures
- **Vitest + RTL + jsdom.** Mock API hooks with `vi.mock('@/shared/api/...')`. Wrap in `QueryClientProvider` + `MemoryRouter`.
- **Color assertions:** Use `container.innerHTML.includes('bg-[#hex]')` not CSS selector queries (jsdom bracket escaping issues).
- **Text changes break tests:** Always grep `__tests__/` for old text strings when changing UI copy.
- **`IntersectionObserver` mock** needed in `__tests__/setup.js` when using it in components.
- **`CollapsibleCard` with `defaultOpen=false`** does NOT render children until expanded — must click header in tests.

---

## 7. Architecture Overview

### Data Flow
```
Source Data (F7, OSHA, WHD, SAM, NLRB, 990, BMF, Mergent, SEC, GLEIF, CorpWatch)
  |
  v
ETL Loaders (scripts/etl/) -> Raw/Source Tables
  |
  v
Deterministic Matcher (scripts/matching/run_deterministic.py)
  -> unified_match_log (2.2M audit trail)
  -> Source-specific match tables (osha_f7_matches, whd_f7_matches, etc.)
  |
  v
Corporate Crosswalk (scripts/etl/build_crosswalk.py)
  -> corporate_identifier_crosswalk (17,111 rows, links SEC/GLEIF/Mergent/CorpWatch/F7)
  |
  v
Scoring Pipeline (scripts/scoring/)
  -> mv_organizing_scorecard (212K OSHA establishments)
  -> mv_unified_scorecard (146,863 F7/union employers, 10 factors)
  -> mv_target_scorecard (4.4M non-union targets, 8 signals)
  -> mv_employer_search (107K search index)
  |
  v
FastAPI (api/main.py, port 8001) -> React Frontend (frontend/)
```

### Two Scorecard Tracks

**Union Reference Track (F7-based):**
- `mv_unified_scorecard` — 146,863 rows (1:1 with f7_employers_deduped)
- 10 factors (each 0-10): OSHA, NLRB, WHD, Contracts, Union Proximity, Financial, Industry Growth, Size (weight=0), Similarity (weight=1 nominally, 0% non-NULL)
- Pillar formula: `weighted_score = (anger*3 + leverage*4) / active_weights` (stability zeroed, dynamic denominator)
- Tiers: Priority (~2.0%), Strong (~10.2%), Promising (~27.7%), Moderate (~34.3%), Low (~25.8%)

**Non-Union Target Track:**
- `mv_target_scorecard` — 4,386,205 rows (from master_employers)
- 8 signals: OSHA, WHD, NLRB, Contracts, Financial, Industry Growth, Union Density, Size
- Gold standard tiers: stub -> bronze (3+ signals or research) -> silver -> gold -> platinum
- 882 bronze tier, 25.5% with enforcement signals

### MV Dependency Chain
```
create_scorecard_mv.py        # OSHA-based organizing scorecard
  -> compute_gower_similarity.py  # Gower distance, employer_comparables
    -> build_employer_data_sources.py  # 13-source flag MV
      -> build_unified_scorecard.py    # 10-factor union reference scorecard
        -> build_target_data_sources.py  # Non-union source flags
          -> build_target_scorecard.py   # Non-union 8-signal scorecard
            -> rebuild_search_mv.py      # Unified search index
```

**DROP CASCADE warning:** Rebuilding crosswalk drops dependent MVs. Must rebuild entire chain.

### Corporate Crosswalk
- **`corporate_identifier_crosswalk`** — 17,111 rows. Links SEC, GLEIF, Mergent, CorpWatch, F7. (USASpending tier needs re-run after crosswalk rebuild.)
- **Tiers:** EIN_EXACT > LEI_EXACT > EIN_F7_BACKFILL > NAME_STATE > USASPENDING
- **Script:** `PYTHONPATH=. py scripts/etl/build_crosswalk.py` (DROP+CREATE). Then `_match_usaspending.py` for federal columns.
- **F7 coverage:** 12,534 (8.5% of 146,863).

---

## 8. Scoring & Matching Summary

### Matching Pipeline (6-Tier Deterministic Cascade)
| Tier | Method | Confidence | Description |
|------|--------|-----------|-------------|
| 1 | EIN exact | 100 | Employer Identification Number |
| 2 | NAME_CITY_STATE | 90 | Normalized name + city + state |
| 3 | NAME_STATE | 80 | Normalized name + state |
| 4 | AGGRESSIVE | 60 | Aggressive normalization + state |
| 5a | RapidFuzz | 45 | token_sort_ratio >= 0.80, 3 blocking indexes |
| 5b | Trigram | 40 | pg_trgm fallback, 0.75 similarity floor |

- **Best-match-wins:** Higher tier supersedes lower.
- **RapidFuzz replaced Splink** — Splink geography overweighting was unfixable. match_method still = `'FUZZY_SPLINK_ADAPTIVE'` for backward compat.
- **Fuzzy FP rates:** 0.80-0.85=40-50%, 0.85-0.90=50-70%, 0.90-0.95=30-40%. Below-0.85 deactivated.

### Unified Scorecard (10 Factors, 3 Pillars)

**Pillar Architecture (Round 4 audit batch 3):**
- **Anger** (weight 3): OSHA + WHD + ULP, dynamic sub-factor denominator
- **Stability** (weight 0): zeroed pending data coverage; kept for display
- **Leverage** (weight 4): proximity + similarity + contracts + financial + growth + size, dynamic sub-factor denominator
- **Formula:** `weighted_score = (anger*3 + leverage*4) / active_pillar_weights`
- Dynamic denominator at both pillar and final level: NULL pillars do not inflate or deflate scores

| Factor | Coverage | Weight (in pillar) | Predictive Power |
|--------|----------|-------------------|-----------------|
| NLRB | 17.6% | Anger sub-factor (4/10) | +10.2 pp (strongest) |
| Industry Growth | 84.9% | Leverage sub-factor (10/100) | +9.6 pp |
| Contracts | 5.9% | Leverage sub-factor (20/100) | +5.7 pp |
| WHD | 7.7% | Anger sub-factor (3/10) | +4.1 pp |
| Financial | 7.3% | Leverage sub-factor (20/100) | +4.1 pp |
| OSHA | 22.3% | Anger sub-factor (3/10) | -0.6 pp (predicts losses) |
| Union Proximity | 100% | Leverage sub-factor (25/100) | +0.0 pp (zero power) |
| Size | 100% | Leverage sub-factor (15/100) | +0.2 pp (zero power) |
| Similarity | 0% | Leverage sub-factor (10/100) | N/A (0% non-NULL) |

**Research quality dual-gate:** >=7.0 enhances scores, 5.0-6.9 saves as unverified notes, <5.0 rejected.

**Pillar weight validation (2026-03-02):** Logistic regression on 6,403 NLRB outcomes shows anger is the strongest predictor (coeff 0.12), stability slightly negative, leverage weak. Model accuracy = base win rate (79.9%), confirming pillars don't add marginal predictive power. This is expected -- the score flags for investigation, not prediction. Current weights (3-0-4) kept. See `docs/pillar_weight_validation.csv`.

### Audit-Validated Findings
- **Score IS predictive** — win rates monotonic by tier: Priority 90.9%, Strong 84.7%, Low 74.1%
- **Selection bias:** Only 34% of NLRB elections link to scored employers. F7-matched baseline is 80.8%.
- **Data richness paradox:** Fewer factors = higher win rates (2-factor=88.2%, 8-factor=73.4%).
- **Priority tier:** ~2,891 employers (post-batch-3 rebalance). D1/D7 decision: NO enforcement gate.
- **Propensity model KILLED** — was hardcoded formula (coin-flip accuracy). Code archived.

---

## 9. Known Failure Modes

### Database
| Symptom | Cause | Fix |
|---------|-------|-----|
| `column "X" does not exist` on MV | MV not rebuilt after schema change | DROP + CREATE MV (not just REFRESH) |
| `duplicate key on pg_type_typname_nsp_index` | Incomplete DROP MV in transaction | Use `autocommit=True` for DROP, verify, CREATE in new connection |
| Silent INSERT failures | f7_employer_id type mismatch (TEXT vs INT) | Ensure all match tables use TEXT |
| `UndefinedTable` on sector views | Museum/sector views never created | Wrap in try/except, return 404 |
| CHECK constraint violation on master tables | New source system not in allowed list | ALTER DROP CONSTRAINT + recreate |
| Missing columns on API endpoint | MV not rebuilt yet, SELECT references new col | Use `_has_col()` pattern: check `pg_attribute` at startup |
| 503 from API on DB error | psycopg2 catch-all handler masks all errors | Add specific error handling or remove catch-all |

### Matching
| Symptom | Cause | Fix |
|---------|-------|-----|
| 0 matches from exact name match | Case mismatch (F7=mixed, source=UPPER) | Wrap both sides in `UPPER(TRIM())` |
| Cross-join explosion on similarity() | No blocking/candidate retrieval | Use `%` operator (GIN-indexed) |
| OSHA match rates seem low (~8.3%) | F7-only matches; non-union go through master_employer_source_ids | Don't set high thresholds |
| Fuzzy match FP rates high (40-70%) | Token similarity conflates similar names | No clean threshold; below-0.85 deactivated |
| Regex strips lowercase | `[^A-Z0-9 ]` instead of `[^A-Za-z0-9 ]` | Use `re.IGNORECASE` |

### Frontend / API
| Symptom | Cause | Fix |
|---------|-------|-----|
| Test fails on color assertion | Changed Tailwind class from `bg-red-600` to `bg-[#hex]` | Use `innerHTML.includes()` |
| Test fails on text content | Changed UI copy | grep `__tests__/` for old strings |
| `financial_trends`/`sister_locals` blank | API must return these fields | Verify API response shape |
| FastAPI route not matched | Parameterized `/{id}` registered before fixed path | Fixed-path routes BEFORE parameterized |
| Stale route behavior | `__pycache__` serving old code | Delete `__pycache__` |

### Data
| Symptom | Cause | Fix |
|---------|-------|-----|
| F7 has no EIN | F7 is private-sector only, no EIN column | Match by name+state or through crosswalk |
| `group_max_workers` is NULL | Never populated | Use BU-level data (median 28 workers) |
| OSHA `union_status` codes inconsistent | N/Y used 2012-2016, A/B used 2015+ | Filter on `!= 'Y'`, NOT `= 'N'` |
| SAM entities barely overlap with F7 | Different domains (govt contractors vs union employers) | ~0% match expected |
| NLRB elections has NO `state` column | State is in `nlrb_participants` | JOIN to get state |
| `bls_industry_occupation_matrix` wrong column names | Columns are `employment_2024`, NOT `emp_2024` | Always verify with `\d` |
| CorpWatch fuzzy matching fails | SEC-style names don't fuzzy-match F7 names | Exact-only for CorpWatch |
| SQL LIKE misses variants | `LIKE '%FED EX%'` doesn't match `FEDEX` | Generate both spaced and stripped patterns |

---

## 10. Agent Trigger Table

Specialist agents in `.claude/agents/` are loaded automatically by Claude Code based on file patterns and task context. Each agent embeds domain knowledge, correctness invariants, and failure modes for its domain.

| Agent | File Patterns | Task Keywords | Primary Spec |
|-------|---------------|---------------|-------------|
| `matching` | `scripts/matching/**`, `scripts/etl/seed_master*`, `scripts/etl/dedup*` | match, link, deduplicate, fuzzy, RapidFuzz, UML | `specs/matching-pipeline.md` |
| `scoring` | `scripts/scoring/**` | score, factor, tier, MV, scorecard, pillar, weight | `specs/scoring-system.md` |
| `etl` | `scripts/etl/**` (non-matching) | load, ingest, ETL, COPY, seed, CHECK constraint | `specs/database-schema.md` |
| `frontend` | `frontend/src/**` | React, component, Tailwind, theme, test, TanStack | `specs/redesign-spec.md` |
| `api` | `api/**` | endpoint, router, FastAPI, auth, response shape | `specs/api-endpoints.md` |
| `research` | `scripts/research/**` | research, dossier, Gemini, grading, contradiction | — |
| `database` | — | schema, ALTER, CREATE TABLE, migration, index, constraint | `specs/database-schema.md` |
| `maintenance` | `scripts/maintenance/**`, `docker*` | MV refresh, dedup, backup, metrics, Docker | `specs/pipeline-manifest.md` |
| `cba` | `scripts/cba/**`, `config/cba_rules/**` | CBA, contract, provision, rule engine, extraction | — |

**Usage:** When working on files matching these patterns, consult the corresponding agent. When an agent needs deeper reference data, it loads the linked spec from `.claude/specs/`.

---

## 11. Files That Matter

### Core
- `db_config.py` — shared DB connection (500+ imports, never move)
- `api/main.py` — FastAPI app, port 8001
- `frontend/` — React 19, Vite 7, TanStack, Zustand, Tailwind 4
- `.env` — credentials (never commit)

### Scripts
- `scripts/scoring/` — all scorecard/MV build scripts (10 scripts)
- `scripts/matching/` — deterministic matcher, adapters (19 + 13 sub)
- `scripts/research/` — research agent (14 tools, Gemini)
- `scripts/etl/` — data loaders (43+ scripts)
- `scripts/cba/` — CBA pipeline (8 scripts)
- `scripts/maintenance/` — MV refresh, dedup, backup (8 scripts)
- `scripts/analysis/` — ad-hoc analysis (54 scripts)

### Documentation
- `.claude/agents/` — 9 domain-specialist agent specs (Tier 2)
- `.claude/specs/` — 12 on-demand reference specs (Tier 3)
- `.claude/skills/` — 6 user-invoked skills (start, ship, debug, schema-check, rebuild-mvs, union-research)
- `PROJECT_CATALOG.md` — comprehensive file catalog (~755 code files, every section)
- `DOCUMENT_INDEX.md` — master catalog of all project documentation
- `Start each AI/PROJECT_STATE.md` — shared AI context (multi-tool)
- `Start each AI/CLAUDE.md` — shared technical reference (multi-tool)
- `COMPLETE_PROJECT_ROADMAP_2026_03.md` — authoritative roadmap (62 tasks, 36 open questions)

### Tests
- `tests/` — backend tests (~1135)
- `frontend/src/**/*.test.jsx` — frontend tests (~233)

---

## 12. Project Status

### Current Phase (2026-03-01)
- **Phase R2: Improved HITL Review UX — DONE.** Run usefulness, flag-only review, A/B comparison, section review, active learning prompts. 6 new API endpoints, 3 learning functions, 2 new frontend components.
- **Phase R1: Research Agent Learning Loop — DONE.** Contradiction detection, human fact review API, learning propagation, frontend review UI.
- **Phase 5 Frontend Redesign — DONE.** All pages redesigned with "Aged Broadsheet" visual theme.
- **Phase 3 Workstreams A+B+C+D — DONE.** Research quality, similarity rebuild, wage outliers, demographics API.
- **All tests pass:** ~1135 backend (0 failures, 3 skipped), 240 frontend (0 failures).

### Active Decisions
| ID | Decision | Status |
|----|----------|--------|
| D1/D7 | No enforcement gate for any tier | CLOSED |
| D5 | Industry Growth weight increase to 3x? | Open |
| D11 | Scoring framework overhaul (Anger/Stability/Leverage) | Implemented (batch 3): stability zeroed, dynamic denominator |
| D12 | Union Proximity weight (3x despite zero power) | Open |

### Deferred (do NOT prompt about until roadmap mostly done)
- Phase 2 remaining re-runs (SAM/WHD/990/SEC with RapidFuzz)
- Phase 2.4 grouping quality
- Phase 2.5 master dedup

### Round 4 Audit Batch 3 (2026-03-01) -- DONE
- **1-1:** Gower similarity (pending re-run, pipeline intact)
- **1-2:** Stability weight zeroed (was 3, now 0)
- **1-8:** Union designation TRIM (already clean)
- **1-10:** Recommended action (API-only, computed at request time)
- **1-14:** Nightly backup via Task Scheduler (2AM daily, 7-day retention)
- **1-15:** Pillar weight validation script (`scripts/analysis/validate_pillar_weights.py`)
- **2-1:** Dynamic denominator at pillar + final formula level
- **2-3:** `refresh_all.py` MV rebuild orchestrator
- **2-4:** Extended `generate_project_metrics.py` -> `PLATFORM_STATUS.md`
- **2-5:** Documentation updates (scoring formulas, tier counts, weights)
- **2-6:** `check_doc_consistency.py` reconciliation check
- **2-7:** `score_change_report.py` (snapshot/compare before/after rebuild)
- **2-8:** GREATEST NULL regression test + anger/stability NULL tests
- **2-9:** `coverage_qa.py` monthly factor coverage QA
- **2-10:** Research quality dual-gate (>=7.0 enhances, 5.0-6.9 notes, <5.0 reject)

### Next Up
- Phase 4 (Matching Quality) DONE. MV rebuilt with score_eligible filters.
- Remaining roadmap items (~52 tasks)

---

## 13. Doc Maintenance Protocol

### Update Triggers
| After this event... | Update these files |
|---------------------|-------------------|
| New tests added | CLAUDE.md Sec 6+12 (test counts), `Start each AI/CLAUDE.md` |
| MV rebuilt | CLAUDE.md Sec 7 (row counts), agents if schema changed |
| New API endpoint | `specs/api-endpoints.md`, `agents/api.md` if router added |
| New DB table/column | `specs/database-schema.md`, relevant agent spec |
| New scoring factor | `agents/scoring.md`, `specs/scoring-system.md`, CLAUDE Sec 8 |
| New data source loaded | `agents/etl.md`, `specs/database-schema.md` |
| New script/file added | `PROJECT_CATALOG.md` |
| Root .md file added/moved | `DOCUMENT_INDEX.md` |
| MEMORY.md approaching 150 lines | Extract detail blocks to topic files, replace with pointers |
| New failure mode | Section 9 (cross-cutting) or agent spec (domain-specific) |
| Same gotcha in 2 sessions | Promote from napkin to canonical location (G4 rule) |
| Monthly | Run `generate_project_metrics.py` + `check_doc_consistency.py` |
| Quarterly | Review agent specs for stale content, archive superseded material |

### MEMORY.md Budget
Stay under 150 lines. Move detail blocks >10 lines to topic files in `memory/`.

### Document Hierarchy
```
Tier 1 (auto-loaded every session):
  CLAUDE.md (this file)     <- constitution, ~434 lines
  MEMORY.md (auto-memory)   <- slim index, ~72 lines

Tier 2 (domain agents, loaded on file-pattern match):
  .claude/agents/*.md       <- 9 specialists, ~1,740 lines total

Tier 3 (on-demand specs, loaded by agents or explicit request):
  .claude/specs/*.md        <- 12 references, ~2,120 lines total

Shared (multi-AI context for Codex/Gemini/other tools):
  Start each AI/            <- common denominator for all AI tools
```

### Canonical Locations
- Matching domain knowledge -> `agents/matching.md`
- Scoring formulas and weights -> `agents/scoring.md`
- Database schema tables -> `specs/database-schema.md`
- API endpoint inventory -> `specs/api-endpoints.md`
- Audit findings and predictive power -> `specs/audit-findings.md`
- Technical gotchas -> Section 9 of this file (cross-cutting) or relevant agent spec (domain-specific)
- Session-specific corrections -> `.claude/napkin.md` (rotate to canonical location once confirmed)

### Multi-AI Coexistence
- `Start each AI/` is the shared context layer for Codex, Gemini, and other tools
- `.claude/` (agents, specs, skills) is Claude Code-specific
- When updating domain knowledge, update the agent spec (canonical). Periodically sync critical changes back to `Start each AI/` for other tools.
