# Gate v0 Evaluation Report

## Summary

- Holdout: 200 companies (selected_holdout_v3.json)
- Gate v0 CV accuracy: 0.398

## Results

| Method | Composite | Race MAE | P>20pp | P>30pp | Abs Bias |
|--------|-----------|----------|--------|--------|----------|
| Gate v0 | 10.444 | 4.349 | 16.50% | 7.50% | 1.134 |
| M8 (V4) | 9.254 | 3.737 | 15.00% | 6.50% | 1.608 |
| M3b | 10.444 | 4.349 | 16.50% | 7.50% | 1.134 |

## Decision

**RETAIN M8 (Gate v0 not better)**

## Gate v0 Routing

- M3b Damp-IPF: 200 companies
