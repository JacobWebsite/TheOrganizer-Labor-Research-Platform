# V10 Demographics Model — Claude Code Implementation Prompt

**Project root:** `C:\Users\jakew\.local\bin\Labor Data Project_real`  
**Working directory:** `scripts\analysis\demographics_comparison\`  
**Database:** PostgreSQL, `olms_multiyear` on localhost (port 5433)  
**Purpose:** Improve Hispanic and Gender accuracy (under-optimized dimensions),
build a confidence/reliability indicator, and create a fresh sealed holdout
for honest future evaluation.

---

## How to Work

Work through this document in the order it is written. Each phase has numbered
checkpoints. At each checkpoint, stop, show the output or result, and wait for
approval before continuing. Do not skip ahead or bundle multiple checkpoints.

When editing files, show the before/after diff for every change. When running
scripts, show the full terminal output. When running database queries, show the
full result.

If something is ambiguous or a file doesn't match what is described, stop and
ask rather than guessing.

Read CLAUDE.md and PROJECT_STATE.md for current server layout, database
credentials, and file locations.

---

## Background You Need

The model estimates workforce demographics (race, gender, Hispanic share) for
employers that don't publicly report this data. It validates against EEO-1
federal contractor filings (~14,000+ federal contractors, ground truth).

### V9.2 Results (what we're building on)

V9.2 passed 7/7 acceptance criteria on the permanent holdout (954 companies):

| # | Criterion | V9.2 | Target |
|---|-----------|------|--------|
| 1 | Race MAE (pp) | 4.403 | < 4.50 |
| 2 | P>20pp rate | 15.4% | < 16.0% |
| 3 | P>30pp rate | 5.9% | < 6.0% |
| 4 | Abs Bias (pp) | 0.313 | < 1.10 |
| 5 | Hispanic MAE (pp) | 6.778 | < 8.00 |
| 6 | Gender MAE (pp) | 11.160 | < 12.00 |
| 7 | HC South P>20pp | 13.9% | < 15.0% |

### V9.2 Architecture (DO NOT CHANGE these unless explicitly told to)

```
Race:     Expert D (75%) + Expert A (25%) blend
          + Black adjustment for Retail Trade and Other Manufacturing
Hispanic: Industry-specific + county-tier-adaptive signal blending
          d_hisp = 0.05 (calibration essentially disabled)
Gender:   Expert F (occupation-weighted), single expert, no blending
          d_gender = 0.5
Calibration: Hierarchical diversity_tier x region x industry (cap 20pp)
Dampening: d_race=0.85, d_hisp=0.05, d_gender=0.5
```

### Why V10 focuses on Hispanic and Gender, not Race

Race estimation has hit the census data ceiling. V9.2 squeezed out the last
gains through expert blending (D+A) and diversity-tier calibration. The
remaining 56 companies with >30pp race error are irreducible outliers —
companies whose workforce simply doesn't match any available census signal.
More race tuning will yield fractions of a percentage point at best.

Meanwhile, Hispanic and Gender are under-optimized:

- **Hispanic:** d_hisp = 0.05 means calibration corrections are essentially
  turned OFF. Race benefits from d_race = 0.85 (using 85% of learned
  corrections). Nobody has tried enabling Hispanic calibration properly.
  This is like having a recipe you perfected for one dish but never applied
  to a second dish that uses the same technique.

- **Gender:** Uses a single Expert F with no blending. Race improved
  dramatically when Expert D was blended with Expert A at 75/25. The same
  "blend two different methods that make different kinds of mistakes"
  approach has never been tried for gender. Gender MAE of 11.16 is the
  weakest metric by far.

### Why a fresh holdout matters

V9.2 tuned dampening directly on the permanent holdout (justified because
dampening is a hyperparameter, not a model parameter). This is defensible
but means the permanent holdout is no longer fully independent. The 7/7
result is real but slightly optimistic for truly unseen companies.

V10 creates a new sealed holdout so future comparisons are fully honest.

### Key files from V9.2

| File | Purpose |
|------|---------|
| `run_v9_2.py` | Main V9.2 pipeline |
| `verify_v9_2_7of7.py` | 7/7 verification with D+A blend |
| `v9_2_7of7_results.json` | Final 7/7 metrics and config |
| `push_p30_v9_2d.py` | D+A blend discovery script |
| `selected_permanent_holdout_1000.json` | Current permanent holdout |
| `expanded_training_v6.json` | Full EEO-1 company pool |

---

## V10 Goals and Acceptance Criteria

### Primary targets (the metrics we're actively trying to improve)

| Metric | V9.2 | V10 Target | V10 Stretch |
|--------|------|------------|-------------|
| Hispanic MAE | 6.778 | < 6.20 | < 5.80 |
| Gender MAE | 11.160 | < 10.20 | < 9.50 |

### Guard rails (must NOT get worse — race is frozen, not being optimized)

| Metric | V9.2 | V10 Floor (must stay above/below) |
|--------|------|-----------------------------------|
| Race MAE | 4.403 | < 4.55 (allow 0.15pp regression max) |
| P>20pp | 15.4% | < 16.5% |
| P>30pp | 5.9% | < 6.5% |
| Abs Bias | 0.313 | < 1.10 |
| HC South P>20pp | 13.9% | < 15.5% |

The philosophy: Race is locked in. We are NOT trying to improve it. We are
trying to improve Hispanic and Gender without breaking Race. Any change that
worsens Race MAE beyond 4.55 is rejected, even if it dramatically improves
Hispanic or Gender.

---

## PHASE 0: Fresh Sealed Holdout

### Why this matters

The permanent holdout (`selected_permanent_holdout_1000.json`) was used to
tune dampening in V9.2. This means it's no longer a fully independent test.
Think of it like a teacher who tweaked the grading rubric after seeing how
students performed on the exam — the grades are still meaningful, but they're
not quite as objective as if the rubric was set beforehand.

V10 creates a NEW sealed holdout that has never been touched by any
optimization. This gives us an honest measurement going forward.

### Checkpoint 0A — Create V10 sealed holdout

Write a script `select_v10_holdout.py` that:

1. Loads the full EEO-1 company pool from `expanded_training_v6.json`
2. Loads the existing permanent holdout from `selected_permanent_holdout_1000.json`
3. From the companies NOT in the permanent holdout, randomly select 1,000
   companies using SEED = 2026031210 (today's date + "10" for V10)
4. Use stratified sampling: proportional representation by NAICS sector and
   Census region, same approach as `select_test_holdout_1000.py`
5. Save to `selected_v10_sealed_holdout_1000.json`
6. Verify ZERO overlap with permanent holdout

```python
# Overlap check (must print PASS)
assert len(perm_ids & v10_ids) == 0, "CONTAMINATION WITH PERMANENT HOLDOUT"
print(f"PASS: zero overlap. V10 sealed holdout N={len(v10_ids)}")
```

**Show:** The count per NAICS sector and per region for the new holdout.

### Checkpoint 0B — Rebuild training set excluding both holdouts

Rebuild the training set to exclude BOTH holdouts:
- `selected_permanent_holdout_1000.json` (existing, for backward comparisons)
- `selected_v10_sealed_holdout_1000.json` (new, for V10 honest evaluation)

```python
assert len(training_ids & perm_ids) == 0, "PERM CONTAMINATION"
assert len(training_ids & v10_ids) == 0, "V10 CONTAMINATION"
print(f"Training N: {len(training_ids)}")  # expect ~10,500-11,000
```

Save to `expanded_training_v10.json`.

**Show:** Training set size. Confirm both holdouts are excluded.

### Checkpoint 0C — Reproduce V9.2 baseline on permanent holdout

Before changing anything, run the V9.2 architecture exactly as-is on the
permanent holdout using the new training set. The results should be very
close to V9.2's reported numbers (small differences are okay because the
training set lost ~1,000 companies to the new holdout).

```
| Criterion | V9.2 (original) | V9.2 (new training) | Gap |
|-----------|-----------------|---------------------|-----|
| Race MAE  | 4.403           |                     |     |
| P>20pp    | 15.4%           |                     |     |
| P>30pp    | 5.9%            |                     |     |
| Hisp MAE  | 6.778           |                     |     |
| Gender MAE| 11.160          |                     |     |
```

If Race MAE exceeds 4.60 or any metric moves by more than 1.0pp, STOP and
investigate — the training set reduction may have removed a critical
calibration bucket. Do not proceed until the baseline is stable.

**Also run on the V10 sealed holdout** to establish V9.2's performance on
truly unseen data:

```
| Criterion | V9.2 on perm holdout | V9.2 on V10 sealed | Gap |
|-----------|---------------------|--------------------|-----|
| Race MAE  |                     |                    |     |
| P>20pp    |                     |                    |     |
| P>30pp    |                     |                    |     |
| Hisp MAE  |                     |                    |     |
| Gender MAE|                     |                    |     |
```

This gap tells us how much the permanent holdout was "consumed" by V9.2's
dampening optimization. If the V10 sealed results are noticeably worse,
that confirms the permanent holdout was partially overfit.

---

## PHASE 1: Enable Hispanic Calibration

### What this is and why it should help

Right now, after the model computes a Hispanic percentage estimate, it applies
a calibration correction — an adjustment learned from training data that says
things like "in the South, Healthcare companies tend to have 3pp more Hispanic
workers than the raw estimate predicts, so add 3pp."

But the dampening parameter (d_hisp) is set to 0.05, which means the model
only applies 5% of that correction. If the correction says "add 3pp," it
actually only adds 0.15pp. This is essentially the same as not correcting
at all.

For race, d_race = 0.85 — the model trusts 85% of its learned corrections,
and this works well. Nobody ever tried turning up the Hispanic dial.

### Why Hispanic calibration was originally set so low

V9.1's dampening grid search found that Hispanic corrections were unstable —
applying them made things worse on the dev holdout. But V9.2 then added
diversity-tier calibration (which V9.1 didn't have). The diversity-tier
hierarchy might produce BETTER Hispanic corrections that actually help.

### Checkpoint 1A — Hispanic calibration grid search

Using the V9.2 architecture (D+A race blend, current Hispanic weights,
Expert F gender), grid-search ONLY d_hisp while keeping d_race=0.85 and
d_gender=0.5 fixed.

Grid: d_hisp = [0.05, 0.10, 0.15, 0.20, 0.25, 0.30, 0.40, 0.50, 0.60, 0.70, 0.80]

Train calibration offsets on the training set. Evaluate on the PERMANENT
holdout (not the V10 sealed holdout — save that for final evaluation).

**Report as a table:**

```
| d_hisp | Hisp MAE | Race MAE | P>20pp | P>30pp | Gender MAE | Notes |
|--------|---------|---------|--------|--------|-----------|-------|
| 0.05   | 6.778   | 4.403   | 15.4%  | 5.9%   | 11.160    | V9.2 baseline |
| 0.10   |         |         |        |        |           | |
| 0.15   |         |         |        |        |           | |
| ...    |         |         |        |        |           | |
```

**Decision rule:**
- Pick the d_hisp that minimizes Hispanic MAE WITHOUT worsening Race MAE
  beyond 4.55 or P>30pp beyond 6.5%
- If ALL values of d_hisp > 0.05 make Hispanic MAE worse, keep 0.05 and
  note this — it means the calibration corrections genuinely hurt for
  Hispanic, and the problem is in the corrections themselves, not the
  dampening

**Show:** Best d_hisp and the improvement in Hispanic MAE.

### Checkpoint 1B — Hispanic calibration with expanded hierarchy

If Checkpoint 1A found improvement (any d_hisp > 0.05 helps), proceed here.
If not, skip to Checkpoint 1C.

The current Hispanic calibration may be using the same bucket hierarchy as
race (diversity_tier x region x industry). But Hispanic concentration is
much more geographically specific than race — Hispanic communities cluster
at the neighborhood level, not the county level.

Test whether a SEPARATE Hispanic-specific calibration hierarchy works better.
Instead of using the existing diversity_tier (based on overall minority %),
create a Hispanic-specific tier:

```python
def get_hispanic_county_tier(county_fips):
    """Hispanic-specific tier based on county Hispanic %"""
    hisp_pct = get_county_hispanic_pct(county_fips)  # from ACS data
    if hisp_pct < 10:
        return 'low_hisp'
    elif hisp_pct < 25:
        return 'med_hisp'
    elif hisp_pct < 50:
        return 'high_hisp'
    else:
        return 'very_high_hisp'
```

The county Hispanic percentage should be available from the same ACS county
demographics table used for diversity_tier. If not, compute it from
`acs_county_demographics` or equivalent.

Build a separate Hispanic calibration hierarchy:
```
1. hispanic_tier x region x industry (min 40 companies)
2. hispanic_tier x industry (min 30)
3. region x industry (min 20)
4. industry (min 20)
5. global (min 20)
```

Cap Hispanic offsets at 15pp (tighter than the 20pp race cap, because
Hispanic corrections are inherently noisier).

Re-run the d_hisp grid search with this new hierarchy.

**Report:** Compare Hispanic MAE with old hierarchy vs new Hispanic-specific
hierarchy, at the best d_hisp from Checkpoint 1A.

### Checkpoint 1C — Hispanic breakdown analysis

Regardless of whether 1A/1B helped, produce this diagnostic:

```
| Hispanic County Tier | N (holdout) | Hisp MAE (V9.2) | Hisp MAE (V10) | Change |
|----------------------|-------------|-----------------|----------------|--------|
| Low (<10%)           |             |                 |                |        |
| Med (10-25%)         |             |                 |                |        |
| High (25-50%)        |             |                 |                |        |
| Very High (50%+)     |             |                 |                |        |
```

And by sector:
```
| Sector | N | Hisp MAE (V9.2) | Hisp MAE (V10) | Change |
|--------|---|-----------------|----------------|--------|
| Construction (23) |   |         |                |        |
| Accommodation (72)|   |         |                |        |
| Healthcare (62)   |   |         |                |        |
| Manufacturing     |   |         |                |        |
```

This tells us WHERE Hispanic accuracy improved (or didn't).

---

## PHASE 2: Gender Expert Blending

### What this is and why it should help

Race accuracy improved dramatically when Expert D was blended with Expert A
at 75/25. The reason: D and A make different kinds of mistakes. When D
overestimates White, A often has a less extreme estimate, and the blend
pulls toward reality.

Gender currently uses only Expert F (occupation-weighted). No blending has
been tried. This is like having discovered that mixing two paint colors
gives a better result, but only applying that technique to one wall of the
house.

Expert F estimates gender by looking at what jobs an industry typically has
(from BLS occupation data) and what gender those jobs typically are. This
works well when a company's actual job mix matches the industry average. But
companies vary — one "Healthcare" company might be a hospital (heavily
nursing = very female) while another might be an outpatient surgery center
(more balanced). Expert F gives them similar estimates because they share
the same broad industry code.

A county-aware expert (like D or V6-Full) would provide a geographic
correction — saying "in this county, Healthcare workers tend to be X%
female" based on local Census data rather than national occupation patterns.

### Checkpoint 2A — Gender expert comparison

Before blending, understand what each expert produces for gender. Run every
available expert's gender estimate on the permanent holdout and compute
Gender MAE for each:

```
| Expert | Gender MAE | Gender Signed Bias | Gender Wins |
|--------|-----------|-------------------|-------------|
| F (current) | 11.160 |               |             |
| D      |           |                   |             |
| A      |           |                   |             |
| B      |           |                   |             |
| V6-Full|           |                   |             |
```

"Gender Wins" = how many companies this expert has the lowest gender error for.

This tells us which expert is the best blending partner for F.

### Checkpoint 2B — Gender blending grid search

Test blending Expert F with the best candidate from 2A. If no single
candidate stands out, test the top 2-3.

For each candidate expert X, test blend ratios:
F_weight = [1.0, 0.90, 0.85, 0.80, 0.75, 0.70, 0.60]
X_weight = 1.0 - F_weight

(F_weight=1.0 is the V9.2 baseline — pure Expert F, no blending)

For each blend, also grid-search d_gender from [0.3, 0.4, 0.5, 0.6, 0.7, 0.8].

**Report:**

```
| Expert X | F_weight | X_weight | d_gender | Gender MAE | Race MAE | P>20pp | Notes |
|----------|----------|----------|----------|-----------|---------|--------|-------|
| (none)   | 1.00     | 0.00     | 0.50     | 11.160    | 4.403   | 15.4%  | V9.2 baseline |
| D        | 0.85     | 0.15     | 0.50     |           |         |        | |
| D        | 0.75     | 0.25     | 0.50     |           |         |        | |
| ...      |          |          |          |           |         |        | |
```

**Decision rule:**
- Pick the blend that minimizes Gender MAE
- REJECT if Race MAE exceeds 4.55 or P>30pp exceeds 6.5%
- If no blend improves Gender MAE, keep pure Expert F and note this

### Checkpoint 2C — Gender breakdown analysis

```
| Sector | N | Gender MAE (V9.2) | Gender MAE (V10) | Change |
|--------|---|-------------------|------------------|--------|
| Healthcare (62)    | | | | |
| Construction (23)  | | | | |
| Transportation (48)| | | | |
| Finance (52)       | | | | |
| Manufacturing      | | | | |
```

And by region:
```
| Region | N | Gender MAE (V9.2) | Gender MAE (V10) | Change |
|--------|---|-------------------|------------------|--------|
| South     | | | | |
| West      | | | | |
| Northeast | | | | |
| Midwest   | | | | |
```

Healthcare and Construction should show the biggest improvements because
they have the most extreme gender ratios (heavily female and heavily male
respectively), which is where a county-aware correction would help most.

---

## PHASE 3: Confidence / Reliability Indicator

### What this is and why it's the most strategically important change

The model has 56 companies with >30pp error that are essentially irreducible
with census data. Rather than fighting for marginal accuracy gains, V10
builds a system that tells users "we're confident about this estimate" vs
"take this with a grain of salt."

This is like a weather forecast that says "70°F, high confidence" vs "70°F,
but could be anywhere from 55-85°." The second forecast isn't more accurate,
but it's more honest, and that honesty helps people make better decisions.

V9.2's error analysis gives us the recipe for predicting which companies
will have bad estimates:

**High-error predictors (from V9.2 report):**
- County diversity tier: Med-High has 25.2% P>20pp vs 4.0% for Low
- Sector: Healthcare 25.6% P>20pp, Admin/Staffing 20.8%, Transportation 20%
- Region: West 22.5% P>20pp, South 17.6%

### Checkpoint 3A — Build the confidence classifier

Write a function `estimate_confidence(company)` that returns one of three
tiers: GREEN, YELLOW, RED.

The classification uses a points system based on the V9.2 error patterns:

```python
def estimate_confidence(naics_group, diversity_tier, region, company_size=None):
    """
    Predict confidence in the demographic estimate for this company.
    Based on V9.2 error distribution analysis.

    Returns: 'GREEN', 'YELLOW', or 'RED'
    """
    risk_points = 0

    # County diversity tier (strongest predictor)
    if diversity_tier == 'High':
        risk_points += 4
    elif diversity_tier == 'Med-High':
        risk_points += 2
    elif diversity_tier == 'Med-Low':
        risk_points += 1
    # Low = 0 points

    # Sector risk
    HIGH_ERROR_SECTORS = [
        'Healthcare/Social (62)',
        'Admin/Staffing (56)',
        'Transportation (48-49)',
        'Accommodation/Food (72)',
    ]
    if naics_group in HIGH_ERROR_SECTORS:
        risk_points += 2

    # Regional risk
    if region == 'West':
        risk_points += 1
    elif region == 'South':
        risk_points += 1

    # Classification
    if risk_points >= 5:
        return 'RED'     # "Low confidence — take with a grain of salt"
    elif risk_points >= 3:
        return 'YELLOW'  # "Moderate confidence — some uncertainty"
    else:
        return 'GREEN'   # "High confidence — estimate is likely reliable"
```

This is a STARTING POINT. The thresholds (5 for RED, 3 for YELLOW) and
point values should be tuned based on validation data.

### Checkpoint 3B — Validate confidence tiers against actual errors

Run the confidence classifier on the permanent holdout and check whether
the tiers actually predict accuracy:

```
| Tier | N | Race MAE | P>20pp | P>30pp | Hisp MAE | Gender MAE |
|------|---|---------|--------|--------|---------|-----------|
| GREEN  | | | | | | |
| YELLOW | | | | | | |
| RED    | | | | | | |
```

**What "good" looks like:**
- GREEN should have P>20pp < 8% and Race MAE < 3.5
- YELLOW should have P>20pp between 10-25%
- RED should have P>20pp > 25%

If the tiers don't separate cleanly (e.g., GREEN and YELLOW have similar
error rates), adjust the point thresholds or point values and re-run.

**Also show:** What fraction of companies fall in each tier:
```
| Tier | % of companies | Interpretation |
|------|---------------|----------------|
| GREEN  | ~60-70% | "Most companies get reliable estimates" |
| YELLOW | ~20-25% | "Some uncertainty, use with caution" |
| RED    | ~5-15%  | "Low confidence, consider alternative sources" |
```

If RED captures more than 20% of companies, the system is too aggressive
and will undermine user trust. If RED captures less than 5%, it's not
flagging enough of the actual problem cases.

### Checkpoint 3C — Tune thresholds on the permanent holdout

Using the validation from 3B, find the point thresholds that best separate
good estimates from bad ones.

**Optimization target:** Maximize the ratio of P>20pp(RED) / P>20pp(GREEN).
In other words, RED companies should have the highest error rate and GREEN
companies the lowest, with the biggest gap between them.

Try adjusting:
- Point values for each risk factor (e.g., Med-High = 3 instead of 2)
- Thresholds for RED/YELLOW/GREEN boundaries
- Adding additional risk factors (e.g., company size, number of data sources)

**Final report:**

```
| Tier | N | % of holdout | Race MAE | P>20pp | P>30pp |
|------|---|-------------|---------|--------|--------|
| GREEN  | | | | | |
| YELLOW | | | | | |
| RED    | | | | | |
| Ratio (RED P>20pp / GREEN P>20pp) | | | | | |
```

A ratio of 5:1 or higher means the confidence tiers are genuinely useful.

---

## PHASE 4: Per-Tier Blend Weight Exploration (Optional)

### What this is

V9.2 uses a fixed 75% D / 25% A race blend for ALL companies regardless of
context. But different types of companies might benefit from different ratios.
In low-diversity counties, maybe 85% D / 15% A is better (because D is
already accurate there). In high-diversity counties, maybe 60% D / 40% A
is better (because A's corrective signal is more needed).

This is a minor optimization — expect 0.1-0.2pp Race MAE improvement at best.
Only do this phase if Phases 1-3 are complete and there is time remaining.

### Checkpoint 4A — Per-diversity-tier blend search

Grid-search D+A blend weight separately for each diversity tier:

```
| Diversity Tier | Best D weight | Best A weight | Race MAE (tier) | vs V9.2 |
|----------------|--------------|--------------|-----------------|---------|
| Low (<15%)     |              |              |                 |         |
| Med-Low (15-30)|              |              |                 |         |
| Med-High (30-50)|             |              |                 |         |
| High (50%+)    |              |              |                 |         |
| Overall        |              |              |                 |         |
```

Grid: D_weight = [0.60, 0.65, 0.70, 0.75, 0.80, 0.85, 0.90]

**Decision rule:**
- Only adopt per-tier weights if overall Race MAE improves by at least 0.05pp
- AND no individual tier gets more than 0.3pp worse
- If the optimal weights are close to 0.75 for all tiers (within 0.05),
  keep the uniform blend — the complexity isn't worth it

---

## PHASE 5: Final Validation

### Checkpoint 5A — Assemble final V10 configuration

Summarize all changes from Phases 1-4:

```
| Component | V9.2 Config | V10 Config | Changed? |
|-----------|------------|------------|----------|
| Race blend | 75% D + 25% A | (unchanged or new weights) | |
| Race dampening | d_race = 0.85 | (unchanged) | |
| Black adjustment | Retail + Other Mfg | (unchanged) | |
| Hispanic weights | (existing industry+tier) | (unchanged or new hierarchy) | |
| Hispanic dampening | d_hisp = 0.05 | (new value from Phase 1) | |
| Gender expert | Expert F only | (F + X blend from Phase 2, or unchanged) | |
| Gender dampening | d_gender = 0.50 | (new value from Phase 2, or unchanged) | |
| Calibration | dt x region x industry | (unchanged or + hispanic tier) | |
| Confidence tiers | (none) | GREEN/YELLOW/RED from Phase 3 | |
```

### Checkpoint 5B — Validate on PERMANENT holdout (backward comparison)

Run V10 on the permanent holdout:

```
| # | Criterion | V9.2 | V10 | Change | Guard rail | Status |
|---|-----------|------|-----|--------|-----------|--------|
| 1 | Race MAE | 4.403 | | | < 4.55 | |
| 2 | P>20pp | 15.4% | | | < 16.5% | |
| 3 | P>30pp | 5.9% | | | < 6.5% | |
| 4 | Abs Bias | 0.313 | | | < 1.10 | |
| 5 | Hispanic MAE | 6.778 | | | < 6.20 (TARGET) | |
| 6 | Gender MAE | 11.160 | | | < 10.20 (TARGET) | |
| 7 | HC South P>20pp | 13.9% | | | < 15.5% | |
```

If ANY guard rail is violated, identify which Phase caused the regression
and revert that specific change.

### Checkpoint 5C — Validate on V10 SEALED holdout (honest evaluation)

This is the most important result. These companies have never been used in
any optimization or dampening search.

```
| # | Criterion | V9.2 (sealed) | V10 (sealed) | Change |
|---|-----------|---------------|--------------|--------|
| 1 | Race MAE | | | |
| 2 | P>20pp | | | |
| 3 | P>30pp | | | |
| 4 | Abs Bias | | | |
| 5 | Hispanic MAE | | | |
| 6 | Gender MAE | | | |
| 7 | HC South P>20pp | | | |
```

Also show the confidence tier performance on the sealed holdout:

```
| Tier | N | Race MAE | P>20pp | P>30pp | Hisp MAE | Gender MAE |
|------|---|---------|--------|--------|---------|-----------|
| GREEN  | | | | | | |
| YELLOW | | | | | | |
| RED    | | | | | | |
```

If confidence tiers work well on BOTH holdouts, they're genuine signal.
If they only work on the permanent holdout (where they were tuned), they're
overfit.

### Checkpoint 5D — Cross-version comparison table

```
| Metric | V6 (325co) | V9.1 | V9.2 | V10 (perm) | V10 (sealed) |
|--------|-----------|------|------|-----------|-------------|
| Race MAE | 4.203 | 4.483 | 4.403 | | |
| P>20pp | 13.5% | 17.1% | 15.4% | | |
| P>30pp | 4.0% | 7.7% | 5.9% | | |
| Hisp MAE | 7.752 | 6.697 | 6.778 | | |
| Gender MAE | 11.979 | 10.798 | 11.160 | | |
| Confidence tiers | -- | -- | -- | | |
```

---

## PHASE 6: Error Distribution Report

### Checkpoint 6A — Write V10_ERROR_DISTRIBUTION.md

Same format as previous error distribution reports. Must include:

1. **Per-dimension breakdown:** Race MAE, Hispanic MAE, Gender MAE by
   sector, region, and diversity tier

2. **Tail analysis for >30pp companies:** How many remain? Which sectors
   and regions? Did the composition change from V9.2?

3. **Hispanic-specific:** Where did Hispanic accuracy improve most? Which
   county Hispanic tiers benefited? Did the industry-specific Hispanic
   weights interact with the new calibration?

4. **Gender-specific:** Where did gender accuracy improve most? Which
   sectors benefited from blending? Did the blend fix the worst gender
   errors or just improve the average?

5. **Confidence tier analysis:** For each tier, show the full demographic
   accuracy breakdown. Do GREEN companies have uniformly good estimates
   across all dimensions, or just race?

6. **Remaining hard cases:** List the 20 companies with the worst errors
   in V10. For each, show which confidence tier they were assigned. If
   most are RED, the confidence system is working. If many are GREEN,
   the confidence system has blind spots.

---

## What NOT to Do

| Approach | Why Not |
|----------|---------|
| More race calibration tuning | V9.2 exhaustively proved this doesn't help |
| More training data of the same type | Going from 10K to 10.5K barely helped in V9.2 |
| ML residual model (XGBoost on errors) | Only ~10K training companies — high overfitting risk |
| Finer geographic granularity for calibration | Tract-level with 10K training companies would overfit |
| Median-based calibration | V9.2 tested this — P>30pp went from 6.4% to 8.4% (worse) |
| Category-specific dampening (different d for White vs minority) | V9.2 tested — slightly worse |
| Trimmed/winsorized calibration | V9.2 tested — P>30pp went from 6.2% to 7.4% (worse) |
| Architecture changes to race pipeline | Race is frozen. Do not modify D+A blend logic. |
| Rebuild permanent holdout | Kept for backward comparison. V10 sealed holdout is the new honest test. |
| Union status flag | Excluded by design |
| BISG surname geocoding | Excluded by design |

---

## File Summary

### New files to create

| File | Purpose |
|------|---------|
| `select_v10_holdout.py` | Create V10 sealed holdout (SEED=2026031210) |
| `selected_v10_sealed_holdout_1000.json` | V10 sealed holdout companies |
| `expanded_training_v10.json` | Training set excluding both holdouts |
| `run_v10.py` | Main V10 pipeline (Hispanic cal + Gender blend) |
| `estimate_confidence.py` | Confidence tier classifier (GREEN/YELLOW/RED) |
| `V10_ERROR_DISTRIBUTION.md` | Error analysis report |
| `v10_results.json` | Final metrics and config |

### Files to read (do NOT modify these)

| File | Purpose |
|------|---------|
| `verify_v9_2_7of7.py` | Reference for V9.2 architecture |
| `run_v9_2.py` | Reference for V9.2 pipeline |
| `v9_2_7of7_results.json` | V9.2 metrics for comparison |
| `selected_permanent_holdout_1000.json` | Existing permanent holdout |

---

## Evidence Base for V10 Changes

| Change | Why we believe it will help |
|--------|---------------------------|
| Hispanic calibration enablement | d_hisp=0.05 is essentially OFF. Race uses d_race=0.85 successfully. Same technique, untried dimension. |
| Hispanic-specific county tier | Hispanic clustering is more geographically concentrated than overall minority %. A Hispanic-specific tier should match the actual distribution better. |
| Gender expert blending | D+A blend reduced race P>30pp by 5 companies. Same principle: two methods that make different mistakes produce better results when combined. Never tried for gender. |
| Confidence tiers | V9.2 error analysis shows clear patterns (Med-High counties = 25% P>20pp vs Low = 4%). These patterns are predictable WITHOUT knowing the actual answer. |
| Fresh sealed holdout | V9.2 tuned dampening on perm holdout. Gemini's analysis identified this as partial holdout consumption. Fresh set restores honest evaluation. |

---

## Important Reminders

- **Hispanic and Gender are the targets.** Race is frozen. Do NOT try to
  improve race. If a change helps Hispanic/Gender but regresses race by
  more than 0.15pp, reject it.

- **All grid searches happen on TRAINING data only.** The permanent holdout
  is used for backward comparison. The V10 sealed holdout is ONLY for the
  final checkpoint (5C). Do not use the sealed holdout during development.

- **If at any point a change makes things WORSE on the permanent holdout,**
  stop and report before continuing. Don't push through a regression hoping
  the next phase will fix it.

- **Watch for Hispanic calibration bucket overfitting.** If any Hispanic
  calibration offset exceeds 15pp, flag it. Hispanic corrections are noisier
  than race corrections because Hispanic communities are more geographically
  concentrated.

- **The confidence tier system does NOT change any estimates.** It only
  labels them. A RED company gets the same demographic estimate as before —
  it just gets a flag saying "we're not confident about this."

- **Run Phases 1, 2, and 3 independently.** Apply Phase 1, lock it in.
  Then apply Phase 2 on top. Then Phase 3 on top of both. Report after
  each phase so we know what each change contributed.

---

*Reference values (permanent holdout, 954 companies):*
*V9.2: Race 4.403, P>20pp 15.4%, P>30pp 5.9%, Hisp 6.778, Gender 11.160 — 7/7*
*V9.1: Race 4.483, P>20pp 17.1%, P>30pp 7.7%, Hisp 6.697, Gender 10.798 — 5/7*
*V6: Race 4.203, P>20pp 13.5%, P>30pp 4.0%, Hisp 7.752, Gender 11.979 — 7/7 (325co)*
