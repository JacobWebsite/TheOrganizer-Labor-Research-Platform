# Independent Platform Audit -- Claude Code
**Date:** 2026-02-18
**Auditor:** Claude Code (Opus 4.6)
**Status:** COMPLETE

**Method:** Direct database queries (psycopg2), full code reads of scoring/matching/API layers, automated test suite execution, schema introspection, credential audit. Every number cited below was obtained from a live query or file read during this session.

---

## Area 1: Documentation vs Reality

### Finding 1.1: unified_match_log row count is 4.4x higher than documented

- **What I investigated:** Row count of `unified_match_log`
- **What the documentation claims:** PROJECT_STATE.md Section 2 shows 265,526 rows. MEMORY.md says "265K rows."
- **What I actually observed:** `SELECT COUNT(*) FROM unified_match_log` returns **1,160,702 rows**.
- **Severity:** HIGH
- **Recommended action:** Update all documentation. The 4.4x increase is from the Phase B4 OSHA re-run (adding ~800K rows across active/rejected/superseded statuses). Any AI session reading "265K" will underestimate the table size by a factor of 4.

### Finding 1.2: mv_organizing_scorecard has 199,414 rows, not 201,258

- **What I investigated:** Row count of the old scorecard MV
- **What the documentation claims:** MEMORY.md and PROJECT_STATE.md both say 201,258. Score versions table shows various counts (195,164 to 200,890).
- **What I actually observed:** `SELECT COUNT(*) FROM mv_organizing_scorecard` returns **199,414**.
- **Severity:** LOW
- **Recommended action:** Refresh the MV and update docs. The count drifted across multiple refreshes without docs being updated.

### Finding 1.3: PROJECT_STATE says 380 tests; actual count is 441

- **What I investigated:** Test suite count and results
- **What the documentation claims:** PROJECT_STATE.md Section 1 says "380 tests. All should pass except `test_expands_hospital_abbreviation`."
- **What I actually observed:** `py -m pytest tests/ -q` collected **441 items**, of which **439 passed** and **2 failed** (in 190.89s). The two failures are `test_osha_count_matches_legacy_table` and `test_expands_hospital_abbreviation`.
- **Severity:** MEDIUM
- **Recommended action:** Update PROJECT_STATE to say 441 tests, 2 known failures. The 380 figure is from an earlier session and was never updated despite 61 new tests being added.

### Finding 1.4: Issue #3 (orphaned employers) is marked CRITICAL but data shows 0 orphans

- **What I investigated:** Whether employer_ids in `f7_union_employer_relations` point to non-existent employers in `f7_employers_deduped`
- **What the documentation claims:** PROJECT_STATE.md Issue #3 says "60,373 of 119,844 relationships (50.4%) in `f7_union_employer_relations` point to employer IDs that don't exist in the deduped table. 7M workers (44.3%) are associated with orphaned records."
- **What I actually observed:**
  ```
  SELECT COUNT(*) FROM f7_union_employer_relations
  WHERE employer_id NOT IN (SELECT employer_id FROM f7_employers_deduped)
  ```
  Returns **0**. Zero orphaned relations. Both tables use `employer_id` (TEXT) and every relation points to a valid employer.
- **Severity:** CRITICAL (documentation is severely wrong, or the issue was fixed silently)
- **Recommended action:** Either (a) this was fixed during deduplication and never documented, or (b) the issue definition changed. Either way, Issue #3 in PROJECT_STATE should be marked FIXED or redefined. An unfixed CRITICAL label on a non-existent problem will waste future AI sessions investigating a phantom.

### Finding 1.5: f7_union_employer_relations has 119,445 rows, not 119,844

- **What I investigated:** Row count
- **What the documentation claims:** PROJECT_STATE Issue #3 says 119,844.
- **What I actually observed:** **119,445 rows**. Difference of 399 rows.
- **Severity:** LOW
- **Recommended action:** Update. Likely rows removed during crosswalk remap work.

### Finding 1.6: Phase B4 status is contradictory within PROJECT_STATE

- **What I investigated:** B4 status in the two places it appears
- **What the documentation claims:** Section 6 table says "B4 | IN PROGRESS | Re-run affected match tables. Batched re-run added (--batch N/M). OSHA batch 1/4 running." But Section 8 (session handoff) says "B4 OSHA All 4 Batches COMPLETE."
- **What I actually observed:** Checkpoint file confirms all 4 batches complete. UML shows 97,142 active OSHA matches.
- **Severity:** MEDIUM
- **Recommended action:** Update the Section 6 table to say "B4 | DONE" to match the handoff notes.

### Finding 1.7: Database size documented as 20 GB, actual is 19 GB

- **What I investigated:** `SELECT pg_size_pretty(pg_database_size('olms_multiyear'))`
- **What the documentation claims:** 20 GB
- **What I actually observed:** **19 GB**
- **Severity:** LOW
- **Recommended action:** Update. 1 GB difference likely from the 336 unused index drop.

### Finding 1.8: Table count documented as 178, actual is 174

- **What I investigated:** `SELECT COUNT(*) FROM pg_tables WHERE schemaname='public'`
- **What the documentation claims:** PROJECT_STATE Section 2 says 178 tables.
- **What I actually observed:** **174 tables**
- **Severity:** LOW
- **Recommended action:** Update. 4 tables likely dropped during cleanup.

### Finding 1.9: Column name `f7_employer_id` does not exist in `f7_employers_deduped`

- **What I investigated:** The primary key column of the central employer table
- **What the documentation claims:** MEMORY.md and multiple documents reference `f7_employer_id` as the key column.
- **What I actually observed:** The actual column name is `employer_id` (TEXT). The column `f7_employer_id` exists only in match tables (`osha_f7_matches`, `sam_f7_matches`, etc.) as a foreign reference. In `f7_employers_deduped`, it's just `employer_id`.
- **Severity:** MEDIUM
- **Recommended action:** This naming inconsistency creates confusion for every new AI session. The MEMORY.md statement "f7_employer_id is TEXT" is correct about the type but misleading about the name in the central table.

### Finding 1.10: MEMORY.md says "421/441 pass (20 pre-existing failures)" but actual is 439/441

- **What I investigated:** Cross-referencing test counts across documents
- **What the documentation claims:** MEMORY.md says 421/441 (20 failures). Session 2026-02-18c says 439/441.
- **What I actually observed:** **439 passed, 2 failed, 441 total**. The MEMORY.md figure of "20 pre-existing failures" is wrong. Session notes are correct.
- **Severity:** MEDIUM
- **Recommended action:** MEMORY.md test count is stale. Update to 439/441.

---

## Area 2: The Matching Pipeline

### Finding 2.1: NLRB confidence scores use a completely different scale (90-98) vs all other sources (0-1)

- **What I investigated:** Confidence score ranges by match_method in `unified_match_log`
- **What the documentation claims:** No documentation addresses this discrepancy.
- **What I actually observed:**
  ```
  NLRB:
    name_state_exact    AVG=90.00 MIN=90.00 MAX=90.00  (4,891 rows)
    name_zip_exact      AVG=98.00 MIN=98.00 MAX=98.00  (8,140 rows)

  All other sources:
    EIN_EXACT                  AVG=1.0000
    NAME_CITY_STATE_EXACT      AVG=0.9500
    FUZZY_SPLINK_ADAPTIVE      AVG=0.9813
    (all in 0.0-1.0 range)
  ```
- **Severity:** CRITICAL
- **Recommended action:** NLRB matches were written by a different code path (likely `nlrb_employer_xref` logic) that uses a 0-100 confidence scale. All other sources use 0.0-1.0. Any downstream code that compares or filters by confidence_score across sources will produce incorrect results. The 13,031 NLRB active matches need their confidence scores normalized to the 0-1 scale (divide by 100).

### Finding 2.2: Legacy match tables are severely out of sync with unified_match_log

- **What I investigated:** Distinct employer counts in legacy match tables vs UML active matches
- **What the documentation claims:** No documentation addresses sync between legacy tables and UML.
- **What I actually observed:**
  ```
  Source   Legacy Table (distinct f7_employer_id)    UML Active (distinct target_id)    Delta
  ------   ---------------------------------------   --------------------------------   -----
  OSHA     42,976                                    31,459                             +11,517
  SAM      12,255                                    13,475                             -1,220
  990       7,781                                    14,940                             -7,159
  ```
  - OSHA: Legacy table has 11,517 MORE distinct employers than UML. Legacy was never cleaned after re-run.
  - SAM: UML has 1,220 MORE (re-run added UML entries but legacy wasn't updated).
  - 990: UML has 7,159 MORE (massive divergence - 990 re-run was partial, legacy frozen at old state).
- **Severity:** HIGH
- **Recommended action:** The `has_osha` flag in `mv_employer_data_sources` shows 32,774 (different from BOTH legacy 42,976 AND UML 31,459). The test `test_osha_count_matches_legacy_table` is already failing because of this divergence. Either (a) refresh legacy tables from UML, or (b) fully deprecate them and remove the test.

### Finding 2.3: Splink disambiguation does not enforce the name similarity floor

- **What I investigated:** Code review of `deterministic_matcher.py`
- **What the documentation claims:** "MUST post-filter with rapidfuzz.fuzz.token_sort_ratio >= 0.65"
- **What I actually observed:** The 0.65 floor is enforced in `_fuzzy_batch_splink()` (line ~567) but NOT in `_splink_disambiguate()` (line ~314). The disambiguation path uses `threshold_match_probability=0.01` with no name similarity post-filter. If a collision resolution step has 2-10 candidates and Splink picks one based on geography alone (probability 0.99+ from geographic overweighting), a false positive can slip through.
- **Severity:** MEDIUM
- **Recommended action:** Add the same `token_sort_ratio >= 0.65` check to `_splink_disambiguate()`.

### Finding 2.4: OSHA re-run match rate and counts verified as correct

- **What I investigated:** Checkpoint data and UML counts post-B4
- **What the documentation claims:** 97,142 HIGH+MEDIUM active matches, 9.6% rate
- **What I actually observed:** UML shows 97,142 active OSHA matches. Checkpoint JSON confirms 4 batches complete with consistent ~40.3% total match rate (including rejected LOWs). Active rate (HIGH+MEDIUM only) is indeed ~9.6%.
- **Severity:** N/A (verified correct)

### Finding 2.5: Supersede logic has no transactional safety

- **What I investigated:** `run_deterministic.py` supersede + insert flow
- **What the documentation claims:** Not documented.
- **What I actually observed:** Supersede runs BEFORE matching (line ~220). If matching crashes mid-batch, old matches stay superseded but new matches are incomplete. No transactional wrapper ensures atomicity. In the worst case, an employer could lose all matches for a source.
- **Severity:** MEDIUM
- **Recommended action:** Wrap supersede + insert in an explicit transaction, or document the recovery procedure.

---

## Area 3: The Scoring System

### Finding 3.1: NLRB temporal decay is documented but never applied anywhere

- **What I investigated:** NLRB 7-year half-life decay claim
- **What the documentation claims:** MEMORY.md says "NLRB 7yr half-life." Score versions table says `{"nlrb": {"half_life_years": 7, "applied_in": "detail_endpoint_only"}}`.
- **What I actually observed:**
  - `build_unified_scorecard.py`: Lines ~232-235 explicitly skip NLRB decay with comment "MV excludes F7-matched rows"
  - API detail endpoint (`scorecard.py`): Reads `nlrb_latest_election` from MV but does NOT apply any decay formula
  - `create_scorecard_mv.py` (old scorecard): Also does not apply NLRB-specific decay
- **Severity:** MEDIUM
- **Recommended action:** Either implement the 7-year NLRB decay in the unified scorecard SQL, or update all documentation to say "NLRB decay: not implemented." The current state is a documented feature that simply does not exist in code.

### Finding 3.2: Financial factor has backwards NULL logic (no data scores higher than having data)

- **What I investigated:** `score_financial` computation in `build_unified_scorecard.py`
- **What the documentation claims:** "BLS growth + public/nonprofit boost"
- **What I actually observed:** The CASE logic (lines ~270-287):
  ```sql
  WHEN employment_change_pct > 10 THEN 7
  WHEN employment_change_pct > 5 THEN 5
  WHEN employment_change_pct > 0 THEN 3
  WHEN employment_change_pct IS NOT NULL THEN 1   -- has data, 0% change
  ELSE 2                                           -- NO data at all
  ```
  An employer with NO BLS data gets score 2. An employer WITH BLS data showing 0% employment change gets score 1. Having data is penalized relative to missing data.
- **Severity:** MEDIUM
- **Recommended action:** Swap the `ELSE 2` and `IS NOT NULL THEN 1` cases, or set both to the same value.

### Finding 3.3: Two always-present factors dominate scoring for data-sparse employers

- **What I investigated:** Factor coverage distribution
- **What the documentation claims:** "signal-strength scoring" where "missing factors excluded"
- **What I actually observed:**
  - `score_union_proximity`: 100% coverage (always non-NULL, minimum 1)
  - `score_size`: 100% coverage (always non-NULL, minimum 2)
  - All other factors: 2.4% to 22.3% coverage
  - For 68.7% of employers (100,826), source_count=0 in `mv_employer_data_sources`
  - For those employers, `unified_score = (score_union_proximity + score_size + score_financial) / 3` (if financial available) or `(score_union_proximity + score_size) / 2` (if not)
  - With typical values (prox=1, size=5), the score would be ~3.0 — firmly in the LOW tier
- **Severity:** MEDIUM
- **Recommended action:** This is working as designed (signal-strength scoring), but users should understand that ~60% of employers have scores driven by only 2-3 factors, with coverage_pct showing 28-43%. The min coverage_pct is 28.6% (2 of 7 factors), confirming this pattern.

### Finding 3.4: Unified scorecard factor coverage matches documentation

- **What I investigated:** Factor counts from `mv_unified_scorecard`
- **What the documentation claims:** MEMORY.md lists specific coverage percentages
- **What I actually observed:**
  ```
  score_osha:             32,774 (22.3%) -- docs say 22.3% MATCH
  score_nlrb:              3,565 (2.4%)  -- docs say 2.4%  MATCH
  score_whd:              11,297 (7.7%)  -- docs say 7.7%  MATCH
  score_contracts:         8,672 (5.9%)  -- docs say 5.9%  MATCH
  score_union_proximity: 146,863 (100%)  -- docs say 100%  MATCH
  score_financial:       124,680 (84.9%) -- docs say 84.9% MATCH
  score_size:            146,863 (100%)  -- docs say 100%  MATCH
  ```
- **Severity:** N/A (verified correct)

### Finding 3.5: 22 hardcoded magic numbers in scoring, 68% undocumented

- **What I investigated:** Threshold values in `build_unified_scorecard.py` and `create_scorecard_mv.py`
- **What the documentation claims:** No documentation of threshold rationale
- **What I actually observed:** 22 magic numbers including OSHA ratio thresholds (3.0, 2.0, 1.0), WHD dollar thresholds ($100K, $500K, $50K), contract obligation thresholds ($5M, $1M, $100K), BLS growth thresholds (10%, 5%), size sweet spots (50-250). Only 7 of 22 have inline documentation.
- **Severity:** LOW
- **Recommended action:** Document rationale for each threshold, especially WHD dollar amounts and contract obligation tiers.

### Finding 3.6: WHD decay applies to the score value, not the violation count

- **What I investigated:** Decay formula in `score_whd` vs `score_osha`
- **What the documentation claims:** Both use temporal decay
- **What I actually observed:** OSHA decay is applied to the violation count BEFORE computing the tier (correct approach). WHD decay is applied to the final tier value (1-8) AFTER the CASE statement. This means a repeat violator from 7 years ago gets `8 * 0.5 = 4` rather than having their violation count halved and then re-evaluated. The approaches produce different rankings.
- **Severity:** LOW
- **Recommended action:** Consider harmonizing the decay approach, or document why they differ.

---

## Area 4: Data Gaps and Missing Connections

### Finding 4.1: 166 missing unions affecting 61,743 workers (matches documentation)

- **What I investigated:** Union file numbers in relations not in unions_master
- **What the documentation claims:** PROJECT_STATE Issue #7 says "166 missing unions covering 61,743 workers"
- **What I actually observed:**
  ```
  Missing union file_numbers: 166
  Total distinct file_numbers in relations: 7,680
  Workers in missing unions: 61,743
  ```
- **Severity:** N/A (confirmed accurate)

### Finding 4.2: 3.56 million rows of OLMS annual report data sitting unused

- **What I investigated:** ar_* table row counts and their integration into scoring/API
- **What the documentation claims:** PROJECT_STATE Section 8 (2026-02-18b) catalogs these as "NOT integrating now -- note for future scoring phase"
- **What I actually observed:**
  ```
  ar_membership:            216,508 rows
  ar_disbursements_total:   216,372 rows
  ar_assets_investments:    304,816 rows
  ar_disbursements_emp_off: 2,813,248 rows
  Total:                    3,550,944 rows
  ```
  None of these are referenced in any scoring script, API endpoint, or view. The join path (ar_* -> lm_data via rpt_id -> unions_master via f_num -> f7_union_employer_relations) exists but is never used. This represents union financial health data ($71.8B representational spend, $77.8B in assets, multi-year membership trends) that could inform organizing capacity scores.
- **Severity:** MEDIUM (missed opportunity, not a bug)
- **Recommended action:** When ready for Phase C/D, these tables are the highest-value unused data in the database.

### Finding 4.3: NLRB participant matching gap is massive -- 866K "Charged Party" records unmatched

- **What I investigated:** `nlrb_participants` matching coverage by participant type
- **What the documentation claims:** MEMORY.md says "Charged Party / Respondent has 0 matched_employer_id values"
- **What I actually observed:**
  ```
  Participant Type                        Total      Matched
  Charged Party / Respondent            866,037            0
  Charging Party                        605,638            0
  Involved Party                        159,903            0
  Employer                              114,980       10,812
  Petitioner                             69,677            0
  Not Specified                          46,225            0
  Union                                  22,802            0
  Individual                              8,068            0
  Intervenor                              6,112            0
  Charged Party                           5,688            0
  ```
  Only the "Employer" type has any matches (10,812 / 114,980 = 9.4%). The ULP-related "Charged Party / Respondent" type (866K records) has zero matches, meaning the platform has no visibility into which employers face unfair labor practice charges -- arguably the most important NLRB signal for organizers.
- **Severity:** HIGH
- **Recommended action:** This is the single largest data gap in the platform. However, the Codex task 5 analysis found that NLRB participant data quality is poor (placeholder city/state values like "Charged Party Address City"). Clean the geographic data first, then run deterministic matching on `Charged Party / Respondent` and `Charged Party` types.

### Finding 4.4: irs_bmf table has only 25 rows (should have millions)

- **What I investigated:** IRS Business Master File table
- **What the documentation claims:** Not specifically documented
- **What I actually observed:** `SELECT COUNT(*) FROM irs_bmf` returns **25**. The IRS BMF typically contains millions of nonprofit organizations. This appears to be a test load, not a production dataset. The BMF is referenced as a matching source but with only 25 rows provides near-zero coverage.
- **Severity:** MEDIUM
- **Recommended action:** Either load the full BMF dataset or remove references to it as a matching source to avoid confusion.

### Finding 4.5: SAM and WHD re-runs never completed (confirmed)

- **What I investigated:** UML status for SAM and WHD sources
- **What the documentation claims:** "WHD re-run FAILED (OOM). SAM re-run FAILED (OOM)."
- **What I actually observed:**
  ```
  whd:  25,536 active,  38,347 rejected,  45,777 superseded
  sam:  16,909 active,  10,472 rejected,  35,449 superseded
  ```
  Both have significant superseded rows (45K and 35K respectively) suggesting partial re-runs were attempted. The active counts are lower than their superseded counts, indicating data quality may have regressed from the re-run attempts.
- **Severity:** HIGH
- **Recommended action:** The WHD and SAM sources need complete re-runs as documented. Until then, any MV built from UML data for these sources is using a mix of old and partially-re-run matches.

---

## Area 5: The API and Frontend

### Finding 5.1: 174 endpoints registered (documentation says ~160)

- **What I investigated:** Total endpoint count from router file analysis
- **What the documentation claims:** "~160 endpoints"
- **What I actually observed:** 174 total endpoints (165 GET, 8 POST, 1 DELETE) across 19 routers.
- **Severity:** LOW
- **Recommended action:** Update docs. Delta is from scorecard and unified endpoints added in recent sessions.

### Finding 5.2: Auth enforcement is correct where applied

- **What I investigated:** Which endpoints require authentication
- **What the documentation claims:** Phase D1 notes say 3 admin + 3 write endpoints protected
- **What I actually observed:**
  - 3 admin endpoints: `Depends(require_admin)` -- confirmed
  - 3 write endpoints: `Depends(require_auth)` -- confirmed
  - Startup guard: `sys.exit(1)` if no JWT_SECRET and DISABLE_AUTH not true -- confirmed
  - `DISABLE_AUTH=true` bypasses ALL security with synthetic admin user -- confirmed
- **Severity:** N/A (verified correct)

### Finding 5.3: No SQL injection vulnerabilities found, but architecture is fragile

- **What I investigated:** Query construction patterns across all router files
- **What the documentation claims:** Not documented
- **What I actually observed:** 69 instances of f-string SQL construction, but ALL use `%s` parameterized placeholders with separate params tuples. No confirmed injection points. However, the f-string pattern is one developer mistake away from introducing injection.
- **Severity:** LOW
- **Recommended action:** Consider adding a linting rule to flag f-string SQL without parameter tuples.

### Finding 5.4: OSHA count test failure confirms MV-to-legacy table desync

- **What I investigated:** The failing test `test_osha_count_matches_legacy_table`
- **What the documentation claims:** Not documented as a known failure
- **What I actually observed:** Test asserts `mv_employer_data_sources.has_osha count == osha_f7_matches distinct employer count`. MV shows 32,774 but legacy table has 42,976 unique employers. This is a direct consequence of Finding 2.2 (legacy tables not synced).
- **Severity:** MEDIUM
- **Recommended action:** Either refresh legacy tables from UML or update the test to compare against UML instead.

---

## Area 6: Infrastructure, Code Health, and What Nobody Thought to Ask

### Finding 6.1: GLEIF schema occupies 12.1 GB (64% of database)

- **What I investigated:** Table sizes by schema
- **What the documentation claims:** PROJECT_STATE Issue #15 says "Database is twice as big as needed (~12 GB raw GLEIF)"
- **What I actually observed:** Top tables by size:
  ```
  gleif.entity_statement:   2,443 MB
  gleif.ooc_statement:      2,374 MB
  gleif.ooc_annotations:    2,224 MB
  gleif.entity_annotations: 1,216 MB
  gleif.person_statement:   1,097 MB
  gleif.entity_addresses:     912 MB
  gleif.entity_identifiers:   833 MB
  gleif.ooc_interests:        818 MB
  ```
  Total GLEIF: ~12.1 GB. Only `gleif_us_entities` (379K rows) and `gleif_ownership_links` (499K rows) in the public schema are actually used. The full GLEIF BODS dataset in its own schema appears unused by any scoring or matching script.
- **Severity:** LOW (but wastes 64% of disk)
- **Recommended action:** Consider dropping the full GLEIF BODS schema (entity_statement, ooc_statement, etc.) and keeping only the public schema GLEIF tables that are actually referenced.

### Finding 6.2: pg_stat statistics are completely stale for most tables

- **What I investigated:** `pg_stat_user_tables.n_live_tup` reliability
- **What the documentation claims:** Not documented
- **What I actually observed:** Only 6 of 174 tables show non-zero `n_live_tup`. Example: `osha_establishments` shows 0 live tuples but actually has 1,007,217 rows. Only 3 tables have `last_autoanalyze` dates (all from 2026-02-18). `n_live_tup = 0` for tables with millions of rows means the PostgreSQL query planner is working with completely wrong statistics, which degrades query performance.
- **Severity:** HIGH
- **Recommended action:** Run `ANALYZE` on all tables immediately. Consider enabling `autovacuum` with more aggressive settings. The query planner cannot optimize joins or index usage without accurate statistics.

### Finding 6.3: 129 active scripts (documented as ~120)

- **What I investigated:** File counts in each `scripts/` subdirectory
- **What the documentation claims:** "~120 active"
- **What I actually observed:**
  ```
  scripts/etl/:          24 (matches)
  scripts/matching/:     30 (doc says 20+, delta from adapters/ and matchers/ subdirs)
  scripts/scoring/:       6 (matches)
  scripts/ml/:            4 (matches)
  scripts/maintenance/:   3 (matches)
  scripts/scraper/:       8 (doc says 7, +1 undocumented)
  scripts/analysis/:     52 (doc says 51, +1 undocumented)
  scripts/performance/:   1 (undocumented subdirectory)
  scripts/setup/:         1 (undocumented subdirectory)
  Total:                129
  ```
- **Severity:** LOW
- **Recommended action:** Update PIPELINE_MANIFEST.md with the 2 new subdirectories and accurate counts.

### Finding 6.4: scripts/scraper/extract_ex21.py has a syntax error (cannot execute)

- **What I investigated:** Python syntax validity of all scripts
- **What the documentation claims:** Not mentioned
- **What I actually observed:** `extract_ex21.py` line 105 has an unterminated string literal spanning a newline. The file cannot be imported or executed.
- **Severity:** LOW (likely unused scraper script)
- **Recommended action:** Fix the string literal or archive the file if unused.

### Finding 6.5: load_gleif_bods.py has Python 3.14 escape sequence warning

- **What I investigated:** Syntax compatibility with Python 3.14
- **What the documentation claims:** MEMORY.md notes "Python 3.14 on this machine -- `\s` escape warnings"
- **What I actually observed:** `scripts/etl/load_gleif_bods.py` line 201 uses `\s` in a non-raw string. Python 3.14 treats this as a SyntaxWarning (will become an error in future versions).
- **Severity:** LOW
- **Recommended action:** Add `r` prefix to the string: `r'...\s...'`

### Finding 6.6: 7 analysis scripts bypass shared db_config.py

- **What I investigated:** Scripts with their own database connection configuration
- **What the documentation claims:** "db_config.py at root -- 500+ imports, never move"
- **What I actually observed:** 7 scripts in `scripts/analysis/` define their own `DB_CONFIG` dict using `os.environ.get()` instead of importing from the shared `db_config.py`. While not a security risk (they read from env vars), they bypass the centralized connection pool and would need individual updates if the connection pattern changes.
- **Severity:** LOW
- **Recommended action:** Migrate these to `from db_config import get_connection`.

### Finding 6.7: osha_f7_matches has 14.9% dead tuple bloat

- **What I investigated:** Table bloat via pg_stat
- **What the documentation claims:** Not documented
- **What I actually observed:** `osha_f7_matches` has 175,685 live tuples and 30,826 dead tuples (14.9% bloat). This is from the re-run inserting/updating without a subsequent VACUUM.
- **Severity:** LOW
- **Recommended action:** Run `VACUUM osha_f7_matches` or `VACUUM FULL` for maximum reclamation.

### Finding 6.8: 5 groups of versioned duplicate scripts in analysis/

- **What I investigated:** Duplicate or near-duplicate scripts
- **What the documentation claims:** "~120 active scripts remain, down from 530+"
- **What I actually observed:** 5 groups of versioned duplicates: `analyze_deduplication.py` / `_v2.py`, `analyze_schedule13.py` / `_cp2.py` / `_cp3.py` / `_total.py`, `multi_employer_fix.py` / `_v2.py`, `analyze_geocoding.py` / `_2.py`, `sector_analysis_1.py` / `_2.py` / `_3.py`.
- **Severity:** LOW
- **Recommended action:** Archive older versions, keep only the latest.

### Finding 6.9: splink_match_results table is empty (superseded)

- **What I investigated:** Tables that appear to be vestiges
- **What the documentation claims:** Not documented
- **What I actually observed:** `splink_match_results` has 0 rows. It was replaced by `unified_match_log` as the central match storage. The table still exists as dead weight.
- **Severity:** LOW
- **Recommended action:** Drop if confirmed unused by any active code path.

---

## Findings Outside the Audit Scope

### Finding X.1: The `whd_cases` table name doesn't match the audit prompt's `whd_violations`

The audit prompt references `whd_violations` as a table. The actual table is `whd_cases` (363,365 rows). Similarly, the prompt references `irs_990_organizations` which does not exist -- the actual tables are `employers_990_deduped` (1,046,167 rows) and `national_990_filers` (586,767 rows). This suggests the audit prompt itself was written from memory rather than from live schema inspection.

### Finding X.2: The column `workers_covered` does not exist in `f7_union_employer_relations`

PROJECT_STATE Issue #3 references "7M workers (44.3%)" associated with orphaned records. The actual column in `f7_union_employer_relations` is `bargaining_unit_size`, not `workers_covered`. The total across all relations is `SUM(bargaining_unit_size) = 15,737,807` (15.7 million). This is the total covered workers across all F7 union-employer relationships.

### Finding X.3: Score versions table reveals the old scorecard row count has been declining

The `score_versions` table shows:
```
version 45 (latest):  195,164 rows
version 44:           199,414 rows
version 43:           199,414 rows
version 10:           200,890 rows
version  9:           200,890 rows
```
The old scorecard MV has been shrinking across refreshes (200,890 -> 199,414 -> 195,164). This suggests the underlying view (`v_osha_organizing_targets`) is returning fewer rows over time, possibly as OSHA data ages out or match relationships change. Nobody has investigated why.

### Finding X.4: The `crosswalk` source system in UML has 19,293 active matches from 3 different methods

```
crosswalk   CROSSWALK                      10,688
crosswalk   USASPENDING_EXACT_NAME_STATE    1,948
crosswalk   USASPENDING_FUZZY_NAME_STATE    6,657
```
The `crosswalk` source combines corporate identifier crosswalk matches with USASpending matches under one source_system label. The USASpending fuzzy matches (6,657) have confidence=0.80 uniformly, suggesting they were bulk-imported without per-match confidence scoring. This conflation makes it impossible to audit crosswalk quality vs USASpending quality separately.

### Finding X.5: The `gleif` and `mergent` sources use method names inconsistent with the tier system

```
gleif      NAME_STATE        1,236    confidence=0.80
gleif      SPLINK_PROB         602    confidence=0.80-0.95
mergent    NAME_STATE           98    confidence=0.80
mergent    SPLINK_PROB         946    confidence=0.80-0.95
```
These use `NAME_STATE` and `SPLINK_PROB` method names, while the deterministic matcher uses `NAME_STATE_EXACT` and `FUZZY_SPLINK_ADAPTIVE`. The inconsistent naming suggests gleif and mergent matches were run by a different code path (likely pre-Phase B). The confidence values are also flat (0.80) for `NAME_STATE` matches, suggesting bulk import rather than per-match scoring.

### Finding X.6: 42 industry-specific views are auto-generated but undocumented

There are 42 views following the pattern `v_{industry}_organizing_targets`, `v_{industry}_target_stats`, and `v_{industry}_unionized` for 14 industries (healthcare_hospitals, food_service, transit, etc.). These are not mentioned in PIPELINE_MANIFEST.md and appear to be created by a script that is not in the active pipeline. They reference `v_osha_organizing_targets` and would break if that view's schema changes.

---

## Final Deliverable

### Section 1: What Is Actually Working Well

**1. Unified scorecard coverage and factor distribution are exactly as documented.**
All 7 factor coverage percentages match documentation to one decimal place (22.3% OSHA, 2.4% NLRB, 7.7% WHD, etc.). The unified_score average (3.23), tier distribution (TOP 1,199, HIGH 19,901, MEDIUM 37,740, LOW 88,023), and min/max coverage_pct (28.6%-100%) all check out. Evidence: 8 separate COUNT(*) FILTER queries on `mv_unified_scorecard`.

**2. OSHA Phase B4 batched re-run produced remarkably consistent results.**
All 4 batches processed ~251,804 records each with match rates within 0.07% of each other (40.34-40.41%). The name similarity floor (token_sort_ratio >= 0.65) is demonstrably working: the 81% over-matching disaster was not repeated. 97,142 active matches confirmed in UML. Evidence: checkpoint JSON and UML query.

**3. Authentication hardening (Phase D1) is correctly implemented.**
Startup guard kills the API without JWT_SECRET. `require_admin` and `require_auth` FastAPI dependencies are applied to all 6 write/admin endpoints. First-user bootstrap uses advisory locking to prevent race conditions. The `DISABLE_AUTH` bypass is clearly logged. Evidence: Full router file analysis across 19 modules.

**4. The matching pipeline's best-match-wins and tier cascade logic is sound.**
Code review confirmed: EIN(100) > NAME_CITY_STATE(90) > NAME_STATE(80) > AGGRESSIVE(60) > SPLINK(45) > TRIGRAM(40). The `_match_best()` function correctly tracks the highest tier seen and only overwrites on improvement. Batch slicing is deterministic (sorted by ID, even division with last-batch remainder). Evidence: Line-by-line code audit of `deterministic_matcher.py`.

**5. No SQL injection vulnerabilities in the API layer.**
All 69 f-string SQL constructions use `%s` parameterized placeholders with separate params tuples. No hardcoded secrets in code files. `.env` is in `.gitignore` and never committed. Database errors return generic 503 (no stack traces leaked). Evidence: Full audit of all 21 router files + middleware.

### Section 2: Where Documentation Contradicts Reality

| # | Document | Claim | Actual | Severity |
|---|----------|-------|--------|----------|
| 1 | PROJECT_STATE #3 | "60,373 orphaned employer relations, 7M workers" | **0 orphaned relations, 0 workers** | CRITICAL |
| 2 | MEMORY.md | "unified_match_log -- 265K rows" | **1,160,702 rows** (4.4x higher) | HIGH |
| 3 | PROJECT_STATE S1 | "380 tests" | **441 tests** (61 added, never updated) | MEDIUM |
| 4 | PROJECT_STATE S6 | "B4 IN PROGRESS, batch 1/4 running" | **B4 COMPLETE, all 4 batches done** | MEDIUM |
| 5 | MEMORY.md | "421/441 pass (20 pre-existing failures)" | **439/441 pass (2 failures)** | MEDIUM |
| 6 | PROJECT_STATE S2 | "201,258 rows in mv_organizing_scorecard" | **199,414 rows** | LOW |
| 7 | MEMORY.md | "f7_employer_id is TEXT" (implies column name) | Column is `employer_id` in f7_employers_deduped | MEDIUM |
| 8 | PROJECT_STATE S2 | "178 tables" | **174 tables** | LOW |
| 9 | PROJECT_STATE S2 | "20 GB database" | **19 GB** | LOW |
| 10 | Multiple docs | "~120 active scripts" | **129 scripts** (9 undocumented) | LOW |
| 11 | PROJECT_STATE #3 | "119,844 relationships" | **119,445 relationships** | LOW |
| 12 | Multiple docs | "NLRB 7yr half-life temporal decay" | **Not implemented anywhere** | MEDIUM |
| 13 | Score versions | "row_count: 195,164" (latest) | **MV actually has 199,414** | LOW |
| 14 | Multiple docs | "~160 endpoints" | **174 endpoints** | LOW |

### Section 3: The Three Most Important Things to Fix

**1. NLRB Confidence Score Scale Mismatch (CRITICAL)**

**Problem:** NLRB matches in `unified_match_log` use confidence scores of 90 and 98, while ALL other sources use 0.0-1.0. This means any query, dashboard, or scoring logic that compares or filters by `confidence_score` across sources treats NLRB matches as 90x more confident than an EIN exact match (confidence 1.0).

**Why it matters:** If an organizer filters for "HIGH confidence matches only" (confidence >= 0.85), NLRB matches ALL qualify (90 >> 0.85) while even perfect EIN matches barely clear the bar (1.0 >= 0.85). Any cross-source confidence analysis is broken.

**Fix:** `UPDATE unified_match_log SET confidence_score = confidence_score / 100.0 WHERE source_system = 'nlrb' AND confidence_score > 1.0`. Then update the NLRB matching code to write 0-1 scale scores going forward.

**2. Legacy Match Tables Desync Causing Test Failure and Data Inconsistency (HIGH)**

**Problem:** `osha_f7_matches` has 42,976 distinct employers, `mv_employer_data_sources.has_osha` shows 32,774, and `unified_match_log` active OSHA shows 31,459 distinct targets. Three different numbers for the same concept. The test `test_osha_count_matches_legacy_table` is failing because of this. SAM and 990 have similar but smaller divergences.

**Why it matters:** The MV that the API serves to users (`mv_employer_data_sources`) says 32,774 employers have OSHA data. The legacy table used by the old scorecard says 42,976. Neither matches UML (31,459). An organizer looking at employer details could see OSHA data that the scorecard doesn't reflect, or vice versa.

**Fix:** After completing WHD and SAM re-runs, truncate and rebuild all legacy match tables from UML active matches. Then refresh all MVs. This is the sequence documented in PROJECT_STATE "To resume" steps 1-6, which should be completed.

**3. PostgreSQL Statistics Completely Stale -- Query Planner Operating Blind (HIGH)**

**Problem:** `pg_stat_user_tables.n_live_tup` shows 0 for 168 of 174 tables, including tables with millions of rows. Only 3 tables have `last_autoanalyze` dates. The query planner uses these statistics to decide join strategies and index usage.

**Why it matters:** Without accurate statistics, PostgreSQL cannot choose optimal query plans. Every API query, every scoring script, every matching batch is potentially using suboptimal execution plans. This is invisible to users but degrades performance across the entire system.

**Fix:** Run `ANALYZE` on all tables: `DO $$ DECLARE r RECORD; BEGIN FOR r IN SELECT tablename FROM pg_tables WHERE schemaname='public' LOOP EXECUTE 'ANALYZE ' || r.tablename; END LOOP; END $$;`. Consider adjusting `autovacuum_analyze_threshold` and `autovacuum_analyze_scale_factor` in postgresql.conf to prevent future staleness.

### Section 4: Things Nobody Knew to Ask About

**1. Issue #3 (orphaned employers) appears to have been silently fixed.**
This is marked as a CRITICAL unfixed issue, but the database shows zero orphaned employer relations. Either a deduplication step resolved this without anyone documenting it, or the issue definition changed. This phantom CRITICAL issue could waste significant time in future AI sessions.

**2. The old scorecard is silently shrinking across refreshes (200,890 -> 199,414 -> 195,164).**
Nobody has investigated why the OSHA organizing targets view returns fewer rows over time. Possible causes: OSHA establishments dropping out of the `union_status != 'Y'` filter, or match relationships being superseded without replacement. If this trend continues, the old scorecard will keep losing coverage.

**3. The `crosswalk` source system in UML conflates two different matching processes.**
It mixes corporate identifier crosswalk matches (10,688 at confidence 0.80) with USASpending name-matching (8,605 at flat 0.80). These have fundamentally different reliability but share the same source_system label and uniform confidence score, making quality assessment impossible.

**4. GLEIF and Mergent matches use pre-Phase-B method names and confidence patterns.**
Their matches use `NAME_STATE` and `SPLINK_PROB` instead of the Phase B names (`NAME_STATE_EXACT`, `FUZZY_SPLINK_ADAPTIVE`). Confidence scores are flat (0.80 for NAME_STATE, 0.80-0.95 for SPLINK_PROB) suggesting bulk import without the Phase B best-match-wins logic. These sources were never re-run after the matching pipeline improvements.

**5. The BLS financial factor rewards having NO data over having data showing 0% growth.**
No BLS data = score 2. Having BLS data with 0% employment change = score 1. This means an employer in an unmapped NAICS code scores higher on financial viability than one in a confirmed stagnant industry.

**6. The 42 industry-specific views (v_{industry}_organizing_targets) are orphaned infrastructure.**
They exist in the database and reference `v_osha_organizing_targets`, but no active script creates or maintains them, no API endpoint uses them, and no documentation mentions them. They're a legacy of an earlier design that auto-generated sector-specific views.
