# Session 2026-03-05: Frontend Fixes (6-4, 6-5, 7-6)

## Task 6-4: Signal Count /8 -> /9
- Backend `build_target_scorecard.py` counts 9 signals: osha, whd, nlrb, contracts, financial, industry_growth, union_density, size, similarity
- `SignalInventory.jsx` already did dynamic counting correctly
- Fixed hardcoded "/8" in 3 files:
  - `ProfileHeader.jsx:128`
  - `TargetsPage.jsx:112`
  - `TargetsTable.jsx:111`

## Task 6-5: Verified Badge for Research-Confirmed Scores
- `ScorecardSection.jsx` had `isEnhanced()` returning true only when `enh > base`
- Added `isVerified()`: returns true when `has_research && enh === base`
- Blue "V" badge (#3a6b8c) next to green "R" badge (#3a7d44)
- Both badges render in the score gauge area per factor

## Task 7-6: Covered Workers vs Members Clarification
- **Bug found:** `UnionProfileHeader.jsx` used `union.total_workers` but column is `f7_total_workers` -- always showed "--"
- **Hero section:** Now shows both "Members (LM)" and "Covered Workers (F-7)" side by side with title tooltips
- **MiniStat:** Renamed "Total Workers" to "Covered Workers (F-7)", fixed to use `f7_total_workers`
- **Extreme ratio warning:** When covered workers > 10x members, explanatory note appears
- **Tooltips added** to "Members" column headers in:
  - UnionResultsTable.jsx (also renamed "Workers" column to "Covered")
  - AffiliationTree.jsx
  - SisterLocalsSection.jsx
  - UnionFinancialsSection.jsx
- No API changes needed -- `unions_master` already has both `members` and `f7_total_workers`

## Test Results
- 248 frontend tests passing (1 pre-existing SettingsPage failure)
- No test files referenced changed strings
