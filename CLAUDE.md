# Labor Relations Research Platform - Claude Context

## Quick Reference
**Last Updated:** 2026-02-14 (audit issues resolved, disk cleanup complete)

### Database Connection
```python
import psycopg2
conn = psycopg2.connect(
    host='localhost',
    dbname='olms_multiyear',
    user='postgres',
    password='<password in .env file>'
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
| F7 Employers | 60,953 | - | 51,337 counted |

---

## Database Schema

### Core Tables
| Table | Records | Description |
|-------|---------|-------------|
| `unions_master` | 26,665 | OLMS union filings (has local_number field) |
| `f7_employers_deduped` | 60,953 | Private sector employers (PK: employer_id) |
| `nlrb_elections` | 33,096 | NLRB election records |
| `nlrb_participants` | 1,906,542 | Union petitioners (95.7% matched to OLMS) |
| `lm_data` | 331,238 | Historical filings (2010-2024) |
| `epi_state_benchmarks` | 51 | State union benchmarks |
| `manual_employers` | 520 | State/public sector + research discoveries |
| `employer_review_flags` | - | Manual review flags (ALREADY_UNION, DUPLICATE, etc.) |
| `mv_employer_search` | 118,015 | Materialized view: unified F7+NLRB+VR+Manual search |

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
| `osha_f7_matches` | 138,340 | Linkages to F-7 employers (13.7% of OSHA establishments / 47.3% of F7 employers) |
| `v_osha_organizing_targets` | - | Organizing target view |

### WHD Tables (Wage & Hour Division - National)
| Table | Records | Description |
|-------|---------|-------------|
| `whd_cases` | 363,365 | National WHISARD wage violation cases (2005-2025) |
| `mv_whd_employer_agg` | 330,419 | Aggregated WHD by employer (name+city+state) |

**Key columns:** `case_id`, `trade_name`, `legal_name`, `name_normalized`, `city`, `state`, `naics_code`, `total_violations`, `civil_penalties`, `backwages_amount`, `employees_violated`, `flsa_repeat_violator`, `flsa_child_labor_violations`, `findings_start_date`, `findings_end_date`

**Match coverage:** F7: 24,610 (6.8%) via `whd_f7_matches`, Mergent: 1,170 (2.1%). Total backwages: $4.7B, penalties: $361M

### Match Tables
| Table | Records | Description |
|-------|---------|-------------|
| `osha_f7_matches` | 138,340 | OSHA-to-F7 employer matches (4-tier) |
| `whd_f7_matches` | 24,610 | WHD-to-F7 employer matches (PK: f7_employer_id, case_id) |
| `national_990_f7_matches` | 14,059 | 990-to-F7 employer matches (PK: f7_employer_id, ein) |
| `sam_f7_matches` | 11,050 | SAM-to-F7 employer matches (PK: f7_employer_id, uei) |
| `nlrb_employer_xref` | 179,275 | NLRB-to-F7 cross-reference |
| `employer_comparables` | 269,810 | Gower similarity results (5 comparables per employer) |

### SAM.gov Tables
| Table | Records | Description |
|-------|---------|-------------|
| `sam_entities` | 826,042 | SAM.gov federal contractor registry (UEI, CAGE, NAICS) |

### Additional Data Tables
| Table | Records | Description |
|-------|---------|-------------|
| `epi_union_membership` | 1,420,064 | EPI union membership microdata (322 MB) |
| `employers_990_deduped` | 1,046,167 | Deduped national 990 employers (265 MB) |
| `ar_disbursements_emp_off` | 2,813,248 | Annual report: disbursements to employees/officers |
| `ar_membership` | 216,508 | Annual report: membership data |
| `ar_disbursements_total` | 216,372 | Annual report: total disbursements |
| `ar_assets_investments` | 304,816 | Annual report: assets and investments |

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

### Corporate Hierarchy Tables
| Table | Records | Description |
|-------|---------|-------------|
| `sec_companies` | 517,403 | SEC EDGAR company registry (CIK, EIN, LEI, ticker) |
| `gleif_us_entities` | 379,192 | GLEIF/Open Ownership US entities (100% with LEI) |
| `gleif_ownership_links` | 498,963 | GLEIF parent→child ownership links |
| `corporate_identifier_crosswalk` | 25,177 | Unified ID mapping across SEC/GLEIF/Mergent/F7/USASpending/SAM/990 |
| ~~`splink_match_results`~~ | ARCHIVED | Was 5,761,285 rows — archived to `~/splink_match_results_archive.sql.gz` and dropped |
| `corporate_hierarchy` | 125,120 | Parent-to-subsidiary relationships |
| `qcew_annual` | 1,943,426 | BLS QCEW industry x geography data (2020-2023) |
| `qcew_industry_density` | 7,143 | State-level NAICS density (private sector, 2023) |
| `f7_industry_scores` | 121,433 | F7 employer industry density scores from QCEW (97.5% matched) |
| `federal_contract_recipients` | 47,193 | USASpending FY2024 federal contract recipients |
| `usaspending_f7_matches` | 9,305 | USASpending-to-F7 matches (exact + fuzzy) |
| `f7_federal_scores` | 9,305 | Federal contractor scores (0-15 pts) |
| `state_fips_map` | 54 | State abbreviation to FIPS code mapping |

**GLEIF Raw Schema** (loaded from pgdump into `gleif` schema):
| Table | Records |
|-------|---------|
| `gleif.entity_statement` | 5,667,010 |
| `gleif.entity_identifiers` | 6,706,686 |
| `gleif.entity_addresses` | 6,706,686 |
| `gleif.ooc_statement` | 5,758,526 |
| `gleif.ooc_interests` | 5,748,906 |
| `gleif.person_statement` | 2,826,102 |

**gleif_us_entities Key Columns:**
- `bods_link` - Numeric row ID from entity_statement._link
- `statementid` - UUID (used for ownership link joins)
- `entity_name`, `name_normalized`, `address_state`, `address_zip`
- `lei` - Legal Entity Identifier (100% coverage)
- `jurisdiction_code` - e.g. `US-NY`

**IMPORTANT:** GLEIF `ooc_statement` references entities via `statementid` (UUID), NOT `_link` (numeric). Always join ownership links through `statementid`.

**Crosswalk Matching Tiers:**
| Tier | Method | Matches | Confidence |
|------|--------|---------|------------|
| 1 | EIN exact (SEC<->Mergent) | 1,127 | HIGH |
| 2 | LEI exact (SEC<->GLEIF) | 84 | HIGH |
| 3 | Name+State (all sources, cleanco-normalized) | 3,009 | MEDIUM |
| 4 | Splink probabilistic (JW>=0.88 + prob>=0.85) | 1,552 | MEDIUM |
| 5 | USASpending exact name+state | 1,994 | HIGH |
| 6 | USASpending fuzzy name+state (pg_trgm>=0.55) | 6,795 | MEDIUM |

**Crosswalk Coverage:**
| Source | Linked | Total | Rate |
|--------|--------|-------|------|
| SEC | 1,948 | 517,403 | 0.4% |
| GLEIF | 3,264 | 379,192 | 0.9% |
| Mergent | 3,361 | 56,426 | 6.0% |
| F7 | ~12,000 | 60,953 | 19.7% |
| Federal contractors | 9,305 | 47,193 | 19.7% |
| Public companies | 358 | - | - |

**Corporate Hierarchy Sources:**
| Source | Links | Description |
|--------|-------|-------------|
| GLEIF | 116,531 | Both-US ownership (direct/indirect/unknown) |
| Mergent parent_duns | 7,404 | Direct parent->child |
| Mergent domestic_parent | 1,185 | Domestic ultimate parent |
| **Total** | **125,120** | 13,929 distinct parents, 54,924 distinct children |

**ETL Scripts:**
- `scripts/etl/load_gleif_bods.py` - Restore GLEIF pgdump + extract US entities
- `scripts/etl/extract_gleif_us_optimized.py` - Optimized 2-step US extraction (use this)
- `scripts/etl/build_crosswalk.py` - Build crosswalk + hierarchy tables
- `scripts/etl/update_normalization.py` - Apply cleanco normalization to GLEIF/SEC name_normalized columns
- `scripts/matching/splink_config.py` - Splink scenario configs (comparisons, blocking rules, thresholds)
- `scripts/matching/splink_pipeline.py` - Splink probabilistic matching pipeline (DuckDB backend)
- `scripts/matching/splink_integrate.py` - Integrate Splink results into crosswalk (1:1 dedup + quality filter)
- `scripts/etl/fetch_qcew.py` - Download BLS QCEW annual data (2020-2023)
- `scripts/etl/_integrate_qcew.py` - QCEW industry density scoring for F7 employers
- `scripts/etl/_fetch_usaspending_api.py` - Fetch federal contract recipients via paginated API
- `scripts/etl/_match_usaspending.py` - Match USASpending recipients to F7 and integrate crosswalk

### Web Scraper Tables (AFSCME)
| Table | Records | Description |
|-------|---------|-------------|
| `web_union_profiles` | 295 | Union directory entries + scraped website text |
| `web_union_employers` | 160 | Employers extracted from union websites (AI + heuristic) |
| `web_union_contracts` | 120 | Contract/CBA documents found (115 with PDF URLs) |
| `web_union_membership` | 31 | Membership counts extracted from web text |
| `web_union_news` | 183 | News items extracted from union sites |
| `scrape_jobs` | 112 | Scrape audit trail (status, duration, errors) |

**Pipeline:** CSV directory load -> OLMS matching -> Crawl4AI fetch -> Heuristic + AI extraction -> 5-tier employer matching (F7 exact, OSHA exact, F7 fuzzy, OSHA fuzzy, cross-state)

**Key columns (web_union_profiles):** `union_name`, `local_number`, `state`, `website_url`, `platform`, `raw_text`, `raw_text_about`, `raw_text_contracts`, `raw_text_news`, `scrape_status` (NO_WEBSITE/EXTRACTED/FAILED), `match_status` (MATCHED_OLMS/UNMATCHED/NO_LOCAL_NUMBER), `f_num`

**Key columns (web_union_employers):** `employer_name`, `state`, `sector` (PUBLIC_STATE/PUBLIC_LOCAL/PUBLIC_EDUCATION/HEALTHCARE/NONPROFIT), `match_status` (MATCHED_F7_EXACT/MATCHED_OSHA_EXACT/MATCHED_F7_FUZZY/MATCHED_OSHA_FUZZY/UNMATCHED), `matched_employer_id` (TEXT, links to f7_employers_deduped.employer_id)

**Match coverage:** 73/160 employers matched (46%). 87 unmatched are predominantly public-sector (confirming F7's private-sector-only gap).

**Scripts:**
- `scripts/etl/setup_afscme_scraper.py` — Checkpoint 1: table creation + CSV load + OLMS matching
- `scripts/scraper/fetch_union_sites.py` — Checkpoint 2: Crawl4AI website fetching
- `scripts/scraper/extract_union_data.py` — Checkpoint 3: heuristic extraction + JSON insert
- `scripts/scraper/fix_extraction.py` — Boilerplate detection + false positive cleanup
- `scripts/scraper/match_web_employers.py` — Checkpoint 4: 5-tier employer matching
- `scripts/scraper/export_html.py` — Generate browsable HTML data viewer

**Data viewer:** `files/afscme_scraper_data.html` — 6-tab HTML with sortable tables

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
| `mergent_employers` | 56,426 | Mergent Intellect employer data (21 sectors) |
| `national_990_filers` | 586,767 | IRS Form 990 national filers (2022-2024), deduped by EIN |
| `ny_990_filers` | 47,614 | IRS Form 990 NY nonprofit filers (2022-2024) |

**Sectors in mergent_employers:**
| Sector | Employers | Unionized | Targets | Employees |
|--------|-----------|-----------|---------|-----------|
| OTHER | 29,614 | 461 | 29,153 | 1,775,877 |
| PROFESSIONAL | 5,674 | 36 | 5,638 | 375,517 |
| CIVIC_ORGANIZATIONS | 3,339 | 40 | 3,299 | 68,864 |
| BUILDING_SERVICES | 2,692 | 44 | 2,648 | 197,485 |
| EDUCATION | 2,487 | 78 | 2,409 | 239,212 |
| HEALTHCARE_AMBULATORY | 2,390 | 41 | 2,349 | 128,632 |
| SOCIAL_SERVICES | 1,520 | 38 | 1,482 | 65,672 |
| BROADCASTING | 1,371 | 9 | 1,362 | 82,536 |
| HEALTHCARE_NURSING | 1,065 | 32 | 1,033 | 128,379 |
| UTILITIES | 869 | 7 | 862 | 21,482 |
| PUBLISHING | 768 | 13 | 755 | 37,462 |
| TRANSIT | 735 | 15 | 720 | 54,538 |
| WASTE_MGMT | 717 | 7 | 710 | 13,998 |
| FOOD_SERVICE | 553 | 7 | 546 | 32,208 |
| HOSPITALITY | 536 | 8 | 528 | 36,453 |
| GOVERNMENT | 525 | 35 | 490 | 48,056 |
| HEALTHCARE_HOSPITALS | 514 | 57 | 457 | 187,352 |
| REPAIR_SERVICES | 394 | 4 | 390 | 11,975 |
| MUSEUMS | 243 | 25 | 218 | 12,659 |
| ARTS_ENTERTAINMENT | 241 | 19 | 222 | 16,859 |
| INFORMATION | 184 | 9 | 175 | 7,352 |

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
- Max score: 62 pts | Tiers: TOP >=30, HIGH >=25, MEDIUM >=20, LOW <20

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
| MEDIUM | 20-24 |
| LOW | <20 |

### Geography Tables
| Table | Records | Description |
|-------|---------|-------------|
| `cbsa_definitions` | 935 | Metro area definitions (CBSA codes, titles, counties) |
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
**WHD:** `/api/whd/summary`, `/search`, `/by-state/{state}`, `/employer/{employer_id}`, `/top-violators`
**VR:** `/api/vr/stats/{summary,by-year,by-state,by-affiliation}`, `/search`, `/map`, `/new-employers`, `/pipeline`, `/{case}`
**Public Sector:** `/api/public-sector/{stats,parent-unions,locals,employers,employer-types,benchmarks}`
**Organizing:** `/api/organizing/{summary,by-state}`, `/scorecard`, `/scorecard/{estab_id}`
**Sectors (21):** `/api/sectors/list`, `/{sector}/{summary,targets,targets/stats,targets/{id},targets/cities,unionized}`
**Museums (Legacy):** `/api/museums/{summary,targets,targets/stats,targets/cities,targets/{id},unionized}`
**Trends:** `/api/trends/{national,sectors,elections}`, `/by-state/{state}`, `/by-affiliation/{aff}`
**Multi-Employer:** `/api/multi-employer/{stats,groups}`, `/employer/{id}/agreement`
**Corporate:** `/api/corporate/family/{id}`, `/corporate/hierarchy/{id}`, `/corporate/hierarchy/stats`, `/corporate/hierarchy/search`, `/corporate/sec/{cik}`
**Projections:** `/api/projections/{summary,search,top}`, `/industry/{naics}`, `/matrix/{code}`, `/employer/{id}/projections`
**Density:** `/api/density/{all,by-state,by-county,county-summary,industry-rates}`, `/by-state/{state}/{history,counties}`, `/by-govt-level`, `/by-county/{fips}/{industry}`, `/state-industry-comparison/{state}`, `/naics/{code}`
**NY Density:** `/api/density/ny/{summary,counties,zips,tracts}`, `/county/{fips}`, `/zip/{code}`, `/tract/{fips}`
**NAICS:** `/api/naics/stats`

---

## Key Features (What Exists - Don't Rebuild)

1. **OSHA Organizing Scorecard** - 9-factor, 0-100 pts via `/api/organizing/scorecard`. Factors: safety violations (20), industry density (10), geographic favorability (15), size (10), NLRB patterns (10), govt contracts (15), company unions (10), employer similarity (5), WHD violations (5)
2. **AFSCME NY Organizing Targets** - 5,428 targets from 990 + contract data, $18.35B funding. Tiers: TOP (70+), HIGH (50-69), MEDIUM (30-49), LOW (<30)
3. **Geographic Analysis** - MSA/metro density, city search, CBSA mapping (40.8%)
4. **Membership Deduplication** - 70.1M raw -> 14.5M deduplicated (matches BLS within 1.5%)
5. **Historical Trends** - 16 years OLMS LM filings (2010-2024), Chart.js visualizations
6. **Public Sector Coverage** - 98.3% of EPI benchmark, 50/51 states within +/-15%
7. **Multi-Sector Organizing Scorecard** - 56,426 Mergent employers, 21 sectors, 62 pts max. Components: size (5), industry density (10), NLRB momentum (10), OSHA (4), contracts (15), labor violations (10), sibling bonus (8). Tiers: TOP>=30, HIGH>=25, MEDIUM>=20, LOW<20. See `docs/METHODOLOGY_SUMMARY_v8.md` for full scoring details
8. **Industry Outlook** - BLS 2024-2034 projections in employer detail, 6-digit NAICS from OSHA, occupation breakdowns
9. **Corporate Hierarchy** - SEC EDGAR (517K), GLEIF (379K entities, 499K ownership links), crosswalk linking SEC/GLEIF/Mergent/F7/USASpending/SAM/990 (25,177 rows: deterministic + Splink + USASpending + SAM + 990), hierarchy with 125K parent->child links from 13,929 distinct parent companies. QCEW industry density scores for 121K F7 employers. 9,305 F7 employers identified as federal contractors with scoring (0-15 pts).

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

**Archived source data:**
- `990_2025_archive.7z` — 650K IRS Form 990 XML files (1.2 GB compressed, was 20 GB). Already loaded into `national_990_filers` and `employers_990_deduped`.
- `data/free_company_dataset.csv.7z` — Company dataset (1.6 GB compressed, was 5.1 GB). Future use for employer email lookup.
- `backup_20260209.dump.7z` — PostgreSQL backup (2.0 GB compressed, was 2.1 GB). Recreatable with `pg_dump`.

**Match quality flags:**
- `osha_f7_matches.low_confidence` — TRUE for 32,243 matches (23.3%) with match_confidence < 0.6
- `whd_f7_matches.low_confidence` — TRUE for 6,657 matches (27.0%) with match_confidence < 0.6

**f7_union_employer_relations note:** 60,373 rows (50.4%) reference pre-2020 employer_ids excluded by the dedup date filter (`WHERE latest_notice_date >= '2020-01-01'`). These are real historical relationships, not errors. JOINs to `f7_employers_deduped` will only show post-2020 active relationships (~59K rows).

**Common gotchas:**
- Contract tables (`ny_state_contracts`, `nyc_contracts`) have NO EIN values - use `vendor_name_normalized` for matching
- `mergent_employers.ein` has ~55% coverage - not reliable for joins
- Always sample 5-10 rows from each table to verify join keys before building matching logic
- F7 uses `employer_name_aggressive` (not `employer_name_normalized`) for fuzzy matching
- F7 has NO `ein` column — match to SEC/GLEIF via name+state only
- GLEIF ownership joins use `statementid` (UUID), NOT `_link` (numeric row ID)
- SEC `lei` coverage is very low (409/517K) — LEI matching mainly useful for GLEIF↔SEC enrichment
- For large GLEIF queries, avoid correlated subqueries — use 2-step INSERT+UPDATE instead

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
py -m uvicorn api.main:app --reload --port 8001
```

Open `files/organizer_v5.html` in browser.
API docs: http://localhost:8001/docs

---

## Session Log

See `docs/session-summaries/SESSION_LOG_2026.md` for full session history.
