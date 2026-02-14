# Audit Resolution Prompt — Database & Platform Fixes
## Based on Deep Audit Report (2026-02-13)

**Instructions:** Work through each phase in order. Each checkpoint requires you to STOP and report results before continuing. Use `psql -U postgres -d olms_multiyear` for all database operations. Always wrap destructive operations in transactions where possible. Log everything you do.

**CRITICAL RULES:**
1. **NEVER delete data without a before/after count comparison**
2. **ALWAYS use `BEGIN; ... COMMIT;` transactions for UPDATE/DELETE operations**
3. **STOP at each checkpoint and report results before proceeding**
4. **If any step fails or produces unexpected results, STOP and report — do not continue**
5. **Create a log file at `~/audit_resolution_log.md` and append results from each checkpoint**

---

## PHASE A: Quick Database Wins (Low Risk)

### Checkpoint A1: Add Primary Keys

Verify no duplicates exist, then add primary keys to 4 tables.

```sql
-- Step 1: Verify uniqueness (must all return 0)
SELECT 'f7_employers_deduped' AS tbl, 
  COUNT(*) - COUNT(DISTINCT employer_id) AS duplicates 
  FROM f7_employers_deduped;

SELECT 'whd_f7_matches' AS tbl,
  COUNT(*) - COUNT(DISTINCT (f7_employer_id, whd_case_id)) AS duplicates 
  FROM whd_f7_matches;

SELECT 'national_990_f7_matches' AS tbl,
  COUNT(*) - COUNT(DISTINCT (f7_employer_id, ein)) AS duplicates 
  FROM national_990_f7_matches;

SELECT 'sam_f7_matches' AS tbl,
  COUNT(*) - COUNT(DISTINCT (f7_employer_id, sam_uei)) AS duplicates 
  FROM sam_f7_matches;
```

If ALL return 0 duplicates, proceed:

```sql
ALTER TABLE f7_employers_deduped ADD PRIMARY KEY (employer_id);
```

For the match tables: inspect the columns first to determine the correct natural key for each, then add the primary key. The keys shown above are best guesses — verify the actual column names exist before running. If the column names differ, use the actual column names that form a unique combination.

**STOP: Report which PKs were added and confirm zero duplicates.**

---

### Checkpoint A2: Drop 15 Exact Duplicate Indexes

These are identical twin indexes. Dropping one in each pair is zero-risk — the other copy remains and provides identical functionality.

```sql
-- 1. osha_establishments: duplicate GIN trigram on estab_name_normalized (53 MB)
DROP INDEX IF EXISTS idx_osha_est_name_norm_trgm;

-- 2. sec_companies: duplicate btree on cik (22 MB)
DROP INDEX IF EXISTS idx_sec_cik;

-- 3. f7_employers_deduped: duplicate GIN trigram on employer_name (21 MB)
DROP INDEX IF EXISTS idx_f7_emp_trgm;

-- 4. f7_employers_deduped: duplicate GIN trigram on employer_name_aggressive (20 MB)
DROP INDEX IF EXISTS idx_f7_emp_agg_trgm;

-- 5. osha_f7_matches: duplicate btree on establishment_id (18 MB)
DROP INDEX IF EXISTS idx_osha_f7_est;

-- 6. f7_employers (raw): duplicate btree on lower(employer_name) (13 MB)
DROP INDEX IF EXISTS idx_employer_search_name;

-- 7. nlrb_participants: duplicate btree on matched_employer_id (13 MB)
DROP INDEX IF EXISTS idx_nlrb_part_employer;

-- 8. nlrb_participants: duplicate btree on matched_union_fnum (13 MB)
DROP INDEX IF EXISTS idx_nlrb_part_olms;

-- 9. ar_membership: duplicate btree on rpt_id (3 MB)
DROP INDEX IF EXISTS idx_ar_mem_rptid;

-- 10. lm_data: duplicate btree on f_num (3 MB)
DROP INDEX IF EXISTS idx_lm_fnum;

-- 11. f7_employers (raw): duplicate btree on state (2 MB)
DROP INDEX IF EXISTS idx_employer_search_state;

-- 12. lm_data: duplicate btree on aff_abbr (2 MB)
DROP INDEX IF EXISTS idx_lm_aff;

-- 13. lm_data: duplicate btree on year (2 MB)
DROP INDEX IF EXISTS idx_lm_year;

-- 14. f7_employers_deduped: duplicate btree on state (2 MB)
DROP INDEX IF EXISTS idx_f7_deduped_state;

-- 15. f7_employers_deduped: duplicate btree on union_file_number (2 MB)
DROP INDEX IF EXISTS idx_f7_deduped_union_fnum;

-- BONUS: federal_bargaining_units duplicates
DROP INDEX IF EXISTS idx_fed_bu_agency;
DROP INDEX IF EXISTS idx_fed_bu_union;
```

**STOP: Report how many indexes were dropped successfully and any that didn't exist (already cleaned up).**

---

### Checkpoint A3: Drop 22 Subset/Overlapping Indexes

These are indexes where a single-column index is made redundant by a multi-column index that starts with the same column. The multi-column index handles all queries the single-column one could.

**Before running:** Query the database to identify these 22 subset indexes. The audit identified these notable examples but didn't provide the complete list as SQL:

- `sec_companies`: `idx_sec_name` (46 MB) — redundant with `idx_sec_name_state` (name+state)
- `gleif_us_entities`: `idx_gus_name` (32 MB) — redundant with `idx_gleif_name_state`
- `national_990_filers`: `idx_n990_state` (4 MB) — redundant with `idx_n990_state_name`
- `qcew_annual`: `idx_qcew_area` (13 MB) — redundant with `idx_qcew_area_ind`

Run this query to find ALL subset index pairs across the database:

```sql
SELECT 
  i1.indexrelid::regclass AS redundant_index,
  i2.indexrelid::regclass AS superset_index,
  pg_size_pretty(pg_relation_size(i1.indexrelid)) AS redundant_size,
  i1.indkey AS redundant_cols,
  i2.indkey AS superset_cols
FROM pg_index i1
JOIN pg_index i2 ON i1.indrelid = i2.indrelid 
  AND i1.indexrelid != i2.indexrelid
  AND i1.indisunique = false
  AND i2.indisunique = false
WHERE array_length(i1.indkey, 1) < array_length(i2.indkey, 1)
  AND i1.indkey = i2.indkey[1:array_length(i1.indkey, 1)]
  AND i1.indclass = i2.indclass[1:array_length(i1.indclass, 1)]
ORDER BY pg_relation_size(i1.indexrelid) DESC;
```

Review the results. For each pair: verify the single-column index is truly redundant (same method, same column as the leading column of the multi-column index). Then generate and execute DROP statements for the redundant ones.

**Do NOT drop any index that is part of a UNIQUE or PRIMARY KEY constraint.**

**STOP: Report the full list of subset indexes found and dropped, with sizes.**

---

### Checkpoint A4: Drop Empty Tables and Duplicate Views

```sql
-- 6 empty tables (planned features never built)
DROP TABLE IF EXISTS employer_ein_crosswalk;
DROP TABLE IF EXISTS sic_naics_xwalk;
DROP TABLE IF EXISTS union_affiliation_naics;
DROP TABLE IF EXISTS union_employer_history;
DROP TABLE IF EXISTS vr_employer_match_staging;
DROP TABLE IF EXISTS vr_union_match_staging;

-- 3 duplicate museum views (keep singular, drop plural)
DROP VIEW IF EXISTS v_museums_organizing_targets;
DROP VIEW IF EXISTS v_museums_target_stats;
DROP VIEW IF EXISTS v_museums_unionized;
```

**STOP: Confirm all 9 drops succeeded.**

---

### Checkpoint A5: ANALYZE Materialized Views

```sql
ANALYZE mv_employer_features;
ANALYZE mv_employer_search;
ANALYZE mv_whd_employer_agg;
```

**STOP: Confirm ANALYZE completed on all 3.**

---

## PHASE B: Fix Orphaned Relationships (CRITICAL — Most Important Phase)

This is the single most impactful fix in the entire resolution. Half of all union-employer bargaining links are invisible because they reference old (pre-dedup) employer IDs.

### Checkpoint B1: Before-State Measurement

Run these queries and record the exact numbers:

```sql
-- 1. Count orphaned bargaining links
SELECT 
  COUNT(*) AS total_relations,
  COUNT(*) FILTER (WHERE r.employer_id IN (SELECT employer_id FROM f7_employers_deduped)) AS valid,
  COUNT(*) FILTER (WHERE r.employer_id NOT IN (SELECT employer_id FROM f7_employers_deduped)) AS orphaned
FROM f7_union_employer_relations r;

-- 2. Count orphaned NLRB cross-references
SELECT 
  COUNT(*) AS total_xref,
  COUNT(*) FILTER (WHERE x.f7_employer_id IS NOT NULL) AS has_f7_link,
  COUNT(*) FILTER (WHERE x.f7_employer_id IS NOT NULL 
    AND x.f7_employer_id IN (SELECT employer_id FROM f7_employers_deduped)) AS valid_f7_link,
  COUNT(*) FILTER (WHERE x.f7_employer_id IS NOT NULL 
    AND x.f7_employer_id NOT IN (SELECT employer_id FROM f7_employers_deduped)) AS orphaned_f7_link
FROM nlrb_employer_xref x;

-- 3. Count covered workers in orphaned relations
SELECT 
  SUM(CASE WHEN r.employer_id NOT IN (SELECT employer_id FROM f7_employers_deduped) 
    THEN COALESCE(r.unit_size, 0) ELSE 0 END) AS orphaned_workers,
  SUM(COALESCE(r.unit_size, 0)) AS total_workers
FROM f7_union_employer_relations r;

-- 4. Verify the merge log exists and has data
SELECT COUNT(*) AS merge_log_entries FROM f7_employer_merge_log;

-- 5. Check merge log structure
SELECT * FROM f7_employer_merge_log LIMIT 5;
```

**STOP: Report all before-state numbers. Expected: ~60,373 orphaned relations, ~14,150 orphaned NLRB links, ~7M orphaned workers, merge log should have entries. Also report the column names in f7_employer_merge_log so we know the exact mapping columns (likely old_employer_id → new_employer_id or similar).**

---

### Checkpoint B2: Execute the Orphan Remap

Using the merge log column names identified in B1, build and execute the remap. The pattern will be something like:

```sql
-- Remap f7_union_employer_relations
BEGIN;

UPDATE f7_union_employer_relations r
SET employer_id = m.new_employer_id    -- use actual column name from merge log
FROM f7_employer_merge_log m           
WHERE r.employer_id = m.old_employer_id  -- use actual column name from merge log
  AND r.employer_id NOT IN (SELECT employer_id FROM f7_employers_deduped);

-- Report how many rows were updated
-- (Should be close to 60,373)

COMMIT;
```

```sql
-- Remap nlrb_employer_xref
BEGIN;

UPDATE nlrb_employer_xref x
SET f7_employer_id = m.new_employer_id  -- use actual column name from merge log
FROM f7_employer_merge_log m
WHERE x.f7_employer_id = m.old_employer_id  -- use actual column name from merge log
  AND x.f7_employer_id IS NOT NULL
  AND x.f7_employer_id NOT IN (SELECT employer_id FROM f7_employers_deduped);

-- Report how many rows were updated  
-- (Should be close to 14,150)

COMMIT;
```

**IMPORTANT:** Adapt the column names (`old_employer_id`, `new_employer_id`) to match whatever the actual merge log uses. Check in B1.

**STOP: Report how many rows were updated in each table.**

---

### Checkpoint B3: After-State Verification

Re-run the exact same queries from B1:

```sql
-- Same 3 queries as B1 — count orphaned relations, NLRB xrefs, and workers
```

**Expected results:**
- Orphaned bargaining links: should be near 0 (some may remain if the merge log doesn't cover every old ID)
- Orphaned NLRB links: should be near 0
- Orphaned workers: should drop from ~7M to near 0

**STOP: Report before vs. after comparison for all metrics. If orphaned count did NOT drop significantly, investigate why and report before continuing.**

---

## PHASE C: Migrate Views from Raw to Deduped Table

### Checkpoint C1: Fix 2 Direct-Reference Views

The views `v_f7_employers_fully_adjusted` and `v_f7_private_sector_reconciled` reference the raw `f7_employers` table instead of `f7_employers_deduped`. The 7 other views that reference these will auto-fix once the base views are corrected.

**Steps:**
1. Get the current definition of each view:
```sql
SELECT pg_get_viewdef('v_f7_employers_fully_adjusted'::regclass, true);
SELECT pg_get_viewdef('v_f7_private_sector_reconciled'::regclass, true);
```

2. For each view, create the replacement by changing references from `f7_employers` to `f7_employers_deduped`. You may need to adjust column references if the two tables have different column names.

3. Use `CREATE OR REPLACE VIEW` with the corrected SQL.

4. Verify the fix by comparing row counts:
```sql
-- Before fix, the fully_adjusted view returns ~96K rows (inflated)
-- After fix, it should return ~61K rows (matching deduped table)
SELECT COUNT(*) FROM v_f7_employers_fully_adjusted;
```

5. Spot-check that the 7 indirect views now also show corrected counts:
```sql
SELECT 'v_state_overview' AS view_name, COUNT(*) FROM v_state_overview
UNION ALL
SELECT 'v_union_f7_summary', COUNT(*) FROM v_union_f7_summary
UNION ALL
SELECT 'v_union_members_counted', COUNT(*) FROM v_union_members_counted;
```

**STOP: Report the old and new row counts for the 2 direct views and at least 3 of the indirect views.**

---

## PHASE D: Archive and Drop Splink Table

### Checkpoint D1: Archive splink_match_results

This table is 5.7M rows and 1.6 GB. It was used during the Splink deduplication process and has zero active references (no views, no API endpoints).

```bash
# Step 1: Export to compressed SQL dump
pg_dump -U postgres -d olms_multiyear -t splink_match_results --no-owner --no-privileges | gzip > ~/splink_match_results_archive.sql.gz

# Step 2: Verify the dump file exists and has reasonable size
ls -lh ~/splink_match_results_archive.sql.gz
```

**STOP: Report the archive file size. Only proceed to DROP after confirming the archive exists and is non-empty.**

### Checkpoint D2: Drop splink_match_results

```sql
DROP TABLE IF EXISTS splink_match_results;
```

**STOP: Confirm the table was dropped. Report the freed space (should be ~1.6 GB).**

---

## PHASE E: Clean Up Dead Files

### Checkpoint E1: Delete Dead API Files

```bash
# Delete old monolith API files that are never imported or used
rm -f api/labor_api_v3.py
rm -f api/labor_api_v4_fixed.py
rm -f api/labor_api_v6.py.bak
rm -f api/__pycache__/labor_api_v6.cpython-314.pyc
```

Also delete the 2 broken verify scripts that import from deleted modules:
```bash
rm -f scripts/verify/check_routes2.py
rm -f scripts/verify/test_api.py
```

**STOP: Report which files were deleted and total space freed.**

### Checkpoint E2: Flag Large Unused Files (DO NOT DELETE)

Report the following files to the user for manual review. **DO NOT delete these — just list them with sizes:**

```bash
# Report these files and their sizes:
ls -lh data/free_company_dataset.csv          # Expected: ~5.1 GB, zero references
ls -lh backup_20260209.dump                   # Expected: ~2.06 GB, recreatable
```

**STOP: Report the file sizes. Remind the user these are flagged for manual deletion.**

---

## PHASE F: Fix Broken Password Pattern in 347 Scripts

### Checkpoint F1: Identify and Count Affected Files

```bash
# Count files with the broken pattern
grep -rl "password='os.environ.get" scripts/ archive/ --include="*.py" | wc -l
```

The broken pattern is: `password='os.environ.get('DB_PASSWORD', '')'`
This wraps a function call in quotes, making it a string literal instead of executable code.

### Checkpoint F2: Execute Bulk Fix

The fix depends on what the broken pattern looks like exactly. First, sample a few files:

```bash
grep -n "password='os.environ.get" scripts/*.py | head -10
```

Then build the appropriate sed or python replacement. The goal is to replace the broken pattern with the correct centralized import. There are two viable approaches:

**Approach A (minimal — just fix the quoting):**
Replace `password='os.environ.get('DB_PASSWORD', '')'` with `password=os.environ.get('DB_PASSWORD', '')`

**Approach B (better — use centralized config):**
Replace the entire `psycopg2.connect(...)` block with `from db_config import get_connection` and use `get_connection()` instead.

Use Approach A for the bulk fix (it's safer as a regex replacement). Test on 3 files first, then apply to all.

```bash
# Test on 3 files first — show the diff without applying
# Then apply to all affected files
# Report total files modified
```

**STOP: Report how many files were fixed. Sample-check 3 fixed files to confirm the pattern is correct.**

---

## PHASE G: Rewrite 5 Broken Corporate API Endpoints

### Checkpoint G1: Audit Existing Data for Corporate Features

Before rewriting endpoints, check what data actually exists:

```sql
-- What's in corporate_hierarchy?
SELECT COUNT(*) FROM corporate_hierarchy;
\d corporate_hierarchy

-- What's in corporate_identifier_crosswalk?
SELECT COUNT(*) FROM corporate_identifier_crosswalk;
\d corporate_identifier_crosswalk

-- What's in sec_companies?
SELECT COUNT(*) FROM sec_companies;
\d sec_companies

-- What's in gleif_us_entities?
SELECT COUNT(*) FROM gleif_us_entities;
\d gleif_us_entities

-- What's in gleif_ownership_links?
SELECT COUNT(*) FROM gleif_ownership_links;
\d gleif_ownership_links
```

**STOP: Report the structure and row counts of all 5 tables. This determines how we rewrite the endpoints.**

### Checkpoint G2: Rewrite the 5 Broken Endpoints

The 5 broken endpoints in `api/routers/corporate.py` are:

1. `GET /api/corporate/family/{employer_id}` — Should show corporate siblings/parent
2. `GET /api/corporate/hierarchy/stats` — Should show hierarchy statistics  
3. `GET /api/corporate/hierarchy/{employer_id}` — Should show hierarchy tree
4. `GET /api/corporate/sec/{cik}` — Should look up by SEC CIK number

(The 5th broken endpoint overlaps with one of the above — verify by reading the file.)

**Rewrite strategy:** Use `corporate_identifier_crosswalk` to bridge from employer_id to external identifiers (EIN, DUNS, CIK, LEI, UEI), then join to `sec_companies`, `gleif_us_entities`, and `corporate_hierarchy` as needed. Do NOT reference columns that don't exist on `f7_employers_deduped` (no `corporate_family_id`, no `sec_cik`, no `ultimate_parent_*`).

For each endpoint:
1. Read the current broken code
2. Identify what the endpoint is trying to return
3. Rewrite using existing tables and columns
4. Test the endpoint with curl or the API test suite

**STOP: Report which endpoints were rewritten and show test results for each.**

---

## PHASE H: Full CLAUDE.md Overhaul

### Checkpoint H1: Fix All 24 Documented Inaccuracies

Read the current CLAUDE.md file. Apply ALL of the following corrections based on the audit findings. The audit report (AUDIT_REPORT_2026.md in the project root or uploaded files) contains the exact correct values.

**CRITICAL fixes (7):**
1. Line ~602: Change startup command from `api.labor_api_v6:app` to `api.main:app`
2. Line ~43: Change `nlrb_participants` from 30,399 to 1,906,542
3. Line ~108: Change `splink_match_results` from ~4,600 to "ARCHIVED — was 5,761,285 rows, table has been dropped and archived to ~/splink_match_results_archive.sql.gz"
4. Line ~44: Change `lm_data` from "2.6M+" to 331,238
5. Line ~63: Change `osha_f7_matches` from "79,981 (44.6%)" to "138,340 (13.7% of OSHA establishments / 47.3% of F7 employers)"
6. Line ~107: Change `corporate_identifier_crosswalk` from 14,561 to 25,177
7. Lines ~239, ~264: Change scoring tiers from "MEDIUM >= 15, LOW < 15" to "MEDIUM >= 20, LOW < 20"

**SIGNIFICANT fixes (6):**
8. Lines ~31, ~41: Change `f7_employers_deduped` from 62,163 to 60,953 (in all 5 places it appears)
9. Line ~74: Change WHD match rate from "2,990 (4.8%)" to "24,610 (6.8%)"
10. Line ~48: Change `mv_employer_search` from 120,169 to 118,015
11. Line ~189: Change `mergent_employers` from 56,431 to 56,426
12. Line ~46: Change `manual_employers` from 509 to 520
13. Line ~415: Change scorecard description from "6-factor, 0-100" to "9-factor scorecard" with correct factor list

**ADD missing tables (9):**
Add documentation entries for these tables that are currently not mentioned:
14. `sam_entities` — 826,042 rows, 826 MB — SAM.gov federal contractor registry
15. `sam_f7_matches` — 11,050 rows — SAM-to-F7 employer matches
16. `whd_f7_matches` — 24,610 rows — WHD-to-F7 employer matches
17. `national_990_f7_matches` — 14,059 rows — 990-to-F7 employer matches
18. `employer_comparables` — 269,810 rows — Gower similarity results
19. `nlrb_employer_xref` — 179,275 rows — NLRB-to-F7 cross-reference
20. Annual report tables (4): `ar_disbursements_emp_off` (2,813,248), `ar_membership` (216,508), `ar_disbursements_total` (216,372), `ar_assets_investments` (304,816)
21. `epi_union_membership` — 1,420,064 rows, 322 MB — EPI union membership microdata
22. `employers_990_deduped` — 1,046,167 rows, 265 MB — Deduped national 990 employers

**REMOVE phantom references (2):**
23. Remove reference to `zip_geography` table — does not exist
24. Remove reference to `cbsa_reference` table — correct name is `cbsa_definitions` (935 rows)

**Additional CLAUDE.md updates based on work done in this session:**
- Note that `splink_match_results` has been archived and dropped
- Note that primary keys have been added to `f7_employers_deduped` and match tables
- Note the orphan remap has been completed (update bargaining link counts)
- Update the total table count, view count, and database size to reflect drops
- Add a "Last updated" date at the top of the file

**STOP: Report how many corrections were made. List any corrections that couldn't be applied (e.g., line numbers shifted, section not found, etc.).**

---

## FINAL: Summary Report

After all phases complete, write a final summary to `~/audit_resolution_log.md` containing:

1. **Space recovered:** Total MB/GB freed from indexes, table drops, and file deletions
2. **Orphans fixed:** Before and after counts for both bargaining links and NLRB xrefs
3. **Workers restored to visibility:** How many covered workers are now visible after the remap
4. **Views corrected:** Which views were migrated and their new row counts
5. **Scripts fixed:** How many files had the password pattern corrected
6. **Endpoints fixed:** Which corporate endpoints now work
7. **Documentation:** Summary of CLAUDE.md changes
8. **Remaining issues NOT addressed in this session:**
   - Issue #2: Mergent-to-F7 matching (1.5% linkage — needs separate session)
   - Issue #4: Low-confidence matches below 0.50 (needs manual review first)
   - Issue #10: Large file cleanup beyond the CSV (archive folder, 990 XMLs, etc.)
   - README.md and docs/README.md need similar overhauls
   - Foreign key constraints (Phase C of audit plan — depends on PKs we just added)
   - Materialized view refresh script with timestamp logging
   - SQL injection fixes for museums.py and sectors.py (add allowlists)
   - Integration tests for the orphan remap

---

*End of prompt.*
