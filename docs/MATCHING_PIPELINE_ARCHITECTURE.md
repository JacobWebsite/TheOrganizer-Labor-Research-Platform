# Matching Pipeline Architecture

The matching pipeline links external data sources (OSHA, WHD, NLRB, SEC, SAM, 990, BMF, Mergent, CorpWatch) to F7 union employers and to non-union master employers. It uses a 6-tier deterministic cascade with in-memory indexes, RapidFuzz fuzzy matching, and pg_trgm trigram fallback. All matches are logged in `unified_match_log` for audit and supersede tracking.

---

## Core Components

```
Source Adapters (load records)
  → Deterministic Matcher (6-tier cascade)
    → Unified Match Log (audit trail)
    → Legacy Match Tables (source-specific)
    → Master Employer Seeding (non-union pool)
      → Master Dedup (EIN → name+state → fuzzy)
```

---

## Deterministic Matcher v4

**File:** `scripts/matching/deterministic_matcher.py`

### 6-Tier Cascade

Records flow through tiers from most-specific to least-specific. First match wins.

```
Source Record
  ↓
[Tier 1: EIN_EXACT] ──→ MATCH (rank=100, confidence=1.0, band=HIGH)
  ↓ no match
[Tier 2: NAME_CITY_STATE] ──→ MATCH (rank=90, confidence=0.95, band=HIGH)
  ↓ no match                   ↓ multiple candidates → DISAMBIGUATE
[Tier 3: NAME_STATE] ──→ MATCH (rank=80, confidence=0.90, band=HIGH)
  ↓ no match               ↓ multiple candidates → DISAMBIGUATE
[Tier 4: NAME_AGGRESSIVE_STATE] ──→ MATCH (rank=60, confidence=0.75, band=MEDIUM)
  ↓ no match                        ↓ multiple candidates → DISAMBIGUATE
[Tier 5a: RapidFuzz] ──→ MATCH (rank=45, confidence=similarity, band=varies)
  ↓ no match
[Tier 5b: Trigram] ──→ MATCH (rank=40, confidence=similarity, band=LOW/MEDIUM)
  ↓ no match
UNMATCHED
```

### Tier Details

#### Tier 1: EIN_EXACT (rank=100, confidence=1.0)

Exact EIN match via `corporate_identifier_crosswalk`.

```python
target_id = self._ein_idx[ein]  # O(1) dict lookup
```

Single-value lookup. Highest confidence. ~20K EINs indexed.

#### Tier 2: NAME_CITY_STATE_EXACT (rank=90, confidence=0.95)

Standard-normalized name + city + state exact match.

```python
candidates = self._name_city_state_idx[(name_std, city, state)]
```

If single candidate → match. If multiple → disambiguate.

#### Tier 3: NAME_STATE_EXACT (rank=80, confidence=0.90)

Standard-normalized name + state exact match (no city requirement).

```python
candidates = self._name_state_idx[(name_std, state)]
```

Broader than Tier 2 — may hit multiple candidates in same state. Disambiguation handles collisions.

#### Tier 4: NAME_AGGRESSIVE_STATE (rank=60, confidence=0.75)

Aggressive-normalized name (legal suffixes and noise tokens removed) + state exact match.

```python
candidates = self._agg_state_idx[(name_agg, state)]
```

"ACME Corp., Inc." becomes "acme" — matches "Acme Corporation" or "Acme Holdings LLC". Higher collision rate.

#### Tier 5a: FUZZY_SPLINK_ADAPTIVE / RapidFuzz (rank=45)

RapidFuzz `token_sort_ratio` with 3 blocking indexes to avoid O(n^2) comparison.

**Blocking indexes (reduce candidate pool):**
1. `state + name[:3]` — first 3 chars of normalized name within state
2. `state + city` — geographic co-location
3. `zip[:3] + name[:2]` — partial zip + 2-char name prefix

**Matching:**
```python
score = rapidfuzz.fuzz.token_sort_ratio(source_name, target_name) / 100.0
if score >= 0.80:  # MATCH_MIN_NAME_SIM env var, default 0.80
    accept match
```

**Tie-breaking (equal similarity):** city exact > zip exact > NAICS exact.

**Performance:** ~2 min for 225K records.

**Match method in log:** `'FUZZY_SPLINK_ADAPTIVE'` (backward compat), but `evidence.match_method_detail = 'rapidfuzz_token_sort_ratio'`.

#### Tier 5b: FUZZY_TRIGRAM (rank=40)

PostgreSQL `pg_trgm` similarity operator. SQL-based batch matching.

```sql
SELECT DISTINCT ON (b.source_id)
    b.source_id, f.employer_id, similarity(b.name_std, f.name_standard) AS sim
FROM _fuzzy_batch b
JOIN f7_employers_deduped f
    ON f.name_standard % b.name_std
WHERE similarity(b.name_std, f.name_standard) >= 0.4
ORDER BY b.source_id, sim DESC
```

Processes in batches of 200 records. Slowest tier (~30-60 min per batch).

**Quality floor:** 0.75 similarity minimum applied post-hoc. Matches below 0.75 auto-rejected. Script: `scripts/maintenance/reject_low_trigram.py`.

### Collision Disambiguation

When Tiers 2-4 return multiple candidates:

**Step 1: City Resolution**
- If source city matches exactly 1 candidate → accept with `_CITY_RESOLVED` suffix
- Most common resolution path

**Step 2: Splink Multi-Field Disambiguation**
- Pre-trained Splink adaptive model scores all candidates
- Requires clear winner: `top_prob - second_prob >= 0.10`
- Name similarity floor enforced: `token_sort_ratio >= min_name_similarity`
- If clear winner → accept with `_SPLINK_RESOLVED` suffix

**Step 3: Ambiguous**
- If still unresolved → flag as `AMBIGUOUS_{method}` with LOW confidence (0.0)
- All candidate IDs logged in evidence

### Confidence Bands

```
score >= 0.85 → HIGH
0.70 <= score < 0.85 → MEDIUM
score < 0.70 → LOW
```

LOW confidence matches are written to `unified_match_log` with `status = 'rejected'`.

### In-Memory Indexes

Built once from `f7_employers_deduped` on first match call:

| Index | Key | Values | ~Size |
|-------|-----|--------|-------|
| `_ein_idx` | ein | employer_id | ~20K |
| `_name_state_idx` | (name_std, state) | [(eid, name, city), ...] | ~170K keys |
| `_name_city_state_idx` | (name_std, city, state) | [(eid, name), ...] | ~100K keys |
| `_agg_state_idx` | (name_agg, state) | [(eid, name, city), ...] | ~130K keys |

---

## Name Normalization

**File:** `src/python/matching/name_normalization.py`

### 3 Levels

#### Level 1: Standard (`normalize_name_standard`)

Conservative, safe for exact matching.

1. ASCII fold (u with umlaut → u)
2. Lowercase
3. Remove punctuation (`&/+` → space, non-alphanumeric → space)
4. Collapse whitespace
5. Remove DBA/AKA tails

```
"Smith & Co., Inc." → "smith co inc"
```

#### Level 2: Aggressive (`normalize_name_aggressive`)

Strips legal identity — used for Tier 4.

1. Apply standard normalization
2. Expand abbreviations (hosp→hospital, mfg→manufacturing, ctr→center, ~20 mappings)
3. Remove legal suffixes (~25: inc, llc, corp, ltd, lp, llp, pllc, pc, plc, pa, na, trust, fund, foundation, cooperative, etc.)
4. Remove noise tokens (the, of, and, services, group, holdings, management, international, enterprises, industries, etc.)

```
"ACME Corp., Inc." → "acme"
"University Hospital Holdings LLC" → "university hospital"
```

#### Level 3: Fuzzy (`normalize_name_fuzzy`)

Token-sorted for approximate matching.

1. Apply aggressive normalization
2. Split into tokens
3. Remove single-char tokens
4. Deduplicate and sort alphabetically

```
"John Smith Hospital" → "hospital john smith"
```

### Phonetic Helpers

- **Soundex:** 4-character American Soundex code. First letter + 3 digits.
- **Metaphone:** More accurate phonetic encoding. Handles silent letters (GN, KN, WR), digraphs (TH→0, SH→X).
- **Phonetic Similarity:** Compares soundex + metaphone of first words. Returns 0.0-1.0 (both match=1.0, one=0.5, none=0.0).

---

## Run Orchestrator

**File:** `scripts/matching/run_deterministic.py`

### CLI

```bash
py scripts/matching/run_deterministic.py <source> [OPTIONS]

Sources: osha, whd, 990, sam, sec, bmf, corpwatch, all

Options:
  --limit N             Limit records
  --dry-run             No writes
  --unmatched-only      Only unmatched records (default)
  --rematch-all         Re-match all (supersedes old)
  --skip-fuzzy          Exact tiers only (fast)
  --skip-legacy         Skip legacy match table writes
  --batch N/M           Run batch N of M (parallelization)
  --batch-status        Show batch progress
```

### Rematch vs Unmatched

- **`--unmatched-only`** (default): Loads only source records not yet in `unified_match_log` with `status='active'`. Fast for incremental runs.
- **`--rematch-all`**: Loads ALL source records. Before processing, supersedes existing active matches for those records. Full re-evaluation.

### Batch Checkpointing

Supports resumable batched re-runs for large sources:

```bash
py scripts/matching/run_deterministic.py osha --rematch-all --batch 1/4
py scripts/matching/run_deterministic.py osha --rematch-all --batch 2/4
py scripts/matching/run_deterministic.py osha --batch-status
```

Checkpoint file: `checkpoints/{source}_rerun.json` — records batch number, run_id, match counts, and band distribution per batch.

### Supersede Logic

Batch-aware: only supersedes old matches for records in the current batch, leaving other batches untouched.

```sql
UPDATE unified_match_log
SET status = 'superseded'
WHERE source_system = %s AND status = 'active' AND source_id = ANY(%s)
```

### Match Run Registration

Each run creates a `match_runs` row before processing:

```sql
INSERT INTO match_runs (run_id, scenario, started_at, source_system, method_type)
VALUES (%s, 'deterministic_{source}', NOW(), %s, 'deterministic_v2')
```

Updated on completion with total_source, total_matched, match_rate, band counts.

---

## Source Adapters

**Directory:** `scripts/matching/adapters/`

Each adapter provides:
- `load_unmatched(conn, limit=None)` — records not yet matched
- `load_all(conn, limit=None)` — all records (for --rematch-all)
- `write_legacy(conn, matches)` — writes to source-specific match table
- `SOURCE_SYSTEM` constant

### Common Output Schema

```python
{
    "id": str,       # source record ID
    "name": str,     # establishment/employer name
    "state": str,    # 2-letter state
    "city": str,     # may be None
    "zip": str,      # may be None
    "naics": str,    # may be None
    "ein": str,      # None for sources without EIN
    "address": str,  # may be None
}
```

### Adapter Inventory

| Adapter | Source Table | ID Field | Name Field | Has EIN | Legacy Table |
|---------|-------------|----------|------------|---------|-------------|
| osha | osha_establishments | establishment_id | estab_name | No | osha_f7_matches |
| whd | whd_cases | case_id | trade_name | No | whd_f7_matches |
| 990 | national_990_filers | id | business_name | Yes | national_990_f7_matches |
| sam | sam_entities | uei | legal_business_name | No | sam_f7_matches |
| sec | sec_companies | cik (TEXT) | company_name | Yes | corporate_identifier_crosswalk |
| bmf | irs_bmf | ein | org_name | Yes (is ID) | corporate_identifier_crosswalk |
| corpwatch | corpwatch_companies | cw_id (TEXT) | company_name | Yes | corpwatch_f7_matches |

**Special adapter behaviors:**
- **SEC/BMF:** Write to `corporate_identifier_crosswalk` instead of a dedicated match table. UPDATE existing rows or INSERT new ones.
- **990:** Has unique constraint on `(f7_employer_id, ein)` — uses `ON CONFLICT DO NOTHING`.
- **CorpWatch:** Filters `is_us = TRUE` (US companies only).

---

## Unified Match Log

**File:** `scripts/matching/create_unified_match_log.py`

Central audit trail for all matches across all sources and runs.

### Schema

```sql
CREATE TABLE unified_match_log (
    id              SERIAL PRIMARY KEY,
    run_id          VARCHAR(36) NOT NULL,
    source_system   VARCHAR(50) NOT NULL,       -- 'osha', 'whd', '990', 'sec', etc.
    source_id       TEXT NOT NULL,
    target_system   VARCHAR(50) NOT NULL DEFAULT 'f7',
    target_id       TEXT NOT NULL,               -- f7_employers_deduped.employer_id
    match_method    VARCHAR(100) NOT NULL,       -- e.g. 'NAME_STATE_EXACT_CITY_RESOLVED'
    match_tier      VARCHAR(20) NOT NULL,        -- 'deterministic' or 'probabilistic'
    confidence_band VARCHAR(10) NOT NULL,        -- 'HIGH', 'MEDIUM', 'LOW'
    confidence_score NUMERIC(5,3),               -- 0.000-1.000
    evidence        JSONB NOT NULL DEFAULT '{}',
    status          VARCHAR(20) DEFAULT 'active', -- 'active', 'superseded', 'rejected'
    created_at      TIMESTAMP DEFAULT NOW(),

    UNIQUE(run_id, source_system, source_id, target_id)
);
```

### Status Values

| Status | Meaning |
|--------|---------|
| active | Current best match |
| superseded | Replaced by a better match in a later run |
| rejected | LOW confidence, logged but not used |

### Evidence JSONB Examples

**Tier 3 with city resolution:**
```json
{
    "source_name": "ACME CORP",
    "target_name": "Acme Corporation",
    "state": "CA",
    "city": "San Francisco",
    "candidates": 3,
    "resolved_by": "city"
}
```

**RapidFuzz match:**
```json
{
    "source_name": "SMITH AND ASSOCIATES",
    "target_name": "Smith Associates LLC",
    "state": "NY",
    "name_similarity": 0.918,
    "match_method_detail": "rapidfuzz_token_sort_ratio"
}
```

### Indexes

```sql
idx_uml_source_system    (source_system)
idx_uml_target_id        (target_id)
idx_uml_confidence_band  (confidence_band)
idx_uml_status           (status) WHERE status='active'
idx_uml_run_id           (run_id)
idx_uml_source_id        (source_system, source_id)
```

**Total rows:** ~1.8M across all sources and runs.

---

## Legacy Match Tables

Source-specific tables used by the scoring system. Written by adapters alongside unified_match_log.

| Table | PK | F7 Column | Extra Columns |
|-------|-----|-----------|---------------|
| osha_f7_matches | establishment_id | f7_employer_id | match_method, match_confidence, matched_at |
| whd_f7_matches | case_id | f7_employer_id | match_method, match_confidence, match_source |
| national_990_f7_matches | n990_id | f7_employer_id | ein, match_method, match_confidence, match_source |
| sam_f7_matches | uei | f7_employer_id | match_method, match_confidence, match_source |
| corpwatch_f7_matches | cw_id | f7_employer_id | match_method, match_confidence |

**SEC, BMF, GLEIF, Mergent** use `corporate_identifier_crosswalk` instead of dedicated match tables.

All legacy tables use `ON CONFLICT DO UPDATE` — re-running upgrades matches if a better tier is found.

---

## NLRB ULP Matching

**File:** `scripts/matching/match_nlrb_ulp.py`

Matches NLRB Unfair Labor Practice charges (CA cases) to F7 employers. Special challenges: 44% of names contain newlines (attorney + employer), city/state fields are garbage for 99.8% of records.

### Name Extraction

Multi-line records split at `\n`:
- Line 1: typically attorney/representative name
- Line 2: typically employer name
- If line 2 is a law firm → skip
- If line 2 is a person name (LAST, FIRST pattern) → skip

**Law firm detection:** Regex for "LLC", "P.C.", "law office", "attorney", "counsel", "Esq." + known firm names (Fisher & Phillips, Jackson Lewis, Littler Mendelson, etc.).

### NLRB Region → State Mapping

NLRB regions map to states for geographic filtering (e.g., Region 1 = CT/MA/ME/NH/RI/VT, Region 2 = NY, Region 13 = IL, Region 20 = CA).

### 3-Tier Name Matching

| Tier | Normalization | Confidence (state match / exact / ambiguous) |
|------|--------------|---------------------------------------------|
| 1 | Simple (lowercase, remove suffixes) | 0.90 / 0.80 / 0.70 |
| 2 | Standard (full normalization) | 0.85 / 0.75 / 0.65 |
| 3 | Aggressive (noise + suffixes removed) | 0.75 / 0.65 / — |

### Output

Updates `nlrb_participants.matched_employer_id` directly. Optionally writes to `unified_match_log`.

**Stats:** 234,656 CA records matched to 22,371 distinct F7 employers. Top: USPS (94K), UPS (2K), AT&T (2K), Kaiser (1.6K), GM (443).

---

## Master Employers & Seed Pipeline

### Schema

**`master_employers`** — Non-union employer pool (4.3M rows after dedup):

```sql
master_id           INT PRIMARY KEY,
canonical_name      TEXT,
display_name        TEXT,
city                TEXT,
state               TEXT,
zip                 TEXT,
naics               TEXT,
employee_count      INT,
employee_count_source TEXT,
ein                 TEXT,
is_union            BOOLEAN,
is_public           BOOLEAN,
is_federal_contractor BOOLEAN,
is_nonprofit        BOOLEAN,
source_origin       TEXT,     -- 'osha', 'whd', 'nlrb', 'bmf', 'sam', etc.
is_labor_org        BOOLEAN,
data_quality_score  INT,
created_at          TIMESTAMP,
updated_at          TIMESTAMP
```

**`master_employer_source_ids`** — Bridge table linking masters to source records (~11M rows):

```sql
master_id       INT REFERENCES master_employers,
source_system   TEXT,     -- 'osha', 'whd', 'nlrb', 'f7', 'sam', 'bmf', etc.
source_id       TEXT,     -- ID in the source table
match_confidence NUMERIC,
matched_at      TIMESTAMP,
PRIMARY KEY (master_id, source_system, source_id)
```

**Check constraints:** `chk_master_source_system` and `chk_master_source_origin` have hardcoded allowed value lists. Adding a new source requires `ALTER TABLE DROP CONSTRAINT` + recreate.

### Seed Scripts (3-Step Pattern)

Each seed script (`seed_master_osha.py`, `seed_master_whd.py`, `seed_master_nlrb.py`) follows the same pattern:

**Step 1: F7 Bridge**
- Link source records already matched to F7 employers
- INSERT into `master_employer_source_ids` using the F7 match
- `ON CONFLICT DO NOTHING` (idempotent)

**Step 2: Name+State Match**
- Match remaining unmatched source records to existing masters by `canonical_name + state`
- INSERT into `master_employer_source_ids`
- Confidence: 0.85

**Step 3: Insert New Masters**
- Create new `master_employers` rows for truly unmatched source records
- Also insert corresponding `master_employer_source_ids` entries

**Source-specific notes:**
- **OSHA:** Filters `union_status != 'Y'` (non-union only). Source origin: 'osha'.
- **NLRB:** Uses temp table `_tmp_nlrb_candidates` (staged approach — massive CTE hangs). Participants with `type IN ('Employer', 'Charged Party / Respondent')`. Name length filter > 3 chars. Source origin: 'nlrb'.
- **WHD:** Similar 3-step pattern. Source origin: 'whd'.

All seed scripts are **idempotent** — `ON CONFLICT DO NOTHING` means re-running returns all zeros. Check source_id counts before assuming scripts haven't run.

---

## Master Employer Deduplication

**File:** `scripts/etl/dedup_master_employers.py`

### 4-Phase Strategy

#### Phase 1: EIN Exact Match

Group masters by EIN. Merge to single winner (F7-sourced preferred).

**Stats:** ~9K merges.

#### Phase 2: Name+State Exact Match

Exact match of `(canonical_name, state)`. Fuzzy validation: `token_sort_ratio >= 0.85`.

**Stats:** ~233K merges.

#### Phase 3: Fuzzy Name Match

Name similarity >= threshold with confirming signal:
- City exact match, OR
- ZIP prefix (first 3 digits) match, OR
- NAICS prefix (first 2 digits) match

Triple-confirm requirement prevents false positives. Quality score 0-100.

**Stats:** ~69K merges (4.2% of 1.6M candidates passed triple-confirm). Quality distribution: 0-20=34%, 21-40=65%, 41+=1.7%.

#### Phase 4: Reserved

For future edge cases.

### Merge Operation

For each (winner, loser) pair:

1. **Move source IDs:** INSERT loser's `master_employer_source_ids` to winner. `ON CONFLICT` updates confidence to `GREATEST`.
2. **Delete loser's source IDs.**
3. **Consolidate fields:** Winner takes priority; gaps filled from loser. Boolean flags OR'd together (is_union, is_public, is_federal_contractor, is_nonprofit).
4. **Log merge:** Insert into `master_employer_merge_log` (winner, loser, phase, confidence, evidence).
5. **Delete loser** from `master_employers`.

### Resumable

Checkpoint table `master_employer_dedup_progress` tracks phase, cursor positions, groups processed, merges executed. Resume with `--phase N --resume`.

### Overall Stats

4.65M → 4.34M (6.7% reduction). 311K masters eliminated.

---

## Duplicate Match Resolution

**File:** `scripts/maintenance/resolve_duplicate_matches.py`

Handles cases where a single source record has multiple active matches to different F7 employers.

### Best-Match-Wins Ranking

```python
METHOD_RANK = {
    "EIN_EXACT": 100,
    "NAME_CITY_STATE_EXACT": 90,
    "NAME_STATE_EXACT": 80,
    "NAME_AGGRESSIVE_STATE": 60,
    "FUZZY_SPLINK_ADAPTIVE": 45,
    "FUZZY_TRIGRAM": 40,
}
```

Sort by: `(method_rank DESC, confidence_score DESC, created_at DESC, id DESC)`. Top match wins; others superseded with `superseded_reason = 'duplicate_source_best_match_wins'`.

---

## Corporate Identifier Crosswalk

**File:** `scripts/etl/build_crosswalk.py`
**Table:** `corporate_identifier_crosswalk` (22,831 rows)
**Rebuild:** `PYTHONPATH=. py scripts/etl/build_crosswalk.py` (~8s)

Links SEC, GLEIF, Mergent, CorpWatch, and F7 employers via shared identifiers.

### 5-Tier Matching

| Tier | Method | Rows | Confidence |
|------|--------|------|------------|
| 1 | EIN_EXACT (SEC ↔ Mergent via EIN) | 1,057 | HIGH |
| 2 | LEI_EXACT (SEC ↔ GLEIF via LEI) | 83 | HIGH |
| 2b | EIN_F7_BACKFILL (F7 ↔ 990/CorpWatch EIN bridge) | 12,463 | HIGH |
| 3 | NAME_STATE (normalized name + state) | 1,155 | MEDIUM |
| 4 | USASPENDING_* (federal contract matching) | 8,002 | varies |

**F7 coverage:** 12,534 of 146,863 (8.5%). Was ~1,200 before EIN backfill (3.8x improvement).

### Key Columns

```sql
id, sec_id, sec_cik, gleif_id, gleif_lei, mergent_id, mergent_duns,
corpwatch_id, f7_employer_id, canonical_name, ein, ticker, state,
is_public, is_federal_contractor, federal_obligations, federal_contract_count,
match_tier, match_confidence, corporate_family_id
```

### USASpending Integration

**Script:** `scripts/etl/_match_usaspending.py` (run after crosswalk build)

Adds `is_federal_contractor`, `federal_obligations`, `federal_contract_count` columns from USASpending data.

### Cascade Warning

`DROP CASCADE` on crosswalk drops dependent MVs: `mv_organizing_scorecard`, `mv_employer_data_sources`, `mv_employer_features`. Must rebuild in order: `create_scorecard_mv.py` → `compute_gower_similarity.py` → `build_employer_data_sources.py` → `build_unified_scorecard.py`.

---

## Key Thresholds

| Parameter | Value | Where Used |
|-----------|-------|-----------|
| HIGH_THRESHOLD | 0.85 | Confidence band cutoff |
| MEDIUM_THRESHOLD | 0.70 | Confidence band cutoff |
| MATCH_MIN_NAME_SIM | 0.80 | RapidFuzz floor (env var) |
| FUZZY_TRIGRAM_SIM | 0.40 | pg_trgm similarity floor |
| TRIGRAM_QUALITY_FLOOR | 0.75 | Post-hoc rejection threshold |
| SPLINK_CLEAR_WINNER | 0.10 | Disambiguation gap required |
| DEDUP_FUZZY_THRESHOLD | 0.85 | Master dedup Phase 2 |
| Below-0.85 deactivated | 2026-02-26 | Fuzzy match FP rate too high |

---

## Fuzzy Match Quality

Audit-validated FP rates by confidence band:

| Band | FP Rate | Action |
|------|---------|--------|
| 0.80-0.85 | 40-50% | **Deactivated** (2026-02-26). 6,660 USASpending matches affected. |
| 0.85-0.90 | 50-70% | Active but high FP |
| 0.90-0.95 | 30-40% | Moderate FP |
| 0.95+ | <10% | Good quality |

No clean threshold exists. The `reject_low_trigram.py` maintenance script rejects trigram matches below 0.75.

---

## Tests

| File | Covers |
|------|--------|
| `tests/test_matching.py` | Exact match functions, name normalization, collision resolution |
| `tests/test_matching_pipeline.py` | Full pipeline integration, adapter loading, unified_match_log writing |
| `tests/test_data_integrity.py` | Match rate assertions, band distribution, cross-source consistency |

---

## Summary Statistics (as of 2026-02-27)

| Metric | Value |
|--------|-------|
| Unified match log total | ~1.8M rows |
| Master employers (post-dedup) | ~4.34M (from 4.65M, 6.7% reduction) |
| F7 employers | 146,863 |
| OSHA matched | ~1.2M establishments |
| WHD matched | ~180K cases |
| NLRB ULP matched | 234,656 (22,371 distinct F7) |
| 990 matched | ~10.6K |
| SAM matched | ~18.5K |
| Crosswalk F7 coverage | 12,534 (8.5%) |
| RapidFuzz speed | ~2 min / 225K records |
| Trigram speed | ~30-60 min / batch |
