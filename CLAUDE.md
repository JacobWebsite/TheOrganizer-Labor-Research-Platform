# Labor Relations Research Platform

> For detailed schema, tables, and API endpoints see `Start each AI/CLAUDE.md`.
> For project status see `Start each AI/PROJECT_STATE.md`.
> For the roadmap see `UNIFIED_ROADMAP_FINAL_2026_02_26.md`.

## Domain Context

This is a labor organizing data platform. Key distinction:

- **F7 employers = UNION reference data.** These employers already have union contracts/CBAs. They are NOT scoring targets.
- **The scorecard scores NON-UNION employers** as investigation targets for organizers.
- **We flag for investigation, not predict outcomes.** The score highlights structural signals (violations, NLRB activity, contracts, industry trends) -- it does not predict whether a union drive will succeed.
- Never conflate union reference employers with non-union scoring targets.

## Workflow

- **Start coding promptly.** Do not spend more than 2-3 minutes on exploration/planning before writing code, unless the user explicitly asks for a plan first. If exploration is needed, ask before diving deep.
- **When presenting roadmaps or task lists, be comprehensive.** Include ALL remaining items, not just easy wins. If unsure of scope, ask rather than presenting a trimmed-down version.
- **After implementing changes, run the full test suite** (`py -m pytest tests/ -x -q` for backend, `cd frontend && npx vitest run` for frontend) and report pass counts before committing. Do not commit with failing tests unless explicitly told to.
- **Current test counts:** ~933 backend, ~158 frontend. All should pass.

## Database

- **Always verify column names against the actual database** before writing queries or scripts. Run `\d table_name` or equivalent -- do not rely on assumptions or plan documents.
- **For materialized views, use `pg_attribute`** -- `information_schema.columns` does NOT include MVs.
- **Before schema changes (DROP CASCADE, ALTER, column renames),** check for dependent materialized views, foreign keys, and downstream tables. Rebuild affected MVs immediately after.
- **Never use `TRUNCATE ... CASCADE` on parent FK tables** -- it cascades to child tables.
- **Check constraints on `master_employer_source_ids` and `master_employers`** have hardcoded allowed value lists. Adding a new source requires ALTER + recreate.
- **`f7_employer_id` is TEXT** everywhere. All match tables must use TEXT.
- **`get_connection()` returns plain psycopg2** -- default cursor uses tuples. Pass `cursor_factory=RealDictCursor` for dict access.
- **`SELECT EXISTS(...)` with RealDictCursor** -- MUST alias: `SELECT EXISTS(...) AS e`.

## Environment

- **Windows with Git Bash.** Python 3.14 (`py` command). Node.js for frontend.
- **`.env` file at project root** stores DB creds and JWT secret. The custom loader in `db_config.py` uses `setdefault` -- shell env vars take precedence.
- **`DISABLE_AUTH=true` in `.env`** bypasses backend JWT auth. Frontend uses `VITE_DISABLE_AUTH=true` in `frontend/.env`.
- **Stale processes can hold ports.** Always check for zombie uvicorn/vite/node processes before debugging connection issues. Use `powershell -Command "Get-CimInstance Win32_Process -Filter \"CommandLine like '%uvicorn%'\""` to find them.
- **Windows cp1252 encoding** -- Unicode arrows/symbols crash stdout. Use ASCII or set `PYTHONIOENCODING=utf-8`.
- **Do NOT pipe Python output through grep on Windows** -- no SIGPIPE, Python hangs as zombie.
- **`py -c` with `!` in passwords** -- write to .py file instead of inline.

## Key Commands

```bash
# Backend
cd "C:\Users\jakew\.local\bin\Labor Data Project_real"
py -m uvicorn api.main:app --reload --port 8001

# Frontend
cd frontend && npx vite
# (frontend/.env has VITE_DISABLE_AUTH=true)

# Tests
py -m pytest tests/ -x -q          # backend
cd frontend && npx vitest run       # frontend

# MV rebuild (in dependency order)
py scripts/scoring/create_scorecard_mv.py
py scripts/scoring/compute_gower_similarity.py
py scripts/scoring/build_employer_data_sources.py
py scripts/scoring/build_unified_scorecard.py
py scripts/scoring/build_target_data_sources.py
py scripts/scoring/build_target_scorecard.py
py scripts/scoring/rebuild_search_mv.py

# Auto-metrics
py scripts/maintenance/generate_project_metrics.py
```

## Files That Matter

- `db_config.py` -- shared DB connection (500+ imports, never move)
- `api/main.py` -- FastAPI app, port 8001
- `frontend/` -- React 19, Vite 7, TanStack, Zustand, Tailwind 4
- `scripts/scoring/` -- all scorecard/MV build scripts
- `scripts/matching/` -- deterministic matcher, adapters
- `scripts/research/` -- research agent (14 tools, Gemini)
- `tests/` -- backend tests
- `frontend/src/**/*.test.jsx` -- frontend tests
