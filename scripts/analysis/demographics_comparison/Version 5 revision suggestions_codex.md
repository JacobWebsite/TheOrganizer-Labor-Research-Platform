# Version 5 Revision Suggestions (Codex)

Date: 2026-03-09
Source reviewed:
- `V5_COMPLETE_RESULTS.md`
- `V5_FINAL_REPORT.md`
- `validate_v5_final.py`
- `train_gate_v1.py`
- `generate_oof_predictions_v5.py`

## Executive Assessment

V5 is a meaningful engineering improvement over prior versions, but the report overstates the strength of the evidence for the final production decision.

What looks solid:
- The zero-collapse fix is real and necessary.
- The Admin/Staffing routing fix is well-motivated.
- BDS as a post-prediction nudge appears net negative and should not remain in the scored production path.
- Occupation-heavy methods appear uncompetitive and can likely be retired.

What is still weak:
- The final Gate v1 win over M3b is small.
- The report does not quantify uncertainty around that win.
- Several document-level counts are inconsistent.
- The validation path and the written production recommendation are not fully aligned.

My overall judgment: V5 is good enough to keep as an experimental candidate, but the current write-up does not yet justify a strong "make Gate v1 the default production model" conclusion.

## High-Confidence Findings

### 1. The zero-collapse fix is the clearest success

This is the strongest and most defensible part of the report. The failure mode is concrete, the fix is concrete, and the before/after contrast is large. This should be framed as a correctness repair first and a model improvement second.

Suggested rewrite:
- "V5 definitively fixes a pathological zeroing bug in IPF-family methods."
- Avoid presenting the smoothing floor as if it were mainly a new modeling advance. It is primarily a bug fix.

### 2. The routing bug fix for Admin/Staffing is credible

The report gives a specific mechanism and a specific corrected route. This is a good example of a targeted domain correction based on observed behavior rather than generic tuning.

Suggested next step:
- Add a small table showing Admin/Staffing error before vs after the route change, not just route counts.

### 3. The BDS nudge should be removed from the decision path

The report explicitly concludes that BDS hurts holdout performance. That is a strong enough result to simplify the system.

Important inconsistency:
- `V5_COMPLETE_RESULTS.md` recommends disabling the BDS nudge.
- `validate_v5_final.py` still applies `apply_bds_nudge()` inside `predict_gate_v1()`.

That means the written recommendation and the validation implementation are not aligned. The report should not claim the nudge should be disabled while the active validation path still includes it.

Suggested revision:
- Re-run final holdout metrics with BDS fully disabled in the evaluated prediction path.
- Treat BDS only as a flagging or plausibility-check signal.

## Reporting And Consistency Issues

These are not minor editorial problems. They affect interpretability.

### 1. Holdout denominator is inconsistent

The documents use multiple holdout counts:
- `225 companies` selected
- `208 successfully processed`
- `V5_FINAL_REPORT.md` says `Fresh holdout: 208 companies`
- `V5_FINAL_REPORT.md` also says `Skipped: 0`

Those statements do not reconcile cleanly.

Revision needed:
- Standardize three numbers everywhere:
  - selected holdout companies
  - evaluable companies
  - skipped companies
- Use the same denominator in the summary, result tables, routing tables, and review-flag tables.

### 2. The review-flag count is not trustworthy as written

`V5_COMPLETE_RESULTS.md` reports:
- `Any flag: 213`
- denominator shown as `225`

But the final scored holdout is `208`. A flag summary should usually be computed on the same evaluated population unless clearly labeled otherwise.

Revision needed:
- Split this into:
  - flags among all selected holdout definitions
  - flags among evaluated companies
- Use exact counts rather than `~180`, `~60`, `~90` if the pipeline can produce exact integers.

### 3. Section numbering has a duplicate

There are two `9.5` sections. Small issue, but it signals that the report needs one editorial pass before being treated as a final artifact.

### 4. The acceptance-criteria framing is too favorable

The report says `ALL 5 CRITERIA PASS`, but this hides two important facts:
- `P>20pp` is worse for Gate v1 than M3b.
- The improvements on the "pass" metrics are very small.

The current framing reads like a launch memo. The evidence reads more like a narrow experimental edge.

Suggested rewrite:
- Replace `ALL 5 CRITERIA PASS` with `Gate v1 narrowly outperformed M3b on the preselected acceptance criteria, but not by a statistically established margin`.

## Statistical And Evaluation Concerns

### 1. The final improvement is too small to present without uncertainty intervals

Gate v1 beats M3b by:
- `0.052` Race MAE
- `0.118` Composite
- `0.377` Abs Bias

That may be real, but the report does not show whether it is stable.

Required additions:
- Paired bootstrap confidence intervals for per-company MAE deltas
- A sign test: how often Gate v1 beats M3b company-by-company
- Standard error or confidence interval for each top-line metric

Without that, the report should avoid definitive language.

### 2. Router CV accuracy is not the right primary success metric

`59.8%` CV accuracy sounds good, but routing is not a standard classification problem. The real question is regret:
- How much worse is the chosen expert than the oracle expert for that company?
- How much does the gate recover of the oracle improvement over Expert D?

Suggested additions:
- Oracle MAE
- Gate regret relative to oracle
- Fraction of oracle gain recovered
- Top-2 routing accuracy

That would make the gate evaluation much more meaningful than plain class accuracy.

### 3. The composite score is subjective and should get a sensitivity analysis

The composite formula is a policy choice, not a law of nature. A model can "win" because the weights reward certain tradeoffs.

Revision needed:
- Show rankings under:
  - pure Race MAE
  - composite without bias term
  - composite with stronger catastrophic-miss penalties
- Show whether Gate v1 still wins across reasonable weighting choices.

### 4. The report should separate model-selection evidence from final-test evidence more cleanly

Run 1 is very useful diagnostically, but it is still training-set centered. Later sections correctly become more cautious, but the report still mixes:
- method search
- model tuning
- final validation

Revision needed:
- Add a dedicated section titled `What was used for model selection vs what was held out for final evaluation`.
- Mark each table as either:
  - training comparison
  - OOF estimate
  - untouched holdout estimate

## Modeling Concerns

### 1. Gate v1 is probably too brittle because it hard-routes to one expert

The gate chooses a single expert, then applies a fixed expert-level calibration vector. That is simple, but the review-flag rate suggests the router is often uncertain.

A better next version would likely be:
- soft mixture of experts
- probability-weighted average of A/B/D predictions
- then calibrate the final mixture output

This is a better match to borderline cases than forcing a hard winner.

### 2. Calibration is too coarse

Calibration is currently one mean signed-error vector per expert. That ignores systematic differences by:
- industry
- region
- urbanicity
- minority-share bucket
- data-source availability

Suggested improvement:
- segment-specific calibration
- or a lightweight calibration model conditioned on segment features

### 3. Gate v1 uses a narrow feature set

`train_gate_v1.py` uses:
- `naics_group`
- `region`
- `urbanicity`
- `size_bucket`
- `minority_share`
- `alpha_used`

That is a fairly weak feature set for routing.

Notable gap:
- The older gate feature builder includes richer signals such as tract availability and ACS-vs-LODES disagreement, but the final Gate v1 does not use them.

Suggested added features:
- PUMS coverage available or not
- tract data available or not
- ACS-vs-LODES disagreement magnitude
- county minority share as numeric
- estimated uncertainty or entropy of source distributions
- expert disagreement proxies

### 4. Geography backoff is still too abrupt

The report discusses `PUMS metro` coverage and fallback to `state-level ACS`, but this appears to remain a discrete backoff rather than a hierarchical shrinkage strategy.

Suggested improvement:
- use tract -> county -> metro -> state shrinkage
- weight by sample size and reliability instead of binary fallback

This is likely more robust in sparse areas than the current approach.

### 5. Gender should be split off as a separate modeling problem

The report is already honest that gender performance remains poor. That suggests the current shared structure is not adequate.

Suggested next step:
- stop treating gender improvement as a side effect of the race-routing model
- build a dedicated gender estimator with different features and, if possible, different data sources

## Holdout Design Concerns

The final holdout is useful, but the composition limits what can be concluded.

Observed limitations:
- Very small rural sample
- Several small NAICS segments
- Strong urban concentration
- Only 208 scored examples

This means the result is directionally useful, but not broad enough for aggressive claims about general production superiority.

Revision needed:
- Add subgroup holdout results by:
  - NAICS group
  - region
  - urbanicity
  - minority-share bucket
  - PUMS available vs fallback
- Show where Gate v1 actually wins and where it loses.

## Specific Revisions To The Written Conclusions

### Current conclusion is too strong

The current report implies:
- Gate v1 is the final winner
- production deployment is justified

More defensible wording:
- "Gate v1 is a promising candidate that slightly outperformed M3b on this fresh holdout, primarily through lower bias and fewer catastrophic misses."
- "Because the margin is small and most predictions are still review-flagged, M3b remains the strongest simple baseline."
- "Before promoting Gate v1 as default, rerun the final validation with BDS disabled and add confidence intervals."

### Current reporting should distinguish:

- engineering fixes that are definitely correct
- experimental modeling gains that are still modest
- production choices that depend on risk tolerance

That distinction would materially improve the credibility of the document.

## Recommended Revision Plan

### P0: Fix report integrity

1. Reconcile all holdout counts and denominators.
2. Correct the review-flag summary so it is based on the right population.
3. Fix duplicate section numbering and do one editorial cleanup pass.
4. Clarify whether final reported Gate v1 metrics include BDS nudge.

### P1: Re-run the final evaluation cleanly

1. Recompute final metrics with BDS disabled in the evaluated path.
2. Add paired bootstrap confidence intervals.
3. Add company-level sign test versus M3b.
4. Report exact evaluated `n` for every metric.

### P2: Improve the routing approach

1. Test soft mixture-of-experts instead of hard routing.
2. Add richer routing features.
3. Report oracle gap and routing regret.
4. Add segment-specific calibration.

### P3: Simplify the model family

1. Retire BDS nudge as a correction mechanism.
2. Retire occupation-weighted families from the main comparison table unless they serve as historical baselines.
3. Keep M3b as the simple, transparent fallback baseline.

### P4: Split off underperforming targets

1. Build a dedicated gender estimation track.
2. Consider separate routing or calibration for Hispanic estimation if that target is operationally important.

## Bottom Line

Version 5 should be revised to say:

- V5 definitely improves methodological hygiene.
- V5 definitely fixes an important IPF failure mode.
- Gate v1 is promising, but its holdout advantage over M3b is narrow and not yet statistically established.
- The report should not treat Gate v1 as a decisive winner until the BDS mismatch is removed, the denominators are cleaned up, and uncertainty is reported.
