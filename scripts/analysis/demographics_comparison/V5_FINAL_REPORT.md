# V5 Final Validation Report

Date: 2026-03-09

## Summary

- Fresh holdout: 208 companies
- Skipped: 0
- Gate v1 CV accuracy: 0.598

## Results

| Method | Composite | Race MAE | P>20pp | P>30pp | Abs Bias | Hisp MAE | Gend MAE |
|--------|-----------|----------|--------|--------|----------|----------|----------|
| M3b (baseline) | 12.497 | 5.234 | 19.81% | 8.70% | 1.722 | 9.309 | 18.572 |
| M8 (V4) | 14.393 | 5.312 | 25.24% | 10.48% | 2.449 | 9.296 | 18.572 |
| Expert A | 14.887 | 5.995 | 26.09% | 10.14% | 0.828 | 9.309 | 18.572 |
| Expert B | 13.493 | 5.384 | 23.11% | 9.33% | 1.471 | 9.196 | 20.259 |
| Expert D | 12.497 | 5.234 | 19.81% | 8.70% | 1.722 | 9.309 | 18.572 |
| Gate v1 | 12.379 | 5.182 | 20.67% | 8.17% | 1.345 | 9.252 | 18.098 |

## Gate v1 Routing

- Expert A: 69 companies
- Expert B: 33 companies
- Expert D: 123 companies
- Review flagged: 213/225

## Acceptance Criteria

- [PASS] Race MAE < M3b (5.182 vs 5.234)
- [PASS] P>30pp no worse (0.082 vs 0.087)
- [PASS] Lower bias (1.345 vs 1.722)
- [PASS] Hispanic no worse (9.252 vs 9.309)
- [PASS] Gender no worse (18.098 vs 18.572)

**Overall: ALL PASS**
