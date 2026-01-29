# Session Summary: Affiliation Fixes, Local Numbers & F-7 Deduplication
**Date:** January 23, 2026

## Overview
This session fixed three major data quality issues in the labor relations database:
1. Missing affiliation mappings (CWA, SAG-AFTRA, UNITE HERE, etc.)
2. Local numbers showing file numbers instead of actual union local designations
3. F-7 employer data containing 15 years of historical duplicates

## Key Metrics

| Metric | Before | After |
|--------|--------|-------|
| F-7 Employers | 150,388 | 71,085 |
| F-7 Date Range | 2010-2025 | 2020-2025 |
| Affiliation Match Rate | 64.6% | 91.3% |
| Mapped Affiliations | 54 | 111 |
| Local Number Display | File numbers only | Actual local numbers |

## Database Changes

### New Table Created
- **f7_employers_deduped** - Deduplicated F-7 employers (last 5 years only)
  - Deduplication key: employer_name + city + state + union
  - Keeps most recent notice per unique combination
  - Indexes on: name, state, union_fnum, notice_date

### Views Updated
1. **v_employer_search** - Now uses deduplicated table + text-based affiliation parsing
2. **v_union_local_search** - Added local_display_name and local_number fields
3. **v_affiliation_summary** - Updated to use deduplicated F-7 counts

### Crosswalk Table Updated
- **crosswalk_affiliation_sector_map** - Added 57 missing affiliations including:
  - CWA, ACT, UNITE HERE, SAG-AFTRA, OPEIU, NNU
  - ILA, ILWU, BSOIW, BCTGMI, SMART, NALC, WGAW
  - Workers United (WU) - important for Starbucks campaign visibility

## Files Created/Modified

### SQL Scripts (run in order if recreating)
1. `fix_affiliations.sql` - Adds missing affiliations to crosswalk
2. `fix_employer_view_v3.sql` - Recreates v_employer_search with text parsing
3. `fix_union_local_view_v2.sql` - Recreates v_union_local_search with local numbers
4. `dedupe_f7_employers.sql` - Creates deduplicated F-7 table
5. `update_views_deduped.sql` - Updates all views to use deduplicated data

### Application Files
- `labor_search_api.py` - FastAPI backend (password: Juniordog33!)
- `labor_search.html` - Web interface with quick filters

### Diagnostic Scripts
- `diagnose_local_numbers.sql` - Analyzes desig_name/desig_num fields
- `check_db.sql` - Quick database state verification

## Technical Details

### Text-Based Affiliation Parsing
When F-7 employers have no union_file_number (31.5% of records), we parse affiliation from the latest_union_name text field using ILIKE patterns:

```sql
CASE 
    WHEN e.latest_union_name ILIKE '%SEIU%' THEN 'SEIU'
    WHEN e.latest_union_name ILIKE '%TEAMSTER%' OR e.latest_union_name ILIKE 'IBT-%' THEN 'IBT'
    WHEN e.latest_union_name ILIKE '%WORKERS UNITED%' THEN 'WU'
    -- ... 30+ patterns
END
```

### Local Number Fields
- **desig_name** - Designation type (LU=Local Union, JC=Joint Council, BR=Branch, etc.)
- **desig_num** - Actual local number (e.g., 1199, 32BJ, 42)
- **local_display_name** - Formatted as "SEIU LU 1199" or "IBT JC 42"

### F-7 Deduplication Logic
```sql
SELECT DISTINCT ON (
    LOWER(TRIM(employer_name)), 
    LOWER(TRIM(COALESCE(city, ''))), 
    COALESCE(state, ''),
    COALESCE(latest_union_fnum::text, LOWER(TRIM(latest_union_name)))
)
FROM f7_employers
WHERE latest_notice_date >= '2020-01-01'
ORDER BY ... latest_notice_date DESC
```

## API Endpoints

| Endpoint | Description |
|----------|-------------|
| GET /affiliations | List all affiliations with stats |
| GET /employers/search | Search employers with filters |
| GET /unions/locals/search | Search union locals |
| GET /unions/locals/{file_number} | Detail view with history + employers |
| GET /states | List states with union density |
| GET /states/{abbr}/employers | Employers in a state |

## Running the Application

```cmd
cd C:\Users\jakew\Downloads\labor-data-project
py -m uvicorn labor_search_api:app --host 0.0.0.0 --port 8000
```

Then open `labor_search.html` in a browser.

## Known Issues / Future Work

1. **8.7% of employers still unmatched** - These are likely independent unions or very small locals
2. **Some locals missing desig_num** - National HQs and some regional bodies don't have local numbers
3. **Workers United complexity** - Some WU locals show as SEIU affiliates due to organizational structure

## Queries for Verification

```sql
-- Check affiliation match rate
SELECT 
    COUNT(*) as total,
    COUNT(affiliation) as matched,
    ROUND(100.0 * COUNT(affiliation) / COUNT(*), 1) as pct
FROM v_employer_search;

-- Check F-7 deduplication
SELECT COUNT(*) FROM f7_employers_deduped;  -- Should be ~71,077

-- Check local numbers
SELECT file_number, local_display_name, local_number, members
FROM v_union_local_search
WHERE affiliation = 'SEIU' AND local_number IS NOT NULL
ORDER BY members DESC LIMIT 10;
```
