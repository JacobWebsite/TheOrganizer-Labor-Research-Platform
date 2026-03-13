# V6 Ablation Study Report

**Holdout:** permanent
**Companies:** 345 processed, 55 skipped
**Runtime:** 94.5s

---

## Full Results Table

| Method | Race MAE | P>20pp | P>30pp | Abs Bias | Composite | Hisp MAE | Gender MAE | N |
|--------|---------|--------|--------|----------|-----------|----------|------------|---|
| M3c-V5 (baseline) | 4.372 | 15.4% | 4.0% | 1.309 | 9.046 | 8.122 | 16.407 | 325 |
| G1 Occ-Gender | 4.372 | 15.4% | 4.0% | 1.309 | 9.046 | 8.122 | 13.774 | 325 |
| H1 Geo-Hisp | 4.372 | 15.4% | 4.0% | 1.309 | 9.046 | 8.193 | 16.407 | 325 |
| M9b QCEW-Adapt | 4.384 | 16.0% | 4.0% | 1.267 | 9.174 | 8.122 | 16.407 | 325 |
| M8-V5 (router) | 4.501 | 16.2% | 6.1% | 1.318 | 10.081 | 8.090 | 16.407 | 327 |
| M9a Ind-LODES | 4.715 | 17.5% | 5.2% | 1.919 | 10.341 | 8.122 | 16.407 | 325 |
| M3c-IND | 4.715 | 17.5% | 5.2% | 1.919 | 10.341 | 8.122 | 16.407 | 325 |
| M2c-Multi | 5.003 | 18.3% | 4.1% | 2.429 | 10.440 | 8.091 | 17.783 | 345 |
| M2c-V5 (3-layer) | 5.021 | 18.3% | 4.3% | 2.435 | 10.560 | 8.082 | 17.786 | 345 |
| Expert-A | 5.304 | 16.0% | 5.2% | 1.888 | 10.618 | 8.122 | 16.407 | 325 |
| Expert-B | 4.882 | 19.1% | 4.6% | 1.951 | 10.624 | 7.972 | 19.083 | 345 |
| M9c Combined | 4.755 | 20.0% | 5.2% | 1.896 | 10.870 | 8.122 | 16.407 | 325 |
| V6-Full | 4.755 | 20.0% | 5.2% | 1.896 | 10.870 | 8.193 | 13.774 | 325 |
| M1b-QCEW | 4.826 | 19.4% | 5.5% | 2.039 | 10.944 | 8.594 | 17.757 | 345 |
| M2c-Metro | 5.413 | 18.3% | 5.5% | 2.745 | 11.405 | 8.473 | 17.933 | 345 |

---

## Ablation Analysis

### Experiment A: Industry-LODES (M9a vs M3c-V5)
- Race MAE: 4.372 -> 4.715 (delta: +0.343 pp)

### Experiment B: QCEW Adaptive (M9b vs M3c-V5)
- Race MAE: 4.372 -> 4.384 (delta: +0.012 pp)

### Experiment C: Combined (M9c vs M3c-V5)
- Race MAE: 4.372 -> 4.755 (delta: +0.383 pp)

### Experiment D: Multi-Tract (M2c-Multi vs M2c-V5)
- Race MAE: 5.021 -> 5.003 (delta: -0.018 pp)

### Experiment E: Metro ACS (M2c-Metro vs M2c-V5)
- Race MAE: 5.021 -> 5.413 (delta: +0.392 pp)

### Experiment F: V6-Full vs M3c-V5
- Race MAE: 4.372 -> 4.755 (delta: +0.383 pp)

### Experiment G: Occupation-Weighted Gender (G1 vs V5 gender)
- Gender MAE: 16.407 -> 13.774 (delta: -2.633 pp)

### Experiment H: Geography-Heavy Hispanic (H1 vs V5 hispanic)
- Hispanic MAE: 8.122 -> 8.193 (delta: +0.071 pp)

---

## V6 Target Check

- [ ] Race MAE < 4.50 pp: actual=4.755, target=4.500
- [ ] P>20pp < 16%%: actual=20.000, target=16.000
- [x] P>30pp < 6%%: actual=5.230, target=6.000
- [ ] Abs Bias < 1.10: actual=1.896, target=1.100
- [ ] Hispanic MAE < 8.00 pp: actual=8.193, target=8.000
- [ ] Gender MAE < 12.00 pp: actual=13.774, target=12.000
