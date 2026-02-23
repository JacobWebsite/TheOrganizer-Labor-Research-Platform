# I1 - NLRB Proximity Scoring and Junk Participant Data

Date: 2026-02-23  
DB: `olms_multiyear` (`postgres`)

## Question
Does NLRB "within 25 miles" proximity scoring use junk participant data?

## Code Path Trace
- `scripts/scoring/build_unified_scorecard.py` is the Phase 1 scorecard path.
- In that script, `score_union_proximity` is computed from:
  - `f7_employers_deduped.canonical_group_id`
  - `employer_canonical_groups.member_count`
  - `mv_employer_data_sources.corporate_family_id`
- NLRB participant data is only used for `score_nlrb` and `has_nlrb`, not for proximity:
  - `nlrb_participants` -> `nlrb_agg` -> `score_nlrb`
  - `build_employer_data_sources.py` builds `has_nlrb` from `nlrb_participants`
- Explicit comment in `build_unified_scorecard.py`:
  - `TODO: nearby 25-mile momentum requires geocoded employer locations. Keep current own-history model.`

## Finding
- There is no implemented "within 25 miles" proximity algorithm in current Phase 1 scoring code.
- Therefore, junk `nlrb_participants` rows are not currently feeding a 25-mile proximity factor.

## Risk Note
- If a 25-mile feature is later introduced, it must not source directly from unvetted participant rows.
- Use geocoded, canonicalized employer entities with strict ID linkage and confidence floors.

