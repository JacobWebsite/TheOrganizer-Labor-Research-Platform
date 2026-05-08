# 2026-05-05 -- Union Explorer Audit Harness

## Changes Made

**3 production bug fixes (Phase 0.5):**
- `api/routers/unions.py:947-975` -- CTE pre-aggregates `ar_membership` per `rpt_id` so the LEFT JOIN to `lm_data` is 1-to-1; eliminates 18x asset/receipts/disbursements inflation on every union with multi-row membership categories. Affected 5,679 distinct unions / 52,892 of 331,236 LM-2 filings (16%) at up to 78x worst case. Verified on SEIU Local 1 (f_num=23715): 2023 assets $262,330,056 -> $14,573,892 (matches `lm_data.ttl_assets`).
- `api/routers/unions.py:300-301` -- `EXCLUDED_AFFILIATIONS` check at the top of `get_national_union_detail` rejects SOC (Strategic Organizing Center, a federation, was returning 2.5M phantom members via `/api/unions/national/SOC`). Plus refactored line 255's hardcoded `('SOC')` literal to use the same constant.
- `frontend/src/features/union-explorer/UnionElectionsSection.jsx:81-97` -- replaced `if (!hasData) return null` with explicit fallback empty-state card so the section always renders when called, regardless of whether `electionNote` is populated.

**`api/config.py` formatter regression guard:** Autoflake/ruff was stripping `from db_config import DB_CONFIG` because it couldn't see the re-export. Worked around with explicit module rebind (`import db_config as _root_db_config; DB_CONFIG = _root_db_config.DB_CONFIG`). This caused L4 + L6 to fail at startup mid-orchestrator-run.

**New audit harness (9 files):**
- `scripts/maintenance/audit_union_explorer.py` -- master orchestrator with `--include-llm`, `--quick`, `--skip-layer N` flags
- `scripts/maintenance/audit_union_layer1.py` + `audit_union_truth_queries.sql` -- 20 deterministic SQL invariants, hard-gate
- `scripts/maintenance/audit_union_layer2.py` -- per-union API<->DB diff with `--mode http|asgi|direct`
- `scripts/maintenance/audit_union_layer4.py` -- DeepSeek-V3 advisory with reasoner escalation, cost cap
- `scripts/maintenance/audit_union_layer5.py` + `audit_union_anomaly_frozen.yaml` -- frozen + re-derived anomaly sets with prior-run diff
- `scripts/maintenance/audit_union_layer6.py` -- 10 response-shape sentinels (Playwright substitute)
- `scripts/maintenance/audit_union_reference_cards.yaml` -- 31 hand-curated affiliation cards
- `RELEASE_CHECKLIST.md` -- audit gate added

## Key Findings

**Codex cross-check produced 3 real bug catches** that pre-existing test suite (~1482 backend, ~344 frontend tests) entirely missed:
- `test_union_disbursements.py` checks bucket fields and internal sum but not API total vs `lm_data.ttl_disbursements` -- Bug 1 was 18x wrong on SEIU Local 1 with no test signal.
- `test_union_health.py` checks ranges, not truth sources.
- No tests touched `/api/unions/national/{aff_abbr}` SOC exclusion (Bug 2).
- No tests for the empty-state suppression (Bug 3).

**Layer 1 caught a 4th bug post-fix:** `/api/unions/national`'s formula uses `union_hierarchy.count_members` while canonical `v_union_members_counted` uses `v_union_members_deduplicated.count_members`. They diverge for 57 affiliations. CWA case: endpoint reports 43 members for the entire affiliation, canonical view reports 38,750. Filed as Open Problem.

**DeepSeek-V3 as auditor produces useful output at $0.0013-0.0037/union.** 20-union test cost $0.07 including reasoner escalation. Full 270-union run projected at ~$0.50-1.00.

**LM-2 disbursement schedule reconciliation is fundamentally broken** in the source data: `ttl_disbursements` (Statement A) does NOT equal SUM of itemized schedule lines because schedules use different accounting bases. 92% of filings diverge >5% even after excluding investments/loans. Replaced strict reconciliation check with "any single bucket > 5x ttl_disbursements" outlier detector (catches parsing bugs without false-positive churn).

## Roadmap Updates

No formal roadmap items closed. Audit harness is a NEW capability not in MERGED_ROADMAP_2026_04_25.md; should be added under "platform hygiene" once user reviews.

## Debugging Notes

- **Windows stdout buffering on concurrent subprocesses can mask completion entirely.** A 270-union DeepSeek run at concurrency 8 ran for 30+ min with 0 bytes in the output file before I killed it. Use `python -u` for any background Python you want to monitor. The Monitor tool's `tail -F | grep` only sees lines once Python flushes -- without `-u`, the buffer holds everything until process exit.
- **f_num typing inconsistency:** `unions_master.f_num` is varchar but `f7_employers_deduped.latest_union_fnum` is INT and `union_fnum_resolution_log.orphan_fnum` is INT. Joins need explicit `::text` cast. CLAUDE.md notes "f7_employer_id is TEXT everywhere" but `latest_union_fnum` is the exception.
- **Correlated subqueries via EXISTS over 26K rows × 331K LM filings hit 200+ second runtime.** Rewrite as `LEFT JOIN <DISTINCT subquery>` for 100x speedup.
- **Rate limiter blocks audit harness in TestClient mode.** Set `RATE_LIMIT_REQUESTS=0` env var BEFORE importing `api.main` (the constant is read at module-import time per `api/middleware/rate_limit.py:14`).
- **Reasoner JSON parsing fails 13/13 in escalation pass.** DeepSeek-R1 returns thinking content + JSON; `json.loads(text)` fails. Need to extract JSON block before parsing. Low priority.
