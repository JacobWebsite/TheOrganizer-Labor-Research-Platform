# V7 Demographics Model — Planning Document

**Date:** 2026-03-09  
**Builds on:** V6 (4.203 race MAE, 11.979 gender MAE, 7/7 criteria passed)  
**Purpose:** Planning only — exact changes to make to each file before execution

---

## The Situation in Plain Language

V6 was trained on 2,702 companies drawn from one of five EEO-1 files. We now know
all five files exist and together contain **14,535 usable companies** (after filtering
for valid NAICS, size ≥ 50, years 2019-2020). That is 5.4x more training data than
V6 had.

The current permanent holdout has only 100 companies. We want 1,000 frozen permanently
and a separate 1,000 as a test holdout — meaning 2,000 total companies are set aside
for evaluation, and roughly 12,000+ go to training.

Everything needs to be rebuilt in the right order because the holdout files and
training file all depend on each other. This document specifies exactly what to
change in each file so Claude Code can execute the changes one step at a time.

---

## Part 1: Data Rebuild — Files to Change (in execution order)

These must be done sequentially. Do not skip steps or run them out of order.

---

### Step 1 — Fix `data_loaders.py`

**Why:** EEO-1 stores ZIP codes as numbers, which strips the leading zero from
states like New Jersey (08512 → 8512) and Massachusetts (02134 → 2134). The
`zip_to_county()` function doesn't pad these back to 5 digits before database
lookup, so ~1,365 companies fail geography resolution and get dropped. This
disproportionately removes the entire Northeast region.

**What to change:** One line in `zip_to_county()`.

Find this function in `data_loaders.py`. It looks like:
```python
def zip_to_county(cur, zipcode):
    if not zipcode:
        return None
    zipcode = str(zipcode).strip()          # <- THIS LINE
    cur.execute(
        "SELECT county_fips FROM zip_county_crosswalk WHERE zip_code = %s LIMIT 1",
        [zipcode])
    row = cur.fetchone()
    return row['county_fips'] if row else None
```

Change the `.strip()` line to `.strip().zfill(5)`:
```python
    zipcode = str(zipcode).strip().zfill(5)  # <- CHANGE TO THIS
```

**What `.zfill(5)` does:** Pads with leading zeros to reach 5 characters. If
the ZIP is already 5 digits nothing changes. If it is 4 digits (e.g. "8512") it
becomes "08512". If it is already a string like "07065" nothing changes.

**Expected result:** ~1,355 more companies resolve geography. Northeast
representation roughly doubles. The usable pool goes from ~13,170 toward ~14,500.

**Verification:** After applying the fix, run a quick count query or print
statement to confirm more ZIPs are resolving than before.

---

### Step 2 — Update `select_permanent_holdout_100.py`

**Why:** The current script was written to select 100 companies. We need 1,000.
The output filename also needs to change so scripts that load it get the right file.

**What to change:**

Find the TARGET constant near the top of the file:
```python
TARGET = 100
```
Change to:
```python
TARGET = 1000
```

Find the SEED constant. Change it from whatever it currently is to:
```python
SEED = 99
```
(Using a different seed than the test holdout (SEED=42) ensures the two holdouts
are selected independently.)

Find the output filename at the bottom of the file where the JSON is saved.
It will reference `selected_permanent_holdout_100.json`. Change to:
```python
output_path = os.path.join(SCRIPT_DIR, 'selected_permanent_holdout_1000.json')
```

Also update the description string inside the JSON output (if one exists) from
"100-company permanent holdout" to "1000-company permanent holdout".

**Do not run this script yet.** Run it only after the ZIP fix in Step 1 is
applied, so the pool it draws from is the full corrected pool.

---

### Step 3 — Update `build_expanded_training_v6.py`

**Why:** This script builds the training set. It currently excludes the 100-company
permanent holdout and the 1,000-company test holdout. The permanent holdout filename
reference needs to change.

**What to change:**

Find the line that loads the permanent holdout file. It will look like:
```python
holdout_path = os.path.join(SCRIPT_DIR, 'selected_permanent_holdout_100.json')
```
Change to:
```python
holdout_path = os.path.join(SCRIPT_DIR, 'selected_permanent_holdout_1000.json')
```

Also verify the print statement that says how many holdout codes were loaded — it
should now confirm 1,000 codes excluded (or close to that, depending on geography
resolution).

**Important:** This script needs to be run **twice** during the rebuild:
- **Pass 1** (Step 5 below): Excludes only the permanent holdout. This produces
  the full training pool from which the test holdout will be drawn.
- **Pass 2** (Step 7 below): Excludes both holdouts. This produces the actual
  training set for the gate.

The script already handles this correctly — the test holdout exclusion only
applies if `selected_test_holdout_1000.json` exists. So Pass 1 (before the test
holdout file exists) will naturally exclude only the permanent holdout.

---

### Step 4 — Update `select_test_holdout_1000.py`

**Why:** This script loads the permanent holdout to verify no overlap. It references
the old 100-company filename.

**What to change:**

Find the line that loads the permanent holdout:
```python
holdout_path = os.path.join(SCRIPT_DIR, 'selected_permanent_holdout_100.json')
```
Change to:
```python
holdout_path = os.path.join(SCRIPT_DIR, 'selected_permanent_holdout_1000.json')
```

Confirm SEED is 42 (different from the permanent holdout's SEED=99 — this ensures
the two 1,000-company sets are independently drawn).

No other changes needed — the stratification logic and TARGET=1000 should already
be correct.

---

### Step 5 — Update `run_ablation_v6.py`

**Why:** The ablation script loads the permanent holdout to know which companies
to evaluate on. It references the old filename.

**What to change:**

Find the line referencing the permanent holdout:
```python
# Will look something like:
holdout_path = os.path.join(SCRIPT_DIR, 'selected_permanent_holdout_100.json')
```
Change to:
```python
holdout_path = os.path.join(SCRIPT_DIR, 'selected_permanent_holdout_1000.json')
```

---

### Step 6 — Update `validate_v6_final.py`

**Why:** The validation script loads a holdout to evaluate against. It references
either the old 100-company or old 400-company permanent holdout.

**What to change:**

Find the line loading the permanent holdout file. The document says line 249:
```python
holdout_path = os.path.join(SCRIPT_DIR, 'selected_permanent_holdout_1000.json')
```
This may already say `_1000.json` (the handoff says "already updated, but pointing
to nonexistent file"). Confirm it says `_1000.json` and leave it if so. No other
changes needed here for the data rebuild.

---

### Step 7 — Execution Order (Summary)

Once all file edits above are made, run in this exact order:

| Step | Command / Action | Output |
|------|-----------------|--------|
| 1 | Apply ZIP fix in `data_loaders.py` | No output file — code change only |
| 2 | Run `select_permanent_holdout_100.py` | `selected_permanent_holdout_1000.json` (1,000 companies) |
| 3 | Run `build_expanded_training_v6.py` (Pass 1) | `expanded_training_v6.json` (~13,500 companies, no test holdout excluded yet) |
| 4 | Run `select_test_holdout_1000.py` | `selected_test_holdout_1000.json` (1,000 companies, verified no overlap) |
| 5 | Run `build_expanded_training_v6.py` (Pass 2) | `expanded_training_v6.json` (~12,500 companies, both holdouts excluded) |
| 6 | **Verify zero overlap** across all three sets before proceeding | Print confirmation |
| 7 | Run `train_gate_v2.py` | `gate_v2.pkl`, `calibration_v2.json` |
| 8 | Run `validate_v6_final.py` on test holdout | V7 test holdout results |
| 9 | Run `validate_v6_final.py` on permanent holdout | V7 permanent holdout results (cross-version comparable) |

---

## Part 2: What V7 Should Improve

Once the data rebuild is complete, these are the opportunities to address —
ordered by expected impact.

---

### Opportunity 1 — Asian Underestimate (Largest Remaining Bias)

**What the problem is:** V6 consistently underestimates Asian share by -2.277
percentage points on average. This is the largest remaining signed bias across
all race categories. It means every company with a significant Asian workforce
(tech, pharma, professional services in coastal metros) gets an estimate that
is too low.

**Why it happens:** The calibration in `calibration_v2.json` applies a global
correction to Asian estimates, but that global correction is being averaged over
industries where Asian underestimation is severe (Information, Professional/Technical
on the West Coast) and industries where it is mild or absent (Construction,
Transportation). A single global number cannot fix both.

**What to change in `train_gate_v2.py`:**

The calibration currently computes one bias per expert per race category:
```python
# Something like: bias['Expert_D']['Asian'] = mean(pred_asian - actual_asian)
# Then correction = -bias * 0.15
```

Change this to compute bias **per industry group per expert per race category**.
Concretely — when the training set grows to 12,000 companies, most industry
groups will have 400-800 examples each. That is enough to estimate a reliable
bias per segment. The calibration hierarchy should be:

- If the industry group has ≥ 50 companies in training: use
  industry-group-specific bias correction
- If 20-49 companies: use broader industry (manufacturing vs services vs
  government) bias correction
- If < 20 companies: use global bias correction (what V6 does)

**What to change in `validate_v6_final.py`:**

When applying calibration, look up the per-industry-group correction instead of
the global one. The company's `naics_group` classification is already computed
before estimation — use it to index into the calibration dictionary.

---

### Opportunity 2 — Gender Overestimate (Systematic +5.2pp Female)

**What the problem is:** V6 overestimates female share by +5.203pp on average
even after CPS shrinkage is applied. The shrinkage is industry-adaptive but
apparently not strong enough for the hardest segments.

**Why it happens:** The G1 gender method uses 50% BLS occupation matrix + 50%
smoothed IPF. The smoothed IPF component still pulls the estimate toward county-
level gender demographics, which tend to be around 50% female. For industries
that are heavily male-dominated (Construction at ~11% female, Transportation at
~25%), the IPF component drags the estimate up.

**What to change in `methodologies_v6.py` / `cached_loaders_v6.py`:**

Adjust the G1 blend weights from 50/50 to be **industry-adaptive**:
- For industries far from 50% female (Construction, Transportation, Mining,
  Manufacturing): increase BLS occupation weight to 70-75%, reduce IPF to 25-30%
- For industries close to 50% (Retail, Finance, Information): keep 50/50
- For heavily female industries (Healthcare at 77%): could go to 60/40 BLS/IPF

The NAICS_GENDER_BENCHMARKS dictionary in `config.py` already has the national
benchmarks — use them to compute how far the industry is from 50% and scale the
blend accordingly:

```python
def get_gender_blend_weight(naics_2digit):
    """Return BLS occupation weight (vs IPF weight) for gender estimation."""
    benchmark = NAICS_GENDER_BENCHMARKS.get(naics_2digit, 45.0)
    distance_from_50 = abs(benchmark - 50.0)
    # More extreme industries: trust occupation data more
    if distance_from_50 > 25:   # e.g. Construction (11%), Healthcare (77%)
        return 0.75  # 75% BLS occupation, 25% IPF
    elif distance_from_50 > 15:  # e.g. Transportation (25%), Retail (50%)
        return 0.60
    else:
        return 0.50  # Industries near 50%: keep current blend
```

**What to change in the CPS shrinkage section of `validate_v6_final.py`:**

The shrinkage currently applies corrections of 31%/24%/14% based on distance
from 50%. Consider tightening these thresholds so more companies get the stronger
31% correction. This is a calibration tweak, not an architectural change — test
a few values on the training set before committing.

---

### Opportunity 3 — Accommodation/Food (Race MAE 13.9pp)

**What the problem is:** Accommodation/Food Svc (NAICS 72 — hotels, restaurants,
bars) has a race MAE of 13.9pp — more than 3x the overall average. V6 only had
5 companies from this sector in the holdout, so this number is noisy, but the
error direction is real. This sector employs large numbers of Hispanic workers
and workers from immigrant communities that are systematically undercounted in
standard Census data.

**Why it matters:** With the expanded data, the holdout will have roughly 50-70
Accommodation/Food companies. The 13.9pp number will become more reliable, and
if it stays high, it becomes the biggest single unresolved problem in the model.

**What to change in `methodologies_v6.py`:**

Add a dedicated Accommodation/Food override that uses a higher geographic weight
for Hispanic estimation and a different race blend:

For NAICS 72 specifically:
- Weight tract-level demographics more heavily (tracts near hotels/restaurants
  tend to have distinctive demographics)
- Weight LODES county more heavily than ACS state — because workforce composition
  in this sector reflects local labor market much more than national industry
  patterns
- Consider hard-routing NAICS 72 to Expert B (tract-heavy 35/25/40 blend) the
  same way NAICS 52/22 are hard-routed to Expert E

**What to change in `config.py`:**

Add NAICS 72 to a special handling dictionary:
```python
HIGH_GEOGRAPHIC_NAICS = {'72', '56', '23'}  # Sectors where workers don't
                                              # reflect registered-county demographics
```

These three sectors share the same problem: the workers don't live near or work
exclusively at the company's registered address. Hotels have seasonal/migrant
workers. Staffing agencies deploy workers to client sites. Construction workers
follow projects. For these, the tract-heavy Expert B is likely better than the
QCEW-adaptive IPF that V6 uses.

---

### Opportunity 4 — Expert F Rebuild (Occupation-Weighted Race)

**What the problem is:** Expert F (occupation-weighted IPF for Manufacturing and
Transportation) was built in V6 but disabled because it used basic smoothed IPF
as its base, which doesn't have variable dampening. It produced a race MAE of
5.136 vs the baseline of 4.372 — significantly worse.

**The insight from the V5 Revision Plan:** Occupation data fails for race because
occupation-to-race correlations are geographically variable. Software developers
are 5% Black nationally but the variance across states is ±6pp. This makes
occupation an unreliable predictor for race across geographies.

**However** — with 12,000 training companies, Expert F could potentially be
validated and calibrated properly if rebuilt correctly.

**What to change in `methodologies_v6.py`:**

Rebuild Expert F with **variable dampening** (from `methodologies_v3.py`)
instead of basic smoothed IPF as the base. The variable dampening uses industry-
specific alpha values from `OPTIMAL_DAMPENING_BY_GROUP` which were tuned on the
training data. Expert F currently skips this and uses a simpler formula.

Test Expert F on the expanded training set before adding it back to the gate.
If it beats baseline for even 2-3 industry groups, route those specific groups
to Expert F and leave the rest on V6-Full.

---

### Opportunity 5 — Gate Improvements (4-digit NAICS, Soft Routing for Expert E)

**4-digit NAICS feature in the gate:**

The gate currently classifies companies into 19 NAICS groups. With 12,000
training companies, many 4-digit NAICS codes will have 30-50 examples each —
enough for the gate to learn fine-grained routing patterns.

**What to change in `train_gate_v2.py`:**

Add `naics_4digit` as a gate feature (it's already noted in the feature list
but needs to be target-encoded — each 4-digit code gets a numerical value based
on its average estimation difficulty in training). This is a standard technique
for encoding high-cardinality categorical variables.

**Soft routing for Expert E:**

Expert E (Finance/Utilities) is currently hard-routed — any NAICS 52 or 22
company goes directly to Expert E and the gate is bypassed. This made sense in
V6 because Finance/Utilities clearly benefits from Expert E (2.252 and 2.625
MAE respectively). But within Finance, there is variation: insurance companies
(NAICS 524) may behave differently from banks (NAICS 522).

**What to change in `validate_v6_final.py`:**

Change the Expert E routing from hard (bypass gate) to soft (gate assigns Expert
E a high initial weight for NAICS 52/22, but other experts can still contribute):

```python
# Current (hard routing):
if naics_group in EXPERT_E_INDUSTRIES:
    prediction = run_expert_e(company)

# Change to (soft routing):
if naics_group in EXPERT_E_INDUSTRIES:
    gate_probs['Expert_E'] = max(gate_probs['Expert_E'], 0.70)  # boost Expert E
    # renormalize other experts to sum with Expert_E to 1.0
    # then blend as normal
```

This still strongly favors Expert E for Finance/Utilities but lets the gate
override in unusual cases.

---

## Part 3: V7 Acceptance Criteria

These are the targets V7 needs to hit, evaluated on the **permanent 1,000-company
holdout**:

| Criterion | V6 Baseline (400 holdout, 325 evaluated) | V7 Target | V7 Stretch |
|-----------|------------------------------------------|-----------|-----------|
| Race MAE | 4.203 pp | **< 3.90 pp** | < 3.70 pp |
| P>20pp | 13.5% | **< 12%** | < 10% |
| P>30pp | 4.0% | **< 3.5%** | < 3.0% |
| Abs Bias | 1.000 | **< 0.85** | < 0.70 |
| Hispanic MAE | 7.752 pp | **< 7.00 pp** | < 6.50 pp |
| Gender MAE | 11.979 pp | **< 10.00 pp** | < 8.50 pp |
| Asian bias | -2.277 pp | **< -1.50 pp** | < -1.00 pp |
| Female bias | +5.203 pp | **< +3.50 pp** | < +2.00 pp |
| Red flag rate | 0.87% | **< 5%** | (keep low) |

Note: V7 targets are tighter because the 1,000-company permanent holdout will
give more reliable segment-level estimates. Some V6 numbers may have been
optimistic due to the 325-company evaluation set being too small for
per-segment reliability.

---

## Part 4: What NOT to Change

Based on what failed in V6 ablation testing — do not attempt these again without
new evidence:

| Thing | Why Not |
|-------|---------|
| Industry-LODES CNS columns for race | Too coarse (20 supersectors), made race MAE worse (+0.343pp) |
| H1 geography-heavy Hispanic | Overfits training, does not generalize |
| OES metro occupation mix for gender | All-industry data, produces ~50% female for everything |
| M9c combined LODES+QCEW | Worse than baseline on holdout (+0.383pp) |
| QWI data | Not in database, skip |

These are documented dead ends. The data is what it is — the opportunity is
in better calibration and routing with the expanded training set, not in
retrying data sources that were already tested and failed.

---

## Part 5: File Change Summary

| File | Change Type | What Changes | Step |
|------|-------------|-------------|------|
| `data_loaders.py` | Bug fix | Add `.zfill(5)` to `zip_to_county()` | Step 1 |
| `select_permanent_holdout_100.py` | Config change | TARGET=1000, SEED=99, output filename | Step 2 |
| `build_expanded_training_v6.py` | Filename update | `_100.json` → `_1000.json` in holdout path | Step 3 |
| `select_test_holdout_1000.py` | Filename update | `_100.json` → `_1000.json` in holdout path | Step 4 |
| `run_ablation_v6.py` | Filename update | `_100.json` → `_1000.json` in holdout path | Step 5 |
| `validate_v6_final.py` | Verify | Confirm already says `_1000.json` | Step 6 |
| `train_gate_v2.py` | Enhancement | Per-segment calibration + 4-digit NAICS feature | Part 2 |
| `methodologies_v6.py` | Enhancement | Adaptive G1 blend weights, Expert F rebuild, NAICS 72 override | Part 2 |
| `cached_loaders_v6.py` | Enhancement | Adaptive blend weight lookup for gender | Part 2 |
| `validate_v6_final.py` | Enhancement | Soft routing for Expert E, per-segment calibration lookup | Part 2 |
| `config.py` | Enhancement | Add HIGH_GEOGRAPHIC_NAICS, update EXPERT_E routing flag | Part 2 |

---

*Last updated: 2026-03-09*  
*Based on: V7_PREPARATION.md handoff, V6_FINAL_REPORT.md, V6_ABLATION_REPORT.md*
