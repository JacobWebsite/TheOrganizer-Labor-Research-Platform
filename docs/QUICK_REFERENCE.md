# Quick Reference - Labor Data Platform

## Connection
```sql
-- PostgreSQL
psql -U postgres -d olms_multiyear
```

## Most Common Queries

### Deduplicated Membership (Use These!)

```sql
-- Total union members (matches BLS ~14.3M)
SELECT SUM(members) FROM v_union_members_counted;

-- Top 20 unions
SELECT f_num, union_name, aff_abbr, members
FROM v_union_members_counted
ORDER BY members DESC LIMIT 20;

-- By sector
SELECT * FROM v_membership_by_sector;

-- By affiliation
SELECT * FROM v_membership_by_affiliation;

-- Compare raw vs deduplicated
SELECT * FROM v_deduplication_comparison;
```

### Union Lookup

```sql
-- Find a union by name
SELECT f_num, union_name, aff_abbr, members_2024, count_members
FROM union_hierarchy
WHERE union_name ILIKE '%teamsters%';

-- Check if union is counted
SELECT f_num, union_name, hierarchy_level, count_members, count_reason
FROM union_hierarchy
WHERE f_num = '93';  -- Teamsters
```

### F-7 Employer Data

```sql
-- Employers by state
SELECT state, COUNT(*) as employers
FROM f7_employers
WHERE state IS NOT NULL
GROUP BY state ORDER BY employers DESC;

-- Unions with most employers
SELECT f_num, union_name, f7_employer_count
FROM unions_master
WHERE f7_employer_count > 50
ORDER BY f7_employer_count DESC;

-- Geocoded employers for mapping
SELECT employer_name, city, state, latitude, longitude
FROM f7_employers
WHERE latitude IS NOT NULL LIMIT 1000;
```

### Financial Data

```sql
-- Top paid officers (2024)
SELECT first_name || ' ' || last_name as name,
       title, l.union_name, e.total::bigint
FROM ar_disbursements_emp_off e
JOIN lm_data l ON e.rpt_id = l.rpt_id AND e.load_year = l.load_year
WHERE e.load_year = 2024 AND e.emp_off_type = 601
ORDER BY e.total DESC LIMIT 20;

-- Membership trends
SELECT yr_covered, COUNT(*) as filings, SUM(members) as members
FROM lm_data
GROUP BY yr_covered ORDER BY yr_covered;
```

## Key Tables

| Table | Use For |
|-------|---------|
| `v_union_members_counted` | **Deduplicated totals** |
| `union_hierarchy` | Check count status |
| `lm_data` | Raw filings |
| `f7_employers` | Employer locations |
| `unions_master` | Union metadata |

## Hierarchy Levels

| Level | Counted? | Example |
|-------|----------|---------|
| FEDERATION | NO | AFL-CIO |
| INTERNATIONAL | YES | SEIU, IBT |
| INTERMEDIATE | NO | District councils |
| LOCAL | Only if independent | SEIU 32BJ (no), CNA (yes) |

## Key Numbers (2024)

| Metric | Value |
|--------|-------|
| Deduplicated members | 14.5M |
| BLS benchmark | 14.3M |
| Raw LM filings | 70.1M |
| Unions counted | 2,238 |
| F-7 employers | 150K |
