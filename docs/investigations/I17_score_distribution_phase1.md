# I17 - Score Distribution After Phase 1 Fixes

Generated: 2026-02-28 23:17

## Summary

Total scored employers: **146,863**. Weighted score range: 1.35-7.68, mean 3.51, median 3.40.

## Tier Distribution

| Tier | Count | % |
|------|------:|--:|
| Priority | 4,004 | 2.7% |
| Strong | 17,927 | 12.2% |
| Promising | 36,753 | 25.0% |
| Moderate | 51,440 | 35.0% |
| Low | 36,739 | 25.0% |

## Weighted Score Histogram

```
  Bin    Count  Bar
  1-2    1,148  
  2-3   42,751  ############################
  3-4   60,104  ########################################
  4-5   41,207  ###########################
  5-6    1,503  #
  6-7      139  
  7-8       11  
```

## Per-Factor Statistics

| Factor | Non-Null | Coverage % | Mean | P25 | P50 | P75 |
|--------|--------:|-----------:|-----:|----:|----:|----:|
| score_osha | 28,973 | 19.7% | 1.36 | 0.00 | 0.40 | 1.46 |
| score_financial | 13,414 | 9.1% | 5.69 | 3.00 | 6.00 | 8.00 |
| score_similarity | 0 | 0.0% | - | - | - | - |
| score_nlrb | 25,879 | 17.6% | 6.64 | 5.18 | 6.37 | 8.40 |
| score_contracts | 0 | 0.0% | - | - | - | - |
| score_industry_growth | 131,204 | 89.3% | 6.67 | 5.00 | 6.70 | 7.20 |
| score_whd | 10,744 | 7.3% | 1.70 | 0.59 | 1.15 | 2.39 |
| score_union_proximity | 73,192 | 49.8% | 8.48 | 5.00 | 10.00 | 10.00 |
| score_size | 146,863 | 100.0% | 2.79 | 0.10 | 0.72 | 4.37 |

## Weighted Score Overall Stats

| Statistic | Value |
|-----------|------:|
| Min | 1.35 |
| Max | 7.68 |
| Mean | 3.51 |
| Std Dev | 0.69 |
| P25 | 2.98 |
| Median (P50) | 3.40 |
| P75 | 4.07 |

## Factor Coverage Distribution

Number of non-null score factors per employer:

| Factors Available | Count | % |
|------------------:|------:|--:|
| 1 | 6,359 | 4.3% |
| 2 | 48,249 | 32.9% |
| 3 | 56,491 | 38.5% |
| 4 | 24,255 | 16.5% |
| 5 | 8,556 | 5.8% |
| 6 | 2,494 | 1.7% |
| 7 | 456 | 0.3% |
| 8 | 3 | 0.0% |

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
