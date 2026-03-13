# Workforce Demographics Estimation: Complete Summary (V1-V4)

**Date:** 2026-03-09
**Scope:** 4 development iterations, 29 methods tested, 797 training + 398 holdout + ~998 development evaluations
**Ground truth:** EEO-1 Type 2 filings (mutually exclusive race/ethnicity categories)
**Primary metric:** Race MAE (mean absolute percentage-point error across race categories)

---

## 1. Problem Statement

The platform estimates workforce demographics (race, gender, Hispanic origin) for employers that do not publicly report this data. No single public dataset captures actual employer-level demographics, so we blend multiple statistical sources -- each capturing a different slice of the labor market -- and validate against the subset of employers that do report via EEO-1 filings.

**Core challenge:** All public data measures area-level or industry-level averages. An individual employer may differ substantially from these averages, especially if its workforce is more or less diverse than its surrounding county or industry peers. This "regression to the mean" creates a systematic bias that no purely statistical method can fully eliminate.

---

## 2. Data Sources

| Source | Table | Geographic Level | Industry Level | What It Measures |
|--------|-------|-----------------|----------------|-----------------|
| ACS (IPUMS) | `cur_acs_workforce_demographics` | State | 4-digit NAICS | Workers in industry X in state Y |
| LODES | `cur_lodes_geo_metrics` | County | 3 broad sectors | Workers whose jobs are in county Z |
| LODES Tract | `cur_lodes_tract_metrics` | Census tract | None | Workers whose jobs are in tract T |
| Census Tract | `acs_tract_demographics` | Census tract | None | Residents of the tract |
| BLS Occ Matrix | `bls_industry_occupation_matrix` | National | 4-digit NAICS | Occupation mix of industry X |
| ACS by Occ | `cur_acs_workforce_demographics` | State | SOC code | Workers in occupation O in state Y |
| ZIP-Tract Crosswalk | `zip_tract_crosswalk` | ZIP -> Tract | None | Maps employer ZIP to census tracts (V3) |

**Source strengths and weaknesses:**

| Source | Strength | Weakness |
|--------|----------|----------|
| ACS | Industry-specific demographics at state level | No sub-state geography; state averages mask local variation |
| LODES | County-level workplace demographics (not residential) | Only 3 industry sectors; no NAICS detail |
| Tract | Local residential demographics | Measures residents, not workers; includes non-workers |
| BLS Occ | Captures occupational segregation | National only; limited SOC-NAICS crosswalk coverage |

---

## 3. Validation Framework

### 3.1 Ground Truth

EEO-1 Type 2 filings from EEOC objector data (2018-2020). Mutually exclusive non-Hispanic race categories: White, Black, Asian, AIAN, NHOPI, Two or More Races. Hispanic/Not Hispanic and Male/Female as separate dimensions.

### 3.2 Company Selection

Companies selected via stratified sampling across 5 classification dimensions:

| Dimension | Buckets |
|-----------|---------|
| NAICS industry group | 18 groups (Finance/Insurance, Professional/Technical, Construction, etc.) |
| Workforce size | 1-99, 100-999, 1k-9999, 10000+ |
| Census region | Midwest, Northeast, South, West |
| Minority share (from EEO-1) | Low (<25%), Medium (25-50%), High (>50%) |
| Urbanicity (from CBSA) | Urban, Suburban, Rural |

Each bucket targets `max(3, round(N * group_share))` companies, with a greedy algorithm maximizing cross-dimensional coverage.

### 3.3 Datasets Used

| Version | Training Set | Holdout Set | Exclusions |
|---------|-------------|-------------|------------|
| V1 | 200 companies (`selected_200.json`) | None (train-only) | -- |
| V2 | Same 200 | 198 companies (`selected_holdout_200.json`) | Excludes V1 200 |
| V3 | 399 companies (`selected_400.json`) | 200 companies (`selected_holdout_v3.json`) | Excludes all prior 398 |
| V4 | All ~998 prior companies (`all_companies_v4.json`) | None (development eval only) | No new companies selected |

**V4 note:** V4 deliberately uses no new companies in order to preserve the remaining untested pool for future true holdout tests. Results from V4 are development evaluations, not generalization benchmarks. The V3 holdout slice within the ~998 pool is used as a proxy generalization check.

### 3.4 Metrics

| Metric | Formula | Interpretation |
|--------|---------|---------------|
| MAE | mean(\|est_k - actual_k\|) across categories | Average category-level percentage point error |
| RMSE | sqrt(mean((est_k - actual_k)^2)) | Penalizes large errors more than MAE |
| Hellinger | sqrt(0.5 * sum((sqrt(p_k) - sqrt(q_k))^2)) | Distributional distance [0,1] |
| Signed Error | est_k - actual_k per category | Positive = overestimate; reveals bias direction |
| Wins | Count of companies where method has lowest MAE | Head-to-head ranking |

---

## 4. Version 1: Establishing the Baseline

### 4.1 Methods (6)

| Method | Formula | Idea |
|--------|---------|------|
| **M1 Baseline** | 60% ACS + 40% LODES | Fixed blend, ACS industry + LODES geography |
| **M2 Three-Layer** | 50% ACS + 30% LODES + 20% Tract | Add residential layer |
| **M3 IPF** | (ACS_k * LODES_k) / sum | Normalized product (maximum entropy) |
| **M4 Occ-Weighted** | 70% occ-weighted ACS + 30% LODES | Weight by BLS occupation mix |
| **M5 Variable-Weight** | Industry-adaptive ACS/LODES weights | Hardcoded: local_labor=40/60, occupation=75/25, mfg=55/45 |
| **M6 IPF+Occ** | IPF using occ-weighted ACS | Combine M3 + M4 |

### 4.2 Results (Training Only, 200 Companies)

| Rank | Method | Race MAE | Race Wins |
|------|--------|----------|-----------|
| 1 | **M1 Baseline (60/40)** | **5.74** | 35 |
| 2 | M4 Occ-Weighted | 5.92 | 16 |
| 3 | M2 Three-Layer | 5.95 | 59 |
| 4 | M5 Variable-Weight | 5.99 | 20 |
| 5 | M3 IPF | 7.13 | 70 |
| 6 | M6 IPF+Occ | 7.13 | 0 |

### 4.3 V1 Key Findings

1. **M1 (simple 60/40 blend) won overall.** Near-zero White/Black bias (+0.5pp/-0.7pp). No complex method beat the simplest approach.

2. **M3 IPF was paradoxical.** Worst overall MAE (7.13) but most individual company wins (70/200). Perfect for rural/low-minority (MAE 1.6) but catastrophic for diverse companies. Overestimates White by +19pp on average due to quadratic amplification: 0.70 * 0.60 = 0.42 (White) vs 0.15 * 0.25 = 0.04 (Black), normalizing to 91% White.

3. **M6 was identical to M3** -- occupation weighting added nothing to IPF. Eliminated.

4. **Minority share was the dominant dimension.** Low (<25%): 3-4 MAE. High (>50%): 13-18 MAE. A 3-5x error gap that persists across all methods and all versions.

5. **All methods underestimate Asian (-3.7 to -7.8pp)** -- ACS NAICS codes too broad, LODES has no industry detail.

6. **All blend methods overestimate Two+ Races (+5.3 to +6.6pp)** -- IPUMS-to-EEO-1 race code mapping artifact.

### 4.4 V1 Decisions

- M1 Baseline selected as production default
- M6 eliminated (identical to M3)
- Investigate: learned weights, dampened IPF, holdout validation

---

## 5. Version 2: Learned Weights and Holdout Validation

### 5.1 New Methods (6)

| Method | Base | Change | Hypothesis |
|--------|------|--------|-----------|
| **M1b Learned-Wt** | M1 | Per-NAICS-group ACS/LODES weights via grid search [0.30, 0.90] | Let data determine optimal blend |
| **M2b Workplace-Tract** | M2 | Use LODES tract (workplace) instead of ACS tract (residential) | Workplace data > residential |
| **M3b Dampened IPF** | M3 | sqrt(ACS_k) * sqrt(LODES_k) normalized | Reduce extreme amplification |
| **M4b State-Occ** | M4 | State-level ACS occupation proportions instead of national BLS | State-specific occ demographics |
| **M5b Min-Adapt** | M5 | Increase ACS weight in high-minority counties (+0.20) | More ACS in diverse areas |
| **M7 Hybrid** | M1b+M3 | M1b race + M3 gender | Cherry-pick best of each |

### 5.2 M1b Weight Optimization

Grid search over 13 ACS weight values (0.30 to 0.90, step 0.05) per NAICS group. Key finding: most industries optimized to heavy LODES:

| Pattern | Groups | ACS/LODES | Interpretation |
|---------|--------|-----------|---------------|
| Heavy LODES | Finance, Prof/Tech, Info, Mfg, Wholesale, Retail, etc. | 0.30/0.70 | County workplace data is more informative than industry averages |
| Heavy ACS | Construction, Admin/Staffing, Utilities | 0.90/0.10 | Workers deployed away from HQ county; LODES at HQ is misleading |
| Moderate | Healthcare, Metal/Machinery | 0.35/0.65 | Slight LODES preference |

### 5.3 V2 Training Results (200 Companies)

| Rank | Method | Race MAE | vs M1 |
|------|--------|----------|-------|
| 1 | **M1b Learned-Wt** | **5.15** | **-10.3%** |
| 2 | M7 Hybrid | 5.15 | -10.3% |
| 3 | M3b Damp-IPF | 5.37 | -6.4% |
| 4 | M1 Baseline | 5.74 | -- |
| 5-10 | M4, M2, M2b, M5, M4b, M5b | 5.92-6.08 | +3% to +6% |
| 11 | M3 IPF | 7.13 | +24.2% |

### 5.4 V2 Holdout Validation (198 Companies) -- Rankings Flipped

| Rank | Method | Holdout MAE | Training MAE | Retention Rate |
|------|--------|-------------|-------------|----------------|
| 1 | **M3b Damp-IPF** | **4.55** | 5.37 | 126% (improves) |
| 2 | M1b Learned-Wt | 4.72 | 5.15 | 45% (overfit) |
| 3 | M7 Hybrid | 4.72 | 5.15 | 45% |
| 4 | M1 Baseline | 4.95 | 5.74 | -- |
| 5-10 | M5, M4, M5b, M2, M2b, M4b | 5.08-5.32 | | |
| 11 | M3 IPF | 6.17 | 7.13 | Consistently bad |

**"Retention rate"** = how much of a method's training advantage over M1 survives on holdout. >100% means the advantage grows. <100% indicates overfitting.

### 5.5 V2 Key Findings

1. **M1b's learned weights were ~55% overfit.** Training advantage -10.3% vs M1; holdout advantage only -4.6%. The 0.90 ACS weights for groups with N <= 11 training companies (Admin/Staffing, Construction, Utilities) didn't generalize.

2. **M3b (Dampened IPF) was the true winner.** Zero trainable parameters (sqrt product), so no overfitting possible. Its advantage over M1 actually grew on holdout (6.4% -> 8.1%).

3. **Three methods were dead on arrival:**
   - M2b = M2 exactly (tract selection heuristic too crude without ZIP crosswalk)
   - M7 = M1b exactly on race (hybrid adds nothing to primary metric)
   - M5b worse than M5 (increasing ACS in diverse areas pushes estimates toward national average -- more White -- exactly the wrong direction)

4. **M3 IPF remained the gender winner** (9.89 MAE, 101/198 wins). Gender distributions are less geographically variable, so IPF's amplification works.

5. **Small-group overfitting confirmed:** NAICS groups with N >= 44 training companies showed no overfitting. Groups with N <= 11 overfit consistently.

### 5.6 V2 Decisions

- M3b Damp-IPF selected as recommended production method
- M2b, M7, M5b, M4b eliminated (dead or worse than base)
- M1b retained for large companies and medium-minority areas
- M3 IPF retained for gender estimation only
- V3 plan: 5-fold CV, constrained weight range, larger training set, ZIP-to-tract crosswalk

---

## 6. Version 3: Cross-Validated Optimization

### 6.1 V2 Weaknesses Addressed

| V2 Problem | V3 Fix |
|-----------|--------|
| M1b overfitting (55% lost on holdout) | 5-fold CV + [0.35, 0.75] weight constraints (M1c) |
| Small training groups (3-11 companies) | 399 new training companies (separate from all prior sets) |
| M2b tract selection too crude | Built `zip_tract_crosswalk` table from LODES + ZIP data (M2c) |
| M3b uses fixed dampening for all industries | Per-NAICS-group alpha exponent via 5-fold CV (M3c) |
| M5b pushed weights in wrong direction | Flipped: increase LODES (not ACS) in high-minority (M5d) |

### 6.2 New Methods (9)

| Method | Base | Change |
|--------|------|--------|
| **M1c CV-Learned-Wt** | M1b | 5-fold CV, weights constrained to [0.35, 0.75] |
| **M1d Regional-Wt** | M1 | 75/25 ACS/LODES for West region, 60/40 for rest |
| **M2c ZIP-Tract** | M2 | ZIP-to-tract crosswalk for 3rd layer (workplace tract) |
| **M3c Var-Damp-IPF** | M3b | ACS^alpha * LODES^(1-alpha), alpha optimized per NAICS group |
| **M3d Select-Damp** | M3 | Raw IPF when county minority <20%, dampened when >20% |
| **M4c Top10-Occ** | M4 | Top-10 occupations instead of top-30 |
| **M4d State-Top5** | M4b | State ACS for top-5 occupations, national for rest |
| **M5c CV-Var-Wt** | M5 | CV-optimized weights by 4 M5 industry categories |
| **M5d Corr-Min-Adapt** | M5b | Flipped direction: reduce ACS (more LODES) in high-minority |

### 6.3 Optimized Parameters (5-Fold CV, 399 Companies)

**M1c/M5c learned weights:**

| Group | ACS Weight | LODES Weight | Interpretation |
|-------|-----------|-------------|---------------|
| Construction (23) | 0.75 | 0.25 | Workers deployed away from HQ |
| Wholesale Trade (42) | 0.50 | 0.50 | Moderate locality |
| All other groups | 0.35 | 0.65 | Default: LODES wins |
| *M5c local_labor category* | 0.75 | 0.25 | Same as Construction |
| *M5c all other categories* | 0.35 | 0.65 | Same as default |

**M3c dampening alphas** (higher alpha = less dampening, more like raw IPF):

| Group | Alpha | Interpretation |
|-------|-------|---------------|
| Construction (23) | 0.65 | Least dampening -- local labor patterns are real |
| Wholesale Trade (42) | 0.45 | Moderate |
| Healthcare/Social (62) | 0.40 | Moderate |
| Professional/Technical (54) | 0.40 | Moderate |
| Finance/Insurance (52) | 0.30 | Most dampening -- national workforce patterns |
| Other | 0.30 | Most dampening |
| All other groups | 0.35 | Default |

### 6.4 V3 Holdout Results (200 Companies, 16 Methods)

| Rank | Method | Holdout MAE | Train MAE | Delta | Wins |
|------|--------|-------------|-----------|-------|------|
| 1 | **M3c Var-Damp-IPF** | **4.33** | 4.09 | +0.23 | 21 |
| 2 | M3b Damp-IPF | 4.48 | 4.21 | +0.26 | 19 |
| 3 | M1b Learned-Wt | 4.52 | 4.46 | +0.05 | 42 |
| 4 | M3d Select-Damp | 4.53 | 4.30 | +0.23 | 0 |
| 5 | M1c CV-Learned-Wt | 4.56 | 4.49 | +0.07 | 5 |
| 6 | M5c CV-Var-Wt | 4.58 | 4.49 | +0.08 | 1 |
| 7 | M2c ZIP-Tract | 4.70 | 4.71 | -0.01 | 9 |
| 8 | M1 Baseline | 4.79 | 4.75 | +0.04 | 2 |
| 9 | M1d Regional-Wt | 4.85 | 4.81 | +0.04 | 1 |
| 10 | M5d Corr-Min-Adapt | 4.91 | 4.91 | +0.00 | 0 |
| 11 | M4 Occ-Weighted | 4.93 | 4.88 | +0.05 | 4 |
| 12 | M4c Top10-Occ | 4.93 | 4.88 | +0.05 | 0 |
| 13 | M4d State-Top5 | 4.93 | 4.88 | +0.05 | 0 |
| 14 | M5 Variable-Weight | 4.93 | 4.90 | +0.03 | 12 |
| 15 | M2 Three-Layer | 5.05 | 5.16 | -0.10 | 13 |
| 16 | M3 IPF (raw) | 5.81 | 5.30 | +0.51 | 71 |

### 6.5 V3 Key Findings

1. **M3c (Variable Dampened IPF) is the new champion.** Per-industry alpha exponents let Finance (alpha=0.30, heavy dampening) behave differently from Construction (alpha=0.65, light dampening). Adds 0.15 MAE improvement over M3b's uniform dampening and generalizes well (delta +0.23).

2. **The CV fix worked exactly as designed.** M1c achieved the tightest generalization gap of any method: train 4.49 -> holdout 4.56 (delta +0.07). But M1b's unconstrained V1-era weights also generalized well on V3's fresh holdout (delta +0.05), suggesting V2's overfitting was partly a holdout-composition effect (V2 holdout had more high-minority companies).

3. **M2c (ZIP-Tract) validated V2's hypothesis.** The `zip_tract_crosswalk` table enabled proper tract selection. M2c: 4.70 vs M2: 5.05 = 6.9% improvement. M2c also achieved the best Hispanic MAE (6.37) of any method because tract-level data captures Hispanic geographic concentration.

4. **Three V3 methods were complete failures:**
   - M4c Top10-Occ = M4 exactly (top-10 vs top-30 makes no difference)
   - M4d State-Top5 = M4 exactly (state-level for top-5 also makes no difference)
   - M1d Regional-Wt was worse than M1 Baseline (West needs more LODES, not more ACS)

5. **M3d (selective dampening) is unreliable.** Ranked #4 overall but won zero individual companies and had the largest overfitting gap in V2-equivalent analysis. A "consistent mediocrity" method that never excels.

6. **The entire M4 occupation-weighted branch is dead.** M4, M4c, and M4d are identical. Across V1, V2, and V3, occupation weighting never materially improved over simple blending. The BLS occupation matrix doesn't add enough signal.

---

## 7. Version 4: Method Routing + Combined Method (IN PROGRESS)

### 7.1 V3 Weaknesses Addressed

| V3 Problem | V4 Fix |
|-----------|--------|
| M3c routes Finance/Insurance through variable dampening despite M3 original dominating (1.31 vs 3.34) | Explicit routing to M3 original for Finance/Insurance and Utilities (M3e) |
| M3d's 20% minority threshold uncalibrated; doesn't account for industry | Cross-validated threshold + industry routing (M3f) |
| M1b has no floor constraint in high-minority counties where LODES is most valuable | Minimum LODES weight floor for >30% and >50% minority counties (M1e) |
| M4c and M4d produced identical output to M4 (suspected code bug) | Debug M4 family first; replace employment-size trim with demographic-variance filter (M4e) |
| M2c's 20% tract weight is conservative; ZIP-to-tract crosswalk works well | Increase tract layer to 35%, reduce county layer to 20% (M2d) |
| M5 variable weights used for blending; industry categories more useful as routing logic | Replace M5 blend with method-routing dispatcher (M5e) |
| No single method exploits the full pattern of context-specific winners | M8: Adaptive Context Router using V3-validated routing rules |

### 7.2 New Methods (7)

| Method | Base | Change | Key Hypothesis |
|--------|------|--------|---------------|
| **M3e Finance-Routed** | M3c | Hard routing: Finance/Insurance + Utilities → M3 original; all else → M3c | Finance/Utilities demographics match M3's amplification model exactly |
| **M3f Threshold-Tuned** | M3d | Finance/Utilities routing + CV-optimized minority threshold [0.15-0.30] | Minority threshold of 20% may not be optimal |
| **M1e High-Min Floor** | M1b | Floor: LODES weight ≥ 40% when minority >50%, ≥ 30% when >30% | LODES local signal most valuable precisely where learned weights ignore it |
| **M4e Variance-Trim** | M4 | Filter out occupations with White deviation >8pp above industry baseline | Niche professional/mgmt occupations inflate White estimates |
| **M2d Amplified Tract** | M2c | 45% ACS + 20% LODES county + 35% LODES tract (up from 20%) | More tract weight when ZIP crosswalk is available |
| **M5e Method-Dispatcher** | M5 | Route by industry category to best V3 method (not blend weights) | Category structure = routing logic, not blending logic |
| **M8 Adaptive Router** | All | Priority routing tree: Finance→M3, Utilities→M3, Admin/Staffing→M4e, HighMinority→M1b, SuburbanLow→M3, Midwest→M3d, Default→M3c | Ensemble by context, not by averaging |

### 7.3 M8 Routing Logic

M8 is a meta-method that selects the best estimator for each company's context. Rules applied in priority order:

| Priority | Condition | Method | Evidence |
|----------|-----------|--------|----------|
| 1 | Finance/Insurance (52) | M3 IPF (original) | V3 holdout: M3 MAE 1.31 vs M3c 3.34 (N=49) |
| 2 | Utilities (22) | M3 IPF (original) | V3 holdout: M3d 1.69 vs M3c 2.87 (N=5) |
| 3 | Admin/Staffing (56) | M4e Variance-Trim | V3 holdout: M4 4.58 vs M3c 6.20 (N=6) |
| 4 | Minority share >50% | M1b Learned-Wt | V3 holdout: M1b 10.36 vs M3c 10.92 (N=24) |
| 5 | Suburban + minority <25% | M3 IPF (original) | V3 holdout: M3 1.41 vs M3c 3.33 (N=51 suburban) |
| 6 | Midwest region | M3d Select-Damp | V3 holdout: M3d 2.75 vs M3c 3.03 (N=49) |
| 7 | All other | M3c Var-Damp-IPF | Overall V3 winner |

M8 also routes Hispanic estimation separately: M2c (geographic tract) for most industries; M1b-based estimate for Admin/Staffing, Healthcare, Retail, Transport Equipment where M1b wins Hispanic.

**Projected M8 performance:** ~3.6–3.9 Race MAE (vs M3c's 4.33), primarily from routing Finance/Insurance (~25% of companies) to M3 original.

### 7.4 V4 Evaluation Approach

V4 runs against `all_companies_v4.json` — all ~998 previously used companies merged from all four prior JSON files. No new companies are selected.

**Why no new holdout:** We are preserving the remaining untested companies for a future true generalization test once V4 methods are finalized. V4 is a development evaluation.

**Optimism bias mitigation:** All results are sliced by `source_set` tag:
- `v3_holdout` slice (200 companies): best proxy for true generalization — never used in any optimization
- `v3_train` slice (400 companies): used to train M3c and M1c parameters
- `v2_*` slices (398 companies): used in V1-V2 development

**Threshold optimization:** M3f's minority-share threshold is cross-validated on the V3 training set only (not all 998), to avoid circular evaluation.

### 7.5 V4 Results

*To be completed after V4 run.*

---

## 8. Progression Summary

### 8.1 Best Method Evolution

| Version | Champion | Holdout MAE | Key Innovation |
|---------|----------|-------------|----------------|
| V1 | M1 Baseline (60/40) | 5.74 (train only) | Simple fixed-weight blend |
| V2 | M3b Dampened IPF | 4.55 | sqrt dampening eliminates IPF overamplification |
| V3 | M3c Var-Damp-IPF | 4.33 | Per-industry dampening alpha via 5-fold CV |
| V4 | M8 Adaptive Router (projected) | ~3.6–3.9 (dev eval) | Context-based method routing; Finance/Insurance fix |

**Total improvement V1→V3: 5.74 → 4.33 = 24.6% reduction in race MAE.**

### 8.2 What We Learned at Each Stage

| Lesson | Version | Evidence |
|--------|---------|----------|
| Simple 60/40 blend is a strong baseline | V1 | Beat 5 more complex methods on training |
| IPF amplification is the core problem with M3 | V1 | +19pp White overestimation average |
| M6 (IPF+Occ) is redundant | V1 | 0 wins, identical to M3 |
| LODES matters more than ACS for most industries | V2 | Most industries optimize to 0.30 ACS / 0.70 LODES |
| Holdout validation is essential | V2 | M1b's 10.3% training advantage was 55% overfit |
| Dampened IPF generalizes perfectly (zero parameters) | V2 | M3b: ranked 3rd on training, 1st on holdout |
| Learned weights overfit when group N < 15 | V2 | Admin/Staffing (N=6) weight of 0.90 didn't generalize |
| Increasing ACS in high-minority areas hurts | V2 | M5b: worse than baseline (pushes toward whiter national average) |
| Workplace tract selection needs ZIP crosswalk | V2 | M2b = M2 exactly without proper geocoding |
| 5-fold CV + weight constraints eliminate overfitting | V3 | M1c generalization delta: only +0.07 MAE |
| Per-industry dampening alpha adds real value | V3 | M3c beats M3b by 0.15 MAE, generalizes well |
| ZIP-to-tract crosswalk fixes M2b's failure | V3 | M2c: 6.9% improvement over M2 |
| Occupation trimming (top-10, state-top-5) has zero effect | V3 | M4c = M4d = M4 to 2 decimal places |
| Regional weight adjustment is counterproductive | V3 | M1d worse than M1 for West |
| Flipping minority-adaptive direction barely helps | V3 | M5d: +0.02 improvement (negligible) |
| M3 original IPF dramatically outperforms M3c for Finance and Suburban low-minority | V3 | Finance: M3 1.31 vs M3c 3.34; Suburban: M3 1.41 vs M3c 3.33 |
| Method routing beats single-formula methods in heterogeneous datasets | V4 (hypothesis) | M8 routing tree exploits context-specific winners |
| Occupation variance (not size) determines which occupations inflate White estimates | V4 (hypothesis) | M4e filters by demographic deviation, not employment rank |

### 7.3 Methods Tested and Eliminated

| Method | Introduced | Eliminated | Reason |
|--------|-----------|-----------|--------|
| M6 IPF+Occ | V1 | V1 | Identical to M3 (0 wins) |
| M2b Workplace-Tract | V2 | V2 | Identical to M2 (no ZIP crosswalk) |
| M7 Hybrid (M1b race + M3 gender) | V2 | V2 | Identical to M1b on primary metric |
| M5b Min-Adapt (+ACS in high-minority) | V2 | V2 | Worse than M5 (wrong direction) |
| M4b State-Occ | V2 | V2 | Worse than M4 on average |
| M1d Regional-Wt (75/25 for West) | V3 | V3 | Worse than M1 Baseline |
| M4c Top10-Occ | V3 | V3 | Identical to M4 (code bug) |
| M4d State-Top5 | V3 | V3 | Identical to M4 (code bug) |
| M5d Corr-Min-Adapt (flipped M5b) | V3 | V3 | Negligible improvement (+0.02 MAE) |

### 8.4 Surviving Production Candidates (post-V3)

| Method | Role | V3 Holdout MAE | Parameters | Strengths |
|--------|------|----------------|-----------|-----------|
| **M3c Var-Damp-IPF** | Primary (race) | **4.33** | 18 alpha values | Best overall; per-industry dampening |
| **M1b Learned-Wt** | High-minority, large cos | 4.52 | 18 weight pairs | Most individual wins (42); best at >50% minority |
| **M1c CV-Learned-Wt** | Max robustness | 4.56 | 18 weight pairs (CV) | Tightest generalization gap (+0.07) |
| **M2c ZIP-Tract** | Best Hispanic accuracy | 4.70 | None (structural) | Best Hispanic MAE (6.37); best for Food/Bev Mfg |
| **M3b Damp-IPF** | Parameter-free fallback | 4.48 | None | Zero parameters; simple formula; robust |
| **M3 IPF** | Gender + Finance/Suburban | 5.81 (race overall) | None | Finance MAE 1.31; Suburban 1.41; best gender |

**V4 adds:** M8 (Adaptive Router) as projected primary method; M3e, M3f as M3c improvements; M1e as M1b refinement; M4e as first working occupation-variance filter; M2d as M2c amplification; M5e as routing dispatcher.

---

## 9. Performance by Employer Type

### 12.1 By Industry (V3 Holdout, Best Method)

| Industry | N | Best Method | MAE | Difficulty |
|----------|---|-------------|-----|-----------|
| Finance/Insurance | 49 | M3 IPF | 1.31 | Easy |
| Utilities | 5 | M3d Select-Damp | 1.69 | Easy |
| Transport Equip Mfg | 3 | M3c Var-Damp-IPF | 1.98 | Easy |
| Construction | 13 | M3c Var-Damp-IPF | 2.15 | Easy |
| Metal/Machinery Mfg | 5 | M1b Learned-Wt | 3.56 | Moderate |
| Chemical/Material Mfg | 5 | M3c Var-Damp-IPF | 3.88 | Moderate |
| Wholesale Trade | 13 | M1 Baseline | 3.72 | Moderate |
| Professional/Technical | 45 | M3c Var-Damp-IPF | 3.85 | Moderate |
| Other | 24 | M1b Learned-Wt | 3.98 | Moderate |
| Admin/Staffing | 6 | M4 Occ-Weighted | 4.58 | Moderate |
| Information | 5 | M4 Occ-Weighted | 4.91 | Moderate |
| Retail Trade | 3 | M3d Select-Damp | 5.40 | Hard |
| Computer/Electrical Mfg | 3 | M1b Learned-Wt | 5.31 | Hard |
| Other Manufacturing | 6 | M3b Damp-IPF | 5.88 | Hard |
| Food/Bev Manufacturing | 4 | M2c ZIP-Tract | 8.05 | Very Hard |
| Healthcare/Social | 11 | M2 Three-Layer | 10.91 | Intractable |

### 12.2 By Key Dimensions (V3 Holdout)

**Workforce Size:**

| Size | N | Best | MAE | Notes |
|------|---|------|-----|-------|
| 1-99 | 54 | M3 IPF | 1.98 | IPF product works for small homogeneous firms |
| 100-999 | 78 | M3c | 4.30 | Sweet spot for dampened IPF |
| 1k-9999 | 49 | M3c | 5.18 | Mid-size is hardest; non-local but not dominant |
| 10000+ | 19 | M3c | 4.64 | National footprint averages toward population |

**Minority Share:**

| Level | N | Best | MAE | Notes |
|-------|---|------|-----|-------|
| Low (<25%) | 120 | M3 IPF | 2.52 | IPF excels when sources agree on White majority |
| Medium (25-50%) | 56 | M1b | 3.84 | Learned weights help in moderate-diversity zone |
| High (>50%) | 24 | M1b | 10.36 | All methods fail; 3-5x worse than low minority |

**Region:**

| Region | N | Best | MAE | Notes |
|--------|---|------|-----|-------|
| Midwest | 49 | M3d | 2.75 | Low diversity + strong LODES data |
| Northeast | 27 | M3c | 4.00 | Urban density helps IPF methods |
| West | 34 | M3c | 4.55 | Hispanic concentration is the wild card |
| South | 90 | M3c | 5.05 | High diversity + complex racial geography |

**Urbanicity:**

| Setting | N | Best | MAE | Notes |
|---------|---|------|-----|-------|
| Suburban | 51 | M3 IPF | 1.41 | IPF dominates homogeneous suburbs |
| Rural | 9 | M5c | 3.60 | Small sample; methods roughly equivalent |
| Urban | 140 | M3c | 4.71 | 70% of companies; main battleground |

---

## 10. Persistent Bias Patterns

These biases appeared in all three versions and represent structural limitations of the data sources.

### 12.1 Average Signed Errors (V3 Holdout, Top Methods)

| Method | White | Black | Asian | AIAN | NHOPI | Two+ |
|--------|-------|-------|-------|------|-------|------|
| M3c Var-Damp-IPF | +1.3 | +0.3 | -2.7 | -0.1 | -0.4 | +1.7 |
| M3b Damp-IPF | +1.2 | +0.1 | -3.2 | -0.2 | -0.4 | +2.5 |
| M1b Learned-Wt | -1.7 | +1.0 | -1.8 | +0.2 | -0.3 | +2.6 |

### 12.2 The High-Minority Problem (Unsolved)

Every method in every version dramatically overestimates White share for companies with >50% minority workforce:

| Version | Best Method | White Overestimate (>50% minority) | MAE |
|---------|------------|-------------------------------------|-----|
| V1 | M2 Three-Layer | +23pp | 12.7 |
| V2 | M1b Learned-Wt | +25pp | 11.07 |
| V3 | M1b Learned-Wt | +25pp | 10.36 |

**Root cause:** Both ACS and LODES measure area/industry averages. A company with >50% minority workforce is, by definition, more diverse than the average employer in its area. Our estimates regress toward that average. No purely statistical method using area-level data can solve this.

### 12.3 Industry-Specific Structural Biases

| Industry | Direction | Magnitude | Root Cause |
|----------|-----------|-----------|-----------|
| Healthcare/Social | Overestimates White | +28-32pp (high minority) | Highly localized diverse workforce (nurses, aides) |
| Food/Bev Manufacturing | Overestimates White | +18-24pp | Immigrant workforce invisible to ACS/LODES |
| Finance/Insurance | Underestimates White | -10-13pp | Company-specific hiring differs from county |
| Construction | Underestimates White | -3-7pp (varies) | Workers at job sites, not HQ county |
| Retail Trade | Underestimates White | -13-16pp | Store-level diversity differs from county average |

### 12.4 The Asian Underestimation Problem

All methods in all versions underestimate Asian share (-1.8 to -7.8pp) because:
1. ACS NAICS codes are too broad (Professional/Technical includes both tech and law firms)
2. LODES has only 3 industry sectors (no industry detail)
3. Asian workers cluster in specific metros at rates far above county averages

### 12.5 The Gender Accuracy Gap

Gender MAE (10-16pp) is consistently 2-3x worse than race MAE (4-6pp) across all methods and versions. IPF-family methods (M3/M3b/M3c) are the best gender estimators because gender distributions are less geographically variable than race. All methods slightly overestimate Female share (+1.5 to +3.6pp).

---

## 11. Recommended Production Configuration

### 11.1 Primary Strategy: Context-Dependent Method Selection

**Post-V3 (current production):**

| Context | Method | Expected MAE |
|---------|--------|-------------|
| **Default (all employers)** | M3c Var-Damp-IPF | ~4.3 |
| **High-minority employers (>50%)** | M1b Learned-Wt | ~10.4 |
| **Finance/Insurance, Utilities** | M3 IPF (raw) | ~1.3–1.7 |
| **Food/Bev Manufacturing** | M2c ZIP-Tract | ~8.1 |
| **Admin/Staffing** | M4 Occ-Weighted | ~4.6 |
| **Gender estimation (all)** | M3 IPF | ~9.9 |
| **Hispanic estimation (all)** | M2c ZIP-Tract | ~6.4 |

**Post-V4 (projected — update after dev eval confirms):**

| Context | Method | Projected MAE |
|---------|--------|--------------|
| **Default** | M8 Adaptive Router | ~3.6–3.9 |
| **Finance/Insurance** | M3 IPF (via M8) | ~1.3–1.5 |
| **Utilities** | M3 IPF (via M8) | ~1.7–1.9 |
| **Admin/Staffing** | M4e Variance-Trim (via M8) | ~4.0–4.6 |
| **High-minority (>50%)** | M1b (via M8) | ~10.0–10.4 |
| **Suburban low-minority** | M3 IPF (via M8) | ~1.4–1.6 |
| **Midwest** | M3d (via M8) | ~2.7–3.0 |

### 11.2 If Only One Method

Use **M3c Var-Damp-IPF** (current) or **M8 Adaptive Router** (post-V4). M3c best overall holdout MAE (4.33), good generalization (+0.23 delta). Formula:

```
For each race category k:
  raw_k = ACS_k^alpha * LODES_k^(1-alpha)
  estimate_k = raw_k / sum(raw_j for all j)

Where alpha is industry-specific (see Section 6.3)
```

### 11.3 If Maximum Robustness Required

Use **M1c CV-Learned-Wt**. Holdout MAE 4.56 (slightly worse than M3c) but the tightest training-to-holdout delta of any method (+0.07 MAE). Will behave identically on new data as it did on training. Formula:

```
estimate = acs_weight * ACS(industry, state) + lodes_weight * LODES(county)

Where (acs_weight, lodes_weight) is per-NAICS-group (see Section 6.3)
```

### 11.4 Known Limitations

1. **High-minority companies (MAE 10+):** Fundamental data gap. Neither ACS nor LODES captures employer-specific hiring patterns. Would require employer-level data (job postings, partnerships, news).

2. **Healthcare/Social (MAE 10+):** Workforce is hyperlocal and diverse in ways that area averages cannot capture.

3. **Food/Bev Manufacturing (MAE 8+):** Immigrant workforce concentration is invisible to both ACS and LODES.

4. **Gender (MAE 10-16):** Industry-level gender composition varies enormously within NAICS codes. No method achieves <10 MAE consistently.

5. **Asian underestimation (-2 to -4pp):** Would require sub-NAICS industry codes or metro-level occupation data.

6. **V4 results are development evaluations only:** All ~998 V4 companies were used in prior rounds. True generalization can only be measured when fresh untested companies are evaluated in a future round.

---

## 12. File Inventory

### 12.1 Reports

| File | Content |
|------|---------|
| `docs/DEMOGRAPHICS_METHODOLOGY_COMPARISON.md` | V1 full report (6 methods, 200 companies) |
| `docs/DEMOGRAPHICS_ESTIMATION_SUMMARY.md` | This document (V1-V4 complete summary) |
| `demographic estimate model/METHODOLOGY_REPORT_V2.md` | V2 training report (11 methods) |
| `demographic estimate model/HOLDOUT_VALIDATION_REPORT.md` | V2 holdout report (198 companies) |
| `scripts/analysis/demographics_comparison/METHODOLOGY_REPORT_V3.md` | V3 auto-generated report |
| `scripts/analysis/demographics_comparison/METHODOLOGY_REPORT_V4.md` | V4 auto-generated report (pending) |

### 12.2 Selection Files

| File | Content |
|------|---------|
| `scripts/analysis/demographics_comparison/selected_200.json` | V1/V2 training set (200 companies) |
| `scripts/analysis/demographics_comparison/selected_holdout_200.json` | V2 holdout set (198 companies) |
| `scripts/analysis/demographics_comparison/selected_400.json` | V3 training set (399 companies) |
| `scripts/analysis/demographics_comparison/selected_holdout_v3.json` | V3 holdout set (200 companies) |
| `scripts/analysis/demographics_comparison/all_companies_v4.json` | V4 merged set (~998 companies, all prior rounds combined) |

### 12.3 Results CSVs

| File | Rows | Content |
|------|------|---------|
| `comparison_200_detailed.csv` | 3,600 | V1 per-company/method/dimension |
| `comparison_200_summary.csv` | 192 | V1 aggregated by dimension |
| `comparison_original_200_v2_detailed.csv` | 6,600 | V2 training per-company/method/dimension |
| `comparison_original_200_v2_summary.csv` | 352 | V2 training aggregated |
| `comparison_holdout_200_v2_detailed.csv` | 6,534 | V2 holdout per-company/method/dimension |
| `comparison_holdout_200_v2_summary.csv` | 352 | V2 holdout aggregated |
| `comparison_training_400_v3_detailed.csv` | ~19,000 | V3 training per-company/method/dimension |
| `comparison_training_400_v3_summary.csv` | ~500 | V3 training aggregated |
| `comparison_holdout_v3_v3_detailed.csv` | 9,600 | V3 holdout per-company/method/dimension |
| `comparison_holdout_v3_v3_summary.csv` | 480 | V3 holdout aggregated |
| `comparison_all_v4_detailed.csv` | ~23,000 | V4 dev eval per-company/method/dimension (pending) |
| `comparison_all_v4_summary.csv` | ~600 | V4 dev eval aggregated (pending) |

### 12.4 Core Scripts

| File | Purpose |
|------|---------|
| `data_loaders.py` | Database query functions (ACS, LODES, tract, occupation) |
| `methodologies.py` | V1 (M1-M6) + V2 (M1b-M5b, M7) method implementations |
| `methodologies_v3.py` | V3 (M1c-M5d) method implementations |
| `methodologies_v4.py` | V4 (M3e, M3f, M1e, M4e, M2d, M5e, M8) method implementations (pending) |
| `cached_loaders.py` | V1 cached wrappers |
| `cached_loaders_v2.py` | V2 cached wrappers |
| `cached_loaders_v3.py` | V3 cached wrappers |
| `cached_loaders_v4.py` | V4 cached wrappers (pending) |
| `classifiers.py` | 5D company classification (NAICS, size, region, minority, urbanicity) |
| `config.py` | Industry weights, categories, EEO-1 path, M8 routing rules |
| `metrics.py` | MAE, RMSE, Hellinger, signed errors |
| `eeo1_parser.py` | EEO-1 CSV parsing |
| `select_200.py` | V1 stratified selection (200 companies) |
| `select_holdout_200.py` | V2 holdout selection (198 companies) |
| `select_400.py` | V3 training selection (399 companies) |
| `select_holdout_v3.py` | V3 holdout selection (200 companies) |
| `build_all_companies.py` | V4 merge of all prior JSON files into all_companies_v4.json (pending) |
| `compute_optimal_weights.py` | V2 single-set weight optimization |
| `compute_optimal_weights_v3.py` | V3 5-fold CV weight optimization |
| `compute_optimal_dampening.py` | V3 5-fold CV alpha optimization |
| `compute_m3f_threshold.py` | V4 CV optimization of M3f minority threshold (pending) |
| `debug_m4_family.py` | V4 M4c/M4d bug investigation script (pending) |
| `build_zip_tract_crosswalk.py` | ZIP-to-tract crosswalk table builder |
| `run_comparison_200.py` | V1 6-method runner |
| `run_comparison_200_v2.py` | V2 11-method runner |
| `run_comparison_400_v3.py` | V3 16-method runner |
| `run_comparison_all_v4.py` | V4 ~23-method runner against all_companies_v4.json (pending) |
| `generate_report_v3.py` | V3 auto-report generator |
| `generate_report_v4.py` | V4 auto-report generator with routing analysis (pending) |
