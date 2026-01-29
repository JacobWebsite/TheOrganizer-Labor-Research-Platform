# Labor Relations Research Platform - Claude Context

## Quick Reference for Claude/Claude Code

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

### Key Tables
| Table | Description | Key Columns |
|-------|-------------|-------------|
| `unions_master` | All OLMS union filings | f_num, union_name, members, sector, state |
| `f7_employers_deduped` | Employer bargaining notices (deduplicated) | employer_id, employer_name, latest_unit_size, exclude_from_counts |
| `state_coverage_comparison` | Coverage vs EPI benchmarks by state | state, platform_private, platform_public, epi_private, epi_public |
| `epi_union_membership` | EPI/BLS union membership data | year, geo_name, demographic_group, group_value, measure, value |
| `federal_bargaining_units` | FLRA federal employee data | unit_id, agency_name, total_in_unit |
| `osha_establishments` | OSHA inspection data with 6-digit NAICS | estab_name, naics_code, ein |

### Current Coverage (January 2026, excl DC)
| Sector | Platform | EPI Benchmark | Coverage |
|--------|----------|---------------|----------|
| Private | 5,962,055 | 7,211,458 | 82.7% |
| Public | 5,298,619 | 6,995,000 | 75.7% |
| Total | 11,260,674 | 14,206,458 | 79.3% |

### Data Sources by Sector

**Private Sector (~6M):**
- F7 Employer Bargaining Notices (OLMS)
- Deduplicated for multi-employer agreements
- Excludes: SAG-AFTRA signatories, federal employers, duplicates

**Public Sector (~5.3M):**
- Form 990 tax filings (NEA, AFT, SEIU, AFSCME)
- FLRA federal bargaining units (1.28M employees)
- OLMS state/local union LM filings
- NOT from F7 employers

### Key Views
- `v_f7_for_bls_counts` - Only counted F7 records (exclude_from_counts = FALSE)
- `v_multi_employer_groups` - Multi-employer agreement groupings
- `v_employer_naics_enhanced` - Employers with OSHA-enriched NAICS

### API Endpoints (localhost:8001)
- `GET /api/summary` - Platform summary with BLS coverage %
- `GET /api/multi-employer/stats` - Deduplication statistics
- `GET /api/employers/by-naics-detailed/{naics}` - 6-digit NAICS search

### Coverage Acceptance Criteria
- **Target**: ±5% of EPI benchmark
- **Acceptable**: ±10% or up to 15% under
- **Needs Attention**: >15% under or >15% over

### Key Methodology Files
- `docs/methodology/STATE_COVERAGE_METHODOLOGY.md` - State-level coverage methodology
- `docs/METHODOLOGY_SUMMARY_v7.md` - Overall platform methodology
- `data/coverage/FINAL_COVERAGE_BY_STATE.csv` - State coverage data

### Exclusion Reasons (f7_employers_deduped.exclude_reason)
| Reason | Description |
|--------|-------------|
| `SAG_AFTRA_SIGNATORY` | Entertainment industry multi-employer |
| `DUPLICATE_WORKER_COUNT` | Same workers counted multiple times |
| `OUTLIER_WORKER_COUNT` | Unrealistic worker counts |
| `FEDERAL_EMPLOYER` | Federal employees (different jurisdiction) |
| `REPEATED_WORKER_COUNT` | Repeated exact counts across filings |
| `CORRUPTED_DATA` | Data quality issues |

### Project Version
- API: v6.4
- Last Updated: January 2026
- GitHub: https://github.com/JacobWebsite/TheOrganizer-Labor-Research-Platform
