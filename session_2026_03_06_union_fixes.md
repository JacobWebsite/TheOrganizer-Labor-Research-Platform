# Session 2026-03-06: Union Section Fixes

## Changes Made

### 1. Fixed 70M inflated member count (stale __pycache__)
- **Root cause:** `api/routers/__pycache__/unions.cpython-314.pyc` was stale, serving old code that didn't include `deduplicated_members` column from `union_hierarchy.count_members`
- **The SQL already computed it** (line 233 of unions.py: `SUM(CASE WHEN uh.count_members THEN um.members ELSE 0 END) as deduplicated_members`)
- **Fix:** Cleared `__pycache__`, restarted uvicorn. No code change needed for this.
- **Result:** National unions summary now shows ~13.9M deduplicated instead of ~70M raw total
- **Frontend already handled it:** Both `UnionsPage.jsx` (line 50) and `NationalUnionsSummary.jsx` (line 52) use `deduplicated_members ?? total_members`

### 2. Added local number to union profile header
- **File:** `frontend/src/features/union-explorer/UnionProfileHeader.jsx` (line 43-46)
- **Change:** Added `Local {union.local_number}` display next to union name when local_number exists and is not '0'
- **Styling:** Slightly smaller, slightly transparent (`text-xl font-normal text-white/80`)

### 3. Added local number to affiliation tree locals
- **File:** `frontend/src/features/union-explorer/AffiliationTree.jsx` (LocalNode, line 25-27)
- **Change:** Shows `Local {local.local_number}` after the union name in the hierarchy tree

### 4. Added local_number to hierarchy API response
- **File:** `api/routers/unions.py` (lines 362-375)
- **Change:** Added `"local_number": u.get('local_number')` to both intermediate-child locals and orphan locals in the hierarchy endpoint
- **The SQL already selected it** (line 328) but it wasn't included in the response dicts

## Test Results
- Backend: 1165 passed, 0 failed, 3 skipped
- Frontend: 264 passed, 1 pre-existing failure (SettingsPage Data Freshness test, unrelated)
