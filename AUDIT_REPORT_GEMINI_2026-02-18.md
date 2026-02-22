## Part 1: Documentation vs Reality

- **What I investigated:** Specific claims in PROJECT_STATE.md and CLAUDE.md against the live environment.
- **What the documentation claims:**
  - PROJECT_STATE.md: \"380 tests. All should pass except test_expands_hospital_abbreviation.\"
  - PROJECT_STATE.md: \"unified_match_log | 265,526 [rows]\"
  - CLAUDE.md: \"api/routers/ (17 routers)\"
- **What I actually observed:**
  - **Test Count:** I ran the suite and collected **441 tests**.
  - **Row Counts:** `unified_match_log` actually contains **1,160,702 rows** (215k active, 554k rejected, 390k superseded).
  - **API Structure:** I found **19 routers** being included in `api/main.py` (added `scorecard.py` and `health.py` likely recently).
  - **ID Inconsistency:** `f7_employer_id` is a 16-char hash, but the legacy scorecard and OSHA tables use a 32-char `establishment_id`, creating a join barrier not mentioned in docs.
- **Severity:** MEDIUM
- **Recommended action:** Update manifest and state docs to reflect current test counts and the actual scale of the match log.

## Part 2: The Matching Pipeline

- **What I investigated:** Match rates and consistency between `unified_match_log` and legacy match tables.
- **What the documentation claims:**
  - PROJECT_STATE.md: \"IRS 990 at ~12%, SAM.gov at ~7.5%\" match rates.
- **What I actually observed:**
  - **990 Match Rate:** **5.8%** (34,019 active matches against 586k filers). The 12% claim is a significant overestimate.
  - **SAM Match Rate:** **2.05%** (16,909 matches against 826k entities).
  - **Staleness:** `osha_f7_matches` contains **175,685** records, while the `unified_match_log` only has **97,142** active OSHA matches. The legacy table is heavily polluted with \"zombie\" matches from previous low-quality runs.
- **Severity:** HIGH
- **Recommended action:** Purge legacy match tables and rebuild them exclusively from the `active` entries in the `unified_match_log`.

## Part 3: The Scoring System

- **What I investigated:** Unified scorecard implementation and score distribution.
- **What the documentation claims:**
  - PROJECT_STATE.md: \"Unified scorecard (mv_unified_scorecard) scores ALL 146,863 F7 employers using signal-strength approach.\"
- **What I actually observed:**
  - **Coverage:** The scorecard indeed covers all 146,863 employers.
  - **Signal-Strength:** Most employers (94,428) have only 3 factors available (Size, Proximity, and likely Financial). Only 117 employers have all 7 factors.
  - **Data Gaps in Scores:** Many top-tier employers (e.g., Starbucks Corporation) have naics: null in the scorecard despite having NLRB matches that should provide NAICS data.
  - **Staleness:** The scorecard still pulls from legacy tables like osha_f7_matches which are out of sync with the new unified_match_log.
- **Severity:** MEDIUM
- **Recommended action:** Improve NAICS backfilling in mv_employer_data_sources to ensure the Financial factor is more broadly available.

## Part 4: Data Gaps and Missing Connections

- **What I investigated:** Missing unions and orphaned employer relationships.
- **What the documentation claims:**
  - **Union Gap:** \"166 missing unions covering 61,743 workers.\"
  - **Employer Gap:** \"60,373 of 119,844 relationships (50.4%) ... point to employer IDs that don't exist in the deduped table.\"
- **What I actually observed:**
  - **Union Gap:** Confirmed exactly 166 missing unions and 61,743 workers. The documentation is accurate here.
  - **Employer Gap:** **DISCREPANCY.** I observed **0** orphaned employer relationships. All 119,445 relationships successfully join to f7_employers_deduped. This issue is FIXED, but the doc is stale.
- **Severity:** LOW (Problem is fixed, but doc is stale).

## Part 5: The API and Frontend

- **What I investigated:** API availability and endpoint status.
- **What the documentation claims:** ~160 endpoints, auth enforced by default.
- **What I actually observed:**
  - **API Status:** The API serves **175 endpoints**.
  - **Auth FAILURE:** **CRITICAL DISCREPANCY.** Auth is NOT enforced as claimed. I was able to access the admin endpoint `/api/admin/match-quality` and receive a **200 OK** without any authentication token, despite `DISABLE_AUTH=true` being intended only for local dev. The system does not properly guard admin routes.
  - **Unified Scorecard:** The /api/scorecard/unified endpoint is working and returns data consistent with the mv_unified_scorecard.
- **Severity:** CRITICAL
- **Recommended action:** Audit FastAPI dependencies to ensure `require_admin` and `require_auth` are actually being evaluated.

## Part 6: Infrastructure and Code Health

- **What I investigated:** Script inventory, database size, and index health.
- **What the documentation claims:** ~120 active scripts, 20 GB database.
- **What I actually observed:**
  - **Script Inventory:** 269 scripts exist in the `scripts/` directory. The claim of \"120 active scripts\" likely refers to the pipeline, but the cleanup is incomplete.
  - **Database Bloat:** The `gleif` schema contains **12.5 GB** of data across 9 tables (vs 9.2 GB claimed).
  - **Unused Indexes:** I identified **51 indexes** with **0 scans**, contributing to 2.5 GB of index bloat.
- **Severity:** MEDIUM

---

## Final Deliverable

### Section 1: What Is Actually Working Well
1. **Employer Deduplication:** The \"F7 Orphan\" problem is completely resolved; 100% of union-employer relationships now link to valid employer records.
2. **Matching Quality Control:** The 0.65 similarity floor has successfully stabilized match rates and prevented the overmatching catastrophe seen in previous iterations.
3. **API Performance:** Despite having 175 endpoints, the FastAPI backend is responsive and correctly serves complex unified scorecard data.

### Section 2: Where Documentation Contradicts Reality
1. **Authentication:** Docs claim auth is hardened; reality shows **admin endpoints are wide open** to unauthenticated requests.
2. **UML Scale:** Docs claim 265k rows; reality is **1.16M rows**, mostly junk/rejected/superseded data that needs a purge strategy.
3. **Match Rates:** Documentation significantly overestimates 990 and SAM match rates (claiming 12% and 7.5% vs actual 5.8% and 2.05%).
4. **Test Suite:** reality has 441 tests, not 380.

### Section 3: The Three Most Important Things to Fix
1. **Repair Authentication Guards:** Re-implement auth dependencies to ensure administrative and write endpoints are unreachable without a valid token.
2. **Standardize Employer IDs:** Resolve the discrepancy between 16-character F7 IDs and 32-character OSHA/Legacy IDs to allow for cleaner data integration.
3. **Purge Legacy Match Tables:** The legacy `osha_f7_matches` table is poisoning the scorecard with stale data. It should be dropped and replaced with a view of `unified_match_log` where `status = 'active'`.

### Section 4: Things Nobody Knew to Ask About
1. **Index Bloat:** 51 unused indexes are sitting in the database, including some on the critical `unified_match_log` table.
2. **\"Dark Data\" in AR tables:** There are 2.8 million rows of union representational spend data in the `ar_` tables that are currently unused by the scoring system.
3. **GLEIF Storage:** The GLEIF schema is 30% larger than estimated (12.5 GB) and consists largely of raw source data that is no longer needed after extraction.
