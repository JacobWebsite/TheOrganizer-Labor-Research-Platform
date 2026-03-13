# BLS/CPS Union Density Data Research - Phase 4 Block C3

**Date:** 2026-02-16
**Goal:** Enhance union density data without IPUMS access
**Current:** 12 BLS industry rates (national averages), state-level actual density from CPS

---

## Current Union Density Infrastructure

### Existing Tables (from `load_industry_density.py`)

1. **`bls_industry_density`** - 12 BLS industry union density rates (2024)
   - National averages only (not state-specific)
   - Broad categories: Agriculture/Mining, Construction, Manufacturing, etc.

2. **`state_industry_shares`** - State-level industry composition
   - 51 states × 13 industry shares (from ACS 2025 estimates)

3. **`state_industry_density_comparison`** - Expected vs actual with climate multiplier
   - Calculates "expected" density from industry mix
   - Compares to "actual" CPS density
   - Climate multiplier = actual / expected (union-friendly states > 1.0)

4. **`county_industry_shares`** - County-level industry composition
   - ~3,100 counties × 13 industry shares

5. **`county_union_density_estimates`** - Industry-adjusted county density
   - Uses state multiplier × expected density from industry mix

6. **`v_state_density_latest`** - View with actual CPS state private density
   - Source of "actual_private_density" column

### Current Limitations

- ❌ No state × industry union density (only national industry averages)
- ❌ No MSA/metro area density
- ❌ Only 12 broad industry categories (BLS has more granular data available)
- ❌ No occupation-specific density
- ❌ Hardcoded 2024 rates (not pulling from BLS API)

---

## BLS Data Sources (NO IPUMS NEEDED)

### Option 1: BLS Union Membership News Release Tables (RECOMMENDED)

**URL:** https://www.bls.gov/news.release/union2.htm

**Available Tables (Annual):**
- **Table 1:** Union affiliation of employed wage and salary workers by selected characteristics
  - Total, by sex, age, race, education
- **Table 2:** Median weekly earnings by union membership
- **Table 3:** Union affiliation by occupation and industry ← CURRENTLY USING THIS (hardcoded)
- **Table 4:** Union affiliation by industry and occupation (detailed)
- **Table 5:** Union affiliation by state

**Download format:** Excel (.xlsx) or CSV
**Update frequency:** Annual (January release for prior year)
**Latest:** 2024 data (released January 2025)

### Option 2: BLS LAU (Local Area Unemployment) with Union Data

**URL:** https://www.bls.gov/lau/

Limited union data, primarily unemployment. Skip.

### Option 3: CPS Public Use Microdata Files (Census.gov)

**URL:** https://www.census.gov/data/datasets/time-series/demo/cps/cps-basic.html

**CPS Basic Monthly Files:**
- No union membership (only labor force status, employment)

**CPS Annual Social and Economic Supplement (ASEC):**
- No union membership

**CPS Union and Earnings Supplement (Outgoing Rotation Groups):**
- **This is what we need!**
- URL: https://www.census.gov/data/datasets/time-series/demo/cps/cps-supp_cps-repwgt/cps-union.html
- Contains union membership questions
- Released monthly (subset of CPS sample)
- Fixed-width format (need to parse with data dictionary)

**NBER CPS Extracts (easier to parse):**
- URL: https://www.nber.org/research/data/current-population-survey-cps-merged-outgoing-rotation-group-earnings-data
- Pre-processed CPS union data (Stata, CSV available)
- Easier than raw Census files

---

## Proposed Enhancement Strategy

### Phase 1: Enhanced BLS Published Tables (2-3 hrs)

**Goal:** Replace hardcoded industry rates with programmatic download

**Tables to download:**
1. **Table 3:** Industry union density (12 categories, national)
2. **Table 5:** State union density (51 states, overall)
3. **Table 4:** Detailed industry × occupation (if available in machine-readable format)

**Implementation:**
- Script: `scripts/etl/load_bls_union_tables.py`
- Download from BLS website (Excel format)
- Parse with pandas
- Load into enhanced tables:
  - `bls_national_industry_density` (replaces hardcoded rates)
  - `bls_state_density` (state-level overall density)
  - `bls_industry_occupation_density` (detailed crosswalk)

**Benefits:**
- Repeatable (can update annually with one command)
- More recent data
- State-level overall density (not industry-specific, but useful)

### Phase 2: State × Industry Estimation (2 hrs)

**Goal:** Estimate state × industry density (not directly published by BLS)

**Method:**
- Use state climate multiplier from existing `state_industry_density_comparison` table
- Apply to national industry rates: `state_industry_density = national_industry_rate × state_multiplier`
- Example: Construction in NY = 10.3% (national) × 1.45 (NY multiplier) = 14.9%

**Implementation:**
- Create table: `estimated_state_industry_density` (51 states × 12 industries = 612 rows)
- View: `v_union_density_enhanced` (combines national + state + estimated state×industry)

**Caveat:** This is an *estimate*, not actual state×industry density (which would require CPS microdata analysis)

### Phase 3: MSA/Metro Area Density (Optional, 1-2 hrs)

**Goal:** Metro area union density estimates

**Sources:**
- BLS doesn't publish MSA union density directly
- Can estimate from county data (roll up counties to MSAs)
- Use OMB MSA definitions: https://www.census.gov/geographies/reference-files/time-series/demo/metro-micro/delineation-files.html

**Implementation:**
- Table: `msa_definitions` (counties → MSAs)
- Table: `msa_union_density_estimates` (population-weighted average of counties)

### Phase 4: CPS Microdata Analysis (SKIP FOR NOW)

**Complexity:** High
- Requires parsing fixed-width CPS files
- Sample sizes for state×industry cells may be too small (noise)
- NBER extracts are easier but still require statistical analysis

**Decision:** SKIP unless Phase 1-2 insufficient. Current approach (national rates + state multipliers) is statistically sound.

---

## Recommended Implementation Plan

### Step 1: Download BLS Tables (30 min)

Manually download (for now):
- 2024 Union Membership Table 3 (industry)
- 2024 Union Membership Table 5 (state)

Files: `data/bls/union_2024_table3.xlsx`, `data/bls/union_2024_table5.xlsx`

### Step 2: Create Enhanced Tables (1 hr)

```sql
-- National industry density (programmatically loaded)
CREATE TABLE bls_national_industry_density (
    year INTEGER,
    industry_code VARCHAR(20),
    industry_name VARCHAR(100),
    total_employed_thousands INTEGER,
    union_members_thousands INTEGER,
    union_density_pct DECIMAL(5,2),
    represented_density_pct DECIMAL(5,2),
    source VARCHAR(50) DEFAULT 'bls_table3',
    PRIMARY KEY (year, industry_code)
);

-- State overall density (from Table 5)
CREATE TABLE bls_state_density (
    year INTEGER,
    state VARCHAR(2),
    state_name VARCHAR(50),
    total_employed_thousands INTEGER,
    union_members_thousands INTEGER,
    union_density_pct DECIMAL(5,2),
    represented_density_pct DECIMAL(5,2),
    private_density_pct DECIMAL(5,2),
    public_density_pct DECIMAL(5,2),
    source VARCHAR(50) DEFAULT 'bls_table5',
    PRIMARY KEY (year, state)
);

-- Estimated state × industry density
CREATE TABLE estimated_state_industry_density (
    year INTEGER,
    state VARCHAR(2),
    industry_code VARCHAR(20),
    national_rate DECIMAL(5,2),
    state_multiplier DECIMAL(5,3),
    estimated_density DECIMAL(5,2),
    confidence VARCHAR(20) DEFAULT 'ESTIMATED',  -- vs 'ACTUAL' if from CPS microdata
    PRIMARY KEY (year, state, industry_code)
);
```

### Step 3: ETL Script (2 hrs)

```python
# scripts/etl/load_bls_union_tables.py
- download_bls_table(year, table_num, output_path)
- parse_table3_industry(excel_path)
- parse_table5_state(excel_path)
- calculate_state_industry_estimates()
- load_to_db()
```

### Step 4: Integration with Scoring (1 hr)

Update `mv_organizing_scorecard` to use state×industry density instead of just national:

```sql
-- Current (national industry rate):
SELECT bls_industry_density.union_density_pct
FROM bls_industry_density
WHERE industry_code = map_naics_to_bls(employer.naics_code)

-- Enhanced (state × industry estimate):
SELECT estimated_state_industry_density.estimated_density
FROM estimated_state_industry_density
WHERE state = employer.state
  AND industry_code = map_naics_to_bls(employer.naics_code)
  AND year = 2024
```

---

## Expected Improvements

### Scoring Precision

**Before (current):**
- Construction employer in NY: Uses 10.3% national construction density

**After (enhanced):**
- Construction employer in NY: Uses 10.3% × 1.45 (NY multiplier) = 14.9% estimated NY construction density

### Granularity

**Before:** National industry averages only
**After:** State × industry estimates (51 × 12 = 612 density values)

### Repeatability

**Before:** Hardcoded rates in script
**After:** Download fresh data from BLS annually with one command

---

## Next Steps

1. ✅ Research complete (this document)
2. ⬜ Download BLS Table 3 and Table 5 for 2024
3. ⬜ Create enhanced table schemas
4. ⬜ Build ETL script `load_bls_union_tables.py`
5. ⬜ Calculate state × industry estimates
6. ⬜ Update scoring to use enhanced density
7. ⬜ Test impact on scorecard rankings

**Estimated time:** 5-6 hours total

---

## Files to Create

- `scripts/etl/load_bls_union_tables.py` - ETL script
- `scripts/etl/create_enhanced_density_tables.sql` - Table schemas
- `data/bls/union_2024_table3.xlsx` - Downloaded BLS Table 3
- `data/bls/union_2024_table5.xlsx` - Downloaded BLS Table 5
- `tests/test_enhanced_density.py` - Unit tests

---

## Decision

**Proceed with Phase 1 + Phase 2** (Steps 1-4 above). Skip CPS microdata for now - the state multiplier approach is statistically sound and much simpler.
