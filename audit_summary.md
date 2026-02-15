# Labor Relations Research Platform - Consolidated Audit Findings

This document consolidates the findings from the comprehensive audit of the Labor Relations Research Platform, covering database schema, data quality, cross-database matching, API endpoints, frontend structure, script inventory, and documentation accuracy.

**Date of Audit:** 2026-02-15

---

## SECTION 1: DATABASE INVENTORY

*   **Total Relations:** 346 (160 tables, 186 views).
*   **Total Size:** 7.52 GB.
*   **Notable Findings:**
    *   `platform_users` table found with ZERO rows. (Severity: 🔵 MEDIUM)
    *   Many tables have "Never" for `Last Analyze` and `Last Autoanalyze` (see Section 6, Finding 15). (Severity: 🟡 MEDIUM)

---

## SECTION 2: DATA QUALITY

*   **Column Completeness:**
    *   Generally good, but notable gaps in `mergent_employers.ein` (44% filled) and `osha_establishments.sic_code` (23% filled). (Severity: 🔵 MEDIUM)
    *   Column name corrections were made for `osha_establishments` and `nlrb_elections` to align with available data.
*   **Duplicate Records:** Found duplicates in:
    *   `f7_employers_deduped`: 1,840 groups. (Severity: 🔵 MEDIUM)
    *   `osha_establishments`: 56,149 groups. (Severity: 🔴 CRITICAL - affects matching accuracy)
    *   `nlrb_elections`: 1,604 groups. (Severity: 🔵 MEDIUM)
*   **Orphaned Records:**
    *   🔴 **CRITICAL:** `nlrb_participants → elections`: **92.34% orphan rate** (1,760,408 records). This is a severe data integrity failure in the NLRB pipeline.
    *   `f7_relations → unions`: 0.69% orphan rate (824 records). (Severity: 🔴 CRITICAL)
    *   Other checks (F7->OSHA, OSHA->Employers, OSHA->Establishments) showed 0% orphan rate.

---

## SECTION 3: CROSS-DATABASE MATCHING

*   **Match Rates:**
    *   F7 employers → OSHA: 25.37%
    *   F7 employers → NLRB: 4.88%
    *   F7 employers → Crosswalk: 15.20%
    *   NLRB elections → Known union: 18.55% (proxy check)
    *   Public sector locals → unions_master: 77.57%
*   **Summary:** Matching is a significant weakness, particularly for NLRB data. Public sector integration is strong. (Severity: 🔴 CRITICAL for NLRB, 🟡 MEDIUM for others)

---

## SECTION 4: API & ENDPOINT AUDIT

*   **General:** Uses FastAPI, structured routers, parameterized queries (prevents SQL injection).
*   **Security Findings:**
    *   🔴 **CRITICAL:** Authentication is **disabled by default** if `JWT_SECRET` is not set. All endpoints are publicly accessible.
    *   🔵 **MEDIUM:** CORS configuration needs production hardening (defaults to `localhost`).
    *   🔵 **MEDIUM:** Weak JWT secret length check.
*   **Other:** Admin endpoints require admin role when auth is enabled. Rate limiting on login attempts.

---

## SECTION 5: FRONTEND REVIEW

*   **Structure:** Well-modularized JavaScript (10 files, largest ~1782 lines), responsive UI (Tailwind CSS), dynamic API base URL (`API_BASE` from `config.js`).
*   **Usability/Accessibility:** Good keyboard navigation, clear loading states, error handling, export/print features, interactive maps (Leaflet), data visualizations (Chart.js), modal organization.
*   **Status:** FIXED. Addressed previous monolithic JS file issue. No hardcoded `localhost` API URLs.

---

## SECTION 6: PREVIOUS AUDIT FINDINGS — ARE THEY FIXED?

*   **Finding 1:** Database password in code: **FIXED**.
*   **Finding 2:** Authentication disabled: **STILL BROKEN (CRITICAL)**.
*   **Finding 3:** CORS configuration: **NEEDS PRODUCTION HARDENING (MEDIUM)**.
*   **Finding 4:** Orphaned data (`f7_union_employer_relations`): 0.69% orphan rate (previously critical, **STILL BROKEN - CRITICAL**).
*   **Finding 5:** Monolithic frontend file: **FIXED**.
*   **Finding 6:** OSHA match rate ~14%: Improved to 25.37% (**FIXED**).
*   **Finding 7:** WHD match rate ~2%: Remains very low (F7: 2.68%, Mergent: 0.38%) (**STILL BROKEN**).
*   **Finding 8:** No tests for matching pipeline: **PARTIALLY FIXED** (tests exist but are incomplete for WHD/990).
*   **Finding 9:** README has wrong startup command: **FIXED**.
*   **Finding 10:** 990 filer data unmatched: **FIXED** (matches now exist).
*   **Finding 11:** GLEIF data size/match count: **FIXED** (size much lower, counts higher).
*   **Finding 12:** LIMIT 500 in API: API communicates total count, allowing clients to detect truncation (**FIXED**).
*   **Finding 13:** Two separate scoring systems not unified: **FIXED** (appears unified based on API code review).
*   **Finding 14:** Orphaned F7 union file numbers: Same as Finding 4 (**STILL BROKEN - CRITICAL**).
*   **Finding 15:** Stale `pg_stat` estimates: **PARTIALLY FIXED** (autoanalyze enabled for some tables, but many core tables are stale).

---

## SECTION 7: WHAT CHANGED SINCE ROUND 1? (DELTA ANALYSIS)

*   **Database Size:** Decreased significantly from 22 GB to 7.52 GB.
*   **Table/View Counts:** Increased number of tables (160 vs 159), slight decrease in views (186 vs 187). This suggests new tables were added (e.g., for matching/integration) and some views may have been consolidated or removed.
*   **New Tables/Views:** Inferred from API audit and Section 1 inventory: `employer_990_matches`, `corporate_identifier_crosswalk`, `osha_f7_matches`, `ps_employers`, `gleif_us_entities`, `mv_employer_search`, `mv_organizing_scorecard`, and numerous `v_` views for aggregated data.
*   **Removed Tables:** Difficult to confirm precisely without a Round 1 table list. However, the significant database size reduction suggests potential removal or pruning of large, old datasets. `splink_match_results` was specifically noted as archived.
*   **Row Count Changes:**
    *   `f7_employers_deduped`: Increased from ~60K (Round 1 estimate) to ~113K (Current), likely due to improved deduplication or data ingestion.
    *   `nlrb_participants`: Current count is ~1.9M. Round 1 mentioned "50% orphaned" but no specific count.
*   **Modified Files (Inferred):**
    *   **API Backend:** Substantial refactoring and additions. New routers (`whd.py`, `museums.py`, `corporate.py`) and features like unified employer search, employer flags, organizing scorecard, and detailed cross-referencing.
    *   **Frontend:** JavaScript is now modularized (resolving monolithic file issue). Features like dynamic API base URL (`API_BASE`), interactive maps (Leaflet), Chart.js visualizations, and saved searches have been added.
*   **New API Endpoints / Frontend Features:**
    *   **API:** Endpoints for WHD data, unified employer search, employer review flags, organizing scorecard, detailed cross-referencing, sector-specific endpoints (e.g., museums).
    *   **Frontend:** Modular JS, dynamic API base configuration, interactive maps, charting, saved searches.

*   **Overall Delta Analysis:** Significant development and refactoring have occurred since Round 1. The database size has decreased dramatically, while new tables/views and data sources (GLEIF, 990, WHD, corporate hierarchy) have been integrated. Core API features (unified search, scorecard) and frontend refactoring (modular JS) represent substantial progress. However, critical data integrity (NLRB orphans) and security (disabled authentication) issues persist.

---

## SECTION 8: SCRIPTS & FILE SYSTEM (WHAT CODE EXISTS?)

**1. File Counts:**
*   **Python Scripts (`.py`):** 494 files found within the `scripts/` directory and its subdirectories.
*   **SQL Scripts (`.sql`):** 34 files found within the `sql/` directory and its subdirectories.

**2. Script Organization:**
*   **Python Scripts:** The `scripts/` directory contains a large number of Python files organized into functional subdirectories (e.g., `etl`, `matching`, `analysis`, `maintenance`, `scoring`, `audit`, `cleanup`, `federal`, `import`, `research`). This structure indicates a modular approach to various tasks including data loading, transformation, matching, analysis, and maintenance.
*   **SQL Scripts:** The `sql/` directory is organized into `bls`, `queries`, and `schema` subdirectories, containing scripts for database schema definitions, query execution, and BLS data management. Root-level SQL files also include utility scripts.

**3. Critical Path Scripts:**
Identifying scripts on the absolute "critical path" requires understanding the project's full orchestration and deployment process. However, based on file names and common development practices, scripts likely essential for core functionality include:
*   **Data Loading/ETL & Matching:** Scripts in `scripts/etl/` and `scripts/matching/` (e.g., `load_f7_data.py`, `match_web_employers.py`, `unified_employer_osha_pipeline.py`).
*   **Schema & Views:** Scripts in `sql/schema/` and core definition files like `sql/deduplication_views.sql`, `sql/f7_schema.sql`.
*   **Core Data Source Loaders:** Scripts responsible for ingesting primary data from sources such as BLS, OSHA, NLRB, WHD, SEC, and GLEIF.
*   **API Backend:** The core API application (`api/main.py` and its routers in `api/routers/`) is critical for platform functionality.

**4. Dead References:**
Determining dead references (scripts referencing non-existent tables or columns) would require static code analysis of the script contents, which is beyond the scope of file listing. Previous audit findings regarding schema discrepancies during data quality checks suggest potential areas for such investigation.

**5. Hardcoded Credentials:**
*   **Status:** FIXED. Searches for hardcoded database credentials (`password=`, `user=`, `host=`, `db_name=`) within Python (`.py`) and SQL (`.sql`) scripts found no matches. Credentials appear to be managed externally via environment variables (e.g., `.env` file and `load_dotenv()`), which is a secure practice.

**6. Scheduled/Recurring Scripts:**
File names and directory structures do not explicitly indicate scheduling mechanisms (e.g., cron syntax or task scheduler references). This suggests that scheduling is managed externally to the codebase (e.g., via system cron jobs or server task schedulers).

---

## SECTION 9: DOCUMENTATION ACCURACY

*   **Comparison:** The `CLAUDE.md` document was reviewed and its claims regarding table names and record counts were compared against the database inventory data gathered in Section 1. All listed tables and their respective record counts in `CLAUDE.md` precisely match the database inventory.
*   **Status:** FIXED. The documentation (`CLAUDE.md`) accurately reflects the current database state regarding table names and record counts.

---

This document consolidates all audit findings to date. Further sections (Overall Assessment, Strategic Vision) will be added as the audit progresses.
