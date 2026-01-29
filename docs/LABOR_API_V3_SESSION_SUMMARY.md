# Labor API v3 & Unified Interface - Session Summary
## Date: January 24, 2026

---

## What Was Accomplished

### 1. Created Unified Labor API v3 (`labor_api_v3.py`)
A FastAPI backend that integrates three data sources:
- **OLMS LM Financial Data** - Union financial filings
- **F-7 Employer Data** - Bargaining unit employers
- **NLRB Data** - Cases and elections

**Endpoints Created:**
| Endpoint | Description |
|----------|-------------|
| `GET /api/affiliations` | List all affiliations with member counts |
| `GET /api/unions/search` | Search unions with filters (affiliation, state, name, etc.) |
| `GET /api/unions/{f_num}` | Union detail with LM financials and NLRB summary |
| `GET /api/unions/{f_num}/employers` | F-7 employers for a union |
| `GET /api/unions/{f_num}/elections` | NLRB elections with vote tallies |
| `GET /api/unions/{f_num}/cases` | NLRB ULP and representation cases |

### 2. Created Web Interface (`labor_unified_v3.html`)
A single-page application with:
- Affiliation dropdown with member/local counts
- Union search with state and member filters
- Union list showing local numbers, members, employer counts
- Detail panel with tabs for:
  - LM Financials (5-year history)
  - F-7 Employers
  - NLRB Elections (with win/loss stats)
  - NLRB Cases (by type)

### 3. Added Local Numbers to Database
- Added `local_number` and `desig_name` columns to `unions_master`
- Populated from `lm_data.desig_num` field
- Updated 25,021 union records
- Interface now displays "Local 1199", "Local 32", etc.

### 4. Fixed Multiple Schema Issues
- Column names: `ttl_assets` not `total_assets`
- Election schema: `tally_type` not `election_type`
- Vote tallies: Separate query to `nlrb_tallies` table
- Type casting: `f_num` varchar ↔ `olms_f_num` int

---

## Current Database Schema Context

```
unions_master:
  - f_num (PK), union_name, aff_abbr, local_number, desig_name
  - members, city, state, sector
  - has_f7_employers, f7_employer_count, f7_total_workers

lm_data:
  - f_num, yr_covered, ttl_assets, ttl_liabilities, ttl_receipts, ttl_disbursements

f7_employers_deduped:
  - employer_id, employer_name, latest_union_fnum
  - city, state, latitude, longitude, latest_unit_size

nlrb_union_xref:
  - olms_f_num (int), nlrb_union_name, match_confidence

nlrb_cases, nlrb_elections, nlrb_tallies, nlrb_participants
```

---

## Known Issues / Technical Debt

### Data Quality
1. **Local numbers showing "0"** - Councils and state organizations use 0
2. **Missing local numbers** - Some unions don't have desig_num in LM data
3. **Generic union names** - All show as "SERVICE EMPLOYEES" instead of "1199SEIU"
4. **F-7 employer counts** - National orgs show 0 (locals have the employers)

### UI/UX
1. **No pagination** - Large result sets load all at once
2. **No loading states** - Some tabs show "Loading..." forever on empty data
3. **Election win/loss logic** - Simplified; doesn't handle runoffs or challenges
4. **No geographic visualization** - Employer data has lat/lng but no map

### Performance
1. **NLRB subqueries are slow** - Could benefit from materialized views
2. **No caching** - Every request hits database
3. **No indexes optimized for API** - May need composite indexes

---

## Files Created This Session

```
C:\Users\jakew\Downloads\labor-data-project\
├── labor_api_v3.py              # FastAPI backend (372 lines)
├── labor_unified_v3.html        # Web interface (943 lines)
├── add_local_numbers.py         # Script to add local_number column
├── test_api_endpoints.py        # API endpoint tester
├── test_local_numbers.py        # Local number verification
├── check_columns.py             # Schema inspection
├── check_elections_cols.py      # Election table schema
└── LABOR_API_V3_SESSION_SUMMARY.md  # This file
```

---

## How to Run

```bash
# Start the API server
cd C:\Users\jakew\Downloads\labor-data-project
py -m uvicorn labor_api_v3:app --reload --port 8000

# Open the interface
# File: labor_unified_v3.html (open in browser)
# API must be running on localhost:8000
```

---

## Possible Next Steps

### CHECKPOINT A: Data Quality Improvements
- [ ] A1: Parse union names to extract meaningful names (e.g., "1199SEIU" from desig fields)
- [ ] A2: Fix "Local 0" display - show as "Council" or "State Organization"
- [ ] A3: Add union name aliases table for better display names
- [ ] A4: Consolidate duplicate unions (same org, different f_nums over years)

### CHECKPOINT B: Geographic Features
- [ ] B1: Add Leaflet map to employer tab showing employer locations
- [ ] B2: Create state-level heatmap of union density
- [ ] B3: Add geocoding for unions without coordinates
- [ ] B4: Regional filtering/aggregation

### CHECKPOINT C: Analytics & Visualization
- [ ] C1: Add Chart.js for financial trend visualization
- [ ] C2: Election win rate trends over time
- [ ] C3: Membership growth/decline charts
- [ ] C4: Industry/sector breakdown views

### CHECKPOINT D: Performance & Scale
- [ ] D1: Create materialized views for NLRB aggregations
- [ ] D2: Add API response caching
- [ ] D3: Implement pagination with cursor-based navigation
- [ ] D4: Add database connection pooling

### CHECKPOINT E: Advanced Search
- [ ] E1: Full-text search across union names
- [ ] E2: Employer name search
- [ ] E3: NLRB case number lookup
- [ ] E4: Cross-reference search (find unions at specific employer)

### CHECKPOINT F: Export & Reporting
- [ ] F1: CSV export for search results
- [ ] F2: PDF report generation for union profiles
- [ ] F3: Bulk data export API
- [ ] F4: Scheduled report generation

### CHECKPOINT G: BLS Integration
- [ ] G1: Add BLS union density data to interface
- [ ] G2: Industry-level density overlays
- [ ] G3: Historical density trends (1983-present)
- [ ] G4: Cross-reference with NLRB activity

---

## Session Statistics

- **API Endpoints**: 6 functional endpoints
- **Database Tables Used**: 8 tables
- **Union Records with Local Numbers**: 25,021
- **Total Affiliations**: 110
- **Match Rate Achievement**: 88-90% (from previous session)

---

## Quick Reference: API Testing

```python
import requests
BASE = "http://localhost:8000/api"

# Get affiliations
requests.get(f"{BASE}/affiliations").json()

# Search SEIU locals in NY
requests.get(f"{BASE}/unions/search?affiliation=SEIU&state=NY").json()

# Get union detail
requests.get(f"{BASE}/unions/31847").json()  # SEIU 1199

# Get employers, elections, cases
requests.get(f"{BASE}/unions/31847/employers").json()
requests.get(f"{BASE}/unions/31847/elections").json()
requests.get(f"{BASE}/unions/31847/cases").json()
```
