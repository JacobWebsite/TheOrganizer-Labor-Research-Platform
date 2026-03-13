# Demographics Estimation V5: Claude Code Implementation Plan

**Project:** `C:\Users\jakew\Downloads\labor-data-project`
**Scripts location:** `scripts/analysis/demographics_comparison/`
**Database:** `olms_multiyear` (PostgreSQL, localhost)
**EEO-1 ground truth:** `EEO_1/objectors_with_corrected_demographics_2026_02_25.csv` (encoding: cp1252)

---

## How to Read This Document

This plan is split into **4 separate Claude Code runs**. Each run is self-contained with a clear goal, explicit checkpoints, and a verification step before moving on. Do not start the next run until the current one passes its verification.

**Why 4 runs and not 1?**
Each run produces output that the next run depends on. Gate v0 needs the prediction tables from Run 1. The expert family in Run 3 needs the scoring infrastructure from Run 2. Splitting them also keeps each session focused enough that nothing gets lost or half-finished.

---

## Before Any Run: Read These Files First

Every Claude Code session should begin by reading:

```
scripts/analysis/demographics_comparison/methodologies_v3.py
scripts/analysis/demographics_comparison/methodologies_v4.py  (if it exists; may be named differently)
scripts/analysis/demographics_comparison/cached_loaders_v3.py
scripts/analysis/demographics_comparison/run_comparison_400_v3.py
```

Also check what JSON company files exist:
```
scripts/analysis/demographics_comparison/selected_200.json
scripts/analysis/demographics_comparison/selected_holdout_200.json
scripts/analysis/demographics_comparison/selected_400.json
scripts/analysis/demographics_comparison/selected_holdout_v3.json
```

And the most recent V4 results CSV — look for files named like `comparison_v4_detailed.csv` or similar in `scripts/analysis/demographics_comparison/`.

---

## Run 1: Immediate Fixes + PUMS Loading

**Goal:** Fix the known broken thing, add the smoothing patch, load the PUMS data, and wire the existing methods to use metro-level geography instead of state-level.

**Estimated session length:** Medium (several file edits + one database load)

---

### Checkpoint 1.1 — Fix the Admin/Staffing routing bug

In the M8 Adaptive Router (wherever it lives in the methodology files), find the routing rule for Admin/Staffing (NAICS group 56). It currently routes to M4e. Change it to route to M1b.

This is a confirmed error from V4 results: M4e was the worst-performing method in V4 overall, and M1b wins Admin/Staffing at 5.7 MAE.

**Verify:** Search the codebase for "M4e" or "56" near routing logic. Confirm the change is in exactly one place and nothing else references the old route.

---

### Checkpoint 1.2 — Add smoothing to all IPF methods

This fixes zero-collapse: when ACS or LODES reports zero workers in a category, the IPF formula currently multiplies that zero and produces zero in the output. The real answer is almost never exactly zero — it's a data gap.

**The fix:** Before any IPF formula runs, add a small floor value to every racial category in both the ACS input and the LODES input. The floor should be 0.1 percentage points (i.e., 0.001 in proportion terms).

In plain terms: if ACS says AIAN = 0.000, replace it with 0.001 before running the formula. Do this for every category, every method, every input source.

**Which methods to update:** M3 IPF, M3b, M3c, M3e, M3d (if it still exists). Any method that multiplies ACS × LODES together.

**Which methods to leave alone:** M1b, M2c — these are weighted averages, not multiplicative. A zero in a weighted average doesn't collapse the way it does in IPF.

**Implementation pattern:**
```python
SMOOTHING_FLOOR = 0.001  # 0.1 percentage points

def apply_floor(dist: dict) -> dict:
    """Ensure no category is exactly zero before IPF runs."""
    floored = {k: max(v, SMOOTHING_FLOOR) for k, v in dist.items()}
    total = sum(floored.values())
    return {k: v / total for k, v in floored.items()}
```

Call `apply_floor()` on both ACS and LODES inputs before the geometric mean step in every IPF method.

**Verify:** Pick a company from the 998-company set that is in Finance/Insurance. Run M3 IPF on it before and after the change. Confirm the output doesn't change meaningfully for normal cases (it won't — the floor only matters when a category is actually zero).

---

### Checkpoint 1.3 — Add composite scoring metric

The existing evaluation only reports race MAE. We need to also report tail metrics that catch catastrophic misses.

**New metric to compute alongside MAE:**

```python
def composite_score(predictions_df):
    """
    predictions_df has columns: company_id, actual_white, actual_black,
    actual_asian, actual_hispanic, actual_aian, actual_nhopi, actual_two_plus,
    pred_white, pred_black, pred_asian, pred_hispanic, pred_aian, pred_nhopi, pred_two_plus
    """
    # For each company, find the max error across all race categories
    cat_cols = ['white', 'black', 'asian', 'aian', 'nhopi', 'two_plus']
    
    max_errors = predictions_df.apply(
        lambda row: max(abs(row[f'actual_{c}'] - row[f'pred_{c}']) for c in cat_cols),
        axis=1
    )
    
    race_mae = predictions_df.apply(
        lambda row: sum(abs(row[f'actual_{c}'] - row[f'pred_{c}']) for c in cat_cols) / len(cat_cols),
        axis=1
    ).mean()
    
    p_over_20 = (max_errors > 20).mean()
    p_over_30 = (max_errors > 30).mean()
    
    # Signed bias per category (positive = overestimate)
    signed_biases = {
        c: (predictions_df[f'pred_{c}'] - predictions_df[f'actual_{c}']).mean()
        for c in cat_cols
    }
    mean_abs_signed_bias = sum(abs(v) for v in signed_biases.values()) / len(cat_cols)
    
    composite = (race_mae
                 + 0.20 * p_over_20 * 100
                 + 0.35 * p_over_30 * 100
                 + 0.15 * mean_abs_signed_bias)
    
    return {
        'race_mae': round(race_mae, 3),
        'p_over_20': round(p_over_20, 4),
        'p_over_30': round(p_over_30, 4),
        'mean_abs_signed_bias': round(mean_abs_signed_bias, 3),
        'composite_score': round(composite, 3),
        'signed_bias': {k: round(v, 3) for k, v in signed_biases.items()}
    }
```

Add this function to the evaluation script. Run it against the existing V4 prediction CSV and print results for every method. **Save this output** — it is the baseline that V5 must beat.

**Verify:** The composite score for M3b should be higher (worse) than M3e on the combined evaluation set, because M3e has lower race MAE. M3b should score better on tail metrics specifically — that's why it remains the production baseline.

---

### Checkpoint 1.4 — Load PUMS metro data into database

The processed PUMS CSV (`acs_occ_demo_profiles.csv`) already exists on disk. It was built from a 29 GB raw IPUMS extract and uses MET2013 (metro area codes) as the geographic unit.

**Task:** Find this file (check `scripts/analysis/demographics_comparison/` and parent directories) and load it into a new PostgreSQL table.

```sql
CREATE TABLE IF NOT EXISTS pums_metro_demographics (
    met2013         VARCHAR(10),
    naics_group     VARCHAR(10),
    race_white      FLOAT,
    race_black      FLOAT,
    race_asian      FLOAT,
    race_hispanic   FLOAT,
    race_aian       FLOAT,
    race_nhopi      FLOAT,
    race_two_plus   FLOAT,
    sex_female      FLOAT,
    n_respondents   INTEGER,
    PRIMARY KEY (met2013, naics_group)
);

CREATE INDEX IF NOT EXISTS idx_pums_metro_naics
    ON pums_metro_demographics (met2013, naics_group);
```

If the CSV column names don't match exactly, inspect them first (`pd.read_csv(..., nrows=5).columns`) and map accordingly.

**Also check:** Does `zip_geography` (or a similar table) have a column for CBSA or MET2013 codes? Run:
```sql
SELECT column_name FROM information_schema.columns
WHERE table_name = 'zip_geography';
```

If a CBSA column exists: you're done, the bridge is already there.
If not: load the Census county-to-CBSA crosswalk. It is a free public file from census.gov — search "Census county CBSA crosswalk 2023". Create a minimal table:

```sql
CREATE TABLE IF NOT EXISTS county_cbsa_xwalk (
    county_fips  VARCHAR(5),
    cbsa_code    VARCHAR(5),
    cbsa_title   VARCHAR(200)
);
```

**Verify:** 
```sql
SELECT COUNT(*) FROM pums_metro_demographics;
SELECT met2013, naics_group, race_white, n_respondents 
FROM pums_metro_demographics 
LIMIT 10;
```
Expect several thousand rows. Spot-check that `n_respondents` values are in the hundreds to thousands range for major metro × industry combinations.

---

### Checkpoint 1.5 — Write get_pums_demographics() in data_loaders

Add to `cached_loaders_v3.py` (or create `cached_loaders_v5.py` as a new file that imports from v3):

```python
def get_pums_demographics(naics_group: str, cbsa_code: str,
                           min_respondents: int = 30) -> dict | None:
    """
    Returns metro-level PUMS demographic estimates for a given industry
    and metro area. Returns None if sample is too small (< min_respondents)
    or if cbsa_code is None/empty (rural/non-metro employer).
    
    Return format matches get_acs_demographics() exactly so callers
    can drop this in as a replacement.
    """
    if not cbsa_code:
        return None
    
    query = """
        SELECT race_white, race_black, race_asian, race_hispanic,
               race_aian, race_nhopi, race_two_plus, sex_female,
               n_respondents
        FROM pums_metro_demographics
        WHERE met2013 = %s AND naics_group = %s
    """
    # ... execute query, check n_respondents >= min_respondents
    # ... if below threshold, return None
    # ... return dict with same keys as get_acs_demographics()
```

**Verify:** Call this function for a major metro + major industry (e.g., CBSA 35620 = New York metro, NAICS group 62 = Healthcare). It should return a dict. Call it for a rural employer (cbsa_code=None). It should return None without error.

---

### Checkpoint 1.6 — Update M3c, M3e, M2c to use PUMS when available

In each of these three methods, add a PUMS lookup at the top:

```python
# Try PUMS metro first; fall back to state ACS
acs_data = get_pums_demographics(naics_group, cbsa_code)
data_source = 'pums_metro'
if acs_data is None:
    acs_data = get_acs_demographics(naics_group, state)  # existing call
    data_source = 'acs_state'
```

Tag every output with `data_source` so downstream reporting can show what % of companies used PUMS vs state ACS.

**Verify:** Run M3c on 10 companies from the 998-company set that are in major metros. Check `data_source` — at least some should say `pums_metro`. Run M3c on a rural company. It should say `acs_state`.

---

### Run 1 Completion Check

Before ending the session, run the updated methods against the full 998-company set and confirm:
1. Admin/Staffing companies now route to M1b, not M4e
2. No method produces exactly 0.000 for any racial category (smoothing works)
3. Composite score is computed and saved for all methods
4. At least 50% of companies in the 998-company set get `data_source = pums_metro` for M3c

Save results as `comparison_v5_run1_detailed.csv`.

---

---

## Run 2: Gate v0 — Learned Router from Existing Predictions

**Goal:** Train a learned routing model (Gate v0) on the existing 998-company prediction data. Compare it against the current M8 hand-coded router. If it wins on the holdout, it replaces M8.

**Estimated session length:** Medium-long (requires careful data prep + model training)

---

### Background to Read First

Read the V4 detailed results CSV produced in Run 1 (or the previous V4 run). It should have one row per company × method with predicted and actual demographics. This is the training data for the gate.

---

### Checkpoint 2.1 — Build gate training table

Create a script `build_gate_training_data.py` that:

1. Loads the 998-company prediction results
2. For each company, collects predictions from these **five explicitly named methods**: M3b, M3 IPF, M2c, M3c, M1b
3. Computes the actual race MAE each method achieved for that company
4. Adds company context features as columns:
   - `naics_group` (2-digit NAICS)
   - `region` (Northeast/South/Midwest/West)
   - `urbanicity` (Urban/Suburban/Rural)
   - `size_bucket` (small/medium/large based on employee count)
   - `county_minority_share` (what % of county workforce is non-white, from LODES)
   - `acs_lodes_disagreement` = absolute difference between ACS white% and LODES white%
   - `has_tract_data` (boolean — does this company have a tract-level estimate?)
   - `is_finance_insurance` (boolean — naics_group == '52') ← **required, see note below**
   - `is_admin_staffing` (boolean — naics_group == '56')
   - `is_healthcare` (boolean — naics_group == '62')
5. Adds label column: `best_method` = name of method with lowest race MAE for this company

**Why `is_finance_insurance` must be an explicit feature:**
M3e's performance advantage (4.26 overall MAE, best in V4) came almost entirely from routing Finance/Insurance to M3 IPF, which achieves 3.5 MAE in that segment vs 5+ for every other method. This is the single largest routing signal in the entire dataset. Adding it as an explicit boolean guarantees the gate can capture it even with only 998 training examples. Without it, the Finance signal gets buried inside the one-hot `naics_group` encoding and the gate may learn a weak version of the pattern or miss it entirely.

**Why M1b must be one of the five methods:**
M1b is the correct specialist for two confirmed hard segments — Admin/Staffing (5.7 MAE, wins that segment) and high-minority employers (11.3 MAE, best available). It must be a named routing destination the gate is explicitly trained to recognize, not just an option it might stumble onto. If M1b predictions are missing from the training table, the gate cannot route to it.

Save as `gate_training_data.csv`.

**Important:** Mark M3c, M3e, and M1b predictions as "potentially contaminated" (these methods were tuned on subsets of the same 998 companies). The gate will use strong regularization to handle this.

**Verify:** 
```python
print(training_df['best_method'].value_counts())
```
Expected approximate distribution: M3b ~30%, M3 IPF ~25% (heavy in Finance/Utilities/Suburban), M3c ~25%, M1b ~15% (Admin/Staffing + high-minority), M2c ~5%. If M3c wins more than 50% or M1b wins zero companies, check for bugs in the MAE calculation or confirm M1b predictions are present in the results CSV.

---

### Checkpoint 2.2 — Train Gate v0

Create `train_v5_gate.py`:

```python
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler, OneHotEncoder
from sklearn.compose import ColumnTransformer
from sklearn.pipeline import Pipeline
from sklearn.model_selection import GroupKFold, cross_val_score
import pandas as pd, numpy as np, joblib

# Load training data
df = pd.read_csv('gate_training_data.csv')

# Features
categorical_features = ['naics_group', 'region', 'urbanicity', 'size_bucket']
numeric_features = ['county_minority_share', 'acs_lodes_disagreement']
boolean_features = ['is_finance_insurance', 'is_admin_staffing', 'is_healthcare', 'has_tract_data']
all_features = categorical_features + numeric_features + boolean_features

# Target
y = df['best_method']

# Preprocessing
preprocessor = ColumnTransformer([
    ('cat', OneHotEncoder(handle_unknown='ignore', sparse_output=False), categorical_features),
    ('num', StandardScaler(), numeric_features)
])

# Gate model — strong L2 regularization (C=0.1 means strong penalty)
gate = Pipeline([
    ('prep', preprocessor),
    ('clf', LogisticRegression(
        C=0.1,              # strong regularization — critical for small dataset
        max_iter=1000,
        multi_class='multinomial',
        solver='lbfgs',
        random_state=42
    ))
])

# Cross-validate — group by naics_group to avoid leakage
cv = GroupKFold(n_splits=5)
scores = cross_val_score(gate, df[all_features], y,
                          groups=df['naics_group'], cv=cv, scoring='accuracy')

print(f"Gate v0 CV accuracy: {scores.mean():.3f} ± {scores.std():.3f}")

# Fit on all data and save
gate.fit(df[all_features], y)
joblib.dump(gate, 'gate_v0.pkl')
print("Gate v0 saved.")
```

**Do not expect high accuracy.** 998 companies is a small training set. 40-55% CV accuracy is reasonable and still useful — it means the gate is doing better than random (which would be ~20-30% for 4-5 methods). The goal is to beat M8's hard-coded rules on the holdout, not to perfectly predict the best method.

---

### Checkpoint 2.3 — Evaluate Gate v0 vs M8

Create `evaluate_gate_v0.py` that:

1. Loads the V3 holdout companies (`selected_holdout_v3.json` — 200 companies not used in gate training)
2. For each company:
   - Runs Gate v0 to predict which method to use
   - Runs the predicted method and gets its demographic estimate
   - Also runs M8 (current hand-coded router) for comparison
   - Also runs M3b (production baseline) for comparison
3. Computes race MAE and composite score for all three approaches on the holdout

**Report format:**

```
=== Gate v0 vs M8 vs M3b — V3 Holdout (200 companies) ===

                  Race MAE   P(>20pp)   P(>30pp)   Composite
M3b (baseline)     4.33      0.XX       0.XX        X.XX
M8 (hand-coded)    4.XX      0.XX       0.XX        X.XX
Gate v0 (learned)  4.XX      0.XX       0.XX        X.XX

=== Gate v0 routing decisions ===
Routes to M3b:     XX companies
Routes to M3 IPF:  XX companies
Routes to M3c:     XX companies
Routes to M1b:     XX companies
Routes to M2c:     XX companies

=== Gate v0 vs M8 agreement rate ===
Agreed on route:   XX%
Disagreed:         XX%
  Of disagreements, Gate v0 was better: XX%
  Of disagreements, M8 was better:      XX%
```

**Decision rule:** If Gate v0 achieves lower composite score than M8 on the holdout: Gate v0 replaces M8 going forward. If not: keep M8, note what Gate v0 got wrong, use that to inform Run 3.

---

### Run 2 Completion Check

1. `gate_training_data.csv` exists with 998 rows and all required columns
2. `gate_v0.pkl` exists and loads without error
3. Evaluation report is printed and saved as `GATE_V0_EVALUATION.md`
4. Clear recommendation recorded: "Gate v0 replaces M8" or "M8 retained, Gate v0 failed because X"

---

---

## Run 3: V5 Expert Family

**Goal:** Build the two new expert models described in the V5 proposal. These give the gate better options to choose between and directly target the two biggest remaining problems: high-minority employers and the Asian underestimation bias.

**Estimated session length:** Long

---

### Background

The expert family is designed as four experts. Two already exist (Expert D = M3b, Expert A is a smoothed upgrade of M3c). Run 3 builds Expert A and Expert B fully. Expert C (occupation-heavy) is deferred — we don't have sub-state occupation data yet.

| Expert | Status | Description |
|--------|--------|-------------|
| Expert A | **Build in Run 3** | Smoothed dampened IPF — M3c with smoothing + learned alpha |
| Expert B | **Build in Run 3** | Tract-heavy model extended from Hispanic to all race categories |
| Expert C | Deferred | Occupation-heavy model — wait for PUMS occupation data |
| Expert D | Already exists | M3b — zero-parameter fallback, keep as-is |

---

### Checkpoint 3.1 — Expert A: Smoothed Dampened IPF

This is M3c with two upgrades: smoothing is already added from Run 1, but alpha (the blend weight between ACS and LODES) should be learned with shrinkage rather than hand-coded by industry group.

**Current M3c behavior:** Alpha is set to a fixed value per NAICS group based on V3 optimization. Different industries have different alpha values.

**Expert A behavior:** Alpha is still per-segment, but:
- Starts at 0.50 (equal weight between ACS and LODES)
- Gets pulled toward 0.50 by a shrinkage penalty proportional to how few companies are in the segment
- Formula: `alpha_final = (n_segment * alpha_learned + shrinkage_weight * 0.50) / (n_segment + shrinkage_weight)`
- Use `shrinkage_weight = 5` as a starting value (tune later if needed)

This prevents the M1b problem where a NAICS group with 3 companies gets an extreme alpha that doesn't generalize.

**Also add:** The national EEO-1 prior as a third input alongside ACS and LODES:

```python
# Expert A formula
prior_k = NATIONAL_EEO1_PRIOR[k]  # national average % for category k
lambda_smooth = 2.0  # percentage points of smoothing

acs_smooth_k   = acs_k   + lambda_smooth * prior_k
lodes_smooth_k = lodes_k + lambda_smooth * prior_k

raw_k = (acs_smooth_k ** alpha) * (lodes_smooth_k ** (1 - alpha))
pred_k = raw_k / sum(raw)
```

The national EEO-1 prior is the average racial composition of private-sector workers nationally (approximate values to use as starting point):
- White: 63%, Black: 12%, Hispanic: 17%, Asian: 6%, AIAN: 0.6%, NHOPI: 0.3%, Two+: 1.1%

**Name this method:** `expert_a_smoothed_ipf` in the methodology file.

**Verify:** Run Expert A on the 998-company set. It should produce race MAE within 0.2pp of M3c (it's an upgrade of M3c, not a different animal). If it's dramatically worse, the alpha shrinkage calculation has a bug.

---

### Checkpoint 3.2 — Expert B: Tract-Heavy Geography Model

M2c currently uses tract-level data only for Hispanic estimation. Expert B extends this to race, making tract-level neighborhood composition a primary input for all categories.

**The idea in plain terms:** The neighborhood where a company is located carries demographic signal. A company in a predominantly Black neighborhood in Atlanta is more likely to have Black workers than a company in a predominantly white suburb. LODES (county-level) blurs this out. Tract-level data preserves it.

**Expert B formula:**
```python
pred = (w1 * acs_industry_state     # what people in this industry look like statewide
      + w2 * lodes_county           # what workers in this county look like
      + w3 * tract_demographics)    # what the neighborhood around this employer looks like

# Starting weights
w1, w2, w3 = 0.35, 0.25, 0.40   # tract gets highest weight
```

**Where tract data comes from:** It already exists for M2c (the ZIP-to-tract crosswalk used for Hispanic). Extend it to pull all race categories from Census tract data, not just Hispanic share.

Check the existing M2c implementation to see exactly which table and columns it uses for tract data. Use the same data source — just pull all race columns instead of only Hispanic.

**Fallback when tract data is missing:** Set w3 = 0, renormalize w1 and w2 to sum to 1.0. Do not error out.

**Name this method:** `expert_b_tract_heavy` in the methodology file.

**Verify:** Expert B should outperform M3c on companies in high-minority neighborhoods specifically. Sort the 998-company set by `county_minority_share` descending. Expert B should rank higher than M3c for the top quartile. If it doesn't, inspect whether the tract data is actually varying across companies or is returning the same values.

---

### Checkpoint 3.3 — Generate out-of-fold predictions for gate retraining

Run a 5-fold cross-validation where:
- The dataset is the 998-company set
- Folds are grouped by NAICS group (so all companies in the same industry go to the same fold)
- For each fold: train Expert A's alpha values on the 80% training fold, predict on the held-out 20%
- Expert B has no learned parameters, so its predictions are always out-of-fold

Save one row per company with columns: `company_id, expert_a_pred_[categories], expert_b_pred_[categories], expert_d_pred_[categories], actual_[categories]`

This is the clean training data for Gate v1.

**Name output file:** `oof_predictions_v5.csv`

---

### Run 3 Completion Check

1. `expert_a_smoothed_ipf` implemented and producing sensible predictions
2. `expert_b_tract_heavy` implemented and producing sensible predictions
3. `oof_predictions_v5.csv` exists with 998 rows, predictions from all three experts
4. Run composite score for Expert A, Expert B, Expert D on the 998-company set — print comparison table

---

---

## Run 4: Gate v1 + Final Validation

**Goal:** Retrain the gate on the clean out-of-fold predictions from Run 3. Validate on a fresh holdout. Decide whether V5 is production-ready.

**Estimated session length:** Medium

---

### Checkpoint 4.1 — Select fresh holdout companies

The 998 companies used in all prior runs have been touched in some way by every design decision. The true test of V5 requires companies that have never been used in any training, optimization, or routing decision.

**The fresh holdout must:**
- Be drawn from the EEO-1 ground truth file (`objectors_with_corrected_demographics_2026_02_25.csv`)
- Not overlap with any of the four existing JSON company files
- Be stratified across NAICS groups, regions, urbanicity levels, and minority share buckets
- Contain 200-250 companies minimum

Create `build_fresh_holdout_v5.py`:
1. Load EEO-1 ground truth file
2. Exclude any company_id already in selected_200.json, selected_holdout_200.json, selected_400.json, selected_holdout_v3.json
3. Apply same 5-dimension stratified sampling used in prior rounds
4. Save as `selected_fresh_holdout_v5.json`
5. Print distribution breakdown and confirm no overlap

**Verify:** Print `len(fresh_holdout)` — should be 200-250. Print `overlap = set(fresh_ids) & set(all_prior_ids)` — must be empty (zero overlap).

---

### Checkpoint 4.2 — Train Gate v1

Retrain the gate using the out-of-fold predictions from Run 3 instead of the raw V4 predictions used for Gate v0.

Key differences from Gate v0:
- Training data is now `oof_predictions_v5.csv` (clean OOF, no contamination)
- Expert options are now A, B, D (not the V4 method names)
- All other gate code is the same

```python
# Same logistic regression structure as Gate v0
# Same features: naics_group, region, urbanicity, size_bucket,
#                county_minority_share, acs_lodes_disagreement
# Same L2 regularization (C=0.1)
# New label column: best_expert (A, B, or D)
```

Save as `gate_v1.pkl`.

Add the OOF calibration layer:
1. On the OOF predictions, compute signed residual per category: `bias_k = mean(pred_k - actual_k)`
2. For each new prediction, subtract the learned bias and renormalize:
   ```python
   calibrated_k = pred_k - bias_k
   # renormalize so all categories sum to 100
   ```

Save bias corrections as `calibration_v1.json`.

---

### Checkpoint 4.3 — BDS-HC calibration (second-pass correction)

The OOF calibration above fixes the model's own average errors. BDS-HC does something different — it brings in an independent external source that tells you what employers of a given type *actually* look like, based on W-2 filings. These two corrections are complementary and both belong in the pipeline.

**What BDS-HC is:** Business Dynamics Statistics by Human Capital. A Census Bureau dataset that cross-tabulates workforce demographics by industry × firm size × state, derived from administrative payroll records rather than surveys. It's already downloaded and sitting on disk.

**Find the downloaded files:** Look in the project directory for BDS-HC CSV files — likely in a `data/` or `raw_data/` subdirectory. Files will be named something like `bds_hc_2021_ind_sz_st.csv` or similar.

**Step 1 — Load BDS-HC into database:**

```sql
CREATE TABLE IF NOT EXISTS bds_hc_benchmarks (
    naics_2digit    VARCHAR(4),
    state_fip       VARCHAR(2),
    size_band       VARCHAR(20),   -- '<50', '50-249', '250-999', '1000+'
    pct_white       FLOAT,
    pct_black       FLOAT,
    pct_hispanic    FLOAT,
    pct_asian       FLOAT,
    pct_female      FLOAT,
    n_firms         INTEGER,
    suppressed      BOOLEAN        -- TRUE if Census marked as 'D' or 'S'
);
```

Handle suppressed values ('D' = withheld to protect identity, 'S' = statistically unreliable): set `suppressed = TRUE`, do not fill with zero.

**Step 2 — Write `get_bds_benchmark(naics_2digit, state_fip, size_band)`:**

Returns the BDS-HC demographic distribution for this employer type. Falls back through this hierarchy when a cell is suppressed:
1. Same NAICS + adjacent size band (one step up or down)
2. Parent NAICS 2-digit + same size band
3. National NAICS 2-digit + same size band
4. If all suppressed: return None (skip calibration for this employer)

**Step 3 — Apply BDS-HC nudge inside M8/Gate v1 as a second calibration pass:**

```python
def apply_bds_calibration(estimate: dict, naics_2digit: str,
                           state_fip: str, size_band: str,
                           is_hard_segment: bool) -> dict:
    """
    Nudges the estimate toward the BDS-HC benchmark when the estimate
    is implausibly far from what employers of this type actually look like.
    
    Hard segments (Healthcare, Admin/Staffing, high-minority) get a
    stronger nudge because the base methods are most wrong there.
    """
    benchmark = get_bds_benchmark(naics_2digit, state_fip, size_band)
    if benchmark is None:
        return estimate  # no BDS data available, return unchanged
    
    nudge_weight = 0.30 if is_hard_segment else 0.18
    
    nudged = {}
    for category in estimate:
        nudged[category] = ((1 - nudge_weight) * estimate[category]
                            + nudge_weight * benchmark[category])
    
    # Renormalize
    total = sum(nudged.values())
    return {k: v / total for k, v in nudged.items()}
```

`is_hard_segment = True` when: naics_group is Healthcare (62), Admin/Staffing (56), Food/Bev Manufacturing (311-312), or `county_minority_share > 0.50`.

**Why the nudge weight is asymmetric:** For normal employers, we trust our estimate more than BDS-HC (0.18 nudge = 82% our estimate). For hard segments, BDS-HC knows something our methods don't — the W-2 data sees actual payroll, not area demographics — so we shift trust toward it (0.30 nudge = 70% our estimate).

**Step 4 — Run the full calibration sequence:**
1. Gate v1 routes to best expert → raw estimate
2. OOF bias correction (from checkpoint 4.2) → bias-corrected estimate
3. BDS-HC nudge (this checkpoint) → final estimate

**Verify:** Run the full pipeline on the 998-company set. Print the average nudge magnitude (how much BDS-HC moved estimates on average) broken down by segment. Healthcare and Admin/Staffing should show larger average movement than Finance. If Healthcare shows near-zero movement, the BDS-HC data may not be loading correctly for that segment.

---

### Checkpoint 4.4 — Final validation on fresh holdout

Run every method against the 200-250 fresh holdout companies:
- M3b (production baseline)
- M8 (hand-coded router, patched in Run 1)
- Gate v0 (from Run 2)
- Gate v1 (from this run)
- Expert A, B, D individually

Report using the composite scoring metric from Run 1.

**Acceptance criteria (from V5 Synthesis document):**

Gate v1 passes if ALL of:
1. Race MAE lower than M3b on fresh holdout
2. P(max_error > 30pp) does not increase vs M3b
3. Mean absolute signed bias on race categories is lower than V4
4. Hispanic and gender MAE are no worse than best current methods

If Gate v1 passes: it is the new production router. M8 is retired.
If Gate v1 fails: record specifically which criterion failed and why. M3b remains production.

---

### Checkpoint 4.5 — Add review flags to production output

Each estimate from Gate v1 should include metadata alongside the prediction:

```python
{
    "predicted_distribution": {...},
    "data_source": "pums_metro" | "acs_state",
    "expert_used": "A" | "B" | "D",
    "confidence_score": 0.0-1.0,  # gate's softmax probability for chosen expert
    "review_flag": True | False,
    "review_reasons": ["expert_disagreement", "sparse_tract_data", etc.]
}
```

Trigger `review_flag = True` when any of:
- Top two experts differ by >= 10pp on White, Black, or Asian
- Gate confidence score < 0.45 (gate isn't sure which expert to use)
- Company has no tract data AND no PUMS metro data (both geographic sources missing)
- Company falls in Admin/Staffing, Healthcare, or high-minority bucket (historically hard segments)

---

### Checkpoint 4.6 — Wire into API

Find the demographics endpoint in the FastAPI routers (likely in `api/routers/profile.py` or similar). Update it to call the new Gate v1 system and return the full metadata including review flags.

The API response should expose:
- `demographics.predicted` (the estimate)
- `demographics.data_source` 
- `demographics.confidence_score`
- `demographics.review_flag`
- `demographics.review_reasons` (list, may be empty)

**Do not remove the existing M3b fallback.** Keep it as a backup: if Gate v1 errors for any reason, fall back to M3b silently and set `data_source = 'fallback_m3b'`.

---

### Run 4 Completion Check

1. Fresh holdout contains 200-250 companies with zero overlap to prior sets
2. Gate v1 and OOF calibration layer trained and saved
3. BDS-HC table loaded and nudge layer verified (Healthcare shows larger movement than Finance)
4. Full comparison table printed and saved as `V5_FINAL_REPORT.md`
5. Clear pass/fail decision documented with reasoning
6. API endpoint updated (or documented as a separate task if session runs long)

---

---

## Architecture Summary

```
                    Company Input
                         │
                    Gate v1 (learned router)
                    features: naics_group, region, urbanicity,
                              size_bucket, county_minority_share,
                              acs_lodes_disagreement,
                              is_finance_insurance ← explicit signal
                              is_admin_staffing, is_healthcare
                         │
        ┌────────────────┼──────────────┬──────────────┐
        │                │              │              │
     Expert A         Expert B       Expert D       M1b
  Smoothed IPF      Tract-Heavy     M3b (safe    (Admin/Staffing,
  (PUMS input)      (race + geo)    fallback)    high-minority)
        │                │              │              │
        └────────────────┼──────────────┴──────────────┘
                         │
                 OOF Calibration
                 (subtract learned
                  per-category bias)
                         │
                 BDS-HC Nudge
                 (external benchmark
                  for hard segments:
                  Healthcare, Admin,
                  Food/Bev, high-minority)
                         │
                  Final Prediction
                  + confidence score
                  + review flag
                  + data_source tag
```

---

## File Inventory at End of All Runs

| File | Created In | Purpose |
|------|------------|---------|
| `comparison_v5_run1_detailed.csv` | Run 1 | V4 methods re-run with smoothing + PUMS |
| `gate_training_data.csv` | Run 2 | 998-company prediction table for Gate v0 |
| `gate_v0.pkl` | Run 2 | Trained Gate v0 model |
| `GATE_V0_EVALUATION.md` | Run 2 | Gate v0 vs M8 comparison report |
| `oof_predictions_v5.csv` | Run 3 | Clean OOF predictions from Expert A, B, D, M1b |
| `selected_fresh_holdout_v5.json` | Run 4 | 200-250 never-before-used companies |
| `gate_v1.pkl` | Run 4 | Trained Gate v1 model |
| `calibration_v1.json` | Run 4 | Per-category OOF bias corrections |
| `V5_FINAL_REPORT.md` | Run 4 | Full comparison + pass/fail decision |
| `methodologies_v5.py` | Run 3 | Expert A and B implementations |
| `cached_loaders_v5.py` | Run 1 | PUMS loader + updated ACS loaders |
| `pums_metro_demographics` (DB) | Run 1 | PUMS metro-level demographics table |
| `bds_hc_benchmarks` (DB) | Run 4 | BDS-HC industry × state × size benchmarks |
| `load_bds_hc.py` | Run 4 | One-time script: BDS-HC CSVs → database |

---

## What Is Explicitly Out of Scope for All 4 Runs

- Expert C (occupation-heavy) — deferred until PUMS sub-state occupation data is available
- Supervised ML / gradient boosting — needs 500+ labeled companies minimum
- NLRB demographic signal extraction — NLP project, not estimation pipeline
- Expanding PUMS to all 50 states — validate 10-state approach in Run 1 first
- Frontend changes — demographics UI updates follow after estimation is validated
