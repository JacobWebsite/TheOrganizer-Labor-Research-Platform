# Labor Relations Research Platform - Shared AI Context

> **For:** Claude Code, Codex, Gemini, and other AI tools. Technical reference with schema essentials, key gotchas, and dev workflow.
> **For project status:** See `PROJECT_STATE.md`.
> **For roadmap:** See `COMPLETE_PROJECT_ROADMAP_2026_03.md` (supersedes Feb 26 roadmap).
> **For redesign spec:** See `UNIFIED_PLATFORM_REDESIGN_SPEC.md`.

**Last Updated:** 2026-03-03

---

## Database Connection

```python
from db_config import get_connection
conn = get_connection()  # Returns plain psycopg2 connection
```
Credentials in `.env` at project root. `db_config.py` (project root, 500+ imports) is the shared connection module.

---

## Core Tables (Quick Reference)

| Table | Records | PK | Key Gotchas |
|-------|---------|-----|-------------|
| `f7_employers_deduped` | 146,863 | `employer_id` (TEXT) | Name: `employer_name_aggressive`. NO EIN column. `cbsa_code` is 100% NULL. |
| `unions_master` | 26,665 | `f_num` (VARCHAR) | `local_number` field exists. |
| `master_employers` | ~4.4M | `master_id` (NOT `id`) | Name: `display_name` (NOT `name`). CHECK constraints on source_system/source_origin. |
| `master_employer_source_ids` | ~4.5M | (master_id, source_system, source_id) | CHECK constraint: `chk_master_source_system` has hardcoded values. |
| `nlrb_elections` | 33,096 | case_number | **NO `state` column** -- state is in `nlrb_participants`. |
| `nlrb_participants` | 1,906,542 | — | State IS here. |
| `unions_master` | 26,693 | f_num (VARCHAR) | `is_likely_inactive` BOOLEAN, `parent_fnum` VARCHAR, `desig_name` codes classify level. |
| `osha_establishments` | 1,007,217 | establishment_id | **NO violation columns** -- use `v_osha_organizing_targets` view. |
| `whd_cases` | 363,365 | case_id | Key cols: trade_name, total_violations, backwages_amount. |
| `sam_entities` | 826,042 | uei | **NO EIN**. NAICS 6-digit. |
| `sec_companies` | 517,403 | cik | Has EIN (62.6%), LEI (0.1%). |
| `mergent_employers` | 56,426 | duns | Column: `company_name` (NOT `employer_name`), `duns` (NOT `duns_number`). EIN ~55%. |
| `national_990_filers` | 586,767 | — | Deduped by EIN. |
| `corporate_identifier_crosswalk` | 17,111 | id | Links SEC/GLEIF/Mergent/CorpWatch/F7. USASpending tier needs re-run. |
| `employer_canonical_groups` | 16,647 groups | — | 40,304 employers in groups. |

### Match Tables

| Table | Records | Join Path |
|-------|---------|-----------|
| `osha_f7_matches` | 145,134 | establishment_id -> f7_employer_id |
| `whd_f7_matches` | 26,312 | (f7_employer_id, case_id) |
| `national_990_f7_matches` | 20,005 | (f7_employer_id, ein). **ein NOT NULL**. |
| `sam_f7_matches` | 15,010 | (f7_employer_id, uei) |
| `unified_match_log` | ~2.2M | Central audit trail. Cols: `match_method` (NOT `method`), `confidence_score` (NOT `score`). |

### Materialized Views

| MV | Rows | Script |
|----|------|--------|
| `mv_unified_scorecard` | 146,863 | `build_unified_scorecard.py` |
| `mv_target_scorecard` | 4,386,205 | `build_target_scorecard.py` |
| `mv_employer_data_sources` | 146,863 | `build_employer_data_sources.py` |
| `mv_target_data_sources` | 4,386,205 | `build_target_data_sources.py` |
| `mv_employer_search` | 107,321 | `rebuild_search_mv.py` |
| `mv_organizing_scorecard` | 212,441 | `create_scorecard_mv.py` |

All support `--refresh` for CONCURRENT refresh. Without `--refresh`: DROP CASCADE + CREATE. **`information_schema.columns` does NOT include MVs** -- use `pg_attribute`.

---

## Key Technical Gotchas

### Database
- **`f7_employer_id` is TEXT everywhere.** All match tables must use TEXT.
- **`master_employers.master_id`** is the PK, NOT `id`. Name column is `display_name`, NOT `name`.
- **`union_file_number` is INTEGER** in `f7_union_employer_relations` but `f_num` is VARCHAR in `unions_master` -- CAST when joining.
- **Never use `TRUNCATE ... CASCADE`** on parent FK tables -- cascades to child tables.
- **CHECK constraints on master tables** -- hardcoded value lists. New source requires `ALTER TABLE DROP CONSTRAINT` + recreate.
- **psycopg2 `%%` for pg_trgm `%` operator** -- only when params tuple is passed.
- **psycopg2 returns Decimal** for DECIMAL columns -- wrap in `float()`.
- **psycopg2 auto-deserializes JSONB** -- `json.loads()` fails because it's already a dict.
- **`SELECT EXISTS(...)` with RealDictCursor** -- MUST alias: `AS e`.
- **`bls_industry_occupation_matrix` columns** -- `employment_2024` (NOT `emp_2024`).
- **OSHA `union_status` codes** -- filter on `!= 'Y'`, NOT `= 'N'` (codes changed over time).
- **DDL before DML** -- CHECK constraint updates need `conn.autocommit=True`. Switch back for INSERTs.

### Matching
- **RapidFuzz replaced Splink** -- Splink geography overweighting unfixable. `token_sort_ratio >= 0.80`. match_method still = `'FUZZY_SPLINK_ADAPTIVE'` for backward compat.
- **Fuzzy FP rates** -- 0.80-0.85=40-50% (deactivated), 0.85-0.90=50-70%.
- **F7 has no EIN** -- match by name+state or through crosswalk.
- **SAM has no EIN** -- match by name+state only.
- **CorpWatch** -- exact-only matching (SEC-style names don't fuzzy-match F7).

### Environment
- **Windows with Git Bash.** Python 3.14 (`py` command).
- **cp1252 encoding** -- Unicode arrows crash stdout. Use ASCII.
- **Do NOT pipe Python through grep** -- no SIGPIPE, Python hangs.
- **`py -c` with `!` in passwords** -- write to .py file instead.
- **Stale processes** -- check for zombie uvicorn/vite. Use `powershell -Command "Stop-Process -Id PID -Force"`.

---

## Scoring System (Summary)

### Unified Scorecard (F7 employers, 146K)
- 10 factors (0-10 each): OSHA(1x), NLRB(3x), WHD(1x), Contracts(2x), Union Proximity(3x), Financial(2x), Industry Growth(2x), Size(0x), Similarity(0x)
- Pillar formula: `weighted_score = (anger*3 + stability*0 + leverage*4) / active_weights`
- Tiers: Priority (top 1.5%), Strong (10.5%), Promising (27.9%), Moderate (35%), Low (25%)

### Target Scorecard (non-union, 4.4M)
- 8 signals, no composite score, filter-driven discovery
- Gold standard tiers: stub -> bronze -> silver -> gold -> platinum

---

## API & Frontend

- **API:** `py -m uvicorn api.main:app --reload --port 8001`. Swagger: `http://localhost:8001/docs`.
- **Frontend:** `cd frontend && VITE_DISABLE_AUTH=true npx vite`. React 19, Vite 7, TanStack, Zustand, Tailwind 4.
- **Auth:** JWT-based. `DISABLE_AUTH=true` in `.env` for dev. First user bootstraps as admin.
- **Fixed-path routes MUST register BEFORE parameterized `/{id}` routes.**
- **`_has_col()` pattern** -- check `pg_attribute` at startup for optional MV columns.

---

## Key Commands

```bash
cd "C:\Users\jakew\.local\bin\Labor Data Project_real"
py -m uvicorn api.main:app --reload --port 8001          # API
cd frontend && VITE_DISABLE_AUTH=true npx vite            # Frontend
py -m pytest tests/ -x -q                                  # Backend tests (~1211)
cd frontend && npx vitest run                              # Frontend tests (~264)
py scripts/maintenance/generate_project_metrics.py         # Auto-metrics
```

### MV Rebuild Order
```bash
py scripts/scoring/create_scorecard_mv.py
py scripts/scoring/compute_gower_similarity.py
py scripts/scoring/build_employer_data_sources.py
py scripts/scoring/build_unified_scorecard.py
py scripts/scoring/build_target_data_sources.py
py scripts/scoring/build_target_scorecard.py
py scripts/scoring/rebuild_search_mv.py
```

---

## Directory Structure

```
api/                    # FastAPI backend (20+ routers)
frontend/               # React frontend
scripts/etl/            # Data loaders (43+)
scripts/matching/       # Deterministic matcher (19+13)
scripts/scoring/        # Scorecard builders (10)
scripts/research/       # Gemini research agent
scripts/maintenance/    # MV refresh, dedup, backup
scripts/cba/            # CBA pipeline (8)
scripts/analysis/       # Ad-hoc analysis (54)
tests/                  # Backend tests
db_config.py            # Shared DB connection (never move)
.env                    # Credentials (never commit)
```

---

## Reference Documents

| Document | Purpose |
|----------|---------|
| `PROJECT_STATE.md` | Current status, active decisions, next up |
| `COMPLETE_PROJECT_ROADMAP_2026_03.md` | Authoritative roadmap (Phases 0-5) |
| `UNIFIED_PLATFORM_REDESIGN_SPEC.md` | Scoring, React, UX design decisions |
| `PIPELINE_MANIFEST.md` | Active script inventory with run order |
| `docs/architecture/MATCHING_PIPELINE_ARCHITECTURE.md` | Full matching system reference |
| `docs/architecture/SCORING_SYSTEM_ARCHITECTURE.md` | Full scoring system reference |
