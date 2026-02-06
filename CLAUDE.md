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
| CIVIC_ORGANIZATIONS | 3,339 | 36 | 3,303 | 68,864 |
| BUILDING_SERVICES | 2,692 | 38 | 2,654 | 197,485 |
| EDUCATION | 2,487 | 75 | 2,412 | 239,212 |
| SOCIAL_SERVICES | 1,520 | 37 | 1,483 | 65,672 |
| BROADCASTING | 1,371 | 8 | 1,363 | 82,536 |
| PUBLISHING | 768 | 10 | 758 | 37,462 |
| WASTE_MGMT | 717 | 5 | 712 | 13,998 |
| GOVERNMENT | 525 | 35 | 490 | 48,056 |
| REPAIR_SERVICES | 394 | 4 | 390 | 11,975 |
| MUSEUMS | 243 | 25 | 218 | 12,659 |
| INFORMATION | 184 | 9 | 175 | 7,352 |

**Mergent Employers Columns (Key):**
- `duns` - D-U-N-S number (unique ID)
- `ein` - IRS Employer ID (55% coverage)
- `company_name`, `city`, `state`, `zip`, `county`
- `employees_site`, `sales_amount`, `naics_primary`
- `sector_category` - One of 11 sectors above
- `has_union` - Boolean flag (F-7, NLRB win, or OSHA union status)
- `organizing_score` - Composite score (0-62 for non-union targets)
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
| TOP | ≥30 |
| HIGH | 25-29 |
| MEDIUM | 15-24 |
| LOW | <15 |

### Geography Tables
| Table | Records | Description |
|-------|---------|-------------|
| `zip_geography` | 39,366 | ZIP to City/County/CBSA mapping |
| `cbsa_reference` | 937 | Metro area definitions |
| `state_sector_union_density` | 6,191 | Union density by state/sector (1978-2025) |
| `state_workforce_shares` | 51 | Public/private workforce shares by state |
| `state_govt_level_density` | 51 | Estimated fed/state/local density by state |
| `county_workforce_shares` | 3,144 | County workforce composition from ACS 2025 |
| `county_union_density_estimates` | 3,144 | Estimated density by county |

### NY Sub-County Density Tables
| Table | Records | Description |
|-------|---------|-------------|
| `ny_county_density_estimates` | 62 | NY county density (industry-weighted, auto-calibrated) |
| `ny_zip_density_estimates` | 1,826 | NY ZIP code density estimates |
| `ny_tract_density_estimates` | 5,411 | NY census tract density estimates |

**NY Density Methodology:**
- 10 private industries: Industry-weighted BLS rates × auto-calibrated multiplier (2.26x)
- Excludes edu/health and public admin from private calculation (avoids double-counting)
- Multiplier auto-derived: `12.4% (CPS target) / avg_county_expected` = 2.26x
- Public sector: Decomposed by govt level (Fed: 42.2%, State: 46.3%, Local: 63.7%)

**Key Columns:**
- `private_class_total` - For-profit + nonprofit share (0-1)
- `govt_class_total` - Federal + state + local share (0-1)
- `private_in_public_industries` - Always 0 (removed from methodology)
- `estimated_private_density` - Industry-weighted with auto-calibrated multiplier
- `estimated_public_density` - Govt-level decomposed
- `estimated_total_density` - Combined weighted density

**NY County Density Range:**
| Metric | Value |
|--------|-------|
| Min Total | 12.2% (Manhattan) |
| Max Total | 26.5% (Hamilton) |
| Avg Total | 20.2% |
| Avg Private | 12.4% (matches CPS) |

### Industry Density Tables
| Table | Records | Description |
|-------|---------|-------------|
| `bls_industry_density` | 12 | BLS 2024 union density by industry |
| `state_industry_shares` | 51 | State-level industry composition (ACS 2025) |
| `county_industry_shares` | 3,144 | County-level industry composition |
| `state_industry_density_comparison` | 51 | Expected vs actual density with climate multiplier |

**BLS Industry Density Rates (2024) - Used in Private Sector Calculation:**
| Industry | Density | Included |
|----------|---------|----------|
| Transportation/Utilities | 16.2% | Yes |
| Construction | 10.3% | Yes |
| Education/Healthcare | 8.1% | **No** (often public sector) |
| Manufacturing | 7.8% | Yes |
| Information | 6.6% | Yes |
| Wholesale Trade | 4.6% | Yes |
| Agriculture/Mining | 4.0% | Yes |
| Retail Trade | 4.0% | Yes |
| Leisure/Hospitality | 3.0% | Yes |
| Other Services | 2.7% | Yes |
| Professional Services | 2.0% | Yes |
| Finance | 1.3% | Yes |
| Public Administration | N/A | **No** (in govt density) |

**Note:** Education/Health and Public Administration are EXCLUDED from private sector industry weighting because these workers are often public employees already captured in government density estimates.

**Education/Health Exclusion Rationale:**
A hybrid approach was tested where:
- 10 industries: Apply BLS rates × state climate multiplier (industry-weighted)
- Edu/Health: Use state CPS private rate directly (no industry adjustment)

Formula tested: `Hybrid = (10_Industry_Frac × Industry_Expected × Climate_Mult) + (EduHealth_Frac × State_Private_Rate)`

**Hybrid vs Current Results (3,144 counties):**
| Metric | Current (Excl Edu/Health) | Hybrid | Difference |
|--------|---------------------------|--------|------------|
| National Avg | 5.26% | 5.19% | -0.07% |
| High Edu/Health Counties (>30%) | Lower | +0.5% to +0.8% | Minimal |
| Low Edu/Health Counties (<15%) | Higher | -1% to -2% | Minimal |

**Decision:** Keep current approach (exclude edu/health entirely). The hybrid adds complexity for negligible improvement (-0.07% difference). Current method is simpler and avoids potential double-counting.

**State Climate Multiplier:**
- Formula: `Actual_Private_Density / Expected_Private_Density`
- Expected = sum of (industry_share × BLS_industry_rate) across 10 private industries
- Interpretation: STRONG (>1.5x), ABOVE_AVERAGE (1.0-1.5x), BELOW_AVERAGE (0.5-1.0x), WEAK (<0.5x)
- Top 3: HI (2.51x), NY (2.40x), WA (2.12x)
- Bottom 3: SD (0.28x), AR (0.33x), SC (0.35x)

**County Private Density Calculation:**
```
County_Private = Σ(County_Industry_Share × BLS_Rate) × State_Climate_Multiplier
```
- Uses county's industry mix for 10 private industries (excludes edu/health, public admin)
- Renormalizes shares to sum to 1.0 before weighting
- Applies state multiplier to account for regional union culture
- Columns in `county_union_density_estimates`:
  - `industry_expected_private` - Before multiplier (from 10 industries)
  - `state_climate_multiplier` - State's union climate factor
  - `industry_adjusted_private` - Final private sector estimate

**State Sector Density:**
- Source: unionstats.com (Hirsch/Macpherson CPS data)
- Sectors: `private`, `public`, `total` (combined)
- Columns: `state`, `state_name`, `sector`, `year`, `density_pct`, `source`
- 25 states have estimated public density (small CPS sample sizes)
- View: `v_state_density_latest` - Latest density with `public_is_estimated` flag

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
- `GET /api/density/by-state` - Union density by state (private & public sectors)
- `GET /api/density/by-state/{state}/history` - Historical density for a state
- `GET /api/density/by-govt-level` - Estimated density by government level (fed/state/local) for all states
- `GET /api/density/by-govt-level/{state}` - Government-level density detail for a state
- `GET /api/density/by-county` - Estimated county density (filters: state, min/max density)
- `GET /api/density/by-county/{fips}` - Single county detail with methodology
- `GET /api/density/by-county/{fips}/industry` - County industry breakdown and density calculation
- `GET /api/density/by-state/{state}/counties` - All counties in a state
- `GET /api/density/county-summary` - National county density statistics
- `GET /api/density/industry-rates` - BLS industry union density rates (12 industries)
- `GET /api/density/state-industry-comparison` - Expected vs actual density by state with climate multiplier
- `GET /api/density/state-industry-comparison/{state}` - Single state industry breakdown
- `GET /api/density/ny/summary` - NY density summary at all geographic levels
- `GET /api/density/ny/counties` - All 62 NY county density estimates
- `GET /api/density/ny/county/{fips}` - Single NY county detail with tract stats
- `GET /api/density/ny/zips` - NY ZIP code density (1,826 ZIPs)
- `GET /api/density/ny/zip/{zip_code}` - Single NY ZIP detail
- `GET /api/density/ny/tracts` - NY census tract density (5,411 tracts)
- `GET /api/density/ny/tract/{tract_fips}` - Single NY tract detail

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
| Sibling Bonus | 8 | Same org has union elsewhere (see below) |

**Sibling Union Bonus (0-8 pts):**
Two matching methods:
1. **Parent company match**: Same `parent_duns` has a unionized location in Mergent data
2. **Name match at different address**: `company_name_normalized` matches F-7 `employer_name_aggressive` but at a different street/city

**Labor Violations Scoring (0-10 pts):**
- Wage theft $100K+ = 4 pts, $50K+ = 3 pts, $10K+ = 2 pts, any = 1 pt
- ULP cases: 3+ = 3 pts, 2 = 2 pts, 1 = 1 pt
- Local labor law violations (PSSL/FWW): 2+ = 2 pts, 1 = 1 pt
- Debarred employer = 1 pt

**Union Detection (Excludes from targets):**
- F-7 contract match → Unionized
- NLRB election win → Unionized
- OSHA union_status = 'Y' or 'A' → Unionized

**Tier Distribution (13,958 non-union targets):**
| Tier | Threshold | Count |
|------|-----------|-------|
| TOP | ≥30 | 167 |
| HIGH | ≥25 | 475 |
| MEDIUM | ≥15 | 3,735 |
| LOW | <15 | 9,581 |

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

## Unified Employer Matching Module

The `scripts/matching/` module provides consistent employer-to-employer matching across all scenarios.

### Usage

```python
from scripts.matching import MatchPipeline

# Single match
pipeline = MatchPipeline(conn, scenario="mergent_to_f7")
result = pipeline.match("ACME Hospital Inc", state="NY", city="Buffalo")

# Run scenario
stats = pipeline.run_scenario(batch_size=1000, limit=10000)
```

### CLI

```bash
# List scenarios
python -m scripts.matching run --list

# Run single scenario
python -m scripts.matching run mergent_to_f7 --limit 1000 --skip-fuzzy

# Test single match
python -m scripts.matching test mergent_to_f7 "ACME Hospital" --state NY
```

### 5-Tier Matching Pipeline

| Tier | Method | Score | Confidence | Speed |
|------|--------|-------|------------|-------|
| 1 | EIN exact | 1.0 | HIGH | Fast |
| 2 | Normalized name + state | 1.0 | HIGH | Fast |
| 3 | Address (fuzzy name + street # + city + state) | 0.4+ | HIGH | Medium |
| 4 | Aggressive name + city | 0.95 | MEDIUM | Medium |
| 5 | Trigram fuzzy + state | 0.65+ | LOW | Slow |

**Address Matching (Tier 3):**
- Uses fuzzy name similarity (>=0.4 threshold) combined with exact street number
- Catches d/b/a names, rebranding, legal entity variations at same location
- Extracts street number from messy formats like "City, ST ZIP, 123 Main St"
- Example: "THC CHICAGO AIRPORT MANAGEMENT D/B/A RENAISSANCE C" → "Renaissance Chicago O'Hare Suites Hotel" (same address: 8500 W Bryn Mawr Ave)

### Available Scenarios

| Scenario | Source | Target | Use Case |
|----------|--------|--------|----------|
| `nlrb_to_f7` | nlrb_participants | f7_employers_deduped | NLRB → F7 |
| `osha_to_f7` | osha_establishments | f7_employers_deduped | OSHA → F7 |
| `mergent_to_f7` | mergent_employers | f7_employers_deduped | Sector targets → F7 |
| `mergent_to_990` | mergent_employers | ny_990_filers | Sector → 990 |
| `mergent_to_nlrb` | mergent_employers | nlrb_participants | Sector → NLRB |
| `mergent_to_osha` | mergent_employers | osha_establishments | Sector → OSHA |
| `violations_to_mergent` | nyc_wage_theft_nys | mergent_employers | Labor violations |
| `contracts_to_990` | ny_state_contracts | employers_990 | Contracts → 990 |
| `vr_to_f7` | nlrb_voluntary_recognition | f7_employers_deduped | VR → F7 |

### Module Structure

```
scripts/matching/
  __init__.py
  config.py          # MatchConfig, SCENARIOS, tier thresholds
  normalizer.py      # Unified normalization (standard/aggressive/fuzzy)
  pipeline.py        # MatchPipeline orchestrator
  differ.py          # Diff report generation
  cli.py             # Command-line interface
  matchers/
    base.py          # MatchResult, BaseMatcher
    exact.py         # EIN, Normalized, Aggressive matchers
    address.py       # Address matcher (fuzzy name + street number)
    fuzzy.py         # Trigram pg_trgm matcher
```

---

## Data Operations

When matching records between tables/datasets, always verify the join key exists in both sources before implementing. Check for null/empty values in join columns first.

**Common gotchas:**
- Contract tables (`ny_state_contracts`, `nyc_contracts`) have NO EIN values - use `vendor_name_normalized` for matching
- `mergent_employers.ein` has ~55% coverage - not reliable for joins
- Always sample 5-10 rows from each table to verify join keys before building matching logic
- F7 uses `employer_name_aggressive` (not `employer_name_normalized`) for fuzzy matching

---

## Development Workflow

After implementing new features or UI changes, offer to start a test server so the user can verify the changes visually.

```cmd
py -m http.server 8080 --directory files
```

Then open: http://localhost:8080/organizer_v5.html

---

## Documentation

When modifying scoring/ranking logic, always update associated documentation to reflect methodology changes. Treat code changes and doc updates as a single unit of work.

**Files to update when scoring changes:**
- `CLAUDE.md` - Scoring Components table, Session Log
- `docs/METHODOLOGY_SUMMARY_v8.md` - If methodology fundamentally changes

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

### 2026-02-05 (NY Sub-County Density Recalibration)
**Tasks:** Recalibrate NY county/ZIP/tract density estimates to match CPS statewide targets

**Problem:** County avg private density was ~13.7% (should match CPS statewide: 12.4%). The `private_in_public_industries` adjustment inflated estimates by blending edu/health workers (8.1% BLS rate) into the private calculation, then multiplying by 2.40x.

**Solution:** Simplified to match national county model:
1. Removed `private_in_public_industries` adjustment entirely
2. Use only 10 BLS private industry rates (exclude edu/health and public admin)
3. Auto-calibrate multiplier: `12.4% / avg_expected` = 2.2618x (was hardcoded 2.40x)

**Files Modified:**
- `scripts/load_ny_density.py` - Removed EDU_HEALTH_RATE, added auto-calibration, simplified formula
- `api/labor_api_v6.py` - Updated 3 methodology strings with new multiplier (2.26x)
- `CLAUDE.md` - Updated methodology docs, county ranges, NYC borough table

**Results (Before -> After):**
| Metric | Before | After |
|--------|--------|-------|
| Climate multiplier | 2.40x (hardcoded) | 2.26x (auto-calibrated) |
| County avg private | 13.7% | 12.4% (matches CPS) |
| County avg total | 21.2% | 20.2% |
| Manhattan total | 14.1% | 12.2% |
| Hamilton total | 26.9% | 26.5% |

**Status:** Complete. All 62 counties, 1,826 ZIPs, 5,411 tracts recalculated.

### 2026-02-05 (Sibling Union Bonus Fix)
**Tasks:** Fix sibling union bonus misclassifications across all sectors

**Problem:** The sibling bonus matching (Method 2: name match at different address) had two bugs:
1. Same-address matches where formatting differences (e.g., "1 WHITEHALL ST FL 9" vs "1 Whitehall Street") made identical locations appear different
2. Cross-state false positives where a name matched an F-7 employer in a different state (different org)

**New Files Created:**
- `scripts/fix_sibling_bonus.py` - Scans all sectors, fixes same-address and cross-state issues

**Files Deleted:**
- `scripts/check_sibling_matches.py` - Investigation script (no longer needed)
- `scripts/check_sibling_matches2.py` - Investigation script (no longer needed)
- `scripts/check_liberty.py` - Investigation script (no longer needed)

**Fix Results:**
| Fix Type | Count | Action |
|----------|-------|--------|
| Same-address (all sectors) | 61 | Moved to has_union=TRUE with f7_match_method='SIBLING_FIX' |
| Cross-state false positives | 40 | Removed sibling bonus (set to 0) |
| Legitimate siblings (kept) | 102 | No change |

**Sector Impact (Before -> After):**
| Sector | Unionized | Targets | Sibling Bonus |
|--------|-----------|---------|---------------|
| BUILDING_SERVICES | 20->38 | 2,672->2,654 | 41->10 |
| EDUCATION | 62->75 | 2,425->2,412 | 70->54 |
| SOCIAL_SERVICES | 24->37 | 1,496->1,483 | 21->6 |
| CIVIC_ORGANIZATIONS | 31->36 | 3,308->3,303 | 20->8 |
| BROADCASTING | 5->8 | 1,366->1,363 | 8->3 |
| PUBLISHING | 5->10 | 763->758 | 14->5 |
| REPAIR_SERVICES | 1->4 | 393->390 | 12->5 |
| WASTE_MGMT | 4->5 | 713->712 | 15->9 |

**Tier Distribution (After Fix):**
| Tier | Before | After |
|------|--------|-------|
| TOP | 191 | 167 |
| HIGH | 492 | 475 |
| MEDIUM | 3,771 | 3,735 |
| LOW | 9,565 | 9,581 |
| Total | 14,019 | 13,958 |

**Spot Checks:**
- Liberty Resources (Syracuse, NY): bonus=0 (was cross-state match to PA org)
- City Harvest: bonus=8 (correct - HQ vs warehouse at different address)
- Hope House (Albany): bonus=8 (correct - different Albany addresses)
- Make the Road NY (Corona): bonus=8 (correct - different Roosevelt Ave locations)

**Status:** Complete. Views refreshed.

### 2026-02-05 (NY Sub-County Density Estimates)
**Tasks:** Implement NY union density estimates at county, ZIP, and census tract levels with class-of-worker adjustment

**New Files Created:**
- `scripts/load_ny_density.py` - Load NY workforce data and calculate density estimates
- `data/ny_county_workforce.xlsx` - Source data (62 counties)
- `data/ny_zip_workforce.xlsx` - Source data (1,826 ZIPs)
- `data/ny_tract_workforce.xlsx` - Source data (5,411 tracts)
- `data/ny_county_density.csv` - Output (62 counties)
- `data/ny_zip_density.csv` - Output (1,826 ZIPs)
- `data/ny_tract_density.csv` - Output (5,411 tracts)

**Database Tables Created:**
- `ny_county_density_estimates` - 62 NY counties
- `ny_zip_density_estimates` - 1,826 NY ZIP codes
- `ny_tract_density_estimates` - 5,411 NY census tracts

**API Endpoints Added:**
- `GET /api/density/ny/summary` - Summary at all levels
- `GET /api/density/ny/counties` - All 62 county estimates
- `GET /api/density/ny/county/{fips}` - Single county detail
- `GET /api/density/ny/zips` - ZIP estimates with pagination
- `GET /api/density/ny/zip/{zip_code}` - Single ZIP detail
- `GET /api/density/ny/tracts` - Tract estimates with pagination
- `GET /api/density/ny/tract/{tract_fips}` - Single tract detail

**Methodology:**
Same as national county model - 10 BLS private industries, excludes edu/health and public admin.
Auto-calibrated multiplier derived from CPS statewide private density target (12.4%).

**Key Results (Recalibrated 2026-02-05):**
| Level | Records | Avg Total | Avg Private | Min Total | Max Total |
|-------|---------|-----------|-------------|-----------|-----------|
| County | 62 | 20.2% | 12.4% | 12.2% | 26.5% |
| ZIP | 1,826 | 18.7% | 11.5% | 0% | 63.7% |
| Tract | 5,411 | 18.6% | 11.7% | 0% | 48.2% |

**NYC Borough Comparison (Recalibrated):**
| Borough | Total Density | Private Density | Public Density |
|---------|---------------|-----------------|----------------|
| Staten Island | 22.4% | 12.7% | 13.1% |
| Bronx | 19.4% | 13.1% | 9.0% |
| Queens | 18.0% | 12.6% | 8.0% |
| Brooklyn | 17.1% | 11.2% | 8.1% |
| Manhattan | 12.2% | 8.3% | 5.3% |

**Top Counties by Total Density:**
1. Hamilton (26.5%) - Rural, high govt employment
2. Lewis (23.4%) - High public sector share
3. Schoharie (22.9%) - Rural govt employment
4. St. Lawrence (22.9%) - University town
5. Franklin (22.4%) - Rural govt employment

**Status:** Complete. Recalibrated 2026-02-05 (removed class-of-worker adjustment, auto-calibrated multiplier).

### 2026-02-05 (Industry-Weighted Density Analysis)
**Tasks:** Calculate expected private sector union density by state based on industry composition, compare to actual CPS density to identify union climate

**New Files Created:**
- `scripts/load_industry_density.py` - Load BLS rates, state/county industry shares, calculate comparisons

**Database Tables Created:**
- `bls_industry_density` - 12 BLS 2024 industry union density rates
- `state_industry_shares` - 51 state industry compositions (ACS 2025)
- `county_industry_shares` - 3,144 county industry compositions
- `state_industry_density_comparison` - Expected vs actual density with climate multiplier

**Database Columns Added:**
- `county_union_density_estimates.industry_expected_private` - Expected from county industry mix
- `county_union_density_estimates.state_climate_multiplier` - State's union culture factor
- `county_union_density_estimates.industry_adjusted_private` - Final industry-adjusted private density

**API Endpoints Added:**
- `GET /api/density/industry-rates` - BLS industry union density rates
- `GET /api/density/state-industry-comparison` - All states expected vs actual
- `GET /api/density/state-industry-comparison/{state}` - Single state industry breakdown
- `GET /api/density/by-county/{fips}/industry` - County industry detail

**Key Results:**
| Interpretation | States | Avg Multiplier |
|----------------|--------|----------------|
| STRONG | 8 | 1.75x |
| ABOVE_AVERAGE | 13 | 1.23x |
| BELOW_AVERAGE | 17 | 0.70x |
| WEAK | 13 | 0.40x |

**Top 5 States by Climate Multiplier:**
1. HI - Expected 6.0%, Actual 13.2%, Multiplier 2.21x
2. NY - Expected 6.1%, Actual 12.4%, Multiplier 2.04x
3. WA - Expected 6.0%, Actual 11.4%, Multiplier 1.90x
4. NV - Expected 5.8%, Actual 9.6%, Multiplier 1.65x
5. MI - Expected 6.2%, Actual 9.8%, Multiplier 1.57x

**Bottom 5 States:**
1. SD - Expected 6.1%, Actual 1.5%, Multiplier 0.24x
2. AR - Expected 6.4%, Actual 1.9%, Multiplier 0.30x
3. SC - Expected 6.2%, Actual 1.9%, Multiplier 0.32x
4. NC - Expected 6.1%, Actual 1.9%, Multiplier 0.32x
5. UT - Expected 6.1%, Actual 2.2%, Multiplier 0.36x

**County Private Density Updates:**
- 3,144 counties updated with industry-adjusted private density
- Range: 1.22% - 14.96%
- Highest: Lake and Peninsula Borough, AK (15.0%)
- Formula: County_Expected × State_Multiplier

**Methodology Revision (same session):**
- EXCLUDED Education/Health (8.1%) and Public Admin from private sector weighting
- Rationale: These workers are often public employees already in govt density estimates
- Renormalized across 10 remaining private industries
- Updated multipliers: HI=2.51x, NY=2.40x, WA=2.12x (higher due to lower expected)
- New county avg: expected=5.88%, adjusted=5.26%, total=8.32%

**Output File Created:**
- `data/county_density_analysis.csv` - 3,144 counties × 39 columns
- Includes: workforce shares, public sector decomposition, old vs new private density, industry composition, state climate

**Hybrid Approach Analysis (same session):**
Tested alternative methodology: industry-weighted for 10 industries, state CPS rate for edu/health.

**New Files Created:**
- `scripts/calc_national_density.py` - Population-weighted national density by sector
- `scripts/compare_edu_inclusion.py` - With vs without edu/health comparison
- `scripts/hybrid_edu_health.py` - Hybrid approach implementation

**Hybrid Formula:**
```
Hybrid = (10_Industry_Frac × Industry_Expected × Climate_Mult) +
         (EduHealth_Frac × State_Private_Rate)
```

**Results:**
| Metric | Current | Hybrid | Difference |
|--------|---------|--------|------------|
| National Avg | 5.26% | 5.19% | -0.07% |
| High Edu/Health (>30%) | Lower | Higher | +0.5% to +0.8% |
| Low Edu/Health (<15%) | Higher | Lower | -1% to -2% |

**Conclusion:** Hybrid approach provides minimal improvement (-0.07% avg difference). Decision: keep current methodology (exclude edu/health entirely) for simplicity and to avoid double-counting with public sector estimates.

**Status:** Complete. All 51 states and 3,144 counties have industry-adjusted estimates.

### 2026-02-05 (Address Matching Tier)
**Tasks:** Add address-based matching as Tier 3 in unified matching module

**New Files Created:**
- `scripts/matching/matchers/address.py` - Address matcher with fuzzy name + exact street number

**Files Modified:**
- `scripts/matching/config.py` - Added TIER_ADDRESS (3), renumbered AGGRESSIVE to 4, FUZZY to 5
- `scripts/matching/config.py` - Added `source_address_col` and `target_address_col` to MatchConfig
- `scripts/matching/config.py` - Updated scenarios with address column mappings
- `scripts/matching/pipeline.py` - Added AddressMatcher to pipeline, passes address to matchers
- `scripts/matching/matchers/base.py` - Added `address` parameter to match() signature
- `scripts/matching/matchers/exact.py` - Added `address` parameter (unused but required)
- `scripts/matching/matchers/fuzzy.py` - Added `address` parameter (unused but required)

**Key Implementation Details:**
1. **Street Number Extraction** - Handles messy NLRB format "City, ST ZIP, 123 Main St"
   - Removes ZIP codes (5/9 digit patterns)
   - Removes state abbreviations
   - Removes city prefix before comma
   - Extracts first remaining number sequence

2. **Address Matching Logic:**
   - Uses pg_trgm `similarity()` for fuzzy name matching (>=0.4 threshold)
   - Uses PostgreSQL regex `~ '^123[^0-9]'` for street number matching
   - Requires state match, optionally matches city
   - Lower name threshold since address provides additional confidence

3. **PostgreSQL Regex Fix:**
   - `\b` word boundary doesn't work reliably in PostgreSQL
   - Changed to `^{num}[^0-9]` pattern (number at start, followed by non-digit)

**Test Results (nlrb_to_f7, 2000 records):**
| Tier | Matches |
|------|---------|
| NORMALIZED | 71 |
| ADDRESS | 30 |
| AGGRESSIVE | 6 |
| **Total** | **107** |

**Example ADDRESS Matches:**
- "THC CHICAGO AIRPORT MANAGEMENT D/B/A RENAISSANCE C" → "Renaissance Chicago O'Hare Suites Hotel" (8500 W Bryn Mawr Ave, Chicago)
- "North American Salt Company, a division of Compass" → "Compass Minerals America Inc" (9200 S. Ewing Ave, Chicago)
- "SG360" → "The Segerdahl Corp d/b/a SG360" (1351 Wheeling Rd, Wheeling IL)

**Address Column Mappings:**
| Table | Address Column |
|-------|----------------|
| nlrb_participants | address |
| f7_employers_deduped | street |
| osha_establishments | site_address |
| mergent_employers | street_address |
| nlrb_voluntary_recognition | (none) |

**Status:** Complete. 5-tier pipeline operational.

### 2026-02-05 (Public Sector Density Estimation)
**Tasks:** Estimate missing public sector union density for 25 states with small CPS samples

**New Files Created:**
- `scripts/estimate_public_density.py` - Load total density, workforce shares, calculate estimates

**Database Objects Created:**
- `state_workforce_shares` table - 51 state records with public/private workforce shares
- `state_sector_union_density` - Added 2,352 'total' records and 150 estimated 'public' records
- `v_state_density_latest` view - Updated with `public_is_estimated` flag

**Algorithm:**
```
Public_Density = (Total_Density - Private_Share × Private_Density) / Public_Share
```

**Results:**
- All 51 states now have public sector density (was 26/51)
- 25 states with estimated values (source = 'estimated_from_total')
- Validation: estimates within ±8.6% of direct measurements (worst case CA)
- All estimates in reasonable 0-80% range

**API Changes:**
- `/api/density/by-state` - Added `public_is_estimated`, `total_density_pct`, `total_year` fields
- `/api/density/by-state/{state}/history` - Added `source` field, now supports sector='total'
- `/api/density/by-govt-level` - NEW: All states with fed/state/local density estimates
- `/api/density/by-govt-level/{state}` - NEW: Single state detail with workforce composition
- `/api/density/by-county` - NEW: County density estimates with filters
- `/api/density/by-county/{fips}` - NEW: Single county detail
- `/api/density/by-state/{state}/counties` - NEW: All counties in a state
- `/api/density/county-summary` - NEW: National county statistics

**County Density Methodology:**
```
County_Density = (Private_Share × State_Private_Rate) +
                 (Fed_Share × State_Fed_Rate) +
                 (State_Share × State_State_Rate) +
                 (Local_Share × State_Local_Rate)
```
- Uses **state-adjusted** federal/state/local rates (not national baselines)
- Self-employed workers excluded (0% union rate)
- 3,144 counties estimated (78 Puerto Rico municipios excluded)
- Confidence: HIGH if state has direct CPS measurement, MEDIUM if state density was estimated

**Key Results:**
- National avg county density: 8.1%
- Range: 0% to 29.2% (Hamilton County, NY highest)
- Top states by avg county density: NY, HI, CA, WA, NJ
- Bottom states: SC, NC, SD, AR, UT

**Status:** Complete

### 2026-02-04 (Unified Matching Module)
**Tasks:** Create unified employer matching module with multi-tier pipeline and diff reporting

**New Files Created:**
- `scripts/matching/__init__.py` - Package exports
- `scripts/matching/config.py` - MatchConfig dataclass, 9 predefined scenarios
- `scripts/matching/normalizer.py` - Unified normalization (standard/aggressive/fuzzy)
- `scripts/matching/pipeline.py` - MatchPipeline orchestrator
- `scripts/matching/differ.py` - DiffReport for comparing runs
- `scripts/matching/cli.py` - Command-line interface
- `scripts/matching/__main__.py` - Module entry point
- `scripts/matching/matchers/__init__.py` - Matcher exports
- `scripts/matching/matchers/base.py` - MatchResult, BaseMatcher base classes
- `scripts/matching/matchers/exact.py` - EINMatcher, NormalizedMatcher, AggressiveMatcher
- `scripts/matching/matchers/fuzzy.py` - TrigramMatcher using pg_trgm
- `scripts/run_unified_matching.py` - Standalone CLI runner
- `scripts/test_matching.py` - Test script

**Key Features:**
1. **Multi-Tier Matching Pipeline**: EIN → Normalized → Address → Aggressive → Fuzzy (5 tiers after 2026-02-05 update)
2. **Consistent Normalization**: Wraps existing name_normalizer.py with levels
3. **9 Predefined Scenarios**: All common matching use cases configured
4. **Diff Reporting**: Compare match runs to see new/lost/changed matches
5. **CLI Interface**: `python -m scripts.matching run --list`
6. **Skip-Fuzzy Option**: `--skip-fuzzy` for faster runs (tier 5 is slow)

**Match Result Schema:**
```python
MatchResult(
    source_id, source_name,
    target_id, target_name,
    score,        # 0.0-1.0
    method,       # "EIN", "NORMALIZED", "AGGRESSIVE", "FUZZY"
    tier,         # 1-4
    confidence,   # "HIGH", "MEDIUM", "LOW"
    matched,      # bool
    metadata      # dict
)
```

**Performance Notes:**
- Tier 1-4: ~1000 records in 35-60 seconds (address tier adds ~25% overhead)
- Tier 5 (fuzzy): Very slow per-record, use `--skip-fuzzy` for batch runs
- Fuzzy matching uses pg_trgm similarity() instead of % operator for psycopg2 compatibility
- Address matching uses pg_trgm similarity() for name + regex for street number

**Files Deprecated (mark but don't delete):**
- `scripts/import/fuzzy_employer_matching.py`
- `scripts/etl/osha_fuzzy_match.py`
- `scripts/match_labor_violations.py` (inline normalization)

**Status:** Complete. Module tested and working.

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
