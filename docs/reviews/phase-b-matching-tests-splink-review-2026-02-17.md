# Phase B Matching Pipeline Review (2026-02-17)

## Scope
Fixes for deterministic matching pipeline:
- B1: first-hit-wins -> best-match-wins
- B2: name collisions no longer silently dropped
- B3: fuzzy tier moved from trigram-only to Splink-first (multi-field probabilistic)

## Files changed
- `scripts/matching/deterministic_matcher.py`
- `scripts/matching/splink_config.py`
- `tests/test_matching_pipeline.py`

## Part 1: Tests added (`tests/test_matching_pipeline.py`)
The new tests verify:
1. Tier specificity precedence: `name+city+state` beats `name+state` when both match.
2. Collision retention: two F7 employers with same normalized `name+state` remain reachable in indexes.
3. Ambiguity behavior: multi-candidate matches are flagged (`AMBIGUOUS_*`) instead of silently resolved.
4. Match tier ordering: EIN > name+city+state > name+state > aggressive+state > fuzzy.
5. Regression guard: OSHA match rate baseline remains >= 13%.
6. Confidence band thresholds: HIGH >= 0.85, MEDIUM >= 0.70, LOW < 0.70.

## Part 2: Splink integration into fuzzy tier
### Deterministic matcher updates (`scripts/matching/deterministic_matcher.py`)
- `_fuzzy_batch()` now uses Splink-first with fallback to trigram.
- Added `_fuzzy_batch_splink()`:
  - Uses fields: `name_normalized`, `state`, `city`, `zip`, `naics`, `street_address`.
  - Loads a pre-trained model from `adaptive_fuzzy` scenario config.
  - Flags near-tied fuzzy candidates as ambiguous (`AMBIGUOUS_FUZZY_SPLINK`).
- Added `_fuzzy_batch_trigram()` as explicit fallback path.
- Added `_band_for_score()` and standardized confidence assignment to:
  - HIGH >= 0.85
  - MEDIUM >= 0.70
  - LOW < 0.70
- Ambiguous exact-collision handling now returns LOW/rejected with explicit ambiguity evidence (no silent first-candidate selection).

### Splink config updates (`scripts/matching/splink_config.py`)
Added new scenario:
- `adaptive_fuzzy`
  - `ADAPTIVE_FUZZY_SETTINGS`
  - `ADAPTIVE_FUZZY_EM_BLOCKING`
  - `model_path = "scripts/matching/models/adaptive_fuzzy_model.json"`

## Training strategy decision
- Recommended and implemented behavior: use a pre-trained Splink model (loaded at runtime), not per-batch EM training.
- Rationale: avoids wasteful/unstable retraining on tiny 200-record batches.
- Fallback behavior: if model/config/deps are unavailable, automatically fallback to trigram fuzzy.

## Validation run
- `python -m pytest tests/test_matching_pipeline.py -q` -> 6 passed
- `python -m pytest tests/test_phase3_matching.py -q` -> 17 passed

## Note
Referenced file `scripts/matching/splink_pipeline_v2.py` was not present; implementation aligned with existing `scripts/matching/splink_pipeline.py` and shared Splink config.

## Next action
Generate/export trained model JSON at:
- `scripts/matching/models/adaptive_fuzzy_model.json`
so deterministic tier-5 uses Splink without falling back to trigram.
