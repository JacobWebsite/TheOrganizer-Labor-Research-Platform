# SCORECARD_SHRINKAGE_INVESTIGATION (2026-02-19)

## Scope
Investigate why `mv_organizing_scorecard` row counts declined across refreshes:
- `200,890 -> 199,414 -> 195,164`

Read-only research only. No MV refreshes and no writes to matching tables.

## Current Counts
- `v_osha_organizing_targets`: `232,110`
- `mv_organizing_scorecard`: `195,164`
- Difference: `36,946`

## Version History Evidence (`score_versions`)
Latest versions show step-down plateaus:
- Versions `8-10`: `200,890`
- Versions `43-44`: `199,414`
- Versions `45-48`: `195,164`

This confirms a real structural drop, not a one-off failed refresh.

## Key View/MV Logic Findings

### 1) `v_osha_organizing_targets` is still large
Definition filters OSHA establishments by:
- `union_status != 'Y'`
- Significant risk signals (`willful > 0` or `repeat > 0` or `serious >= 3` or `fatality > 0`)

Current row count is high (`232,110`), so source OSHA risk-target volume is not collapsing.

### 2) Old MV explicitly excludes F7-matched establishments via legacy table
`mv_organizing_scorecard` definition contains:
- `f7_matches AS (SELECT DISTINCT establishment_id FROM osha_f7_matches)`
- Final filter: `WHERE fm.establishment_id IS NULL`

So **any establishment present in `osha_f7_matches` is removed from old scorecard output**.

### 3) Exclusion pressure from `osha_f7_matches` is large and stale vs active UML
Observed:
- `osha_f7_matches` rows: `175,685`
- Rows in legacy table with no active UML counterpart: `78,543`
- `legacy rows with no active UML counterpart (estab+employer pair)`: `78,543`
- `legacy/UML exact-pair mismatches`: `78,543`

This means the legacy table includes many rows that are no longer active in `unified_match_log`, but still trigger old-MV exclusion.

### 4) Active-only UML exclusion would be much smaller
For establishments in `v_osha_organizing_targets`:
- Excluded by legacy `osha_f7_matches`: `36,946`
- Would be excluded by **active UML only**: `19,669`

So legacy-table-driven exclusion is currently about `17,277` establishments higher than active UML would justify.

### 5) Superseded-without-active churn exists
In OSHA UML establishment-level status:
- Establishments with active rows: `97,142`
- Establishments with superseded rows but no active row: `12,952`

This supports the hypothesis that match reruns/superseding behavior can increase exclusions if legacy tables are not rebuilt from active UML.

## Root-Cause Assessment
Most likely primary causes of shrinkage:
1. **Design behavior**: old MV intentionally excludes F7-matched establishments (`WHERE fm.establishment_id IS NULL`).
2. **Data drift**: exclusion source is `osha_f7_matches` (legacy), not active UML.
3. **Re-run churn**: superseded/obsolete legacy rows remain and continue excluding establishments.

Less likely cause:
- Raw OSHA establishments being removed. Current OSHA base remains at `1,007,217` and risk-target view remains large.

## Practical Implication
Old scorecard row count can shrink over time even without OSHA source data shrinking, if:
- Legacy match tables accumulate stale rows, or
- Re-runs supersede matches but legacy tables are not rebuilt from active UML.

## Recommended Follow-up (no action taken here)
- Run legacy table rebuild from active UML after source re-runs complete.
- Then compare:
  - `COUNT(*) FROM mv_organizing_scorecard`
  - `COUNT(*) FROM v_osha_organizing_targets`
  - Exclusion count driven by active UML vs legacy tables.
- Keep old scorecard labeled as backward-compatibility output only (already true in roadmap/state docs).
