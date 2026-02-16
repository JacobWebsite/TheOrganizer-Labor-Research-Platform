## Section 2: Data Quality Deep Dive

### Overview
This section assesses the data quality of core tables within the 'olms_multiyear' database, focusing on column completeness (presence of NULL values), duplicate records, and orphaned records (issues with data consistency across related tables).

### Findings

#### Finding 2.1: 7_employers_deduped - Column Completeness
*   **Description:** The 7_employers_deduped table, containing 146,863 employer records, shows high completeness for critical fields. employer_name has no missing values. street and city have a small percentage of missing values (2.74% and 2.51% respectively).
*   **Severity:** LOW (Missing address components are common in real-world data but could impact location-based analysis if not handled)
*   **Confidence:** Verified

#### Finding 2.2: 7_employers_deduped - Duplicate Records
*   **Description:** No duplicate employer_id values were found, indicating that employer_id effectively serves as a unique identifier. Furthermore, no duplicate combinations of employer_name, street, city, and state were found, which suggests the deduplication process for employers is highly effective.
*   **Severity:** LOW
*   **Confidence:** Verified

#### Finding 2.3: 7_employers_deduped - Orphaned Records
*   **Description:** Checks for orphaned corporate_parent_id (self-referencing) and canonical_group_id (referencing employer_canonical_groups) revealed no issues. All foreign key references appear to be valid.
*   **Severity:** LOW
*   **Confidence:** Verified

#### Finding 2.4: unions_master - Column Completeness
*   **Description:** The unions_master table, containing 26,665 union records, has complete data for _num and union_name (0% NULLs). However, approximately 6.54% of records have missing values for members.
*   **Severity:** MEDIUM (Missing membership data can affect analyses of union strength and reach.)
*   **Confidence:** Verified

#### Finding 2.5: unions_master - Duplicate Records
*   **Description:** No duplicate _num values were found, indicating _num is a unique identifier. However, multiple duplicate combinations of union_name, city, and state were identified (e.g., "STATE COUNTY AND MUNI EMPLS AFL-CIO" in ALBANY, NY appearing 15 times). This could indicate multiple local chapters of the same union are represented with identical names and locations, or a lack of granular unique identifiers for sub-entities.
*   **Severity:** MEDIUM (Potential for misinterpretation of union presence if not properly understood, or if intended to represent unique entities.)
*   **Confidence:** Verified

#### Finding 2.6: unions_master - Orphaned Records
*   **Description:** A significant number of orphaned union_file_number values were found in 7_union_employer_relations that do not correspond to any _num in unions_master. Specifically, 195 distinct union_file_number values in 7_union_employer_relations had no matching record in unions_master. This indicates a break in referential integrity, where employer-union relationships exist for unions that are not defined in the master union list.
*   **Severity:** HIGH (This represents a critical data consistency issue that can lead to incomplete or inaccurate reporting on union-employer relationships.)
*   **Confidence:** Verified

#### Finding 2.7: 
lrb_cases - Column Completeness
*   **Description:** The 
lrb_cases table, with 477,688 records, shows complete data for case_number, egion, case_type, earliest_date, and latest_date (0% NULLs). **However, the case_year column is entirely empty (100% NULLs).**
*   **Severity:** CRITICAL (A completely empty case_year column severely impacts any time-series analysis or filtering by year for NLRB cases. This column is either unused, incorrectly populated, or a major data ingestion failure.)
*   **Confidence:** Verified

#### Finding 2.8: 
lrb_cases - Duplicate Records
*   **Description:** No duplicate case_number values were found, indicating that case_number is a unique identifier for NLRB cases.
*   **Severity:** LOW
*   **Confidence:** Verified

#### Finding 2.9: 
lrb_cases - Orphaned Records
*   **Description:** Checks for orphaned case_number values in 
lrb_participants that reference 
lrb_cases found no issues. All case_number references from 
lrb_participants appear to be valid.
*   **Severity:** LOW
*   **Confidence:** Verified
## Section 3: Materialized Views & Indexes

### Overview
This section reviews the implementation and usage of database views and indexes. It aims to identify the status of materialized views (whether they are up-to-date), assess their size, and analyze index usage to flag any that are unused or potentially missing.

### Findings

#### Finding 3.1: Materialized View Status
*   **Description:** The database contains 4 materialized views: mv_employer_features, mv_employer_search, mv_organizing_scorecard, and mv_whd_employer_agg. All of these materialized views are currently populated and up-to-date (ispopulated = True).
*   **Severity:** LOW
*   **Confidence:** Verified

#### Finding 3.2: View Sizes
*   **Description:** Regular views (non-materialized) consume negligible storage, as they only store their definition. Materialized views, which store pre-computed data, have the following sizes:
    *   mv_employer_features: ~8.9 MB
    *   mv_employer_search: ~36.2 MB
    *   mv_organizing_scorecard: ~7.3 MB
    *   mv_whd_employer_agg: ~46.7 MB
*   **Severity:** LOW (These sizes are reasonable for cached data.)
*   **Confidence:** Verified

#### Finding 3.3: Unused Indexes
*   **Description:** A substantial number of indexes across various tables in the public schema are currently unused, as indicated by a scans_used count of 0. These include primary key indexes for tables like organizing_targets and platform_users, and many other functional indexes (idx_nyc_contracts_agency, idx_smr_prob, etc.). Unused indexes consume disk space and incur overhead during data modification operations (inserts, updates, deletes) without providing any query performance benefits.
*   **Severity:** HIGH (A large number of unused indexes suggests potential database bloat, reduced write performance, and indicates that either the indexes are not correctly designed, or queries are not optimized to use them. This warrants investigation to determine if these indexes can be removed or need to be re-evaluated.)
*   **Confidence:** Verified (Based on direct query of pg_stat_user_indexes)

---
*End of Section 3 Report*
## Section 4: Cross-Reference Integrity

### Overview
This section examines the connections and integrity between various data sources and entities within the database, ensuring that relationships are correctly maintained and references are valid.

### Findings

#### Finding 4.1: Corporate Crosswalk Integrity
*   **Description:** The corporate_hierarchy table, which defines relationships between corporate entities, correctly references employers in the 7_employers_deduped table. No orphaned child_f7_employer_id entries were found in corporate_hierarchy, meaning all child employers linked in the hierarchy exist in the main employer list.
*   **Severity:** LOW
*   **Confidence:** Verified

#### Finding 4.2: OSHA Matching Integrity
*   **Description:** The osha_f7_matches table, responsible for linking OSHA establishments to the main employer data, maintains strong referential integrity. No orphaned 7_employer_id or establishment_id entries were found, confirming that all OSHA matches point to valid employers and OSHA establishments.
*   **Severity:** LOW
*   **Confidence:** Verified

#### Finding 4.3: NLRB Participant-to-Election Linkage Verification
*   **Description:** As noted in the audit instructions, it was expected that a high percentage of NLRB participants would not be linked directly to NLRB elections, as participants include all case types, not just elections. Our analysis found that approximately **92.34%** of NLRB participants are not linked to NLRB election records (1,760,408 out of 1,906,542 total participants). This precisely matches the expected benchmark mentioned in the audit documentation (92.34%).
*   **Severity:** LOW (This is an expected and verified behavior, not an issue.)
*   **Confidence:** Verified

#### Finding 4.4: Public Sector Linkage Integrity
*   **Description:** The ps_employers table, which lists public sector employers, correctly references entities in the 7_employers_deduped table. No orphaned 7_employer_id entries were found, ensuring that all public sector employers are valid entries in the main deduplicated employer list.
*   **Severity:** LOW
*   **Confidence:** Verified

#### Finding 4.5: Scoring Coverage Verification
*   **Description:** The mv_organizing_scorecard materialized view contains 9 distinct score-related columns (score_company_unions, score_industry_density, score_geographic, score_size, score_osha, score_nlrb, score_contracts, score_projections, score_similarity). This aligns perfectly with the audit document's claim of a "Scoring system: 9 factors."
*   **Severity:** LOW
*   **Confidence:** Verified

---
*End of Section 4 Report*
## Section 5: API Endpoint Audit

### Overview
This section audits the API endpoints, focusing on their structure, security, and integrity. The original monolithic API file (labor_api_v6.py) has been refactored into a modular structure under pi/, with endpoints organized into routers by topic.

### Findings

#### Finding 5.1: Modular API Structure
*   **Description:** The API has been successfully refactored from a single file into a modular FastAPI application. Endpoints are logically grouped into 17 different routers (e.g., uth.py, employers.py, 
lrb.py), which improves maintainability and organization. The main entry point is pi/main.py.
*   **Severity:** LOW
*   **Confidence:** Verified

#### Finding 5.2: "Fail-Open" Authentication Mechanism
*   **Description:** The authentication system, managed by AuthMiddleware, is contingent on the JWT_SECRET environment variable. If this secret is not set, authentication is effectively disabled, leaving all endpoints, including administrative ones (/api/admin/*), publicly accessible. This "fail-open" design is a significant security risk if not properly managed in production.
*   **Severity:** CRITICAL
*   **Confidence:** Verified

#### Finding 5.3: Use of F-strings for Dynamic SQL
*   **Description:** Several endpoints across multiple routers (health.py, lookups.py, employers.py, unions.py, 
lrb.py, osha.py, organizing.py, projections.py) use Python f-strings to dynamically construct SQL queries, particularly for WHERE clauses. While the user-provided *values* are correctly parameterized (mitigating SQL injection for values), this pattern of query construction can be risky if not handled with extreme care, as it could potentially allow for manipulation of the query's structure. In the current implementation, this risk is low as the query structure itself is not being manipulated by user input, but it is a pattern to be aware of.
*   **Severity:** LOW
*   **Confidence:** Verified

#### Finding 5.4: External Script Dependency
*   **Description:** The /api/admin/refresh-freshness endpoint executes an external Python script (scripts/maintenance/create_data_freshness.py) using subprocess.run. This creates a dependency on the file system and an external process, which could be a point of failure if the script is not found, has incorrect permissions, or fails to execute. The script itself is well-structured and directly queries the database.
*   **Severity:** LOW
*   **Confidence:** Verified

#### Finding 5.5: Data Type Mismatch in Joins
*   **Description:** Multiple endpoints across various routers (health.py, employers.py, unions.py) use an explicit type cast (::text) when joining 7_employers_deduped.latest_union_fnum (integer) with unions_master.f_num (character varying). This confirms the data type mismatch identified in Section 2, which can impact query performance and indicates an inconsistency in the database schema.
*   **Severity:** MEDIUM
*   **Confidence:** Verified

---
*End of Section 5 Report*
