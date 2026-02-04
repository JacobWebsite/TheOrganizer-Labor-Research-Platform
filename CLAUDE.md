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

### Mergent Employer Tables (Sector Scorecards)
| Table | Records | Description |
|-------|---------|-------------|
| `mergent_employers` | 14,240 | Mergent Intellect employer data (11 sectors) |
| `ny_990_filers` | 37,480 | IRS Form 990 NY nonprofit filers (2022-2024) |

**Sectors in mergent_employers:**
| Sector | Employers | Unionized | Targets | Employees |
|--------|-----------|-----------|---------|-----------|
| CIVIC_ORGANIZATIONS | 3,339 | 31 | 3,308 | 68,864 |
| BUILDING_SERVICES | 2,692 | 20 | 2,672 | 197,485 |
| EDUCATION | 2,487 | 62 | 2,425 | 239,212 |
| SOCIAL_SERVICES | 1,520 | 24 | 1,496 | 65,672 |
| BROADCASTING | 1,371 | 5 | 1,366 | 82,536 |
| PUBLISHING | 768 | 5 | 763 | 37,462 |
| WASTE_MGMT | 717 | 4 | 713 | 13,998 |
| GOVERNMENT | 525 | 35 | 490 | 48,056 |
| REPAIR_SERVICES | 394 | 1 | 393 | 11,975 |
| MUSEUMS | 243 | 25 | 218 | 12,659 |
| INFORMATION | 184 | 9 | 175 | 7,352 |

**Mergent Employers Columns (Key):**
- `duns` - D-U-N-S number (unique ID)
- `ein` - IRS Employer ID (55% coverage)
- `company_name`, `city`, `state`, `zip`, `county`
- `employees_site`, `sales_amount`, `naics_primary`
- `sector_category` - One of 11 sectors above
- `has_union` - Boolean flag (F-7, NLRB win, or OSHA union status)
- `organizing_score` - Composite score (0-52 for non-union targets)
- `score_priority` - Tier: TOP, HIGH, MEDIUM, LOW

**Match Columns:**
- `ny990_id`, `ny990_employees`, `ny990_revenue`, `ny990_match_method`
- `matched_f7_employer_id`, `f7_union_name`, `f7_union_fnum`
- `osha_establishment_id`, `osha_violation_count`, `osha_total_penalties`
- `nlrb_case_number`, `nlrb_election_date`, `nlrb_union_won`
- `whd_violation_count`, `whd_backwages`, `whd_employees_violated`

**Score Columns:**
- `score_geographic` (removed - set to 0), `score_size` (0-5), `score_industry_density` (0-10 BLS)
- `score_nlrb_momentum` (0-10 by NAICS), `score_osha_violations` (0-4), `score_govt_contracts` (0-15)
- `score_labor_violations` (0-10 NYC Comptroller), `sibling_union_bonus` (0-8)
- Max score: 62 pts | Tiers: TOP ≥30, HIGH ≥25, MEDIUM ≥15, LOW <15

**Labor Violation Columns:**
- `nyc_wage_theft_cases`, `nyc_wage_theft_amount` - NYS/US DOL wage theft
- `nyc_ulp_cases` - NLRB ULP cases (open + closed)
- `nyc_local_law_cases`, `nyc_local_law_amount` - PSSL, Fair Workweek violations
- `nyc_debarred` - Boolean, on NYS debarment list

### Sector Organizing Views
For each sector (e.g., `education`, `social_services`, `building_services`):
| View Pattern | Description |
|--------------|-------------|
| `v_{sector}_organizing_targets` | Non-union targets ranked by organizing score |
| `v_{sector}_target_stats` | Summary stats by priority tier |
| `v_{sector}_unionized` | Already-unionized employers for reference |

**Available Sectors:**
`civic_organizations`, `building_services`, `education`, `social_services`, `broadcasting`, `publishing`, `waste_mgmt`, `government`, `repair_services`, `museums`, `information`

**Priority Tiers:**
| Tier | Score Range |
|------|-------------|
| TOP | 40+ |
| HIGH | 30-39 |
| MEDIUM | 20-29 |
| LOW | <20 |

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

### Museum Organizing Targets (Legacy)
- `GET /api/museums/summary` - Sector overview (targets + unionized counts, density %)
- `GET /api/museums/targets` - Search targets (tier, city, employees, score filters)
- `GET /api/museums/targets/stats` - Summary by tier (HIGH/MEDIUM/LOW)
- `GET /api/museums/targets/cities` - Cities with target counts for dropdown
- `GET /api/museums/targets/{target_id}` - Target detail with nearby unionized museums
- `GET /api/museums/unionized` - Reference list of unionized museums

### Sector Organizing Targets (Generic - 11 Sectors)
Supports all sectors: `civic_organizations`, `building_services`, `education`, `social_services`, `broadcasting`, `publishing`, `waste_mgmt`, `government`, `repair_services`, `museums`, `information`

- `GET /api/sectors/list` - List all sectors with target/unionized counts
- `GET /api/sectors/{sector}/summary` - Sector overview with tier breakdown
- `GET /api/sectors/{sector}/targets` - Search targets (tier, city, employees, score filters)
- `GET /api/sectors/{sector}/targets/stats` - Summary by priority tier
- `GET /api/sectors/{sector}/targets/{target_id}` - Target detail with nearby unionized
- `GET /api/sectors/{sector}/targets/cities` - Cities with targets for dropdown
- `GET /api/sectors/{sector}/unionized` - Reference list of unionized employers

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

### 1. OSHA Organizing Scorecard (6-factor, 0-100 points)
*For OSHA establishments via `/api/organizing/scorecard` - separate from Mergent sector scorecard*

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

### 7. Multi-Sector Organizing Scorecard (Mergent-based)
Integrated data pipeline: Mergent Intellect → 990 matching → F-7/NLRB/OSHA matching → Contract matching → Scoring

**Data Sources Combined:**
- Mergent Intellect: 14,240 NY employers across 11 sectors
- IRS Form 990: ~50% matched - employee counts, revenue validation
- F-7 Employers: 221 matched (existing union contracts)
- NLRB Elections: Win/loss data matched
- OSHA: Violation data matched
- NY State Contracts: 1,059 matched ($8.8B via normalized name)
- NYC Contracts: 554 matched ($46B via normalized name)

**Scoring Components (62 pts max for non-union targets):**
| Factor | Max | Criteria |
|--------|-----|----------|
| Size | 5 | 100-500 emp=5, 50-99=4, 25-49=3 |
| Industry Density | 10 | BLS NAICS density: 15%+=10, 10-15%=8, 5-10%=6, 2-5%=4, <2%=2 |
| NLRB Momentum | 10 | Wins in same 2-digit NAICS: 10+=10, 5-9=8, 3-4=6, 1-2=4, 0=0 |
| OSHA Violations | 4 | 5+ AND recent=4, 3+ OR recent=3 |
| Govt Contracts | 15 | $5M+=15, $1M+=12, $500K+=10, $100K+=7, any=4 |
| Labor Violations | 10 | NYC Comptroller data (wage theft, ULP, PSSL/FWW, debarment) |
| Sibling Bonus | 8 | Parent/sibling union in same family |

**Labor Violations Scoring (0-10 pts):**
- Wage theft $100K+ = 4 pts, $50K+ = 3 pts, $10K+ = 2 pts, any = 1 pt
- ULP cases: 3+ = 3 pts, 2 = 2 pts, 1 = 1 pt
- Local labor law violations (PSSL/FWW): 2+ = 2 pts, 1 = 1 pt
- Debarred employer = 1 pt

**Union Detection (Excludes from targets):**
- F-7 contract match → Unionized
- NLRB election win → Unionized
- OSHA union_status = 'Y' or 'A' → Unionized

**Tier Distribution (14,019 non-union targets):**
| Tier | Threshold | Count | Avg Score |
|------|-----------|-------|-----------|
| TOP | ≥30 | 173 | 31.5 |
| HIGH | ≥25 | 476 | 26.8 |
| MEDIUM | ≥15 | 3,755 | 17.9 |
| LOW | <15 | 9,615 | 10.2 |
| LOW | <15 | 9,630 | 75 (1%) | $7.5M |

**Top Targets (TOP tier, 30+ pts):**
1. NY Botanical Garden (39 pts, MUSEUMS, $15M+ contracts)
2. Niagara University (36 pts, EDUCATION, $5.8M contracts)
3. Alvin Ailey Dance Foundation (36 pts, EDUCATION, $10.9M contracts)
4. Project Renewal Inc (44 pts, SOCIAL_SERVICES, $2.4B contracts)
5. Replications Inc (35 pts, EDUCATION, $18M contracts)

**Score Reason Explanations (UI Feature):**
Each score component in the detail view shows human-readable reason text explaining why that score was assigned:
- Size: "200 employees (100-500 sweet spot)"
- Industry Density: "5-10% union density (moderate)"
- NLRB Momentum: "5-9 recent wins in industry"
- OSHA: "12 violations (recent + multiple)"
- Contracts: "$28,800,000 in contracts (≥$5M)"
- Labor Violations: "2 wage theft ($45,000), 1 ULP cases"
- Sibling Bonus: "Parent company has union (strong)"

### 8. Industry Outlook (Employer Detail)
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

-- Museum organizing targets (non-union, ranked by score)
SELECT employer_name, city, best_employee_count, total_score, priority_tier
FROM v_museum_organizing_targets WHERE priority_tier IN ('HIGH', 'MEDIUM');

-- Museum target stats by tier
SELECT * FROM v_museum_target_stats;

-- Already-unionized museums (reference)
SELECT employer_name, best_employee_count, union_name FROM v_museum_unionized;
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

### 2026-02-04 (Score Reasons)
**Tasks:** Add Score Reason Explanations to Organizing Scorecard

**Files Modified:**
- `files/organizer_v5.html` - Added score reason explanations to sector detail view

**Changes:**
1. **Modified `renderScoreRow()` function** - Added 6th `reason` parameter, displays italic gray text below progress bar
2. **Added `getScoreReason()` function** - Generates human-readable explanations for 7 score types:
   - `size`: Shows employee count and tier description (e.g., "200 employees (100-500 sweet spot)")
   - `industry_density`: Shows approximate density range from score (e.g., "5-10% union density (moderate)")
   - `nlrb`: Shows win count range (e.g., "5-9 recent wins in industry")
   - `osha`: Shows violation count (e.g., "12 violations (recent + multiple)")
   - `contracts`: Shows total contract value (e.g., "$28,800,000 in contracts (≥$5M)")
   - `labor`: Lists violation types (e.g., "2 wage theft ($45,000), 1 ULP cases")
   - `sibling`: Describes sibling union relationship (e.g., "Parent company has union (strong)")
3. **Updated `renderSectorDetail()` calls** - All 7 score rows now pass reason text

**Example Output:**
```
Size Sweet Spot          5/5
[████████████████████]
200 employees (100-500 sweet spot)
```

**Status:** Complete. Backward compatible - OSHA scorecard continues to work without reasons.

### 2026-02-04 (continued)
**Tasks:** Process Remaining Mergent Employers Through Scorecard Pipeline
**Files Modified:**
- `CLAUDE.md` - Updated documentation with 11-sector data
- `api/labor_api_v6.py` - Added generic sector API endpoints
- `scripts/load_mergent_employers.py` - Created CSV loader script
- `scripts/run_mergent_matching.py` - Created matching pipeline script
- `scripts/create_sector_views.py` - Created sector view generator

**Database Objects Created:**
- Loaded 13,997 additional employers into `mergent_employers` table
- Created 33 new views (3 per sector × 11 sectors):
  - `v_{sector}_organizing_targets` - Non-union targets
  - `v_{sector}_target_stats` - Summary by tier
  - `v_{sector}_unionized` - Unionized reference

**Key Results:**
- **14,240 total employers** in mergent_employers (up from 243)
- **11 sectors** with organizing targets
- **221 unionized** employers identified across all sectors
- **14,019 non-union targets** with organizing scores
- **28.8% 990 match rate**, 1.5% F-7 match rate, 0.6% OSHA match rate

**Sector Breakdown:**
| Sector | Total | Targets | Unionized |
|--------|-------|---------|-----------|
| CIVIC_ORGANIZATIONS | 3,339 | 3,308 | 31 |
| BUILDING_SERVICES | 2,692 | 2,672 | 20 |
| EDUCATION | 2,487 | 2,425 | 62 |
| SOCIAL_SERVICES | 1,520 | 1,496 | 24 |
| BROADCASTING | 1,371 | 1,366 | 5 |
| PUBLISHING | 768 | 763 | 5 |
| WASTE_MGMT | 717 | 713 | 4 |
| GOVERNMENT | 525 | 490 | 35 |
| REPAIR_SERVICES | 394 | 393 | 1 |
| MUSEUMS | 243 | 218 | 25 |
| INFORMATION | 184 | 175 | 9 |

**API Endpoints Added:**
- `GET /api/sectors/list` - All sectors with counts
- `GET /api/sectors/{sector}/summary` - Sector overview
- `GET /api/sectors/{sector}/targets` - Search targets
- `GET /api/sectors/{sector}/targets/stats` - Tier breakdown
- `GET /api/sectors/{sector}/targets/{id}` - Target detail
- `GET /api/sectors/{sector}/targets/cities` - City dropdown
- `GET /api/sectors/{sector}/unionized` - Unionized list

**Status:** Complete. Server restart required to activate new endpoints.

### 2026-02-04
**Tasks:** Scoring Methodology Overhaul & Contract Matching Fix

**Scoring Changes:**
1. **Removed Geographic Score** - Was 0-15 based on NYC/upstate location, now set to 0
2. **Industry Density (0-10)** - Now uses BLS NAICS union density data from `v_naics_union_density`
   - 15%+ density = 10 pts (Utilities, Transportation)
   - 10-15% = 8 pts (Education, Construction)
   - 5-10% = 6 pts (Healthcare, Manufacturing, Information)
   - 2-5% = 4 pts (Retail, Admin Services)
   - <2% = 2 pts (Finance, Professional Services)
3. **NLRB Momentum (0-10)** - Now based on recent union wins in same 2-digit NAICS
   - 10+ wins = 10 pts, 5-9 wins = 8 pts, 3-4 wins = 6 pts, 1-2 wins = 4 pts

**Tier Thresholds Adjusted:**
- TOP: ≥30 pts (was ≥40) - 164 targets, 100% have contracts
- HIGH: ≥25 pts (was ≥30) - 480 targets, 92% have contracts
- MEDIUM: ≥15 pts (was ≥20) - 3,745 targets
- LOW: <15 pts - 9,630 targets

**Contract Matching Fixed:**
- Original matching used EIN (0% coverage in contract tables)
- Fixed to use normalized name matching (`company_name_normalized` ↔ `vendor_name_normalized`)
- Results: 1,059 NY State matches ($8.8B), 554 NYC matches ($46B capped)
- Total: 1,369 employers with $54.9B in government contracts

**Labor Violations Added (NEW):**
- Added `score_labor_violations` (0-10 pts) using NYC Comptroller data
- Matched 158 employers to wage theft cases ($8.2M total)
- Matched 37 employers to ULP cases
- Matched 18 employers to local labor law violations (PSSL/FWW)
- Scoring: Wage theft amount (0-4) + ULP cases (0-3) + Local law (0-2) + Debarred (0-1)
- New max score: 62 pts (was 52)

**Files Modified:**
- `api/labor_api_v6.py` - Reordered sector endpoints (cities before target_id)
- `scripts/create_sector_views.py` - Refreshed all 33 sector views
- `scripts/match_labor_violations.py` - NEW: NYC Comptroller matching script
- `CLAUDE.md` - Updated scoring documentation

**Database Updates:**
- `mergent_employers.score_geographic` - Set to 0 for all rows
- `mergent_employers.score_industry_density` - Recalculated from BLS data
- `mergent_employers.score_nlrb_momentum` - Recalculated by 2-digit NAICS
- `mergent_employers.score_labor_violations` - NEW: NYC Comptroller violations
- `mergent_employers.nyc_wage_theft_*`, `nyc_ulp_*`, `nyc_local_law_*`, `nyc_debarred` - NEW
- `mergent_employers.organizing_score` - Recalculated totals (now includes labor violations)
- `mergent_employers.score_priority` - Updated with new tier thresholds
- All `v_{sector}_*` views recreated
- Added `employer_name_normalized` to all NYC Comptroller tables

**Frontend Changes (files/organizer_v5.html):**
- Added Union Preset dropdown (AFSCME NY, SEIU NY, UAW NY, CWA NY)
- Added Data Source dropdown (OSHA vs 11 Mergent Sectors)
- Added Tier and City filter dropdowns for sector view
- Added `renderSectorDetail()` function for sector target details
- Score breakdown bar updated for new scoring weights

**Status:** Complete. Scoring now uses BLS industry density and NAICS-based NLRB momentum.

### 2025-02-04
**Tasks:** Museum Sector Organizing Scorecard - Complete Pipeline
**Files Modified:**
- `CLAUDE.md` - Added museum scorecard documentation
- `api/labor_api_v6.py` - Added 6 museum API endpoints
- `scripts/extract_ny_990.py` - Created NY 990 extraction script

**Database Objects Created:**
- `ny_990_filers` table - 37,480 NY nonprofit 990 filers
- `mergent_employers` table - 243 NY museums with scoring columns
- `v_museum_organizing_targets` view - 218 non-union targets
- `v_museum_target_stats` view - Summary by tier
- `v_museum_unionized` view - 25 unionized museums

**Key Results:**
- **14,240 employers** loaded from Mergent Intellect (11 sectors)
- **1,369 employers** matched to government contracts ($54.9B total)
- **221 (1.6%)** identified as unionized (F-7, NLRB wins, OSHA status)
- **14,019 non-union targets** scored and ranked
- **164 TOP tier** targets (30+ pts, all with contracts)
- **Top target:** NY Botanical Garden (39 pts, $15M+ contracts)

**Status:** Multi-sector scorecard complete with BLS density and NAICS-based NLRB scoring.

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
