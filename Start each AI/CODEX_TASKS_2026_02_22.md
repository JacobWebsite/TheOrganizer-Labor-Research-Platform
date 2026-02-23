# Codex Tasks (2026-02-22)

## Project Context

**Read these docs first** (in order):
1. `Start each AI/PROJECT_STATE.md` -- live status, latest numbers, known issues
2. `Start each AI/UNIFIED_ROADMAP_2026_02_19.md` -- phased plan (A-G), what's done vs remaining
3. `Start each AI/UNIFIED_PLATFORM_REDESIGN_SPEC.md` -- target architecture for scoring, React frontend, master employer vision
4. `Start each AI/CLAUDE.md` -- technical reference (DB schema, API, scripts, conventions)

### What This Project Is

A **labor union organizing research platform**. It ingests data from 10+ federal sources (OSHA violations, NLRB elections, DOL wage theft, SAM.gov government contracts, IRS 990 filings, SEC EDGAR, Mergent business data, GLEIF corporate ownership, BLS statistics) and cross-matches them against the DOL's F-7 union-employer filings to help labor organizers identify and research employer targets.

- **Database:** PostgreSQL `olms_multiyear` on localhost, user `postgres`
- **Backend:** FastAPI (`api/main.py`, port 8001)
- **Frontend:** Vanilla JS (`files/organizer_v5.html`) -- React migration planned
- **146,863 F7 employers** in `f7_employers_deduped` (the primary employer table)
- **3,026,290 master employers** in `master_employers` (seeded from F7 + SAM + Mergent + BMF, NOT yet deduped)
- **3,080,492 source ID mappings** in `master_employer_source_ids`
- **1,738,115 cross-source match records** in `unified_match_log`
- **4 key MVs:** `mv_organizing_scorecard` (212K), `mv_employer_data_sources` (147K), `mv_unified_scorecard` (147K), `mv_employer_search` (107K)
- **479 tests**, 478 passing (1 pre-existing hospital abbreviation failure)
- **MV refresh JUST COMPLETED (2026-02-22):** NLRB 7yr decay, BLS financial fix, NLRB flag alignment all now live

### What's Already Done

| Phase | Status | Summary |
|-------|--------|---------|
| **Phases 1-5** | DONE | Core platform, ETL, matching pipeline, scoring, frontend |
| **Phase A** | DONE | Data quality fixes (scorecard, corporate endpoints, match inflation, time boundaries) |
| **Phase B** | DONE | Matching pipeline overhaul (tier reorder, best-match-wins, Splink integration, full re-run) |
| **Phase C** | DONE | Missing unions resolution (195 orphans -> 0 active) |
| **Phase D** | DONE | Auth hardening, GLEIF archive, cleanup, docs refresh |
| **Phase E1+E3** | DONE | Employer data sources MV + unified scorecard MV (7 factors, signal-strength scoring) |
| **Phase G seeding** | DONE | master_employers: 3,026,290 rows. master_employer_source_ids: 3,080,492 |
| **MV refresh** | DONE (today) | All 4 MVs refreshed. NLRB decay + financial fix now live. unified_score avg=3.72 |

### Current Unified Scorecard (7 factors, equal weight)

The current `mv_unified_scorecard` has 7 factors scored 0-10 each with equal weight:

| Factor | Column | Coverage | Avg Score |
|--------|--------|----------|-----------|
| OSHA Safety | `score_osha` | 21.4% | 1.49 |
| NLRB Activity | `score_nlrb` | 3.8% | 2.60 |
| Wage Theft | `score_whd` | 8.2% | 1.18 |
| Gov Contracts | `score_contracts` | 5.9% | 6.37 |
| Union Proximity | `score_union_proximity` | 100% | 3.26 |
| Financial/Industry | `score_financial` | 84.9% | 3.22 |
| Employer Size | `score_size` | 100% | 5.08 |

**Current formula:** `unified_score = AVG(non-null factors)`. All factors weighted equally.
**Current tiers:** TOP >= 7, HIGH >= 5, MEDIUM >= 3.5, LOW < 3.5.

### Key Technical Conventions

- **DB access:** Always `from db_config import get_connection` (project root). Returns bare psycopg2 connection (tuples). Pass `cursor_factory=RealDictCursor` for dict access.
- **f7_employer_id is TEXT** (hash string). All match tables must use TEXT for this column.
- **EIN is NOT unique** per employer -- subsidiaries share parent EINs, some are reused.
- **master_employers.id is BIGSERIAL** (auto-increment integer PK).
- **Encoding:** ASCII only in print statements. Windows cp1252 crashes on Unicode arrows/emoji.
- **Python 3.14:** Watch for `\s` escape warnings in regex strings. Use raw strings (`r'\s'`).
- **`naics_sectors` column is `sector_name`** -- NOT `naics_sector_name`.
- **`SELECT EXISTS(...)` with RealDictCursor** -- MUST alias: `SELECT EXISTS(...) AS e`.
- **`SELECT COUNT(*)` with RealDictCursor** -- alias as `AS cnt` for clarity.
- **psycopg2 `%%` for pg_trgm `%` operator** -- only when params tuple is passed.
- **NEVER use `TRUNCATE ... CASCADE` on parent FK tables** -- cascades to child tables.

---

## Task 1: Implement 8-Factor Weighted Scoring

### Context

The `UNIFIED_PLATFORM_REDESIGN_SPEC.md` Section 2 defines a new scoring system that supersedes the current 7-factor equal-weight approach. The new system has:

1. **8 factors** (adds "Statistical Similarity" using Gower distance engine)
2. **Weighted average** (3x/2x/1x tiers instead of equal weight)
3. **Percentile-based tier labels** (Priority/Strong/Promising/Moderate/Low instead of fixed thresholds TOP/HIGH/MEDIUM/LOW)

### Target Scoring System (from Redesign Spec Section 2)

#### 8 Factors with Weights

| Factor | Weight | Score Logic |
|--------|--------|-------------|
| **Union Proximity** (3x) | 3 | 2+ unionized siblings=10, 1 sibling OR corporate family=5, none=0. No data -> skip. |
| **Employer Size** (3x) | 3 | Under 15=0, 15-500 linear ramp 0-10, 500+ plateau=10. No data -> skip. |
| **NLRB Activity** (3x) | 3 | 70% nearby momentum + 30% own history. Wins positive, losses NEGATIVE. 7yr half-life. No data -> skip. |
| **Gov Contracts** (2x) | 2 | None=0, Federal only=4, State only=6, City only=7, any two=8, all three=10. Dollar value is tiebreaker only. No data -> skip. |
| **Industry Growth** (2x) | 2 | BLS 10yr projections mapped linearly to 0-10. No NAICS -> skip. |
| **Statistical Similarity** (2x) | 2 | Combination of: how many comparable unionized employers found + how close best matches are. Only for employers WITHOUT corporate/sibling union. No data -> skip. |
| **OSHA Safety** (1x) | 1 | Industry-normalized violations. 5yr half-life (NOT 10yr). +1 for willful/repeat (capped at 10). No data -> skip. |
| **WHD Wage Theft** (1x) | 1 | 0 cases=0, 1=5, 2-3=7, 4+=10. 5yr half-life (NOT 7yr). No data -> skip. |

#### Weighted Average Formula

```
weighted_score = SUM(factor_score * factor_weight) / SUM(weight of factors with data)
```

Example: OSHA=6 (1x), NLRB=8 (3x), Contracts=7 (2x), Size=10 (3x)
= (6*1 + 8*3 + 7*2 + 10*3) / (1+3+2+3) = 74/9 = 8.2

#### Percentile-Based Tiers

| Tier | Percentile | Approx Count |
|------|-----------|-------------|
| **Priority** | Top 3% | ~4,400 |
| **Strong** | Next 12% | ~17,600 |
| **Promising** | Next 25% | ~36,700 |
| **Moderate** | Next 35% | ~51,400 |
| **Low** | Bottom 25% | ~36,700 |

### What to Build

#### 1. Update `scripts/scoring/build_unified_scorecard.py`

Modify the existing MV SQL to implement the new scoring:

**Changes to existing factors:**
- `score_osha`: Change half-life from 10yr to **5yr** (change `exp(-LN(2)/10 * ...)` to `exp(-LN(2)/5 * ...)`)
- `score_whd`: Change half-life from 7yr to **5yr**, simplify scoring to case-count-based (0=0, 1=5, 2-3=7, 4+=10)
- `score_union_proximity`: Update to binary: 2+ siblings=10, 1 sibling or corporate family=5, none=0. Skip if no group data AND no corporate family.
- `score_contracts`: Update to multi-level (federal=4, state=6, city=7, two levels=8, all three=10). Currently only has federal data -- design to accommodate state/city when available.
- `score_financial`: Rename to `score_industry_growth`. Simplify to BLS projection linear mapping only. Drop public/nonprofit boost.
- `score_size`: Update to Under 15=0, 15-500 linear ramp, 500+ plateau at 10.
- `score_nlrb`: Current implementation is close. The "70% nearby + 30% own history" with losses as negative requires a CTE for nearby elections within 25 miles of each employer. **NOTE:** The platform does NOT currently have employer lat/lng coordinates, so the "25 miles nearby" calculation is not possible yet. For now, keep the current NLRB scoring approach but apply the 7yr half-life (already implemented). Add a TODO comment noting the nearby-momentum feature needs geocoding first.

**New factor:**
- `score_similarity` (2x): NEW. Use the existing `employer_comparables` table (269K rows, 5 comparables per employer). Score based on:
  - How many of the 5 comparables have unions
  - How close the best comparable is (Gower distance)
  - NULL for employers that already have union proximity score >= 5 (avoid double-counting)

  Suggested formula:
  ```sql
  -- For employers WITHOUT strong union proximity (score_union_proximity < 5):
  -- Count unionized comparables (0-5) and best similarity score
  -- 5 unionized comparables = 10, 4 = 8, 3 = 6, 2 = 4, 1 = 2, 0 = 0
  -- Boost by 1 if best comparable is very similar (distance < 0.15)
  ```

**New columns in MV:**
- `score_similarity` (0-10, NULL if no comparables or union proximity >= 5)
- `weighted_score` (0-10, replacing `unified_score`) -- uses weighted average formula
- `score_tier` -- percentile-based: Priority/Strong/Promising/Moderate/Low
- `total_weight` -- sum of weights of factors with data (for transparency)

**Keep existing columns** for backward compatibility:
- `unified_score` -- keep as alias/copy of `weighted_score`
- All 7 existing factor columns -- keep them, just update their logic

**Percentile calculation:**
The tier assignment uses `PERCENT_RANK()` window function:
```sql
PERCENT_RANK() OVER (ORDER BY weighted_score ASC) AS score_percentile,
CASE
    WHEN PERCENT_RANK() OVER (ORDER BY weighted_score ASC) >= 0.97 THEN 'Priority'
    WHEN PERCENT_RANK() OVER (ORDER BY weighted_score ASC) >= 0.85 THEN 'Strong'
    WHEN PERCENT_RANK() OVER (ORDER BY weighted_score ASC) >= 0.60 THEN 'Promising'
    WHEN PERCENT_RANK() OVER (ORDER BY weighted_score ASC) >= 0.25 THEN 'Moderate'
    ELSE 'Low'
END AS score_tier
```

#### 2. Update `scripts/scoring/build_employer_data_sources.py`

No changes needed to data sources MV -- it doesn't contain scoring logic.

#### 3. Update API endpoints

In `api/routers/scorecard.py`:
- The `/api/scorecard/unified` endpoint should return `weighted_score`, `score_tier` (new names), `score_similarity`, `total_weight`
- The `/api/scorecard/unified/stats` endpoint should return tier distribution using new tier names (Priority/Strong/Promising/Moderate/Low)
- The `/api/scorecard/unified/{employer_id}` detail endpoint should include `score_similarity` and explain factor weights in the explanation text
- Keep old field names (`unified_score`, `score_tier` with TOP/HIGH/MEDIUM/LOW) as aliases for backward compatibility

In `api/routers/profile.py`:
- Update the employer profile endpoint to include `score_similarity` and `weighted_score`

#### 4. Write tests

Create `tests/test_weighted_scorecard.py` with:
- Test that `weighted_score` uses correct weighted average formula (mock a known employer)
- Test that `score_similarity` is NULL when union proximity >= 5
- Test that `score_similarity` is non-NULL when comparables exist and union proximity < 5
- Test percentile-based tier distribution (Priority ~3%, Strong ~12%, etc. -- allow 1% tolerance)
- Test that OSHA decay is 5yr (not 10yr)
- Test that WHD scoring uses case count (0=0, 1=5, 2-3=7, 4+=10)
- Test that all 8 factor columns exist in MV
- Test that `weighted_score` and `unified_score` are equal (alias)
- Test backward compatibility: old tier names still work in API responses

### Important Notes

- The `employer_comparables` table has columns: `employer_id`, `comparable_employer_id`, `gower_distance`, `rank` (1-5). Lower distance = more similar.
- To check if a comparable employer has a union, join `employer_comparables` to `f7_employers_deduped` on `comparable_employer_id = employer_id` and check `latest_union_fnum IS NOT NULL`.
- The `employer_comparables` table may not have rows for all employers (only 54,968 in `mv_employer_features`). Employers without comparables get `score_similarity = NULL`.
- **Do NOT delete or rename the `unified_score` column** -- keep it as a copy of `weighted_score` for backward compatibility. Frontend JS references `unified_score`.

### Verification

After building, the refresh should show:
```
Score range: ~0.5 - 10.0, avg should shift due to weights
Tier distribution:
  Priority  : ~4,400 (3%)
  Strong    : ~17,600 (12%)
  Promising : ~36,700 (25%)
  Moderate  : ~51,400 (35%)
  Low       : ~36,700 (25%)
```

Run `py -m pytest tests/ -q` -- all existing tests + new tests should pass (except the 1 known failure).

### Do NOT

- Modify `build_employer_data_sources.py` (data sources MV is separate from scoring)
- Modify `rebuild_search_mv.py`
- Modify `run_deterministic.py` or any matching code
- Drop or rename existing columns (backward compatibility)
- Modify frontend files (that's a separate task)

---

## Task 2: Master Employer Dedup Pipeline

### Context

The `master_employers` table was seeded on 2026-02-22 with 3,026,290 rows from 4 sources:
- **F7:** 146,863 (already deduped within F7)
- **SAM:** 797,226
- **Mergent:** 54,859
- **BMF:** 2,027,342

During seeding, BMF records were matched to existing masters via EIN (7,602 matches) and name+state (8,835 matches), but the SAM, Mergent, and BMF records that did NOT match existing masters were inserted as new rows. This means there are likely **hundreds of thousands of duplicates** across sources -- the same real-world employer appearing as separate master records from SAM, BMF, and Mergent.

### Current Schema

```sql
-- master_employers (3,026,290 rows)
CREATE TABLE master_employers (
    id BIGSERIAL PRIMARY KEY,
    canonical_name TEXT NOT NULL,
    display_name TEXT NOT NULL,
    city TEXT,
    state TEXT,
    zip TEXT,
    naics TEXT,
    employee_count INTEGER,
    employee_count_source TEXT,
    ein TEXT,           -- NOT unique (subsidiaries share)
    is_union BOOLEAN DEFAULT FALSE,
    is_public BOOLEAN DEFAULT FALSE,
    is_federal_contractor BOOLEAN DEFAULT FALSE,
    is_nonprofit BOOLEAN DEFAULT FALSE,
    is_labor_org BOOLEAN DEFAULT FALSE,
    source_origin TEXT NOT NULL,  -- 'f7', 'sam', 'mergent', 'bmf'
    data_quality_score INTEGER DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- master_employer_source_ids (3,080,492 rows)
CREATE TABLE master_employer_source_ids (
    master_id BIGINT REFERENCES master_employers(id),
    source_system TEXT NOT NULL,
    source_id TEXT NOT NULL,
    match_confidence NUMERIC(5,4),
    matched_at TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (master_id, source_system, source_id)
);
```

### Source Breakdown in master_employer_source_ids

| source_system | Count | Notes |
|--------------|-------|-------|
| bmf | 2,043,779 | Many matched to existing masters via EIN/name |
| sam | 833,538 | |
| f7 | 146,863 | 1:1 with f7_employers_deduped |
| mergent | 56,312 | |

### What to Build

Create `scripts/etl/dedup_master_employers.py` that performs cross-source deduplication:

#### Phase 1: EIN-Based Merge (highest confidence)

```
Find master_employers records that share the same EIN but have different IDs.
Group by EIN. Within each group, pick a "winner" (priority: f7 > sam > mergent > bmf).
Merge losers into winner:
  - Move all source_ids from loser to winner
  - Update winner's fields if loser has better data (e.g., winner has no employee_count, loser does)
  - Log merge in master_employer_merge_log
  - DELETE loser from master_employers
```

**Important EIN caveats:**
- EIN is NOT unique per real-world entity. Subsidiaries share parent EINs. Some EINs are reused across unrelated entities after dissolution.
- Only merge when EIN matches AND (name similarity >= 0.70 OR same state). Do NOT blindly merge all same-EIN records.
- Use `rapidfuzz.fuzz.token_sort_ratio` for name similarity (same library used throughout project).

#### Phase 2: Name + State Exact Merge

```
Find records with same canonical_name + same state but different IDs.
Merge using same winner-selection logic as Phase 1.
```

**Important:** `canonical_name` is already normalized (lowercase, stripped suffixes). This is high-confidence.

#### Phase 3: Name + State Fuzzy Merge

```
For remaining records, find pairs where:
  - Same state
  - token_sort_ratio(canonical_name_a, canonical_name_b) >= 0.85
  - At least one confirming signal (same city, same zip prefix, same NAICS 2-digit)
Merge with lower confidence logged.
```

**Important:** This phase is slower and riskier. Must support `--dry-run` and `--limit N`.

#### Phase 4: Populate `data_quality_score`

After dedup, set `data_quality_score` based on:
- Number of distinct source_systems in source_ids (1 source=20, 2=40, 3=60, 4=80, 5+=100)
- Bonus: +10 if has EIN, +10 if has employee_count

#### CLI Flags

```
py scripts/etl/dedup_master_employers.py [options]

  --phase 1|2|3|4|all    Which phase to run (default: all)
  --dry-run              Count merges but don't execute
  --limit N              Process only first N groups (for testing)
  --batch-size N         Commit every N merges (default: 1000)
  --min-name-sim FLOAT   Minimum name similarity for Phase 3 (default: 0.85)
  --verbose              Print each merge decision
```

#### Output Summary

Print after each phase:
```
Phase 1 (EIN merge):
  Groups found: X
  Merges executed: Y
  Records eliminated: Z

Phase 2 (Name+State exact):
  Groups found: X
  Merges executed: Y
  Records eliminated: Z

Phase 3 (Name+State fuzzy):
  Candidate pairs: X
  Merges executed: Y
  Records eliminated: Z

Phase 4 (Quality scores):
  Updated: X records
  Distribution: 0-20: N, 21-40: N, 41-60: N, 61-80: N, 81-100: N

Final: master_employers went from A to B rows (C% reduction)
```

#### Merge Log Table

Create if not exists:
```sql
CREATE TABLE IF NOT EXISTS master_employer_merge_log (
    merge_id BIGSERIAL PRIMARY KEY,
    winner_master_id BIGINT NOT NULL,
    loser_master_id BIGINT NOT NULL,
    merge_phase TEXT NOT NULL,       -- 'ein', 'name_state_exact', 'name_state_fuzzy'
    merge_confidence NUMERIC(5,4),
    merge_evidence JSONB,            -- {"ein": "123456789", "name_sim": 0.92, ...}
    merged_at TIMESTAMPTZ DEFAULT NOW()
);
```

### Constraints

- Use `from db_config import get_connection` for database access.
- ASCII only in print statements (Windows cp1252).
- Python 3.14 -- use raw strings for regex.
- Transaction safety: each batch of merges in a transaction. Rollback on error.
- Do NOT modify `f7_employers_deduped`, `sam_entities`, `mergent_employers`, `irs_bmf`, or any source tables.
- Do NOT modify the matching pipeline.
- Do NOT modify test files.
- The F7 source records in master_employers should NEVER be merge losers (they are the canonical base).

### Verification

After running:
```sql
-- Should be significantly fewer rows
SELECT COUNT(*) FROM master_employers;  -- Target: 500K-1.5M (down from 3M)

-- Source distribution should still have all sources
SELECT source_origin, COUNT(*) FROM master_employers GROUP BY 1 ORDER BY 2 DESC;

-- Merge log should have entries
SELECT merge_phase, COUNT(*) FROM master_employer_merge_log GROUP BY 1;

-- No orphaned source_ids
SELECT COUNT(*) FROM master_employer_source_ids s
LEFT JOIN master_employers m ON m.id = s.master_id
WHERE m.id IS NULL;  -- Should be 0

-- Quality scores populated
SELECT
  CASE WHEN data_quality_score <= 20 THEN '0-20'
       WHEN data_quality_score <= 40 THEN '21-40'
       WHEN data_quality_score <= 60 THEN '41-60'
       WHEN data_quality_score <= 80 THEN '61-80'
       ELSE '81-100' END AS tier,
  COUNT(*)
FROM master_employers GROUP BY 1 ORDER BY 1;
```

### Do NOT

- Modify source tables (f7_employers_deduped, sam_entities, etc.)
- Modify the matching pipeline
- Modify test files
- Delete master_employers records with source_origin='f7' (these are canonical)
- Run the script automatically -- just create it. We'll run and validate interactively.

---

## Task 3: Master Employer API Endpoints

### Context

The master employer table (after dedup from Task 2) will contain the full universe of employers -- both unionized (from F7) and non-unionized (from SAM, OSHA, BMF, Mergent). This is the foundation for the platform's #1 feature: non-union target discovery.

Currently all search/profile endpoints only cover F7 employers (146,863). The master table will expose 500K-1.5M+ employers.

### What to Build

#### 1. Create `api/routers/master.py`

New router with prefix `/api/master/`.

**Endpoints:**

`GET /api/master/search`
- Parameters: `q` (name search), `state`, `naics`, `min_employees`, `max_employees`, `source_origin` (filter by origin), `has_union` (bool), `is_federal_contractor` (bool), `is_nonprofit` (bool), `min_quality` (0-100), `sort` (name/quality/employees), `order` (asc/desc), `page`, `limit` (default 25, max 100)
- Returns: paginated list with `total`, `page`, `pages`, `results[]`
- Each result: `id`, `display_name`, `city`, `state`, `naics`, `employee_count`, `is_union`, `is_federal_contractor`, `is_nonprofit`, `is_labor_org`, `source_origin`, `data_quality_score`, `source_count` (from source_ids)
- Name search uses `canonical_name ILIKE '%' || normalize(q) || '%'` or trigram if pg_trgm is available on master_employers
- **Performance:** master_employers will be 500K-1.5M rows. Use proper indexes. Add `CREATE INDEX IF NOT EXISTS` in the router's startup or in a migration.

`GET /api/master/{id}`
- Returns full employer profile from master table + all linked source data
- Include: basic info from master_employers + all source_ids from master_employer_source_ids
- If employer has F7 link: include unified scorecard data (join via source_id where source_system='f7')
- If employer has OSHA link: include violation summary
- If employer has NLRB link: include election history
- If employer has WHD link: include case summary
- If employer has SAM link: include contractor info
- If employer has BMF link: include nonprofit info

`GET /api/master/stats`
- Returns: total count, count by source_origin, count by state (top 20), count by is_union/is_nonprofit/is_federal_contractor, quality score distribution, avg source_count

`GET /api/master/non-union-targets`
- Pre-filtered to: `is_union = FALSE AND is_labor_org = FALSE AND data_quality_score >= 40`
- Same search/filter params as `/search`
- Ordered by `data_quality_score DESC` by default
- This is the key "discovery" endpoint

#### 2. Register router in `api/main.py`

Add `from api.routers import master` and include the router.

#### 3. Write tests

Create `tests/test_master_employers.py` with:
- Test `/api/master/stats` returns expected structure
- Test `/api/master/search` with name query returns results
- Test `/api/master/search` with state filter
- Test `/api/master/search` pagination
- Test `/api/master/{id}` for a known F7 employer (should include scorecard data)
- Test `/api/master/{id}` for a non-F7 employer (should NOT include scorecard data)
- Test `/api/master/{id}` returns 404 for bogus ID
- Test `/api/master/non-union-targets` excludes union employers
- Test `/api/master/non-union-targets` excludes labor orgs

#### 4. Indexes

Create these indexes if they don't exist (can be in the router file or a separate migration):
```sql
CREATE INDEX IF NOT EXISTS idx_master_employers_canonical_name_trgm
    ON master_employers USING gin (canonical_name gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_master_employers_state ON master_employers(state);
CREATE INDEX IF NOT EXISTS idx_master_employers_ein ON master_employers(ein);
CREATE INDEX IF NOT EXISTS idx_master_employers_naics ON master_employers(naics);
CREATE INDEX IF NOT EXISTS idx_master_employers_source_origin ON master_employers(source_origin);
CREATE INDEX IF NOT EXISTS idx_master_employers_quality ON master_employers(data_quality_score);
CREATE INDEX IF NOT EXISTS idx_master_employers_union ON master_employers(is_union);
```

### Constraints

- Use `from api.database import get_db` for database connections (NOT db_config -- API uses its own pool).
- Use `from api.helpers import safe_sort_col, safe_order_dir` for SQL injection prevention.
- Follow the patterns in existing routers (see `api/routers/employers.py`, `api/routers/scorecard.py`).
- All endpoints must handle empty results gracefully (return empty list, not 500).
- Add proper docstrings for Swagger/OpenAPI docs.
- Use `Depends(require_auth)` on any write endpoints (none in this task, but good practice for future).

### Do NOT

- Modify existing routers (employers.py, scorecard.py, etc.)
- Modify the master_employers table schema
- Modify the matching pipeline
- Run database migrations -- just create the migration SQL as comments or a separate file

---

## Reference Files

For all tasks, these files contain patterns and conventions to follow:

| File | Why Read It |
|------|------------|
| `Start each AI/PROJECT_STATE.md` | Current status, latest numbers, known issues |
| `Start each AI/UNIFIED_ROADMAP_2026_02_19.md` | Phase G master employer plan (tasks G1-G7) |
| `Start each AI/UNIFIED_PLATFORM_REDESIGN_SPEC.md` | Target architecture -- Section 2 for scoring (Task 1), Section 4 for master employer (Tasks 2-3) |
| `Start each AI/CLAUDE.md` | Technical reference, DB schema, API, conventions |
| `scripts/scoring/build_unified_scorecard.py` | Current scoring MV (Task 1 modifies this) |
| `scripts/scoring/build_employer_data_sources.py` | Data sources MV (context for Task 1) |
| `scripts/scoring/compute_gower_similarity.py` | Gower engine (Task 1 uses comparables) |
| `scripts/etl/seed_master_chunked.py` | Master seeding script (context for Task 2) |
| `api/routers/scorecard.py` | Scorecard API (Task 1 updates, Task 3 pattern) |
| `api/routers/employers.py` | Employer API (Task 3 pattern) |
| `api/routers/profile.py` | Profile API (Task 1 updates) |
| `api/database.py` | API database pool (Task 3 uses this) |
| `api/helpers.py` | SQL safety helpers (Task 3 uses these) |
| `db_config.py` | Database connection helper (Tasks 1-2 use this) |
| `tests/test_unified_scorecard.py` | Existing scorecard tests (Task 1 pattern) |

---

## Execution Order

These tasks have dependencies:

```
Task 1 (8-factor scoring) -- independent, can start immediately
Task 2 (master dedup)     -- independent, can start immediately
Task 3 (master API)       -- depends on Task 2 (needs deduped data for meaningful results)
```

**Tasks 1 and 2 can run in parallel.** Task 3 should wait for Task 2.
