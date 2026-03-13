# V6 Final Validation Report

**Holdout:** selected_permanent_holdout_1000.json
**Companies:** 992 processed, 0 skipped
**Runtime:** 307.2s

---

## Results

| Method | Race MAE | P>20pp | P>30pp | Abs Bias | Hisp MAE | Gender MAE | N |
|--------|---------|--------|--------|----------|----------|------------|---|
| V5 M3c (baseline) | 4.856 | 19.9% | 8.6% | 0.902 | 8.614 | 13.865 | 954 |
| V6 Pipeline | 4.526 | 16.1% | 7.9% | 0.536 | 7.111 | 11.779 | 992 |

## Confidence Tiers

- **GREEN:** 296 (29.6%)
- **YELLOW:** 682 (68.2%)
- **RED:** 22 (2.2%)

## Expert Routing

- A: 162 companies
- B: 181 companies
- D: 174 companies
- E: 278 companies
- F: 79 companies
- G: 14 companies
- V6: 112 companies

## Per-Industry-Group Race MAE

| Industry Group | Race MAE |
|---------------|---------|
| Finance/Insurance (52) | 2.861 |
| Utilities (22) | 3.043 |
| Retail Trade (44-45) | 3.763 |
| Metal/Machinery Mfg (331-333) | 3.918 |
| Wholesale Trade (42) | 3.976 |
| Professional/Technical (54) | 4.151 |
| Transport Equip Mfg (336) | 4.158 |
| Other Manufacturing | 4.300 |
| Information (51) | 4.364 |
| Chemical/Material Mfg (325-327) | 4.386 |
| Computer/Electrical Mfg (334-335) | 4.481 |
| Transportation/Warehousing (48-49) | 4.912 |
| Agriculture/Mining (11,21) | 5.079 |
| Construction (23) | 5.247 |
| Healthcare/Social (62) | 5.469 |
| Other | 5.586 |
| Accommodation/Food Svc (72) | 5.701 |
| Food/Bev Manufacturing (311,312) | 5.851 |
| Admin/Staffing (56) | 5.872 |

## Acceptance Criteria

- [ ] Race MAE < 4.50 pp: actual=4.526, target=4.500
- [ ] P>20pp < 16%%: actual=16.130, target=16.000
- [ ] P>30pp < 6%%: actual=7.860, target=6.000
- [x] Abs Bias < 1.10: actual=0.536, target=1.100
- [x] Hispanic MAE < 8.00 pp: actual=7.111, target=8.000
- [x] Gender MAE < 12.00 pp: actual=11.779, target=12.000
- [x] Red flag rate < 15%%: actual=2.200, target=15.000

**Result: 4/7 criteria passed**