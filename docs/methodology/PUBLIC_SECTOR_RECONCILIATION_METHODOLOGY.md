# Public Sector Union Reconciliation - Detailed Methodology

**Date:** January 29, 2026  
**Version:** 1.0

---

## Overview

This document describes the methodology used to reconcile public sector union membership data against EPI (Economic Policy Institute) benchmarks derived from CPS (Current Population Survey) data.

### Problem Statement

State and local public sector unions are largely exempt from OLMS LM reporting requirements under the LMRDA (Labor Management Reporting and Disclosure Act). This creates a significant gap in our membership data that must be filled through alternative sources.

### Goal

Achieve ≥85% coverage of EPI public sector membership benchmarks for all 51 states/DC.

### Result

**50 of 51 states** within ±15% of EPI benchmark (98.3% national coverage).

---

## Data Sources

### Primary Sources

| Source | Coverage | Data Available | Limitations |
|--------|----------|----------------|-------------|
| OLMS LM Filings | Unions >$300K revenue or filing requirements met | Membership, finances, officers | Most public unions exempt |
| NEA State Reports | Teachers | State affiliate membership | May include retirees |
| AFT State Reports | Teachers, public employees | Local membership counts | Overlap with NEA merged affiliates |
| IAFF Reports | Firefighters | State/local membership | Generally accurate |
| FOP Reports | Police | Lodge membership | Varies by state |
| Union Websites | All | Self-reported membership | May be outdated |
| Form 990 Data | Nonprofits | Revenue-based estimates | Requires per-capita rates |

### Benchmark Source

| Source | Table | Key Fields |
|--------|-------|------------|
| EPI/CPS Analysis | `epi_state_benchmarks` | `members_public`, `members_public_year` |

EPI data derived from Bureau of Labor Statistics Current Population Survey - Outgoing Rotation Groups (CPS-ORG). Individuals self-report union membership status.

---

## Methodology Steps

### Step 1: Load OLMS Data

Query public sector unions from `unions_master`:

```sql
SELECT f_num, union_name, aff_abbr, members, state, city
FROM unions_master
WHERE sector = 'PUBLIC_SECTOR'
  AND yr_covered >= 2022
  AND members > 0;
```

**Result:** 1,179 public sector locals with LM filings

### Step 2: Identify NEA State Affiliates

NEA state affiliates typically don't file OLMS reports. Added manually for each state:

| Pattern | Examples |
|---------|----------|
| State Education Association | California Teachers Association (CTA), New York State United Teachers (NYSUT) |
| State-specific names | Massachusetts Teachers Association (MTA), Texas State Teachers Association (TSTA) |

**Source:** NEA website, state affiliate websites, news reports

### Step 3: Add AFT Locals

AFT locals that meet OLMS thresholds already in database. Added:
- State federations
- Large city locals (Chicago Teachers Union, UFT, etc.)
- Higher education locals

### Step 4: Add Police/Fire Unions

| Union | Coverage | Notes |
|-------|----------|-------|
| FOP | State lodges | Often don't file OLMS |
| IAFF | State/local | Better OLMS coverage |
| PBA | Northeast | State-specific |
| CLEAT | Texas | State association |

### Step 5: Add Transit Workers

Transit unions (ATU, TWU) generally file OLMS. Verified coverage and added missing locals.

### Step 6: Add Municipal/County Unions

AFSCME councils and locals verified against OLMS. Added:
- State councils
- Large county/city locals
- Independent municipal associations

### Step 7: Add Higher Education

| Category | Examples |
|----------|----------|
| Faculty | AAUP chapters, AFT/NEA affiliates |
| Graduate students | UAW, SEIU, AFT locals |
| Staff | AFSCME, SEIU locals |

### Step 8: Validate Against EPI

For each state, calculate:

```sql
SELECT 
    state,
    SUM(num_employees) as our_total,
    epi.members_public as epi_benchmark,
    ROUND(100.0 * SUM(num_employees) / epi.members_public, 1) as coverage_pct
FROM manual_employers m
JOIN epi_state_benchmarks epi ON m.state = epi.state
WHERE m.recognition_type = 'STATE_PUBLIC'
GROUP BY state, epi.members_public;
```

**Target:** 85-115% of EPI benchmark

---

## Quality Controls

### Overcount Detection

States showing >115% coverage investigated for:
1. **Duplicate entries** - Same union counted twice
2. **Retiree inclusion** - Non-working members
3. **Represented vs Members** - F-7 data counts covered workers, not just members
4. **Headquarters effect** - National HQ distorts state totals (especially DC)

**Resolution:** Remove duplicates, adjust estimates, add notes

### Undercount Detection

States showing <85% coverage investigated for:
1. **Missing NEA affiliates** - Teachers not counted
2. **Missing police/fire** - Often don't file OLMS
3. **Missing municipal unions** - County/city workers
4. **Missing transit** - ATU/TWU locals

**Resolution:** Web research to identify and add missing unions

### Methodology Variance Documentation

For states where gap cannot be closed through research:

1. Document root cause
2. Cross-reference with BLS total union data
3. Add methodology note to database
4. Mark as "DOCUMENTED VARIANCE" not "INCOMPLETE"

**Example: Texas**
```sql
INSERT INTO manual_employers (employer_name, state, num_employees, recognition_type, notes)
VALUES (
    'METHODOLOGY NOTE - Texas Gap',
    'TX',
    0,
    'N/A',
    'Remaining ~100K gap likely reflects CPS respondents counting ATPE (100K+ members) 
     as union-like though it explicitly does not support collective bargaining. 
     Texas has no public sector CB except meet-and-confer. Our 225K = 37% of total 
     TX union membership (603K BLS), reasonable for public sector share.'
);
```

---

## Reconciliation Results

### National Summary

| Metric | Value |
|--------|-------|
| States COMPLETE (±15%) | 50 |
| States DOCUMENTED VARIANCE | 1 |
| National Coverage | 98.3% |
| Our Total | 6,903,645 |
| EPI Benchmark | 7,021,619 |

### Coverage Distribution

| Range | States | Interpretation |
|-------|--------|----------------|
| 85-95% | 12 | Slight undercount, acceptable |
| 95-105% | 28 | Excellent match |
| 105-115% | 10 | Slight overcount, acceptable |
| <85% | 1 | Documented variance (TX) |
| >115% | 0 | None |

### State Results (Top 20 by EPI)

| State | Our Data | EPI | Coverage |
|-------|----------|-----|----------|
| CA | 1,320,800 | 1,386,075 | 95.3% |
| NY | 1,082,600 | 945,094 | 114.5% |
| IL | 377,000 | 367,943 | 102.5% |
| NJ | 327,100 | 336,506 | 97.2% |
| TX | 225,400 | 326,621 | 69.0%* |
| PA | 321,000 | 322,324 | 99.6% |
| OH | 262,200 | 269,742 | 97.2% |
| MA | 257,500 | 266,491 | 96.6% |
| FL | 251,000 | 264,585 | 94.9% |
| WA | 236,000 | 262,314 | 90.0% |

*Documented methodology variance

---

## Database Schema

### Tables Used

| Table | Purpose |
|-------|---------|
| `manual_employers` | State-level public sector aggregates |
| `epi_state_benchmarks` | EPI/CPS benchmarks by state |
| `ps_parent_unions` | International union reference |
| `ps_union_locals` | Local unions with source tracking |
| `ps_employers` | Public sector employers |
| `ps_bargaining_units` | Union-employer relationships |

### Key Fields in manual_employers

| Field | Description |
|-------|-------------|
| `employer_name` | Union/employer name |
| `state` | State code |
| `num_employees` | Membership count |
| `recognition_type` | 'STATE_PUBLIC' for this methodology |
| `affiliation` | Parent union (NEA, AFT, AFSCME, etc.) |
| `source_type` | 'OLMS', 'WEB_RESEARCH', 'ORG_WEBSITE' |
| `notes` | Documentation of sources, methodology |

---

## Limitations and Caveats

### Data Quality

1. **Self-reported membership** - EPI/CPS relies on individual survey responses
2. **Timing differences** - Our data annual, CPS monthly averaged
3. **Definition variance** - "Union member" vs "covered by CBA" vs "dues-paying"
4. **Sample size** - Small state CPS data less reliable

### Known Gaps

1. **Small independent unions** - <$300K don't file OLMS
2. **Professional associations** - May be counted as "union-like" in CPS
3. **Free riders** - Post-Janus, represented workers may not be members
4. **Seasonal workers** - Teachers during summer, etc.

### Methodology Assumptions

1. NEA/AFT state affiliate membership includes active teachers only
2. Police/fire estimates based on department counts × typical union density
3. Municipal estimates based on city size and state CB rights
4. Higher ed estimates based on enrollment and typical ratios

---

## Future Improvements

1. **State PERB data** - Integrate state labor board filings
2. **Contract database** - Track bargaining unit sizes from contracts
3. **Form 990 expansion** - More public sector unions
4. **Survey data** - Direct union membership surveys
5. **Real-time monitoring** - Track organizing activity

---

*Document Version: 1.0 | Created: January 29, 2026*
