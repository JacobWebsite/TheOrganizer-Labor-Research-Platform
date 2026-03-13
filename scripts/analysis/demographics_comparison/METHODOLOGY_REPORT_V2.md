# Demographics Estimation Methodology Report V2

**Date:** 2026-03-08
**Validation set:** 200 EEO-1 companies (stratified across 5 dimensions)
**Methods evaluated:** 11 (5 original + 6 new variants)
**Ground truth:** EEO-1 Type 2 filings (mutually exclusive race/ethnicity categories)

---

## 1. Executive Summary

We evaluated 11 workforce demographics estimation methods against EEO-1 ground truth for 200 companies stratified across industry, size, region, minority share, and urbanicity. The new **M1b (Learned Weights)** method achieves the best overall race MAE of **5.15**, a **10.3% improvement** over the previous champion M1 Baseline (5.74). **M3b (Dampened IPF)** places second at 5.37.

| Rank | Method | Race MAE | Hellinger | Race Wins | Improvement vs M1 |
|------|--------|----------|-----------|-----------|-------------------|
| 1 | **M1b Learned-Wt** | **5.15** | **0.1710** | **77** | **-10.3%** |
| 2 | M7 Hybrid | 5.15 | 0.1710 | 0 | -10.3% |
| 3 | **M3b Damp-IPF** | **5.37** | **0.1860** | **36** | **-6.4%** |
| 4 | M1 Baseline | 5.74 | 0.1919 | 2 | -- |
| 5 | M4 Occ-Weighted | 5.92 | 0.2001 | 6 | +3.1% |
| 6 | M2 Three-Layer | 5.95 | 0.1994 | 6 | +3.7% |
| 7 | M2b Workplace-Tract | 5.95 | 0.1994 | 0 | +3.7% |
| 8 | M5 Variable-Weight | 5.99 | 0.2005 | 5 | +4.4% |
| 9 | M4b State-Occ | 6.00 | 0.2022 | 13 | +4.5% |
| 10 | M5b Min-Adapt | 6.08 | 0.2046 | 1 | +5.9% |
| 11 | M3 IPF | 7.13 | 0.2463 | 54 | +24.2% |

**Key insight:** The learned weights strongly favor LODES (county-level workplace data) over ACS (industry-level survey data) for most industries. The default 60/40 ACS/LODES split underweights the geographic signal.

**Caveat:** These results are on the training set (the same 200 companies used to optimize M1b weights). A holdout set of 198 fresh companies has been selected for honest out-of-sample validation but has not yet been evaluated.

---

## 2. Data Sources

### 2.1 ACS (American Community Survey)
- **Table:** `cur_acs_workforce_demographics`
- **Granularity:** Industry (NAICS 4-digit) x State x Occupation (SOC) x Demographics
- **Demographics:** Race (9 codes), Hispanic origin, Sex
- **Strengths:** Industry-specific, occupation-level detail
- **Weaknesses:** Survey-based (sampling error), no sub-state geography, codes don't separate NHOPI from Asian

### 2.2 LODES (Longitudinal Employer-Household Dynamics)
- **Table:** `cur_lodes_geo_metrics` (county level), `cur_lodes_tract_metrics` (tract level, new)
- **Granularity:** County or Census tract (workplace location)
- **Demographics:** Race (6 categories), Hispanic, Gender
- **Year:** 2022
- **Strengths:** Census-derived, fine geography, workplace-based (not residential)
- **Weaknesses:** Not industry-specific, covers all jobs in a geography

### 2.3 ACS Tract Demographics
- **Table:** `acs_tract_demographics`
- **Granularity:** Census tract (residential population)
- **Demographics:** Race, Hispanic, Gender, Education, Income
- **Coverage:** 85,396 tracts
- **Limitation:** Residential population, not workforce

### 2.4 BLS Industry-Occupation Matrix
- **Table:** `bls_industry_occupation_matrix`
- **Content:** Occupation shares by NAICS industry (national level)
- **Used by:** M4, M4b for occupation-weighted estimates

### 2.5 Ground Truth: EEO-1 Type 2 Filings
- **Source:** EEOC objectors dataset (2018-2020)
- **Categories:** Mutually exclusive non-Hispanic race (White, Black, Asian, AIAN, NHOPI, Two+), Hispanic/Not Hispanic, Male/Female
- **Validation set:** 200 companies, stratified across 18 industry groups, 4 size buckets, 4 regions, 3 minority share levels, 3 urbanicity levels

---

## 3. Method Descriptions

### 3.1 Original Methods (M1-M5)

#### M1: Baseline (60/40 Fixed Blend)
- **Formula:** 60% ACS + 40% LODES for all three dimensions (race, Hispanic, gender)
- **Rationale:** Simple weighted average giving moderate weight to both industry composition and local geography
- **Fallback:** If one source missing, renormalizes to the other

#### M2: Three-Layer (50/30/20)
- **Formula:** 50% ACS + 30% LODES (county) + 20% ACS tract (residential)
- **Rationale:** Adds a third residential demographic layer for finer geographic granularity
- **Fallback:** Missing layers dropped, weights renormalized

#### M3: IPF (Iterative Proportional Fitting)
- **Formula:** For each race category k: raw_k = ACS_k * LODES_k, then normalize to 100
- **Rationale:** Maximum-entropy solution that amplifies where both sources agree
- **Behavior:** Extreme -- categories where both sources are high get squared, small categories get crushed toward zero
- **Known issue:** Systematically overestimates White, underestimates minorities in diverse areas

#### M4: Occupation-Weighted
- **Formula:** 70% occupation-weighted ACS + 30% LODES
- **Process:** Uses BLS occupation matrix to get the occupation mix for the NAICS industry, then queries ACS demographics per SOC code, weighted by employment share
- **Rationale:** Accounts for occupational segregation within industries
- **Fallback:** Falls back to M1-style 70/30 blend if no occupation data available

#### M5: Variable-Weight by Industry
- **Formula:** Same as M1 but with industry-adaptive weights from config
- **Weight groups:** Local labor (40/60 ACS/LODES), Occupation-driven (75/25), Manufacturing (55/45), Default (60/40)
- **Rationale:** Industries where local labor dominates should weight LODES more

#### M6: IPF + Occupation (ELIMINATED)
- Identical to M3 in practice. Excluded from V2 comparison.

### 3.2 New Methods (M1b-M5b, M7)

#### M1b: Learned Weights by Industry Group
- **Formula:** Same blend as M1 but with per-NAICS-group optimized ACS/LODES weights
- **Optimization:** For each of 19 NAICS groups, tested ACS weights from 0.30 to 0.90 (step 0.05) and picked the weight minimizing average race MAE across companies in that group
- **Key finding:** Most groups optimize to 0.30 ACS / 0.70 LODES (heavy LODES preference), except Construction (0.90/0.10), Admin/Staffing (0.90/0.10), and Utilities (0.90/0.10)

**Learned weights:**

| NAICS Group | ACS Weight | LODES Weight |
|-------------|-----------|-------------|
| Accommodation/Food Svc (72) | 0.30 | 0.70 |
| Admin/Staffing (56) | 0.90 | 0.10 |
| Agriculture/Mining (11,21) | 0.65 | 0.35 |
| Chemical/Material Mfg (325-327) | 0.30 | 0.70 |
| Computer/Electrical Mfg (334-335) | 0.30 | 0.70 |
| Construction (23) | 0.90 | 0.10 |
| Finance/Insurance (52) | 0.30 | 0.70 |
| Food/Bev Manufacturing (311,312) | 0.30 | 0.70 |
| Healthcare/Social (62) | 0.35 | 0.65 |
| Information (51) | 0.30 | 0.70 |
| Metal/Machinery Mfg (331-333) | 0.35 | 0.65 |
| Other | 0.30 | 0.70 |
| Other Manufacturing | 0.30 | 0.70 |
| Professional/Technical (54) | 0.30 | 0.70 |
| Retail Trade (44-45) | 0.30 | 0.70 |
| Transport Equip Mfg (336) | 0.30 | 0.70 |
| Transportation/Warehousing (48-49) | 0.30 | 0.70 |
| Utilities (22) | 0.90 | 0.10 |
| Wholesale Trade (42) | 0.30 | 0.70 |

**Interpretation:** County-level LODES workplace data is a stronger signal than industry-level ACS for most sectors. The exceptions -- Construction, Admin/Staffing, Utilities -- are industries where the local workforce composition varies significantly from county-level averages (e.g., construction crews travel to job sites in other counties; staffing agencies deploy workers across geographies).

#### M2b: Workplace Tract LODES
- **Formula:** 50% ACS + 30% LODES (county) + 20% LODES (tract, workplace)
- **Difference from M2:** Third layer uses workplace LODES tract data (from `cur_lodes_tract_metrics`) instead of residential ACS tract data
- **Tract selection:** Picks the highest-employment tract in the company's county
- **Fallback:** Falls back to residential ACS tract data, then to M1 weights
- **Result:** No improvement over M2 (identical scores). The tract selection heuristic (largest tract in county) is too coarse -- it doesn't identify the company's actual workplace tract

#### M3b: Dampened IPF
- **Formula:** For each race category k: raw_k = sqrt(ACS_k) * sqrt(LODES_k), then normalize
- **Difference from M3:** Uses geometric mean (sqrt product) instead of raw product, reducing the multiplicative amplification that causes M3's extreme biases
- **Hispanic and Gender:** Uses standard IPF (same as M3)
- **Result:** Significant improvement over M3 (5.37 vs 7.13), making it the second-best method overall

#### M4b: State-Level Occupation Mix
- **Formula:** Same as M4 but uses state-level ACS occupation proportions instead of national BLS matrix
- **Fallback per SOC:** If a SOC code has <100 state-level workers, falls back to national ACS for that occupation
- **Fallback cascade:** State ACS occ mix -> National BLS occ mix -> 70/30 ACS/LODES blend
- **Result:** Slightly worse than M4 on average (6.00 vs 5.92) but wins in specific subgroups (Admin/Staffing, Chemical Manufacturing)

#### M5b: Minority Share Adaptive
- **Formula:** Same as M5 (variable industry weights) but adjusts based on county minority share
- **Adjustment:** In high-minority counties (>50%), adds 0.20 to ACS weight; in medium-minority (>30%), adds 0.10. Caps ACS at 0.85
- **Rationale:** In high-minority areas, industry-level ACS may be more representative than county LODES (which captures all industries)
- **Result:** Worse than M5 (6.08 vs 5.99). The minority-share adjustment pushes weights in the wrong direction

#### M7: Hybrid (M1b race + M3 gender)
- **Formula:** Takes race and Hispanic estimates from M1b, gender estimate from M3 IPF
- **Rationale:** M1b excels at race, M3 IPF wins gender frequently
- **Result:** Matches M1b exactly on race MAE. The hybrid adds zero value because race MAE is the dominant metric and M3's gender advantage doesn't offset

---

## 4. Results by Dimension

### 4.1 By Industry Group (Race MAE)

| Industry Group | N | Best Method | Best MAE | M1 MAE | Winner |
|---------------|---|-------------|----------|--------|--------|
| Utilities (22) | 5 | M3 IPF | 1.96 | 3.36 | M3 dominates (homogeneous rural counties) |
| Metal/Machinery Mfg | 6 | M3b Damp-IPF | 2.21 | 2.64 | -16% improvement |
| Transport Equip Mfg | 3 | M1b | 2.88 | 3.49 | -17% improvement |
| Utilities | 5 | M3 IPF | 1.96 | 3.36 | IPF wins in homogeneous counties |
| Chemical/Material Mfg | 5 | M4b State-Occ | 3.41 | 3.76 | State occ mix helps here |
| Food/Bev Mfg | 5 | M1b/M3b (tie) | 3.56 | 3.82 | -7% improvement |
| Other Manufacturing | 5 | M3 IPF | 3.08 | 4.49 | IPF wins (mostly homogeneous) |
| Agriculture/Mining | 3 | M1b | 4.22 | 4.29 | Marginal improvement |
| Construction (23) | 11 | M1b | 4.26 | 5.26 | -19% improvement (0.90 ACS weight) |
| Wholesale Trade | 12 | M1b | 4.44 | 4.77 | -7% improvement |
| Prof/Technical (54) | 44 | M3b Damp-IPF | 4.56 | 5.21 | -12% improvement |
| Other | 23 | M3b Damp-IPF | 4.61 | 5.00 | -8% improvement |
| Information (51) | 5 | M1b | 5.17 | 5.82 | -11% improvement |
| Healthcare/Social (62) | 10 | M1b | 5.76 | 5.90 | -2% (marginal) |
| Computer/Elec Mfg | 3 | M1b | 6.05 | 7.26 | -17% improvement |
| Finance/Insurance (52) | 48 | M1b | 6.65 | 7.62 | -13% improvement |
| Retail Trade | 3 | M3b Damp-IPF | 6.67 | 7.90 | -16% improvement |
| Admin/Staffing (56) | 6 | M4b State-Occ | 7.03 | 7.43 | -5% improvement |
| Accommodation/Food | 3 | M1b | 7.46 | 9.51 | -22% improvement |

**Key patterns:**
- M1b wins in 10 of 18 groups outright
- M3b wins in 5 groups (especially well-mixed areas: Professional/Technical, Other, Metal/Machinery)
- M3 (standard IPF) only wins in homogeneous groups (Utilities, Other Manufacturing) where the product amplification works in its favor
- Finance/Insurance (largest group, N=48) sees a major 13% improvement with M1b

### 4.2 By Workforce Size (Race MAE)

| Size Bucket | N | M1 | M1b | M3b | Best |
|-------------|---|-----|-----|-----|------|
| 1-99 | 25 | 6.27 | 5.47 | 5.49 | M3 IPF (4.71) |
| 100-999 | 101 | 5.72 | **5.27** | 5.35 | M1b |
| 1k-9999 | 50 | 5.82 | **5.12** | 5.62 | M1b |
| 10000+ | 24 | 5.10 | **4.43** | 4.83 | M1b |

- M1b is the clear winner for companies with 100+ employees
- For small companies (1-99), M3 IPF wins -- these tend to be in rural/homogeneous counties where IPF's product amplification helps
- M1b's advantage grows with company size: -8% for 100-999, -12% for 1k-9999, -13% for 10000+

### 4.3 By Region (Race MAE)

| Region | N | M1 | M1b | M3b | Best |
|--------|---|-----|-----|-----|------|
| Midwest | 59 | 3.41 | 3.20 | **3.04** | M3b |
| Northeast | 25 | 4.79 | **4.28** | 4.62 | M1b |
| South | 77 | 6.52 | **5.90** | 6.14 | M1b |
| West | 39 | 8.34 | **7.20** | 7.85 | M1b |

- M3b wins in the Midwest (less diverse, IPF dampening works well)
- M1b wins in all other regions
- The West remains the hardest region (MAE ~7.2 even at best), likely due to greater workforce diversity and commuting patterns
- All methods show a clear gradient: Midwest < Northeast < South < West

### 4.4 By Minority Share (Race MAE)

| Minority Level | N | M1 | M1b | M3b | M3 | Best |
|---------------|---|-----|-----|-----|----|------|
| Low (<25%) | 111 | 3.99 | 3.67 | 3.35 | **3.14** | M3 IPF |
| Medium (25-50%) | 60 | 5.35 | **4.73** | 5.26 | 9.29 | M1b |
| High (>50%) | 29 | 13.26 | **11.70** | 13.34 | 17.91 | M1b |

- This is the most impactful dimension. High-minority companies have 3x the error of low-minority ones
- M3 IPF dominates at low minority share (its product amplification helps in white-majority settings) but catastrophically fails at high minority share (17.91 MAE, overestimates White by 47.7pp)
- M1b reduces high-minority error from 13.26 to 11.70 (-12%), but 11.70 is still very high
- All methods systematically overestimate White share in high-minority companies -- a fundamental data gap issue

### 4.5 By Urbanicity (Race MAE)

| Setting | N | M1 | M1b | M3b | M3 | Best |
|---------|---|-----|-----|-----|----|------|
| Rural | 26 | 4.09 | 3.22 | 3.27 | **1.60** | M3 IPF |
| Suburban | 17 | 4.46 | **3.91** | 4.31 | 5.56 | M1b |
| Urban | 157 | 6.15 | **5.61** | 5.83 | 8.21 | M1b |

- M3 IPF dominates rural areas (MAE 1.60 vs M1b's 3.22) because rural counties are demographically homogeneous
- M1b wins decisively in urban areas (where 78% of companies are located)
- The urban challenge is the main bottleneck for overall accuracy

---

## 5. Gender and Hispanic Results

### 5.1 Gender MAE

| Method | Avg Gender MAE | Gender Wins |
|--------|---------------|-------------|
| M3 IPF | 10.93 | 101 |
| M3b Damp-IPF | 10.93 | 0 |
| M4b State-Occ | 12.47 | 23 |
| M4 Occ-Weighted | 11.71 | 15 |
| M1b Learned-Wt | 14.82 | 32 |
| M1 Baseline | 12.55 | 3 |
| M2/M2b | 13.52 | 10 |

- M3 IPF is the clear gender winner (wins 101 of 200 companies)
- Gender MAE is much higher than race MAE across all methods (10-15pp vs 5-7pp)
- The IPF product amplification works better for binary gender estimation
- M1b trades gender accuracy for race accuracy (14.82 gender vs 12.55 for M1) -- this is the cost of heavy LODES weighting, since LODES gender data is coarser

### 5.2 Hispanic MAE

| Method | Avg Hispanic MAE |
|--------|-----------------|
| M5 Variable-Weight | 7.41 |
| M1 Baseline | 7.50 |
| M4 Occ-Weighted | 7.51 |
| M5b Min-Adapt | 7.45 |
| M1b Learned-Wt | 7.60 |
| M3 IPF | 8.85 |
| M3b Damp-IPF | 8.85 |

- Hispanic estimation is relatively consistent across methods (7.4-8.9 MAE)
- The blend methods slightly outperform IPF variants for Hispanic
- Hispanic MAE is higher than race MAE but lower than gender MAE

---

## 6. Bias Analysis

### 6.1 Systematic White Overestimation

All methods overestimate White share in high-minority companies:

| Method | Avg White Overestimate (High Minority) |
|--------|---------------------------------------|
| M3 IPF | +47.7pp |
| M3b Damp-IPF | +29.9pp |
| M1 Baseline | +26.1pp |
| M5b Min-Adapt | +26.1pp |
| M5 Variable-Weight | +26.0pp |
| M1b Learned-Wt | +25.8pp |
| M4 Occ-Weighted | +25.8pp |
| M4b State-Occ | +25.6pp |
| M2/M2b | +23.0pp |

**Root cause:** Both ACS and LODES reflect the broader workforce, not individual employers. A company in a majority-minority county that hires disproportionately from minority communities will look more diverse than the county average. Neither data source captures employer-specific hiring patterns.

### 6.2 Black Underestimation

Conversely, all methods underestimate Black share in high-minority companies (12-22pp). This is the mirror of the White overestimate.

### 6.3 Geographic Bias

- **West:** All methods overestimate White (2-10pp depending on method) due to California's diverse workforce being underrepresented in county averages
- **Rural:** Most methods underestimate White (8-12pp) because ACS industry data reflects national composition, not the local (whiter) workforce. Exception: M3 IPF, which overcorrects
- **Midwest:** Slight underestimate of White for blend methods, slight overestimate for IPF methods

### 6.4 Industry-Specific Biases

Persistent across methods (>5pp bias in any method):
- **Retail Trade:** Underestimates Black by 9-21pp
- **Healthcare/Social:** Underestimates Black by 5-18pp
- **Other Manufacturing:** Underestimates White by 8-15pp
- **Utilities:** Underestimates White by 7-12pp (except M3)
- **Computer/Electrical Mfg:** Overestimates Black by 8-11pp
- **Finance/Insurance:** Overestimates White by 5-26pp

These biases reflect structural mismatches between data source composition and actual employer demographics.

---

## 7. Method-Specific Observations

### 7.1 M1b: Why Learned Weights Work

The optimization discovered that the original 60/40 ACS/LODES default significantly overweights ACS for most industries. The county-level LODES workplace data is more informative because:

1. **LODES captures local labor markets.** An employer in a specific county draws from that county's workforce. ACS gives national industry averages.
2. **ACS NAICS coverage is imprecise.** ACS uses 4-digit NAICS with fallback to 2-digit, introducing noise from dissimilar industries.
3. **The exceptions are informative.** Construction (0.90 ACS) and Admin/Staffing (0.90 ACS) are industries where workers don't work in the company's county -- they're deployed elsewhere. LODES workplace data for the company's HQ county doesn't reflect where these workers actually are.

### 7.2 M3b: Why Dampening Helps

Standard IPF (M3) computes category_k = ACS_k * LODES_k, which squares any agreement. If both sources say 80% White, IPF returns ~96% White after normalization. Dampened IPF uses sqrt(ACS_k) * sqrt(LODES_k) = geometric mean, which is equivalent to a log-space average. This preserves the directional agreement while preventing the extreme amplification.

M3b's improvement is largest for Professional/Technical (-23% vs M3) and Finance/Insurance (-22% vs M3) -- diverse white-collar industries where M3's amplification was most harmful.

### 7.3 M2b: Why Workplace Tract Didn't Help

M2b matches M2 exactly because the tract selection heuristic is too crude. We pick the highest-employment tract in the county, which is typically a commercial/industrial center. Without knowing the company's actual address (or at least its ZIP centroid), we can't identify the right tract. A future improvement would use ZIP-to-tract crosswalks or geocoding.

### 7.4 M5b: Why Minority Adaptation Failed

M5b increases ACS weight in high-minority counties, reasoning that industry composition matters more when the local workforce is diverse. In practice, this pushes estimates toward the national industry average (more White) -- exactly the wrong direction. The county LODES data is actually more valuable in diverse areas because it reflects the local labor supply.

---

## 8. Recommendations

### 8.1 Production Method

**Recommended:** M1b (Learned Weights) as the primary production method.

- Best overall race MAE (5.15)
- Wins 77 of 200 head-to-head comparisons
- Simple to understand and implement (just different weights per industry)
- Robust across size buckets, regions, and industry groups

**Consideration:** Run holdout validation before finalizing. The weights were optimized on this same 200-company set, so M1b's advantage may be partially due to overfitting. If holdout performance degrades significantly, fall back to M3b or a blended approach.

### 8.2 Ensemble Option

For maximum robustness, consider an ensemble:
- **Urban + Medium/High minority:** M1b
- **Rural + Low minority:** M3 IPF or M3b
- **Gender estimation:** Use M3 IPF gender output regardless of race method

This would capture M1b's urban race advantage while keeping M3's rural accuracy.

### 8.3 Known Limitations

1. **High-minority companies remain the biggest challenge.** Even the best method (M1b) has 11.7 MAE -- nearly 3x the low-minority error. No method can solve this without employer-level data.
2. **Gender estimation is weak across the board** (10-15 MAE). Neither ACS nor LODES provides strong gender signals at the needed granularity.
3. **Western companies are hardest** (MAE ~7.2 at best), likely due to California's extreme workforce diversity and commuting patterns.
4. **Small companies (1-99) are noisy.** Individual company composition varies widely from area averages. M3 IPF helps here but is harmful elsewhere.

### 8.4 Future Improvements

1. **ZIP-to-tract geocoding** for M2b (would make workplace tract layer useful)
2. **Cross-validation** for weight optimization (k-fold instead of single split)
3. **Company-size adaptive weighting** (small companies -> more LODES, large -> more ACS)
4. **Occupation-by-geography interaction** (M4b with county-level occupation data)
5. **Holdout validation** (198 companies selected, ready to run)

---

## 9. Validation Infrastructure

### 9.1 Data Pipeline

```
Step 1: build_lodes_tract_table.py
        -> Creates cur_lodes_tract_metrics (80,813 tracts from 2.2M LODES blocks)

Step 2: compute_optimal_weights.py
        -> Finds per-NAICS-group optimal ACS/LODES weights
        -> Output hardcoded in methodologies.py OPTIMAL_WEIGHTS_BY_GROUP

Step 3: run_comparison_200_v2.py --companies selected_200.json
        -> Runs all 11 methods against 200 EEO-1 companies
        -> Outputs comparison_original_200_v2_detailed.csv (6,600 rows)
        -> Outputs comparison_original_200_v2_summary.csv (352 rows)

Step 4: select_holdout_200.py
        -> Selects 198 holdout companies (zero overlap with original 200)
        -> Outputs selected_holdout_200.json

Step 5 (pending): run_comparison_200_v2.py --companies selected_holdout_200.json
        -> Honest out-of-sample validation
```

### 9.2 Validation Set Composition

**Original 200 companies:**

| Dimension | Buckets | Range |
|-----------|---------|-------|
| Industry | 18 groups | 3-48 companies per group |
| Size | 4 buckets | 24-101 per bucket |
| Region | 4 regions | 25-77 per region |
| Minority Share | 3 levels | 29-111 per level |
| Urbanicity | 3 levels | 17-157 per level |

**Holdout 198 companies:** Same stratification algorithm, zero overlap, comparable distribution.

### 9.3 Metrics

- **MAE (Mean Absolute Error):** Average |estimated - actual| across race categories. Primary metric.
- **Hellinger Distance:** Distribution distance [0,1]. More sensitive to tail categories.
- **RMSE:** Root mean square error. Penalizes large errors more than MAE.
- **Max Error:** Worst single-category error. Identifies failure modes.
- **Signed Errors:** Per-category bias direction (positive = overestimate).
- **Win Count:** How often a method has the lowest MAE for a specific company.

---

## 10. File Inventory

| File | Purpose |
|------|---------|
| `data_loaders.py` | Database query functions (ACS, LODES, tract, occupation) |
| `methodologies.py` | 11 estimation methods + helpers |
| `cached_loaders.py` | Cached wrappers for M1-M6 |
| `cached_loaders_v2.py` | Cached wrappers for M1b-M5b, M7 |
| `classifiers.py` | 5D company classification |
| `config.py` | Industry weights, categories, EEO-1 path |
| `metrics.py` | MAE, RMSE, Hellinger, signed errors |
| `eeo1_parser.py` | EEO-1 CSV parsing |
| `select_200.py` | Original 200 stratified selection |
| `select_holdout_200.py` | Holdout 198 selection |
| `build_lodes_tract_table.py` | LODES tract ETL (80K tracts) |
| `compute_optimal_weights.py` | M1b weight optimization |
| `run_comparison_200.py` | Original 6-method runner |
| `run_comparison_200_v2.py` | V2 11-method runner |
| `selected_200.json` | Original 200 companies |
| `selected_holdout_200.json` | Holdout 198 companies |
| `comparison_original_200_v2_detailed.csv` | Per-company/method/dimension results |
| `comparison_original_200_v2_summary.csv` | Aggregated by classification/bucket/method |
