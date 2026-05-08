# 2026-04-30 — Beta Hardening + 24Q EPA + FEC

Multi-package marathon: Plan A+B (M-1/M-2 + Plan B doc sweep) + Pkg 1 (Beta Hardening) + Pkg 2 (EPA ECHO Q21) + Pkg 3 (F7 diagnosis + identity guard) + Pkg A 24Q-38 FEC partial.

## Changes Made

### Process debt (M-1, M-2)
- `scripts/maintenance/check_critical_routes.py` + `config/critical_routes.txt` (13 routes) + `RELEASE_CHECKLIST.md` — diffs `/openapi.json` against manifest
- `scripts/maintenance/check_critical_mvs.py` + `config/critical_mvs.txt` (6 MVs with row-count floors) — would have caught today's regression
- `api/services/demographics_bounds.py` + `tests/test_demographics_bounds.py` (16 tests) — wired into demographics.py (3 endpoints) + profile.py (workforce-profile)

### Critical regression discovered + fixed
- `mv_target_scorecard` MISSING from DB (5,382,051 rows R7-verified 2026-04-25). API returning 503 on all `/api/targets/scorecard*`. Rebuilt in 225s — exact row-count match (no data loss; underlying tables intact)
- Patched `api/routers/target_scorecard.py:_check_mv` to cache only positive results (previously cached on False → required process restart to recover from MV drop+rebuild)

### Plan B doc sweep
- `CLAUDE.md`: tier counts (off 5x), crosswalk count (28K → 39,827), Priority count (~2,891 → 1,052), test counts (1,316 → 1,411), MV chain note for MISSING mv_target_scorecard
- `.claude/agents/scoring.md`: D12 sub-factor weights table, dynamic-denominator formula, current tier distribution, P1 #38 gate change
- `.claude/agents/matching.md`: V2 12-tier cascade (was 6-tier), 0.90 floors (was 0.80/0.75), V2 per-method FP rates
- `Systems/Scoring System.md`, `Systems/Matching Pipeline.md`: live counts re-verified
- `.claude/specs/`: `scoring-system.md`, `unified-scorecard-guide.md`, `roadmap.md` — D11/D12/D13 marked CLOSED, formula updated to dynamic-denominator

### Package 1: Beta Hardening
- `scripts/maintenance/deactivate_phonetic_state.py` — superseded 7,671 PHONETIC_STATE matches (90% FP per R7), 2,353 distinct F7s affected, _RESOLVED variants left intact
- `scripts/scoring/rebuild_search_mv.py` modified — DISTINCT ON dropped election_date, NLRB rows 86,153 → 55,531 (-36%); Starbucks 183 → 86
- `frontend/src/shared/components/SourceFreshnessFooter.jsx` (new) wired into OshaSection/NlrbSection/WhdCard — displays source-level "data refreshed through {date}" when employer has no records

### Package 2: EPA ECHO Q21 (24Q-29 + 24Q-30)
- `scripts/etl/load_epa_echo.py` — 3,090,831 facilities loaded in 211s (index-deferred pattern; first attempt with index-during-insert was 30x slower and killed)
- `scripts/etl/seed_master_epa_echo.py` — updated TWO CHECK constraints (chk_master_source_system + chk_master_source_origin); 286,284 source links across 253,034 distinct masters; 209,022 new master rows
- `scripts/maintenance/verify_epa_echo_signal.py` — top match Cummins Inc Indianapolis $1.67B penalty
- Refreshed `mv_target_data_sources` (+209K) and rebuilt `mv_target_scorecard` (still 5,382,051 rows — new EPA-only masters intentionally excluded due to data_quality_score=35 below scorecard threshold)
- New vault note `Data Sources/Enforcement and Workplace Conditions/EPA ECHO.md`

### Package 3: Diagnose + Patch
- F7 orphan rate diagnosis: 100,005 of 146,863 (68.1%) have zero active UML matches. Root cause = Splink retirement (FUZZY_SPLINK_ADAPTIVE 36,957 superseded, replacement FUZZY_INMEMORY_TRIGRAM only 7,959 active, net loss ~26K F7s). Today's PHONETIC removal contributed only 955 newly orphaned (~2.3%). Wrote `Open Problems/F7 Orphan Rate Regression.md`
- R7-16 identity-grafting guard already shipped 2026-04-27 (composite 3-strategy fuzzy at lines 4685-4730 of tools.py). Today added complementary alias-collision layer using `config/employer_aliases.json` exclude_terms. Catches Cleveland Clinic → Cleveland-Cliffs (partial=83 slips fuzzy guard) and NYC Hospitals → NYU Langone. New `tests/test_company_enrich_guard.py` 13/13 pass

### Package A 24Q-P0: FEC partial (24Q-38)
- `scripts/etl/load_fec.py` — 4-file loader for 2023-24 cycle. Loaded 3 of 4: fec_committees (20,941), fec_candidates (9,804), fec_committee_contributions (703,597). indiv24.zip deferred (4+ GB compressed)
- `scripts/etl/seed_master_fec.py` — chk_master_source_system updated for 'fec'. **116 corporate PACs matched to 115 masters** (99 strict state + 17 loose state). Sample matches: Abbott Labs, Amedisys, Alliance for Automotive Innovation
- New vault notes: `Data Sources/Federal Contracting and Tax/FEC Campaign Finance.md`, `Open Problems/FEC indiv24 Load Deferred.md`, `Open Problems/LDA Lobbying ETL Not Yet Built.md`

## Key Findings

- **mv_target_scorecard regression went silent for 5 days.** Was 5.38M on 2026-04-25, missing on 2026-04-30. No alert fired because no MV-presence check existed. Now fixed (`check_critical_mvs.py`).
- **F7 orphan regression direction (worse) is consistent: 64.7% R6 → 67.4% R7 → 68.1% today.** Root cause = Splink retirement, NOT today's PHONETIC removal (which added only 955 orphans).
- **EPA ECHO file is bigger than docs claimed**: 3.09M facilities vs documented 1.5M.
- **FEC indiv24.zip 2024 cycle is 4+ GB** compressed (much bigger than 2022 cycle ~1 GB). Bulk approach needs adjustment for current cycles.
- **Index-deferred pattern saves ~30x on bulk loads.** EPA ECHO went from killed-at-6-min-and-going to 211 seconds total.
- **The formatter (likely ruff with auto-remove-unused) will strip top-level imports between separate Edits.** Workaround: combine import + use in single edit, OR use local import at call site (the pattern profile.py:1697 already uses for demographics_v5).
- **Windows zombie-socket pattern recurred 4th time in 5 days.** :8001 has 2 dead PIDs holding LISTENING. Fresh uvicorn forced to :8002. Frontend Vite proxy mismatch blocks live UI verification until reboot.

## Roadmap Updates

**Closed:**
- M-1 process-debt route check
- M-2 process-debt demographics asserts
- P0 #18 PHONETIC_STATE deactivation (was R7-PARTIAL)
- P1 #28 freshness labels (SourceFreshnessFooter)
- P1 #43 NLRB dedupe
- 24Q-29 EPA ECHO bulk ETL
- 24Q-30 EPA ECHO matching to master
- 24Q-38 FEC PAC matching (partial — indiv contributions deferred)

**Resolved:** mv_target_scorecard regression (rebuilt + self-heal patch)

**Opened:** F7 Orphan Rate Regression, FEC indiv24 Load Deferred, LDA Lobbying ETL Not Yet Built

**Still pending:**
- 24Q-9/10 SEC 13F Stockholders
- 24Q-12/13/14 DEF14A directors + interlocks
- 24Q-31 EnvironmentalCard frontend (1-2 hrs; surfaces today's EPA work)
- 24Q-39 LDA (deferred)
- 24Q-40 NIMSP state political giving
- 24Q-41 Political activity card UI
- 24Q-42 Restructure dossier to 24-Q
- REG-2/3/7 (Jacob admin)

## Debugging Notes

- **CHECK constraints come in pairs.** Adding a new source_system requires updating both `master_employer_source_ids.chk_master_source_system` AND `master_employers.chk_master_source_origin`. First pass on EPA seed only updated source_system → seed crashed on `chk_master_source_origin`.
- **Index-deferred is the correct pattern for bulk load > 100K rows.** Always create indexes AFTER COPY/INSERT, especially GIN trigram indexes which are very expensive per-row.
- **The `_MV_EXISTS` cache pattern needs negative-only-cache logic.** target_scorecard.py originally cached `False` indefinitely; that meant the API needed restart after MV rebuild. Patched to only cache `True`. Apply this pattern to other MV-existence checks if any.
- **Windows + bash quoting drops nested double quotes silently.** `Bash` tool calls with paths containing spaces inside `"..."` need careful escaping or use of forward slashes. Found via "ls" command failing with `unexpected EOF` errors.

## Test Status

- `tests/test_demographics_bounds.py` — 16/16 pass
- `tests/test_company_enrich_guard.py` — 13/13 pass
- `frontend/__tests__/ProfileCards.test.jsx` — 14/14 pass
- All 6 critical MVs green via `check_critical_mvs.py`
- All 13 critical routes green via `check_critical_routes.py`
- Pre-existing: `tests/test_api.py::test_data_freshness_endpoint` returns 403 vs expected 503 (auth middleware, unrelated to this session)

## Files Modified (summary)

| Layer | Count | New/Modified |
|---|---:|---|
| Backend Python | 14 | 8 new, 6 modified |
| Backend tests | 2 | both new (29 tests total) |
| Backend config | 3 | all new |
| Frontend | 4 | 1 new, 3 modified |
| Vault notes | 14 | 6 new, 8 modified |
| Project root docs | 1 | RELEASE_CHECKLIST.md (new) |
| **Total** | **38** | **24 new, 17 modified** |
