# I2 - Why Comparables -> Similarity Produces Only 186 Scores

Date: 2026-02-23  
DB: `olms_multiyear` (`postgres`)

## Question
Why does the `employer_comparables -> score_similarity` path produce only 186 non-null scores?

## Confirmed Findings
1. Bridge mismatch between F7 and Mergent IDs:
- `mv_employer_data_sources` rows: `146,863`
- Name+state bridge matches into `mv_employer_features`: `833`
- Query logic: `LOWER(TRIM(eds.employer_name)) + state` joined to `mv_employer_features`
- `mv_employer_features.employer_id` is Mergent integer ID space; `mv_employer_data_sources.employer_id` is hex F7 ID space.

2. Proximity gate suppresses all similarity candidates:
- `score_union_proximity` distribution: `NULL=78,036`, `5=16,462`, `10=52,365`
- Gate in `build_unified_scorecard.py`:
  - `WHEN rs.score_union_proximity >= 5 THEN NULL`
- Result: no rows pass with `<5`; candidates are blocked.

3. End-to-end outcome:
- `mv_unified_scorecard` total rows: `146,863`
- `score_similarity IS NOT NULL`: `186`

## Additional Validation (Direct ID Mapping)
- Using direct crosswalk (`corporate_identifier_crosswalk.f7_employer_id -> mergent_duns -> mergent_employers.id`):
  - F7 rows with Mergent DUNS mapping: `1,045`
  - Those with comparables present: `347`
- Even with direct ID mapping, current proximity gate still blocks all mapped rows from scoring.

## Root Cause Summary
- The known answer is correct:
  1. Weak name+state bridge creates tiny overlap (`833/146,863`).
  2. `score_union_proximity >= 5` gate nulls similarity in practice because proximity is only `5` or `10` when non-null.

## Proposed Fix
1. Replace name+state bridge with direct ID bridge:
- Add `feature_employer_id` to `corporate_identifier_crosswalk` or build a stable bridge view:
  - `f7_employer_id -> mergent_duns -> mergent_employers.id (= mv_employer_features.employer_id)`
2. Remove/invert proximity gate:
- Current gate suppresses similarity exactly where proximity exists.
- Options:
  - Allow coexistence of proximity + similarity.
  - Or downweight one factor rather than nulling similarity.
3. Recompute similarity coverage after both changes and compare distribution.

