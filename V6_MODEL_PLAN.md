# V6 Demographics Estimation Model Plan

**Status:** COMPLETE (2026-03-09) -- 7/7 acceptance criteria passed
**Builds On:** V5 (Gate v1 + Expert A/B/D + PUMS metro)
**Ground Truth:** EEO-1 filings (~5,000 companies)
**Current Benchmarks (V5 fresh holdout, 208 companies):**

| Metric | V5 Gate v1 | V6 Target | V6 Stretch |
|--------|-----------|-----------|-----------|
| Race MAE | 5.182pp | < 4.50pp | < 4.20pp |
| P>20pp | 20.67% | < 17% | < 14% |
| P>30pp | 8.17% | < 6.5% | < 5% |
| Abs Bias | 1.345 | < 1.10 | < 0.90 |
| Hispanic MAE | 9.252pp | < 8.00pp | < 7.00pp |
| Gender MAE | 18.098pp | < 12.00pp | < 8.00pp |
| Ground truth leak | FAIL | PASS | PASS |
| Red flag rate | 94.7% | < 20% | < 10% |

---

## Philosophy

V6 is not a replacement for V5. It is a layered improvement. Every method from V1 through V5 still exists in code and none of it gets deleted.

### The Central Insight That Shapes V6

A post-hoc review of V2 through V5 revealed something critical: **every single method in the pipeline — all 30 of them — uses only two data distributions:**

```
ACS:   "What % of [industry] workers in [state] are [race]?"
LODES: "What % of ALL workers in [county] are [race]?"
```

The fanciest method (M3c variable-dampened IPF) just finds a smarter way to multiply these two numbers together. The gate just picks which multiplication to use. But the accuracy ceiling is set entirely by these two inputs.

Meanwhile, the database contains a large amount of data that was loaded but never used:

| Data | In Database | Used | What It Adds |
|------|------------|------|-------------|
| LODES industry employment (CNS01-CNS20) | Yes (in ETL output) | **No** | "% of Manufacturing workers in this county who are Black" vs. all workers |
| QCEW location quotient | Yes (1.9M rows) | **No** | How much to trust LODES for this county/industry pair |
| Metro-level ACS | Yes (metro_cbsa column) | **No** | Industry data at metro level, better than state-level fallback |
| OES occupation wages by metro | Yes (414K rows) | **No** | Local occupation mix for gender estimation |
| LODES education brackets | Yes | **No** | New dimension: education estimation |
| ACS education/age | Yes | **No** | New dimension: education and age estimation |

**The implication:** More sophisticated routing on top of the same two inputs produces diminishing returns. V3-V5 spent three iterations refining the combination formula. Each iteration gained about 0.2-0.5pp. Feeding better inputs into even simple formulas should gain 0.5-1.5pp.

**This means Phase 0 (data infrastructure) matters more than Phase 3 (gate upgrade).**

### The V6 Goals

1. **Fix what is broken** — remove the ground truth data leak, remove the BDS nudge that makes things worse
2. **Unlock data already in the database** — industry-specific LODES, QCEW concentration, metro ACS, OES occupation data
3. **Restore what was dropped** — M3_ORIGINAL was the best method for Finance/Utilities (3.14 MAE) and was left out of the Gate v1 expert pool by mistake
4. **Add new data that was downloaded but never wired in** — CPS Table 11 (gender by occupation), sitting in the project folder unused
5. **Build dimension-specific models** — race, gender, and Hispanic benefit from different approaches; tying them to one formula hurts all three
6. **Expand training data** — we have ~5,000 EEO-1 companies but only used 997 to train V5
7. **Improve routing and confidence** — once the base methods are better, the gate upgrade pays off more

Each phase builds on the previous. You don't need to finish Phase 3 to benefit from Phase 0.

---

## What the Model Does (Plain Language Explanation)

The model has two layers:

**Layer 1 — The Experts.** Each "expert" is a formula that takes a company's industry code (NAICS), state, county, and size and produces an estimate of what percent of workers are White, Black, Asian, etc., plus Hispanic share and gender split. The formulas use Census data, LODES job data, and tract demographics blended together in different ways. Some formulas are better for urban companies; others are better for Finance; others are better in sparse rural areas.

**Layer 2 — The Gate.** The gate is a learned model (logistic regression in V5, to be upgraded to a decision tree in V6) that looks at a company's characteristics and decides which expert to hand it to. Think of it like a triage nurse routing patients to the right specialist.

The key insight is: **both layers need to be as good as possible.** If your specialists are mediocre, the gate can't fix that. If your gate routes to the wrong specialist half the time, even great specialists produce bad results.

---

## Phase 0: Data Infrastructure (Do Before Everything Else)

This phase has no visible accuracy improvement on its own. It just builds the plumbing that every subsequent phase depends on. Think of it like installing pipes before turning on the water. Without this, all the better methods in Phases 1-4 can't run.

**Time estimate: 3-5 days. Do this before writing any new estimation methods.**

### 0.1 Verify and Expose Industry-Specific LODES (CNS Columns)

**What the problem is:** Your LODES query currently asks "what percent of all workers in this county are Black?" That's useful, but it's imprecise. A pharmaceutical company in a county that's 40% agricultural workers gets contaminated by farm worker demographics.

**What already exists:** The LODES WAC files your ETL already processed contain columns called CNS01 through CNS20 — one for each NAICS supersector. These columns contain employment counts broken down by industry within each Census block. So instead of "all county workers," you can ask "Manufacturing workers in this county specifically."

**The check to run first:**
```sql
-- Check if CNS columns already exist in your LODES table
SELECT column_name FROM information_schema.columns
WHERE table_name = 'cur_lodes_geo_metrics'
  AND column_name LIKE 'cns%';
```

If this returns 20 rows (CNS01-CNS20), the data is there and you just need a new loader function. If it returns nothing, the ETL needs to be updated to include those columns from the raw WAC files.

**What to build:** A new loader function in `data_loaders.py`:
```python
def get_lodes_industry_race(county_fips, naics_2digit):
    """
    Returns race demographics weighted by employment in THIS specific industry
    within this county — not all industries combined.
    """
    cns_code = NAICS_TO_CNS[naics_2digit]  # e.g., '31' -> 'CNS05'
    # Weight each tract's demographics by how many of THIS industry's
    # jobs are in that tract
    ...
```

**NAICS-to-CNS mapping:**
| NAICS | CNS | Sector |
|-------|-----|--------|
| 11 | CNS01 | Agriculture |
| 21 | CNS02 | Mining |
| 22 | CNS03 | Utilities |
| 23 | CNS04 | Construction |
| 31-33 | CNS05 | Manufacturing |
| 42 | CNS06 | Wholesale |
| 44-45 | CNS07 | Retail |
| 48-49 | CNS08 | Transportation |
| 51 | CNS09 | Information |
| 52 | CNS10 | Finance |
| 53 | CNS11 | Real Estate |
| 54 | CNS12 | Professional |
| 55 | CNS13 | Management |
| 56 | CNS14 | Admin/Staffing |
| 61 | CNS15 | Education |
| 62 | CNS16 | Healthcare |
| 71 | CNS17 | Arts/Entertainment |
| 72 | CNS18 | Accommodation/Food |
| 81 | CNS19 | Other Services |
| 92 | CNS20 | Public Admin |

### 0.2 Build QCEW Concentration Loader

**What the problem is:** All current methods assume the company's registered county is representative of its workers. But a pharmaceutical company headquartered in a county dominated by government employment is getting estimated using government worker demographics.

**What QCEW tells you:** Your `qcew_annual` table (1.9M rows, completely unused by the demographics pipeline) contains a column called `location_quotient` for each county × industry combination. This number tells you how concentrated a given industry is in a given county relative to the national average. A location quotient of 2.0 means "this industry is twice as represented here as nationally." A location quotient of 0.3 means "this industry barely exists here."

**Why this matters for estimation:** When LQ is high (industry is strongly present), LODES county demographics are actually meaningful for that industry — weight LODES more. When LQ is low (industry is sparse), LODES is giving you the wrong workers — fall back to ACS.

**What to build:**
```python
def get_qcew_concentration(county_fips, naics_2digit):
    """
    Returns: location_quotient, industry_share, avg_annual_pay
    High LQ (>1.5) = trust LODES more for this industry here
    Low LQ (<0.5) = fall back to ACS, LODES is misleading
    """
    ...
```

### 0.3 Build Metro-Level ACS Loader

**What the problem is:** 26.5% of companies fall back to state-level ACS when PUMS has no data. State-level ACS is much less precise than metro-level.

**What already exists:** Your `cur_acs_workforce_demographics` table has a `metro_cbsa` column that your data loaders never query. The data is there.

**What to build:**
```python
def get_acs_race_metro(naics_code, cbsa_code):
    """
    Get ACS race demographics at metro × industry level.
    More precise than state-level for companies in major metros.
    Fills the gap between PUMS (very specific but sparse) and state ACS (broad).
    """
    ...
```

**Fallback chain after this addition:**
1. PUMS (metro × 2-digit NAICS, needs ≥30 respondents)
2. **ACS metro** ← new, fills this gap
3. ACS state × 4-digit NAICS
4. ACS state × 2-digit NAICS

### 0.4 Build Multi-Tract Ensemble Loader

**What the problem is:** The M2 family of methods picks ONE census tract per ZIP code. But ZIP codes often contain multiple tracts with different demographics. Picking one at random introduces noise.

**The fix:** Use all tracts in the ZIP, weighted by employment counts from LODES. This averages out the noise.

```python
def get_multi_tract_demographics(zipcode):
    """
    Get demographics averaged across ALL tracts in this ZIP,
    weighted by how many jobs are in each tract.
    """
    ...
```

### 0.5 Verify OES Metro Occupation Data

Check that `oes_occupation_wages` contains metro-level occupation employment counts — this will be used in Phase 2 to improve gender estimation with local (not just national) occupation mixes.

```sql
SELECT COUNT(*) FROM oes_occupation_wages WHERE area_type = 'metro';
-- Expected: several hundred thousand rows
```

---

## Critical Bug Fixes (Do These After Phase 0)

### Fix 1: Remove the Ground Truth Leak

**What it is:** Gate v1 was trained using a feature called `minority_share` — the actual percentage of minority workers from EEO-1 ground truth data. This is cheating: in real production, you don't have EEO-1 data for the companies you're trying to estimate. The gate learned to route based on information it wouldn't have in real use.

**Why it matters:** The holdout results look better than production will actually be. The gate will perform worse on real companies than the numbers suggest.

**The fix:** Replace `minority_share` (from EEO-1) with `lodes_minority_share` (computed from LODES county data — the percentage of jobs in a county held by non-white workers). This is publicly available, doesn't require knowing the answer, and is a reasonable proxy.

**Files to change:** `build_gate_training_data.py`, `train_gate_v1.py`, `cached_loaders_v5.py` (add `lodes_minority_share` feature)

### Fix 2: Remove BDS Nudge from Production Path

**What it is:** The V5 pipeline applies a small correction based on BDS (Business Dynamics Statistics) sector-level bracket data. Testing showed this nudge increases race MAE by 0.045pp on average — it makes things slightly worse.

**Why it happens:** BDS brackets are too coarse ("10-25% minority") to meaningfully adjust individual company estimates.

**The fix:** Remove from the production pipeline. Keep the code and the loaded data — it might still be useful as a gate feature or for validation. Just don't apply it as a correction.

---

## Phase 1: Restore Lost Methods and Fix the Expert Pool

### 1.1 Restore Expert E: M3_ORIGINAL for Finance and Utilities

**Background:** V5's M8-V5 routing showed that M3_ORIGINAL (raw IPF without dampening) produces a 3.14 average race MAE for Finance and Utilities companies — compared to ~4.5 for the general experts. This is a huge gap. But Gate v1 doesn't include M3_ORIGINAL as an expert option at all; those companies fall to Expert D instead.

**What M3_ORIGINAL is:** IPF where each race category estimate is `ACS_pct × LODES_pct`, normalized to sum to 100. No dampening, no smoothing. It works exceptionally well for Finance and Utilities because those industries have very consistent workforce compositions across a metro area, so ACS and LODES agree strongly and the raw product amplifies that agreement.

**The fix:** Add Expert E as a hard-routed method. Any company with NAICS starting with 52 (Finance/Insurance) or 22 (Utilities) goes directly to Expert E, bypassing the gate entirely. This is not a decision the gate needs to learn — it's deterministic.

**Implementation:**
```python
def route_expert(company):
    naics2 = company['naics4'][:2]
    if naics2 in ('52', '22'):
        return 'Expert_E'  # Hard route, skip gate
    else:
        return gate_v2.predict(company)  # Gate decides between A/B/D
```

**Expected gain:** ~0.3-0.5pp reduction in race MAE for the ~15% of companies in Finance/Utilities.

### 1.2 Add Expert F: Occupation-Weighted IPF for Manufacturing

**Background:** Manufacturing occupations have highly distinctive demographics. A metal fabrication plant has a very different workforce than a pharmaceutical manufacturing facility, even though both are NAICS 31-33. The V1 method M6 (occupation-weighted IPF) tried to handle this but was dropped when the learning model took over.

**What it does:** Instead of using ACS at the industry level as one input to IPF, use ACS at the occupation level — weighted by the BLS occupation matrix for that specific 4-digit industry. So for "metal can manufacturing" (NAICS 3412), you'd look up the occupation distribution (machinists, assemblers, welders, etc.) and average the demographics of those specific occupations.

**Data already in the database:** `bls_industry_occupation_matrix` (67,699 rows), `newsrc_acs_occ_demo_profiles` (11.5M rows at state×metro×industry×occupation)

**Industries where this helps most:** NAICS 31-33 Manufacturing, NAICS 48-49 Transportation, NAICS 56 Admin/Staffing. These are industries where occupation mix varies enormously within the industry code.

**Implementation:** Resurrect the `_build_occ_weighted()` function from `methodologies.py` (already written) and wire it into a new Expert F that feeds occupation-weighted ACS into IPF.

### 1.3 Soft Routing vs. Hard Routing

**What it currently is (hard routing):** The gate picks one expert (argmax of probabilities) and that expert's output is used entirely.

**What soft routing is:** The gate outputs probabilities like [Expert A: 40%, Expert B: 35%, Expert D: 25%]. Instead of picking Expert A, you compute a weighted blend: `0.40 × A_output + 0.35 × B_output + 0.25 × D_output`.

**Why it helps:** The gate is only 59.8% accurate at picking the right expert. When it's uncertain (e.g., 40/35/25 split), hard routing still commits to one expert and potentially makes a big error. Soft routing naturally hedges in uncertain cases and commits more confidently when probabilities are lopsided.

**Expected gain:** 0.2-0.5pp MAE improvement with no retraining required — just a change to the prediction step.

**Implementation:** 3-4 lines of code in `validate_v5_final.py` or the production router.

---

## Phase 1.5: Better Base Methods (Race)

Once Phase 0 infrastructure is built, build new estimation methods that feed from it. These should be evaluated against existing methods on the full 997-company training set before touching the gate.

**The principle:** These are not new experts for the gate to route to. They are new method *variants* that replace specific inputs. Test them independently first. If they beat their base methods, promote them to the expert pool.

### New Methods to Implement and Test

| Method | Formula | New Data Used | Expected Race MAE |
|--------|---------|--------------|-----------------|
| **M9a Industry-LODES IPF** | ACS × LODES_industry (not all-county) | CNS columns from 0.1 | ~3.8-4.0pp |
| **M9b QCEW-Weighted Blend** | Weight ACS vs LODES based on location quotient | QCEW from 0.2 | ~4.2-4.4pp |
| **M9c Industry-LODES + QCEW** | M9a formula but alpha adapts by LQ | Both | ~3.6-3.9pp |
| **M3c-IND** | Existing M3c but with industry-weighted LODES | CNS columns | ~0.4pp better than M3c |
| **M1b-QCEW** | Existing M1b but LQ-adaptive weights | QCEW | ~0.3pp better than M1b |
| **M2c-Multi** | Existing M2c but multi-tract ensemble | Multi-tract from 0.4 | ~0.2pp better than M2c |

**Why M9a is expected to be the biggest gain:** LODES wins over ACS in most industries because it's geographic. But it loses precision by being all-industry. Restoring industry specificity to the dominant input should significantly close the gap between LODES's geographic accuracy and ACS's industry accuracy — you're getting both signals in one.

**Where industry-LODES helps most:**
- Counties with mixed industry profiles (e.g., county has both hospital and factory — pharma company gets contaminated by factory worker demographics under current method)
- High-minority companies (currently the biggest source of estimation error)
- Urban areas where multiple industries coexist in the same county

### Ablation Study Framework

Before combining everything, test each new data source in isolation. This tells you which sources are actually adding value and which are noise.

| Experiment | What Changes | What It Measures |
|-----------|-------------|-----------------|
| A. Industry-LODES only | Replace LODES input with CNS-weighted version | Value of industry-specific geography |
| B. QCEW weighting only | Add LQ-adaptive weights to M1b | Value of industry concentration signal |
| C. A + B combined | Industry-LODES + QCEW adaptive weight | Do they help each other? |
| D. Multi-tract only | Replace single-tract selection in M2c | Value of averaging across tracts |
| E. Metro ACS only | Add metro ACS layer before state ACS fallback | Value of metro resolution |
| F. All combined | A + B + D + E | Cumulative race improvement |
| G. Gender model | Occupation-based gender (Phase 2) | Gender-specific improvement |
| H. Hispanic model | Geography-heavy blend (Phase 3) | Hispanic-specific improvement |

**Why this matters:** If you combine all new sources without testing them individually, you won't know which ones actually work. And if combined performance is disappointing, you'll have no way to debug it. The ablation study gives you a clear record of what each piece contributed.

**Output:** After running experiments A-F, you'll know whether M9c beats M3c enough to replace it as the primary race expert. If it does, rebuild the gate with M9c as the main expert. If M9a already beats M9c (simpler is better), use M9a.

---

## Phase 2: Gender Estimation Overhaul

Gender is the most broken part of the model. An 18pp MAE means that on average we're off by 18 percentage points on male/female split — equivalent to predicting 60% female when the real answer is 40% female for a warehouse company. Race estimation is much better (5pp MAE) because the data sources give industry-level signals that mostly apply to the industry. Gender doesn't work that way — gender split is much more driven by occupation than by industry.

### 2.1 CPS Table 11 Integration

**What CPS Table 11 is:** The Bureau of Labor Statistics Current Population Survey, Table 11: "Employed people by detailed occupation, sex, race, and Hispanic or Latino ethnicity." It contains 2025 data for ~400 detailed occupations, giving the percentage female for each occupation. Already downloaded to `cpsaat11.xlsx` in the project folder.

**Example values from the file:**
- Software developers: 20.3% female
- Registered nurses: 87.3% female
- Construction laborers: 4.7% female
- Cashiers: 68.5% female
- Truck drivers: 7.7% female
- Medical assistants: 90.8% female
- Security guards: 22.9% female

**What it solves:** Instead of asking "what percent female are Healthcare workers in Florida?" (which averages nurses, doctors, orderlies, and janitors all together), we ask "what occupations does *this specific* healthcare company employ, and what's the gender split for each of those occupations?"

**How to load it:** Parse `cpsaat11.xlsx`, skipping the header rows. The data starts at row 8 with columns: Occupation, Total (thousands), % Women, % White, % Black, % Asian, % Hispanic. Map BLS occupation titles to SOC codes using a crosswalk table (or fuzzy match). Load into a new table `cps_occ_gender_2025`.

**Schema:**
```sql
CREATE TABLE cps_occ_gender_2025 (
    soc_code     VARCHAR(10),
    occupation   TEXT,
    total_emp_k  NUMERIC,  -- thousands
    pct_women    NUMERIC,  -- percent female
    pct_white    NUMERIC,
    pct_black    NUMERIC,
    pct_asian    NUMERIC,
    pct_hispanic NUMERIC,
    year         INTEGER DEFAULT 2025,
    PRIMARY KEY (soc_code, year)
);
```

### 2.2 New Gender Method: Occupation-Weighted CPS

**The method:**
1. Look up the BLS occupation mix for the company's 4-digit NAICS code (`bls_industry_occupation_matrix`)
2. For each occupation in that mix, look up the % female from `cps_occ_gender_2025`
3. Weight by employment share: `pct_female = SUM(occ_share × occ_pct_female)`
4. Use as the primary gender estimate; blend with LODES county gender (30% weight) as a geographic adjustment

**Why this is much better than the current approach:** The current method applies industry-level ACS gender and county LODES gender. Both of these reflect the general workforce, not the specific occupation mix of the company. A hospital and a medical device manufacturer are both NAICS 62 but one is 75% female (patient care) and the other is 30% female (engineers). CPS Table 11 + occupation matrix captures this distinction.

**Expected improvement:** Current gender MAE is 18.1pp. The goal with this method alone is 8-12pp. That is a huge improvement for a relatively small amount of work.

**Fallback chain:**
1. Try: CPS Table 11 × BLS occupation matrix (primary — ~85% coverage)
2. Fall back to: ACS occupation demographics (`newsrc_acs_occ_demo_profiles`) for industries with poor SOC matching
3. Fall back to: Current V5 method (LODES/ACS blend) as last resort

### 2.3 Gender as a Separate Estimation Track

Right now gender is bundled into the same expert that handles race. This means the gate is optimized for race MAE and gender is along for the ride.

For V6, gender should have its own estimation path and its own confidence score. The output structure becomes:

```python
{
    'race':     {'White': 45.2, 'Black': 23.1, ...},  # From race expert
    'hispanic': {'Hispanic': 18.3, 'Not Hispanic': 81.7},
    'gender':   {'Male': 62.1, 'Female': 37.9},  # From gender expert
    'confidence': {
        'race': 0.72,
        'hispanic': 0.81,
        'gender': 0.68
    }
}
```

This also allows the platform to display race and gender estimates with independent confidence levels. If we know the race estimate is solid but the gender estimate is uncertain, users can make informed decisions about which to rely on.

### 2.4 OES Metro Occupation Data (Enhancement to Gender Method)

**The limitation of CPS + BLS alone:** The BLS occupation matrix gives national occupation mixes for each industry. But a software company in San Francisco has a very different occupation mix than a software company in rural Ohio. One skews heavily toward senior engineers; the other might have more diverse roles.

**What OES adds:** Your `oes_occupation_wages` table (414K rows, completely unused) contains occupation employment counts at the metro level, broken down by industry. This lets the gender estimation use *local* occupation mixes rather than national ones.

**How to use it:**
```python
def get_occupation_mix_local(naics_code, cbsa_code):
    """
    Returns occupation distribution for this industry in this metro.
    Falls back to national BLS matrix if metro has insufficient data.
    """
    ...
```

**Expected additional gain:** On top of the CPS × BLS method (expected 8-12pp gender MAE), using local occupation mixes could bring gender MAE down another 1-2pp for companies in major metros. Low priority to implement — get the national method working first, then upgrade.

---

## Phase 2.5: Hispanic Estimation Overhaul

Hispanic has a different problem than gender. Its 9.3pp MAE isn't because we're using the wrong model type — it's because we're using the same formula for Hispanic as for race, but Hispanic concentration is fundamentally geographic in a way that race isn't.

**The pattern:** Hispanic workers are heavily concentrated in specific regions (Southwest, Florida, New York City metro, Chicago) regardless of industry. A healthcare company in El Paso is probably 60-70% Hispanic. An identical healthcare company in rural Vermont is probably 2-3% Hispanic. The industry-level ACS signal that works for race is much weaker for Hispanic because location dominates.

**The current method** gives ACS (industry × state) a similar weight as LODES (county geography). For Hispanic estimation, geography should dominate.

### The Hispanic-Specific Method

Use a multi-source geography blend with much heavier geographic weighting:

```python
def estimate_hispanic_geography_heavy(county_fips, cbsa_code, state_fips, naics_code):
    """
    Geography-dominant Hispanic estimation.
    ACS industry signal is a small adjustment, not a primary input.
    """
    lodes_hispanic    = get_lodes_hispanic(county_fips)       # w = 0.35
    pums_hispanic     = get_pums_hispanic(cbsa_code, naics_code)  # w = 0.30
    tract_hispanic    = get_tract_hispanic(county_fips)       # w = 0.20
    acs_hispanic      = get_acs_hispanic(state_fips, naics_code)  # w = 0.15

    return (0.35 * lodes_hispanic + 0.30 * pums_hispanic
          + 0.20 * tract_hispanic + 0.15 * acs_hispanic)
```

This is the H1 method from the revision plan. All four data sources already exist in the database — this is a new weighting scheme, not new data.

**Expected improvement:** 0.5-1.5pp Hispanic MAE reduction (from 9.3pp toward ~7.5-8.0pp). Low implementation effort since no new data loading is required.

---

## Phase 2.6: Education and Age (New Dimensions)

These are bonus dimensions that don't exist in the current API at all. They don't improve race/gender/Hispanic MAE — they extend what the platform can tell users about a company's workforce.

**What data exists (unused):**

| Dimension | ACS | LODES | Estimation Difficulty |
|-----------|-----|-------|----------------------|
| Education (15 levels) | Yes, state × industry | Yes, 4 brackets by county | Medium — strong industry signal |
| Age (6 buckets) | Yes, state × industry | No | Higher — weaker geographic signal |

**These don't have EEO-1 ground truth** for validation (EEO-1 doesn't report education or age), so they can't be formally validated. Ship as "directional estimates" with explicit caveats — the flag tier system handles this.

**Suggested approach:**
- Education: Simple ACS × LODES blend using same IPF approach as race — use industry signal from ACS and geographic signal from LODES education brackets
- Age: ACS state × industry only (no LODES age data) — lower confidence, higher uncertainty flag
- Both use `YELLOW` confidence flag minimum — never auto-use-OK

**Implementation priority:** Low — do after race/gender/Hispanic improvements are validated.

---

## Phase 3: Expand and Improve the Gate

The gate is currently a logistic regression trained on 997 companies. This is adequate but not great. The key improvements are:

### 3.1 Expand the Training Set to ~3,500 Companies

**Current state:** The EEO-1 file has ~5,000 companies with usable data. V5 used only 997, leaving ~4,000 on the table.

**Why we didn't use all of them before:** The 997 companies in the training set came from an early selection pass. Expanding requires auditing the full EEO-1 file for data quality.

**The audit steps:**
1. Load the full EEO-1 file and deduplicate by company — some companies filed multiple years; keep the most recent
2. Filter out records with invalid NAICS codes, missing geography, or total headcount of 0
3. Filter out companies where no LODES/ACS data is available (they can't be estimated anyway)
4. Target: **3,500 training / 500 holdout**, stratified to ensure each industry group and region has proportional representation

**Why this matters:** The gate currently has very few examples for some segments (e.g., small Finance companies in rural areas). With more data, the gate can learn to distinguish cases that currently look identical to it.

### 3.2 Upgrade from Logistic Regression to LightGBM

**What logistic regression does:** Learns a linear combination of features to route to experts. It's fast and interpretable but can't capture interactions — for example, "Healthcare companies in the South are different from Healthcare companies in the Northeast, so route them differently."

**What LightGBM is:** A gradient boosted decision tree — it learns a series of if/then rules and can naturally capture interactions like "IF industry = Healthcare AND region = South THEN Expert B." It generally outperforms logistic regression when there are nonlinear relationships, which there definitely are here.

**Additional gate features to add:**
- ACS-vs-LODES divergence: how much do state industry demographics and county job demographics disagree? High divergence = uncertain case
- Tract diversity (Shannon entropy): how diverse is the surrounding census tract?
- PUMS available flag: does this company have a metro-level PUMS match?
- 4-digit NAICS code (not just industry group): more granular
- `lodes_minority_share` (replacing the leaked `minority_share` feature)
- Company size bucket (already used, keep it)

### 3.3 Per-Segment Calibration

**What calibration is:** Even after the gate picks the right expert, there are systematic biases. For example, Expert D consistently over-predicts Asian share by 3.1pp. V5 corrects this by subtracting the global Expert D Asian bias from every Expert D output.

**What per-segment calibration adds:** The bias isn't uniform. Expert D might over-predict Asian by 3pp for Healthcare companies but under-predict by 1pp for Finance companies. With enough training data (3,500 companies), we can estimate biases separately for each industry-region segment.

**Rules:**
- If the segment has ≥30 training companies: use segment-specific calibration
- If 15-29 companies: use industry-group calibration (broader)  
- If <15: fall back to global calibration (what V5 does)

---

## Phase 4: New Data Sources

### 4.1 Quarterly Workforce Indicators (QWI)

**What it is:** Census Bureau data that combines unemployment insurance records with demographic data. Provides employment counts by race and sex at the 4-digit NAICS × county level — more granular than LODES (which only has 3 broad sectors) and more granular than ACS (which only has industry × state).

**Why it matters:** QWI would give us a data source that simultaneously knows the industry *and* the geography at a fine level. Currently, industry comes from ACS (state-level) and geography comes from LODES (county-level, but only 3 sectors). QWI bridges this gap.

**Status:** Data downloaded to `New Data sources 2_27/2024_annual_by_industry/`. Not yet loaded into the database.

**ETL:** Load into `qwi_county_industry_demo`, create lookup function in `data_loaders.py`.

### 4.2 LODES Origin-Destination File (Labor Shed Estimation)

**What it is:** The LODES OD file traces commuting flows — which residential census tracts workers commute *from* to reach a given worksite. If you know where workers live and you know the demographics of those residential tracts, you can estimate the demographics of the workforce at that worksite.

**Why it's valuable:** Standard LODES WAC data tells you about jobs in a census tract. But for companies where workers don't live near the worksite (construction, trucking, staffing), WAC demographics are unreliable. The OD file traces actual commute patterns to get a better "labor shed" estimate.

**Caveat:** This is an indirect inference. Workers commuting from a tract doesn't mean the workers look exactly like the residents of that tract (ecological fallacy). Use as a supplementary signal, not as the primary estimate.

**Status:** Data available at `New Data sources 2_27/LODES_bulk_2022/`. Not yet loaded.

**Priority:** Lower than QWI. Focus on QWI first.

### 4.3 CPS Table 18: Gender by Industry

**What it is:** The companion table to Table 11 — gives gender breakdown by industry rather than by occupation. Already referenced in documentation; likely already downloaded.

**Use case:** National-level gender benchmarks by industry. Used as a calibration reference to catch cases where the occupation-weighted estimate looks implausible (e.g., estimated 95% male for a nursing home).

**Integration:** Load into `cps_industry_gender_2025`, use in Expert G's fallback chain and as a sanity-check cap on gender estimates.

---

## Phase 5: Hardcoded Heuristic Methods (Don't Fear These)

The trend in V3-V5 was toward learned routing and away from hand-coded rules. But hardcoded rules are not bad — they're excellent when you have strong domain knowledge. Here are specific heuristics that should be added as hard overrides:

### 5.1 Industry-Specific Gender Floors and Ceilings

Some industries have known gender distributions that don't change much:
- NAICS 23 (Construction): Almost never more than 15% female. If the occupation-weighted estimate says 35% female, something went wrong. Cap at 15% and flag for review.
- NAICS 721 (Hotels/Motels): Typically 55-65% female
- NAICS 6211 (Physicians): Approximately 40% female (was 30% a decade ago)
- NAICS 481 (Air transportation): Approximately 40% female overall (pilots ~7%, flight attendants ~74%, ground crew ~20%)

**Implementation:** A `GENDER_BOUNDS` dictionary keyed by NAICS2 or NAICS3, with soft and hard bounds. Soft bounds trigger a flag; hard bounds cap the estimate and require a strong signal to override.

### 5.2 High-Confidence NAICS Lookup Table

For industries where Census data is sparse but the true gender/race split is well-established from other sources, maintain a lookup table of national benchmarks. This is just a Python dictionary:

```python
NAICS_GENDER_BENCHMARKS = {
    '2361': {'pct_female': 8.5,  'source': 'CPS2025', 'confidence': 'high'},   # Residential construction
    '6211': {'pct_female': 40.2, 'source': 'CPS2025', 'confidence': 'high'},   # Physicians
    '7211': {'pct_female': 58.1, 'source': 'CPS2025', 'confidence': 'medium'}, # Hotels
    ...
}
```

When the occupation-weighted estimate has low confidence (sparse occupation data for this NAICS), blend toward the benchmark.

### 5.3 Workforce Composition Flags

Certain combinations of NAICS + company characteristics are strong signals that can override the general model:
- NAICS 4812 (Non-scheduled air) + small company (< 50 employees) → likely charter operation → male-dominated
- NAICS 6232 (Residential care facilities) → very likely female-dominated
- NAICS 5617 (Services to buildings, including janitorial) → likely 30-40% female, high Hispanic

These don't need to be learned — they're documented industry knowledge. A dictionary of these patterns is more reliable than waiting for the gate to learn them from limited examples.

---

## Phase 6: Tiered Confidence and Review Flags

One of the biggest problems in V5 is that 94.7% of companies get flagged for review, making the flag useless. V6 should implement a three-tier system:

### Tier Definitions

**Red Flag (< 15% estimated accuracy):** Manual review required before using this estimate. Triggers when:
- No LODES data for this county
- No ACS data for this industry
- Gate confidence < 0.35 (very uncertain routing)
- Estimated demographics are implausible (e.g., 0% for a major race category after smoothing)

**Yellow Flag (directional use only):** Use with caution, appropriate for broad industry comparisons but not company-specific decisions. Triggers when:
- PUMS data not available (fell back to state ACS)
- Gate confidence 0.35-0.60
- Company is in NAICS with historically high estimation error (Construction, Admin/Staffing)
- EEO-1 ground truth gap > 5 years old

**Green (automated use OK):** Triggers when:
- PUMS metro coverage confirmed
- Gate confidence > 0.60
- Company is in NAICS with historically low estimation error (Finance, Healthcare, Information)
- Historical MAE for this segment < 4pp

### Implementation

Track two things per estimate:
1. `data_quality_score`: how complete/reliable the input data is (0-1)
2. `gate_confidence`: the gate's confidence in its routing decision (max probability of the chosen expert)

Combine into a flag tier:
```python
if data_quality < 0.4 or gate_confidence < 0.35:
    flag = 'RED'
elif data_quality < 0.7 or gate_confidence < 0.60:
    flag = 'YELLOW'
else:
    flag = 'GREEN'
```

---

## Permanent Holdout: The 400-Company Gold Standard

### Why This Needs to Happen Before V6 Training Starts

Every version of the model so far has used a different holdout pool. V5 evaluated on 208 companies; V6 will evaluate on ~500 different ones. This makes cross-version comparison unreliable — if V7 looks better than V6, you can't tell whether the model actually improved or just got a easier holdout draw.

The fix is to designate 400 companies **right now**, before V6 training begins, and never train any version on them. These 400 become your permanent measuring stick. Every future version — V6, V7, V8 — gets evaluated on the same companies, making comparisons valid and meaningful.

This is sometimes called a "gold standard" or "benchmark" holdout. The key rule: **once selected, these companies are never used for training in any version, ever.** They are evaluation-only for the lifetime of the project.

### How Many: 400

The right size balances two competing needs:

- **Too small** (< 200): Per-segment estimates are too noisy. If you have 8 Finance companies in the holdout and the model makes one big mistake, your Finance MAE swings by 3pp — that's noise, not signal.
- **Too large** (> 500): You're sacrificing meaningful training data. Every company in the permanent holdout is one fewer example the gate can learn from.

400 is the right number because it gives you **~20-30 companies per major industry group**, which is enough to get a stable MAE estimate for each segment. With 18 NAICS groups across 4 regions, you have 72 potential cells — you won't fill all of them, but you'll cover the ~25 cells that actually matter.

### How to Stratify: Proportional with a Floor

**Do not** stratify purely equally (same number per segment — produces distorted overall MAE) and **do not** stratify purely proportionally (rare-but-hard segments get too few companies).

The rule: for each industry group × region cell:
- **Minimum: 8 companies** if at least 8 exist in the EEO-1 pool
- **Maximum: proportional** — a segment that is 20% of the EEO-1 pool should be ~20% of the holdout
- **Cap at 40** per cell — no single segment dominates

In practice this means your high-frequency segments (Healthcare Northeast, Finance Northeast) get 25-40 companies each, and low-frequency segments (Agriculture West, Utilities Midwest) get their floor of 8.

### The 18 Industry Groups

Based on the NAICS groupings already used in the model:

| Group | NAICS Codes |
|-------|------------|
| Accommodation/Food Svc | 72 |
| Admin/Staffing | 56 |
| Agriculture/Mining | 11, 21 |
| Chemical/Material Mfg | 325–327 |
| Computer/Electrical Mfg | 334–335 |
| Construction | 23 |
| Finance/Insurance | 52 |
| Food/Bev Manufacturing | 311, 312 |
| Healthcare/Social | 62 |
| Information | 51 |
| Metal/Machinery Mfg | 331–333 |
| Other Manufacturing | remaining 31–33 |
| Professional/Technical | 54 |
| Retail Trade | 44–45 |
| Transport Equip Mfg | 336 |
| Transportation/Warehousing | 48–49 |
| Utilities | 22 |
| Other | everything else |

### The 4 Regions

| Region | States |
|--------|--------|
| Northeast | CT, ME, MA, NH, NJ, NY, PA, RI, VT |
| South | AL, AR, DC, DE, FL, GA, KY, LA, MD, MS, NC, OK, SC, TN, TX, VA, WV |
| Midwest | IA, IL, IN, KS, MI, MN, MO, ND, NE, OH, SD, WI |
| West | AK, AZ, CA, CO, HI, ID, MT, NM, NV, OR, UT, WA, WY |

### Selection Script: `select_permanent_holdout.py`

Create this script in `scripts/analysis/demographics_comparison/`. Run it once, save the output as `selected_permanent_holdout_400.json`, and never re-run it — the selection is frozen.

```python
"""
select_permanent_holdout.py

Selects 400 companies from the full EEO-1 pool as a permanent holdout.
Run ONCE before V6 training begins. Output is frozen forever.

Usage: python select_permanent_holdout.py
Output: selected_permanent_holdout_400.json
"""
import json
import random
import pandas as pd
from eeo1_parser import load_full_eeo1  # existing parser

SEED = 42  # Fixed seed — same result every run
TARGET_TOTAL = 400
FLOOR_PER_CELL = 8
CAP_PER_CELL = 40

NAICS_GROUPS = {
    'Accommodation/Food Svc':   lambda n: n[:2] in ('72',),
    'Admin/Staffing':           lambda n: n[:2] in ('56',),
    'Agriculture/Mining':       lambda n: n[:2] in ('11', '21'),
    'Construction':             lambda n: n[:2] in ('23',),
    'Finance/Insurance':        lambda n: n[:2] in ('52',),
    'Healthcare/Social':        lambda n: n[:2] in ('62',),
    'Information':              lambda n: n[:2] in ('51',),
    'Manufacturing':            lambda n: n[:2] in ('31', '32', '33'),
    'Professional/Technical':   lambda n: n[:2] in ('54',),
    'Retail Trade':             lambda n: n[:2] in ('44', '45'),
    'Transportation/Warehousing': lambda n: n[:2] in ('48', '49'),
    'Utilities':                lambda n: n[:2] in ('22',),
    'Other':                    lambda n: True,  # catch-all, checked last
}

REGION_MAP = {
    'Northeast': {'CT','ME','MA','NH','NJ','NY','PA','RI','VT'},
    'South':     {'AL','AR','DC','DE','FL','GA','KY','LA','MD',
                  'MS','NC','OK','SC','TN','TX','VA','WV'},
    'Midwest':   {'IA','IL','IN','KS','MI','MN','MO','ND','NE','OH','SD','WI'},
    'West':      {'AK','AZ','CA','CO','HI','ID','MT','NM','NV','OR','UT','WA','WY'},
}

def assign_region(state_abbr):
    for region, states in REGION_MAP.items():
        if state_abbr in states:
            return region
    return 'Other'

def assign_naics_group(naics4):
    for group_name, test_fn in NAICS_GROUPS.items():
        if test_fn(naics4):
            return group_name
    return 'Other'

def select_permanent_holdout():
    random.seed(SEED)

    # Load and deduplicate EEO-1 (keep most recent filing per company)
    df = load_full_eeo1()
    df = df.sort_values('year', ascending=False).drop_duplicates('company_id')
    df = df[df['total_employees'] > 0]
    df = df[df['naics4'].notna()]

    # Assign stratification cells
    df['naics_group'] = df['naics4'].apply(assign_naics_group)
    df['region'] = df['state_abbr'].apply(assign_region)
    df['cell'] = df['naics_group'] + '|' + df['region']

    # --- Step 1: Flag sparse cells (< 8 companies total in EEO-1) ---
    cell_counts = df['cell'].value_counts()
    sparse_cells = set(cell_counts[cell_counts < FLOOR_PER_CELL].index)

    # --- Step 2: Compute target per cell ---
    total_companies = len(df)
    targets = {}
    for cell, count in cell_counts.items():
        if cell in sparse_cells:
            # Take all of them — segment too rare to train on anyway
            targets[cell] = count
        else:
            proportional = round((count / total_companies) * TARGET_TOTAL)
            targets[cell] = max(FLOOR_PER_CELL, min(CAP_PER_CELL, proportional))

    # Adjust total to hit TARGET_TOTAL exactly
    # Scale down the largest cells if we've overshot
    while sum(targets.values()) > TARGET_TOTAL:
        biggest_cell = max(
            (c for c in targets if c not in sparse_cells),
            key=lambda c: targets[c]
        )
        targets[biggest_cell] -= 1

    # --- Step 3: Sample from each cell ---
    selected_ids = []
    for cell, n in targets.items():
        cell_df = df[df['cell'] == cell]
        n_sample = min(n, len(cell_df))
        sampled = cell_df.sample(n=n_sample, random_state=SEED)
        selected_ids.extend(sampled['company_id'].tolist())

    # --- Step 4: Save ---
    output = {
        'version': 'permanent_holdout_v1',
        'seed': SEED,
        'total_selected': len(selected_ids),
        'cell_counts': {
            cell: len([i for i in selected_ids
                       if df.set_index('company_id').loc[i, 'cell'] == cell])
            for cell in targets
        },
        'company_ids': selected_ids,
        'note': 'FROZEN — never use these companies for training in any version'
    }

    with open('selected_permanent_holdout_400.json', 'w') as f:
        json.dump(output, f, indent=2)

    print(f"Selected {len(selected_ids)} companies")
    print(f"Cell distribution:")
    for cell, count in sorted(output['cell_counts'].items()):
        print(f"  {cell}: {count}")

if __name__ == '__main__':
    select_permanent_holdout()
```

### What to Do With the Output

1. Run the script once before any V6 training begins
2. Commit `selected_permanent_holdout_400.json` to the repo with message "FREEZE: permanent holdout — never modify"
3. Add a check to all future training scripts that asserts zero overlap with this file:

```python
# Add to top of any training script
def assert_no_holdout_contamination(training_ids, holdout_file='selected_permanent_holdout_400.json'):
    with open(holdout_file) as f:
        holdout = set(json.load(f)['company_ids'])
    overlap = set(training_ids) & holdout
    assert len(overlap) == 0, f"CONTAMINATION: {len(overlap)} holdout companies in training set!"
```

4. Add a `validate_permanent_holdout.py` script that evaluates every future version against these same 400 companies and logs results to a running comparison table

### Version Comparison Table (Maintained in `selected_permanent_holdout_400.json`)

As each new version ships, append results:

| Version | Race MAE | Hispanic MAE | Gender MAE | P>20pp | P>30pp | Date |
|---------|----------|-------------|-----------|--------|--------|------|
| V5 | TBD (backfill) | TBD | TBD | TBD | TBD | — |
| V6 | — | — | — | — | — | — |
| V7 | — | — | — | — | — | — |

This table becomes the authoritative record of model improvement over time.

### Holdout Pool Lifecycle

As the EEO-1 pool is consumed across versions:

| Version | Training Pool | Permanent Holdout | Version Holdout |
|---------|--------------|------------------|----------------|
| V5 | 997 companies | Not yet selected | 208 companies |
| **V6** | **~3,500** (incl. V5 holdout) | **400 frozen now** | **~500 from remainder** |
| V7 | ~4,100 (incl. V6 holdout) | Same 400 | ~400 from remainder |
| V8+ | ~4,500 (nearly full pool) | Same 400 | Use temporal holdout (new EEO-1 filings) |

When the pool is exhausted, shift to a **temporal holdout** — the most recent year of EEO-1 filings is always held back. The model was trained on older data and evaluated on newer data, which is actually more realistic: in production you're always estimating companies whose current EEO-1 you don't have.

---

## Implementation Sequence

The right order — data infrastructure first, then better inputs, then architecture:

| Step | Phase | What | Effort | Expected Gain |
|------|-------|------|--------|--------------|
| 0 | Pre-work | **Freeze permanent holdout (run once, never again)** | 2 hours | Eval integrity forever |
| 1 | Pre-work | Remove BDS nudge | 1 hour | +0.045pp MAE |
| 2 | Pre-work | Fix ground truth leak (replace `minority_share`) | 2 hours | Integrity fix |
| 3 | Pre-work | Add soft routing (blend instead of argmax) | 2 hours | ~0.3pp race MAE |
| 4 | Phase 0 | Verify CNS columns in LODES table (or re-run ETL) | 1-2 days | Unlocks Steps 8-9 |
| 5 | Phase 0 | Build QCEW concentration loader | 4 hours | Unlocks Step 9 |
| 6 | Phase 0 | Build metro ACS loader | 3 hours | ~0.1-0.2pp race MAE |
| 7 | Phase 0 | Build multi-tract ensemble loader | 3 hours | ~0.1-0.2pp race MAE |
| 8 | Phase 1.5 | Implement M9a (industry-LODES IPF) + ablation A | 6 hours | **~0.5-1.0pp race MAE** |
| 9 | Phase 1.5 | Implement M9b (QCEW-weighted) + ablation B | 4 hours | ~0.2-0.4pp race MAE |
| 10 | Phase 1.5 | Implement M9c (combined) + ablation C | 4 hours | ~0.5-1.5pp race MAE total |
| 11 | Phase 1 | Restore Expert E (Finance/Utilities hard route) | 4 hours | ~0.3-0.5pp race MAE |
| 12 | Phase 1 | Add occupation-weighted Expert F (Manufacturing) | 6 hours | ~0.3pp race MAE |
| 13 | Phase 2 | Load CPS Table 11 into database | 3 hours | Setup for Step 14 |
| 14 | Phase 2 | Build occupation-weighted gender method (G1) | 8 hours | **~6-10pp gender MAE** |
| 15 | Phase 2 | Separate gender estimation track + confidence | 4 hours | Modularity |
| 16 | Phase 2.5 | Build geography-heavy Hispanic method (H1) | 4 hours | ~0.5-1.5pp Hispanic MAE |
| 17 | Phase 3 | Expand EEO-1 training set audit (997→3,500) | 6 hours | Gate quality foundation |
| 18 | Phase 3 | Retrain gate on expanded data | 4 hours | ~0.3pp race MAE |
| 19 | Phase 3 | Upgrade gate to LightGBM | 6 hours | ~0.2pp race MAE |
| 20 | Phase 3 | Add richer gate features (QCEW LQ, divergence, etc.) | 4 hours | ~0.2pp race MAE |
| 21 | Phase 3 | Per-segment calibration | 8 hours | ~0.2pp race MAE |
| 22 | Phase 4 | Load QWI into database | 8 hours | New granular source |
| 23 | Phase 4 | Add QWI as Expert input | 6 hours | ~0.3pp race MAE |
| 24 | Phase 5 | Industry gender bounds/heuristics | 4 hours | ~1pp gender MAE |
| 25 | Phase 6 | Tiered confidence flags | 4 hours | Red flag rate < 20% |
| 26 | Phase 2.6 | Education/age estimation (new dimensions) | 1 week | New API output |

**The big shift from V5 thinking:** Steps 1-3 are quick fixes you should do in a single session. Steps 4-10 (data infrastructure + new base methods) are the most important work in the entire V6 effort — they attack the ceiling. Steps 11-25 (architecture/gate) are still valuable but produce smaller gains per unit of effort.

---

## Expert Pool Summary

After V6 is complete, the full expert pool:

| Expert | Method | Input Data | Hard-Routed For | Gate Routes Here For |
|--------|--------|-----------|-----------------|----------------------|
| **Expert A** | Smooth-IPF with prior | ACS + LODES | — | Sparse data / rural |
| **Expert B** | Tract-heavy 35/25/40 | ACS + LODES + Tract | — | High-minority urban |
| **Expert D** | Dampened IPF (M3b) | ACS + LODES | — | General (most companies) |
| **Expert E** *(new)* | Raw IPF M3_ORIGINAL | ACS + LODES | Finance (52), Utilities (22) | — |
| **Expert F** *(new)* | Occupation-weighted IPF | ACS occ + BLS matrix | — | Manufacturing, Transport |
| **Expert G** *(new)* | Industry-LODES IPF | ACS + **LODES-CNS** | — | Promoted if M9c beats M3c |
| **M1B** | Learned-weight ACS/LODES | ACS + LODES | Admin/Staffing (56) | — |
| **Gender Expert** *(new)* | CPS Table 11 × BLS occ | CPS + BLS + OES | All companies (separate track) | — |
| **Hispanic Expert** *(new)* | Geography-heavy blend | LODES + PUMS + Tract + ACS | All companies (separate track) | — |

---

## Key Principles

**1. Addition, not replacement.** Every method stays in the codebase. New methods go on top. Old methods become fallbacks.

**2. Data first, architecture second.** Better inputs to simple formulas beats smarter formulas fed the same bad inputs. Prove the data improvement works before touching the gate.

**3. Test in isolation before combining.** Run the ablation study (experiments A-H) before building the combined pipeline. You need to know which data sources actually contribute.

**4. Separate concerns.** Race, Hispanic, and gender estimation are allowed to use completely different models. Tying them together was a convenience that hurt gender accuracy.

**5. Hardcoded knowledge is fine.** When you have strong prior knowledge (Finance workers are rarely construction laborers), hardcode it. Don't wait for the model to learn something you already know.

**6. The training set is the foundation.** A better gate trained on 3,500 companies is worth more than any algorithmic improvement trained on 997.

**7. Confidence matters.** A system that tells you "I'm 90% confident" when it's actually 60% confident causes real harm. The tiered flag system is not a nice-to-have — it determines whether users can trust the output.

---

## V6 Files to Create/Modify

| File | Action | What Changes |
|------|--------|-------------|
| `data_loaders.py` | Modify | Add `get_lodes_industry_race()`, `get_qcew_concentration()`, `get_acs_race_metro()`, `get_multi_tract_demographics()`, `get_pct_female_by_occupation()`, `get_lodes_minority_share()` |
| `methodologies.py` | Modify | Add Expert E (M3_ORIGINAL), Expert F (occ-weighted IPF), M9a/M9b/M9c (industry-LODES methods) |
| `methodologies_v6.py` | New | All new V6 methods: Gender Expert (G1/G2), Hispanic Expert (H1), education/age |
| `cached_loaders_v6.py` | New | Extends V5; adds CPS Table 11, QCEW, OES metro occupation lookups |
| `build_gate_training_data.py` | Modify | Replace `minority_share` with `lodes_minority_share`; add QCEW LQ, ACS-LODES divergence, PUMS flag |
| `train_gate_v2.py` | New | LightGBM gate; trained on expanded 3,500-company dataset |
| `load_cps_table11.py` | New | ETL: `cpsaat11.xlsx` → `cps_occ_gender_2025` table |
| `load_qwi.py` | New | ETL: QWI files → `qwi_county_industry_demo` table |
| `run_comparison_v6.py` | New | Ablation study runner: experiments A-H, all new + existing methods on 997-company training set |
| `validate_v6_final.py` | New | Holdout validation with all experts, gender/Hispanic tracks, tiered flags |
| `select_permanent_holdout.py` | New | One-time script to freeze 400-company gold standard holdout |
| `selected_permanent_holdout_400.json` | New (frozen) | Output of above — never modify after creation |
| `validate_permanent_holdout.py` | New | Evaluates any model version against the frozen 400 |
| `config.py` | Modify | Add `GENDER_BOUNDS`, `NAICS_GENDER_BENCHMARKS`, `NAICS_TO_CNS` mappings |

---

## Acceptance Criteria

V6 ships when all of the following are true on the **fresh holdout** (never used in training):

| Criterion | V5 Baseline | V6 Target | V6 Stretch |
|-----------|------------|-----------|-----------|
| Race MAE | 5.182pp | **< 4.50pp** | < 4.00pp |
| P>20pp | 20.67% | **< 16%** | < 12% |
| P>30pp | 8.17% | **< 6%** | < 4% |
| Abs Bias | 1.345 | **< 1.10** | < 0.80 |
| Hispanic MAE | 9.252pp | **< 8.00pp** | < 7.00pp |
| Gender MAE | 18.098pp | **< 12.00pp** | < 9.00pp |
| Ground truth leak | FAIL | **PASS** | PASS |
| Red flag rate | 94.7% | **< 15%** | < 10% |

Additionally:
- [ ] Ablation study results documented (experiments A-H each run and recorded)
- [ ] Permanent holdout (400 companies) frozen before any V6 training
- [ ] Contamination check passes (zero holdout companies in training set)
- [ ] Per-segment MAE reported for all 18 industry groups × 4 regions
- [ ] Gender and Hispanic tracked independently from race

---

*Last updated: 2026-03-09*
*Incorporates: V5 Revision Plan (Claude Code Opus 4.6, post-hoc review)*
*Previous version: V5 (Gate v1 + Expert A/B/D + PUMS metro)*

