# Union Search Improvements - Checkpoint Plan

**Date:** January 29, 2026  
**Goal:** Enhance union search with additional filters, better display, and richer data

---

## Current State

**API Filters Supported:**
- ✅ name (searches union_name, local_number, display_name)
- ✅ aff_abbr (affiliation)
- ✅ sector (private/public)
- ✅ state
- ✅ city
- ✅ union_type (LU, JC, etc.)
- ✅ min_members
- ✅ has_employers (boolean)

**UI Filters Present:**
- ✅ Name / Local #
- ✅ Affiliation dropdown
- ✅ Type dropdown
- ✅ State dropdown
- ✅ Min Members input
- ❌ City (API supports, UI missing)
- ❌ Sector (API supports, UI missing)
- ❌ Has Employers checkbox

**Display Currently Shows:**
- display_name (with local numbers ✅)
- City, State
- F-Num, Affiliation
- Member count
- F-7 employer count (if any)

---

## Checkpoint 1: Add Missing UI Filters ⏳

**Goal:** Add City, Sector, and Has Employers filters to UI

**Changes to labor_search_v6.html:**

1. Add City dropdown (state-dependent, like employer search)
2. Add Sector dropdown (Private/Public)
3. Add "Has F-7 Employers" checkbox

**New grid layout:** 9 columns instead of 7

**Validation:**
- [ ] City dropdown populates when state selected
- [ ] Sector filter works
- [ ] Has Employers checkbox filters correctly

---

## Checkpoint 2: Add Financial Data to Results ⏳

**Goal:** Show key financial metrics in union search results

**API Changes:**
- Add ttl_assets, ttl_receipts to union search response

**Display Changes:**
- Show total assets (formatted as $X.XM or $X.XB)
- Show annual receipts

**Validation:**
- [ ] Financial data displays for unions with data
- [ ] Gracefully handles nulls

---

## Checkpoint 3: Add Election Stats to Results ⏳

**Goal:** Show NLRB election win/loss record in search results

**API Changes:**
- Add subquery to count elections won/lost per union

**Display Changes:**
- Show "12W / 3L" style election record
- Color code (green for high win rate, red for low)

**Validation:**
- [ ] Election stats appear for unions with NLRB history
- [ ] Performance acceptable (may need optimization)

---

## Checkpoint 4: Improve Search by Local Number ⏳

**Goal:** Better handling of "Local 32" and "32" searches

**Current:** API searches local_number = clean_name
**Improve:** 
- Handle "SEIU 32" → search for SEIU + local 32
- Handle "32BJ" → search for local_number containing "32BJ"
- Handle "#32" → strip # and search

**Validation:**
- [ ] "Local 32" finds SEIU Local 32
- [ ] "SEIU 32" finds SEIU Local 32
- [ ] "1199" finds Local 1199 unions

---

## Checkpoint 5: Add Union Hierarchy Display ⏳

**Goal:** Show parent union relationship in results

**API Changes:**
- Add parent_union_name, parent_f_num to response
- Use existing affiliation to look up national HQ

**Display Changes:**
- Show "Part of: SEIU National" under local unions
- Link to parent union detail

**Validation:**
- [ ] Locals show their parent union
- [ ] Click on parent opens parent detail

---

## Checkpoint 6: Test & Polish ⏳

**Test Cases:**

| Search | Expected |
|--------|----------|
| "SEIU" | All SEIU unions |
| "Local 32" | SEIU Local 32, IBT Local 32 |
| "32" | All Local 32s |
| State=CA + Has Employers | CA unions with F-7 data |
| Sector=Public | Public sector unions only |

**Polish:**
- Responsive grid for mobile
- Loading states
- Clear all filters button

---

## Files to Modify

1. `api/labor_api_v6.py` - Add financial & election data to response
2. `frontend/labor_search_v6.html` - Add filters & improve display
3. `frontend/labor_search_v6_osha.html` - Same updates

---

## Estimated Time: 4-6 hours

---

*Ready to begin. Proceeding with Checkpoint 1.*
