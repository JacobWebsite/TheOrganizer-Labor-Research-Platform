# Teamsters Locals Comparison Report

**Generated:** February 3, 2026
**Data Sources:**
- Official: teamster.org/locals/ (scraped)
- Database: `unions_master` WHERE `aff_abbr = 'IBT'`

---

## Executive Summary

| Metric | Count |
|--------|-------|
| Official Website Locals | 338 |
| Database IBT Locals (LU) | 389 |
| **Matched** | **306 (91%)** |
| City/State Discrepancies | 25 |
| DB Only (not on website) | 79 |
| Website Only (not in DB) | 32 |

### Key Findings

1. **90.5% Coverage** - Database contains 306 of 338 website locals
2. **Canadian Locals** - 22 Canadian locals on website not expected in OLMS data
3. **US Gaps** - Only 10 US locals missing from database
4. **Stale DB Records** - 33 locals with 500+ members in DB not on website (likely merged/closed)
5. **Coordinates Available** - All 338 website locals include lat/long for mapping

---

## Canadian Locals (Expected Not in OLMS)

The OLMS database only covers US unions. These 22 Canadian locals are on the Teamsters website but correctly absent from our database:

| Local | City | Province |
|-------|------|----------|
| 31 | Delta BC | CN |
| 91 | Ottawa | Ont |
| 106 | Montreal | Que |
| 155 | Vancouver | BC |
| 213 | Vancouver | BC |
| 230 | Markham | Ont |
| 362 | Calgary | Alb |
| 395 | Saskatoon | SK |
| 419 | Mississauga | Ont |
| 464 | Vancouver | BC |
| 555 | Montreal | Quebec |
| 647 | Mississauga | Ont |
| 847 | Mississauga | Ont |
| 855 | St. John's | Nfld |
| 879 | Stoney Creek | Ont |
| 927 | Dartmouth | NS |
| 931 | Montreal | Que |
| 938 | Mississauga | Ont |
| 979 | Winnipeg | Man |
| 987 | Calgary | Alb |
| 1979 | Pickering | Ont |
| 1999 | Montreal | Que |

---

## US Locals Missing from Database

These 10 US locals appear on the official website but are not in our `unions_master` table. They may be:
- Newly chartered
- Filed under different local numbers
- Missing from OLMS data

| Local | City | State | Action Needed |
|-------|------|-------|---------------|
| 8 | State College | PA | Investigate |
| 77 | Fort Washington | PA | Investigate |
| 127 | Milford | MA | Investigate |
| 214 | Detroit | MI | Investigate |
| 237 | New York | NY | Public sector local |
| 320 | Minneapolis | MN | Public sector local |
| 502 | Philadelphia | PA | Investigate |
| 700 | Lombard | IL | Investigate |
| 831 | New York | NY | Investigate |
| 1699 | La Mesa | CA | Investigate |

**Note:** Locals 237 and 320 are likely public sector Teamsters locals that file with state agencies instead of federal OLMS.

---

## Database Locals Not on Website (Active)

These locals have 500+ members in our database but don't appear on teamster.org. They may be:
- Merged into other locals
- Closed/disbanded
- Filed under different local numbers

| Local | City | State | Members | Last Filed |
|-------|------|-------|---------|------------|
| 2011 | Riverview | FL | 4,203 | 2016 |
| 505 | Huntington | WV | 3,270 | 2012 |
| 961 | Denver | CO | 3,168 | 2010 |
| 995 | So. El Monte | CA | 2,744 | 2014 |
| 486 | Grand Rapids | MI | 2,449 | 2013 |
| 111 | Rahway | NJ | 1,702 | 2012 |
| 624 | Santa Rosa | CA | 1,566 | 2011 |
| 807 | New York | NY | 1,536 | 2021 |
| 968 | Houston | TX | 1,432 | 2015 |
| 311 | Baltimore | MD | 1,420 | 2015 |

**Note:** Most of these locals have old filing dates (2010-2016), suggesting they may have merged or closed.

---

## City/State Discrepancies

These locals match by number but have different city/state data:

| Local | Website | Database | Issue |
|-------|---------|----------|-------|
| 25 | Boston, MA | Charlestown, MA | City |
| 122 | Boston, MA | Dorchester, MA | City |
| 229 | Scranton, PA | Dunmore, PA | City |
| 251 | E. Providence, RI | East Providence, RI | Abbreviation |
| 293 | Independence, OH | Cleveland, OH | City |
| 340 | S. Portland, ME | South Portland, ME | Abbreviation |
| 344 | Milwaukee, WI | West Allis, WI | City |
| 453 | Cumberland, MD | Washington, DC | State mismatch |
| 541 | Oak Grove, MO | Kansas City, MO | City |
| 589 | Silverdale, WA | Port Angeles, WA | City |

Most discrepancies are minor (abbreviations, neighboring cities). Local 453 has a state mismatch that should be investigated.

---

## Data Quality Recommendations

### Immediate Actions
1. **Investigate Local 453** - State mismatch (MD vs DC)
2. **Add public sector note** - Locals 237, 320, 1932 are public sector
3. **Review stale locals** - 33 locals with 500+ members not on website (old filings)

### Database Improvements
1. Add `is_active` flag based on website presence
2. Add `last_verified` timestamp
3. Cross-reference with NLRB data for recent activity
4. Store lat/long coordinates for mapping

### Website Data Value
- Contact information (phone, email, website)
- Leadership names and titles
- Division/conference affiliations
- Verified addresses
- Geographic coordinates for all locals

---

## Files Generated

| File | Description |
|------|-------------|
| `teamsters_official_locals.csv` | 338 locals from website (with lat/long) |
| `teamsters_database_locals.csv` | 389 locals from database |
| `teamsters_comparison_report.csv` | Side-by-side comparison |
| `teamsters_missing_from_db.csv` | 32 website-only locals |
| `teamsters_not_on_website.csv` | 79 database-only locals |
| `teamsters_discrepancies.csv` | 18 city/state mismatches |

---

## Database Objects Created

```sql
-- Reference table with official Teamsters data
SELECT * FROM teamsters_official_locals;

-- Comparison view
SELECT * FROM v_teamsters_comparison
WHERE match_status != 'MATCH';
```
