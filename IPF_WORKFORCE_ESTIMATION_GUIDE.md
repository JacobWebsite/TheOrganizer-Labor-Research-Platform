# Iterative Proportional Fitting (IPF) for Workforce Demographic Estimation

**Project:** Labor Relations Research Platform  
**Date:** March 2026  
**Purpose:** Plain-English guide to what IPF is, the different types, and exactly which variant to use for estimating employer workforce demographics

---

## The Problem This Solves

The platform currently estimates what an employer's workforce looks like using a fixed recipe:

```
estimate = (ACS industry average × 60%) + (LODES county average × 40%)
```

This works but has a fundamental structural flaw: it's **additive**. If ACS says 30% Black workers and LODES says 50% Black workers, you get 38% — a number that doesn't actually satisfy either data source. It partially violates both constraints simultaneously.

The deeper problem: you have more information than this formula uses. You know the industry demographics. You know the county demographics. You know the employer's size. You're about to add BDS-HC firm-type benchmarks. But the 60/40 formula can't respect all of these simultaneously — adjusting to one source pulls you away from another.

**IPF solves this.** It finds the estimate that satisfies every data source you have at once, rather than blending them into a single compromise number.

---

## What IPF Is (Plain English)

IPF stands for **Iterative Proportional Fitting**. It also goes by other names — "raking," "matrix balancing," "RAS algorithm," "biproportional fitting" — depending on which field you encounter it in. They all describe the same mathematical process.

### The Grid Analogy

Imagine a spreadsheet grid where:
- Each **row** represents a race category (White, Black, Hispanic, Asian, Other)
- Each **column** represents a gender (Male, Female)
- Each **cell** holds the estimated number of workers in that combination (e.g., Black women)

You know two things about this grid:
1. The **row totals** — from ACS, you know the industry employs roughly 40% Black workers overall
2. The **column totals** — from LODES, you know the county is roughly 55% female overall

But you don't know how those two facts combine inside the cells. How many workers are specifically Black women vs. Black men vs. White women, etc.?

IPF solves this by:
1. Starting with a "best guess" grid (called the **seed**)
2. Adjusting every row to match the row totals
3. Adjusting every column to match the column totals
4. Repeating steps 2 and 3 until the grid satisfies both simultaneously

Each "round" of adjustments is an **iteration**. The algorithm keeps iterating until the grid stops changing — that's convergence. Usually takes 10–30 iterations. It always finds the same answer regardless of how many times you run it.

### Why This Is Mathematically Better Than Blending

The 60/40 blend gives you a **point estimate** — one number that compromises between two sources.

IPF gives you a **joint distribution** — a complete picture of how all demographic dimensions interact, respecting every data source simultaneously. The final estimate isn't a compromise; it's the actual maximum-likelihood answer given all available evidence.

In statistical terms: IPF finds the maximum entropy solution — the distribution that makes the fewest unsupported assumptions while satisfying all your known constraints.

---

## The Three Types of IPF

### 2D IPF — Two Constraint Dimensions

The simplest form. You have two separate lists of totals (rows and columns) and you want to find the grid that satisfies both.

**Example in your context:** 
- Row constraint: racial breakdown from ACS (White 45%, Black 32%, Hispanic 15%, Asian 8%)
- Column constraint: gender breakdown from LODES (Female 61%, Male 39%)
- Goal: estimate the full race × gender breakdown for this employer

This tells you what share of workers are in each race + gender combination, consistent with both the ACS race totals and the LODES gender totals.

**When to use:** When you only have two independent sources of demographic information.

---

### 3D IPF — Three Constraint Dimensions

Extends 2D to a third dimension. Instead of a flat grid (rows × columns), you're working with a cube (rows × columns × depth).

**Example in your context:**
- Dimension 1 (race): racial breakdown from ACS industry × state
- Dimension 2 (gender): gender breakdown from LODES county
- Dimension 3 (firm type): demographic distribution from BDS-HC for employers of this size × industry × state

The "slice" through the third dimension is what makes this more powerful — you're not just balancing race against gender, you're simultaneously making sure the overall demographic profile matches what we know about employers of this type.

**When to use:** When you have three independent data sources that each constrain the estimate from a different angle. **This is what you want for this project.**

---

### N-Dimensional IPF — Any Number of Constraints

The same principle extended to four, five, or more dimensions. Each new dimension adds another constraint.

**Possible future extension for this platform:**
- Dimension 4: occupation type from BLS OES (e.g., what share are in production vs. professional roles)
- Dimension 5: education level from BDS-HC education tables

**When to use:** When you have many high-quality data sources and the computational cost is worth the added precision. Generally overkill for a first implementation — start with 3D and expand later.

---

## The Recommended Setup for This Platform

### Which IPF Type: **3D**

Three dimensions simultaneously:

| Dimension | Data Source | What It Constrains |
|---|---|---|
| Race × Ethnicity | ACS PUMS microdata (industry × state) | Industry-level racial composition |
| Gender | LODES WAC (county level) | Local-area gender distribution |
| Firm Type | BDS-HC (industry × size × state) | What employers of this specific type look like |

### The Seed Matrix

The seed is your starting estimate — the grid IPF adjusts from. The quality of your seed matters: a better seed means fewer iterations and more realistic output.

**Three options, ranked best to worst:**

**Option 1 — ACS PUMS Microdata Seed (Recommended for most employers)**

Build the starting matrix from actual individual-level ACS survey records, cross-tabulated by race × gender × industry × state. This is real observed data, not a made-up starting point. IPF then adjusts it toward your county and firm-size constraints. Since you already have ACS PUMS data loaded in the platform, this is achievable without downloading anything new.

How to build it: Pull all ACS PUMS records for the target industry and state. Create a cross-tabulation (race × gender). Use that as your seed array. Normalize to proportions (everything sums to 1.0).

**Option 2 — EEO-1 Verified Seed (Best for federal contractors)**

For employers where you have actual EEO-1 data from the FOIA release, use that as your seed. The EEO-1 already tells you the actual race × gender × job-level breakdown for that specific company. IPF then barely needs to move — you'd just be applying small adjustments to account for the fact that the EEO-1 data is from 2016–2020 and current LODES/BDS-HC reflect more recent conditions.

This produces the most accurate estimates because you're starting from real employer-specific data rather than industry averages.

**Option 3 — Uniform Seed (Last Resort)**

Fill every cell with 1 (equal probability everywhere). IPF will adjust from scratch based only on your constraints. Fast to implement but can produce strange results when constraints are sparse. Only use this if you have no prior information at all.

---

## A Step-by-Step Example

Say you're estimating the workforce demographics of a medium-sized nursing home (NAICS 6231) in Cook County, Illinois with approximately 200 employees.

**Step 1: Build the seed matrix**

Pull ACS PUMS records for NAICS 6231 in Illinois. Cross-tabulate by race (5 categories) × gender (2 categories). Normalize to proportions. You now have a 5×2 matrix that looks roughly like:

```
           Male    Female
White      0.08    0.32
Black      0.04    0.28
Hispanic   0.02    0.14
Asian      0.01    0.08
Other      0.01    0.02
```
*All cells sum to 1.0*

**Step 2: Define Constraint 1 — Industry × State (ACS)**

From ACS for NAICS 6231 in Illinois:
- White: 38%, Black: 32%, Hispanic: 16%, Asian: 9%, Other: 5%
- These are your "row totals" that the final estimate must match

**Step 3: Define Constraint 2 — County (LODES)**

From LODES WAC for Cook County:
- Female: 74%, Male: 26%
- These are your "column totals" that the final estimate must match

**Step 4: Define Constraint 3 — Firm Size × Industry (BDS-HC)**

From BDS-HC for healthcare employers with 50–249 workers in the Midwest:
- This bucket shows 70–90% female workforce is most common
- Anchors the overall female/male distribution toward this range

**Step 5: Run 3D IPF**

The algorithm adjusts the seed matrix iteratively until all three constraints are satisfied simultaneously. After ~15 iterations, it converges to something like:

```
           Male    Female
White      0.04    0.34
Black      0.02    0.30
Hispanic   0.01    0.15
Asian      0.01    0.08
Other      0.00    0.05
```

This estimate now respects the ACS racial breakdown, the LODES county gender split, AND the BDS-HC firm-type anchor — simultaneously. No single source was arbitrarily overweighted.

**Step 6: Convert to headcounts**

Multiply proportions by estimated total employment (200 workers):
- Black women: 0.30 × 200 = ~60 workers
- White women: 0.34 × 200 = ~68 workers
- etc.

---

## Important Practical Considerations

### Constraints Must Be Consistent

The biggest practical issue: your constraints need to be mathematically compatible — they all need to refer to proportions that sum to the same total. The fix is simple: **always normalize to proportions, never use raw counts.** You're estimating the composition (what % of workers are X) not the total headcount (which you already know from establishment size data).

### Zero Cells

If your seed has a zero in any cell, that cell will stay at zero forever — IPF can only multiply, not add from nothing. For demographic estimation, avoid zeros in the seed. If a cell genuinely should be near-zero (e.g., very few workers in a category), use a small number like 0.001 instead.

### When IPF Struggles

IPF has known limitations in two situations:

1. **Very sparse data:** If your industry × state × size combination has very few ACS records (e.g., a small, specialized industry in a rural state), the seed is unreliable. Fall back to a broader seed (4-digit NAICS → 2-digit NAICS → national average).

2. **Highly contradictory constraints:** If ACS says 20% Black and LODES says 70% Black and BDS-HC says 30%, those are genuinely conflicting signals. IPF will find the best compromise, but the result should be flagged with lower confidence. This situation usually means one of your data sources is mismatched — check that the NAICS codes and geographic boundaries actually correspond to the same employer.

### Convergence Check

Always verify that your IPF run actually converged. A good convergence criterion: the maximum change in any cell between the last two iterations should be less than 0.01% (0.0001). If it hasn't converged after 50 iterations, something is wrong with the constraints.

---

## The Python Implementation

The `ipfn` package (installable via pip) handles 2D and 3D IPF with numpy arrays. For 3D implementation with your three constraint dimensions:

```python
# Install: pip install ipfn
from ipfn import ipfn
import numpy as np

# -------------------------------------------------------
# Step 1: Build seed from ACS PUMS
# Shape: (5 race categories × 2 gender × 3 industry sectors)
# Each cell is a proportion
# -------------------------------------------------------
seed = build_acs_seed(naics_code, state_fips)  # your function

# -------------------------------------------------------
# Step 2: Define constraints (all as proportions summing to 1.0)
# -------------------------------------------------------

# Constraint 1: Race proportions from ACS (applies to dimension 0)
race_margins = np.array([0.38, 0.32, 0.16, 0.09, 0.05])  # White, Black, Hispanic, Asian, Other

# Constraint 2: Gender proportions from LODES (applies to dimension 1)
gender_margins = np.array([0.26, 0.74])  # Male, Female

# Constraint 3: BDS-HC firm type profile (applies to dimensions 0 and 1 jointly)
firmtype_margins = bds_hc_lookup(naics_sector, firm_size_band, state_fips)

# -------------------------------------------------------
# Step 3: Run IPF
# -------------------------------------------------------
aggregates = [race_margins, gender_margins, firmtype_margins]
dimensions = [[0], [1], [0, 1]]  # which dimensions each constraint applies to

IPF = ipfn(seed, aggregates, dimensions)
result = IPF.iteration()

# result is now a normalized array of proportions that satisfies all constraints
# Multiply by employee count to get headcounts
```

For the BDS-HC constraint specifically, you'll need to pre-process the BDS-HC tables into a lookup function that returns the expected marginal distribution for a given industry × size × state combination. This becomes a reference table in your database.

---

## How This Fits Into the Existing Pipeline

The existing workforce composition estimation sits inside the `mv_employer_features` materialized view and the demographic estimation function. The change is surgical — you're not rebuilding the whole pipeline, just replacing the final blending step:

**Current flow:**
```
ACS industry average → multiply by 0.6
LODES county average → multiply by 0.4
Add together → final estimate
```

**New flow:**
```
ACS PUMS microdata → build seed matrix
ACS industry average → constraint 1
LODES county average → constraint 2
BDS-HC firm profile → constraint 3
Run IPF until convergence → final estimate
EEO-1 verified? → use as seed instead (for contractors)
```

The output format is the same — demographic proportions per employer. The downstream scoring system doesn't need to change. The research tool doesn't need to change. The frontend doesn't need to change. Only the estimation function itself is upgraded.

---

## Suggested Implementation Order

| Phase | Task | What It Does |
|---|---|---|
| 1 | Build ACS PUMS seed function | Creates starting matrix from existing ACS data |
| 2 | Load BDS-HC tables → `bds_hc_benchmarks` table | Makes the third constraint available |
| 3 | Implement 2D IPF (race × gender) | Simplest working version — replace the 60/40 blend |
| 4 | Extend to 3D (add BDS-HC dimension) | Full implementation with firm-type constraint |
| 5 | Add EEO-1 seed override for contractors | Highest accuracy for federal contractor employers |
| 6 | Validate: compare IPF output vs. EEO-1 actuals | Measure accuracy improvement over 60/40 baseline |

Starting with 2D IPF (Phase 3) already removes the fixed-weight problem and is the biggest single improvement. The BDS-HC third dimension (Phase 4) adds meaningful precision for industries where firm size strongly predicts workforce demographics — which BDS-HC confirmed is true across every sector.

---

## Summary Decision Table

| Question | Answer |
|---|---|
| Which IPF type? | **3D IPF** |
| Seed matrix source? | **ACS PUMS microdata** (or EEO-1 for contractors) |
| Constraint 1? | **ACS industry × state demographic proportions** |
| Constraint 2? | **LODES county demographic proportions** |
| Constraint 3? | **BDS-HC firm size × industry × state distribution** |
| Python package? | **`ipfn`** (simpler) or `scipy.optimize` with custom implementation |
| Express constraints as? | **Proportions (0–1), not raw counts** |
| Convergence threshold? | **< 0.01% change between iterations** |
| Max iterations? | **50 (flag non-convergence as a data quality issue)** |
| Fallback when data sparse? | **Widen NAICS scope (4-digit → 2-digit → national)** |

---

## Key References

| Resource | URL |
|---|---|
| Lomax et al. IPF guide (best plain-language explanation) | https://www.tandfonline.com/doi/full/10.1080/00330124.2015.1099449 |
| Loxton et al. IPF performance evaluation | https://www.jasss.org/18/2/21.html |
| `ipfn` Python package documentation | https://datascience.oneoffcoder.com/ipf.html |
| Multi-dimensional IPF example (3D race × age × gender) | https://datascience.oneoffcoder.com/ipf-ii.html |
| `mipfp` R package (alternative implementation) | https://cran.r-project.org/web/packages/mipfp/mipfp.pdf |
| Wikipedia IPF (mathematical detail) | https://en.wikipedia.org/wiki/Iterative_proportional_fitting |
| BDS-HC working paper (firm demographics data) | https://www2.census.gov/library/working-papers/2025/adrm/ces/CES-WP-25-20.pdf |
