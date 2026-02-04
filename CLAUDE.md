# Labor Relations Research Platform - Claude Context

## Quick Reference
**Last Updated:** February 2026

### Database Connection
```python
import psycopg2
conn = psycopg2.connect(
    host='localhost',
    dbname='olms_multiyear',
    user='postgres',
    password='Juniordog33!'
)
```

### Current Platform Status

| Metric | Value | Benchmark | Coverage |
|--------|-------|-----------|----------|
| Total Members | 14.5M | 14.3M (BLS) | 101.4% |
| Private Sector | 6.65M | 7.2M | 92% |
| Federal Sector | 1.28M | 1.1M | 116% |
| State/Local Public | 6.9M | 7.0M (EPI) | 98.3% |
| States Reconciled | 50/51 | - | 98% |

---

## Database Schema

### Core Tables
| Table | Records | Description |
|-------|---------|-------------|
| `unions_master` | 26,665 | OLMS union filings (has local_number field) |
| `f7_employers_deduped` | 63,118 | Private sector employers |
| `nlrb_elections` | 33,096 | NLRB election records |
| `nlrb_participants` | 30,399 | Union petitioners (95.7% matched to OLMS) |
| `lm_data` | 2.6M+ | Historical filings (2010-2024) |
| `epi_state_benchmarks` | 51 | State union benchmarks |
| `manual_employers` | 431 | State-level public sector |

### Public Sector Tables
| Table | Records | Description |
|-------|---------|-------------|
| `ps_parent_unions` | 24 | International unions (AFSCME, NEA, etc.) |
| `ps_union_locals` | 1,520 | Local unions, councils, chapters |
| `ps_employers` | 7,987 | Public employers by type |
| `ps_bargaining_units` | 438 | Union-employer relationships |

### OSHA Tables
| Table | Records | Description |
|-------|---------|-------------|
| `osha_establishments` | 1,007,217 | OSHA-covered workplaces |
| `osha_violations_detail` | 2,245,020 | Violation records ($3.52B penalties) |
| `osha_f7_matches` | 79,981 | Linkages to F-7 employers (44.6% match rate) |
| `v_osha_organizing_targets` | - | Organizing target view |

### Unified Employer Tables (NEW)
| Table | Records | Description |
|-------|---------|-------------|
| `unified_employers_osha` | 100,768 | All employer sources combined |
| `osha_unified_matches` | 42,812 | OSHA matches to unified employers |

**Unified Employers by Source:**
| Source | Count | Description |
|--------|-------|-------------|
| F7 | 63,118 | F-7 employers (private sector CBAs) |
| NLRB | 28,839 | NLRB participants not in F-7 |
| PUBLIC | 7,987 | Public sector employers |
| VR | 824 | Voluntary recognition not in F-7 |

**OSHA Matches by Source:**
| Source | Establishments | Employers |
|--------|---------------|-----------|
| F7 | 38,024 | 13,400 |
| NLRB | 4,607 | 2,306 |
| VR | 94 | 31 |
| PUBLIC | 87 | 43 |
| **Total** | **42,812** | **15,780** |

86% of matches (36,814) have a union connection via `union_fnum`.

### Contract/Target Tables (AFSCME NY)
| Table | Records | Description |
|-------|---------|-------------|
| `ny_state_contracts` | 51,500 | NY State contracts (Open Book NY) |
| `nyc_contracts` | 49,767 | NYC contracts (Open Data API) |
| `employers_990` | 5,942 | IRS 990 nonprofit employers |
| `organizing_targets` | 5,428 | Prioritized organizing targets |

### Geography Tables
| Table | Records | Description |
|-------|---------|-------------|
| `zip_geography` | 39,366 | ZIP to City/County/CBSA mapping |
| `cbsa_reference` | 937 | Metro area definitions |

### NYC Employer Violations Tables
Source: [NYC Comptroller Employer Violations Dashboard](https://comptroller.nyc.gov/services/for-the-public/employer-violations-dashboard/)

| Table | Records | Description |
|-------|---------|-------------|
| `nyc_wage_theft_nys` | 3,281 | NYS DOL wage theft cases |
| `nyc_wage_theft_usdol` | 431 | Federal DOL wage theft ($12.2M back wages) |
| `nyc_wage_theft_litigation` | 54 | Court settlements ($457M total) |
| `nyc_ulp_closed` | 260 | Closed NLRB ULP cases with violation counts |
| `nyc_ulp_open` | 660 | Open NLRB ULP cases |
| `nyc_local_labor_laws` | 568 | PSSL, Fair Workweek violations ($52M recovered) |
| `nyc_discrimination` | 111 | Discrimination/harassment settlements |
| `nyc_prevailing_wage` | 46 | Public works underpayment cases |
| `nyc_debarment_list` | 210 | NYS debarred employers |
| `nyc_osha_violations` | 3,454 | NYC-specific OSHA violations ($12.9M penalties) |
| `v_nyc_employer_violations_summary` | - | Aggregated view of repeat offenders |

**Key Fields by Table:**
- `nyc_wage_theft_nys`: employer_name, wages_owed, num_claimants, city
- `nyc_wage_theft_usdol`: trade_name, naics_code, backwages_amount, employees_violated
- `nyc_ulp_*`: employer, case_number, violations_8a1/8a3/8a5, union_filing
- `nyc_local_labor_laws`: employer_name, pssl_flag, fww_flag, total_recovered, covered_workers

---

## API Endpoints (localhost:8001)

### Core
- `GET /api/health` - Health check
- `GET /api/summary` - Platform summary with coverage %
- `GET /api/stats/breakdown` - Detailed statistics breakdown

### Lookups (Dropdowns)
- `GET /api/lookups/sectors` - Union sectors (Private, Federal, Public, RLA)
- `GET /api/lookups/affiliations` - National union affiliations
- `GET /api/lookups/states` - States with employer counts
- `GET /api/lookups/naics-sectors` - NAICS sector codes
- `GET /api/lookups/metros` - Metro areas
- `GET /api/lookups/cities` - Cities for filters

### Employers
- `GET /api/employers/search` - Search by name, state, NAICS, city (returns naics_detailed, naics_source)
- `GET /api/employers/fuzzy-search` - Fuzzy name matching search (returns naics_detailed)
- `GET /api/employers/normalized-search` - Normalized name search (returns naics_detailed)
- `GET /api/employers/{employer_id}` - Employer detail
- `GET /api/employers/{employer_id}/similar` - Similar employers
- `GET /api/employers/{employer_id}/osha` - OSHA data for employer
- `GET /api/employers/{employer_id}/nlrb` - NLRB elections for employer
- `GET /api/employers/cities` - City list for dropdown
- `GET /api/employers/by-naics-detailed/{naics_code}` - Detailed NAICS search

### Unions
- `GET /api/unions/search` - Search unions
- `GET /api/unions/{f_num}` - Union detail with top employers
- `GET /api/unions/{f_num}/employers` - All employers for union
- `GET /api/unions/locals/{affiliation}` - Locals by affiliation
- `GET /api/unions/national` - List national/international unions
- `GET /api/unions/national/{aff_abbr}` - National union detail
- `GET /api/unions/types` - Union designation types
- `GET /api/unions/cities` - Cities with union presence

### NLRB
- `GET /api/nlrb/summary` - NLRB statistics summary
- `GET /api/nlrb/elections/search` - Election search (use for recent elections)
- `GET /api/nlrb/elections/map` - Elections with coordinates for mapping
- `GET /api/nlrb/elections/by-year` - Elections grouped by year
- `GET /api/nlrb/elections/by-state` - Elections grouped by state
- `GET /api/nlrb/elections/by-affiliation` - Elections grouped by union affiliation
- `GET /api/nlrb/election/{case_number}` - Single election detail
- `GET /api/nlrb/ulp/search` - ULP case search
- `GET /api/nlrb/ulp/by-section` - ULP cases by NLRA section

### OSHA
- `GET /api/osha/summary` - OSHA summary statistics
- `GET /api/osha/establishments/search` - Establishment search
- `GET /api/osha/establishments/{establishment_id}` - Establishment detail
- `GET /api/osha/by-state` - OSHA stats by state
- `GET /api/osha/high-severity` - High severity violations
- `GET /api/osha/organizing-targets` - High-violation organizing targets
- `GET /api/osha/employer-safety/{f7_employer_id}` - Safety record for F-7 employer
- `GET /api/osha/unified-matches` - OSHA matches from unified employers

### Voluntary Recognition
- `GET /api/vr/stats/summary` - VR statistics summary
- `GET /api/vr/stats/by-year` - VR cases by year
- `GET /api/vr/stats/by-state` - VR cases by state
- `GET /api/vr/stats/by-affiliation` - VR cases by union
- `GET /api/vr/search` - Search VR cases
- `GET /api/vr/map` - VR cases with coordinates
- `GET /api/vr/new-employers` - Employers new from VR (not in F-7)
- `GET /api/vr/pipeline` - VR pipeline analysis
- `GET /api/vr/{case_number}` - Single VR case detail

### Public Sector
- `GET /api/public-sector/stats` - Summary statistics
- `GET /api/public-sector/parent-unions` - List parent unions
- `GET /api/public-sector/locals` - Search locals
- `GET /api/public-sector/employers` - Search employers
- `GET /api/public-sector/employer-types` - Employer type list
- `GET /api/public-sector/benchmarks` - EPI benchmarks

### Organizing
- `GET /api/organizing/summary` - Organizing activity summary
- `GET /api/organizing/by-state` - Organizing stats by state
- `GET /api/organizing/scorecard` - 6-factor OSHA scorecard search
- `GET /api/organizing/scorecard/{estab_id}` - Scorecard detail for establishment
- `GET /api/osha/organizing-targets` - OSHA-based organizing targets (high violations)

### Unified Employers (NEW)
- `GET /api/employers/unified/stats` - Stats by source type (F7, NLRB, VR, PUBLIC)
- `GET /api/employers/unified/search` - Search all unified employers
- `GET /api/employers/unified/{id}` - Employer detail with OSHA matches
- `GET /api/employers/unified/sources` - List source types with counts
- `GET /api/osha/unified-matches` - Search OSHA matches from unified employers

### Geographic
- `GET /api/lookups/metros` - List metro areas with density
- `GET /api/metros/{cbsa_code}/stats` - Metro stats with density
- `GET /api/lookups/states` - States with employer counts
- `GET /api/lookups/cities` - Cities for dropdown filters

### Trends
- `GET /api/trends/national` - National membership 2010-2024
- `GET /api/trends/by-state/{state}` - State trends
- `GET /api/trends/states/summary` - All states summary
- `GET /api/trends/by-affiliation/{aff_abbr}` - Affiliation trends
- `GET /api/trends/affiliations/summary` - All affiliations summary
- `GET /api/trends/elections` - Election win rates by year
- `GET /api/trends/elections/by-affiliation/{aff_abbr}` - Election trends by union
- `GET /api/trends/sectors` - Sector trends

### Multi-Employer
- `GET /api/multi-employer/stats` - Deduplication statistics
- `GET /api/multi-employer/groups` - Multi-employer agreement groups
- `GET /api/employer/{employer_id}/agreement` - Agreement details for employer
- `GET /api/corporate/family/{employer_id}` - Corporate family relationships

### Projections (BLS)
- `GET /api/projections/summary` - BLS projections summary
- `GET /api/projections/industry/{naics_code}` - Industry projections
- `GET /api/projections/occupations/{naics_code}` - Occupation projections
- `GET /api/projections/naics/{naics_2digit}` - 2-digit NAICS projections
- `GET /api/projections/industries/{sector}` - All sub-industries in a sector
- `GET /api/projections/matrix/{code}` - Detailed industry by BLS matrix code
- `GET /api/projections/matrix/{code}/occupations` - Occupation breakdown for industry
- `GET /api/projections/search` - Search/filter industry projections
- `GET /api/projections/top` - Top growing industries
- `GET /api/employer/{employer_id}/projections` - Projections for employer
- `GET /api/density/naics/{naics_2digit}` - Union density by NAICS
- `GET /api/density/all` - All density data

### NAICS
- `GET /api/naics/stats` - NAICS statistics

---

## Key Features (What Exists - Don't Rebuild)

### 1. Organizing Scorecard (6-factor, 0-100 points)
| Factor | Points | Description |
|--------|--------|-------------|
| Safety Violations | 0-25 | OSHA violation count, severity, recency |
| Industry Density | 0-15 | Existing union presence in NAICS sector |
| Geographic Presence | 0-15 | Union activity in state |
| Establishment Size | 0-15 | Sweet spot 100-500 employees |
| NLRB Momentum | 0-15 | Recent organizing activity nearby |
| Government Contracts | 0-15 | NY State & NYC contract funding |

**Government Contracts Scoring:**
- $5M+ funding: 10 base points
- $1M+ funding: 7 base points
- $100K+ funding: 4 base points
- Any funding: 2 base points
- Bonus: +5 for 5+ contracts, +3 for 2+ contracts

### 2. AFSCME NY Organizing Targets
- **5,428 targets** identified from 990 + contract data
- **$18.35B** total government funding
- **47 TOP tier**, 414 HIGH tier targets
- Priority scoring based on employee count, funding, sector alignment

**Priority Tiers:**
- TOP (70+): Immediate action recommended
- HIGH (50-69): Strong potential
- MEDIUM (30-49): Worth investigating
- LOW (<30): Lower priority

### 3. Geographic Analysis
- MSA/Metro area analysis with union density %
- City-level employer search
- CBSA mapping (40.8% of employers mapped)
- Metro dropdown filter in UI

### 4. Membership Deduplication
- Raw 70.1M → Deduplicated 14.5M
- Matches BLS within 1.5%
- Handles hierarchy (federation → international → local)
- Canadian member exclusion, retiree adjustment

### 5. Historical Trends (2010-2024)
- 16 years of OLMS LM filings
- National, state, affiliation breakdowns
- Election win rate trends
- Chart.js visualizations in Trends tab

### 6. Public Sector Coverage
- 98.3% of EPI benchmark covered
- 50 of 51 states within ±15%
- NEA/AFT state affiliate research
- Form 990 revenue validation

### 7. Industry Outlook (Employer Detail)
- Shows BLS 2024-2034 employment projections in employer detail view
- Uses detailed NAICS (6-digit from OSHA) when available via `/api/projections/matrix/{code}`
- Falls back to sector-level projections when detailed unavailable
- Expandable occupation breakdown showing top jobs with growth rates
- Fields: `naics_detailed`, `naics_source`, `naics_confidence` on employer search results

---

## Frontend Interfaces

| File | Purpose |
|------|---------|
| **`files/organizer_v5.html`** | **PRIMARY FRONTEND - All new features go here** |
| `frontend/labor_search_v6.html` | Legacy research interface (deprecated for new work) |

**IMPORTANT:** All frontend and backend development should target the Organizer interface (`files/organizer_v5.html`). This is the polished, production-ready UI focused on organizing workflows.

---

## Key Views

```sql
-- Deduplicated membership
SELECT * FROM v_union_members_deduplicated;

-- State public sector comparison
SELECT * FROM v_state_epi_comparison;

-- Union name lookup
SELECT * FROM v_union_name_lookup WHERE confidence = 'HIGH';

-- Public sector by state
SELECT state, SUM(members) FROM ps_union_locals GROUP BY state;

-- OSHA organizing targets
SELECT * FROM v_osha_organizing_targets WHERE score >= 50;
```

---

## Reference Documentation

| Document | Purpose |
|----------|---------|
| `LABOR_PLATFORM_ROADMAP_v10.md` | Current roadmap, future phases |
| `docs/METHODOLOGY_SUMMARY_v8.md` | Complete methodology reference |
| `EPI_BENCHMARK_METHODOLOGY.md` | EPI benchmark explanation |
| `PUBLIC_SECTOR_SCHEMA_DOCS.md` | Public sector schema reference |
| `docs/AFSCME_NY_CASE_STUDY.md` | Organizing targets feature docs |
| `docs/FORM_990_FINAL_RESULTS.md` | 990 methodology results |
| `docs/EXTENDED_ROADMAP.md` | Future checkpoints H-O |

---

## Coverage Acceptance Criteria

| Status | Criteria |
|--------|----------|
| COMPLETE | Within ±15% of EPI benchmark |
| NEEDS REVIEW | 15-25% variance |
| INCOMPLETE | >25% variance without documentation |

---

## Starting the Platform

```cmd
cd C:\Users\jakew\Downloads\labor-data-project
py -m uvicorn api.labor_api_v6:app --reload --port 8001
```

Open `files/organizer_v5.html` in browser.
API docs: http://localhost:8001/docs

---

## Session Log

### 2025-02-03
**Tasks:** AFSCME NY locals reconciliation and duplicate verification
**Files Modified:**
- `CLAUDE.md` - Added session log
- `scripts/analyze_afscme_ny.py` - Created AFSCME NY analysis script
- `scripts/verify_dc37_duplicates.py` - Created DC37 duplicate verification script

**Key Findings:**
- **AFSCME NY deduplicated total: 339,990 members**
  - CSEA (Local 1000): 201,013
  - DC37 (Local 37): 121,845
  - Other NY locals (74): 17,132
- **Duplicates identified and excluded:**
  - CSEA Regions 1-6: 189,770 (already in Local 1000)
  - DC37 Locals (14): 16,587 (already in Local 37)
- **Designation codes:** DC = District Council (aggregates), LU = Local Union, R = Region
- **Data source:** LM-2 filings (DOL), not Form 990 (IRS) - unions file LM-2

**Key Decisions:**
- DC (District Council) designations report aggregate membership including their locals
- When locals also file LM reports, members are double-counted if added naively
- CSEA 990 data doesn't exist - unions file LM-2 with DOL instead

**Status:** Completed
