# Labor Relations Research Platform - Project Status v7

**Date:** January 28, 2026  
**Version:** 7.0 - OSHA Integration Complete  
**Database:** PostgreSQL `olms_multiyear`  
**API Version:** 6.1-osha

---

## Executive Summary

Comprehensive Labor Relations Research Platform integrating multiple federal datasets to analyze workplace organization trends, employer relationships, and labor market dynamics across the United States. The platform now includes full OSHA enforcement data integration with 1M+ establishments, 2.2M violations, and linkage to F-7 employer records.

---

## Recent Session: OSHA Integration (January 28, 2026)

### Phases Completed

| Phase | Task | Result |
|-------|------|--------|
| 1 | Create PostgreSQL schema | 5 tables, 15 indexes |
| 2 | Extract establishments (2012+) | 1,007,217 records |
| 3 | Aggregate violations | 872,163 summary records |
| 4 | Load violation details | 2,245,020 violations ($3.52B penalties) |
| 5 | Load accidents/fatalities | 63,066 accidents (25,082 fatalities) |
| 6 | F-7 employer matching | 60,105 matches (20,029 unique F-7 employers) |
| 7 | Views & API endpoints | 5 views, 7 new API endpoints |

### OSHA Data Summary

| Metric | Value |
|--------|-------|
| Date Range | January 2012 → January 2026 |
| Total Establishments | 1,007,217 |
| Total Violations | 2,245,020 |
| Total Penalties | $3.52 billion |
| Accidents | 63,066 |
| Fatality Incidents | 25,082 |
| F-7 Employers Matched | 20,029 (31.6%) |

### Violation Breakdown

| Type | Count | Penalties |
|------|-------|-----------|
| Serious (S) | 1,393,789 | $2.36B |
| Other (O) | 772,138 | $356M |
| Repeat (R) | 69,585 | $493M |
| Willful (W) | 8,891 | $302M |
| Unclassified (U) | 599 | $2.7M |

### Match Methods Used (F-7 to OSHA)

| Method | Matches | Confidence |
|--------|---------|------------|
| NORMALIZED_NAME_STATE | 18,295 | 0.85 |
| STREET_NUM_ZIP | 17,602 | 0.70 |
| ADDRESS_CITY_STATE | 8,234 | 0.75 |
| FUZZY_TRIGRAM | 5,747 | 0.69 |
| EXACT_NAME_STATE | 4,933 | 0.95 |
| EXACT_NAME_CITY_STATE | 2,053 | 0.90 |
| **Total** | **60,105** | |

---

## Current Data Assets

| Source | Table(s) | Records | Key Data |
|--------|----------|---------|----------|
| OLMS LM Filings | `lm_data` | 2.6M+ | Union financials, membership, officers (2010-2025) |
| F-7 Employer Notices | `f7_employers_deduped` | 63,118 | Employers with union bargaining agreements |
| NLRB Elections | `nlrb_elections`, `nlrb_cases` | 33,096 | Union election results, tallies, participants |
| NLRB ULP Cases | `nlrb_allegations` | 715,805 | Unfair labor practice allegations |
| Voluntary Recognition | `nlrb_voluntary_recognition` | 1,681 | Non-election union recognitions |
| OSHA Enforcement | `osha_establishments` | 1,007,217 | Workplace safety inspections (2012-2026) |
| OSHA Violations | `osha_violations_detail` | 2,245,020 | Violation details with penalties |
| OSHA Accidents | `osha_accidents` | 63,066 | Workplace accidents & fatalities |
| BLS Density | `bls_union_density` | State/industry | Union membership rates |
| Employment Projections | `employment_projections` | NAICS-based | 2023-2033 employment outlook |
| NAICS Crosswalks | `naics_*` | 4,607 | Version mappings 2002→2022 |

---

## Database Schema

```
PostgreSQL: olms_multiyear (localhost)
├── Union Data
│   ├── lm_data (2.6M+ financial filings)
│   ├── unions_master (50,039 unions with sector classification)
│   └── union_sector (sector lookup)
├── Employer Data
│   ├── f7_employers_deduped (63,118 employers)
│   ├── discovered_employers (new unions from research)
│   └── employer_ein_crosswalk (EIN registry - ready for 990/SEC)
├── NLRB Data
│   ├── nlrb_cases, nlrb_elections, nlrb_tallies
│   ├── nlrb_participants, nlrb_allegations
│   └── nlrb_voluntary_recognition
├── OSHA Data
│   ├── osha_establishments (1M+)
│   ├── osha_violation_summary (872K)
│   ├── osha_violations_detail (2.2M)
│   ├── osha_accidents (63K)
│   └── osha_f7_matches (60K)
├── Reference Data
│   ├── naics_version_crosswalk, naics_sic_crosswalk
│   └── naics_codes_reference
└── Views (40+)
    ├── v_employer_safety_profile
    ├── v_osha_organizing_targets
    ├── v_osha_state_summary
    ├── v_osha_high_severity_recent
    └── v_osha_establishment_search
```

---

## API Endpoints (v6.1-osha)

### OSHA Endpoints (New)

| Endpoint | Description |
|----------|-------------|
| `GET /api/osha/summary` | Database-wide OSHA statistics |
| `GET /api/osha/establishments/search` | Search with filters (state, union_status, risk_level) |
| `GET /api/osha/establishments/{id}` | Detailed info + violations + accidents |
| `GET /api/osha/by-state` | State-level summary statistics |
| `GET /api/osha/high-severity` | Recent willful/repeat violations |
| `GET /api/osha/organizing-targets` | Non-union establishments with violations |
| `GET /api/osha/employer-safety/{f7_id}` | Safety profile for F-7 employer |

### Existing Endpoints

| Category | Endpoints |
|----------|-----------|
| Lookups | `/api/lookups/sectors`, `/affiliations`, `/states`, `/naics-sectors` |
| Density | `/api/density/naics/{code}`, `/api/density/all` |
| Projections | `/api/projections/naics/{code}`, `/top`, `/occupations/{code}` |
| Employers | `/api/employers/search`, `/fuzzy-search`, `/{id}` |
| Unions | `/api/unions/search`, `/{f_num}`, `/locals/{affiliation}` |
| NLRB | `/api/nlrb/summary`, `/elections/*`, `/ulp/*` |
| Voluntary Recognition | `/api/vr/stats/*`, `/search`, `/{case_number}` |
| Health | `/api/health` |

**Total: 45 endpoints**

---

## Key Accomplishments

### Data Quality
- **Member Reconciliation**: Reduced overcounting from 70.1M to 14.5M (within 1.5% of BLS benchmark)
- **F7-to-LM Match Rate**: 97.6% through temporal expansion (2010-2025)
- **Geocoding**: 150,000+ employers geocoded (75.8% success rate)
- **OSHA-F7 Linkage**: 31.6% of F-7 employers linked to safety data

### Infrastructure
- EIN crosswalk table ready for Form 990, SEC, Mergent data
- Normalized name columns with trigram indexes
- Multi-method matching framework (exact, normalized, fuzzy, address-based)

---

## Views Created (OSHA)

| View | Rows | Description |
|------|------|-------------|
| `v_employer_safety_profile` | 58,309 | F-7 employers with full OSHA safety data |
| `v_osha_organizing_targets` | 24,841 | Non-union establishments with significant violations |
| `v_osha_state_summary` | 58 | State-level OSHA statistics |
| `v_osha_high_severity_recent` | 11,127 | Willful/repeat violations (last 2 years) |
| `v_osha_establishment_search` | 1,007,217 | Full establishment search with all metrics |

---

## Next Steps

### Immediate Priority

| Task | Effort | Description |
|------|--------|-------------|
| Update web interface | 4-6 hrs | Display OSHA data in employer search results |
| OSHA indicators | 2-3 hrs | Add safety badges/icons to employer cards |
| OSHA dashboard | 4-6 hrs | Create dedicated safety monitoring view |
| Improve F-7 match rate | 4-8 hrs | Additional matching methods (currently 31.6%) |

### Data Integration Options

| Source | Value | Effort | Description |
|--------|-------|--------|-------------|
| **Form 990 (IRS)** | 🔴 HIGH | 8-12 hrs | EINs for unions, public sector financial data |
| **Mergent Intellect** | 🔴 HIGH | 16-24 hrs | DUNS, corporate hierarchies, employee counts |
| **SEC EDGAR** | 🟡 MED | 12-16 hrs | Public company financials, labor disclosures |
| **DOL WHD** | 🟡 MED | 8-12 hrs | Wage & hour violations by employer |
| **BLS QCEW** | 🟡 MED | 8-12 hrs | Establishment employment by NAICS/county |
| **State Labor Data** | 🟡 MED | 20-40 hrs | Public sector unions (CA PERB, NY PERB, etc.) |
| **FMCS Arbitration** | 🟢 LOW | 6-10 hrs | Arbitration cases, mediator data |
| **Census Business Patterns** | 🟢 LOW | 4-6 hrs | Establishment counts by geography |

### Feature Development

| Feature | Effort | Description |
|---------|--------|-------------|
| Organizing Target Scoring | 20-30 hrs | ML-based likelihood scores |
| Corporate Hierarchy Mapping | 12-16 hrs | Link subsidiaries to parents |
| Geographic Clustering | 8-12 hrs | Union density hotspots/gaps |
| Contract Expiration Tracking | 6-10 hrs | Negotiation alerts |
| Industry Trend Dashboard | 8-12 hrs | Sector-level analytics |

---

## Technical Notes

### Database Connection
```python
DB_CONFIG = {
    'host': 'localhost',
    'dbname': 'olms_multiyear',
    'user': 'postgres',
    'password': 'Juniordog33!'
}
```

### Running the API
```powershell
cd C:\Users\jakew\Downloads\labor-data-project\api
py -m uvicorn labor_api_v6:app --host 0.0.0.0 --port 8001
```

### Key Files
| File | Location |
|------|----------|
| API | `api/labor_api_v6.py` |
| OSHA Source | `C:\Users\jakew\Downloads\osha_enforcement.db` |
| NAICS Crosswalks | `naics_crosswalks/` |
| Load Scripts | `load_osha_*.py` |

### Known Limitations
- OSHA `union_status` Y/N data only available through 2016
- F-7 to OSHA match rate is 31.6% (room for improvement)
- Some OSHA establishments lack NAICS codes

---

## Data Sources Reference

| Source | URL | Update Frequency |
|--------|-----|------------------|
| OLMS LM Filings | https://www.dol.gov/agencies/olms | Annual |
| F-7 Notices | https://www.dol.gov/agencies/olms | Continuous |
| NLRB Cases | https://www.nlrb.gov/cases | Continuous |
| OSHA Enforcement | https://www.osha.gov/data | Weekly |
| BLS Union Membership | https://www.bls.gov/cps | Annual |
| Census NAICS | https://www.census.gov/naics | Every 5 years |

---

## Version History

| Version | Date | Changes |
|---------|------|---------|
| 7.0 | 2026-01-28 | OSHA integration complete (1M+ establishments) |
| 6.1 | 2026-01-27 | Voluntary recognition integration |
| 6.0 | 2026-01-25 | NLRB data integration |
| 5.0 | 2026-01-23 | F-7 employer geocoding |
| 4.0 | 2026-01-20 | BLS density integration |
| 3.0 | 2026-01-15 | Unified database schema |

---

*Generated: January 28, 2026*
