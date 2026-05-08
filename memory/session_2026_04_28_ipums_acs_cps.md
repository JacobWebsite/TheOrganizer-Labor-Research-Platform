# 2026-04-28 — IPUMS double-track session (ACS insurance + CPS ORG)

Two of four queued IPUMS use cases closed in one session. Triggered by the user noting they'd just gotten an IPUMS API key.

## Track 1 — ACS insurance columns backfilled

**Problem closed**: deferred-pipeline item "ACS Insurance Columns (code ready, pipeline not re-run)" — flagged in `new_data_sources.md` and project memory months ago. Docs claimed re-extract was required; it wasn't (the existing `usa_00001.dat` layout already had all 6 insurance variables — HCOVANY, HCOVPRIV, HINSCAID, HINSCARE, HCOVPUB2, HCOVSUB2).

**Pipeline run**:
- `scripts/etl/newsrc_build_acs_profiles.py` — 65.3M kept person-records → 34,144,767 cells. ~16 min wall clock.
- `scripts/etl/newsrc_curate_all.py --only acs` — `cur_acs_workforce_demographics` 11,478,933 rows now with 6 new `pct_*_insurance` columns. ~4.6 min.

**Verified output (national workforce-weighted)**:
- pct_any_insurance: 90.35%
- pct_private_insurance: 68.62%
- pct_medicaid: 16.32%
- pct_medicare: 22.71%
- pct_public_insurance: 15.39%
- pct_subsidized: 7.10%

State spot checks: TX 80.2% (non-expansion, lowest), NY 94.2% (Medicaid expansion + Essential Plan), CA 92.1%. Healthcare workers (NAICS 6211) 89-97% across top-5 states.

**Side fix to script**: added `--spill-keys` mode (default 8M groups) that flushes in-memory aggregator to numbered chunk CSVs and merge-aggregates in Postgres. The successful run completed in-memory without it — an earlier MemoryError on the same file was an isolated failure during a contended Python session, not deterministic. The spill path is now the safety net for future re-runs (e.g. when pulling a fresh extract via API). One bug surfaced and fixed: `SET maintenance_work_mem='2GB'` exceeds local Postgres cap (2,097,151 kB) — now '1GB'.

## Track 2 — CPS ORG microdata acquired

**Problem closed**: `Data Sources/Not Yet Acquired/CPS Microdata.md` — in the queue since 2026-03-18 vault setup. Now superseded by `Data Sources/BLS Labor Statistics/CPS ORG Microdata.md`.

**Three new ETL scripts**:
- `scripts/etl/cps_pull_org_extract.py` (228 lines) — IPUMS REST API submit/poll/download. Reads `IPUMS API Key` from `.env` (literal name has spaces; can't use shell env loading). Fetches authoritative sample list from `/metadata/cps/samples` endpoint; dedups year-month preferring `_b` over `_s` suffix.
- `scripts/etl/cps_load_org.py` (149 lines) — DDI XML parser (namespaced `ddi:codebook:2_5`) + fixed-width streaming loader. COPYs into `cps_org_raw` (TEXT staging).
- `scripts/etl/cps_curate_density.py` (~270 lines) — 8 GROUPING SETS aggregations into `cur_cps_density_*` tables.

**Pipeline run**:
- Submitted CPS extract #2 (72 monthly samples 2019-2024, 23 requested vars). IPUMS auto-added 9 ID vars → 32 total.
- Server-side processing: ~5 min.
- Downloaded: 178.4 MB `.dat.gz` + 0.2 MB DDI XML.
- Loaded: 7,582,963 person-records (1,562,158 with `EARNWT > 0`, the actual ORG sample).
- Curated 8 tables in 14 seconds.

**Verified output**:

| Table | Rows | Notes |
|-------|------|-------|
| cps_org_raw | 7,582,963 | TEXT staging, 32 cols |
| cur_cps_density_state | 153 | Validation target |
| cur_cps_density_state_year | 918 | Time series |
| cur_cps_density_state_industry | 31,264 | NEW capability |
| cur_cps_density_msa | 780 | 65 identified MSAs |
| cur_cps_density_msa_industry | 93,786 | **Killer feature** |
| cur_cps_density_state_occ | 55,985 | NEW |
| cur_cps_density_county | 840 | 280 of 3,143 counties (Census suppresses small-pop) |
| cur_cps_density_county_industry | 84,693 | County × IND × sector |

**Validation**:
- National 2024 union member rate: CPS = **9.98%** vs BLS published = **9.9%** (exact match).
- 51 states/DC vs `bls_state_density`: mean abs delta **0.90pp**, max 4.15pp (small-state sampling variance: HI n=1773, AK n=1354).
- Sub-state spot checks match real-world unions: NYC hospitals 34% private (1199SEIU), NYC truck transport 47% (Teamsters), Brooklyn hospitals 58%, Brooklyn public sector 50.65%.

**Beta-state county coverage**: NY=14, VA=12, OH=10 reliable counties — all major beta-state metros covered.

## IPUMS API gotchas (caught while building)

1. `INDNAICS` and `OCCSOC` aren't valid CPS variable names — CPS uses Census codes (IND, OCC, IND1990, OCC2010). Crosswalk to NAICS at curate time.
2. Pre-2024 basic-monthly `_b` samples are sparse; `_s` (supplement-attached) versions cover the gaps. Both contain the ORG/union variables. Metadata API at `/metadata/cps/samples?version=2` is authoritative.
3. Auth header is `Authorization: <key>` (no `Bearer` prefix).
4. `.env` key has spaces in var name (`IPUMS API Key`) — must read .env manually.
5. DDI XML namespaced (`ddi:codebook:2_5`); ElementTree needs full namespace URI for `.iter()`.
6. **`union` is a SQL reserved word** — must always quote `"union"` in queries.
7. Implied decimals: WTFINL/EARNWT have 4 (÷10000), EARNWEEK/HOURWAGE have 2 (÷100).
8. 25.6% of CPS ORG records have suppressed METFIPS; 59% have suppressed COUNTY (Census confidentiality for <~100K population).

## DB changes

`data_refresh_log` rows 4-14 inserted (one per touched table):
- ids 4-5: ACS insurance refresh (newsrc + curated)
- ids 6-12: CPS ORG load + 6 curate tables
- ids 13-14: CPS county tables (added after user asked about county-level support)

Total new tables: **8** (`cps_org_raw` + 7 `cur_cps_density_*`).
Total updated tables: **2** (`newsrc_acs_occ_demo_profiles` rebuilt + 6 insurance cols on `cur_acs_workforce_demographics`).

## What's next (queued)

User explicitly said "let's plan to do the tier one stuff another night":

**Tier 1 IPUMS, queued for future session**:
1. **CPS re-extract with `UNIONCOV` + `FAMINC`** — closes the coverage-rate gap from today's pull. Single re-submit, ~10 min.
2. **PUMS 2024 1-year refresh** — closes deferred item from 2026-04-16 ACS refresh. Refreshes `pums_metro_demographics`. ~30 min.
3. **CPS ASEC March supplement** — pulls `_s` files from 2019-2024 March for income/poverty cross-tabs of union households. ~30 min.

**Pre-existing queue (lower priority)**:
- CPS ORG historical (2003, 2013 snapshots) for density-regression paper.

## Out of scope (deliberately)

- Wiring `cur_cps_density_msa_industry` and `cur_cps_density_county_industry` into `score_union_density` on `mv_target_scorecard` — separate downstream task. Currently scoring uses state-level density only.
- CIC → NAICS crosswalk for IND codes — useful but not blocking; queries can use IND directly for now.
- Frontend exposure of insurance columns or sub-state union density — UI work.
- `corporate_family_rollup` / Lowe's etc work — that was earlier in the day, separate session.

## Files modified / added (this session)

**Code** (4 files in `scripts/etl/`):
- M `newsrc_build_acs_profiles.py` — added `--spill-keys` mode + work_mem fix
- A `cps_pull_org_extract.py` — IPUMS API submit/poll/download
- A `cps_load_org.py` — DDI parser + fixed-width loader
- A `cps_curate_density.py` — 8 density rollup tables

**Vault**:
- A `Data Sources/BLS Labor Statistics/CPS ORG Microdata.md` (full data source note)
- M `Data Sources/Census and Demographics/ACS Workforce Demographics.md` (added 6 insurance cols)
- M `Data Sources/Not Yet Acquired/CPS Microdata.md` (converted to redirect stub)
- A `Work Log/2026-04-28 - ACS Insurance Columns Backfilled.md`
- A `Work Log/2026-04-28 - CPS ORG Microdata Acquired.md`

**Memory** (auto-memory at `~/.claude/projects/.../memory/`):
- A `session_2026_04_28_acs_insurance_columns.md`
- A `session_2026_04_28_cps_org_microdata.md`
- M `MEMORY.md` (added two index entries at top)

## No commits yet
This is a wrapup, not a `/ship`. Code and vault changes are uncommitted. Next session can `/ship` to commit the 4 ETL scripts + vault notes.
