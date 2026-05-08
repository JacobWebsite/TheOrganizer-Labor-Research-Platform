# Session 2026-04-28 — R7-1 Demographics ETL Deep Fix

## Changes Made

Closed R7-1 (BL-BLOCK in MERGED_ROADMAP_2026_04_25). Two phases:

**Phase 1 (initial API-level fix):**
- Patched `_build_demographics` in `api/routers/demographics.py` to use rollup-grain filter for state-fallback path. NY 145M → 4.1M.
- Same fix in `api/routers/profile.py::_get_acs_demographics` and `scripts/research/tools.py::search_acs_workforce`.
- Added `TestPlausibilityBounds` regression guard.

**Phase 2 (deeper ETL root-cause fix, after user flagged universe-mismatch):**
- Found two compounding bugs in `scripts/etl/newsrc_curate_all.py::build_acs()`:
  1. **Sample stacking**: `GROUP BY 1..10` collapsed across IPUMS sample-year dimension. 9 samples (5 1-year + 4 5-year ACS for 2020-2024) summed = 9× inflation. NY single-sample 16M × 9 = 145M.
  2. **Sentinel filter mismatch**: build script's `OCCSOC in {"", "000000", "0000"}` filter never matched the actual single-char `"0"` sentinel, so not-in-LF people leaked into an "all-zeros" rollup row.
- Fixed at curate step: `WHERE sample = '202303' AND indnaics <> '0' AND occsoc <> '0' AND classwkr <> '0'`.
- Sample 202303 = 2023 ACS 5-year (largest, most stable, all insurance vars).
- Rebuilt `cur_acs_workforce_demographics`: 11,478,933 → 6,356,288 rows, ~86 sec via `py scripts/etl/newsrc_curate_all.py --only acs`.
- Reverted Phase 1's API grain filters (no longer needed; cleaned table is uniform leaves).
- Tightened regression test with QCEW-anchored bounds + new age-distribution check.

**Files modified:**
- `scripts/etl/newsrc_curate_all.py` (build_acs source filter)
- `api/routers/demographics.py` (simplified _build_demographics)
- `api/routers/profile.py` (simplified _get_acs_demographics)
- `scripts/research/tools.py` (simplified search_acs_workforce)
- `tests/test_demographics_wiring.py` (TestPlausibilityBounds tightened)

**Vault:**
- `Open Problems/Demographics ACS Total Workers Inconsistent Across Grains.md` — resolved same session.
- `Work Log/2026-04-28 - R7-1 Demographics ETL Deep Fix.md`

## Key Findings

**Ground truth: BLS QCEW 2024 NY = 9,705,821 covered employment.** Post-fix `/api/demographics/NY` = 11,863,969 (ratio 1.22). The ~22% gap is expected (ACS counts self-employed + federal + agricultural, QCEW doesn't). All 5 spot-checked states (NY/CA/TX/FL/IL) land at 1.22-1.28 — consistent with definitional difference, not residual bug.

**Insurance percentages unaffected.** ≤0.1pp drift between 9-sample-stacking and 1-sample because ratios cancel multiplicative bias. The 2026-04-28 morning ACS insurance backfill (TX 80.2%, NY 94.2%) still valid.

**Age distribution now workforce-shaped.** NY 65+ pre-fix = 55.8% (matched ACS B23001 not-in-LF). Post-fix = 10.2%. Matches BLS workforce.

**Industry totals corrected.** NY 6111 (education) 7M → 874K. Matches reality.

**Pattern worth remembering**: API-layer grain filter can hide an underlying ETL bug. Phase 1's "fix" returned a 4.1M number that looked plausible but was actually NY's not-in-LF population × 9 samples. Always validate against an external ground truth (QCEW, ACS B23001 published tables, etc.) before declaring a demographics fix resolved.

## Roadmap Updates

- **R7-1 (BL-BLOCK)**: CLOSED. Demographics state-fallback no longer returns impossible totals; reconciles to QCEW within expected bounds.
- No new items added.

Open R7 items remaining (per merged roadmap): R7-7 search ranking, REG-2/3/4/5/6/7, DISABLE_AUTH flip, PHONETIC_STATE deactivation.

## Debugging Notes

- **IPUMS sample codes**: 6-digit `YYYYNN` where YYYY=year and NN=01 (1-year ACS) or 03 (5-year ACS). Multiple samples in one extract is intentional for trend analysis but must be filtered at curate time, not summed.
- **IPUMS sentinel encoding**: `INDNAICS='0'`, `OCCSOC='0'`, `CLASSWKR='0'` for not-in-labor-force people. Single char, not "0000" or "000000". The build script at `newsrc_build_acs_profiles.py:185` still has the broken filter — left it because the curate-step filter now catches the same rows. Future cleanup: also fix the build-step filter for consistency.
- **CLASSWKR codes** in this dataset: only `'0'` (N/A, dropped), `'1'` (self-employed), `'2'` (wage worker). NY post-fix: 10.7M wage + 1.2M self-employed.
- **Codex CLI still broken** (gpt-5.5 model error) — wrapup crosscheck skipped this session, same as prior 3 sessions.
- **Curate rebuild via `--only` flag**: `py scripts/etl/newsrc_curate_all.py --only acs` rebuilds just the ACS table without touching form5500/ppp/etc. ~86 sec total (drop + create + 3 indexes).
- **Tests**: 67/67 pass in `tests/test_demographics_wiring.py + tests/test_workforce_profile.py + tests/test_research_new_sources.py`.
