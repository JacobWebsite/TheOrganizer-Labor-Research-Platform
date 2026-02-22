# MV_UNIFIED_SCORECARD - Complete Reference Guide

## Overview

`mv_unified_scorecard` is a **materialized view** that scores all **146,863 F7 employers** on an **8-factor organizing difficulty scale (0-10 per factor)**. It is the primary data structure for the labor relations research platform's employer ranking and targeting functionality.

**Key Facts:**
- **Total employers:** 146,863 (67,552 post-2020 active + 79,311 historical pre-2020)
- **Score range:** 0.0 to 10.0 (average score varies by factor availability)
- **Tiers:** TOP (>=7.0), HIGH (>=5.0), MEDIUM (>=3.5), LOW (<3.5) average
- **Coverage:** 2 always-available factors + up to 5 conditional factors
- **Refresh:** Run `python scripts/scoring/build_unified_scorecard.py --refresh`

---

## Column Structure (Complete Schema)

### Employer Identification

| Column | Type | Description |
|--------|------|-------------|
| `employer_id` | TEXT (PK) | Unique F7 employer identifier |
| `employer_name` | TEXT | Legal employer name |
| `state` | CHAR(2) | Two-letter state code |
| `city` | TEXT | City name |

### Master Data

| Column | Type | Description |
|--------|------|-------------|
| `naics` | CHAR(6) | 6-digit NAICS code (industry) |
| `naics_detailed` | CHAR(6) | Detailed NAICS (same as naics in current implementation) |
| `latest_unit_size` | INTEGER | Most recent bargaining unit size (from OLMS filings) |
| `latest_union_fnum` | CHAR(5) | Union file number (OLMS) |
| `latest_union_name` | TEXT | Union name |
| `is_historical` | BOOLEAN | TRUE if last filing pre-2020 |
| `canonical_group_id` | INTEGER | Reference to employer_canonical_groups for multi-employer tracking |
| `is_canonical_rep` | BOOLEAN | TRUE if this employer represents the group |
| `source_count` | INTEGER | Number of data sources matched to this employer |

### Data Source Flags

Boolean columns indicating whether data is available from each source:

| Column | Type | Description |
|--------|------|-------------|
| `has_osha` | BOOLEAN | OSHA establishment match found |
| `has_nlrb` | BOOLEAN | NLRB election data found |
| `has_whd` | BOOLEAN | Wage & Hour Division violations found |
| `has_990` | BOOLEAN | IRS Form 990 filing available |
| `has_sam` | BOOLEAN | SAM.gov registration found |
| `has_sec` | BOOLEAN | SEC EDGAR filing found |
| `has_gleif` | BOOLEAN | GLEIF entity identifier found |
| `has_mergent` | BOOLEAN | Mergent Intellect data found |
| `is_public` | BOOLEAN | Publicly traded company |
| `is_federal_contractor` | BOOLEAN | Identified as federal contractor |

### Corporate Ownership

| Column | Type | Description |
|--------|------|-------------|
| `corporate_family_id` | TEXT | Corporate family linkage ID (for hierarchy analysis) |
| `federal_obligations` | NUMERIC | Total federal contract obligations (USD) |
| `federal_contract_count` | INTEGER | Number of federal contracts |
| `ein` | TEXT | Employer Identification Number (IRS) |
| `ticker` | TEXT | Stock ticker symbol (if public) |

---

## 7 SCORING FACTORS (Each 0-10 Scale)

### Factor 1: OSHA Safety Violations (`score_osha`)

**Availability:** NULL if no OSHA match; otherwise 0-10

**Methodology:**
- Base score (0-7): Decayed industry-normalized violation ratio
  - Violations > 3.0x industry avg = 7 points
  - Violations > 2.0x industry avg = 5 points
  - Violations > 1.0x industry avg = 3 points
  - Violations = 0 or 1x avg = 0 points
- Severity bonus (+0-3): Willful violations (×2) + repeat violations
- Temporal decay: 10-year half-life (older inspections worth less)
- Industry normalization: Uses ref_osha_industry_averages by NAICS prefix

**Data source:** `osha_f7_matches` + `osha_establishments` + `osha_violation_summary`

**Example ranges:**
- Score 9-10: 50+ violations with willful/repeat, recent inspection
- Score 5-7: 20-50 violations, decayed recent inspection
- Score 1-3: < 10 violations or very old inspection
- Score 0: No violations recorded

---

### Factor 2: NLRB Election Activity (`score_nlrb`)

**Availability:** NULL if no NLRB match; otherwise 1-10 (minimum 1 if data exists)

**Methodology:**
- Base score (1-7): Election activity level
  - 3+ elections = 7 points
  - 2 elections = 5 points
  - 1 election with union win = 4 points
  - 1 election, no win = 3 points
  - No elections = 1 point
- Temporal decay: 7-year half-life (recent elections weighted more)
- Applied to base via MAX-decay in aggregation

**Data source:** `nlrb_participants` + `nlrb_elections`

**Example ranges:**
- Score 8-10: 3+ elections in last 3 years with wins
- Score 5-7: 2+ elections, some recent activity
- Score 3-4: 1 election, union activity present
- Score 1-2: No election activity, minimal presence

---

### Factor 3: Wage Theft Violations (`score_whd`)

**Availability:** NULL if no WHD match; otherwise 0-10

**Methodology:**
- Base score progression:
  - Repeat violator = 8 points
  - Penalties > $100K = 7 points
  - Backwages > $500K = 6 points
  - Penalties > $10K OR violations > 10 = 5 points
  - Backwages > $50K = 4 points
  - Any violation = 2 points
  - No violations = 1 point (minimum)
- Temporal decay: 7-year half-life on latest finding

**Data source:** `whd_f7_matches` + `whd_cases`

**Example ranges:**
- Score 8-10: Repeat violator with $500K+ backwages, recent
- Score 5-7: $100K+ penalties or multiple violations
- Score 2-4: Single case with modest damages
- Score 0-1: No violations (rare, since NULL when no data)

---

### Factor 4: Government Contracts (`score_contracts`)

**Availability:** NULL if not federal contractor; otherwise 1-10

**Methodology:**
- No decay (federal contracting is structural, not temporal)
- Scoring by contract value:
  - > $5M obligations = 10 points
  - > $1M obligations = 7 points
  - > $100K obligations = 4 points
  - > $0 obligations = 2 points
  - No contracts = 1 point (but this means is_federal_contractor = FALSE)

**Data source:** `f7_employers_deduped.is_federal_contractor` + `.federal_obligations`

**Example ranges:**
- Score 9-10: $5M+ federal contracts
- Score 6-8: $1M-5M in obligations
- Score 3-5: $100K-1M in federal work
- Score 1-2: Minimal federal contracts or not a contractor (NULL)

---

### Factor 5: Union Proximity (`score_union_proximity`)

**Availability:** Always available (1-10)

**Methodology:**
- Based on canonical employer group size and geographic reach
- Scoring:
  - Cross-state group + 5+ members = 10 points
  - Cross-state group (any size) = 8 points
  - Same-state group + 5+ members = 7 points
  - Same-state group + 3-4 members = 5 points
  - Same-state group + 2 members = 3 points
  - Single employer (no group) = 1 point

**Data source:** `employer_canonical_groups` + `f7_employers_deduped.canonical_group_id`

**Example ranges:**
- Score 10: National union with 10+ employers in multiple states
- Score 7-8: Regional union covering 5+ employers
- Score 3-5: Local/small group (2-4 employers same state)
- Score 1-2: Single isolated employer (most common)

---

### Factor 6: Financial / Industry Viability (`score_financial`)

**Availability:** NULL only if no NAICS code; otherwise 0-10

**Methodology:**
- Base score (0-7): BLS industry employment projection (2024-2034)
  - Growth > 10% = 7 points
  - Growth 5-10% = 5 points
  - Growth 0-5% = 3 points
  - Data available but 0% growth = 2 points
  - No BLS data for NAICS = 2 points
- Public company bonus (+2): More leverage, data availability
- Nonprofit bonus (+1): Has Form 990 filing

**Data source:** `bls_industry_projections` + `f7_employers_deduped.is_public`, `.has_990`

**Example ranges:**
- Score 9-10: Growing industry + public company or nonprofit data
- Score 5-7: Growing industry, standard private employer
- Score 3-4: Declining/stable industry
- Score 1-2: Shrinking industry or no NAICS code (NULL)

---

### Factor 7: Employer Size (`score_size`)

**Availability:** Always available (1-10)

**Methodology:**
- Optimal range for organizing: 50-250 employees
- Scoring by unit size:
  - 50-250 employees = 10 points (sweet spot)
  - 251-500 employees = 8 points
  - 25-49 employees = 6 points
  - 501-1000 employees = 4 points
  - < 25 or > 1000 = 2 points
- Reflects both organizing difficulty (large = harder) and leverage (small = fragile)

**Data source:** `f7_employers_deduped.latest_unit_size` (from OLMS filings)

**Example ranges:**
- Score 9-10: 50-250 employees
- Score 6-8: 25-500 employees
- Score 2-4: < 25 or > 500 employees

---

## Aggregate Metrics

### `factors_available`

**Type:** INTEGER (0-7)

**Description:** Count of non-NULL factor scores. Since union_proximity and size are always available, minimum is 2.

**Range:** 2-7 (most employers have 2-3 factors)

**Interpretation:**
- 7 factors: Extremely well-documented employer (rare: ~2-3%)
- 5-6 factors: Strong data coverage (rare: ~5-10%)
- 3-4 factors: Typical multi-source match (common: ~40%)
- 2 factors: Union proximity + size only (common: ~50%)

---

### `unified_score`

**Type:** NUMERIC(4,2)

**Description:** Average of all non-NULL factor scores, rounded to 2 decimals. TRUE average ignores NULL values.

**Formula:** `SUM(non-NULL factors) / COUNT(non-NULL factors)`

**Range:** 0.5 to 10.0 (observed range typically 2.5-8.0 for active employers)

**Important:** NOT a sum (which would be 0-70), but a per-factor average.

**Example calculations:**
- Employer A: OSHA=5, NLRB=6, size=10, union_prox=2 = (5+6+10+2)/4 = **5.75**
- Employer B: size=10, union_prox=3 = (10+3)/2 = **6.50** (fewer factors, higher average)
- Employer C: All factors, avg=4.2 = **4.20** (7 factors, lower average due to sample)

---

### `coverage_pct`

**Type:** NUMERIC(5,1)

**Description:** Percentage of available factors scored (0-100).

**Formula:** `100 * factors_available / 7`

**Interpretation:**
- 100%: All 7 factors scored (< 5% of employers)
- 57-86%: 4-6 factors (common: ~30%)
- 29-43%: 2-3 factors (very common: ~65%)

---

### `score_tier`

**Type:** CHAR(8)

**Description:** Priority tier based on unified_score average.

**Tiers:**

| Tier | Average Score | Interpretation |
|------|----------------|-----------------|
| TOP | >= 7.0 | Highest priority targets (rare) |
| HIGH | 5.0-6.9 | Strong targets (moderate) |
| MEDIUM | 3.5-4.9 | Fair targets (common) |
| LOW | < 3.5 | Lower priority (common) |

**Conversion:** `score_tier` recalculates using same avg logic as `unified_score`.

---

## Example Records

### HIGH Coverage Employer (6/7 factors)

Hypothetical large logistics company in strong union state:

```
employer_id:          'F7_00012345'
employer_name:        'UNION LOGISTICS INC'
state:                'NY'
city:                 'Buffalo'
naics:                '493100'  (Warehousing and storage)
latest_unit_size:     285

-- Data sources
has_osha:             TRUE
has_nlrb:             TRUE
has_whd:              TRUE
is_federal_contractor: TRUE
is_public:            FALSE
has_990:              FALSE

-- Factor scores
score_osha:           7          (28 violations, recent, severe)
score_nlrb:           6          (2 elections in 5 years, 1 union win)
score_whd:            5          (12K penalties, 1 violation)
score_contracts:      4          ($250K federal obligations)
score_union_proximity: 7          (5-employer group, same state)
score_financial:      5          (4% industry growth, stable)
score_size:           10         (285 employees, perfect size)

-- Aggregates
factors_available:    7
unified_score:        6.29       (49/7)
coverage_pct:         100.0
score_tier:          'HIGH'
```

---

### MEDIUM Coverage Employer (3/7 factors)

Typical small healthcare nonprofit:

```
employer_id:          'F7_00045678'
employer_name:        'METRO HEALTH SERVICES'
state:                'CA'
city:                 'Oakland'
naics:                '621610'  (Home healthcare services)
latest_unit_size:     95

-- Data sources
has_osha:             FALSE
has_nlrb:             FALSE
has_whd:              FALSE
is_federal_contractor: FALSE
is_public:            FALSE
has_990:              TRUE       (but no bonus since no financial score)

-- Factor scores
score_osha:           NULL       (no match)
score_nlrb:           NULL       (no match)
score_whd:            NULL       (no match)
score_contracts:      NULL       (not contractor)
score_union_proximity: 2          (isolated, no group)
score_financial:      3          (2% growth, stable sector, has 990)
score_size:           10         (95 employees, strong size)

-- Aggregates
factors_available:    3          (should be 2 minimum, but 990 bonus adds 1)
unified_score:        5.00       (15/3)
coverage_pct:         42.9
score_tier:          'MEDIUM'
```

---

### LOW Coverage Employer (2/7 factors)

Isolated single establishment, no external matches:

```
employer_id:          'F7_00098765'
employer_name:        'ACME RETAIL CORP'
state:                'MS'
city:                 'Jackson'
naics:                '452111'  (Supermarkets)
latest_unit_size:     40

-- Data sources
has_osha:             FALSE
has_nlrb:             FALSE
has_whd:              FALSE
is_federal_contractor: FALSE
is_public:            FALSE
has_990:              FALSE

-- Factor scores
score_osha:           NULL       (no match)
score_nlrb:           NULL       (no match)
score_whd:            NULL       (no match)
score_contracts:      NULL       (not contractor)
score_union_proximity: 1          (single employer, no group)
score_financial:      2          (4% growth, no 990, standard naics)
score_size:           6          (40 employees, smaller)

-- Aggregates
factors_available:    2          (minimum: only union_prox + size)
unified_score:        3.00       (6/2)
coverage_pct:         28.6
score_tier:          'LOW'
```

---

## Using the Scorecard

### Query Examples

**Get top 100 targets nationwide:**
```sql
SELECT employer_name, state, city, unified_score, score_tier, factors_available
FROM mv_unified_scorecard
WHERE score_tier IN ('TOP', 'HIGH')
ORDER BY unified_score DESC
LIMIT 100;
```

**Find high-opportunity targets with multiple data sources:**
```sql
SELECT employer_name, state, unified_score, source_count, factors_available
FROM mv_unified_scorecard
WHERE unified_score >= 6.0
  AND factors_available >= 5
  AND state = 'CA'
ORDER BY unified_score DESC;
```

**Identify OSHA organizing angles:**
```sql
SELECT employer_name, city, score_osha, total_violations, latest_inspection
FROM mv_unified_scorecard
WHERE score_osha >= 6
ORDER BY score_osha DESC, latest_inspection DESC;
```

**List poorly-documented targets (opportunity for research):**
```sql
SELECT employer_name, state, city, unified_score, factors_available
FROM mv_unified_scorecard
WHERE factors_available <= 2
  AND unified_score >= 5.0
ORDER BY state, unified_score DESC;
```

---

## Data Quality Notes

**CRITICAL WARNINGS:**

1. **NLRB confidence scale bug:** NLRB matches use integer confidence (90, 98) vs. other sources (0.0-1.0 decimal). Never compare cross-source without normalizing.

2. **Legacy match tables out of sync:** `osha_f7_matches` has 145,134 rows vs. 97,142 active in `unified_match_log`. Use UML as authoritative source.

3. **NULL factors are intentional:** NULL means "no data source available," not "score is zero." NULL values are excluded from average calculation.

4. **Temporal decay assumptions:**
   - OSHA: 10-year half-life (violations older than 10 years worth ~50%)
   - NLRB: 7-year half-life
   - WHD: 7-year half-life
   - Contracts: No decay (federal work is structural)

5. **BLS data gaps:** ~2% of NAICS codes lack industry projections. These default to score 2 (floor for stability).

---

## Refresh Procedure

**Manual refresh (full rebuild):**
```bash
cd /sessions/affectionate-happy-gauss/mnt/labor-data-project
python scripts/scoring/build_unified_scorecard.py --refresh
```

**Automated refresh (part of pipeline):**
```bash
python scripts/maintenance/refresh_materialized_views.py
```

**Verification:**
```sql
-- Check row count
SELECT COUNT(*) FROM mv_unified_scorecard;  -- Should be 146,863

-- Check score distribution
SELECT MIN(unified_score), AVG(unified_score), MAX(unified_score),
       COUNT(CASE WHEN factors_available >= 5 THEN 1 END) AS well_documented
FROM mv_unified_scorecard;

-- Check tier distribution
SELECT score_tier, COUNT(*) FROM mv_unified_scorecard GROUP BY score_tier;
```

---

## API Endpoint

Primary endpoint: `/api/organizing/scorecard`

```
GET /api/organizing/scorecard?sort=score&limit=100&tier=HIGH
GET /api/organizing/scorecard/{estab_id}
```

Returns JSON with all columns above + calculated stats.

