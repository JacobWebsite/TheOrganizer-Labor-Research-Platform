# Session Summary: 2026-02-22 - Codex - Master Dedup Progress + Phase 3 Plan

## Scope
- Documented Phase 3 dedup execution approach and safety controls.
- Completed Phase 2 dedup to exhaustion.
- Completed Phase 4 quality-score backfill using resumable chunked updates.

## Dedup Execution Status

### Phase 1 (EIN)
- Completed previously.
- No additional merges on resume.

### Phase 2 (Name+State Exact)
- Multiple bounded runs completed (`--max-seconds 900`, `--batch-size 250`).
- Final resume run returned zero merges.
- Net table reduction across Phase 1+2:
  - `master_employers`: `3,026,290 -> 2,736,890`
  - Reduced: `289,400` rows.

### Phase 4 (Quality Scores)
- Initial monolithic update timed out.
- Reworked to chunked/resumable logic using `master_employer_dedup_progress` cursor.
- Completion check:
  - Resume run reported `Updated: 0`, `Last PK: 4,027,816` (already fully processed).
- Final distribution:
  - `0-20`: 781,777
  - `21-40`: 1,927,187
  - `41-60`: 26,295
  - `61-80`: 1,531
  - `81-100`: 100

## Phase 3 (Name+State Fuzzy) - Implementation Plan

### Objective
Run lower-confidence fuzzy merges with explicit safeguards to avoid over-merging.

### Current Controls in Script
- Blocking strategy: `(state, left(canonical_name, 8))` blocks.
- Similarity threshold: `--min-name-sim` (default `0.85`, configurable).
- Confirming signal required:
  - same city OR
  - same ZIP prefix OR
  - same NAICS-2 prefix.
- F7 protection:
  - records with F7 source are never merged into non-F7 winners.
  - no F7-vs-F7 loser merges.
- Resumability:
  - persisted cursor in `master_employer_dedup_progress` (`phase_3_fuzzy`).
- Timeout safety:
  - `statement_timeout`, `lock_timeout`, bounded run windows (`--max-seconds`).
- Transaction safety:
  - committed in batches (`--batch-size`).

### Recommended Rollout
1. Dry-run sample:
   - `python scripts/etl/dedup_master_employers.py --phase 3 --dry-run --limit 200 --min-name-sim 0.88`
2. Conservative first write run:
   - `python scripts/etl/dedup_master_employers.py --phase 3 --limit 500 --min-name-sim 0.88 --batch-size 200 --max-seconds 900`
3. Resume iteratively:
   - same command + `--resume`
4. If precision is strong, gradually relax:
   - `--min-name-sim 0.87` then `0.86` (avoid dropping straight to `0.85`).

### Validation Queries After Each Wave
- No source-id orphans:
  - `SELECT COUNT(*) FROM master_employer_source_ids s LEFT JOIN master_employers m ON m.master_id = s.master_id WHERE m.master_id IS NULL;`
- Merge volume by phase:
  - `SELECT merge_phase, COUNT(*) FROM master_employer_merge_log GROUP BY 1 ORDER BY 2 DESC;`
- Spot-check fuzzy evidence:
  - `SELECT winner_master_id, loser_master_id, merge_confidence, merge_evidence FROM master_employer_merge_log WHERE merge_phase='name_state_fuzzy' ORDER BY merge_id DESC LIMIT 100;`

## Files Changed This Session
- `scripts/etl/dedup_master_employers.py`
  - connection-drop resilience
  - Phase 4 chunked/resumable update path
  - Phase 4 timeout now configurable via CLI

