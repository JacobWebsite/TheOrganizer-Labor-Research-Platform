# V9 Quick Test: Expert G Two+ Clamp & D+G Blend Re-evaluation

**Context:** We ran Expert G solo on the permanent holdout and found it has a +13.33pp Two+ (multiracial) bias that contaminates all its estimates. Before committing to V9's 2-model architecture, we need to know: is G's problem mostly the Two+ overflow, or is it deeper?

**Goal:** Clamp Expert G's Two+ predictions, redistribute the excess, then re-run the D+G blend to see if the blend now beats V8 post-calibration (Race MAE 4.526).

---

## Step 1: Locate the existing analysis

Find the script that produced the Expert G solo and D+G blend results (the one that generated the tables showing G's Race MAE of 7.240 and the D+G blend Race MAE of 4.809). It's likely in `/root/project/` — check recent Python files related to `ceiling`, `per_dimension`, `expert_g`, or `blend`. Read CLAUDE.md and PROJECT_STATE.md for current file locations.

**Checkpoint: Show me the script path before proceeding.**

---

## Step 2: Understand Expert G's raw output

From that script (or from the V8 estimation pipeline), extract Expert G's raw predictions for ALL permanent holdout companies. We need per-company estimates for: White, Black, Asian, AIAN, NHOPI, Two+, Hispanic, and gender (male/female).

Also extract Expert D's raw predictions for the same companies, and the ground truth (EEO-1 actual values).

**Checkpoint: Show me a sample of 5 companies with G's raw predictions, D's raw predictions, and ground truth side by side. Confirm the Two+ over-prediction is visible (G's Two+ should average ~13pp higher than truth).**

---

## Step 3: Build the Two+ clamp

For each company, clamp Expert G's Two+ estimate using this logic:

```
For each company:
    # Get the county-level Two+ rate from ACS data (same source the model already uses)
    county_two_plus = [company's county ACS Two+ percentage]
    
    # If county data unavailable, use national average (~3.5%)
    if county_two_plus is missing:
        county_two_plus = 3.5
    
    # Clamp G's Two+ to max of 2x the county rate (generous ceiling)
    clamped_two_plus = min(G_two_plus_estimate, county_two_plus * 2.0)
    
    # Calculate the excess that was removed
    excess = G_two_plus_estimate - clamped_two_plus
    
    # Redistribute excess proportionally to White, Black, Asian, AIAN, NHOPI
    # (proportional to their current G estimates)
    for category in [White, Black, Asian, AIAN, NHOPI]:
        share = G_category / sum(G_White, G_Black, G_Asian, G_AIAN, G_NHOPI)
        G_category_adjusted = G_category + (excess * share)
    
    # Verify: all race categories should still sum to 100%
```

**Checkpoint: Show me the same 5 companies after clamping. Show the before/after Two+ values and confirm they sum to 100%.**

---

## Step 4: Re-run the D+G blend with clamped G

Build the blended estimate for each company:

```
Blend rules:
    White %    = Expert D estimate
    Asian %    = Expert D estimate  
    AIAN %     = Expert D estimate
    NHOPI %    = Expert D estimate
    Black %    = Expert G estimate (after Two+ clamp)
    Hispanic % = Expert G estimate (after Two+ clamp)
    Two+ %     = Expert D estimate (NOT G — G's Two+ is unreliable even after clamp)

Then normalize race categories (White + Black + Asian + AIAN + NHOPI + Two+) to sum to 100%.
```

**Checkpoint: Show 5 example companies with the blend vs D-solo vs ground truth.**

---

## Step 5: Full evaluation

Calculate these metrics on the FULL permanent holdout for four scenarios:

| Metric | D solo | G solo | D+G blend (raw G) | D+G blend (clamped G) | V8 post-cal |
|--------|--------|--------|--------------------|-----------------------|-------------|
| Race MAE | | | | | 4.526 |
| Black MAE | | | | | |
| Hispanic MAE | | | | | 7.111 |
| P>20pp | | | | | 16.1% |
| P>30pp | | | | | 7.9% |
| Abs Bias | | | | | 0.536 |

Also break down by region:

| Region | D solo | D+G raw | D+G clamped |
|--------|--------|---------|-------------|
| South | | | |
| West | | | |
| Northeast | | | |
| Midwest | | | |

And by sector (Healthcare 62, Admin/Staffing 56, Finance 52):

| Sector | D solo | D+G raw | D+G clamped |
|--------|--------|---------|-------------|
| Healthcare | | | |
| Admin/Staffing | | | |
| Finance | | | |

---

## Step 6: Diagnosis

Based on the results, answer these questions:

1. **Did the Two+ clamp improve the D+G blend?** Compare D+G raw vs D+G clamped. If clamped is meaningfully better (>0.1pp Race MAE improvement), the Two+ overflow was a major part of G's problem.

2. **Does the clamped blend beat V8 post-calibration (4.526)?** If yes, V9's per-category approach has legs. If no, the problem is deeper than Two+ — G's occupation-chain methodology has fundamental issues beyond the Two+ bias.

3. **Where does the clamped blend help most?** Check if South + Healthcare improved. These are the segments where V9 is supposed to shine.

4. **What are the worst individual companies in the clamped blend?** List the 10 companies with highest max-category error in the clamped blend. Are they the same companies that V8 struggles with, or different ones?

**Important:** These are all PRE-calibration numbers. V8's 4.526 is POST-calibration. So the clamped blend doesn't need to beat 4.526 raw — it just needs to show meaningful improvement over the raw blend (4.809) to suggest that adding calibration on top could close the gap. If the clamped blend gets to ~4.5-4.6 pre-calibration, that's very promising because calibration typically improves MAE by 0.3-0.5pp.

---

*Reference: V8 permanent holdout Race MAE = 4.526 (post-cal), V6 = 4.203 (post-cal)*
*D solo pre-cal = 4.856, G solo pre-cal = 7.240, D+G raw blend pre-cal = 4.809*
