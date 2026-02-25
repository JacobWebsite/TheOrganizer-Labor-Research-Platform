# I17 - Score Distribution After Phase 1 Fixes

Generated: 2026-02-24 19:05

## Summary

Total scored employers: **146,863**. Weighted score range: 0.00-10.00, mean 4.18, median 4.00.

## Tier Distribution

| Tier | Count | % |
|------|------:|--:|
| Priority | 2,283 | 1.6% |
| Strong | 15,424 | 10.5% |
| Promising | 40,733 | 27.7% |
| Moderate | 51,698 | 35.2% |
| Low | 36,725 | 25.0% |

## Weighted Score Histogram

```
  Bin    Count  Bar
  0-1    5,982  ######
  1-2    5,720  ######
  2-3   34,442  ########################################
  3-4   27,209  ###############################
  4-5   19,624  ######################
  5-6   32,297  #####################################
  6-7   11,092  ############
  7-8    4,763  #####
  8-9    3,645  ####
 9-10    1,847  ##
10-11      242  
```

## Per-Factor Statistics

| Factor | Non-Null | Coverage % | Mean | P25 | P50 | P75 |
|--------|--------:|-----------:|-----:|----:|----:|----:|
| score_osha | 32,051 | 21.8% | 1.44 | 0.00 | 0.43 | 1.57 |
| score_financial | 10,755 | 7.3% | 5.71 | 3.00 | 6.00 | 8.00 |
| score_similarity | 191 | 0.1% | 8.06 | 10.00 | 10.00 | 10.00 |
| score_whd | 12,025 | 8.2% | 1.70 | 0.59 | 1.15 | 2.39 |
| score_contracts | 8,672 | 5.9% | 5.48 | 4.00 | 6.00 | 8.00 |
| score_industry_growth | 130,975 | 89.2% | 6.67 | 5.00 | 6.70 | 7.20 |
| score_nlrb | 25,879 | 17.6% | 3.59 | 1.69 | 3.37 | 5.06 |
| score_union_proximity | 67,180 | 45.7% | 8.79 | 10.00 | 10.00 | 10.00 |
| score_size | 146,863 | 100.0% | 1.48 | 0.00 | 0.19 | 1.63 |

## Weighted Score Overall Stats

| Statistic | Value |
|-----------|------:|
| Min | 0.00 |
| Max | 10.00 |
| Mean | 4.18 |
| Std Dev | 1.91 |
| P25 | 2.82 |
| Median (P50) | 4.00 |
| P75 | 5.45 |

## Factor Coverage Distribution

Number of non-null score factors per employer:

| Factors Available | Count | % |
|------------------:|------:|--:|
| 1 | 6,171 | 4.2% |
| 2 | 46,866 | 31.9% |
| 3 | 56,736 | 38.6% |
| 4 | 24,845 | 16.9% |
| 5 | 9,165 | 6.2% |
| 6 | 2,543 | 1.7% |
| 7 | 470 | 0.3% |
| 8 | 67 | 0.0% |

## Comparison to Pre-Phase-1

Before Phase 1 fixes, the weighted score distribution was bimodal with peaks at 0-1.5 (employers with sparse data) and 5-6.5 (employers with union proximity and industry growth only). Phase 1 fixes addressed:

- **score_contracts**: Was flat 4.00 for all contractors. Now uses obligation-based tiers (1/2/4/6/8/10).
- **score_financial**: Was BLS-growth-only. Now uses 990 revenue scale + asset cushion + revenue-per-worker.
- **score_tier**: Now percentile-based instead of fixed thresholds.
- **score_nlrb**: Added ULP boost tiers (1=2, 2-3=4, 4-9=6, 10+=8) and 7yr decay.

## Implications

- Check whether the bimodal distribution has smoothed out after Phase 1 fixes.
- Factors with low coverage (e.g., score_similarity at ~0.1%) contribute little to differentiation and may warrant reduced weight or removal.
- If the majority of employers cluster in 2-3 factors_available, score precision is limited and additional data enrichment would help.
