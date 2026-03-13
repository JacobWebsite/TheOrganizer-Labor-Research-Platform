# V8 Demographics Model -- Full Summary & Analysis

**Date:** 2026-03-11
**Permanent holdout result:** 4/7 criteria passed (regression from V6's 7/7)
**Official Race MAE:** 4.526pp (target <4.50, missed by 0.026pp)

---

## Executive Summary

V8 was the most ambitious model revision to date, adding three new external data
sources (ABS minority ownership density, EPA transit scores, 4-digit NAICS),
regional/county-tier calibration stratification, and four routing adjustments
(dampening tuning, Expert E ceiling, Expert G soft boost, YELLOW confidence
floor). Despite this, V8 passes only 4/7 acceptance criteria on the permanent
holdout -- the same count as V7, and a regression from V6's clean 7/7 sweep.

The core problem identified in V7 remains: Healthcare and Admin/Staffing in the
South and West produce errors that are systematic, not random. V8's tools
correctly identify the pattern -- ABS minority ownership became the single most
important gate feature -- but the gate and calibration system cannot translate
that signal into proportionally better estimates. The model knows *which*
companies are hard but still can't estimate *what* their demographics are.

---

## Cross-Version Comparison (Permanent Holdout)

| Criterion       | V6 Result | V7 Result | V8 Result | V8 Target | V8 Status |
|-----------------|-----------|-----------|-----------|-----------|-----------|
| Race MAE        | 4.203 pp  | 4.62 pp   | 4.526 pp  | < 4.50    | FAIL (-0.026) |
| P>20pp          | --        | --        | 16.1%     | < 16%     | FAIL (-0.1%) |
| P>30pp          | --        | --        | 7.9%      | < 6%      | FAIL      |
| Abs Bias        | 1.000     | --        | 0.536     | < 1.10    | PASS      |
| Hispanic MAE    | 7.752 pp  | --        | 7.111 pp  | < 8.00    | PASS      |
| Gender MAE      | 11.979 pp | --        | 11.779 pp | < 12.00   | PASS      |
| Red flag rate   | 0.87%     | --        | 2.2%      | < 15%     | PASS      |

V8 improved Race MAE from V7 (4.526 vs 4.62) but couldn't recover to V6 levels
(4.203). The model is doing better on average (bias down to 0.536 from 1.000)
but the tail errors remain stubborn.

---

## Phase 0: Free Tuning -- What Each Change Did

### 0A: Dampening (kept at 0.80)

The dampening rescale mechanism was implemented (`--dampening` CLI flag, rescale
factor applied at calibration time), but the default remained 0.80. The training
script also still uses `DAMPENING = 0.80`. This means V8's calibration
corrections are dampened to 80% of measured bias -- the same as V7.

**Assessment:** Neutral. The infrastructure for testing 0.85/0.90 exists but
either wasn't tested or didn't help. Given that the regional calibration cells
have small N in some segments (and county_tier:high is entirely empty), keeping
conservative dampening was probably correct. Increasing dampening on already-
noisy segment corrections could amplify errors.

### 0B: Expert E Ceiling for Non-Finance (implemented, minimal impact)

**What it does:** Caps Expert E's gate probability at 0.30 for companies outside
Finance/Insurance (52) and Utilities (22). Excess probability is redistributed
to other experts proportionally.

**V7:** Expert E routed to 272 companies
**V8:** Expert E routes to 278 companies (permanent holdout)

**Assessment: Failed.** The cap barely changed routing because Expert E's gate
probability for non-Finance companies was rarely above 0.30 to begin with. The
gate assigns E high probability for Finance companies (where the floor boosts it
to 0.70) and moderate probability elsewhere. The 0.30 cap doesn't bite. Expert E
continues to be the most-routed expert by a wide margin, handling 28% of all
companies.

The real issue: Expert E isn't just Finance-specific -- it's a generally
competitive estimator. The gate routes to it because it genuinely performs well
for many company types, not because of a routing bug.

### 0C: YELLOW Floor for High-Geographic Sectors (implemented, working as designed)

**What it does:** Forces any company in NAICS 72 (Accommodation/Food), 56
(Admin/Staffing), or 23 (Construction) to YELLOW confidence minimum. These
sectors have structural address-workforce mismatches -- the company HQ ZIP code
doesn't represent where workers actually are.

**Result:** GREEN tier dropped from ~32% to ~30% on permanent holdout. 68% of
companies are now YELLOW. This correctly communicates uncertainty for sectors
where the model's geographic inputs are structurally unreliable.

**Assessment: Success (as a communication fix).** This doesn't change any
estimates -- it changes how we report confidence. For a staffing agency where 20%
of companies have >30pp error, labeling the estimate as "GREEN = high
confidence" would be dishonest. YELLOW is the right signal. No impact on MAE
or P>20pp metrics, by design.

### 0D: Expert G Soft Boost for Healthcare (implemented, minimal impact)

**What it does:** Sets a floor of 0.20 probability for Expert G (occupation-
chain) on all Healthcare companies (NAICS 62). Expert G had the smallest raw
White bias (-0.9pp vs -4.7 to -20.7pp for other experts), meaning its pre-
calibration estimates were closest to reality for diverse Healthcare workforces.

**V7:** Expert G routed to 4 companies
**V8:** Expert G routes to 14 companies

**Assessment: Marginal improvement.** 14 is better than 4, but still only 1.4%
of the holdout. The 0.20 floor isn't enough to make G the winning expert because
other experts (A, B, D, E) all have higher base probabilities. The gate
fundamentally doesn't trust Expert G -- its 28.6% cross-validation accuracy is
achieved largely without G. The soft boost means G gets 20% weight in the
probability blend for Healthcare, but the top expert still wins the argmax.

Healthcare Race MAE on permanent holdout: 5.469pp. This is an improvement over
V7's test holdout (6.086), but the holdouts are different samples so the
comparison is approximate. Healthcare remains the single hardest sector after
Finance becomes the easiest (2.861pp).

---

## Phase 1: New Data Sources -- Impact Assessment

### ABS Minority Ownership Density (Census Annual Business Survey)

**What it is:** For each county x 2-digit NAICS combination, the percentage of
businesses owned by racial/ethnic minorities. Computed from the Census Annual
Business Survey's county-level tables. Not individual company data (that's
confidential) -- it's an area-level signal.

**Research basis:** Stoll, Raphael & Holzer (2001) found +21pp Black workforce
share in Black-owned vs white-owned firms in the same industry/county. Kerr &
Kerr (2021) showed co-ethnic hiring effects are strongest where local ethnic
labor pools are largest.

**Implementation:** `build_abs_owner_density.py` processed ABS CSV files into
`abs_owner_density.json` keyed by FIPS5_NAICS2. Loaded in `cached_loaders_v6.py`
via `get_abs_owner_density()`. Added as `abs_minority_owner_share` gate feature
with -1.0 sentinel for missing values.

**Gate importance: 0.2278 -- HIGHEST of all 63 features.**

This is remarkable. ABS minority ownership density is more important to the gate
than every other feature: more than QCEW employment concentration (0.1338), more
than ACS-LODES divergence (0.1144), more than average pay (0.1125), more than
tract diversity entropy (0.0825). It tells the gate something fundamentally
different from any existing feature: not "what does the population look like
here?" but "what do the *businesses* look like here?"

**Assessment: Strong signal, limited translation.** The gate clearly learned to
use ABS data for routing decisions, but routing to a slightly better expert
doesn't fix the underlying estimation problem. All experts still use the same
geographic census data as their base -- they just weight it differently. ABS
tells the gate "this company is in a high-minority-business area, route
carefully" but doesn't give any expert better raw demographic estimates.

The value of ABS would be much higher if it were used directly in the estimation
pipeline (e.g., as a prior adjustment or an additional data source for experts)
rather than only as a gate routing signal.

### EPA Smart Location Database (Transit Scores)

**What it is:** Transit accessibility scores from the EPA's Smart Location
Database V3. For each Census block group: number of transit routes within 0.5mi,
transit frequency, jobs accessible by transit within 45min, walkability index.
Aggregated to ZIP code level via ZIP-tract crosswalk.

**Research basis:** Holzer & Ihlanfeldt (1996) found transit proximity explains
a major portion of Black employment rate differences between central-city and
suburban firms. Pew Research Center (2016) showed Black workers commute by
transit at 6x the white rate, Hispanic at 3x.

**Implementation:** `build_sld_transit_table.py` processed EPA SLD data into
`sld_transit_scores.json`. Added `get_transit_score()` to cached_loaders.
Transit score and transit tier encoded as gate features.

**Gate importance: < 0.001 -- essentially zero.**

Transit score didn't appear in the top 50 features. The gate learned nothing
useful from it.

**Assessment: Failed hypothesis.** The research literature on transit and
workforce demographics is real, but the signal doesn't help at the granularity
we need. Transit accessibility is strongly correlated with urbanity, which is
already captured by tract diversity entropy, LODES data, and ACS-LODES
divergence. Adding transit on top provides no new routing information. The gate
correctly identified it as redundant and ignored it.

The transit research is about *why* urban workplaces are more diverse -- it
explains the mechanism (workers can commute via transit) but doesn't add
predictive power beyond just knowing the workplace is urban. Population density
alone does the same job.

### 4-Digit NAICS Encoding

**What it is:** The first 4 digits of the NAICS code, encoded as a categorical
feature via a vocabulary of 50 codes built from training data.

**Research basis:** UC Berkeley Labor Center (2015) showed significant
demographic variation within NAICS 72 by restaurant type. EPI/Stuesse & Dollar
(2020) showed beef vs poultry processing have dramatically different Hispanic
workforce shares.

**Implementation:** `naics4_vocab.pkl` with 50 codes. Missing/rare codes mapped
to a default category. Added as `naics4_encoded` numeric feature in the gate.

**Gate importance: 0.0552 (meaningful, 6th most important feature)**

**Assessment: Moderate success.** 4-digit NAICS adds real information --
distinguishing nursing homes (6231) from hospitals (6221) within Healthcare,
or poultry processing (3116) from bakeries (3118) within Food Manufacturing.
It's not transformative but contributes meaningfully to routing decisions.

---

## Phase 2: Regional Calibration System

### Design

The core structural change: for Healthcare (62) and Admin/Staffing (56),
calibration corrections now have a 3-level fallback hierarchy:

1. **County minority tier** (most specific): low (<25%), medium (25-50%), high (>50%)
2. **Census region**: Northeast, Midwest, South, West
3. **Industry-level** (existing V7 behavior)
4. **Global fallback**

The idea: a hospital in rural Vermont and a hospital in Atlanta should not get
the same White/Black calibration correction. The South has systematically
different workforce demographics than the Midwest.

### Calibration Corrections Computed

The regional calibration system correctly identified huge variation. Example
for Expert A on Healthcare:

| Segment                              | White Correction | Black Correction | N     |
|--------------------------------------|-----------------|-----------------|-------|
| Healthcare (industry-level, V7-style) | (combined)      | (combined)      | ~1500 |
| Healthcare, Midwest                   | +2.22           | +2.11           | 357   |
| Healthcare, South                     | -9.02           | +12.53          | 419   |
| Healthcare, West                      | -5.22           | -0.52           | 334   |
| Healthcare, Northeast                 | -6.15           | +9.83           | 319   |
| Healthcare, county_tier:low           | +1.89           | +1.12           | 887   |
| Healthcare, county_tier:medium        | -14.97          | +14.82          | 524   |
| Healthcare, county_tier:high          | N/A             | N/A             | < 30  |

The corrections tell the right story: Healthcare in the South needs a massive
White-down/Black-up correction (-9.02/+12.53), while Midwest Healthcare barely
needs any (+2.22/+2.11). Medium-diversity counties need enormous corrections
(-14.97/+14.82). This is exactly the pattern V7's error distribution predicted.

### Usage in Practice

| Calibration Level | Companies | % of Holdout |
|-------------------|-----------|-------------|
| county_tier       | 170       | 17.1%       |
| region            | 8         | 0.8%        |
| industry          | 814       | 82.1%       |
| global            | 8         | 0.8%        |

**Only 18% of companies used the new fine-grained corrections.** The rest fell
through to industry-level (the V7 behavior).

### Why So Few Used Regional Calibration

1. **county_tier:high is empty for ALL experts.** There weren't enough companies
   in >50% minority counties to meet the N>=30 threshold. This is the exact
   segment where corrections would matter most -- diverse Southern/Western
   counties -- but the training data is too sparse.

2. **Only Healthcare and Admin/Staffing are eligible.** The 814 companies using
   industry-level calibration include all other sectors, which were excluded
   from regional calibration by design (REGIONAL_CALIBRATION_INDUSTRIES).

3. **Region corrections are rarely selected** because county_tier is checked
   first in the fallback hierarchy, and most Healthcare/Admin companies have
   county minority data available (they fall into county_tier:low or
   county_tier:medium, bypassing the region level).

**Assessment: Partially successful architecture, hampered by data sparsity.**
The calibration hierarchy is correct and the corrections are meaningful. But the
critical high-diversity-county segment is empty, and 82% of companies still use
the same V7-era industry-level corrections. The 17% that do use county-tier
corrections are mostly in low/medium-diversity counties where the corrections
are smaller and less impactful.

---

## Expert Routing Analysis (Permanent Holdout)

| Expert | Companies | % | Designed For | Assessment |
|--------|-----------|---|-------------|------------|
| E      | 278       | 28.0% | Finance/Utilities | Over-routed; cap ineffective |
| B      | 181       | 18.2% | High-geography sectors | Working as intended |
| D      | 174       | 17.5% | General (V5 legacy) | Reliable baseline |
| A      | 162       | 16.3% | ACS-weighted general | Working as intended |
| V6     | 112       | 11.3% | Composite fallback | Working as intended |
| F      | 79        | 8.0% | Manufacturing occ-weighted | Working as intended |
| G      | 14        | 1.4% | Occupation-chain | Barely used despite boost |

### Expert E: Still Dominant, Cap Failed

Expert E was designed for Finance/Insurance (52) and Utilities (22) -- about 150
companies in the holdout. It handles 278, nearly double its target domain. The
0.30 probability cap for non-Finance sectors was implemented but the gate rarely
assigns E > 0.30 outside Finance to begin with. The cap doesn't bite.

Expert E performs well broadly because its methodology (whatever it uses
internally) produces competitive estimates even outside Finance. The "over-
routing" may not actually be a problem -- E's industry-level calibration
corrections adjust for sector differences regardless.

### Expert G: The Missed Opportunity

Expert G has the best raw signed bias characteristics of any expert (smallest
White over-prediction), which should make it ideal for diverse-workforce
sectors like Healthcare. Despite the 0.20 probability floor for Healthcare, it
only routes to 14 companies because the argmax still favors other experts.

The soft boost approach is structurally limited: a 0.20 floor means G needs to
beat every other expert's probability AFTER they've been reduced to fit a 0.80
total. With 6 other experts sharing 0.80, the average competing probability is
~0.13 each -- meaning the gate's natural routing easily overwhelms G's boost.

To make Expert G meaningful would require either:
- A hard-route (force G for Healthcare), which risks regression if G is actually
  worse on many Healthcare subtypes
- A much higher floor (0.40+), which would distort routing for the majority of
  Healthcare companies where other experts are genuinely better

---

## Error Distribution (Permanent Holdout)

| Max Error Bucket | Companies | % | V7 Pattern |
|-----------------|-----------|---|------------|
| 0-1 pp | 3 | 0.3% | Same |
| 1-3 pp | 103 | 10.4% | Same |
| 3-5 pp | 120 | 12.1% | Slightly fewer |
| 5-10 pp | 301 | 30.3% | Same |
| 10-15 pp | 199 | 20.1% | Same |
| 15-20 pp | 106 | 10.7% | Slightly more |
| 20-30 pp | 82 | 8.3% | Same |
| >30 pp | 78 | 7.9% | Slightly more |

P>20pp = 16.1% (82 + 78 = 160 companies)
P>30pp = 7.9% (78 companies)

### The Tail Didn't Shrink

The >30pp catastrophic bucket contains 78 companies (7.9%), actually slightly
worse than V7's 7.1% on its test holdout (different samples, so not directly
comparable). The composition is the same:

- **Healthcare/Social: 17 companies** (22% of bucket) -- still the #1 problem
- **Other: 14** (18%) -- miscellaneous hard cases
- **Professional/Technical: 9** (12%)
- **Admin/Staffing: 7** (9%)
- **South: 32** (41%) -- still massively over-represented vs 35% baseline

The error direction is unchanged: White over-predicted (26 companies), Black
under-predicted (28 companies). The model systematically underestimates
diversity in the South and West for Healthcare and Staffing.

### Per-Industry Results

| Industry | V8 MAE (perm) | V7 MAE (test) | Direction |
|----------|---------------|---------------|-----------|
| Finance/Insurance (52) | 2.861 | -- | Best sector |
| Utilities (22) | 3.043 | -- | Strong |
| Healthcare/Social (62) | 5.469 | 6.086 | Improved* |
| Admin/Staffing (56) | 5.872 | 7.018 | Improved* |
| Construction (23) | 5.247 | -- | Moderate |

*Different holdout samples; approximate comparison only.

Healthcare and Admin/Staffing show apparent improvement but these are different
company samples (V8 permanent holdout vs V7 test holdout), so the comparison is
directional, not definitive.

---

## Gate Model Performance

| Metric | V7 | V8 |
|--------|-----|-----|
| CV Accuracy | 29.2% | 28.6% |
| Random Baseline | 14.3% | 14.3% |
| N Training | ~11,000 | 11,524 |
| N Features | ~50 | 63 |

The gate's cross-validation accuracy actually decreased slightly (28.6% vs
29.2%) despite having 13 more features. Adding features without adding
discriminative signal just adds noise.

### Feature Importance Rankings (V8 Gate)

| Rank | Feature | Importance | New in V8? |
|------|---------|-----------|------------|
| 1 | ABS minority owner share | 0.2278 | YES |
| 2 | QCEW location quotient | 0.1338 | No |
| 3 | ACS-LODES divergence | 0.1144 | No |
| 4 | QCEW average pay (log) | 0.1125 | No |
| 5 | Tract diversity entropy | 0.0825 | No |
| 6 | 4-digit NAICS | 0.0552 | YES |
| 7 | Region: West | 0.0220 | No |
| 8 | NAICS 2-digit: 52 | 0.0194 | No |
| 9 | Has PUMS data | 0.0175 | No |
| 10 | Industry: Healthcare | 0.0169 | No |
| -- | Transit score | < 0.001 | YES (failed) |

ABS minority ownership is the single most important feature in the gate by a
wide margin. The gate learned to use it aggressively. But better routing
doesn't fix what the experts can't estimate.

---

## What Worked

1. **ABS minority ownership density as a gate signal.** Highest feature
   importance by far. The gate now has a fundamentally new type of information
   about business composition vs population composition.

2. **Regional calibration architecture.** The fallback hierarchy (county_tier ->
   region -> industry -> global) is correct and the corrections are meaningful.
   Healthcare-South corrections are dramatically different from Healthcare-
   Midwest, which is exactly what V7 error analysis predicted.

3. **YELLOW confidence floor for high-geographic sectors.** Honest communication
   about structural limitations in Staffing/Construction/Accommodation.

4. **Abs Bias improvement.** Down from 1.000 (V6) to 0.536 (V8). The model's
   systematic directional errors are smaller.

5. **Hispanic and Gender MAE.** Both comfortably pass targets. Hispanic MAE
   improved from 7.752 (V6) to 7.111 (V8). Gender from 11.979 to 11.779.

## What Failed

1. **Transit scores provided zero signal.** The research hypothesis was
   plausible but the feature is redundant with existing urbanity proxies. The
   400MB download and ETL pipeline produced nothing.

2. **Expert E cap didn't reduce over-routing.** 278 companies vs 272 -- the cap
   threshold of 0.30 was too generous. The gate rarely exceeds 0.30 for E
   outside Finance anyway.

3. **Expert G remains unused.** 14 companies despite the 0.20 floor. The soft
   boost is too weak against 6 competing experts. The smallest raw bias doesn't
   mean the best accuracy -- other experts may have higher variance but better
   average performance.

4. **county_tier:high calibration is empty.** The exact segment that needs the
   most correction (high-diversity counties in Healthcare/Staffing) has
   insufficient training data for any expert. This is the single biggest
   structural gap in V8.

5. **P>30pp actually worsened.** 78 companies (7.9%) vs V7's 70 (7.1% on a
   different holdout). The catastrophic tail is the hardest problem and V8's
   tools didn't dent it.

6. **Gate accuracy decreased.** 28.6% vs 29.2%. More features without more
   signal = more noise.

---

## Root Cause Analysis

The fundamental problem V8 tried to solve -- Healthcare/Staffing companies in
diverse Southern/Western counties have workforces that don't match census
demographics -- is real and well-characterized. V8's approach was:

1. **Give the gate better information** (ABS, transit, NAICS4) to route better
2. **Give calibration finer segments** (region, county-tier) to correct better

Both approaches have the same limitation: **they still rely on the same 7
experts that use the same underlying census data.** Better routing to a slightly
less-wrong expert is marginal. Finer calibration segments help but the critical
"high diversity county" segment has no data.

The model's architecture means that every estimate starts from census data
(ACS tract demographics, LODES workplace demographics, county demographics).
For companies where census demographics systematically diverge from workforce
demographics -- Healthcare in the South, Staffing everywhere -- no amount of
routing or calibration fully compensates.

To actually close the gap would require either:
- **New data sources used in estimation** (not just routing): e.g., using ABS
  minority ownership directly as a prior adjustment in expert methodologies
- **Dedicated expert for high-error sectors** that uses fundamentally different
  inputs (BLS occupational data, CMS provider staffing data, etc.)
- **Accepting structural limits** and focusing on honest uncertainty
  communication (the YELLOW floor approach, extended further)

---

## Summary Scorecard

| V8 Component | Effort | Impact | Verdict |
|-------------|--------|--------|---------|
| ABS minority ownership (gate feature) | Medium | High signal, low accuracy gain | Best new addition |
| EPA transit scores (gate feature) | Medium | Zero signal | Remove in V9 |
| 4-digit NAICS (gate feature) | Low | Moderate signal | Keep |
| Regional calibration hierarchy | Medium | Correct but underutilized | Needs more training data |
| Expert E cap | Low | None | Rethink or remove |
| Expert G soft boost | Low | Minimal | Need harder routing or drop G |
| YELLOW confidence floor | Low | Correct communication | Keep |
| Dampening tuning infrastructure | Low | Neutral (kept 0.80) | Available for future |

**Bottom line:** V8 correctly diagnosed the problem and built the right
infrastructure. The regional calibration system is architecturally sound. ABS
minority ownership is a powerful signal. But the improvements are marginal
because the model's fundamental limitation -- census-based estimation for
non-census-like workforces -- wasn't addressed at the estimation layer. V8
improved the routing and calibration layers but left the estimation layer
unchanged.

---

*Generated: 2026-03-11*
*V8 permanent holdout: Race MAE 4.526pp | P>20pp 16.1% | P>30pp 7.9% -- 4/7*
*V6 permanent holdout: Race MAE 4.203pp -- 7/7*
*V7 permanent holdout: Race MAE 4.62pp -- ~4/7*
