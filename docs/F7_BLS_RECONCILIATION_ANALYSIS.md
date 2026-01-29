# F7 to BLS Private Sector Reconciliation Analysis

## Overview

This document describes the comprehensive reconciliation of F-7 employer bargaining notice data with Bureau of Labor Statistics (BLS) Current Population Survey private sector union membership estimates. The analysis identifies systematic overcounting in F7 data and develops adjustment factors to produce reliable private sector coverage estimates.

**Final Result: F7 captures 87.6% of BLS private sector union membership (6.40M vs 7.30M)**

---

## Data Sources

### F-7 Employer Bargaining Notices
- **Source**: Federal Mediation and Conciliation Service (FMCS)
- **Legal Basis**: 29 U.S.C. 158(d)(3) - NLRA/Taft-Hartley Act
- **Coverage**: Private sector employers modifying or terminating collective bargaining agreements
- **Raw Data**: ~150,000 employer records, 21.96M reported workers

### BLS Current Population Survey
- **Private Sector Union Members**: 7.30M (2024)
- **Total Union Members**: 14.3M
- **Methodology**: Household survey asking about union membership

### OLMS LM Financial Filings
- **Source**: Department of Labor Office of Labor-Management Standards
- **Used For**: Validating membership counts and matching F7 employers to union affiliations

---

## Problem Statement

Raw F7 data reports 21.96M workers in bargaining units, but BLS indicates only 7.30M private sector union members exist. This 3x overcount stems from:

1. **Jurisdictional contamination**: Federal and public sector filings despite NLRA private-sector-only requirement
2. **Multi-employer associations**: Regional agreements filed as single employers covering thousands of contractors
3. **Filing errors**: Union locals listed as employers
4. **Duplicate filings**: Same employer filing multiple times for different contracts/locals

---

## Methodology

### Step 1: Classify F7 Employers by Match Type

| Match Type | Description | Employers | Raw Workers |
|------------|-------------|-----------|-------------|
| **MATCHED** | F7 linked to OLMS filing via file number | 67,515 | 8.63M |
| **NAME_INFERRED** | Affiliation assigned by employer name pattern | 16,461 | 8.74M |
| **UNMATCHED** | No file number or pattern match | 15,734 | 3.63M |

### Step 2: Identify and Exclude Non-Private Sector

**Excluded Affiliations:**
- AFGE (American Federation of Government Employees) - Federal
- APWU (American Postal Workers Union) - Federal/Postal
- NALC (National Association of Letter Carriers) - Federal/Postal
- NFFE (National Federation of Federal Employees) - Federal
- NTEU (National Treasury Employees Union) - Federal
- AFT (American Federation of Teachers) - Primarily Public

**Excluded by Union Name Pattern:**
- `%Government Employees%`
- `%Treasury Employees%`
- `%Teachers%`

**Excluded by Employer Name Pattern:**
- `%state of%`, `%city of%`, `%county of%` - Direct government
- `%department of%`, `%HUD/%` - Federal agencies
- `local %`, `% local %` - Union locals listed as employers
- `%signator%` - Multi-employer placeholder entries
- `%brotherhood%` - Often union self-filings

**Total Excluded: ~1.5M raw workers**

### Step 3: Apply Adjustment Factors by Match Type

| Match Type | Factor | Rationale |
|------------|--------|-----------|
| **MATCHED** | Per-affiliation (~55% avg) | Based on comparison to NHQ validated membership |
| **NAME_INFERRED** | **0.15** (15%) | Multi-employer associations grossly overcount |
| **UNMATCHED** | **0.35** (35%) | Conservative estimate for unknown employers |

**NAME_INFERRED Factor Derivation:**

Analysis revealed extreme overcounting in NAME_INFERRED:
- PPF (Plumbers/Pipefitters) MATCHED locals average 450 workers
- PPF NAME_INFERRED employers average 6,981 workers (15.5x higher)
- This indicates association-wide agreements, not individual employers

Example: 20+ different pipeline contractors all reporting exactly 9,000 workers each - clearly the same regional master agreement.

### Step 4: Deduplicate by Employer Name

Same employer often files multiple F7s for:
- Different union locals at same facility
- Different contract types (main agreement, supplements)
- Annual renewals

**Deduplication approach:** Group by (employer_name, affiliation, match_type), take MAX(workers)

**Impact:**
- YRC Freight: 36 filings → 1 (53K → 25K)
- Ford Motor: 42 filings → 1 (37K → 8.7K)
- ABF Freight: 30 filings → 1 (50K → 16K)

---

## Key Findings

### 1. SAG-AFTRA Extreme Duplication

SAG-AFTRA files separate F7 notices for each contract type, all listing total membership:

| Filing | Reported Workers |
|--------|------------------|
| AT&T Inc. (placeholder) | 999,999 |
| All Signatories to Network TV Code | 165,000 |
| All Signatories to Commercials Code | 165,000 |
| All Signatories to Video Games | 160,000 |
| (11 more similar entries) | 165,000 each |
| **Total Raw** | **3.3M** |
| **Actual Membership** | **~160K** |

### 2. Building Trades Association Agreements

Building trades unions show dramatic NAME_INFERRED vs MATCHED differences:

| Union | MATCHED Avg | NAME_INFERRED Avg | Ratio |
|-------|-------------|-------------------|-------|
| PPF (Plumbers) | 450 | 6,981 | 15.5x |
| CJA (Carpenters) | 176 | 536 | 3.0x |
| LIUNA (Laborers) | 237 | 549 | 2.3x |
| BAC (Bricklayers) | 228 | 435 | 1.9x |

NAME_INFERRED entries represent regional contractor associations (AGC, NECA, etc.) filing for all signatory employers.

### 3. Federal Sector Leakage

Despite NLRA exclusion, substantial federal presence in F7:

| Source | Raw Workers | Examples |
|--------|-------------|----------|
| AFGE filings | 567K | VA (300K), SSA (25K), USCIS |
| APWU filings | 403K | Postal workers |
| SEIU federal | 178K | HUD (139K), VA (17K) |
| Other federal agencies | 50K+ | Treasury, DOJ, etc. |

### 4. Public Sector in MATCHED

Even after affiliation exclusions, public employers appear:

| Employer | Workers | Notes |
|----------|---------|-------|
| State of California BU 12 | 21K | IUOE state workers |
| WA Dept of Corrections | 11K | IBT corrections officers |
| Various cities/counties | 20K+ | Municipal workers |

---

## Final Results

### Reconciled Private Sector by Match Type

| Match Type | Unique Employers | Raw Workers | Reconciled | Effective Factor |
|------------|------------------|-------------|------------|------------------|
| MATCHED | 60,181 | 7.86M | 4.37M | 55.6% |
| NAME_INFERRED | 15,443 | 6.82M | 1.02M | 15.0% |
| UNMATCHED | 14,313 | 2.86M | 1.00M | 35.0% |
| **TOTAL** | **89,937** | **17.55M** | **6.40M** | **36.4%** |

### Comparison to BLS Benchmark

| Metric | Value |
|--------|-------|
| F7 Reconciled Private Sector | 6.40M |
| BLS Private Sector Union Members | 7.30M |
| **Gap** | **0.90M (12.4%)** |
| **F7 Coverage Rate** | **87.6%** |

### Gap Explanation

The 12.4% gap is consistent with workers legitimately NOT captured by F7:

1. **Card Check / Voluntary Recognition (~5-10%)**: No NLRB election required, may not file F7
2. **First Contracts**: New certifications haven't reached contract renewal
3. **Small Units**: Below practical filing thresholds
4. **Railway Labor Act Carriers**: Airlines and railroads under different jurisdiction
5. **Agricultural Workers**: Exempt from NLRA coverage

---

## Database Objects

### Views Created

**`v_f7_private_sector_reconciled`**
```sql
-- Columns: employer_name, affiliation, match_type, max_raw, max_matched_adj, reconciled_workers
-- 89,937 rows representing unique private sector employers

SELECT * FROM v_f7_private_sector_reconciled LIMIT 10;
```

**`v_f7_reconciliation_summary`**
```sql
-- Quick summary by match type with BLS comparison
SELECT * FROM v_f7_reconciliation_summary;
```

### Sample Queries

```sql
-- Total reconciled private sector workers
SELECT SUM(reconciled_workers) as total_private
FROM v_f7_private_sector_reconciled;
-- Result: 6,396,375

-- By affiliation
SELECT affiliation, 
    COUNT(*) as employers, 
    SUM(reconciled_workers) as workers
FROM v_f7_private_sector_reconciled
GROUP BY affiliation
ORDER BY workers DESC
LIMIT 15;

-- By state
SELECT state, SUM(reconciled_workers) as workers
FROM v_f7_private_sector_reconciled r
JOIN f7_employers e ON r.employer_name = e.employer_name
GROUP BY state
ORDER BY workers DESC;
```

---

## Adjustment Factor Summary

| Category | Factor | Application |
|----------|--------|-------------|
| Federal affiliations | 0.00 | AFGE, APWU, NALC, NFFE, NTEU |
| Public affiliations | 0.00 | AFT |
| MATCHED private | ~0.50-0.60 | Per-affiliation based on NHQ |
| NAME_INFERRED private | 0.15 | Multi-employer associations |
| UNMATCHED private | 0.35 | Conservative unknown |
| Union-as-employer | 0.00 | Filing errors excluded |
| Signatories/placeholders | 0.00 | Excluded by pattern |

---

## Limitations

1. **Name-based deduplication imperfect**: "Kroger Company" vs "The Kroger Company" treated as different
2. **Over-exclusion possible**: Some private employers with "City" in name (e.g., "City of Hope" hospital)
3. **Temporal mismatch**: F7 spans 16 years, BLS is annual snapshot
4. **Multi-employer complexity**: Some legitimate agreements may be over-deflated
5. **NAICS gaps**: Many employers lack industry classification

---

## Conclusions

1. **Raw F7 data is unreliable** for membership estimation without significant adjustment
2. **Multi-employer associations** are the primary source of overcounting
3. **Federal/public contamination** exists despite NLRA private-sector jurisdiction
4. **87.6% coverage** after reconciliation is consistent with expected F7 limitations
5. **Adjustment factors** vary significantly by match type and affiliation

---

## References

- 29 U.S.C. 158(d)(3) - NLRA F7 notice requirements
- BLS Union Members Summary (USDL-24-0128)
- OLMS Public Disclosure Data
- FMCS F-7 Notice Database

---

*Analysis completed: January 2025*
*Database: olms_multiyear (PostgreSQL)*
*Views: v_f7_private_sector_reconciled, v_f7_reconciliation_summary*
