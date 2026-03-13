# New Sources Ingestion Context (2026-02-28)

## Why This Exists
You downloaded a large bundle of new data into:

`C:\Users\jakew\.local\bin\Labor Data Project_real\New Data sources 2_27`

This document and the companion scripts turn that bundle into repeatable ETL loads for:

- Form 5500 (2016-2025 bulk)
- LODES (2022 bulk, multi-state)
- CBP (CBP2023 + CB2300CBP)
- PPP public files
- USAspending full contract extracts (FY2022/FY2024/FY2025/FY2026 currently present)

You confirmed OEWS + BLS projections are already in DB, so they are excluded from this loader set.

## Scripts Added
All under [`scripts/etl`](C:\Users\jakew\.local\bin\Labor Data Project_real\scripts\etl):

- [`newsrc_common.py`](C:\Users\jakew\.local\bin\Labor Data Project_real\scripts\etl\newsrc_common.py)
  Shared helper functions for header sanitization, table creation, and COPY loading.
- [`newsrc_manifest.py`](C:\Users\jakew\.local\bin\Labor Data Project_real\scripts\etl\newsrc_manifest.py)
  Builds a JSON inventory/coverage manifest for the new-source folder.
- [`newsrc_stage_to_raw.py`](C:\Users\jakew\.local\bin\Labor Data Project_real\scripts\etl\newsrc_stage_to_raw.py)
  Optional staging script to move/copy files into `data/raw/<source>/`.
- [`newsrc_load_cbp.py`](C:\Users\jakew\.local\bin\Labor Data Project_real\scripts\etl\newsrc_load_cbp.py)
  Loads `CBP2023.dat` + `CB2300CBP.dat` into raw tables.
- [`newsrc_load_ppp.py`](C:\Users\jakew\.local\bin\Labor Data Project_real\scripts\etl\newsrc_load_ppp.py)
  Loads `public_*.csv` PPP shards into a single raw table.
- [`newsrc_load_form5500.py`](C:\Users\jakew\.local\bin\Labor Data Project_real\scripts\etl\newsrc_load_form5500.py)
  Loads Form 5500 bulk zip CSVs.
- [`newsrc_load_lodes.py`](C:\Users\jakew\.local\bin\Labor Data Project_real\scripts\etl\newsrc_load_lodes.py)
  Loads LODES `wac/rac/od/xwalk` gz CSVs into separate raw tables.
- [`newsrc_load_usaspending.py`](C:\Users\jakew\.local\bin\Labor Data Project_real\scripts\etl\newsrc_load_usaspending.py)
  Loads `FY*_All_Contracts_Full_*.zip` CSV shards into a raw table.
- [`newsrc_run_all.py`](C:\Users\jakew\.local\bin\Labor Data Project_real\scripts\etl\newsrc_run_all.py)
  One-command orchestrator for manifest + all loaders.

## Raw Tables Created by These Scripts
- `newsrc_cbp2023_raw`
- `newsrc_cb2300cbp_raw`
- `newsrc_ppp_public_raw`
- `newsrc_form5500_all`
- `newsrc_lodes_wac_2022`
- `newsrc_lodes_rac_2022`
- `newsrc_lodes_od_2022`
- `newsrc_lodes_xwalk_2022`
- `newsrc_usaspending_contracts_raw`

All columns are loaded as `TEXT` plus:
- `_source_file`
- `_loaded_at`

This is intentional as a raw landing zone for rapid ingest and future typed transforms.

## Recommended Run Order
From project root:

```powershell
cd "C:\Users\jakew\.local\bin\Labor Data Project_real"
```

### 1) Manifest only
```powershell
python scripts/etl/newsrc_manifest.py
```

### 2) Full load (append mode)
```powershell
python scripts/etl/newsrc_run_all.py
```

### 3) Full reload (truncate first)
```powershell
python scripts/etl/newsrc_run_all.py --truncate
```

### 4) If needed, skip heavy sources
```powershell
python scripts/etl/newsrc_run_all.py --skip-lodes --skip-usaspending
```

## Optional Canonical Staging
If you want files copied/moved from `New Data sources 2_27` into canonical `data/raw/*`:

```powershell
python scripts/etl/newsrc_stage_to_raw.py --copy
```

Without `--copy`, files are moved.

## Validation Queries
Use these after load:

```sql
SELECT COUNT(*) FROM newsrc_form5500_all;
SELECT COUNT(*) FROM newsrc_lodes_wac_2022;
SELECT COUNT(*) FROM newsrc_lodes_rac_2022;
SELECT COUNT(*) FROM newsrc_lodes_od_2022;
SELECT COUNT(*) FROM newsrc_lodes_xwalk_2022;
SELECT COUNT(*) FROM newsrc_cbp2023_raw;
SELECT COUNT(*) FROM newsrc_cb2300cbp_raw;
SELECT COUNT(*) FROM newsrc_ppp_public_raw;
SELECT COUNT(*) FROM newsrc_usaspending_contracts_raw;
```

## Known Notes
- USAspending FY2023 is not present in the current bundle by design.
- NY LODES was merged into the same folder; loader handles mixed state files.
- These scripts are raw-ingest focused. Typed/factorized downstream tables should be built next.

## Next Engineering Step (after raw loads)
Build typed curated tables + employer linkages:
- `cur_form5500_sponsor_rollup`
- `cur_lodes_state_metrics`
- `cur_cbp_geo_naics`
- `cur_ppp_employer_snapshot`
- `cur_usaspending_recipient_rollup`

Then wire these into `master_employers`, `mv_employer_data_sources`, and scorecard factors.
