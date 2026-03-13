# Technical Lessons (moved from MEMORY.md)

Most of these are now also in CLAUDE.md sections 3, 4, 9. This file is the full archive.

## Database & psycopg2
- **Check constraints on master tables** — hardcoded allowed value lists. `seed_master()` checks/updates at runtime.
- **unified_match_log columns** — `match_method` (NOT `method`), `confidence_score` (NOT `score`). `run_id` NOT NULL. Unique on `(run_id, source_system, source_id, target_id)`.
- **`get_connection()` returns plain psycopg2** — default cursor uses tuples. Pass `cursor_factory=RealDictCursor` for dict access.
- **`SELECT EXISTS(...)` with RealDictCursor** — MUST alias: `SELECT EXISTS(...) AS e`.
- **`SELECT COUNT(*)` with RealDictCursor** — alias as `AS cnt`.
- **f7_employer_id is TEXT** — all match tables must use TEXT.
- **NEVER use `TRUNCATE ... CASCADE` on parent FK tables**.
- **psycopg2 `%%` for pg_trgm `%` operator** — only when params tuple is passed.
- **psycopg2 auto-deserializes JSONB** — check `isinstance(val, dict)` first.
- **psycopg2 returns Decimal for DECIMAL columns** — wrap in `float()`.
- **`REFRESH MATERIALIZED VIEW CONCURRENTLY` does NOT update SQL definition** — must DROP + CREATE.
- **`pg_type_typname_nsp_index` duplicate key on CREATE MV** — use `autocommit=True` for DROP, verify, CREATE in new connection.
- **`information_schema.columns` does NOT include MVs** — use `pg_attribute`.
- **Missing DB views** — catch `psycopg2.errors.UndefinedTable`, return 404.

## SQL Patterns
- **OSHA `union_status` codes** — N/Y used 2012-2016, A/B used 2015+. Filter on `!= 'Y'`, NOT `= 'N'`.
- **SQL LIKE space variants** — `LIKE '%FED EX%'` doesn't match `FEDEX`. Generate both patterns.
- **Large UPDATE on big tables (1.9M+ rows)** — split into separate transactions, consider batched approach.
- **Large INSERT with CTE+DISTINCT ON+NOT EXISTS hangs** — staged approach: TEMP TABLE, INDEX, DELETE existing, INSERT.
- **Seed scripts are idempotent** — `ON CONFLICT DO NOTHING`. Re-running returns all zeros.

## Windows / Environment
- **Python 3.14** — `\s` escape warnings. passlib incompatible with bcrypt 5.x.
- **Windows cp1252 encoding** — Unicode arrows crash. Use ASCII or `PYTHONIOENCODING=utf-8`.
- **`py -c` with `!` in passwords** — write to .py file instead of inline.
- **Windows process killing** — use `powershell -Command "Stop-Process -Id PID -Force"`.
- **Do NOT pipe Python output through grep on Windows** — no SIGPIPE, Python hangs as zombie.
- **Crawl4AI on Windows** — redirect sys.stdout/stderr to UTF-8 during `asyncio.run()`.

## External APIs
- **Gemini API cannot mix tool types** — `function_declarations` and `google_search` in same request = 400. Separate calls.
- **Gemini can't reliably reproduce large JSON** — 40K+ char rewrites fail. Use patch-based approach.
- **Census Bureau batch geocoder** — only returns matched records. Free, max 10K/batch, ~2 min/batch.

## Matching
- **Splink REPLACED by RapidFuzz** — token_sort_ratio >= 0.80, 3 blocking indexes.
- **CorpWatch fuzzy matching not useful** — exact-only is the right strategy.
- **OSHA batch contention** — 3+ concurrent pg_trgm queries slow dramatically. Max 2 parallel.
- **`--rematch-all` vs `--unmatched-only`** — `--rematch-all` supersedes old matches, processes ALL records.
- **Match rate tests are F7-only** — rates ~8.3%/~4.7%. Don't set high thresholds.
- **Dedup stats (2026-02-27):** Phase 1 EIN=9K, Phase 2 name+state=233K, Phase 3 fuzzy=69K.

## Scoring
- **weighted_score formula is pillar-based** — `(anger*3 + stability*3 + leverage*4) / 10`. Legacy is `legacy_weighted_score`.
- **`_resolve_employer_url` Tier 4 Google Search** — set `RESEARCH_SCRAPER_GOOGLE_FALLBACK=false` in tests.
- **Labor orgs ARE valid employers** — `is_labor_org=TRUE` is metadata only.

## Column Name Gotchas
- **`bls_industry_occupation_matrix`** — `employment_2024`, NOT `emp_2024`. NO `display_level`.
- **`f7_employers_deduped.cbsa_code`** — 100% NULL. Use `cbsa_definitions` + `msa_union_stats`.
- **`mergent_employers`** — `company_name` and `duns`, NOT `employer_name`/`duns_number`.
- **CorpWatch CSVs** — tab-delimited, NULL as literal `"NULL"`, EIN as `irs_number`, `cw_id` is PK.
