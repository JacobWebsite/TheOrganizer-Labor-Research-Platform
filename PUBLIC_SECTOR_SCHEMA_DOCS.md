# Public Sector Union Database Schema

## Overview

New normalized schema for tracking public sector unions, their locals, employers, and bargaining relationships.

## Tables

### 1. `ps_parent_unions` - International/National Unions
| Column | Type | Description |
|--------|------|-------------|
| id | SERIAL | Primary key |
| abbrev | VARCHAR(20) | Union abbreviation (AFSCME, NEA, AFT, etc.) |
| full_name | VARCHAR(255) | Full union name |
| federation | VARCHAR(50) | Parent federation (AFL-CIO, Independent, etc.) |
| headquarters_city | VARCHAR(100) | HQ location |
| headquarters_state | CHAR(2) | HQ state |
| sector_focus | VARCHAR(100) | PUBLIC, MIXED, PRIVATE |

**Current data:** 24 parent unions

### 2. `ps_union_locals` - Local Unions/Councils/Chapters
| Column | Type | Description |
|--------|------|-------------|
| id | SERIAL | Primary key |
| parent_union_id | INTEGER | FK to ps_parent_unions |
| f_num | VARCHAR(20) | OLMS file number (if OLMS filer) |
| local_name | VARCHAR(255) | Local union name |
| local_designation | VARCHAR(100) | Local number/council designation |
| state | CHAR(2) | State |
| city | VARCHAR(100) | City |
| members | INTEGER | Membership count |
| members_year | INTEGER | Year of membership count |
| sector_type | VARCHAR(50) | K12, HIGHER_ED, STATE_GOVT, COUNTY, MUNICIPAL, TRANSIT, POLICE, FIRE |
| files_lm_report | BOOLEAN | Whether union files OLMS LM reports |
| source_type | VARCHAR(50) | OLMS, WEB_RESEARCH, STATE_REGISTRY, ORG_WEBSITE |

**Current data:** 1,520 locals (1,179 from OLMS, 341 from manual research)

### 3. `ps_employers` - Public Sector Employers
| Column | Type | Description |
|--------|------|-------------|
| id | SERIAL | Primary key |
| employer_name | VARCHAR(255) | Employer name |
| employer_type | VARCHAR(50) | FEDERAL, STATE_AGENCY, COUNTY, CITY, SCHOOL_DISTRICT, UNIVERSITY, TRANSIT_AUTHORITY, etc. |
| state | CHAR(2) | State |
| city | VARCHAR(100) | City |
| county | VARCHAR(100) | County |
| fips_code | VARCHAR(10) | FIPS code |
| total_employees | INTEGER | Total workforce |
| f7_employer_id | TEXT | Link to F7 employer data |

**Current data:** 7,987 employers

### 4. `ps_bargaining_units` - Union-Employer Relationships
| Column | Type | Description |
|--------|------|-------------|
| id | SERIAL | Primary key |
| local_id | INTEGER | FK to ps_union_locals |
| employer_id | INTEGER | FK to ps_employers |
| unit_name | VARCHAR(255) | Bargaining unit description |
| unit_size | INTEGER | Workers in unit |
| recognition_date | DATE | When recognized |
| contract_start | DATE | Current contract start |
| contract_end | DATE | Current contract expiration |
| exclusive_rep | BOOLEAN | Exclusive representative status |

**Current data:** 438 bargaining unit relationships

## Data Sources

1. **OLMS LM Filings** - Union financial reports (unions_master table)
   - Provides: Local names, membership, file numbers, cities
   - Limitation: Many state/local unions exempt from LMRDA reporting

2. **F7 Employer Notices** - Employer bargaining notices
   - Provides: Employer names, union relationships, unit sizes
   - Limitation: Only captures recent notice filings

3. **Manual Research** - Web research from this session
   - Provides: NEA state affiliates, police/fire unions, state-level aggregates
   - Added to supplement OLMS gaps

## Sample Queries

```sql
-- Locals by parent union
SELECT p.abbrev, COUNT(*) as locals, SUM(l.members) as members
FROM ps_union_locals l
JOIN ps_parent_unions p ON l.parent_union_id = p.id
GROUP BY p.abbrev ORDER BY members DESC;

-- Employers by type
SELECT employer_type, COUNT(*), SUM(total_employees)
FROM ps_employers GROUP BY employer_type;

-- Union-employer relationships for a state
SELECT p.abbrev, l.local_designation, e.employer_name, bu.unit_size
FROM ps_bargaining_units bu
JOIN ps_union_locals l ON bu.local_id = l.id
JOIN ps_parent_unions p ON l.parent_union_id = p.id
JOIN ps_employers e ON bu.employer_id = e.id
WHERE l.state = 'CA' ORDER BY bu.unit_size DESC;
```

## Next Steps

1. **Add more specific employers** - Individual school districts, cities, counties
2. **Populate bargaining unit relationships** - Link locals to specific employers
3. **Add contract data** - Expiration dates, wage info
4. **Import state registry data** - PERB filings, state labor relations data
5. **Clean employer classifications** - Some private employers misclassified as public
