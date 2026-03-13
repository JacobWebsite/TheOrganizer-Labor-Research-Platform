# Demographics Comparison: 10-Company Baseline + 200-Company Scale-Up

## Date: 2026-03-08

## What Was Done

### Phase 1: 10-Company Comparison (existing)
- 6 methods tested against EEO-1 ground truth for 10 hand-picked companies
- M1 Baseline (60/40 ACS/LODES) won on race MAE (6.8)
- IPF best for gender but worst for race (+30pp White bias)
- All methods showed systematic White overestimation and Black underestimation

### Phase 2: 200-Company Scale-Up (this session)
Created 4 new files in `scripts/analysis/demographics_comparison/`:
- `classifiers.py` -- 5D classification (NAICS group, size, region, minority share, urbanicity)
- `select_200.py` -- stratified sampling from 2,444 eligible EEO-1 companies
- `cached_loaders.py` -- dict-cached data loaders (84.3% hit rate, 3.9s runtime)
- `run_comparison_200.py` -- main runner with dimensional bucketing + bias analysis

### Phase 3: Comprehensive Documentation
- Created `docs/DEMOGRAPHICS_METHODOLOGY_COMPARISON.md` -- full methodology, results, bias analysis, recommendations

## Key Results (200 companies)

### Overall
| Method | Race MAE | Hellinger | Race Wins | Gender Wins |
|--------|----------|-----------|-----------|-------------|
| M1 Baseline (60/40) | **5.74** | **0.192** | 35 | 5 |
| M2 Three-Layer | 5.95 | 0.199 | 59 | 46 |
| M3 IPF | 7.13 | 0.246 | **70** | **113** |
| M4 Occ-Weighted | 5.92 | 0.200 | 16 | 20 |
| M5 Variable-Weight | 5.99 | 0.201 | 20 | 16 |
| M6 IPF+Occ | 7.13 | 0.246 | 0 | 0 |

### Critical Findings
1. **Minority share is the strongest moderator**: Low (<25%) MAE=3.1-4.0, High (>50%) MAE=12.7-17.9
2. **Bias flips by minority share**: High-minority = +26pp White overestimate; Low-minority = -9pp White underestimate
3. **M3 IPF dominates rural + low-minority** (MAE 1.6, wins 21/25) but catastrophic for diverse companies (+48pp White bias)
4. **M6 identical to M3** -- eliminate M6
5. **Regional gradient**: Midwest 3.4 < Northeast 4.8 < South 6.5 < West 8.3
6. **Asian systematically underestimated** by all methods (-3.7 to -7.8pp)
7. **Two+ overestimated** by blend methods (+5.3 to +6.6pp) -- IPUMS coding artifact

### Production Recommendation
- Default: M1 Baseline (60/40)
- Override: M3 IPF for rural + low-minority counties (configurable flag)
- Eliminate: M6 IPF+Occ

## Output Files
- `scripts/analysis/demographics_comparison/selected_200.json` (200 companies)
- `scripts/analysis/demographics_comparison/comparison_200_detailed.csv` (3,600 rows)
- `scripts/analysis/demographics_comparison/comparison_200_summary.csv` (192 rows)
- `docs/DEMOGRAPHICS_METHODOLOGY_COMPARISON.md` (full write-up)
