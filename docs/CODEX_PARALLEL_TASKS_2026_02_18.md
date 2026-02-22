# Codex Parallel Tasks — 2026-02-18

**Context:** OSHA matching re-run (B4) is running in 25% batches via Claude Code. These tasks are all independent of that run and of each other. Pick any subset to run in parallel.

**Priority:** Tasks 1, 2, 5 (data quality) > Task 3 (disk space) > Tasks 6, 7 (enrichment) > Task 4 (small fix)

**Database:** PostgreSQL `olms_multiyear`, localhost:5432, user `postgres`. Credentials in `.env` at project root.

**Connection pattern:** `from db_config import get_connection` (db_config.py is at project root, 500+ scripts use it, never move it).

**Key docs:** `PROJECT_STATE.md` (read first), `PIPELINE_MANIFEST.md`, `UNIFIED_ROADMAP_2026_02_17.md`

---

## Task 1: Investigate the 195 Missing Unions (Phase C1-C3)

**Issue:** PROJECT_STATE.md issue #7. 195 missing unions covering 92,627 workers. Rows in `f7_union_employer_relations` reference file numbers not in `unions_master`.

**Steps:**

1. Query how many of the 195 orphaned file numbers appear in `f7_fnum_crosswalk`:

```sql
-- Count orphaned file numbers
SELECT COUNT(DISTINCT r.latest_union_fnum)
FROM f7_union_employer_relations r
LEFT JOIN unions_master u ON u.f_num = r.latest_union_fnum::text
WHERE u.f_num IS NULL;

-- Check crosswalk for remappings
SELECT r.latest_union_fnum, c.new_fnum,
       COUNT(*) AS relation_count,
       SUM(r.members) AS total_workers
FROM f7_union_employer_relations r
LEFT JOIN unions_master u ON u.f_num = r.latest_union_fnum::text
LEFT JOIN f7_fnum_crosswalk c ON c.old_fnum = r.latest_union_fnum::text
WHERE u.f_num IS NULL
GROUP BY r.latest_union_fnum, c.new_fnum
ORDER BY total_workers DESC NULLS LAST;
```

2. For crosswalk hits: verify the `new_fnum` exists in `unions_master`, then UPDATE the relations.
3. For remaining orphans: rank by worker count, list top 20.
4. Write results to `docs/MISSING_UNIONS_ANALYSIS.md` with:
   - How many resolved via crosswalk
   - Top 20 unresolved by worker count
   - Suggested categories (merged, dissolved, data error, unknown)

**Important:** Do NOT modify `f7_union_employer_relations` without explicit approval. Research only, write report.

---

## Task 2: Fix WHD Score Factor (zeros on f7_employers_deduped)

**Issue:** `mv_unified_scorecard`'s `score_whd` factor works (aggregates from `whd_f7_matches` + `whd_cases` directly), but the WHD columns on `f7_employers_deduped` are ALL zeros. Any code reading WHD directly from the employer table gets nothing.

**Steps:**

1. Verify the problem:

```sql
SELECT COUNT(*) FROM f7_employers_deduped WHERE whd_violation_count > 0;
-- Expected: 0
```

2. Check what WHD columns exist:

```sql
SELECT column_name, data_type FROM information_schema.columns
WHERE table_name = 'f7_employers_deduped' AND column_name LIKE 'whd%';
```

3. Check the actual join structure of `whd_f7_matches`:

```sql
SELECT column_name FROM information_schema.columns
WHERE table_name = 'whd_f7_matches';

SELECT column_name FROM information_schema.columns
WHERE table_name = 'whd_cases' AND column_name IN ('case_id', 'bw_amt', 'ee_viols', 'case_id');
```

4. Write an UPDATE that aggregates from `whd_f7_matches` + `whd_cases` (adjust column names based on step 3):

```sql
UPDATE f7_employers_deduped e SET
  whd_violation_count = agg.violations,
  whd_back_wages = agg.back_wages
FROM (
  SELECT m.f7_employer_id,
         COUNT(DISTINCT c.case_id) AS violations,
         COALESCE(SUM(c.bw_amt), 0) AS back_wages
  FROM whd_f7_matches m
  JOIN whd_cases c ON c.case_id = m.case_id
  GROUP BY m.f7_employer_id
) agg
WHERE e.employer_id = agg.f7_employer_id;
```

5. Verify and print summary: how many employers got WHD data, avg violations, max back_wages.

**Important:** Check actual column names on BOTH tables before writing JOINs. The join key on `whd_f7_matches` might be `case_id` or something else — verify with `information_schema.columns` first.

---

## Task 3: Drop Unused Database Indexes (~1.67 GB recovery)

**Issue:** Audit found ~299 confirmed unused indexes consuming ~1.67 GB. They slow down writes and waste space.

**Steps:**

1. Find unused non-unique indexes:

```sql
SELECT schemaname, tablename, indexrelname,
       pg_size_pretty(pg_relation_size(i.indexrelid)) AS size,
       pg_relation_size(i.indexrelid) AS size_bytes,
       idx_scan, idx_tup_read
FROM pg_stat_user_indexes i
JOIN pg_index USING (indexrelid)
WHERE idx_scan = 0
  AND NOT indisunique
  AND NOT indisprimary
ORDER BY pg_relation_size(i.indexrelid) DESC;
```

2. Print the list with sizes. Total up the space.

3. **DROP** indexes that are:
   - Never scanned (`idx_scan = 0`)
   - NOT unique/primary
   - NOT on these core pipeline tables (list but DON'T drop):
     - `unified_match_log`
     - `osha_f7_matches`, `whd_f7_matches`, `sam_f7_matches`, `national_990_f7_matches`
     - `f7_employers_deduped`
     - `corporate_identifier_crosswalk`
     - `mv_organizing_scorecard`, `mv_unified_scorecard`, `mv_employer_data_sources`

4. `VACUUM ANALYZE` the affected tables after dropping.

5. Report total space recovered.

**Important:** Be conservative. If unsure, skip it. Better to leave a useless index than drop a needed one.

---

## Task 4: Fix Freshness Metadata (contracts "3023" bug)

**Issue:** The `data_freshness` table has an entry claiming contracts data runs through year "3023" — obviously a typo. There may be other similar issues.

**Steps:**

1. `SELECT * FROM data_freshness ORDER BY source_name;`
2. Identify any obviously wrong dates (years > 2026, years < 2000, NULL dates).
3. Fix the contracts entry and any other bad rows.
4. Read `scripts/maintenance/create_data_freshness.py` to understand if this is auto-generated or manual.
5. If the script generates it wrong, fix the script. If it's a manual entry, just fix the row.
6. Run: `py scripts/maintenance/create_data_freshness.py --refresh`
7. Verify all dates are reasonable.

---

## Task 5: NLRB ULP Matching Gap Analysis

**Issue:** In `nlrb_participants`, the "Charged Party / Respondent" participant type has 0 `matched_employer_id` values. Only the "Employer" type is matched (5,548 employers with elections). ULPs (unfair labor practice cases) are a key organizing signal but we're missing all employer linkage for them.

**Steps:**

1. Quantify the gap:

```sql
SELECT participant_type,
       COUNT(*) AS total,
       COUNT(matched_employer_id) AS matched,
       COUNT(*) - COUNT(matched_employer_id) AS unmatched
FROM nlrb_participants
GROUP BY participant_type
ORDER BY total DESC;
```

2. Sample 20 "Charged Party / Respondent" rows:

```sql
SELECT participant_name, city, state, case_number
FROM nlrb_participants
WHERE participant_type LIKE 'Charged%'
LIMIT 20;
```

3. Check how many could match F7 by name+state:

```sql
SELECT COUNT(DISTINCT p.id)
FROM nlrb_participants p
JOIN f7_employers_deduped f
  ON UPPER(f.name_standard) = UPPER(p.participant_name)
  AND UPPER(f.state) = UPPER(p.state)
WHERE p.participant_type LIKE 'Charged%'
  AND p.matched_employer_id IS NULL;
```

4. Write findings to `docs/NLRB_ULP_MATCHING_GAP.md`:
   - How many ULP respondents exist
   - How many are matchable by simple name+state
   - Sample matches (are they correct?)
   - Recommendation: should we run the deterministic matcher on these?

**Important:** Research only — do NOT update `nlrb_participants`. Just analyze and report.

---

## Task 6: Catalog Unused OLMS Annual Report Tables (Phase C4)

**Issue:** Four OLMS annual report tables are loaded but not connected to anything yet. They contain high-value union capacity data.

**Tables:**

| Table | Rows | Contains |
|-------|------|----------|
| `ar_disbursements_total` | 216,372 | Union spending by category |
| `ar_membership` | 216,508 | Year-over-year membership counts |
| `ar_assets_investments` | 304,816 | Union financial health |
| `ar_disbursements_emp_off` | 2,813,248 | Payments to union officers |

**Steps:**

1. For each table:
   ```sql
   SELECT column_name, data_type FROM information_schema.columns
   WHERE table_name = '...' ORDER BY ordinal_position;
   ```

2. Sample 5 rows from each.

3. For `ar_disbursements_total`: find columns related to organizing spend. Look for categories like "organizing", "representational activities", etc.:
   ```sql
   SELECT DISTINCT category FROM ar_disbursements_total;  -- or similar column
   ```

4. For `ar_membership`: identify year-over-year membership columns. Calculate: how many unions show growth vs decline?

5. For `ar_assets_investments`: total union assets? Distribution of cash/investments?

6. Write catalog to `docs/OLMS_ANNUAL_REPORT_CATALOG.md`:
   - Schema for each table
   - Key columns and what they mean
   - Sample data
   - Integration priority (Tier 1: organizing spend + membership trends, Tier 2: financial health, Future: officer data)
   - Suggested JOIN keys to connect to `unions_master` and `f7_union_employer_relations`

---

## Task 7: Migrate Remaining Scorecard UI to Unified Scorecard

**Issue:** The unified scorecard (`mv_unified_scorecard`, 146,863 rows, 7 factors each 0-10) has API endpoints built by a previous Codex session, but the frontend may not be fully wired up to use them.

**API endpoints (already exist):**
- `GET /api/scorecard/unified` — list with pagination, state/tier filters
- `GET /api/scorecard/unified/{employer_id}` — detail with per-factor explanations
- `GET /api/scorecard/unified/stats` — aggregate statistics
- `GET /api/scorecard/unified/states` — state list with counts

**Steps:**

1. Read `files/js/scorecard.js` and `files/organizer_v5.html`
2. Read `api/routers/scorecard.py` (new namespace)
3. Read `api/routers/organizing.py` (old scorecard endpoints)
4. Check: does the frontend's unified scorecard mode call `/api/scorecard/unified/*`?
5. If not, wire it up:
   - List view: `GET /api/scorecard/unified?offset=0&page_size=50&state=XX&tier=HIGH`
   - Detail: `GET /api/scorecard/unified/{employer_id}`
   - Stats: `GET /api/scorecard/unified/stats`
   - States: `GET /api/scorecard/unified/states`
6. The unified detail endpoint returns per-factor explanations — render them in the detail modal (`score_osha`, `score_nlrb`, `score_whd`, `score_contracts`, `score_union_proximity`, `score_financial`, `score_size` — each 0-10, NULL if no data)
7. Show `coverage_pct` and `score_tier` in the list view
8. Run tests after changes: `py -m pytest tests/ -q`

**API start:** `py -m uvicorn api.main:app --reload --port 8001`

**Frontend:** `files/organizer_v5.html` (served by API static files at `http://localhost:8001`)

---

## Reminders for All Tasks

- **Python 3.14** on this machine — use `\\s` not `\s` in regex strings (escape warning)
- **Windows cp1252** — use ASCII in print statements (no Unicode arrows)
- **RealDictCursor** — the API pool uses `row['column']`, but `db_config.get_connection()` returns a plain psycopg2 connection with tuple access `row[0]`
- **`SELECT EXISTS(...)` with RealDictCursor** — MUST alias: `SELECT EXISTS(...) AS e`
- **f7_employer_id is TEXT** — all match tables must use TEXT
- **Never `TRUNCATE ... CASCADE`** on parent FK tables
- Commit only when explicitly asked
