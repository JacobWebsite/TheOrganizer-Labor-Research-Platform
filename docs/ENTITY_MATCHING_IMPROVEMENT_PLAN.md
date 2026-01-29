# Entity Matching Improvement Plan - COMPLETED

## Executive Summary

**Project Status: ✅ COMPLETE**

This document tracks the systematic improvement of entity matching across the labor relations platform. All checkpoints have been successfully executed.

### Final Results

| Dataset | Metric | Starting | Final | Improvement |
|---------|--------|----------|-------|-------------|
| **F-7 Employers** | Union Match Rate | 67.5% | **96.2%** | **+28.7%** |
| **F-7 Employers** | Worker Coverage | ~54% | **97.9%** | **+44%** |
| **NLRB Elections** | Union Match Rate | ~89% | **93.4%** | **+4.4%** |
| **VR Cases** | Union Match Rate | 86.6% | **93.4%** | **+6.8%** |
| **VR Cases** | Employer Match Rate | 31.0% | **35.1%** | **+4.1%** |

---

## Checkpoint Progress

### Checkpoint A: SAG-AFTRA Standardization ✅
- **Status**: Complete
- **Employers Added**: 108
- **Workers Linked**: 1,652,904
- **Method**: Pattern match on "SAG-AFTRA", "Screen Actors" → f_num=391

### Checkpoint B: Carpenters Regional Councils ✅
- **Status**: Complete
- **Employers Added**: 838
- **Workers Linked**: 508,796
- **Method**: Pattern match on "Carpenter", "UBC", regional councils → f_num=85

### Checkpoint C: SEIU Local Normalization ✅
- **Status**: Complete
- **Employers Added**: 5,225
- **Workers Linked**: 1,243,884
- **Method**: Pattern match on "SEIU", "Service Employees", "1199" variants → f_num=137

### Checkpoint D: Building Trades & Major Unions ✅
- **Status**: Complete
- **Employers Added**: 10,463
- **Workers Linked**: 3,222,789
- **Unions Mapped**: 18 major unions including:
  - United Association (Plumbers) → f_num=111
  - Bricklayers (BAC) → f_num=34
  - Teamsters (IBT) → f_num=93
  - IATSE → f_num=172
  - Ironworkers → f_num=52
  - Sheet Metal (SMART) → f_num=73
  - UAW → f_num=149
  - Directors Guild → f_num=18
  - Machinists (IAM) → f_num=107
  - UFCW → f_num=76
  - UNITE HERE → f_num=130
  - IBEW → f_num=68
  - Laborers (LIUNA) → f_num=80
  - Operating Engineers (IUOE) → f_num=94
  - Steelworkers (USW) → f_num=117

### Checkpoint E: Remaining Major Unions ✅
- **Status**: Complete
- **Employers Added**: 1,991
- **Workers Linked**: 1,433,337
- **Unions Mapped**: 22 unions including:
  - CWA → f_num=188
  - National Nurses United → f_num=544309
  - American Nurses Association → f_num=233
  - AFGE → f_num=500002
  - APWU → f_num=510
  - AFT → f_num=12
  - AFSCME → f_num=289
  - Actors Equity (AAA) → f_num=48
  - Writers Guild → f_num=78
  - Musicians (AFM) → f_num=207
  - NTEU → f_num=500003
  - Boilermakers → f_num=74

### Checkpoint F: Final Cleanup ✅
- **Status**: Complete
- **Employers Added**: 1,798
- **Workers Linked**: 442,300
- **Patterns Addressed**:
  - AFL-CIO federation patterns → f_num=106
  - Trades Councils → f_num=106
  - Workers United → f_num=544070
  - RWDSU → f_num=71
  - Seafarers → f_num=14
  - District Councils mapped to parent unions

### Checkpoint G: NLRB & VR Matching ✅
- **Status**: Complete
- **NLRB Tallies Updated**: 1,282
- **VR Union Matches Added**: 114
- **VR Employer Matches Added**: 69

---

## Cumulative F-7 Progress

| Checkpoint | Match Rate | Employers Matched | Added |
|------------|------------|-------------------|-------|
| Starting | 67.5% | 47,951 | - |
| A (SAG-AFTRA) | 67.6% | 48,059 | +108 |
| B (Carpenters) | 68.8% | 48,897 | +838 |
| C (SEIU) | 76.1% | 54,122 | +5,225 |
| D (Building Trades) | 90.9% | 64,585 | +10,463 |
| E (Remaining) | 93.7% | 66,576 | +1,991 |
| **F (Final)** | **96.2%** | **68,374** | **+1,798** |

**Total F-7 Improvement: +20,423 employers (+42.6%)**

---

## Remaining Unmatched

### F-7 Employers (2,703 remaining, 328K workers)
- Small independent/company unions
- Abbreviated names without context (SMART 20, BAC 1)
- Niche professional associations
- Data quality issues (misspellings, partial names)

### NLRB Elections (2,297 remaining of 34,683 union entries)
- Local-specific naming variations
- Misspellings and typos
- Independent unions not in OLMS

### VR Cases
- Union: 111 remaining (6.6%)
- Employer: 1,091 remaining (64.9%) - expected for newly organized workplaces

---

## Scripts Created

All scripts saved in `C:\Users\jakew\Downloads\labor-data-project\`:

| Script | Purpose |
|--------|---------|
| checkpoint_a1.py - checkpoint_a3.py | SAG-AFTRA analysis, fix, verify |
| checkpoint_b1.py - checkpoint_b3.py | Carpenters analysis, fix, verify |
| checkpoint_c1.py - checkpoint_c3.py | SEIU analysis, fix, verify |
| checkpoint_d1.py - checkpoint_d3.py | Building trades analysis, fix, verify |
| checkpoint_e1.py - checkpoint_e3.py | Remaining unions analysis, fix, verify |
| checkpoint_f1.py - checkpoint_f3.py | Final cleanup analysis, fix, verify |
| checkpoint_g1.py - checkpoint_g6.py | NLRB/VR matching improvements |
| checkpoint_g_final.py | Final summary |

---

## Key Union f_num Mappings

| Union | f_num | Affiliation |
|-------|-------|-------------|
| Teamsters | 93 | IBT |
| SEIU | 137 | SEIU |
| Operating Engineers | 94 | IUOE |
| Carpenters | 85 | CJA |
| Plumbers/Pipefitters | 111 | PPF/UA |
| UFCW | 76 | UFCW |
| Steelworkers | 117 | USW |
| IBEW | 68 | IBEW |
| UAW | 149 | UAW |
| Machinists | 107 | IAM |
| CWA | 188 | CWA |
| AFSCME | 289 | AFSCME |
| AFT | 12 | AFT |
| UNITE HERE | 130 | UNITHE |
| Laborers | 80 | LIUNA |
| Bricklayers | 34 | BAC |
| Painters | 35 | PAT/IUPAT |
| Sheet Metal/SMART | 73 | SMART |
| Ironworkers | 52 | BSOIW |
| Boilermakers | 74 | BBF |
| NNU | 544309 | NNU |
| Workers United | 544070 | WU |
| AFGE | 500002 | AFGE |
| SAG-AFTRA | 391 | SAG |
| IATSE | 172 | IATSE |
| Directors Guild | 18 | DGA |
| Actors Equity/AAA | 48 | AAA |
| AFL-CIO | 106 | AFL-CIO |

---

## Completion Date
January 25, 2026

## Next Steps
1. Create SQL views for improved data access
2. Run BLS coverage calculations
3. Update platform UI to reflect new matching
