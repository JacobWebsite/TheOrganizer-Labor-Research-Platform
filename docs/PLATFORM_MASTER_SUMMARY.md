# Labor Relations Research Platform - Master Summary

**Version:** 6.0-unified  
**Last Updated:** January 25, 2026  
**Status:** Production Ready ✅

---

## Project Overview

A comprehensive labor relations research platform integrating multiple federal datasets to analyze workplace organization trends, financial patterns, and employer relationships across the United States. The platform provides unified search, mapping, and analysis capabilities spanning 16 years of data.

---

## Platform Statistics

| Metric | Value |
|--------|-------|
| **Total Unions** | 26,665 |
| **Total Employers** | 71,077 |
| **NLRB Elections** | 32,793 |
| **Election Win Rate** | 68.0% |
| **ULP Cases** | 422,500 |
| **Voluntary Recognition Cases** | 1,681 |
| **API Endpoints** | 38 |
| **Data Coverage** | 2007-2025 |

---

## Data Sources Integrated

| Source | Description | Records | Update Frequency |
|--------|-------------|---------|------------------|
| **OLMS LM Filings** | Union financial reports (LM-2, LM-3, LM-4) | 26,665 unions | Annual |
| **DOL F-7 Notices** | Employer bargaining unit notifications | 71,077 employers | Ongoing |
| **NLRB Elections** | Representation election results | 32,793 elections | Ongoing |
| **NLRB ULP Cases** | Unfair labor practice filings | 422,500 cases | Ongoing |
| **NLRB Voluntary Recognition** | VR notice postings | 1,681 cases | Ongoing |
| **BLS Union Density** | CPS-derived membership rates | All NAICS sectors | Annual |
| **BLS Employment Projections** | 10-year industry/occupation forecasts | 2024-2034 | Decennial |
| **Census Geocoding** | Employer address coordinates | 73.6% success | One-time |

---

## Key Accomplishments

### Data Quality
- **Member Deduplication:** Reduced reported 70.1M to 14.5M actual members (matches BLS within 1.5%)
- **Employer Geocoding:** 73.6% success rate (52,300+ addresses)
- **Cross-Dataset Matching:** 91.3% employer match rate (F7 ↔ NLRB)
- **VR Union Matching:** 86.6% matched to OLMS records

### Technical Infrastructure
- **Unified API:** Single FastAPI server with 38 endpoints
- **Fuzzy Search:** pg_trgm similarity matching for typo tolerance
- **Normalized Search:** Strips Inc/LLC/Corp for better matching
- **Interactive Maps:** Leaflet with marker clustering
- **Real-time Filtering:** Cascading dropdowns with live updates

### Analytical Views
- **15 VR-specific views** for pipeline and trend analysis
- **Combined organizing views** merging elections + voluntary recognition
- **Industry density views** linking NAICS to BLS union rates
- **Employment projection views** for strategic targeting

---

## Architecture

### Current Stack
```
┌─────────────────────────────────────────────────────┐
│                  Web Interface                       │
│              labor_search_v6.html                    │
│     (Tailwind CSS, Leaflet Maps, Chart.js)          │
└─────────────────────┬───────────────────────────────┘
                      │ HTTP/JSON
┌─────────────────────▼───────────────────────────────┐
│                   REST API                           │
│               labor_api_v6.py                        │
│         (FastAPI, 38 endpoints, Port 8001)          │
└─────────────────────┬───────────────────────────────┘
                      │ psycopg2
┌─────────────────────▼───────────────────────────────┐
│                  PostgreSQL                          │
│               olms_multiyear                         │
│    (pg_trgm extension, 40+ views, indexes)          │
└─────────────────────────────────────────────────────┘
```

### Key Files
| File | Lines | Purpose |
|------|-------|---------|
| `labor_api_v6.py` | 1,327 | Unified API server |
| `labor_search_v6.html` | 1,201 | Web interface |
| `schema_v4_employer_search.sql` | ~500 | Database schema |

---

## API Endpoint Summary

| Category | Endpoints | Key Features |
|----------|-----------|--------------|
| **Lookups** | 4 | Sectors, affiliations, states, NAICS |
| **Density** | 2 | Union density by industry |
| **Projections** | 3 | Employment forecasts, top industries |
| **Employers** | 4 | Search, fuzzy, normalized, detail |
| **Unions** | 3 | Search, detail, locals |
| **NLRB Elections** | 7 | Search, map, stats, detail |
| **NLRB ULP** | 2 | Search, by NLRA section |
| **Voluntary Recognition** | 9 | Search, map, pipeline, stats |
| **Combined** | 2 | Elections + VR organizing activity |
| **Platform** | 2 | Summary, health check |

---

## Potential Next Steps

### Tier 1: Quick Wins (1-2 days each)

| Feature | Description | Value |
|---------|-------------|-------|
| **CSV Export** | Download button for search results | High - immediate user need |
| **Date Range Filters** | Add from/to date on all searches | Medium - better filtering |
| **Employer Detail Page** | Dedicated page with full history | Medium - better UX |
| **Bookmark/Save Searches** | Store filter combinations | Medium - power user feature |
| **Print-Friendly Views** | CSS for reports/printing | Low - nice to have |

### Tier 2: Medium Projects (1-2 weeks each)

| Feature | Description | Value |
|---------|-------------|-------|
| **Contract Database** | Track first contract dates after VR/election wins | High - completes organizing lifecycle |
| **News Monitoring** | Link cases to news coverage via API | High - context for cases |
| **Metro-Level Analysis** | CBSA coverage rates using HUD crosswalk | High - geographic insights |
| **Industry Deep-Dive** | Detailed NAICS 4-digit analysis with density | Medium - strategic targeting |
| **Employer Relationships** | Parent/subsidiary linkage detection | Medium - corporate structure |
| **Union Financial Trends** | LM-2 revenue/expense analysis over time | Medium - union health metrics |

### Tier 3: Major Projects (1+ months each)

| Feature | Description | Value |
|---------|-------------|-------|
| **Predictive Analytics** | Model election outcomes, VR likelihood | High - strategic value |
| **Public API** | Rate-limited access for researchers | High - community benefit |
| **Real-time Updates** | Webhook/polling for new NLRB filings | Medium - freshness |
| **Mobile App** | React Native or PWA version | Medium - accessibility |
| **Multi-tenant Auth** | User accounts with saved preferences | Medium - personalization |
| **Data Visualization Dashboard** | D3.js interactive charts/trends | Medium - executive view |

### Tier 4: Integration Opportunities

| Data Source | Description | Complexity |
|-------------|-------------|------------|
| **Mergent Intellect** | Company financials, D&B data | Medium (CUNY access) |
| **IRS 990 Forms** | Nonprofit employer financials (hospitals, universities) | Medium |
| **SEC Filings** | Public company labor disclosures, pension liabilities | Medium |
| **OSHA Records** | Safety violations by employer | Low-Medium |
| **Political Contributions** | FEC/state campaign finance | Medium |
| **BLS QCEW** | Quarterly employment by establishment | Medium |
| **County Business Patterns** | Annual employment by NAICS/geography | Low |

### Tier 5: Research Applications

| Application | Description |
|-------------|-------------|
| **Organizing Success Factors** | What predicts election wins? Industry, unit size, region? |
| **VR vs Election Outcomes** | Compare recognition paths and subsequent outcomes |
| **Employer Resistance Patterns** | ULP filing rates by industry, employer size |
| **Union Growth/Decline** | Which affiliations are growing? Where? |
| **Geographic Clustering** | Hot spots for organizing activity |
| **Industry Transitions** | How do workers move between sectors? |

---

## Running the Platform

### Start API Server
```bash
cd C:\Users\jakew\Downloads\labor-data-project
py -m uvicorn labor_api_v6:app --host 127.0.0.1 --port 8001
```

### Access Points
| Resource | URL |
|----------|-----|
| Web Interface | `labor_search_v6.html` (open in browser) |
| Swagger Docs | http://127.0.0.1:8001/docs |
| Health Check | http://127.0.0.1:8001/api/health |
| Platform Summary | http://127.0.0.1:8001/api/summary |

### Database Connection
```python
DB_CONFIG = {
    'host': 'localhost',
    'port': 5432,
    'database': 'olms_multiyear',
    'user': 'postgres',
    'password': 'Juniordog33!'
}
```

---

## Session History

| Date | Session | Key Accomplishments |
|------|---------|---------------------|
| Jan 2026 | VR Integration | 8 checkpoints: schema, loading, matching, views, API, UI |
| Jan 2026 | NLRB Integration | Elections, ULP, participant matching |
| Jan 2026 | BLS Integration | Union density, employment projections |
| Dec 2025 | Employer Geocoding | 73.6% success, batch processing |
| Dec 2025 | Member Deduplication | Hierarchy analysis, 70.1M → 14.5M |
| Nov 2025 | Initial Platform | OLMS + F7 integration, basic search |

---

## Documentation Index

| Document | Purpose |
|----------|---------|
| `PLATFORM_MASTER_SUMMARY.md` | This file - overall summary |
| `PROJECT_STATUS_v6.md` | Current version status |
| `VR_INTEGRATION_COMPLETE.md` | VR integration details |
| `nlrb_integration_plan.md` | NLRB integration reference |
| `BLS_NAICS_INTEGRATION_PLAN_v2.md` | Density/projections reference |
| `EMPLOYER_GEOCODING_SESSION_SUMMARY.md` | Geocoding details |

---

## Contact & Resources

- **CUNY Resources:** University database access for commercial data
- **UVA Access:** Additional research database access
- **NLRB Data:** https://www.nlrb.gov/reports/graphs-data
- **OLMS Data:** https://www.dol.gov/agencies/olms
- **BLS Data:** https://www.bls.gov/cps/

---

**Platform Status:** OPERATIONAL ✅  
**Ready for:** Production use, future development, research applications
