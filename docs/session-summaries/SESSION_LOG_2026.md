# Session Log - 2026

Extracted from CLAUDE.md during project cleanup (2026-02-06).

### 2026-02-06 (Union Discovery Pipeline)
**Tasks:** Discover organizing events missing from database, cross-check against existing tables, insert genuinely new records

**Pipeline:** 3-script approach: catalog -> crosscheck -> insert

**Script 1: `scripts/discovery/catalog_research_events.py`**
- Hard-coded 99 qualifying organizing events from 5 research agents:
  - NY Discovery & Gap Analysis (26 events)
  - Construction/Mfg/Retail NAICS 23,31,44 (16 events)
  - Transport/Tech/Professional NAICS 48,51,54 (13 events)
  - Education/Healthcare NAICS 61,62 (22 events)
  - Arts/Hospitality NAICS 71,72 (14 events) + Additional (8 events)
- Excluded: worker centers, contract renegotiations, failed elections (Mercedes-Benz), withdrawn petitions (SHoP Architects)
- Output: `data/organizing_events_catalog.csv`

**Script 2: `scripts/discovery/crosscheck_events.py`**
- Cross-checked 99 events against 5 database tables:
  - `manual_employers` (432 records) - normalized name + state
  - `f7_employers_deduped` (63K) - aggressive name + state, partial prefix
  - `nlrb_elections` + `nlrb_participants` (33K) - employer participant name + state
  - `nlrb_voluntary_recognition` - normalized name + state
  - `mergent_employers` (14K) - normalized name + state

**Cross-check Results:**
| Status | Count | Workers | Description |
|--------|-------|---------|-------------|
| NEW | 77 | 174,357 | Not found anywhere -> insert |
| IN_F7 | 16 | 17,110 | Already has union contract |
| IN_NLRB | 4 | 13,280 | Election in NLRB data |
| IN_VR | 1 | 25 | In voluntary recognition |
| ALREADY_MANUAL | 1 | 4,000 | Already in manual_employers |

**Script 3: `scripts/discovery/insert_new_events.py`**
- Inserted 77 NEW records into `manual_employers` (432 -> 509)
- 84% union-linked (65/77 matched to unions_master via aff_abbr + state)
- Union linkage strategy: exact local -> largest local in state -> largest national

**Key New Records:**
| Category | Records | Workers | Notable |
|----------|---------|---------|---------|
| NY PERB farm certs (UFW) | 7 | 360 | 100% gap - state jurisdiction only |
| Video game unions (CWA) | 9 | 2,006 | Microsoft/ABK neutrality wave |
| Grad student unions (UAW) | 12 | 42,600 | Stanford, Yale, Northwestern, etc. |
| Museum AFSCME wave | 1 | 300 | LACMA (others already in F7) |
| Cannabis (RWDSU Local 338) | 1 | 600 | NY LPA framework |
| Healthcare nurses | 0 | - | Corewell, Sharp already in F7/NLRB |
| Retail (REI, Apple, H&M) | 7 | 1,320 | RWDSU, IAM, CWA |
| Amazon/Starbucks | 3 | 22,084 | JFK8->IBT, aggregate stores |
| Home health HHWA (1199SEIU) | 1 | 6,700 | Controversial rapid recognition |

**Affiliation Distribution (inserted):**
| Affiliation | Records | Workers |
|-------------|---------|---------|
| UAW | 22 | 75,050 |
| CWA | 15 | 4,528 |
| UNAFF | 12 | 7,490 |
| RWDSU | 6 | 2,100 |
| SEIU | 5 | 60,200 |
| IBT | 4 | 8,209 |
| WU | 3 | 14,300 |
| Other | 10 | 2,480 |

**Affiliation Code Notes:**
- UNITE HERE stored as `UNITHE` in unions_master (128 records), NOT `UNITEHERE`
- SAG-AFTRA stored as `SAGAFTRA` (26) and `AFTRA` (29)
- UFW not in unions_master - farm workers used `UNAFF` code
- WGA East used `UNAFF` code (not in unions_master as separate aff_abbr)

**Status:** Complete. Sector views refreshed.

### 2026-02-06 (NAICS Enrichment from OSHA Matches)
**Tasks:** Fill missing NAICS codes in f7_employers_deduped using OSHA match data

**Problem:** 9,192 F7 employers had `naics_source = 'NONE'`. Of those, 1,239 had OSHA matches with valid NAICS codes that could be transferred.

**Results:**
| Metric | Before | After | Change |
|--------|--------|-------|--------|
| OSHA-sourced NAICS | 20,090 | 21,329 | +1,239 |
| No NAICS (NONE) | 9,192 | 7,953 | -1,239 |

**Status:** Complete. 0 remaining enrichable records.

### 2026-02-06 (F7 Data Quality Cleanup)
**Tasks:** Audit and clean up f7_employers_deduped (63,118 records) and mergent_employers (14,240 records)

**Phase 1 Audits (4 parallel scripts):**
- **Name Quality:** 29 empty `employer_name_aggressive`, 428 short names, 211 case mismatch JOIN losses
- **Duplicates:** 420 duplicate groups (234 true dups, 142 multi-location, 44 generic names)
- **Coverage Gaps:** 257 missing street, 16,361 missing geocodes, 9,192 no NAICS
- **Metadata:** 25 unionized museum records with stale `score_priority`

**Phase 2 Fixes Applied:**
| Fix | Records | Impact |
|-----|---------|--------|
| Lowercase mergent `company_name_normalized` | 14,238 | Unlocked 211 case-sensitive JOIN matches |
| NULL `score_priority` for unionized records | 25 | Museums sector cleaned |
| Flag empty/short aggressive names | 457 | Data quality flags added |
| NormalizedMatcher case-insensitive fix | - | Added `LOWER()` for robust matching |

**Remaining Enrichment Opportunities:**
- 211 addresses recoverable from lm_data
- 16,104 geocodable records (have address but no lat/lon)
- 234 true duplicate groups need human review

**Status:** Complete. All verifications passed. Sector views refreshed.

### 2026-02-06 (Full Matching Run - All 9 Scenarios)
**Tasks:** Run all unified matching scenarios at full scale

**Results:**
| Scenario | Source | Matched | Rate | Tiers |
|----------|--------|---------|------|-------|
| nlrb_to_f7 | 114,980 | 16,949 | 14.7% | NORM: 12,617, ADDR: 4,141, AGG: 191 |
| osha_to_f7 | 1,007,217 | 32,994 | 3.3% | NORM: 25,725, ADDR: 6,792, AGG: 477 |
| mergent_to_f7 | 14,240 | ~850 | ~6% | Mixed |
| mergent_to_990 | 14,240 | 4,336 | 30.4% | EIN: 3,824, NORM: 512 |
| mergent_to_nlrb | 14,240 | 304 | 2.1% | NORM: 274, AGG: 30 |
| mergent_to_osha | 14,240 | ~600 | ~4% | Mixed |

**Performance Notes:**
- Bulk-load + in-memory hash join: OSHA 1M records in 72 seconds (~14K rec/s)
- Address matching (Tier 3) contributed 24% of NLRB matches and 21% of OSHA matches

**Status:** Complete. All 9 scenarios run successfully.

### 2026-02-05 (NY Sub-County Density Recalibration)
**Tasks:** Recalibrate NY county/ZIP/tract density estimates to match CPS statewide targets

**Solution:** Simplified to match national county model:
1. Removed `private_in_public_industries` adjustment entirely
2. Use only 10 BLS private industry rates (exclude edu/health and public admin)
3. Auto-calibrate multiplier: `12.4% / avg_expected` = 2.2618x

**Results (Before -> After):**
| Metric | Before | After |
|--------|--------|-------|
| Climate multiplier | 2.40x (hardcoded) | 2.26x (auto-calibrated) |
| County avg private | 13.7% | 12.4% (matches CPS) |

**Status:** Complete. All 62 counties, 1,826 ZIPs, 5,411 tracts recalculated.

### 2026-02-05 (Sibling Union Bonus Fix)
**Tasks:** Fix sibling union bonus misclassifications across all sectors

**Problem:** Two bugs in name match at different address:
1. Same-address matches where formatting differences made identical locations appear different
2. Cross-state false positives where name matched F-7 employer in different state

**Fix Results:**
| Fix Type | Count | Action |
|----------|-------|--------|
| Same-address (all sectors) | 61 | Moved to has_union=TRUE |
| Cross-state false positives | 40 | Removed sibling bonus |
| Legitimate siblings (kept) | 102 | No change |

**Status:** Complete. Views refreshed.

### 2026-02-05 (NY Sub-County Density Estimates)
**Tasks:** Implement NY union density estimates at county, ZIP, and census tract levels

**Database Tables Created:**
- `ny_county_density_estimates` - 62 NY counties
- `ny_zip_density_estimates` - 1,826 NY ZIP codes
- `ny_tract_density_estimates` - 5,411 NY census tracts

**Key Results:**
| Level | Records | Avg Total | Avg Private |
|-------|---------|-----------|-------------|
| County | 62 | 20.2% | 12.4% |
| ZIP | 1,826 | 18.7% | 11.5% |
| Tract | 5,411 | 18.6% | 11.7% |

**Status:** Complete.

### 2026-02-05 (Industry-Weighted Density Analysis)
**Tasks:** Calculate expected private sector union density by state based on industry composition

**Database Tables Created:**
- `bls_industry_density` - 12 BLS 2024 industry union density rates
- `state_industry_shares` - 51 state industry compositions (ACS 2025)
- `county_industry_shares` - 3,144 county industry compositions
- `state_industry_density_comparison` - Expected vs actual with climate multiplier

**Key Results:** Top states: HI (2.51x), NY (2.40x), WA (2.12x). Bottom: SD (0.28x), AR (0.33x), SC (0.35x).

**Methodology Decision:** Excluded edu/health from private sector weighting (avoids double-counting with public sector). Hybrid approach tested, minimal improvement (-0.07% avg difference).

**Status:** Complete. All 51 states and 3,144 counties have industry-adjusted estimates.

### 2026-02-05 (Address Matching Tier)
**Tasks:** Add address-based matching as Tier 3 in unified matching module

- Uses pg_trgm `similarity()` for fuzzy name matching (>=0.4 threshold)
- Uses PostgreSQL regex for street number matching
- Contributed 24% of NLRB matches and 21% of OSHA matches

**Status:** Complete. 5-tier pipeline operational.

### 2026-02-05 (Public Sector Density Estimation)
**Tasks:** Estimate missing public sector union density for 25 states with small CPS samples

**Algorithm:** `Public_Density = (Total_Density - Private_Share * Private_Density) / Public_Share`

- All 51 states now have public sector density (was 26/51)
- County density calculated for 3,144 counties using govt-level decomposition

**Status:** Complete

### 2026-02-04 (Unified Matching Module)
**Tasks:** Create unified employer matching module with multi-tier pipeline

**5-Tier Pipeline:** EIN -> Normalized -> Address -> Aggressive -> Fuzzy
- 9 predefined scenarios, CLI interface, diff reporting
- Module: `scripts/matching/`

**Status:** Complete. Module tested and working.

### 2026-02-04 (Score Reasons)
**Tasks:** Add Score Reason Explanations to Organizing Scorecard
- Human-readable explanations for all 7 score components in detail view

**Status:** Complete.

### 2026-02-04 (Multi-Sector Scorecard Pipeline)
**Tasks:** Process all 11 sectors through Mergent scoring pipeline
- 14,240 employers loaded, 221 unionized, 13,958 non-union targets scored
- 33 database views created (3 per sector)
- Generic sector API endpoints added

**Status:** Complete.

### 2026-02-04 (Scoring Methodology Overhaul)
**Tasks:** Remove geographic score, add BLS industry density, fix contract matching, add labor violations

**Changes:**
- Removed geographic score (was 0-15)
- Industry density now uses BLS NAICS data (0-10)
- NLRB momentum by 2-digit NAICS (0-10)
- Contract matching fixed: EIN -> normalized name ($54.9B matched)
- Labor violations added (0-10 from NYC Comptroller)
- New max score: 62 pts. Tiers: TOP>=30, HIGH>=25, MEDIUM>=15, LOW<15

**Status:** Complete.

### 2025-02-04 (Museum Sector Scorecard)
**Tasks:** Museum sector organizing scorecard - initial pipeline
- `ny_990_filers` table (37,480), `mergent_employers` table (243 museums)
- Museum organizing views created

**Status:** Complete.

### 2025-02-03 (AFSCME NY Reconciliation)
**Tasks:** AFSCME NY locals reconciliation and duplicate verification
- AFSCME NY deduplicated total: 339,990 members
- DC designations aggregate locals (double-counting risk)

**Status:** Completed
