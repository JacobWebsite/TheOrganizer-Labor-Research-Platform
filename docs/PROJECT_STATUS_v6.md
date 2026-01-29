# Labor Relations Research Platform - Project Status

**Last Updated:** January 25, 2026  
**Current Version:** 6.0-unified  
**Status:** Production Ready

---

## Platform Overview

A comprehensive labor relations research platform integrating federal datasets to analyze workplace organization trends, financial patterns, and employer relationships across the United States.

### Data Sources Integrated
| Source | Records | Coverage |
|--------|---------|----------|
| OLMS Union Filings | 26,665 unions | 2010-2025 |
| F-7 Employer Bargaining | 71,077 employers | 16 years |
| NLRB Elections | 32,793 elections | Historical |
| NLRB ULP Cases | 422,500 cases | Historical |
| Voluntary Recognition | 1,681 cases | 2007-2024 |
| BLS Union Density | All NAICS sectors | Annual |
| BLS Employment Projections | Industry & occupation | 2024-2034 |

### Key Metrics
- **Total Union Members:** 73.3M (reported, pre-dedup)
- **Deduplicated Members:** ~14.5M (matches BLS)
- **Geocoded Employers:** 73.6% success rate
- **Employer Match Rate:** 91.3% (F7 to NLRB)

---

## Current Architecture

### API: `labor_api_v6.py`
- **Endpoints:** 38 total
- **Port:** 8001
- **Framework:** FastAPI
- **Database:** PostgreSQL (olms_multiyear)

### Web Interface: `labor_search_v6.html`
- **Tabs:** 5 (Employers, Unions, Elections, ULP, Vol. Recognition)
- **Maps:** Leaflet with marker clustering
- **Charts:** Chart.js for visualizations

### Database: `olms_multiyear`
- **Primary Tables:** unions_master, f7_employers_deduped, nlrb_elections, nlrb_cases, nlrb_voluntary_recognition
- **Views:** 40+ analytical views
- **Extensions:** pg_trgm (fuzzy search), PostGIS-ready

---

## API Endpoint Reference

### Lookups
- `GET /api/lookups/sectors` - Union sectors
- `GET /api/lookups/affiliations` - National unions
- `GET /api/lookups/states` - State list
- `GET /api/lookups/naics-sectors` - Industries with density

### BLS Data
- `GET /api/density/naics/{code}` - Union density by industry
- `GET /api/density/all` - All sector density
- `GET /api/projections/naics/{code}` - Employment projections
- `GET /api/projections/top` - Growing/declining industries
- `GET /api/projections/occupations/{code}` - Top occupations

### Employers
- `GET /api/employers/search` - Basic search
- `GET /api/employers/fuzzy-search` - Typo-tolerant
- `GET /api/employers/normalized-search` - Strips Inc/LLC
- `GET /api/employers/{id}` - Detail with NLRB history

### Unions
- `GET /api/unions/search` - Search unions
- `GET /api/unions/{f_num}` - Union detail
- `GET /api/unions/locals/{aff}` - Locals by affiliation

### NLRB Elections
- `GET /api/nlrb/summary` - Overview stats
- `GET /api/nlrb/elections/search` - Search elections
- `GET /api/nlrb/elections/map` - Geocoded elections
- `GET /api/nlrb/elections/by-year` - Yearly breakdown
- `GET /api/nlrb/elections/by-state` - State breakdown
- `GET /api/nlrb/elections/by-affiliation` - Union breakdown
- `GET /api/nlrb/election/{case}` - Election detail

### NLRB ULP
- `GET /api/nlrb/ulp/search` - Search ULP cases
- `GET /api/nlrb/ulp/by-section` - By NLRA section

### Voluntary Recognition
- `GET /api/vr/stats/summary` - VR statistics
- `GET /api/vr/stats/by-year` - Yearly trends
- `GET /api/vr/stats/by-state` - State breakdown
- `GET /api/vr/stats/by-affiliation` - Union breakdown
- `GET /api/vr/search` - Search VR cases
- `GET /api/vr/map` - Geocoded VR cases
- `GET /api/vr/new-employers` - Pipeline (not in F7)
- `GET /api/vr/pipeline` - VR to F7 timing
- `GET /api/vr/{case}` - Case detail

### Combined
- `GET /api/organizing/summary` - Elections + VR
- `GET /api/organizing/by-state` - Combined by state
- `GET /api/summary` - Platform overview
- `GET /api/health` - Health check

---

## Quick Start

```bash
# Start API
cd C:\Users\jakew\Downloads\labor-data-project
py -m uvicorn labor_api_v6:app --host 127.0.0.1 --port 8001

# Open web interface
# File: labor_search_v6.html

# Swagger docs
# http://127.0.0.1:8001/docs
```

---

## Version History

| Version | Date | Changes |
|---------|------|---------|
| 6.0 | Jan 25, 2026 | Unified API: VR + density + projections + all features |
| 5.1 | Jan 25, 2026 | VR integration into v5 API |
| 5.0 | Jan 2026 | NLRB elections & ULP integration |
| 4.2 | Jan 2026 | Fuzzy/normalized employer search |
| 4.0 | Jan 2026 | BLS density & projections |
| 3.0 | Dec 2025 | Employer geocoding complete |

---

## Files Reference

### Core Files (Use These)
| File | Purpose |
|------|---------|
| `labor_api_v6.py` | **Current API** - all endpoints |
| `labor_search_v6.html` | **Current Web UI** - all features |
| `schema_v4_employer_search.sql` | Database schema |

### Documentation
| File | Purpose |
|------|---------|
| `VR_INTEGRATION_COMPLETE.md` | VR integration details |
| `PROJECT_STATUS_v6.md` | This file |
| `nlrb_integration_plan.md` | NLRB integration reference |

### Legacy (Reference Only)
- `labor_api_v4.py` - Density/projections
- `labor_api_v5.py` - NLRB + VR (superseded)
- `vr_api_endpoints.py` - Standalone VR (merged into v6)

---

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

## Next Development Priorities

1. **CSV Export** - Download search results
2. **Contract Tracking** - First contract dates after VR
3. **News Integration** - Link cases to coverage
4. **Metro Analysis** - CBSA-level coverage rates
5. **Public API** - Rate-limited researcher access

---

**Platform Status: OPERATIONAL** ✅
