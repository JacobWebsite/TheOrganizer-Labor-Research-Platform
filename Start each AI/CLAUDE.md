# Labor Relations Research Platform - Claude Context

> **Document Purpose:** Technical implementation reference — schema, gotchas, matching details, API reference, dev workflow. For project status, see `PROJECT_STATE.md`. For the plan, see `UNIFIED_ROADMAP_2026_02_19.md`. For redesign decisions (scoring, React, UX), see `UNIFIED_PLATFORM_REDESIGN_SPEC.md`. For file locations, see `PROJECT_DIRECTORY.md`.

## Quick Reference
**Last Updated:** 2026-02-21 (Reconciled with UNIFIED_PLATFORM_REDESIGN_SPEC.md. 456 tests, 1 known failure. All B4 re-runs complete. Numbers aligned across all project documents.)

**Start here:** Read `PROJECT_STATE.md` for quick start, DB inventory, known issues, and recent decisions. Read `PIPELINE_MANIFEST.md` for the active script manifest.

### Database Connection
```python
from db_config import get_connection
conn = get_connection()
```
Credentials are in `.env` at project root. The `db_config.py` module (project root) is imported by all scripts — never use inline `psycopg2.connect()` with hardcoded credentials.

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
| F7 Employers | 146,863 | - | 67,552 post-2020 + 79,311 historical |

### Project Directory Structure

```
labor-data-project/
├── api/                        # FastAPI backend (20 routers + middleware + auth)
│   └── routers/                # 20 router files (scorecard.py, health.py, profile.py added post-2026-02-17)
├── files/                      # Frontend (organizer_v5.html + 21 JS + 1 CSS)
│   ├── css/
│   └── js/
├── scripts/
│   ├── etl/           (24)     # Stage 1: Data loading (OSHA, WHD, SAM, SEC, BLS, etc.)
│   ├── matching/      (30)     # Stage 2: Record linkage (deterministic + Splink)
│   │   ├── adapters/  (7)      # Source-specific data loaders
│   │   └── matchers/  (5)      # Matching algorithm implementations
│   ├── scoring/       (4)      # Stage 3: Score computation (MV, Gower, NLRB)
│   ├── ml/            (4)      # Stage 3: Machine learning (propensity model)
│   ├── maintenance/   (3)      # Stage 4: Periodic refresh + DB inventory
│   ├── scraper/       (7)      # Stage 5: Web intelligence (AFSCME)
│   ├── analysis/      (52)     # Ad-hoc analysis templates (not pipeline; 5 groups of versioned duplicates exist)
│   ├── setup/         (1)      # Database initialization
│   └── performance/   (1)      # Performance profiling
├── src/python/matching/        # Shared library (name_normalization.py)
├── tests/                      # 457 automated tests (456 pass, 1 known failure: test_expands_hospital_abbreviation)
├── docs/                       # Documentation and audit reports
├── sql/                        # SQL scripts
├── data/                       # Small reference files (NAICS crosswalks, EPI benchmarks)
├── archive/                    # Everything archived (not deleted)
│   ├── old_scripts/            # Dead/superseded scripts (~400 files)
│   ├── old_api/                # Dead API monoliths
│   ├── old_roadmaps/           # Superseded roadmap versions
│   ├── old_docs/               # Consolidated docs
│   ├── imported_data/          # Data files already in PostgreSQL (~8.5 GB)
│   └── ...                     # Other archived artifacts
├── db_config.py                # Shared DB connection (imported by all scripts)
├── .env                        # Credentials (never commit)
├── CLAUDE.md                   # This file
├── PROJECT_STATE.md            # Shared AI context (DB inventory, status, decisions)
├── PIPELINE_MANIFEST.md        # Active script manifest (69 pipeline + 51 analysis)
├── UNIFIED_ROADMAP_2026_02_19.md  # Single source of truth for roadmap
├── UNIFIED_PLATFORM_REDESIGN_SPEC.md  # Platform redesign specification (scoring, React, UX)
└── README.md
```

**Key organizational rules:**
- `PIPELINE_MANIFEST.md` lists every active script. If it's not there, it's archived.
- `archive/` holds everything moved during reorganization — nothing was permanently deleted.
- `db_config.py` stays at project root (500+ imports depend on it).
- All old roadmaps are in `archive/old_roadmaps/` — only `UNIFIED_ROADMAP_2026_02_19.md` is current.

---

## Database Schema

### Core Tables
| Table | Records | Description |
|-------|---------|-------------|
| `unions_master` | 26,665 | OLMS union filings (has local_number field) |
| `f7_employers_deduped` | 146,863 | Private sector employers (67,552 post-2020 + 79,311 historical pre-2020) |
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
| `osha_f7_matches` | 145,134 | Linkages to F-7 employers (14.4% of OSHA establishments) |
| `v_osha_organizing_targets` | - | Organizing target view |

### WHD Tables (Wage & Hour Division - National)
| Table | Records | Description |
|-------|---------|-------------|
| `whd_cases` | 363,365 | National WHISARD wage violation cases (2005-2025) |
| `mv_whd_employer_agg` | 330,419 | Aggregated WHD by employer (name+city+state) |

**Key columns:** `case_id`, `trade_name`, `legal_name`, `name_normalized`, `city`, `state`, `naics_code`, `total_violations`, `civil_penalties`, `backwages_amount`, `employees_violated`, `flsa_repeat_violator`, `flsa_child_labor_violations`, `findings_start_date`, `findings_end_date`

**Match coverage:** F7: 26,312 via `whd_f7_matches`, Mergent: 1,170 (2.1%). Total backwages: $4.7B, penalties: $361M

### Match Tables
| Table | Records | Description |
|-------|---------|-------------|
| `osha_f7_matches` | 145,134 | OSHA-to-F7 employer matches (6-tier deterministic + fuzzy) |
| `whd_f7_matches` | 26,312 | WHD-to-F7 employer matches (PK: f7_employer_id, case_id) |
| `national_990_f7_matches` | 14,428 | 990-to-F7 employer matches (PK: f7_employer_id, ein) |
| `sam_f7_matches` | 15,010 | SAM-to-F7 employer matches (PK: f7_employer_id, uei) |
| `nlrb_employer_xref` | 179,275 | NLRB-to-F7 cross-reference |
| `employer_comparables` | 269,810 | Gower similarity results (5 comparables per employer) |

### Phase 3-5 Tables (Added Feb 2026)
| Table | Records | Description |
|-------|---------|-------------|
| `unified_match_log` | 1,738,115 | Central audit trail for all matches (source, tier, confidence, evidence JSONB). ⚠️ NLRB confidence scale was normalized to 0.0-1.0 (2026-02-19). |
| `employer_canonical_groups` | 16,209 groups | Canonical employer grouping (40,304 employers, 403 cross-state) |
| `historical_merge_candidates` | 5,128 | Historical employer merge candidates (2,124 exact + 3,004 aggressive) |
| `score_versions` | - | Score methodology version tracking (auto-insert on create/refresh) |
| `ml_model_versions` | - | ML model metadata (partial unique index on is_active) |
| `ml_election_propensity_scores` | 146,693 | NLRB election propensity scores (unique on employer_id+model_name) |
| `bls_national_industry_density` | 9 | BLS national industry union density rates |
| `bls_state_density` | 51 | BLS state-level union density |
| `estimated_state_industry_density` | 459 | State x industry density estimates (national_rate x state_multiplier) |
| `bls_industry_occupation_matrix` | 67,699 | BLS occupation-industry staffing patterns (422 industries x 832 occupations) |
| `occupation_similarity` | 8,731 | Cosine similarity between occupations (threshold >= 0.30) |
| `industry_occupation_overlap` | 130,638 | Weighted Jaccard industry overlap (threshold >= 0.05) |
| `naics_to_bls_industry` | 2,035 | NAICS code to BLS industry mapping |

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

### Unified Employer Tables (Legacy)
| Table | Records | Description |
|-------|---------|-------------|
| `unified_employers_osha` | 100,768 | All employer sources combined (legacy, pre-Phase 3) |
| `osha_unified_matches` | 42,812 | OSHA matches to unified employers (legacy) |

**Note:** These legacy tables predate the Phase 3 matching pipeline overhaul. The current matching system uses `unified_match_log` (**1,738,115 entries**) as the central audit trail and `osha_f7_matches` / `whd_f7_matches` / etc. as the active match tables. Legacy match tables were **rebuilt from UML** on 2026-02-20: osha(97,142), sam(28,816), 990(20,005), whd(19,462), nlrb_xref(13,031).

### Corporate Hierarchy Tables
| Table | Records | Description |
|-------|---------|-------------|
| `sec_companies` | 517,403 | SEC EDGAR company registry (CIK, EIN, LEI, ticker) |
| `gleif_us_entities` | 379,192 | GLEIF/Open Ownership US entities (100% with LEI) |
| `gleif_ownership_links` | 498,963 | GLEIF parent→child ownership links |
| `corporate_identifier_crosswalk` | 25,177 | Unified ID mapping across SEC/GLEIF/Mergent/F7/USASpending/SAM/990 |
| ~~`splink_match_results`~~ | 0 rows | Was replaced by `unified_match_log`. Table still exists in DB but is empty and unused. Should be dropped. |
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
| F7 | ~12,000 | 146,863 | 8.2% |
| Federal contractors | 9,305 | 47,193 | 19.7% |
| Public companies | 358 | - | - |

**Corporate Hierarchy Sources:**
| Source | Links | Description |
|--------|-------|-------------|
| GLEIF | 116,531 | Both-US ownership (direct/indirect/unknown) |
| Mergent parent_duns | 7,404 | Direct parent->child |
| Mergent domestic_parent | 1,185 | Domestic ultimate parent |
| **Total** | **125,120** | 13,929 distinct parents, 54,924 distinct children |

**ETL/Matching Scripts:** See `PIPELINE_MANIFEST.md` for the complete active script inventory with run order and dependencies.

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

**Scripts:** See Stage 5 in `PIPELINE_MANIFEST.md` for the full web scraping pipeline.

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
- `organizing_score` - [LEGACY] Composite score (0-62 Mergent-specific scale, superseded by `mv_organizing_scorecard` 0-80 unified scale)
- `score_priority` - Tier: TOP, HIGH, MEDIUM, LOW

**Match Columns:**
- `ny990_id`, `ny990_employees`, `ny990_revenue`, `ny990_match_method`
- `matched_f7_employer_id`, `f7_union_name`, `f7_union_fnum`
- `osha_establishment_id`, `osha_violation_count`, `osha_total_penalties`
- `nlrb_case_number`, `nlrb_election_date`, `nlrb_union_won`
- `whd_violation_count`, `whd_backwages`, `whd_employees_violated`

**Score Columns (LEGACY Mergent-specific -- superseded by unified MV scorecard):**
- `score_geographic` (removed - set to 0), `score_size` (0-5), `score_industry_density` (0-10 BLS)
- `score_nlrb_momentum` (0-10 by NAICS), `score_osha_violations` (0-4), `score_govt_contracts` (0-15)
- `score_labor_violations` (0-10 NYC Comptroller), `sibling_union_bonus` (0-8)
- Max score: 62 pts | Tiers: TOP >=30, HIGH >=25, MEDIUM >=20, LOW <20
- **Current unified scorecard:** `mv_organizing_scorecard` -- 8 active factors, each 0-10, max 80 pts, observed range 12-54. See Key Features #1 above.

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
**Organizing:** `/api/organizing/{summary,by-state}`, `/scorecard`, `/scorecard/{estab_id}`, `/siblings/{estab_id}`, `/propensity/{employer_id}`
**Sectors (21):** `/api/sectors/list`, `/{sector}/{summary,targets,targets/stats,targets/{id},targets/cities,unionized}`
**Museums (Legacy):** `/api/museums/{summary,targets,targets/stats,targets/cities,targets/{id},unionized}`
**Trends:** `/api/trends/{national,sectors,elections}`, `/by-state/{state}`, `/by-affiliation/{aff}`
**Multi-Employer:** `/api/multi-employer/{stats,groups}`, `/employer/{id}/agreement`
**Corporate:** `/api/corporate/family/{id}`, `/corporate/hierarchy/{id}`, `/corporate/hierarchy/stats`, `/corporate/hierarchy/search`, `/corporate/sec/{cik}`
**Projections:** `/api/projections/{summary,search,top}`, `/industry/{naics}`, `/matrix/{code}`, `/employer/{id}/projections`
**Density:** `/api/density/{all,by-state,by-county,county-summary,industry-rates}`, `/by-state/{state}/{history,counties}`, `/by-govt-level`, `/by-county/{fips}/{industry}`, `/state-industry-comparison/{state}`, `/naics/{code}`
**NY Density:** `/api/density/ny/{summary,counties,zips,tracts}`, `/county/{fips}`, `/zip/{code}`, `/tract/{fips}`
**NAICS:** `/api/naics/stats`
**Admin:** `/api/admin/refresh-scorecard` (POST), `/data-freshness`, `/refresh-freshness` (POST), `/score-versions`, `/match-quality`, `/match-review`, `/match-review/{id}` (POST), `/propensity-models`, `/employer-groups`

---

## Key Features (What Exists - Don't Rebuild)

1. **OSHA Organizing Scorecard** - [LEGACY — see `UNIFIED_PLATFORM_REDESIGN_SPEC.md` Section 2 for the redesigned 8-factor weighted scoring system with percentile-based tiers (Priority/Strong/Promising/Moderate/Low)] Current MV: 8 active factors (of 9 in MV -- company_unions always 0), each max 10 pts, theoretical max 80, observed range 12-54 with temporal decay, avg 31.9. Via `/api/organizing/scorecard`. Factors: industry_density (10), geographic (10), size (10), osha (10, with temporal decay), nlrb (10), contracts (10), projections (10), similarity (10). Tiers: TOP>=30, HIGH>=25, MEDIUM>=20, LOW<20.
2. **AFSCME NY Organizing Targets** - [LEGACY] 5,428 targets from 990 + contract data, $18.35B funding. Uses old Mergent-specific scoring (0-62 scale), not the current unified MV scorecard.
3. **Geographic Analysis** - MSA/metro density, city search, CBSA mapping (40.8%)
4. **Membership Deduplication** - 70.1M raw -> 14.5M deduplicated (matches BLS within 1.5%)
5. **Historical Trends** - 16 years OLMS LM filings (2010-2024), Chart.js visualizations
6. **Public Sector Coverage** - 98.3% of EPI benchmark, 50/51 states within +/-15%
7. **Multi-Sector Organizing Scorecard** - [LEGACY Mergent-specific] 56,426 Mergent employers, 21 sectors, 62 pts max. Superseded by unified `mv_organizing_scorecard` (22,389 rows, 8 factors, 80 pts max). Legacy components: size (5), industry density (10), NLRB momentum (10), OSHA (4), contracts (15), labor violations (10), sibling bonus (8). See `docs/METHODOLOGY_SUMMARY_v8.md` for historical methodology
8. **Industry Outlook** - BLS 2024-2034 projections in employer detail, 6-digit NAICS from OSHA, occupation breakdowns
9. **Corporate Hierarchy** - SEC EDGAR (517K), GLEIF (379K entities, 499K ownership links), crosswalk linking SEC/GLEIF/Mergent/F7/USASpending/SAM/990 (25,177 rows: deterministic + Splink + USASpending + SAM + 990), hierarchy with 125K parent->child links from 13,929 distinct parent companies. QCEW industry density scores for 121K F7 employers. 9,305 F7 employers identified as federal contractors with scoring (0-15 pts).

---

## Frontend Interfaces

| File | Purpose |
|------|---------|
| **`files/organizer_v5.html`** | **PRIMARY FRONTEND - All new features go here** |

**IMPORTANT:** The current frontend is `files/organizer_v5.html` (vanilla JS). A full React + Vite migration is planned — see `UNIFIED_PLATFORM_REDESIGN_SPEC.md` Section 5 for the React implementation plan (shadcn/ui, Zustand, TanStack Query). Legacy frontends archived to `archive/frontend/`.

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
| `UNIFIED_ROADMAP_2026_02_19.md` | **Current roadmap** — supersedes ALL prior roadmaps (archived in `archive/old_roadmaps/`) |
| `UNIFIED_PLATFORM_REDESIGN_SPEC.md` | **Platform redesign spec** — scoring (8 factors, weighted), React/Vite frontend, UX design, page layouts, task list. Supersedes scoring and frontend sections in the Roadmap. |
| `PROJECT_STATE.md` | Shared AI context — quick start, DB inventory, status, decisions, design rationale |
| `PIPELINE_MANIFEST.md` | Active script manifest — every pipeline script, what it does, when to run it |
| `docs/METHODOLOGY_SUMMARY_v8.md` | Complete methodology reference |
| `docs/EPI_BENCHMARK_METHODOLOGY.md` | EPI benchmark explanation |
| `docs/PUBLIC_SECTOR_SCHEMA_DOCS.md` | Public sector schema reference |
| `docs/AFSCME_NY_CASE_STUDY.md` | Organizing targets feature docs |
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

### 5-Tier Matching Pipeline (Legacy — `scripts/matching/pipeline.py`)

Used for NLRB, Mergent, VR, and contract scenarios via `scripts/matching/cli.py`.

| Tier | Method | Score | Confidence | Speed |
|------|--------|-------|------------|-------|
| 1 | EIN exact | 1.0 | HIGH | Fast |
| 2 | Normalized name + state | 1.0 | HIGH | Fast |
| 3 | Address (fuzzy name + street # + city + state) | 0.4+ | HIGH | Medium |
| 4 | Aggressive name + city | 0.95 | MEDIUM | Medium |
| 5 | Trigram fuzzy + state | 0.65+ | LOW | Slow |

### 6-Tier Deterministic Matcher v4 (`scripts/matching/deterministic_matcher.py`)

Used for OSHA, WHD, 990, SAM, SEC, BMF via `scripts/matching/run_deterministic.py`. Best-match-wins (keeps highest tier per source record).

| Tier | Method | Rank | Band | Speed |
|------|--------|------|------|-------|
| 1 | EIN exact | 100 | HIGH | Fast |
| 2 | Name + city + state exact | 90 | HIGH | Fast |
| 3 | Name + state exact | 80 | HIGH | Fast |
| 4 | Aggressive name + state | 60 | MEDIUM | Fast |
| 5a | Splink probabilistic (adaptive fuzzy model + name floor >= 0.70) | 45 | MEDIUM | Medium |
| 5b | Trigram pg_trgm (fallback for Splink misses) | 40 | LOW | Slow |

**Splink calibration note:** The pre-trained model overweights geography (state+city+zip BF ~8.5M). A `rapidfuzz.fuzz.token_sort_ratio >= 0.70` post-filter is required to prevent false positives (was 0.65 before 2026-02-19, configurable via `MATCH_MIN_NAME_SIM`). Without it, match rate inflates from ~4% to ~81%.

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
  config.py                    # MatchConfig, SCENARIOS, tier thresholds
  normalizer.py                # Unified normalization (standard/aggressive/fuzzy)
  pipeline.py                  # MatchPipeline orchestrator
  differ.py                    # Diff report generation
  cli.py                       # Command-line interface
  deterministic_matcher.py     # [Phase 3+B] Core v4 batch-optimized matcher (6-tier cascade, best-match-wins, Splink tier 5a)
  run_deterministic.py         # [Phase 3] CLI runner: osha|whd|990|sam|sec|all
  create_unified_match_log.py  # [Phase 3] Unified match log table creation
  match_quality_report.py      # [Phase 3] Match quality metrics generator
  resolve_historical_employers.py  # [Phase 3] Historical employer resolution
  build_employer_groups.py     # [Phase 3] Canonical employer grouping
  create_nlrb_bridge.py        # [Phase 3] v_nlrb_employer_history view
  splink_pipeline.py           # [Phase 3] Splink v2 probabilistic matching (DuckDB)
  splink_config.py             # Splink scenario configs
  matchers/
    base.py          # MatchResult, BaseMatcher
    exact.py         # EIN, Normalized, Aggressive matchers
    address.py       # Address matcher (fuzzy name + street number)
    fuzzy.py         # Trigram pg_trgm matcher
  adapters/
    osha_adapter.py            # [Phase 3] OSHA source adapter
    whd_adapter.py             # [Phase 3] WHD source adapter
    n990_adapter.py            # [Phase 3] 990 source adapter
    sam_adapter.py             # [Phase 3] SAM source adapter
    sec_adapter_module.py      # [Phase 4] SEC EDGAR adapter
    bmf_adapter_module.py      # [Phase 4] IRS BMF adapter
```

**Canonical name normalization:** `src/python/matching/name_normalization.py` -- 3 levels + soundex + metaphone + phonetic_similarity. 30+ abbreviation mappings.

---

## Data Operations

When matching records between tables/datasets, always verify the join key exists in both sources before implementing. Check for null/empty values in join columns first.

**Archived source data** (in `archive/imported_data/`):
- `990/990_2025_archive.7z` — 650K IRS Form 990 XML files (1.2 GB). Already loaded into `national_990_filers` and `employers_990_deduped`.
- `backup_20260209.dump.7z` — PostgreSQL backup (2.0 GB). Recreatable with `pg_dump`.
- `whd/`, `lm2/`, `nlrb/` — Source data files already imported into PostgreSQL.
- See `archive/imported_data/` for full list of archived data.

**Match quality flags:**
- `osha_f7_matches.low_confidence` — TRUE for 32,243 matches (23.3%) with match_confidence < 0.6
- `whd_f7_matches.low_confidence` — TRUE for 6,657 matches (27.0%) with match_confidence < 0.6

**f7_union_employer_relations note:** Orphan issue FIXED (Feb 14 2026, confirmed 2026-02-19 audit). Previously 60,373 rows (50.4%) were orphaned. Fix: 3,531 repointed to existing deduped employers, 52,760 historical pre-2020 employers inserted into f7_employers_deduped. Orphan rate now 0%. All 119,445 relations (not 119,832 — confirmed by audit) resolve via JOIN. Column for covered workers is `bargaining_unit_size`, not `workers_covered`.

⚠️ **CRITICAL DATA QUALITY WARNINGS — Read before working with matches or scores:**

1. **NLRB confidence scale bug:** NLRB matches in `unified_match_log` store `confidence_score` as 90 or 98 (integer). All other sources use 0.0–1.0 (decimal). Never compare confidence scores across sources that include NLRB without first dividing NLRB scores by 100. Fix pending: `UPDATE unified_match_log SET confidence_score = confidence_score / 100.0 WHERE source_system = 'nlrb' AND confidence_score > 1.0;`

2. **Legacy match tables are out of sync:** `osha_f7_matches`, `sam_f7_matches`, `national_990_f7_matches` do not match the active counts in `unified_match_log`. Use `unified_match_log WHERE status = 'active'` as the authoritative source for match counts until legacy tables are rebuilt post re-run.

3. **PostgreSQL statistics are stale:** 168 of 174 tables show 0 live rows to the query planner. Run `ANALYZE` on all tables before performance-sensitive work. Query plans may be suboptimal until this is done.

4. **BLS financial factor inverted logic:** In `build_unified_scorecard.py`, an employer with NO BLS industry data gets `score_financial = 2`. An employer WITH data showing 0% growth gets `score_financial = 1`. This is backwards — no data scores higher than confirmed stagnation. Fix pending.

5. **IRS BMF has 25 rows:** `irs_bmf` contains a test load of 25 records, not the ~1.8M expected. Do not use for matching until the full dataset is loaded.

6. **Splink disambiguation missing name floor:** The `_splink_disambiguate()` function in `deterministic_matcher.py` does not enforce the `token_sort_ratio >= 0.70` name similarity floor. False positives can slip through via geographic overweighting during collision resolution.

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
- `CLAUDE.md` — Scoring Components table
- `PROJECT_STATE.md` — Section 4 if status changes
- `docs/METHODOLOGY_SUMMARY_v8.md` — If methodology fundamentally changes

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

## Folder Reorganization (2026-02-16)

The project was reorganized from 530+ scripts to ~120 active. Key changes:
- **~400 scripts archived** to `archive/old_scripts/` (ETL, matching, scoring, maintenance, root scripts)
- **~8.5 GB data archived** to `archive/imported_data/` (SQLite DBs, CSVs, dumps already in PostgreSQL)
- **64 root Python files** moved to `archive/old_scripts/root_scripts/`
- **17 old roadmaps** moved to `archive/old_roadmaps/`
- **472 .pyc files** deleted from 30 `__pycache__/` directories
- **25 credential patterns fixed** (`os.environ.get` -> `db_config.get_connection`)
- **`PIPELINE_MANIFEST.md`** created — lists every active script with dependencies and run order
- **`PROJECT_STATE.md`** created — shared AI context with auto-generated DB inventory
- **Nothing was permanently deleted** — everything moved to `archive/`
