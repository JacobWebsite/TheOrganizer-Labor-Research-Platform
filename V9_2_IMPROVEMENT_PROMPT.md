# V9.2: Improving V9.1 — Training Expansion + County Diversity Calibration + Adaptive Black Estimator

**Date:** 2026-03-11  
**Starting point:** V9.1 hybrid architecture (D race + Industry+Adaptive Hispanic + F gender)  
**V9.1 result:** 5/7 pass (Race MAE 4.483, P>20pp 17.1%, P>30pp 7.7%)  
**Goal:** Pass 7/7. Specifically: push P>20pp below 16.0% and P>30pp below 6.0%.

**Key files:**
- V9.1 pipeline: `scripts/analysis/demographics_comparison/run_v9_1_partial_lock.py`
- Expert combos: `scripts/analysis/demographics_comparison/test_expert_combos.py`
- Dampening grid: `scripts/analysis/demographics_comparison/test_dampening_grid.py`
- Tail analysis: `scripts/analysis/demographics_comparison/analyze_tails.py`
- Expert predictions checkpoint from: `run_v9_best_of_ipf.py`
- EEO-1 ground truth: 16,798 federal contractors
- Permanent holdout: `selected_permanent_holdout_1000.json` (1,000 companies, NEVER changes)

Read CLAUDE.md and PROJECT_STATE.md for current server layout, database credentials, and file locations.

---

## Background (read this before coding)

V9.1 gets 5/7 — it passes Race MAE, Abs Bias, Hispanic MAE, Gender MAE, and Healthcare South P>20pp. It fails ONLY on the two tail metrics:

- P>20pp: 17.1% (need < 16.0%) — roughly 171 companies. Need to "fix" ~11 to pass.
- P>30pp: 7.7% (need < 6.0%) — roughly 77 companies. Need to fix ~17 to pass.

The tail analysis shows:
- **86% of severe errors (>30pp) are White overestimation** — the model predicts too White, the real workforce has more Black/Asian/Hispanic workers.
- **County diversity is the #1 predictor of error.** Companies in 50%+ minority counties: 78.6% P>20pp rate. Companies in <15% minority counties: 5.2% P>20pp rate.
- **Worst sectors:** Accommodation/Food (14.6% P>30pp), Healthcare (11.4%), Manufacturing (9.0%).

V9.1 only used **2,702 training companies** even though 16,798 are available. The rest went unused. This means calibration buckets were thin and grid-searched weights were trained on too little data.

We are making three changes, tested one at a time so we know what helps:

1. **Expand training to ~15,000 companies** (more data for calibration and weight tuning)
2. **Add county diversity tier to calibration** (target the 50%+ minority county companies directly)
3. **Build an adaptive Black estimator** (same approach that worked for Hispanic — grid-searched per-industry signal blending)

---

## Data Split

| Set | Size | Purpose |
|-----|------|---------|
| **Training** | ~15,000 | Train calibration, grid-search weights, pick expert winners |
| **Dev holdout** | ~800 | Quick iteration and sanity checks during development |
| **Permanent holdout** | ~1,000 | Final scorecard. Use `selected_permanent_holdout_1000.json`. NEVER changes. |

**Setup:**
1. Load the permanent holdout from `selected_permanent_holdout_1000.json`.
2. From the remaining ~15,798 companies, randomly select ~15,000 as training (seed `20260311v92`). The leftover ~800 become the dev holdout.
3. Save dev holdout IDs to `dev_holdout_v92.json`.

**Checkpoint: Confirm split sizes. Verify permanent holdout matches the exact same companies as V9.1. Show overlap check — zero companies should appear in more than one set.**

---

## Step 1: Re-Run V9.1 Exactly on the New Training Split (Baseline)

Before changing anything, re-run the V9.1 architecture (Expert D for race, Industry+Adaptive Hispanic, Expert F for gender, 3D calibration with d=0.8/0.3/1.0) but trained on the larger 15,000-company training set.

This tells us: **how much does more training data alone improve things?**

Use the same code from `run_v9_1_partial_lock.py` and `test_dampening_grid.py`, but with the new larger training split.

Steps:
1. Run all experts (A, B, D, E, F, G, V6-Full) on all 15,000 training companies
2. Re-run the Hispanic grid search on the larger training set (same grid ranges as V9.1)
3. Re-train calibration buckets (region × industry) on the larger training set
4. Re-run the dampening grid search (same grid as V9.1: race [0.3-0.8], hisp [0.3-0.7], gender [0.0-1.0])
5. Apply the best configuration to the permanent holdout

**Report — Baseline V9.1 retrained on 15K:**

```
| Criterion         | V9.1 (2.7K train) | V9.1 (15K train) | Target  |
|--------------------|-------------------|-------------------|---------|
| Race MAE           | 4.483             |                   | < 4.50  |
| P>20pp             | 17.1%             |                   | < 16.0% |
| P>30pp             | 7.7%              |                   | < 6.0%  |
| Abs Bias           | 0.330             |                   | < 1.10  |
| Hispanic MAE       | 6.697             |                   | < 8.00  |
| Gender MAE         | 10.798            |                   | < 12.00 |
| HC South P>20pp    | 13.9%             |                   | < 15.0% |
| Criteria pass      | 5/7               |                   |         |
```

Also show:
- How many calibration buckets now have ≥ 20 companies (vs V9.1's count)
- The 5 calibration buckets that gained the most companies
- Whether the optimal dampening values changed

**Checkpoint: Show results. If this alone passes 7/7, we're done — skip to final validation. If not, proceed to Step 2.**

---

## Step 2: Add County Diversity Tier to Calibration

The single biggest improvement opportunity. V9.1's calibration uses region × industry buckets. But a hospital in a 55% minority county in the South needs a very different correction than a hospital in a 12% minority county in the South. Right now they share the same bucket.

### 2A: Define county diversity tiers

Use the same tiers from V9.1's tail analysis:

| Tier | County Minority % | V9.1 P>20pp in this tier |
|------|-------------------|--------------------------|
| Low | < 15% | 5.2% |
| Medium-Low | 15-30% | 13.8% |
| Medium-High | 30-50% | 21.4% |
| High | 50%+ | 78.6% |

For each company, compute county minority percentage from ACS county demographics (already available in the pipeline). Assign to a tier.

### 2B: Expand calibration hierarchy

The new calibration lookup order (most specific → least specific):

```
1. diversity_tier × region × industry  (e.g., "High × South × Healthcare")
2. diversity_tier × industry           (e.g., "High × Healthcare")  
3. region × industry                   (e.g., "South × Healthcare" — V9.1 behavior)
4. industry                            (e.g., "Healthcare")
5. global
```

**Minimum bucket size: 20 companies.** If a bucket has fewer than 20 training companies, fall through to the next level.

With 15,000 training companies, the critical "High × South × Healthcare" bucket should have meaningful data. Check how many companies fall in each bucket.

### 2C: Train and evaluate

1. Compute calibration offsets for ALL bucket levels on the 15,000 training set
2. For each holdout company, apply the most specific available bucket
3. Re-run the dampening grid search (the optimal dampening might change with finer buckets)

**Report — V9.1 + county diversity calibration:**

```
| Criterion         | V9.1 (15K) | + Diversity Cal | Target  |
|--------------------|-----------|-----------------|---------|
| Race MAE           |           |                 | < 4.50  |
| P>20pp             |           |                 | < 16.0% |
| P>30pp             |           |                 | < 6.0%  |
| Abs Bias           |           |                 | < 1.10  |
| Hispanic MAE       |           |                 | < 8.00  |
| Gender MAE         |           |                 | < 12.00 |
| HC South P>20pp    |           |                 | < 15.0% |
| Criteria pass      |           |                 |         |
```

**Critical detail — show county diversity tier breakdown:**

```
| Diversity Tier | N (holdout) | P>20pp BEFORE | P>20pp AFTER | Change |
|----------------|-------------|---------------|--------------|--------|
| Low (<15%)     |             |               |              |        |
| Med-Low (15-30)|             |               |              |        |
| Med-High (30-50)|            |               |              |        |
| High (50%+)    |             |               |              |        |
```

This is the key table. If the High tier P>20pp drops significantly (from 78.6%), the approach is working. If it barely moves, the corrections are too noisy or the bucket sizes are still too small.

Also show:
- How many companies used each calibration level (diversity_tier × region × industry vs fallthrough)
- The 10 largest calibration corrections (biggest absolute offset) — are they reasonable?
- Did any calibration bucket have a correction > 20pp? If so, flag it — that's suspiciously large and might be overfitting to a small bucket.

**Checkpoint: Show results. If this passes 7/7, skip to final validation. If not, proceed to Step 3.**

---

## Step 3: Adaptive Black Estimator

This applies the same idea that worked for Hispanic (grid-searched per-industry signal blending) to the Black estimate specifically.

### 3A: Why this is tricky (and how to avoid the Frankenstein problem)

In V9.1, Hispanic is estimated independently — it doesn't affect the race vector at all. But Black is part of the race vector (White + Black + Asian + AIAN + NHOPI + Two+ = 100%). If you improve Black by pushing it up, you have to take from somewhere — and that somewhere is almost certainly White (since 86% of tail errors are White overestimation).

The Frankenstein problem from V9.1-PL happened because estimates from different experts were stitched together. We avoid this by **adjusting WITHIN Expert D's race vector** — keeping D's internal consistency but nudging the White/Black split.

### 3B: Collect Black signals

For each company, collect these signals (many are already computed from the Hispanic estimator or existing pipeline):

| Signal | Source | What it tells you |
|--------|--------|-------------------|
| Expert D Black estimate | Expert D | The current race-vector Black % |
| LODES industry Black | LEHD WAC CNS codes | Black share of workers in this industry in this county |
| ABS minority ownership | ABS | Minority business density in this county × industry |
| Occ-chain Black | BLS × ACS | Black share expected from occupation mix |
| County Black % | ACS | Raw county Black population share |

### 3C: Compute adjustment signal

For each company:

```python
# Get the "alternative Black signals" — what other data sources think Black % should be
lodes_industry_black = get_lodes_industry_black(county_fips, naics_cns_code)
occ_chain_black = get_occ_chain_black(naics_group, state_fips)
county_black_pct = get_county_black_pct(county_fips)

# Expert D's current Black estimate
d_black = expert_d_race_vector['Black']

# Compute a blended "alternative" Black estimate
# Weights are grid-searched per industry (see 3D below)
alt_black = (w_lodes * lodes_industry_black + 
             w_occ * occ_chain_black + 
             w_county * county_black_pct)

# The adjustment is the difference between the alternative and D's estimate
# Positive = alt thinks more Black than D does
adjustment = alt_black - d_black

# Apply a FRACTION of the adjustment (controlled by adjustment_strength)
# This is conservative — we're nudging, not replacing
black_nudge = adjustment * adjustment_strength

# Apply within D's race vector
adjusted_black = d_black + black_nudge
adjusted_white = expert_d_race_vector['White'] - black_nudge  # take from White

# Keep all other categories from Expert D unchanged
# Renormalize to 100%
```

**The key design choice:** the adjustment takes from White and gives to Black (or vice versa). This is justified because 86% of tail errors are White overestimation with corresponding Black underestimation. The other four categories (Asian, AIAN, NHOPI, Two+) stay untouched from Expert D.

### 3D: Grid search per-industry weights

For 5 high-error industries (from V9.1 tail analysis), grid-search the signal weights and adjustment strength:

```
Industries to tune:
  - Accommodation/Food Service (NAICS 72) — 14.6% P>30pp
  - Healthcare/Social Assistance (NAICS 62) — 11.4% P>30pp
  - Manufacturing (NAICS 31-33) — 9.0% P>30pp
  - Transportation/Warehousing (NAICS 48-49) — 8.9% P>30pp
  - Retail Trade (NAICS 44-45) — 7.7% P>30pp

Grid parameters:
  w_lodes:    [0.0, 0.2, 0.4, 0.6]
  w_occ:      [0.0, 0.1, 0.2, 0.3]
  w_county:   [0.0, 0.2, 0.4]
  (weights renormalized to sum to 1.0)
  
  adjustment_strength: [0.05, 0.10, 0.15, 0.20, 0.30]

For all other industries:
  Use a single default weight set, also grid-searched.

Optimize on TRAINING set only (15,000 companies).
Metric to optimize: minimize P>20pp rate, with Race MAE < 4.50 as a constraint.
```

**Important:** The adjustment strength should be SMALL (0.05-0.30). We're nudging, not replacing. If the grid search picks adjustment_strength > 0.20, flag it — that's aggressive and might hurt the dev holdout.

### 3E: Apply and evaluate

1. Apply the adaptive Black adjustment to Expert D's race vector
2. Re-run Hispanic estimation (unchanged from V9.1)
3. Re-run gender estimation (unchanged from V9.1)
4. Re-run calibration (now with county diversity tiers from Step 2)
5. Re-run dampening grid search (might need different dampening with the Black adjustment in place)

**Report — Full V9.2 (15K train + diversity cal + adaptive Black):**

```
| Criterion         | V9.1 (2.7K) | V9.1 (15K) | + Div Cal | + Adapt Black | Target  |
|--------------------|-------------|-----------|-----------|---------------|---------|
| Race MAE           | 4.483       |           |           |               | < 4.50  |
| P>20pp             | 17.1%       |           |           |               | < 16.0% |
| P>30pp             | 7.7%        |           |           |               | < 6.0%  |
| Abs Bias           | 0.330       |           |           |               | < 1.10  |
| Hispanic MAE       | 6.697       |           |           |               | < 8.00  |
| Gender MAE         | 10.798      |           |           |               | < 12.00 |
| HC South P>20pp    | 13.9%       |           |           |               | < 15.0% |
| Criteria pass      | 5/7         |           |           |               |         |
```

**County diversity tier breakdown (permanent holdout):**
```
| Diversity Tier  | N | P>20pp (V9.1) | P>20pp (V9.2) | Change |
|-----------------|---|---------------|---------------|--------|
| Low (<15%)      |   | 5.2%          |               |        |
| Med-Low (15-30) |   | 13.8%         |               |        |
| Med-High (30-50)|   | 21.4%         |               |        |
| High (50%+)     |   | 78.6%         |               |        |
```

**Sector breakdown (permanent holdout):**
```
| Sector              | P>30pp (V9.1) | P>30pp (V9.2) | Change |
|---------------------|---------------|---------------|--------|
| Accommodation/Food  | 14.6%         |               |        |
| Healthcare          | 11.4%         |               |        |
| Manufacturing       | 9.0%          |               |        |
| Transportation      | 8.9%          |               |        |
| Retail              | 7.7%          |               |        |
```

**Bias direction for >30pp errors (permanent holdout):**
```
| Category | V9.1 White bias | V9.2 White bias | Change |
|----------|-----------------|-----------------|--------|
| White    | +27.28          |                 |        |
| Black    | -17.52          |                 |        |
```

If the adaptive Black adjustment is working, the White overestimation bias and Black underestimation bias in the >30pp bucket should both shrink.

**Region breakdown (permanent holdout):**
```
| Region    | Race MAE (V9.1) | Race MAE (V9.2) | P>20pp (V9.1) | P>20pp (V9.2) |
|-----------|-----------------|-----------------|---------------|---------------|
| South     |                 |                 | 20.8%         |               |
| West      |                 |                 | 16.6%         |               |
| Northeast |                 |                 | 14.4%         |               |
| Midwest   |                 |                 | 12.6%         |               |
```

---

## Step 4: Validation Checks

Before declaring victory or failure, run these sanity checks:

### 4A: Did we break anything?

```
| Metric that V9.1 PASSED | V9.1 value | V9.2 value | Still passes? |
|--------------------------|------------|------------|---------------|
| Race MAE < 4.50          | 4.483      |            |               |
| Abs Bias < 1.10          | 0.330      |            |               |
| Hispanic MAE < 8.00      | 6.697      |            |               |
| Gender MAE < 12.00       | 10.798     |            |               |
| HC South P>20pp < 15.0%  | 13.9%      |            |               |
```

If ANY previously passing metric now fails, that's a regression. Investigate what caused it before proceeding.

### 4B: Dev holdout vs permanent holdout consistency

```
| Metric   | Dev holdout (~800) | Permanent holdout (1,000) | Gap |
|----------|--------------------|-----------------------------|-----|
| Race MAE |                    |                             |     |
| P>20pp   |                    |                             |     |
| P>30pp   |                    |                             |     |
```

If the gap is large (e.g., dev P>20pp = 14% but permanent = 17%), that signals overfitting to the training data. The grid-searched weights might not generalize.

### 4C: The 77 worst companies

List the 20 companies with the highest max-category error in V9.2. For each, show:
- Industry (NAICS)
- State
- County minority %
- V9.1 max error → V9.2 max error (did it improve?)
- Which category had the biggest error
- What V9.2 predicted vs ground truth for White and Black

This tells us whether the improvements are reaching the actual worst cases, or just reshuffling which companies are in the tail.

---

## Step 5: Final 7/7 Acceptance Test

**Only run this after all three improvements are applied and Steps 4A-4C pass sanity checks.**

```
| # | Criterion         | V9.2 Result | Target  | Pass? | V9.1  | V6    |
|---|-------------------|-------------|---------|-------|-------|-------|
| 1 | Race MAE (pp)     |             | < 4.50  |       | 4.483 | 4.203 |
| 2 | P>20pp rate       |             | < 16.0% |       | 17.1% | 13.5%*|
| 3 | P>30pp rate       |             | < 6.0%  |       | 7.7%  | 4.0%* |
| 4 | Abs Bias (pp)     |             | < 1.10  |       | 0.330 | 1.000 |
| 5 | Hispanic MAE (pp) |             | < 8.00  |       | 6.697 | 7.752 |
| 6 | Gender MAE (pp)   |             | < 12.00 |       |10.798 |11.979 |
| 7 | HC South P>20pp   |             | < 15.0% |       | 13.9% | --    |

*V6 tested on 325-company holdout, not comparable to 1,000-company holdout
```

---

## Decision Framework

**Outcome A: 7/7 pass.**
→ Ship V9.2. Update CLAUDE.md, PROJECT_STATE.md. This is the new production model.

**Outcome B: 6/7 — P>30pp still fails but P>20pp passes.**
→ Very close. Investigate whether a slightly more aggressive adjustment_strength or a fourth calibration dimension (firm size) could push P>30pp under 6%. Also consider whether the P>30pp target of 6% is realistic for 1,000 companies when V6 achieved 4.0% on only 325.

**Outcome C: Still 5/7 — P>20pp and P>30pp both still fail.**
→ The census ceiling is real. Ship V9.2 anyway if it's better than V9.1 (even marginally). Accept 5/7 as the practical limit. Redirect effort to platform priorities. For future demographics improvement, the only path is non-census data:
  - EEO-1 FOIA data (already have ~23K federal contractors — use as direct estimates where available)
  - Job posting language analysis (bilingual requirements, diversity mentions)
  - CMS staffing data for hospitals
  - H-1B filings for Asian % in tech

**Outcome D: Regression — worse than V9.1 on any metric.**
→ The changes backfired. Revert to V9.1. Investigate which specific change caused the regression (Step 1, 2, or 3) by looking at the per-step results.

---

## Important Notes

- **Run Steps 1, 2, and 3 sequentially and report after each one.** Don't combine them all at once. We need to know what each change contributes independently.
- **All grid searches happen on TRAINING data only.** Never optimize on the dev holdout or permanent holdout.
- **The permanent holdout is only touched for final evaluation.** Use the dev holdout for quick checks during development.
- **If at any point a change makes things WORSE on the dev holdout, stop and report before applying it to the permanent holdout.** Don't push through a regression hoping calibration will fix it.
- **Watch for calibration bucket overfitting.** If any single calibration offset exceeds 25pp, flag it. That likely means the bucket has too few companies and the correction is noise.
- **The adaptive Black adjustment must be conservative.** adjustment_strength > 0.20 is a yellow flag. > 0.30 is a red flag. If the grid search picks high values, it's likely overfitting to the training set.

---

*Reference values (permanent holdout):*
*V9.1: Race MAE 4.483, P>20pp 17.1%, P>30pp 7.7% — 5/7*
*V8: Race MAE 4.526, P>20pp 16.1%, P>30pp 7.9% — 4/7*
*V6: Race MAE 4.203, P>20pp 13.5%, P>30pp 4.0% — 7/7 (on 325 companies)*
