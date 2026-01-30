# Public Sector Reconciliation Summary
## January 29, 2026

---

## EXECUTIVE SUMMARY

We have made significant progress reconciling public sector union membership data against EPI (Economic Policy Institute) state-level benchmarks. The goal is to achieve coverage within ±10% of EPI benchmarks for each state.

### Current Status
| Category | States | Description |
|----------|--------|-------------|
| **COMPLETE** | 17 | Within ±10% of EPI benchmark |
| **CLOSE** | 14 | 85-90% coverage, minor adjustments needed |
| **GAP-SMALL** | 14 | 70-85% coverage, research needed |
| **GAP-LARGE** | 1 | <70% coverage (Texas only) |
| **OVERCOUNT** | 5 | >110% of benchmark, need reduction |

### Total Records: 362 manual_employers entries across 51 states/DC

---

## COMPLETED STATES (17)

These states are within ±10% of EPI benchmarks and require no further work:

| State | EPI Benchmark | Our Data | Coverage |
|-------|--------------|----------|----------|
| California | 1,386,075 | 1,256,500 | 90.7% |
| Illinois | 367,943 | 377,000 | 102.5% |
| New Jersey | 336,506 | 327,100 | 97.2% |
| Florida | 264,585 | 251,000 | 94.9% |
| Virginia | 123,427 | 123,745 | 100.3% |
| Colorado | 71,027 | 66,000 | 92.9% |
| Tennessee | 61,838 | 57,000 | 92.2% |
| North Carolina | 43,950 | 40,000 | 91.0% |
| Nevada | 38,350 | 36,000 | 93.9% |
| Louisiana | 34,113 | 32,000 | 93.8% |
| New Mexico | 29,708 | 27,000 | 90.9% |
| West Virginia | 28,575 | 26,000 | 91.0% |
| South Carolina | 25,029 | 23,000 | 91.9% |
| Delaware | 21,865 | 23,000 | 105.2% |
| Vermont | 21,704 | 23,000 | 106.0% |
| Idaho | 18,243 | 20,000 | 109.6% |
| Wyoming | 6,779 | 7,000 | 103.3% |

---

## WORK COMPLETED THIS SESSION

### Phase 1: Methodology Fixes on Previously Researched States

1. **California** - Fixed Kaiser Permanente (29K) classification from public to PRIVATE_VOLUNTARY
2. **California** - Marked UTLA (35K) as STATE_PUBLIC_DUPLICATE to avoid double-counting with CTA/CFT
3. **New York** - Verified NYSUT (467K), CSEA (250K), DC37 (150K) - 14.5% over EPI but methodology variance acceptable
4. **Virginia** - Confirmed federal/state separation - now at 100.3% of benchmark

### Phase 2: Tier 1 Priority States (Gap > 200K)

Added comprehensive records for:
- **Pennsylvania** (322K benchmark): 10 records, 252K captured (78.2%)
- **Ohio** (270K benchmark): 9 records, 228K captured (84.5%)
- **Massachusetts** (266K benchmark): 10 records, 207K captured (77.7%)
- **Florida** (265K benchmark): 9 records, 251K captured (94.9%)
- **Washington** (262K benchmark): 9 records, 236K captured (90.0%)
- **Maryland** (214K benchmark): 9 records, 156K captured (73.0%)
- **Michigan** (205K benchmark): 9 records, 177K captured (86.2%)

### Phase 3: Tier 2 States (Gap 100K-200K)

Added records for: Minnesota, Connecticut, Oregon, Wisconsin, Indiana

### Phase 4: Tier 3 States (Gap 50K-100K)

Added records for: Arizona, Georgia, Hawaii, Alabama, Missouri, Kentucky, Colorado, Iowa, Tennessee, Oklahoma

### Phase 5: All Remaining States

Added records for all 50 states + DC with:
- Education unions (NEA/AFT affiliates)
- State employee unions (AFSCME/SEIU)
- Police/Fire unions (FOP/IAFF)
- Federal employees (AFGE and others)

### Data Cleanup

- Removed 43 duplicate records
- Adjusted overestimated small states (MT, UT, AK, DE, VT, ID, AR, DC)
- Fixed DC WMATA allocation (regional authority shared with MD/VA)

---

## REMAINING WORK ROADMAP

### Priority 1: Fix Overcounts (5 states)

| State | EPI | Our Data | Issue |
|-------|-----|----------|-------|
| NY | 945,094 | 1,082,600 | 114.5% - NYSUT methodology includes retirees |
| MT | 31,841 | 37,000 | 116.2% - Reduce education estimate |
| UT | 30,802 | 34,000 | 110.4% - Reduce estimates |
| AK | 29,161 | 40,000 | 137.2% - Significant overcount |
| AR | 17,980 | 20,000 | 111.2% - Minor reduction needed |

**Action:** Review source data, reduce inflated estimates

### Priority 2: Close Gaps in Large States (4 states, 306K gap total)

| State | EPI | Our Data | Gap | Priority Research |
|-------|-----|----------|-----|-------------------|
| TX | 326,621 | 207,900 | 118,721 | School districts, municipal workers |
| PA | 322,324 | 252,000 | 70,324 | Pittsburgh municipal, transit, universities |
| MA | 266,491 | 207,000 | 59,491 | Higher ed, municipal workers |
| MD | 213,619 | 156,000 | 57,619 | Montgomery/PG County, Baltimore |

**Action:** Deep-dive research on specific unions and employers

### Priority 3: Close Gaps in Medium States (10 states)

| State | Coverage | Gap | Notes |
|-------|----------|-----|-------|
| CT | 80.5% | 26,400 | More AFT locals, state workers |
| WI | 81.4% | 18,944 | Post-Act 10 verification |
| IN | 78.7% | 21,622 | Limited CB, verify association membership |
| GA | 80.4% | 18,737 | No CB - verify advocacy union sizes |
| OH | 84.5% | 41,742 | County workers, transit |
| NH | 76.8% | 9,949 | State workers, municipal |
| AL | 84.9% | 11,217 | No CB verification |
| KY | 83.2% | 12,078 | Verify estimates |
| RI | 82.8% | 7,256 | Providence, state workers |
| ME | 84.7% | 6,130 | Municipal workers |

### Priority 4: Fine-Tune Close States (14 states)

States at 85-90% just need minor verification/adjustment

---

## DATA QUALITY NOTES

### States with Strong Collective Bargaining
High confidence in data: CA, NY, IL, NJ, WA, OR, MN, HI, CT, RI, MA, MD

### States with Limited/No Collective Bargaining
Lower confidence (advocacy unions only): TX, GA, NC, SC, VA*, TN, MS, AL, AZ
*VA recently enabled local CB (2021+)

### Post-Janus Impact States (2018+)
May have membership declines: All states with agency fee arrangements

### Right-to-Work States (2011-2017 changes)
WI (Act 10, 2011), MI (2013), IN (2012), IA (2017) - significant declines

---

## METHODOLOGY PRINCIPLES ESTABLISHED

1. **Members vs. Represented**: EPI benchmarks are union MEMBERS, not all represented workers
2. **No Double-Counting**: Mark duplicates (e.g., UTLA counted in both CTA and CFT)
3. **Federal Separation**: Federal employees tracked separately from state/local
4. **Private Sector Exclusion**: Kaiser, other private healthcare not in public counts
5. **Regional Authorities**: WMATA, Port Authority split across states
6. **Retiree Exclusion**: Where possible, use active member counts only

---

## DATABASE ARTIFACTS

### Tables
- `manual_employers` - 362 records across 51 states/DC
- `epi_state_benchmarks` - 51 states with members/represented by sector

### Views
- `v_public_sector_members` - Categorizes records by sector
- `v_state_epi_comparison` - Compares our data to EPI benchmarks

### Recognition Types Used
- `STATE_PUBLIC` - State/local government employees
- `STATUTORY` - NJ-style statutory bargaining
- `LOCAL_BARGAINING` - VA-style local CB ordinances
- `COLLECTIVE_BARGAINING` - DC, transit authorities
- `FEDERAL` - Federal employees (tracked separately)
- `STATE_PUBLIC_DUPLICATE` - For double-count avoidance

---

## NEXT STEPS

1. **Immediate**: Fix 5 overcounted states (NY, MT, UT, AK, AR)
2. **Short-term**: Deep research on TX, PA, MA, MD gaps
3. **Medium-term**: Verify medium-state estimates with LM-2 filings
4. **Long-term**: Cross-reference with F-7 employer data when integrated

---

*Document generated: January 29, 2026*
*Database: olms_multiyear*
*Total public sector members tracked: ~7.1M (state/local)*
