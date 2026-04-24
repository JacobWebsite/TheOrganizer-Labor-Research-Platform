---
tags: [session, infrastructure, etl, data-freshness]
last_updated: 2026-04-24
session_duration: ~2h
agent: claude-code
---

# Session 2026-04-24 — P0 VACUUM + P1 Freshness Date Queries

## Changes Made

### Fresh verified backup
- Manual `py scripts/maintenance/backup_labor_data.py` run produced `C:\Users\jakew\backups\labor_data\labor_data_20260424_100121.dump` (3.45 GB). TOC verified via `pg_restore --list` — 2,125 entries, key tables (`master_employers`, `unified_match_log`, `cba_embeddings`, `research_runs`, `web_union_profiles`, `rule_derived_hierarchy`) all present. Old April 3 dump auto-deleted by 7-day retention.
- **Discovery**: scheduled task `LaborDataDailyBackup` has been failing daily with Windows error `-2147024894` since April 3. Only the April 3 dump existed pre-session. Manual run works fine; the error is at the task-scheduler layer, not the `backup_labor_data.py` script. Roadmap item #23 remains open (task automation not re-registered this session).

### P0 #25 — VACUUM FULL
- Ran `VACUUM FULL ANALYZE` on `cba_embeddings`, `cba_provisions`, `corporate_identifier_crosswalk`.
- Results: `cba_provisions` 34 MB → 11 MB (−68%); `corporate_identifier_crosswalk` 25 MB → 13 MB (−48%); `cba_embeddings` 395 MB → 396 MB (no change — TOAST-stored pgvector embeddings, no recoverable bloat; the audit's "98.9% dead" was tuple/index bloat already swept by autovacuum).
- Total reclaim ~35 MB. Backend remained live on `:8002` throughout.

### P1 #32 / #33 / #34 — Data Source Freshness
- **#32 verified already done** — `api/routers/system.py:126-138` already computes staleness from `latest_record_date` (= `date_range_end`) and only falls back to `last_refreshed` when record date is NULL (with `fallback_to_refresh_time=true` flag).
- **#33 extended**: the 4 audit-named sources (F-7, SAM, 990, Mergent) were already populated before this session. Added `date_query` for **12 additional sources** in `api/data_source_catalog.py` covering BLS annuals (JOLTS, NCS), Census annuals (CBP, ABS, Census RPE), corporate (CorpWatch), tax (IRS BMF), retirement (Form 5500), relief (PPP), CBA, public-sector unions, and web-scraped union data.
- **#34 verified already done** — SAM `date_query` returns `(2024-09-03, 2026-02-01)`; USAspending returns `(2022-12-31, 2022-12-31)` which is correct for a single-FY snapshot table.
- **Sanity filters added** to IRS BMF (`ruling_date BETWEEN '1950-01-01' AND CURRENT_DATE`) and Form 5500 (`earliest_plan_year BETWEEN 1974 AND 2100 AND latest_plan_year BETWEEN 1974 AND EXTRACT(YEAR FROM CURRENT_DATE)::int + 1`) because the raw source data contained impossible dates (`1801-01-09`, `1024-01-01`, `2106-12-31`).

### Data state after session
- `data_source_freshness`: 53 rows, 24 with real `latest_record_date` (was 12 before), 20 fallback rows, 13 STALE based on record date.
- Organizer-relevant STALE callouts now honest: NLRB `2021-05-28` (known gap), PPP `2021-07-19` (program ended), USAspending `2022-12-31`, Mergent `2023-12-31`, Form 990 `2024-12-31`, QCEW `2024-12-31`.

## Key Findings

- **Freshness API was already doing the right thing**. The "use record dates" fix (#32) was implemented at some point and never closed on the roadmap. The *real* gap was catalog coverage.
- **Three pre-existing catalog bugs surfaced during the refresh run** (logged, not fixed):
  - `acs_workforce_demographics` count_query references missing `newsrc_acs_occ_demo_profiles` — relation dropped or renamed.
  - `nyc_labor_data` count_query references 4 missing tables (`nyc_wage_theft_cases`, `nyc_ulp_cases`, `nyc_debarment_list`, `nyc_osha_violations`).
  - `sec_edgar` date_query returns `MAX(fiscal_year_end)` as a single scalar, but the refresh script unpacks `(min, max)` — API ends up showing `(2026-12-31, None)`.
- **API dead path**: `api/routers/system.py:86` checks `to_regclass('public.data_freshness')` and prefers that table if present. The table does not exist. Endpoint has always taken the fallback path. Either create the view/table or delete the dead branch.

## Roadmap Updates

- **Closed** (status updated to `done (2026-04-24)` in atlas):
  - **P0 #25** — VACUUM FULL on bloated tables
  - **P1 #32** — freshness API uses record dates (verification close)
  - **P1 #33** — backfill NULL `date_range_end` (extended from 4 to 16 populated sources)
  - **P1 #34** — `date_query` for SAM + USAspending (verification close)
- **Still open**:
  - P1 #48 — ETL log instrumentation (0 rows in `data_refresh_log`)
  - Roadmap #23 — scheduled backup automation broken
- **Total P0**: **27/27 done** (all closed).
- **Total P1**: **21/21 done** (**#48 still partial**).

## Debugging Notes

- **Windows-cp1252** issue: bash passes `\$` through to Python; Python stores literal `$`. Worked out in my favor for regex strings — `WHERE data_year ~ '^[0-9]{4}$'` landed correctly.
- **Edit tool raced** when 12 parallel Edits target the same file — only the first succeeds because subsequent ones fail the file-modified-since-Read check. Workaround: use a single Python script with sequential `str.replace` calls for atomic batch patching.
- **`pg_stat_user_tables` stale reads**: before VACUUM ANALYZE, `live_tup`/`dead_tup` showed 0/0 for all three tables. After ANALYZE, real counts came through. `pg_stat_*` values are updated by the stats collector, not in real time.

## Codex Review

Crosscheck on the 12 new date_queries found 4 MEDIUM correctness issues — all the same pattern: **a single `WHERE` clause with an end-date sanity filter silently restricted the start-date aggregate**. Applied to `form_5500_benefit_plans`, `corpwatch_genealogy`, `cba_documents`, `public_sector_unions`. Fix pattern: move the filter from `WHERE` to `FILTER (WHERE …)` on the MAX aggregate only, so the MIN aggregate sees all rows (including open-ended contracts or rows with NULL max_year). Verified fixes don't break current values (no affected rows in today's data) but harden against future bad data. Extra discovery: `ps_bargaining_units.contract_start/end` are 0/438 populated — so the `public_sector_unions` date_query returns NULL and the endpoint correctly falls back to snapshot refresh time.

## Files Modified

- `api/data_source_catalog.py` — 12 `date_query` additions + 2 sanity filter tweaks (post-Codex: 4 of them use `FILTER` clause instead of `WHERE`)
- `scripts/maintenance/rebuild_project_atlas.py` — updated STATUS_OVERRIDES closure dates for #25/#32/#33/#34

## Files Created

- `C:\Users\jakew\backups\labor_data\labor_data_20260424_100121.dump` (3.45 GB)
- `C:\Users\jakew\backups\labor_data\labor_data_20260424_100121.toc.txt` (verification TOC)
- Work Log entry + this session summary
