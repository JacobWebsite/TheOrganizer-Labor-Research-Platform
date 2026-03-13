# V9 Best-of + IPF Results

**Date:** 2026-03-11
**Status:** Failed Phase 4 stop gate
**Conclusion:** Stop at pre-calibration. Do not proceed to Phase 5.

## Split

- Training: 10,000
- Dev: 1,525
- Permanent: 1,000
- Total evaluated universe: 12,525
- Split seed: `20260311`
- Dev holdout file: `dev_holdout_1500.json`

No overlap was found between train, dev, and permanent sets.

## Category Winners

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

## Main Pre-Cal Scorecard

### All 2,525 holdout companies

| Metric    | D solo | Best-of naive | Best-of + IPF | Best-of + IPF + ABS |
|-----------|--------|---------------|---------------|---------------------|
| Race MAE  | 4.779  | 4.735         | 4.735         | 4.735               |
| Black MAE | 8.795  | 8.592         | 8.592         | 8.592               |
| Hisp MAE  | 8.820  | 7.437         | 7.437         | 7.437               |
| Gender MAE| 14.169 | 12.836        | 12.836        | 12.836              |
| P>20pp    | 19.84% | 19.96%        | 19.96%        | 19.96%              |
| P>30pp    | 7.82%  | 8.79%         | 8.79%         | 8.79%               |
| Abs Bias  | 0.865  | 1.396         | 1.396         | 1.396               |

### Permanent 1,000

| Metric    | D solo | Best-of naive | Best-of + IPF | V8 post-cal | V6 post-cal |
|-----------|--------|---------------|---------------|-------------|-------------|
| Race MAE  | 4.782  | 4.762         | 4.762         | 4.526       | 4.203       |
| Black MAE | 8.789  | 8.573         | 8.573         |             |             |
| Hisp MAE  | 9.169  | 7.767         | 7.767         | 7.111       | 7.752       |
| Gender MAE| 13.720 | 12.406        | 12.406        | 11.779      | 11.979      |
| P>20pp    | 19.08% | 20.60%        | 20.60%        | 16.1%       |             |
| P>30pp    | 7.97%  | 9.50%         | 9.50%         | 7.9%        |             |
| Abs Bias  | 0.943  | 1.531         | 1.531         | 0.536       | 1.000       |

## Critical Stop Gate

Healthcare South tail rates on **All 2,525**:

| Metric | D solo | Best-of + IPF |
|--------|--------|---------------|
| P>20pp | 30.23% | 33.72%        |
| P>30pp | 12.79% | 19.77%        |
| Count  | 86     | 86            |

The stop gate failed because Best-of + IPF made the Healthcare South tail worse on both thresholds.

## Structural Finding

The IPF and IPF+ABS scorecards are identical to naive best-of. In the implemented setup:

- race row margins are fixed to the normalized best-of race vector
- gender column margins are fixed to the best-of gender vector

That means the 2D IPF step cannot change the reported race marginals, so it cannot improve race MAE or race tail metrics relative to naive normalization. ABS seed adjustment changes only the internal matrix cells, not the final race/gender margins reported in the scorecard.

## Files

- Results JSON: `v9_best_of_ipf_results.json`
- Prediction checkpoint: `v9_best_of_ipf_prediction_checkpoint.json`
- Dev split: `dev_holdout_1500.json`
