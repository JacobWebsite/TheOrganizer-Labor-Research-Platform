# Prompt for Claude: Full Parallel Work Update + Instructions

Use this as the authoritative handoff from Codex parallel lane.

Date: 2026-02-15
Repo: `C:\Users\jakew\Downloads\labor-data-project`

You must first read these files in order:
1. `docs/MASTER_PARALLEL_SUMMARY_2026-02-15.md`
2. `docs/CHAT_COMPRESSED_2026-02-15.md`
3. `docs/HANDOFF_CLAUDE_GEMINI_2026-02-15.md`
4. `docs/CI_CHECK_REPORT.md`
5. `docs/PHASE1_MERGE_VALIDATION_REPORT.md`
6. `docs/PARALLEL_DB_CONFIG_MIGRATION_REPORT.md`

## What has already been completed
- Frontend safety fixes and scorecard key alignment in:
  - `files/js/scorecard.js`
  - `files/js/detail.js`
  - `files/js/modals.js`
- Password quoted-literal bug lane completed (scanner/fixer + fixes; findings now 0).
- Scorecard list/detail parity patch in `api/routers/organizing.py` (`federal_contract_count`).
- Phase 3 normalization scaffolding and tests added.
- CI/validator/release tooling added and reports generated.
- `db_config.get_connection()` migration completed for:
  - `scripts/verify`
  - `scripts/maintenance`
  - `scripts/export`
- ETL migration batch 1 completed; ETL residual now 15.
- Python 3.14 import/dataclass loader blocker fixed in migration guard/smoke.

## Current validated state
- `python scripts/analysis/phase1_merge_validator.py` => Passed 7/7
- `python scripts/analysis/run_ci_checks.py` => Passed 6/6
- `python -m pytest tests/test_db_config_migration_guard.py -q` => 2 passed
- `python scripts/analysis/smoke_migrated_scopes.py` => pass
- Global residual migration backlog:
  - Files changed: 156
  - Total replacements: 160

## Important nuance
Two innerHTML checks differ by design:
- Merge validator includes prioritized-risk scanner (currently reports 1).
- CI check includes strict lint scanner (currently reports 0).
Do not treat this difference as a failing state unless strict lint regresses.

## Your next tasks (execute exactly)
1. Continue controlled migration on `scripts/import`:
- `python scripts/analysis/migrate_to_db_config_connection.py --dry-run --include-prefix scripts/import`
- `python scripts/analysis/migrate_to_db_config_connection.py --apply --include-prefix scripts/import --limit 25 --backup-dir docs/db_config_migration_backups`

2. After apply, run required checkpoints:
- `python -m py_compile <changed_files>`
- `python scripts/analysis/phase1_merge_validator.py`
- `python scripts/analysis/run_ci_checks.py`
- `python scripts/analysis/build_release_gate_summary.py`
- `python scripts/analysis/migrate_to_db_config_connection.py --dry-run --include-prefix scripts/import`

3. Update these docs with exact command outputs and counts:
- `docs/HANDOFF_CLAUDE_GEMINI_2026-02-15.md`
- `docs/CHAT_COMPRESSED_2026-02-15.md`
- `docs/PARALLEL_DB_CONFIG_MIGRATION_REPORT.md`

4. Then repeat for `scripts/cleanup` with the same batch protocol.

## Constraints
- Do not revert unrelated worktree changes.
- Keep migrations capped (`--limit 25`) and backed up.
- Treat `docs/db_config_migration_backups` as excluded scan area.

## Expected output from you
Return:
1. exact commands run
2. files changed and replacements
3. residual count for target prefix and global residual
4. validator/CI outcomes
5. any warnings or regressions
