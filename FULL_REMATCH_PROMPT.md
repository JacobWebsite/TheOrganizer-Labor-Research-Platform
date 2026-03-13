# Full Re-Match & Deduplication Prompt

## Objective

Perform a complete, from-scratch re-matching and deduplication of all employer records across all data sources. This replaces all existing matches in the F7 match tables, the unified_match_log, the master_employer_source_ids linkages, and the master_employer_merge_log. The goal is a single, clean pass using the best available matching infrastructure (6-tier deterministic cascade + RapidFuzz) applied uniformly to every source.

---

## Current Benchmarks (as of 2026-03-05)

### Source Table Sizes

| Table | Rows | Has EIN | Has State | Has City | Has Zip |
|-------|------|---------|-----------|----------|---------|
| `f7_employers_deduped` | 146,863 | No | Yes | Yes | Yes |
| `master_employers` | 4,546,912 | 44.9% | 97.6% | 97.6% | 97.6% |
| `osha_establishments` | 1,007,217 | No | Yes (site_state) | Yes (site_city) | Yes (site_zip) |
| `sam_entities` | 826,042 | No (UEI) | Yes (physical_state) | Yes (physical_city) | Yes (physical_zip) |
| `whd_cases` | 363,365 | No | Yes | Yes | Yes |
| `nlrb_participants` | 1,906,542 | No | Yes | Yes | Yes |
| `nlrb_elections` | 33,096 | No | No (in participants) | No | No |
| `nlrb_voluntary_recognition` | 1,681 | No | Yes (unit_state) | Yes (unit_city) | No |
| `ny_990_filers` | 47,614 | Yes | Yes | Yes | No |
| `sec_companies` | 517,403 | Yes | Yes | Yes | No |
| `corpwatch_companies` | 1,421,198 | Yes | Yes | Yes | No |
| `mergent_employers` | 70,426 | Yes | Yes | Yes | Yes |

### Current F7 Match Rates (target to beat)

| Match Table | Matched Rows | Distinct F7 Matched | F7 Rate |
|-------------|-------------|---------------------|---------|
| `osha_f7_matches` | 83,763 | 28,973 | 19.7% |
| `whd_f7_matches` | 17,145 | 10,744 | 7.3% |
| `sam_f7_matches` | 24,208 | 16,802 | 11.4% |
| `national_990_f7_matches` | 20,005 | 10,646 | 7.2% |
| `usaspending_f7_matches` | 9,305 | 9,305 | 6.3% |
| `corpwatch_f7_matches` | 3,057 | - | - |

### Current Master Employer Cross-Linkage

| Distinct Sources | Employer Count | % of Total |
|-----------------|---------------|------------|
| 1 source only | 4,260,380 | 93.7% |
| 2 sources | 225,556 | 5.0% |
| 3 sources | 33,185 | 0.7% |
| 4+ sources | 11,952 | 0.3% |

**Top single-source silos (employers linked to ONLY this source):**

| Source | Single-Source Count |
|--------|-------------------|
| bmf | 1,676,249 |
| sam | 778,569 |
| osha | 615,942 |
| corpwatch | 606,747 |
| whd | 269,576 |
| nlrb | 186,727 |
| f7 | 84,418 |
| mergent | 42,152 |

### Prior Dedup Results (699K merges total)

| Phase | Method | Merges | Runtime Date |
|-------|--------|--------|-------------|
| EIN exact | Same EIN -> merge | 9,808 | 2026-03-02 |
| Name+state exact | Identical canonical_name + state | 613,171 | 2026-03-02 |
| Name+state fuzzy | RapidFuzz token_sort_ratio >= 0.85 | 76,212 | 2026-03-02 |
| **Total** | | **699,191** | |

### Unified Match Log (2.2M entries, all status=ACTIVE count is 0)

| Source | Total Matches | Top Method | Top Method Count |
|--------|--------------|------------|-----------------|
| osha | 1,256,753 | FUZZY_TRIGRAM | 743,509 |
| sam | 300,349 | FUZZY_TRIGRAM | 211,333 |
| 990 | 246,040 | FUZZY_TRIGRAM | 124,427 |
| whd | 197,502 | FUZZY_TRIGRAM | 88,865 |
| sec | 159,743 | FUZZY_TRIGRAM | 118,136 |
| crosswalk | 19,293 | CROSSWALK | 10,688 |
| nlrb | 17,516 | NAME_ZIP_EXACT | 8,140 |
| corpwatch | 7,394 | FUZZY_TRIGRAM | 3,486 |
| gleif | 1,840 | NAME_STATE | 1,236 |
| mergent | 1,045 | SPLINK_PROB | 946 |
| bmf | 30 | EIN_EXACT | 14 |

### master_employers Field Coverage

| Field | Coverage |
|-------|---------|
| canonical_name | 100.0% |
| state | 97.6% |
| city | 97.6% |
| zip | 97.6% |
| ein | 44.9% |
| naics | 38.4% |
| employee_count | 20.1% |

---

## Existing Infrastructure

### Scripts Available
- `scripts/matching/deterministic_matcher.py` -- 6-tier cascade matcher (EIN, name+city+state, name+state, aggressive, RapidFuzz, trigram)
- `scripts/matching/run_deterministic.py` -- CLI runner with adapters for: osha, whd, 990, sam, sec, bmf, corpwatch
- `scripts/matching/adapters/` -- 7 source-specific adapters (osha, whd, n990, sam, sec, bmf, corpwatch)
- `scripts/matching/corroborate_matches.py` -- cross-source corroboration
- `scripts/matching/add_score_eligible.py` -- score eligibility flags
- `scripts/matching/build_employer_groups.py` -- canonical employer grouping
- `scripts/matching/match_nlrb_ulp.py` -- NLRB ULP-specific matcher
- `scripts/matching/create_unified_match_log.py` -- UML builder
- `scripts/etl/dedup_master_employers.py` -- 4-phase RapidFuzz dedup (EIN, exact, fuzzy, quality)
- `scripts/etl/seed_master_from_sources.py` -- seeds master_employers from SAM, Mergent, BMF
- `scripts/etl/seed_master_osha.py`, `seed_master_whd.py`, `seed_master_nlrb.py`, etc.
- `scripts/matching/config.py` -- MatchConfig dataclass with 9 predefined scenarios
- `scripts/scoring/refresh_all.py` -- full MV rebuild chain

### Match Tables (output targets)
- `osha_f7_matches`, `whd_f7_matches`, `sam_f7_matches`
- `national_990_f7_matches`, `corpwatch_f7_matches`, `usaspending_f7_matches`
- `unified_match_log` (2.2M audit trail)
- `master_employer_source_ids` (5.2M linkages)
- `master_employer_merge_log` (699K merge records)

### Key Schema Constraints
- `f7_employer_id` is TEXT everywhere
- `master_employers` PK is `master_id` (BIGINT), name is `display_name`/`canonical_name`
- `master_employers.zip` (not `zip_code`), `master_employers.naics` (not `naics_code`)
- `osha_establishments` uses `site_city`, `site_state`, `site_zip`
- `sam_entities` uses `physical_city`, `physical_state`, `physical_zip`
- `master_employer_source_ids` CHECK constraint has hardcoded allowed source list
- `unified_match_log` columns: id, run_id, source_system, source_id, target_system, target_id, match_method, match_tier, confidence_band, confidence_score, evidence, status, created_at

---

## Execution Plan (Blocking Order)

### PHASE 0: Pre-Flight Checks & Backup
**Blocks:** Everything

1. Snapshot current state for rollback:
   ```sql
   CREATE TABLE osha_f7_matches_backup AS SELECT * FROM osha_f7_matches;
   CREATE TABLE whd_f7_matches_backup AS SELECT * FROM whd_f7_matches;
   CREATE TABLE sam_f7_matches_backup AS SELECT * FROM sam_f7_matches;
   CREATE TABLE national_990_f7_matches_backup AS SELECT * FROM national_990_f7_matches;
   CREATE TABLE corpwatch_f7_matches_backup AS SELECT * FROM corpwatch_f7_matches;
   CREATE TABLE usaspending_f7_matches_backup AS SELECT * FROM usaspending_f7_matches;
   CREATE TABLE unified_match_log_backup AS SELECT * FROM unified_match_log;
   CREATE TABLE master_employer_source_ids_backup AS SELECT * FROM master_employer_source_ids;
   CREATE TABLE master_employer_merge_log_backup AS SELECT * FROM master_employer_merge_log;
   CREATE TABLE master_employers_backup AS SELECT * FROM master_employers;
   ```
2. Record current benchmarks (row counts, match rates, cross-linkage %) for comparison.
3. Verify all source tables are intact (row counts match expected).
4. Verify indexes exist on all source tables for name, state, city, EIN columns.
5. Verify `pg_trgm` extension is installed.

**Estimated time:** 30-60 min (mostly backup I/O for 4.5M master_employers)

---

### PHASE 1: Rebuild master_employers from Scratch
**Blocks:** Phase 2, 3, 4, 5
**Blocked by:** Phase 0

The current master_employers was built incrementally with different seed scripts at different times. A clean rebuild ensures consistent normalization.

1. **Truncate master_employers and master_employer_source_ids** (keep backups from Phase 0).
2. **Re-seed from each source in priority order:**
   - F7 first (these are the reference employers, highest priority)
   - Then OSHA, WHD, NLRB, SAM, CorpWatch, Mergent, BMF, PPP, Form5500
   - Each seed script should:
     a. Normalize names (standard + aggressive) using `src/python/matching/name_normalization.py`
     b. Try EIN exact match to existing master record first
     c. Try canonical_name + state exact match second
     d. If no match, INSERT as new master_employer
     e. Always INSERT into master_employer_source_ids
3. **After all seeds complete, verify:**
   - Total master_employers should be in the 4-5M range
   - Every source system should have entries in master_employer_source_ids
   - No orphaned source_ids (every master_id in source_ids exists in master_employers)

**Estimated time:** 2-4 hours
**Success criteria:** master_employers populated, all sources linked, no orphans

---

### PHASE 2: Full Deterministic Matching (Sources -> F7)
**Blocks:** Phase 3, 4
**Blocked by:** Phase 1

Run the 6-tier deterministic cascade for EVERY source against f7_employers_deduped. This is matching source records to union reference employers.

1. **Clear existing F7 match tables:**
   ```sql
   TRUNCATE osha_f7_matches, whd_f7_matches, sam_f7_matches,
            national_990_f7_matches, corpwatch_f7_matches;
   TRUNCATE unified_match_log;
   ```

2. **Run deterministic matching for each source (can parallelize across sources):**
   ```bash
   py scripts/matching/run_deterministic.py osha --rematch-all
   py scripts/matching/run_deterministic.py whd --rematch-all
   py scripts/matching/run_deterministic.py sam --rematch-all
   py scripts/matching/run_deterministic.py 990 --rematch-all
   py scripts/matching/run_deterministic.py sec --rematch-all
   py scripts/matching/run_deterministic.py corpwatch --rematch-all
   py scripts/matching/run_deterministic.py bmf --rematch-all
   ```
   For large sources (OSHA: 1M rows), use batched mode:
   ```bash
   py scripts/matching/run_deterministic.py osha --rematch-all --batch 1/4
   py scripts/matching/run_deterministic.py osha --rematch-all --batch 2/4
   py scripts/matching/run_deterministic.py osha --rematch-all --batch 3/4
   py scripts/matching/run_deterministic.py osha --rematch-all --batch 4/4
   ```

3. **Run NLRB-specific matching:**
   ```bash
   py scripts/matching/match_nlrb_ulp.py
   ```

4. **Run USAspending matching:**
   ```bash
   PYTHONPATH=. py scripts/etl/_match_usaspending.py
   ```

5. **After all matching, verify F7 match rates meet or exceed current benchmarks:**
   - OSHA -> F7: >= 19.7% (28,973 distinct F7)
   - WHD -> F7: >= 7.3% (10,744 distinct F7)
   - SAM -> F7: >= 11.4% (16,802 distinct F7)
   - 990 -> F7: >= 7.2% (10,646 distinct F7)
   - USAspending -> F7: >= 6.3% (9,305 distinct F7)

**Estimated time:** 4-12 hours (OSHA alone is 1M records through 6 tiers)
**Success criteria:** All F7 match rates >= current benchmarks. unified_match_log populated.

---

### PHASE 3: Cross-Source Corroboration & Score Eligibility
**Blocks:** Phase 4
**Blocked by:** Phase 2

1. **Run corroboration:**
   ```bash
   py scripts/matching/corroborate_matches.py
   ```
   This cross-validates matches: if OSHA and WHD both match the same F7 employer, confidence increases. Matches with only one low-confidence source get flagged.

2. **Run score eligibility:**
   ```bash
   py scripts/matching/add_score_eligible.py
   ```
   Marks which F7 employers have sufficient match quality to receive scores.

3. **Verify:**
   - Corroboration should flag high-FP fuzzy matches (confidence < 0.85)
   - score_eligible should cover roughly the same set as before

**Estimated time:** 1-2 hours
**Success criteria:** Corroboration complete, score_eligible flags set

---

### PHASE 4: Master Employer Deduplication
**Blocks:** Phase 5
**Blocked by:** Phase 1 (needs seeded master_employers), Phase 2 (informs quality)

Full dedup of master_employers using the 4-phase dedup pipeline.

1. **Clear prior dedup state:**
   ```sql
   TRUNCATE master_employer_dedup_progress;
   TRUNCATE master_employer_merge_log;
   ```

2. **Run dedup phases sequentially:**
   ```bash
   # Phase 1: EIN exact dedup
   py scripts/etl/dedup_master_employers.py --phase 1

   # Phase 2: Exact name+state dedup
   py scripts/etl/dedup_master_employers.py --phase 2

   # Phase 3: Fuzzy name+state dedup (RapidFuzz, token_sort_ratio >= 0.85)
   py scripts/etl/dedup_master_employers.py --phase 3

   # Phase 4: Quality cleanup
   py scripts/etl/dedup_master_employers.py --phase 4
   ```

3. **Verify against prior benchmarks:**
   - EIN phase: ~10K merges expected
   - Exact name+state: ~600K merges expected
   - Fuzzy: ~75K merges expected
   - Total merges should be in the 650-750K range
   - Final master_employers count should be ~4.5M (down from ~5.2M pre-dedup)

4. **After dedup, cross-linkage should improve:**
   - Target: < 90% single-source employers (currently 93.7%)
   - Target: > 7% with 2+ sources (currently 5.0%)

**Estimated time:** 2-6 hours (fuzzy phase is the bottleneck -- 4.5M pairwise within blocking groups)
**Success criteria:** Merge counts comparable to prior run. Cross-linkage improved.

---

### PHASE 5: Rebuild Employer Groups & Scorecards
**Blocks:** Nothing (final phase)
**Blocked by:** Phase 3 + Phase 4

1. **Rebuild employer groups:**
   ```bash
   py scripts/matching/build_employer_groups.py
   ```

2. **Rebuild corporate crosswalk:**
   ```bash
   PYTHONPATH=. py scripts/etl/build_crosswalk.py
   PYTHONPATH=. py scripts/etl/_match_usaspending.py
   ```

3. **Rebuild all MVs in dependency order:**
   ```bash
   py scripts/scoring/refresh_all.py --with-report
   ```
   This runs the full chain:
   - create_scorecard_mv.py (OSHA organizing scorecard)
   - compute_gower_similarity.py (or --skip-gower if unchanged)
   - build_employer_data_sources.py (13-source flags)
   - build_unified_scorecard.py (10-factor union reference scorecard)
   - build_target_data_sources.py (non-union source flags)
   - build_target_scorecard.py (non-union 8-signal scorecard)
   - rebuild_search_mv.py (unified search index)

4. **Run score change report:**
   Compare new scores against pre-rematch snapshot. Report:
   - How many employers changed tiers
   - Net match rate changes per source
   - Factor coverage changes

5. **Run full test suite:**
   ```bash
   py -m pytest tests/ -x -q
   cd frontend && npx vitest run
   ```

**Estimated time:** 2-4 hours (Gower similarity is the bottleneck)
**Success criteria:** All tests pass. Score distribution is reasonable. No regressions.

---

## Total Estimated Runtime

| Phase | Duration | Can Parallelize? |
|-------|----------|-----------------|
| Phase 0: Backup | 30-60 min | No |
| Phase 1: Re-seed master | 2-4 hours | Sources can be parallelized |
| Phase 2: Deterministic matching | 4-12 hours | Sources can be parallelized |
| Phase 3: Corroboration + eligibility | 1-2 hours | No |
| Phase 4: Master dedup | 2-6 hours | Phases are sequential |
| Phase 5: Rebuild groups + MVs | 2-4 hours | MV chain is sequential |
| **Total** | **12-28 hours** | |

---

## Success Criteria (Ratchets -- Must Meet or Exceed)

| Metric | Current Baseline | Minimum Acceptable |
|--------|-----------------|-------------------|
| OSHA -> F7 distinct match rate | 19.7% (28,973) | >= 19.0% |
| WHD -> F7 distinct match rate | 7.3% (10,744) | >= 7.0% |
| SAM -> F7 distinct match rate | 11.4% (16,802) | >= 11.0% |
| 990 -> F7 distinct match rate | 7.2% (10,646) | >= 7.0% |
| USAspending -> F7 match count | 9,305 | >= 9,000 |
| Master employer dedup merges | 699,191 | >= 650,000 |
| Single-source master employers | 93.7% | <= 92% (improvement) |
| Multi-source (2+) master employers | 6.3% | >= 7% (improvement) |
| Backend tests passing | 1,135 | >= 1,135 |
| Frontend tests passing | 249 | >= 249 |
| mv_target_scorecard rows | 4,384,210 | >= 4,000,000 |
| mv_unified_scorecard rows | 146,863 | = 146,863 (1:1 with F7) |

---

## Rollback Plan

If any phase fails or results are worse than baselines:

1. **Restore from Phase 0 backups:**
   ```sql
   TRUNCATE osha_f7_matches; INSERT INTO osha_f7_matches SELECT * FROM osha_f7_matches_backup;
   TRUNCATE whd_f7_matches; INSERT INTO whd_f7_matches SELECT * FROM whd_f7_matches_backup;
   -- (repeat for all match tables)
   TRUNCATE master_employers; INSERT INTO master_employers SELECT * FROM master_employers_backup;
   TRUNCATE master_employer_source_ids; INSERT INTO master_employer_source_ids SELECT * FROM master_employer_source_ids_backup;
   TRUNCATE master_employer_merge_log; INSERT INTO master_employer_merge_log SELECT * FROM master_employer_merge_log_backup;
   TRUNCATE unified_match_log; INSERT INTO unified_match_log SELECT * FROM unified_match_log_backup;
   ```
2. **Re-run refresh_all.py** to rebuild MVs from restored data.
3. **Drop backup tables** once new data is confirmed good.

---

## Known Gotchas

- **Windows cp1252:** Use ASCII in print statements. No Unicode arrows.
- **Do NOT pipe Python through grep on Windows** -- Python hangs as zombie.
- **`py -c` with `!` in passwords:** Write to .py file instead.
- **OSHA `union_status` codes:** N/Y used 2012-2016, A/B used 2015+. Filter `!= 'Y'`, NOT `= 'N'`.
- **NLRB elections has NO `state` column** -- state is in `nlrb_participants`, must JOIN.
- **`f7_employers_deduped.cbsa_code` is 100% NULL** -- don't join on it.
- **psycopg2 returns Decimal** for DECIMAL columns -- wrap in `float()`.
- **RapidFuzz FP rates by band:** 0.80-0.85 = 40-50% FP, 0.85-0.90 = 50-70% FP, 0.90-0.95 = 30-40% FP. Below 0.85 was previously deactivated for this reason.
- **Large UPDATE on big tables (1.9M+):** Self-join CTE takes 30+ min. Batch.
- **`TRUNCATE ... CASCADE` on parent FK tables** cascades to children -- use plain TRUNCATE or DELETE.
- **After crosswalk rebuild, must re-run `_match_usaspending.py`** for federal contractor columns.
- **`master_employer_source_ids` CHECK constraint** has hardcoded allowed source list -- if adding a new source, ALTER the constraint first.
- **MV dependency chain is strict** -- if you DROP CASCADE any MV, the entire downstream chain must be rebuilt.
- **`osha_violation_summary` joins on `establishment_id`** (NOT `activity_nr`).
