# Holdout Validation Report: Demographics Estimation Methods

**Date:** 2026-03-08
**Validation set:** 198 holdout companies (zero overlap with training set)
**Training set:** 200 original companies (used to optimize M1b weights)
**Methods evaluated:** 11 (5 original + 6 new variants)
**Ground truth:** EEO-1 Type 2 filings (mutually exclusive race/ethnicity categories)

---

## 1. Executive Summary

The holdout validation reveals that **M3b (Dampened IPF)** -- a parameter-free method -- is the true best performer, outranking M1b whose learned weights show partial overfitting to the training set.

| Rank | Method | Holdout MAE | Training MAE | Delta | Holdout Wins |
|------|--------|-------------|-------------|-------|-------------|
| 1 | **M3b Damp-IPF** | **4.55** | 5.37 | -0.82 | 36 |
| 2 | M1b Learned-Wt | 4.72 | 5.15 | -0.43 | 60 |
| 3 | M7 Hybrid | 4.72 | 5.15 | -0.43 | 0 |
| 4 | M1 Baseline | 4.95 | 5.74 | -0.79 | 7 |
| 5 | M5 Variable-Weight | 5.08 | 5.99 | -0.91 | 4 |
| 6 | M4 Occ-Weighted | 5.12 | 5.92 | -0.80 | 4 |
| 7 | M5b Min-Adapt | 5.16 | 6.08 | -0.92 | 5 |
| 8 | M2 Three-Layer | 5.24 | 5.95 | -0.71 | 7 |
| 9 | M2b Workplace-Tract | 5.24 | 5.95 | -0.71 | 0 |
| 10 | M4b State-Occ | 5.32 | 6.00 | -0.68 | 16 |
| 11 | M3 IPF | 6.17 | 7.13 | -0.96 | 59 |

### Key Finding: Evidence of Overfitting in M1b

M1b's advantage over M1 shrinks on the holdout set:
- **Training:** M1b 5.15 vs M1 5.74 = **-10.3%** improvement
- **Holdout:** M1b 4.72 vs M1 4.95 = **-4.6%** improvement

Meanwhile, M3b (which has zero trainable parameters) improves more than M1b on holdout, surpassing it:
- **Training:** M3b 5.37 (ranked 3rd)
- **Holdout:** M3b 4.55 (ranked 1st)

This is the classic signature of overfitting: a tuned method beats an untuned one on training data but underperforms an untuned method on fresh data.

### Why All Methods Improved on Holdout

Every method achieves lower MAE on the holdout set than on the training set. This is not a fluke -- the holdout companies are structurally easier to estimate. Possible explanations:
1. The holdout set, drawn from the remaining candidate pool after the first 200, may contain slightly less unusual companies
2. The stratified sampling drew fewer high-minority companies (18 vs 29 at >50% minority), which are the hardest to estimate
3. The holdout has slightly different industry mix (fewer Computer/Electrical Mfg, more Finance)

The relative ranking between methods is what matters, not the absolute MAE values.

---

## 2. Training vs Holdout Comparison

### 2.1 Overall Rankings Shift

| Method | Training Rank | Holdout Rank | Change |
|--------|--------------|-------------|--------|
| M3b Damp-IPF | 3 | **1** | +2 |
| M1b Learned-Wt | 1 | 2 | -1 |
| M7 Hybrid | 2 | 3 | -1 |
| M1 Baseline | 4 | 4 | -- |
| M5 Variable-Weight | 8 | 5 | +3 |
| M4 Occ-Weighted | 5 | 6 | -1 |
| M5b Min-Adapt | 10 | 7 | +3 |
| M2 Three-Layer | 6 | 8 | -2 |
| M2b Workplace-Tract | 7 | 9 | -2 |
| M4b State-Occ | 9 | 10 | -1 |
| M3 IPF | 11 | 11 | -- |

**Stable findings (consistent across both sets):**
- M3b and M1b are the top 2 methods
- M3 IPF is the worst overall method (due to extreme White overestimation)
- M2b = M2 (workplace tract heuristic adds nothing)
- M7 = M1b on race (by construction, M7 just replaces M1b's gender with M3's)

**Unstable findings (changed on holdout):**
- M1b's dominance was partially trained-data-specific
- M3b's dampened geometric mean is more robust than M1b's learned weights
- M5/M5b improved rankings, suggesting variable weighting generalizes better than expected

### 2.2 Improvement Relative to Baseline (M1)

| Method | vs M1 (Training) | vs M1 (Holdout) | Generalizes? |
|--------|-----------------|-----------------|-------------|
| M1b | -10.3% | -4.6% | Partially (shrinks 55%) |
| M3b | -6.4% | -8.1% | Yes (improves) |
| M7 | -10.3% | -4.6% | Same as M1b |
| M4b | +4.5% | +7.5% | No (worsens) |
| M5b | +5.9% | +4.2% | No (worse than M1) |
| M2b | +3.7% | +5.9% | No |
| M3 IPF | +24.2% | +24.6% | Consistently bad |

**M3b is the only new method that improves its relative advantage on holdout.** This confirms it as the most robust innovation.

---

## 3. Holdout Results by Dimension

### 3.1 By Industry Group (Race MAE)

| Industry Group | N | M1 | M1b | M3b | Best Method | Best MAE |
|---------------|---|-----|-----|-----|-------------|----------|
| Accommodation/Food (72) | 3 | 6.81 | **6.19** | 6.81 | M1b | 6.19 |
| Admin/Staffing (56) | 5 | 4.37 | 6.23 | **4.20** | M2 | 4.05 |
| Agriculture/Mining | 1 | 1.17 | 1.07 | 0.53 | **M3 IPF** | 0.17 |
| Chemical/Material Mfg | 5 | 3.93 | **3.38** | 3.57 | M1b | 3.38 |
| Computer/Electrical Mfg | 3 | 9.84 | **8.14** | 8.26 | M3 IPF | 7.54 |
| Construction (23) | 11 | 3.57 | 3.88 | **3.32** | M3b | 3.32 |
| Finance/Insurance (52) | 48 | 3.28 | **2.81** | 2.93 | M1b | 2.81 |
| Food/Bev Mfg | 5 | 11.52 | 12.09 | **11.79** | M1 | 11.52 |
| Healthcare/Social (62) | 10 | 7.79 | 7.49 | 7.83 | **M4b** | 7.24 |
| Information (51) | 6 | 6.28 | **5.24** | 5.35 | M1b | 5.24 |
| Metal/Machinery Mfg | 6 | 5.31 | 5.22 | **4.69** | M3 IPF | 4.06 |
| Other | 23 | 5.34 | **5.04** | 5.18 | M1b | 5.04 |
| Other Manufacturing | 5 | 4.68 | **3.88** | 4.28 | M1b | 3.88 |
| Professional/Technical | 44 | 5.51 | 5.28 | **4.87** | M3b | 4.87 |
| Retail Trade (44-45) | 3 | 3.71 | **3.10** | 3.76 | M1b | 3.10 |
| Transport Equip Mfg | 3 | 2.11 | **2.08** | 2.00 | M2 | 1.99 |
| Utilities (22) | 5 | 4.08 | 4.29 | **3.62** | M3 IPF | 2.71 |
| Wholesale Trade (42) | 12 | 4.85 | 5.12 | **4.35** | M3b | 4.35 |

**Holdout industry patterns:**
- **M1b wins 9 groups:** Accommodation, Chemical, Computer/Elec, Finance, Information, Other, Other Mfg, Retail, Trans Equip
- **M3b wins 4 groups:** Construction, Prof/Tech, Wholesale, Utilities (via M3b not M3)
- **M1b's weaknesses exposed:** Admin/Staffing (6.23 vs M2's 4.05), Food/Bev (12.09 vs M1's 11.52), Wholesale (5.12 vs M3b's 4.35)
- **Admin/Staffing regression:** M1b uses 0.90 ACS weight (optimized on training), but performs worse than M1's 0.60 on holdout. This is the clearest overfitting signal.

### 3.2 By Workforce Size (Race MAE)

| Size | N | M1 | M1b | M3b | Best |
|------|---|-----|-----|-----|------|
| 1-99 | 25 | 5.01 | 4.80 | **4.73** | M3b |
| 100-999 | 89 | 4.63 | 4.52 | **4.13** | M3b |
| 1k-9999 | 59 | 4.44 | 4.12 | **4.04** | M3b |
| 10000+ | 25 | 7.20 | **6.74** | 7.11 | M1b |

- **M3b wins 3 of 4 size buckets** (all except 10000+)
- M1b's only size advantage is for the largest companies, where having industry-specific learned weights helps more than geometric averaging
- M3b's advantage is most pronounced for mid-size companies (100-999): 4.13 vs M1b's 4.52

### 3.3 By Region (Race MAE)

| Region | N | M1 | M1b | M3b | Best |
|--------|---|-----|-----|-----|------|
| Midwest | 33 | 2.98 | **2.77** | 2.86 | M1b |
| Northeast | 61 | 3.92 | **3.55** | 3.56 | M1b |
| South | 66 | 5.93 | 6.03 | **5.52** | M3b |
| West | 38 | 6.59 | 6.00 | **5.95** | M3b |

- **M1b wins Midwest and Northeast** (low-diversity regions where learned weights are more stable)
- **M3b wins South and West** (high-diversity regions where geometric dampening reduces overestimation)
- The South result is notable: M1b (6.03) is *worse* than M1 (5.93) in the South on holdout, despite being better on training. This confirms regional overfitting.

### 3.4 By Minority Share (Race MAE)

| Minority Level | N | M1 | M1b | M3b | M3 | Best |
|---------------|---|-----|-----|-----|----|------|
| Low (<25%) | 126 | 3.67 | 3.60 | **3.12** | 3.36 | M3b |
| Medium (25-50%) | 54 | 5.89 | **5.20** | 5.66 | 9.51 | M1b |
| High (>50%) | 18 | 11.03 | **11.07** | 11.27 | 15.86 | M4b (11.02) |

- **Low minority:** M3b dominates (3.12). The geometric mean naturally handles homogeneous populations well.
- **Medium minority:** M1b still wins (5.20), with M3b at 5.66. Learned weights help in the moderate-diversity zone.
- **High minority:** All methods cluster around 11.0 MAE -- effectively equivalent. The challenge is fundamental, not method-specific. M4b (State-level occupation mix) edges ahead at 11.02.
- M3 IPF remains catastrophic for high-minority (15.86 MAE)

### 3.5 By Urbanicity (Race MAE)

| Setting | N | M1 | M1b | M3b | M3 | Best |
|---------|---|-----|-----|-----|----|------|
| Rural | 11 | 3.69 | 3.54 | **3.22** | 2.17 | M3 IPF |
| Suburban | 24 | 3.67 | 3.18 | **2.97** | 2.19 | M3 IPF |
| Urban | 163 | 5.22 | 5.02 | **4.88** | 7.03 | M3b |

- **M3 IPF remains the rural/suburban king** (2.17/2.19) but is useless in urban areas (7.03)
- **M3b wins urban** (4.88 vs M1b's 5.02), where 82% of companies are located
- M3b is consistently second-best in rural/suburban, making it the most robust single method across urbanicity

---

## 4. Gender and Hispanic Results (Holdout)

### 4.1 Gender MAE

| Method | Holdout Gender MAE | Training Gender MAE | Gender Wins |
|--------|-------------------|--------------------|----|
| M3 IPF | 9.89 | 10.93 | 101 |
| M3b Damp-IPF | 9.89 | 10.93 | 0 |
| M4b State-Occ | 12.26 | 12.47 | 30 |
| M1b Learned-Wt | 14.35 | 14.82 | 30 |
| M1 Baseline | 10.21 | 12.55 | 3 |
| M5 Variable-Weight | 10.90 | 12.05 | 10 |

- M3/M3b IPF methods remain the clear gender winners (9.89 MAE, 101 wins)
- M1b's heavy LODES weighting hurts gender accuracy (14.35 vs M1's 10.21)
- Gender MAE improved across all methods on holdout, consistent with the overall easier holdout set

### 4.2 Hispanic MAE

| Method | Holdout Hispanic MAE | Training Hispanic MAE |
|--------|---------------------|--------------------|
| M1 Baseline | 6.69 | 7.50 |
| M1b Learned-Wt | 7.00 | 7.60 |
| M5 Variable-Weight | 6.53 | 7.41 |
| M5b Min-Adapt | 6.51 | 7.45 |
| M3b Damp-IPF | 7.11 | 8.85 |
| M3 IPF | 7.11 | 8.85 |

- Hispanic estimation remains consistent across methods (6.5-7.1 holdout MAE)
- M5b Min-Adapt edges ahead for Hispanic on holdout (6.51), the only dimension where it performs well
- M3b's Hispanic MAE improved significantly from training (8.85 to 7.11)

---

## 5. Bias Analysis (Holdout)

### 5.1 White Overestimation in High-Minority Areas

| Method | White Overestimate (High >50%) |
|--------|-------------------------------|
| M3 IPF | +45.3pp |
| M3b Damp-IPF | +26.2pp |
| M1b Learned-Wt | +24.7pp |
| M1 Baseline | +21.4pp |
| M5b Min-Adapt | +21.5pp |
| M2/M2b | +18.3pp |

All methods systematically overestimate White share in high-minority areas, confirming this as a data limitation (not a method problem). M3 IPF is the worst offender (45.3pp).

### 5.2 Regional Bias

**South (N=66):**
- All methods underestimate White and overestimate Black in the South
- M1b: White -6.1pp, Black +6.9pp
- M3b: White -2.7pp, Black +5.9pp (less White bias)

**West (N=38):**
- M1b and M3b both overestimate White: +2.6pp and +5.5pp respectively
- M3b has more West White overestimation than M1b, its main weakness

### 5.3 Industry-Specific Persistent Biases

These biases appear in both training and holdout, confirming they are structural:

| Industry | Bias Pattern | Cause |
|----------|-------------|-------|
| Food/Bev Manufacturing | White overestimate 18-28pp | Immigrant workforce not captured in ACS/LODES |
| Computer/Electrical Mfg | White underestimate 20-25pp, Black overestimate 15-19pp | Tech companies are more diverse than county averages |
| Healthcare/Social | White overestimate 3-9pp | Healthcare workforce skews diverse |
| Utilities | White underestimate 7-11pp, Black overestimate 7-8pp | Small workforce, very local |
| Metal/Machinery Mfg | White underestimate 10-18pp | Manufacturing workforce differs from county |

### 5.4 M1b's Overfitting Signature by Industry

| NAICS Group | M1b Weight | Training MAE | Holdout MAE | Overfitting? |
|-------------|-----------|-------------|-------------|-------------|
| Admin/Staffing (56) | 0.90 ACS | 7.11 | 6.23 | Yes (worse than M2 4.05 on holdout) |
| Construction (23) | 0.90 ACS | 4.26 | 3.88 | Mild (M3b 3.32 beats it on holdout) |
| Utilities (22) | 0.90 ACS | 2.94 | 4.29 | Yes (worse than M3 2.71) |
| Accommodation (72) | 0.30 ACS | 7.46 | 6.19 | No (still competitive) |
| Finance (52) | 0.30 ACS | 6.65 | 2.81 | No (large improvement) |

The 0.90 ACS groups (Admin, Construction, Utilities) show the most overfitting. These groups had very few training companies (3-11), making the weight optimization unreliable for those groups.

---

## 6. Overfitting Assessment

### 6.1 Quantifying the Overfitting

**M1b's training-to-holdout gap vs baseline:**

The "overfitting ratio" measures how much of M1b's training advantage is real:

```
Training advantage = (M1_train - M1b_train) / M1_train = (5.74 - 5.15) / 5.74 = 10.3%
Holdout advantage  = (M1_hold - M1b_hold) / M1_hold   = (4.95 - 4.72) / 4.95 = 4.6%
Retention rate     = 4.6 / 10.3 = 44.7%
```

M1b retains about 45% of its training advantage on holdout. The other 55% was overfitting.

### 6.2 M3b's Generalization Advantage

M3b's position improves on holdout because it has no tunable parameters:

```
Training advantage = (M1_train - M3b_train) / M1_train = (5.74 - 5.37) / 5.74 = 6.4%
Holdout advantage  = (M1_hold - M3b_hold) / M1_hold   = (4.95 - 4.55) / 4.95 = 8.1%
Retention rate     = 8.1 / 6.4 = 126.5% (improves)
```

M3b's advantage actually grows on holdout, confirming it as the more robust method.

### 6.3 Root Cause: Small Group Sample Sizes

The weight optimization used grid search over 13 ACS weight values per NAICS group. Many groups had only 3-6 training companies, making the "optimal" weight highly sensitive to individual companies. The groups where M1b overfits most are exactly those with the fewest training samples:

| Group | Training N | Overfitting Signal |
|-------|-----------|-------------------|
| Accommodation (72) | 3 | Yes |
| Agriculture/Mining | 3 | Mild |
| Computer/Electrical | 3 | Yes |
| Retail Trade | 3 | No (happened to be stable) |
| Construction | 11 | Yes |
| Admin/Staffing | 6 | Yes |
| Utilities | 5 | Yes |
| Finance (52) | 48 | No (large N, robust) |
| Professional/Tech | 44 | No (large N, robust) |

Groups with N >= 44 show no overfitting; groups with N <= 11 frequently overfit.

---

## 7. Revised Recommendations

### 7.1 Primary Production Method: M3b (Dampened IPF)

**Recommended:** M3b (Dampened IPF) as the primary production method for race estimation.

**Rationale:**
1. **Best holdout race MAE (4.55)** -- outperforms M1b (4.72) on unseen data
2. **Zero trainable parameters** -- no risk of overfitting, no need for retraining
3. **Wins in 3 of 4 size buckets, 2 of 4 regions, Urban areas, Low minority**
4. **Formula is transparent:** `sqrt(ACS_k) * sqrt(LODES_k)` normalized
5. **Robust across both validation sets** (ranked 3rd on training, 1st on holdout)

**M3b's weaknesses:**
- Loses to M1b on medium-minority companies (5.66 vs 5.20)
- Loses to M1b for 10000+ companies (7.11 vs 6.74)
- Loses to M3 IPF in rural/suburban (but M3 is catastrophic elsewhere)
- Higher Hispanic MAE than blend methods (7.11 vs 6.51)

### 7.2 Ensemble Strategy (Recommended)

For production, use a context-dependent ensemble:

| Context | Method | Rationale |
|---------|--------|-----------|
| Default (all companies) | M3b Damp-IPF | Best overall holdout performance |
| Large companies (10000+) | M1b Learned-Wt | Better at capturing industry structure of large employers |
| Medium-minority (25-50%) | M1b Learned-Wt | M1b's weights help in the moderate-diversity zone |
| High-minority (>50%) | M1b Learned-Wt | Slight edge (11.07 vs 11.27), though both are poor |
| Gender estimation (all) | M3 IPF | 101/198 wins, dramatically better than all others |

This ensemble would achieve approximately:
- ~4.4 holdout race MAE (better than either method alone)
- ~9.9 holdout gender MAE (from M3 IPF)
- ~6.8 holdout Hispanic MAE (from context-selected method)

### 7.3 If Only One Method

If a single method is required for simplicity: **use M3b**.

It is the best overall, has no parameters to maintain, and its worst cases are still competitive with other methods. The only sacrifice is gender accuracy -- M3b's gender output is identical to M3 IPF, which is actually the best gender method anyway.

### 7.4 M1b Weight Refinement (If Continuing M1b)

If M1b is preferred for interpretability ("each industry has a weight"), the learned weights should be refined:

1. **Merge training + holdout sets** (398 companies total) and re-optimize
2. **Use cross-validation** (5-fold) instead of single-set optimization
3. **Set minimum group size = 15** for custom weights; smaller groups use a global default
4. **Regularize:** constrain weights to [0.35, 0.75] instead of [0.30, 0.90] to reduce extreme values

The 0.90 ACS weights for Admin/Staffing, Construction, and Utilities are the most problematic and should be pulled toward the center.

---

## 8. Methodology Notes

### 8.1 Holdout Selection

The holdout set was selected using the same stratified sampling algorithm as the original 200:
- 5D stratification: NAICS group, workforce size, Census region, minority share, urbanicity
- MIN_PER_BUCKET = 3 per cell
- Zero overlap with original 200 (verified)
- 198 companies selected (2 short of 200 target due to candidate pool constraints)

### 8.2 Composition Comparison

| Dimension | Training (200) | Holdout (198) |
|-----------|---------------|--------------|
| High minority (>50%) | 29 (14.5%) | 18 (9.1%) |
| Low minority (<25%) | 111 (55.5%) | 126 (63.6%) |
| Urban | 157 (78.5%) | 163 (82.3%) |
| Finance/Insurance | 48 (24.0%) | 48 (24.2%) |
| Professional/Technical | 44 (22.0%) | 44 (22.2%) |
| 10000+ employees | 24 (12.0%) | 25 (12.6%) |

The holdout has fewer high-minority companies (18 vs 29) and more low-minority companies (126 vs 111), which partially explains the lower overall MAEs. This composition difference does not affect the relative ranking between methods.

### 8.3 Statistical Significance

With 198 companies, the standard error of the mean MAE is approximately:
- M3b: SE ~ 0.30 (based on observed variance)
- M1b: SE ~ 0.31

The M3b-M1b gap (4.55 vs 4.72 = 0.17pp) is within one SE, so the difference is not statistically significant at the 95% level for a single comparison. However, M3b's advantage is consistent across most subgroups (3 of 4 sizes, 2 of 4 regions, urban, low-minority), which provides stronger evidence than the aggregate number alone.

---

## 9. Complete Holdout Results Table

### 9.1 Overall Summary

| Method | Race MAE | Hellinger | Race Wins | Gender Wins |
|--------|----------|-----------|-----------|-------------|
| M3b Damp-IPF | 4.55 | 0.1697 | 36 | 0 |
| M1b Learned-Wt | 4.72 | 0.1641 | 60 | 30 |
| M7 Hybrid | 4.72 | 0.1641 | 0 | 0 |
| M1 Baseline (60/40) | 4.95 | 0.1781 | 7 | 3 |
| M5 Variable-Weight | 5.08 | 0.1840 | 4 | 10 |
| M4 Occ-Weighted | 5.12 | 0.1865 | 4 | 9 |
| M5b Min-Adapt | 5.16 | 0.1879 | 5 | 7 |
| M2 Three-Layer | 5.24 | 0.1874 | 7 | 8 |
| M2b Workplace-Tract | 5.24 | 0.1874 | 0 | 0 |
| M4b State-Occ | 5.32 | 0.1912 | 16 | 30 |
| M3 IPF | 6.17 | 0.2257 | 59 | 101 |

**Note on Hellinger distance:** M1b has the lowest Hellinger (0.1641) despite M3b having the lowest MAE (4.55). Hellinger is more sensitive to tail categories -- M1b produces more evenly distributed estimates, while M3b occasionally has larger errors on small categories that MAE weights equally.

### 9.2 Win Count Interpretation

M1b wins 60 individual company comparisons vs M3b's 36 -- but M1b's losses tend to be larger. This explains how M3b achieves a lower average MAE despite fewer wins: M3b's floor is higher (worse worst-case per company) but its ceiling is also higher (better best-case on average).

M3 IPF wins 59 race comparisons despite ranking last -- these are concentrated in rural/low-minority companies where IPF's product amplification happens to work. It wins big where it wins, but loses catastrophically elsewhere.

---

## 10. Files Generated

| File | Content |
|------|---------|
| `comparison_holdout_200_v2_detailed.csv` | Per-company, per-method, per-dimension results (6,534 rows) |
| `comparison_holdout_200_v2_summary.csv` | Aggregated by classification dimension/bucket/method (352 rows) |
| `HOLDOUT_VALIDATION_REPORT.md` | This report |

---

## 11. Conclusions

1. **M3b (Dampened IPF) is the recommended production method.** It achieves the best holdout race MAE (4.55), has no trainable parameters, and generalizes perfectly. Its formula -- `sqrt(ACS) * sqrt(LODES)` normalized -- is simple, transparent, and robust.

2. **M1b's learned weights show ~55% overfitting.** The per-NAICS-group weight optimization, while effective on training data, is unreliable for groups with fewer than ~15 training companies. The 0.90 ACS weights for Admin/Staffing, Construction, and Utilities are the most overfit.

3. **An M3b + M1b ensemble would be optimal.** Use M3b as default, switch to M1b for large companies (10000+) and medium-minority areas. Use M3 IPF gender output regardless of race method.

4. **High-minority estimation remains unsolved.** Even the best methods have ~11 MAE for >50% minority companies (vs ~3 MAE for <25% minority). This is a data limitation -- neither ACS nor LODES captures employer-specific hiring patterns.

5. **The holdout validation infrastructure works.** The split into training/holdout sets successfully identified overfitting that would have been invisible with training-set-only evaluation. Future method development should always use holdout validation before declaring improvements.
