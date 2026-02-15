# Labor Relations Research Platform

**Version:** 7.1 (Phase 1 Complete)
**Last Updated:** February 15, 2026
**Status:** Active Development
**GitHub:** [TheOrganizer-Labor-Research-Platform](https://github.com/JacobWebsite/TheOrganizer-Labor-Research-Platform)

---

## Quick Start

```cmd
cd C:\Users\jakew\Downloads\labor-data-project

# Start the API (requires PostgreSQL running with olms_multiyear database)
py -m uvicorn api.main:app --reload --port 8001
```

Open `files/organizer_v5.html` in your browser.

**API Docs:** http://localhost:8001/docs

### Environment Variables

Create a `.env` file in the project root:

```env
DB_HOST=localhost
DB_PORT=5432
DB_NAME=olms_multiyear
DB_USER=postgres
DB_PASSWORD=your_password

# JWT Auth -- required for production (32+ chars)
LABOR_JWT_SECRET=your_secret_here

# Set to bypass auth in development
# DISABLE_AUTH=true

# CORS (comma-separated; defaults to localhost:8001,8080)
# ALLOWED_ORIGINS=http://localhost:8001,http://localhost:8080
```

### Authentication

Auth is enforced when `LABOR_JWT_SECRET` is set in `.env`. Set `DISABLE_AUTH=true` to bypass in development.

- **First user** registers as admin (advisory-locked bootstrap)
- Subsequent registration requires admin token
- Login: `POST /api/auth/login` returns JWT
- All non-public endpoints require `Authorization: Bearer <token>`
- Generate tokens: `py -m api.middleware.auth --user admin --role admin`

---

## Current Coverage (February 2026)

| Sector | Platform | Benchmark | Coverage |
|--------|----------|-----------|----------|
| **Total Members** | 14.5M | 14.3M (BLS) | **101.4%** |
| **Private Sector** | 6.65M | 7.2M | 92% |
| **Federal Sector** | 1.28M | 1.1M | 116% |
| **State/Local Public** | 6.9M | 7.0M (EPI) | **98.3%** |

### Public Sector Reconciliation: COMPLETE

- **50 of 51 states** within +/-15% of EPI benchmark
- **1 state** (Texas) with documented methodology variance
- **National coverage:** 98.3%

---

## Key Features

### 1. Organizing Scorecard (9-factor, range 10-78)
Data-driven target identification using 9 SQL-computed factors: OSHA violations, industry density, geographic presence, establishment size, NLRB momentum, government contracts, WHD violations, union presence, and membership trends. Served via materialized view (`mv_organizing_scorecard`, 24,841 rows).

### 2. ULP Context
Unfair Labor Practice case tracking linked to employers via NLRB participant matching. ULP badges in scorecard list, detailed case info in employer detail view. Not a scoring factor -- context only.

### 3. Geographic Analysis
MSA/Metro area analysis, city-level employer search, CBSA mapping, county-level density estimates, NY sub-county (ZIP/census tract) density.

### 4. Union Density Estimates
BLS industry density, state-level density by government level, county estimates with industry-weighted methodology, NY sub-county granularity.

### 5. Historical Trends (2010-2024)
16 years of membership data with national, state, and affiliation breakdowns.

### 6. Data Freshness Tracking
15 data sources (~7M records) with automated freshness monitoring. Admin endpoints for refresh.

---

## Data Sources

| Source | Records | Description |
|--------|---------|-------------|
| **OLMS LM Filings** | 26,665 unions | Union financial reports (2010-2025) |
| **F-7 Employer Notices** | 113,713 employers | Private sector bargaining units (60,953 current + 52,760 historical) |
| **NLRB Elections** | 33,096 elections | Election outcomes |
| **NLRB Participants** | 30,399 unions | 95.7% matched to OLMS |
| **OSHA Establishments** | 1,007,217 | Workplace safety data |
| **OSHA Violations** | 2,245,020 | $3.52B in penalties |
| **WHD Investigations** | ~250,000 | Wage and Hour Division |
| **SAM.gov Entities** | 826,000 | Federal contractor registrations |
| **IRS Form 990** | 5,942 | Nonprofit employer data |
| **GLEIF** | 3,260 matched | Legal Entity Identifier data |
| **Mergent** | 947 matched | Corporate intelligence data |
| **Public Sector Locals** | 1,520 locals | State/local unions |
| **Public Sector Employers** | 7,987 employers | Government employers |
| **NY State Contracts** | 51,500 | Government contracts |
| **NYC Contracts** | 49,767 | NYC government contracts |

---

## API Endpoints (152 total, 17 routers)

### Auth (`/api/auth/`)
- `POST /api/auth/login` - Login, returns JWT
- `POST /api/auth/register` - Register (first user = admin, subsequent need admin token)
- `POST /api/auth/refresh` - Refresh JWT
- `GET /api/auth/me` - Current user info

### Core
- `GET /api/health` - Health check
- `GET /api/summary` - Platform summary

### Employers (`/api/employers/`)
- `GET /api/employers/search` - Search by name, state, NAICS, city
- `GET /api/employers/{id}` - Employer detail
- `GET /api/employers/cities` - City list

### Unions (`/api/unions/`)
- `GET /api/unions/search` - Search unions
- `GET /api/unions/{f_num}` - Union detail
- `GET /api/unions/locals/{aff}` - Locals by affiliation

### NLRB (`/api/nlrb/`)
- `GET /api/nlrb/elections/search` - Election search
- `GET /api/elections/recent` - Recent elections

### OSHA (`/api/osha/`)
- `GET /api/osha/summary` - OSHA summary
- `GET /api/osha/establishments/search` - Establishment search

### WHD (`/api/whd/`)
- Wage and Hour Division investigation search and detail

### Public Sector (`/api/public-sector/`)
- `GET /api/public-sector/stats` - Summary statistics
- `GET /api/public-sector/locals` - Search locals
- `GET /api/public-sector/employers` - Search employers

### Organizing (`/api/organizing/`)
- `GET /api/organizing/scorecard` - 9-factor scorecard search
- `GET /api/organizing/scorecard/{id}` - Employer detail with score breakdown

### Density (`/api/density/`)
- `GET /api/density/by-state` - State-level density
- `GET /api/density/by-govt-level` - By government level
- `GET /api/density/by-county` - County estimates
- `GET /api/density/county-summary` - National summary
- `GET /api/density/ny/*` - NY sub-county (counties, ZIPs, tracts)
- Industry-weighted analysis and comparison endpoints

### Trends (`/api/trends/`)
- `GET /api/trends/national` - National trends
- `GET /api/trends/by-state/{state}` - State trends
- `GET /api/trends/by-affiliation/{aff}` - Affiliation trends

### Corporate (`/api/corporate/`)
- Cross-reference via corporate identifier crosswalk (GLEIF, Mergent, SEC, EIN)

### Admin (`/api/admin/`)
- `POST /api/admin/refresh-scorecard` - Refresh materialized view (admin-only)
- `GET /api/admin/data-freshness` - Data source freshness stats
- `POST /api/admin/refresh-freshness` - Refresh freshness data (admin-only)

### Additional Routers
- **Lookups** - NAICS codes, state lists, reference data
- **Sectors** - Sector-level analysis
- **Projections** - Membership projections
- **VR** - Voter registration crosswalk
- **Museums** - Labor museum data

---

## Test Suite

165 tests across 5 test files:

```cmd
py -m pytest tests/ -v
```

| File | Tests | Description |
|------|-------|-------------|
| `test_api.py` | 33 | Core API endpoint integration tests |
| `test_auth.py` | 16 | JWT auth flow (register, login, refresh, protected) |
| `test_data_integrity.py` | 24 | Database constraint and referential integrity |
| `test_matching.py` | 53 | Employer matching pipeline validation |
| `test_scoring.py` | 39 | Scorecard computation and tier distribution |

---

## Project Structure

```
labor-data-project/
├── api/                    # FastAPI backend
│   ├── main.py             # App entry point (v7.0)
│   ├── config.py           # Environment config
│   ├── database.py         # Connection pool (RealDictCursor)
│   ├── middleware/          # Auth middleware
│   └── routers/            # 17 endpoint routers
├── files/                  # Frontend assets
│   ├── organizer_v5.html   # Main SPA (2,138 lines, markup only)
│   ├── css/organizer.css   # Styles (227 lines)
│   └── js/                 # 10 JS modules (global scope, load-order dependent)
│       ├── config.js       # API base URL
│       ├── utils.js        # Shared utilities
│       ├── maps.js         # Leaflet map integration
│       ├── territory.js    # Territory mode
│       ├── search.js       # Search functionality
│       ├── deepdive.js     # Deep dive analysis
│       ├── detail.js       # Employer detail view
│       ├── scorecard.js    # Scorecard display
│       ├── modals.js       # Modal dialogs
│       └── app.js          # App initialization
├── tests/                  # pytest test suite (165 tests)
├── scripts/                # ETL, matching, maintenance scripts
├── docs/                   # Documentation and audit reports
├── sql/                    # SQL scripts
├── db_config.py            # Shared database connection config
├── .env                    # Environment variables (not committed)
└── Roadmap_TRUE_02_15.md   # Current roadmap (7 phases, 14 weeks)
```

---

## Key Documentation

| Document | Description |
|----------|-------------|
| [CLAUDE.md](CLAUDE.md) | Comprehensive reference for Claude Code |
| [Roadmap_TRUE_02_15.md](Roadmap_TRUE_02_15.md) | Current roadmap (supersedes all prior) |
| [docs/METHODOLOGY_SUMMARY_v8.md](docs/METHODOLOGY_SUMMARY_v8.md) | Complete methodology |
| [docs/AUDIT_REPORT_ROUND2_CLAUDE.md](docs/AUDIT_REPORT_ROUND2_CLAUDE.md) | Round 2 audit report |
| [PUBLIC_SECTOR_SCHEMA_DOCS.md](PUBLIC_SECTOR_SCHEMA_DOCS.md) | Public sector schema |
| [EPI_BENCHMARK_METHODOLOGY.md](EPI_BENCHMARK_METHODOLOGY.md) | Benchmark methodology |

---

## Materialized View Refresh

The organizing scorecard uses a materialized view that must be refreshed after data changes:

```cmd
# Refresh scorecard (concurrent, no downtime)
py scripts/scoring/create_scorecard_mv.py --refresh

# Or via API (admin auth required)
curl -X POST http://localhost:8001/api/admin/refresh-scorecard -H "Authorization: Bearer <token>"

# Refresh data freshness stats
py scripts/maintenance/create_data_freshness.py --refresh
```

---

## Database Connection

```python
from db_config import get_connection
conn = get_connection()
```

Database: PostgreSQL `olms_multiyear` on localhost, ~160 tables, 186 views, 4 materialized views, ~20 GB, ~24M rows.

---

## Contact

**Project:** Labor Relations Research Platform
**Database:** PostgreSQL (`olms_multiyear`)
**Location:** `C:\Users\jakew\Downloads\labor-data-project`

---

*Last Updated: February 15, 2026*
