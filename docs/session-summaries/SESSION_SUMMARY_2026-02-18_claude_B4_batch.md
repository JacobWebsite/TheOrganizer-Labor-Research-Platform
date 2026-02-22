# Session Summary - 2026-02-18 (Claude Code — B4 Batched OSHA Re-run + Quick Wins + Crosswalk)

## Scope
Added batched re-run capability to the matching pipeline, completed OSHA batch 1/4, started batch 2/4. Dropped unused indexes (3 GB), fixed freshness bug, applied 29 crosswalk remaps for missing unions.

## Completed Work

### Batched re-run feature (`run_deterministic.py`)
- Added `--batch N/M` argument (e.g., `--batch 1/4` for first 25%)
- Records sorted deterministically by ID, sliced to requested batch
- Per-batch supersede: only touches current batch's old matches in `unified_match_log` (unprocessed batches keep their existing matches intact)
- Checkpoint file saved to `checkpoints/{source}_rerun.json` after each batch with per-batch stats
- `--batch-status` flag to check progress without running anything
- Quality report printed after each batch: match rate, band breakdown, method distribution, cross-batch comparison, automatic warnings (>60% rate, excessive LOW matches)
- Created `checkpoints/` directory

### OSHA Batch 1/4 (COMPLETE)
- Run ID: `det-osha-20260218-091338-b1of4`
- 251,804 records processed

| Metric | Value |
|--------|-------|
| Total matched | 101,589 (40.3%) |
| HIGH+MEDIUM (written to legacy) | 24,349 (9.7%) |
| LOW (rejected) | 77,240 |
| No match | 150,215 |
| Splink matches | 12,946 |
| Trigram matches | 78,133 (mostly LOW/rejected) |
| Exact tiers 1-4 | 10,510 |

### OSHA Batch 2/4 (running at session end)

### Task 3: Dropped unused indexes
- 336 non-unique, non-primary indexes with 0 scans dropped
- 43 indexes on protected pipeline tables preserved
- **3.0 GB recovered**
- VACUUM ANALYZE on 15 major tables
- 5 GLEIF indexes were orphans (tables already gone)

### Task 4: Freshness "3023" bug
- Fixed 1 row: `ny_state_contracts.end_date` 3023-03-31 -> 2023-03-31
- Fixed 2 Unicode characters in `create_data_freshness.py` (would crash on cp1252)
- Refreshed `data_source_freshness` table

### Crosswalk remaps (Issue #7)
- Applied 29 remaps: 24 one-to-one (automatic) + 5 one-to-many (manual picks)
- Orphaned file numbers: 195 -> 166
- Orphaned workers: 92,627 -> 61,743 (30,884 resolved)
- **Deferred:** Case 12590 (CWA District 7, 80 rels, 38K workers) -- district council needs geographic devolution across 5 successor locals spanning 19 states
- Manual tie-break decisions:
  - 18001 (USW multistate) -> 51950 (WV): 8 shared employers
  - 23547 (GCC/IBT 14-M) -> 521560 (PPPWU): higher confidence, GCC successor
  - 49490 (1199SEIU 123) -> 83 (Falls Church, VA): membership size match
  - 56148 (GCC/IBT 705) -> 542772 (PPPWU): higher confidence, existing rels
  - 65266 (UFCW 800) -> 544266 (Dayton, OH): 2/3 employers in OH

### Codex review
- Task 1 (missing unions): Good research, wrote `docs/MISSING_UNIONS_ANALYSIS.md`
- Task 2 (WHD fix): Fixed f7_employers_deduped (11,297 employers), but left `update_whd_scores.py` targeting deprecated Mergent scorecard
- Task 5 (NLRB ULP gap): Found 871K unmatched rows with garbage geography (placeholder literals). Blocker documented.

### Codex parallel task document
- Wrote `docs/CODEX_PARALLEL_TASKS_2026_02_18.md` with 7 independent tasks:
  1. Investigate 195 missing unions (Phase C1-C3)
  2. Fix WHD zeros on f7_employers_deduped
  3. Drop unused database indexes (~1.67 GB)
  4. Fix freshness metadata "3023" bug
  5. NLRB ULP matching gap analysis
  6. Catalog unused OLMS annual report tables (Phase C4)
  7. Migrate scorecard UI to unified scorecard

## Quality Assessment

The name similarity floor (token_sort_ratio >= 0.65) is working. The previous catastrophic run (81% match rate, 835K garbage matches) is not repeating. Active rate of ~9% is higher than old baseline (~4%) mainly from Splink finding legitimate new matches.

**Known concern:** A few Splink false positives at 0.65 floor (e.g., "nex transport" -> "cassens transport"). Could tighten to 0.70 if needed after all 4 batches complete and full quality review.

**Sample good Splink matches:**
- "supreme steel inc" -> "supreme steel" (sim=0.65)
- "teva pharmaceuticals usa" -> "teva pharmaceuticals" (sim=0.909)
- "royals hot chicken" -> "royals hot chicken" (sim=0.857)

**Sample correctly rejected trigram matches:**
- "GREGORY PACKAGING, INC" -> "Graphic Packaging Intl" (sim=0.452, LOW)
- "COMMERCIAL INTERIORS, INC." -> "WEG Commercial Motors" (sim=0.406, LOW)

## To Resume

1. Check batch 2/4: `py scripts/matching/run_deterministic.py osha --batch-status`
2. Run batch 3/4: `py scripts/matching/run_deterministic.py osha --rematch-all --batch 3/4`
3. Run batch 4/4: `py scripts/matching/run_deterministic.py osha --rematch-all --batch 4/4`
4. After all 4 OSHA batches: run SEC, BMF, WHD, SAM, 990 (smaller sources, unbatched)
5. Decision needed: tighten Splink name floor from 0.65 to 0.70? Review after all OSHA batches.
6. Refresh MVs after all matching complete
7. Devolve CWA District 7 (fnum 12590) relations by geography

## Pre-run DB State (for rollback reference)
- OSHA establishments: 1,007,217
- osha_f7_matches: 147,271
- UML osha active: 62,903
- UML osha rejected: 132,430
- UML osha superseded: 147,865

## Files Modified
- `scripts/matching/run_deterministic.py` -- added batch/checkpoint logic
- `scripts/maintenance/create_data_freshness.py` -- fixed Unicode
- `scripts/analysis/show_crosswalk_detail.py` (new) -- one-to-many crosswalk analysis
- `checkpoints/` directory created (new)
- `checkpoints/osha_rerun.json` -- batch 1/4 checkpoint
- `docs/CODEX_PARALLEL_TASKS_2026_02_18.md` (new)
- `PROJECT_STATE.md` -- updated B4 status, issue #7, issue #15, index count
- `ny_state_contracts` table -- fixed 1 row (3023 -> 2023)
- `f7_union_employer_relations` table -- 29 crosswalk remaps (247 rows updated)
- 336 unused database indexes dropped (3.0 GB)
