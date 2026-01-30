# Labor Relations Research Platform - Claude Context

## Quick Reference for Claude/Claude Code

**Last Updated:** January 29, 2026

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
| Total Members | 14.5M | 14.3M (BLS) | 101.4% ✅ |
| Private Sector | 6.65M | 7.2M | 92% |
| Federal Sector | 1.28M | 1.1M | 116% |
| State/Local Public | 6.9M | 7.0M (EPI) | **98.3%** ✅ |
| States Reconciled | 50/51 | - | 98% ✅ |

### Key Tables

| Table | Records | Description |
|-------|---------|-------------|
| `unions_master` | 26,665 | OLMS union filings |
| `f7_employers_deduped` | 63,118 | Private sector employers |
| `nlrb_elections` | 33,096 | NLRB election records |
| `nlrb_participants` | 30,399 unions | 95.7% matched |
| `epi_state_benchmarks` | 51 | State union benchmarks |
| `manual_employers` | 431 | State-level public sector |

### NEW: Public Sector Schema

| Table | Records | Description |
|-------|---------|-------------|
| `ps_parent_unions` | 24 | International unions (AFSCME, NEA, etc.) |
| `ps_union_locals` | 1,520 | Local unions, councils, chapters |
| `ps_employers` | 7,987 | Public employers by type |
| `ps_bargaining_units` | 438 | Union-employer relationships |

### Employer Types in ps_employers

| Type | Count | Workers |
|------|-------|---------|
| FEDERAL | 3,575 | 1.49M |
| COUNTY | 1,415 | 154K |
| UNIVERSITY | 891 | 191K |
| SCHOOL_DISTRICT | 847 | 74K |
| CITY | 723 | 75K |
| TRANSIT_AUTHORITY | 423 | 59K |
| STATE_AGENCY | 90 | 17K |

### Key Views

```sql
-- Deduplicated membership
SELECT * FROM v_union_members_deduplicated;

-- State public sector comparison
SELECT * FROM v_state_epi_comparison;

-- Union name lookup
SELECT * FROM v_union_name_lookup WHERE confidence = 'HIGH';

-- Public sector by state
SELECT state, SUM(members) FROM ps_union_locals GROUP BY state;
```

### Documentation

| Document | Location |
|----------|----------|
| Methodology v8 | `docs/METHODOLOGY_SUMMARY_v8.md` |
| Project Roadmap v9 | `LABOR_PLATFORM_ROADMAP_v9.md` |
| Public Sector Schema | `PUBLIC_SECTOR_SCHEMA_DOCS.md` |
| Public Sector Methodology | `docs/methodology/PUBLIC_SECTOR_RECONCILIATION_METHODOLOGY.md` |
| EPI Benchmarks | `EPI_BENCHMARK_METHODOLOGY.md` |

### Coverage Acceptance Criteria

| Status | Criteria |
|--------|----------|
| ✅ COMPLETE | Within ±15% of EPI benchmark |
| ⚠️ NEEDS REVIEW | 15-25% variance |
| ❌ INCOMPLETE | >25% variance without documentation |

### API Endpoints (localhost:8001)

- `GET /api/summary` - Platform summary with coverage %
- `GET /api/multi-employer/stats` - Deduplication statistics
- `GET /api/employers/by-naics-detailed/{naics}` - NAICS search
