# New Data Sources Pipeline (2026-02-28)

Full pipeline integration of 8 new datasets: ABS, CBP, Form 5500, LODES, PPP, USAspending, ACS.

## Raw Tables (newsrc loaders)
| Table | Rows | Loader Script |
|-------|------|---------------|
| `newsrc_abs_raw` | 112K | `newsrc_load_abs.py` |
| `newsrc_cbp2023_raw` | 13.3M | `newsrc_load_cbp.py` |
| `newsrc_cbp2023_naics_raw` | 13.3M | `newsrc_load_cbp.py` (second table) |
| `newsrc_form5500_all` | 2,358,809 | `newsrc_load_form5500.py` (140-col superset, main F_5500 filings only) |
| `newsrc_lodes_wac_2022` | ~4.4M total | `newsrc_load_lodes.py` (4 tables: wac/rac/od/xwalk) |
| `newsrc_ppp_public_raw` | 11.5M | `newsrc_load_ppp.py` |
| `newsrc_usaspending_contracts_raw` | 4M+ | `newsrc_load_usaspending.py` |
| `newsrc_acs_occ_demo_profiles` | 34.1M | `newsrc_build_acs_profiles.py` (29 GB IPUMS fixed-width) |

All raw tables use TEXT columns + `_source_file` and `_loaded_at` metadata columns.

**NOTE: All raw `newsrc_*` tables DROPPED (2026-02-28)** to reclaim 167 GB. Source files remain on disk in `New Data sources 2_27/` for reloads. Drop script: `scripts/etl/newsrc_drop_raw_tables.py`.

## Curated Tables
| Table | Rows | Description |
|-------|------|-------------|
| `cur_form5500_sponsor_rollup` | 259K | One row per EIN, aggregated plan count/assets/participants |
| `cur_ppp_employer_rollup` | 9.5M | One row per borrower, aggregated loan amounts |
| `cur_usaspending_recipient_rollup` | 94K | One row per recipient UEI, aggregated contracts |
| `cur_cbp_geo_naics` | 1,488,919 | National/state/county x NAICS establishment+employment |
| `cur_lodes_geo_metrics` | 3K | County-level workforce metrics from WAC/RAC/OD |
| `cur_abs_geo_naics` | 112K | Firm demographics by NAICS/geography |
| `cur_acs_workforce_demographics` | 11.5M | Geo x industry x occupation x demographic workforce profile |

Build all: `py scripts/etl/newsrc_curate_all.py` (or `--only acs` for just ACS)

## Master Employer Seeding
| Seed Script | Links Created | Method |
|-------------|--------------|--------|
| `seed_master_form5500.py` | 53,023 | 37,254 EIN exact + 15,769 name+state |
| `seed_master_ppp.py` | 149,788 | Name+state matching |

Both added to `master_employer_source_ids` with `source_system='form5500'`/`'ppp'`.

## MV Updates
- **`mv_employer_data_sources`** — 146,863 rows. Added `has_form5500`, `has_ppp` flags. Source count now 0-11 (was 0-9).
- **`mv_target_data_sources`** — 4,386,205 rows (was 4,377,118). form5500=48,663, ppp=141,415.
- **`mv_target_scorecard`** — 4,386,205 rows. 882 bronze tier (was 330).

## Research Tools Added (5 new + 1 modified)
In `scripts/research/tools.py`:
- `search_form5500()` — Query Form 5500 data via EIN bridge
- `search_ppp_loans()` — Query PPP loan data by name+state
- `search_cbp_context()` — County/state CBP establishment+employment data
- `search_lodes_workforce()` — LODES commute/workforce metrics by county
- `search_abs_demographics()` — ABS firm demographics by NAICS+state
- `search_acs_workforce()` — ACS workforce demographics by state+NAICS/SOC/metro (gender, race, age, education, worker class)
- `get_industry_profile()` — Extended with CBP local context

## BLS Datasets (loaded 2026-03-04)
| Table | Rows | Loader Script | Source |
|-------|------|---------------|--------|
| `oes_occupation_wages` | 414K | `load_oes_wages.py` | `Data_3_04/oesm24all.zip` |
| `mv_oes_area_wages` | 224K | (MV) | cross-industry, detailed SOC |
| `bls_soii_series` | 891K | `load_bls_soii.py` | `Data_3_04/is.*` |
| `bls_soii_data` | 5.7M | `load_bls_soii.py` | `is.data.1.AllData` |
| `mv_soii_industry_rates` | 46K | (MV) | national, private, annual rates |
| `bls_jolts_series` | 2K | `load_bls_jolts.py` | `Data_3_04/jt.*` |
| `bls_jolts_data` | 370K | `load_bls_jolts.py` | `jt.data.1.AllItems.txt` |
| `mv_jolts_industry_rates` | 63K | (MV) | national rates, all sizes |
| `bls_ncs_series` | 100K | `load_bls_ncs.py` | `Data_3_04/nb.*` |
| `bls_ncs_data` | 768K | `load_bls_ncs.py` | `nb.data.1.AllData` |
| `mv_ncs_benefits_access` | 593K | (MV) | annual, all occupations |

Plus 22 lookup tables (5 SOII + 5 JOLTS + 6 NCS + 6 unused/reserved).

Shared helper: `scripts/etl/bls_tsv_helpers.py` (parse_bls_lookup, load_lookup_table, stream_bls_data, load_data_file).

### ACS Insurance Columns (code ready, pipeline not re-run)
- `newsrc_build_acs_profiles.py`: 6 new weighted columns (hcovany, hcovpriv, hinscaid, hinscare, hcovpub2, hcovsub2)
- `newsrc_curate_all.py`: 6 new rate columns on `cur_acs_workforce_demographics` (pct_any_insurance, etc.)
- Requires re-running ACS pipeline against IPUMS data file to populate

## Key Technical Lessons
- **CBP geotype codes**: '01'=National, '02'=State, '03'=County (NOT Census FIPS codes '04'/'05')
- **CBP state-level records**: `county_fips='000'` (not NULL or empty string)
- **State FIPS lookup table**: `state_fips_map` with columns `state_abbr`, `state_fips`, `state_name` (NOT `state_fips_lookup` with `abbreviation`/`fips`)
- **`osha_violation_summary` columns**: `violation_count` (NOT `total_violations`), `total_penalties`
- **DDL + DML transaction ordering**: CHECK constraint updates (DDL) need `conn.autocommit=True`. Switch to `autocommit=False` for seed INSERT transaction. Mixing causes issues.
- **Multi-schema CSVs (Form 5500, ABS)**: Scan ALL files first for superset header, DROP+CREATE table with full column set, then COPY each file using only its columns
- **Form 5500 form types**: F_5500 (main), F_5500_SF (short form), F_SCH_C/H/I/R (schedules). Only load main F_5500 filings unless schedule data needed.
- **ABS loader --truncate**: Must DROP table (not just TRUNCATE) since schema changes between files require table recreation
- **IPUMS ACS `usa_00001.dat` is a directory** containing `usa_00001.dat` file (nested). Script auto-detects: `if data_path.is_dir() and (data_path / data_path.name).is_file()`.
- **IPUMS extract has no EMPSTAT variable** — uses LABFORCE instead (filtering on `LABFORCE in {'1','2'}`). Removed EMPSTAT from NEEDED_VARS.
- **ACS NAICS codes are IPUMS-style** (e.g. `3113`, `113M`, `22S`) — NOT standard Census NAICS codes. `naics4 = SUBSTR(indnaics, 1, 4)` in curated table.
- **VACUUM FULL on 24 GB takes 45+ min** — locks all tables exclusively. Can be cancelled safely; disk space stays allocated but reusable. Run overnight if needed.
