# Labor Relations Research Platform - Project Status Summary
## Updated: January 25, 2026

---

## PLATFORM OVERVIEW

A comprehensive labor relations research platform integrating multiple federal datasets:
- **OLMS (Office of Labor-Management Standards)**: Union financial filings, membership data
- **F-7 Employer Bargaining Notices**: Employers with existing union contracts
- **BLS (Bureau of Labor Statistics)**: Union density by industry
- **NLRB (National Labor Relations Board)**: Elections and Unfair Labor Practice cases

### Current Database Stats
| Dataset | Records |
|---------|---------|
| Unions (OLMS) | 26,665 |
| Employers (F-7) | 71,077 |
| NLRB Elections | 32,793 |
| NLRB ULP Cases | 422,500 |
| Total NLRB Records | 5,745,810 |

---

## COMPLETED PHASES

### Phase 1-3: Core Data Infrastructure ✅
- PostgreSQL database `olms_multiyear` with full schema
- OLMS union data (2010-2025) with deduplication
- F-7 employer data with geocoding (73.6% success rate)
- BLS union density integration by NAICS sector
- `unions_master` view consolidating all union data

### Phase 4: NLRB Data Load ✅
- 7 NLRB tables: cases, participants, elections, tallies, allegations, filings, docket
- Source: SQLite database (992MB) at `C:\Users\jakew\Downloads\labor-data-project\Claude Ai union project\nlrb (1).db`
- Schema: `nlrb_schema_phase1.sql`

### Phase 5: Entity Matching ✅
- **Union Matching**: 86.3% match rate (improved from 48.2%)
  - Uses affiliation extraction + local number lookup
  - Script: `improved_union_matching.py`
- **Employer Matching**: 20.5% match rate (expected - F-7 only has contract employers)
- Matched fields added to `nlrb_tallies` and `nlrb_participants`

### Phase 6: API Development ✅
- **File**: `labor_api_v5.py`
- **Port**: 8001
- **Endpoints**: 20+ covering employers, unions, elections, ULP cases

### Phase 7: Integrated Web Interface ✅
- **File**: `labor_search_v5.html`
- **Features**:
  - 4 tabs: Employers, Unions, Elections, ULP Cases
  - Dashboard stats bar
  - Click-through to NLRB history modals
  - Map visualizations with clustering
  - Pagination and filtering

---

## KEY FILES

### API & Interface
| File | Purpose |
|------|---------|
| `labor_api_v5.py` | Integrated FastAPI backend |
| `labor_search_v5.html` | Main web interface (4 tabs) |
| `nlrb_explorer.html` | Standalone NLRB explorer (backup) |

### Data Processing Scripts
| File | Purpose |
|------|---------|
| `improved_union_matching.py` | NLRB-to-OLMS union matching |
| `load_data.py` | Original data loader |
| `generate_data.py` | Data generation utilities |

### Schema & Documentation
| File | Purpose |
|------|---------|
| `schema.sql` | Core database schema |
| `nlrb_schema_phase1.sql` | NLRB tables schema |
| `f7_schema.sql` | F-7 employer schema |
| `nlrb_integration_plan.md` | 7-phase integration plan |

---

## HOW TO RUN

### Start the API
```powershell
cd C:\Users\jakew\Downloads\labor-data-project
py -m uvicorn labor_api_v5:app --reload --port 8001
```

### Open the Interface
Open in browser: `C:\Users\jakew\Downloads\labor-data-project\labor_search_v5.html`

### Database Connection
```python
DB_CONFIG = {
    'host': 'localhost',
    'port': 5432,
    'database': 'olms_multiyear',
    'user': 'postgres',
    'password': 'Juniordog33!'
}
```

---

## NEXT PHASES (Suggested Priorities)

### Phase 8: Data Quality & Reconciliation
- [ ] Improve employer matching (currently 20.5%)
- [ ] Add fuzzy employer name matching for NLRB participants
- [ ] Reconcile NLRB union names that didn't match (13.7% unmatched)
- [ ] Cross-reference with BLS membership estimates

### Phase 9: Enhanced Analytics
- [ ] Yearly trends visualization (elections over time)
- [ ] State-level heat maps
- [ ] Industry-specific analysis (link NAICS to elections)
- [ ] Win rate analysis by union size, industry, region

### Phase 10: Additional Data Sources
- [ ] OSHA safety records integration
- [ ] IRS 990 forms (union finances)
- [ ] SEC filings (employer data)
- [ ] Political contribution tracking (OpenSecrets)
- [ ] Contract database development

### Phase 11: Advanced Features
- [ ] CSV/Excel export functionality
- [ ] Saved searches and alerts
- [ ] API authentication for public deployment
- [ ] Predictive analytics (election outcome modeling)

### Phase 12: Geographic Analysis
- [ ] Metro/micropolitan statistical area (CBSA) integration
- [ ] HUD ZIP-to-CBSA crosswalk implementation
- [ ] County Business Patterns employment data
- [ ] Regional coverage rate calculations

---

## API ENDPOINT REFERENCE

### Lookups
- `GET /api/lookups/sectors` - Union sectors
- `GET /api/lookups/affiliations` - National affiliations
- `GET /api/lookups/states` - States with counts

### Employers
- `GET /api/employers/search` - Search with filters
- `GET /api/employers/{id}` - Detail + NLRB history

### Unions
- `GET /api/unions/search` - Search with filters
- `GET /api/unions/{f_num}` - Detail + NLRB history
- `GET /api/unions/locals/{aff}` - Locals by affiliation

### NLRB Elections
- `GET /api/nlrb/summary` - Dashboard stats
- `GET /api/nlrb/elections/search` - Search elections
- `GET /api/nlrb/elections/map` - Map data
- `GET /api/nlrb/elections/by-year` - Yearly trends
- `GET /api/nlrb/elections/by-state` - State breakdown
- `GET /api/nlrb/elections/by-affiliation` - Union performance
- `GET /api/nlrb/election/{case}` - Election detail

### NLRB ULP Cases
- `GET /api/nlrb/ulp/search` - Search ULP cases
- `GET /api/nlrb/ulp/by-section` - By NLRA section

### Platform
- `GET /api/summary` - Overall platform stats
- `GET /api/health` - Health check

---

## NOTES FOR NEW CHAT

1. **Always start the API first** before testing the web interface
2. **Database is PostgreSQL** - ensure it's running on localhost:5432
3. **NLRB source data** is in SQLite at the path noted above (if re-import needed)
4. **Match rates** are documented - some low rates are expected (e.g., F-7 only has contract employers)
5. **Project transcripts** are in `/mnt/transcripts/` for detailed session history
6. **User has CUNY/UVA access** for commercial databases if needed for future phases

---

## QUICK VERIFICATION COMMANDS

```powershell
# Test API health
Invoke-WebRequest -Uri "http://127.0.0.1:8001/api/health" -UseBasicParsing | Select-Object -ExpandProperty Content

# Test summary stats
Invoke-WebRequest -Uri "http://127.0.0.1:8001/api/summary" -UseBasicParsing | Select-Object -ExpandProperty Content

# Test employer search
Invoke-WebRequest -Uri "http://127.0.0.1:8001/api/employers/search?name=starbucks&limit=3" -UseBasicParsing | Select-Object -ExpandProperty Content

# Test NLRB election search
Invoke-WebRequest -Uri "http://127.0.0.1:8001/api/nlrb/elections/search?year_from=2024&limit=5" -UseBasicParsing | Select-Object -ExpandProperty Content
```
