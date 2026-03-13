# Codex Summary: V9 Best-of-Expert + IPF Test

**Date:** 2026-03-11  
**Author:** Codex  
**Status:** Phase 4 stop gate failed

## Executive Conclusion

The V9 "best-of expert per category + IPF normalization" approach does not justify further investment in its current form.

It produces a small average Race MAE improvement over `D solo` on the holdouts, but it fails the actual decision criterion: tail risk in **Healthcare/South** gets worse, not better. That is enough to stop before calibration.

There is also a structural issue in the IPF design used here: once race row margins are fixed to the normalized best-of race vector, the 2D IPF step cannot change the final race marginals. In practice, `Best-of naive`, `Best-of + IPF`, and `Best-of + IPF + ABS` collapse to the same race scorecard. That means IPF is not adding corrective power for the metric that matters most.

## Experimental Setup

- Frozen permanent holdout: 1,000 companies from `selected_permanent_holdout_1000.json`
- Remaining pool from `expanded_training_v6.json`: 11,525 companies
- New split:
  - Training: 10,000
  - Dev: 1,525
  - Permanent: 1,000
- Split seed: `20260311`

Artifacts written:

- `dev_holdout_1500.json`
- `v9_best_of_ipf_prediction_checkpoint.json`
- `v9_best_of_ipf_results.json`
- `V9_BEST_OF_IPF_RESULTS.md`

## Category Winners Learned on Training

| Category | Winner |
|----------|--------|
| White    | D |
| Black    | G |
| Asian    | D |
| AIAN     | G |
| NHOPI    | B |
| Two+     | F |
| Hispanic | B |
| Female   | F |

This confirms the earlier V8.5 finding that different experts are best for different dimensions. The theoretical per-category advantage is real. The practical issue is that the assembled vector still has to be normalized, and the normalization method here does not solve the tail problem.

## Main Results

### All holdouts combined (2,525 companies)

| Metric    | D solo | Best-of naive | Best-of + IPF |
|-----------|--------|---------------|---------------|
| Race MAE  | 4.779  | 4.735         | 4.735         |
| Black MAE | 8.795  | 8.592         | 8.592         |
| Hisp MAE  | 8.820  | 7.437         | 7.437         |
| Gender MAE| 14.169 | 12.836        | 12.836        |
| P>20pp    | 19.84% | 19.96%        | 19.96%        |
| P>30pp    | 7.82%  | 8.79%         | 8.79%         |
| Abs Bias  | 0.865  | 1.396         | 1.396         |

Interpretation:

- Average error improves slightly.
- Tail error gets worse.
- Bias gets worse.
- IPF provides no observable gain over naive normalization.

### Permanent holdout (1,000 companies)

| Metric    | D solo | Best-of naive | Best-of + IPF | V8 post-cal | V6 post-cal |
|-----------|--------|---------------|---------------|-------------|-------------|
| Race MAE  | 4.782  | 4.762         | 4.762         | 4.526       | 4.203       |
| Black MAE | 8.789  | 8.573         | 8.573         |             |             |
| Hisp MAE  | 9.169  | 7.767         | 7.767         | 7.111       | 7.752       |
| Gender MAE| 13.720 | 12.406        | 12.406        | 11.779      | 11.979      |
| P>20pp    | 19.08% | 20.60%        | 20.60%        | 16.1%       |             |
| P>30pp    | 7.97%  | 9.50%         | 9.50%         | 7.9%        |             |
| Abs Bias  | 0.943  | 1.531         | 1.531         | 0.536       | 1.000       |

Interpretation:

- This does not recover V8, and it is far from V6.
- The permanent-holdout tail metrics are materially worse than V8.
- Pre-calibration numbers are not close enough to justify expecting calibration to rescue the approach.

## Stop Gate Result

The prompt’s critical gate was:

> If Best-of + IPF does not reduce P>20pp and P>30pp for Healthcare South on All 2,500 compared to D solo, stop.

Observed result on the combined holdouts:

| Metric | D solo | Best-of + IPF |
|--------|--------|---------------|
| P>20pp | 30.23% | 33.72%        |
| P>30pp | 12.79% | 19.77%        |
| Count  | 86     | 86            |

This is a clear fail. The approach worsens both tail thresholds in the exact segment it was supposed to fix.

## Why IPF Did Not Help

The decisive issue is mathematical, not just empirical.

In this experiment:

- row margins = normalized best-of race estimates
- column margins = best-of gender estimate
- reported race output = row sums of the converged matrix

Once the row margins are fixed, the output race percentages are fixed. IPF can change the internal race-by-gender cells, but it cannot change the final race marginals reported to the scorecard. That is why:

- `Best-of naive`
- `Best-of + IPF`
- `Best-of + IPF + ABS`

all produced identical race metrics.

ABS seed adjustment likewise has no scorecard effect if the final row and column margins are held constant.

So the current IPF formulation is not just underperforming. It is largely incapable of changing the race outcome being evaluated.

## What This Means

This result does **not** prove that per-category selection is useless. It proves that:

1. Per-category selection alone is not enough.
2. This IPF normalization design does not solve the race-reconciliation problem.
3. The hard cases remain structural, especially Healthcare/South.

The small MAE improvement suggests there is some signal in per-category winner selection. But the cost is worse tail behavior, and the proposed IPF layer does not supply a mechanism to correct that.

## Recommendation

Do not proceed to Phase 5 calibration for this V9 variant.

Recommended project decision:

- Mark this variant as failed at the pre-calibration gate.
- Keep V6 as the production benchmark.
- Treat this experiment as further evidence that the census-based stack is close to its ceiling on race prediction, especially in diverse Southern healthcare labor markets.

If demographics work continues, the next credible directions are:

- Use non-census signals that can actually move race marginals.
- Reframe ABS or occupation-chain as direct race constraints, not just seed shaping.
- Test a normalization method where race margins are not fully locked before reconciliation.
- Otherwise, redirect effort to platform priorities rather than additional census-only architecture churn.

## Bottom Line

This V9 path produced an interesting diagnostic but not a shippable model.

The average got a little better. The tail got worse. IPF did not materially change the evaluated race output. By the prompt’s own gate, the correct decision is to stop here.
