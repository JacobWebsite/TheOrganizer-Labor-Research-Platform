# Labor Relations Research Platform - Project Roadmap v8

**Date:** January 28, 2026  
**Status:** Active Development  
**Goal:** Comprehensive organizing target identification system

---

## Executive Summary

The platform has achieved **96.2% F-7 employer matching** and **95.7% NLRB participant matching** (exceeding the 80% target). The union names crosswalk proved highly effective, enabling rapid matching of 29,089 union petitioner records.

**Key Achievements This Session:**
- NLRB union petitioner matching: 51.3% → **95.7%** (29,089 of 30,399 records)
- Confirmed comprehensive BLS/EPI data already loaded (1.4M+ EPI records)
- Industry-occupation growth matrix available (113,842 records)

---

## Current Platform Status

### Data Assets

| Asset | Records | Match Rate | Status |
|-------|---------|------------|--------|
| F-7 Employers | 63,118 | 96.2% matched | ✅ Complete |
| NLRB Elections | 33,096 | - | ✅ Loaded |
| **NLRB Participants** | **30,399 unions** | **95.7% matched** | ✅ **COMPLETE** |
| OLMS Unions | 26,665 | - | ✅ Complete |
| FLRA Federal Units | 2,183 | - | ✅ Complete |
| Union Names Crosswalk | 171,481 | 56.7% NLRB coverage | ✅ Loaded |
| EPI Union Membership | 1,420,064 | - | ✅ **Already Loaded** |
| BLS Industry-Occupation Matrix | 113,842 | - | ✅ **Already Loaded** |

### BLS/EPI Data Already Available

| Table | Records | Coverage |
|-------|---------|----------|
| epi_union_membership | 1,420,064 | National 1973-2024, state demographics |
| bls_state_union_rates | 2,550 | State membership 2000-2024 |
| bls_industry_union_density | 5,472 | Industry density 1983-2024 |
| bls_occupation_union_density | 4,328 | Occupation rates 2000-2024 |
| bls_national_union_trends | 9,832 | Govt/Private 1983-2024 |
| bls_industry_projections | 424 | Employment 2024→2034 |
| bls_occupation_projections | 1,113 | Occupations 2024→2034 |
| bls_industry_occupation_matrix | 113,842 | Industry×Occupation growth |
| unionstats_state | 10,710 | State/sector 1983-2024 |
| unionstats_industry | 281 | Industry detail 2024 |

### BLS Alignment

| Sector | Platform | BLS Benchmark | Coverage |
|--------|----------|---------------|----------|
| Total Members | 14.5M | 14.3M | 101.4% ✅ |
| Private Sector | 6.65M | 7.2-7.3M | 91-92% |
| Federal Sector | 1.28M | 1.1M | 116% |
| State/Local Public | 5.5M | 5.6M | 98.4% ✅ |

---

## NLRB Matching Results (Completed Jan 28, 2026)

### Summary
- **Target:** 80%+ match rate
- **Achieved:** 95.7% (29,089 of 30,399 union petitioners)
- **Improvement:** From ~50% baseline to 95.7%

### Match Method Breakdown

| Category | Records | % of Matched |
|----------|---------|--------------|
| Crosswalk Exact (high conf) | 15,588 | 53.6% |
| Crosswalk Affiliation | 10,047 | 34.5% |
| Pattern Match | 3,454 | 11.9% |

### Top Matched Unions

| Rank | Union | F# | Records |
|------|-------|-----|---------|
| 1 | SEIU | 137 | 2,323 |
| 2 | IAM Machinists | 107 | 1,123 |
| 3 | Workers United | 518899 | 1,074 |
| 4 | SPFPA | 518836 | 961 |
| 5 | UFCW | 76 | 718 |
| 6 | USW Steelworkers | 117 | 680 |
| 7 | CWA | 78 | 528 |
| 8 | AFSCME | 92 | 470 |
| 9 | Teamsters | 93 | 431 |
| 10 | UAW | 105 | 395 |

### Unmatched Analysis (1,310 records)
- NULL entries: 187 (cannot be matched)
- Law firms: ~120 (correctly excluded - these are attorneys, not unions)
- Small independent unions: ~1,000

### Scripts Created
- `nlrb_crosswalk_matching.py` - Phase 1 exact matching
- `nlrb_matching_phase2.py` - Affiliation-based matching  
- `nlrb_matching_phase3.py` - UE, nurses, SAG-AFTRA
- `nlrb_matching_phase4.py` - Additional affiliations
- `nlrb_matching_phase5.py` - Extended patterns
- `nlrb_matching_phase6.py` - Final cleanup
- `nlrb_final_summary.py` - Results summary

---

## Remaining Priorities

### High Priority

| Task | Status | Notes |
|------|--------|-------|
| NLRB Crosswalk Matching | ✅ COMPLETE | 95.7% achieved |
| EPI Data Load | ✅ ALREADY DONE | 1.4M+ records |
| Industry-Occupation Matrix | ✅ ALREADY DONE | 113K records |
| OSHA Data Download | 🔲 Not Started | Safety targeting |

### Medium Priority

| Task | Hours | Impact |
|------|-------|--------|
| OSHA-to-F7 Matching | 8-10 | Violation linkage |
| Similar Firm Algorithm | 10-15 | Target generation |
| Union-Research Skill Updates | 4-6 | Better discovery |

### Lower Priority

| Task | Hours | Impact |
|------|-------|--------|
| Mergent/Data Axle Integration | 15-20 | Corporate hierarchies |
| Target Search UI | 12-15 | User interface |
| Predictive Scoring | 15-20 | ML-based targets |

---

## Success Metrics

| Metric | Previous | Current | Target |
|--------|----------|---------|--------|
| F-7 Match Rate | 96.2% | 96.2% | 98%+ |
| NLRB Participant Match | ~50% | **95.7%** | 80%+ ✅ |
| BLS Coverage | 91-92% | 91-92% | 95%+ |
| Organizing Targets Generated | 0 | 0 | 10,000+ |
| OSHA-Linked Employers | 0 | 0 | 50,000+ |

---

## Available Tools

| Tool | Best For |
|------|----------|
| union_names_crosswalk | Name resolution, matching |
| Desktop Commander | PostgreSQL, file ops |
| union-research skill | Web research, discovery |
| xlsx skill | Excel/CSV parsing |
| Web Search | OSHA, SEC, news |
| frontend-design skill | UI development |

---

## Database Reference

### Key Tables
```
f7_employers_deduped       - 63,118 private sector employers
nlrb_participants          - 1,906,542 case participants (30,399 union petitioners)
nlrb_elections             - 33,096 election records
unions_master              - 26,665 OLMS unions
union_names_crosswalk      - 171,481 name variations
v_union_name_lookup        - 100,023 high-confidence lookups
epi_union_membership       - 1,420,064 EPI historical data
bls_industry_occupation_matrix - 113,842 growth projections
```

### Connection
```python
psycopg2.connect(
    host='localhost',
    dbname='olms_multiyear',
    user='postgres',
    password='Juniordog33!'
)
```

---

*Last Updated: January 28, 2026*
