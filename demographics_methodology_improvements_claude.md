# Demographics Methodology: First Pass Review & Improvement Plan
**Date:** 2026-03-08  
**Status:** In progress — 200-company validation run underway  
**Context:** First pass tested 6 estimation methods against 10 EEO-1 ground truth companies

---

## What the First Pass Did

Tested 6 methods for estimating workforce demographics against real EEO-1 government filings for 10 companies. Goal: find which guessing method is least wrong.

### The 6 Methods (Plain English)

| Method | How It Works |
|--------|-------------|
| **M1 Baseline 60/40** | Blend industry average (60%) + county average (40%). Simple arithmetic. |
| **M2 Three-Layer** | Same but adds census tract (neighborhood). 50/30/20 weights. |
| **M3 IPF** | Mathematical technique: start with rough guess, keep adjusting until all constraints satisfied simultaneously. Like solving a Sudoku. |
| **M4 Occ-Weighted** | Look at what specific jobs the company has, blend those occupational averages. |
| **M5 Variable-Weight** | Like M1/M2 but weights shift based on context. |
| **M6 IPF + Occ** | Combines M3 and M4. |

### Results

| Method | Avg Race MAE | Avg Hellinger | Race Wins | Gender Wins |
|--------|-------------|---------------|-----------|-------------|
| **M1 Baseline** | **6.8** | **0.206** | 3 | 0 |
| M4 Occ-Weighted | 7.0 | 0.213 | 3 | 2 |
| M5 Variable-Weight | 7.2 | 0.208 | 1 | 0 |
| M2 Three-Layer | 7.2 | 0.216 | 3 | 2 |
| M3 IPF | 11.1 | 0.337 | 0 | 6 |
| M6 IPF+Occ | 11.1 | 0.337 | 0 | 0 |

*MAE = Mean Absolute Error. How many percentage points off on average. Lower is better.*

---

## Key Findings

**1. Simple wins for race.** The simplest method (M1) beat all the fancy math for racial composition. This signals the problem is the underlying data, not the model design.

**2. IPF wins for gender, fails for race.** IPF's math works well on simple 2-way splits (male/female) but amplifies bias on race — because if the data already slightly overestimates White workers, IPF makes that error larger.

**3. Every method has the same systematic bias.** All 6 methods:
- Overestimate White workers by ~10 percentage points
- Underestimate Black workers by ~10 percentage points
- This is a **data source problem**, not a model problem. ACS and LODES measure where people *live*, not where they *work*. Black workers who commute into whiter areas are undercounted.

**4. Outlier employers break everything.** OSI Industries (60% Black workforce) had a best-case error of 13.7pp — nearly double the average. No blending of regional/national averages can predict an employer that's a genuine outlier from its industry.

**5. NHOPI gap exposed.** Alexander & Baldwin (Hawaii) showed the Census data lumps Native Hawaiian/Pacific Islander workers in with Asian — causing a ~33pp underestimation error for NHOPI workers.

---

## Improvement Priorities

### Priority 1 — Fix the Systematic Bias (Most Important)

The 10pp White overestimation / Black underestimation affects every method equally. Fixing the model design won't help until this is addressed.

**Approach: Calibration offsets by industry**
- Use the EEO-1 ground truth data to calculate how wrong each industry estimate typically is
- Example: "In meat processing, Black workers are consistently underestimated by 11pp — apply a +11pp correction"
- This is called a **calibration offset** — common in survey science
- Apply before feeding data into any of the 6 methods

### Priority 2 — Build the Hybrid Method

Results clearly show: **M1 for race, M3 for gender**. These answer different sub-questions and can be combined:
- Race prediction → use simple weighted averages (M1 logic)
- Gender prediction → use IPF's multiplicative correction (M3 logic)
- Run both independently, combine outputs

### Priority 3 — Handle Outlier Employers Explicitly

No formula will predict OSI Industries-type employers from regional averages alone. The fix is **detection + honest flagging**, not a better formula:

- If EEO-1 data exists for this employer → use the real data (have 16,798 federal contractors)
- If BDS-HC shows high industry variance → widen confidence intervals, show uncertainty in UI
- If OSHA/NLRB records contain workforce composition clues → use those signals
- Surface this uncertainty to the user rather than presenting a false precision

### Priority 4 — Expand Validation Set

10 companies is too small to draw confident conclusions. Current gaps in the validation set:
- No large retail (Walmart-type: female-dominated, very racially diverse)
- No healthcare systems (most common organizing target type)
- No tech companies (different failure modes — overestimates Asian workers)
- Limited geographic variety (concentrated in Southeast/Midwest)

**Target:** 50–100 companies stratified across industries before declaring a method winner.  
*(200-company run in progress — will inform next iteration)*

### Priority 5 — Fix the NHOPI Data Gap

The Census data currently used (`IPUMS`) doesn't separate Native Hawaiian/Pacific Islander from Asian. Fix:
- Switch to IPUMS variables `RACASIAN` vs `RACPACIS` for the separation
- Targeted data pipeline change — doesn't require rebuilding the whole estimation flow
- Matters most for Hawaii, Guam, parts of California, Pacific Islander-heavy workforces

---

## Key Insight

> The problem is not the math. The raw data sources (ACS, LODES) have structural bias baked in. Fixing that bias through calibration will do more good than switching to fancier formulas.

---

## Suggested Implementation Order

1. **Calculate calibration offsets by industry** using EEO-1 ground truth → improves all methods immediately, no rebuild required
2. **Wire hybrid M1+M3** as new default in `api/routers/profile.py`
3. **Add confidence/uncertainty flags** to outputs — especially high-variance industries
4. **Expand validation to 50–100 companies** before finalizing method choice
5. **Fix NHOPI data gap** in IPUMS variable selection

---

## Open Questions for Next Session

- What does the 200-company run show about systematic bias patterns by industry?
- Does the White overestimation vary by region (South vs. Northeast vs. West)?
- Which industries have the highest employer-to-employer variance (where IPF uncertainty flags matter most)?
- Does adding BDS-HC as a calibration constraint meaningfully reduce MAE vs. M1 baseline?

---

*To be updated after 200-company validation results and multi-AI review.*
