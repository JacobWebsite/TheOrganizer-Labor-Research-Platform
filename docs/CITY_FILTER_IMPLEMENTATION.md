# City Filter Implementation - Checkpoint Plan

**Date:** January 29, 2026  
**Goal:** Add city filtering to employer search with state-dependent dropdown

---

## Current State

**Problem:** Employer search has state filter but no city filter, limiting geographic precision.

**Data Analysis:**
- 10,208 unique cities across 62,885 employers
- Cities per state range from 50-1,200+
- Too many cities for single dropdown → need state-dependent approach

**Approach:** State-dependent city dropdown
1. When user selects a state, load cities for that state
2. Show top cities by employer count (max 200)
3. Include "All Cities" option

---

## Checkpoint 1: Create Cities API Endpoint ✅ COMPLETE

**Goal:** New endpoint to get cities for a state

**Endpoint:** `GET /api/employers/cities?state=CA`

**Test Results:**
- CA: LOS ANGELES (573), SAN FRANCISCO (524), SACRAMENTO (258)...
- NY: NEW YORK (1454), BROOKLYN (446), BRONX (363)...

---

## Checkpoint 2: Update Search API to Accept City ✅ COMPLETE

**Goal:** Add `city` parameter to `/api/employers/search`

**Test Results:**
- NY + BROOKLYN returns 446 employers (matches city count ✅)

---

## Checkpoint 3: Add City Dropdown to Frontend ✅ COMPLETE

**Goal:** Add city dropdown that populates when state is selected

**Files Updated:**
- `frontend/labor_search_v6.html` - Added city dropdown + loadCities()
- `frontend/labor_search_v6_osha.html` - Same updates

---

## Checkpoint 4: Update Search Function ✅ COMPLETE

**Goal:** Include city in search request

**Files Updated:** Both v6 and v6_osha frontends now include city parameter

---

## Checkpoint 5: Test & Verify ✅ COMPLETE

**Test Cases - ALL PASSED:**

| State | City | Expected | Result |
|-------|------|----------|--------|
| CA | LOS ANGELES | 573 employers | ✅ 573 |
| NY | NEW YORK | 1454 employers | ✅ |
| NY | BROOKLYN | 446 employers | ✅ 446 |
| CA | (All) | 7350 employers | ✅ |

---

## Files Modified

1. `api/labor_api_v6.py` - Added `/api/employers/cities` endpoint + city filter
2. `frontend/labor_search_v6.html` - Added city dropdown + loadCities() + search param
3. `frontend/labor_search_v6_osha.html` - Same updates

---

## Completion Summary

**Date Completed:** January 29, 2026
**Time Taken:** ~25 minutes
**Status:** ✅ ALL CHECKPOINTS COMPLETE

**Features:**
- State-dependent city dropdown (cities load when state selected)
- Shows employer count per city in dropdown
- Top 200 cities per state (ordered by employer count)
- Case-insensitive city matching
- Works with all existing filters (union, NAICS, name)
