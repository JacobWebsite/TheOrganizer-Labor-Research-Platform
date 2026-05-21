# Pfizer Bundled Migration — Follow-Up Findings

Date: 2026-05-21
Branch: `ship/2026-05-18-pfizer-name-fix`
Round-2 audit: `pfizer_bundled_20260521T152638Z`

## 1. Broader-regex round-2 migration — DONE

The original `$`-anchored CANDIDATE_REGEX_PG missed bug victims whose display_name had parenthetical/descriptive tails (e.g. `PFIZER PRODUCTS CORPORATION (DE)` → `pfizer productsoration (de)`). Per-row check found 4,317 additional master victims under the broader regex.

Round-2 commit `e55c75a` drops the anchor; commit `pfizer_bundled_20260521T152638Z` migrated:
- 2,549 master canonical_name UPDATEs
- 2,607 mergent normalized UPDATEs
- 30 dedup merges
- 0 ID-conflict skips
- 0 f7-vs-f7 skips
- All 7 verification gates PASS

Post-round-2 state: **0 master rows** match the tight-signature corrupt patterns (`%productsoration%`, `%hcporation%`, `%holdingsoration%`, `%technologiesoration%`, `%systemsoration%`, `%grouporation%`, `%industriesoration%`, `%solutionsoration%`, `%enterprisesoration%`, `%servicesoration%`).

Snapshot tables retained: `backfill_pfizer_pre_20260521T152638Z` + `..._source_ids_pre_20260521T152638Z` + `..._mergent_pre_20260521T152638Z`.

## 2. Pfizer H.C.P. duplicate — DONE

Pair: 1987063 (mergent, NY, NEW YORK, EIN 380908630) + 8282347 (gleif, NY, NULL city, no EIN).

The bundled migration didn't merge them because the collision group SQL includes `city` and the two rows had different city values. Manually merged via `merge_one()` 2026-05-21:
- Winner: 1987063 (mergent — source_priority 2 vs gleif 6)
- Loser: 8282347 (deleted, gleif source_id absorbed)
- `merge_log` row inserted with `merge_phase='pfizer_bundled_hcp_followup'`

## 3. 48 ID-conflict skips — review pending

From the first migration run (`pfizer_bundled_20260520T221958Z`). All have same canonical + state but conflicting EINs. Audit table `pfizer_skipped_id_conflicts_20260520T221958Z` persists the pairs.

Enriched CSV produced: `docs/scratch/pfizer_id_conflict_review_2026_05_21.csv` (loser/winner master_ids + EINs + display + canonical + state).

Patterns observed:
- All 48 have both rows still present (none merged via other paths)
- 6/48 share the first 3 EIN chars (same IRS issuer; likely same entity with stale data)
- Common case: same display + state, EINs differ (e.g. ANNE GRADY CORPORATION OH, BRYANT PARK CORPORATION NY)
- A few are clearly LLC/CORP variants (e.g. ATALANTA SOSNOFF CAPITAL, LLC vs ATALANTA/SOSNOFF CAPITAL CORPORATION)

Not auto-merged — needs human judgment between "same entity, one stale EIN" vs "two distinct legal entities".

## 4. state_local columns — pre-existing real upstream work

`build_employer_data_sources.py` references three columns on `corporate_identifier_crosswalk` that don't exist:
- `is_state_local_contractor`
- `state_local_contract_count`
- `state_local_source_count`

`scripts/etl/build_crosswalk.py` does NOT populate these columns. They were never added to the table schema. The SQL was written assuming they would be there.

The actual state/local contract data lives in:
- `state_local_contracts_unified` (6.08M rows)
- `state_local_contracts_master_matches` (34.6K rows)
- `state_local_contracts_f7_matches` (4.0K rows)

Real fix path (deferred — separate ticket):
1. `ALTER TABLE corporate_identifier_crosswalk ADD COLUMN is_state_local_contractor BOOLEAN, ADD COLUMN state_local_contract_count INT, ADD COLUMN state_local_source_count INT`
2. Populate via JOIN from `state_local_contracts_master_matches` grouped by `f7_employer_id`
3. Update `build_crosswalk.py` to compute these on every rebuild
4. Drop the FALSE/0 stub in `build_employer_data_sources.py` (commit `88480d8`) once columns exist

Current stub unblocks the MV chain; correctness when state_local data is missing is "0 contracts everywhere," which is a known-safe under-count.

## 5. 48,467 (canonical, state) duplicate groups remain

Phase-2 dedup landscape: 48,467 distinct `(canonical_name, state)` groups have ≥2 rows in master_employers. The Pfizer migration's bundled dedup only handled groups where ≥1 row was a Pfizer-bug victim (601 groups → 559 + 30 = 589 merges across the two runs).

The remaining 47,878 groups are non-Pfizer dedup candidates that have been accumulating across all data sources. Running `py scripts/etl/dedup_master_employers.py --phase 2 --limit 50000` would attack them with the same merge_one machinery + Employer.rank() winner selection.

Out of scope for the Pfizer migration. Tracked separately.
