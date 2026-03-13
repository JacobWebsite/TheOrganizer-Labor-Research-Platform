# V7 Demographics Model -- Preparation Document

**Date:** 2026-03-09
**Purpose:** Handoff document capturing V6 results, expanded data discoveries, known bugs, and the intended V7 data split.

---

## 1. V6 Results (Baseline for V7)

V6 passed **7/7 acceptance criteria** on the old 400-company permanent holdout (325 evaluated, 55 skipped due to missing geography). Trained on **2,702 companies** from a single EEO-1 file (objectors only).

| Criterion | V5 Baseline | V6 Result | Target | Status |
|-----------|------------|-----------|--------|--------|
| Race MAE | 4.372 pp | **4.203 pp** | < 4.50 | PASS |
| P>20pp | 15.4% | **13.5%** | < 16% | PASS |
| P>30pp | 4.0% | **4.0%** | < 6% | PASS |
| Abs Bias | 1.309 | **1.000** | < 1.10 | PASS |
| Hispanic MAE | 8.122 pp | **7.752 pp** | < 8.00 | PASS |
| Gender MAE | 16.407 pp | **11.979 pp** | < 12.00 | PASS |
| Red flag rate | 94.7% | **0.87%** | < 15% | PASS |

### V6 Per-category signed bias (pred - actual)
- White: +0.911 (slight overestimate)
- Black: +0.474 (slight overestimate)
- Asian: -2.277 (underestimate -- largest remaining error)
- AIAN: -0.055 (negligible)
- NHOPI: -0.668 (underestimate)
- Two+: +1.614 (overestimate)
- Female: +5.203 (systematic overestimate, partially mitigated by CPS shrinkage)

### Per-Industry Race MAE (top/bottom)
- Best: Finance/Insurance 2.252, Utilities 2.625, Construction 2.873
- Worst: Accommodation/Food 13.943 (N=5), Food/Bev Mfg 5.979, Transport/Warehousing 5.479

---

## 2. EEO-1 Data Discovery: 5x More Companies Available

V6 was trained on **1 of 5 EEO-1 CSV files** (objectors only, ~4,769 unique companies). The full dataset:

| File | Rows | Description |
|------|------|-------------|
| `nonobjectors_with_corrected_demographics-Updated.csv` | 56,380 | Largest file -- companies that did NOT object to disclosure |
| `objectors_with_corrected_demographics_2026_02_25.csv` | 16,798 | Companies that objected (used in V5/V6) |
| `affirmativelydidnotobject_with_corrected_demographics.csv` | 41 | Small supplement |
| `agreeingtodisclosure_with_corrected_demographics.csv` | 72 | Small supplement |
| `Bellwether-EEO1-Data.csv` | 19 | Bellwether companies (all dupes of above) |

**Total unique company-year rows across all files: 73,282**

### Year Coverage
- 2016-2018: NO usable NAICS or ZIP codes (0% coverage)
- **2019-2020: 100% NAICS + ZIP coverage** -- the only usable years
- 2019-2020 rows: **26,986**
- Unique company codes in 2019-2020: **14,692**
- After parse (non-zero total): **14,691**
- After filters (NAICS >= 4 digits, total >= 50): **14,535**

All 5 CSVs share the same column structure: `YEAR, COMPANY, UNIT, CONAME, NAME, STREET, STREET2, CITY, STATE, ZIPCODE, NAICS, DUNS, CNTYNAME, QUES3, STATUS, AIANF1, AIANF2, ...` with race/gender breakdowns across 11 job categories (F1-F10 female, M1-M10 male, TOTAL10).

### Key Column Details (from eeo1_parser.py)
- `TOTAL10` = total headcount (job category 10 = all categories combined)
- Race columns: `WHF10+WHM10` (White), `BLKF10+BLKM10` (Black), `ASIANF10+ASIANM10` (Asian), `AIANF10+AIANM10` (AIAN), `NHOPIF10+NHOPIM10` (NHOPI), `TOMRF10+TOMRM10` (Two+)
- Hispanic: `HISPF10+HISPM10`
- Gender: `FT10` (Female total), `MT10` (Male total)
- Race categories are mutually exclusive of Hispanic in EEO-1
- Deduplication key: `(COMPANY, YEAR)` -- first occurrence kept
- Encoding: cp1252 (Windows)

### Workplace Size Distribution (from training set build)
| Size Bucket | Count | % |
|-------------|-------|---|
| 1-99 | 1,742 | 14.4% |
| 100-999 | 7,527 | 62.3% |
| 1,000-9,999 | 2,352 | 19.5% |
| 10,000+ | 449 | 3.7% |

Size classification function:
```python
def classify_size_bucket(total):
    if total < 100: return '1-99'
    elif total < 1000: return '100-999'
    elif total < 10000: return '1000-9999'
    else: return '10000+'
```

---

## 3. Known Bug: ZIP Code Zero-Padding

**Problem:** EEO-1 CSVs store ZIP codes as numbers, stripping leading zeros from northeastern states (e.g., `08512` stored as `8512`, `07065` as `7065`). The `zip_to_county()` function in `data_loaders.py` does NOT zero-pad before DB lookup.

**Impact:** ~1,365 companies fail geography resolution and are dropped. This disproportionately affects the Northeast region (~50% loss in Northeast representation).

**Fix needed in `data_loaders.py`:**
```python
def zip_to_county(cur, zipcode):
    """Resolve a ZIP code to county_fips via zip_county_crosswalk."""
    if not zipcode:
        return None
    zipcode = str(zipcode).strip().zfill(5)  # <-- ADD THIS LINE
    cur.execute(
        "SELECT county_fips FROM zip_county_crosswalk WHERE zip_code = %s LIMIT 1",
        [zipcode])
    row = cur.fetchone()
    return row['county_fips'] if row else None
```

**Expected recovery:** ~1,355 additional companies, bringing the usable pool from ~13,170 to ~14,500+. Northeast representation nearly doubles.

**Note:** This fix was implemented during V6 work but was reverted by a linter/file watcher. Must be re-applied and verified.

---

## 4. Intended V7 Data Split

| Set | Size | Purpose | Stratification | Status |
|-----|------|---------|---------------|--------|
| **Permanent Holdout** | **1,000** | Frozen forever, cross-version comparison | naics_group x region (76 cells) | **NEEDS CREATION** |
| **Test Holdout** | **1,000** | Evaluation only, never trains | naics_group x region (76 cells) | Exists but needs rebuild after new permanent holdout |
| **Training** | **~12,000+** | Gate training + calibration | Everything else | Needs rebuild after holdouts |

### Current State (INCOMPLETE -- needs rebuilding)
- `selected_permanent_holdout_100.json`: 100 companies (WRONG SIZE, need 1,000)
- `selected_test_holdout_1000.json`: 1,000 companies (drawn from pool that only excluded 100 permanent holdout -- need to reselect after creating 1,000 permanent holdout)
- `expanded_training_v6.json`: 12,164 companies (based on 100 permanent + 1,000 test exclusion -- wrong)

### Build Order (must be sequential)
1. **Fix ZIP zero-padding** in `data_loaders.py` (recovers ~1,355 companies)
2. **Create 1,000 permanent holdout** (`select_permanent_holdout_100.py` with TARGET=1000)
   - Uses SEED=99 for reproducibility
   - Proportional allocation across 76 strata (naics_group x region)
   - Output: `selected_permanent_holdout_1000.json`
3. **Build full pool** (run `build_expanded_training_v6.py` -- excludes only permanent holdout since test holdout doesn't exist yet)
4. **Select 1,000 test holdout** (run `select_test_holdout_1000.py` from the full pool)
   - Uses SEED=42 for reproducibility
   - Verifies zero overlap with permanent holdout
5. **Rebuild training set** (run `build_expanded_training_v6.py` again -- now excludes both holdouts)
6. **Retrain Gate V2** (run `train_gate_v2.py` on final training set)
7. **Validate** on both holdouts

### File References to Update
Scripts that reference the permanent holdout filename:
- `build_expanded_training_v6.py` line 45: `selected_permanent_holdout_100.json` -> `_1000.json`
- `validate_v6_final.py` line 249: `selected_permanent_holdout_1000.json` (already updated, but pointing to nonexistent file)
- `select_test_holdout_1000.py` line 37: needs to match new permanent holdout filename
- `run_ablation_v6.py` line 64: `selected_permanent_holdout_100.json` -> `_1000.json`

---

## 5. V6 Architecture Summary (for V7 to build on)

### Estimation Pipeline
```
Company Input
    |
    v
Expert Routing (by NAICS group)
    |
    +-- Finance/Utilities (NAICS 52, 22) --> Expert E: Smoothed IPF with industry LODES
    |
    +-- All other industries --> V6-Full:
            Race:     M9b QCEW-Adaptive dampened IPF
            Hispanic: Expert-B tract-heavy blend (35% ACS + 25% LODES + 40% tract)
            Gender:   G1 occupation-weighted (50% BLS industry-occupation + 50% smoothed IPF)
    |
    v
Post-processing:
    1. Training-derived calibration (15% dampening)
    2. CPS benchmark shrinkage for gender (industry-adaptive: 31%/24%/14%)
    3. Gender bounds enforcement (soft/hard by NAICS 2-digit)
    4. Confidence tier assignment (RED/YELLOW/GREEN)
```

### Key Methods
| Method | What It Does | Used For |
|--------|-------------|----------|
| M9b (QCEW-Adaptive) | ACS x LODES IPF with alpha adjusted by QCEW location quotient | Race (V6-Full) |
| Expert-B | 35% ACS + 25% LODES + 40% tract blend | Hispanic (V6-Full) |
| G1 | 50% BLS occupation matrix + 50% smoothed IPF | Gender (V6-Full) |
| Expert E | Smoothed IPF with industry-specific LODES | Finance/Utilities only |
| Expert F | Occupation-weighted IPF | **DISABLED** (hurts race accuracy) |
| Variable dampened IPF | Per-industry-group alpha from OPTIMAL_DAMPENING_BY_GROUP | Core IPF method |

### What DIDN'T Work (avoid in V7)
1. **Industry-LODES (CNS columns):** Too coarse (20 supersectors), hurts race accuracy
2. **Expert F occupation-weighted race:** smoothed_ipf without variable dampening is worse than baseline
3. **H1 geographic Hispanic:** Overfits training set, does not generalize to holdout
4. **OES metro occupation mix:** All-industry (not industry-specific), produces ~50% female for everything
5. **QWI data:** Not available in project

### Gate V2
- **Model:** sklearn GradientBoostingClassifier (100 trees, max_depth=4)
- **Features:** naics_group, region, size_bucket, lodes_minority_share, naics_2digit, QCEW_LQ, ACS-LODES divergence, tract_entropy, has_pums, has_tract, has_occupation
- **Training:** 5-fold GroupKFold CV (grouping by NAICS 2-digit)
- **Experts evaluated:** A, B, D, E, F, V6-Full (6 experts)
- **Outputs:** `gate_v2.pkl`, `calibration_v2.json` (per-expert per-dimension bias corrections)
- **Calibration dampening:** 15% (corrections = -bias * 0.15 then re-normalize to 100%)

### Config Constants (config.py)
```python
# Expert E hard routes
EXPERT_E_INDUSTRIES = {'Finance/Insurance (52)', 'Utilities (22)'}

# Expert F (disabled but defined)
EXPERT_F_INDUSTRIES = {
    'Chemical/Material Mfg (325-327)', 'Computer/Electrical Mfg (334-335)',
    'Food/Bev Manufacturing (311,312)', 'Metal/Machinery Mfg (331-333)',
    'Other Manufacturing', 'Transport Equip Mfg (336)',
    'Transportation/Warehousing (48-49)', 'Admin/Staffing (56)',
}

# CPS benchmark % female by NAICS 2-digit
NAICS_GENDER_BENCHMARKS = {
    '11': 27.0, '21': 15.0, '22': 24.0, '23': 11.0,
    '31': 29.0, '32': 29.0, '33': 29.0,
    '42': 30.0, '44': 50.0, '45': 50.0,
    '48': 25.0, '49': 25.0, '51': 40.0,
    '52': 53.0, '54': 44.0, '56': 40.0,
    '62': 77.0, '71': 48.0, '72': 54.0, '81': 45.0,
}

# Gender bounds by NAICS 2-digit (soft_min/max, hard_min/max for % Female)
GENDER_BOUNDS = {
    '23': {'soft_min': 3, 'soft_max': 25, 'hard_min': 1, 'hard_max': 35},  # Construction
    '62': {'soft_min': 50, 'soft_max': 95, 'hard_min': 40, 'hard_max': 98}, # Healthcare
    # ... (18 industry entries total)
}
```

---

## 6. Data Sources Available

### Census/Labor Data (in PostgreSQL)
| Table | Description | Used By |
|-------|-------------|---------|
| `cur_acs_workforce_demographics` | ACS state x industry demographics + metro_cbsa column | ACS race/hispanic |
| `cur_lodes_geo_metrics` | LODES county-level demographics | LODES race/hispanic |
| `lodes_county_industry_demographics` | LODES by CNS industry code (57,970 rows, 3,029 counties) | Industry-specific LODES |
| `lodes_tract_demographics` | LODES tract-level demographics | Tract race/hispanic |
| `zip_county_crosswalk` | ZIP -> county_fips resolution | Geography lookup |
| `zip_tract_crosswalk` | ZIP -> tract FIPS | Multi-tract ensemble |
| `qcew_annual` | QCEW annual data (LQ, industry share, avg pay) | QCEW concentration |
| `cur_pums_demographics` | PUMS metro-level demographics | Metro fallback |
| `cps_occ_gender_2025` | CPS Table 11 occupations (575 rows) | Gender estimation |
| `bls_industry_occupation_matrix` | BLS industry-occupation employment | Gender estimation |
| `oes_occupation_wages` | OES metro occupation data | Not useful (all-industry) |
| `cbsa_county_crosswalk` | County -> CBSA lookup | Metro identification |

### Industry Classification (classifiers.py)
19 NAICS groups used for stratification:
```
Professional/Technical (54), Finance/Insurance (52), Healthcare/Social (62),
Construction (23), Wholesale Trade (42), Admin/Staffing (56),
Metal/Machinery Mfg (331-333), Other Manufacturing, Chemical/Material Mfg (325-327),
Information (51), Computer/Electrical Mfg (334-335), Transportation/Warehousing (48-49),
Retail Trade (44-45), Utilities (22), Food/Bev Manufacturing (311,312),
Transport Equip Mfg (336), Agriculture/Mining (11,21), Accommodation/Food Svc (72),
Other
```

### Region Classification (classifiers.py)
4 Census regions: Northeast, Midwest, South, West

---

## 7. File Inventory

### Core Pipeline Files
| File | Description |
|------|-------------|
| `config.py` | Configuration: EEO-1 paths, industry weights, bounds, benchmarks |
| `eeo1_parser.py` | CSV parser: `parse_eeo1_row()`, `load_all_eeo1_data()`, `load_eeo1_data()` |
| `data_loaders.py` | DB queries: `zip_to_county()`, ACS/LODES/PUMS/QCEW/tract/occupation loaders |
| `classifiers.py` | `classify_naics_group()`, `classify_region()` |
| `metrics.py` | `composite_score()`, `mae()` |
| `methodologies_v3.py` | Variable dampened IPF, `OPTIMAL_DAMPENING_BY_GROUP` |
| `methodologies_v5.py` | Smoothed IPF, `RACE_CATS` constant |
| `methodologies_v6.py` | V6 methods: Expert E/F, M9a/b/c, G1, H1, `apply_gender_bounds()` |
| `cached_loaders.py` through `cached_loaders_v6.py` | Cached wrappers (v1-v6) with DB caching |
| `validate_v6_final.py` | Full V6 validation pipeline with expert routing + post-processing |
| `train_gate_v2.py` | Gate V2 training (GradientBoosting, 6 experts, 11 features) |

### Data Split Files
| File | Description |
|------|-------------|
| `select_permanent_holdout_100.py` | Script to generate permanent holdout (TARGET variable controls count) |
| `select_test_holdout_1000.py` | Script to generate test holdout from training pool |
| `build_expanded_training_v6.py` | Training set builder (loads all EEO-1, filters, excludes holdouts) |
| `selected_permanent_holdout_100.json` | Current 100-company permanent holdout (NEEDS TO BE 1,000) |
| `selected_test_holdout_1000.json` | Current 1,000-company test holdout (needs rebuild after new permanent) |
| `expanded_training_v6.json` | Current training set (needs rebuild) |
| `gate_v2.pkl` | Trained gate model (needs retrain) |
| `calibration_v2.json` | Per-expert bias corrections (needs retrain) |

### Earlier Version Files (for reference)
| File | Description |
|------|-------------|
| `all_companies_v4.json` | Original 997-company training set (V5) |
| `selected_permanent_holdout_400.json` | Old 400-company permanent holdout (V6, retired) |
| `methodologies_v4.py` | V4 methods |
| `train_gate_v1.py` | Gate V1 (logistic regression) |
| `validate_v5_final.py` | V5 validation pipeline |

---

## 8. V7 Checklist

### Must Do Before Training
- [ ] Fix ZIP zero-padding in `data_loaders.py` (Section 3)
- [ ] Update `select_permanent_holdout_100.py`: set TARGET=1000, output filename to `_1000.json`
- [ ] Run permanent holdout selection (1,000 companies)
- [ ] Update file references in: `build_expanded_training_v6.py`, `select_test_holdout_1000.py`, `validate_v6_final.py`, `run_ablation_v6.py`
- [ ] Build full pool (pass 1, excluding only permanent holdout)
- [ ] Select 1,000 test holdout from pool
- [ ] Rebuild training set (pass 2, excluding both holdouts)
- [ ] Verify zero overlap across all three sets

### Training
- [ ] Retrain Gate V2 on ~12,000+ training companies
- [ ] Generate new `calibration_v2.json`
- [ ] Validate on test holdout (1,000 companies)
- [ ] Validate on permanent holdout (1,000 companies)
- [ ] Compare V6 baseline vs V7 on permanent holdout

### Known Opportunities for V7
1. **4x more training data** (2,702 -> ~12,000+) should improve calibration quality
2. **ZIP fix recovers ~1,355 companies**, especially Northeast (currently underrepresented)
3. **Asian underestimate** (-2.277 signed bias) is the largest remaining race error
4. **Gender overestimate** (+5.203 female) despite CPS shrinkage -- may need stronger regularization
5. **Accommodation/Food Svc** (Race MAE 13.9) is a huge outlier -- needs special handling
6. **Admin/Staffing** (Race MAE 5.3) and **Transport/Warehousing** (5.5) have room for improvement
7. **Expert F** was disabled because it used basic smoothed_ipf -- could work if rebuilt with variable dampening
8. **Gate V2** currently uses hard routing for Expert E -- could benefit from soft routing (probability-weighted blend)

### Estimated Runtime
- Training set build: ~3 minutes
- Gate V2 training: ~3-4 hours (1.15s/company x 12,000 companies x 6 experts)
- Validation: ~1-2 minutes per holdout set
