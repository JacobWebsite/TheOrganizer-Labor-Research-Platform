# Labor Relations Research Platform

**Version:** 7.0  
**Last Updated:** January 29, 2026  
**Status:** Active Development  
**GitHub:** [TheOrganizer-Labor-Research-Platform](https://github.com/JacobWebsite/TheOrganizer-Labor-Research-Platform)

---

## Quick Start

```cmd
cd C:\Users\jakew\Downloads\labor-data-project
py -m uvicorn api.labor_api_v6:app --reload --port 8001
```

Open `frontend/labor_search_v6_osha.html` in your browser.

**API Docs:** http://localhost:8001/docs

---

## Current Coverage (January 2026)

| Sector | Platform | Benchmark | Coverage |
|--------|----------|-----------|----------|
| **Total Members** | 14.5M | 14.3M (BLS) | **101.4%** ✅ |
| **Private Sector** | 6.65M | 7.2M | 92% |
| **Federal Sector** | 1.28M | 1.1M | 116% |
| **State/Local Public** | 6.9M | 7.0M (EPI) | **98.3%** ✅ |

### Public Sector Reconciliation: COMPLETE

- **50 of 51 states** within ±15% of EPI benchmark
- **1 state** (Texas) with documented methodology variance
- **National coverage:** 98.3%

---

## For Claude/Claude Code

See **[CLAUDE.md](CLAUDE.md)** for:
- Database connection details
- Key tables and columns
- Current metrics
- Quick reference queries

---

## Overview

This platform integrates multiple federal government databases to create a comprehensive analytical framework for understanding labor relations in the United States:

### Data Sources

| Source | Records | Description |
|--------|---------|-------------|
| **OLMS LM Filings** | 26,665 unions | Union financial reports (2010-2025) |
| **F-7 Employer Notices** | 63,118 employers | Private sector bargaining units |
| **NLRB Elections** | 33,096 elections | Election outcomes |
| **NLRB Participants** | 30,399 unions | 95.7% matched to OLMS |
| **FLRA Data** | 2,183 units | Federal sector coverage |
| **EPI/BLS Data** | 1.4M+ records | Union density benchmarks |
| **Public Sector Locals** | 1,520 locals | State/local unions |
| **Public Sector Employers** | 7,987 employers | Government employers |

---

## Database Schema

### Core Tables

```
unions_master              -- 26,665 OLMS union filings
f7_employers_deduped       -- 63,118 private sector employers
nlrb_elections            -- 33,096 election records
nlrb_participants         -- 30,399 union petitioners
epi_state_benchmarks      -- 51 state benchmarks
manual_employers          -- 431 state-level public sector
```

### Public Sector Schema (NEW)

```
ps_parent_unions          -- 24 international unions
ps_union_locals           -- 1,520 local unions
ps_employers              -- 7,987 public employers
ps_bargaining_units       -- 438 union-employer relationships
```

---

## Key Documentation

| Document | Description |
|----------|-------------|
| [CLAUDE.md](CLAUDE.md) | Quick reference for Claude |
| [LABOR_PLATFORM_ROADMAP_v9.md](LABOR_PLATFORM_ROADMAP_v9.md) | Project roadmap |
| [docs/METHODOLOGY_SUMMARY_v8.md](docs/METHODOLOGY_SUMMARY_v8.md) | Complete methodology |
| [PUBLIC_SECTOR_SCHEMA_DOCS.md](PUBLIC_SECTOR_SCHEMA_DOCS.md) | Public sector tables |
| [EPI_BENCHMARK_METHODOLOGY.md](EPI_BENCHMARK_METHODOLOGY.md) | Benchmark usage |

---

## API Endpoints

### Summary
- `GET /api/summary` - Platform metrics and coverage

### Employers
- `GET /api/employers/search` - Search by name, state, NAICS
- `GET /api/employers/{id}` - Employer detail
- `GET /api/employers/by-naics/{code}` - By industry

### Unions
- `GET /api/unions/search` - Search unions
- `GET /api/unions/{f_num}` - Union detail

### Elections
- `GET /api/elections/recent` - Recent NLRB elections
- `GET /api/elections/by-employer/{name}` - By employer

---

## Project Structure

```
labor-data-project/
├── api/                    # FastAPI backend
├── frontend/               # HTML/JS interfaces
├── docs/                   # Documentation
│   ├── methodology/        # Detailed methodologies
│   └── session-summaries/  # Session documentation
├── scripts/                # Python utilities
├── sql/                    # SQL scripts
└── data/                   # Data exports
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

## Methodology Highlights

### Membership Deduplication
Raw OLMS data: 70.1M → Deduplicated: 14.5M (matches BLS within 1.5%)

Key adjustments:
- Hierarchy deduplication (federation → international → local)
- Canadian member exclusion (-1.3M)
- Retiree/inactive adjustment (-2.1M)
- NEA/AFT dual affiliation correction (-903K)

### Public Sector Reconciliation
State/local unions exempt from OLMS reporting. Reconciled through:
- NEA/AFT state affiliate research
- Form 990 revenue analysis
- Web research on police, fire, transit unions
- Validation against EPI/CPS benchmarks

---

## Contact

**Project:** Labor Relations Research Platform  
**Database:** PostgreSQL (`olms_multiyear`)  
**Location:** `C:\Users\jakew\Downloads\labor-data-project`

---

*Last Updated: January 29, 2026*
