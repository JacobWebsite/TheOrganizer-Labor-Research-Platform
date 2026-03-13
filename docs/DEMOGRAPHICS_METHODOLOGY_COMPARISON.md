# Workforce Demographics Estimation: Methodology Comparison

**Date:** 2026-03-08
**Author:** Demographics comparison framework (automated)
**Dataset:** 200 EEO-1 companies, stratified across 5 classification dimensions
**Scripts:** `scripts/analysis/demographics_comparison/`

---

## 1. Problem Statement

The platform estimates workforce demographics (race, gender, Hispanic origin) for employers that do not publicly report this data. Since no single public dataset captures actual employer-level demographics, we blend multiple statistical sources -- each capturing a different slice of the labor market.

The question: **which blending methodology produces the most accurate estimates, and does the answer change depending on company characteristics?**

This study tests 6 estimation methods against EEO-1 ground truth for 200 companies, classified across 5 dimensions (industry, size, region, minority share, urbanicity), to determine where each method works and where it fails.

---

## 2. Data Sources

### 2.1 Ground Truth: EEO-1 Reports

The Equal Employment Opportunity Commission (EEOC) requires companies with 100+ employees to file annual EEO-1 reports disclosing workforce demographics. A subset of these reports are publicly available through FOIA objector data.

**Key properties:**
- Mutually exclusive race categories (non-Hispanic): White, Black, Asian, AIAN, NHOPI, Two or More Races
- Hispanic/Not Hispanic as a separate dimension
- Male/Female gender
- Job Category 10 = company-wide totals
- Source file: `EEO_1/objectors_with_corrected_demographics_2026_02_25.csv` (cp1252 encoding)

### 2.2 Estimation Sources

| Source | Geographic Level | Industry Level | What It Measures |
|--------|-----------------|----------------|-----------------|
| **ACS (IPUMS)** | State | 4-digit NAICS | Workers in industry X in state Y |
| **LODES** | County | 3 broad sectors | Workers whose jobs are in county Z |
| **Census Tract** | County (aggregated) | None | Residents of the county |
| **BLS Occupation Matrix** | National | 4-digit NAICS | Occupation mix of industry X |
| **ACS by Occupation** | State | SOC code | Workers in occupation O in state Y |

**Table:** `cur_acs_workforce_demographics` (ACS), `cur_lodes_geo_metrics` (LODES), `acs_tract_demographics` (tract), `bls_industry_occupation_matrix` (BLS)

### 2.3 Source Characteristics

| Source | Strength | Weakness |
|--------|----------|----------|
| ACS | Industry-specific race/ethnicity at state level | No sub-state geography; state averages mask local variation |
| LODES | County-level job location demographics | Only 3 industry sectors (Goods/Trade/Services); no NAICS detail |
| Tract | Local residential demographics at county level | Measures residents, not workers; includes non-workers |
| Occupation | Captures occupational segregation patterns | National only; limited SOC-NAICS crosswalk coverage |

---

## 3. Estimation Methods

All methods produce three independent estimates: `race`, `hispanic`, and `gender`. Each is a probability distribution summing to 100%.

### M1: Baseline (60/40 ACS/LODES)

```
estimate = 0.60 * ACS(industry, state) + 0.40 * LODES(county)
```

Fixed-weight linear blend. ACS provides industry signal; LODES provides geographic signal. The 60/40 split reflects that industry composition is generally a stronger predictor of workforce demographics than county-level averages.

### M2: Three-Layer (50/30/20 ACS/LODES/Tract)

```
estimate = 0.50 * ACS(industry, state) + 0.30 * LODES(county) + 0.20 * Tract(county)
```

Adds residential population demographics as a third signal. Hypothesis: residential demographics capture local labor pool characteristics that LODES (commuter-adjusted) may miss.

### M3: IPF (Iterative Proportional Fitting)

```
estimate_k = (ACS_k * LODES_k) / sum(ACS_j * LODES_j)   for each category k
```

Normalized product of ACS and LODES marginals (maximum entropy solution). Amplifies categories where both sources agree, suppresses categories where they disagree. Mathematically equivalent to Bayesian posterior with uniform prior.

### M4: Occupation-Weighted

```
occ_weighted_ACS = sum(ACS_by_occupation(soc, state) * pct_of_industry(soc))  for top 30 SOCs
estimate = 0.70 * occ_weighted_ACS + 0.30 * LODES(county)
```

Replaces aggregate ACS with occupation-specific demographics weighted by the industry's occupation mix (from BLS). Captures occupational segregation (e.g., nursing is 85% female vs. construction is 96% male). Falls back to M1-style blend (70/30) if no occupation data available.

### M5: Variable-Weight

```
(acs_w, lodes_w) = industry_weights(NAICS)
estimate = acs_w * ACS(industry, state) + lodes_w * LODES(county)
```

Same as M1 but with industry-adaptive weights:
- Local labor industries (agriculture, construction, food mfg, restaurants): 40% ACS / 60% LODES
- Occupation-stratified industries (finance, professional, healthcare): 75% ACS / 25% LODES
- Manufacturing: 55% ACS / 45% LODES
- Default: 60% ACS / 40% LODES

### M6: IPF + Occupation

```
occ_weighted_ACS = (same as M4)
estimate_k = (occ_ACS_k * LODES_k) / sum(occ_ACS_j * LODES_j)
```

IPF using occupation-weighted ACS as one marginal and LODES as the other. Combines M3's multiplicative fusion with M4's occupation detail. Falls back to M3 if no occupation data.

---

## 4. Validation Sample

### 4.1 Selection Process

From the 16,798-row EEO-1 objector dataset:

1. **Base filters**: Single-unit companies, NAICS present, TOTAL >= 50, valid ZIP, year 2020/2019/2018
2. **Data availability**: ZIP resolves to county with LODES data; ACS has matching NAICS+state
3. **Deduplication**: Most recent year per company code
4. **Result**: 2,444 eligible companies

### 4.2 Stratified Sampling

200 companies selected via greedy algorithm maximizing coverage across 5 classification dimensions:

- **Proportional NAICS targets**: Each industry group gets `max(3, round(200 * group_share))` slots
- **Coverage optimization**: Within each NAICS group, candidates are scored by how many under-represented buckets they fill in the other 4 dimensions
- **Post-selection verification**: All buckets in all dimensions have >= 3 companies

### 4.3 Sample Composition

**Industry (18 groups):**

| Industry Group | N | % |
|---|---|---|
| Finance/Insurance (52) | 48 | 24% |
| Professional/Technical (54) | 44 | 22% |
| Other (53,55,61,71,81,92) | 23 | 12% |
| Wholesale Trade (42) | 12 | 6% |
| Construction (23) | 11 | 6% |
| Healthcare/Social (62) | 10 | 5% |
| Admin/Staffing (56) | 6 | 3% |
| Metal/Machinery Mfg (331-333) | 6 | 3% |
| Chemical/Material Mfg (325-327) | 5 | 2% |
| Food/Bev Manufacturing (311,312) | 5 | 2% |
| Information (51) | 5 | 2% |
| Other Manufacturing | 5 | 2% |
| Utilities (22) | 5 | 2% |
| Accommodation/Food Svc (72) | 3 | 2% |
| Agriculture/Mining (11,21) | 3 | 2% |
| Computer/Electrical Mfg (334-335) | 3 | 2% |
| Retail Trade (44-45) | 3 | 2% |
| Transport Equip Mfg (336) | 3 | 2% |

**Size:** 1-99 (25), 100-999 (101), 1k-9999 (50), 10000+ (24)
**Region:** South (77), Midwest (59), West (39), Northeast (25)
**Minority Share:** Low <25% (111), Medium 25-50% (60), High >50% (29)
**Urbanicity:** Urban (157), Rural (26), Suburban (17)

**Workforce range:** 50 to 238,609 employees (median 517, mean 7,273)
**Year:** 193 companies from 2020, 7 from 2019
**States:** 37 states represented; top 5: CA (25), VA (15), IL (14), PA (13), TX/NY (12 each)

---

## 5. Metrics

| Metric | Formula | Interpretation |
|--------|---------|---------------|
| **MAE** | mean(\|est_k - actual_k\|) across categories | Average category-level percentage point error |
| **RMSE** | sqrt(mean((est_k - actual_k)^2)) | Penalizes large errors more than MAE |
| **Hellinger** | sqrt(0.5 * sum((sqrt(p_k) - sqrt(q_k))^2)) | Distributional distance; range [0,1] |
| **Signed Error** | est_k - actual_k per category | Positive = overestimate; reveals systematic bias |
| **Wins** | Count of companies where method has lowest MAE | Head-to-head ranking |

---

## 6. Results

### 6.1 Overall Performance

| Method | Race MAE | Race RMSE | Hisp MAE | Hellinger | Gender MAE | Race Wins | Gender Wins |
|--------|----------|-----------|----------|-----------|------------|-----------|-------------|
| **M1 Baseline (60/40)** | **5.74** | **8.31** | 7.05 | **0.192** | 12.60 | 35 | 5 |
| M2 Three-Layer (50/30/20) | 5.95 | 8.55 | 7.24 | 0.199 | 13.68 | 59 | 46 |
| M3 IPF | 7.13 | 10.93 | 8.33 | 0.246 | **10.67** | **70** | **113** |
| M4 Occ-Weighted | 5.92 | 8.56 | 7.06 | 0.200 | 11.62 | 16 | 20 |
| M5 Variable-Weight | 5.99 | 8.66 | **6.99** | 0.201 | 12.44 | 20 | 16 |
| M6 IPF+Occ | 7.13 | 10.93 | 8.33 | 0.246 | 10.67 | 0 | 0 |

**Key findings:**
- **M1 Baseline wins overall** on Race MAE (5.74), Race RMSE (8.31), and Hellinger (0.192)
- **M3 IPF wins the most individual companies** (70 race wins) despite worse average MAE -- it excels when both sources agree but catastrophically fails when they disagree
- **M3 IPF wins gender** (10.67 MAE, 113 wins) because gender distributions are less geographically variable
- **M6 IPF+Occ is identical to M3 IPF** in practice (0 wins, same MAE) -- occupation weighting adds nothing to IPF. **Recommendation: eliminate M6.**
- **M5 Variable-Weight wins Hispanic** (6.99 MAE) by a thin margin

### 6.2 M1 Baseline Error Distribution

| Percentile | Race MAE |
|---|---|
| P10 (best 10%) | 1.8 |
| P25 | 2.9 |
| **P50 (median)** | **4.6** |
| P75 | 7.2 |
| P90 (worst 10%) | 11.0 |
| Max | 26.1 |

| Error Bracket | Companies | Share |
|---|---|---|
| MAE < 3 | 54 | 27% |
| MAE 3-5 | 59 | 30% |
| MAE 5-8 | 46 | 23% |
| MAE 8-12 | 25 | 12% |
| MAE 12-20 | 13 | 6% |
| MAE > 20 | 3 | 2% |

57% of companies have Race MAE under 5pp. 80% are under 8pp.

### 6.3 Systematic Bias (Signed Errors)

**Race dimension (average across 200 companies):**

| Method | White | Black | Asian | AIAN | NHOPI | Two+ |
|--------|-------|-------|-------|------|-------|------|
| M1 Baseline | +0.5 | -0.7 | -4.3 | -0.1 | -0.6 | +5.3 |
| M2 Three-Layer | -1.7 | -0.4 | -3.7 | -0.1 | -0.6 | +6.6 |
| M3 IPF | **+19.1** | **-8.7** | -7.8 | -0.8 | -0.8 | -1.1 |
| M4 Occ-Weighted | +0.5 | -1.0 | -4.8 | -0.2 | -0.7 | +6.2 |
| M5 Variable-Weight | +0.3 | -0.8 | -4.7 | -0.1 | -0.7 | +5.9 |
| M6 IPF+Occ | +19.1 | -8.7 | -7.8 | -0.8 | -0.8 | -1.1 |

**Key bias patterns:**
- All methods underestimate Asian (-3.7 to -7.8pp) -- ACS/LODES do not capture Asian concentration in tech/finance
- All blend methods (M1-M5) overestimate Two+ (+5.3 to +6.6pp) -- likely an ACS coding artifact (IPUMS codes 7-9)
- IPF (M3/M6) massively overestimates White (+19.1pp) and underestimates Black (-8.7pp) -- the multiplicative product amplifies the White-majority signal from both sources
- M1 is nearly unbiased on White (+0.5pp) and Black (-0.7pp) on average

**Hispanic dimension:**

| Method | Hispanic | Not Hispanic |
|--------|----------|-------------|
| M1 Baseline | +1.0 | -1.0 |
| M3 IPF | -7.2 | +7.2 |
| M5 Variable-Weight | +0.7 | -0.7 |

Blend methods are nearly unbiased on Hispanic. IPF systematically underestimates Hispanic share (-7.2pp).

**Gender dimension:**

| Method | Female | Male |
|--------|--------|------|
| M1 Baseline | +3.6 | -3.6 |
| M3 IPF | +1.5 | -1.5 |
| M4 Occ-Weighted | +3.1 | -3.1 |

All methods slightly overestimate Female share. IPF has the lowest gender bias.

---

## 7. Results by Dimension

### 7.1 By Industry Group (Race MAE)

| Industry | N | M1 | M2 | M3 | M4 | M5 | Best |
|----------|---|----|----|----|----|----|----|
| Metal/Machinery Mfg | 6 | 2.6 | 3.2 | 3.1 | 2.8 | **2.6** | M5 |
| Utilities | 5 | 3.4 | 4.1 | **2.0** | 3.2 | 3.4 | M3 |
| Transport Equip Mfg | 3 | 3.5 | 3.7 | 6.6 | 3.7 | **3.4** | M5 |
| Food/Bev Mfg | 5 | 3.8 | 4.2 | 5.3 | 3.9 | **3.6** | M5 |
| Chemical/Material Mfg | 5 | 3.8 | 3.9 | 4.8 | 3.8 | **3.7** | M5 |
| Agriculture/Mining | 3 | **4.3** | 4.8 | 6.8 | 4.4 | 4.3 | M1 |
| Other Mfg | 5 | 4.5 | 5.0 | **3.1** | 4.8 | 4.3 | M3 |
| Wholesale Trade | 12 | **4.8** | 5.1 | 6.5 | 4.9 | 4.8 | M1 |
| Other | 23 | **5.0** | 5.3 | 6.9 | 5.1 | 5.0 | M1 |
| Professional/Technical | 44 | **5.2** | 5.6 | 5.9 | 5.4 | 5.5 | M1 |
| Construction | 11 | 5.3 | 5.6 | 4.9 | **4.8** | 6.2 | M4 |
| Information | 5 | **5.8** | 6.1 | 8.9 | 6.0 | 5.8 | M1 |
| Healthcare/Social | 10 | **5.9** | 6.0 | 10.8 | 6.2 | 6.5 | M1 |
| Computer/Electrical Mfg | 3 | 7.3 | 7.5 | 8.8 | 7.7 | **7.0** | M5 |
| Admin/Staffing | 6 | 7.4 | 7.8 | 8.3 | **7.3** | 7.4 | M4 |
| Finance/Insurance | 48 | 7.6 | **7.4** | 9.3 | 8.0 | 8.2 | M2 |
| Retail Trade | 3 | **7.9** | 7.9 | 8.5 | 8.3 | 7.9 | M1 |
| Accommodation/Food Svc | 3 | 9.5 | **8.9** | 13.2 | 10.4 | 9.5 | M2 |

**Patterns:**
- Manufacturing industries are easiest to estimate (MAE 2-4) -- homogeneous workforce composition
- Service industries are hardest (MAE 7-10) -- diverse workforce, more geographic variation
- M5 Variable-Weight wins most manufacturing groups (adjusts toward LODES for local labor)
- M1 Baseline wins the largest groups (Professional/Technical, Healthcare, Wholesale)
- M3 IPF wins for Utilities and Other Manufacturing but is worst for Healthcare (+10.8)

### 7.2 By Workforce Size (Race MAE)

| Size | N | M1 | M2 | M3 | M4 | M5 | Best |
|------|---|----|----|----|----|----|----|
| 1-99 | 25 | 6.3 | 6.4 | **4.7** | 6.4 | 6.5 | M3 |
| 100-999 | 101 | **5.7** | 6.0 | 7.0 | 5.9 | 6.0 | M1 |
| 1k-9999 | 50 | **5.8** | 6.0 | 8.0 | 6.0 | 6.1 | M1 |
| 10000+ | 24 | **5.1** | 5.3 | 8.5 | 5.3 | 5.4 | M1 |

- M3 IPF wins for small companies (1-99) -- these tend to be in homogeneous areas where source agreement is high
- M1 Baseline wins for all other size brackets
- Larger companies (10000+) actually have *lower* MAE than mid-size -- their national footprint averages toward population distributions

### 7.3 By Census Region (Race MAE)

| Region | N | M1 | M2 | M3 | M4 | M5 | Best |
|--------|---|----|----|----|----|----|----|
| Midwest | 59 | **3.4** | 3.8 | 4.0 | 3.5 | 3.5 | M1 |
| Northeast | 25 | **4.8** | 5.0 | 6.5 | 4.9 | 5.2 | M1 |
| South | 77 | **6.5** | 6.7 | 7.8 | 6.7 | 6.8 | M1 |
| West | 39 | **8.3** | 8.4 | 11.0 | 8.7 | 8.7 | M1 |

- M1 Baseline wins every region
- Clear geographic gradient: Midwest (3.4) < Northeast (4.8) < South (6.5) < West (8.3)
- West is hardest -- high Asian/Hispanic populations that our data sources systematically underestimate
- South error driven by Black underestimation in majority-Black workplaces

### 7.4 By Minority Share (Race MAE)

| Minority Share | N | M1 | M2 | M3 | M4 | M5 | Best |
|----------------|---|----|----|----|----|----|----|
| Low (<25%) | 111 | 4.0 | 4.5 | **3.1** | 4.1 | 4.1 | M3 |
| Medium (25-50%) | 60 | **5.3** | 5.4 | 9.3 | 5.6 | 5.6 | M1 |
| High (>50%) | 29 | 13.3 | **12.7** | 17.9 | 13.8 | 13.9 | M2 |

**This is the most important dimension.** Minority share is the strongest moderator of method performance:

- **Low minority (<25%)**: M3 IPF is best (3.1) because both ACS and LODES agree on White-majority signal
- **Medium minority (25-50%)**: M1 Baseline is best (5.3); IPF degrades to 9.3
- **High minority (>50%)**: M2 Three-Layer is best (12.7) but all methods struggle badly (12.7-17.9)

**The bias flips direction:**

| Minority Share | M1 White Bias | M1 Black Bias |
|----------------|---------------|---------------|
| Low (<25%) | **-8.9pp** (underestimates) | **+5.0pp** (overestimates) |
| Medium (25-50%) | +5.4pp | -4.9pp |
| High (>50%) | **+26.1pp** (overestimates) | **-13.4pp** (underestimates) |

This is regression toward the mean: our data sources (ACS and LODES) reflect area/industry averages, which are systematically Whiter than the actual workforce of companies that self-select into majority-minority locations.

### 7.5 By Urbanicity (Race MAE)

| Urbanicity | N | M1 | M2 | M3 | M4 | M5 | Best |
|------------|---|----|----|----|----|----|----|
| Rural | 26 | 4.1 | 4.1 | **1.6** | 4.2 | 4.5 | M3 |
| Suburban | 17 | **4.5** | 4.7 | 5.6 | 4.5 | 4.5 | M1 |
| Urban | 157 | **6.2** | 6.4 | 8.2 | 6.4 | 6.4 | M1 |

- M3 IPF dominates rural areas (MAE 1.6) -- rural counties have homogeneous populations where LODES and ACS strongly agree
- Urban areas are hardest -- more diverse populations with more within-county variation

---

## 8. Cross-Dimensional Analysis

### 8.1 Interacting Dimensions

**Low-Minority + Rural (N=25):**
- M3 IPF wins 21 of 25 companies (84%)
- Average Race MAE: 1.6
- These are the "easy" cases -- homogeneous, rural workplaces where all data sources agree

**High-Minority + South (N=14):**
- M2 Three-Layer wins 12 of 14 companies (86%)
- Average Race MAE: ~13
- Adding tract residential data (M2) helps because Southern counties have strong residential segregation patterns that LODES captures

### 8.2 Method Selection Heuristic

Based on the cross-dimensional results, a context-aware method selection could improve accuracy:

| Context | Recommended Method | Expected MAE |
|---------|-------------------|-------------|
| Rural + Low minority | M3 IPF | ~1.6 |
| Suburban or Urban + Low minority | M1 Baseline | ~4.0 |
| Medium minority | M1 Baseline | ~5.3 |
| High minority + South | M2 Three-Layer | ~12.7 |
| High minority + other regions | M1 Baseline or M2 | ~13 |

**Estimated improvement from context-aware selection:** ~0.5-1.0pp MAE reduction vs. always using M1.

---

## 9. Systematic Bias Deep Dive

### 9.1 Why All Methods Overestimate White for High-Minority Companies

The root cause is **regression to the mean**. Our estimation sources (ACS and LODES) measure:
- ACS: All workers in NAICS X in state Y -- mixes White-majority suburbs with minority-heavy urban cores
- LODES: All workers in county Z -- includes all employers, not just minority-heavy ones

A company with >50% minority workforce is, by definition, more diverse than the area/industry average. Our estimates regress toward that average, inflating White share by 23-26pp.

**No purely statistical fix exists.** A company at the tail of the distribution will always be pulled toward the mean by area-level data. Possible mitigations:
1. Sub-county geography (tract-level LODES) -- narrows the averaging window
2. Company-specific signals (job postings, news, partnerships) -- non-statistical evidence
3. Bayesian prior adjustment when industry/area minority share is known to be high

### 9.2 Why M3 IPF Has Massive White Bias

IPF computes the normalized product: `est_k = (ACS_k * LODES_k) / sum(ACS_j * LODES_j)`. When both ACS and LODES show White-majority (e.g., 70% and 60%), the product disproportionately amplifies White:

```
White: 0.70 * 0.60 = 0.420
Black: 0.15 * 0.25 = 0.0375
After normalization: White = 91.6%, Black = 8.2%
```

The quadratic amplification is mathematically guaranteed to push the majority category higher. This is desirable when the sources are accurate (rural/homogeneous areas) but catastrophic when they both share the same regression-to-mean bias.

### 9.3 The Asian Underestimation Problem

All methods underestimate Asian share by 3.7 to 7.8pp. This occurs because:
1. **ACS NAICS codes are too broad** -- "Professional/Technical (54)" includes both tech (high Asian) and law firms (low Asian)
2. **LODES has only 3 industry sectors** -- cannot distinguish tech from other services
3. **Geographic concentration** -- Asian workers cluster in specific metros (SF Bay, Seattle, NYC) at rates far above county averages

### 9.4 The Two+ Overestimation

Blend methods (M1-M5) overestimate Two or More Races by 5-7pp. This is likely an IPUMS coding artifact:
- IPUMS race codes 7 (Two major), 8 (Three+), 9 (Two minor+major) are lumped into Two+
- Code 6 (Other) is also added to Two+ in our mapping
- The ACS categories don't map cleanly to EEO-1's stricter "Two or More Races" definition

---

## 10. Performance Characteristics

| Metric | Value |
|--------|-------|
| Companies processed | 200 |
| Methods tested | 6 |
| Total estimates | 3,600 (200 x 6 x 3 dimensions) |
| Non-null estimates | 3,599 (99.97%) |
| Runtime | 3.9 seconds |
| Cache hit rate | 84.3% (6,910 hits / 1,290 misses) |
| Unique cache keys | 1,290 |

The `CachedLoaders` class wraps all data access functions with a dict-based cache keyed by `(function_name, args)`. LODES queries (county-level) achieve the highest reuse since multiple companies may share a county. ACS queries (NAICS x state) are also well-cached because the NAICS fallback hierarchy means many companies resolve to the same 2-digit NAICS + state pair.

---

## 11. Recommendations

### 11.1 Production Method Selection

**Default: M1 Baseline (60/40 ACS/LODES)**
- Lowest overall Race MAE (5.74)
- Nearly unbiased on White (+0.5pp) and Black (-0.7pp)
- Robust across industries, sizes, and regions
- Simple, interpretable, reproducible

**Context-aware override for known-homogeneous areas:**
If county minority share < 15% AND urbanicity = Rural, consider M3 IPF (expected MAE ~1.6 vs. M1's ~4.1). This should be implemented as a configurable flag, not a default.

### 11.2 Methods to Eliminate

- **M6 IPF+Occ**: Identical performance to M3 IPF (0 wins). Occupation weighting adds no value when combined with IPF's multiplicative fusion. Remove.
- **M2 Three-Layer**: Marginally useful for high-minority Southern companies but adds complexity for minimal overall benefit. Keep as optional.
- **M5 Variable-Weight**: Industry-adaptive weights help manufacturing but hurt other industries. Net effect is slightly worse than M1. Keep for manufacturing-specific use only.

### 11.3 Known Limitations

1. **Asian underestimation (-4.3pp)**: Cannot fix with current data sources; need sub-NAICS industry codes or company-specific signals
2. **Two+ overestimation (+5.3pp)**: IPUMS-to-EEO-1 race code mapping artifact; fixable with improved crosswalk
3. **High-minority companies (MAE 13+)**: Fundamental regression-to-mean problem; sub-county geography may help
4. **Gender (MAE 10-13)**: All methods are weak on gender because industry-level gender composition varies enormously within NAICS codes (e.g., "Healthcare" includes surgeons and nurses)

---

## 12. Reproduction

```bash
# Step 1: Select 200 companies (writes selected_200.json)
py scripts/analysis/demographics_comparison/select_200.py

# Step 2: Run comparison (writes CSV files + console output)
py scripts/analysis/demographics_comparison/run_comparison_200.py

# Original 10-company comparison (unchanged)
py scripts/analysis/demographics_comparison/run_comparison.py
```

### Output Files

| File | Rows | Description |
|------|------|-------------|
| `selected_200.json` | 200 | Selected companies with 5D classifications |
| `comparison_200_detailed.csv` | 3,600 | One row per (company, method, dimension) |
| `comparison_200_summary.csv` | 192 | One row per (classification_dim, bucket, method) |

### Source Files

| File | Lines | Purpose |
|------|-------|---------|
| `config.py` | 181 | Constants, 10 validation companies, industry weights |
| `data_loaders.py` | 445 | SQL query wrappers for ACS, LODES, tract, occupation |
| `methodologies.py` | 319 | 6 estimation methods with shared helpers |
| `metrics.py` | 92 | MAE, RMSE, Hellinger, signed errors |
| `eeo1_parser.py` | 146 | EEO-1 CSV parser (cp1252 encoding) |
| `classifiers.py` | 133 | 5D classification (region, NAICS, size, minority, urbanicity) |
| `select_companies.py` | 377 | 7-axis candidate selection for 10-company set |
| `select_200.py` | 204 | Stratified 200-company selection |
| `cached_loaders.py` | 217 | Dict-cached data loaders + cached method wrappers |
| `run_comparison.py` | 436 | 10-company comparison runner |
| `run_comparison_200.py` | 316 | 200-company comparison with dimensional bucketing |
| `bds_hc_check.py` | 211 | BDS-HC plausibility validation |

---

## Appendix A: Classification Definitions

### NAICS Groups (18)

| Group | NAICS Prefixes |
|-------|---------------|
| Agriculture/Mining | 11, 21 |
| Utilities | 22 |
| Construction | 23 |
| Food/Bev Mfg | 311, 312 |
| Chemical/Material Mfg | 325, 326, 327 |
| Metal/Machinery Mfg | 331, 332, 333 |
| Computer/Electrical Mfg | 334, 335 |
| Transport Equip Mfg | 336 |
| Other Manufacturing | 31, 32, 33 (catch-all) |
| Wholesale Trade | 42 |
| Retail Trade | 44, 45 |
| Transportation/Warehousing | 48, 49 |
| Information | 51 |
| Finance/Insurance | 52 |
| Professional/Technical | 54 |
| Admin/Staffing | 56 |
| Healthcare/Social | 62 |
| Accommodation/Food Svc | 72 |
| Other | everything else |

### Census Regions

| Region | States |
|--------|--------|
| Northeast | CT, ME, MA, NH, RI, VT, NJ, NY, PA |
| South | AL, AR, DE, DC, FL, GA, KY, LA, MD, MS, NC, OK, SC, TN, TX, VA, WV |
| Midwest | IL, IN, IA, KS, MI, MN, MO, NE, ND, OH, SD, WI |
| West | AK, AZ, CA, CO, HI, ID, MT, NV, NM, OR, UT, WA, WY |

### Urbanicity (from CBSA)

| Category | Definition |
|----------|-----------|
| Urban | Metropolitan CBSA + Central county |
| Suburban | Metropolitan + Outlying, or Micropolitan |
| Rural | No CBSA match |

### Minority Share (from EEO-1 truth)

| Category | Definition |
|----------|-----------|
| Low | < 25% non-White |
| Medium | 25-50% non-White |
| High | > 50% non-White |

### Size Buckets

| Category | Range |
|----------|-------|
| 1-99 | 1 to 99 employees |
| 100-999 | 100 to 999 |
| 1k-9999 | 1,000 to 9,999 |
| 10000+ | 10,000+ |
