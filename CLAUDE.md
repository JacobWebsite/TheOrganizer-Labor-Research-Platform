# Labor Relations Research Platform - Claude Context

## Quick Reference
**Last Updated:** February 2026

### Database Connection
```python
import psycopg2
conn = psycopg2.connect(
    host='localhost',
    dbname='olms_multiyear',
    user='postgres',
    password='Juniordog33!'
)
```

### Current Platform Status

| Metric | Value | Benchmark | Coverage |
|--------|-------|-----------|----------|
| Total Members | 14.5M | 14.3M (BLS) | 101.4% |
| Private Sector | 6.65M | 7.2M | 92% |
| Federal Sector | 1.28M | 1.1M | 116% |
| State/Local Public | 6.9M | 7.0M (EPI) | 98.3% |
| States Reconciled | 50/51 | - | 98% |

---

## Database Schema

### Core Tables
| Table | Records | Description |
|-------|---------|-------------|
| `unions_master` | 26,665 | OLMS union filings (has local_number field) |
| `f7_employers_deduped` | 63,118 | Private sector employers |
| `nlrb_elections` | 33,096 | NLRB election records |
| `nlrb_participants` | 30,399 | Union petitioners (95.7% matched to OLMS) |
| `lm_data` | 2.6M+ | Historical filings (2010-2024) |
| `epi_state_benchmarks` | 51 | State union benchmarks |
| `manual_employers` | 431 | State-level public sector |

### Public Sector Tables
| Table | Records | Description |
|-------|---------|-------------|
| `ps_parent_unions` | 24 | International unions (AFSCME, NEA, etc.) |
| `ps_union_locals` | 1,520 | Local unions, councils, chapters |
| `ps_employers` | 7,987 | Public employers by type |
| `ps_bargaining_units` | 438 | Union-employer relationships |

### OSHA Tables
| Table | Records | Description |
|-------|---------|-------------|
| `osha_establishments` | 1,007,217 | OSHA-covered workplaces |
| `osha_violations_detail` | 2,245,020 | Violation records ($3.52B penalties) |
| `osha_f7_matches` | 60,105 | Linkages to F-7 employers |
| `v_osha_organizing_targets` | - | Organizing target view |

### Contract/Target Tables (AFSCME NY)
| Table | Records | Description |
|-------|---------|-------------|
| `ny_state_contracts` | 51,500 | NY State contracts (Open Book NY) |
| `nyc_contracts` | 49,767 | NYC contracts (Open Data API) |
| `employers_990` | 5,942 | IRS 990 nonprofit employers |
| `organizing_targets` | 5,428 | Prioritized organizing targets |

### Geography Tables
| Table | Records | Description |
|-------|---------|-------------|
| `zip_geography` | 39,366 | ZIP to City/County/CBSA mapping |
| `cbsa_reference` | 937 | Metro area definitions |

---

## API Endpoints (localhost:8000)

### Core
- `GET /api/health` - Health check
- `GET /api/summary` - Platform summary with coverage %

### Employers
- `GET /api/employers/search` - Search by name, state, NAICS, city
- `GET /api/employers/{id}` - Employer detail with OSHA data
- `GET /api/employers/cities` - City list for dropdown
- `GET /api/employers/by-naics/{code}` - By industry code
- `GET /api/employers/by-naics-detailed/{naics}` - Detailed NAICS search

### Unions
- `GET /api/unions/search` - Search unions
- `GET /api/unions/{f_num}` - Union detail
- `GET /api/unions/locals/{aff}` - Locals by affiliation

### NLRB
- `GET /api/nlrb/elections/search` - Election search
- `GET /api/nlrb/ulp/search` - ULP search
- `GET /api/nlrb/participants/search` - Participant search
- `GET /api/elections/recent` - Recent elections
- `GET /api/elections/by-employer/{name}` - By employer

### OSHA
- `GET /api/osha/summary` - OSHA summary statistics
- `GET /api/osha/establishments/search` - Establishment search
- `GET /api/osha/high-severity` - High severity violations

### Public Sector
- `GET /api/public-sector/stats` - Summary statistics
- `GET /api/public-sector/parent-unions` - List parent unions
- `GET /api/public-sector/locals` - Search locals
- `GET /api/public-sector/employers` - Search employers
- `GET /api/public-sector/employer-types` - Employer type list
- `GET /api/public-sector/benchmarks` - EPI benchmarks

### Organizing Targets
- `GET /api/targets/search` - Search 990-based targets
- `GET /api/targets/stats` - Target statistics
- `GET /api/targets/{id}` - Target detail with contracts
- `GET /api/targets/{id}/contracts` - All contracts for target
- `GET /api/targets/for-union/{f_num}` - Recommended for union
- `GET /api/organizing/scorecard` - 6-factor OSHA scorecard search
- `GET /api/organizing/scorecard/{estab_id}` - Scorecard detail

### Geographic
- `GET /api/metros` - List metro areas
- `GET /api/metros/{cbsa}/stats` - Metro stats with density

### Trends
- `GET /api/trends/national` - National membership 2010-2024
- `GET /api/trends/by-state/{state}` - State trends
- `GET /api/trends/by-affiliation/{aff}` - Affiliation trends
- `GET /api/trends/elections-by-year` - Election win rates

### Multi-Employer
- `GET /api/multi-employer/stats` - Deduplication statistics

---

## Key Features (What Exists - Don't Rebuild)

### 1. Organizing Scorecard (6-factor, 0-100 points)
| Factor | Points | Description |
|--------|--------|-------------|
| Safety Violations | 0-25 | OSHA violation count, severity, recency |
| Industry Density | 0-15 | Existing union presence in NAICS sector |
| Geographic Presence | 0-15 | Union activity in state |
| Establishment Size | 0-15 | Sweet spot 100-500 employees |
| NLRB Momentum | 0-15 | Recent organizing activity nearby |
| Government Contracts | 0-15 | NY State & NYC contract funding |

**Government Contracts Scoring:**
- $5M+ funding: 10 base points
- $1M+ funding: 7 base points
- $100K+ funding: 4 base points
- Any funding: 2 base points
- Bonus: +5 for 5+ contracts, +3 for 2+ contracts

### 2. AFSCME NY Organizing Targets
- **5,428 targets** identified from 990 + contract data
- **$18.35B** total government funding
- **47 TOP tier**, 414 HIGH tier targets
- Priority scoring based on employee count, funding, sector alignment

**Priority Tiers:**
- TOP (70+): Immediate action recommended
- HIGH (50-69): Strong potential
- MEDIUM (30-49): Worth investigating
- LOW (<30): Lower priority

### 3. Geographic Analysis
- MSA/Metro area analysis with union density %
- City-level employer search
- CBSA mapping (40.8% of employers mapped)
- Metro dropdown filter in UI

### 4. Membership Deduplication
- Raw 70.1M → Deduplicated 14.5M
- Matches BLS within 1.5%
- Handles hierarchy (federation → international → local)
- Canadian member exclusion, retiree adjustment

### 5. Historical Trends (2010-2024)
- 16 years of OLMS LM filings
- National, state, affiliation breakdowns
- Election win rate trends
- Chart.js visualizations in Trends tab

### 6. Public Sector Coverage
- 98.3% of EPI benchmark covered
- 50 of 51 states within ±15%
- NEA/AFT state affiliate research
- Form 990 revenue validation

---

## Frontend Interfaces

| File | Purpose |
|------|---------|
| `frontend/labor_search_v6.html` | Main search interface (6 tabs) |
| `frontend/labor_search_v6_osha.html` | OSHA-enhanced version |
| `files/organizer_v5.html` | Organizing targets/scorecard UI |

**UI Tabs:** Employers, Unions, NLRB, OSHA, Public Sector, Trends

---

## Key Views

```sql
-- Deduplicated membership
SELECT * FROM v_union_members_deduplicated;

-- State public sector comparison
SELECT * FROM v_state_epi_comparison;

-- Union name lookup
SELECT * FROM v_union_name_lookup WHERE confidence = 'HIGH';

-- Public sector by state
SELECT state, SUM(members) FROM ps_union_locals GROUP BY state;

-- OSHA organizing targets
SELECT * FROM v_osha_organizing_targets WHERE score >= 50;
```

---

## Reference Documentation

| Document | Purpose |
|----------|---------|
| `LABOR_PLATFORM_ROADMAP_v10.md` | Current roadmap, future phases |
| `docs/METHODOLOGY_SUMMARY_v8.md` | Complete methodology reference |
| `EPI_BENCHMARK_METHODOLOGY.md` | EPI benchmark explanation |
| `PUBLIC_SECTOR_SCHEMA_DOCS.md` | Public sector schema reference |
| `docs/AFSCME_NY_CASE_STUDY.md` | Organizing targets feature docs |
| `docs/FORM_990_FINAL_RESULTS.md` | 990 methodology results |
| `docs/EXTENDED_ROADMAP.md` | Future checkpoints H-O |

---

## Coverage Acceptance Criteria

| Status | Criteria |
|--------|----------|
| COMPLETE | Within ±15% of EPI benchmark |
| NEEDS REVIEW | 15-25% variance |
| INCOMPLETE | >25% variance without documentation |

---

## Starting the Platform

```cmd
cd C:\Users\jakew\Downloads\labor-data-project
py -m uvicorn api.labor_api_v6:app --reload --port 8000
```

Open `frontend/labor_search_v6.html` in browser.
API docs: http://localhost:8000/docs
