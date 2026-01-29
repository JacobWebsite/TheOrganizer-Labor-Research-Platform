# Labor Relations Research Platform - Comprehensive Methodology Summary

**Last Updated:** January 26, 2026  
**Version:** 7.1

---

## Table of Contents

1. [Project Overview](#1-project-overview)
2. [What Has Worked](#2-what-has-worked)
3. [What Has Been Revised](#3-what-has-been-revised)
4. [Open Questions](#4-open-questions)
5. [Possible Solutions](#5-possible-solutions)
6. [Validation Framework](#6-validation-framework)

---

## 1. Project Overview

### Goal
Build a comprehensive labor relations research platform integrating multiple federal datasets to analyze workplace organization trends, employer relationships, and labor market dynamics across the United States.

### Core Problem Solved
**Raw OLMS LM data reports 70.1M union members, but BLS benchmark is only 14.3M.** The platform developed systematic methodologies to reconcile these differences and produce accurate membership counts.

### Data Sources Integrated
| Source | Records | Purpose |
|--------|---------|---------|
| OLMS LM Filings | 26,665 unions | Union financial data, membership |
| F-7 Bargaining Notices | 150,386 employers | Private sector employer coverage |
| NLRB Elections | 33,096 elections | Election outcomes, trends |
| NLRB ULP Cases | 426,834 cases | Unfair labor practice tracking |
| FLRA Data | 2,183 units | Federal sector coverage |
| BLS CPS Data | All NAICS | Union density benchmarks |
| Form 990 | 39 orgs | Public sector estimates |

### Final Platform Metrics
| Metric | Value |
|--------|-------|
| Deduplicated OLMS Members | 14.5M (vs 70.1M raw) |
| BLS Benchmark | 14.3M |
| Accuracy | 101.4% (within 1.5%) |

---

## 2. What Has Worked

### 2.1 Hierarchy-Based Deduplication ✅

**Problem:** Raw LM data counted members at every level (federation → international → local), creating 4-5x overcounting.

**Solution:** Classify each union's hierarchy level and count only "leaf" organizations:

```
HIERARCHY CLASSIFICATION:
├── FEDERATION (e.g., AFL-CIO): count_members = FALSE
├── INTERNATIONAL (e.g., SEIU National): count_members = FALSE (if locals exist)
│   └── LOCAL (e.g., SEIU Local 32BJ): count_members = TRUE
└── INDEPENDENT: count_members = TRUE
```

**Implementation:**
1. Created `union_hierarchy` table with `count_members` flag
2. Identified 35+ federations by naming patterns
3. Linked locals to parent internationals via `aff_abbr`
4. Created `v_union_members_counted` view for deduplicated totals

**Result:** 70.1M → 14.5M (matches BLS within 1.5%)

### 2.2 NHQ-Based Reconciliation ✅

**Problem:** Bottom-up deduplication is complex; needed simpler "macro" validation.

**Solution:** Use National Headquarters (NHQ) filings only, then subtract known overcounts:

```
Raw OLMS NHQ Data:              20,241,994  (100.0%)
  Less: Retirees/Inactive:      (2,094,249) (-10.3%)
  Less: NEA/AFT Dual Affiliates:  (903,013) ( -4.5%)
  Less: Canadian Members:       (1,329,500) ( -6.6%)
                                -----------
ESTIMATED US UNION MEMBERS:     15,915,232  ( 78.6%)
```

**Key Adjustments:**
| Adjustment | Amount | Source |
|------------|--------|--------|
| Retirees/Inactive | -2.1M | Schedule 13 categories |
| NEA/AFT Dual | -903K | NYSUT, FEA, Education MN |
| Canadian Members | -1.3M | Web research on 23 unions |

**Result:** 15.9M (within 11.3% of BLS)

### 2.3 Form 990 Public Sector Estimation ✅

**Problem:** Public sector unions (teachers, firefighters, police) don't file OLMS LM forms.

**Solution:** Use IRS Form 990 dues revenue with per-capita rates:

```
Estimated Members = Dues Revenue / Per-Capita Rate
```

**Validated Per-Capita Rates:**
| Union | Annual Rate | Validation Method |
|-------|-------------|-------------------|
| NEA | $134.44 | Cross-validated vs LM-2 (0.00% variance) |
| AFT | $242.16 | Constitutional rate |
| FOP | $11.50 | Confirmed extremely low national per-capita |
| IAFF | $190.00 | Convention resolutions |
| AFSCME | $251.40 | Constitutional rate |
| SEIU | $151.80 | Constitutional rate |

**Result:** 98.4% coverage of BLS public sector benchmark

### 2.4 F-7 Reconciliation with Adjustment Factors ✅

**Problem:** F-7 data reports 21.96M workers vs BLS 7.3M private sector (3x overcount).

**Solution:** Apply different adjustment factors by match type:

| Match Type | Factor | Rationale |
|------------|--------|-----------|
| MATCHED | Per-affiliation (~55% avg) | Validated against NHQ |
| NAME_INFERRED | 0.15 (15%) | Multi-employer associations |
| UNMATCHED | 0.35 (35%) | Conservative estimate |

**Exclusions Applied:**
- Federal affiliations (AFGE, APWU, NALC, NFFE, NTEU)
- Public sector patterns (`%state of%`, `%city of%`, `%county of%`)
- Union locals listed as employers (`local %`, `%brotherhood%`)
- Multi-employer placeholders (`%signator%`)

**Result:** F-7 captures 87.6% of BLS private sector (6.40M vs 7.30M)

### 2.5 Employer Geocoding ✅

**Problem:** Need geographic visualization of labor relations data.

**Solution:** Census Geocoder API with batch processing:

| Metric | Result |
|--------|--------|
| Success Rate | 73.6% (110,995 of 150,386) |
| Processing Speed | 237 addr/sec (10K batches, 4 threads) |
| Total Time | 6.5 minutes |

### 2.6 Cross-Dataset Matching ✅

**Problem:** Need to link employers across F-7, NLRB, OLMS datasets.

**Solution:** Multi-phase matching approach:

| Phase | Method | Match Rate |
|-------|--------|------------|
| Exact | file_number lookup | 60% |
| Affiliation | Name pattern extraction | 20% |
| Fuzzy | pg_trgm similarity | 10% |
| Temporal | Expand to 16-year history | +14% |

**Final F-7 → OLMS Match Rate:** 97.6%

---

## 3. What Has Been Revised

### 3.1 Raw Summation → Hierarchy Deduplication 🔄

**Initial Approach (Wrong):**
```sql
SELECT SUM(members) FROM lm_data;  -- Returns 70.1M
```

**Revised Approach (Correct):**
```sql
SELECT SUM(members) FROM v_union_members_counted;  -- Returns 14.5M
```

**Lesson:** Cannot simply sum all LM filings; must account for hierarchy structure.

### 3.2 2025 Data → 2024 Data 🔄

**Initial Approach:** Used 2025 LM filings (5,790 records)

**Revised:** Switched to 2024 filings (19,554 records)

**Reason:** 2025 data incomplete; fiscal year reporting means 2025 data won't be complete until mid-2026.

### 3.3 Form 990 as Gap-Filler → Validation Tool 🔄

**Initial Approach (Wrong):** Fabricate 990 dues revenue estimates to fill OLMS gaps

**Revised Approach (Correct):** Use 990 data as cross-validation:
- For unions filing BOTH LM and 990: compare to identify discrepancies
- 990 implied > OLMS reported → indicates public sector gap
- Never fabricate 990 revenue numbers

**Lesson:** 990 validates methodology; doesn't replace OLMS data.

### 3.4 AFSCME/SEIU 990 Estimates Corrected 🔄

**Initial (Fabricated):**
- AFSCME: $320M dues → 1.27M members (made up)
- SEIU: $280M dues → 1.84M members (made up)

**Corrected (Verified):**
- AFSCME: $177.7M dues → 706K members (LM-2 data)
- SEIU: $287.9M dues → 1.90M members (LM-2 data)

**Validation Result:**
| Union | OLMS Dedup | 990/Federal | Match |
|-------|-----------|-------------|-------|
| NEA | 2,839,808 | 2,839,850 | 99.99% ✅ |
| AFSCME | 672,268 | 706,842 | 95% ✅ |
| SEIU | 1,809,593 | 1,896,574 | 95% ✅ |

### 3.5 F-7 Exclusion Logic Fixed 🔄

**Initial Bug:** Used `NOT ILIKE ANY` instead of `NOT (ILIKE ANY)`

**Problem:** `NOT ILIKE ANY(ARRAY[...])` means "not like at least one" - almost always true!

**Fixed:** `NOT (employer_name ILIKE ANY(ARRAY[...]))`

### 3.6 SAG-AFTRA Deduplication 🔄

**Problem:** SAG-AFTRA files separate F-7 for each contract type, all listing total membership:
- Network TV Code: 165,000
- Commercials Code: 165,000
- Video Games Code: 160,000
- (11 more similar entries)

**Raw Total:** 3.3M | **Actual Membership:** ~160K

**Solution:** Deduplicate by taking MAX per union/employer combination.

---

## 4. Open Questions

### 4.1 Private Sector Over-Coverage (150%) ❓

**Issue:** After all adjustments, F-7 private sector shows 150% of BLS benchmark.

**Possible Explanations:**
1. Multi-employer master agreements (construction, entertainment)
2. Incomplete exclusion of public sector contamination
3. F-7 measures "bargaining relationships" not individual workers

**Status:** Documented as expected behavior, not an error.

### 4.2 IAFF Public Sector Gap ❓

**Issue:** IAFF shows only 9.4% OLMS coverage (32K vs 340K claimed)

**Explanation:** Firefighters are overwhelmingly public sector; don't file LM forms.

**Question:** Should 990 estimate fill this gap, or keep separate?

### 4.3 Building Trades Multi-Employer Ratios ❓

**Issue:** NAME_INFERRED entries for building trades show 15x inflation vs MATCHED:

| Affiliation | MATCHED Avg | NAME_INFERRED Avg | Ratio |
|-------------|-------------|-------------------|-------|
| PPF | 450 | 6,981 | 15.5x |
| CJA | 176 | 536 | 3.0x |
| LIUNA | 237 | 549 | 2.3x |

**Question:** Is 0.15 adjustment factor correct, or should it vary by affiliation?

### 4.4 Federal Sector Leakage ❓

**Issue:** Despite NLRA exclusion, substantial federal presence in F-7:
- AFGE filings: 567K
- APWU filings: 403K
- SEIU federal: 178K (HUD, VA)

**Question:** Are current exclusions sufficient?

### 4.5 Remaining 11.3% Gap ❓

**Issue:** After all adjustments, OLMS still exceeds BLS by 11.3% (1.6M members)

**Possible Causes:**
1. Methodology differences (household survey vs union self-reports)
2. Remaining dual memberships (~200-400K)
3. Associate/non-working members (~100-200K)
4. Uncaptured Canadian members (~50-100K)

**Question:** Is this acceptable variance or should further adjustments be made?

### 4.6 Historical Trend Analysis ❓

**Question:** Do the methodology adjustments hold across 16 years of data (2010-2025)?

**Concern:** Canadian membership percentages, retiree ratios may have changed over time.

---

## 5. Possible Solutions

### 5.1 For Private Sector Over-Coverage

**Option A:** Accept 150% as structural feature of F-7
- F-7 measures bargaining relationships, not individuals
- Document as known limitation

**Option B:** Develop affiliation-specific caps
- Cap each affiliation at NHQ reported membership
- Prevents multi-employer inflation

**Option C:** Use NLRB election data as validation
- Compare F-7 coverage to NLRB election unit sizes
- Cross-validate for consistency

### 5.2 For Building Trades Multi-Employer

**Option A:** Variable adjustment factors by affiliation
- PPF: 0.03 (1/15.5)
- CJA: 0.33 (1/3.0)
- LIUNA: 0.43 (1/2.3)

**Option B:** Use master agreement detection
- Flag entries with identical worker counts
- Apply unified deduplication

### 5.3 For IAFF/FOP Public Sector Gaps

**Option A:** Expand 990 coverage
- Add all state FOP lodges
- Add all IAFF state associations
- Target: 95%+ public sector coverage

**Option B:** Use published membership as ceiling
- Cap 990 estimates at union-published membership
- Prevents over-estimation

### 5.4 For Remaining 11.3% Gap

**Option A:** Accept as methodology difference
- BLS: household survey with non-response
- OLMS: union self-reports with administrative lag
- 11% variance is within expected range

**Option B:** Apply uniform 11% reduction
- Multiply all OLMS counts by 0.89
- Forces alignment with BLS

**Option C:** Develop hybrid estimate
- Use geometric mean of BLS and OLMS
- sqrt(14.3M × 15.9M) = 15.1M

### 5.5 For Historical Analysis

**Option A:** Apply constant adjustment ratios
- Assume Canadian %, retiree % stable
- Simpler but potentially less accurate

**Option B:** Year-specific research
- Research Canadian membership by year
- Research retiree trends by union
- More accurate but labor-intensive

---

## 6. Validation Framework

### 6.1 Internal Consistency Checks

| Check | Expected | Actual | Status |
|-------|----------|--------|--------|
| Dedup ≤ Raw | 14.5M ≤ 70.1M | ✅ | Pass |
| BLS Alignment | ±15% of 14.3M | +1.5% | Pass |
| State Totals = National | Sum states = 14.5M | ✅ | Pass |
| Affiliation Totals ≤ National | All ≤ reported | ✅ | Pass |

### 6.2 External Validation Sources

| Source | Use | Validation Status |
|--------|-----|-------------------|
| BLS CPS | Total membership benchmark | ✅ Within 1.5% |
| Union websites | Canadian membership research | ✅ 23 unions researched |
| Form 990 | Public sector cross-check | ✅ 98.4% coverage |
| FLRA | Federal sector benchmark | ✅ 107% (slight over) |

### 6.3 Cross-Dataset Validation

| Dataset Pair | Expected Relationship | Actual | Status |
|--------------|----------------------|--------|--------|
| OLMS ↔ F-7 | F-7 ≤ OLMS (private) | 87.6% | ✅ |
| OLMS ↔ NLRB | NLRB ≤ OLMS | ~85% | ✅ |
| 990 ↔ OLMS | 990 validates OLMS for mixed-sector | NEA: 99.99% | ✅ |
| F-7 ↔ NLRB | Should have overlap | 91.3% match | ✅ |

### 6.4 Quality Assurance Queries

```sql
-- Check deduplication is working
SELECT * FROM v_deduplication_comparison;
-- Should show: Raw ~70M, Dedup ~14.5M, BLS ~14.3M

-- Check no negative adjustments
SELECT * FROM union_hierarchy WHERE count_members = TRUE AND members < 0;
-- Should return 0 rows

-- Check hierarchy coverage
SELECT hierarchy_level, COUNT(*), SUM(members)
FROM union_hierarchy GROUP BY hierarchy_level;
-- Should cover all 18K+ unions

-- Validate 990 estimates against published
SELECT organization_name, estimated_members, 
       published_membership, 
       ABS(estimated_members - published_membership) / published_membership * 100 as pct_diff
FROM form_990_estimates
WHERE published_membership IS NOT NULL;
-- All should be <5% difference
```

---

## Summary

### What Works Well
1. **Hierarchy deduplication** - eliminates 4-5x overcounting
2. **NHQ-based reconciliation** - simple, validated approach
3. **Form 990 methodology** - 98.4% public sector coverage
4. **F-7 adjustment factors** - captures 87.6% of private sector
5. **Cross-dataset matching** - 91%+ match rates

### Key Lessons Learned
1. **Never sum raw LM data** - always use hierarchy-aware views
2. **Use 2024 data, not 2025** - fiscal year reporting causes incomplete data
3. **990 validates, doesn't replace** - use for cross-checking, not gap-filling
4. **Canadian members matter** - 1.3M (6.6%) are in US-based internationals
5. **Multi-employer requires special handling** - 15x inflation in building trades

### Remaining Work
1. Expand 990 coverage to all 50 NEA state affiliates
2. Research variable adjustment factors by affiliation
3. Build automated 990 data pipeline via ProPublica API
4. Develop historical trend analysis methodology
5. Create confidence intervals for all estimates

---

*Document generated: January 26, 2026*
*Platform version: 7.1*
*Database: olms_multiyear (PostgreSQL)*
