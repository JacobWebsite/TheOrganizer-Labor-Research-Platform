# Phase 3 Normalization Integration Checklist

Goal: adopt canonical normalization from `src/python/matching/name_normalization.py` across match pipelines.

## Canonical APIs
- `normalize_name_standard(name)`
- `normalize_name_aggressive(name)`
- `normalize_name_fuzzy(name)`
- Optional helper bundle: `src/python/matching/integration_stubs.py`

## Integration Targets (first pass)
- `scripts/matching/f7_comprehensive_match.py`
- `scripts/matching/match_f7_to_lm.py`
- `scripts/matching/nlrb_crosswalk_matching.py`
- `scripts/etl/unified_employer_osha_pipeline.py`
- `scripts/etl/osha_fuzzy_match.py`
- `scripts/etl/osha_match_improvement.py`
- `src/python/nlrb/load_nlrb_data.py` (if name cleanup occurs there)

## Implementation Steps
1. Replace ad-hoc lowercase/punctuation stripping with `normalize_name_standard`.
2. Route deterministic fallback passes to `normalize_name_aggressive`.
3. Route trigram/Splink/fuzzy passes to `normalize_name_fuzzy`.
4. Keep old and new values side-by-side in logs during rollout.
5. Add run-level metadata (`normalization_version`) to output artifacts.
6. Run before/after quality checks: precision, recall, unresolved rate.

## Guardrails
- Do not change matching thresholds in same commit as normalization migration.
- Keep geographic constraints unchanged in migration commits.
- Preserve raw input names for auditability.

## Verification
- Unit tests: `tests/test_name_normalization.py`
- Add per-pipeline smoke tests after wiring.
- Track weekly unresolved counts and false positive review samples.

