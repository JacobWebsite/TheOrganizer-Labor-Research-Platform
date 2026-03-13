# Demographics Methodology: Synthesis & Action Roadmap
**Date:** 2026-03-08  
**Sources:** Claude, GPT, Gemini review of first-pass results  
**Status:** Awaiting 200-company validation results — this document defines what to look for and what to build next

---

## How to Read This Document

Three AI systems reviewed the same first-pass results and were largely in agreement on the core problems. Where they differed, it was mostly *depth and sequence*, not disagreement. This synthesis resolves those differences into a single prioritized action plan.

The 200-company run will answer specific questions called out at the end of each section. Don't start building anything until those answers come back.

---

## What All Three AIs Agreed On (High Confidence)

These findings were consistent across all three reviews. They are almost certainly correct.

### 1. The Bias Problem Is the Most Urgent Issue

Every method overestimates White workers by ~10 percentage points and underestimates Black workers by ~10 percentage points. This is not a flaw in any one method — it shows up in all six. That means it's coming from the raw data sources (ACS and LODES), not from the math applied to them.

**Why this happens:** ACS and LODES measure where people *live*, not where they *work*. Think of a city like Chicago: the workforce at a South Side warehouse might be 70% Black, but if you measure the surrounding county's population (which includes wealthy suburbs), you'd estimate a much whiter workforce. The data is measuring the wrong thing.

**The fix all three agreed on:** Calculate a "correction factor" by industry using your EEO-1 ground truth. For example: "In meat processing, Black workers are consistently undercounted by 11 percentage points — add 11pp back." This is called a **calibration offset**. It's a well-established technique in survey science. Apply it before running any estimation method.

**What the 200-company run will tell you:** Whether the bias is consistent within industries, or whether it varies a lot employer-to-employer. If it's consistent (e.g., "meat processing always underestimates Black by 10-12pp"), calibration offsets will work well. If it's wildly variable, you'll need something more sophisticated.

---

### 2. The Hybrid Method Is the Right Architecture

IPF wins for gender. Simple weighted averages win for race. These aren't competing — they're solving different sub-problems.

**The hybrid approach (all three agreed):**
- Use M1 (simple 60/40 blend) for race estimation
- Use M3 (IPF) for gender estimation
- Run both independently, combine the outputs

This is low-effort to implement and should produce better results than any single method. It becomes the new default once built.

---

### 3. The Validation Set Is Too Small

Ten companies cannot support reliable conclusions. All three AIs flagged this independently.

**Target validation set (synthesized from GPT + Gemini recommendations):**

| Dimension | What to Include |
|-----------|----------------|
| Industry | At least 15–20 different NAICS sectors |
| Workforce size | Small (<100), Medium (100–1k), Large (1k–10k), Very Large (10k+) |
| Region | Northeast, South, Midwest, West |
| Minority share | Low (<20%), Medium (20–40%), High (>40%) |
| Urbanicity | Urban, Suburban, Rural |

The 200-company run is a strong start. Target 300–500 before making final method decisions.

**Current gaps in the 10-company set (not yet covered):**
- Large retail (Walmart-type: female-dominated, very racially diverse)
- Healthcare systems (most common organizing target type)
- Tech companies (different failure mode: overestimates Asian workers)
- More geographic variety — currently Southeast/Midwest-heavy

---

### 4. Outlier Employers Cannot Be Estimated — They Need to Be Detected

OSI Industries (60% Black workforce in meat processing) had a best-case error of 13.7pp — nearly double the average. No blending of regional or national averages will ever predict an employer that's a genuine outlier from its sector.

The right response is **not a better formula**. It's:
1. Detect when you're in outlier territory (high industry variance = unreliable estimate)
2. Fall back to real data when available (16,798 employers have EEO-1 ground truth)
3. Show honest uncertainty in the UI instead of false precision

**How to detect outlier territory:** BDS-HC data shows the variance within each industry × size × region bucket. High variance = your estimate could be way off. Surface this as a confidence rating to the user.

---

## Where the AIs Differed (Resolved Below)

### On: How Sophisticated the Model Should Get

- **Claude:** Fix the data bias first; simpler methods will work better once the inputs are corrected
- **GPT:** Move toward learned/regression weights that optimize themselves from data
- **Gemini:** Build a meta-model (ensemble) that automatically picks the best method per employer

**Synthesis:** These aren't mutually exclusive — they're a sequence. The correct order is:
1. Fix bias (calibration offsets) — do this first, improves everything immediately
2. Learned weights (GPT's regression approach) — do this once you have 200+ validation companies
3. Meta-model routing (Gemini's ensemble) — do this once you have 500+ and a stable dataset

Don't jump to step 3 before completing step 1. A meta-model built on biased data just automates the bias.

---

### On: Geography — How Local Is the Right Local?

- **Claude:** County-level is the right geography; problem is the data, not the geographic unit
- **GPT:** Use LODES Origin-Destination commuting matrices instead of static county boundaries
- **Gemini:** Test multiple geographic rings (tract → zip → county → MSA → state) and find which predicts best by firm type

**Synthesis:** Gemini's hierarchical testing is the right diagnostic. The 200-company run should measure error at different geographic granularities to find where county-level breaks down. GPT's commuter-shed model is the theoretically correct solution — but it's complex to build and should wait until you know *which employer types* actually need it (not all will).

**What the 200-company run will tell you:** Whether rural employers, urban employers, and suburban employers have systematically different error patterns. If yes, different geographic rings are needed by location type.

---

### On: Machine Learning

- **GPT:** Move to gradient boosting or random forest once EEO-1 training data is large enough
- **Gemini:** Train a lightweight meta-model (XGBoost) to route between methods
- **Claude:** (Did not recommend ML yet — focus on data quality first)

**Synthesis:** ML is the right long-term direction, but requires:
- At least 500 matched EEO-1 companies as training data
- Stable, bias-corrected input features
- A clear baseline to beat

The 200-company run is step one toward having enough training data. Don't start ML architecture until you have ~500 companies and have fixed the systematic bias. Otherwise you're training a model to learn the bias.

---

## Prioritized Action Plan

This is the sequence of work, ordered by impact and dependency.

### Immediate (Do Before or During 200-Company Analysis)

**Action 1: Add error breakdown dimensions to the 200-company output**

The 200-company run should not just report average MAE. It should report:
- MAE by NAICS industry group
- MAE by firm size bucket
- MAE by region (Northeast / South / Midwest / West)
- MAE by minority share (low / medium / high)
- Bias direction per race group (not just magnitude)
- Employer-to-employer variance within each industry bucket

This turns the run from "how accurate are we overall" into "where exactly do we fail and why."

---

### After 200-Company Results Come Back

**Action 2: Calculate industry-specific calibration offsets**

For each industry in the validation set:
- Calculate average error per race group (e.g., "healthcare systematically underestimates Black by X pp")
- Store these offsets in a lookup table in the database
- Apply them automatically before any estimation method runs

This is the highest-leverage single fix. It improves all 6 methods simultaneously without rebuilding anything.

**Decision gate:** If error within an industry varies by more than ±8pp employer-to-employer, offsets won't be reliable for that industry. Flag those industries differently (show wider uncertainty bounds in the UI instead).

---

**Action 3: Implement the hybrid M1 + M3 method**

- Race → M1 (60/40 weighted blend)
- Gender → M3 (IPF)
- Wire as new default in `api/routers/profile.py`

This is mechanical once you've confirmed the hybrid outperforms both single methods in the 200-company data.

---

**Action 4: Add confidence flags to all demographic outputs**

Every demographic estimate in the UI should show:
- **Data source:** EEO-1 verified / BDS-HC calibrated / Blended estimate
- **Confidence level:** Based on industry variance from BDS-HC
- **Flagged as outlier:** If employer's characteristics suggest it diverges from industry norms

This prevents users from treating estimates as facts. It also protects the platform's credibility — wrong data is more damaging than missing data.

---

### Medium Term (After Bias Is Fixed)

**Action 5: Learned weights via regression**

Replace the fixed 60/40 blend with weights estimated from the EEO-1 ground truth data:

```
race_share = w1 × ACS_county + w2 × LODES_workplace + w3 × industry_baseline + w4 × occupation_weights
```

Where w1–w4 are learned by industry rather than fixed. This is GPT's recommendation and it's sound — but only after calibration offsets are applied, otherwise the regression learns biased weights.

Technique: Ridge regression with cross-validation. Produces industry-specific weight sets.

---

**Action 6: Commuter-shed modeling for high-error employer types**

If the 200-company run shows urban employers or specific industries have much higher error than average, implement LODES Origin-Destination (OD) commuting matrices for those types.

**What this does in plain English:** Instead of asking "who lives in this county?", ask "who actually commutes *into* this employer's census tract for work?" LODES has exactly this data — it tracks home-to-work flows at the census tract level. It's more accurate but more complex to build.

**Only build this if** the 200-company data shows county-level geography is the error source for specific firm types — don't build it speculatively.

---

**Action 7: Fix the NHOPI data gap**

The Census data currently used (IPUMS) lumps Native Hawaiian/Pacific Islander in with Asian. Fix:
- Switch IPUMS queries to use `RACASIAN` vs `RACPACIS` variable separation
- Targeted pipeline change — doesn't require rebuilding the estimation flow
- Priority: Hawaii, Guam, Pacific-facing California employers

All three AIs agreed this is a known gap. It's a contained fix with clear scope.

---

**Action 8: Intelligent handling of suppressed BDS-HC values**

Currently, suppressed values in BDS-HC (marked 'D' or 'S') are zeroed out. This is wrong — they're not zero, they're just hidden for privacy. Fix:
- Replace zero-fill with imputation using historical averages for that NAICS/size/state bucket
- Use surrounding geographic marginals as fallback when no historical data exists

This improves the accuracy of the BDS-HC calibration constraint.

---

### Long Term (500+ Companies, Stable Baseline)

**Action 9: Meta-model routing (Gemini's ensemble approach)**

Train a lightweight classifier that looks at an employer's profile (industry, size, region, minority share, urbanicity) and automatically selects the best estimation method for that specific employer type.

This is the "smart system" end state: rather than one method for all employers, the system routes each employer to whichever method is known to work best for its profile.

**Requires:** 500+ validated companies; stable bias-corrected inputs; proven hybrid method baseline to beat.

---

**Action 10: Supervised ML (GPT's gradient boosting approach)**

Once enough EEO-1 training data is accumulated, reframe the whole problem as a supervised learning task — the existing estimation methods become *features* fed into a model, rather than standalone methods.

This is the theoretical ceiling on accuracy. It's also the most complex to build and validate. Treat it as a research direction, not near-term work.

---

## Open Questions — Answered by the 200-Company Run

| Question | Why It Matters | What a Good Answer Looks Like |
|----------|---------------|-------------------------------|
| Does White overestimation vary by industry? | Determines if calibration offsets work or if we need something more complex | Consistent within-industry bias → offsets will work |
| Does it vary by region? | Determines if we need regional calibration vs. national | If South differs from Northeast, add region as a calibration dimension |
| Which industries have highest employer-to-employer variance? | Determines where confidence flags are most critical | Industries with >15pp spread need wide uncertainty bounds |
| Does error differ by firm size? | Large vs. small firms may need different methods | If small firms (<100) are systematically worse, flag differently |
| Do urban employers have higher error than rural? | Determines if commuter-shed modeling is worth building | Urban outlier pattern → prioritize OD modeling |
| Does M4 (occ-weighted) beat M1 in specific industries? | Determines if occupational matrices are worth expanding | If healthcare or hospitality improves, expand occupational data |

---

## Key Principles (Shared Across All Three AIs)

These are the "laws" that should govern every design decision going forward:

1. **Wrong data is worse than missing data.** A bad estimate presented as fact destroys user trust permanently. Show uncertainty; don't hide it.

2. **Fix the inputs before improving the math.** The systematic 10pp bias is a data problem. No amount of better algorithms fixes biased training data.

3. **Simple methods beat complex methods when the data is dirty.** M1 won the first round for exactly this reason. Add complexity only when you have clean enough data to benefit from it.

4. **Real data beats any estimate.** For the 16,798 EEO-1 employers, always use the actual data. For federal contractors identifiable via SAM.gov, flag and prioritize EEO-1 matching.

5. **Validate before scaling.** Don't deploy to production until the hybrid method + calibration offsets are tested against 200+ companies and shown to outperform the M1 baseline.

---

*Update this document after 200-company results are in.*
