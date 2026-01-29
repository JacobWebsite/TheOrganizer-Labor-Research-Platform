# F7 to BLS Private Sector Reconciliation Methodology

## Executive Summary

This document describes the methodology for reconciling F-7 employer bargaining notice data with BLS Current Population Survey (CPS) private sector union membership estimates.

**Key Results:**
| Metric | Value |
|--------|-------|
| F7 Raw Workers | 21.96M |
| F7 Reconciled (Private Sector) | 6.40M |
| BLS Private Sector Benchmark | 7.30M |
| **F7 Coverage Rate** | **87.6%** |

The ~12% gap is consistent with expected structural limitations of F7 data (card check, voluntary recognition, RLA carriers, first contracts).

---

## Background

### What is F7 Data?
F-7 notices are required under 29 U.S.C. 158(d)(3) (NLRA/Taft-Hartley) when employers and unions modify or terminate collective bargaining agreements. They are filed with the Federal Mediation and Conciliation Service (FMCS).

### Legal Jurisdiction
F7 applies **only to private sector** employers under NLRA. NOT covered:
- Federal employees (FSLMRA)
- State/local public employees (state laws)
- Airlines and railroads (Railway Labor Act)
- Agricultural workers (NLRA exemption)

### BLS Benchmark
BLS CPS reports ~14.3M total union members, of which ~7.3M are in private sector employment.

---

## Raw Data Issues Identified

### 1. Federal/Public Sector Contamination (~1.5M raw)
Despite legal exclusion, F7 data contains filings from:

| Category | Raw Workers | Notes |
|----------|-------------|-------|
| AFGE (Federal) | 567K | VA, SSA, USCIS, etc. |
| APWU (Postal) | 403K | Federal postal workers |
| NALC (Postal) | 2K | Letter carriers |
| AFT (Teachers) | 99K | Mostly public schools |
| NTEU (Federal) | 33K | IRS, Treasury, etc. |
| State/City/County employers | 200K+ | Direct government |

### 2. Multi-Employer Association Overcounting (~7M raw → 1M adjusted)
NAME_INFERRED employers (no file number match) often represent:
- Regional master agreements covering all signatory contractors
- Same workers counted under multiple contract types
- Association-wide bargaining (AGC, NECA, etc.)

**Evidence:** PPF (Plumbers/Pipefitters) NAME_INFERRED employers average 6,981 workers vs. 450 for MATCHED locals - a 15x difference indicating association agreements.

### 3. Union-as-Employer Filing Errors (~470K raw)
Entries where the union local is listed as the employer:
- "Teamsters Local 701" - 16K
- "Local 804, IBT" - 8.5K
- Various "Local %", "UAW Local %", etc.

### 4. Duplicate Filings (~600K overcount)
Same employer filing multiple times:
- YRC Freight: 36 filings, 53K raw
- Ford Motor: 42 filings, 37K raw
- ABF Freight: 30 filings, 50K raw

### 5. "All Signatories" Placeholder Entries (~3M raw)
SAG-AFTRA alone has:
- "AT&T Inc." - 999,999 (placeholder)
- 11+ "All Signatories to..." entries at 165K each
- All representing same ~160K actual members

---

## Reconciliation Methodology

### Step 1: Classify Match Types

| Match Type | Description | Count | Raw Workers |
|------------|-------------|-------|-------------|
| MATCHED | F7 employer linked to LM filing via file number | 67K | 8.6M |
| NAME_INFERRED | Affiliation assigned by employer name pattern | 16K | 8.7M |
| UNMATCHED | No file number or pattern match | 16K | 3.6M |

### Step 2: Apply Exclusion Filters

**Excluded Affiliations:**
- AFGE, APWU, NALC, NFFE, NTEU, AFT

**Excluded Union Name Patterns:**
- `%Government Employees%`
- `%Treasury Employees%`
- `%Teachers%`

**Excluded Employer Name Patterns:**
- `%state of%`, `%city of%`, `%county of%`
- `%department of%`, `%HUD/%`
- `local %`, `% local %`
- `%signator%`, `%brotherhood%`

### Step 3: Apply Adjustment Factors

| Match Type | Factor | Rationale |
|------------|--------|-----------|
| MATCHED | Per-affiliation (avg ~55%) | Based on NHQ membership comparison |
| NAME_INFERRED | **0.15** (15%) | Multi-employer associations |
| UNMATCHED | **0.35** (35%) | Conservative unknown |

### Step 4: Deduplicate by Employer Name

Group by (employer_name, affiliation, match_type) and take MAX(workers) to eliminate duplicate filings.

---

## Final Results

### By Match Type
| Match Type | Unique Employers | Raw Workers | Reconciled | Effective Factor |
|------------|------------------|-------------|------------|------------------|
| MATCHED | 60,181 | 7.86M | 4.37M | 55.6% |
| NAME_INFERRED | 15,443 | 6.82M | 1.02M | 15.0% |
| UNMATCHED | 14,313 | 2.86M | 1.00M | 35.0% |
| **TOTAL** | **89,937** | **17.55M** | **6.40M** | **36.4%** |

### Comparison to BLS
| Metric | Value |
|--------|-------|
| F7 Reconciled Private | 6.40M |
| BLS Private Sector | 7.30M |
| **Gap** | **0.90M (12.4%)** |

### Gap Explanation
The 12.4% gap is consistent with workers NOT captured by F7:
1. **Card check / voluntary recognition** (~5-10%): No NLRB election, no F7 requirement
2. **First contracts**: New certifications haven't reached renewal
3. **Small units**: Below practical filing thresholds
4. **RLA carriers**: Airlines and railroads under different law
5. **Agricultural workers**: Exempt from NLRA

---

## Database Objects

### Views Created

**v_f7_private_sector_reconciled**
- Deduplicated, private-sector-only F7 employers
- Columns: employer_name, affiliation, match_type, max_raw, reconciled_workers

**v_f7_reconciliation_summary**
- Aggregated summary by match type with BLS comparison

### Sample Queries

```sql
-- Total reconciled private sector
SELECT SUM(reconciled_workers) FROM v_f7_private_sector_reconciled;

-- By affiliation
SELECT affiliation, COUNT(*) as employers, SUM(reconciled_workers) as workers
FROM v_f7_private_sector_reconciled
GROUP BY affiliation
ORDER BY workers DESC;

-- Summary with BLS comparison
SELECT * FROM v_f7_reconciliation_summary;
```

---

## Limitations and Caveats

1. **Name-based deduplication is imperfect**: "Kroger Company" vs "The Kroger Company" treated as different
2. **Exclusion patterns may be over/under-inclusive**: Some private "City of Hope" hospital excluded by pattern
3. **Adjustment factors are estimates**: Derived from aggregate comparisons, not individual verification
4. **Temporal mismatch**: F7 data spans 16 years, BLS is annual snapshot
5. **Multi-employer complexity**: Some legitimate multi-employer agreements may be over-deflated

---

## Appendix: Key Findings

### SAG-AFTRA Duplication
SAG-AFTRA reports ~3.3M raw workers from 207 employers, but actual membership is ~160K. The union files separate F7s for each contract type (Network TV, Commercials, Video Games, etc.) with total membership each time.

### Building Trades Pattern
Building trades unions (PPF, CJA, BAC, LIUNA, IBEW) show extreme NAME_INFERRED overcounting because regional contractor associations file for all signatory employers collectively.

### Public Sector Leakage
Despite NLRA exclusion, ~1.5M raw workers in F7 are federal/public sector - likely due to:
- Hybrid private/public employers (contractors at federal facilities)
- Filing errors
- Private-sector arms of public entities

---

*Document created: January 2025*
*Database: olms_multiyear (PostgreSQL)*
