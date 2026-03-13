# V9 Proposal: 2-Model Dimension-Specific Architecture

**Date:** 2026-03-11
**Based on:** `analyze_per_dimension_ceiling.py` results on permanent holdout
**Theoretical ceiling:** 28.9% Race MAE reduction (3.357 -> 2.387 pp)

---

## The Problem with the Current Architecture

The V6-V8 gate system picks **1 expert for everything**: race, Hispanic, gender.
But analysis shows that for **87% of companies**, the best expert for race is a
different expert than the best for Hispanic or gender.

Each race category has a different optimal expert:

| Category | Best Expert | Why It Makes Sense |
|----------|-----------|-------------------|
| White %  | D (V5 census blend) | White % is well-predicted by county census data |
| Black %  | G (occupation-chain) | Black workforce share diverges most from census -- occupational composition is a better signal |
| Asian %  | D (V5 census blend) | Asian % follows census patterns in professional/technical sectors |
| Hispanic % | G (occupation-chain) | Hispanic workforce clusters by occupation type, not just geography |
| Two+ %   | F (occ-weighted) | Multiracial % is noisy; occupation weighting smooths it |
| Gender   | F (occ-weighted) | Gender segregation is fundamentally occupational, not geographic |

**The current gate forces Expert G to compete against D/E for overall race MAE,
where D wins because White and Asian are larger categories. But G is the best
expert for the two categories where errors are largest and most consequential
(Black, Hispanic).**

Expert G is routed to only 14 companies (1.4%) because the gate optimizes for
overall race MAE, where D/E win due to White/Asian dominance. Meanwhile, G's
superior Black/Hispanic estimates are thrown away for 98.6% of companies.

---

## Proposed Architecture: 2 Models

### Model 1: "Geographic-Census" (base estimates)

**Source:** Expert D methodology (V5 M3c census blend)
**Best at:** White, Asian, AIAN -- categories that track census demographics
**When it wins:** Low-diversity counties, Midwest/Northeast, Finance,
Manufacturing

Expert D uses county-level census data weighted by industry. This works well
for categories where the workforce roughly mirrors local demographics (White,
Asian) or where the category is small enough that census is the only signal
(AIAN).

### Model 2: "Occupation-Diverse" (diversity correction)

**Source:** Expert G methodology (occupation-chain demographic estimation)
**Best at:** Black, Hispanic -- categories where workforce diverges from census
**When it wins:** Healthcare, Admin/Staffing, South/West, high-diversity counties

Expert G uses occupational composition to estimate demographics. Healthcare
hires nurses, aides, orderlies -- these occupations have very different
demographics than the surrounding county. G captures this because it reasons
from "what jobs does this company have?" rather than "what does the county
look like?"

### How They Combine

For each company:
```
White %    = Model 1 (D) estimate
Asian %    = Model 1 (D) estimate
AIAN %     = Model 1 (D) estimate
Black %    = Model 2 (G) estimate
Hispanic % = Model 2 (G) estimate
Two+ %     = Model 1 with F-style occupation weighting
Gender     = F-style occupation weighting (gender is occupational, not geographic)
```

**No gate model needed.** No routing. No probability blending. Just run both
models and pick per-dimension.

### Segment-Specific Overrides

The per-segment analysis shows that the optimal expert varies by segment.
A lookup table trained from data:

| Segment | White Best | Black Best | Hispanic Best | Gender Best |
|---------|-----------|-----------|--------------|------------|
| Healthcare, South, medium-diversity | V6 | G | A | G |
| Finance, Midwest, low-diversity | E | G | A | A |
| Professional/Technical, South, medium | E | G | G | A |
| Construction, South, medium | F | G | A | A |

These overrides can be computed deterministically from training data: for each
segment x category, which expert has the lowest mean absolute error? No ML model
needed -- just a lookup table.

---

## Why Averaging Doesn't Work

The analysis tested blending (averaging top-2, top-3, all experts):

| Approach | Race MAE |
|----------|---------|
| Single best expert | 3.357 pp |
| Average top 2 | 3.457 pp (WORSE) |
| Average top 3 | 3.541 pp (WORSE) |
| Average ALL | 4.994 pp (much WORSE) |
| Per-category oracle | 2.387 pp (BEST) |

Averaging introduces noise from the weaker expert. If Expert D estimates White
at 72% (correct) and Expert G estimates White at 60% (wrong), averaging gives
66% -- worse than either expert alone for White.

**The key insight: you don't want to BLEND estimates. You want to SELECT the
best estimate per category.** This is fundamentally different from ensemble
averaging.

---

## What This Eliminates

The 2-model architecture removes:
- Gate model training (GradientBoostingClassifier, 3-5 hours)
- Gate cross-validation accuracy as a metric
- Soft routing overrides (Expert E boost, Expert G floor, Expert E cap)
- Expert probability blending
- 5 of 7 expert implementations (keep D, G, possibly F for gender)

What remains:
- Expert D estimation (geographic-census)
- Expert G estimation (occupation-chain)
- Expert F estimation (for gender/Two+)
- Per-segment lookup table (which expert for which category in which segment)
- Calibration (still needed, now per-model per-dimension)
- Confidence tiers (still needed)

---

## Risks

1. **Oracle vs Reality gap:** The 28.9% improvement is with oracle selection
   (knowing ground truth). A real system uses segment-based lookup tables,
   which won't be as good. Realistic improvement: 10-20%.

2. **Expert G quality concerns:** G is globally best for Black/Hispanic but
   the gate only routed it to 14 companies. This might mean G has high variance
   -- great average but some catastrophic failures. Need to check G's error
   distribution, not just its mean.

3. **Normalization:** If White comes from Model 1 and Black from Model 2,
   the percentages may not sum to 100%. Need a normalization step.

4. **Small categories:** AIAN, NHOPI, Two+ are small enough that the "best
   expert" choice may be noise. Could just use Model 1 for all three.

5. **Calibration interaction:** Current calibration corrections are per-expert
   and trained on full predictions. With per-category selection, calibration
   needs to be retrained on the blended output.

---

## Implementation Steps

### Phase A: Validate Expert G quality
- Run Expert G on ALL holdout companies (not just the 14 the gate routes to)
- Check its error distribution for Black and Hispanic
- Flag: does it have a fat tail of catastrophic errors?
- If yes: we may need a "use G unless G looks unreasonable" rule

### Phase B: Build per-segment lookup table
- From training data: for each (naics_group x region x county_tier) segment
  and each category, record which expert has lowest MAE
- Minimum segment size: 30 companies
- Fallback hierarchy: segment -> naics_group -> global

### Phase C: Implement 2-model estimator
- Run Expert D and Expert G (and F for gender) on every company
- Select per-category based on lookup table
- Normalize to 100% per dimension
- Apply calibration (retrained for this new approach)

### Phase D: Evaluate
- Same acceptance criteria as V8
- Compare to V8 and V6 on permanent holdout
- Especially watch: Healthcare South P>20pp and P>30pp

---

## Connection to V8 Analysis

V8 proved that:
- The gate is only 28.6% accurate (worse than V7's 29.2%)
- Expert G is the best for Black despite being used for 1.4% of companies
- ABS minority ownership is the strongest gate feature but can't fix estimation
- Regional calibration correctly identifies South vs Midwest differences but
  only 18% of companies use the fine-grained corrections

All of these problems dissolve in a 2-model architecture:
- No gate accuracy to worry about
- Expert G gets used for Black on every company, not 1.4%
- ABS data could become an estimation feature (not just a routing signal)
- Regional calibration becomes per-model per-category (simpler, more effective)

---

*Generated: 2026-03-11*
*V8 Race MAE: 4.526 (post-calibration, permanent holdout)*
*Theoretical 2-model ceiling: 2.387 (pre-calibration, oracle)*
*Realistic target: 3.5-4.0 (post-calibration, segment-lookup)*
