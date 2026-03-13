# Session 2026-03-08: Demographics Methodology Comparison Framework

## Task
Built a complete framework to compare 6 workforce demographics estimation methods against EEO-1 ground truth (16,798 federal contractors, FY2016-2020).

## Files Created
All in `scripts/analysis/demographics_comparison/`:
- `__init__.py`
- `config.py` -- 10 validation companies, industry weight tables, category constants
- `eeo1_parser.py` -- parses EEO-1 CSV (cp1252 encoding) into ground truth dicts
- `select_companies.py` -- scans EEO-1, filters to 2,163 valid candidates, groups by 7 benchmark axes
- `data_loaders.py` -- SQL queries: ACS (non-Hispanic race), LODES county, tract, BLS occ matrix, with NAICS fallback cascade
- `methodologies.py` -- 6 methods: baseline 60/40, three-layer 50/30/20, IPF, occ-weighted, variable-weight, IPF+occ
- `metrics.py` -- MAE, RMSE, Hellinger distance, max absolute error, signed errors
- `bds_hc_check.py` -- BDS-HC plausibility checker (sector x size x bucket)
- `run_comparison.py` -- main runner: loads truth, runs all methods, prints summary + CSV

## 10 Validation Companies Selected
| Company | State | NAICS | N | Axis |
|---------|-------|-------|---|------|
| CARE INITIATIVES | IA | 623110 | 2,958 | 1 (nursing home) |
| UNITED LAUNCH ALLIANCE | CO | 336414 | 2,645 | 1 (aerospace) |
| BUTTERBALL LLC | NC | 311615 | 7,125 | 2 (poultry) |
| OSI INDUSTRIES LLC | IL | 311612 | 7,159 | 2 (meat processing) |
| ESA MANAGEMENT LLC | NC | 721110 | 8,120 | 3 (hotel chain) |
| TYSON FOODS INC | AR | 311615 | 121,310 | 4 (size extreme large) |
| PRISM HOTEL PARTNERS GP | TX | 721110 | 1,059 | 4 (size extreme small) |
| ALEXANDER & BALDWIN INC | HI | 531210 | 648 | 5 (majority-minority HI) |
| HOWROYD WRIGHT EMPLOYMENT AGENCY | CA | 561311 | 8,980 | 6 (staffing, hard case) |
| DUCOMMUN INCORPORATED | CA | 336413 | 2,462 | 1 (aerospace parts) |

## Results Summary
| Method | Avg Race MAE | Avg Hellinger | Race Wins | Gender Wins |
|--------|-------------|---------------|-----------|-------------|
| **M1 Baseline (60/40)** | **6.8** | **0.206** | 3 | 0 |
| M4 Occ-Weighted | 7.0 | 0.213 | 3 | 2 |
| M5 Variable-Weight | 7.2 | 0.208 | 1 | 0 |
| M2 Three-Layer | 7.2 | 0.216 | 3 | 2 |
| M3 IPF | 11.1 | 0.337 | 0 | 6 |
| M6 IPF+Occ | 11.1 | 0.337 | 0 | 0 |

## Key Findings
1. **M1 Baseline wins race estimation** (avg MAE 6.8). Simple 60/40 ACS/LODES blend is hard to beat.
2. **IPF (M3/M6) worst for race** -- normalized product amplifies majority (White) by avg +30pp. But IPF is *best for gender* (wins 6/10) because multiplicative correction narrows the estimate.
3. **Systematic White overestimation across ALL methods** (~10pp avg). ACS + LODES data sources have structural White bias relative to EEO-1 ground truth.
4. **Systematic Black underestimation** (~10pp avg). Corollary of White overestimation.
5. **OSI Industries hardest case** -- 60% Black workforce, best MAE=13.7. Its workforce radically differs from both industry and county averages.
6. **Alexander & Baldwin (HI) exposes NHOPI gap** -- IPUMS doesn't separate NHOPI from Asian. All methods underestimate NHOPI by ~33pp.
7. **Staffing agency (Howroyd Wright)** performed as expected hard case -- ~20pp gender error.
8. **BDS-HC plausibility check** mostly N/A for manufacturing (suppressed data). Hotels/staffing fall outside modal bucket -- confirms genuinely diverse workplaces vs sector norms.

## Design Decisions
- Hispanic compared as **separate dimension** (ACS cross-cutting vs EEO-1 mutually exclusive)
- ACS race queries filter `hispanic='0'` for non-Hispanic race alignment with EEO-1
- IPUMS doesn't separate NHOPI from Asian -- NHOPI=0 for ACS sources
- EEO-1 CSV uses cp1252 encoding (not UTF-8)
- BDS-HC files have suppressed values marked 'D' or 'S' -- must handle as 0

## Gotchas Discovered
- EEO-1 CSV encoding is cp1252, not UTF-8
- BDS-HC has suppressed values ('D', 'S') that break int() parsing
- LODES `pct_minority` stores values as 0-1 proportion, not 0-100 percentage
- BDS `ifsizecoarse` bucket labels include full text ("a) 1 to 19", not just "a")

## Next Steps
- Consider hybrid method: M1 for race, M3 for gender
- Investigate White overestimation bias -- may need ACS non-Hispanic race filtering refinement
- Add more companies to validation set (especially diverse workplaces)
- Wire winning method into production API (`api/routers/profile.py`)
- Task 4-9 (research benchmark) could reference this comparison framework
