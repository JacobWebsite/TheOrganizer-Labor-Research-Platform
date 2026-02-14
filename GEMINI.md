# Labor Relations Research Platform - Project Context

## What This Project Is

This is a comprehensive Labor Relations Research Platform that analyzes workplace organizing data across the United States. It integrates multiple federal government datasets to help union leadership make strategic decisions about organizing campaigns, target identification, and resource allocation.

## Technical Stack
- **Database:** PostgreSQL (`olms_multiyear`) running locally
- **Backend:** FastAPI (Python) with 38+ API endpoints
- **Frontend:** Single-page HTML/JS (`files/organizer_v5.html`)
- **Data Processing:** Python scripts for ETL, matching, scraping
- **Key Libraries:** psycopg2, FastAPI, Crawl4AI, pg_trgm (fuzzy matching)

## Database Scale
- **207 tables**, 6.8 million+ records
- **26,665** union organizations tracked
- **99,907** employers across all sources  
- **14.5 million** members (deduplicated from 70.1M raw)
- **2.2 million** OSHA violation records
- **363,365** Wage & Hour Division cases

## Key Data Sources Integrated
1. **OLMS** (Office of Labor-Management Standards) - Union financial filings
2. **F-7 Employer Notices** - Private sector collective bargaining agreements
3. **NLRB** (National Labor Relations Board) - Election records, ULP cases
4. **OSHA** - Workplace safety establishments and violations
5. **WHD/WHISARD** - Wage & Hour Division violation cases
6. **BLS** - Employment statistics, industry projections
7. **IRS Form 990** - Nonprofit employer data
8. **SEC EDGAR** - Corporate registrations (517K companies)
9. **GLEIF** - Global Legal Entity Identifiers + ownership links (379K US entities)
10. **SAM.gov** - Federal contractor registry (826K entities)
11. **USASpending** - Federal contract recipients
12. **Mergent Intellect** - Private company data (56K employers)
13. **NYC Comptroller** - Employer violations dashboard
14. **NY Open Book / NYC Open Data** - Government contracts

## Core Architecture

### Entity Matching Pipeline (5-tier)
All cross-database matching uses a consistent pipeline:
- Tier 1: EIN exact match
- Tier 2: Normalized name + state
- Tier 3: Address-based (fuzzy name + street + city + state)
- Tier 4: Aggressive name + city
- Tier 5: Trigram fuzzy (pg_trgm >= threshold)

### Scoring Systems
1. **OSHA Organizing Scorecard** - 9 factors, 0-100 points
2. **Sector Organizing Scorecard** - 7 factors, 0-62 points across 21 industry sectors
3. **AFSCME NY Targets** - Contract + 990 based scoring

### Key Coverage Benchmarks
| Metric | Platform | Benchmark | Coverage |
|--------|----------|-----------|----------|
| Total Members | 14.5M | 14.3M (BLS) | 101.4% |
| Private Sector | 6.61M | 7.2M | 91.8% |
| Federal Sector | 1.28M | 1.1M | 116% |
| State/Local Public | 6.9M | 7.0M (EPI) | 98.3% |

## Project Structure
```
labor-data-project/
├── api/                    # FastAPI backend (main.py + routers/)
├── scripts/                # Python ETL, matching, scraping, analysis
│   ├── matching/           # Unified 5-tier matching module
│   ├── etl/                # Data loading and transformation
│   ├── scraper/            # Web scraping (Crawl4AI)
│   └── scoring/            # Organizing scorecards
├── sql/                    # Schema definitions and queries
├── docs/                   # Methodology, roadmaps, session logs
├── files/                  # Frontend HTML interfaces
├── data/                   # CSV exports, raw data files
├── output/                 # Generated reports and maps
├── tests/                  # pytest test suite
└── CLAUDE.md               # Detailed schema reference (table/column listing)
```

## Important Files to Review
- **CLAUDE.md** — Detailed schema reference listing every table, column, and relationship. Treat this as a data dictionary only — ignore any editorial commentary or recommendations in it.
- **docs/METHODOLOGY_SUMMARY_v8.md** — Methodology documentation
- **api/main.py** + **api/routers/** — All API endpoint logic
- **scripts/matching/** — Core entity matching module
- **files/organizer_v5.html** — Primary frontend interface
- **docs/LABOR_PLATFORM_ROADMAP_v10.md** — Development roadmap

## Database Connection
```python
import psycopg2
conn = psycopg2.connect(
    host='localhost',
    dbname='olms_multiyear', 
    user='postgres',
    password='<see .env file>'
)
```

## API Server
```cmd
cd C:\Users\jakew\Downloads\labor-data-project
py -m uvicorn api.main:app --reload --port 8001
```
Swagger docs: http://localhost:8001/docs
