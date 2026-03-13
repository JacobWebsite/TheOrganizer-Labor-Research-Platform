# Demographics Estimation V4: Method Tweaks + New Combined Method

**Date:** 2026-03-09  
**Project:** `C:\Users\jakew\Downloads\labor-data-project`  
**Scripts location:** `scripts/analysis/demographics_comparison/`  
**Builds on:** V3 holdout results (`comparison_holdout_v3_v3_detailed.csv`)

---

## Before Reading Further: What V3 Taught Us

The single most important pattern in V3 is this:

**M3 original IPF (the simplest method) is dramatically better than everything else in two specific contexts:**
- Finance/Insurance: MAE 1.31 vs M3c's 3.34 — a 2.03pp gap
- Suburban companies: MAE 1.41 vs M3c's 3.33 — a 1.92pp gap

These gaps are not small noise. They are larger than the total gap between M3c (best overall) and M1 Baseline (8th place). The original IPF's amplification effect is somehow perfectly calibrated for these low-diversity, concentrated-workforce settings.

M3d (selective dampening) correctly identified this — it routes to M3 for low-minority contexts and wins Midwest and Suburban as a result. But M3d still falls short of M3's full Finance/Insurance performance because it uses M3b above the minority threshold rather than M3's full amplification.

**This means the biggest single improvement available in V4 is explicitly routing Finance/Insurance and Suburban low-minority companies to M3 IPF.** Everything else is incremental.

The second major pattern: **Admin/Staffing is the one industry where occupation data wins** (M4 at 4.58 vs M3c at 6.20). Admin/Staffing is also the industry where LODES county data is most unreliable — staffing agencies place workers at client sites, not their own address. Occupation data bypasses this problem entirely.

---

## Step 0: Before Writing Any Code

Read the existing V3 files:
```
scripts/analysis/demographics_comparison/methodologies_v3.py
scripts/analysis/demographics_comparison/compute_optimal_dampening.py
scripts/analysis/demographics_comparison/compute_optimal_weights_v3.py
scripts/analysis/demographics_comparison/run_comparison_400_v3.py
scripts/analysis/demographics_comparison/cached_loaders_v3.py
```

Also read carefully: the M4c and M4d implementations. Find and document why they produced identical output to M4. This must be fixed before any M4-family tweaks are meaningful.

---

## Company Set for V4: All Previously Used Companies

**Do not select any new companies for V4.**

We are preserving the remaining untested companies for future rounds where we need a clean, unseen holdout. V4 runs on every company that has already been used across all prior rounds combined.

### The Four Existing Company Files

| File | Round | Purpose | Approx Count |
|------|-------|---------|-------------|
| `selected_200.json` | V2 training | Original training set | 200 |
| `selected_holdout_200.json` | V2 holdout | V2 honest test | 198 |
| `selected_400.json` | V3 training | Expanded training set | 400 |
| `selected_holdout_v3.json` | V3 holdout | V3 honest test | 200 |

**Total: ~998 companies**

### What to Build: `build_all_companies.py`

A small utility script that:

1. Loads all four JSON files
2. Deduplicates by company code (in case any company appears in more than one set — unlikely but verify)
3. Merges into a single list: `all_companies_v4.json`
4. Prints a summary: total companies, any duplicates removed, breakdown by NAICS group, region, minority share, and urbanicity so we can confirm the combined set has good coverage

```python
import json, os

files = [
    'selected_200.json',
    'selected_holdout_200.json',
    'selected_400.json',
    'selected_holdout_v3.json',
]

all_companies = {}
for f in files:
    data = json.load(open(f))
    for company in data:
        code = company['company_code']
        if code in all_companies:
            print(f"DUPLICATE: {code} in {f}")
        else:
            all_companies[code] = company

merged = list(all_companies.values())
json.dump(merged, open('all_companies_v4.json', 'w'), indent=2)
print(f"Total companies: {len(merged)}")
```

### What This Means for Interpreting V4 Results

Because all ~998 companies were used in some form during earlier rounds — some to train M1b's weights (V3 training set), some as holdout tests — **V4 results are not a clean holdout**. The methods have "seen" these companies in varying degrees:

- The V3 training set (400 companies) was used directly to optimize M1c and M3c's parameters
- The V3 holdout (200 companies) was never used for optimization but its results informed the V4 method designs (the routing rules in M8 were built from V3 holdout patterns)
- The V2 sets (398 companies) were used to build earlier methods

This means V4 results will be **somewhat optimistic** — especially for M8, whose routing rules were explicitly designed around the V3 holdout patterns. Think of V4 as a "development evaluation" rather than a true generalization test.

The purpose of V4 is: confirm that the new methods work as designed, identify any bugs or unexpected interactions, and stress-test the routing logic across a large diverse sample. The true generalization test happens in a future round when we unlock fresh companies.

**Do not over-interpret V4 MAE numbers as the methods' true real-world performance.**

---

## Part A: Tweaks to Existing Methods (6 methods)

All changes go into `methodologies_v4.py`. One targeted change per method. Do not modify V3 files.

---

### METHOD 1: M3e — Finance/Utilities-Routed Variable Dampening

**Base method:** M3c (Variable Dampening IPF, V3 overall winner at 4.326 MAE)  
**One change:** Add explicit routing for Finance/Insurance and Utilities to M3 original IPF

**Why:** M3c's per-industry dampening exponent clearly does not go far enough for these two industries. Finance/Insurance has a 2.03pp gap between M3 and M3c. Utilities has a 1.18pp gap. Both industries tend to operate in homogeneous counties (suburban office parks, utility service territories) where M3's amplification effect is mathematically perfect. No amount of exponent tuning captures this — M3c needs to fully hand off to M3 for these groups.

**Implementation:**
```python
def estimate_m3e(naics_group, naics, state, county_fips, county_minority_share, ...):
    
    # Hard routing for industries where M3 original IPF wins decisively
    if naics_group in ['Finance/Insurance (52)', 'Utilities (22)']:
        return estimate_m3_original(naics, state, county_fips)
    
    # For all other industries, use M3c (variable dampening)
    alpha = OPTIMAL_DAMPENING_BY_GROUP.get(naics_group, GLOBAL_OPTIMAL_ALPHA)
    acs = ACS(naics, state)
    lodes = LODES(county_fips)
    raw = {k: acs[k]**alpha * lodes[k]**(1-alpha) for k in acs}
    total = sum(raw.values())
    return {k: v/total for k, v in raw.items()}
```

**Expected impact:** Finance/Insurance has N=49 in holdout (25% of all companies). Improving from 3.34 to ~1.31 on those 49 companies would reduce overall MAE by approximately 0.5pp — the largest single improvement available from any tweak.

**Verification check:** After running, confirm Finance/Insurance MAE is close to M3's 1.31. If it's 1.6–1.9, the routing is working but there may be minor implementation differences in how M3 original is called.

---

### METHOD 2: M3f — Minority + Industry Threshold Tuning

**Base method:** M3d (Selective Dampening by minority share, V3 4th place at 4.529 MAE)  
**One change:** Add Finance/Insurance and Utilities routing AND test three minority-share thresholds

**Why M3d underperforms in some areas:** M3d uses M3b's dampened formula above 20% minority share. But M3b is not as good as M3 for Finance/Insurance and Suburban regardless of minority share. M3f adds explicit industry-based routing on top of M3d's threshold logic.

**Implementation:**
```python
def estimate_m3f(naics_group, naics, state, county_fips, county_minority_share, ...):
    
    # Industries where M3 original always wins regardless of minority share
    if naics_group in ['Finance/Insurance (52)', 'Utilities (22)']:
        return estimate_m3_original(naics, state, county_fips)
    
    # For remaining industries: use threshold routing
    # THRESHOLD IS A PARAMETER — test 0.15, 0.20, 0.25 in cross-validation
    THRESHOLD = OPTIMAL_M3F_THRESHOLD  # determined by 5-fold CV on 400 training companies
    
    if county_minority_share > THRESHOLD:
        return estimate_m3b_dampened(naics, state, county_fips)  # Geometric mean
    else:
        return estimate_m3_original(naics, state, county_fips)   # Full amplification
```

**How to optimize the threshold:** Run 5-fold cross-validation on the 400 training companies for threshold values [0.15, 0.20, 0.25, 0.30]. Pick the threshold that minimizes cross-validated race MAE. Store as `OPTIMAL_M3F_THRESHOLD` in config.

**Note:** If the optimal threshold turns out to be 0.20 (same as M3d), then M3f's only improvement over M3d is the Finance/Utilities routing.

---

### METHOD 3: M1e — High-Minority Floor Constraint

**Base method:** M1b (Learned Weights, V3 3rd place at 4.517 MAE)  
**One change:** Add a minimum ACS weight floor for high-minority counties

**Why:** M1b already wins high-minority companies (10.36 MAE vs 10.92 for M3c). The learned weights tend to push toward LODES in industries where LODES was more accurate during training. But in high-minority counties, LODES county data reflects the diversity of the surrounding population — and for high-minority contexts that's actually useful signal. The problem is that the optimizer doesn't have enough high-minority training examples in some industry groups to learn the right weight.

**Implementation:**
```python
def estimate_m1e(naics_group, naics, state, county_fips, county_minority_share, ...):
    
    # Get the standard learned weight for this industry group
    acs_weight = OPTIMAL_WEIGHTS_V3_BY_GROUP.get(naics_group, GLOBAL_OPTIMAL_WEIGHT)
    lodes_weight = 1 - acs_weight
    
    # In high-minority counties: impose a floor on LODES weight
    # LODES captures local diversity; don't let optimizer ignore it entirely
    if county_minority_share > 0.50:
        lodes_weight = max(lodes_weight, 0.40)  # LODES gets at least 40%
        acs_weight = 1 - lodes_weight
    elif county_minority_share > 0.30:
        lodes_weight = max(lodes_weight, 0.30)  # LODES gets at least 30%
        acs_weight = 1 - lodes_weight
    
    return acs_weight * ACS(naics, state) + lodes_weight * LODES(county_fips)
```

**What this tests:** Whether guaranteeing a minimum local-geography signal in diverse areas reduces the White overestimation that plagues all methods. If it doesn't improve high-minority MAE, it confirms the problem is structural (neither ACS nor LODES can see employer-specific hiring patterns) rather than a weighting problem.

---

### METHOD 4: M4e — Fix Bug + Demographic-Variance Occupation Trim

**Critical prerequisite:** First identify and fix why M4c and M4d produced identical output to M4.

**Before writing M4e, document the bug:**
- Run M4 and M4c on a single test company and print the exact occupation list used
- If both lists have 30 occupations, the top_n parameter is not being passed or respected
- Print the occupation weights to confirm M4c is actually using 10 occupations

**One change after fix:** Replace the fixed top-N cutoff with demographic-variance-based filtering

**Why top-10 didn't work:** Trimming the bottom occupations by employment size (occupations 11–30) may not capture the right ones. The occupations that introduce the most bias are not necessarily the smallest ones — they're the ones with the most extreme demographics relative to the industry average. A small occupation that is 95% White inflates the estimate more than a large one that matches the industry average.

**Implementation:**
```python
def estimate_m4e(naics, state, county_fips, ...):
    
    all_occs = get_top_n_occupations(naics, n=30)  # Get all 30 first
    
    # Calculate each occupation's "demographic deviation" from industry ACS baseline
    industry_baseline = ACS(naics, state)  # The industry-level demographic estimate
    
    filtered_occs = []
    for soc, emp_weight in all_occs:
        occ_demo = get_acs_by_occupation_national(soc)
        white_deviation = occ_demo['White'] - industry_baseline['White']
        
        # Exclude occupations that push White estimate >8pp above industry baseline
        # These are the niche professional/management roles that cause systematic overestimation
        if white_deviation > 8.0:
            continue  # Skip this occupation
        filtered_occs.append((soc, emp_weight))
    
    # Renormalize employment weights to sum to 1
    total_weight = sum(w for _, w in filtered_occs)
    filtered_occs = [(soc, w/total_weight) for soc, w in filtered_occs]
    
    # If filtering removed everything (edge case), fall back to top-10
    if not filtered_occs:
        filtered_occs = all_occs[:10]
    
    occ_weighted_acs = weighted_average_demographics(filtered_occs, state)
    return 0.70 * occ_weighted_acs + 0.30 * LODES(county_fips)
```

**The 8.0pp threshold** is a starting point. Test [4.0, 6.0, 8.0, 10.0] in cross-validation on the training set and pick the best one.

**Expected result:** Should help most in Computer/Electrical (M3c White overestimate +10.9pp) and Information (overestimate +2.2pp) where the occupation mix includes high-White engineering/professional roles that inflate the estimate.

---

### METHOD 5: M2d — Amplified Geographic Tract Layer

**Base method:** M2c (ZIP-to-tract geographic layer, V3 7th overall but best Hispanic at 6.374)  
**One change:** Increase the weight of the tract-level layer from 20% to 35%

**Why:** M2c's current formula is 50% ACS + 30% LODES county + 20% LODES tract. The tract layer is what makes M2c special — it's the most geographically precise signal we have. But 20% is a conservative weight. The fact that M2c wins Hispanic in 8 of 16 industry groups suggests the ZIP-to-tract crosswalk is working well and deserves more weight.

**Implementation:**
```python
def estimate_m2d(naics, state, county_fips, zip_code, ...):
    
    best_tract = get_zip_to_tract(zip_code)  # Same ZIP-tract crosswalk as M2c
    
    acs_signal = ACS(naics, state)
    county_signal = LODES(county_fips)
    tract_signal = LODES_tract(best_tract) if best_tract else county_signal
    
    # Changed: 0.50/0.30/0.20 → 0.45/0.20/0.35
    # More tract, less county (tract is more precise; county adds noise when tract is known)
    return 0.45 * acs_signal + 0.20 * county_signal + 0.35 * tract_signal
```

**Why reduce county and increase tract:** The county-level LODES signal is partially redundant once you have a good tract-level signal. Keeping both at high weight just averages them, diluting the precision of the tract. This change bets that the tract is usually the better geographic signal when available.

**What to watch:** Computer/Electrical Hispanic MAE was just 1.48 with M2c. If M2d's amplified tract weight maintains or improves this, it confirms the tract layer is the source of that accuracy.

---

### METHOD 6: M5e — Industry-Category Routing (M5 as Dispatcher)

**Base method:** M5 (Variable-Weight by industry category, currently 14th place)  
**One change:** Replace M5's weight-blending logic with method routing

**The core idea:** M5 already classifies companies into 4 industry categories. Instead of using different ACS/LODES weights per category, use those same categories to route to the method that V3 showed wins in each category's context.

This is a fundamentally different use of M5's structure — not a weighted blend, but a dispatcher.

**Implementation:**
```python
def estimate_m5e(naics_group, naics, state, county_fips, county_minority_share, ...):
    
    category = get_industry_category(naics_group)
    # Categories: 'local_labor', 'occupation_driven', 'manufacturing', 'professional'
    
    if category == 'occupation_driven':
        # Healthcare, Finance, Admin/Staffing — occupation structure dominates
        if naics_group in ['Finance/Insurance (52)', 'Utilities (22)']:
            return estimate_m3_original(naics, state, county_fips)  # M3 wins here
        elif naics_group == 'Admin/Staffing (56)':
            return estimate_m4e(naics, state, county_fips)  # Occupation data wins here
        else:
            return estimate_m3c(naics_group, naics, state, county_fips)  # Default to M3c
    
    elif category == 'local_labor':
        # Construction, food service, agriculture — geography dominates
        return estimate_m3d(naics_group, naics, state, county_fips, county_minority_share)
    
    elif category == 'manufacturing':
        # All manufacturing — M3c wins in most, M1b in Computer/Electrical
        if naics_group == 'Computer/Electrical Mfg (334-335)':
            return estimate_m1b(naics_group, naics, state, county_fips)
        else:
            return estimate_m3c(naics_group, naics, state, county_fips)
    
    else:  # 'professional' or default
        return estimate_m3c(naics_group, naics, state, county_fips)
```

**What this tests:** Whether explicit method routing outperforms any form of weight blending. If M5e performs well, it validates the routing-based approach that M8 (below) extends to all companies.

---

## Part B: New Method — M8 Adaptive Context Router

This is the main new method. It is architecturally different from everything that came before.

### The Core Design Philosophy

Every existing method tries to be a single formula that works reasonably well everywhere. M8 does something different: it maps each company to the specific method that the V3 data showed is best for that company's context, then applies that method.

Think of it like a doctor who doesn't give every patient the same medication. Instead, they read the symptoms and choose the right treatment for that specific case. M8 reads a company's context signals (industry, location diversity, geography type) and chooses the right estimation method.

This is only possible because we now have V3 holdout results across 200 companies and 5 context dimensions — enough data to know which method wins where with confidence.

### Architecture Overview

M8 has three components:
1. **Race Router** — picks the race estimation method based on context
2. **Hispanic Override** — always uses M2c's geographic layer for Hispanic
3. **Gender** — always uses M3/M3c family (all identical)

### The Race Router (Decision Tree)

Rules are applied in priority order. First rule that matches wins.

```python
def route_race_method(naics_group, county_minority_share, urbanicity, region):
    
    # RULE 1: Finance/Insurance → M3 original IPF
    # Evidence: M3 MAE 1.31 vs M3c 3.34 (2.03pp gap, N=49 companies)
    # Why: Finance companies cluster in homogeneous suburban counties.
    #      M3's amplification is mathematically perfect for this.
    if naics_group == 'Finance/Insurance (52)':
        return 'M3_ORIGINAL'
    
    # RULE 2: Utilities → M3 original IPF  
    # Evidence: M3d MAE 1.69, M3 MAE 2.28, M3c MAE 2.87 (N=5, small but consistent)
    # Why: Utilities cover defined service territories — highly predictable demographics
    if naics_group == 'Utilities (22)':
        return 'M3_ORIGINAL'
    
    # RULE 3: Admin/Staffing → M4 (occupation-weighted)
    # Evidence: M4 MAE 4.58 vs M3c 6.20 (1.62pp gap, N=6)
    # Why: Staffing agencies place workers everywhere. NAICS code is meaningless
    #      for predicting workforce demographics. Occupation mix is the real signal.
    if naics_group == 'Admin/Staffing (56)':
        return 'M4E'  # Use M4e (fixed + demographic-variance trim)
    
    # RULE 4: High minority (>50%) → M1b
    # Evidence: M1b MAE 10.36 vs M3c 10.92 (N=24)
    # Why: Learned NAICS weights capture some of the employer-specific
    #      demographic patterns that pure IPF approaches miss
    if county_minority_share > 0.50:
        return 'M1B'
    
    # RULE 5: Suburban + Low minority → M3 original IPF
    # Evidence: M3 MAE 1.41 vs M3c 3.33 (1.92pp gap, N=51 suburban)
    # Condition: urbanicity == 'Suburban' AND minority_share < 0.25
    # Why: Suburban low-diversity = perfectly homogeneous counties where
    #      IPF amplification captures the concentration effect exactly
    if urbanicity == 'Suburban' and county_minority_share < 0.25:
        return 'M3_ORIGINAL'
    
    # RULE 6: Midwest → M3d (selective dampening)
    # Evidence: M3d MAE 2.75 vs M3c 3.03 in Midwest (N=49)
    # Condition: region == 'Midwest'  
    # Why: Midwest companies sit in more homogeneous counties on average;
    #      M3d's selective dampening preserves M3's amplification advantage
    if region == 'Midwest':
        return 'M3D'
    
    # DEFAULT: M3c (overall V3 winner)
    # Wins: Northeast, South, West, Urban, Professional/Technical,
    #       Construction, Transport Equipment, Chemical Manufacturing
    return 'M3C'
```

**What this decision tree is NOT:** It is not a probability blend. For each company, exactly one method is selected and applied. The output is that method's estimate, not a weighted average of multiple methods.

### The Hispanic Override

M2c wins Hispanic overall (6.374 MAE vs M3c's 7.316 and M1b's 6.675). But it loses in specific industries.

Build a Hispanic method router:
```python
def route_hispanic_method(naics_group):
    
    # Industries where M1b wins Hispanic
    m1b_wins_hispanic = [
        'Admin/Staffing (56)',    # M1b: 12.11  M2c: 14.54
        'Healthcare/Social (62)', # M1b: 7.64   M2c: 8.49
        'Other',                  # M1b: 8.69   M2c: 9.08
        'Retail Trade (44-45)',   # M1b: 2.39   M2c: 4.00
        'Transport Equip Mfg',    # M1b: 1.72   M2c: 2.23
    ]
    
    if naics_group in m1b_wins_hispanic:
        return 'M1B_HISPANIC'  # Use M1b's LODES-weighted estimate for Hispanic
    
    return 'M2C_HISPANIC'  # Default: M2c's geographic tract layer
```

### Implementation Notes

M8 is a meta-method — it calls other methods' estimation functions. It does not have its own formula.

```python
def estimate_m8(naics_group, naics, state, county_fips, zip_code,
                county_minority_share, urbanicity, region, ...):
    
    # Route race estimation
    race_method = route_race_method(naics_group, county_minority_share, urbanicity, region)
    race_estimate = {
        'M3_ORIGINAL': lambda: estimate_m3_original(naics, state, county_fips),
        'M4E':         lambda: estimate_m4e(naics, state, county_fips),
        'M1B':         lambda: estimate_m1b(naics_group, naics, state, county_fips),
        'M3D':         lambda: estimate_m3d(naics_group, naics, state, county_fips, county_minority_share),
        'M3C':         lambda: estimate_m3c(naics_group, naics, state, county_fips),
    }[race_method]()
    
    # Route Hispanic estimation separately
    hisp_method = route_hispanic_method(naics_group)
    hisp_estimate = {
        'M1B_HISPANIC': lambda: estimate_m1b_hispanic(naics_group, naics, state, county_fips),
        'M2C_HISPANIC': lambda: estimate_m2c_hispanic(naics, state, county_fips, zip_code),
    }[hisp_method]()
    
    # Gender always uses M3c family (all IPF variants identical on gender)
    gender_estimate = estimate_m3c_gender(naics, state, county_fips)
    
    return {
        'race': race_estimate,
        'hispanic': hisp_estimate,
        'gender': gender_estimate,
        'routing_used': race_method  # Log which method was selected
    }
```

**The routing log is important.** Store which method each company was routed to in the output CSV. This lets us audit whether the routing rules are working as expected — e.g., confirm that all 49 Finance/Insurance companies are being routed to M3_ORIGINAL.

### Expected Performance Estimate

Based on V3 holdout data, rough projected M8 performance:

| Segment | N | Current Best (M3c) | M8 Projected | Source of Gain |
|---------|---|-------------------|--------------|----------------|
| Finance/Insurance | 49 | 3.34 | ~1.50 | Route to M3 original |
| Utilities | 5 | 2.87 | ~1.90 | Route to M3 original |
| Admin/Staffing | 6 | 6.20 | ~4.58 | Route to M4e |
| High minority (>50%) | 24 | 10.92 | ~10.36 | Route to M1b |
| Suburban low-minority | ~40 | 3.33 | ~1.60 | Route to M3 original |
| Midwest | 49 | 3.03 | ~2.75 | Route to M3d |
| All other | ~27 | varies | varies | Default M3c |

**Rough overall projection:** ~3.6–3.9 Race MAE (vs M3c's 4.326)  
This would be a 0.4–0.7pp improvement — roughly equivalent to all the gains from V1 to V3 combined.

---

## Part C: Occupation Investigation (Critical Before M4e Can Work)

Before M4e can be properly evaluated, we need to understand and fix why M4c and M4d produced identical output.

### Investigation Script: `debug_m4_family.py`

Build a standalone script that:

1. Takes a single test company (e.g., a Finance/Insurance company and a Manufacturing company — two different contexts)
2. Runs M4, M4c, and M4d on that company
3. Prints at each step:
   - The full list of occupations selected (SOC codes + employment weights)
   - For M4c: confirms exactly 10 occupations are in the list
   - For M4d: confirms which occupations are using state vs national data
   - The final demographic estimate from each method
4. If all three produce identical occupation lists, the code change did not execute

### What to Fix

**If M4c bug:** The `get_occupation_weighted_acs` function doesn't accept or respect a `top_n` parameter. Fix: add `top_n=30` as a default parameter, implement the slicing logic: `occupations = all_occupations[:top_n]`.

**If M4d bug:** The state-level ACS occupation lookup is always falling back to national. Fix: print the fallback trigger condition (usually `n < 100 workers`) and check whether state-level data is actually loaded for the relevant occupations. If the state table is empty, load it.

---

## Part D: V4 Runner

### What to build: `run_comparison_all_v4.py`

Run all methods against `all_companies_v4.json` (~998 companies).

Methods: 5 surviving originals + 6 V3 variants + 6 V4 tweaks + M8 = **~23 methods total**

**New output column:** `routing_method` — for M8, log which sub-method was selected for each company. This lets us verify the routing rules are working and analyze performance by routing path.

**Also tag each row with:** `source_set` — which original JSON file each company came from (`v2_train`, `v2_holdout`, `v3_train`, `v3_holdout`). This lets us slice results by how "familiar" the company is to each method, as a proxy for measuring optimism bias.

**Key comparisons to surface in the report:**
1. M3e vs M3c: does Finance/Utilities routing improve overall MAE?
2. M8 vs M3c: does the full routing system beat the single best method?
3. M8's Finance/Insurance segment: actual MAE vs projected ~1.50
4. M4e vs M4: does the demographic-variance trim now show a difference? (Confirms bug fix)
5. M1e vs M1b: does the high-minority floor help the hardest segment?
6. V3-holdout slice vs full-set: how much do results differ on the 200 companies that were a true holdout last round? This is our best proxy for real generalization.

---

## File Summary

New files to create:

| File | Purpose |
|------|---------|
| `build_all_companies.py` | Merge all 4 prior company JSON files into `all_companies_v4.json` |
| `methodologies_v4.py` | M3e, M3f, M1e, M4e, M2d, M5e, M8 |
| `debug_m4_family.py` | Investigate + confirm M4c/M4d bug fix |
| `compute_m3f_threshold.py` | Cross-validate optimal minority threshold for M3f using V3 training set |
| `run_comparison_all_v4.py` | Full runner: ~23 methods × ~998 companies |
| `generate_report_v4.py` | Auto-generate synthesis report with routing analysis |

Modify:
- `config.py`: Add `M4_VARIANCE_THRESHOLD`, `OPTIMAL_M3F_THRESHOLD`, `M8_ROUTING_RULES`

Do not modify: all V1, V2, V3 files. Do not create any new company selection scripts.

---

## Checkpoints

**Checkpoint A:** After `debug_m4_family.py` — confirm M4c bug is identified and fixed. Show diff of the fix before proceeding.

**Checkpoint B:** After `build_all_companies.py` — print the count and dimension breakdown. Confirm ~998 companies with no duplicates. Confirm the combined set has at least 3 companies in every NAICS group and region bucket.

**Checkpoint C:** After `compute_m3f_threshold.py` — report the optimal threshold (expected 0.15–0.30). Use only the V3 training set (selected_400.json) for this optimization, not the full ~998 set. If it returns 0.20 exactly, note that M3f's only improvement over M3d is the Finance/Utilities routing.

**Checkpoint D:** After the full run — review M8 routing distribution first. How many companies were routed to each method? Finance/Insurance should be ~200 across the full set (roughly 4× the 49 in V3 holdout alone). If counts look wrong, the routing logic has a bug.

**Checkpoint E:** After the full run — slice results by `source_set`. The V3 holdout slice (200 companies that were the cleanest test last round) should show M8 and M3e performing close to the full-set numbers. If they perform dramatically better on the V3 training slice than the V3 holdout slice, we have optimism bias.

---

## Important Caveats for V4

**No holdout — these are development results only.** All ~998 companies have been seen in some form. M8's routing rules were explicitly built from V3 holdout patterns. Expect V4 MAE numbers to be noticeably better than V3 holdout numbers — some of that improvement is real, some is optimism from reusing seen data. The source_set slice (Checkpoint E) is the best available tool for estimating how much is real.

**Finance/Insurance N=~200 in full set:** With ~200 Finance companies across all prior sets, the Finance/Insurance routing in M3e and M8 will have a very large effect on overall MAE. If M3 truly dominates Finance across all 200 of those companies (not just the 49 in V3 holdout), that strongly validates the routing rule. If M3's advantage shrinks or disappears in the V2 company sets, the V3 finding may have been a fluke of that specific 49-company sample.

**M8 is not magic:** M8 is an assembly of existing methods with routing logic derived from V3 data. Its advantage depends entirely on the routing rules being correct. Treat the routing rules as hypotheses being confirmed, not facts already established.

**The high-minority ceiling:** M1e's floor constraint and M8's routing to M1b for high-minority still leave ~10+ MAE for majority-minority employers. No methodological tweak breaks through this without a fundamentally different data source.

**Optimizing M3f threshold:** Use only `selected_400.json` (the V3 training set) for this cross-validation, not the full ~998. Using all 998 companies to optimize a threshold that gets evaluated on those same 998 companies is circular — it would just find the threshold that fits the noise in the full dataset.
