# Pfizer Back-fill + Dedup Bundle — Atomic Migration Plan

**Date:** 2026-05-20
**Branch:** `ship/2026-05-18-pfizer-name-fix` (worktree: `C:\Users\jakew\.local\bin\Labor_Data_Project_wt_pfizer_fix`)
**Synthesized from:** in-house Plan agent design + Codex CLI review

---

## Context

The Pfizer canonical-name back-fill migration ran with `--commit` today and rolled back cleanly because the post-fix collision count (10,690) exceeded the `--max-dedup-candidates 1000` safety threshold. DB is unchanged.

**Why this matters:** The 18,403 `mpany`-pattern corruptions (e.g. `kroger company` → `krogermpany`) create silent duplicate masters every Mergent reload. When fixed, each corrupt-then-fixed master collides with its clean sibling (typically GLEIF/SEC/SAM) on `(canonical_name, state, city)`. These collisions are *legitimate* duplicates — the corruption was hiding them. Until they're merged, every downstream consumer (search, scoring, dossiers, director-network) sees two rows for one company.

**Why Option B (bundled atomic txn) over Option A (chain dedup script after migration):** A leaves the DB in a broken 10,690-dup intermediate state between the two scripts. If the dedup step hits an edge case it cannot recover from, search/scoring degrade silently. B is harder to build but the migration either lands clean or doesn't land at all — the strictly safer end-state.

**Intended outcome:** One transaction repairs ~32,202 master canonical names, repoints all loser FK references to winners, deletes losers, writes merge-log audit rows, and updates ~36,627 Mergent normalized names. Either all of that lands, or none of it does. Existing `dedup_master_employers.py` merge logic gets reused (not forked).

**Design decisions confirmed:**
- ID-conflict policy: **skip the pair, log to audit table, continue** (don't abort the whole migration on one outlier)
- PR scope: **one branch, multiple commits, single review cycle**
- UX: **explicit `--bundled` flag**, off by default (keep current safety behavior unchanged)

---

## Recommended approach

Extract `merge_one()` and its supporting primitives into a new library `src/python/matching/master_dedup.py`. Convert `dedup_master_employers.py` into a thin CLI on top. Add a `--bundled` mode to the back-fill script that, inside one transaction:

1. Acquires an advisory lock (no concurrent migrations)
2. Snapshots affected rows to persistent `backfill_pfizer_pre_<TS>` tables (rollback insurance)
3. Stages canonical-fix plans into temp tables (`_pfizer_backfill_master`, `_pfizer_backfill_mergent`)
4. Materializes the post-fix collision graph (`_collision_groups`)
5. Validates: every collision involves ≥1 Pfizer-corrupt row; no row appears in both winner and loser sets
6. Picks one **terminal** winner per collision group via `Employer.rank()` (star topology, no chains)
7. Skips pairs with conflicting strong identifiers (EIN/CIK/LEI/DUNS) → logs to `_pfizer_skipped_id_conflicts`
8. Locks affected masters with `SELECT ... FOR UPDATE ORDER BY master_id` (deterministic, avoids deadlocks)
9. Bulk-repoints FK references from losers to winners across 6+ tables
10. Calls `merge_one()` per pair to write merge-log + blend winner fields + DELETE loser
11. UPDATEs surviving masters' `canonical_name` to corrected values
12. UPDATEs `mergent_employers.company_name_normalized`
13. Runs an in-txn verification ladder (5 hard gates)
14. Inserts a migration-audit row with counts + start/complete timestamps + merge-map checksum
15. Commits, or rolls back on any failure

MV refresh runs **after** commit (separate process) — `REFRESH MATERIALIZED VIEW CONCURRENTLY` for the three critical MVs.

---

## Critical files

| Path | Action | Why |
|---|---|---|
| `src/python/matching/master_dedup.py` | **NEW** (~260 LOC) | Extracted library: `Employer`, `MergeContext`, `SOURCE_PRIORITY`, `merge_one`, `fetch_employers`, `bulk_repoint`, `validate_merge_map`, `has_id_conflict` |
| `scripts/etl/dedup_master_employers.py` | EDIT (~-200 / +10) | Becomes thin CLI; imports from library; `MERGE_LOG_HAS_*` flags become `MergeContext` fields |
| `scripts/llm_dedup/apply_rule_merges.py` | EDIT (~-7 / +5) | Drops attribute-setting hack (lines 37–43); uses `MergeContext.detect()` |
| `scripts/llm_dedup/apply_llm_gold_merges.py` | EDIT (~-7 / +5) | Same pattern as `apply_rule_merges.py` |
| `scripts/maintenance/backfill_pfizer_canonical_corruption.py` | EDIT (+220 / -10) | Adds `--bundled` mode + `run_bundled()` orchestrator + snapshot logic + verification ladder |
| `tests/etl/test_master_dedup.py` | **NEW** (~280 LOC) | 12 unit + 7 integration tests for library primitives |
| `tests/etl/conftest.py` | **NEW** (~40 LOC) | `integration_conn` fixture (skips if `LABOR_TEST_DB` unset) |
| `tests/maintenance/test_backfill_pfizer_bundled.py` | **NEW** (~140 LOC) | End-to-end smoke on 50-row synthetic fixture |
| `tests/maintenance/__init__.py` | **NEW** (empty) | Package marker |
| `docs/runbooks/pfizer_backfill_rollback.md` | **NEW** (~80 LOC) | Level-3 rollback runbook (restore from snapshot) |
| `docs/scratch/pfizer_dedup_bundle_plan_2026_05_20.md` | **NEW** | This plan, copied into worktree |
| `RELEASE_CHECKLIST.md` | EDIT (+5) | "Drop `backfill_pfizer_pre_*` snapshot tables after ship" |

Net: ~+800 LOC, ~-220 LOC.

---

## Existing functions/utilities to reuse

| Function | Location | Use |
|---|---|---|
| `merge_one()` | `scripts/etl/dedup_master_employers.py:386` | Per-pair merge primitive (extract to library, do not re-implement) |
| `Employer.rank()` | `scripts/etl/dedup_master_employers.py:42-53` | Winner selection (extract) |
| `SOURCE_PRIORITY` dict | `scripts/etl/dedup_master_employers.py:23` | `{f7:0, sam:1, mergent:2, bmf:3, sec:4, 990:5, gleif:6}` — keep semantics |
| `fetch_employers()` | `scripts/etl/dedup_master_employers.py` | Batched `Employer` load (extract) |
| `_check_critical_mvs()` | `scripts/maintenance/backfill_pfizer_canonical_corruption.py:111` | MV existence gate — keep, re-run post-commit |
| `_buggy_normalize_name_for_per_row_check()` | `scripts/maintenance/backfill_pfizer_canonical_corruption.py` | Per-row bug-victim check — keep |
| `normalize_name_legal_suffixes_only()` | `src/python/matching/name_normalization.py:138` | Replacement normalizer — keep |
| `apply_rule_merges.py`'s `UnionFind` pattern | `scripts/llm_dedup/apply_rule_merges.py` | N-way cluster handling reference (not reused directly; we pick one winner per cluster top-down) |

---

## Step-by-step implementation

### Phase A — Library extraction (1.5 hr, LOW risk)

A.1. `src/python/matching/master_dedup.py`: copy `Employer`, `MergeContext` (new, replaces module globals), `SOURCE_PRIORITY`, `EMP_COUNT_PRIORITY`, `pref()`, `name_sim()`, `has_confirming_signal()`, `_get_pk_col()`, `_table_col()`, `ensure_dedup_tables()`, `fetch_employers()`, `merge_one()` from `dedup_master_employers.py`. Replace the two module-level booleans (`MERGE_LOG_HAS_REASON`, `MERGE_LOG_HAS_MERGED_BY`) with a `MergeContext` dataclass that has a `.detect(cur)` classmethod.

A.2. `dedup_master_employers.py`: keep `parse_args()`, `run_phase()`, `run_phase3_cascade()`, `run_phase4()`, `count_rows()`, `main()`. Replace the in-file copy of the extracted code with `from src.python.matching.master_dedup import (...)`. `run_phase*` functions take `ctx: MergeContext` instead of reading globals.

A.3. `apply_rule_merges.py` + `apply_llm_gold_merges.py`: drop attribute-setting hack (lines 37–43 in `apply_rule_merges.py`); use `MergeContext.detect(cur)` and pass it through.

A.4. Run existing test suite. Manual smoke: `py scripts/etl/dedup_master_employers.py --dry-run --phase 2 --limit 100` against local DB; output should match a pre-refactor `git stash`'d run.

**Gate:** zero production behavior change. `git diff --stat` shows only refactors.

### Phase B — `bulk_repoint()` primitive (1 hr, LOW risk)

B.1. Add to `master_dedup.py`:

```python
REPOINT_TARGETS = [
    ("employer_directors",       ("master_id",)),
    ("employer_wage_outliers",   ("master_id",)),    # UNIQUE on master_id
    ("sec_13f_issuer_master_map", ("master_id",)),
    ("employer_comparables",     ("employer_id", "comparable_employer_id")),  # UNIQUE composite
    ("rule_derived_hierarchy",   ("child_master_id", "parent_master_id")),
    # Runtime probe via _table_col() — missing tables silently skipped
]

def bulk_repoint(cur, winner_map_table: str = "_winner_map") -> Dict[str, int]:
    """For each (table, col) in REPOINT_TARGETS, UPDATE col = winner_master_id
    WHERE col = loser_master_id (joined against winner_map_table).

    Two-step for tables with UNIQUE constraints (DELETE collisions, then UPDATE).
    Tables missing in this DB → silent skip + 0 in result dict.
    Returns {f'{table}.{col}': rows_updated}.
    """
```

B.2. **Mandatory pre-impl step**: implementer runs this and updates `REPOINT_TARGETS` if anything is missing:

```sql
-- All declared FKs on master_employers.master_id
SELECT c.conrelid::regclass AS table_name,
       a.attname AS column_name,
       c.confdeltype AS on_delete,
       c.conname
FROM pg_constraint c
JOIN pg_attribute a ON a.attrelid = c.conrelid AND a.attnum = ANY(c.conkey)
WHERE c.contype = 'f' AND c.confrelid = 'master_employers'::regclass;

-- Un-FK'd columns that LOOK like master_id refs
SELECT t.table_name, c.column_name
FROM information_schema.columns c
JOIN information_schema.tables t USING (table_schema, table_name)
WHERE c.table_schema = 'public'
  AND c.column_name IN ('master_id', 'employer_id', 'comparable_employer_id',
                        'child_master_id', 'parent_master_id',
                        'winner_master_id', 'loser_master_id')
  AND t.table_type = 'BASE TABLE'
ORDER BY 1, 2;
```

B.3. Unit + integration tests for `bulk_repoint`: idempotence, two-step DELETE+UPDATE behavior, missing-table skip.

### Phase C — Bundled mode in the back-fill script (3.5 hr, MED risk)

C.1. Add `--bundled` flag to argparse. Default off — `--commit` without `--bundled` behaves unchanged (still refuses past 1000-collision threshold).

C.2. Replace `estimate_dedup_candidates()` with a function that materializes `_collision_groups`:

```sql
CREATE TEMP TABLE _post_fix_view AS
SELECT m.master_id,
       COALESCE(p.new_canonical, m.canonical_name) AS post_canonical,
       m.state, m.city, m.source_origin,
       EXISTS(SELECT 1 FROM master_employer_source_ids sid
              WHERE sid.master_id = m.master_id AND sid.source_system = 'f7') AS has_f7
FROM master_employers m
LEFT JOIN _pfizer_backfill_master p USING (master_id);

CREATE TEMP TABLE _collision_groups AS
SELECT post_canonical, state, city, array_agg(master_id ORDER BY master_id) AS ids
FROM _post_fix_view
WHERE post_canonical IS NOT NULL AND btrim(post_canonical) <> '' AND state IS NOT NULL
GROUP BY post_canonical, state, city
HAVING COUNT(*) >= 2
   AND COUNT(*) FILTER (WHERE master_id IN (SELECT master_id FROM _pfizer_backfill_master)) >= 1;
```

C.3. `_pick_winners_for_groups(cur, ctx) -> dict[loser_mid, winner_mid]`:
- iterate `_collision_groups` rows
- batch `fetch_employers(ids)` for each group
- sort by `Employer.rank()` to pick winner
- skip pairs where `winner.has_f7 AND loser.has_f7` (mirrors `dedup_master_employers.py` line 444)
- skip pairs where `has_id_conflict(winner, loser)` → log to `_pfizer_skipped_id_conflicts(loser_mid, winner_mid, conflict_field, loser_value, winner_value)`
- assemble star-topology map: every loser → one terminal winner per group

C.4. `validate_merge_map(cur, winner_map)` — fails fast if:
- self-merge (winner == loser)
- duplicate loser_master_id
- any master_id is both a winner and a loser
- a referenced master_id no longer exists

C.5. Snapshot tables (PERSISTENT — survive txn commit; named `backfill_pfizer_pre_<TS>`, `..._mergent_pre_<TS>`, `..._source_ids_pre_<TS>`).

C.6. Main bundled flow (replaces current `--commit` path when `--bundled` set):

```python
if args.commit and args.bundled:
    # Pre-flight (unchanged from non-bundled): MV check, plan build, CSV write
    with conn:                                          # autocommit=False
        with conn.cursor() as cur:
            _acquire_advisory_lock(cur, lock_id=18052026)  # arbitrary fixed int
            _set_timeouts(cur, statement='30min', lock='5min', idle_in_txn='30min')
            _stage_plan_temp_tables(cur, master_plan, mergent_plan)
            collision_count = _materialize_collision_groups(cur)
            log(f"  collision groups: {collision_count:,}")
            winner_map, skipped = _pick_winners_for_groups(cur, ctx)
            log(f"  winner map: {len(winner_map):,} pairs; skipped: {len(skipped):,}")
            _write_winner_map_table(cur, winner_map)
            validate_merge_map(cur, winner_map)
            _create_snapshot_tables(cur, ts)
            _verify_checksum_unchanged(cur, master_plan)   # abort if rows changed since preview
            _lock_affected_rows_for_update(cur, winner_map)
            repoint_counts = bulk_repoint(cur)
            log(f"  re-pointed: {repoint_counts}")
            for loser_mid, winner_mid in winner_map.items():
                winner_emp, loser_emp = _load_pair(cur, ctx, winner_mid, loser_mid)
                merge_one(cur, ctx, winner_emp, loser_emp,
                          phase="pfizer_bundled", conf=0.95,
                          ev={"rule": "post_backfill_collision"})
            master_updated = commit_master(cur, master_plan, log)
            mergent_updated = commit_mergent(cur, mergent_plan, log)
            _insert_migration_audit_row(cur, name="pfizer_bundled_2026_05_20",
                                        counts={...}, checksum=...,
                                        started=start_ts, completed=now())
            verification = _run_verification_ladder(cur, master_plan, winner_map, log)
            if not verification["all_pass"]:
                raise RuntimeError(f"Verification ladder failed: {verification}")
        conn.commit()
```

C.7. `_run_verification_ladder(cur, plan, winner_map, log)` runs in-txn before commit. See §Verification below.

### Phase D — Tests (2 hr, LOW risk)

D.1. `tests/etl/conftest.py`: `integration_conn` fixture using `LABOR_TEST_DB` env var; skip when unset.

D.2. `tests/etl/test_master_dedup.py` (12 unit + 7 integration). Critical cases:
- `Employer.rank()` source-priority ordering
- `pref()` longer-string wins, None handling
- `MergeContext.detect()` introspects pk_col + optional columns
- `has_id_conflict()` returns True only when both sides have non-null IDs that disagree
- `merge_one()` re-points source_ids, deletes loser, writes log, blends fields
- `bulk_repoint()` idempotent, handles UNIQUE conflicts, skips missing tables
- 3-way merge picks single terminal winner (no A→B→C chains)
- Two `has_f7=True` rows are NOT merged (line-444 rule preserved)

D.3. `tests/maintenance/test_backfill_pfizer_bundled.py`: seed 50 synthetic corrupt masters in 25 collision pairs; run bundled migration; assert verification ladder passes; assert rollback path leaves DB unchanged.

D.4. Full test run:
- `pytest tests/` (unit suite, skips integration)
- `LABOR_TEST_DB=... pytest tests/ -m integration` (full integration)

### Phase E — Documentation (30 min)

E.1. Copy plan to `docs/scratch/pfizer_dedup_bundle_plan_2026_05_20.md` in worktree.
E.2. Write `docs/runbooks/pfizer_backfill_rollback.md` — Level 3 restore from snapshot.
E.3. Add `RELEASE_CHECKLIST.md` entry: "Drop `backfill_pfizer_pre_*` snapshot tables after ship".

### Phase F — Dry-run + commit (1.5 hr active)

F.1. `py scripts/maintenance/backfill_pfizer_canonical_corruption.py --bundled` (preview-only) — review CSV, collision count, ID-conflict skip count.
F.2. `py scripts/maintenance/check_critical_mvs.py` — re-verify 3 critical MVs.
F.3. `py scripts/maintenance/backfill_pfizer_canonical_corruption.py --bundled --commit` — applies migration.
F.4. `py scripts/maintenance/check_critical_mvs.py` again — confirm MVs survived (per napkin 2026-05-12 5th recurrence).
F.5. `py scripts/scoring/refresh_all.py --skip-gower` — fast MV rebuild (~30 min).
F.6. Smoke API tests (see Verification §B).
F.7. Overnight: `py scripts/scoring/compute_gower_similarity.py` then `py scripts/scoring/refresh_all.py`. **DO NOT** invoke `compute_gower_similarity.py --dry-run` (napkin: destructive, drops `employer_comparables`).

---

## Verification

### Verification ladder (inside txn, pre-commit — all must pass)

| # | Check | SQL |
|---|---|---|
| V1 | Corruption regex returns 0 in master_employers | `SELECT COUNT(*) FROM master_employers WHERE canonical_name ~ '(?<![c])oration$\|(?<![p])mpany$\|(?<![c])orporated$'` → 0 |
| V2 | Corruption regex returns 0 in mergent_employers | Same against `company_name_normalized` → 0 |
| V3 | Loser FK orphans = 0 | For each table in `REPOINT_TARGETS`: `SELECT COUNT(*) FROM <t> LEFT JOIN master_employers m USING (master_id) WHERE m.master_id IS NULL AND <t>.master_id IS NOT NULL` → 0 |
| V4 | master_employers row-count delta = expected | Count of `_winner_map` rows = pre-txn rowcount minus post-txn rowcount |
| V5 | merge_log row-count delta = expected | `SELECT COUNT(*) FROM master_employer_merge_log WHERE merge_phase='pfizer_bundled' AND merged_at >= <txn_start>` = distinct loser count |
| V6 | Audit row inserted | Migration-audit table has row with `migration_name='pfizer_bundled_2026_05_20'` and `completed_at IS NOT NULL` |

Any failure → `conn.rollback()` + exit code 4.

### Post-commit smoke (separate process)

| # | Check | Command |
|---|---|---|
| B1 | MVs survived | `py scripts/maintenance/check_critical_mvs.py` exits 0 |
| B2 | Pfizer canonical fixed | `curl /api/employers/unified-search?name=pfizer` returns row with `canonical_name='pfizer products'` (not `'pfizer productsoration'`) |
| B3 | Kroger canonical fixed | Same for `kroger` → `'kroger'` (not `'krogermpany'`) |
| B4 | Director re-point worked | Pick 3 random masters from `master_employer_merge_log WHERE merge_phase='pfizer_bundled'`, confirm `winner_master_id` has director count > 0 |
| B5 | mv_employer_search row count dropped | By the count of distinct losers DELETEd |
| B6 | Audit table query | `SELECT * FROM master_employer_merge_log WHERE merge_phase='pfizer_bundled' AND merged_at >= <commit_ts>` matches verification-ladder V5 count |

### Acceptance criteria (binary, all required before `--commit`)

- A1: `pytest tests/` exits 0 (unit suite)
- A2: `LABOR_TEST_DB=... pytest tests/ -m integration` exits 0
- A3: Refactor smoke (`dedup_master_employers.py --dry-run --phase 2 --limit 100`) matches pre-refactor stash output
- A4: `py scripts/maintenance/backfill_pfizer_canonical_corruption.py --bundled` (no `--commit`) exits 0 + prints expected collision count
- A5: `py scripts/maintenance/check_critical_mvs.py` exits 0
- A6: PR diff review confirms changes confined to the files in Critical Files table

---

## Rollback story

**Level 1 (free):** Postgres `ROLLBACK`. Any in-txn failure (verification, validation, exception) returns DB to pre-script state.

**Level 2 (cheap):** Pre-commit snapshot tables `backfill_pfizer_pre_<TS>`, `..._mergent_pre_<TS>`, `..._source_ids_pre_<TS>`. Created inside txn (drop on rollback, persist on commit). Retention: drop after next `/ship` cycle.

**Level 3 (worst case):** Restore-from-snapshot runbook at `docs/runbooks/pfizer_backfill_rollback.md`. Not single-button (merge_log entries stay, employer_directors stay re-pointed) but restores master row state.

Downstream-consumer redirect pattern: anything joining on the now-deleted loser_master_id can `LEFT JOIN master_employer_merge_log mml ON mml.loser_master_id = <old_id>` to find the new master.

---

## Open follow-ups (post-launch)

1. The DBA-pattern bug (`_remove_dba_tail`) affected 618 masters total but only 1 was in today's actionable set. The other 617 are now safe on future Mergent reloads (because the upstream fix is in place), but their current canonical_name may already be wrong. Consider a follow-up sweep.

2. `check_canonical_name_health.py` (mentioned in design doc, not yet built) — CI guard that fails if corruption regex finds >10 rows. Catches the next normalization bug before it sediments. Easy add post-launch.

3. The 2 `display_name='COMPANY'` junk masters (7412256, 7412257) are skipped by the migration. Separate ticket to delete or quarantine them.

4. Post-commit, ~unknown small number of pairs will be in `_pfizer_skipped_id_conflicts` (ID-conflict skips). Manual review required to decide merge-or-not per pair. Persist this table similarly to the snapshot tables.

---

## Risks (consolidated)

| # | Risk | Severity | Mitigation |
|---|---|---|---|
| R1 | FK enumeration incomplete (missed table → dangling refs) | HIGH | Mandatory pre-impl SQL introspection (§Phase B.2); `bulk_repoint` skips missing tables; V3 verification catches declared-FK orphans |
| R2 | `merge_one()` per-pair too slow (10,690 × 50ms = ~9 min) | LOW | Observed 500/sec from `apply_rule_merges.py` → ~22s actual; bump statement_timeout to 30 min anyway |
| R3 | Winner selection differs from production dedup | MED | Mirror line-444 `has_f7 AND has_f7` skip rule; add `test_two_f7_rows_not_merged` |
| R4 | Snapshot tables clutter schema | LOW | Single-rule retention: drop after next `/ship`; documented in `RELEASE_CHECKLIST.md` |
| R5 | MV refresh during business hours | LOW | `REFRESH MATERIALIZED VIEW CONCURRENTLY`; schedule for off-hours |
| R6 | Late-arriving downstream consumer breaks days later | MED | Snapshot + restore runbook + merge_log redirect pattern |
| R7 | `compute_gower_similarity.py --dry-run` is destructive | HIGH if confused | Plan explicitly says run WITHOUT `--dry-run`; napkin entry already documents this |
| R8 | Strong-identifier conflict silently overrides downstream consumer expectations | MED | Skip-on-conflict policy + `_pfizer_skipped_id_conflicts` audit table for manual review |
| R9 | Concurrent migration runs corrupt state | LOW | Advisory lock (Phase C.6) |
| R10 | Row state changed between preview CSV and commit | LOW | Checksum verification (`_verify_checksum_unchanged`) aborts if affected rowset shifted |

---

## Estimated effort

| Phase | Description | Effort |
|---|---|---|
| A | Library extraction + `apply_*` refactor | 1.5 hr |
| B | `bulk_repoint()` + tests | 1 hr |
| C | Bundled mode + verification ladder | 3.5 hr |
| D | Test plan implementation | 2 hr |
| E | Documentation | 0.5 hr |
| F | Dry-run + commit + MV refresh + smoke | 1.5 hr active (+~4 hr overnight Gower) |
| **Total dev** | | **~9 hr** |
| **Wall clock** | (incl. overnight Gower) | **~13 hr** |

Single developer; phases A → B → C → D → F are sequential; E can happen anywhere.

---

## Where I'm most likely to mess this up

Per Codex: **chained groups**. The existing pairwise merge CLI thinks in pairs; this migration is really group dedup after canonical normalization. Pick one terminal winner per collision group, merge all losers directly into it, make the merge log reflect that final winner. This is the core design constraint I will not compromise. Star topology enforced in `_pick_winners_for_groups()` and validated by `validate_merge_map()`.

Second-most-likely error: a missed FK target in `REPOINT_TARGETS`. Mitigation is the mandatory pre-impl introspection step in Phase B.2 — the FK list in the plan is a starting point, not the final authority.
