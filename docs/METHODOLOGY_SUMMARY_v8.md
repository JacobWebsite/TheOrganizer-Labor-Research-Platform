# Labor Relations Research Platform - Comprehensive Methodology Summary

**Last Updated:** January 29, 2026  
**Version:** 8.0

---

## Table of Contents

1. [Project Overview](#1-project-overview)
2. [Data Architecture](#2-data-architecture)
3. [Membership Deduplication Methodology](#3-membership-deduplication-methodology)
4. [Public Sector Reconciliation Methodology](#4-public-sector-reconciliation-methodology)
5. [Entity Matching Methodology](#5-entity-matching-methodology)
6. [Validation Framework](#6-validation-framework)
7. [Open Questions & Future Work](#7-open-questions--future-work)

---

## 1. Project Overview

### Goal
Build a comprehensive labor relations research platform integrating multiple federal datasets to analyze workplace organization trends, employer relationships, and labor market dynamics across the United States.

### Core Problem Solved
**Raw OLMS LM data reports 70.1M union members, but BLS benchmark is only 14.3M.** The platform developed systematic methodologies to reconcile these differences and produce accurate membership counts.

### Final Platform Metrics (January 2026)
| Metric | Value | Benchmark | Accuracy |
|--------|-------|-----------|----------|
| Total Union Members | 14.5M | 14.3M (BLS) | 101.4% ✅ |
| Private Sector | 6.65M | 7.2M | 92% |
| Federal Sector | 1.28M | 1.1M | 116% |
| State/Local Public | 6.9M | 7.0M (EPI) | 98.3% ✅ |

---

## 2. Data Architecture

### Core Tables

| Table | Records | Purpose |
|-------|---------|---------|
| `unions_master` | 26,665 | OLMS LM union filings |
| `union_hierarchy` | 26,665 | Hierarchy classification for deduplication |
| `f7_employers` | 99,907 | F-7 bargaining notice employers |
| `f7_union_employer_relations` | 150,386 | Union-employer relationships |
| `nlrb_elections` | 33,096 | NLRB election records |
| `nlrb_participants` | 1,906,542 | Case participants (95.7% matched) |
| `flra_units` | 2,183 | Federal sector bargaining units |
| `manual_employers` | 431 | State/local public sector research |
| `epi_state_benchmarks` | 51 | EPI/CPS state benchmarks |

### New Public Sector Schema (v8)

| Table | Records | Purpose |
|-------|---------|---------|
| `ps_parent_unions` | 24 | International/national unions |
| `ps_union_locals` | 1,520 | Local unions, councils, chapters |
| `ps_employers` | 7,987 | Public sector employers by type |
| `ps_bargaining_units` | 438 | Union-employer relationships |

---

## 3. Membership Deduplication Methodology

### Problem Statement
Raw OLMS LM data overcounts members 4.9x because:
1. **Hierarchy double-counting**: Members counted at federation, international, AND local levels
2. **Multi-employer agreements**: Same workers reported by multiple employers
3. **Retiree/inactive members**: Non-working members included
4. **Canadian members**: International unions include non-US members
5. **Dual affiliations**: NEA/AFT merged affiliates count twice

### Solution: Hierarchy-Based Deduplication

**Step 1: Classify Hierarchy Levels**
```
FEDERATION (AFL-CIO, CTW)     → count_members = FALSE
INTERMEDIATE (District Council) → count_members = FALSE  
INTERNATIONAL (SEIU National)  → count_members = FALSE (if locals exist)
LOCAL (SEIU Local 32BJ)       → count_members = TRUE
INDEPENDENT                    → count_members = TRUE
```

**Step 2: Apply Adjustments**
| Adjustment | Amount | Method |
|------------|--------|--------|
| Hierarchy dedup | -55.6M | count_members flag |
| Retirees/Inactive | -2.1M | Schedule 13 analysis |
| Canadian Members | -1.3M | 23 union web research |
| NEA/AFT Dual | -903K | NYSUT, FEA, Education MN |

**Step 3: Validate Against BLS**
| Sector | Raw | Deduped | BLS | Accuracy |
|--------|-----|---------|-----|----------|
| Total | 70.1M | 14.5M | 14.3M | 101.4% |

### Key Views
- `v_union_members_counted` - Deduplicated totals
- `v_union_members_deduplicated` - By union detail

---

## 4. Public Sector Reconciliation Methodology

### Problem Statement
State/local public sector unions largely exempt from OLMS LM reporting under LMRDA. Need alternative methodology to estimate membership by state.

### Solution: Multi-Source Reconciliation Against EPI Benchmarks

#### Step 1: Establish Benchmarks
Loaded EPI (Economic Policy Institute) state-level data from CPS analysis:
- `members_public`: Dues-paying public sector union members by state
- `represented_public`: Workers covered by CBAs (includes free riders)
- Source years: 2019-2025 depending on state sample size

#### Step 2: Compile Public Sector Data Sources

| Source | Coverage | Strengths | Limitations |
|--------|----------|-----------|-------------|
| OLMS LM Filings | Unions >$300K/year or >12K workers | Official data | Most exempt |
| NEA/AFT Reports | Teachers | Direct counts | May overlap |
| Form 990 Data | Nonprofits | Revenue-based estimates | Requires per-capita rates |
| Web Research | All | Fills gaps | Manual, time-intensive |
| F-7 Notices | Some public | Official | Limited coverage |

#### Step 3: State-by-State Research Protocol

For each state:
1. **Load OLMS data**: Public sector unions that file (SEIU, AFSCME councils)
2. **Add NEA state affiliates**: State education associations (don't file OLMS)
3. **Add AFT locals**: Teachers unions, classified staff
4. **Add police unions**: FOP, PBA, CLEAT (state associations)
5. **Add fire unions**: IAFF state/local affiliates
6. **Add transit unions**: ATU, TWU locals
7. **Add municipal/county unions**: AFSCME locals, independent associations
8. **Add higher ed unions**: AAUP chapters, graduate employee unions

#### Step 4: Validate Against EPI
Target: Within ±15% of `members_public` benchmark

| Status | Criteria | States |
|--------|----------|--------|
| COMPLETE | 85-115% of EPI | 50 |
| DOCUMENTED VARIANCE | <85% with explanation | 1 (Texas) |

#### Step 5: Handle Methodology Variances

**Texas Variance Example:**
- Our data: 225,400 state/local members
- EPI benchmark: 326,621
- Coverage: 69.0%

**Root Cause Analysis:**
1. CPS respondents self-identify ATPE (100K+ members) as "union-like" though it explicitly does not support collective bargaining
2. Texas has no public sector collective bargaining except limited meet-and-confer
3. BLS shows 603K total TX union members; our 225K public sector = 37%, reasonable

**Resolution:** Document as methodology variance, not missing data.

### Reconciliation Results

| Metric | Value |
|--------|-------|
| States COMPLETE (±15% of EPI) | 50 of 51 |
| States with Documented Variance | 1 (Texas) |
| National State/Local Total | 6,903,645 |
| EPI National Benchmark | 7,021,619 |
| National Coverage | **98.3%** |

### Data Quality Flags

Records flagged for review:
- `coverage_rate > 130%` → Possible double-counting
- `coverage_rate < 70%` → Possible missing data
- `is_right_to_work = TRUE AND high_density` → Verify estimates
- `headquarters_state = TRUE` → May distort state totals

---

## 5. Entity Matching Methodology

### Union Name Matching

**Challenge:** Same union appears with different names across datasets
- OLMS: "SERVICE EMPLOYEES AFL-CIO"
- NLRB: "SEIU Local 32BJ"
- F-7: "Service Employees International Union"

**Solution: Union Names Crosswalk**

| Stage | Method | Match Rate |
|-------|--------|------------|
| Exact | Normalized string match | 53.6% |
| Affiliation | Match by aff_abbr pattern | 34.5% |
| Fuzzy | Levenshtein + token overlap | 11.9% |

**Result:** 95.7% NLRB participant matching (up from ~50%)

### Employer Matching

**Challenge:** F-7 employers need deduplication and classification

**Solution:**
1. Normalize names (remove punctuation, standardize suffixes)
2. Group by address/city/state
3. Confidence scoring (high/medium/low)
4. Manual review for ambiguous cases

**Result:** 96.2% F-7 employer matching

---

## 6. Validation Framework

### Benchmark Sources

| Benchmark | Source | Frequency | Use |
|-----------|--------|-----------|-----|
| Total members | BLS CPS | Annual | National validation |
| State members | EPI Analysis | Annual | State validation |
| Industry density | BLS CPS | Annual | Sector validation |
| Election outcomes | NLRB | Continuous | Activity validation |

### Validation Rules

1. **Macro validation**: Platform total within 5% of BLS
2. **Sector validation**: Each sector within 20% of BLS
3. **State validation**: Each state within 15% of EPI
4. **Trend validation**: Year-over-year changes directionally consistent

### Quality Metrics

| Metric | Target | Current |
|--------|--------|---------|
| BLS alignment | <5% | 1.4% ✅ |
| State coverage | >85% | 98.3% ✅ |
| NLRB match rate | >80% | 95.7% ✅ |
| F-7 match rate | >95% | 96.2% ✅ |

---

## 7. Open Questions & Future Work

### Unresolved Issues

1. **Represented vs Members**: F-7 counts represented workers; EPI tracks members. Gap = free riders (especially post-Janus in public sector)

2. **Temporal Alignment**: OLMS data is annual; CPS is monthly averaged. Timing differences can cause 2-3% variance.

3. **Small Union Coverage**: Unions <$300K/year exempt from LM reporting. Estimated 500K workers in small independents not captured.

### Future Enhancements

| Enhancement | Impact | Effort |
|-------------|--------|--------|
| OSHA integration | Safety-based targeting | Medium |
| Contract expiration tracking | Organizing timing | High |
| Mergent corporate hierarchies | Parent company analysis | High |
| State PERB data | Better public sector | Medium |
| Real-time NLRB monitoring | Current activity | Medium |

---

## Appendix: Key SQL Views

```sql
-- Deduplicated membership
SELECT * FROM v_union_members_deduplicated;

-- State public sector comparison
SELECT * FROM v_state_epi_comparison;

-- Union name lookup
SELECT * FROM v_union_name_lookup WHERE confidence = 'HIGH';

-- Public sector locals with employer counts
SELECT * FROM v_ps_union_locals_full;
```

---

*Document Version: 8.0 | Last Updated: January 29, 2026*
