# Claude Code Prompt: Demographics Method Improvements + Fresh Holdout Set

## Context (Read First)

You are working on a workforce demographics estimation system. The system tries to guess what a company's workforce looks like racially and by gender, using public government data sources since most companies don't publish this information.

We have already built and tested 6 estimation methods (M1–M6) against 200 real companies where we know the true answer from government EEO-1 filings. The results are documented in:
- `scripts/analysis/demographics_comparison/` — all existing code
- `DEMOGRAPHICS_METHODOLOGY_COMPARISON.md` — the 200-company results

**Do not modify any existing files.** Add new methods and new scripts only. The existing 6 methods must remain exactly as they are — we need them as the unchanged baseline to compare against.

---

## What We're Building

Two things:

1. **Six improved method variants** — one targeted improvement per existing method, each added as a new method in `methodologies.py`
2. **A fresh holdout set of 200 companies** — a second randomly selected group, locked away, used only for the final honest comparison at the end

These will be tested by running the existing `run_comparison_200.py` logic against both the original 200 and the new holdout 200.

---

## Part 1: The Six Method Improvements

Add each of these as a new method in `scripts/analysis/demographics_comparison/methodologies.py`. Name them M1b, M2b, M3b, M4b, M5b, M7 (we skip M6 entirely — it has been eliminated). Each new method is a standalone function, same input/output signature as the existing methods.

---

### M1b — Learned Weights by Industry Group

**What M1 currently does:** Blends ACS (industry signal) and LODES (county signal) at a fixed 60/40 ratio for every company regardless of industry.

**What M1b does differently:** Calculates the optimal ACS/LODES weight split *per industry group* by finding which weights minimize MAE across the original 200-company validation set. Stores those optimal weights in a lookup table inside the function. For any industry not in the table, falls back to 60/40.

**Implementation notes:**
- Use the 18 NAICS industry groups already defined in `config.py`
- For each group, try weight combinations from 30/70 to 90/10 in 5-point increments
- Pick the combination that minimizes race MAE across the companies in that group from the original 200-company results CSV (`comparison_200_detailed.csv`)
- The lookup table should be hardcoded in the function after you calculate it — not recalculated at runtime
- If fewer than 3 companies in a group, use 60/40 default
- Apply the same weight logic as M1 otherwise (same ACS and LODES sources, same normalization)

---

### M2b — Workplace Tract Instead of Residential Tract

**What M2 currently does:** Blends ACS (50%) + LODES county (30%) + Census tract residential demographics (20%). The tract data measures who *lives* near the company, not who works there.

**What M2b does differently:** Replaces the residential tract layer with LODES workplace-area tract demographics — meaning: the demographic breakdown of people whose jobs are located *in* that specific census tract. This measures actual workers rather than nearby residents.

**Implementation notes:**
- The existing `data_loaders.py` queries `cur_lodes_geo_metrics` for county-level LODES data
- LODES data in that table should also have tract-level breakdowns — query at tract level using the company's census tract FIPS code (derivable from ZIP → county → tract lookup, or use the tract field if already available on the company record)
- If tract-level LODES data is unavailable for a company, fall back to county-level LODES (same as M2 behavior)
- Keep the same 50/30/20 weights — only the source of the third layer changes
- If tract lookup fails entirely, fall back to M1 behavior (60/40 ACS/LODES)

---

### M3b — Dampened IPF

**What M3 currently does:** Multiplies ACS and LODES proportions together, then normalizes. This amplifies whatever group is already dominant — if both sources say 70% White, the product gives ~91% White before normalization. Works well for homogeneous areas, catastrophically bad for diverse ones.

**What M3b does differently:** Applies a square root to each proportion before multiplying. This "dampens" the amplification so the majority group can't run away. Mathematically: `est_k = (sqrt(ACS_k) * sqrt(LODES_k)) / sum(sqrt(ACS_j) * sqrt(LODES_j))`.

**Implementation notes:**
- This is a one-line change to the IPF formula in terms of logic
- Apply dampening to the race dimension only — keep standard IPF for gender (gender already works well)
- All other behavior identical to M3 (same sources, same fallback logic)
- The square root approach is the simplest valid dampening — do not use other exponents

---

### M4b — State-Level Occupation Demographics

**What M4 currently does:** Looks at the mix of job types (occupations) in an industry nationally, then weights ACS demographic data by those occupational proportions. Uses national occupation averages — a software developer in California is treated identically to one in Nebraska.

**What M4b does differently:** Uses state-level occupation demographic data from ACS instead of national. The ACS `acs_occupation_demographics` table (or equivalent) should have race/gender breakdowns by SOC occupation code *and* state. Query it filtered to the company's state.

**Implementation notes:**
- Check `data_loaders.py` for the existing occupation data query — identify whether it currently filters by state or pulls national
- If state-level data exists in the table, add a state filter parameter to the query
- If a specific SOC × state combination has fewer than 100 workers in ACS (too small to be reliable), fall back to the national figure for that occupation
- Keep top-30 SOC occupation list and 70/30 final blend with LODES — same as M4
- If no occupation data available at all, fall back to M1 (same as M4's existing fallback)

---

### M5b — Minority Share Adaptive Weighting

**What M5 currently does:** Uses industry-adaptive ACS/LODES weights — some industries get 40/60 (local labor dominated), others 75/25 (industry dominated). These weights were hand-coded guesses.

**What M5b does differently:** Adds a second dimension to the weight adjustment based on the county's minority share. When the county minority share is above 30%, shift weight *away* from LODES (which will regress toward that county's average) and *toward* ACS (which at least captures national industry patterns). This directly addresses the regression-to-mean problem for diverse counties.

**Implementation notes:**
- Start from M5's existing industry weight lookup as the base weights
- Get county minority share from `cur_lodes_geo_metrics` — this is the `pct_minority` field (stored as 0–1 proportion, multiply by 100 for percentage)
- Adjustment rule: if county minority share > 30%, add +10pp to ACS weight (subtract 10pp from LODES weight). If > 50%, add +20pp to ACS weight. Cap ACS weight at 85%.
- Apply the same adjustment logic to all 18 industry groups consistently
- If LODES county data unavailable, fall back to ACS-only (same as M5's existing fallback)

---

### M7 — Hybrid: M1b for Race, M3 for Gender

**What this does:** A combined method that routes race and gender estimation to different underlying methods. Uses M1b (learned weights by industry) for the race dimension, and the existing M3 IPF for the gender dimension. The 200-company results confirmed IPF is best for gender (MAE 10.67 vs M1's 12.60) and weighted blends are best for race.

**Implementation notes:**
- This is a routing function — it calls M1b internally for race/hispanic output, calls M3 internally for gender output, and combines them into one result dict
- Output format must be identical to all other methods: `{'race': {...}, 'hispanic': {...}, 'gender': {...}}`
- No new data sources or queries — pure composition of existing methods
- This is the method most likely to become the production default if it outperforms M1

---

## Part 2: Fresh Holdout Set of 200 Companies

Create a new script: `scripts/analysis/demographics_comparison/select_holdout_200.py`

**Purpose:** Select a second set of 200 companies from the EEO-1 data that were NOT in the original 200. This set is used only for final validation — it should not be looked at until all method improvements are finalized.

**Requirements:**
- Load `selected_200.json` to get the list of company codes already used
- Exclude all companies in that list from the candidate pool
- Apply identical base filters as `select_200.py` (TOTAL >= 50, valid ZIP, LODES data available, ACS match, etc.)
- Apply identical stratified sampling logic across the same 5 dimensions (industry, size, region, minority share, urbanicity)
- Same coverage targets: all dimension buckets must have >= 3 companies
- Output to `selected_holdout_200.json` in the same format as `selected_200.json`
- Print a composition summary identical to the one printed by `select_200.py` so we can verify coverage

**Important:** This script should be written but we will NOT run the comparison against it yet. It is created now and set aside.

---

## Part 3: Updated Comparison Runner

Update `run_comparison_200.py` (or create `run_comparison_200_v2.py` — prefer the latter to preserve the original) to:

1. Include M1b, M2b, M3b, M4b, M5b, M7 alongside the original M1–M5 in every comparison table
2. Accept a command-line argument `--companies` that accepts either `selected_200.json` or `selected_holdout_200.json` so the same runner works on both sets
3. Output to a filename that reflects which company set was used (e.g., `comparison_original_200_v2_detailed.csv` vs `comparison_holdout_200_detailed.csv`)
4. All existing output formats (summary table, dimensional breakdown by industry/size/region/minority/urbanicity) remain identical — just add the new methods as additional columns

---

## Checkpoints

Before starting, confirm:
- [ ] You can find and read `methodologies.py` and understand the input/output signature of existing methods
- [ ] You can find `comparison_200_detailed.csv` with per-company results for the original 200
- [ ] You can read `selected_200.json` to get the list of already-used company codes
- [ ] The `cur_lodes_geo_metrics` table has a `pct_minority` field you can query

After each method variant, verify:
- [ ] The new method produces valid probability distributions (all values 0–1, sum to 1.0 within each dimension)
- [ ] The new method has a fallback for missing data identical in behavior to its parent method's fallback
- [ ] No existing method code was modified

After all methods are added:
- [ ] Run `run_comparison_200_v2.py --companies selected_200.json` and confirm all 11 methods appear in output
- [ ] Confirm M6 does NOT appear in the new runner
- [ ] Confirm `selected_holdout_200.json` was created but the holdout comparison was NOT run

---

## What Success Looks Like

The final output of this session should be:
1. Six new method functions in `methodologies.py` (M1b, M2b, M3b, M4b, M5b, M7)
2. `run_comparison_200_v2.py` that runs all 11 methods (M1–M5 + M1b, M2b, M3b, M4b, M5b, M7)
3. `selected_holdout_200.json` created and ready but not yet used
4. A comparison results CSV for the original 200 companies showing all 11 methods side by side

We will interpret those results in a separate session and decide which method, if any, becomes the new production default.
