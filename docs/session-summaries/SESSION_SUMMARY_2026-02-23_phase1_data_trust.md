# Session Summary: 2026-02-23 — Phase 1 Data Trust (Fix the Scoring System)

**Agents:** Claude Code (scoring fixes, coordination), Codex (investigations I1-I5, cleanup scripts), Gemini (OSHA cleanup, data coverage, investigations I6-I10)

## Decisions Made (D1-D7)

| Decision | Resolution | Rationale |
|----------|-----------|-----------|
| D1: Name similarity floor | 0.80 | 57% of OSHA Splink matches were in 0.65-0.70 garbage band. Sampled 20 borderline matches — nearly all <0.75 were false positives. |
| D2: Priority tier meaning | REJECTED | Targeting is structural. Recent violations (2yr) and active contracts are yes/no flags, not scoring requirements. |
| D3: Min factors for Strong | YES (3) | Prevents low-data employers from appearing in Priority/Strong tiers. |
| D4: Stale OSHA handling | YES | Bulk-reject OSHA Splink matches with name_similarity < 0.80. |
| D5: score_similarity | Weight 0, keep column | Pipeline broken: name+state bridge only matches 833/146K (integer vs hex ID mismatch), proximity >= 5 gate kills everything (all values are 5, 10, or NULL). |
| D7: Empty columns | Drop 8, keep 6 — DEFERRED | Views (v_f7_for_bls_counts, v_employer_with_agreements, v_f7_employers_current) depend on columns. 5 of 8 used in WHERE/JOIN across 6 API routers. |

## Work Completed

### Claude: Scoring Fixes (`build_unified_scorecard.py`)

1. **score_financial (1.1 — NEW factor)**
   - Added `financial_990` CTE joining `national_990_f7_matches` + `national_990_filers`
   - Revenue scale (0-6): $0->0, $100K->1, $500K->2, $1M->3, $5M->4, $10M->5, $50M+->6
   - Asset cushion (+0-2): assets > 2x expenses -> +2, > 1x -> +1
   - Revenue per worker (+0-2): >$200K -> +2, >$100K -> +1
   - Public companies (via SEC crosswalk): flat 7
   - Coverage: 10,755 employers (7.3%), 11 distinct values

2. **score_contracts (1.2 — FIX)**
   - Replaced flat 4.00 for all contractors with obligation tiers:
     - $100M+ -> 10, $10M+ -> 8, $1M+ -> 6, $100K+ -> 4, <$100K -> 2, contractor no data -> 1
   - Coverage: 8,672 employers, 6 distinct values

3. **score_similarity (1.3)**
   - Set weight to 0 in total_weight, factors_available, and weighted_score numerator/denominator
   - Replaced with score_financial in weight calculations
   - Column retained for future pipeline fix

4. **Tier logic (1.6)**
   - Min 3 `factors_available` for both Priority AND Strong (was only Priority)
   - New flag columns: `has_recent_violations` (2yr OSHA/WHD/NLRB inspections, 26,486 employers), `has_active_contracts` (8,672 employers)

5. **MV rebuild (1.8) + validation (1.9)**
   - All 4 MVs rebuilt: unified_scorecard, employer_data_sources, employer_search, organizing_scorecard
   - Created `scripts/analysis/score_validation_set.py` — samples 3 employers per tier across NAICS sectors

6. **Column drops (1.7 — DEFERRED)**
   - Attempted DROP on 8 columns, blocked by 3 views + 6 API routers
   - Deferred to Phase 3 (coordinated view + API refactor)

### Codex: Investigations + Cleanup

- **I1:** No NLRB proximity junk risk — uses canonical groups, not individual match counts
- **I2:** Confirmed score_similarity pipeline bugs (name+state bridge ID mismatch, proximity gate)
- **I3:** 46,624/46,627 dangling matches already rejected; 1 active dangling row found
- **I4:** 115 junk/placeholder records quantified (names like `*****`, `1`, `3M`, `AD`, `Bureau of Prisons`)
- **I5:** All current active OSHA matches already >= 0.80 (floor already effective)
- **`flag_junk_records.py --commit`:** 115 records flagged `exclude_from_scoring=TRUE`
- **`fix_dangling_matches.py --commit`:** 1 active dangling row marked `status='orphaned'`

### Gemini: OSHA Cleanup + Data Coverage + Investigations

- **1.4 (`reject_stale_osha.py`):** 46,528 active OSHA Splink matches with sim < 0.80 superseded. Active Splink: 51,302 -> 4,774. Total active OSHA: 97,142 -> 50,614.
- **1.5B:** Data coverage indicator added to profile API (`source_count`, `factors_available`, `data_coverage` label)
- **1.5C + I6:** Membership 72M vs 14.5M is hierarchy double-counting
- **I7:** 538K superseded matches in UML — expected from pipeline evolution
- **I8:** Employer grouping: over-merging on generic names, under-merging nationals
- **I9:** NAICS inference: ~5K-6K employers recoverable from OSHA/WHD matches
- **I10:** 3K+ association records inflate building trades metrics

## Key Metrics (Post-Phase 1)

| Metric | Before | After |
|--------|--------|-------|
| weighted_score avg | 4.12 | 4.16 |
| Priority tier | 2.9% | 1.6% (2,332) |
| Strong tier | 12.1% | 10.5% (15,350) |
| Active OSHA matches | 97,142 | 50,614 |
| Active OSHA Splink | 51,302 | 4,774 |
| score_financial coverage | 0 (duplicate of growth) | 10,755 (7.3%) |
| score_contracts values | 1 (flat 4.00) | 6 (tiered 1-10) |
| Junk records flagged | 0 | 115 |

## Files Changed

- **Modified:** `scripts/scoring/build_unified_scorecard.py` (major — all scoring logic)
- **Modified:** `api/routers/profile.py` (Gemini — data coverage indicator)
- **New:** `scripts/analysis/score_validation_set.py`, `scripts/analysis/flag_junk_records.py`, `scripts/maintenance/fix_dangling_matches.py`, `scripts/maintenance/reject_stale_osha.py`
- **New:** `docs/investigations/I1_nlrb_proximity_junk.md` through `I10_multi_employer_agreements.md`
- **Commits:** `2ae857c` (Phase 1 scoring + Codex), `5e09377` (Gemini I7-I10)

## Errors Encountered

1. `name_similarity` is in `evidence` JSONB, not a direct column
2. `source_type` doesn't exist — correct column is `source_system`
3. `score_financial` computed in `weighted` CTE couldn't be referenced in same CTE — moved to `scored` CTE
4. Duplicate `is_public` in SELECT — removed duplicate
5. Column drops blocked by view dependencies (3 views + 6 API routers) — deferred

## Phase 2 Plan

- **Track A (Claude):** Splink model retune (2.1), OSHA re-run (2.2), evaluate other sources (2.3), MV rebuild (2.6)
- **Track B (Codex):** Employer grouping fix (2.4), NAICS inference (2A.2), Multi-employer flagging (2A.6)
- **Deferred:** Geocoding (2A.4), NLRB xref rebuild (2A.5), master dedup quality
