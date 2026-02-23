# I11 - Trigram Quality Audit (`FUZZY_TRIGRAM`)

Date: 2026-02-23  
DB: `olms_multiyear` (`postgres`)

## Scope
Audit active `FUZZY_TRIGRAM` matches and recommend a similarity floor.

## SQL Used
```sql
-- Requested top-50 sample
SELECT source_system, source_id, target_id AS f7_employer_id,
       evidence->>'source_name' AS src,
       evidence->>'target_name' AS tgt,
       (evidence->>'similarity')::float AS sim
FROM unified_match_log
WHERE status = 'active' AND match_method = 'FUZZY_TRIGRAM'
ORDER BY (evidence->>'similarity')::float DESC
LIMIT 50;

-- Distribution
SELECT
  COUNT(*) AS n,
  MIN((evidence->>'similarity')::float) AS min_sim,
  PERCENTILE_CONT(0.25) WITHIN GROUP (ORDER BY (evidence->>'similarity')::float) AS p25,
  PERCENTILE_CONT(0.50) WITHIN GROUP (ORDER BY (evidence->>'similarity')::float) AS p50,
  PERCENTILE_CONT(0.75) WITHIN GROUP (ORDER BY (evidence->>'similarity')::float) AS p75,
  PERCENTILE_CONT(0.90) WITHIN GROUP (ORDER BY (evidence->>'similarity')::float) AS p90,
  MAX((evidence->>'similarity')::float) AS max_sim
FROM unified_match_log
WHERE status='active' AND match_method='FUZZY_TRIGRAM';

-- Volume retained at candidate floors
SELECT COUNT(*) FROM unified_match_log
WHERE status='active' AND match_method='FUZZY_TRIGRAM'
  AND (evidence->>'similarity')::float >= 0.75;
```

## Findings
- Active trigram matches now: `15,615` (not `15,242` in prompt).
- Similarity distribution:
  - min: `0.700`
  - p25: `0.714`
  - p50: `0.737`
  - p75: `0.778`
  - p90: `0.826`
  - max: `1.000`

### Top-50 by similarity (requested query)
- All 50 had `sim = 1.0`
- These looked high-quality (mostly token-order/municipal-wording variants).

### Low-tail quality check (bottom 50 by similarity, all at `sim = 0.70`)
- Approx qualitative split:
  - good: `18`
  - borderline: `26`
  - obvious bad: `6`
- Common bad patterns:
  - short acronym collisions (`TW Services` vs `TK&K Services`)
  - generic construction collisions (`... Construction` vs other construction entity)
  - semantically different names with similar tokens.

### Mid-tail spot check (`sim 0.74-0.76`, sample 50)
- good: `29`
- borderline: `20`
- bad: `1`

## Recommendation
- Effective floor is already `0.70` in current active data (no active rows below).
- Raise trigram similarity floor to **`0.75`** to remove most obvious false positives from the low tail.
  - Retained at `>= 0.75`: `6,618 / 15,615` (~42.4%).
- If recall loss is too high, compromise floor `0.74` can be tested, but `0.75` is the cleaner quality boundary based on sampled errors.

