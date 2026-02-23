# I12 - Duplicate Active Match Audit

Date: 2026-02-23  
DB: `olms_multiyear` (`postgres`)

## Scope
Check whether one source record is actively matched to multiple F7 targets.

## SQL Used
```sql
SELECT source_system, source_id, COUNT(DISTINCT target_id) AS target_count
FROM unified_match_log
WHERE status = 'active'
GROUP BY source_system, source_id
HAVING COUNT(DISTINCT target_id) > 1
ORDER BY target_count DESC
LIMIT 20;

-- Summary
WITH d AS (
  SELECT source_system, source_id, COUNT(DISTINCT target_id) AS tc
  FROM unified_match_log
  WHERE status='active'
  GROUP BY source_system, source_id
  HAVING COUNT(DISTINCT target_id) > 1
)
SELECT COUNT(*) AS dup_keys, MAX(tc) AS max_targets, AVG(tc) AS avg_targets
FROM d;

-- Method-set root cause view
WITH d AS (
  SELECT source_system, source_id
  FROM unified_match_log
  WHERE status='active'
  GROUP BY source_system, source_id
  HAVING COUNT(DISTINCT target_id) > 1
),
methods AS (
  SELECT u.source_system, u.source_id,
         string_agg(DISTINCT u.match_method, ',' ORDER BY u.match_method) AS method_set,
         COUNT(DISTINCT u.target_id) AS target_count
  FROM unified_match_log u
  JOIN d ON d.source_system=u.source_system AND d.source_id=u.source_id
  WHERE u.status='active'
  GROUP BY u.source_system, u.source_id
)
SELECT source_system, method_set, COUNT(*) AS dup_keys, MAX(target_count) AS max_targets
FROM methods
GROUP BY source_system, method_set
ORDER BY dup_keys DESC;
```

## Findings
- Duplicate active source keys (`source_system`,`source_id`) with >1 target: `70`
- Max distinct targets per key: `3`
- Average targets among duplicate keys: `2.04`

By source:
- `gleif`: `29`
- `sec`: `19`
- `990`: `15`
- `osha`: `7`

Dominant method-set patterns:
- `gleif`: `NAME_STATE,SPLINK_PROB` (and some `NAME_STATE`-only duplicates)
- `sec`: `FUZZY_TRIGRAM` duplicates
- `990`: `FUZZY_TRIGRAM` duplicates
- `osha`: mixed `FUZZY_SPLINK_ADAPTIVE,FUZZY_TRIGRAM`

## Root Cause Assessment
Best-match-wins is not consistently enforced across all active rows in `unified_match_log`:
- Cross-method collisions still active for the same source key (not superseded to one winner).
- Some single-method duplicates (especially trigram in `990`/`sec`) indicate multiple active targets were inserted for one source record.
- Several duplicate targets are near-duplicate F7 entities (same organization represented by multiple F7 IDs), which amplifies duplicate active matches.

## Recommendation
1. Add a post-run dedupe pass for active UML rows:
   - keep highest-confidence winner per `(source_system, source_id)`
   - mark all others `superseded`.
2. Add/verify write-time guardrails:
   - unique active winner semantics per source key.
3. For source systems with many duplicates (`gleif`, `sec`, `990`), run targeted reconciliation first.

