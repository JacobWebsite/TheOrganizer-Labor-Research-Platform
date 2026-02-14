# Session Log - 2026

Extracted from CLAUDE.md during project cleanup (2026-02-06).

### 2026-02-14 (Audit Remediation + Disk Cleanup)
**Tasks:** Commit audit fixes, compress and archive 990 XML data

**Committed (d543273):** 290 files changed, 5,196 insertions, 8,954 deletions
- **CLAUDE.md:** Fixed 24 inaccuracies — startup command, 13 wrong row counts, added 9 missing table sections, corrected scoring tiers (MEDIUM>=20), removed 2 nonexistent table refs, updated scorecard to 9-factor
- **corporate.py:** Rewrote 5 broken endpoints to use `corporate_identifier_crosswalk` instead of nonexistent columns (`corporate_family_id`, `sec_cik` on `f7_employers_deduped`)
- **258 scripts:** Fixed broken password pattern (`password='os.environ.get(...)'` string literal -> actual function call)
- **organizer_v5.html:** Fixed duplicate HTML IDs, 5 API response shape mismatches, undefined function ref, NLRB search param
- **Deleted dead code:** `api/labor_api_v3.py`, `v4_fixed.py`, `v6.py.bak` (8.4K lines), 2 scripts importing deleted modules

**Disk cleanup:**
- Compressed `990 2025/` (650K XML files, 20 GB) to `990_2025_archive.7z` (1.2 GB, 94% reduction)
- Deleted original directory — **~19 GB recovered**

**Remaining audit issues (not yet addressed):**
1. 60,373 orphaned `f7_union_employer_relations` rows (50.4% of bargaining links)
2. Dead score factors (4/9 always zero for 98.5% of Mergent employers)
3. 14,150 orphaned NLRB xref rows
4. No primary key on `f7_employers_deduped`
5. ~40K low-confidence matches (<0.6)
6. 222 MB duplicate indexes
7. ~37.9 GB additional disk recovery possible (archive/, free_company_dataset.csv, etc.)

---

### 2026-02-13 (Comprehensive Platform Audit)
**Tasks:** Full 8-section audit of the entire platform — database, API, scripts, documentation

**Audit Report:** `docs/AUDIT_REPORT_2026.md` (1,254 lines)

**Platform Health Score: 68/100 — FUNCTIONAL BUT FRAGILE**

| Category | Score |
|----------|-------|
| Data Completeness | 78/100 |
| Data Integrity | 55/100 |
| API Reliability | 88/100 |
| Code Quality | 50/100 |
| Documentation | 30/100 |
| Infrastructure | 55/100 |

**8 Sections Completed:**

1. **Database Table Inventory** — 346 objects (149 tables, 194 views, 3 materialized views), 22 GB total. 6 empty tables. `f7_employers_deduped` has NO primary key. `splink_match_results` largest at 1.6 GB. Autovacuum never ran (stale stats).

2. **Data Quality Deep Dive** — Column-by-column null analysis on 7 core tables. **CRITICAL: 60,373 orphaned rows (50.4%) in `f7_union_employer_relations`** — employer_ids point to pre-dedup IDs, silently dropping half of bargaining links in any JOIN. 1,604 duplicate NLRB case_numbers. Crosswalk covers 37.4% of F7.

3. **Materialized Views & Indexes** — All 3 materialized views working. All 187 regular views working (0 broken). 535 indexes consuming 3.4 GB; **73% never scanned**. 21 confirmed duplicate indexes wasting 176 MB. 257 unused non-unique indexes consuming 2.1 GB. 9 views reference raw `f7_employers` instead of deduped. 67 sector-specific views (36% of all views).

4. **Cross-Reference Integrity** — 61.7% of F7 employers have at least 1 external match. OSHA strongest at 47.3% F7 coverage. Mergent-to-F7 connection nearly nonexistent (1.5%). 14,150 orphaned `nlrb_employer_xref` records (same root cause as #2). Only 5.3% of public sector employers have bargaining units.

5. **API Endpoint Audit** — 144 endpoints across 16 routers. 140 working, **4 broken** (`corporate.py` references nonexistent `corporate_ultimate_parents` table and `corporate_family_id` column). Zero SQL injection vulnerabilities. 98 tables have no API access (15.9M rows invisible to frontend).

6. **File System & Script Inventory** — 778 Python files, 102 SQL. **259 scripts have broken password pattern** (`password='os.environ.get(...)'` as string literal). 1 script has hardcoded password (`nlrb_win_rates.py`). Only 32 scripts use correct `db_config` import. 3 dead API monoliths (348 KB) in active `api/` directory. 71.8 MB of SQL data dumps in archive. All 13 critical path scripts verified present.

7. **Documentation Accuracy** — **CLAUDE.md has 19 factual inaccuracies**: startup command wrong (will fail), 13 wrong row counts (splink off by 1,250x), scoring tiers wrong (>=15 should be >=20), missing 13+ tables and 7+ features. README.md has 12 inaccuracies. Roadmap v12 completely obsolete (all 4 phases described as future work are complete).

8. **Summary & Recommendations** — Top 10 issues ranked by impact. 8 quick wins (<30 min each). Tables that could be dropped (~3.5 GB recoverable). Missing indexes to add. Documentation update priorities.

**Top 3 Issues:**
1. 60,373 orphaned `f7_union_employer_relations` rows (50.4% of bargaining links broken)
2. CLAUDE.md startup command wrong + 19 inaccuracies
3. `f7_employers_deduped` has no primary key

**Also completed:** LM2 vs F7 membership comparison (14.5M LM2 vs 15.8M F7, 108.7% ratio). Three structural patterns: public sector unions invisible to F7, building trades 10-32x over-covered, 195 orphaned F7 file numbers. Script: `scripts/analysis/compare_lm2_vs_f7.py`.

**Status:** Audit complete. Report at `docs/AUDIT_REPORT_2026.md`. No code changes made — audit is read-only.

---

### 2026-02-08 (Phase 5: Data Integrity Sprint - Splink F7 Self-Dedup + Merge)
**Tasks:** Use Splink probabilistic matching for F7 internal deduplication, execute graduated-confidence merges, link multi-location employer groups, run supporting integrity tasks

**Splink F7 Self-Dedup:**
- Added `f7_self_dedup` scenario to `splink_config.py`: dedupe_only mode, 6 comparisons (name JW, state exact, city Levenshtein, ZIP JW, NAICS exact+TF, street JW), 3 prediction blocking rules, 2 EM training rules
- Added `load_self_dedup_data()` and `run_splink_dedup()` to `splink_pipeline.py` for single-DataFrame `Linker([df], settings)` mode
- Ran on 62,100 records: 3.79M candidate pairs, ~21 minutes

**Combined Evidence Rescoring:**
- Created `splink_rescore_pairs.py`: joins pg_trgm pairs (11,815) with Splink results (3.79M) for combined-evidence classification
- Classification tiers: AUTO_MERGE, SPLINK_CONFIRMED, NEW_MATCH, LIKELY_DUPLICATE, MULTI_LOCATION, PGTRGM_ONLY_HIGH/LOW, GEO_ONLY, LOW_CONFIDENCE
- Critical fix: name_level >= 3 for NEW_MATCH produced 3.77M false positives (geographic noise). Raised to name_level >= 4 (JW >= 0.88) -- reduced to 262 legitimate pairs

**Merge Execution (graduated confidence):**
| Batch | Pairs | Merged | Errors | Notes |
|-------|-------|--------|--------|-------|
| TRUE_DUPLICATE | 234 groups | 0 | 0 | Already done in prior session |
| SPLINK_CONFIRMED | 1,079 | 967 | 0 | pg_trgm 0.8-0.9 + Splink >= 0.85 |
| NEW_MATCH | 262 | 243 | 0 | Splink-only discoveries, name_level >= 4 |
| **Total** | **1,575** | **1,210** | **0** | |

- First SPLINK_CONFIRMED attempt failed: crosswalk used `gleif_lei` not `lei`, no `usaspending_uei` column. Fixed and re-ran successfully.
- Employer count: 62,163 -> 60,953 (-1,210)

**Multi-Location Linking:**
- Created `link_multi_location.py`: adds `corporate_parent_id` column, uses union-find for group building
- MULTI_LOCATION classification never triggered (Splink threshold 0.70 means pairs below 0.50 never returned). Fixed by detecting multi-location pattern directly: pg_trgm >= 0.8 + different cities
- Result: 969 employers in 459 groups linked via corporate_parent_id (NO deletes, NO FK changes)

**Crosswalk & Post-Merge:**
- Added crosswalk update step to `merge_f7_enhanced.py`: COALESCE identifiers from deleted into keeper row, then DELETE orphan
- Added crosswalk orphan check to `post_merge_refresh.py`: found 4,964 orphans, auto-fixed 589 via merge log
- BLS coverage: 90.4% (within 90-110% PASS range)

**Supporting Integrity Tasks (Step 7):**
- Union hierarchy audit: 2,104 orphan locals found + flagged
- Sector contamination check: ran successfully
- Geocoding: 35 PO Box centroid records applied (Census API intermittent on batch 1)
- Final validation: 8/8 PASS, 0 orphan references

**Scripts Created/Modified:**
| File | Action |
|------|--------|
| `scripts/matching/splink_config.py` | Modified: added F7_SELF_DEDUP scenario |
| `scripts/matching/splink_pipeline.py` | Modified: added dedupe_only branch |
| `scripts/cleanup/splink_rescore_pairs.py` | **Created**: pg_trgm + Splink evidence join |
| `scripts/cleanup/merge_f7_enhanced.py` | Modified: added crosswalk update + `--source combined` |
| `scripts/cleanup/link_multi_location.py` | **Created**: corporate_parent_id linking |
| `scripts/cleanup/post_merge_refresh.py` | Modified: added crosswalk orphan check |

**Key Lessons:**
- name_level >= 4 (JW >= 0.88) required for Splink-only NEW_MATCH; level 3 only safe with pg_trgm cross-confirmation
- 99%+ of Splink self-dedup pairs are geographic noise (same city/zip, different employers)
- Crosswalk table uses `gleif_lei` (not `lei`), has no `usaspending_uei` column
- MULTI_LOCATION classification requires fallback detection since Splink threshold (0.70) prevents low-prob pairs from being returned

**Status:** Data Integrity Sprint complete. F7 employers: 60,953. 1,210 merges (0 errors). 459 multi-location groups linked. Validation 8/8 PASS. BLS coverage 90.4%.

---

### 2026-02-08 (Phase 3: QCEW + USASpending Data Expansion)
**Tasks:** Integrate BLS QCEW industry density data and USASpending federal contract recipients

**QCEW Integration:**
- Downloaded 4 years of BLS QCEW annual data (2020-2023): 302 MB, 1,943,426 rows
- Created `qcew_industry_density` table: 7,143 state-level NAICS density aggregations
- Built NAICS mapping to handle QCEW hyphenated codes (e.g., "31-33" Manufacturing, "44-45" Retail, "48-49" Transport)
- Created `f7_industry_scores`: 121,433 rows, 97.5% matched to QCEW (118,346 of 121,433)
- All F7 NAICS codes are 2-digit; matched to QCEW level 74 (county-level NAICS sector)
- Top industry: NAICS 62 (Healthcare) with avg 123,820 establishments/state, avg pay $46,540

**USASpending Integration:**
- Bulk download API returned 403 Forbidden; fell back to paginated search API
- Fetched 418,289 FY2024 contract awards across 51 states (~50 min total)
- Extracted 47,193 unique federal contract recipients (100% with UEI)
- Key finding: USASpending has NO EIN (tax-sensitive data) -- the F7->USASpending->EIN bridge won't work
- Exact name+state matching: 2,283 F7 employers identified as federal contractors
- Fuzzy name+state matching (pg_trgm >= 0.55): 7,022 additional matches
- Total F7 federal contractors identified: 9,305

**Federal Contractor Scoring (0-15 pts):**
| Score | Criteria | Count |
|-------|----------|-------|
| 15 | $10M+ obligations | 2,651 |
| 12 | $1M-$10M | 2,455 |
| 9 | $100K-$1M | 2,567 |
| 6 | $10K-$100K | 1,548 |
| 3 | Any contract | 77 |

**Crosswalk Growth (cumulative):**
| Phase | Total | Change |
|-------|-------|--------|
| After Splink (Phase 2) | 5,772 | - |
| **After USASpending (Phase 3)** | **14,561** | **+152%** |

**New crosswalk tiers added:**
- USASPENDING_EXACT_NAME_STATE: 1,994
- USASPENDING_FUZZY_NAME_STATE: 6,795

**Scripts Created:**
- `scripts/etl/fetch_qcew.py` -- Download BLS QCEW annual data
- `scripts/etl/_integrate_qcew.py` -- QCEW industry density scoring for F7
- `scripts/etl/_fetch_usaspending_api.py` -- Paginated USASpending API fetch
- `scripts/etl/_match_usaspending.py` -- USASpending-to-F7 matching and crosswalk integration

**Status:** Phase 3 complete. Crosswalk at 14,561 rows (+383% from initial 3,010 baseline). 9,305 F7 employers identified as federal contractors with scoring.

---

### 2026-02-08 (Phase 2: Splink Probabilistic Matching)
**Tasks:** Integrate Splink 4.0.12 for probabilistic record linkage on unmatched employer records

**Setup:**
- Installed Splink 4.0.12 with DuckDB 1.4.4 backend
- Created `splink_config.py` with scenario definitions (comparisons, blocking rules)
- Created `splink_pipeline.py` with full EM training + prediction pipeline
- Created `splink_integrate.py` for quality filtering and crosswalk integration

**Scenario 1: Mergent -> F7 (54K x 60K)**
- Blocking: state + 3-char name prefix (704K pairs from 378M, 99.8% reduction)
- EM training: 2 passes (state+city, 5-char name prefix), converged in 25 iterations each
- Prediction: 1.97M candidate pairs above 0.70 threshold in 23s
- Quality filter: prob >= 0.85 AND Jaro-Winkler name >= 0.88 (level 3+)
- 1:1 deduplication (best per source AND target)
- **Result: 947 auto-accept + 307 needs_review**
- Total time: 11 minutes

**Scenario 2: GLEIF -> F7 (376K x 59K)**
- Much cleaner results: only 2,628 candidates above 0.70
- **Result: 605 auto-accept** (all name_level >= 3)
- Total time: 90 seconds

**Crosswalk Growth (cumulative):**
| Phase | Total | Mergent | F7 | GLEIF | SEC |
|-------|-------|---------|-----|-------|-----|
| Before cleanco | 3,010 | 1,737 | 1,253 | 1,332 | 1,926 |
| After cleanco | 4,220 | 2,414 | 1,820 | 2,659 | 1,948 |
| **After Splink** | **5,772** | **3,361** | **3,372** | **3,264** | **1,948** |
| Growth | **+91.8%** | **+93.5%** | **+169%** | **+145%** | +1.1% |

**Key Design Decisions:**
- DuckDB backend (not PostgreSQL) -- Splink 4.x default, handles 300K+ records in memory fine
- Name comparison level filter (JW >= 0.88) critical for quality -- without it, geographic overlaps dominate
- 1:1 deduplication mandatory -- raw Splink returns many-to-many (avg 46 targets per source before dedup)
- EM training uses separate blocking rules from prediction (required by Splink to estimate all parameters)

**Scripts Created:**
- `scripts/matching/splink_config.py` -- Scenario settings, comparisons, blocking rules
- `scripts/matching/splink_pipeline.py` -- Full pipeline: load -> train -> predict -> save
- `scripts/matching/splink_integrate.py` -- Quality filter + crosswalk integration

**Status:** Phase 2 complete. Crosswalk at 5,772 rows (+91.8% from baseline). Next: Phase 3 (QCEW/USASpending data expansion).

---

### 2026-02-08 (Phase 1: RapidFuzz + cleanco Integration)
**Tasks:** Integrate RapidFuzz and cleanco libraries, rebuild crosswalk with improved normalization

**Libraries Installed:** RapidFuzz (already present), cleanco (new)

**Changes Made:**
- `scripts/matching/normalizer.py`: Added cleanco `basename()` call at start of `_normalize_standard()` and `_normalize_aggressive()` — strips 80+ international legal suffixes (GmbH, S.A., Pty Ltd, AG, NV, BV, AB, ApS)
- `scripts/matching/matchers/fuzzy.py`: Replaced difflib with RapidFuzz composite scoring (0.35 x Jaro-Winkler + 0.35 x token_set_ratio + 0.30 x fuzz.ratio). pg_trgm now fetches top-5 candidates for re-scoring instead of top-1.
- `scripts/etl/update_normalization.py`: Batch-updated 379K GLEIF + 517K SEC `name_normalized` columns with cleanco (283s total)

**Crosswalk Rebuild Results (Before -> After cleanco):**
| Metric | Before | After | Change |
|--------|--------|-------|--------|
| Total crosswalk | 3,010 | **4,220** | **+1,210 (+40.2%)** |
| GLEIF linked | 1,332 | **2,659** | **+1,327 (+99.6%)** |
| Mergent linked | 1,737 | **2,414** | +677 (+39.0%) |
| F7 linked | 1,253 | **1,820** | +567 (+45.3%) |
| SEC linked | 1,926 | 1,948 | +22 |
| 3+ sources | 224 | **396** | +172 |

**Key Insight:** cleanco nearly doubled GLEIF matches — international suffixes were the main blocker for GLEIF name+state joins. Far exceeded plan estimate of 3,200-3,400.

**Status:** Phase 1 complete. RapidFuzz fuzzy scoring ready for matching runs. Crosswalk rebuilt.

---

### 2026-02-08 (GLEIF Load + Corporate Crosswalk)
**Tasks:** Load GLEIF/Open Ownership data, build corporate identifier crosswalk and hierarchy

**Phase 1: GLEIF Data Load**
- Previous session (2026-02-07) had loaded SEC EDGAR (`sec_companies`: 517,403 rows) and restored GLEIF pgdump into `gleif` schema (52.7M rows across 9 tables)
- The US entity extraction query (`INSERT INTO gleif_us_entities`) had been running for 13+ hours, stuck on a correlated LEI subquery — 0 rows written, 12GB temp files spilled
- Killed PID 49932 and rewrote as optimized 2-step:
  1. INSERT entities without LEI (JOIN + DISTINCT ON) — 379,113 rows in 20s
  2. UPDATE LEI via indexed JOIN — 379,192 rows in 11s
- Total: **40 seconds** vs 13+ hours stuck
- Added `statementid` column (UUID) to `gleif_us_entities` for ownership link joins

**Key Discovery:** GLEIF `ooc_statement` references entities via `statementid` (UUID), NOT `_link` (numeric row ID). Initial ownership link extraction returned 0 rows due to this mismatch. Fixed by adding statementid column and joining through it.

**Phase 1 Results:**
| Table | Records |
|-------|---------|
| `gleif_us_entities` | 379,192 (100% with LEI, 51 states) |
| `gleif_ownership_links` | 498,963 |

**Ownership Link Breakdown:**
| Type | Count |
|------|-------|
| Both US | 116,521 |
| Parent US only | 24,843 |
| Child US only | 357,599 |
| Direct | 173,332 |
| Indirect | 171,557 |
| Unknown | 154,074 |

**Phase 2: Corporate Identifier Crosswalk**
- Created `corporate_identifier_crosswalk` table with 3-tier matching:

| Tier | Method | Matches | Confidence |
|------|--------|---------|------------|
| 1 | EIN exact (SEC↔Mergent) | 1,127 | HIGH |
| 2 | LEI exact (SEC↔GLEIF) | 84 | HIGH |
| 3a | Name+State (SEC↔F7) | 670 | MEDIUM |
| 3b | Name+State (GLEIF↔F7) | 583 new + 82 updated | MEDIUM |
| 3c | Name+State (GLEIF↔Mergent) | 546 new + 35 updated | MEDIUM |
| 3d | Name+State backfill (SEC↔Mergent) | 45 updated | MEDIUM |
| 3e | Name+State backfill (Mergent↔F7) | 64 updated | MEDIUM |

**Crosswalk Results:** 3,010 rows total
- SEC linked: 1,926 | GLEIF: 1,332 | Mergent: 1,737 | F7: 1,253
- Public companies: 351 | 3+ sources: 224 | All 4 sources: 4

**Phase 3: Corporate Hierarchy**
- Built `corporate_hierarchy` from GLEIF ownership + Mergent parent_duns:

| Source | Links |
|--------|-------|
| GLEIF ownership (both-US) | 116,525 |
| Mergent parent_duns | 7,401 |
| Mergent domestic_parent | 1,185 |
| **Total** | **125,111** |

- 13,929 distinct parents, 54,924 distinct children, 94 children linked to F7

**Sample hierarchies:** CBRE Group → CBRE Capital Markets, Ameren Corp → Ameren Illinois, AEP → Indiana Michigan Power, Bloomberg LP → Bloomberg Inc, Amalgamated Financial → Amalgamated Bank

**Scripts Created:**
- `scripts/etl/extract_gleif_us_optimized.py` — Optimized 2-step US extraction
- `scripts/etl/build_crosswalk.py` — Full crosswalk + hierarchy builder

**Performance Notes:**
- Composite indexes on (name_normalized, state) across all 4 tables essential for name+state joins
- All Tier 3 name+state matches completed in <1s each thanks to indexes
- GLEIF ownership extraction: 56s for 499K links

**Status:** Complete. CLAUDE.md updated with new tables, API endpoints, features, and gotchas.

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
