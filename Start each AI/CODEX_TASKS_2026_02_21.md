# Codex Tasks (2026-02-21)

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
- **146,863 employers** in `f7_employers_deduped` (the primary employer table, sourced from F-7 filings)
- **1,738,115 cross-source match records** in `unified_match_log` (the central audit trail)
- **3 materialized views** power the API: `mv_organizing_scorecard` (212K), `mv_employer_data_sources` (147K), `mv_unified_scorecard` (147K)
- **464 tests**, 463 passing (1 pre-existing hospital abbreviation failure)

### What's Already Done

| Phase | Status | Summary |
|-------|--------|---------|
| **Phases 1-5** | DONE | Core platform, ETL, matching pipeline, scoring, frontend |
| **Phase A** | DONE | Data quality fixes (scorecard, corporate endpoints, match inflation, time boundaries) |
| **Phase B** | DONE | Matching pipeline overhaul (tier reorder, best-match-wins, Splink integration, full re-run of all 6 sources) |
| **Phase C** | DONE | Missing unions resolution (195 orphans -> 0 active, 138 historical) |
| **Phase D1** | DONE | Auth hardening |
| **Phase E1+E3** | DONE | Employer data sources MV + unified scorecard MV (7 factors, signal-strength scoring) |

### What's Next -- The Dependency Chain

These two Codex tasks are **steps 2 and 3** in the following execution order. Steps 1 and 1b are already done as of today.

```
1.  MV refresh (scorecard + data sources)                    <-- DONE (today)
1b. Legacy table alignment verification                      <-- DONE (2026-02-20)
2.  Load full IRS BMF (1.8M)                                 <-- TASK 1 BELOW
3.  Design master employer table schema                      <-- TASK 2 BELOW
4.  Build SAM -> master seeding pipeline                     (future, depends on 3)
5.  Build Mergent -> master matching pipeline                 (future, depends on 3)
6.  Cross-source dedup (F-7 + SAM + Mergent + BMF)           (future, depends on 2-5)
7.  React frontend build                                     (future, depends on stable APIs)
```

**Why BMF first (Task 1):** The full BMF gives us 1.8M tax-exempt organizations with EINs. EIN is the strongest cross-source join key -- it links nonprofits to their 990 filings, SAM contracts, and SEC filings. Without BMF loaded, the master employer table would be missing its best nonprofit identity bridge. BMF also identifies which employers are labor organizations themselves (NTEE code J, subsection 05) -- important for excluding unions from the "organizing target" universe.

**Why master schema second (Task 2):** The master employer table is the foundation for non-union target discovery -- the #1 product goal. Currently we only see employers with existing union contracts (F-7). The master table expands to SAM (826K government contractors), Mergent (56K private companies), BMF (1.8M nonprofits), and OSHA (1M+ establishments). The schema must be designed before any seeding pipelines (steps 4-6) can be built.

**How they connect:** Task 1 loads BMF data that Task 2's schema must accommodate. The master employer schema (Task 2) includes a Wave 0 seed from F-7 and must be forward-compatible with BMF seeding (which would use EIN as the primary match key). Task 2's design doc should reference the BMF column structure from Task 1.

### Key Technical Conventions

- **DB access:** Always `from db_config import get_connection` (project root). Returns bare psycopg2 connection.
- **Name normalization:** `scripts/import/name_normalizer.py` -> `normalize_employer_aggressive()`. Must use `importlib` to import (directory named 'import' is a Python reserved word). On Python 3.14, register module in `sys.modules` BEFORE `exec_module` to avoid `@dataclass` crash.
- **Bulk inserts:** Use `COPY` with `StringIO` for speed (pattern used in ETL scripts throughout project).
- **Encoding:** ASCII only in print statements. Windows cp1252 crashes on Unicode arrows/emoji.
- **Python 3.14:** Watch for `\s` escape warnings in regex strings. Use raw strings (`r'\s'`).
- **f7_employer_id is TEXT** (hash string). All match tables must use TEXT for this column.
- **EIN is NOT unique** per employer -- subsidiaries share parent EINs, some are reused across entities.
- **NAICS** is the industry code system used throughout. `naics_sectors` table has `sector_name` column (not `naics_sector_name`).

---

## Task 1: Full IRS BMF Load (1.8M records)

### Context

The `irs_bmf` table exists but has only ~25 test rows loaded via ProPublica API. The ProPublica API is paginated (250/page with 0.5s delay) -- far too slow for 1.8M records. We need to load the full IRS Business Master File from the bulk download.

The IRS publishes the full BMF as fixed-width text files at: https://www.irs.gov/charities-non-profits/exempt-organizations-business-master-file-extract-eo-bmf

There are separate files per region/state. The format is documented in the IRS Publication 78 / EO BMF layout.

### Current State

- **Table:** `irs_bmf` in PostgreSQL database `olms_multiyear` (localhost, user `postgres`)
- **Existing schema:** `scripts/etl/create_irs_bmf_table.sql`
- **Existing loader:** `scripts/etl/irs_bmf_loader.py` (ProPublica API -- too slow for full load)
- **Existing adapter:** `scripts/matching/adapters/bmf_adapter_module.py` (works, don't break it)
- **Current rows:** ~25 (test data)
- **Target rows:** ~1.8M (all US tax-exempt organizations)
- **DB config:** `from db_config import get_connection` (file at project root, returns bare psycopg2 connection)

### What to Build

Create `scripts/etl/load_bmf_bulk.py` that:

1. **Downloads** all IRS EO BMF extract files (CSV format preferred if available, otherwise fixed-width). The IRS provides these at the URL above -- there are ~30+ regional files. Check what format they're currently published in (the IRS recently switched some to CSV).

2. **Parses** each file and extracts at minimum these fields (map to existing `irs_bmf` columns):
   - `ein` (TEXT, PRIMARY KEY) -- Employer Identification Number
   - `org_name` (TEXT NOT NULL) -- Organization name
   - `state` (TEXT) -- 2-letter state code
   - `city` (TEXT) -- City name
   - `zip_code` (TEXT) -- ZIP code (5-digit)
   - `ntee_code` (TEXT) -- National Taxonomy of Exempt Entities code
   - `subsection_code` (TEXT) -- IRS subsection (e.g., '03' = 501(c)(3), '05' = 501(c)(5))
   - `ruling_date` (DATE) -- Tax-exempt ruling date
   - `deductibility_code` (TEXT)
   - `foundation_code` (TEXT)
   - `income_amount` (NUMERIC)
   - `asset_amount` (NUMERIC)

3. **Bulk loads** using `COPY` with `StringIO` (fast pattern used elsewhere in this project). Batch size ~50K rows. Use `ON CONFLICT (ein) DO UPDATE` to handle duplicates across regional files (keep latest/richest record).

4. **Filters out** records with NULL/empty `ein` or `org_name`.

5. **Adds these new columns** to `irs_bmf` if they don't exist (ALTER TABLE, idempotent):
   - `name_normalized` (TEXT) -- lowercase, stripped of punctuation, for matching
   - `is_labor_org` (BOOLEAN DEFAULT FALSE) -- TRUE if `ntee_code LIKE 'J%'` OR `subsection_code = '05'`
   - `group_exemption_number` (TEXT) -- GEN from BMF, links subordinate orgs to parent

6. **Populates** `name_normalized` using the same normalization as the rest of the project. Import the normalizer:
   ```python
   import importlib, importlib.util, sys
   spec = importlib.util.spec_from_file_location("name_normalizer", "scripts/import/name_normalizer.py")
   mod = importlib.util.module_from_spec(spec)
   sys.modules["name_normalizer"] = mod  # MUST register before exec_module (Python 3.14 fix)
   spec.loader.exec_module(mod)
   normalize = mod.normalize_employer_aggressive
   ```

7. **CLI flags:**
   - `--download-dir DIR` (default: `data/bmf_bulk/`) -- where to save downloaded files
   - `--skip-download` -- use already-downloaded files
   - `--limit N` -- only load first N records (for testing)
   - `--dry-run` -- parse and count but don't insert

8. **Prints summary** at end:
   - Total records loaded
   - Records skipped (missing EIN/name)
   - Breakdown by subsection_code (top 10)
   - Count of labor orgs (`is_labor_org = TRUE`)
   - Count by state (top 10)

### Constraints

- Use `from db_config import get_connection` for database access.
- Do NOT use Unicode characters in print statements (Windows cp1252 encoding). Use ASCII only.
- Do NOT use inline `py -c` commands. Write everything to .py files.
- Transaction safety: wrap in try/except, rollback on error.
- The `irs_bmf` table already exists -- don't DROP it, just TRUNCATE + reload (or use ON CONFLICT).
- The `bmf_adapter_module.py` reads from `irs_bmf` with columns `ein`, `org_name`, `state`, `city`, `zip_code` -- do NOT rename these columns.

### Verification

After loading, these queries should work:
```sql
SELECT COUNT(*) FROM irs_bmf;  -- Should be ~1.8M
SELECT COUNT(*) FROM irs_bmf WHERE is_labor_org;  -- Should be ~60-80K
SELECT subsection_code, COUNT(*) FROM irs_bmf GROUP BY 1 ORDER BY 2 DESC LIMIT 10;
SELECT state, COUNT(*) FROM irs_bmf GROUP BY 1 ORDER BY 2 DESC LIMIT 10;
```

### Do NOT

- Modify `bmf_adapter_module.py` (the matching adapter works as-is)
- Modify `run_deterministic.py`
- Run the matching pipeline
- Modify any test files

---

## Task 2: Master Employer Table Schema Design

### Context

The platform currently has 146,863 employers in `f7_employers_deduped`, all sourced from F-7 union-employer filings. This means we only see employers that already have union contracts. The #1 product goal is **non-union target discovery** -- surfacing employers that have OSHA violations, NLRB activity, government contracts, or wage theft violations but NO union contract. These employers are invisible today.

The master employer table will be the single canonical employer universe. It starts with the F-7 base and grows as we seed from SAM (826K government contractors), Mergent (56K private companies), BMF (1.8M nonprofits), OSHA (1M+ establishments), and NLRB participants.

### Current Tables to Unify

| Table | Rows | Key Fields | Identity Keys |
|-------|------|-----------|--------------|
| `f7_employers_deduped` | 146,863 | employer_id (TEXT hash), employer_name, city, state, naics, latest_unit_size | employer_id |
| `sam_entities` | 826K+ | entity name, EIN, DUNS/UEI, NAICS, employees, address, city, state | UEI, DUNS, EIN |
| `mergent_employers` | 56K | company_name, duns, revenue, employees, state, city | DUNS |
| `irs_bmf` | 1.8M (after Task 1) | ein, org_name, state, city, ntee_code, subsection_code | EIN |
| `osha_establishments` | 1M+ | establishment name, address, city, state, ZIP, employees, NAICS | establishment_id (INT) |
| `sec_companies` | 517K | company name, CIK, state, SIC | CIK |
| `nlrb_participants` | 1.9M | participant_name, city, state, participant_type | case_number + name |

### Existing Linkage

| Table | Covers | Links |
|-------|--------|-------|
| `unified_match_log` | 1,738,115 rows | source_system + source_id -> f7_employer_id |
| `corporate_identifier_crosswalk` | 3,313 employers | f7_employer_id -> sec_cik, gleif_lei, mergent_duns, ein |
| `employer_canonical_groups` | 16,209 groups (40,304 employers) | group_id -> canonical_employer_id |
| `osha_f7_matches` | 97,142 | establishment_id -> f7_employer_id |
| `sam_f7_matches` | 28,816 | sam record -> f7_employer_id |

### What to Build

Create `scripts/etl/create_master_employers.sql` with the DDL for the master employer table and supporting tables. Also create `docs/MASTER_EMPLOYER_SCHEMA.md` documenting the design decisions.

#### Schema Requirements

**Table: `master_employers`**
- One row per real-world employer entity
- `master_id` -- synthetic primary key (SERIAL or UUID, your recommendation with rationale)
- `canonical_name` -- best available name (normalized)
- `display_name` -- original-case name for UI display
- `city`, `state`, `zip` -- best available location
- `naics` -- best available industry code
- `employee_count` -- best estimate (with source attribution)
- `employee_count_source` -- which source provided the count
- `ein` -- EIN if known (nullable, not unique -- subsidiaries share EINs)
- `is_union` -- BOOLEAN, TRUE if has F-7 relationship
- `is_public` -- BOOLEAN, from SEC/crosswalk
- `is_federal_contractor` -- BOOLEAN, from SAM
- `is_nonprofit` -- BOOLEAN, from BMF/990
- `source_origin` -- which source first created this record ('f7', 'sam', 'mergent', 'osha', 'bmf', 'nlrb')
- `created_at`, `updated_at` -- timestamps
- `data_quality_score` -- 0-100, based on how many sources confirm identity

**Table: `master_employer_source_ids`**
- Maps master_id to all source-specific IDs
- `master_id` (FK) + `source_system` (TEXT) + `source_id` (TEXT) -- composite PK
- `match_confidence` -- from unified_match_log or manual
- `matched_at` -- timestamp

**Table: `master_employer_merge_log`**
- Audit trail for when two master records are merged
- `merge_id` (SERIAL PK)
- `winner_master_id`, `loser_master_id`
- `merge_reason` (TEXT) -- 'ein_match', 'name_dedup', 'manual', etc.
- `merged_by` (TEXT) -- 'system' or user
- `merged_at` (TIMESTAMP)

#### Design Decisions to Document

In `docs/MASTER_EMPLOYER_SCHEMA.md`, explain:

1. **PK strategy:** Why SERIAL vs UUID vs hash. Consider: the F-7 uses TEXT hash IDs (`employer_id`), other sources use integers. What's the best approach for a unifying key?

2. **EIN handling:** EIN is NOT unique per employer (subsidiaries share parent EIN, some EINs are reused). How to handle: nullable, non-unique, with crosswalk?

3. **Name resolution:** When SAM says "ACME CORP" and OSHA says "Acme Corporation" and F-7 says "ACME CORPORATION INC" -- which name wins? Propose a priority order.

4. **Employee count reconciliation:** SAM says 500, Mergent says 450, OSHA says 200 (one location). How to reconcile? Propose rules.

5. **Seeding order:** Which source seeds first? Recommended: F-7 (146K, already deduped) -> SAM (826K, has EIN+DUNS) -> Mergent (56K, has DUNS) -> BMF (1.8M, has EIN) -> OSHA (1M, no strong ID). Explain why.

6. **Dedup strategy per wave:** How each source gets matched to existing master records before creating new ones.

7. **Visibility rules:** Minimum data threshold to surface an employer as a "target" in the UI. Proposal from redesign spec: minimum 2 scoring factors with data.

#### Migration Path

Include in the SQL file:
- `CREATE TABLE IF NOT EXISTS` (idempotent)
- Indexes on: `ein`, `state`, `naics`, `canonical_name` (trigram GIN), `source_origin`
- Comments on columns explaining their purpose
- A seed query that populates `master_employers` from `f7_employers_deduped` as Wave 0 (the initial load)

### Constraints

- SQL must be valid PostgreSQL.
- Do NOT create any Python scripts that modify the database. Schema only + documentation.
- Do NOT modify any existing tables (f7_employers_deduped, sam_entities, etc.).
- The schema must be forward-compatible with the seeding pipelines (Tasks 6-7 in the dependency map).
- Reference existing patterns: `scripts/etl/create_irs_bmf_table.sql` for table creation style.

### Do NOT

- Run any SQL against the database
- Modify existing tables or views
- Create Python scripts that write to the DB
- Modify the matching pipeline
- Modify test files

---

## How the Matching Pipeline Works (context for Task 2)

The existing matching pipeline connects source records (OSHA, SAM, 990, etc.) to F-7 employers. Understanding this is critical for designing the master table.

**Flow:** Source adapter loads unmatched records -> deterministic matcher runs 6-tier cascade -> results written to `unified_match_log` -> legacy match tables rebuilt from UML.

**Tier cascade (strict to broad):**
1. EIN exact match (confidence 100)
2. Name + City + State (90)
3. Name + State (80)
4. Aggressive name normalization (60)
5a. Splink probabilistic (45) -- with name similarity floor >= 0.70
5b. Trigram fallback (40)

**Best-match-wins:** Each source record keeps only its highest-confidence match. Re-runs supersede old matches.

**Key tables:**
- `unified_match_log` -- 1.7M rows. Columns: `source_system`, `source_id`, `f7_employer_id`, `match_tier`, `confidence_score`, `status` ('active'/'superseded'/'rejected')
- Legacy match tables (rebuilt from UML): `osha_f7_matches`, `sam_f7_matches`, `national_990_f7_matches`, `whd_f7_matches`, `nlrb_employer_xref`

**The gap Task 2 fills:** Currently matching only goes source -> F-7 employer. If an OSHA establishment has violations but no F-7 match, it's invisible. The master table adds these unmatched records as new employers, expanding beyond the F-7 universe.

**Match rates by source (active matches / total source records):**
- OSHA: 97,142 / 1,007,217 (9.6%)
- SAM: 28,816 / 826,042 (3.5%)
- 990: 20,215 / 586,767 (3.4%)
- WHD: 19,462 / 363,365 (5.4%)
- SEC: 5,339 / 517,403 (1.0%)
- BMF: 9 / 25 (will change dramatically after Task 1)

The vast majority of source records are **unmatched** -- these are the non-union employers that the master table will capture.

---

## Reference Files

For both tasks, these files contain patterns and conventions to follow:

| File | Why Read It |
|------|------------|
| `Start each AI/PROJECT_STATE.md` | Current status, latest numbers, known issues |
| `Start each AI/UNIFIED_ROADMAP_2026_02_19.md` | Phase G master employer plan (tasks G1-G7) |
| `Start each AI/UNIFIED_PLATFORM_REDESIGN_SPEC.md` | Target architecture, scoring factors, visibility rules |
| `Start each AI/CLAUDE.md` | Technical reference, DB schema, API, conventions |
| `scripts/etl/create_irs_bmf_table.sql` | Existing BMF schema (Task 1 must preserve) |
| `scripts/etl/irs_bmf_loader.py` | Existing BMF loader (reference for field mapping) |
| `scripts/matching/adapters/bmf_adapter_module.py` | BMF adapter (Task 1 must not break) |
| `scripts/matching/run_deterministic.py` | Matching pipeline entry point (context for Task 2) |
| `scripts/matching/deterministic_matcher.py` | 6-tier cascade logic (context for Task 2) |
| `scripts/scoring/build_employer_data_sources.py` | MV that reads from match tables (context for Task 2) |
| `scripts/scoring/build_unified_scorecard.py` | 7-factor scoring (context for Task 2 visibility rules) |
| `docs/IRS_BMF_RESEARCH.md` | BMF data source research |
| `docs/NY_EXPORT_METHODOLOGY.md` | Dedup methodology proof-of-concept (context for Task 2) |
| `db_config.py` | Database connection helper (project root, 500+ imports -- never move) |
