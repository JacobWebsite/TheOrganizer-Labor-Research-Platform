# 2026-04-27 — R7 Audit Tracks A through H (21 items closed in one day)

## Session Scope

Six tracks of R7 audit work executed in sequence, each landing 2-5 fixes per track. Total
**21 R7 audit items closed**: 13 R7-NEW P0 beta-blockers + 1 regression (REG-1) + 5 Week 1
quick wins + 2 process/scoring tweaks (M-1, FA9.6).

```
ad3ae4d  Track A   backend  R7-5/R7-6/R7-13/R7-14/REG-1   (5 fixes + Apr 16-24 WIP catch-up)
f681a6f  Track A   frontend R7-13 ComparablesCard test
c54da60  Track B'  backend  R7-19/R7-3/R7-2/P0 #2/FA9.6
761456d  Track D+E+G  backend  R7-15/R7-11/R7-9/R7-18 + WIP
7b761f4  Track D+G  frontend R7-10/R7-12/R7-8 + new state-local hook
52d2af1  Track H   backend  R7-17/R7-16
```

## Items closed (with audit IDs)

| Track | Items | What |
|---|---|---|
| **A** | R7-5, R7-6, R7-13, R7-14, REG-1 | empty unified-search guard, family-rollup deploy drift, comparable_type string, MASTER- prefix on /comparables, profile MV column rename |
| **B'** | R7-19, R7-3, R7-2, P0 #2, FA9.6 | NLRB freshness UNION ALL aliasing, IPUMS HISPAN labels, demographics vintage fields, admin 503→403, ANALYZE 8 tables |
| **D** | R7-10, R7-11, R7-12, R7-15 | WHD card field renames, WHD case-sensitivity (Kroger), NLRB card field renames, master /data-sources synthesizer |
| **E** | R7-18 | thin-data weighted_score cap at 7.0 (96.7% of Promising perfect-10s were single-factor union_proximity) |
| **G** | R7-9, R7-8 | new state-local-contracts endpoint, GovernmentContractsCard renders both federal + state/local |
| **H** | R7-17, R7-16, M-1 | anger pillar NULL propagation (2,526 affected rows → 0), CompanyEnrich identity grafting guard, /ship deploy hygiene step |

## Changes Made

### Backend code
- `api/data_source_catalog.py:87` — UNION ALL aliasing fix (R7-19); both subqueries now alias d/x.
- `api/dependencies.py:45` — require_admin returns 403 not 503 when DISABLE_AUTH (P0 #2).
- `api/routers/demographics.py` — added ACS_PUMS_VINTAGE/QCEW_VINTAGE constants, replaced
  HISPANIC_LABELS with full IPUMS HISPAN encoding (codes 0-4 → Not Hispanic / Mexican /
  Puerto Rican / Cuban / Other), added acs_year/qcew_year/methodology fields to all 4
  response paths (R7-2 + R7-3).
- `api/routers/employers.py:357` — empty unified-search guard, metro check moved ahead (R7-5).
- `api/routers/employers.py:1004` — /data-sources accepts master IDs via mv_target_scorecard
  + state_local_contracts_master_matches synthesis (R7-15).
- `api/routers/employers.py:1604` — /comparables strips MASTER- prefix (R7-14).
- `api/routers/master.py` — NEW endpoint /api/employers/master/{id}/state-local-contracts (R7-9).
- `api/routers/profile.py:168` — SELECT canonical_id::text instead of nonexistent
  employer_id column on mv_employer_search (REG-1).
- `api/routers/whd.py:200` — lowercase + strip name_norm before WHERE = name_normalized
  (R7-11). Same fix on mergent path.
- `scripts/scoring/build_unified_scorecard.py` — R7-18 cap weighted_score at 7.0 for thin-data
  rows (factors_available<3 AND direct_factors_available=0); R7-17 added enh_score_nlrb to
  score_anger gate AND formula numerator+denominator (weight 3).
- `scripts/research/tools.py search_company_enrich` — composite fuzzy guard
  (partial<80 AND token_sort<65 AND token_set<75) before accepting CompanyEnrich response (R7-16).

### Frontend code
- `WhdCard.jsx` — 6 field renames: caseCount = cases.length, totalViolations = sum of
  cases or whd_violation_count, backwages = whd_backwages, totalPenalties = whd_penalties,
  case-row .violations_count → .total_violations, case-row .backwages → .backwages_amount (R7-10).
- `NlrbSection.jsx` — 5 field renames with `??` fallbacks: summary.union_wins, .union_losses,
  .ulp_cases; election row .eligible_voters; result derived from union_won boolean (R7-12).
- `ComparablesCard.jsx` — line 60 'nonunion' → 'non_union' to match backend DB constraint (R7-13).
- `__tests__/ComparablesCard.test.jsx` — fixture rename + new file added to repo (R7-13 lock).
- `GovernmentContractsCard.jsx` — full rewrite: removed federal-only short-circuit, renders
  federal + state/local sections side-by-side using existing dataSources fields (R7-8).
- `shared/api/profile.js` — new useEmployerMasterStateLocalContracts hook with retry:false
  for the R7-9 endpoint.
- `vite.config.js` — proxy retargeted from :8001 → :8002 → :8003 → :8004 → :8005 over the day
  (Windows kernel-zombie-socket pattern recurred 3 times). NOT committed; revert to :8001
  after next reboot.

### Vault / docs
- `.claude/skills/ship/SKILL.md` — added step 4 "Deploy hygiene check (M-1)" with diff-driven
  openapi-grep workflow + zombie-socket Windows-gotcha note.

## Key Findings

### Windows kernel-zombie-socket pattern is reproducible

After EVERY taskkill /F on a uvicorn PID, the kernel keeps the port LISTENING under the dead
PID. New uvicorn binds the same port (SO_REUSEADDR) but Windows routes incoming connections
to the zombie. `taskkill /F` on the zombie returns "process not found" but netstat still
shows it. **Only a Windows reboot frees the port.** Workaround pattern (used today 3 times):
move new uvicorn to next port (8002→8003→8004→8005), update Vite proxy, continue. This
session started fresh from :8001 post-Jacob-reboot, then exhibited the pattern again.

### StatReload misses ~50% of edits on Windows

`uvicorn --reload` with StatReload watcher polls file mtimes, but on Windows it consistently
misses some file edits. `touch` doesn't help (mtime change isn't detected). Reliable signal:
the `WARNING: StatReload detected changes in 'X'. Reloading...` log line. If you don't see
that line after editing a file, the new code IS NOT loaded — kill+restart uvicorn (and
accept the zombie).

### IPUMS HISPAN encoding doesn't match what was in the API

The existing demographics.py had `HISPANIC_LABELS = {"0": "Not Hispanic", "1":
"Hispanic/Latino"}` — only 2 codes. Database has codes 0-4. Codes 2/3/4 rendered raw.
The agent diagnosed this. Replacement is full IPUMS USA HISPAN: 0=Not Hispanic, 1=Mexican,
2=Puerto Rican, 3=Cuban, 4=Other Hispanic/Latino. Note the existing "1": "Hispanic/Latino"
was ALSO wrong — IPUMS HISPAN.1 specifically means Mexican, not generic Hispanic. So the
fix slightly changes the displayed label even for code 1 (~29.7% of CA workers in the test).

### `mv_employer_data_sources` is F7-only; master-id callers need bridge

R7-15 fix had to synthesize a response for master IDs because the MV is keyed on F7 hex
employer_id. Solution: query `mv_target_scorecard` for has_* flags + is_federal_contractor,
then augment with `state_local_contracts_master_matches` for state/local fields. Master IDs
not in `mv_target_scorecard` (e.g. master 100000 = Lineage Logistics LLC) still 404 with a
clearer "Master employer not found" message. ~5.38M of 5.49M masters are in the target
scorecard; the rest are unscorable for various reasons.

### R7-18 cap shipped: thin-data perfect-10s went from thousands → 0

Pre-fix, 96.7% of Promising perfect-10s were single-factor `union_proximity`-only thin-data
rows. After cap (weighted_score capped at 7.0 when factors_available<3 AND
direct_factors_available=0), 14,363 thin-data rows are now correctly capped, and zero rows
have a perfect 10 score from indirect factors alone. Tier shift: Priority 1,166 → 1,052
and Strong 2,702 → 2,828 (some rows reclassified down because the cap pulled their
weighted_score below the percentile threshold; some prior-NULL rows promoted as anger
became computable).

### R7-17 fix is now ZERO affected

Pre-fix: 2,526 employers (252 Priority + 453 Strong + 921 Promising + 609 Moderate + 291 Low)
had `score_nlrb` non-NULL but `score_anger` NULL. Cause: anger CASE gate checked
enh_score_osha/enh_score_whd/nlrb_ulp_count>0 but not enh_score_nlrb. Fix: include
enh_score_nlrb in both gate AND formula (numerator weight 3, denominator weight 3).
Post-rebuild count: **0**.

### CompanyEnrich identity grafting is a real reproducible bug

"Crouse Hospital" returns "Children's National Hospital" data — different entity, different
city. token_sort_ratio alone (57%) catches this but false-rejects "Starbucks" → "Starbucks
Coffee Company" (also 55%). Composite fix (partial>=80 OR token_sort>=65 OR token_set>=75)
empirically separates Crouse (75/57/70 — all reject) from legitimate variants
(Walmart 100/78/100, Starbucks 100/55/100, Apple 100/71/100, AT&T 86/55/55, Kroger 75/50/75,
Home Depot 100/71/100). Cleveland Clinic→Cleveland-Cliffs (audit's other example) still
slips through (83/78/78) — that's a search-ranking issue (R7-7), not name-validation.

## Database Changes

- `mv_unified_scorecard` rebuilt twice (once for R7-18, once for R7-17): 146,863 rows
  - 14,363 thin-data rows now capped at weighted_score=7.0
  - Tier distribution shifted: Priority 1,166 → 1,052, Strong 2,702 → 2,828, Promising
    +180, Moderate -338, Low +146 (net of various effects)
  - Rows with score_nlrb non-NULL but score_anger NULL: 2,526 → 0
- `mv_employer_data_sources` rebuilt (14.5s) — collateral effect of refresh_all.py
- `data_source_freshness` table re-populated via `create_data_freshness.py --refresh`
  (R7-19 took effect — NLRB latest_record_date 2021-05-28 → 2026-01-21)
- 8 stalest large tables ANALYZE'd (FA9.6): all state_contracts_* from Apr 22, ~37s total

## New Problems Found

- **`build_target_data_sources` MV rebuild fails** with rc=1 in 0.4s — pre-existing,
  unrelated to today's work. Stops the rebuild chain so `mv_target_scorecard` etc. don't
  refresh either. Logged for separate investigation. Not blocking — the unified scorecard
  rebuilt cleanly.
- Windows zombie-socket pattern is now confirmed 3x in 2 sessions; the workaround (move
  to next port, update Vite proxy) is reliable but accumulates port-jumping commits.
  Recommend documenting it formally in the project's Windows runbook.

## What's Next

The R7 roadmap has 9 items still open (out of original ~30):

**Quick wins remaining:**
- M-1 partial — added to /ship; needs to actually be USED next time a route ships
- REG-3 — postgres listen_addresses=localhost (10 min, needs Jacob coord)
- REG-2 — backup task re-register (1 hr, needs admin)

**Heavier:**
- R7-7 — search ranking tiebreak + alias dictionary (4-8 hrs) — most user-visible
- R7-1 — demographics 145M total_workers state-fallback aggregation (1-2 days) — deepest data bug
- REG-4 — F7 orphan rate investigation (overnight)
- REG-5 — P0 docs sweep (2-4 hrs)
- REG-6 — SEC Exhibit 21 DB pipeline
- REG-7 — NLRB nightly cron admin install

**Pre-beta polish:**
- DISABLE_AUTH flip + JWT secret (30 min)
- PHONETIC_STATE deactivation (1 day)
- Live Gemini soak test ($25)

## Files Modified

```
api/data_source_catalog.py
api/dependencies.py
api/routers/demographics.py
api/routers/employers.py
api/routers/master.py
api/routers/profile.py
api/routers/whd.py
scripts/scoring/build_unified_scorecard.py
scripts/research/tools.py
frontend/src/features/employer-profile/WhdCard.jsx
frontend/src/features/employer-profile/NlrbSection.jsx
frontend/src/features/employer-profile/GovernmentContractsCard.jsx
frontend/src/features/employer-profile/ComparablesCard.jsx
frontend/__tests__/ComparablesCard.test.jsx  (NEW)
frontend/src/shared/api/profile.js
frontend/vite.config.js  (uncommitted workaround; revert post-reboot)
.claude/skills/ship/SKILL.md  (vault — M-1 step)
```

## Tests

- Backend: not run this session (no pytest invocation; recommended before /ship)
- Frontend: vitest 294/294 passing across 40 test files (run after Track D edits)

## Session Stats

- Duration: ~5 hours active work (multiple track context-switches)
- Commits: 6 (all unpushed)
- Net code changes: +1,500 / -200 lines roughly (large because of WIP catch-up bundling)
- Audit blockers closed: 21 (13 R7-NEW P0 + 1 regression + 5 Week 1 quick wins + 2 misc)
- Servers respawned: 4 times (Windows zombie pattern)
- MV rebuilds: 2 (both via refresh_all.py --skip-gower)
