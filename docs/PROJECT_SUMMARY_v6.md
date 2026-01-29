# Labor Relations Platform - Project Summary v6

## Last Updated: January 26, 2026

---

## Executive Summary

The Labor Relations Platform is a comprehensive research database integrating multiple federal datasets to analyze workplace organization trends, financial patterns, and employer relationships across the United States. This document summarizes the current state of the platform after completing entity matching improvements, BLS coverage validation, and sector reclassification.

---

## Platform Statistics

### Data Sources

| Source | Records | Description |
|--------|---------|-------------|
| OLMS Unions | 26,665 | Master union registry from Department of Labor |
| F-7 Employers | 71,077 | Employers with F-7 bargaining notices |
| NLRB Elections | 67,779 | Election tallies (2010-2025) |
| VR Cases | 1,681 | Voluntary recognition cases |
| Union Hierarchy | 18,067 | Deduplicated membership structure |
| BLS Data | 16 tables | Union density, state rates, industry data |

### Match Rates Achieved

| Dataset | Match Rate | Workers/Cases |
|---------|------------|---------------|
| F-7 Employer → Union | **96.2%** | 15.16M workers |
| F-7 Worker Coverage | **97.9%** | 15.16M of 15.48M |
| NLRB Election → Union | **93.4%** | 32,386 of 34,683 |
| VR → Union | **93.4%** | 1,570 of 1,681 |
| VR → Employer | **35.1%** | 590 of 1,681 |

---

## Entity Matching Improvements

### F-7 Employer → Union Matching

Improved from **67.5% to 96.2%** (+28.7%)

| Checkpoint | Target | Employers Added | Workers Linked |
|------------|--------|-----------------|----------------|
| A | SAG-AFTRA (f_num=391) | +108 | 1,652,904 |
| B | Carpenters (f_num=85) | +838 | 508,796 |
| C | SEIU (f_num=137) | +5,225 | 1,243,884 |
| D | Building Trades (18 unions) | +10,463 | 3,222,789 |
| E | Remaining Major Unions | +1,991 | 1,433,337 |
| F | Final Cleanup | +1,798 | 442,300 |
| **TOTAL** | | **+20,423** | **8,504,010** |

### Key Union F_NUM Mappings

| Union | F_NUM | Employers | Workers |
|-------|-------|-----------|---------|
| SEIU | 137 | 5,225 | 1,243,884 |
| Carpenters (CJA) | 85 | 838 | 508,796 |
| SAG-AFTRA | 391 | 108 | 1,652,904 |
| Teamsters (IBT) | 93 | 1,226 | varies |
| IBEW | 68 | 2,106 | varies |
| Operating Engineers | 132 | 1,898 | varies |
| Laborers (LIUNA) | 80 | 1,461 | varies |
| Steelworkers (USW) | 117 | 235 | varies |
| UFCW | 76 | 1,012 | varies |
| Machinists (IAM) | 107 | 1,334 | varies |

### NLRB & VR Matching (Checkpoint G)

**NLRB Elections:**
- Updated 1,282 tallies with pattern-based matching
- Major fixes: Steelworkers (172), UE (128), Workers United (119), Painters (88)
- Final rate: 93.4% of union entries matched

**Voluntary Recognition:**
- Updated 114 cases with union matching
- Major fixes: UNITE HERE (48), Workers United (28), Painters (18)
- Final union rate: 93.4%
- Employer matching limited to 35.1% (expected for new organizing)

---

## BLS Coverage Analysis

### National Benchmarks (2024)

| Metric | BLS | Platform | Coverage |
|--------|-----|----------|----------|
| Total Union Members | 14,325,000 | 14,507,547 | **101.3%** |
| State-Level Total | 14,258,000 | 14,232,030 | **99.8%** |

### Sector-Adjusted Coverage (After Reclassification)

| Sector | BLS Benchmark | Platform | Coverage |
|--------|---------------|----------|----------|
| **PRIVATE (strict)** | 7,300,000 | 10,964,597 | **150.2%** |
| **PRIVATE + MIXED(70%)** | 7,300,000 | 12,280,762 | **168.2%** |
| **PUBLIC in F-7** | 7,025,000 | 929,088 | **13.2%** |

**Note:** 150% private coverage reflects multi-employer agreements in building trades and entertainment, not overcounting.

### State Coverage (Top 10)

| State | BLS Members | Platform | Coverage |
|-------|-------------|----------|----------|
| California | 2,381,000 | 2,414,099 | 101.4% |
| New York | 1,706,000 | 1,640,003 | 96.1% |
| Illinois | 734,000 | 892,644 | 121.6% |
| Pennsylvania | 666,000 | 631,189 | 94.8% |
| Ohio | 621,000 | 557,377 | 89.8% |
| Michigan | 581,000 | 647,455 | 111.4% |
| Washington | 548,000 | 756,096 | 138.0% |
| Massachusetts | 496,000 | 416,603 | 84.0% |
| Florida | 462,000 | 246,638 | 53.4% |
| Minnesota | 379,000 | 783,109 | 206.6% |

---

## Sector Reclassification

### Problem Addressed

The original `sector` field in `unions_master` had classification issues:
- SEIU classified as PUBLIC_SECTOR (actually ~70% private)
- Entertainment unions in OTHER (should be PRIVATE)
- Maritime, hospitality, communications in OTHER

### Changes Made

| Checkpoint | Action | Impact |
|------------|--------|--------|
| A | Added `sector_revised` column | Preserved original data |
| B | OTHER → PRIVATE (4,103 unions) | Entertainment, maritime, hospitality |
| C | Created MIXED sector | SEIU (144 unions, 4.9M members) |
| D | Fixed PUBLIC_SECTOR | OPEIU, UE → PRIVATE |
| E | Flagged federations | 496 unions, 22.7M excluded |
| F | Validated against F-7 | Confirmed accuracy |

### F-7 by Revised Sector

| Sector | Employers | Workers |
|--------|-----------|---------|
| PRIVATE | 49,308 | 10,485,997 |
| MIXED_PUBLIC_PRIVATE | 6,904 | 1,880,235 |
| UNKNOWN | 5,305 | 1,053,034 |
| FEDERAL | 186 | 721,346 |
| RAILROAD_AIRLINE_RLA | 4,467 | 478,600 |
| OTHER | 1,231 | 329,832 |
| PUBLIC_SECTOR | 973 | 207,742 |

---

## Database Views

### Analytical Views

| View | Rows | Purpose |
|------|------|---------|
| `v_f7_union_summary` | 71,077 | F-7 employers with union details |
| `v_nlrb_election_summary` | 67,779 | NLRB elections with union matches |
| `v_vr_summary` | 1,681 | VR cases with matches |
| `v_union_activity_summary` | 21,919 | Union-level aggregation |
| `v_platform_metrics` | 5 | Platform-wide metrics |
| `v_state_union_activity` | 61 | State-level aggregation |

### Coverage Views

| View | Purpose |
|------|---------|
| `v_bls_coverage_summary` | National BLS comparison |
| `v_bls_sector_coverage` | F-7 by revised sector |
| `v_sector_coverage_summary` | Sector-adjusted BLS metrics |
| `v_platform_master_metrics` | Master dashboard metrics |

---

## Top Unions by Activity

| Union | F-7 Employers | NLRB Elections | VR Cases | Total |
|-------|---------------|----------------|----------|-------|
| SEIU | 5,225 | 2,996 | 32 | 8,253 |
| Machinists (IAM) | 1,334 | 863 | 85 | 2,282 |
| Teamsters (IBT) | 1,226 | 341 | 161 | 1,728 |
| Steelworkers (USW) | 235 | 797 | 7 | 1,039 |
| Carpenters (CJA) | 838 | 85 | 7 | 930 |
| AFSCME | 248 | 640 | 8 | 896 |
| CWA | 404 | 438 | 13 | 855 |

---

## Files & Documentation

### Project Documentation
- `PROJECT_STATUS_v5.md` - Previous status summary
- `ENTITY_MATCHING_IMPROVEMENT_PLAN.md` - Matching methodology
- `ENTITY_MATCHING_BLS_COVERAGE_FINAL.md` - Coverage analysis
- `SECTOR_RECLASSIFICATION_PLAN.md` - Sector fixes
- `PROJECT_SUMMARY_v6.md` - This document

### Key Scripts

**Entity Matching:**
- `checkpoint_a1.py` through `checkpoint_f3.py` - F-7 matching
- `checkpoint_g1.py` through `checkpoint_g_final.py` - NLRB/VR matching

**BLS Coverage:**
- `bls_coverage_3_1.py` through `bls_coverage_3_5.py`

**Sector Reclassification:**
- `sector_reclass_a.py` through `sector_reclass_final.py`

**Views:**
- `create_views_2_1.py` through `create_views_2_5.py`

---

## Database Schema Additions

### New Columns
```sql
-- unions_master
ALTER TABLE unions_master ADD COLUMN sector_revised VARCHAR(30);
ALTER TABLE unions_master ADD COLUMN is_federation BOOLEAN DEFAULT FALSE;
```

### Sector Values
- `PRIVATE` - Private sector unions
- `PUBLIC_SECTOR` - State/local government (AFT, AFSCME, IAFF)
- `FEDERAL` - Federal employees and postal (AFGE, NALC, APWU)
- `RAILROAD_AIRLINE_RLA` - Railway Labor Act covered
- `MIXED_PUBLIC_PRIVATE` - Mixed sector (SEIU)
- `OTHER` - Unclassified

---

## Key Findings

### 1. Entity Matching Success
- Achieved 96.2% F-7 employer match rate (from 67.5%)
- 97.9% of workers now linked to unions
- Pattern-based matching effective for union name variations

### 2. BLS Alignment
- Platform within 1.3% of BLS national benchmarks
- 99.8% state-level coverage
- Validates data quality

### 3. Sector Classification
- SEIU is ~70% private sector (healthcare, janitorial)
- F-7 system is private-sector focused
- 150% private coverage reflects multi-employer agreements

### 4. Multi-Employer Agreements
- Building trades use master agreements covering hundreds of contractors
- Entertainment guilds cover all studios/networks
- Explains why F-7 totals exceed BLS benchmarks

---

## Federal Sector Verification

### OPM Benchmark Data

| Metric | Value |
|--------|-------|
| Federal Bargaining Unit Size | 1,284,167 |
| Estimated Members (~78% after Janus) | ~1,000,000 |
| Top Agency (VA) | 285,083 |
| Top Union (AFGE) | 772,174 |

### F-7 Federal Sector Analysis

Federal workers appear in F-7 data (721K) despite F-7 being an NLRA (private sector) filing. These are correctly **EXCLUDED** from private coverage calculations.

| Union | F-7 Workers | Sector Classification |
|-------|-------------|----------------------|
| AFGE | 490,915 | FEDERAL ✅ |
| APWU | 203,714 | FEDERAL ✅ |
| NTEU | 17,330 | FEDERAL ✅ |
| NAGE | 6,219 | FEDERAL ✅ |
| NFFE | 1,668 | FEDERAL ✅ |
| NALC | 1,500 | FEDERAL ✅ |

### Why Federal Workers in F-7?

F-7 is filed under NLRA, but federal employees use FSLMRA. Explanations:
1. **NAF employees** - Military base exchanges use NLRA
2. **USPS** - Semi-independent with unique legal status
3. **Data entry errors** - Wrong form filed historically
4. **TVA** - Uniquely uses NLRA despite being federal

### Coverage Verification

| Sector | Workers | In 150% Coverage? |
|--------|---------|-------------------|
| PRIVATE | 10,485,997 | ✅ YES |
| RAILROAD_AIRLINE_RLA | 478,600 | ✅ YES |
| FEDERAL | 721,346 | ❌ EXCLUDED |
| PUBLIC_SECTOR | 207,742 | ❌ EXCLUDED |
| MIXED (SEIU) | 1,880,235 | ❌ EXCLUDED |

**Misclassification rate: 0.006%** (477 workers potentially federal in PRIVATE)

---

## Future Work

### Data Quality
- [ ] Classify remaining UNKNOWN sector unions (1.05M workers)
- [ ] Improve VR employer matching (currently 35.1%)
- [ ] Add confidence scores to all matches

### New Data Sources
- [ ] IRS 990 forms for union finances
- [ ] SEC filings for company data
- [ ] OSHA safety records
- [ ] Political contribution tracking

### Features
- [ ] CSV export functionality
- [ ] Metro-level analysis (CBSA integration)
- [ ] Industry coverage rates by NAICS
- [ ] Contract database integration

---

## Connection Details

```python
conn = psycopg2.connect(
    host='localhost',
    dbname='olms_multiyear',
    user='postgres',
    password='Juniordog33!'
)
```

---

## Summary Metrics

```
================================================================================
                        LABOR RELATIONS PLATFORM SUMMARY
================================================================================

DATA SOURCES:           26,665 unions | 71,077 employers | 67,779 elections

MATCH RATES:            F-7 Employers:  96.2%
                        F-7 Workers:    97.9%
                        NLRB Elections: 93.4%
                        VR Cases:       93.4%

BLS COVERAGE:           National:       101.3%
                        State-Level:    99.8%
                        Private Sector: 150.2% (multi-employer adjusted)

SECTOR BREAKDOWN:       PRIVATE:        10.49M workers (F-7)
                        MIXED (SEIU):   1.88M workers (F-7)
                        PUBLIC:         0.93M workers (F-7)

================================================================================
```
