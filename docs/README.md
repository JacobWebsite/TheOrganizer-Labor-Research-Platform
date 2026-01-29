# Labor Relations Data Platform

**Last Updated:** January 24, 2026  
**Status:** Active Development  
**Primary Database:** PostgreSQL (`olms_multiyear`)

---

## Quick Start (New Unified Interface)

```cmd
cd C:\Users\jakew\Downloads\labor-data-project
py -m uvicorn api.labor_api_v6:app --reload --port 8000
```

Then open `frontend/labor_search_v6.html` in your browser.

---

## Development Checkpoints

To continue development, start a new Claude chat and say:

> "Continue with Checkpoint [X]"

### Data Quality & UI
| ID | Focus | Description |
|----|-------|-------------|
| **A** | Data Quality | Fix union display names, local number handling |
| **B** | Geographic | Add Leaflet maps for employer visualization |
| **C** | Charts | Chart.js for financial trends, elections |
| **D** | Performance | Caching, pagination, materialized views |
| **E** | Search | Full-text search, cross-reference queries |
| **F** | Export | CSV/PDF export, bulk data API |
| **G** | BLS Data | Surface density data in interface |

### External Data Integration
| ID | Focus | Description |
|----|-------|-------------|
| **H** | Mergent Intellect | Employer enrichment - revenue, NAICS, hierarchy |
| **I** | IRS 990 Forms | Union exec compensation, investments, PACs |
| **J** | SEC/Edgar | Public company labor disclosures |
| **K** | OSHA | Workplace safety records |
| **L** | FEC/Political | PAC spending, lobbying data |
| **M** | Contracts | Actual CBA terms and expirations |
| **N** | News | Real-time monitoring, organizing alerts |
| **O** | Predictive | Election forecasting, organizing likelihood |

**See:** `EXTENDED_ROADMAP.md` for detailed descriptions  
**See:** `PROJECT_STATUS_SUMMARY.md` for current state

---

## Overview

This platform integrates multiple federal government databases to create a comprehensive analytical framework for understanding labor relations in the United States. The system combines Department of Labor financial filings, NLRB election data, employer bargaining notices, and BLS density statistics spanning four decades.

### Key Capabilities

- Track union membership and financial trends (2010-2025)
- Analyze officer/employee compensation across 26,000+ organizations
- Link unions to employers through F-7 bargaining notices (71K+ deduplicated employers)
- **91.3% affiliation match rate** on employer data (text-based parsing for unions without file numbers)
- Compare union density by state, industry, and demographics (1983-2024)
- **Local number display** showing actual union local designations (e.g., "SEIU LU 1199")

---

## Quick Start

### Web Interface (Recommended)

```cmd
cd C:\Users\jakew\Downloads\labor-data-project
py -m uvicorn labor_search_api:app --host 0.0.0.0 --port 8000
```

Then open `labor_search.html` in your browser.

**API Documentation:** http://localhost:8000/docs

### Connect to PostgreSQL

```bash
# Windows
psql -U postgres -d olms_multiyear
# Password: Juniordog33!
```

### Key Tables/Views

| Resource | Records | Description |
|----------|---------|-------------|
| f7_employers_deduped | 71,085 | Deduplicated employers (2020-2025) |
| v_employer_search | 71,085 | Employer search with affiliations |
| v_union_local_search | ~18,000 | Union locals with local numbers |
| lm_data | 331,000+ | LM financial filings (all years) |

### Key Queries

```sql
-- Search employers by affiliation
SELECT employer_name, city, state, bargaining_unit_size, affiliation
FROM v_employer_search
WHERE affiliation = 'SEIU'
ORDER BY bargaining_unit_size DESC LIMIT 20;

-- Search union locals with local numbers
SELECT local_display_name, local_number, city, state, members, f7_employer_count
FROM v_union_local_search
WHERE affiliation = 'CWA' AND members > 1000
ORDER BY members DESC;

-- Top affiliations by F-7 employer count
SELECT affiliation, affiliation_name, local_count, f7_employer_count
FROM v_affiliation_summary
WHERE f7_employer_count > 0
ORDER BY f7_employer_count DESC;
```

---

## Database Schema

### Core Tables

| Table | Records | Description |
|-------|---------|-------------|
| `lm_data` | 331,238 | Union LM filings (2010-2025) |
| `f7_employers` | 150,388 | Geocoded F-7 employer notices |
| `unions_master` | 26,665 | Union metadata with F-7 linkage |
| `union_hierarchy` | 18,067 | **Deduplication flags for each union** |

### Detail Tables

| Table | Records | Description |
|-------|---------|-------------|
| `ar_disbursements_emp_off` | ~500K | Officer & employee compensation |
| `ar_membership` | 216,508 | Membership by category |
| `ar_assets_investments` | 304,816 | Investment holdings |
| `ar_disbursements_total` | 216,372 | Spending by category |

### Reference Tables

| Table | Records | Description |
|-------|---------|-------------|
| `union_sector` | 6 | Sector classifications |
| `union_match_status` | 6 | F-7 match status codes |

### Views (Deduplicated)

| View | Purpose |
|------|---------|
| `v_union_members_counted` | **Use for totals** - only counted unions |
| `v_union_members_deduplicated` | All unions with dedup flags |
| `v_hierarchy_summary` | Summary by hierarchy level |
| `v_membership_by_sector` | Totals by sector |
| `v_membership_by_affiliation` | Totals by affiliation |
| `v_membership_by_state` | Totals by state |
| `v_deduplication_comparison` | Raw vs deduplicated vs BLS |

---

## Member Deduplication

### The Problem

Raw LM data reports **70.1 million** members, but the BLS benchmark is only **14.3 million**. This 4.9x overcount occurs because:

1. **Hierarchy double-counting**: AFL-CIO reports 13.4M, but SEIU (part of AFL-CIO) also reports 1.9M, and SEIU locals also report their members
2. **Multi-employer bargaining**: Building trades locals counted once per employer relationship
3. **Data quality issues**: Some unions report erroneous values (e.g., ACT reported 3.6M instead of 22K)

### The Solution

The `union_hierarchy` table classifies each union and flags whether to count its members:

| Level | Count | Counted | Description |
|-------|-------|---------|-------------|
| FEDERATION | 312 | 0 | AFL-CIO, departments (aggregate other unions) |
| INTERNATIONAL | 60 | 13.4M | SEIU, IBT, UAW, etc. (primary count level) |
| INTERMEDIATE | 3 | 0 | District councils |
| LOCAL | 17,709 | 1.1M | Local unions (count only independents) |
| **TOTAL** | | **14.5M** | +1.5% vs BLS |

### Key Fields in `union_hierarchy`

```sql
SELECT f_num, union_name, hierarchy_level, count_members, count_reason
FROM union_hierarchy
WHERE f_num = '137';  -- SEIU

-- Returns:
-- f_num: 137
-- union_name: SERVICE EMPLOYEES
-- hierarchy_level: INTERNATIONAL
-- count_members: TRUE
-- count_reason: International union - primary count level
```

See [MEMBER_DEDUPLICATION.md](docs/MEMBER_DEDUPLICATION.md) for full methodology.

---

## F-7 Employer Integration

### Data Loaded

| Table | Records | Description |
|-------|---------|-------------|
| `f7_employers` | 150,388 | Unique employers from F-7 notices |
| `unions_master` | 26,665 | Unions with F-7 employer counts |

### Geocoding Stats

- **Total employers:** 150,388
- **Geocoded:** 110,996 (73.8%)
- **Top states:** CA (17,799), NY (16,516), IL (14,817)

### Sample Queries

```sql
-- Employers by state
SELECT state, COUNT(*) as employers, SUM(latest_unit_size) as workers
FROM f7_employers
WHERE state IS NOT NULL
GROUP BY state
ORDER BY employers DESC;

-- Unions with most employers
SELECT f_num, union_name, f7_employer_count, f7_total_workers
FROM unions_master
WHERE f7_employer_count > 100
ORDER BY f7_employer_count DESC;

-- Geocoded employers for mapping
SELECT employer_name, latitude, longitude, latest_union_name
FROM f7_employers
WHERE latitude IS NOT NULL
LIMIT 1000;
```

---

## Project Structure

```
labor-data-project/
├── api/                   # FastAPI endpoints
│   ├── labor_api_v6.py    # LATEST - Full platform API
│   └── vr_api_endpoints.py
├── archive/               # Historical/old files
│   ├── bls_phases/        # Old BLS phase folders
│   ├── old_scripts/       # Checkpoint scripts, old versions
│   └── Claude Ai union project/
├── data/                  # All data files
│   ├── bls/               # BLS raw data
│   ├── crosswalk/         # Union-employer linkage databases
│   ├── f7/                # F-7 employer databases
│   ├── nlrb/              # NLRB election data
│   ├── olms/              # OLMS reference data
│   ├── raw/               # Raw downloads (XML, web search, etc.)
│   ├── unionstats/        # BLS density xlsx (40 years)
│   └── unified_labor.db   # SQLite unified database
├── docs/                  # Documentation and markdown files
│   ├── README.md          # This file
│   └── *.md               # All methodology docs
├── frontend/              # Web interface HTML
│   ├── labor_search_v6.html  # LATEST - Full search UI
│   └── nlrb_explorer.html
├── output/                # Generated exports
│   ├── *.csv              # All CSV outputs
│   └── *.xlsx             # Excel exports
├── scripts/               # Python scripts by function
│   ├── analysis/          # Coverage analysis, sector checks
│   ├── export/            # CSV/Excel generation
│   ├── import/            # Data loading, transformations
│   └── maintenance/       # Verification, tests, checks
├── sql/                   # SQL files
│   ├── schema/            # Table/view creation
│   └── queries/           # Query files
├── src/                   # Legacy Python source
├── start-claude.bat       # Start Claude Code helper
└── union-research.skill   # Skill configuration
```

---

## Scripts Reference

All scripts organized under `scripts/` directory:

### Analysis (`scripts/analysis/`)
| Script | Purpose |
|--------|---------|
| `analyze_coverage.py` | Private sector coverage vs BLS |
| `federal_deep_dive.py` | Federal sector analysis |
| `sector_final_summary.py` | Sector breakdown summary |

### Import (`scripts/import/`)
| Script | Purpose |
|--------|---------|
| `load_multiyear_olms.py` | Load 331K LM filings |
| `load_f7_data.py` | Load F-7 employers and unions_master |
| `vr_loader_2*.py` | Load voluntary recognition data |
| `recalc_990_*.py` | Form 990 public sector estimates |
| `name_normalizer.py` | Union name standardization |

### Export (`scripts/export/`)
| Script | Purpose |
|--------|---------|
| `export_coverage.py` | Excel coverage export |
| `generate_discovery_reports.py` | 2024 discovery reports |
| `extract_locals_councils.py` | Union locals CSV export |

### Maintenance (`scripts/maintenance/`)
| Script | Purpose |
|--------|---------|
| `verify_discovery_2024.py` | Verify 2024 discoveries |
| `validation_framework.py` | Data validation checks |
| `check_*.py` | Various schema/data checks |
| `test_*.py` | API and query tests |

---

## Integration Status

### Completed

- [x] Multi-year OLMS data (331K records, 2010-2025)
- [x] Financial detail tables (officer pay, membership, investments)
- [x] F-7 employer integration (150K geocoded employers)
- [x] Union-employer crosswalk (unions_master)
- [x] **Member deduplication** (70M → 14.5M, matches BLS)
- [x] Sector classification (PRIVATE, FEDERAL, PUBLIC, RLA, OTHER)

### Pending

- [ ] NLRB election data integration
- [ ] UnionStats density data (40 years)
- [ ] BLS projection data
- [ ] Web dashboard update

---

## Key Metrics (2024)

| Metric | Raw Value | Deduplicated |
|--------|-----------|--------------|
| Filings | 18,082 | 2,238 counted |
| Members | 70.1M | 14.5M |
| Assets | $18.8B | - |
| Receipts | $12.6B | - |

---

## Resources

- **OLMS Data:** https://www.dol.gov/agencies/olms
- **NLRB Data:** https://www.nlrb.gov/reports/data
- **BLS Union Data:** https://www.bls.gov/cps/cpslutabs.htm
- **UnionStats:** https://unionstats.com/
