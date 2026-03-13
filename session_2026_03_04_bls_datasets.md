# Session 2026-03-04: Load 5 New Datasets (OES, SOII, JOLTS, NCS, ACS Insurance)

## What Was Done
Implemented and loaded 4 new BLS datasets + modified ACS pipeline for health insurance columns.

## Files Created (5)
| File | Purpose |
|------|---------|
| `scripts/etl/bls_tsv_helpers.py` | Shared BLS helper: `parse_bls_lookup`, `load_lookup_table`, `stream_bls_data`, `load_data_file` |
| `scripts/etl/load_oes_wages.py` | OES wage data (xlsx from zip) |
| `scripts/etl/load_bls_soii.py` | SOII injury/illness rates |
| `scripts/etl/load_bls_jolts.py` | JOLTS turnover/quits |
| `scripts/etl/load_bls_ncs.py` | NCS employee benefits |

## Files Modified (2)
| File | Changes |
|------|---------|
| `scripts/etl/newsrc_build_acs_profiles.py` | Added 6 insurance vars (HCOVANY, HCOVPRIV, HINSCAID, HINSCARE, HCOVPUB2, HCOVSUB2); agg changed to 7-element list; 6 new CSV/DB columns; idempotent ALTER TABLE |
| `scripts/etl/newsrc_curate_all.py` | Added 6 insurance rate columns to `cur_acs_workforce_demographics` (pct_any_insurance, pct_private_insurance, pct_medicaid, pct_medicare, pct_public_insurance, pct_subsidized) |

## Tables Loaded
| Dataset | Table | Rows | Notes |
|---------|-------|------|-------|
| OES | `oes_occupation_wages` | 414,437 | 2024 data, from xlsx in zip |
| OES MV | `mv_oes_area_wages` | 224,039 | cross-industry, detailed SOC only |
| SOII lookups | 5 tables | ~1,611 total | industry, area, case_type, data_type, supersector |
| SOII | `bls_soii_series` | 891,324 | loaded via COPY for speed |
| SOII | `bls_soii_data` | 5,691,796 | 0 orphan rows |
| SOII MV | `mv_soii_industry_rates` | 45,592 | annual rates, national, private sector |
| JOLTS lookups | 5 tables | ~101 total | industry, dataelement, sizeclass, state, ratelevel |
| JOLTS | `bls_jolts_series` | 1,984 | |
| JOLTS | `bls_jolts_data` | 369,636 | from jt.data.1.AllItems |
| JOLTS MV | `mv_jolts_industry_rates` | 63,012 | national rates, all sizes |
| NCS lookups | 6 tables | ~1,367 total | industry, estimate, datatype, subcell, ownership, provision |
| NCS | `bls_ncs_series` | 100,124 | |
| NCS | `bls_ncs_data` | 768,207 | |
| NCS MV | `mv_ncs_benefits_access` | 592,896 | annual, all occupations |

## Data Source Files (in Data_3_04/)
- OES: `oesm24all.zip` -> `oesm24all/all_data_M_2024.xlsx`
- SOII: `is.*` files (is.data.1.AllData = 231 MB, is.series = 120 MB)
- JOLTS: `jt.*` files (jt.data.1.AllItems.txt primary)
- NCS: `nb.*` files (nb.data.1.AllData)

## Bugs Fixed During Load
- OES `i_group` VARCHAR(20) too short for "cross-industry, ownership" (26 chars) -> widened to VARCHAR(40)
- OES openpyxl holds xlsx file open -> Windows PermissionError on temp cleanup (resolved by DROP+CREATE on retry)
- SOII verify query used `d.value` but MV column is `rate`
- OSHA join: `osha_violation_summary` joins on `establishment_id` not `activity_nr`

## Spot Check Results
- Software Devs (15-1252) national: mean=$144,570, median=$133,080 (correct)
- Nursing Care (623100) injury+illness rate 2024: 6.3/100 FTE (correct; 2022 COVID spike: 13.1)
- Total nonfarm quit rate 2024 annual avg: 2.1% (correct)
- Healthcare medical+retirement access 2025: 64% (correct)
- SOII orphan data rows: 0

## ACS Insurance Status
- Code modified but ACS pipeline NOT re-run (requires usa_00001.dat IPUMS file in original source dir)
- Insurance columns will populate on next `newsrc_build_acs_profiles.py` run
- HCOVPUB2 and HCOVSUB2 are optional (graceful default if not in layout)

## Tests
- 1135 passed, 3 skipped, 0 failures (after dropping empty MV from dry-run)
