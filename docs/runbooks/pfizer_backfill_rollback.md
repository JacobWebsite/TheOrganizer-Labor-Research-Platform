# Pfizer Bundled Back-fill — Rollback Runbook

Last updated: 2026-05-20
Migration script: `scripts/maintenance/backfill_pfizer_canonical_corruption.py --bundled --commit`
Plan: `docs/scratch/pfizer_dedup_bundle_plan_2026_05_20.md`

This runbook covers three levels of rollback for the bundled Pfizer
canonical-name back-fill + dedup migration. Pick the lowest level that
addresses your situation.

## Level 1 — Postgres `ROLLBACK` (free, in-txn)

If the migration script raises an exception mid-run, the script's own
`except` block runs `conn.rollback()` and the DB returns to its
pre-script state. No manual intervention required.

This covers:
- Verification-ladder failure (V1-V6)
- Advisory-lock acquisition failure
- Statement-timeout exceeded
- Any other RuntimeError raised in `run_bundled()`

**How to confirm Level 1 was clean:**
```sql
-- Pfizer canary: should still be corrupt (canonical = 'pfizer productsoration')
SELECT master_id, canonical_name, display_name
FROM master_employers WHERE master_id = 157650;

-- Corruption count: should match the pre-migration count
SELECT COUNT(*) FROM master_employers
WHERE canonical_name ~ '(?<![c])oration$|(?<![p])mpany$|(?<![c])orporated$';
-- Expected: matches the count from before the migration (~23K).
```

If both queries return the pre-migration state, no further action.

## Level 2 — Snapshot Tables (post-commit safety net)

The bundled migration creates three permanent snapshot tables inside
the transaction:
- `backfill_pfizer_pre_<TS>` — affected master_employers rows
- `backfill_pfizer_source_ids_pre_<TS>` — affected master_employer_source_ids rows
- `backfill_pfizer_mergent_pre_<TS>` — affected mergent_employers rows

These persist on commit, drop on rollback. Locate them via:
```sql
SELECT tablename FROM pg_tables
WHERE schemaname='public' AND tablename LIKE 'backfill_pfizer_%'
ORDER BY tablename DESC;
```

The bundled run logs the table names to stdout under "snapshot:" lines
and to the `maintenance_migration_audit.counts.snapshot_tables` JSON
field.

### Inspect the snapshot

```sql
SELECT COUNT(*) FROM backfill_pfizer_pre_<TS>;             -- pre-state rows
SELECT COUNT(*) FROM backfill_pfizer_source_ids_pre_<TS>;
SELECT COUNT(*) FROM backfill_pfizer_mergent_pre_<TS>;

-- Spot-check a known canary
SELECT master_id, canonical_name, display_name
FROM backfill_pfizer_pre_<TS>
WHERE master_id = 157650;
```

### Retention

Drop after the next `/ship` cycle (when you're confident no downstream
consumer broke):

```sql
DROP TABLE backfill_pfizer_pre_<TS>;
DROP TABLE backfill_pfizer_source_ids_pre_<TS>;
DROP TABLE backfill_pfizer_mergent_pre_<TS>;
```

The RELEASE_CHECKLIST has this step in the post-ship cleanup section.

## Level 3 — Restore from Snapshot (worst-case recovery)

Use Level 3 ONLY if a downstream consumer breaks days after the migration
and reverting the migration is the only path forward. This is NOT a
single-button revert — `merge_log` entries stay, `employer_directors`
stays re-pointed, MVs may need separate handling.

### Step 1: identify the migration

```sql
SELECT migration_name, counts, started_at, completed_at
FROM maintenance_migration_audit
WHERE migration_name LIKE 'pfizer_bundled_%'
ORDER BY completed_at DESC;
```

The `counts` JSON includes `snapshot_tables`, e.g.:
```json
{"snapshot_tables": ["backfill_pfizer_pre_20260520T220000Z",
                     "backfill_pfizer_source_ids_pre_20260520T220000Z",
                     "backfill_pfizer_mergent_pre_20260520T220000Z"], ...}
```

### Step 2: restore master rows

In one transaction:

```sql
BEGIN;
SET statement_timeout = '30min';

-- Re-insert the deleted losers
INSERT INTO master_employers
SELECT * FROM backfill_pfizer_pre_<TS> s
WHERE NOT EXISTS (
    SELECT 1 FROM master_employers m WHERE m.master_id = s.master_id
);

-- Reverse the canonical UPDATEs by joining against the snapshot
UPDATE master_employers m
SET canonical_name = s.canonical_name,
    display_name  = s.display_name,
    city          = s.city,
    state         = s.state,
    zip           = s.zip,
    naics         = s.naics,
    ein           = s.ein,
    employee_count = s.employee_count,
    employee_count_source = s.employee_count_source,
    is_union      = s.is_union,
    is_public     = s.is_public,
    is_federal_contractor = s.is_federal_contractor,
    is_nonprofit  = s.is_nonprofit,
    updated_at    = s.updated_at
FROM backfill_pfizer_pre_<TS> s
WHERE m.master_id = s.master_id;

-- Restore source IDs (idempotent ON CONFLICT)
INSERT INTO master_employer_source_ids
SELECT * FROM backfill_pfizer_source_ids_pre_<TS> s
ON CONFLICT (master_id, source_system, source_id) DO NOTHING;

-- Restore mergent_employers.company_name_normalized
UPDATE mergent_employers e
SET company_name_normalized = s.company_name_normalized
FROM backfill_pfizer_mergent_pre_<TS> s
WHERE e.id = s.id;

COMMIT;
```

### Step 3: handle the merge_log

The `master_employer_merge_log` rows from the bundled migration are
intentional historical record. Decide:

- **Leave them** (recommended): they document that the merge happened
  even though the data state is now reverted. Downstream consumers can
  still trace winner ↔ loser linkage if they need the lineage.

- **Hard-delete them** (NOT recommended without good reason):
```sql
DELETE FROM master_employer_merge_log
WHERE merge_phase = 'pfizer_bundled'
  AND merged_at >= '<migration_start_ts>';
```

### Step 4: handle employer_directors re-points

The `bulk_repoint()` call updated `employer_directors.master_id` from
loser → winner. After restoring the loser via Level 3 Step 2, those
re-pointed director rows now reference the (restored) winner, not the
loser they originally belonged to. This is usually fine because:

1. The original loser was a Pfizer-corruption-victim that the dedup
   correctly merged.
2. Director relationships are a SHARED graph — the restored loser and
   the winner may both share directors anyway.

If you need to reverse the director re-point, you must replay it from
the merge_log rows + the original `employer_directors` state at
migration-start time. There is no snapshot of `employer_directors`
because the table is large; rebuilding the pre-state requires:

```sql
-- For each loser-master_id in master_employer_merge_log
-- that is now restored:
WITH restored AS (
  SELECT loser_master_id, winner_master_id
  FROM master_employer_merge_log mml
  WHERE mml.merge_phase = 'pfizer_bundled'
    AND EXISTS (SELECT 1 FROM master_employers m
                WHERE m.master_id = mml.loser_master_id)
)
-- (... requires custom logic; talk to maintenance owner first ...)
```

In practice: Step 4 is rarely worth doing. Document the imbalance and
move on.

### Step 5: handle other re-pointed tables

Same logic as Step 4 for `employer_wage_outliers`,
`sec_13f_issuer_master_map`, `sec_10k_relationship_links`,
`sec_10k_filings_to_download`, `rule_derived_hierarchy`,
`state_local_contracts_master_matches`, and (purged)
`employer_comparables`.

For `employer_comparables` specifically: the migration DELETEd loser-
side rows. The Gower MV rebuild (`compute_gower_similarity.py`) will
re-populate them from current `master_employers`. After a Level 3
restore, kick off a Gower rebuild to regenerate comparables for the
restored masters.

### Step 6: rebuild MVs

```bash
py scripts/scoring/refresh_all.py --skip-gower      # fast (~30 min)
py scripts/scoring/compute_gower_similarity.py      # ~4 hr (overnight)
# DO NOT pass --dry-run to compute_gower_similarity.py; it DROPs
# employer_comparables. See napkin entry 2026-05-12.
py scripts/scoring/refresh_all.py                   # full final pass
```

## Downstream consumer redirect pattern

Anything joining on a now-DELETEd loser_master_id can use the merge log
to redirect:

```sql
-- Before (broken — loser_master_id no longer exists):
SELECT ... FROM <table> t WHERE t.master_id = <old_id>;

-- After (works through merge_log):
SELECT ... FROM <table> t
JOIN master_employers m ON m.master_id = COALESCE(
    (SELECT mml.winner_master_id
     FROM master_employer_merge_log mml
     WHERE mml.loser_master_id = <old_id>
     ORDER BY mml.merged_at DESC LIMIT 1),
    <old_id>
);
```

This pattern lets downstream code continue to work using historical
master_ids without a full DB-side restore.

## Contact

- Open Problem: `Open Problems/Pfizer Master Canonical Name Corruption.md` (in vault)
- Plan: `docs/scratch/pfizer_dedup_bundle_plan_2026_05_20.md`
- Maintenance owner: Jacob (jakewartel@gmail.com)
