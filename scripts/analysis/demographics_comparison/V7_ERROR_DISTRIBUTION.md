# V7 Error Distribution Analysis

**Holdout:** test (991 companies)
**Date:** 2026-03-10

---

## Distribution Summary

| Max Error Bucket | Companies | % | Cumulative |
|-----------------|-----------|---|------------|
| 0-1 pp | 2 | 0.2% | 0.2% |
| 1-3 pp | 104 | 10.5% | 10.7% |
| 3-5 pp | 149 | 15.0% | 25.7% |
| 5-10 pp | 299 | 30.2% | 55.9% |
| 10-15 pp | 193 | 19.5% | 75.4% |
| 15-20 pp | 83 | 8.4% | 83.8% |
| 20-30 pp | 91 | 9.2% | 92.9% |
| >30 pp | 70 | 7.1% | 100.0% |

"Max error" = the largest absolute error for any single race category for that company.
P>20pp target (<16%) counts the bottom two rows; P>30pp target (<6%) counts the last row.

---

## Bucket Profiles

### 0-1 pp (2 companies, 0.2%) -- Nearly perfect
- Metal/Machinery, Construction
- Too few to draw conclusions

### 1-3 pp (104 companies, 10.5%) -- Excellent
- **Top industries:** Finance/Insurance (29), Professional/Technical (15), Metal/Machinery (11)
- **Expert routing:** E:45, V6:21, B:16 -- Expert E dominates
- **Regions:** Midwest:35, South:32, Northeast:19, West:18
- **Sizes:** 100-999 (71%), small-mid companies
- **Worst category:** Evenly spread (White:34, Black:28, Asian:25)
- **Avg data quality:** 0.90 | **Avg MAE:** 1.0

### 3-5 pp (149 companies, 15.0%) -- Good
- **Top industries:** Finance/Insurance (35), Professional/Technical (29), Wholesale (10)
- **Expert routing:** E:58, D:32, B:20
- **Regions:** Midwest:52, Northeast:35, South:35, West:27
- **Worst category:** White dominates (80/149 = 54%)
- **Avg data quality:** 0.92 | **Avg MAE:** 1.6

### 5-10 pp (299 companies, 30.2%) -- Acceptable
- **Top industries:** Professional/Technical (63), Finance/Insurance (38), Other (36), Healthcare (24)
- **Expert routing:** E:85, D:70, A:50 -- more spread across experts
- **Regions:** South:99, Midwest:90, Northeast:63, West:47
- **Worst category:** White dominates (190/299 = 64%)
- **Avg data quality:** 0.94 | **Avg MAE:** 2.8

### 10-15 pp (193 companies, 19.5%) -- Rough
- **Top industries:** Healthcare/Social (37), Other (31), Professional/Technical (30), Construction (18)
- **Healthcare emerges as #1 problem sector**
- **Expert routing:** More evenly spread (A:42, B:42, E:42, D:29)
- **Regions:** South:74 (38%) -- starting to skew
- **Worst category:** White still dominates (130/193 = 67%)
- **Avg data quality:** 0.94 | **Avg MAE:** 4.4

### 15-20 pp (83 companies, 8.4%) -- Poor
- **Top industries:** Healthcare/Social (19), Other (14), Professional/Technical (9), Admin/Staffing (7)
- **Expert routing:** D:21, B:19, A:18 -- Expert E drops off
- **Regions:** South:34 (41%), West:22 (27%) -- clear geographic skew
- **Worst category:** White (48/83 = 58%), Black (19)
- **Avg data quality:** 0.94 | **Avg MAE:** 6.1

### 20-30 pp (91 companies, 9.2%) -- Bad
- **Top industries:** Healthcare/Social (24), Professional/Technical (15), Other (13)
- **Expert routing:** A:19, B:19, E:19, D:13
- **Regions:** South:47 (52%) -- strongly South-biased
- **Sizes:** 100-999 (65%)
- **Worst category:** White (59/91 = 65%)
- **Error direction:** White over-predicted 19x, under-predicted 40x. Black under-predicted 18x, over-predicted 3x
- **Avg data quality:** 0.96 | **Avg MAE:** 8.4

### >30 pp (70 companies, 7.1%) -- Catastrophic
- **Top industries:** Healthcare/Social (17), Admin/Staffing (10), Professional/Technical (9)
- **Expert routing:** B:19, D:14, A:12, E:12
- **Regions:** South:33 (47%), West:21 (30%) -- 77% from South+West
- **Sizes:** 100-999 (73%)
- **Worst category:** White (35/70 = 50%), Black (24/70 = 34%)
- **Error direction:** White over-predicted 24x, under-predicted 11x. Black over-predicted 3x, under-predicted 21x
- **Avg data quality:** 0.98 | **Avg MAE:** 14.7

---

## Key Patterns

### The distribution is NOT random. Clear systemic patterns:

**1. Industry is the strongest predictor of error bucket:**
- Finance/Insurance: concentrates in 1-5pp (excellent). 64/139 (46%) have <5pp error.
- Metal/Machinery, Wholesale: similarly strong.
- Healthcare/Social: concentrates in 10-30+pp (bad). 41/131 (31%) have >20pp error.
- Admin/Staffing: 10/49 (20%) have >30pp error -- worst catastrophic rate.

**2. Geography matters -- Southern companies are harder:**
- South represents ~35% of the holdout but ~50% of the >20pp bucket.
- Midwest companies are easiest (overrepresented in good buckets).
- This likely reflects more diverse workforces that diverge from county-level census baselines.

**3. The systematic error is: we over-predict White, under-predict Black:**
- In the >30pp bucket: 24 companies have White over-predicted, only 11 under-predicted.
- Black is under-predicted 21x vs over-predicted 3x.
- This means for diverse Southern companies, census data overstates the White share of the workforce.

**4. Data quality does NOT explain errors:**
- The worst bucket (>30pp) has the highest avg data quality (0.98).
- We have good data -- we just systematically estimate wrong for these company types.
- The problem is not missing data; it's that census demographics don't match workforce demographics for certain industries in certain geographies.

**5. No single expert is responsible:**
- Errors are spread across all experts. Expert B has slightly more >30pp cases (19), but also handles many good cases.
- The gate model is routing reasonably -- the experts themselves all struggle with the same company types.

---

## Implications for V8

The ~161 companies above 20pp (16.3%) are concentrated in:
1. **Healthcare + Staffing in the South/West** -- these workforces hire disproportionately from minority communities relative to county populations
2. **Mid-size companies (100-999)** in diverse metros

Potential approaches:
- Industry-geography interaction terms (e.g., "Healthcare in South" gets different White/Black priors)
- Using establishment-level LODES data (workplace vs residence) more aggressively for these sectors
- Sector-specific calibration that adjusts White downward and Black upward for Healthcare/Staffing in high-diversity counties
- Treating the >20pp companies as a separate modeling problem rather than trying to improve the general model
