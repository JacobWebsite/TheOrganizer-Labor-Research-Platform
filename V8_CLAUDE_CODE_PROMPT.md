# V8 Demographics Model — Claude Code Implementation Prompt

**Project root:** `C:\Users\jakew\.local\bin\Labor Data Project_real`  
**Working directory:** `scripts\analysis\demographics_comparison\`  
**Database:** PostgreSQL, `olms_multiyear` on localhost (port 5433)  
**Purpose:** Implement targeted V8 improvements based on V7 error distribution analysis
and Claude Code's V7_RECOMMENDATIONS.md review.

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

---

## Background You Need

The model estimates workforce demographics (race, gender, Hispanic share) for
employers that don't publicly report this data. It validates against EEO-1
federal contractor filings (~23,000 federal contractors, gold-standard ground
truth).

**V7 results (what we're building on):**
- Race MAE: 4.388pp | P>20pp: 16.25% | P>30pp: 7.06% — 5/7 criteria passed
- Also fails permanent holdout: Race MAE 4.62 (target <4.50)
- Root cause: Healthcare and Admin/Staffing in South/West are systematically
  miscalibrated. Calibration already applies corrections on average — the
  problem is HIGH VARIANCE within sectors. A nursing home in Vermont and a
  hospital in Atlanta both get the same Healthcare correction, but their
  workforces are totally different.
- 161 companies above 20pp error: 41 Healthcare (25%), 16 Admin/Staffing (10%),
  80 Southern companies (50%) vs 35% of the overall sample.

**V8 goals, in priority order:**
1. Test dampening increase (no retrain needed — free to check)
2. Cap Expert E outside Finance/Utilities (trivial code change)
3. Add Admin/Staffing to YELLOW-minimum confidence tier (honesty fix)
4. Soft boost Expert G for Healthcare companies
5. Add Census region AND county minority-share tier as calibration axes
   for Healthcare and Admin/Staffing (this is the main structural fix)
6. Add 4-digit NAICS as a gate feature
7. Add ABS minority-owner density as a gate feature (files already downloaded)
8. Add EPA Smart Location Database transit score as a gate feature

**Data split — same structure as V7, permanent holdout is FROZEN:**
- Permanent holdout: `selected_permanent_holdout_1000.json` — DO NOT REBUILD,
  DO NOT RE-DRAW. Frozen across all versions for cross-version comparison.
- Test holdout: new `selected_test_holdout_v8_1000.json` (SEED=77)
- Training: everything else (~12,000+ companies)

---

## PHASE 0: Free Tuning — No Retrain Needed

These changes test directly on existing results without rebuilding the gate.
They are free information. Do them first.

### Checkpoint 0A — Test dampening 0.85 and 0.90

**What dampening is:** After computing a calibration correction from training
data, the model only applies `DAMPENING * correction` to avoid overfitting.
Currently DAMPENING = 0.80. Claude Code's review noted that with 1,500+
Healthcare training examples the overfitting risk is low, and 0.90 may close
more of the bias gap.

Find DAMPENING in `validate_v6_final.py` or wherever calibration is applied
at inference time. It will be a constant like:
```python
DAMPENING = 0.80
```

Run validation on the test holdout three times:
1. DAMPENING = 0.80 (current baseline — confirm matches V7 results)
2. DAMPENING = 0.85
3. DAMPENING = 0.90

```
py validate_v6_final.py --holdout selected_test_holdout_1000.json
```

**Report results as a comparison table:**

| DAMPENING | Race MAE | P>20pp | P>30pp | Abs Bias | Notes |
|-----------|---------|--------|--------|----------|-------|
| 0.80 | 4.388 | 16.25% | 7.06% | 0.147 | V7 baseline |
| 0.85 | ? | ? | ? | ? | |
| 0.90 | ? | ? | ? | ? | |

**Decision rule:**
- If 0.90 improves P>20pp or P>30pp without worsening Abs Bias beyond 0.30,
  use 0.90 for V8.
- If 0.85 is better than 0.90, use 0.85.
- If both are worse, keep 0.80 and note this.

Do not proceed to the next checkpoint until you have chosen a dampening value.

---

### Checkpoint 0B — Cap Expert E outside Finance/Utilities

**The problem:** Expert E was designed for Finance (NAICS 52) and Utilities (22).
There are ~150 Finance/Utilities companies in the holdout. But Expert E is being
routed to 272 companies — it is bleeding into sectors where it's not optimal.

Find the soft-routing section in `validate_v6_final.py`. After the existing
floor logic for Finance, add a ceiling for non-Finance companies:

```python
from config import EXPERT_E_INDUSTRIES

# After the floor logic (boost E to 0.70 for Finance/Utilities)...

# NEW: Cap Expert E for non-Finance/Utilities sectors
if naics_group not in EXPERT_E_INDUSTRIES:
    if gate_probs.get('Expert_E', 0) > 0.30:
        excess = gate_probs['Expert_E'] - 0.30
        gate_probs['Expert_E'] = 0.30
        others = {k: v for k, v in gate_probs.items() if k != 'Expert_E'}
        others_total = sum(others.values())
        if others_total > 0:
            scale = (others_total + excess) / others_total
            for k in others:
                gate_probs[k] *= scale
```

Run validation again. Report:
1. How many companies now route primarily to Expert E? (Target: closer to 150)
2. Did P>20pp or P>30pp improve?
3. Which experts gained routing away from Expert E?

**If Expert E cap makes things worse overall, do NOT include it in V8.**

---

### Checkpoint 0C — Force YELLOW minimum for Admin/Staffing

**The reasoning:** Staffing agencies (NAICS 56) deploy workers to client sites.
The company HQ address has almost no relationship to where the workers actually
are. 20% of staffing companies land in the >30pp catastrophic error bucket.
This is a structural data limitation, not a fixable model error. The honest
response is to flag these as lower-confidence rather than presenting wrong
numbers as reliable.

Find the confidence tier assignment logic in `validate_v6_final.py` and add
an override:

```python
from config import HIGH_GEOGRAPHIC_NAICS

# Structural override: sectors with address-workforce mismatch
naics_2 = str(company.get('naics', ''))[:2]
if naics_2 in HIGH_GEOGRAPHIC_NAICS:  # includes '56' Admin/Staffing
    if tier == 'GREEN':
        tier = 'YELLOW'
        tier_override_reason = 'address_mismatch_sector'
```

Run validation again. Report:
1. How many Admin/Staffing companies moved from GREEN to YELLOW?
2. Confirm Race MAE and P>20pp metrics are UNCHANGED (this only affects
   the displayed confidence tier, not the underlying estimate).

---

### Checkpoint 0D — Soft boost Expert G for Healthcare

**The problem:** Expert G (occupation-chain) was routed to only 4 companies
on the test holdout. But it has the smallest White bias of any expert
(-0.9pp vs -4.7 to -20.7pp for other experts). That means its raw estimates
before calibration are already closest to reality for diverse-workforce sectors.

Apply a soft floor for Healthcare (not a hard-route — we want the gate to still
be able to override):

```python
# Soft boost Expert G for Healthcare (NAICS 62)
if naics_group == 'Healthcare/Social (62)':
    current_g = gate_probs.get('Expert_G', 0.0)
    if current_g < 0.20:
        boost = 0.20 - current_g
        gate_probs['Expert_G'] = 0.20
        others = {k: v for k, v in gate_probs.items() if k != 'Expert_G'}
        others_total = sum(others.values())
        if others_total > 0:
            scale = (1.0 - 0.20) / others_total
            for k in others:
                gate_probs[k] = others[k] * scale
```

Run validation. Report:
1. How many Healthcare companies now route to Expert G? (Was 4)
2. Did Healthcare Race MAE improve? (Was 6.086pp)
3. Did P>20pp or P>30pp change?

**If Expert G boost makes Healthcare worse, revert it.**

---

After Checkpoints 0A–0D, summarize what's being kept:

```
PHASE 0 SUMMARY:
DAMPENING: [chosen value and rationale]
Expert E cap: [keep/revert — state why]
Staffing YELLOW floor: [keep regardless of MAE — communication fix]
Expert G Healthcare boost: [keep/revert — state why]

Combined Phase 0 results vs V7 baseline:
[table showing Race MAE, P>20pp, P>30pp with all Phase 0 changes active]
```

Wait for approval before proceeding to Phase 1.

---

## PHASE 1: Data Pipeline — Build New External Feature Tables

### Checkpoint 1A — Build ABS minority-owner density table

**What this is:** The Census Annual Business Survey (ABS) counts how many
businesses in each county and industry are owned by people of different
racial/ethnic backgrounds. It anonymizes individual employers, so you cannot
look up whether Company X is minority-owned. But you CAN compute: "In Dallas
County, TX, among healthcare businesses, 38% are minority-owned." That
area-level percentage tells you something different from just knowing the
county's general population demographics.

**Files already downloaded:**
```
C:\Users\jakew\.local\bin\Labor Data Project_real\New Data sources 2_27\ABS_latest_state_local\csv\
```

Key file: `ABS_2023_abscb_county.csv`
Columns: `NAME`, `GEO_ID`, `NAICS2022`, `RACE_GROUP`, `ETH_GROUP`,
`FIRMPDEMP`, `state`, `county`

**Write new script `build_abs_owner_density.py`:**

1. Load the CSV. Parse FIPS as: `fips = state.zfill(2) + county.zfill(3)`

2. For each `fips × naics_2digit` combination, compute:
   - `total_firms`: rows where `RACE_GROUP == '00'` (all-owners total)
   - `minority_firms`: rows where RACE_GROUP is NOT '00' AND NOT '96'
     (white alone), and FIRMPDEMP is numeric (not 'D' or 'S' — suppressed)
   - `minority_owner_share` = minority_firms / total_firms
   - `black_owner_share`: RACE_GROUP == '20' (Black or African American alone)
   - `hispanic_owner_share`: ETH_GROUP == '30' (Hispanic or Latino)

3. Handle suppressed data ('D', 'S' values) as NULL — do not count them.
   If >50% of minority categories are suppressed, set minority_owner_share
   to NULL rather than computing from partial data.

4. Add `conf_flag BOOLEAN`: True when total_firms >= 5.

5. Write to PostgreSQL table `abs_owner_density` and backup JSON
   `abs_owner_density.json` keyed as `"FIPS5_NAICS2"`.

**Verify:**
1. Total rows in output
2. Spot-check Jefferson County, AL (FIPS 01073), NAICS 62 — minority_owner_share?
3. Distribution: min, 25th, median, 75th, max of minority_owner_share
4. How many rows have conf_flag = False?

---

### Checkpoint 1B — Build EPA Smart Location Database transit score table

**What this is:** The EPA pre-computed transit accessibility scores for every
Census block group (~220,000 neighborhoods) in the US by processing GTFS data
from every transit agency. We download this one pre-built table instead of
building our own pipeline. The key signal: is this employer in a location
workers without cars can reach?

**Download — exact URL:**
```
https://edg.epa.gov/EPADataCommons/public/OA/SLD/SmartLocationDatabaseV3.zip
```
(~400MB, file geodatabase)

CSV version on Data.gov (easier to work with):
https://catalog.data.gov/dataset/smart-location-database8
→ `EPA_SmartLocationDatabase_V3_Jan_2021_Final.csv`

**Variables needed:**

| Variable | Description |
|----------|-------------|
| `GEOID10` | 12-digit block group ID (join key) |
| `D4a` | Number of transit routes within 0.5 miles |
| `D4c` | Transit frequency, afternoon peak (trips/hr within 0.5mi) |
| `D5tr` | Jobs accessible by transit within 45 min |
| `NatWalkInd` | Walkability Index (1-20) |

**Write new script `build_sld_transit_table.py`:**

1. Load SLD file, keep the 5 columns above.

2. Compute `transit_score` (0–100):
   ```python
   import numpy as np
   def compute_transit_score(d4a, d4c, d5tr):
       if pd.isna(d4a) or d4a == 0:
           return 0.0
       score = (d4a * 5) + (d4c * 2) + (np.log1p(d5tr) * 3)
       return min(100.0, float(score))
   ```

3. Compute `transit_tier`:
   - `'none'` if d4a == 0 or NaN
   - `'minimal'` if d4a 1–2 AND d4c < 5
   - `'moderate'` if d4a 3–5 OR d4c 5–20
   - `'high'` if d4a > 5 OR d4c > 20

4. Write to PostgreSQL `sld_transit_scores` and backup `sld_transit_scores.json`
   keyed by `geoid10`.

5. Add `get_transit_score(zipcode)` to `cached_loaders_v6.py` using the
   existing ZIP → tract crosswalk (from `build_zip_tract_crosswalk.py`).
   Average transit_score across block groups in the ZIP if multiple.

**Verify:**
1. Total rows loaded
2. Spot checks:
   - ZIP 10001 (Manhattan): transit_tier = 'high', score > 80
   - ZIP 39401 (rural MS): 'none' or 'minimal', score < 10
   - ZIP 30092 (suburban Atlanta): 'minimal' or 'moderate'
3. Distribution of transit_tier across all block groups
4. % of block groups with D4a == 0

---

## PHASE 2: Code Changes — No Scripts Run Yet

### Checkpoint 2A — Add Census region and county minority-share tier to `config.py`

Two calibration axes for Healthcare and Admin/Staffing:
- **Census region (4 categories):** coarser, always available
- **County minority-share tier (3 categories):** finer, captures suburban
  Atlanta vs. rural Alabama (both "South" but very different)

County tier bins from ACS data already in the database:
- `'low'` = county <20% non-white residents
- `'mid'` = 20–40%
- `'high'` = >40%

Add to `config.py`:

```python
# ============================================================
# V8 parameters
# ============================================================

STATE_TO_CENSUS_REGION = {
    'CT': 'Northeast', 'ME': 'Northeast', 'MA': 'Northeast',
    'NH': 'Northeast', 'RI': 'Northeast', 'VT': 'Northeast',
    'NJ': 'Northeast', 'NY': 'Northeast', 'PA': 'Northeast',
    'IL': 'Midwest', 'IN': 'Midwest', 'MI': 'Midwest',
    'OH': 'Midwest', 'WI': 'Midwest', 'IA': 'Midwest',
    'KS': 'Midwest', 'MN': 'Midwest', 'MO': 'Midwest',
    'NE': 'Midwest', 'ND': 'Midwest', 'SD': 'Midwest',
    'DE': 'South', 'FL': 'South', 'GA': 'South',
    'MD': 'South', 'NC': 'South', 'SC': 'South',
    'VA': 'South', 'DC': 'South', 'WV': 'South',
    'AL': 'South', 'KY': 'South', 'MS': 'South',
    'TN': 'South', 'AR': 'South', 'LA': 'South',
    'OK': 'South', 'TX': 'South',
    'AZ': 'West', 'CO': 'West', 'ID': 'West',
    'MT': 'West', 'NV': 'West', 'NM': 'West',
    'UT': 'West', 'WY': 'West', 'AK': 'West',
    'CA': 'West', 'HI': 'West', 'OR': 'West', 'WA': 'West',
}

def get_census_region(state_abbr):
    return STATE_TO_CENSUS_REGION.get(str(state_abbr).upper(), 'Unknown')

def get_county_minority_tier(minority_pct):
    """
    Bin county non-white % into 3 tiers.
    minority_pct: float 0-100 from ACS county demographics.
    """
    if minority_pct is None:
        return 'unknown'
    if minority_pct < 20.0:
        return 'low'
    elif minority_pct < 40.0:
        return 'mid'
    else:
        return 'high'

# Industries where regional + county-diversity calibration is applied
REGIONAL_CALIBRATION_INDUSTRIES = {
    'Healthcare/Social (62)',
    'Admin/Staffing (56)',
}

# Minimum examples required for a region/tier-specific correction
REGIONAL_CAL_MIN_N = 30
```

**Show:** Full diff.

---

### Checkpoint 2B — Extend calibration computation in `train_gate_v2.py`

Currently: `expert → industry_group → correction`

For REGIONAL_CALIBRATION_INDUSTRIES, also compute:
- `expert → industry_group|region:REGION → correction`
- `expert → industry_group|county_tier:TIER → correction`

Fallback hierarchy at prediction time:
county_tier → region → industry → global

```python
from config import (REGIONAL_CALIBRATION_INDUSTRIES, REGIONAL_CAL_MIN_N,
                    get_census_region, get_county_minority_tier)

for expert in EXPERTS:
    for industry_group, industry_slice in slices.items():
        calibration[expert][industry_group] = compute_correction(industry_slice)

        if industry_group in REGIONAL_CALIBRATION_INDUSTRIES:
            # Region sub-segments
            for region in ['Northeast', 'Midwest', 'South', 'West']:
                key = f"{industry_group}|region:{region}"
                sub = [c for c in industry_slice
                       if get_census_region(c.get('state','')) == region]
                if len(sub) >= REGIONAL_CAL_MIN_N:
                    calibration[expert][key] = compute_correction(sub)

            # County diversity tier sub-segments
            for tier in ['low', 'mid', 'high']:
                key = f"{industry_group}|county_tier:{tier}"
                sub = [c for c in industry_slice
                       if get_county_minority_tier(
                           c.get('county_minority_pct')) == tier]
                if len(sub) >= REGIONAL_CAL_MIN_N:
                    calibration[expert][key] = compute_correction(sub)
```

Also add `county_minority_pct` to the training data extraction loop —
query ACS county demographics for each company's county_fips.

**Show:** Full diff. Print N for every region × industry and county_tier ×
industry cell. All must exceed REGIONAL_CAL_MIN_N = 30.

---

### Checkpoint 2C — Update calibration lookup in `validate_v6_final.py`

```python
def get_calibration_correction(calibration, expert, industry_group,
                                state, county_minority_pct):
    """
    Fallback hierarchy:
    1. industry|county_tier (most specific)
    2. industry|region
    3. industry
    4. _global
    """
    if industry_group in REGIONAL_CALIBRATION_INDUSTRIES:
        tier = get_county_minority_tier(county_minority_pct)
        tier_key = f"{industry_group}|county_tier:{tier}"
        if tier_key in calibration.get(expert, {}):
            return calibration[expert][tier_key], 'county_tier'

        region = get_census_region(state)
        region_key = f"{industry_group}|region:{region}"
        if region_key in calibration.get(expert, {}):
            return calibration[expert][region_key], 'region'

    correction = calibration[expert].get(
        industry_group,
        calibration[expert].get('_global', {})
    )
    level = 'industry' if industry_group in calibration[expert] else 'global'
    return correction, level
```

Also look up `county_minority_pct` from the database for each company
at prediction time and pass it to this function.

Log which calibration tier was used per company — report the distribution
in Phase 5 validation.

**Show:** Full diff.

---

### Checkpoint 2D — Add 4-digit NAICS as gate feature

In `train_gate_v2.py`, add to the feature vector:

```python
naics4 = str(company.get('naics', ''))[:4]
features['naics4_encoded'] = encode_naics4(naics4)
```

Build vocabulary from training data and save as `naics4_vocab.pkl`.
Load it in `validate_v6_final.py` for inference.

**Show:** Full diff for both files. Print the top 20 most common 4-digit
NAICS codes in training data with their counts.

---

### Checkpoint 2E — Add ABS minority-owner density as gate feature

Add `get_abs_owner_density()` to `cached_loaders_v6.py` (loads from
`abs_owner_density.json`, returns minority_owner_share for county × naics2,
None if missing).

In `train_gate_v2.py`, add to feature vector:
```python
abs_share = get_abs_owner_density(
    county_fips=company.get('county_fips'),
    naics2=str(company.get('naics', ''))[:2]
)
features['abs_minority_owner_share'] = abs_share if abs_share is not None else -1.0
```

Use -1.0 as sentinel (missing) vs 0.0 (genuinely zero minority-owned firms).

**Show:** Full diff.

---

### Checkpoint 2F — Add transit score as gate feature

In `train_gate_v2.py`, add:
```python
transit_score, transit_tier = get_transit_score(company.get('zipcode'))
features['transit_score'] = transit_score if transit_score is not None else -1.0
tier_enc = {'none': 0, 'minimal': 1, 'moderate': 2, 'high': 3}
features['transit_tier_encoded'] = tier_enc.get(transit_tier, -1)
```

**Show:** Full diff.

---

## PHASE 3: New Test Holdout

### Checkpoint 3A — Draw V8 test holdout (SEED=77)

```
py select_test_holdout_1000.py --output selected_test_holdout_v8_1000.json --seed 77
```

Add `--output` and `--seed` flag support if not already present (show diff).

Verify zero overlap with permanent holdout:
```python
import json
with open('selected_permanent_holdout_1000.json') as f:
    perm = set(json.load(f)['company_ids'])
with open('selected_test_holdout_v8_1000.json') as f:
    test_v8 = set(json.load(f)['company_ids'])
assert len(perm & test_v8) == 0, "CONTAMINATION"
print(f"PASS: zero overlap. V8 test N={len(test_v8)}")
```

---

### Checkpoint 3B — Rebuild training set

```
py build_expanded_training_v6.py
```

Must exclude both `selected_permanent_holdout_1000.json` and
`selected_test_holdout_v8_1000.json`. Add V8 filename to exclusion list
if needed (show diff).

Verify clean separation:
```python
assert len(training_ids & perm) == 0, "PERM CONTAMINATION"
assert len(training_ids & test_v8) == 0, "TEST CONTAMINATION"
print(f"Training N: {len(training_ids)}")  # expect ~12,000-12,500
```

---

## PHASE 4: Gate Training

### Checkpoint 4A — Train Gate V2 with V8 features

```
py train_gate_v2.py
```

Expected runtime: 3–5 hours. Show progress. Do not interrupt.

**When complete, verify:**
1. `gate_v2.pkl`, `calibration_v2.json`, `naics4_vocab.pkl` all written
2. Feature importances: `naics4_encoded`, `abs_minority_owner_share`,
   `transit_score` all have non-zero importance
3. Regional calibration: Healthcare South vs Healthcare Midwest have
   DIFFERENT White/Black corrections — print side by side
4. County-tier calibration: Healthcare high-diversity vs low-diversity
   tier differ substantially — print side by side
5. N counts for all calibration cells — all must exceed 30

---

## PHASE 5: Validation

### Checkpoint 5A — Validate on V8 test holdout

```
py validate_v6_final.py --holdout selected_test_holdout_v8_1000.json
```

**Full results table:**

| Criterion | V7 Actual | V8 Target | V8 Result | Status |
|-----------|-----------|-----------|-----------|--------|
| Race MAE | 4.388 pp | < 3.90 pp | ? | |
| P>20pp | 16.25% | < 12% | ? | |
| P>30pp | 7.06% | < 6% | ? | |
| Abs Bias | 0.147 | < 0.85 | ? | |
| Hispanic MAE | 6.420 pp | < 7.00 pp | ? | |
| Gender MAE | 11.687 pp | < 10.00 pp | ? | |
| Asian signed bias | ~-2.3 pp | < -1.50 pp | ? | |
| Female signed bias | ~+5.2 pp | < +3.50 pp | ? | |
| Red flag rate | 2.5% | < 5% | ? | |

**Regional breakdown:**

| Region | Race MAE | P>20pp | N |
|--------|---------|--------|---|
| South | ? | ? | ? |
| Midwest | ? | ? | ? |
| Northeast | ? | ? | ? |
| West | ? | ? | ? |

**Per-industry Race MAE:**

| Industry | V7 MAE | V8 MAE | Change |
|----------|--------|--------|--------|
| Healthcare/Social (62) | 6.086 | ? | ? |
| Admin/Staffing (56) | 7.018 | ? | ? |
| Accommodation/Food (72) | 5.315 | ? | ? |

**Calibration tier usage:** Report % of companies using county_tier vs
region vs industry vs global corrections.

---

### Checkpoint 5B — Validate on permanent holdout (official cross-version benchmark)

```
py validate_v6_final.py --holdout selected_permanent_holdout_1000.json
```

Same metrics table. V7 permanent holdout Race MAE was 4.62pp (failed target
of <4.50). This is the official comparison number for V7 vs V8.

---

## PHASE 6: Error Distribution Analysis

### Checkpoint 6A — Generate V8 error distribution report

Run the same analysis as `V7_ERROR_DISTRIBUTION.md`. Write to `V8_ERROR_DISTRIBUTION.md`.

Key questions:
1. **South bucket shrink?** V7: South = 47–52% of >20pp. V8 target: ≤40%.
2. **Healthcare improve?** V7 MAE: 6.086. Target: <5.0.
3. **Admin/Staffing improve?** V7 MAE: 7.018. Target: <6.0.
4. **New features detecting hard cases?**
   For the >30pp error bucket, print average transit_score,
   average abs_minority_owner_share, distribution of county_minority_tier.
5. **Calibration tier for remaining hard cases?**
   For companies still in >20pp bucket, what % used county_tier corrections
   vs. falling through to industry/global?

---

## What NOT to Do

| Approach | Why Not |
|----------|---------|
| Rebuild permanent holdout | Frozen forever — breaks cross-version comparison |
| Hard-route Expert G for Healthcare | Soft boost (0.20 floor) is safer; hard-route risks regression |
| Dedicated Healthcare Expert H | High effort; defer to V9 if V8 doesn't close the gap |
| Architecture simplification | Strategic V9 question; don't destabilize V8 |
| Union status flag | Excluded by design |
| BISG surname geocoding | Excluded by design |
| Credential inflation scoring | Requires job posting data not available |
| Industry-LODES CNS columns for race | +0.343pp MAE worse in V6 ablation |
| National CPS for occupation demographics | No geographic variation |

---

## File Change Summary

| File | Changes |
|------|---------|
| `config.py` | Add STATE_TO_CENSUS_REGION, get_census_region(), get_county_minority_tier(), REGIONAL_CALIBRATION_INDUSTRIES, REGIONAL_CAL_MIN_N |
| `train_gate_v2.py` | Regional + county-tier calibration; naics4, abs_minority_owner_share, transit_score, transit_tier features; save naics4_vocab.pkl |
| `validate_v6_final.py` | get_calibration_correction() with fallback hierarchy; Expert E ceiling; Expert G soft boost; staffing YELLOW floor; load naics4_vocab.pkl |
| `cached_loaders_v6.py` | Add get_abs_owner_density(); add get_transit_score() |

## New Files

| File | Purpose |
|------|---------|
| `build_abs_owner_density.py` | ETL: minority-owner density from ABS CSV |
| `build_sld_transit_table.py` | ETL: transit score from EPA SLD |
| `abs_owner_density.json` | Backup lookup for ABS data |
| `sld_transit_scores.json` | Backup lookup for transit scores |
| `naics4_vocab.pkl` | 4-digit NAICS encoding vocabulary |
| `selected_test_holdout_v8_1000.json` | V8 test holdout, SEED=77 |
| `V8_ERROR_DISTRIBUTION.md` | Error analysis matching V7 format |

---

## Research Citations for Every V8 Change

| Change | Citation |
|--------|---------|
| Dampening 0.85–0.90 | V7_RECOMMENDATIONS.md (Claude Code, 2026-03-10): 1,500+ Healthcare training examples make overfitting risk low |
| Expert E ceiling (non-Finance) | V7_RECOMMENDATIONS.md: Expert E routing 272 companies vs ~150 Finance in holdout |
| Expert G soft boost (Healthcare) | V7_RECOMMENDATIONS.md: Expert G has smallest White raw bias (-0.9pp vs -4.7 to -20.7pp for other experts) |
| Admin/Staffing YELLOW floor | V7_RECOMMENDATIONS.md + V7_ERROR_DISTRIBUTION.md: 20% of NAICS 56 in >30pp bucket; HQ address structurally mismatches worker locations |
| Regional calibration (South/West) | V7_ERROR_DISTRIBUTION.md: South = 47–52% of >20pp bucket despite 35% sample; White over-predicted 24×, Black under-predicted 21× in >30pp bucket |
| County minority-tier calibration | V7_RECOMMENDATIONS.md Rec #2: county minority share captures sub-regional variation more precisely than 4 broad Census regions |
| 4-digit NAICS gate feature | UC Berkeley Labor Center (2015), "Racial and Gender Segregation in the Restaurant Industry": significant demographic variation within NAICS 72 by restaurant type; EPI/Stuesse & Dollar (2020): beef vs. poultry processing dramatically different Hispanic workforce shares |
| ABS minority-owner density | Stoll, Raphael & Holzer (2001), IRP Discussion Paper 1236-01: +21pp Black workforce share in Black-owned vs. white-owned firms in same industry/county; Kerr & Kerr (2021), HBS WP 21-101: co-ethnic hiring effects strongest where local ethnic labor pool is largest |
| EPA SLD transit score | Holzer & Ihlanfeldt (1996), *New England Economic Review*: transit proximity explains major portion of Black employment rate differences between central-city and suburban firms; Pew Research Center (2016): Black workers commute by transit at ~6× white rate, Hispanic at ~3× white rate |

---

## EPA Data Download Links

**Main SLD download (~400MB, file geodatabase):**
https://edg.epa.gov/EPADataCommons/public/OA/SLD/SmartLocationDatabaseV3.zip

**CSV on Data.gov (easier to work with):**
https://catalog.data.gov/dataset/smart-location-database8
File: `EPA_SmartLocationDatabase_V3_Jan_2021_Final.csv`

**Technical documentation (variable definitions):**
https://www.epa.gov/system/files/documents/2023-10/epa_sld_3.0_technicaldocumentationuserguide_may2021_0.pdf

**DBF-only transit variables (8MB — fastest download if you only need transit):**
https://edg.epa.gov/data/Public/OP/SLD/SLD_Trans45_DBF.zip

---

*Generated: 2026-03-11*  
*Incorporates: V7_CLAUDE_CODE_PROMPT.md + V7_RECOMMENDATIONS.md (Claude Code review, 2026-03-10)*  
*V7 baseline: Race MAE 4.388pp | P>20pp 16.25% | P>30pp 7.06% — 5/7 criteria*  
*V8 goal: P>20pp < 12% | P>30pp < 6% | Race MAE < 3.90pp*
