# AFSCME NY Organizing Targets Case Study

**Labor Relations Research Platform - Case Study**
**Generated:** February 2026

## Executive Summary

This case study demonstrates how the Labor Relations Research Platform identifies potential organizing targets for AFSCME in New York State by cross-referencing government contract data with employer information from IRS 990 filings. The analysis identified **5,428 potential targets** receiving **$18.35 billion** in government funding, with 47 TOP-tier and 414 HIGH-tier priority organizations.

## Data Sources

| Source | Records | AFSCME-Relevant | Value |
|--------|---------|-----------------|-------|
| NY State Contracts | 51,500 | 23,964 | $368.9B |
| NYC Contracts | 49,767 | 24,325 | $11,249B |
| 990 Employers (NY) | 5,942 | 1,271 | - |

## Methodology

### 1. Data Collection

**NY State Contracts** were loaded from Open Book New York (contracts after 01/01/2023). The Excel export contains 51,500 contract records from 15,677 unique vendors.

**NYC Contracts** were fetched from NYC Open Data's Recent Contract Awards API (dataset qyyg-4tf5), containing 49,767 contracts from 13,984 unique vendors.

**990 Employer Data** was extracted from IRS Form 990 XML filings, identifying 5,942 nonprofit employers in New York State.

### 2. Sector Classification

Contracts were flagged as "AFSCME-relevant" based on keyword matching in agency names, vendor names, and contract descriptions:

**AFSCME-Relevant Sectors:**
- Health & Mental Hygiene (hospitals, community health)
- Social Services (DSS, HRA, child services)
- Education (schools, universities, afterschool programs)
- Senior Care (aging services, nursing homes)
- Transit & Transportation
- Parks & Recreation
- Housing & Community Development
- Sanitation & Environmental Services

### 3. Employer Matching

Contract vendors were matched to 990 employers using:
1. **EIN matching** (exact match when available)
2. **Fuzzy name matching** using token set ratio (threshold: 80%)
3. **Name normalization** (uppercase, punctuation removal, LLC/Inc handling)

### 4. Priority Scoring

#### 990-Based Targets (organizing_targets table)
Each target receives a priority score (0-100) based on:

| Factor | Weight | Description |
|--------|--------|-------------|
| Employee Count | 30 pts | Larger employers score higher |
| Government Funding | 20 pts | Higher contract values = more revenue stability |
| Industry Alignment | 20 pts | AFSCME core sectors score higher |
| Multiple Contracts | 10 pts | Repeat contractors = stronger relationships |
| 990 Data Quality | 10 pts | Complete financials enable analysis |
| Geographic Density | 10 pts | Areas with existing AFSCME presence |

#### OSHA-Based Organizing Scorecard (NEW - Enhanced)
The platform now includes an OSHA-based organizing scorecard that integrates government contract data with workplace safety information. This 6-factor scoring system (0-100) includes:

| Factor | Points | Description |
|--------|--------|-------------|
| Safety Violations | 0-25 | OSHA violation count, severity, and recency |
| Industry Density | 0-15 | Existing union presence in NAICS sector |
| Geographic Presence | 0-15 | Union activity in state |
| Establishment Size | 0-15 | Sweet spot 100-500 employees |
| NLRB Momentum | 0-15 | Recent organizing activity nearby |
| **Government Contracts** | **0-15** | **NY State & NYC contract funding (NEW)** |

**Government Contracts Scoring Logic:**
- $5M+ funding: 10 base points
- $1M+ funding: 7 base points
- $100K+ funding: 4 base points
- Any funding: 2 base points
- Bonus: +5 for 5+ contracts, +3 for 2+ contracts
- Maximum: 15 points

**Priority Tiers:**
- **TOP** (70+): Immediate action recommended
- **HIGH** (50-69): Strong potential, prioritize outreach
- **MEDIUM** (30-49): Worth investigating
- **LOW** (<30): Lower priority

## Key Findings

### Overall Statistics

| Metric | Value |
|--------|-------|
| Total Targets | 5,428 |
| TOP Tier | 47 |
| HIGH Tier | 414 |
| MEDIUM Tier | 1,557 |
| Total Funding | $18.35B |
| Est. Employees | 46,899 |
| Avg Priority Score | 34.6 |

### Top 20 Organizing Targets

| Rank | Organization | City | Sector | Score | Employees | Funding |
|------|--------------|------|--------|-------|-----------|---------|
| 1 | Research Foundation for SUNY | Albany | Education | 97.0 | 15,050 | $306.5M |
| 2 | Community Action Org of WNY | Buffalo | Social Services | 93.5 | 532 | $10.2M |
| 3 | Russell Sage College | Troy | Education | 93.0 | 1,207 | $6.6M |
| 4 | AIDS Community Resources Inc | Syracuse | Education | 87.0 | 156 | $25.2M |
| 5 | Albany Schenectady Greene County | Altamont | Education | 87.0 | 191 | $35.8M |
| 6 | YMCA of Geneva | Geneva | Social Services | 83.5 | 67 | $40.5M |
| 7 | United Way of Buffalo & Erie | Buffalo | Social Services | 83.5 | 63 | $119.7M |
| 8 | On Point NYC Inc | New York | Education | 83.0 | 147 | $9.9M |
| 9 | Head Start of Eastern Orange County | Newburgh | Education | 82.0 | 50 | $41.1M |
| 10 | Jacob A. Riis Neighborhood | Long Island City | Senior Care | 82.0 | 246 | $1.4M |
| 11 | Bronx Community College | Bronx | Education | 82.0 | 54 | $27.8M |
| 12 | Inwood Academy Charter School | New York | Education | 79.0 | 227 | $1.6M |
| 13 | Mott Haven Academy Charter | Bronx | Education | 79.0 | 123 | $2.3M |
| 14 | American Dream Charter School | Bronx | Education | 79.0 | 128 | $2.3M |
| 15 | Western NY Library | Amherst | Social Services | 78.5 | 10 | $3,397M* |
| 16 | UJAMAA Community Dev Corp | Mount Vernon | Social Services | 78.5 | 11 | $11.9M |
| 17 | Westchester Community Opportunity | Elmsford | Social Services | 76.5 | 469 | $0.5M |
| 18 | Rural Health Network of SCNY | Binghamton | Social Services | 75.5 | 63 | $1.9M |
| 19 | Properties with Purpose Inc | New York | Social Services | 75.5 | - | $3.7M |
| 20 | Truxton Academy Charter | Truxton | Education | 74.0 | 51 | $2.6M |

*Funding values may include multi-year contract totals

### By Industry

| Industry | Targets | High Priority | Funding |
|----------|---------|---------------|---------|
| Education | 745 | 216 | $1,487M |
| Social Services | 226 | 111 | $3,786M |
| Arts/Entertainment | 146 | 5 | $54M |
| Healthcare | 75 | 75 | $537M |
| Housing | 50 | 18 | $202M |
| Senior Care | 21 | 21 | $132M |
| Transportation | 11 | 5 | $170M |

### Geographic Distribution (Top Cities)

The targets are distributed across New York State, with concentrations in:
- New York City (all boroughs)
- Buffalo
- Albany
- Syracuse
- Rochester

## Data Quality Notes

### Strengths
- **Comprehensive Coverage**: 100,000+ government contracts analyzed
- **Multiple Data Sources**: Cross-referencing increases confidence
- **Recent Data**: Contracts from 2023+ only
- **Financial Validation**: 990 filings provide independent verification

### Limitations
1. **Employee Count Gaps**: ~15% of targets lack employee data
2. **Matching Accuracy**: Fuzzy matching may produce false positives (~5% estimated)
3. **Funding Attribution**: Multi-year contracts may overstate annual funding
4. **Existing Organizing**: Some targets may already have union representation by other unions
5. **990 Coverage**: Private employers without 990 filings not captured

### Recommendations for Validation
- Cross-reference TOP targets with organizer field knowledge
- Verify employee counts through site visits
- Check for existing collective bargaining agreements
- Confirm AFSCME jurisdiction applicability

## Reproducibility

### Prerequisites
- PostgreSQL database with OLMS multiyear data
- Python 3.10+ with psycopg2, pandas
- Access to NY Open Data and NYC Open Data APIs

### Steps to Reproduce

1. **Load NY State Contracts**
```bash
python scripts/afscme_ny/load_ny_contracts.py
```

2. **Load NYC Contracts**
```bash
python scripts/afscme_ny/load_nyc_contracts.py
```

3. **Load 990 Employers** (if not already loaded)
```bash
python scripts/import/load_990_employers.py
```

4. **Match Contracts to Employers**
```bash
python scripts/afscme_ny/match_contracts_to_employers.py
```

5. **Generate Targets**
```bash
python scripts/afscme_ny/identify_afscme_targets.py
```

6. **Access via API**
```bash
# Start API server
python -m uvicorn api.labor_api_v5:app --port 8001

# Query targets
curl "http://localhost:8001/api/targets/search?state=NY&tier=TOP"
curl "http://localhost:8001/api/targets/stats"
```

7. **Access via Frontend**
- Open `frontend/labor_search_v6.html` in browser
- Click "Targets" tab
- Use filters to explore organizing opportunities

## API Endpoints

### 990-Based Targets
| Endpoint | Description |
|----------|-------------|
| `GET /api/targets/search` | Search targets with filters |
| `GET /api/targets/stats` | Summary statistics |
| `GET /api/targets/{id}` | Target details with contracts |
| `GET /api/targets/{id}/contracts` | All contracts for a target |
| `GET /api/targets/for-union/{f_num}` | Recommended targets for a union |

### OSHA-Based Organizing Scorecard (NEW)
| Endpoint | Description |
|----------|-------------|
| `GET /api/organizing/scorecard` | Search OSHA establishments with 6-factor scoring |
| `GET /api/organizing/scorecard/{estab_id}` | Detailed scorecard for specific establishment |

**Scorecard Query Parameters:**
- `state` - Filter by state (e.g., NY)
- `naics_2digit` - Filter by industry (e.g., 62 for Healthcare)
- `min_employees` / `max_employees` - Employee count range
- `min_score` - Minimum organizing score (0-100)
- `has_contracts` - true/false to filter by contract presence
- `limit` / `offset` - Pagination

### Example Queries

```bash
# Top 10 targets with $1M+ funding
curl "http://localhost:8001/api/targets/search?min_contract_value=1000000&tier=TOP&limit=10"

# Social services sector targets
curl "http://localhost:8001/api/targets/search?sector=Social%20Services&sort_by=funding"

# Export to CSV (via frontend)
# Use the "Export" button on the Targets tab
```

## Conclusion

The Labor Relations Research Platform provides a data-driven approach to identifying organizing targets by analyzing public government contract data and nonprofit employer information. The methodology successfully identified thousands of potential targets in AFSCME-relevant sectors across New York State.

The TOP-tier targets represent organizations with strong government funding relationships, substantial employee bases, and alignment with AFSCME's core sectors. These should be prioritized for further research and organizer outreach.

---

*This case study was generated using the Labor Relations Research Platform v5.0. For questions or updates, contact the platform maintainers.*
