# Session Summary - 2026-02-23 - Phase 2A Enrichment Follow-up

## Scope
Completed three requested workstreams:
1. NAICS keyword inference (`2A.2` extension)
2. Splink disambiguation name-floor hardening + regression test
3. Investigations I11-I14 write-ups

## Changes Made

### 1) NAICS Keyword Inference
- Added: `scripts/etl/infer_naics_keywords.py`
- Behavior:
  - Targets `f7_employers_deduped` rows where `naics IS NULL`
  - Keyword-to-sector mapping across 12 sectors
  - Writes NAICS as `<2-digit>0000` and `naics_source='KEYWORD_INFERRED'`
  - Updates only if exactly one sector category matches
  - Dry-run default, `--commit` persists

Run results:
- NULL NAICS scanned: `18,030`
- Unique sector matches: `2,142`
- Ambiguous (skipped): `57`
- No match: `15,831`
- Committed updates: `2,142`
- Remaining NULL NAICS: `15,888`

### 2) Splink Disambiguation Name Floor
- Updated: `scripts/matching/deterministic_matcher.py`
  - In `_splink_disambiguate()`, name-floor check now explicitly uses Splink normalized fields when present:
    - `name_normalized_l`
    - `name_normalized_r`
  - Falls back to normalized source/target names if those fields are absent
  - Returns `None` when `token_sort_ratio < self.min_name_similarity` (so record stays ambiguous)

- Added test: `tests/test_splink_disambiguate.py`
  - Verifies disambiguation rejects below-floor winner

Test result:
- `python -m pytest -q tests/test_splink_disambiguate.py` -> `1 passed`

### 3) Investigation Reports (I11-I14)
Added:
- `docs/investigations/I11_priority_composition.md`
- `docs/investigations/I12_propensity_model_verification.md`
- `docs/investigations/I13_misclassification_edge_cases.md`
- `docs/investigations/I14_geographic_gaps.md`

Key findings snapshot:
- I11: Priority tier is mostly structural; `86.1%` of Priority has zero OSHA/NLRB/WHD enforcement.
- I12: In this DB, AUC is model-level (`ml_model_versions.test_auc`), not in per-employer scores table.
- I13: `1,843` rows flagged `is_labor_org=TRUE`; keyword-miss check found `0` obvious unflagged union/local/council names.
- I14: Low-count geography concentrated in territories/non-US codes; `WY` is the main potential US coverage gap.

## Files Touched This Session
- `scripts/etl/infer_naics_keywords.py` (new)
- `scripts/matching/deterministic_matcher.py` (updated)
- `tests/test_splink_disambiguate.py` (new)
- `docs/investigations/I11_priority_composition.md` (new)
- `docs/investigations/I12_propensity_model_verification.md` (new)
- `docs/investigations/I13_misclassification_edge_cases.md` (new)
- `docs/investigations/I14_geographic_gaps.md` (new)

