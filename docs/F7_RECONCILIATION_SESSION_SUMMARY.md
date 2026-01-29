# F7 Reconciliation Analysis Session Summary
## Date: January 24, 2025

### Objective
Reconcile F7 employer bargaining notice data (~22M raw workers) with BLS private sector union membership benchmark (7.3M).

### Key Discoveries

#### 1. Public Sector Contamination (~1.5M raw)
F7 data contains federal and public sector employers despite NLRA only applying to private sector:
- AFGE: 567K (VA, SSA, USCIS)
- APWU: 403K (Postal)
- AFT: 99K (Teachers)
- State/City/County employers: 200K+

#### 2. Multi-Employer Association Overcounting
NAME_INFERRED employers (pattern-matched without file numbers) represent association-wide agreements:
- PPF NAME_INFERRED avg: 6,981 workers (vs 450 for MATCHED)
- Same workers counted multiple times across different contracts
- Required 0.15 (85% deflation) factor

#### 3. Union-as-Employer Filing Errors (~470K raw)
Entries where union locals are listed as employers ("Local 804, IBT", "Teamsters Local 701")

#### 4. Duplicate Filings (~600K overcount)
Same employer filing multiple times (YRC Freight: 36 filings, Ford: 42 filings)

#### 5. SAG-AFTRA Extreme Duplication
3.3M raw from 207 employers representing only ~160K actual members
- Multiple "All Signatories to..." entries at 165K each
- AT&T Inc. placeholder at 999,999

### Final Reconciliation

| Category | Employers | Reconciled Workers |
|----------|-----------|-------------------|
| MATCHED (×~0.56) | 60,181 | 4.37M |
| NAME_INFERRED (×0.15) | 15,443 | 1.02M |
| UNMATCHED (×0.35) | 14,313 | 1.00M |
| **TOTAL PRIVATE** | **89,937** | **6.40M** |
| BLS Benchmark | - | 7.30M |

**F7 Coverage: 87.6%** - Gap explained by card check, voluntary recognition, RLA, first contracts.

### Database Objects Created
- `v_f7_private_sector_reconciled` - Deduplicated private sector employers with reconciled workers
- `v_f7_reconciliation_summary` - Summary by match type with BLS comparison

### Files Created
- `F7_BLS_RECONCILIATION_METHODOLOGY.md` - Full methodology documentation

### Key SQL Patterns Used
```sql
-- Proper exclusion syntax
AND NOT (column ILIKE ANY(ARRAY['%pattern1%','%pattern2%']))

-- Deduplication by employer name
GROUP BY employer_name, affiliation, match_type
-- Take MAX to avoid double-counting
```

### Next Steps
1. Consider fuzzy matching for employer name deduplication (e.g., "Kroger" vs "The Kroger Company")
2. Validate specific large employers individually
3. Integrate with NLRB election data for first-contract analysis
4. Build industry-level reconciliation using NAICS codes
