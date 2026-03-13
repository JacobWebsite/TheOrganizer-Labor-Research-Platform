# Claude Code Handoff: New Data Integration

Date: 2026-02-28
Project root: `C:\Users\jakew\.local\bin\Labor Data Project_real`

## 1. Objective
Integrate newly downloaded external datasets into the production data system so they can drive employer enrichment and scorecard/research workflows.

Primary datasets now in scope:
- ACS/IPUMS extract (occupation-demographic profiles)
- LODES (LEHD Origin-Destination Employment Statistics)
- Form 5500 bulk filings
- PPP public loans
- Census CBP
- USAspending contracts
- Census ABS latest release (state/local pulls)

## 2. Current Data Status (Confirmed)
Source folder:
- `C:\Users\jakew\.local\bin\Labor Data Project_real\New Data sources 2_27`

Present in folder:
- LODES bulk 2022 (`LODES_bulk_2022`)
- Form 5500 bulk (`Form5500_bulk`) and latest snapshot (`F_5500_2025_Latest`)
- PPP public shards (`public_*.csv`)
- CBP (`CBP2023`, `CB2300CBP`)
- USAspending contracts (`FY2022`, `FY2024`, `FY2025`, `FY2026` zips)
- ACS/IPUMS files (`usa_00001.dat.gz`, `usa_00001.txt`, extracted data)
- ABS latest pull (`ABS_latest_state_local`)

ABS result details:
- Downloaded JSON files: 17
- Converted CSV files: 17
- Location: `New Data sources 2_27\ABS_latest_state_local\csv`
- Log: `New Data sources 2_27\ABS_latest_state_local\ABS_latest_download_log.txt`
- Note: 3 skips are expected due to missing congressional-district variants for some ABS datasets.

## 3. Scripts Already Added

### ETL loaders (Python)
Path: `scripts\etl`
- `newsrc_common.py`
- `newsrc_manifest.py`
- `newsrc_stage_to_raw.py`
- `newsrc_load_cbp.py`
- `newsrc_load_ppp.py`
- `newsrc_load_form5500.py`
- `newsrc_load_lodes.py`
- `newsrc_load_usaspending.py`
- `newsrc_run_all.py`
- `newsrc_build_acs_profiles.py`

### ABS acquisition/conversion (PowerShell)
Path: `scripts`
- `download_abs_latest_state_local.ps1`
- `convert_abs_json_to_csv.ps1`
- (older/general) `download_abs_bulk.ps1`

## 4. Existing New-Source Raw Tables
Created by the current loaders:
- `newsrc_cbp2023_raw`
- `newsrc_cb2300cbp_raw`
- `newsrc_ppp_public_raw`
- `newsrc_form5500_all`
- `newsrc_lodes_wac_2022`
- `newsrc_lodes_rac_2022`
- `newsrc_lodes_od_2022`
- `newsrc_lodes_xwalk_2022`
- `newsrc_usaspending_contracts_raw`
- `newsrc_acs_occ_demo_profiles` (from `newsrc_build_acs_profiles.py`, when DB load enabled)

All raw loaders use text landing columns plus `_source_file` and `_loaded_at`.

## 5. What Is Not Integrated Yet
1. ABS is downloaded and converted, but there is no Python ETL loader yet in `scripts\etl`.
2. `newsrc_run_all.py` does not include ABS or ACS profile build steps.
3. Curated typed tables/views from these raw sources are not yet wired into core system objects (`mv_employer_data_sources`, scorecards, profile enrichments).

## 6. Required Integration Work for Claude Code

### A) Add ABS ingestion into ETL pipeline
1. Create `scripts\etl\newsrc_load_abs.py`.
2. Input folder: `New Data sources 2_27\ABS_latest_state_local\csv`.
3. Load all `ABS_*.csv` files.
4. Recommended destination model:
   - One unified raw table: `newsrc_abs_raw`
   - Include metadata columns parsed from filename:
     - `abs_vintage` (e.g., 2023)
     - `abs_dataset` (`abscs`, `abscb`, `abscbo`, `absmcb`)
     - `abs_geo_level` (`us`, `state`, `county`, `msa_micro`, `congressional_district`)
5. Add `--truncate` support consistent with other loaders.
6. Reuse helper functions from `newsrc_common.py`.

### B) Add ABS to orchestration
1. Update `scripts\etl\newsrc_run_all.py`.
2. Add `newsrc_load_abs.py` step.
3. Add optional switch `--skip-abs`.
4. Consider adding `newsrc_build_acs_profiles.py` to the run sequence behind a switch (`--with-acs-profiles`) to avoid heavy reruns by default.

### C) Curated integration layer (first-pass)
Create SQL or Python transform(s) to produce typed rollups from raw tables:
1. `cur_abs_geo_naics` from `newsrc_abs_raw`
2. `cur_lodes_geo_metrics` from 2022 LODES tables
3. `cur_form5500_sponsor_rollup`
4. `cur_ppp_employer_rollup`
5. `cur_usaspending_recipient_rollup`
6. `cur_cbp_geo_naics`

Use normalized keys where possible:
- geography: state/county FIPS
- industry: NAICS
- employer join keys: EIN, canonicalized name + state fallback

### D) Wire into core serving layer
Target integration points:
- `mv_employer_data_sources` (core cross-source adapter)
- `scripts/scoring/build_unified_scorecard.py` factor inputs
- `api/routers/profile.py` enrichment payload
- optional new diagnostics endpoint under `api/routers` for source coverage

### E) Add validation and tests
1. Add row-count smoke checks for new raw/cur tables.
2. Add schema tests for required columns and non-null metadata.
3. Add at least one API-level integration assertion showing new-source data appears in profile or source summary payload.

## 7. Command Reference

### Run full existing new-source load
```powershell
cd "C:\Users\jakew\.local\bin\Labor Data Project_real"
python scripts/etl/newsrc_run_all.py --truncate
```

### Build ACS occupation-demographic profile output
```powershell
python scripts/etl/newsrc_build_acs_profiles.py
```

### ABS download + conversion (if rerun needed)
Important: PowerShell may block script execution by policy.

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
& "C:\Users\jakew\.local\bin\Labor Data Project_real\scripts\download_abs_latest_state_local.ps1" -ApiKey "<CENSUS_API_KEY>"
& "C:\Users\jakew\.local\bin\Labor Data Project_real\scripts\convert_abs_json_to_csv.ps1"
```

## 8. Acceptance Criteria for This Integration Sprint
1. `newsrc_load_abs.py` exists and loads all ABS CSVs into DB.
2. `newsrc_run_all.py` can run end-to-end (with or without ABS/ACS switches).
3. Curated tables exist for ABS + at least two other new sources.
4. At least one core serving layer object (`mv_employer_data_sources` or profile endpoint enrichment) includes the new curated data.
5. Tests pass and include new-source assertions.
6. `docs/NEW_SOURCES_INGESTION_CONTEXT_2026-02-28.md` is updated to include ABS loader and orchestration changes.

## 9. Suggested Prompt To Give Claude Code
Use this verbatim:

"Continue integration of newly downloaded labor datasets in `C:\\Users\\jakew\\.local\\bin\\Labor Data Project_real`.
Current loaders exist for CBP, PPP, Form5500, LODES, USAspending, and ACS profile builder. ABS latest data is already downloaded and converted to CSV at `New Data sources 2_27\\ABS_latest_state_local\\csv`, but no ETL loader exists yet.

Please do the following end-to-end:
1) Implement `scripts/etl/newsrc_load_abs.py` using the same conventions as other `newsrc_load_*` loaders (including `--truncate`, `_source_file`, `_loaded_at`, and table auto-create from headers).
2) Update `scripts/etl/newsrc_run_all.py` to include ABS loading with `--skip-abs`.
3) Add a first curated transform layer for ABS and at least two of: LODES, PPP, Form5500, CBP, USAspending.
4) Wire one curated output into system-serving objects (`mv_employer_data_sources` or profile enrichment path) with minimal-risk changes.
5) Add/extend tests for loader smoke, schema checks, and one API integration check.
6) Run validation commands and report row counts for new raw and curated tables.
7) Update docs with exact commands and resulting table list.

Do not remove existing behavior. Keep changes incremental and test-backed."

## 10. Notes
- OEWS and BLS projections were intentionally excluded from this ingestion batch because user indicated those are already in DB.
- USAspending FY2023 is intentionally missing from the current folder.
- Keep API keys out of committed docs/config; use env var or runtime argument.
