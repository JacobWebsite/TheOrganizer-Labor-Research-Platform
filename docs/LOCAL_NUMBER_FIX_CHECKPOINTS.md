# Local Number Display Fix - Checkpoint Plan
**Date:** January 29, 2026  
**Goal:** Show "SEIU Local 32 (New York, NY)" instead of "SERVICE EMPLOYEES (New York, NY)"

---

## ✅ Checkpoint 1: Database View (COMPLETE)
View `v_union_display_names` already exists and produces correct display names:
- "SEIU Local 1199" for locals with numbers
- "SEIU Council" for councils without numbers
- Fallback to "SERVICE EMPLOYEES" for NHQ entries

## ✅ Checkpoint 2: API Endpoint (COMPLETE)
`/api/unions/locals/{affiliation}` already updated to use `v_union_display_names`

## ⏳ Checkpoint 3: Frontend Dropdown Update
**File:** `frontend/labor_search_v6.html`
**Task:** Update loadLocals() to use `display_name` field

## ⏳ Checkpoint 4: Test & Verify
- Test dropdown shows formatted names
- Verify API returns correct data
