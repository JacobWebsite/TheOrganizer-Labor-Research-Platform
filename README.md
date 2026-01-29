# Labor Relations Research Platform

**Version:** 6.4
**Last Updated:** January 28, 2026
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

| Sector | Platform | EPI Benchmark | Coverage |
|--------|----------|---------------|----------|
| **Private** | 5,962,055 | 7,211,458 | **82.7%** |
| **Public** | 5,298,619 | 6,995,000 | **75.7%** |
| **Total** | 11,260,674 | 14,206,458 | **79.3%** |

*Excludes DC due to federal HQ effects*

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

- **OLMS LM Filings:** 331,000+ union financial reports (2010-2025)
- **F-7 Employer Notices:** 63,000+ deduplicated employers with bargaining units
- **FLRA Federal Data:** 1.28M federal employees in 2,183 bargaining units
- **EPI/BLS Benchmarks:** State-level union membership data
- **OSHA Integration:** 6-digit NAICS codes for 20,090 employers

### Key Capabilities

- Track union membership and financial trends
- Analyze officer/employee compensation across 26,000+ organizations
- Link unions to employers through F-7 bargaining notices
- Compare coverage against BLS/EPI benchmarks by state
- Multi-employer agreement deduplication (reduced 203% → 82.7% of BLS)

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

### Key Tables

| Table | Records | Description |
|-------|---------|-------------|
| `unions_master` | 26,665 | Union metadata with sector, members, F7 linkage |
| `f7_employers_deduped` | 63,118 | Deduplicated employers with exclusion flags |
| `state_coverage_comparison` | 51 | Coverage vs EPI benchmarks by state |
| `epi_union_membership` | 1.4M | EPI/BLS union membership data |
| `federal_bargaining_units` | 2,183 | FLRA federal employee data |
| `lm_data` | 331,238 | Union LM filings (2010-2025) |

### Key Views

| View | Purpose |
|------|---------|
| `v_f7_for_bls_counts` | Only counted F7 records (exclude_from_counts = FALSE) |
| `v_multi_employer_groups` | Multi-employer agreement groupings |
| `v_employer_naics_enhanced` | Employers with OSHA-enriched 6-digit NAICS |

---

## Project Structure

```
labor-data-project/
├── CLAUDE.md                 # Quick reference for Claude/Claude Code
├── README.md                 # This file
├── api/
│   └── labor_api_v6.py       # FastAPI v6.4 - Main API
├── frontend/
│   └── labor_search_v6_osha.html  # Web interface
├── docs/
│   ├── coverage/             # State coverage CSVs
│   │   ├── FINAL_COVERAGE_BY_STATE.csv
│   │   └── COVERAGE_REFERENCE_ANNOTATED.csv
│   ├── methodology/          # Methodology documentation
│   │   └── STATE_COVERAGE_METHODOLOGY.md
│   └── [35+ markdown docs]   # Session summaries, status reports
├── scripts/
│   ├── analysis/      (33)   # Multi-employer, coverage analysis
│   ├── coverage/      (16)   # Public/private sector scripts
│   ├── etl/           (30)   # OSHA, NAICS, data loading
│   ├── federal/        (9)   # Federal checkpoint scripts
│   ├── maintenance/   (95)   # Check, fix, update scripts
│   └── matching/      (19)   # NLRB, F7 matching scripts
├── data/                     # Raw data files (gitignored)
├── sql/                      # SQL scripts
└── archive/                  # Old versions, historical files
```

---

## Data Sources

### Private Sector (~6M workers)
- **Source:** F-7 Employer Bargaining Notices (OLMS)
- **Deduplication:** Multi-employer agreements, SAG-AFTRA signatories removed
- **Exclusions:** Federal employers, outliers, corrupted data

### Public Sector (~5.3M workers)
- **Source:** Form 990 tax filings (NEA, AFT, SEIU, AFSCME)
- **Source:** FLRA federal bargaining units (1.28M employees)
- **Source:** OLMS state/local union LM filings
- **Note:** NOT from F-7 employers (different jurisdiction)

### Exclusion Categories (f7_employers_deduped)

| exclude_reason | Description |
|----------------|-------------|
| `SAG_AFTRA_SIGNATORY` | Entertainment industry multi-employer |
| `DUPLICATE_WORKER_COUNT` | Same workers counted multiple times |
| `OUTLIER_WORKER_COUNT` | Unrealistic worker counts |
| `FEDERAL_EMPLOYER` | Federal employees (CSRA jurisdiction) |
| `REPEATED_WORKER_COUNT` | Repeated exact counts across filings |

---

## API Endpoints (v6.4)

### Core Endpoints
| Endpoint | Description |
|----------|-------------|
| `GET /api/summary` | Platform summary with BLS coverage % |
| `GET /api/unions` | Search unions |
| `GET /api/employers` | Search employers |
| `GET /api/employer/{id}` | Employer details |

### Multi-Employer Endpoints
| Endpoint | Description |
|----------|-------------|
| `GET /api/multi-employer/stats` | Deduplication statistics |
| `GET /api/multi-employer/groups` | Multi-employer agreement groups |

### NAICS Endpoints
| Endpoint | Description |
|----------|-------------|
| `GET /api/naics/stats` | NAICS enrichment statistics |
| `GET /api/employers/by-naics-detailed/{naics}` | 6-digit NAICS search |

---

## Coverage Acceptance Criteria

| Status | Criteria |
|--------|----------|
| **Target** | ±5% of EPI benchmark |
| **Acceptable** | ±10% or up to 15% under |
| **Needs Attention** | >15% under or >15% over |

Current status: **Private (82.7%)** and **Public (75.7%)** are both acceptable.

---

## Sample Queries

```sql
-- Coverage by state
SELECT state, platform_private, epi_private, private_coverage_pct
FROM state_coverage_comparison
WHERE state != 'DC'
ORDER BY private_coverage_pct DESC;

-- Multi-employer groups
SELECT * FROM v_multi_employer_groups
ORDER BY total_workers DESC LIMIT 20;

-- Employers with 6-digit NAICS
SELECT employer_name, naics_detailed, naics_source, latest_unit_size
FROM f7_employers_deduped
WHERE naics_detailed IS NOT NULL
ORDER BY latest_unit_size DESC LIMIT 20;

-- Public sector unions
SELECT union_name, members, state
FROM unions_master
WHERE sector IN ('FEDERAL', 'PUBLIC_SECTOR')
ORDER BY members DESC LIMIT 20;
```

---

## Development Roadmap

### Completed
- [x] Multi-year OLMS data (331K records)
- [x] F-7 employer deduplication (63K employers)
- [x] Multi-employer agreement handling
- [x] OSHA NAICS enrichment (20K employers)
- [x] State coverage comparison framework
- [x] Federal bargaining units (FLRA)
- [x] API v6.4 with deduplication endpoints

### In Progress
- [ ] Public sector gap analysis
- [ ] State-level coverage improvements

### Planned
- [ ] NLRB election data integration
- [ ] Contract expiration tracking
- [ ] Real-time organizing alerts

---

## Resources

- **OLMS Data:** https://www.dol.gov/agencies/olms
- **NLRB Data:** https://www.nlrb.gov/reports/data
- **BLS Union Data:** https://www.bls.gov/cps/cpslutabs.htm
- **EPI Union Stats:** https://www.epi.org/data/
- **FLRA Federal Data:** https://www.flra.gov/

---

## License

This project integrates publicly available federal government data for research purposes.
