# V6 Run 1 Checkpoint Report

**Date:** 2026-03-09
**Steps Completed:** 0 (Holdout), 1 (BDS Nudge), 2 (Leak Fix), 3 (Soft Routing), 4 (CNS LODES), 5 (QCEW), 6 (Metro ACS), 7 (Multi-Tract + OES), 13 (CPS Table 11)

---

## 1. Permanent Holdout (Step 0)

- **400 companies selected**, stratified across 18 industry groups x 4 regions
- All 18 industry groups represented (6-32 companies per group)
- Pool: 3,421 unique EEO-1 companies, after excluding 997 V5 training companies
- **Zero overlap with V5 training set** - contamination check PASS
- Seed: 42, reproducible
- File: `selected_permanent_holdout_400.json`

## 2. BDS Nudge Removed (Step 1)

- `apply_bds_nudge()` disconnected from `predict_gate_v1()` pipeline
- `benchmarks` parameter removed from function signature
- `load_bds_benchmarks()` no longer called in `main()`
- `HARD_SEGMENTS` review flag removed
- All functions/definitions preserved (just disconnected) - VERIFIED

## 3. Ground Truth Leak Fixed (Step 2)

- `minority_share` (from EEO-1 ground truth) replaced with `lodes_minority_share` (from LODES county data) in:
  - `build_gate_training_data.py` - new `lodes_minority_share` feature added
  - `train_gate_v1.py` - reads from `gate_training_data.csv` instead of `cls.get('minority_share')`
  - `validate_v5_final.py` - computes inline from `cl.get_lodes_pct_minority()`
- Feature name updated from `'minority_share'` to `'lodes_minority_share'` in all feature lists - VERIFIED

## 4. Soft Routing (Step 3)

- `predict_gate_v1()` now runs ALL three experts (A, B, D) and blends via gate probabilities
- Old: argmax expert selection
- New: `result = sum(prob_i * expert_i_output)` for each race/hispanic/gender category
- Calibration still applied using argmax expert's biases
- `_data_source` = `'soft_blend'`

## 5. Data Loader Status

| Loader | Status | Test Result |
|--------|--------|-------------|
| `get_lodes_minority_share()` | WORKING | 5/5 non-null returns |
| `get_lodes_industry_race()` | PENDING ETL | Returns None (table not yet created) |
| `get_qcew_concentration()` | WORKING | 5/5 non-null, LQ values 0.27-1.84 |
| `get_acs_race_metro()` | WORKING | 4/5 non-null (Hawaii has no metro ACS) |
| `get_multi_tract_demographics()` | WORKING | 5/5 non-null, 54-326 tracts per ZIP |
| `get_occupation_mix_local()` | WORKING | 5/5 non-null, 409-619 occupations per metro |
| `get_pct_female_by_occupation()` | WORKING | Returns valid percentages |

## 6. CNS LODES Industry Columns (Step 4)

- **CNS columns NOT in `cur_lodes_geo_metrics`** (confirmed via schema check)
- **WAC files contain CNS01-CNS20** (confirmed in `New Data sources 2_27/LODES_bulk_2022/`)
- `NAICS_TO_CNS` mapping added to `config.py` (24 entries)
- ETL script created: `scripts/etl/lodes_curate_industry_demographics.py`
- **ETL NOT YET RUN** - creates `lodes_county_industry_demographics` table
- Loader function `get_lodes_industry_race()` handles missing table gracefully

## 7. CPS Table 11 (Step 13)

- ETL script: `scripts/etl/load_cps_table11.py` - COMPLETED
- **575 rows loaded** into `cps_occ_gender_2025`
- SOC mapping: 509 mapped (88.5%), 66 with fallback keys
- Data verified: pct_women ranges from 0.0% (cement masons) to 100.0% (skincare specialists)

## 8. Baseline Metrics (V5 + Fixes on Permanent Holdout)

| Metric | V5 Fresh Holdout | V5+Fixes Perm Holdout | V6 Target |
|--------|-----------------|----------------------|-----------|
| Race MAE | 5.182 pp | **4.536 pp** | < 4.50 pp |
| P>20pp | 20.67% | **16.52%** | < 16% |
| P>30pp | 8.17% | **5.80%** | < 6% |
| Abs Bias | 1.345 | 1.942 | < 1.10 |
| Hispanic MAE | 9.252 pp | 9.819 pp | < 8.00 pp |
| Gender MAE | 18.098 pp | 17.782 pp | < 12.00 pp |

**Notes:**
- Different holdout sets, so V5 Fresh vs Perm Holdout not directly comparable
- Race MAE already near V6 target after soft routing + leak fix
- Abs Bias increased - likely due to soft routing adding systematic White over-prediction
- Gender and Hispanic still need significant improvement (Run 2 targets)
- 345/400 companies evaluated (55 skipped due to missing county FIPS)

## Files Created/Modified

| File | Action |
|------|--------|
| `select_permanent_holdout.py` | NEW - holdout selection |
| `selected_permanent_holdout_400.json` | NEW - frozen holdout data |
| `config.py` | MODIFIED - added NAICS_TO_CNS mapping |
| `data_loaders.py` | MODIFIED - 7 new loader functions |
| `validate_v5_final.py` | MODIFIED - BDS nudge removed, soft routing, leak fix |
| `build_gate_training_data.py` | MODIFIED - lodes_minority_share feature |
| `train_gate_v1.py` | MODIFIED - lodes_minority_share from CSV lookup |
| `scripts/etl/lodes_curate_industry_demographics.py` | NEW - CNS LODES ETL |
| `scripts/etl/load_cps_table11.py` | NEW - CPS Table 11 ETL |

## Deferred to Run 2

- Run the LODES industry demographics ETL (creates the CNS-weighted table)
- Retrain gate with LODES minority share (requires re-running build_gate_training_data + train_gate_v1)
- Build V6 methodologies (M9a, M9b, M9c)
- Gender occupation-weighted method
- Hispanic geography-heavy method
