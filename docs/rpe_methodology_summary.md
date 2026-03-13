# RPE Workforce Size Estimation: Tool & Methodology Summary

## What It Does

The RPE (Revenue Per Employee) system estimates workforce size for employers that lack direct headcount data. Given an employer's **revenue** (from IRS Form 990) and **industry** (NAICS code), it divides revenue by the Census Bureau's average revenue-per-employee for that industry to produce an employee count estimate.

```
estimated_employees = employer_revenue / industry_rpe_ratio
```

This fills a critical gap: roughly 10-20% of scored employers have 990 revenue but no other source of employee count.

---

## Data Sources

| Source | Geo Level | Granularity | Rows | Origin |
|--------|-----------|-------------|------|--------|
| EC2200BASIC.zip | National | 2-6 digit NAICS | 2,055 | 2022 Economic Census |
| us_state_6digitnaics_2022.xlsx | State | 6-digit NAICS | 84,354 | SUSB (Statistics of U.S. Businesses) |
| county_3digitnaics_2022.xlsx | County | 3-digit NAICS | 175,444 | SUSB |

**Total:** 261,853 RPE ratios in `census_rpe_ratios`.

All three sources derive from the Census Bureau's establishment-level data. RPE is computed as:
```
rpe = (receipts_in_thousands * 1000) / employee_count
```

---

## Geographic Cascade

When estimating, the system prefers the most geographically specific RPE available:

**For non-union targets** (master_employers with ZIP):
```
county RPE  -->  state RPE  -->  national RPE
  (best)          (fallback)       (last resort)
```

**For union reference employers** (f7_employers, no structured ZIP):
```
state RPE  -->  national RPE
```

Within each geographic level, the system also cascades on NAICS specificity -- trying the full 6-digit code first, then 5, 4, 3, 2-digit prefixes until a match is found.

---

## Size Source Precedence

RPE is the last-resort size estimate. Direct data always wins:

**Union reference (mv_unified_scorecard):**
1. `company_size` (from Mergent/D&B)
2. `f7_unit_size` (from F7 bargaining unit data)
3. `ppp_2020` (PPP loan job count)
4. `rpe_estimate` (this system)

**Non-union targets (mv_target_scorecard):**
1. `employee_count` (direct from any source)
2. `rpe_estimate` (this system)

The `size_source` / `employee_count_source` column tracks which method produced each employer's size.

---

## Validation Methodology

### Dual Ground Truth Approach

To avoid relying on a single (potentially noisy) benchmark, we validate against two independent ground truths and check whether they agree.

### Ground Truth A: NLRB Whole-Company Elections

**Concept:** For small single-location employers where a union election covered essentially the entire non-supervisory workforce, the NLRB's legally mandated `eligible_voters` count is a high-quality headcount.

**Pipeline:**
```
NLRB election (eligible_voters)
  -> matched employer (f7_employers_deduped)
    -> matched 990 filer (total_revenue)
```

**Employee estimation:**
```
actual_employees = eligible_voters * supervisor_multiplier
```

The supervisor multiplier comes from the BLS Industry-Occupation Matrix:
- Management occupations (SOC 11-xxxx)
- First-line supervisors (by title)
- `multiplier = 1 / (1 - supervisor_pct)`, default 1.15

**Filters (whole-company proxy):**
- Known employee count < 200 (small, likely single-location)
- `eligible_voters / known_emp >= 0.5` (unit covers majority of workforce)
- Valid 990 revenue, NAICS, state

**Sample:** ~625 cases after filtering (from 2,002 raw linked elections).

### Ground Truth B: 990 Self-Reported Employees

**Concept:** 990 nonprofit filers report both `total_revenue` and `total_employees` directly. Straightforward comparison.

**Pipeline:**
```
990 filer (total_revenue, total_employees)
  -> matched F7 employer (state, NAICS, ZIP)
  DISTINCT ON ein, best match_confidence
```

**Sample:** ~8,759 cases.

### Accuracy Metrics

| Metric | Definition |
|--------|-----------|
| Median Error | Median of `\|estimated - actual\| / actual` |
| Within 25% | Share where `0.75 <= est/actual <= 1.33` |
| Within 50% | Share where `0.5 <= est/actual <= 2.0` |
| Within 3x | Share where `0.33 <= est/actual <= 3.0` |

Results are broken down by:
- **Geographic level** (national vs. state vs. county)
- **Employer size** (<25, 25-100, 100-500, 500+)
- **Sector** (2-digit NAICS, top 10)
- **NAICS match depth** (how many digits matched)

---

## Results (2026-03-03)

### Headline Numbers

**Ground Truth A (NLRB, n=530):**

| Level | Median Error | Within 25% | Within 50% | Within 3x |
|-------|-------------|-----------|-----------|----------|
| National | 95.2% | 7.4% | 18.1% | 26.8% |
| State | 95.8% | 7.7% | 15.8% | 24.7% |
| County | 95.8% | 8.4% | 16.4% | 26.1% |

**Ground Truth B (990, n=7,793):**

| Level | Median Error | Within 25% | Within 50% | Within 3x |
|-------|-------------|-----------|-----------|----------|
| National | 58.8% | 22.8% | 49.1% | 67.2% |
| State | 59.1% | 21.1% | 48.0% | 66.4% |
| County | 59.7% | 22.0% | 47.2% | 65.4% |

### Cross-Validation Summary

| Metric | GT-A (NLRB) | GT-B (990) |
|--------|-------------|-----------|
| State W50% vs National | -2.3pp | -1.0pp |
| County W50% vs National | -1.7pp | -1.8pp |
| State Med.Err vs National | +0.6pp | +0.2pp |
| County Med.Err vs National | +0.7pp | +0.8pp |

**Both ground truths agree:** geographic RPE does **not** improve over national. State and county are directionally *worse* by 1-2 percentage points.

### Sector Highlights (GT-B, national level)

| Sector | n | Median Error | Within 50% |
|--------|---|-------------|-----------|
| Healthcare (62) | 2,015 | 50.0% | 57.2% |
| Education (61) | 976 | 51.3% | 59.4% |
| Utilities (22) | 497 | 46.6% | 57.3% |
| Food service (72) | 357 | 63.5% | 50.1% |
| Construction (23) | 1,199 | 63.6% | 41.1% |
| Arts/recreation (71) | 1,177 | 67.7% | 40.6% |
| Information (51) | 133 | 75.9% | 24.8% |

RPE works best for labor-intensive sectors with uniform revenue/employee ratios (healthcare, education, utilities). It works poorly for capital-intensive or project-based sectors (construction, information).

### Size Effects (GT-B, national level)

| Size | n | Median Error | Within 50% |
|------|---|-------------|-----------|
| 500+ | 991 | 36.5% | 70.3% |
| 100-500 | 1,527 | 56.5% | 47.2% |
| 25-100 | 1,691 | 61.3% | 45.1% |
| <25 | 3,584 | 64.6% | 45.8% |

Larger employers are estimated more accurately -- regression to the mean helps.

---

## Interpretation & Limitations

### What RPE Is Good For
- **Order-of-magnitude sizing** for employers with no other size data
- **Tier assignment** (small/medium/large) rather than precise headcount
- **Screening filter** to identify employers likely above a size threshold

### What RPE Is Not Good For
- Precise headcount prediction (median error ~59% even at best)
- Cross-sector comparison (healthcare RPE != construction RPE)
- Single-location precision (county data adds noise, not signal)

### Known Issues
1. **Geographic RPE hurts more than it helps** -- county data has extreme noise in small counties (holding companies can produce RPE < $1/employee)
2. **Construction** is fundamentally broken for RPE (project-based revenue decoupled from headcount)
3. **NLRB ground truth (GT-A) shows much worse accuracy** than 990 (GT-B) -- these are small nonprofits where bargaining unit size and 990 reported employees may both be noisy
4. **Census NAICS ranges** at 2-digit level use combined codes (31-33, 44-45, 48-49) -- no standalone "31" exists

### Recommended Next Steps
1. Use national RPE only (drop geographic cascade from scoring CTEs)
2. Add sector-specific bias corrections for worst sectors
3. Filter out holding companies / pass-through entities before applying RPE
4. Explore NLRB eligible_voters + BLS supervisor ratios as an independent size estimate (separate from RPE validation)
5. Load Mergent Sales column for private-sector validation with larger sample

---

## File Reference

| File | Purpose |
|------|---------|
| `scripts/etl/load_census_rpe.py` | Load Census/SUSB data into `census_rpe_ratios` |
| `scripts/analysis/validate_rpe_estimates.py` | Dual validation (NLRB + 990 ground truths) |
| `scripts/scoring/build_unified_scorecard.py` | RPE CTE for union reference scorecard |
| `scripts/scoring/build_target_scorecard.py` | RPE CTE for non-union target scorecard |
| `tests/test_rpe_estimates.py` | 23 tests covering data quality, geo levels, coverage, integration |
| `census_rpe_ratios` (table) | 261,853 rows: national + state + county RPE ratios |
| `zip_county_crosswalk` (table) | 39,366 ZIP-to-county mappings for county cascade |
| `bls_industry_occupation_matrix` (table) | BLS occupation data for supervisor multipliers |

---

## Gemini Suggestions (2026-03-03)

### 1. Operationalize "National-Only" Preference
Validation results show that State and County levels add ~1-2pp of median error and significant outlier noise.
*   **Action:** Deprecate the geographic cascade in `build_target_scorecard.py` and `build_unified_scorecard.py`.
*   **Goal:** Use National RPE as the primary estimator to reduce variance from small-sample geographic cells.

### 2. Implement Reliability Tiers
Users of the scorecard should know which RPE estimates are "best guesses" vs. "shots in the dark."
*   **Tier 1 (High):** Healthcare (62), Education (61), Utilities (22).
*   **Tier 2 (Med):** Manufacturing (31-33), Food Service (72).
*   **Tier 3 (Low):** Construction (23), Information (51).
*   **Action:** Add a `rpe_confidence_tier` column to the scorecard.

### 3. Apply RPE Sanity Filters
Extreme RPE ratios (e.g., <$30k or >$2M per employee) usually indicate data entry errors or holding companies.
*   **Action:** Implement a "clipping" or "fallback" rule in the ETL process: if a specific 6-digit NAICS ratio is an outlier, revert to the 3-digit or 2-digit sector average.

### 4. Refine the Supervisor Multiplier
The 1.15 default multiplier for NLRB ground truth (GT-A) may be too coarse for the 95% error rate seen.
*   **Action:** Perform a sensitivity analysis on the supervisor multiplier. Consider industry-specific ratios from the `bls_industry_occupation_matrix` instead of a global flat rate.

### 5. Filter Non-Operating Entities
RPE assumes an active business model. Holding companies and "pass-through" entities break the math.
*   **Action:** Use 990 "Business Name" keywords (e.g., "Holding", "Trust", "Foundation") to flag and exclude entities where RPE is likely to fail.


---

## Suggestions (Optional)

The following improvements can strengthen the methodology and make production decisions clearer:

1. **Resolve sample-size inconsistencies**
   - Reconcile `~625` vs `n=530` (GT-A) and `~8,759` vs `n=7,793` (GT-B).
   - Add a filter attrition table showing row counts after each eligibility step.

2. **Add uncertainty intervals**
   - Report bootstrap 95% confidence intervals for median error and Within-50%.
   - Treat small deltas (1-2pp) as inconclusive unless confidence intervals do not overlap.

3. **Define explicit production policy**
   - Document a clear default: national RPE only.
   - Define fallback behavior for missing/low-confidence NAICS.
   - Define exception sectors where alternate logic is preferred.

4. **Benchmark against simple baselines**
   - Compare RPE against naive alternatives (global median RPE, sector median size, PPP-only where available).
   - Quantify the net value of RPE over these baselines.

5. **Add sector calibration**
   - Apply sector-size correction factors or quantile calibration to reduce systematic bias.
   - Prioritize weak sectors (e.g., construction, information, arts/recreation).

6. **Strengthen ground-truth caveats**
   - Expand bias notes for GT-A (`eligible_voters` as proxy for total employees).
   - Document expected bias direction and where GT-A should be interpreted cautiously.

7. **Document outlier controls**
   - Specify winsorization/trim rules for extreme RPE values.
   - Add explicit handling for holding companies and pass-through entities.

8. **Report coverage and operational impact**
   - Include the share of scored employers using RPE by scorecard and sector.
   - Pair accuracy metrics with usage prevalence to show impact.

9. **Add threshold-based evaluation**
   - Report precision/recall for practical cutoffs (`>50`, `>100`, `>500` employees).
   - Align evaluation with organizing/screening use cases.

10. **Convert limitations into enforceable rules**
   - Translate known issues into concrete model-policy flags (for example, low-confidence labels or exclusions).
   - Ensure these rules are reflected in scorecard output fields.

11. **Improve reproducibility metadata**
   - Record dataset snapshot dates, script version/commit hash, and run commands.
   - Make it straightforward to regenerate the exact report.

12. **Add executive summary block**
   - Add a short top section: key findings, decision taken, expected downstream effect.
   - Keep this section non-technical for fast stakeholder review.
