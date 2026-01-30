# EPI State Union Benchmarks - Methodology Guide

## Overview

This document describes the new benchmark system using EPI (Economic Policy Institute) data that distinguishes between:

1. **Union Members** - Dues-paying members
2. **Represented Workers** - Workers covered by collective bargaining agreements (includes non-members)
3. **Free Riders** - Workers who are represented but not paying dues

## Critical Post-Janus Context (2018)

The Supreme Court's Janus v. AFSCME decision (2018) eliminated mandatory agency fees for public sector workers. This created a significant gap between:
- Workers covered by union contracts (represented)
- Workers paying union dues (members)

The **free rider rate** shows what percentage of covered workers are NOT paying dues.

## Data Sources

- **Source:** EPI Analysis of CPS-ORG (Current Population Survey - Outgoing Rotation Groups)
- **Years:** Most recent available for each state (2024-2025 for private sector, varies for public sector)
- **Note:** Small state public sector data may be from older years due to CPS sample size limitations

## Database Tables

### `epi_state_benchmarks`
Primary benchmark table with EPI data:

| Column | Description |
|--------|-------------|
| `members_private` | Dues-paying members in private sector |
| `members_private_year` | Year of the data |
| `members_public` | Dues-paying members in public sector |
| `members_public_year` | Year of the data |
| `members_total` | Total dues-paying members |
| `represented_private` | Workers covered by CBAs (private) |
| `represented_public` | Workers covered by CBAs (public) |
| `free_riders_public` | Represented - Members (public sector) |
| `free_rider_rate_public` | Percentage of covered workers not paying dues |

### `v_state_epi_comparison`
Comparison view between our project data and EPI benchmarks:

| Column | Description |
|--------|-------------|
| `our_lm_members` | Our LM filing membership data |
| `our_public_total` | Our manual_employers public sector data |
| `lm_vs_epi_members_pct` | Our private coverage vs EPI benchmark |
| `public_vs_epi_members_pct` | Our public coverage vs EPI benchmark |
| `private_gap` | EPI members - Our LM members |
| `public_gap` | EPI members - Our public sector data |

## How to Compare Our Data

### Private Sector (F-7 and LM Data)

| Our Data Source | EPI Benchmark to Compare |
|-----------------|-------------------------|
| **F-7 covered workers** | `represented_private` (workers under CBAs) |
| **LM reported members** | `members_private` (dues-paying members) |

F-7 data reports workers covered by bargaining agreements, so compare to **represented** numbers.
LM data reports dues-paying members, so compare to **members** numbers.

### Public Sector (manual_employers)

| Our Data Source | EPI Benchmark to Compare |
|-----------------|-------------------------|
| **manual_employers membership** | `members_public` (dues-paying members) |
| **manual_employers total + free riders** | `represented_public` (all covered workers) |

If our public sector numbers exceed `members_public` but are close to `represented_public`, 
we may be counting represented workers rather than just dues-paying members.

## Understanding the Free Rider Gap

Example for California (2025):
- Public sector members: 1,386,075
- Public sector represented: 1,509,931
- Free riders: 123,856 (8.2% rate)

This means ~124K workers in CA are covered by union contracts but NOT paying dues post-Janus.

**High Free Rider States (>20%):**
- Utah: 39.5%
- South Carolina: 38.4%
- New Mexico: 26.7%
- Iowa: 26.2%
- South Dakota: 25.3%
- North Dakota: 23.4%
- Kansas: 22.3%

**Low Free Rider States (<5%):**
- New York: 2.4%
- Hawaii: 2.5%
- Illinois: 2.6%
- Minnesota: 2.6%
- Rhode Island: 2.6%
- Delaware: 3.0%
- Alaska: 3.3%

## Interpretation Guidelines

### When Our LM Data > EPI Members Private:
- Possible headquarters location effects (national unions headquartered in state)
- Multi-state unions counting all members at HQ address
- Need to verify if membership is properly allocated by state

### When Our LM Data < EPI Members Private:
- Incomplete LM coverage
- Some unions not filing or late filing
- May need additional research

### When Public Sector Data > EPI Members Public:
- Might be counting represented workers, not just members
- Could indicate good coverage of all organized workers
- Compare to `represented_public` for validation

### When Public Sector Data < EPI Members Public:
- Gap in coverage - need additional research
- Priority states for public sector research

## States Requiring Public Sector Research (Largest Gaps)

Based on current coverage, these states have the largest public sector gaps:

1. Pennsylvania: 322,324 members, 0 in our data
2. Massachusetts: 266,491 members, 0 in our data
3. Ohio: 269,742 members, 50 in our data
4. Washington: 262,314 members, 0 in our data
5. Florida: 264,585 members, 0 in our data
6. Michigan: 205,302 members, 0 in our data
7. Minnesota: 187,397 members, 0 in our data

## CSV Exports

Two CSV files have been created:

1. `epi_state_benchmarks_2025.csv` - Complete EPI benchmark data
2. `state_coverage_vs_epi_benchmarks.csv` - Comparison with our project data

## SQL Queries for Analysis

```sql
-- View all EPI benchmarks
SELECT * FROM epi_state_benchmarks ORDER BY members_total DESC;

-- Compare our data vs EPI benchmarks
SELECT * FROM v_state_epi_comparison ORDER BY epi_members_total DESC;

-- Find states with high free rider rates
SELECT state, state_name, members_public, represented_public, 
       free_riders_public, free_rider_rate_public
FROM epi_state_benchmarks
WHERE free_rider_rate_public > 15
ORDER BY free_rider_rate_public DESC;

-- Find states needing public sector research
SELECT state, state_name, epi_members_public, our_public_total, public_gap
FROM v_state_epi_comparison
WHERE public_gap > 50000
ORDER BY public_gap DESC;
```

## Date Created
January 29, 2026
