# Labor Relations Research Platform

**Version:** 7.0
**Last Updated:** February 2026
**Status:** Active Development
**GitHub:** [TheOrganizer-Labor-Research-Platform](https://github.com/JacobWebsite/TheOrganizer-Labor-Research-Platform)

---

## Quick Start

```cmd
cd C:\Users\jakew\Downloads\labor-data-project
py -m uvicorn api.labor_api_v6:app --reload --port 8000
```

Open `frontend/labor_search_v6.html` in your browser.

**API Docs:** http://localhost:8000/docs

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

## For Claude/Claude Code

See **[CLAUDE.md](CLAUDE.md)** for:
- Database connection details
- Key tables and columns
- API endpoints
- Feature documentation
- Quick reference queries

---

## Key Features

### 1. Organizing Scorecard (6-factor, 0-100 points)
Data-driven target identification using OSHA violations, industry density, geographic presence, establishment size, NLRB momentum, and government contracts.

### 2. AFSCME NY Organizing Targets
5,428 targets identified from IRS 990 + NY government contract data, with $18.35B total funding and tiered priority scoring.

### 3. Geographic Analysis
MSA/Metro area analysis, city-level employer search, CBSA mapping for 40.8% of employers.

### 4. Historical Trends (2010-2024)
16 years of membership data with national, state, and affiliation breakdowns.

### 5. Membership Deduplication
Raw 70.1M deduplicated to 14.5M, matching BLS within 1.5%.

---

## Data Sources

| Source | Records | Description |
|--------|---------|-------------|
| **OLMS LM Filings** | 26,665 unions | Union financial reports (2010-2025) |
| **F-7 Employer Notices** | 63,118 employers | Private sector bargaining units |
| **NLRB Elections** | 33,096 elections | Election outcomes |
| **NLRB Participants** | 30,399 unions | 95.7% matched to OLMS |
| **OSHA Establishments** | 1,007,217 | Workplace safety data |
| **OSHA Violations** | 2,245,020 | $3.52B in penalties |
| **Public Sector Locals** | 1,520 locals | State/local unions |
| **Public Sector Employers** | 7,987 employers | Government employers |
| **NY State Contracts** | 51,500 | Government contracts |
| **NYC Contracts** | 49,767 | NYC government contracts |
| **990 Employers** | 5,942 | Nonprofit employer data |

---

## API Endpoints

### Core
- `GET /api/health` - Health check
- `GET /api/summary` - Platform summary

### Employers
- `GET /api/employers/search` - Search by name, state, NAICS, city
- `GET /api/employers/{id}` - Employer detail
- `GET /api/employers/cities` - City list

### Unions
- `GET /api/unions/search` - Search unions
- `GET /api/unions/{f_num}` - Union detail
- `GET /api/unions/locals/{aff}` - Locals by affiliation

### NLRB
- `GET /api/nlrb/elections/search` - Election search
- `GET /api/elections/recent` - Recent elections

### OSHA
- `GET /api/osha/summary` - OSHA summary
- `GET /api/osha/establishments/search` - Establishment search

### Public Sector
- `GET /api/public-sector/stats` - Summary statistics
- `GET /api/public-sector/locals` - Search locals
- `GET /api/public-sector/employers` - Search employers

### Organizing Targets
- `GET /api/targets/search` - Search targets
- `GET /api/organizing/scorecard` - 6-factor scorecard search

### Trends
- `GET /api/trends/national` - National trends
- `GET /api/trends/by-state/{state}` - State trends
- `GET /api/trends/by-affiliation/{aff}` - Affiliation trends

---

## Key Documentation

| Document | Description |
|----------|-------------|
| [CLAUDE.md](CLAUDE.md) | Comprehensive reference for Claude Code |
| [LABOR_PLATFORM_ROADMAP_v10.md](LABOR_PLATFORM_ROADMAP_v10.md) | Current roadmap |
| [docs/METHODOLOGY_SUMMARY_v8.md](docs/METHODOLOGY_SUMMARY_v8.md) | Complete methodology |
| [PUBLIC_SECTOR_SCHEMA_DOCS.md](PUBLIC_SECTOR_SCHEMA_DOCS.md) | Public sector schema |
| [EPI_BENCHMARK_METHODOLOGY.md](EPI_BENCHMARK_METHODOLOGY.md) | Benchmark methodology |
| [docs/AFSCME_NY_CASE_STUDY.md](docs/AFSCME_NY_CASE_STUDY.md) | Organizing targets feature |
| [docs/FORM_990_FINAL_RESULTS.md](docs/FORM_990_FINAL_RESULTS.md) | 990 methodology results |
| [docs/EXTENDED_ROADMAP.md](docs/EXTENDED_ROADMAP.md) | Future checkpoints H-O |

---

## Project Structure

```
labor-data-project/
├── api/                    # FastAPI backend
├── frontend/               # HTML/JS interfaces
├── docs/                   # Key documentation
├── scripts/                # Python utilities
├── sql/                    # SQL scripts
├── data/                   # Data exports
├── archive/                # Historical documentation
└── files/                  # Supporting files
```

---

## Database Connection

```python
import psycopg2
conn = psycopg2.connect(
    host='localhost',
    dbname='olms_multiyear',
    user='postgres',
    password='Juniordog33!'
)
```

---

## Contact

**Project:** Labor Relations Research Platform
**Database:** PostgreSQL (`olms_multiyear`)
**Location:** `C:\Users\jakew\Downloads\labor-data-project`

---

*Last Updated: February 2026*
