# Labor Platform v5 Session Summary
## January 31, 2026 - Analytics Dashboard, Corporate Hierarchy & Data Integration Planning

---

## Session Overview

This session extended the Labor Relations Platform v5 with two major new features and created comprehensive instructions for integrating three underutilized data sources.

**Starting Point:** Platform v5 with Organizing Scorecard feature complete
**Ending Point:** Analytics Dashboard + Corporate Hierarchy implemented, data integration plan created

---

## Features Implemented

### 1. Analytics Dashboard

**Access:** "Analytics" button in header

**New API Endpoints:**
| Endpoint | Purpose |
|----------|---------|
| `GET /api/dashboard/summary` | Core metrics (unions, members, employers, OSHA, NLRB) |
| `GET /api/dashboard/trends` | Time-series data for charts (membership, F-7, NLRB, OSHA by year) |
| `GET /api/dashboard/nlrb-recent` | Recent elections + stats by union |
| `GET /api/dashboard/geographic` | State-level breakdowns |
| `GET /api/dashboard/growth` | Growing/declining unions YoY comparison |

**Dashboard Components:**
- **6 Summary Cards:** Total Unions, Members, Employers, Workers Covered, OSHA Establishments, NLRB Cases (1yr)
- **4 Trend Charts (Chart.js):**
  1. Membership Trends — LM filing members over time
  2. NLRB Elections — Stacked bar (wins vs losses by year)
  3. F-7 Filings — Dual-axis (filings + workers covered)
  4. OSHA Violations — Total vs serious violations by year
- **Data Tables:**
  - Recent NLRB Elections (15 most recent)
  - Growing Unions (positive YoY change)
  - Declining Unions (negative YoY change)
  - Top States by Membership (bar visualization)
  - Top National Unions (clickable → opens national dashboard)
  - Top Industries by workers

---

### 2. Corporate Hierarchy / Family View

**Purpose:** Identify related employers (subsidiaries, divisions, locations) using name matching algorithms.

**New API Endpoints:**
| Endpoint | Purpose |
|----------|---------|
| `GET /api/corporate/family/{employer_id}` | Find all related employers by normalized name matching |
| `GET /api/corporate/search?q=...` | Search for corporate families by name |
| `GET /api/corporate/top` | Get largest corporate families by total workers |

**Name Matching Algorithm:**
- `normalize_company_name()` — Removes legal suffixes (Inc, Corp, LLC, Ltd), geographic suffixes (USA, America), punctuation
- `extract_root_name()` — Extracts brand/parent name from full company name

**Frontend Features:**
- **Corporate Family Section in Employer Detail:** Auto-loads when selecting any employer, shows summary with "View All →" button
- **Corporate Family Modal:**
  - Summary cards: locations, workers, states, unions
  - Scrollable list of all related locations
  - Interactive map with blue clustered markers
  - Breakdown by State (bar visualization)
  - Breakdown by Union
  - Click any location → loads in main view

---

## Database Inventory Completed

Verified all data loaded in PostgreSQL `olms_multiyear`:

| Table | Records | Status in API |
|-------|---------|---------------|
| **nlrb_participants** | 1,906,542 | ⚠️ Partially used |
| **epi_union_membership** | 1,420,064 | ⚠️ Not in API |
| **osha_establishments** | 1,007,217 | ✅ Fully integrated |
| **osha_violation_summary** | 872,163 | ✅ Fully integrated |
| **nlrb_cases** | 477,688 | ✅ Integrated |
| **lm_data** | 331,238 | ✅ Used for trends |
| **ar_membership** | 216,508 | ⚠️ Lightly used |
| **f7_employers_deduped** | 63,118 | ✅ Fully integrated |
| **nlrb_elections** | 33,096 | ✅ Fully integrated |
| **bls_union_data** | 31,007 | ✅ Integrated |
| **unions_master** | 26,665 | ✅ Fully integrated |

**Total tables/views in database:** 207

---

## Data Integration Plan Created

Created comprehensive Claude Code instructions for integrating three underutilized data sources:

### Target Data Sources:
1. **EPI Union Membership (1.4M records)** — Historical state/industry density trends 1983-2024
2. **NLRB Participants (1.9M records)** — Enhanced employer/union matching with addresses
3. **AR Membership (216K records)** — Detailed membership categories by union

### Planned New Endpoints (16 total):

**EPI Union Membership (5 endpoints):**
- `GET /api/epi/national-trends` — National membership 1983-2024
- `GET /api/epi/by-state` — State breakdown for year
- `GET /api/epi/state-history/{state}` — State historical trend
- `GET /api/epi/by-sector` — Public vs private breakdown
- `GET /api/epi/compare-states` — Multi-state comparison

**NLRB Participants (5 endpoints):**
- `GET /api/nlrb/participants/search` — Search by name
- `GET /api/nlrb/participants/by-case/{case}` — All participants in case
- `GET /api/nlrb/employers/{id}/cases` — Enhanced employer matching
- `GET /api/nlrb/unions/{f_num}/cases` — Enhanced union matching
- `GET /api/nlrb/participants/stats` — Data quality stats

**AR Membership (6 endpoints):**
- `GET /api/membership/union/{f_num}` — Union detail breakdown
- `GET /api/membership/trends` — Year-over-year trends
- `GET /api/membership/by-affiliation` — By national union
- `GET /api/membership/by-state` — By state
- `GET /api/membership/categories` — Category breakdown
- `GET /api/membership/growth` — YoY growth by affiliation

---

## Files Modified/Created

### Modified:
| File | Lines | Changes |
|------|-------|---------|
| `labor_api_v5.py` | 3,106 | +Dashboard endpoints, +Corporate hierarchy endpoints |
| `organizer_v5.html` | 5,728 | +Analytics Dashboard modal, +Corporate Family modal, +Corporate cluster styles |

### Created:
| File | Purpose |
|------|---------|
| `CLAUDE_CODE_INTEGRATION_INSTRUCTIONS.md` | Detailed instructions for Claude Code to implement EPI, NLRB Participants, AR Membership integration |

---

## Deployment Commands

```powershell
# Copy files
copy organizer_v5.html C:\Users\jakew\Downloads\labor-data-project\
copy labor_api_v5.py C:\Users\jakew\Downloads\labor-data-project\

# Start API
cd C:\Users\jakew\Downloads\labor-data-project
py -m uvicorn labor_api_v5:app --reload --port 8000
```

---

## Database Verification Command

```cmd
set PGPASSWORD=<password in .env file>
psql -U postgres -d olms_multiyear -c "SELECT 'f7_employers_deduped' as tbl, COUNT(*) FROM f7_employers_deduped UNION ALL SELECT 'unions_master', COUNT(*) FROM unions_master UNION ALL SELECT 'osha_establishments', COUNT(*) FROM osha_establishments UNION ALL SELECT 'nlrb_elections', COUNT(*) FROM nlrb_elections UNION ALL SELECT 'nlrb_cases', COUNT(*) FROM nlrb_cases UNION ALL SELECT 'nlrb_participants', COUNT(*) FROM nlrb_participants UNION ALL SELECT 'lm_data', COUNT(*) FROM lm_data UNION ALL SELECT 'bls_union_data', COUNT(*) FROM bls_union_data UNION ALL SELECT 'ar_membership', COUNT(*) FROM ar_membership UNION ALL SELECT 'epi_union_membership', COUNT(*) FROM epi_union_membership UNION ALL SELECT 'osha_violation_summary', COUNT(*) FROM osha_violation_summary ORDER BY count DESC;"
```

---

## Platform Feature Summary (v5 Complete)

| Feature | Status |
|---------|--------|
| Dual-mode search (Employers/Unions) | ✅ |
| Geographic cascade filters | ✅ |
| Find Similar Employers | ✅ |
| Stats Breakdown | ✅ |
| NLRB/OSHA detail panels | ✅ |
| Enhanced union details | ✅ |
| Interactive map view | ✅ |
| National Union Dashboard | ✅ |
| Keyboard navigation | ✅ |
| URL deep linking | ✅ |
| Saved Searches | ✅ |
| Comparison View | ✅ |
| Print/PDF Report | ✅ |
| Organizing Scorecard | ✅ |
| **Analytics Dashboard** | ✅ NEW |
| **Corporate Hierarchy** | ✅ NEW |

---

## Next Steps (For Claude Code)

1. Follow `CLAUDE_CODE_INTEGRATION_INSTRUCTIONS.md` to add 16 new endpoints
2. Add EPI historical charts to Analytics Dashboard
3. Enhance employer/union detail views with NLRB participant matching
4. Add membership breakdown to union detail view

**Estimated time:** 3-4 hours with checkpoints

---

*Session completed: January 31, 2026*
