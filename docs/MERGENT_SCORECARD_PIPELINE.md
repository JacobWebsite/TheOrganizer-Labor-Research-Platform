# Mergent Employer Scorecard Pipeline

## Overview

This document describes the complete pipeline for processing Mergent Intellect employer data into organizing target scorecards. The pipeline was developed and validated using the **Museums sector (243 employers)** and is ready to scale to all remaining sectors (~14,000 employers).

**Goal:** Identify non-union employers suitable for organizing campaigns, ranked by a composite score based on multiple data sources.

---

## Pipeline Architecture

```
Mergent CSV Files (by sector)
        ↓
   Load to PostgreSQL (mergent_employers table)
        ↓
   Match to IRS 990 (ny_990_filers) by EIN, then name
        ↓
   Match to F-7 Employers (existing union contracts)
        ↓
   Match to NLRB Elections (wins = unionized)
        ↓
   Match to OSHA Establishments (violations data)
        ↓
   Match to Government Contracts (NY State + NYC)
        ↓
   Calculate Component Scores
        ↓
   Flag has_union = TRUE/FALSE
        ↓
   Calculate organizing_score (non-union only)
        ↓
   Create sector views for API/frontend
```

---

## Database Connection

```python
import psycopg2
from psycopg2.extras import RealDictCursor

conn = psycopg2.connect(
    host='localhost',
    dbname='olms_multiyear',
    user='postgres',
    password='Juniordog33!'
)
```

---

## Key Tables

### Source Data (Already Loaded)

| Table | Records | Description |
|-------|---------|-------------|
| `ny_990_filers` | 37,480 | IRS Form 990 NY nonprofits (extracted from XML) |
| `f7_employers_deduped` | 63,118 | Private sector employers with union contracts |
| `nlrb_elections` | 33,096 | NLRB election records |
| `nlrb_participants` | 30,399 | Union petitioners matched to OLMS |
| `osha_establishments` | 1,007,217 | OSHA-covered workplaces (43,594 in NY) |
| `osha_violations_detail` | 2,245,020 | Violation records |
| `ny_state_contracts` | 51,500 | NY State contracts |
| `nyc_contracts` | 49,767 | NYC contracts |
| `organizing_targets` | 5,428 | Existing 990-based targets (has contract data) |

### Target Table (Mergent Data)

```sql
-- mergent_employers table structure (key columns)
CREATE TABLE mergent_employers (
    id SERIAL PRIMARY KEY,
    duns VARCHAR(20),                    -- D-U-N-S number (unique ID)
    ein VARCHAR(20),                     -- IRS Employer ID
    company_name TEXT,
    company_name_normalized TEXT,        -- Uppercase, stripped
    city TEXT,
    state VARCHAR(2),
    zip VARCHAR(10),
    county TEXT,
    employees_site INTEGER,
    sales_amount NUMERIC,
    naics_primary VARCHAR(10),
    website TEXT,
    sector_category VARCHAR(50),         -- MUSEUMS, HEALTHCARE, etc.
    
    -- 990 Match
    ny990_id INTEGER,
    ny990_employees INTEGER,
    ny990_revenue NUMERIC,
    ny990_match_method VARCHAR(20),      -- EIN, NAME_CITY, FUZZY_NAME
    
    -- F-7 Match (union contract)
    matched_f7_employer_id VARCHAR(20),
    f7_union_name TEXT,
    f7_union_fnum VARCHAR(20),
    f7_match_method VARCHAR(20),
    
    -- NLRB Match
    nlrb_case_number VARCHAR(20),
    nlrb_election_date DATE,
    nlrb_union_won BOOLEAN,
    nlrb_eligible_voters INTEGER,
    nlrb_match_method VARCHAR(20),
    
    -- OSHA Match
    osha_establishment_id VARCHAR(20),
    osha_total_inspections INTEGER,
    osha_union_status VARCHAR(5),        -- Y, A, N, B
    osha_match_method VARCHAR(20),
    osha_violation_count INTEGER,
    osha_total_penalties NUMERIC,
    osha_last_violation_date DATE,
    
    -- Contract Match
    ny_state_contracts INTEGER,
    ny_state_contract_value NUMERIC,
    nyc_contracts INTEGER,
    nyc_contract_value NUMERIC,
    
    -- Union Status
    has_union BOOLEAN DEFAULT FALSE,
    
    -- Scores
    score_geographic INTEGER DEFAULT 0,
    score_size INTEGER DEFAULT 0,
    score_industry_density INTEGER DEFAULT 0,
    score_nlrb_momentum INTEGER DEFAULT 0,
    score_osha_violations INTEGER DEFAULT 0,
    score_govt_contracts INTEGER DEFAULT 0,
    sibling_union_bonus INTEGER DEFAULT 0,
    sibling_union_note TEXT,
    organizing_score INTEGER DEFAULT 0
);
```

---

## Step-by-Step Pipeline

### Step 1: Load Mergent CSV

```sql
-- Create staging table for CSV import
CREATE TEMP TABLE mergent_staging (
    duns TEXT,
    ein TEXT,
    company_name TEXT,
    trade_name TEXT,
    street_address TEXT,
    city TEXT,
    state TEXT,
    zip TEXT,
    county TEXT,
    employees_site TEXT,
    employees_all_sites TEXT,
    sales_amount TEXT,
    naics_primary TEXT,
    naics_desc TEXT,
    sic_primary TEXT,
    phone TEXT,
    website TEXT,
    year_founded TEXT,
    parent_duns TEXT,
    parent_name TEXT
);

-- Load CSV (adjust path)
COPY mergent_staging FROM 'C:/path/to/sector_file.csv' 
WITH (FORMAT csv, HEADER true, ENCODING 'UTF-8');

-- Insert into main table
INSERT INTO mergent_employers (
    duns, ein, company_name, company_name_normalized,
    city, state, zip, county, employees_site, sales_amount,
    naics_primary, website, sector_category
)
SELECT 
    duns,
    NULLIF(REGEXP_REPLACE(ein, '[^0-9]', '', 'g'), ''),
    company_name,
    UPPER(REGEXP_REPLACE(company_name, '\s+(LLC|INC|CORP|LTD|CO|LP|LLP)\.?$', '', 'gi')),
    city,
    state,
    zip,
    county,
    NULLIF(REGEXP_REPLACE(employees_site, '[^0-9]', '', 'g'), '')::INTEGER,
    NULLIF(REGEXP_REPLACE(sales_amount, '[^0-9.]', '', 'g'), '')::NUMERIC,
    naics_primary,
    website,
    'SECTOR_NAME'  -- Replace with actual sector
FROM mergent_staging;
```

### Step 2: Match to IRS 990

```sql
-- Match by EIN (exact)
UPDATE mergent_employers m
SET 
    ny990_id = n.id,
    ny990_employees = n.totemployeescnt,
    ny990_revenue = n.totrevenue,
    ny990_match_method = 'EIN'
FROM ny_990_filers n
WHERE m.ein = n.ein
  AND m.ein IS NOT NULL
  AND m.ny990_id IS NULL
  AND m.sector_category = 'SECTOR_NAME';

-- Match by normalized name + city
UPDATE mergent_employers m
SET 
    ny990_id = n.id,
    ny990_employees = n.totemployeescnt,
    ny990_revenue = n.totrevenue,
    ny990_match_method = 'NAME_CITY'
FROM ny_990_filers n
WHERE m.company_name_normalized = n.name_normalized
  AND UPPER(m.city) = UPPER(n.city)
  AND m.ny990_id IS NULL
  AND m.sector_category = 'SECTOR_NAME';

-- Fuzzy match (requires pg_trgm extension)
UPDATE mergent_employers m
SET 
    ny990_id = sub.id,
    ny990_employees = sub.totemployeescnt,
    ny990_revenue = sub.totrevenue,
    ny990_match_method = 'FUZZY_NAME'
FROM (
    SELECT DISTINCT ON (m2.id) 
        m2.id as mergent_id, n.*,
        similarity(m2.company_name_normalized, n.name_normalized) as sim
    FROM mergent_employers m2
    JOIN ny_990_filers n ON UPPER(m2.city) = UPPER(n.city)
    WHERE m2.ny990_id IS NULL
      AND m2.sector_category = 'SECTOR_NAME'
      AND similarity(m2.company_name_normalized, n.name_normalized) >= 0.7
    ORDER BY m2.id, sim DESC
) sub
WHERE m.id = sub.mergent_id;
```

### Step 3: Match to F-7 Employers (Union Contracts)

```sql
-- Match by EIN
UPDATE mergent_employers m
SET 
    matched_f7_employer_id = f.employer_id,
    f7_union_name = f.latest_union_name,
    f7_union_fnum = f.latest_union_fnum,
    f7_match_method = 'EIN',
    has_union = TRUE
FROM f7_employers_deduped f
WHERE m.ein = f.ein
  AND m.ein IS NOT NULL
  AND f.state = 'NY'
  AND m.matched_f7_employer_id IS NULL
  AND m.sector_category = 'SECTOR_NAME';

-- Match by normalized name + city
UPDATE mergent_employers m
SET 
    matched_f7_employer_id = f.employer_id,
    f7_union_name = f.latest_union_name,
    f7_union_fnum = f.latest_union_fnum,
    f7_match_method = 'NAME_CITY',
    has_union = TRUE
FROM f7_employers_deduped f
WHERE m.company_name_normalized = UPPER(REGEXP_REPLACE(f.employer_name, '\s+(LLC|INC|CORP|LTD|CO|LP|LLP)\.?$', '', 'gi'))
  AND UPPER(m.city) = UPPER(f.city)
  AND f.state = 'NY'
  AND m.matched_f7_employer_id IS NULL
  AND m.sector_category = 'SECTOR_NAME';
```

### Step 4: Match to NLRB Elections

```sql
-- Match by name + city to nlrb_participants (which links to elections)
UPDATE mergent_employers m
SET 
    nlrb_case_number = e.case_number,
    nlrb_election_date = e.date_closed::DATE,
    nlrb_union_won = (e.results = 'Wins'),
    nlrb_eligible_voters = e.eligible_voters,
    nlrb_match_method = 'NAME_CITY'
FROM nlrb_participants p
JOIN nlrb_elections e ON p.case_number = e.case_number
WHERE m.company_name_normalized ILIKE '%' || UPPER(SPLIT_PART(p.employer_name, ' ', 1)) || '%'
  AND UPPER(m.city) = UPPER(p.employer_city)
  AND p.employer_state = 'NY'
  AND m.nlrb_case_number IS NULL
  AND m.sector_category = 'SECTOR_NAME';

-- Mark NLRB wins as unionized
UPDATE mergent_employers
SET has_union = TRUE
WHERE nlrb_union_won = TRUE
  AND sector_category = 'SECTOR_NAME';
```

### Step 5: Match to OSHA

```sql
-- Match by name + city
UPDATE mergent_employers m
SET 
    osha_establishment_id = o.establishment_id,
    osha_total_inspections = o.total_inspections,
    osha_union_status = o.union_status,
    osha_match_method = 'NAME_CITY'
FROM osha_establishments o
WHERE m.company_name_normalized ILIKE '%' || 
      UPPER(REGEXP_REPLACE(SPLIT_PART(o.estab_name, ' ', 1), '[^A-Z0-9]', '', 'g')) || '%'
  AND UPPER(m.city) = UPPER(o.site_city)
  AND o.site_state = 'NY'
  AND m.osha_establishment_id IS NULL
  AND m.sector_category = 'SECTOR_NAME';

-- Get violation counts
UPDATE mergent_employers m
SET 
    osha_violation_count = v.violation_count,
    osha_total_penalties = v.total_penalties,
    osha_last_violation_date = v.last_violation
FROM (
    SELECT establishment_id,
           COUNT(*) as violation_count,
           SUM(current_penalty) as total_penalties,
           MAX(issuance_date) as last_violation
    FROM osha_violations_detail
    GROUP BY establishment_id
) v
WHERE m.osha_establishment_id = v.establishment_id
  AND m.sector_category = 'SECTOR_NAME';

-- Mark OSHA union status as unionized
UPDATE mergent_employers
SET has_union = TRUE
WHERE osha_union_status IN ('Y', 'A')
  AND has_union = FALSE
  AND sector_category = 'SECTOR_NAME';
```

### Step 6: Match to Government Contracts

```sql
-- Match via organizing_targets table (already has contract totals by EIN)
UPDATE mergent_employers m
SET 
    ny_state_contracts = t.ny_state_contracts,
    ny_state_contract_value = t.ny_state_contract_value,
    nyc_contracts = t.nyc_contracts,
    nyc_contract_value = t.nyc_contract_value
FROM organizing_targets t
WHERE m.ein = t.ein
  AND m.ein IS NOT NULL
  AND m.sector_category = 'SECTOR_NAME';
```

### Step 7: Calculate Scores

```sql
-- Geographic Score (0-15)
UPDATE mergent_employers
SET score_geographic = CASE
    WHEN UPPER(city) IN ('NEW YORK', 'BROOKLYN', 'BRONX', 'QUEENS', 'STATEN ISLAND',
                         'FLUSHING', 'ASTORIA', 'LONG ISLAND CITY', 'JAMAICA', 'CORONA') THEN 15
    WHEN UPPER(city) IN ('BUFFALO', 'ROCHESTER', 'SYRACUSE', 'ALBANY', 'YONKERS') THEN 10
    ELSE 5
END
WHERE sector_category = 'SECTOR_NAME';

-- Size Score (0-5) - Sweet spot 50-500 employees
UPDATE mergent_employers
SET score_size = CASE
    WHEN COALESCE(ny990_employees, employees_site) BETWEEN 100 AND 500 THEN 5
    WHEN COALESCE(ny990_employees, employees_site) BETWEEN 50 AND 99 THEN 4
    WHEN COALESCE(ny990_employees, employees_site) BETWEEN 25 AND 49 THEN 3
    WHEN COALESCE(ny990_employees, employees_site) BETWEEN 500 AND 1000 THEN 2
    WHEN COALESCE(ny990_employees, employees_site) > 1000 THEN 1
    ELSE 0
END
WHERE sector_category = 'SECTOR_NAME';

-- OSHA Violations Score (0-4)
UPDATE mergent_employers
SET score_osha_violations = CASE
    WHEN osha_violation_count >= 5 AND osha_last_violation_date >= '2022-01-01' THEN 4
    WHEN osha_violation_count >= 3 OR osha_last_violation_date >= '2022-01-01' THEN 3
    WHEN osha_violation_count > 0 THEN 2
    WHEN osha_establishment_id IS NOT NULL THEN 1
    ELSE 0
END
WHERE sector_category = 'SECTOR_NAME';

-- Government Contracts Score (0-15)
UPDATE mergent_employers
SET score_govt_contracts = CASE
    WHEN COALESCE(ny_state_contract_value, 0) + COALESCE(nyc_contract_value, 0) >= 5000000 THEN 15
    WHEN COALESCE(ny_state_contract_value, 0) + COALESCE(nyc_contract_value, 0) >= 1000000 THEN 12
    WHEN COALESCE(ny_state_contract_value, 0) + COALESCE(nyc_contract_value, 0) >= 500000 THEN 10
    WHEN COALESCE(ny_state_contract_value, 0) + COALESCE(nyc_contract_value, 0) >= 100000 THEN 7
    WHEN COALESCE(ny_state_contracts, 0) + COALESCE(nyc_contracts, 0) >= 3 THEN 5
    WHEN COALESCE(ny_state_contracts, 0) + COALESCE(nyc_contracts, 0) >= 1 THEN 3
    ELSE 0
END
WHERE sector_category = 'SECTOR_NAME';

-- Industry Density Score (0-5) - Varies by sector
-- For museums: 10% unionized, so NYC=5, other=3
-- Calculate per-sector based on: SELECT COUNT(*) FILTER (WHERE has_union) * 100.0 / COUNT(*) FROM mergent_employers WHERE sector_category = 'X'

-- NLRB Momentum Score (0-5) - Based on recent wins in same city/region
-- Requires knowledge of recent organizing in the sector
```

### Step 8: Calculate Final Organizing Score

```sql
-- Only for non-union employers
UPDATE mergent_employers
SET organizing_score = 
    score_geographic + 
    score_size + 
    score_industry_density + 
    score_nlrb_momentum + 
    score_osha_violations + 
    score_govt_contracts +
    sibling_union_bonus
WHERE has_union = FALSE
  AND sector_category = 'SECTOR_NAME';
```

### Step 9: Create Sector View

```sql
CREATE OR REPLACE VIEW v_SECTOR_organizing_targets AS
SELECT 
    duns as id,
    company_name as employer_name,
    city, state, zip, county,
    employees_site as mergent_employees,
    ny990_employees as irs_employees,
    COALESCE(ny990_employees, employees_site) as best_employee_count,
    ROUND(COALESCE(ny990_revenue, 0) / 1000000.0, 2) as revenue_millions,
    ein, naics_primary as naics_code, website,
    organizing_score as total_score,
    score_geographic, score_size, score_industry_density,
    score_nlrb_momentum, score_osha_violations, score_govt_contracts,
    sibling_union_bonus,
    CASE 
        WHEN organizing_score >= 40 THEN 'TOP'
        WHEN organizing_score >= 30 THEN 'HIGH'
        WHEN organizing_score >= 20 THEN 'MEDIUM'
        ELSE 'LOW'
    END as priority_tier,
    ny990_match_method IS NOT NULL as has_990_data,
    osha_establishment_id IS NOT NULL as has_osha_data,
    osha_violation_count, osha_total_penalties, osha_last_violation_date,
    ny_state_contracts, ny_state_contract_value,
    nyc_contracts, nyc_contract_value,
    COALESCE(ny_state_contract_value, 0) + COALESCE(nyc_contract_value, 0) as total_contract_value,
    sibling_union_note,
    'SECTOR_NAME' as sector_category
FROM mergent_employers
WHERE sector_category = 'SECTOR_NAME'
  AND has_union = FALSE
ORDER BY organizing_score DESC, COALESCE(ny990_employees, employees_site) DESC;
```

---

## Sectors to Process

Based on MERGENT_QUICK_REFERENCE.md:

| Tier | Sector | NAICS | Est. Records | Priority |
|------|--------|-------|--------------|----------|
| 1A | Hospitals | 622 | 300-500 | HIGH |
| 1B | Nursing/Residential Care | 623 | 1,500-2,500 | HIGH |
| 1C | Ambulatory Healthcare | 621 | 2,000-3,000 | HIGH |
| 1D | Social Services | 624 | 3,000-4,000 | HIGH |
| 1E | Museums/Cultural | 711, 712 | 243 | ✅ DONE |
| 2A | Education Services | 611 | 1,500-2,000 | MEDIUM |
| 2B | Building Services | 561 | 1,500-2,500 | MEDIUM |
| 2C | Professional Services | 541 | 1,000-1,500 | MEDIUM |
| 3A | Transit/Transportation | 485, 488 | 800-1,200 | LOWER |
| 3B | Utilities | 221 | 200-400 | LOWER |
| 3C | Hotels/Accommodation | 721 | 500-800 | LOWER |
| 3D | Food Service Contractors | 722 | 300-500 | LOWER |

**Total Expected: 10,000-15,000 employers**

---

## Mergent CSV Files Location

```
C:\Users\jakew\Downloads\labor-data-project\AFSCME case example NY\
├── Museums_New_York_advancesearch15170634296983ab5bdc310.csv  ✅ LOADED
├── [Healthcare files - need to download]
├── [Social Services files - need to download]
├── [Education files - need to download]
└── [Other sector files]
```

**Download from:** CUNY Library → Mergent Intellect → Advanced Search
**Export fields:** See MERGENT_QUICK_REFERENCE.md

---

## API Endpoints Pattern

For each sector, add these endpoints to `api/labor_api_v6.py`:

```python
@app.get("/api/{sector}/targets")
@app.get("/api/{sector}/targets/stats")
@app.get("/api/{sector}/targets/{target_id}")
@app.get("/api/{sector}/targets/cities")
@app.get("/api/{sector}/unionized")
@app.get("/api/{sector}/summary")
```

---

## Validation Checklist

After processing each sector:

- [ ] 990 match rate > 50%
- [ ] F-7 matches flagged as has_union = TRUE
- [ ] NLRB wins flagged as has_union = TRUE
- [ ] OSHA union_status Y/A flagged as has_union = TRUE
- [ ] All non-union have organizing_score > 0
- [ ] Views created and queryable
- [ ] API endpoints tested

---

## Key Learnings from Museums

1. **EIN matching is most reliable** - 84% of museums had EINs, 92% of those matched to 990
2. **Name matching requires normalization** - Strip LLC/Inc/Corp, uppercase, handle punctuation
3. **NLRB wins without F-7 = recently organized** - 7 museums won elections but no contract filed yet
4. **OSHA match rate varies by sector** - Museums = 9% (low-risk), Healthcare will be higher
5. **Sibling union bonus is rare** - Only 3 museums had parent/sibling unions

---

## Files Reference

| File | Purpose |
|------|---------|
| `CLAUDE.md` | Platform reference for Claude |
| `MERGENT_QUICK_REFERENCE.md` | Mergent query guide |
| `MERGENT_SCORECARD_PIPELINE.md` | This document |
| `api/labor_api_v6.py` | API with museum endpoints |
| `scripts/extract_ny_990.py` | 990 XML extraction script |

---

*Created: February 4, 2025*
*Status: Museums complete, ready for remaining sectors*
