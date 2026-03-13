# V9 Test: Best-of-Expert Per-Category + IPF Normalization

**Date:** 2026-03-11
**Context:** V8.5 tested three ways to use Expert G's signal (blend, Two+ clamp, occ-chain adjustment). All three produced only marginal improvements. The occupation-chain correction was only directionally correct 60% of the time for Black.

**New approach:** Instead of trying to fix Expert G, we assemble the best estimate per racial category from whichever expert is genuinely best at that category, then use IPF (Iterative Proportional Fitting) to normalize the assembled estimates using external constraints — including ABS minority ownership and Expert G's occupation signal as constraints rather than direct estimates.

**Why IPF instead of proportional normalization:** When you pick White from Expert D and Black from Expert G, they don't sum to 100%. Simple proportional scaling (divide everything by the total) is crude — it shrinks confident estimates as much as uncertain ones. IPF uses real-world data (ACS industry demographics, LODES county demographics, ABS minority business density) to intelligently decide HOW to redistribute. Categories that already match the constraints barely change; categories that conflict get adjusted toward the data.

---

## Data Split

We use a three-way split of the ~12,500 ground truth companies:

| Set | Size | Purpose | Changes between versions? |
|-----|------|---------|--------------------------|
| **Training** | ~10,000 | Pick expert winners per category, train calibration corrections | Can reshuffle between versions |
| **Dev holdout** | ~1,500 | Experiment, tune IPF parameters, iterate freely | Can change between versions |
| **Permanent holdout** | ~1,000 | Final official scorecard, cross-version comparison | NEVER changes — use `selected_permanent_holdout_1000.json` |

**Setup instructions:**
1. Load the permanent holdout from `selected_permanent_holdout_1000.json` — these ~1,000 companies are locked and must be identical to previous versions.
2. From the remaining ~11,500 companies, randomly select 10,000 as training. The leftover ~1,500 become the dev holdout.
3. Save the dev holdout company IDs to `dev_holdout_1500.json` so we can reproduce this exact split later.

**Reporting rule:** Every evaluation table in this prompt shows THREE rows:
- **All 2,500** (dev + permanent combined — gives the most statistically reliable numbers)
- **Dev 1,500** (where we tuned — expect slightly optimistic results)
- **Permanent 1,000** (the official cross-version benchmark — compare to V6's 4.203 and V8's 4.526)

**Checkpoint: Confirm the split sizes and that the permanent holdout matches the existing file exactly. Show 5 company IDs from each set to verify no overlap.**

---

## Phase 1: Per-Category Expert Benchmarking

**Goal:** For each racial category AND for Hispanic AND for gender, determine which expert has the lowest MAE on the TRAINING data (10,000 companies only — never peek at either holdout).

### Step 1A: Run all experts on training companies

Using the 10,000 training companies, run every expert (A, B, D, E, F, G, V6-Full) and record their raw (pre-calibration) estimates for every category:

- Race: White, Black, Asian, AIAN, NHOPI, Two+
- Ethnicity: Hispanic
- Gender: Female

For each company × expert × category, record:
- The expert's raw estimate
- The ground truth value
- The absolute error

**Checkpoint: Show a summary table:**

```
| Category | Expert A | Expert B | Expert D | Expert E | Expert F | Expert G | V6-Full | WINNER |
|----------|----------|----------|----------|----------|----------|----------|---------|--------|
| White    |   MAE    |   MAE    |   MAE    |   MAE    |   MAE    |   MAE    |  MAE    |        |
| Black    |   ...    |   ...    |   ...    |   ...    |   ...    |   ...    |  ...    |        |
| Asian    |   ...    |   ...    |   ...    |   ...    |   ...    |   ...    |  ...    |        |
| Hispanic |   ...    |   ...    |   ...    |   ...    |   ...    |   ...    |  ...    |        |
| Female   |   ...    |   ...    |   ...    |   ...    |   ...    |   ...    |  ...    |        |
| Two+     |   ...    |   ...    |   ...    |   ...    |   ...    |   ...    |  ...    |        |
| AIAN     |   ...    |   ...    |   ...    |   ...    |   ...    |   ...    |  ...    |        |
| NHOPI    |   ...    |   ...    |   ...    |   ...    |   ...    |   ...    |  ...    |        |
```

Highlight the winner (lowest MAE) in each row. Also show:
- The P>20pp rate per expert (overall, not per category)
- The P>30pp rate per expert
- The number of companies each expert fails on (returns no estimate)

Also check: how close are the top 2 experts for each category? If the winner only beats the runner-up by less than 0.1pp, flag it — the "winner" might not be meaningfully better and could be noise.

**Do NOT proceed until I approve the category winners.**

---

## Phase 2: Assemble "Best-of" Estimates on Both Holdouts

### Step 2A: Run all experts on BOTH holdouts

Run every expert on all ~2,500 holdout companies (1,500 dev + 1,000 permanent). Save all raw estimates for every company × expert × category.

### Step 2B: Assemble "best-of" vector

Using the category winners identified in Phase 1 (from training data), assemble one combined estimate per company:

```python
# Example (actual winners determined by Phase 1 results):
best_of = {
    'White':    expert_D_estimate,   # if D won White on training
    'Black':    expert_X_estimate,   # whoever won Black on training
    'Asian':    expert_Y_estimate,   # whoever won Asian on training
    'AIAN':     expert_Z_estimate,   # whoever won AIAN on training
    'NHOPI':    expert_W_estimate,   # whoever won NHOPI on training
    'Two+':     expert_Q_estimate,   # whoever won Two+ on training
    'Hispanic': expert_H_estimate,   # whoever won Hispanic on training
    'Female':   expert_F_estimate,   # whoever won Female on training
}
```

### Step 2C: Simple normalization baseline

First, normalize the race categories (White + Black + Asian + AIAN + NHOPI + Two+) to sum to 100% using proportional scaling. This is the "naive" baseline.

Calculate metrics for this naive best-of:

```
| Metric    | All 2,500 | Dev 1,500 | Perm 1,000 | V8 post-cal (perm) |
|-----------|-----------|-----------|------------|---------------------|
| Race MAE  |           |           |            | 4.526               |
| Black MAE |           |           |            |                     |
| Hisp MAE  |           |           |            | 7.111               |
| Gender MAE|           |           |            | 11.779              |
| P>20pp    |           |           |            | 16.1%               |
| P>30pp    |           |           |            | 7.9%                |
| Abs Bias  |           |           |            | 0.536               |
```

**Region breakdown (Race MAE):**
```
| Region    | All 2,500 | Dev 1,500 | Perm 1,000 | V8 post-cal (perm) |
|-----------|-----------|-----------|------------|---------------------|
| South     |           |           |            |                     |
| West      |           |           |            |                     |
| Northeast |           |           |            |                     |
| Midwest   |           |           |            |                     |
```

**Sector breakdown (Race MAE):**
```
| Sector         | All 2,500 | Dev 1,500 | Perm 1,000 | V8 post-cal (perm) |
|----------------|-----------|-----------|------------|---------------------|
| Healthcare 62  |           |           |            |                     |
| Admin/Staff 56 |           |           |            |                     |
| Finance 52     |           |           |            |                     |
```

**Healthcare South tail rates:**
```
| Metric | All 2,500 | Dev 1,500 | Perm 1,000 | V8 post-cal (perm) |
|--------|-----------|-----------|------------|---------------------|
| P>20pp |           |           |            |                     |
| P>30pp |           |           |            |                     |
| Count  |           |           |            |                     |
```

**Checkpoint: Show results. This is the baseline that IPF needs to beat. Note: these are PRE-calibration numbers. V8 reference is POST-calibration. The best-of naive doesn't need to beat V8 raw — it just needs to be close enough that calibration could close the gap.**

---

## Phase 3: IPF Normalization

**Goal:** Replace proportional normalization with IPF, using external constraints to intelligently reconcile the best-of estimates.

### Step 3A: Install ipfn

```bash
pip install ipfn --break-system-packages
```

### Step 3B: Build the 2D IPF normalizer

**Why 2D:** A 1D IPF (just race categories) with one constraint is mathematically equivalent to proportional rescaling — it won't add anything new. The power of IPF comes from having at least 2 dimensions that constrain each other. We use race × gender.

For each company in BOTH holdouts, run a 2D IPF:

**SEED:** ACS PUMS cross-tabulation (race × gender) for this company's NAICS industry × state. This is a 6×2 matrix of proportions from real survey data showing how race and gender combine for workers in this industry and state.

Build this from whatever ACS PUMS data is already in the pipeline. If per-industry per-state PUMS cross-tabs aren't readily available, fall back to:
1. ACS industry-level race proportions as row seeds
2. LODES county gender proportions as column seeds  
3. Assume independence (multiply row × column) to fill the 6×2 matrix

**CONSTRAINT 1 (row margins — race):** The best-of race estimates from Phase 2, normalized to sum to 1.0. These tell IPF "the final race breakdown should match these proportions."

**CONSTRAINT 2 (column margins — gender):** The best gender estimate from Phase 2, expressed as [Female proportion, Male proportion]. These tell IPF "the final gender split should match this."

IPF then adjusts the seed matrix until both constraints are simultaneously satisfied. The result is a 6×2 race-by-gender matrix that:
- Respects the best per-category race estimates
- Respects the best gender estimate
- Has internal cross-tabulation structure from real ACS data (e.g., knowing that in nursing, Black workers skew more female than White workers)
- Sums to 100% by construction — no arbitrary scaling needed

```python
from ipfn import ipfn
import numpy as np

def ipf_normalize_2d(best_of_race, best_of_gender, acs_seed_matrix):
    """
    best_of_race: dict {'White': 62.3, 'Black': 18.7, 'Asian': 8.1, ...}
        — from per-category expert winners, must sum to ~100
    best_of_gender: dict {'Female': 74.2, 'Male': 25.8}
        — from gender expert winner
    acs_seed_matrix: 6x2 numpy array
        — ACS PUMS cross-tab (race × gender) for this industry × state
        — rows: White, Black, Asian, AIAN, NHOPI, Two+
        — cols: Male, Female
    
    Returns: dict with all race, gender, and cross-tab estimates
    """
    categories = ['White', 'Black', 'Asian', 'AIAN', 'NHOPI', 'Two+']
    
    # Ensure no zeros in seed (IPF can't create from zero)
    seed = np.maximum(acs_seed_matrix, 0.00001)
    seed = seed / seed.sum()  # normalize to sum to 1
    
    # Row margins (race proportions from best-of)
    race_margins = np.array([best_of_race.get(c, 0.1) for c in categories])
    race_margins = np.maximum(race_margins, 0.01)  # no zeros
    race_margins = race_margins / race_margins.sum()  # normalize to 1
    
    # Column margins (gender proportions from best-of)
    gender_margins = np.array([
        best_of_gender.get('Male', 50.0) / 100.0,
        best_of_gender.get('Female', 50.0) / 100.0
    ])
    gender_margins = np.maximum(gender_margins, 0.01)
    gender_margins = gender_margins / gender_margins.sum()
    
    # Run IPF
    aggregates = [race_margins, gender_margins]
    dimensions = [[0], [1]]  # dim 0 = race rows, dim 1 = gender cols
    
    ipf_solver = ipfn.ipfn(seed, aggregates, dimensions, 
                           convergence_rate=0.0001, max_iteration=50)
    result = ipf_solver.iteration()
    
    # Extract results
    output = {}
    for i, cat in enumerate(categories):
        output[cat] = float(result[i, :].sum()) * 100  # row sum = race %
    output['Male'] = float(result[:, 0].sum()) * 100    # col sum = gender %
    output['Female'] = float(result[:, 1].sum()) * 100
    
    return output
```

**Implementation notes:**
- Convergence threshold: < 0.0001 (0.01% change between iterations)
- Max iterations: 50
- If IPF doesn't converge, fall back to proportional normalization and flag the company
- Never let any seed cell be exactly 0 — use 0.00001 minimum
- Hispanic is estimated separately (not part of the race × gender matrix) — just use the best-of Hispanic estimate directly

**Checkpoint: Show the IPF setup for 5 example companies. For each, show:**
1. The best-of raw estimates (before normalization)
2. The ACS seed matrix
3. The IPF output matrix
4. Confirm convergence (how many iterations, final change)
5. Confirm outputs sum to 100% for race and 100% for gender

---

### Step 3C: ABS-adjusted variant (OPTIONAL)

For companies where ABS minority ownership density data is available, test modifying the seed matrix before running IPF:

```python
# If ABS minority business ownership for this county × NAICS is above
# the national median, adjust the ACS seed to allow for higher minority
# workforce share before running IPF:

if abs_minority_share is not None and abs_minority_share > national_median_abs:
    boost = 1.0 + (abs_minority_share - national_median_abs) * 0.5
    # Boost non-White rows in the seed
    for i in range(1, 6):  # Black, Asian, AIAN, NHOPI, Two+
        seed[i, :] *= boost
    seed = seed / seed.sum()  # renormalize
```

This nudges IPF's starting point toward higher diversity when ABS data says the local business environment is more diverse. The best-of estimates (constraints) still dominate the final answer — this just gives IPF a better starting grid to work from.

Run this as a separate variant. Do NOT mix it into the main IPF results.

**Checkpoint: Show results with and without ABS seed adjustment for 5 companies in high-ABS-density areas. Does the ABS adjustment change the IPF output meaningfully?**

---

## Phase 4: Full Evaluation (Pre-Calibration)

Calculate all metrics on BOTH holdouts for these scenarios:

**Main scorecard:**
```
| Metric    | D solo | Best-of | Best-of | Best-of  | V8      | V6      |
|           | (raw)  | naive   | + IPF   | +IPF+ABS | post-cal| post-cal|
|           |        | norm    |         | (if run) | (perm)  | (perm)  |
|-----------|--------|---------|---------|----------|---------|---------|
|                         ALL 2,500 (dev + permanent)                   |
|-----------|--------|---------|---------|----------|---------|---------|
| Race MAE  |        |         |         |          |  —      |  —      |
| Black MAE |        |         |         |          |  —      |  —      |
| Hisp MAE  |        |         |         |          |  —      |  —      |
| Gender MAE|        |         |         |          |  —      |  —      |
| P>20pp    |        |         |         |          |  —      |  —      |
| P>30pp    |        |         |         |          |  —      |  —      |
| Abs Bias  |        |         |         |          |  —      |  —      |
|-----------|--------|---------|---------|----------|---------|---------|
|                          DEV HOLDOUT 1,500                            |
|-----------|--------|---------|---------|----------|---------|---------|
| Race MAE  |        |         |         |          |  —      |  —      |
| Black MAE |        |         |         |          |  —      |  —      |
| Hisp MAE  |        |         |         |          |  —      |  —      |
| Gender MAE|        |         |         |          |  —      |  —      |
| P>20pp    |        |         |         |          |  —      |  —      |
| P>30pp    |        |         |         |          |  —      |  —      |
| Abs Bias  |        |         |         |          |  —      |  —      |
|-----------|--------|---------|---------|----------|---------|---------|
|                      PERMANENT HOLDOUT 1,000                          |
|-----------|--------|---------|---------|----------|---------|---------|
| Race MAE  | 4.856  |         |         |          | 4.526   | 4.203   |
| Black MAE | 8.873  |         |         |          |         |         |
| Hisp MAE  |        |         |         |          | 7.111   | 7.752   |
| Gender MAE|        |         |         |          | 11.779  | 11.979  |
| P>20pp    | 19.9%  |         |         |          | 16.1%   |         |
| P>30pp    | 8.6%   |         |         |          | 7.9%    |         |
| Abs Bias  |        |         |         |          | 0.536   | 1.000   |
```

**Region breakdown (Race MAE) — show for all three sets:**
```
All 2,500:
| Region    | D solo | Best-of naive | Best-of+IPF | +ABS (if run) |
|-----------|--------|---------------|-------------|---------------|
| South     |        |               |             |               |
| West      |        |               |             |               |
| Northeast |        |               |             |               |
| Midwest   |        |               |             |               |

Dev 1,500:
| Region    | D solo | Best-of naive | Best-of+IPF | +ABS (if run) |
|-----------|--------|---------------|-------------|---------------|
| South     |        |               |             |               |
| West      |        |               |             |               |
| Northeast |        |               |             |               |
| Midwest   |        |               |             |               |

Permanent 1,000:
| Region    | D solo | Best-of naive | Best-of+IPF | +ABS  | V8 post-cal |
|-----------|--------|---------------|-------------|-------|-------------|
| South     | 5.680  |               |             |       |             |
| West      | 5.480  |               |             |       |             |
| Northeast | 4.375  |               |             |       |             |
| Midwest   | 3.454  |               |             |       |             |
```

**Sector breakdown (Race MAE) — show for all three sets:**
```
All 2,500:
| Sector         | D solo | Best-of naive | Best-of+IPF | +ABS (if run) |
|----------------|--------|---------------|-------------|---------------|
| Healthcare 62  |        |               |             |               |
| Admin/Staff 56 |        |               |             |               |
| Finance 52     |        |               |             |               |

Dev 1,500:
| Sector         | D solo | Best-of naive | Best-of+IPF | +ABS (if run) |
|----------------|--------|---------------|-------------|---------------|
| Healthcare 62  |        |               |             |               |
| Admin/Staff 56 |        |               |             |               |
| Finance 52     |        |               |             |               |

Permanent 1,000:
| Sector         | D solo | Best-of naive | Best-of+IPF | +ABS  | V8 post-cal |
|----------------|--------|---------------|-------------|-------|-------------|
| Healthcare 62  |        |               |             |       |             |
| Admin/Staff 56 |        |               |             |       |             |
| Finance 52     |        |               |             |       |             |
```

**THE CRITICAL TEST — Healthcare South tail rates (show for all three sets):**
```
All 2,500:
| Metric | D solo | Best-of naive | Best-of+IPF | +ABS (if run) |
|--------|--------|---------------|-------------|---------------|
| P>20pp |        |               |             |               |
| P>30pp |        |               |             |               |
| Count  |        |               |             |               |

Dev 1,500:
| Metric | D solo | Best-of naive | Best-of+IPF | +ABS (if run) |
|--------|--------|---------------|-------------|---------------|
| P>20pp |        |               |             |               |
| P>30pp |        |               |             |               |
| Count  |        |               |             |               |

Permanent 1,000:
| Metric | D solo | Best-of+IPF | V8 post-cal |
|--------|--------|-------------|-------------|
| P>20pp |        |             |             |
| P>30pp |        |             |             |
| Count  |        |             |             |
```

**STOP GATE: If the Best-of+IPF approach does NOT reduce P>20pp and P>30pp for Healthcare South on the ALL 2,500 set compared to D solo, STOP HERE. Report results and do not proceed to Phase 5. The approach isn't working.**

---

## Phase 5: Add Calibration (only if Phase 4 passes the stop gate)

### Step 5A: Retrain calibration on training set

Using the 10,000 TRAINING companies:
1. Run the best-of+IPF pipeline on all training companies
2. Compare IPF output to ground truth
3. Compute bias corrections using V8's calibration structure:
   - Per industry group (same as V8)
   - Per industry group × region (same as V8 regional calibration)
   - Per industry group × county minority tier (same as V8)
   - Fallback hierarchy: county_tier → region → industry → global
4. Apply dampening at 0.80 (same as V8)

### Step 5B: Apply calibration to BOTH holdouts

Run the full pipeline on all 2,500 holdout companies:
best-of assembly → IPF normalization → calibration → final estimate

### Step 5C: Final comparison (post-calibration)

**Main scorecard:**
```
| Metric    | All 2,500       | Dev 1,500       | Perm 1,000      | V8    | V6    |
|           | Best-of+IPF+cal | Best-of+IPF+cal | Best-of+IPF+cal | perm  | perm  |
|-----------|-----------------|-----------------|-----------------|-------|-------|
| Race MAE  |                 |                 |                 | 4.526 | 4.203 |
| Black MAE |                 |                 |                 |       |       |
| Hisp MAE  |                 |                 |                 | 7.111 | 7.752 |
| Gender MAE|                 |                 |                 |11.779 |11.979 |
| P>20pp    |                 |                 |                 | 16.1% |       |
| P>30pp    |                 |                 |                 | 7.9%  |       |
| Abs Bias  |                 |                 |                 | 0.536 | 1.000 |
```

**Region breakdown post-cal — show for all three sets:**
```
All 2,500:
| Region    | Best-of+IPF+cal |
|-----------|-----------------|
| South     |                 |
| West      |                 |
| Northeast |                 |
| Midwest   |                 |

Dev 1,500:
| Region    | Best-of+IPF+cal |
|-----------|-----------------|
| South     |                 |
| West      |                 |
| Northeast |                 |
| Midwest   |                 |

Permanent 1,000:
| Region    | Best-of+IPF+cal | V8 post-cal | V6 post-cal |
|-----------|-----------------|-------------|-------------|
| South     |                 |             |             |
| West      |                 |             |             |
| Northeast |                 |             |             |
| Midwest   |                 |             |             |
```

**Sector breakdown post-cal — show for all three sets:**
```
All 2,500:
| Sector         | Best-of+IPF+cal |
|----------------|-----------------|
| Healthcare 62  |                 |
| Admin/Staff 56 |                 |
| Finance 52     |                 |

Dev 1,500:
| Sector         | Best-of+IPF+cal |
|----------------|-----------------|
| Healthcare 62  |                 |
| Admin/Staff 56 |                 |
| Finance 52     |                 |

Permanent 1,000:
| Sector         | Best-of+IPF+cal | V8 post-cal | V6 post-cal |
|----------------|-----------------|-------------|-------------|
| Healthcare 62  |                 |             |             |
| Admin/Staff 56 |                 |             |             |
| Finance 52     |                 |             |             |
```

**Healthcare South tail rates post-cal — show for all three sets:**
```
All 2,500:
| Metric | Best-of+IPF+cal |
|--------|-----------------|
| P>20pp |                 |
| P>30pp |                 |
| Count  |                 |

Dev 1,500:
| Metric | Best-of+IPF+cal |
|--------|-----------------|
| P>20pp |                 |
| P>30pp |                 |
| Count  |                 |

Permanent 1,000:
| Metric | Best-of+IPF+cal | V8 post-cal |
|--------|-----------------|-------------|
| P>20pp |                 |             |
| P>30pp |                 |             |
| Count  |                 |             |
```

**Improvement from calibration — show the delta:**
```
| Metric   | Pre-cal (All 2,500) | Post-cal (All 2,500) | Calibration gain |
|----------|---------------------|----------------------|------------------|
| Race MAE |                     |                      |                  |
| P>20pp   |                     |                      |                  |
| P>30pp   |                     |                      |                  |
```

### Step 5D: 7/7 acceptance test (Permanent holdout only)

```
| Criterion    | V9 Result (perm) | Target  | Pass/Fail | V8 (perm) | V6 (perm) |
|--------------|------------------|---------|-----------|-----------|-----------|
| Race MAE     |                  | < 4.20  |           | 4.526     | 4.203     |
| P>20pp       |                  | < 16%   |           | 16.1%     |           |
| P>30pp       |                  | < 6%    |           | 7.9%      |           |
| Abs Bias     |                  | < 1.10  |           | 0.536     | 1.000     |
| Hispanic MAE |                  | < 8.00  |           | 7.111     | 7.752     |
| Gender MAE   |                  | < 12.00 |           | 11.779    | 11.979    |
| Red flag rate|                  | < 15%   |           | 2.2%      | 0.87%     |
```

---

## Decision Framework

After completing all phases, the results tell us one of three things:

**Outcome A: Best-of+IPF+calibration passes 7/7 on permanent holdout and beats V6 Race MAE (< 4.203).**
→ This becomes V9. Ship it. Update CLAUDE.md and PROJECT_STATE.md.

**Outcome B: Best-of+IPF improves tail rates (P>20/P>30) in Healthcare South on All 2,500 but doesn't pass 7/7 on permanent holdout.**
→ The approach has legs but needs more work. Investigate:
  - 3D IPF: add BDS-HC firm-type profiles as a third dimension
  - ABS as a constraint dimension (not just seed adjustment)
  - Occupation-chain as a third constraint rather than a direct estimate
  - Whether different expert winners by SEGMENT (not just global) helps

**Outcome C: Best-of+IPF does NOT improve Healthcare South tail rates on All 2,500 (fails the Phase 4 stop gate).**
→ The ~4.2-4.5 Race MAE range is the census data ceiling. Document this finding. Revert to V6 as production model. Redirect effort to platform priorities (F-7 orphans, scoring overhaul, frontend). Plan a future demographics push centered on non-census data acquisition (LinkedIn signals, H-1B filings, CMS staffing data).

---

## Why the three-set reporting matters

**All 2,500** gives you the most statistically reliable numbers. With 2,500 companies, the P>30pp bucket might have 150-200 companies instead of 78. Segment breakdowns (Healthcare South) have enough companies to be meaningful. Use this set for making decisions about whether the approach works.

**Dev 1,500** is where you tuned. Results here might be slightly optimistic because you made choices (like which IPF variant to use) based partly on seeing these numbers. That's fine — it's what the dev set is for. But don't treat these numbers as the final answer.

**Permanent 1,000** is the ONLY set that matters for cross-version comparison. V6 got 4.203 here. V8 got 4.526 here. Whatever V9 gets here is the official result. Because no tuning decisions were based on this set, the number is unbiased.

If the All 2,500 numbers look great but the Permanent 1,000 numbers look bad, that's a sign of overfitting to the dev set. If both look similar, the results are trustworthy.

---

*Reference values (all on permanent holdout):*
*V6: Race MAE 4.203, 7/7 pass*
*V8: Race MAE 4.526, 4/7 pass*
*V8.5 D+G blend: Race MAE 4.809 pre-cal*
*V8.5 occ-chain Black-only adjustment: Race MAE 4.808 pre-cal*
*Theoretical per-category oracle: Race MAE 2.387 pre-cal*
