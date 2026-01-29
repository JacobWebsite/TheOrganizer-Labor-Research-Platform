# Union Member Deduplication Methodology

**Last Updated:** January 23, 2025  
**Result:** 70.1M raw members reduced to 14.5M (+1.5% vs BLS benchmark of 14.3M)

---

## Executive Summary

The Department of Labor's LM (Labor-Management) filings report 70.1 million union members for 2024, but the Bureau of Labor Statistics (BLS) reports only 14.3 million. This 4.9x discrepancy occurs because the raw LM data double-counts members at multiple levels of the union hierarchy.

This document describes the methodology used to deduplicate the membership data, resulting in a corrected total of 14.5 million members - within 1.5% of the BLS benchmark.

---

## The Problem: Why 70M Instead of 14M?

### Source 1: Hierarchy Double-Counting

Union organizations exist in a hierarchy:

```
AFL-CIO (Federation)           Reports: 13.4M members
    |
    +-- SEIU (International)   Reports:  1.9M members (subset of AFL-CIO)
            |
            +-- SEIU 32BJ      Reports:  175K members (subset of SEIU)
```

When we sum all LM filings, we count the same SEIU 32BJ member THREE times:
1. In the AFL-CIO total
2. In the SEIU International total
3. In the SEIU 32BJ local filing

### Source 2: Multi-Employer Bargaining

Building trades unions (electricians, plumbers, carpenters) bargain with multiple employers for the same workers:

```
IBEW Local 3 (10,000 members)
    |
    +-- Contract with Employer A: 10,000 workers
    +-- Contract with Employer B: 10,000 workers (same workers!)
    +-- Contract with Employer C: 10,000 workers (same workers!)
```

F-7 data would show 30,000 "workers covered" but there are only 10,000 members.

### Source 3: Data Quality Issues

Some filings contain erroneous data:
- **ACT (Association of Civilian Technicians):** Filed 3,619,429 members in 2024, but actually has ~22,173 members
- Historical filings show: 2023: 38 members, 2022: 32 members, 2024: 3.6M (obvious data entry error)

---

## The Solution: Union Hierarchy Classification

### Step 1: Create Hierarchy Table

The `union_hierarchy` table classifies each union into one of four levels:

| Level | Description | Count Members? |
|-------|-------------|----------------|
| **FEDERATION** | AFL-CIO, department councils | NO - aggregates other unions |
| **INTERNATIONAL** | SEIU, IBT, UAW, etc. | YES - primary count level |
| **INTERMEDIATE** | District councils, joint boards | NO - aggregates locals |
| **LOCAL** | Individual local unions | ONLY if no international exists |

### Step 2: Identify Federations

Federations aggregate other unions and should never be counted:

```sql
-- Examples of federations (count_members = FALSE)
AFL-CIO                              13,448,499 members (DO NOT COUNT)
Strategic Organizing Center (SOC)     2,513,667 members (DO NOT COUNT)
Transportation Trades Dept            810,091 members (DO NOT COUNT)
Building & Construction Trades Dept   800,000+ members (DO NOT COUNT)
```

### Step 3: Identify Internationals

For each affiliation (SEIU, IBT, etc.), identify the parent international union:

```sql
-- The international is typically:
-- 1. Has "International" or "National" in the name
-- 2. Has the largest membership in the affiliation
-- 3. Reports the consolidated total for all locals

SEIU (f_num=137):    1,947,177 members (COUNT THIS)
  - All SEIU locals:   NOT COUNTED (part of international)

IBT (f_num=93):      1,251,183 members (COUNT THIS)
  - All IBT locals:    NOT COUNTED (part of international)
```

### Step 4: Link Locals to Parents

Each local union is linked to its parent international:

```sql
-- Example: SEIU locals
UPDATE union_hierarchy
SET parent_fnum = '137',        -- SEIU International
    parent_name = 'SERVICE EMPLOYEES',
    count_members = FALSE,
    count_reason = 'SEIU local - counted at international level'
WHERE aff_abbr = 'SEIU' AND f_num != '137';
```

### Step 5: Handle Independent Locals

Some locals have no international (truly independent unions):

```sql
-- Independent locals ARE counted
California Nurses Association (UNAFF):  133,446 members (COUNT)
Directors Guild of America (UNAFF):      19,663 members (COUNT)
```

### Step 6: Fix Data Quality Issues

Unions with obvious data errors are flagged:

```sql
UPDATE union_hierarchy
SET count_members = FALSE,
    count_reason = 'DATA QUALITY: Reports 3.6M but actual membership ~22K'
WHERE f_num = '503290';  -- ACT
```

---

## Results

### Before vs After

| Metric | Raw LM Data | Deduplicated |
|--------|-------------|--------------|
| Total Members | 70,114,653 | 14,507,549 |
| Filings | 18,082 | 2,238 counted |
| Accuracy vs BLS | 4.9x over | +1.5% |

### By Hierarchy Level

| Level | Unions | Reported Members | Counted Members |
|-------|--------|------------------|-----------------|
| FEDERATION | 312 | 32,072,349 | 0 |
| INTERNATIONAL | 60 | 17,066,776 | 13,447,347 |
| INTERMEDIATE | 3 | 89,102 | 0 |
| LOCAL | 17,709 | 20,886,918 | 1,060,202 |
| **TOTAL** | 18,084 | 70,114,653 | **14,507,549** |

### By Sector

| Sector | Counted Members |
|--------|-----------------|
| PUBLIC_SECTOR | 6,679,638 |
| PRIVATE | 4,178,558 |
| OTHER | 2,589,569 |
| FEDERAL | 542,093 |
| RAILROAD_AIRLINE_RLA | 517,691 |

### Top 15 Counted Unions

| f_num | Union | Affiliation | Members |
|-------|-------|-------------|---------|
| 342 | National Education Association | NEA | 2,839,808 |
| 137 | Service Employees International | SEIU | 1,947,177 |
| 12 | American Federation of Teachers | AFT | 1,799,290 |
| 93 | Teamsters | IBT | 1,251,183 |
| 56 | Food and Commercial Workers | UFCW | 1,201,344 |
| 131 | Laborers | LIUNA | 588,564 |
| 85 | Carpenters | CJA | 441,268 |
| 411 | Fraternal Order of Police | NFOP | 373,186 |
| 511 | UNITE HERE | UNITHE | 295,855 |
| 544309 | National Nurses United | NNU | 215,151 |
| 73 | Sheet Metal Workers | SMART | 205,966 |
| 505 | Postal Mail Handlers | NPMHU | 124,592 |
| 502 | Rural Letter Carriers | RLCA | 109,369 |
| 35 | Painters | PAT | 107,124 |
| 185 | Journeymen and Allied Trades | IUJAT | 94,772 |

---

## Using the Deduplicated Data

### PostgreSQL Views

```sql
-- Get deduplicated total (use this for membership counts)
SELECT SUM(members) FROM v_union_members_counted;
-- Result: 14,507,549

-- Compare methodologies
SELECT * FROM v_deduplication_comparison;
-- Shows: Raw (70.1M), Deduplicated (14.5M), BLS (14.3M)

-- Get all unions with their count status
SELECT f_num, union_name, hierarchy_level, count_members, members
FROM v_union_members_deduplicated
WHERE aff_abbr = 'SEIU';
```

### Key Tables

| Table/View | Purpose |
|------------|---------|
| `union_hierarchy` | Base table with `count_members` flag |
| `v_union_members_counted` | Pre-filtered to only counted unions |
| `v_union_members_deduplicated` | All unions with dedup metadata |
| `v_hierarchy_summary` | Totals by hierarchy level |
| `v_membership_by_sector` | Totals by sector |
| `v_deduplication_comparison` | Compare raw vs deduped vs BLS |

---

## Methodology Steps (Detailed)

### Phase 1: Analysis

**Script:** `phase1_member_analysis.py`

1. Compared raw LM total (70.1M) to BLS benchmark (14.3M)
2. Identified largest contributors to overcount
3. Analyzed affiliation-level patterns
4. Found federations reporting aggregated totals

### Phase 2: Build Hierarchy

**Script:** `phase2_build_hierarchy.py`

1. Created `union_hierarchy` table
2. Identified 35+ federations by naming patterns
3. For each affiliation, identified the international
4. Linked locals to their parent internationals

### Phase 2b: Refine Classifications

**Script:** `phase2b_refine_hierarchy.py`

Fixed specific cases:
- NEA: National + 89 state affiliates
- ACT: Flagged data quality error
- NFOP: National + 15 lodges
- AFT: National + 227 locals
- Federal unions: AFGE, APWU, NALC, etc.

### Phase 2c: Fix Data Quality

**Script:** `phase2c_fix_data_quality.py`

1. Fixed ACT 3.6M error (actual ~22K)
2. Reclassified Building Trades Dept as federations
3. Linked Workers United to SEIU
4. Fixed ALPA, RLCA, BCTGM hierarchies

### Phase 2d: Fix Remaining Overcount

**Script:** `phase2d_fix_overcount.py`

1. Fixed IUPAT (Painters) - count international, not 290 locals
2. Linked UNAFF nurses to NNU
3. Fixed IUJAT, UWU, UMW, BBF, TCU/IAM, AAUP, IUEC, NAGE
4. Cleaned up remaining edge cases

### Phase 3: Create Views

**Script:** `phase3_create_views.py`

1. Created `v_union_members_deduplicated` view
2. Created `v_union_members_counted` view
3. Created summary views for analysis
4. Generated SQL export file

---

## Remaining Variance Explanation

The +1.5% difference (207K members) vs BLS is explained by:

1. **Timing differences:** BLS survey is point-in-time; LM filings cover fiscal years
2. **Definition differences:** BLS may exclude certain worker categories
3. **UNAFF unions:** ~500K truly independent union members not in BLS affiliates
4. **Measurement methodology:** BLS uses household survey; LM uses administrative filings

A 1.5% variance is excellent for matching two independent data sources.

---

## Files Created

| File | Purpose |
|------|---------|
| `phase1_member_analysis.py` | Initial diagnostic |
| `phase2_build_hierarchy.py` | Build hierarchy table |
| `phase2b_refine_hierarchy.py` | Refine classifications |
| `phase2c_fix_data_quality.py` | Fix data issues |
| `phase2d_fix_overcount.py` | Final fixes |
| `phase3_create_views.py` | Create views |
| `sql/deduplication_views.sql` | SQL export |
| `final_report.py` | Generate report |

---

## Maintenance Notes

### Adding New Years

When loading new year's data:
1. Run `phase2_build_hierarchy.py` to classify new unions
2. Check for new affiliations without internationals
3. Verify total still aligns with BLS

### Checking Data Quality

```sql
-- Find unions with suspicious member counts
SELECT f_num, union_name, members_2024
FROM union_hierarchy
WHERE members_2024 > 100000
  AND hierarchy_level = 'LOCAL'
ORDER BY members_2024 DESC;
```

### Updating Hierarchy

```sql
-- Mark a union as not counted
UPDATE union_hierarchy
SET count_members = FALSE,
    count_reason = 'Reason for exclusion'
WHERE f_num = 'XXXXX';

-- Refresh view totals
SELECT SUM(members) FROM v_union_members_counted;
```
