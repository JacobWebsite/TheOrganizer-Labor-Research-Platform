# Claude/Gemini Update Prompt (Copy/Paste)

Use this exact update prompt in Claude and Gemini.

---
You are receiving a parallel-lane checkpoint from Codex. Treat this as source-of-truth.

Date: 2026-02-15

New completed work:
1) Python 3.14 migrator import blocker is fixed.
- `tests/test_db_config_migration_guard.py` and `scripts/analysis/smoke_migrated_scopes.py` now register migrator module in `sys.modules` before `exec_module`.
- Guard test and smoke now pass.

2) Fresh validation is green:
- `python -m pytest tests/test_db_config_migration_guard.py -q` -> 2 passed
- `python scripts/analysis/smoke_migrated_scopes.py` -> verify/maintenance pending=0, passed
- `python scripts/analysis/run_ci_checks.py` -> Passed 6/6
- `python scripts/analysis/phase1_merge_validator.py` -> Passed 7/7

3) Migrator hardening completed:
- `scripts/analysis/migrate_to_db_config_connection.py` now excludes `db_config_migration_backups` from scan candidates.

4) ETL migration batch 1 completed:
- Applied:
  - `python scripts/analysis/migrate_to_db_config_connection.py --apply --include-prefix scripts/etl --limit 25 --backup-dir docs/db_config_migration_backups`
- Residual ETL after apply:
  - `python scripts/analysis/migrate_to_db_config_connection.py --dry-run --include-prefix scripts/etl`
  - Result: `Files changed: 15`
- Compile/verification after apply:
  - `python -m py_compile` across `scripts/etl/*.py` passed (non-blocking warning in `scripts/etl/load_gleif_bods.py` for `\s` escapes)
  - validator/CI/release reports regenerated

5) Current global residual:
- `python scripts/analysis/migrate_to_db_config_connection.py --dry-run`
- `Files changed: 156`
- `Total replacements: 160`
- Largest buckets now:
  - `scripts/import`: 38
  - `scripts/cleanup`: 29
  - `scripts/matching`: 19
  - `scripts/etl`: 15
  - `scripts/density`: 14

Instructions (execute in this order):
1. Read:
- `docs/CHAT_COMPRESSED_2026-02-15.md`
- `docs/HANDOFF_CLAUDE_GEMINI_2026-02-15.md`
- `docs/CI_CHECK_REPORT.md`
- `docs/PARALLEL_DB_CONFIG_MIGRATION_REPORT.md`

2. Next migration batch target = `scripts/import`:
- `python scripts/analysis/migrate_to_db_config_connection.py --dry-run --include-prefix scripts/import`
- `python scripts/analysis/migrate_to_db_config_connection.py --apply --include-prefix scripts/import --limit 25 --backup-dir docs/db_config_migration_backups`

3. After each batch, run:
- `python -m py_compile <changed_files>`
- `python scripts/analysis/phase1_merge_validator.py`
- `python scripts/analysis/run_ci_checks.py`
- `python scripts/analysis/build_release_gate_summary.py`

4. Update docs with exact command output:
- files changed
- residual count
- compile/validator/CI status
- any warnings/regressions

Do not revert unrelated worktree files.
---
