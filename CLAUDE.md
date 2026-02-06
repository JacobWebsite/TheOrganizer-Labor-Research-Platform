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

### Core Principle: Data Quality Over External Benchmarks
**Always prefer accurate, deduplicated data over hitting BLS/EPI coverage targets.**
Never inflate counts or skip exclusions to stay within benchmark ranges.
BLS check is WARNING-level in validation framework, not critical.

### Current Platform Status

| Metric | Value | Benchmark | Coverage |
|--------|-------|-----------|----------|
| Total Members | 14.5M | 14.3M (BLS) | 101.4% |
| Private Sector | 6.61M | 7.2M | 91.8% |
| Federal Sector | 1.28M | 1.1M | 116% |
| State/Local Public | 6.9M | 7.0M (EPI) | 98.3% |
| States Reconciled | 50/51 | - | 98% |
| F7 Employers | 62,163 | - | 51,337 counted |

---

## Database Schema

### Core Tables
| Table | Records | Description |
|-------|---------|-------------|
| `unions_master` | 26,665 | OLMS union filings (has local_number field) |
| `f7_employers_deduped` | 62,163 | Private sector employers |
| `nlrb_elections` | 33,096 | NLRB election records |
| `nlrb_participants` | 30,399 | Union petitioners (95.7% matched to OLMS) |
| `lm_data` | 2.6M+ | Historical filings (2010-2024) |
| `epi_state_benchmarks` | 51 | State union benchmarks |
| `manual_employers` | 509 | State/public sector + research discoveries |
| `employer_review_flags` | - | Manual review flags (ALREADY_UNION, DUPLICATE, etc.) |
| `mv_employer_search` | 120,169 | Materialized view: unified F7+NLRB+VR+Manual search |

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
| `mergent_employers` | 37,679 | Mergent Intellect employer data (21 sectors) |
| `ny_990_filers` | 37,480 | IRS Form 990 NY nonprofit filers (2022-2024) |

**Sectors in mergent_employers:**
| Sector | Employers | Unionized | Targets | Employees |
|--------|-----------|-----------|---------|-----------|
| OTHER | 16,840 | 360 | 16,480 | 1,451,088 |
| CIVIC_ORGANIZATIONS | 3,339 | 40 | 3,299 | 68,864 |
| PROFESSIONAL | 2,838 | 28 | 2,810 | 244,586 |
| BUILDING_SERVICES | 2,692 | 44 | 2,648 | 197,485 |
| EDUCATION | 2,487 | 78 | 2,409 | 239,212 |
| SOCIAL_SERVICES | 1,520 | 38 | 1,482 | 65,672 |
| BROADCASTING | 1,371 | 9 | 1,362 | 82,536 |
| HEALTHCARE_AMBULATORY | 1,107 | 35 | 1,072 | 102,805 |
| HEALTHCARE_NURSING | 772 | 27 | 745 | 120,645 |
| PUBLISHING | 768 | 13 | 755 | 37,462 |
| WASTE_MGMT | 717 | 7 | 710 | 13,998 |
| GOVERNMENT | 525 | 35 | 490 | 48,056 |
| TRANSIT | 443 | 9 | 434 | 45,992 |
| UTILITIES | 436 | 6 | 430 | 16,175 |
| REPAIR_SERVICES | 394 | 4 | 390 | 11,975 |
| HEALTHCARE_HOSPITALS | 374 | 55 | 319 | 178,769 |
| HOSPITALITY | 265 | 6 | 259 | 23,908 |
| MUSEUMS | 243 | 25 | 218 | 12,659 |
| FOOD_SERVICE | 215 | 4 | 211 | 20,311 |
| INFORMATION | 184 | 9 | 175 | 7,352 |
| ARTS_ENTERTAINMENT | 149 | 13 | 136 | 14,339 |

**Mergent Employers Columns (Key):**
- `duns` - D-U-N-S number (unique ID)
- `ein` - IRS Employer ID (55% coverage)
- `company_name`, `city`, `state`, `zip`, `county`
- `employees_site`, `sales_amount`, `naics_primary`
- `sector_category` - One of 21 sectors above
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
- Max score: 62 pts | Tiers: TOP >=30, HIGH >=25, MEDIUM >=15, LOW <15

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
`other`, `civic_organizations`, `professional`, `building_services`, `education`, `social_services`, `broadcasting`, `healthcare_ambulatory`, `healthcare_nursing`, `publishing`, `waste_mgmt`, `government`, `transit`, `utilities`, `repair_services`, `healthcare_hospitals`, `hospitality`, `museums`, `food_service`, `information`, `arts_entertainment`

**Priority Tiers:**
| Tier | Score Range |
|------|-------------|
| TOP | >=30 |
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
- 10 private industries: Industry-weighted BLS rates x auto-calibrated multiplier (2.26x)
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

**State Climate Multiplier:**
- Formula: `Actual_Private_Density / Expected_Private_Density`
- Expected = sum of (industry_share x BLS_industry_rate) across 10 private industries
- Interpretation: STRONG (>1.5x), ABOVE_AVERAGE (1.0-1.5x), BELOW_AVERAGE (0.5-1.0x), WEAK (<0.5x)
- Top 3: HI (2.51x), NY (2.40x), WA (2.12x)
- Bottom 3: SD (0.28x), AR (0.33x), SC (0.35x)

**County Private Density Calculation:**
```
County_Private = sum(County_Industry_Share x BLS_Rate) x State_Climate_Multiplier
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

Full Swagger docs: http://localhost:8001/docs

**Core:** `/api/health`, `/api/summary`, `/api/stats/breakdown`
**Lookups:** `/api/lookups/{sectors,affiliations,states,naics-sectors,metros,cities}`
**Employers:** `/api/employers/search` (name/state/NAICS/city), `fuzzy-search`, `normalized-search`, `/{id}`, `/{id}/osha`, `/{id}/nlrb`, `/cities`, `/by-naics-detailed/{code}`
**Unified Employers:** `/api/employers/unified/{stats,search,sources}`, `/{id}`
**Unified Search:** `/api/employers/unified-search` (name/state/city/source_type/has_union), `/unified-detail/{canonical_id}`
**Review Flags:** `/api/employers/flags` (POST), `/flags/pending`, `/flags/{id}` (DELETE), `/flags/by-employer/{canonical_id}`
**Unions:** `/api/unions/search`, `/{f_num}`, `/{f_num}/employers`, `/locals/{aff}`, `/national`, `/national/{aff_abbr}`
**NLRB:** `/api/nlrb/summary`, `/elections/search`, `/elections/map`, `/elections/by-{year,state,affiliation}`, `/election/{case}`, `/ulp/search`, `/ulp/by-section`
**OSHA:** `/api/osha/summary`, `/establishments/search`, `/establishments/{id}`, `/by-state`, `/high-severity`, `/organizing-targets`, `/employer-safety/{id}`, `/unified-matches`
**VR:** `/api/vr/stats/{summary,by-year,by-state,by-affiliation}`, `/search`, `/map`, `/new-employers`, `/pipeline`, `/{case}`
**Public Sector:** `/api/public-sector/{stats,parent-unions,locals,employers,employer-types,benchmarks}`
**Organizing:** `/api/organizing/{summary,by-state}`, `/scorecard`, `/scorecard/{estab_id}`
**Sectors (21):** `/api/sectors/list`, `/{sector}/{summary,targets,targets/stats,targets/{id},targets/cities,unionized}`
**Museums (Legacy):** `/api/museums/{summary,targets,targets/stats,targets/cities,targets/{id},unionized}`
**Trends:** `/api/trends/{national,sectors,elections}`, `/by-state/{state}`, `/by-affiliation/{aff}`
**Multi-Employer:** `/api/multi-employer/{stats,groups}`, `/employer/{id}/agreement`, `/corporate/family/{id}`
**Projections:** `/api/projections/{summary,search,top}`, `/industry/{naics}`, `/matrix/{code}`, `/employer/{id}/projections`
**Density:** `/api/density/{all,by-state,by-county,county-summary,industry-rates}`, `/by-state/{state}/{history,counties}`, `/by-govt-level`, `/by-county/{fips}/{industry}`, `/state-industry-comparison/{state}`, `/naics/{code}`
**NY Density:** `/api/density/ny/{summary,counties,zips,tracts}`, `/county/{fips}`, `/zip/{code}`, `/tract/{fips}`
**NAICS:** `/api/naics/stats`

---

## Key Features (What Exists - Don't Rebuild)

1. **OSHA Organizing Scorecard** - 6-factor, 0-100 pts via `/api/organizing/scorecard`. Factors: safety violations (25), industry density (15), geographic (15), size (15), NLRB momentum (15), govt contracts (15)
2. **AFSCME NY Organizing Targets** - 5,428 targets from 990 + contract data, $18.35B funding. Tiers: TOP (70+), HIGH (50-69), MEDIUM (30-49), LOW (<30)
3. **Geographic Analysis** - MSA/metro density, city search, CBSA mapping (40.8%)
4. **Membership Deduplication** - 70.1M raw -> 14.5M deduplicated (matches BLS within 1.5%)
5. **Historical Trends** - 16 years OLMS LM filings (2010-2024), Chart.js visualizations
6. **Public Sector Coverage** - 98.3% of EPI benchmark, 50/51 states within +/-15%
7. **Multi-Sector Organizing Scorecard** - 37,679 Mergent employers, 21 sectors, 62 pts max. Components: size (5), industry density (10), NLRB momentum (10), OSHA (4), contracts (15), labor violations (10), sibling bonus (8). Tiers: TOP>=30, HIGH>=25, MEDIUM>=15, LOW<15. See `docs/METHODOLOGY_SUMMARY_v8.md` for full scoring details
8. **Industry Outlook** - BLS 2024-2034 projections in employer detail, 6-digit NAICS from OSHA, occupation breakdowns

---

## Frontend Interfaces

| File | Purpose |
|------|---------|
| **`files/organizer_v5.html`** | **PRIMARY FRONTEND - All new features go here** |

**IMPORTANT:** All frontend and backend development should target the Organizer interface (`files/organizer_v5.html`). Legacy frontend archived to `archive/frontend/`.

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

-- Sector organizing targets (non-union, ranked by score)
SELECT employer_name, city, best_employee_count, total_score, priority_tier
FROM v_{sector}_organizing_targets WHERE priority_tier IN ('HIGH', 'MEDIUM');
```

---

## Reference Documentation

| Document | Purpose |
|----------|---------|
| `docs/LABOR_PLATFORM_ROADMAP_v10.md` | Current roadmap, future phases |
| `docs/METHODOLOGY_SUMMARY_v8.md` | Complete methodology reference |
| `docs/EPI_BENCHMARK_METHODOLOGY.md` | EPI benchmark explanation |
| `docs/PUBLIC_SECTOR_SCHEMA_DOCS.md` | Public sector schema reference |
| `docs/AFSCME_NY_CASE_STUDY.md` | Organizing targets feature docs |
| `docs/FORM_990_FINAL_RESULTS.md` | 990 methodology results |
| `docs/EXTENDED_ROADMAP.md` | Future checkpoints H-O |
| `docs/session-summaries/SESSION_LOG_2026.md` | Full session history |

---

## Coverage Acceptance Criteria

| Status | Criteria |
|--------|----------|
| COMPLETE | Within +/-15% of EPI benchmark |
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

### Available Scenarios

| Scenario | Source | Target |
|----------|--------|--------|
| `nlrb_to_f7` | nlrb_participants | f7_employers_deduped |
| `osha_to_f7` | osha_establishments | f7_employers_deduped |
| `mergent_to_f7` | mergent_employers | f7_employers_deduped |
| `mergent_to_990` | mergent_employers | ny_990_filers |
| `mergent_to_nlrb` | mergent_employers | nlrb_participants |
| `mergent_to_osha` | mergent_employers | osha_establishments |
| `violations_to_mergent` | nyc_wage_theft_nys | mergent_employers |
| `contracts_to_990` | ny_state_contracts | employers_990 |
| `vr_to_f7` | nlrb_voluntary_recognition | f7_employers_deduped |

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
- `CLAUDE.md` - Scoring Components table
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

See `docs/session-summaries/SESSION_LOG_2026.md` for full session history.
