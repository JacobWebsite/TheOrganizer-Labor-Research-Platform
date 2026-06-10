---
title: Scoring Weights vs Predictive Power — Design Memo
date: 2026-05-12
author: scoring-agent
status: recommendation
---

# Scoring Weights vs Predictive Power

## TL;DR

**Recommendation: Option C — defer to post-launch.** The Open Problem
was already marked resolved 2026-04-03 (D12 closed proximity 25 -> 10
and bumped contracts/financial/similarity). Re-litigating weights mid-
launch-runway costs 1-2 weeks of compute + tier-migration UX for an
uncertain gain. Real organizing-outcome data will accumulate as the
platform is used; that's a much better learning signal than NLRB
binary win/loss, which the 2026-03-02 logistic regression already
showed is too noisy.

## Current Weight Derivation

Pillar weights and Leverage sub-weights are hand-picked, shaped by:

1. **Domain intuition.** "Anger" (enforcement signals) and "Leverage"
   (structural power) are organizer-facing concepts predating any data.
   Original three-pillar Anger/Stability/Leverage 3/3/4 ratios came
   from project-launch design docs, not regression.

2. **Coverage pragmatism.** Sparse factors get lower weight so they
   don't dominate the small subset that has them (e.g., Form 5500
   benefits at 2.5% coverage demoted to passthrough flags via D13).

3. **One-shot logistic regression (2026-03-02).**
   `scripts/analysis/validate_pillar_weights.py` ran logreg on 6,403
   NLRB election outcomes with anger/stability/leverage features
   (output: `docs/analysis/pillar_weight_validation.csv`):
   - Base win rate 79.9%; model accuracy ~80% (no marginal lift).
   - Stability coefficient slightly negative.
   - Conclusion: pillars do not add predictive power beyond base
     rates. Individual factors do vary in lift — NLRB +10.2pp,
     Industry Growth +9.6pp, Contracts +5.7pp, WHD/Financial +4.1pp;
     Proximity +0.0pp, Size +0.2pp.

Current weights (in `scripts/scoring/build_unified_scorecard.py:619-696`):

| Pillar | Weight | Sub-factor | Sub-weight | Lift |
|--------|-------:|------------|-----------:|-----:|
| Anger | 3 | OSHA | 3 | -0.6 |
| | | WHD | 3 | +4.1 |
| | | NLRB | 3 | +10.2 |
| | | ULP | 4 (gated) | (subsumed) |
| Leverage | 4 | Contracts | 25 | +5.7 |
| | | Financial | 25 | +4.1 |
| | | Similarity | 15 | N/A |
| | | Industry Growth | 10 | +9.6 |
| | | Proximity | 10 | +0.0 |
| | | Size | 0 | +0.2 |
| Stability | 0 (D13) | — | — | — |

Dynamic denominator `(anger*3 + leverage*4) / active_pillar_weights`
ensures NULL pillars don't deflate the score (D12 fix).

## What "Learned From Outcomes" Would Require

1. **Labeled training data for "successful organizing."** Not NLRB
   election outcomes — they have self-selection bias (only employers
   that reached petition stage are in the data), 80% base win-rate
   swamps weight tuning, and per-employer signal is noisy. We have
   none of the alternatives (campaign-movement, organizer-graded
   actionability, long-term density changes).

2. **A model class.** Logreg coefficients aren't directly interpretable
   as 0-100 sub-factor weights. Would need a re-projection step
   (e.g., Lasso for sparsity then normalize), stability validation,
   and hold-out evaluation. Multi-week effort.

3. **A validation harness.** We have `score_change_report.py` for
   pre/post tier-migration counts; we don't have organizer feedback
   capture or a labeled cohort.

## Three Options

### Option A — Keep fixed weights, accept the limitation
Current state. Documented in CLAUDE.md predictive-power table and the
Open Problem note. No further work pre-launch.

### Option B — Approximate via correlations with NLRB win-rate
Reallocate sub-weights proportional to lift: Contracts 30, Industry
Growth 25, Financial 20, Proximity 10, Size 5, Similarity 10.

- **Pros:** Visible "predictive power respected" story.
- **Cons:** Re-runs the 2026-03-02 mistake of treating NLRB win/loss
  as ground truth — the +10.2pp NLRB lift mostly reflects that
  prior-election employers are likely to face another, not "good
  organizing target." Forces high tier migration (Strong / Promising
  / Speculative reshuffle) needing organizer-facing comms mid-launch.
  ~1-2 days compute + ~1 week UX.

### Option C — Defer to post-launch
Ship with current weights. Build the outcome metric as the platform
is used: organizer feedback per scored employer, campaign trackers,
note-taking on actions. Feed a supervised-learning pipeline 6-12
months post-launch.

- **Pros:** Avoids re-litigating a settled decision (D12 closed
  2026-04-03). Launch roadmap stays intact. Buys time to build the
  *right* outcome metric instead of the available-but-wrong one.
- **Cons:** Ships with documented limitation. Organizers may surface
  "why does this Speculative employer rank high?" — answer is the
  size/similarity model thinks they look like organized comparables,
  unverified.

## Recommendation: Option C

1. **The Open Problem was already resolved 2026-04-03.** D12+D13
   reduced proximity 25 -> 10, demoted stability to flags, bumped
   contracts/financial/similarity. Current weights are the post-fix
   state, not pre-discussion priors.

2. **Outcome data is the bottleneck, not weights.** Re-running
   regression with different weight combos changes nothing
   fundamental; the data is the limit.

3. **Launch timing.** Week 4 of 9 in
   `ROADMAP_2026_05_04_to_2026_07_05_LAUNCH.md`. Adding tier-migration
   work to that runway is net-negative vs shipping with documented
   limitations.

**Post-launch next steps (Q3 2026):**
- Add organizer feedback capture per scored employer.
- Define operational outcome metric (campaign-movement vs election-win).
- Re-run `validate_pillar_weights.py` once new outcome metric has
  200+ labeled rows.
- If signal clears noise, re-run weight tuning with hold-out + review.

## References

- `Open Problems/Scoring Weights Ignore Predictive Power.md` (resolved 2026-04-03)
- `scripts/scoring/build_unified_scorecard.py:619-696`
- `scripts/analysis/validate_pillar_weights.py`
- `docs/analysis/pillar_weight_validation.csv`
- `CLAUDE.md` 10-factor table with predictive lift annotations
- `ROADMAP_2026_05_04_to_2026_07_05_LAUNCH.md`
