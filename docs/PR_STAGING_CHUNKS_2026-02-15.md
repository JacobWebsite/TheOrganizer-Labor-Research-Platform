# PR Staging Chunks (Exact Commands)

Use these commands from repo root. Each chunk is intentionally conflict-minimized.

## Chunk 1: Frontend Safety + Regression Guards
```bash
git add files/js/scorecard.js files/js/detail.js files/js/modals.js
git add tests/test_frontend_xss_regressions.py
git add scripts/analysis/prioritize_innerhtml_api_risk.py scripts/analysis/check_js_innerhtml_safety.py
git add docs/PARALLEL_INNERHTML_API_RISK_PRIORITY.md docs/JS_INNERHTML_SAFETY_CHECK.md
```

## Chunk 2: Password Scanner/Fixer + Rollback
```bash
git add scripts/analysis/find_literal_password_bug.py scripts/analysis/fix_literal_password_bug.py
git add scripts/analysis/rollback_password_fix.py
git add docs/PARALLEL_PHASE1_PASSWORD_AUDIT.md docs/PARALLEL_PASSWORD_AUTOFIX_REPORT.md
```

## Chunk 3: Scorecard API Parity
```bash
git add api/routers/organizing.py
git add tests/test_scorecard_contract_field_parity.py
```

## Chunk 4: db_config Migration Tooling + Guard
```bash
git add scripts/analysis/migrate_to_db_config_connection.py scripts/analysis/rollback_db_config_migration.py
git add tests/test_db_config_migration_guard.py
git add scripts/analysis/smoke_migrated_scopes.py
git add docs/PARALLEL_DB_CONFIG_MIGRATION_REPORT.md
```

## Chunk 5: Migrated Scripts (verify + maintenance + export)
```bash
git add scripts/verify/*.py
git add scripts/maintenance/*.py
git add scripts/export/*.py
```

## Chunk 6: Validation/Release Gate Tooling
```bash
git add scripts/analysis/phase1_merge_validator.py scripts/analysis/run_ci_checks.py
git add scripts/analysis/check_router_docs_drift.py scripts/analysis/build_release_gate_summary.py
git add scripts/analysis/capture_query_plans.py scripts/analysis/benchmark_endpoints.py
git add docs/PHASE1_MERGE_VALIDATION_REPORT.md docs/CI_CHECK_REPORT.md docs/RELEASE_GATE_SUMMARY.md
git add docs/PARALLEL_ROUTER_DOCS_DRIFT.md docs/PARALLEL_QUERY_PLAN_BASELINE.md docs/PARALLEL_FRONTEND_API_AUDIT.md
```

## Chunk 7: Phase 3 Scaffolding
```bash
git add src/python/matching/__init__.py src/python/matching/name_normalization.py src/python/matching/integration_stubs.py
git add tests/test_name_normalization.py
git add docs/PHASE3_NORMALIZATION_INTEGRATION_CHECKLIST.md
```

## Chunk 8: Handoff/Planning Docs
```bash
git add docs/CHAT_COMPRESSED_2026-02-15.md
git add docs/HANDOFF_CLAUDE_GEMINI_2026-02-15.md
git add docs/CHECKPOINT_PARALLEL_CODEX_PHASE1_2026-02-15.md
git add docs/PARALLEL_PR_BUNDLE_PLAN.md docs/PR_STAGING_CHUNKS_2026-02-15.md
```

