# Demographics Estimation V3: Implementation Plan for Claude Code

**Date:** 2026-03-08  
**Project:** `C:\Users\jakew\Downloads\labor-data-project`  
**Scripts location:** `scripts/analysis/demographics_comparison/`  
**Database:** `olms_multiyear` (PostgreSQL, localhost)

---

## Context (Read This First)

We are iteratively improving demographic estimation methods for a labor relations research platform. The system estimates workforce demographics (race, gender, Hispanic) for employers that don't publicly report this data, by blending multiple government statistical sources.

We have run two rounds of experiments:
- **V1:** Tested 6 original methods against 200 EEO-1 ground truth companies
- **V2:** Tested 11 methods (5 original + 6 new variants) against 200 training companies + 198 holdout companies. M3b (Dampened IPF) won the honest holdout test. M1b (Learned Weights) showed partial overfitting.

**V3 goal:** Test 9 modified methods (one targeted change per method) against a larger 400-company training set plus a fresh 200-company holdout. The larger training set gives weight optimization more data and reduces overfitting risk.

**Scientific discipline:** Each method gets exactly ONE change from its V2 version. This is intentional — changing one thing at a time is how we know which change caused which outcome. Do not add extra changes beyond what is specified.

---

## Step 0: Before Writing Any Code

Read these existing files in full before starting:

```
scripts/analysis/demographics_comparison/methodologies.py
scripts/analysis/demographics_comparison/cached_loaders.py
scripts/analysis/demographics_comparison/cached_loaders_v2.py
scripts/analysis/demographics_comparison/select_200.py
scripts/analysis/demographics_comparison/select_holdout_200.py
scripts/analysis/demographics_comparison/run_comparison_200_v2.py
scripts/analysis/demographics_comparison/compute_optimal_weights.py
scripts/analysis/demographics_comparison/config.py
```

Understanding the existing code structure before writing anything prevents duplication and keeps everything consistent with the existing architecture.

---

## Step 1: Expand the Training Pool to 400 Companies

### What to build: `select_400.py`

This is a new selection script that picks 400 training companies. It must:

1. **Load the existing used company codes** from both `selected_200.json` and `selected_holdout_200.json`
2. **Exclude all previously used companies** — zero overlap with either prior set
3. **Use the same stratified sampling algorithm** as `select_200.py` — same 5 dimensions (NAICS group, workforce size, Census region, minority share, urbanicity), same `max(3, round(N * group_share))` proportional targets, same coverage optimization
4. **Target 400 companies** — adjust the `TARGET_N` constant accordingly
5. **Verify post-selection** that all dimension buckets still have >= 3 companies
6. **Output:** `selected_400.json` in the same format as `selected_200.json`

**Why 400:** The V2 weight optimization for M1b had as few as 3 companies in some NAICS groups, producing unreliable weights for those groups. 400 companies roughly doubles the per-group sample size, pushing most groups above the 15-company minimum threshold needed for reliable weight optimization.

**Note on the candidate pool:** The original eligible pool was 2,444 companies. We have used 398 (200 + 198). That leaves approximately 2,046 eligible companies — more than enough to select 400 new ones plus a fresh 200 holdout.

---

## Step 2: Select a Fresh Holdout Set

### What to build: `select_holdout_v3.py`

Same approach as `select_holdout_200.py` but:
- Excludes the original 200, the original 198 holdout, AND the new 400 training companies
- Targets 200 companies
- Same stratification algorithm
- Output: `selected_holdout_v3.json`

**This holdout is locked. Do not use it for anything until the final evaluation in Step 6.**

---

## Step 3: Implement the 9 Modified Methods

All changes go into a new file: `methodologies_v3.py`

Copy `methodologies.py` as the starting point. Implement each of the 9 changes below as new method functions alongside the originals. **Do not modify or delete any existing method.** Add new methods with the naming convention shown.

---

### METHOD 1: M3c — Variable Dampening IPF

**Base method:** M3b (Dampened IPF), which uses `sqrt(ACS_k) * sqrt(LODES_k)` normalized  
**One change:** Replace the fixed `0.5` exponent with a per-NAICS-group optimized exponent

**How it works:**
- The exponent `α` controls how much dampening is applied: `ACS_k^α * LODES_k^(1-α)` normalized
- `α = 0.5` is the geometric mean (current M3b)
- `α = 1.0` is pure ACS
- `α = 0.0` is pure LODES
- Lower α = more LODES weight, more dampening of the majority signal
- Higher α = more ACS weight, closer to original IPF behavior

**Implementation:**
1. Build `compute_optimal_dampening.py` — for each NAICS group, test α values `[0.30, 0.35, 0.40, 0.45, 0.50, 0.55, 0.60, 0.65, 0.70]` against the 400 training companies using 5-fold cross-validation. Pick the α that minimizes average race MAE for that group.
2. Groups with fewer than 15 training companies: use the global optimum α (the α that minimizes MAE across all 400 companies)
3. Store results as `OPTIMAL_DAMPENING_BY_GROUP` dict in `methodologies_v3.py`
4. Apply via: `raw_k = ACS_k^α * LODES_k^(1-α)` then normalize

**Expected behavior:** Industries with homogeneous workforces (Utilities, Metal/Machinery) should optimize toward higher α (less dampening, closer to M3). Industries with diverse workforces (Finance, Professional/Technical) should optimize toward lower α (more dampening, closer to linear blend).

---

### METHOD 2: M1c — Cross-Validated Learned Weights

**Base method:** M1b (Learned Weights by Industry Group)  
**One change:** Replace single-set weight optimization with 5-fold cross-validation + weight constraints

**How it works:**
The original M1b found optimal weights by testing every ACS weight from 0.30 to 0.90 on all 400 training companies at once and picking the winner. This caused overfitting in small groups because the optimizer found weights that fit specific companies rather than the general pattern.

**Implementation:**
1. Build `compute_optimal_weights_v3.py` — same grid search but:
   - Use 5-fold cross-validation: split the 400 training companies into 5 equal groups, optimize on 4, validate on 1, repeat 5 times, average the MAE across validation folds
   - Pick the weight that minimizes the cross-validated (not training) MAE
   - Constrain the search range to `[0.35, 0.75]` — no values outside this range are permitted
   - Minimum group size: if a NAICS group has fewer than 15 training companies, do not learn custom weights for it. Assign the global cross-validated optimum instead
2. Store results as `OPTIMAL_WEIGHTS_V3_BY_GROUP` dict in `methodologies_v3.py`
3. Method function: identical formula to M1b, just uses the new weight table

**Why this reduces overfitting:** Cross-validation forces the optimizer to find weights that generalize across different subsets of the data. The range constraint `[0.35, 0.75]` prevents the extreme 0.90 ACS weights that caused Admin/Staffing and Utilities to overfit badly in V2.

---

### METHOD 3: M1d — Regional Weight Adjustment

**Base method:** M1 Baseline (60/40 ACS/LODES, same for all companies)  
**One change:** Shift ACS weight higher for West-region companies only

**Why:** The West had the worst error in V2 (holdout MAE 6.59 vs Midwest 2.98). Root cause: Asian and Hispanic workers cluster in specific West Coast metros at rates that county-level LODES cannot capture. ACS measures statewide industry composition, which in California and Washington reflects tech/agriculture demographics better than a single county average.

**Implementation:**
```python
def estimate_m1d(naics, state, county_fips, region, ...):
    if region == 'West':
        acs_weight = 0.75
        lodes_weight = 0.25
    else:
        acs_weight = 0.60
        lodes_weight = 0.40
    
    return acs_weight * ACS(naics, state) + lodes_weight * LODES(county_fips)
```

The `region` classification already exists in `classifiers.py`. West = AK, AZ, CA, CO, HI, ID, MT, NV, NM, OR, UT, WA, WY.

**What we're testing:** Whether giving ACS more weight in the West reduces the systematic underestimation of Asian/Hispanic workers in Western metros. If it works, the mechanism is clear. If it doesn't, the problem is elsewhere (likely sub-county concentration that even ACS can't capture).

---

### METHOD 4: M2c — ZIP-to-Tract Workplace Layer

**Base methods:** M2 (Three-Layer with residential tract) and M2b (Three-Layer with workplace tract)  
**One change:** Replace the broken tract selection heuristic with ZIP-to-tract crosswalk lookup

**Why M2b failed in V2:** It selected the highest-employment tract in the county as a proxy for the company's tract. This is almost always the wrong tract — it picks major commercial districts, not the company's actual location.

**Implementation:**
1. Check if a ZIP-to-tract crosswalk table already exists in the database. If not, build `build_zip_tract_crosswalk.py`:
   - Source: HUD USPS ZIP-Tract crosswalk (free, public, available at `https://www.huduser.gov/portal/datasets/usps_crosswalk.html`)
   - Or use Census ZCTA-to-tract relationship file
   - Table name: `zip_tract_crosswalk` with columns: `zip_code`, `tract_geoid`, `res_ratio` (residential weight), `bus_ratio` (business weight)
   - Use `bus_ratio` for business location matching (higher weight = more businesses in this tract for this ZIP)
2. In the method: look up the company's ZIP code in `zip_tract_crosswalk`, pick the tract with the highest `bus_ratio` for that ZIP
3. Pull LODES tract-level demographics for that tract from `cur_lodes_tract_metrics`
4. Formula: `0.50 * ACS(naics, state) + 0.30 * LODES(county) + 0.20 * LODES_tract(best_tract)`
5. Fallback: if ZIP not in crosswalk, fall back to M2 (residential ACS tract layer)

**Note:** This fixes both M2 and M2b simultaneously since they share the same underlying problem. Run this as one method (M2c) rather than two separate experiments.

---

### METHOD 5: M4c — Top-10 Occupation Trim

**Base method:** M4 (Occupation-Weighted, currently uses top-30 SOC codes)  
**One change:** Trim to top-10 occupations by employment share

**Why:** The bottom 20 occupations in M4's top-30 list each represent roughly 1-2% of the workforce. At that size, the ACS demographic data for each specific occupation is based on small samples (high sampling error) and the employment share weight is so small it may add noise rather than signal. The top 10 occupations typically account for 70-80% of employment in most industries.

**Implementation:**
```python
def estimate_m4c(naics, state, county_fips, ...):
    # Same as M4 but change top_n=30 to top_n=10
    occ_weighted_acs = get_occupation_weighted_acs(naics, state, top_n=10)
    return 0.70 * occ_weighted_acs + 0.30 * LODES(county_fips)
```

Check whether `get_occupation_weighted_acs` already accepts a `top_n` parameter. If so, this is a one-line change. If not, refactor it to accept one.

---

### METHOD 6: M3d — Selective Dampening by County Minority Share

**Base method:** M3 (Original IPF — currently uses raw product ACS_k * LODES_k)  
**One change:** Apply geometric mean dampening only when county minority share exceeds 20%; use original IPF below that threshold

**Why:** M3's original product amplification works correctly in homogeneous (low-minority) areas — that's why it wins in rural/low-minority contexts with MAE as low as 1.6. But it's catastrophic in diverse areas (+45pp White overestimation in high-minority holdout). This change preserves M3's rural superpower while adding M3b's safety valve in diverse areas.

**Implementation:**
```python
def estimate_m3d(naics, state, county_fips, county_minority_share, ...):
    acs = ACS(naics, state)
    lodes = LODES(county_fips)
    
    if county_minority_share > 0.20:
        # Dampened geometric mean (M3b behavior)
        raw = {k: sqrt(acs[k]) * sqrt(lodes[k]) for k in acs}
    else:
        # Original IPF product (M3 behavior)
        raw = {k: acs[k] * lodes[k] for k in acs}
    
    total = sum(raw.values())
    return {k: v / total for k, v in raw.items()}
```

`county_minority_share` is already available in `cur_lodes_geo_metrics` as `pct_minority`. Confirm this field exists and is populated. The threshold 0.20 (20%) was chosen because M3 wins reliably below this level and fails badly above it — visible in V2's minority share breakdown.

---

### METHOD 7: M5c — Data-Derived Variable Weights

**Base method:** M5 (Variable-Weight — currently uses hand-coded weight categories)  
**One change:** Replace hand-coded weight categories with data-derived weights using the same cross-validation approach as M1c

**Why:** M5 already has the right structure — it recognizes that different industries should have different ACS/LODES weights. But the weights (e.g., "local labor industries = 40/60, finance = 75/25") were manually assigned based on intuition, not calculated from data. V2 showed M5 generalizes better than expected (rank improved on holdout), suggesting the structure is sound. The weights just need to be data-driven.

**Implementation:**
1. Reuse `compute_optimal_weights_v3.py` from Method 2 — it already calculates per-group optimal weights with 5-fold cross-validation and constraints
2. M5c uses the same `OPTIMAL_WEIGHTS_V3_BY_GROUP` table as M1c
3. The difference between M5c and M1c: M5c uses M5's industry category groupings as the level of analysis (the 4 hand-coded categories: local-labor, occupation-driven, manufacturing, default), not the 18 NAICS groups
   - This means fewer, larger groups — less overfitting risk
   - One optimal weight per category rather than per NAICS group
4. If M5c ends up producing identical weights to M1c (because the categories collapse to the same solution), note this in the output and treat them as equivalent

**Note:** M5c and M1c both use the same optimization script. Run the optimization once and apply the results to both.

---

### METHOD 8: M4d — State-Level Top-5 Occupation Mix

**Base method:** M4b (State-Level Occupation Mix — used state ACS for all top-30 SOC codes)  
**One change:** Use state-level occupation demographics only for the top-5 occupations; fall back to national for all others

**Why M4b underperformed M4:** State-level ACS samples for specific occupation codes are small. For rare occupations (those ranked 6-30 in a given industry), the state sample might be a few hundred workers — too small for reliable demographic estimates. Noise from these small-sample occupations dragged down M4b's accuracy.

The top 5 occupations in any industry typically have state samples large enough to be reliable (thousands of workers). Using state data for these and national data for everything else captures the geographic signal where it's strongest while avoiding noise from rare occupations.

**Implementation:**
```python
def estimate_m4d(naics, state, county_fips, ...):
    top5_occs = get_top_n_occupations(naics, n=5)
    remaining_occs = get_top_n_occupations(naics, n=30)[5:]
    
    # Top 5: use state-level ACS
    top5_demo = weighted_average([
        get_acs_by_occupation_state(soc, state) * weight 
        for soc, weight in top5_occs
    ])
    
    # Remaining: use national ACS
    remaining_demo = weighted_average([
        get_acs_by_occupation_national(soc) * weight 
        for soc, weight in remaining_occs
    ])
    
    # Re-weight to combine
    top5_share = sum(weight for _, weight in top5_occs)
    remaining_share = sum(weight for _, weight in remaining_occs)
    
    occ_weighted = (top5_demo * top5_share + remaining_demo * remaining_share)
    return 0.70 * occ_weighted + 0.30 * LODES(county_fips)
```

Check the existing M4b implementation carefully before writing this — the state/national fallback logic may already be partially built and just needs the threshold lowered from 30 to 5.

---

### METHOD 9: M5d — Corrected Minority-Adaptive Weights

**Base method:** M5b (Minority-Adaptive — increased ACS weight in high-minority counties)  
**One change:** Flip the direction: increase LODES weight (decrease ACS weight) in high-minority counties

**Why M5b failed:** It increased ACS weight in diverse counties on the theory that national industry composition matters more than local geography when local geography is diverse. The data showed the opposite — in high-minority counties, LODES workplace data is *more* valuable because it captures the actual local labor supply, while ACS national averages are *less* valuable because they reflect the national industry average which is Whiter than diverse local markets.

**Implementation:**
```python
def estimate_m5d(naics, state, county_fips, county_minority_share, ...):
    # Start with M5's industry-adaptive base weights
    base_acs_w, base_lodes_w = get_industry_base_weights(naics)
    
    # Adjust based on county minority share (opposite direction from M5b)
    if county_minority_share > 0.50:
        acs_w = max(0.20, base_acs_w - 0.20)   # Reduce ACS weight
        lodes_w = min(0.80, base_lodes_w + 0.20) # Increase LODES weight
    elif county_minority_share > 0.30:
        acs_w = max(0.25, base_acs_w - 0.10)
        lodes_w = min(0.75, base_lodes_w + 0.10)
    else:
        acs_w = base_acs_w
        lodes_w = base_lodes_w
    
    return acs_w * ACS(naics, state) + lodes_w * LODES(county_fips)
```

`county_minority_share` comes from `cur_lodes_geo_metrics.pct_minority`. The adjustment values (-0.20 in high-minority, -0.10 in medium-minority) mirror what M5b added but in reverse. The `max`/`min` constraints prevent weights from going outside [0.20, 0.80].

---

## Step 4: Build the V3 Comparison Runner

### What to build: `run_comparison_400_v3.py`

Based on `run_comparison_200_v2.py`. Changes:

1. **Load `selected_400.json`** instead of `selected_200.json`
2. **Run all methods:** the 5 surviving originals (M1, M2, M3, M3b, M1b) + the 9 new V3 variants (M1c, M1d, M2c, M3c, M3d, M4c, M4d, M5c, M5d) = **14 methods total**
3. **Same metrics as V2:** Race MAE, Race RMSE, Hellinger, Signed Errors, Win Count, Gender MAE, Hispanic MAE
4. **Same dimensional breakdowns:** by NAICS group, size bucket, Census region, minority share, urbanicity
5. **Additional output:** For M1c and M5c, print the cross-validated optimal weights so they can be inspected

**Output files:**
- `comparison_400_v3_detailed.csv` — one row per (company, method, dimension)
- `comparison_400_v3_summary.csv` — aggregated by classification bucket

---

## Step 5: Build Cached Loaders for New Methods

### What to build: `cached_loaders_v3.py`

Same pattern as `cached_loaders_v2.py`. Wrap all 9 new method functions with the dict-based cache. Methods that share data queries with existing methods (M1d, M3d, M5d — which all use the same ACS/LODES lookups as their base methods) should reuse the existing cache keys where possible to maintain the high cache hit rate.

---

## Step 6: Run and Validate

### Training run (Step 6a)
```bash
# Select 400 training companies
py scripts/analysis/demographics_comparison/select_400.py

# Select fresh 200 holdout (locked until Step 6b)
py scripts/analysis/demographics_comparison/select_holdout_v3.py

# Compute optimal weights and dampening factors using 400 companies
py scripts/analysis/demographics_comparison/compute_optimal_weights_v3.py
py scripts/analysis/demographics_comparison/compute_optimal_dampening.py

# Run comparison
py scripts/analysis/demographics_comparison/run_comparison_400_v3.py --companies selected_400.json
```

### Holdout run (Step 6b — only after training results are reviewed)
```bash
py scripts/analysis/demographics_comparison/run_comparison_400_v3.py --companies selected_holdout_v3.json
```

**Important:** Do not look at the holdout results until after the training results have been reviewed and you have decided which methods to carry forward. The holdout is the final honest verdict, not a development tool.

---

## Step 7: Output Report Structure

### What to build: `generate_report_v3.py`

Auto-generate a markdown report `METHODOLOGY_REPORT_V3.md` with this structure:

**Section 1: Executive Summary table** — rank all 14 methods by holdout Race MAE, show training MAE, delta, and generalization score (`holdout_advantage / training_advantage * 100%`)

**Section 2: For each new V3 method**, a four-line summary:
- What changed from the base method
- Training MAE vs base method (improvement %)
- Holdout MAE vs base method (improvement %)
- Generalization score — did the improvement hold up?

**Section 3: Dimensional breakdowns** — by industry, size, region, minority share, urbanicity. Show top-3 methods per bucket.

**Section 4: Overfitting flags** — any method where the training advantage shrinks by more than 50% on holdout gets flagged. This is the V2 M1b lesson applied systematically.

**Section 5: Bias analysis** — signed errors for the top-3 methods. Specifically track whether the structural biases (Food/Bev White overestimate, Computer/Electrical White underestimate) improved.

---

## Checkpoints — Stop and Review Before Proceeding

**Checkpoint A:** After `select_400.py` runs — verify the output shows 400 companies with balanced dimension coverage. Confirm zero overlap with existing sets.

**Checkpoint B:** After `compute_optimal_weights_v3.py` runs — review the learned weights. Any industry group with fewer than 15 companies should show the global default weight, not a custom weight. Any learned weight outside [0.35, 0.75] is a bug — the constraints should prevent this.

**Checkpoint C:** After `compute_optimal_dampening.py` runs — review the dampening factors. Check that high-diversity industries (Finance, Admin/Staffing) optimized toward lower α (more dampening) and low-diversity industries (Utilities, Metal/Machinery) optimized toward higher α. If the pattern is random, the optimization may not have converged properly.

**Checkpoint D:** After the training run — before running the holdout, share the training results summary. Confirm the V3 methods as a group are showing improvements before unlocking the holdout.

---

## What Not to Change

These things stay exactly the same as V2. Do not alter them:

- EEO-1 ground truth parsing (`eeo1_parser.py`) — same source, same encoding
- All 5 classification dimensions and their bucket definitions (`classifiers.py`)
- All metric calculations — MAE, RMSE, Hellinger, signed errors (`metrics.py`)
- The stratified sampling algorithm logic (just change TARGET_N and exclusion list)
- M3b's formula for gender estimation — M3b gender stays as `sqrt(ACS) * sqrt(LODES)` regardless of what M3c does to race estimation
- M7 (Hybrid) — this is not being changed. It will automatically inherit M1c's race output since M7 = M1b_race + M3_gender. Note this in the report.

---

## File Summary

New files to create:

| File | Purpose |
|------|---------|
| `select_400.py` | Select 400 training companies, no overlap with existing sets |
| `select_holdout_v3.py` | Select 200 fresh holdout companies |
| `compute_optimal_weights_v3.py` | 5-fold CV weight optimization with constraints for M1c and M5c |
| `compute_optimal_dampening.py` | 5-fold CV dampening factor optimization for M3c |
| `methodologies_v3.py` | All 9 new method functions + inherited originals |
| `cached_loaders_v3.py` | Cached wrappers for V3 methods |
| `run_comparison_400_v3.py` | Main runner: 14 methods × 400 companies |
| `generate_report_v3.py` | Auto-generate METHODOLOGY_REPORT_V3.md |

Existing files to modify (minimally):

| File | Modification |
|------|-------------|
| `config.py` | Add `V3_METHODS` list, `OPTIMAL_DAMPENING_BY_GROUP` dict placeholder |

Existing files — do not modify:

```
methodologies.py, methodologies_v2.py (preserve originals)
cached_loaders.py, cached_loaders_v2.py
select_200.py, select_holdout_200.py
run_comparison_200.py, run_comparison_200_v2.py
metrics.py, classifiers.py, eeo1_parser.py, data_loaders.py
```

---

## Key Numbers to Track

When you share results back, the most important numbers to surface are:

1. **M3c vs M3b holdout MAE** — did variable dampening improve on M3b's 4.55?
2. **M1c vs M1b holdout MAE** — did cross-validation recover the overfitting gap? (M1b was 4.72 holdout)
3. **M1d West MAE** — did regional weighting reduce the West's 6.59 holdout MAE?
4. **M2c vs M2 holdout MAE** — did proper tract selection unlock the geographic layer?
5. **M3d vs M3 in rural/low-minority** — did it preserve M3's 2.17 rural MAE?
6. **M3d vs M3b in high-minority** — did it match or beat M3b's 11.27 high-minority MAE?
7. **Generalization scores** — for any method that beats M3b on training, does the advantage hold on holdout?

---

*This plan was written assuming familiarity with the existing V2 codebase. Read the existing files first (Step 0) before writing any new code.*
