# I12 - Geographic Enforcement Bias Analysis

Generated: 2026-02-24 19:05

## Summary

This investigation examines whether geographic enforcement density (specifically OSHA inspection/match rates by state) systematically inflates organizing scores. If states with more OSHA data also score higher, the scorecard may reflect enforcement geography rather than genuine organizing potential.

- **States analyzed:** 61
- **OSHA match rate range:** 0.0% - 30.6%
- **Avg weighted score range:** 0.05 - 8.88
- **Pearson r (OSHA match % vs avg score):** **0.0828**
- **Pearson r (OSHA match % vs median score):** **0.0270**
- **Enforcement quartile thresholds:** Q25 = 12.5%, Q75 = 18.7%
- **High-enforcement states (>= Q75):** 17 states
- **Low-enforcement states (<= Q25):** 17 states

**Interpretation:** The correlation is **negligible** and **positive** (r = 0.0828). 
This suggests that OSHA enforcement density does NOT systematically inflate scores at a concerning level.

## OSHA Match Rate by State

### Top 10 States (Highest OSHA Match Rate)

| State | F7 Employers | OSHA Matched | Match % |
|-------|------------:|-----------:|--------:|
| PR | 468 | 143 | 30.6% |
| UT | 409 | 101 | 24.7% |
| VI | 93 | 22 | 23.7% |
| AK | 632 | 143 | 22.6% |
| PW | 9 | 2 | 22.2% |
| MI | 6,767 | 1,484 | 21.9% |
| NE | 365 | 79 | 21.6% |
| VT | 251 | 53 | 21.1% |
| IA | 1,489 | 314 | 21.1% |
| KS | 937 | 194 | 20.7% |

### Bottom 10 States (Lowest OSHA Match Rate)

| State | F7 Employers | OSHA Matched | Match % |
|-------|------------:|-----------:|--------:|
| FL | 2,970 | 315 | 10.6% |
| MD | 2,351 | 242 | 10.3% |
| SC | 319 | 32 | 10.0% |
| MN | 6,080 | 596 | 9.8% |
| DC | 943 | 76 | 8.1% |
| AB | 1 | 0 | 0.0% |
| ON | 2 | 0 | 0.0% |
| MB | 1 | 0 | 0.0% |
| AS | 1 | 0 | 0.0% |
| MP | 6 | 0 | 0.0% |

## Average Weighted Score by State

### Top 10 States (Highest Avg Weighted Score)

| State | Employers | Avg Score | Std Dev | Median |
|-------|--------:|---------:|--------:|-------:|
| MB | 1 | 8.88 | N/A | 8.88 |
| NV | 1,511 | 4.61 | 1.98 | 4.62 |
| MN | 6,080 | 4.58 | 1.99 | 4.66 |
| CA | 17,351 | 4.53 | 1.88 | 4.80 |
| GA | 1,285 | 4.52 | 2.03 | 4.41 |
| FL | 2,970 | 4.51 | 1.96 | 4.48 |
| TX | 2,751 | 4.41 | 1.93 | 4.47 |
| HI | 1,048 | 4.38 | 1.76 | 4.05 |
| UT | 409 | 4.34 | 1.99 | 4.03 |
| VA | 1,550 | 4.33 | 1.87 | 4.27 |

### Bottom 10 States (Lowest Avg Weighted Score)

| State | Employers | Avg Score | Std Dev | Median |
|-------|--------:|---------:|--------:|-------:|
| WY | 89 | 3.53 | 1.42 | 3.10 |
| MP | 6 | 3.45 | 0.75 | 3.69 |
| GU | 16 | 3.44 | 1.89 | 2.79 |
| VT | 251 | 3.40 | 1.70 | 3.13 |
| VI | 93 | 3.37 | 1.75 | 3.02 |
| MH | 7 | 3.35 | 1.52 | 2.60 |
| AS | 1 | 2.88 | N/A | 2.88 |
| PW | 9 | 2.57 | 1.10 | 2.88 |
| AB | 1 | 1.69 | N/A | 1.69 |
| ON | 2 | 0.05 | 0.07 | 0.05 |

## Correlation Analysis

| Metric | Value |
|--------|------:|
| Pearson r (OSHA match % vs avg score) | 0.0828 |
| Pearson r (OSHA match % vs median score) | 0.0270 |
| States in analysis | 61 |
| Q25 enforcement threshold | 12.5% |
| Q75 enforcement threshold | 18.7% |

## Scatter Data (All States)

Sorted by OSHA match rate descending. Can be used to plot enforcement density vs. organizing score.

| State | OSHA Match % | Avg Score | Median Score | F7 Employers | OSHA Matched |
|-------|------------:|---------:|------------:|------------:|-----------:|
| PR | 30.6% | 3.80 | 3.68 | 468 | 143 |
| UT | 24.7% | 4.34 | 4.03 | 409 | 101 |
| VI | 23.7% | 3.37 | 3.02 | 93 | 22 |
| AK | 22.6% | 3.91 | 3.77 | 632 | 143 |
| PW | 22.2% | 2.57 | 2.88 | 9 | 2 |
| MI | 21.9% | 4.31 | 4.21 | 6,767 | 1,484 |
| NE | 21.6% | 3.91 | 3.49 | 365 | 79 |
| VT | 21.1% | 3.40 | 3.13 | 251 | 53 |
| IA | 21.1% | 4.14 | 3.68 | 1,489 | 314 |
| KS | 20.7% | 4.04 | 3.68 | 937 | 194 |
| HI | 19.9% | 4.38 | 4.05 | 1,048 | 209 |
| SD | 19.4% | 3.81 | 3.78 | 124 | 24 |
| NV | 19.3% | 4.61 | 4.62 | 1,511 | 291 |
| LA | 19.0% | 4.00 | 3.56 | 756 | 144 |
| TN | 18.9% | 4.02 | 3.71 | 1,098 | 208 |
| MS | 18.7% | 4.27 | 4.11 | 347 | 65 |
| WI | 18.7% | 4.12 | 3.78 | 3,456 | 645 |
| WV | 18.6% | 3.95 | 3.74 | 826 | 154 |
| ME | 18.5% | 4.01 | 3.74 | 271 | 50 |
| AR | 18.3% | 4.24 | 3.87 | 421 | 77 |
| TX | 18.1% | 4.41 | 4.47 | 2,751 | 497 |
| OK | 17.8% | 3.87 | 3.54 | 449 | 80 |
| ND | 17.8% | 4.20 | 4.03 | 185 | 33 |
| VA | 17.5% | 4.33 | 4.27 | 1,550 | 272 |
| AL | 17.4% | 4.23 | 4.08 | 945 | 164 |
| CO | 17.1% | 4.06 | 3.88 | 1,192 | 204 |
| GA | 17.0% | 4.52 | 4.41 | 1,285 | 218 |
| MT | 16.2% | 3.69 | 3.27 | 517 | 84 |
| CA | 16.0% | 4.53 | 4.80 | 17,351 | 2,772 |
| OH | 15.8% | 4.24 | 4.17 | 6,997 | 1,106 |
| CT | 15.2% | 4.13 | 4.10 | 2,052 | 311 |
| NM | 15.1% | 3.95 | 3.59 | 365 | 55 |
| ID | 14.6% | 4.13 | 4.08 | 316 | 46 |
| WY | 14.6% | 3.53 | 3.10 | 89 | 13 |
| MH | 14.3% | 3.35 | 2.60 | 7 | 1 |
| NH | 14.2% | 3.98 | 3.72 | 318 | 45 |
| PA | 14.2% | 4.18 | 4.07 | 9,627 | 1,366 |
| NC | 14.1% | 4.08 | 3.86 | 717 | 101 |
| OR | 14.0% | 4.21 | 4.06 | 2,494 | 349 |
| MO | 13.6% | 4.17 | 3.97 | 5,324 | 726 |
| AZ | 13.5% | 4.29 | 4.13 | 857 | 116 |
| DE | 13.4% | 4.05 | 3.77 | 359 | 48 |
| NJ | 13.2% | 3.93 | 3.72 | 7,313 | 966 |
| IN | 13.0% | 4.00 | 3.68 | 3,748 | 487 |
| GU | 12.5% | 3.44 | 2.79 | 16 | 2 |
| KY | 12.5% | 4.30 | 4.21 | 1,508 | 188 |
| MA | 12.3% | 4.23 | 4.04 | 3,853 | 472 |
| WA | 12.0% | 4.16 | 3.99 | 5,561 | 667 |
| RI | 11.8% | 4.12 | 3.91 | 718 | 85 |
| IL | 11.6% | 3.88 | 3.68 | 14,416 | 1,674 |
| NY | 11.6% | 4.11 | 3.76 | 16,138 | 1,864 |
| FL | 10.6% | 4.51 | 4.48 | 2,970 | 315 |
| MD | 10.3% | 4.24 | 4.06 | 2,351 | 242 |
| SC | 10.0% | 3.99 | 3.77 | 319 | 32 |
| MN | 9.8% | 4.58 | 4.66 | 6,080 | 596 |
| DC | 8.1% | 4.32 | 4.06 | 943 | 76 |
| AB | 0.0% | 1.69 | 1.69 | 1 | 0 |
| ON | 0.0% | 0.05 | 0.05 | 2 | 0 |
| MB | 0.0% | 8.88 | 8.88 | 1 | 0 |
| AS | 0.0% | 2.88 | 2.88 | 1 | 0 |
| MP | 0.0% | 3.45 | 3.69 | 6 | 0 |

## Within-Industry Comparison

For the top 5 most common 2-digit NAICS codes, compare average scores in high-enforcement states (top quartile, >= 18.7%) vs low-enforcement states (bottom quartile, <= 12.5%).

### NAICS 23 (26,347 employers)

| Enforcement Level | Employers | Avg Weighted Score | Avg OSHA Score |
|-------------------|--------:|-----------------:|--------------:|
| HIGH | 4,459 | 4.43 | 2.45 |
| LOW | 9,159 | 4.50 | 2.09 |
| **DELTA (HIGH - LOW)** | | **-0.07** | **+0.36** |

### NAICS 31 (24,075 employers)

| Enforcement Level | Employers | Avg Weighted Score | Avg OSHA Score |
|-------------------|--------:|-----------------:|--------------:|
| HIGH | 4,475 | 3.90 | 1.64 |
| LOW | 7,134 | 3.71 | 1.04 |
| **DELTA (HIGH - LOW)** | | **+0.19** | **+0.60** |

### NAICS 62 (17,005 employers)

| Enforcement Level | Employers | Avg Weighted Score | Avg OSHA Score |
|-------------------|--------:|-----------------:|--------------:|
| HIGH | 1,995 | 5.09 | 1.19 |
| LOW | 7,797 | 5.57 | 0.82 |
| **DELTA (HIGH - LOW)** | | **-0.48** | **+0.37** |

### NAICS 48 (14,882 employers)

| Enforcement Level | Employers | Avg Weighted Score | Avg OSHA Score |
|-------------------|--------:|-----------------:|--------------:|
| HIGH | 1,712 | 4.26 | 1.41 |
| LOW | 4,932 | 4.34 | 0.88 |
| **DELTA (HIGH - LOW)** | | **-0.08** | **+0.53** |

### NAICS 72 (7,571 employers)

| Enforcement Level | Employers | Avg Weighted Score | Avg OSHA Score |
|-------------------|--------:|-----------------:|--------------:|
| HIGH | 1,150 | 4.87 | 1.19 |
| LOW | 3,007 | 4.34 | 0.79 |
| **DELTA (HIGH - LOW)** | | **+0.53** | **+0.40** |

## Score Component Isolation

Average score by component in high-enforcement vs low-enforcement states. Large deltas in score_osha with small deltas elsewhere would confirm enforcement-driven bias rather than genuine differences.

| Component | High Enforcement | Low Enforcement | Delta | Pct of Weighted Delta |
|-----------|----------------:|---------------:|------:|--------------------:|
| weighted_score | 4.20 | 4.15 | +0.05 | 100.0% |
| score_osha | 1.73 | 1.30 | +0.43 | 860.0% |
| score_nlrb | 3.66 | 3.48 | +0.18 | 360.0% |
| score_whd | 1.78 | 1.66 | +0.12 | 240.0% |
| score_contracts | 5.57 | 5.26 | +0.31 | 620.0% |
| score_union_proximity | 8.63 | 8.72 | -0.09 | -180.0% |
| score_industry_growth | 6.59 | 6.77 | -0.18 | -360.0% |
| score_size | 1.67 | 1.41 | +0.26 | 520.0% |
| score_financial | 5.81 | 5.83 | -0.02 | -40.0% |

**High-enforcement states:** AK, HI, IA, KS, LA, MI, MS, NE, NV, PR, PW, SD, TN, UT, VI, VT, WI
**Low-enforcement states:** AB, AS, DC, FL, GU, IL, KY, MA, MB, MD, MN, MP, NY, ON, RI, SC, WA

## Conclusion

Geographic enforcement density does **not** appear to systematically inflate organizing scores at a concerning level (r = 0.0828). While states with higher OSHA match rates do tend to have slightly different score profiles, the effect is weak enough that the current scoring approach is defensible without geographic normalization.

The OSHA component delta between high and low enforcement states is **+0.43** points. The overall weighted score delta is **+0.05** points.
OSHA accounts for approximately **860.0%** of the total score gap between enforcement quartiles.

## Recommendations

1. **No immediate action required.** The weak/negligible correlation does not warrant geographic normalization at this time.
2. **Document:** Note the finding in scoring methodology documentation to demonstrate that enforcement bias was investigated and found to be minor.
3. **Re-run periodically:** As new OSHA data is ingested or matching algorithms change, re-run this investigation to ensure the conclusion still holds.
