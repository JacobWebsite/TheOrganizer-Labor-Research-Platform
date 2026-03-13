# Demographics Estimation V5 Proposal

## 1. Goal

Build a `v5` demographics estimator that is:

- more robust on unseen companies than `v4`
- less dependent on hard-coded routing rules
- less prone to zero-collapse on rare categories
- explicitly optimized for both average error and bad outliers
- calibrated enough to reduce the recurring White-over / Asian-under bias

The production target should remain **company-level workforce composition estimation**, not individual classification.

## 2. Why V5 Is Needed

Current evidence suggests:

- `v4` development evaluation ranks `M3e Fin-Route-IPF` and `M8 Adaptive-Router` first on the combined ~998-company evaluation set
- the same `v4` report notes that run has **no new holdout**
- the dedicated holdout report still recommends `M3b Damp-IPF` as the most reliable production race model
- `M8` is still a manually authored rule router rather than a learned ensemble
- the multiplicative IPF family can collapse categories to zero when one source is zero
- top `v4` methods still show systematic signed bias, especially White overestimation and Asian underestimation

That means `v5` should focus first on **generalization, calibration, and tail-risk control**, not just squeezing out another small development-set MAE gain.

## 3. Core V5 Idea

`v5` should be a **regularized mixture-of-experts** with:

1. a small number of interpretable expert models
2. a learned gating model that picks or blends experts based on company context
3. probability smoothing so rare categories never collapse to zero
4. post-hoc calibration to reduce systematic bias
5. uncertainty scoring and a review flag for historically hard cases

Instead of:

- hand-tuned `if/elif` routing
- declaring a winner from a reused development pool
- optimizing only average race MAE

`v5` should learn which expert works best **out of fold** and then score itself using both mean and tail metrics.

## 4. Proposed V5 Architecture

### 4.1 Expert models

Keep the model family small and interpretable.

#### Expert A: Smoothed Dampened IPF

This is the `M3b/M3c` family upgraded with smoothing.

For category `k`:

```text
acs'_k   = acs_k   + λ * prior_k
lodes'_k = lodes_k + λ * prior_k

raw_k = (acs'_k ^ α) * (lodes'_k ^ (1 - α))
pred_k = raw_k / Σ raw
```

Where:

- `prior_k` is a broad fallback prior for the category
- `λ` is a small pseudocount / smoothing weight
- `α` is learned with shrinkage, not picked by hard-coded group tables alone

Recommended starting values:

- `prior_k`: national EEO-1 prior, optionally adjusted by region
- `λ`: 1.0 to 3.0 percentage points
- `α`: learned by segment but shrunk toward `0.50`

#### Expert B: Tract-Heavy Geography Model

This extends the current Hispanic tract logic to race.

```text
pred = w1 * acs_industry_state + w2 * lodes_county + w3 * tract_proxy
```

Where `tract_proxy` is drawn from:

- ZIP-to-best-tract crosswalk
- tract racial composition
- tract Hispanic composition
- optionally a tract-to-county reliability score

Recommended starting weights:

- race: `0.40 / 0.25 / 0.35`
- Hispanic: `0.45 / 0.20 / 0.35`
- gender: keep lower tract weight unless validation shows improvement

#### Expert C: Occupation-Heavy Model

This is the `M4` idea, but focused on cases where occupation signal is actually informative.

```text
pred = w1 * occupation_mix_demo + w2 * acs_industry_state + w3 * lodes_county
```

Recommended use:

- healthcare
- professional services
- finance
- staffing
- large diversified firms where occupation mix is better than pure geography

#### Expert D: Simple Conservative Blend

This is a low-variance fallback.

```text
pred = 0.50 * acs_industry_state + 0.30 * lodes_county + 0.20 * broad_prior
```

Its job is not to win on average. Its job is to be stable when other experts disagree or when inputs are sparse.

### 4.2 Gating model

Replace hard-coded routing with a learned model that outputs expert weights.

For company `i`, compute:

```text
g_i = softmax(βX_i)
final_pred_i = Σ_e g_i,e * expert_pred_i,e
```

Where `X_i` includes:

- `naics_group`
- `state`
- `region`
- `urbanicity`
- `county_minority_share`
- `size_bucket`
- ZIP/tract coverage quality
- occupation coverage quality
- source disagreement features:
  - `|acs_white - lodes_white|`
  - entropy of ACS prior
  - entropy of LODES prior
  - `max category gap`

Recommended first implementation:

- multinomial logistic regression or gradient boosted trees
- strong regularization
- trained only on **out-of-fold expert predictions**

Important rule:

- the gate should learn from out-of-fold predictions only
- never train the gate on in-sample expert predictions

### 4.3 Calibration layer

After the ensemble produces a distribution, apply calibration.

Recommended options:

- per-category linear bias correction on out-of-fold predictions
- simplex-preserving temperature scaling
- Dirichlet calibration if implementation effort is acceptable

Minimum viable calibration:

1. fit signed residual correction by category on out-of-fold predictions
2. renormalize to 100
3. enforce category floor and ceiling rules

This directly targets the recurring:

- White positive bias
- Asian negative bias
- occasional large Black over/under corrections in subgroup pockets

### 4.4 Uncertainty and abstention

Each prediction should include:

- `predicted_distribution`
- `confidence_score`
- `review_flag`
- `review_reason`

Trigger `review_flag = true` when:

- top two experts differ by more than `10pp` on any major category
- model entropy is very low while source disagreement is high
- company falls in a historically hard segment
- tract mapping is weak or missing
- occupation coverage is weak or missing

Likely hard segments:

- ethnic/community banks
- unusual finance firms
- staffing companies
- firms with highly atypical Asian or Black concentration relative to county priors

## 5. Dimension-Specific Strategy

Do not force one winner across race, Hispanic, and gender.

### Race

Use full ensemble:

- smoothed dampened IPF
- tract-heavy expert
- occupation-heavy expert
- conservative blend

Primary target metric:

- weighted race MAE with tail penalty

### Hispanic

Keep geography stronger than in race.

Starting point:

- tract-heavy expert should likely carry more weight
- occupation-heavy should remain secondary
- conservative blend should be available as fallback

Primary target metric:

- Hispanic MAE

### Gender

Current evidence says pure IPF still wins, but gender is underdeveloped methodologically.

For `v5`, test:

- IPF baseline
- occupation-heavy gender expert
- conservative blend

Possible added data later:

- BLS/OEWS occupation-by-sex signal
- better staffing-pattern proxies by industry

Primary target metric:

- gender MAE

## 6. Smoothing and Backoff Rules

This is a critical `v5` change.

### 6.1 Category floor

Before final normalization:

- no category should be exactly `0` unless every source and prior says `0`
- apply a small floor such as `0.1` to `0.25` percentage points for rare categories

### 6.2 Reliability-weighted backoff

When a source is weak, shrink toward a broader prior.

Examples:

- missing tract -> shrink tract-heavy expert toward county prior
- sparse occupation mix -> shrink occupation-heavy expert toward ACS + broad prior
- extreme ACS/LODES conflict -> increase conservative blend weight

### 6.3 Hierarchical shrinkage

Any segment-specific parameter should shrink toward a parent group:

- NAICS 6 -> NAICS group -> all-industry prior
- state -> region -> national

This is how `v5` avoids the `M1b` problem where tiny groups get extreme weights.

## 7. Evaluation Framework

This is as important as the model itself.

### 7.1 Split design

Use three levels:

1. **Development folds** for model and hyperparameter tuning
2. **Validation set** for final design decisions
3. **Frozen test set** used once for final reporting

If sample size is tight, use:

- grouped 5-fold cross-validation for development
- plus one untouched final holdout

### 7.2 Grouping rules

Splits should be grouped to avoid leakage through near-duplicates.

Recommended grouping keys:

- company code
- corporate family if available
- NAICS group sanity check
- source-set origin

### 7.3 Metrics

Stop choosing winners by race MAE alone.

Use a dashboard:

- race MAE
- race Hellinger
- Hispanic MAE
- gender MAE
- max category error
- `P(max_error > 20pp)`
- `P(max_error > 30pp)`
- signed bias by category
- performance by:
  - industry group
  - size bucket
  - region
  - minority-share bucket
  - urbanicity

### 7.4 Selection objective

For race, recommend:

```text
score = race_mae
      + 0.20 * p(max_error > 20)
      + 0.35 * p(max_error > 30)
      + 0.15 * mean_abs_signed_bias
```

This can be tuned, but the key is:

- punish catastrophic misses
- punish systematic bias
- do not let tiny average gains hide ugly tails

## 8. Recommended Initial V5 Parameters

Start simple.

### 8.1 Experts

- Expert A: smoothed dampened IPF, `α = 0.50`, `λ = 2.0`
- Expert B: tract-heavy blend
- Expert C: occupation-heavy blend
- Expert D: conservative blend

### 8.2 Gate

- multinomial logistic regression
- `L2` regularization
- one-hot NAICS group, region, urbanicity, size bucket
- continuous inputs standardized

### 8.3 Calibration

- per-category linear residual correction on out-of-fold predictions
- renormalize to 100

### 8.4 Review flags

Raise a review flag if:

- any two experts differ by `>= 10pp` on White, Black, or Asian
- predicted Asian share exceeds county Asian by `>= 20pp`
- predicted Black share exceeds county Black by `>= 25pp`
- final max category share is `>= 85%` and expert disagreement is high

These thresholds should be re-tuned after the first `v5` validation pass.

## 9. Implementation Plan

### Phase 1: Baseline V5 skeleton

Create:

- `methodologies_v5.py`
- `compute_v5_oof_predictions.py`
- `train_v5_gate.py`
- `evaluate_v5.py`
- `generate_report_v5.py`

Deliverables:

- expert predictions per company
- out-of-fold gate training table
- calibrated final predictions
- `V5_REPORT.md`

### Phase 2: Smoothed expert family

Implement:

- smoothed dampened IPF
- tract-heavy race expert
- conservative fallback expert

Goal:

- beat `M3b` on development folds without worse tail behavior

### Phase 3: Learned gate

Train:

- out-of-fold expert selection/blending model

Goal:

- beat best single expert on validation
- retain interpretable routing diagnostics

### Phase 4: Calibration and review flagging

Implement:

- bias correction
- confidence score
- review flag

Goal:

- reduce signed White/Asian bias
- reduce catastrophic cases

## 10. Acceptance Criteria

Do not call `v5` successful unless it meets all of:

1. beats `M3b` on validation race MAE
2. does not increase `P(max_error > 30pp)`
3. reduces average absolute signed bias on race categories
4. keeps Hispanic and gender at least neutral relative to the best current methods
5. remains interpretable enough to explain why a company received a given estimate

## 11. Recommended Production Policy

Until `v5` passes validation:

- use `M3b` as the production race baseline
- use the best current Hispanic method separately
- use the best current gender baseline separately
- treat `M8` as a development prototype, not the final production router

If `v5` passes validation:

- deploy ensemble prediction
- expose confidence and review flags
- log segment-level residuals for periodic recalibration

## 12. What Not To Do In V5

- do not add more hand-authored routing exceptions
- do not optimize only on the combined evaluation pool
- do not accept zero-collapse for rare categories
- do not declare success from average MAE alone
- do not use the model for individual-level demographic assignment

## 13. One-Sentence Summary

`v5` should be a **smoothed, calibrated, out-of-fold-trained mixture-of-experts** that keeps the interpretability of `M3b/M3c`, adds tract and occupation specialists, learns routing instead of hard-coding it, and is selected using generalization plus tail-risk metrics rather than development-set race MAE alone.
