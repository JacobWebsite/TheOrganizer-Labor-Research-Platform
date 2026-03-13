# Labor Relations Research Platform - Project Roadmap v10

**Date:** January 29, 2026  
**Status:** Active Development  
**Goal:** Comprehensive organizing target identification system

---

## Executive Summary

The platform has achieved **98.3% public sector coverage** against EPI benchmarks and **101.4% alignment** with BLS total membership benchmarks. The next phase focuses on **UI improvements** (particularly local number display and geographic granularity), **historical trend visualization**, and preparing the final data enrichment layer (Form 990 + Mergent + SEC).

---

## Current Platform Status

### Data Assets

| Asset | Records | Status |
|-------|---------|--------|
| OLMS Union Filings | 26,665 unions | ✅ Complete |
| OLMS Historical Data | 16 years (2010-2024) | ✅ Available |
| F-7 Employers | 63,118 (96.2% matched) | ✅ Complete |
| NLRB Elections | 33,096 | ✅ Complete |
| NLRB Participants | 30,399 (95.7% matched) | ✅ Complete |
| OSHA Establishments | 1,007,217 | ✅ Complete |
| OSHA Violations | 2,245,020 ($3.52B penalties) | ✅ Complete |
| Public Sector Locals | 1,520 | ✅ Complete |
| Public Sector Employers | 7,987 | ✅ Complete |
| EPI State Benchmarks | 51 states | ✅ Complete |

### BLS/EPI Alignment

| Sector | Platform | Benchmark | Coverage |
|--------|----------|-----------|----------|
| **Total Members** | 14.5M | 14.3M (BLS) | **101.4%** ✅ |
| Private Sector | 6.65M | 7.2M | 92% |
| Federal Sector | 1.28M | 1.1M | 116% |
| **State/Local Public** | 6.9M | 7.0M (EPI) | **98.3%** ✅ |

---

## Phase 1: UI Improvements (Priority: HIGH)

### 1.1 Local Number Display 🔧
**Problem:** Dropdown shows "SERVICE EMPLOYEES (Brooklyn, NY)" instead of "SEIU Local 32BJ (Brooklyn, NY)"

**Data Available:**
- `unions_master.local_number` - numeric local identifier (e.g., "32")
- `unions_master.desig_name` - designation suffix (e.g., "BJ")
- `ps_union_locals.local_designation` - local designation

**Solution:**
1. Update `/api/unions/locals/{aff}` to return formatted display name
2. Construct display as: `{aff_abbr} Local {local_number}{desig_name} ({city}, {state})`
3. Example: "SEIU Local 32BJ (New York, NY)" instead of "SERVICE EMPLOYEES (New York, NY)"

**Effort:** 2-3 hours

### 1.2 Geographic Granularity 🗺️ - MOSTLY COMPLETE ✅
**Problem:** Current UI only shows state-level data. Users can't drill down to city/county level.

**Completed Jan 29-30, 2026:**
1. ✅ **City-level employer search** - City filter added to employer tab
2. ✅ **MSA/Metro area analysis** - Metro dropdown with union density %
3. ✅ **CBSA mapping** - 25,763 employers (40.8%) mapped to metros
4. ✅ **MSA stats API** - `/api/metros/{cbsa}/stats` with density by sector

**Remaining (Optional):**
- County heat map visualization
- County-level public sector drill-down
3. **County-level public sector** - ps_employers has employer_type but limited geography
4. **Heat map by county** - Visualize union density geographically

**Data Available:**
- `f7_employers_deduped` - has city, state, lat/lon for 150K+ employers
- `osha_establishments` - has city, state for 1M+ establishments
- ✅ **HUD ZIP-to-Tract Crosswalk** - `C:\Users\jakew\Downloads\HUD ZIP-to-CBSA\ZIP_TRACT_092025.xlsx`
  - 189,375 rows, 39,366 unique ZIPs, 3,277 counties
  - Contains: ZIP, Census Tract, City, State, County FIPS (derived from tract[:5])
- ✅ **OMB CBSA Delineation File** - `list1_2023.xlsx` (uploaded)
  - 1,918 rows mapping County FIPS → CBSA (Metro Area)
  - 937 unique CBSAs (1,252 metro + 663 micro)
  - Contains: CBSA Code, CBSA Title, FIPS State/County, Metro/Micro type

**Geographic Hierarchy (Complete):**
```
ZIP Code → Census Tract → County FIPS → CBSA/Metro Area
  (HUD)        (HUD)        (derived)      (OMB)
```

**Implementation Plan:**
1. Load HUD ZIP-to-Tract into PostgreSQL (derive county FIPS)
2. Load OMB CBSA delineation file  
3. Create `zip_geography` table with ZIP → City, County, CBSA, Metro Name
4. Join to F-7/OSHA employers via ZIP code
5. Add city dropdown, MSA dropdown to UI

**Effort:** 6-10 hours total
- Load HUD + OMB files: 2-3 hours
- City filter UI: 2 hours
- MSA grouping + dropdown: 2-4 hours
- County heat map: 4-6 hours (optional)

### 1.3 Public Sector UI Tab 🏛️ - COMPLETE ✅
**Problem:** New public sector data (1,520 locals, 7,987 employers) not exposed in web interface

**Completed Jan 29, 2026:**
1. ✅ Add "Public Sector" tab to main navigation (6th tab)
2. ✅ Summary stats: Locals, Employers, Parents, BUs, Members
3. ✅ Union Locals search with parent union & state filters
4. ✅ Employers search with employer type & state filters
5. ✅ Color-coded employer type badges (Federal, County, School, etc)
6. ✅ Pagination for both locals and employers
7. ✅ 6 API endpoints: stats, parent-unions, locals, employers, employer-types, benchmarks

**Remaining (Optional):**
- State-level EPI benchmark comparison widget

**Effort:** ~~6-8 hours~~ → 25 min actual

### 1.4 Union Search Improvements 🔍 - MOSTLY COMPLETE ✅
**Current Issues:** (RESOLVED)
- ~~Search shows truncated names~~ → Now shows "SEIU Local 32" ✅
- ~~Sector filtering limited~~ → Sector badges added ✅

**Completed:**
1. ✅ Display full union name with local number in results
2. ✅ Show public/private/federal sector badges (colored)
3. ✅ Organization type badges (Local, Council, NHQ, etc.)

**Remaining (Optional):**
- Dedicated local number search field
- Member count trends (spark lines)

**Effort:** ~~4-6 hours~~ → ~1 hour completed, ~3 hours remaining

---

## Phase 2: Historical Trends (Priority: MEDIUM-HIGH)

### 2.1 Available Data
16 years of OLMS LM filings (2010-2024):

| Year | Filings | Notes |
|------|---------|-------|
| 2010 | 24,095 | Full year |
| ... | ... | ... |
| 2024 | 19,554 | Full year |
| 2025 | 5,790 | Incomplete |

### 2.2 Trend Visualizations Needed

1. **National membership trends** - Total union membership 2010-2024
2. **By affiliation** - SEIU, AFSCME, NEA, etc. growth/decline
3. **By state** - State-level membership over time
4. **By industry** - NAICS sector trends (private sector only)
5. **Election win rates** - NLRB win rate by year

**Implementation:**
- Add "Trends" tab to UI
- Line charts with Chart.js (already loaded)
- Dropdown filters: affiliation, state, industry, date range
- Export capability for researchers

**Effort:** 8-10 hours

### 2.3 API Endpoints Needed
```
GET /api/trends/national?start_year=2010&end_year=2024
GET /api/trends/by-affiliation/{aff}?start_year=2010&end_year=2024
GET /api/trends/by-state/{state}?start_year=2010&end_year=2024
GET /api/trends/elections-by-year
```

**Effort:** 4-6 hours

---

## Phase 3: Data Quality Improvements (Priority: MEDIUM)

### 3.1 OSHA-to-F7 Match Improvement - IMPROVED ⚠️
**Before:** 31.6% of F-7 employers matched to OSHA (20,094)
**After:** 44.6% of F-7 employers matched to OSHA (28,137)
**Target:** 50%+

**Completed Feb 2026:**
1. ✅ ZIP code + fuzzy name + NAICS validation
2. ✅ Address normalization with abbreviations (St→Street, etc.)
3. ✅ State + prefix matching with similarity threshold
4. ✅ City + NAICS + lower similarity threshold
5. ✅ Corporate suffix stripping (Inc, LLC, Corp)

**Remaining potential:**
- EIN lookup (requires external data)
- Parent company linkage (requires Mergent data)

**Methods added:** 13 new matching algorithms
**Improvement:** +8,043 employers (+12.8%)

### 3.2 Headquarters Location Fix
**Problem:** DC shows 8.3M public sector members due to national HQ locations

**Solution:**
- Already handling in most views
- Need to ensure ps_union_locals UI excludes NHQ from state counts
- Add "headquarters_only" flag to clarify

**Effort:** 2-4 hours

---

## Phase 4: Final Data Enrichment Layer (Priority: LOWER - Final Addition)

### Overview
Group together as final platform enrichment:
- **Form 990** (IRS) - Union AND employer verification
- **Mergent Intellect / Data Axle** - Corporate hierarchies
- **SEC 10-K** - Public company labor disclosures

### 4.1 Form 990 Data (Dual Purpose)

**For Unions:**
- Cross-validate public sector membership estimates
- Executive compensation data
- Revenue/expense breakdown
- Already validated: NEA 99.99% match vs OLMS

**For Employers (Nonprofit):**
- Hospitals, universities, social services
- Employee counts, revenue
- EIN linkage to F-7 employers

**Source:** ProPublica Nonprofit Explorer API
**Effort:** 12-16 hours

### 4.2 Mergent Intellect / Data Axle

**Data Available:**
- DUNS numbers
- Revenue, employee counts
- Corporate parent-subsidiary links
- Executive contacts
- Accurate NAICS codes

**Access:** CUNY Library subscription
**Effort:** 15-20 hours

### 4.3 SEC 10-K Filings

**Data Available:**
- Annual reports for public companies
- Labor relations disclosures (Item 1)
- CBA mentions in risk factors
- Employee counts

**Source:** SEC EDGAR API
**Effort:** 12-16 hours

### 4.4 Integration Strategy
1. Create unified `employer_enrichment` table
2. Link via EIN, DUNS, or name matching
3. Add to employer detail view in UI
4. Enable filtering by revenue, employee count, corporate parent

**Total Phase 4 Effort:** 40-52 hours

---

## NOT IN SCOPE

| Item | Reason |
|------|--------|
| Contract Expiration Tracking | Handled by [Bargaining for the Common Good](https://www.bargainingforthecommongood.org/mapping-landing/) |
| State PERB Data | Later-term project (CA PERB, NY PERB, etc.) |
| Predictive ML Models | Requires Phase 4 data first |

---

## Recommended Execution Order

### Immediate (Week 1)
1. ~~**Local Number Display** (2-3 hrs)~~ ✅ COMPLETE - Jan 29, 2026
2. ~~**City Filter for Employers** (2 hrs)~~ ✅ COMPLETE - Jan 29, 2026
3. ~~**Historical Trends API** (4-6 hrs)~~ ✅ COMPLETE - 8 endpoints done

### Short-term (Weeks 2-3)
4. ~~**Trends Visualization Tab** (8-10 hrs)~~ ✅ COMPLETE - Jan 30, 2026
5. ~~**Public Sector UI Tab** (6-8 hrs)~~ ✅ COMPLETE - Jan 29, 2026
6. ~~**Union Search Improvements** (4-6 hrs)~~ ✅ MOSTLY COMPLETE - Jan 29, 2026

### Medium-term (Month 2)
7. ~~**MSA/County Geography** (8-12 hrs)~~ ✅ COMPLETE - Jan 30, 2026
8. **OSHA Match Improvement** (8-12 hrs) - Better safety linkage

### Final Phase (Month 3+)
9. **Form 990 + Mergent + SEC Integration** (40-52 hrs) - Complete employer enrichment

---

## Success Metrics

| Metric | Current | Target | Status |
|--------|---------|--------|--------|
| F-7 Match Rate | 96.2% | 98%+ | ⏳ |
| OSHA-F7 Match | 44.6% | 50%+ | ⚠️ Close |
| BLS Coverage | 101.4% | 95-105% | ✅ |
| Public Sector Coverage | 98.3% | 90%+ | ✅ |
| UI Local Numbers | Done | Done | ✅ |
| UI City Search | Done | Done | ✅ |
| UI Sector Badges | Done | Done | ✅ |
| UI Public Sector Tab | Done | Done | ✅ |
| UI MSA/Metro Filter | Done | Done | ✅ |
| UI Trends Visualization | Done | Done | ✅ |

---

## Technical Reference

### Database Connection
```python
psycopg2.connect(
    host='localhost',
    dbname='olms_multiyear',
    user='postgres',
    password='<password in .env file>'
)
```

### Key Tables
```sql
-- Core
unions_master          -- 26,665 unions with local_number field
f7_employers_deduped   -- 63,118 employers
lm_data                -- 2.6M+ historical filings (2010-2024)

-- Public Sector
ps_parent_unions       -- 24 international unions
ps_union_locals        -- 1,520 locals
ps_employers           -- 7,987 public employers
ps_bargaining_units    -- 438 relationships

-- OSHA
osha_establishments    -- 1,007,217 establishments
osha_violations_detail -- 2,245,020 violations
osha_f7_matches        -- 60,105 linkages

-- Reference
epi_state_benchmarks   -- 51 state benchmarks
naics_sectors          -- Industry codes
```

### Current Files
```
frontend/labor_search_v6.html      -- Current UI
frontend/labor_search_v6_osha.html -- OSHA-enhanced UI
api/labor_api_v6.py               -- Current API (v6.4)
```

### Geographic Data Files
```
C:\Users\jakew\Downloads\HUD ZIP-to-CBSA\
├── ZIP_TRACT_092025.xlsx          -- Latest (189K rows, 39K ZIPs)
├── ZIP_TRACT_122023.xlsx          -- 2023 version
├── ZIP_TRACT_122021.xlsx          -- 2021 version
└── [other historical versions]

OMB CBSA Delineation:
├── list1_2023.xlsx                -- County → Metro Area (1,918 rows, 937 CBSAs)
    - CBSA Code, CBSA Title
    - FIPS State Code, FIPS County Code
    - County name, State name
    - Metropolitan/Micropolitan type
```

---

*Last Updated: January 29, 2026*
