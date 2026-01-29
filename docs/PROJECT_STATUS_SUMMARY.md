# Labor Relations Research Platform - Project Status
## Last Updated: January 25, 2026 (Phase 5 Fuzzy Filter Integration)

---

## Current State

### Working Components
- **API v4.2** (`labor_api_v42.py`) - FastAPI backend on port 8001
- **Web Interface v4** (`labor_search_v4.html`) - Enhanced search UI
- **PostgreSQL Database** (`olms_multiyear`) - 2.8M+ records

### Recent Updates (Jan 25, 2026)
- ✅ Fuzzy search now respects all filter dropdowns (affiliation, NAICS, state, sector)
- ✅ Normalized search fully integrated with filters
- ✅ Local union dropdown shows "Local 123 - City, ST" format
- ✅ Canonical union name lookup with 43 variant mappings
- ✅ NEW: `/api/projections/naics/{code}` endpoint for BLS employment projections
- ✅ Industry Info panel shows employment 2024 and 10-year growth forecast

### Data Loaded
| Source | Records | Status |
|--------|---------|--------|
| OLMS LM Filings | 26,000+ unions | ✅ Complete |
| F-7 Employers | 150,386 unique | ✅ Geocoded (75.8%) |
| NLRB Cases | 5.3M records | ✅ 88% union matched |
| BLS Union Density | 32,239 records | ✅ Phase 1 Complete |
| BLS Employment Projections | 115,378 records | ✅ Phase 2 Complete |
| BLS Crosswalk Tables | 58,912 records | ✅ Phase 3 Complete |

### BLS Integration Summary (NEW)
| Phase | Table | Records | Description |
|-------|-------|---------|-------------|
| Phase 1 | bls_union_series | 1,232 | Union rates by state/industry/occupation |
| Phase 1 | bls_union_data | 31,007 | Time series 1983-2024 |
| Phase 2 | bls_industry_projections | 423 | Industry forecasts 2024-2034 |
| Phase 2 | bls_occupation_projections | 1,113 | Occupation forecasts |
| Phase 2 | bls_industry_occupation_matrix | 113,842 | Industry-occupation crosswalk |
| Phase 3 | census_industry_naics_xwalk | 24,373 | Census → NAICS mapping |
| Phase 3 | census_occupation_soc_xwalk | 34,539 | Census → SOC mapping |
| **Total** | | **206,529** | |

### Quick Start
```bash
cd C:\Users\jakew\Downloads\labor-data-project
py -m uvicorn labor_api_v42:app --reload --port 8001
# Open labor_search_v4.html in browser
```

---

## All Available Checkpoints

### Data Quality & UI (Original)
| ID | Name | Description |
|----|------|-------------|
| **A** | Data Quality | Fix union display names, "Local 0" handling, name aliases |
| **B** | Geographic Features | Add Leaflet maps, state heatmaps, employer visualization |
| **C** | Analytics & Visualization | Chart.js financials, election trends, membership charts |
| **D** | Performance & Scale | Materialized views, caching, pagination, connection pooling |
| **E** | Advanced Search | Full-text search, employer lookup, cross-reference queries |
| **F** | Export & Reporting | CSV export, PDF reports, bulk data API |
| **G** | BLS Integration | ✅ COMPLETE - Surface density data in UI, historical trends |

### External Data Integration (New)
| ID | Name | Description |
|----|------|-------------|
| **H** | Mergent Intellect | Employer enrichment - revenue, employees, NAICS, corporate hierarchy |
| **I** | IRS 990 Forms | Union financials - exec compensation, expenses, investments, PACs |
| **J** | SEC/Edgar | Public company data - 10-K labor disclosures, CBA mentions |
| **K** | OSHA | Workplace safety - inspections, violations, injury rates |
| **L** | FEC/Political | Political spending - PAC contributions, lobbying |
| **M** | Contract Database | Actual CBAs - wages, benefits, expirations |
| **N** | News & Media | Real-time monitoring - organizing alerts, sentiment |
| **O** | Predictive Analytics | Forecasting - election outcomes, organizing likelihood |

---

## BLS Integration Views (NEW)

```sql
-- Available views after Phase 3:
SELECT * FROM v_naics_sector_summary;         -- NAICS sectors overview
SELECT * FROM v_soc_major_group_summary;      -- SOC groups overview
SELECT * FROM v_database_integration_summary; -- Full database summary
```

See `BLS_INTEGRATION_QUERIES.sql` for detailed integration examples.

---

## To Continue Work

Start a new chat and say:

> "Continue with Checkpoint [X]"

Where X is any letter A-O from the tables above.

### Recommended Starting Points

**For immediate value:**
- **Checkpoint H** (Mergent) - Enrich employer data with financials
- **Checkpoint I** (990s) - Add union executive compensation data

**For quick wins:**
- **Checkpoint B** (Maps) - Visualize existing geocoded data
- **Checkpoint K** (OSHA) - Low-effort safety data integration

**For analytical depth:**
- **Checkpoint C** (Charts) - Visualize financial trends
- Use new BLS crosswalk tables for industry/occupation analysis

---

## OLMS-BLS Reconciliation Analysis (NEW - Jan 2025)

Successfully reconciled OLMS membership data with BLS CPS estimates through systematic adjustments:

| Adjustment | Amount | % Impact |
|------------|-------:|--------:|
| Raw OLMS NHQ Data | 20,241,994 | 100% |
| Less: Retirees/Inactive | (2,094,249) | -10.3% |
| Less: NEA/AFT Dual Affiliates | (903,013) | -4.5% |
| Less: Canadian Members (23 unions) | (1,329,500) | -6.6% |
| **Final US Estimate** | **15,915,232** | **78.6%** |
| BLS Benchmark | 14,300,000 | |
| **Remaining Gap** | **+11.3%** | |

### Key Findings
- **Canadian members**: ~1.3M workers in US-based international unions (UFCW 250K, USW 225K, LIUNA 160K, IBT 125K, SEIU 100K lead)
- **Retirees**: Schedule 13 categories exclude 2.1M non-active members
- **NEA/AFT overlap**: NYSUT, FEA, Education MN dual affiliations = 903K dedup
- **Remaining gap (11.3%)**: Explained by methodology differences (household survey vs union self-reports)

See: `OLMS_BLS_RECONCILIATION_ANALYSIS.md` for full methodology and Canadian membership research.

---

## Key Files Reference

```
C:\Users\jakew\Downloads\labor-data-project\
├── labor_api_v3.py                    # FastAPI backend
├── labor_unified_v3.html              # Web interface
├── PROJECT_STATUS_SUMMARY.md          # This file
├── OLMS_BLS_RECONCILIATION_ANALYSIS.md # Membership reconciliation (NEW)
├── BLS_INTEGRATION_QUERIES.sql        # BLS integration examples
├── final_reconciliation_v2.py         # OLMS-BLS analysis script (NEW)
├── final_us_membership_high_confidence.csv # US-only estimates (NEW)
├── bls_phase3_complete/               # Phase 3 SQL scripts
├── schema.sql                         # Database schema
└── [various .py scripts]              # Data processing utilities
```

## Database Connection
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

## Session Transcripts

Previous work is documented in:
- `/mnt/transcripts/` (Claude's computer)
- Session summaries in project directory (your computer)

Key sessions:
- NLRB integration and matching (88% union match achieved)
- F-7 employer geocoding (75.8% success)
- API v3 development
- BLS Phase 1-3 integration
- **OLMS-BLS Reconciliation** (this session) - Canadian membership research, Schedule 13 analysis
