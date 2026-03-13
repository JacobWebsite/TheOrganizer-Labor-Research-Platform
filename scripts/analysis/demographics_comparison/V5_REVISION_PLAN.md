# V5 Demographics Estimation: Revision Analysis & Improvement Plan

**Date:** 2026-03-09
**Author:** Claude Code (Opus 4.6) -- post-hoc review of V2/V3/V4/V5 reports
**Scope:** Diagnostic analysis of data utilization gaps, base model improvements, and gate refinements

---

## 1. Executive Summary

The demographics estimation pipeline evolved across 4 generations (V2-V5) from simple blends to expert routing, improving race MAE from ~5.74 to ~5.18 on holdout. But this evolution prioritized **model architecture** (routing, gating, calibration) over **data utilization**. The 30 base models all draw from the same narrow slice of available data, leaving enormous signal on the table.

### The core problem

Every method in the pipeline -- all 30 of them -- estimates race demographics using some combination of just **two distributions**:

```
ACS:   "What % of [industry] workers in [state] are [race]?"
LODES: "What % of all workers in [county] are [race]?"
```

That's it. The fanciest method (M3c variable-dampened IPF) just finds a better way to multiply these two numbers together. The gate (V5) just picks which multiplication to use. But the fundamental ceiling is set by these two inputs.

Meanwhile, the database contains:

| Data source | Available | Used by demographics pipeline |
|------------|-----------|-------------------------------|
| ACS race/hispanic/gender by state x industry | Yes | **Yes** (primary input) |
| ACS education (15 levels) by state x industry | Yes | **No** |
| ACS age (6 buckets) by state x industry | Yes | **No** |
| ACS insurance (6 types) by state x industry | Yes | **No** |
| ACS metro_cbsa field (metro-level aggregation) | Yes | **No** (PUMS used instead, 73.5% coverage) |
| LODES race/hispanic/gender by county | Yes | **Yes** (primary input) |
| LODES education (4 brackets) by county | Yes | **No** |
| LODES industry-specific employment (CNS01-CNS20) | Yes | **No** |
| LODES tract-level demographics | Yes | Partially (M2 family only) |
| PUMS metro x industry demographics | Yes (V5) | **Yes** (V5 fallback) |
| Census tract residential demographics | Yes | Partially (M2 family only) |
| BLS occupation matrix (industry x occupation) | Yes | Poorly (M4 family, underperforms) |
| ACS occupation x sex tabulations | Loadable | **No** |
| QCEW county x industry employment/wages | Yes (1.9M rows) | **No** |
| OES occupation x area wages | Yes (414K rows) | **No** |
| BDS-HC sector-level brackets | Yes (V5) | Net negative, disabled |
| QWI demographics by firm characteristics | Fetchable | **No** |

**The biggest single improvement is not a better gate or more experts -- it is giving the base models better inputs.**

### Impact estimate

| Improvement category | Est. race MAE gain | Effort | Section |
|---------------------|-------------------|--------|---------|
| Better base model inputs (LODES industry, QCEW weighting) | 0.5-1.5pp | Medium | Sec 3-4 |
| Geographic resolution (tract ensembles, metro ACS) | 0.2-0.5pp | Low-Medium | Sec 5 |
| Dimension-specific models (gender via occupation) | 5-10pp gender MAE | Medium | Sec 6 |
| Gate/routing fixes (soft routing, leak fix, GBT) | 0.2-0.5pp | Low | Sec 7 |
| More training data | 0.3-0.5pp | Medium | Sec 8 |

---

## 2. What Each Version Got Right and Wrong

### V2: Discovered LODES > ACS but didn't ask why

**Right:** M1b learned that most industries optimize to 0.30 ACS / 0.70 LODES. County-level workplace demographics beat industry-level survey data.

**Wrong:** Treated this as a weight-tuning finding instead of asking the deeper question: *LODES wins because it's geographic. But LODES doesn't know what industry the company is in. What if we could get geographic data that ALSO knows the industry?*

That data exists. LODES WAC files contain **CNS01-CNS20**: employment counts broken down by 20 NAICS supersectors, per Census block. The ETL in `lodes_curate_demographics.py` loads these columns into `cur_lodes_geo_metrics` but the demographics pipeline **never queries them**. Instead of asking "what % of ALL workers in this county are Black?", we could ask "what % of MANUFACTURING workers in this county are Black?" -- a dramatically more relevant question.

**Missed finding:** The three industries where ACS beats LODES (Construction 0.90/0.10, Admin/Staffing 0.90/0.10, Utilities 0.90/0.10) are all industries where workers deploy away from HQ. This is a COMMUTING signal. LODES captures workplace location; for these industries, the company's registered county isn't where the workers are. QCEW establishment counts could identify multi-site employers.

### V3: Refined dampening but stopped exploring data

**Right:** Variable dampening (M3c) with per-industry alpha is the best IPF variant. The alpha parameter effectively learns how much to trust ACS vs LODES per industry.

**Wrong:** All 8 new V3 methods are variations on blending/dampening the same two inputs. None tried adding new inputs. The dimensional breakdowns show the same patterns as V2: Healthcare is terrible (10.9 MAE), high-minority is terrible (10.4 MAE), West is hardest. These patterns are stable across methods because the DATA is the bottleneck, not the formula.

**Key evidence:** M4c (top-10 occupations) and M4d (state-top-5) both produce IDENTICAL MAE to M4 (4.88/4.88). Changing how many occupations you include doesn't matter because the occupation-to-race mapping itself is too noisy. But this only means occupation fails for RACE. The V2 report shows M3 IPF wins gender (10.93 MAE) -- occupation data was never tried for gender specifically.

### V4: Built routing before maximizing base model quality

**Right:** M3e routing Finance/Utilities to undampened IPF works because these industries are in homogeneous geographies where IPF's amplification is correct. M8 hand-tuned router captures this and other segment-specific patterns.

**Wrong:** The routing gains are small (M3e: 4.26 vs M3c: 4.41 = 0.15pp). The V4 report shows all top methods converge within a 0.5pp band (4.26-4.74), suggesting we've extracted most of the signal from the current two inputs. Adding more routing complexity on top of exhausted inputs yields diminishing returns.

**Missed opportunity:** V4 shows QCEW data was loaded (1.9M rows in `qcew_annual`) but never connected to the demographics pipeline. QCEW provides county x industry employment counts -- exactly the bridge between LODES (geographic, all-industry) and ACS (industry-specific, state-level).

### V5: Gate added architectural complexity over an underfed foundation

**Right:** Smoothing floor fixed zero-collapse. PUMS metro data reduced bias. OOF calibration is principled.

**Wrong:** Gate v1 improves holdout by only 0.052pp MAE. The entire expert+gate+calibration system adds ~1,000 lines of code for a gain smaller than random holdout variation. Meanwhile, the `minority_share` feature leaks ground truth (Section 7.1).

**Net assessment:** V2-V5 spent 4 iterations refining how to combine ACS and LODES. The next iteration should focus on what ELSE to feed the models.

---

## 3. Highest-Impact Data Gap: Industry-Specific LODES

### 3.1 The problem

Current LODES usage:
```python
# data_loaders.py - get_lodes_race()
SELECT total_jobs, jobs_white, jobs_black, jobs_asian, ...
FROM cur_lodes_geo_metrics
WHERE county_fips = %s
```

This returns demographics for **all workers in the county regardless of industry**. A pharmaceutical company in a county with a large agricultural sector gets blended with farm worker demographics.

### 3.2 The available data

LODES WAC files contain industry-specific employment per block:
```
CNS01: Agriculture/Forestry/Fishing (NAICS 11)
CNS02: Mining/Quarrying/Oil/Gas (NAICS 21)
CNS03: Utilities (NAICS 22)
CNS04: Construction (NAICS 23)
CNS05: Manufacturing (NAICS 31-33)
...
CNS20: Public Administration (NAICS 92)
```

The ETL in `lodes_curate_demographics.py` processes these from the raw WAC .gz files. The block-level data aggregates to tract and county levels.

### 3.3 What we can build

**Industry-weighted LODES demographics:** Instead of total county demographics, weight by industry employment share:

```python
def get_lodes_industry_weighted_race(county_fips, naics_2digit):
    """
    Estimate race demographics for a specific industry in a specific county.

    Uses LODES CNS codes to weight: if 30% of jobs in this county's NAICS 31-33
    sector are in tracts that are 60% White, and 70% are in tracts that are 40% White,
    the industry-weighted estimate is 0.3*60 + 0.7*40 = 46% White.
    """
    # Map NAICS to CNS code
    cns_code = NAICS_TO_CNS[naics_2digit]

    # Get tract-level data: demographics + industry employment
    tracts = query("""
        SELECT t.race_white_pct, t.race_black_pct, ...,
               t.{cns_code} as industry_jobs, t.total_jobs
        FROM cur_lodes_tract_metrics t
        WHERE t.county_fips = %s AND t.{cns_code} > 0
    """, county_fips)

    # Weight demographics by industry employment in each tract
    total_industry_jobs = sum(t.industry_jobs for t in tracts)
    weighted = {}
    for cat in RACE_CATEGORIES:
        weighted[cat] = sum(
            t[cat] * t.industry_jobs / total_industry_jobs
            for t in tracts
        )
    return weighted
```

This is the LODES equivalent of what PUMS does for ACS -- adding industry specificity to geographic data.

### 3.4 Expected impact

The current best method (M3c) computes `ACS_industry_state ^ alpha * LODES_all_county ^ (1-alpha)`. The industry-weighted LODES version would compute `ACS_industry_state ^ alpha * LODES_industry_county ^ (1-alpha)` -- both inputs now carry industry AND geography signal.

**Conservative estimate:** 0.5-1.0pp race MAE improvement. The evidence:
- V2 showed LODES dominates ACS (0.70 vs 0.30 weight) for most industries
- LODES dominates BECAUSE it's geographic, but it loses information by being all-industry
- Restoring industry specificity to the dominant input should significantly reduce the industry-geography mismatch that drives errors

**Where it helps most:**
- Counties with diverse industry mixes (e.g., a county with both a hospital and a factory)
- High-minority companies (the biggest error source) where industry composition within the county differs from overall composition
- Urban areas (748 of 997 companies) where multiple industries coexist

### 3.5 Implementation requirements

1. Verify that `cur_lodes_tract_metrics` contains the CNS01-CNS20 columns (or re-run the ETL to include them)
2. Build the NAICS-to-CNS mapping (straightforward: 2-digit NAICS -> 1 of 20 supersectors)
3. Create `get_lodes_industry_race(county_fips, naics_2digit)` in data_loaders.py
4. Create new method variants (M1b-IND, M3c-IND, etc.) that use industry-weighted LODES
5. Evaluate on the 997-company training set + holdout

---

## 4. Second-Highest Impact: QCEW Industry Concentration

### 4.1 The problem

All current methods assume the company's county is representative. But a pharma company in a county dominated by government employment will get poor estimates because the county-level demographics are government-worker demographics.

### 4.2 The available data

`qcew_annual` (1.9M rows) contains:
- `area_fips` (county)
- `industry_code` (NAICS, multiple levels)
- `annual_avg_emplvl` (average employment)
- `annual_avg_estabs` (number of establishments)
- `avg_annual_pay`
- `location_quotient` (industry concentration relative to national)

### 4.3 What we can build

**Industry concentration weighting:** Use QCEW to determine how representative the county is for this industry:

```python
def get_industry_concentration(county_fips, naics_2digit):
    """
    Returns location quotient and employment share for this industry in this county.
    LQ > 1.0 means the industry is more concentrated here than nationally.
    """
    row = query("""
        SELECT location_quotient, annual_avg_emplvl,
               annual_avg_emplvl::float / NULLIF(
                   (SELECT SUM(annual_avg_emplvl) FROM qcew_annual
                    WHERE area_fips = %s AND industry_code = '10'), 0
               ) as industry_share
        FROM qcew_annual
        WHERE area_fips = %s AND industry_code = %s AND year = 2023
    """, county_fips, county_fips, naics_2digit)
    return row
```

**Usage in estimation:** When LQ is high (e.g., > 1.5), LODES county data IS the industry data -- weight LODES more. When LQ is low (e.g., < 0.5), the county has very few workers in this industry -- LODES is unreliable, weight ACS more:

```python
def adaptive_weight(base_acs_weight, lq):
    """Adjust ACS/LODES weight based on industry concentration."""
    if lq > 1.5:  # industry is overrepresented locally
        return max(base_acs_weight - 0.15, 0.20)  # trust LODES more
    elif lq < 0.5:  # industry barely exists locally
        return min(base_acs_weight + 0.15, 0.80)  # trust ACS more
    return base_acs_weight
```

### 4.4 Expected impact

0.2-0.5pp race MAE improvement. The biggest gains come from companies in counties where their industry is a small fraction of employment (the county demographics are irrelevant) and from multi-industry counties where overall LODES averages are misleading.

### 4.5 Complementarity with Section 3

Industry-weighted LODES (Section 3) and QCEW concentration (Section 4) are complementary:
- **Industry-weighted LODES** gives industry-specific demographics within the county
- **QCEW concentration** tells you how reliable those industry-specific demographics are (high LQ = reliable, low LQ = noisy/sparse)
- Together, they let you estimate: "What are manufacturing-worker demographics in this county?" (Section 3) and "How confident should we be in that estimate?" (Section 4)

---

## 5. Geographic Resolution Improvements

### 5.1 Multi-tract ensembles (replacing single-tract selection)

**Current M2 family problem:** M2c uses a ZIP-to-tract crosswalk to find ONE tract per company. But ZIP codes often span multiple tracts. The single-tract selection is noisy.

**Fix:** Use ALL tracts in the ZIP code, weighted by employment:

```python
def get_multi_tract_demographics(zipcode):
    """
    Get demographics averaged across all tracts in this ZIP,
    weighted by tract employment from LODES.
    """
    tracts = query("""
        SELECT z.tract_fips, t.total_jobs,
               t.race_white_pct, t.race_black_pct, ...
        FROM zip_tract_crosswalk z
        JOIN cur_lodes_tract_metrics t ON t.tract_fips = z.tract_fips
        WHERE z.zipcode = %s AND t.total_jobs > 0
    """, zipcode)

    total_jobs = sum(t.total_jobs for t in tracts)
    weighted = {}
    for cat in RACE_CATEGORIES:
        weighted[cat] = sum(
            t[cat] * t.total_jobs / total_jobs
            for t in tracts
        )
    return weighted
```

**Expected impact:** 0.1-0.2pp for M2 family methods. Reduces noise from single-tract selection.

### 5.2 Metro-level ACS (already in the database)

`cur_acs_workforce_demographics` has a `metro_cbsa` column but the data loaders only query by `(naics4, state_fips)`. Before PUMS was added, metro-level ACS was already possible:

```python
def get_acs_race_metro(naics_code, cbsa_code):
    """Get ACS race demographics at metro x industry level."""
    return query("""
        SELECT race, SUM(weighted_count) as count
        FROM cur_acs_workforce_demographics
        WHERE naics_code LIKE %s AND metro_cbsa = %s
          AND hispanic = '0'
        GROUP BY race
    """, naics_code[:2] + '%', cbsa_code)
```

This is complementary to PUMS: ACS has industry detail at NAICS 4-digit, while PUMS is limited to 2-digit. ACS-metro would cover different companies than PUMS-metro (specifically: uncommon industries in common metros where PUMS has < 30 respondents).

**Expected impact:** 0.1-0.2pp by filling PUMS coverage gaps (currently 26.5% of companies fall back to state ACS).

### 5.3 Adjacent-county pooling for rural areas

Rural companies (122 in training set, MAE ~1.8 at best) sometimes have very sparse LODES data. Pooling adjacent counties would increase sample size:

```python
def get_pooled_lodes_race(county_fips, radius=1):
    """Pool LODES data from adjacent counties."""
    return query("""
        SELECT SUM(jobs_white) as jobs_white, SUM(jobs_black) as jobs_black, ...
        FROM cur_lodes_geo_metrics g
        JOIN county_adjacency a ON g.county_fips = a.neighbor_fips
        WHERE a.county_fips = %s
    """, county_fips)
```

This needs a county adjacency table (available from Census Bureau). Low priority since rural MAE is already lowest.

---

## 6. Dimension-Specific Models

### 6.1 Gender: The occupation approach that was abandoned too early

**The history:**
- V2: M4 (occupation-weighted) tested for ALL dimensions. Race MAE: 5.92 (bad). Gender MAE: 11.71 (actually competitive).
- V2: M3 IPF wins gender outright (10.93 MAE, 101 of 200 wins). Nobody asked why.
- V3-V5: M4 family declared "consistently underperforming" and ignored. But that conclusion was based on RACE MAE. Gender was never analyzed separately.

**Why occupation works for gender but not race:**

Occupation-to-gender correlations are **strong and geographically stable**:
| Occupation | Female % (National) | Std Dev across states |
|-----------|-------------------|---------------------|
| Registered Nurses (29-1141) | 87% | ~3pp |
| Construction Laborers (47-2061) | 3% | ~2pp |
| Software Developers (15-1256) | 22% | ~4pp |
| Elementary Teachers (25-2021) | 79% | ~3pp |

Occupation-to-race correlations are **weak and geographically variable**:
| Occupation | Black % (National) | Std Dev across states |
|-----------|-------------------|---------------------|
| Registered Nurses (29-1141) | 12% | ~12pp |
| Construction Laborers (47-2061) | 8% | ~10pp |
| Software Developers (15-1256) | 5% | ~6pp |

Gender ratios within occupations are consistent everywhere. Race ratios within occupations vary hugely by geography. That's why M4 fails for race (occupation doesn't predict local racial composition) but should succeed for gender (occupation DOES predict gender composition everywhere).

**Proposed gender model:**

```python
def estimate_gender_by_occupation(naics_code, state_fips):
    """
    Estimate gender composition from BLS occupation mix + ACS occupation-sex data.

    Step 1: Get occupation mix for this industry (BLS matrix)
    Step 2: For each occupation, get gender split (ACS PUMS or table S2401)
    Step 3: Weighted average: sum(occ_share_i * female_pct_i)
    """
    occ_mix = get_bls_occupation_mix(naics_code)  # already in database
    gender_est = {'Male': 0, 'Female': 0}

    for soc_code, share in occ_mix.items():
        occ_gender = get_acs_occupation_gender(soc_code, state_fips)
        gender_est['Female'] += share * occ_gender['Female']
        gender_est['Male'] += share * occ_gender['Male']

    return gender_est
```

**Data needed:** ACS occupation x sex tabulation. Either:
- Census table S2401 (nationally) or B24010 (by state) -- downloadable via Census API
- PUMS microdata already loaded, just needs sex x occupation aggregation

**Expected impact:** 5-10pp gender MAE reduction (from ~18pp to ~8-13pp). This is the single largest accuracy improvement available in the entire pipeline.

### 6.2 Hispanic: Geography-dominant model

Hispanic MAE (~7.5-9.3pp) is moderate for a binary category. The V2 report shows blend methods slightly outperform IPF for Hispanic. This makes sense: Hispanic concentration is highly geographic (Southwest, Florida, NYC metro) and less occupation/industry-dependent.

**Proposed Hispanic model:**

Use a geography-heavy blend with multiple geographic layers:
```
est_hispanic = w1 * LODES_county_hispanic
             + w2 * PUMS_metro_hispanic
             + w3 * tract_hispanic
             + w4 * ACS_state_industry_hispanic
```

With weights heavily favoring geography (w1+w2+w3 >> w4). The current methods use the same formula for Hispanic as for race, which underweights the geographic signal.

**Expected impact:** 0.5-1.5pp Hispanic MAE improvement. Low effort since all data sources already exist.

### 6.3 Education and age (new dimensions)

The database has education and age data in both ACS and LODES, but the demographics pipeline estimates neither.

| Dimension | ACS data | LODES data | Estimation difficulty |
|-----------|----------|-----------|---------------------|
| Education (15 levels) | Yes, by industry x state | Yes, 4 brackets by county | Medium (strong industry signal) |
| Age (6 buckets) | Yes, by industry x state | No | Higher (weaker geographic signal) |

These aren't needed for the EEO-1 validation (EEO-1 doesn't report education/age), but they're valuable for the workforce profile API. They can be estimated with the same blend/IPF framework without ground truth validation -- just shipped as "directional estimates" with appropriate caveats.

---

## 7. Gate and Routing Improvements

These are lower priority than Sections 3-6 because routing can only select among existing methods. Better methods >> better routing. But once the base methods are improved, these fixes become important.

### 7.1 Critical: Fix ground truth leak in gate features

Gate v1 uses `minority_share` (Low/Medium/High) derived from EEO-1 ground truth. At inference time for a new company, this is unavailable. The reported 59.8% CV accuracy and all holdout metrics are optimistic.

**Fix:** Replace with `lodes_minority_share` derived from LODES county data:
```python
lodes_dist = get_lodes_race(county_fips)
lodes_white_pct = lodes_dist.get('White', 50.0)
lodes_minority_share = classify_minority(lodes_white_pct)
```

### 7.2 Soft routing instead of hard argmax

Gate v1 picks one expert and discards the others. With only 59.8% routing accuracy, 40% of companies use the wrong expert.

**Fix:** Weighted blend using gate probabilities:
```python
# Current
expert = argmax(gate_probs)
pred = experts[expert].predict(company)

# Fixed
preds = [expert.predict(company) for expert in experts]
pred = {cat: sum(gate_probs[i] * preds[i][cat] for i in range(3))
        for cat in RACE_CATEGORIES}
```

### 7.3 Upgrade gate to gradient-boosted trees

Logistic regression can't capture nonlinear feature interactions. LightGBM/XGBoost with 50-100 trees would capture "Healthcare x South x Urban -> Expert B" patterns.

**Additional features to add:**
- `acs_lodes_divergence`: L1 distance between ACS and LODES distributions (high = experts disagree)
- `industry_lq`: QCEW location quotient (high = LODES more trustworthy)
- `pums_available`: Binary flag
- `tract_diversity`: Shannon entropy of tract demographics
- `naics_4digit`: Finer industry code (target-encoded for tree models)
- `lodes_minority_share`: Replaces the leaked `minority_share`

### 7.4 Per-segment calibration

Replace global per-expert calibration (6 bias values per expert) with segment-level calibration. Expert D's Asian bias (-3.10pp) is concentrated in West Coast tech; applying it uniformly hurts Midwest companies.

**Hierarchy:** `naics_group x region` (n >= 30) -> `naics_group` (n >= 15) -> global

### 7.5 Tiered review flags

Replace 94.7% flat flag rate with actionable tiers:

| Tier | Criteria | Expected rate | Action |
|------|----------|--------------|--------|
| **Red** | Gate confidence < 0.35 AND expert disagreement > 15pp | ~10-15% | Manual review required |
| **Yellow** | Confidence < 0.45 OR no PUMS OR hard segment | ~40-50% | Use with caution |
| **Green** | None of the above | ~35-50% | Automated use OK |

---

## 8. Training Data Expansion

~5,000 EEO-1 filings exist, 997 are used for training, 208 for holdout. ~3,800 are unused. Even with quality filtering, 2,500+ training companies should be achievable.

**Steps:**
1. Audit EEO-1 file for duplicates (same company, multiple years) -- keep most recent
2. Quality filters: non-zero headcount, valid state, parseable NAICS
3. Geographic matching: ZIP -> county -> CBSA -> state
4. Stratified split: 3,000+ training / 500 holdout
5. Retrain all methods + gate on expanded set

**Impact:** 0.3-0.5pp race MAE from more training data. Also enables per-segment calibration (currently too few companies per segment).

---

## 9. Complete Inventory: What's in the Database vs What's Used

### 9.1 cur_acs_workforce_demographics

| Column/Field | In Database | Used | Notes |
|-------------|------------|------|-------|
| race (9 codes) | Yes | **Yes** | Primary race input for ACS |
| hispanic | Yes | **Yes** | Primary Hispanic input |
| sex | Yes | **Yes** | Primary gender input |
| education (15 levels) | Yes | **No** | Could estimate education distribution |
| age_bucket (6 groups) | Yes | **No** | Could estimate age distribution |
| pct_any_insurance | Yes | **No** | Health insurance coverage rate |
| pct_private_insurance | Yes | **No** | Private vs public insurance split |
| pct_medicaid | Yes | **No** | Medicaid coverage rate |
| pct_medicare | Yes | **No** | Medicare coverage rate |
| pct_public_insurance | Yes | **No** | Public insurance coverage rate |
| pct_subsidized | Yes | **No** | Subsidized insurance rate |
| worker_class | Yes | **No** | Private/govt/self-employed classification |
| metro_cbsa | Yes | **No** | Metro-level aggregation possible but not queried |
| naics_code (4-digit) | Yes | Partially | Falls back to 2-digit too quickly |
| state_fips | Yes | **Yes** | Primary geographic key |

**11 available fields, 3 used.** The insurance and education data could be useful as features (companies in industries with high Medicaid rates have different demographics than those with high private insurance rates).

### 9.2 cur_lodes_geo_metrics (county level)

| Column/Field | In Database | Used | Notes |
|-------------|------------|------|-------|
| total_jobs | Yes | **Yes** | Denominator |
| jobs_white, jobs_black, jobs_asian, jobs_aian, jobs_nhopi, jobs_two_plus | Yes | **Yes** | Race demographics |
| jobs_hispanic, jobs_not_hispanic | Yes | **Yes** | Hispanic demographics |
| jobs_male, jobs_female | Yes | **Yes** | Gender demographics |
| jobs_edu_less_than_hs | Yes | **No** | Education bracket 1 |
| jobs_edu_hs | Yes | **No** | Education bracket 2 |
| jobs_edu_some_college | Yes | **No** | Education bracket 3 |
| jobs_edu_bachelors_plus | Yes | **No** | Education bracket 4 |
| pct_bachelors_plus | Yes | **No** | Derived education metric |
| pct_minority | Yes | **No** | Could replace leaked minority_share feature |
| CNS01-CNS20 (industry employment) | In raw data | **No** | Industry-specific employment counts |

**The CNS01-CNS20 fields are the single biggest missed opportunity.** They allow industry-specific LODES demographics. Need to verify if they're in `cur_lodes_geo_metrics` or only in the raw WAC files (may need ETL update).

### 9.3 cur_lodes_tract_metrics (tract level)

| Column/Field | In Database | Used | Notes |
|-------------|------------|------|-------|
| race demographics | Yes | Partially | Used by M2c/M2d family only |
| hispanic | Yes | Partially | Same |
| gender | Yes | Partially | Same |
| education brackets | Likely | **No** | If loaded from WAC, same CD01-CD04 as county |
| industry employment (CNS) | Likely | **No** | Would enable tract x industry demographics |

### 9.4 qcew_annual (1.9M rows)

| Column/Field | In Database | Used | Notes |
|-------------|------------|------|-------|
| area_fips (county) | Yes | **No** | Geographic key |
| industry_code (NAICS) | Yes | **No** | Industry key |
| annual_avg_emplvl | Yes | **No** | Employment count |
| annual_avg_estabs | Yes | **No** | Establishment count (multi-site indicator) |
| avg_annual_pay | Yes | **No** | Wage level (correlates with demographics) |
| location_quotient | Yes | **No** | Industry concentration signal |

**Completely unused by demographics pipeline.** QCEW is the natural bridge between LODES (geographic) and ACS (industry) because it tells you HOW MUCH of each industry exists in each county.

### 9.5 oes_occupation_wages (414K rows)

| Column/Field | In Database | Used | Notes |
|-------------|------------|------|-------|
| occ_code (SOC) | Yes | **No** | Occupation |
| area_code | Yes | **No** | Metro/state/national |
| naics_code | Yes | **No** | Industry |
| tot_emp | Yes | **No** | Employment |
| h_mean, a_mean | Yes | **No** | Hourly/annual mean wages |

Could provide occupation x metro employment counts for the gender model (Section 6.1), giving local occupation mixes instead of relying on the national BLS matrix.

### 9.6 bls_industry_occupation_matrix

| Column/Field | In Database | Used | Notes |
|-------------|------------|------|-------|
| naics_code | Yes | By M4 family | Industry |
| soc_code | Yes | By M4 family | Occupation |
| employment_2024 | Yes | By M4 family | Employment share |

Used by M4 family, but M4 was evaluated only for race (where it fails) and never independently for gender (where it should excel).

---

## 10. Proposed Method Variants for V6

Based on the data gaps identified above, here are concrete new methods to evaluate:

### 10.1 New base methods (Priority 1)

| Method | Formula | New data used | Expected MAE |
|--------|---------|--------------|-------------|
| **M9a Industry-LODES IPF** | `ACS_industry_state ^ alpha * LODES_industry_county ^ (1-alpha)` | LODES CNS industry codes | ~3.8-4.0 |
| **M9b QCEW-Weighted Blend** | `w(LQ) * ACS + (1-w(LQ)) * LODES` where w adapts to industry concentration | QCEW location quotient | ~4.2-4.4 |
| **M9c Industry-LODES + QCEW** | M9a with alpha adapted by QCEW concentration | Both | ~3.6-3.9 |
| **M9d Full-Stack** | `ACS_metro_industry ^ a * LODES_industry_county ^ b * Tract_ensemble ^ c` | Industry LODES + multi-tract + metro ACS | ~3.5-3.8 |

### 10.2 Dimension-specific methods (Priority 2)

| Method | Dimension | Formula | New data used | Expected MAE |
|--------|-----------|---------|--------------|-------------|
| **G1 Occ-Gender** | Gender | `sum(occ_share_i * female_pct_i)` from BLS matrix + ACS occ-sex | ACS occupation x sex | ~8-12 (vs 18 current) |
| **G2 Occ-Gender-Metro** | Gender | G1 but with OES metro occupation counts instead of national BLS | OES metro data | ~7-11 |
| **H1 Geo-Hispanic** | Hispanic | `0.20*ACS + 0.30*LODES + 0.30*tract + 0.20*PUMS` | Multi-source geographic | ~6-8 (vs 9 current) |

### 10.3 Enhanced existing methods (Priority 3)

| Method | Change from base | New data used |
|--------|-----------------|--------------|
| **M3c-IND** | M3c but with industry-weighted LODES | LODES CNS codes |
| **M1b-QCEW** | M1b but with LQ-adaptive weights | QCEW |
| **M2c-Multi** | M2c but with multi-tract ensemble | Multi-tract weighting |
| **Expert-B-IND** | Expert B but with industry-weighted tract | LODES CNS at tract level |

---

## 11. Implementation Roadmap

### Phase 1: Data Infrastructure (3-5 days)

```
Day 1-2: LODES Industry Data
  [ ] Verify CNS01-CNS20 columns in cur_lodes_geo_metrics
  [ ] If missing: update lodes_curate_demographics.py to include them
  [ ] Build NAICS-to-CNS mapping table
  [ ] Create get_lodes_industry_race(county_fips, naics_2digit) loader
  [ ] Create get_lodes_industry_tract_race(tract_fips, naics_2digit) loader

Day 3: QCEW Integration
  [ ] Create get_qcew_concentration(county_fips, naics_2digit) loader
  [ ] Returns: location_quotient, industry_share, establishment_count
  [ ] Index qcew_annual on (area_fips, industry_code, year)

Day 4: Multi-tract and Metro ACS
  [ ] Create get_multi_tract_demographics(zipcode) loader
  [ ] Create get_acs_race_metro(naics_code, cbsa_code) loader
  [ ] Verify coverage rates on 997 training companies

Day 5: Gender Data
  [ ] Download ACS occupation x sex tabulation (S2401 or PUMS aggregate)
  [ ] Create get_occupation_gender(soc_code, state_fips) loader
  [ ] Create estimate_gender_by_occupation(naics_code, state_fips)
```

### Phase 2: New Base Methods (1 week)

```
Week 1:
  [ ] Implement M9a-M9d (industry-LODES methods)
  [ ] Implement G1-G2 (occupation-gender methods)
  [ ] Implement H1 (geography-heavy Hispanic)
  [ ] Implement M3c-IND, M1b-QCEW, M2c-Multi, Expert-B-IND
  [ ] Run all new + existing methods on 997 training companies
  [ ] Generate comparison report: V6_BASE_METHODS.md
```

### Phase 3: Evaluation and Gate Rebuild (1 week)

```
Week 2:
  [ ] Expand training set (P5 from revision plan)
  [ ] Fix ground truth leak in gate features
  [ ] If new base methods beat old ones: rebuild expert roster
  [ ] Train new gate (GBT, soft routing, enriched features)
  [ ] Per-segment calibration
  [ ] Evaluate on fresh holdout
  [ ] Generate final report: V6_FINAL_RESULTS.md
```

### Phase 4: Production Integration (3 days)

```
  [ ] Update demographics_v5.py -> demographics_v6.py
  [ ] Tiered review flags
  [ ] Gender-specific endpoint using occupation model
  [ ] Education/age estimation endpoints (if quality is acceptable)
  [ ] Update API response schema
```

---

## 12. Evaluation Framework

### 12.1 V6 Acceptance Criteria

| Criterion | V5 Gate v1 (current) | V6 target | Stretch |
|-----------|---------------------|-----------|---------|
| Race MAE (holdout) | 5.18 | < 4.50 | < 4.00 |
| P>20pp (holdout) | 20.67% | < 16% | < 12% |
| P>30pp (holdout) | 8.17% | < 6% | < 4% |
| Abs Bias (holdout) | 1.35 | < 1.10 | < 0.80 |
| Hispanic MAE | 9.25 | < 8.00 | < 7.00 |
| Gender MAE | 18.10 | < 12.00 | < 9.00 |
| No GT leakage | FAIL | PASS | PASS |
| Red flag rate | 94.7% (all flagged) | < 15% | < 10% |

### 12.2 Ablation Study

To isolate the value of each new data source:

| Experiment | What changes | Measures |
|-----------|-------------|---------|
| A. Industry-LODES only | Replace LODES with industry-weighted LODES in M3c | Value of industry-specific geography |
| B. QCEW weighting only | Add LQ-adaptive weights to M1b | Value of concentration signal |
| C. A + B combined | Industry-LODES + QCEW | Complementarity |
| D. Multi-tract only | Multi-tract ensemble in M2c | Value of geographic averaging |
| E. Metro ACS only | Metro ACS fallback before state ACS | Value of metro resolution |
| F. Gender model | Occupation-based gender (G1) | Gender-specific improvement |
| G. Full stack | All of A-F + expanded data + new gate | Cumulative improvement |

### 12.3 Per-Segment Reporting

All holdout results must be broken down by:
- Industry group (18 groups)
- Minority share (Low/Medium/High)
- Urbanicity (Rural/Suburban/Urban)
- Region (4 Census regions)
- Company size (4 buckets)

This identifies which segments benefit from which data sources, informing future routing decisions.

---

## 13. Summary: Where the Gains Are

```
Current pipeline:
  ACS (state x industry) ----\
                               >-- Blend/IPF/Dampen --> Route --> Calibrate --> Estimate
  LODES (county, all-industry) /

Proposed pipeline:
  ACS (metro x industry) --------\
  LODES (county x industry) ------\
  LODES (multi-tract x industry) --+-- Blend/IPF/Dampen --> Route --> Calibrate --> Estimate
  QCEW (concentration weights) ---/    (per dimension)
  BLS/ACS (occupation x gender) -------> Gender-specific model --> Gender estimate
  Multi-source geography -----------> Hispanic-specific model --> Hispanic estimate
```

The current pipeline feeds two distributions into 30 ways of combining them. The proposed pipeline feeds richer, more relevant distributions into the same combination methods. The methods don't need to get fancier -- they need better food.

**Priority order:**
1. Industry-specific LODES (Section 3) -- biggest single gain for race
2. Occupation-based gender model (Section 6.1) -- biggest single gain for gender
3. QCEW concentration weighting (Section 4) -- complements #1
4. Expanded training set + gate fixes (Sections 7-8) -- enables better routing
5. Multi-tract ensembles + metro ACS (Section 5) -- incremental geographic gains
6. Hispanic-specific geography model (Section 6.2) -- targeted Hispanic improvement
