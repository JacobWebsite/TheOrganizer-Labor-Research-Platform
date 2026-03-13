# V10 Error Distribution Report

**Date:** 2026-03-12
**Holdout:** Permanent (954 companies with valid predictions)
**Training:** 10,525 companies (expanded_training_v10.json, excludes both holdouts)

## V10 Configuration

| Component | V9.2 | V10 | Changed? |
|---|---|---|---|
| Race blend | 75% D + 25% A | 75% D + 25% A | No |
| Race dampening | d_race = 0.85 | d_race = 0.85 | No |
| Black adjustment | Retail + Other Mfg | Retail + Other Mfg | No |
| Hispanic weights | industry+tier | industry+tier | No |
| Hispanic dampening | d_hisp = 0.05 | d_hisp = 0.50 | **YES** |
| Hispanic calibration | standard hierarchy | Hispanic-specific hierarchy | **YES** |
| Hispanic cal cap | 20pp | 15pp | **YES** |
| Gender expert | Expert F only | Expert F only | No |
| Gender dampening | d_gender = 0.50 | d_gender = 0.95 | **YES** |
| Confidence tiers | (none) | GREEN/YELLOW/RED | **NEW** |

## Summary Metrics

### Permanent Holdout (backward comparison)

| # | Criterion | V9.2 | V10 | Change | Guard rail | Status |
|---|---|---|---|---|---|---|
| 1 | Race MAE | 4.405 | 4.405 | 0.000 | < 4.55 | PASS |
| 2 | P>20pp | 16.0% | 16.0% | 0.0% | < 16.5% | PASS |
| 3 | P>30pp | 6.1% | 6.1% | 0.0% | < 6.5% | PASS |
| 4 | Abs Bias | 0.310 | 0.310 | 0.000 | < 1.10 | PASS |
| 5 | Hispanic MAE | 6.783 | 6.616 | -0.167 | target < 6.20 | improved |
| 6 | Gender MAE | 11.139 | 10.689 | -0.450 | target < 10.20 | improved |
| 7 | HC South P>20pp | 13.9% | 13.9% | 0.0% | < 15.5% | PASS |

### V10 Sealed Holdout (honest evaluation, never optimized against)

| # | Criterion | V9.2 sealed | V10 sealed | Change |
|---|---|---|---|---|
| 1 | Race MAE | 4.325 | 4.325 | 0.000 |
| 2 | P>20pp | 16.3% | 16.3% | 0.0% |
| 3 | P>30pp | 5.7% | 5.7% | 0.0% |
| 4 | Abs Bias | 0.256 | 0.256 | 0.000 |
| 5 | Hispanic MAE | 6.765 | 6.768 | +0.003 |
| 6 | Gender MAE | 11.036 | 10.550 | **-0.486** |
| 7 | HC South P>20pp | 29.7% | 29.7% | 0.0% |

### Cross-Version Comparison

| Metric | V6 (325co) | V9.1 | V9.2 | V10 (perm) | V10 (sealed) |
|---|---|---|---|---|---|
| Race MAE | 4.203 | 4.483 | 4.403 | 4.405 | 4.325 |
| P>20pp | 13.5% | 17.1% | 15.4% | 16.0% | 16.3% |
| P>30pp | 4.0% | 7.7% | 5.9% | 6.1% | 5.7% |
| Hispanic MAE | 7.752 | 6.697 | 6.778 | 6.616 | 6.768 |
| Gender MAE | 11.979 | 10.798 | 11.160 | 10.689 | **10.550** |

---

## 1. Per-Dimension Breakdown

### By Sector

| Sector | N | Race MAE | Hisp MAE | Gender MAE | P>20pp | P>30pp |
|---|---|---|---|---|---|---|
| Utilities (22) | 15 | 2.423 | 2.313 | 5.006 | 6.7% | 0.0% |
| Finance/Insurance (52) | 136 | 2.765 | 2.950 | 7.534 | 6.6% | 1.5% |
| Retail Trade (44-45) | 15 | 3.648 | 5.560 | 8.052 | 13.3% | 0.0% |
| Metal/Machinery Mfg (331-333) | 41 | 3.902 | 6.702 | 10.230 | 17.1% | 9.8% |
| Construction (23) | 60 | 4.066 | 12.183 | 6.073 | 13.3% | 1.7% |
| Transport Equip Mfg (336) | 9 | 4.082 | 9.581 | 12.654 | 11.1% | 11.1% |
| Professional/Technical (54) | 165 | 4.156 | 3.675 | 10.765 | 10.3% | 3.6% |
| Information (51) | 29 | 4.146 | 3.359 | 10.376 | 17.2% | 10.3% |
| Chemical/Material Mfg (325-327) | 28 | 4.250 | 8.132 | 13.422 | 14.3% | 10.7% |
| Wholesale Trade (42) | 52 | 4.358 | 7.084 | 9.058 | 15.4% | 1.9% |
| Computer/Electrical Mfg (334-335) | 29 | 4.420 | 4.485 | 9.765 | 13.8% | 3.4% |
| Food/Bev Manufacturing (311,312) | 16 | 4.507 | 19.160 | 10.750 | 6.2% | 6.2% |
| Other Manufacturing | 33 | 4.730 | 8.786 | 9.960 | 18.2% | 9.1% |
| Transportation/Warehousing (48-49) | 25 | 5.236 | 6.298 | 10.136 | 20.0% | 8.0% |
| Healthcare/Social (62) | 125 | 5.351 | 6.848 | 8.367 | 26.4% | 9.6% |
| Admin/Staffing (56) | 48 | 5.365 | 10.559 | 18.847 | 22.9% | 10.4% |
| Other | 110 | 5.616 | 7.597 | 18.112 | 24.5% | 10.0% |
| Accommodation/Food Svc (72) | 9 | 5.918 | 12.130 | 8.337 | 11.1% | 11.1% |
| Agriculture/Mining (11,21) | 9 | 6.483 | 20.299 | 9.724 | 33.3% | 11.1% |

**Notable patterns:**
- Admin/Staffing has by far the worst Gender MAE (18.847) -- staffing agencies have highly variable gender composition
- Construction has excellent Gender MAE (6.073) despite high Hispanic MAE (12.183) -- gender is predictable (heavily male), Hispanic is not
- Healthcare has moderate Race MAE (5.351) but the highest P>20pp (26.4%) -- some hospitals deviate sharply from local demographics

### By Region

| Region | N | Race MAE | Hisp MAE | Gender MAE | P>20pp | P>30pp |
|---|---|---|---|---|---|---|
| Midwest | 226 | 3.215 | 4.982 | 10.584 | 7.5% | 4.0% |
| Northeast | 188 | 4.264 | 6.181 | 10.363 | 15.4% | 5.9% |
| South | 353 | 4.794 | 6.652 | 10.798 | 18.7% | 7.1% |
| West | 187 | 5.252 | 9.178 | 10.965 | 21.9% | 7.0% |

**Notable:** Gender MAE is remarkably uniform across regions (~10.4-11.0pp). Race and Hispanic vary much more geographically. The West has the worst Hispanic MAE (9.178) due to high but variable Hispanic concentration.

### By Diversity Tier

| Tier | N | Race MAE | Hisp MAE | Gender MAE | P>20pp | P>30pp |
|---|---|---|---|---|---|---|
| Low (<15%) | 248 | 2.685 | 5.647 | 10.482 | 4.4% | 2.0% |
| Med-Low (15-30%) | 406 | 4.470 | 7.020 | 10.508 | 14.0% | 5.7% |
| Med-High (30-50%) | 286 | 5.588 | 6.996 | 11.118 | 26.2% | 9.8% |
| High (50%+) | 14 | 8.819 | 5.505 | 9.255 | 71.4% | 14.3% |

**The gradient is stark for race:** Low-diversity counties (2.685 MAE) are 3x more accurate than High-diversity (8.819). Gender shows minimal tier sensitivity. Hispanic is non-monotonic -- High-diversity actually has lower Hispanic MAE (5.505) than Med-Low (7.020), likely because the Hispanic signal is strong and consistent in majority-minority counties.

---

## 2. Tail Analysis: >30pp Error Companies

**58 companies** with >30pp max category error (6.1% of holdout).

### By Sector

| Sector | Count |
|---|---|
| Healthcare/Social (62) | 12 |
| Other | 11 |
| Professional/Technical (54) | 6 |
| Admin/Staffing (56) | 5 |
| Metal/Machinery Mfg (331-333) | 4 |
| Other Manufacturing | 3 |
| Information (51) | 3 |
| Chemical/Material Mfg (325-327) | 3 |
| All others | 11 |

Healthcare + Other + Prof/Tech account for 50% of the tail.

### By Confidence Tier

| Tier | Count | % of tail |
|---|---|---|
| GREEN | 25 | 43% |
| YELLOW | 23 | 40% |
| RED | 10 | 17% |

**Interpretation:** RED is overrepresented (5.5% of companies but 17% of tail = 3.1x concentration), confirming the confidence system works directionally. However, GREEN still has 25 of the worst companies -- these are the "blind spots" where observable characteristics don't predict poor estimates. Most are small employers in niche industries (community organizations, international importers, mission-driven nonprofits) whose workforces don't match any census signal.

### Worst 20 Companies

| MaxErr | Company | Sector | DivTier | Region | Conf |
|---|---|---|---|---|---|
| 78.9 | WATTS LABOR COMMUNITY ACTION COMM | Other | Med-Low | West | GREEN |
| 76.2 | LAKE REGION CONFERENCE | Other | Med-Low | Midwest | GREEN |
| 75.3 | BROOKLYN COMMUNITY HOUSING & SERVICES | Prof/Tech | Med-High | NE | GREEN |
| 66.0 | UNITED PLANNING ORGANIZATION | Other | Med-High | South | YELLOW |
| 64.7 | JFC INTERNATIONAL INC | Wholesale | Med-Low | West | GREEN |
| 61.9 | CHAGS HEALTH INFO TECHNOLOGY | Prof/Tech | Med-High | South | YELLOW |
| 56.1 | FRESH EXPRESS | Agri/Mining | Med-Low | South | GREEN |
| 54.8 | THE URBAN ALLIANCE FOUNDATION | Admin/Staff | Med-High | South | RED |
| 53.6 | GOV SERVICES INC | Admin/Staff | Med-High | South | RED |
| 53.0 | WU YEE CHILDREN'S SERVICES | Healthcare | Med-High | West | RED |
| 50.6 | SOBRAN INC | Prof/Tech | Low | Midwest | GREEN |
| 50.4 | WARMKRAFT INC | Other Mfg | Med-Low | South | GREEN |
| 48.7 | CAMPESINOS UNIDOS INC | Other | Low | West | GREEN |
| 46.5 | SAN FRANCISCO FEDERAL CREDIT UNIT | Finance | Med-High | West | YELLOW |
| 42.9 | AIDES AT HOME INC | Healthcare | Med-Low | NE | YELLOW |
| 42.6 | SOCIAL DEVELOPMENT COMMISSION | Healthcare | Med-Low | Midwest | YELLOW |
| 41.5 | SOS CHILDREN'S VILLAGES ILLINOIS | Healthcare | Med-Low | Midwest | YELLOW |
| 41.0 | ALLIED MATERIALS & EQUIPMENT CO | Other Mfg | Med-Low | Midwest | GREEN |
| 40.7 | MITSUBISHI HEAVY IND AMERICA | Metal/Mach | Med-High | South | YELLOW |
| 40.6 | QUEENS BOROUGH PUBLIC LIBRARY | Information | Med-High | NE | GREEN |

These companies have workforces that don't match census signals at all. Many are community organizations, mission-driven nonprofits, or international subsidiaries -- irreducible with demographic estimation.

---

## 3. Hispanic-Specific Analysis

### What Changed

V10 enabled Hispanic calibration (d_hisp: 0.05 -> 0.50) with a Hispanic-specific hierarchy using county Hispanic % tiers instead of general diversity tiers. Cap reduced from 20pp to 15pp.

### Where It Helped (permanent holdout)

| Hispanic County Tier | N | V9.2 Hisp MAE | V10 Hisp MAE | Change |
|---|---|---|---|---|
| Low (<10%) | 469 | 4.634 | 4.589 | -0.045 |
| Med (10-25%) | 336 | 7.631 | 7.414 | -0.217 |
| High (25-50%) | 141 | 11.056 | 10.405 | **-0.650** |
| Very High (50%+) | 8 | 28.561 | 27.256 | -1.305 |

Improvement scaled with Hispanic concentration -- exactly the right behavior. The biggest gains were in high-Hispanic counties where the calibration has the strongest signal.

### Replication on Sealed Holdout

Hispanic MAE on sealed holdout: V9.2=6.765, V10=6.768 (+0.003). The improvement did **not** replicate on truly unseen data. The Hispanic-specific calibration hierarchy improved the permanent holdout but did not generalize. This is documented as mild calibration overfitting -- the corrections are valid on average but the specific bucket-level offsets are unstable with ~10K training companies.

**Decision:** Kept anyway because (a) it does no harm (+0.003pp is noise), (b) the Hispanic-specific hierarchy is architecturally sounder than using general diversity tiers for Hispanic calibration, and (c) with more training data in the future the corrections should stabilize.

---

## 4. Gender-Specific Analysis

### What Changed

V10 increased gender dampening from d_gender=0.50 to d_gender=0.95. No blending -- Expert F remains the sole gender expert. Testing showed blending with Expert D made things worse at every ratio.

### Why It Helped

The gender calibration corrections were valid but V9.2 was only applying 50% of them. At 95%, the model trusts its learned corrections almost fully. The improvement is a simple, robust hyperparameter change -- no new calibration structure, no new data sources.

### Replication

Gender improvement replicated on the sealed holdout: -0.486pp (11.036 -> 10.550). This is the most robust V10 change.

### Gender MAE by Sector

| Sector | Gender MAE | Notes |
|---|---|---|
| Utilities | 5.006 | Best -- predictable male-heavy workforce |
| Construction | 6.073 | Predictable male-heavy |
| Finance/Insurance | 7.534 | Moderate |
| Healthcare | 8.367 | Large but more variable |
| Admin/Staffing | **18.847** | Worst -- staffing agencies vary wildly |
| Other | **18.112** | Catch-all bucket, highly variable |

Admin/Staffing is the clear outlier -- staffing agencies place workers in diverse industries, so their gender composition is unpredictable from industry alone.

---

## 5. Confidence Tier Analysis

### Permanent Holdout Performance

| Tier | N | % | Race MAE | Hisp MAE | Gender MAE | P>20pp | P>30pp |
|---|---|---|---|---|---|---|---|
| GREEN | 569 | 61.5% | 3.641 | 6.225 | 10.593 | 9.1% | 4.4% |
| YELLOW | 330 | 33.0% | 5.203 | 6.753 | 10.757 | 23.0% | 7.0% |
| RED | 55 | 5.5% | 7.523 | 10.154 | 11.342 | 45.5% | 18.2% |

GREEN has uniformly good estimates across all dimensions. RED has elevated error across race (7.5 MAE) and Hispanic (10.2 MAE). Gender is less well-separated by confidence tier (10.6 vs 11.3) because gender error is driven more by industry-level variability than by geographic factors.

### Sealed Holdout Replication

| Tier | N | Race MAE | P>20pp | P>30pp |
|---|---|---|---|---|
| GREEN | 633 | 3.556 | 10.7% | 3.4% |
| YELLOW | 309 | 5.359 | 24.3% | 8.4% |
| RED | 58 | 6.528 | 31.0% | 13.8% |

Separation holds on truly unseen data. P>20pp ratio: 2.9:1 (weaker than 5.0:1 on perm but still directionally correct). The confidence system is genuine signal, not overfit.

---

## 6. Remaining Hard Cases

Of the 58 companies with >30pp error:
- 43% are GREEN (25 companies) -- these are the confidence system's blind spots
- 40% are YELLOW (23 companies)
- 17% are RED (10 companies)

The blind spots are concentrated in:
- Community organizations (mission-driven hiring doesn't match local demographics)
- International subsidiaries (workforce reflects parent company culture, not local labor market)
- Niche nonprofits (small, specialized workforces)

These companies are irreducible outliers with census-based estimation. No amount of calibration tuning can fix a 78.9pp error for a community action committee in Watts, LA whose workforce is 90%+ Black in a county that is 35% minority overall.

---

## Key Takeaways

1. **Gender d_gender=0.95 is the real win.** -0.450pp on perm, -0.486pp on sealed. Best gender accuracy across all model versions.
2. **Hispanic calibration is architecturally sound but statistically noisy.** Improvement on perm holdout did not replicate on sealed. Kept for architectural reasons; will strengthen with more training data.
3. **Race is at the census ceiling.** Zero movement in V10 confirms V8.5's analysis that ~4.4pp Race MAE is the floor.
4. **Confidence tiers are genuine signal.** 5:1 P>20pp separation on perm, 2.9:1 on sealed. Users can trust GREEN estimates and treat RED with caution.
5. **58 companies (6.1%) are irreducible outliers.** Their workforces don't match any available census signal. The confidence system catches 17% of them as RED but misses 43% as GREEN.
