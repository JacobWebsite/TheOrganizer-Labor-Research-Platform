# I19 - Mel-Ro Construction OSHA Match Spot Check

Generated: 2026-02-24 19:05:06

## Summary

Investigated **Mel-Ro Construction** (`6c5fec90faef51ae`) which has **12** active OSHA matches in `unified_match_log`.

- Sampled **12** matches for spot-check
- Estimated false-positive rate: **100.0%** (12/12 SUSPECT)

## Target Employer Details

| Field | Value |
| --- | --- |
| employer_id | `6c5fec90faef51ae` |
| employer_name | Mel-Ro Construction |
| city | Colorado Springs |
| state | CO |
| naics | 23 |
| latest_unit_size | 20 |

### Other Mel-Ro matches in f7_employers_deduped

| employer_id | employer_name | city | state |
| --- | --- | --- | --- |
| 58b8c558e7ee83ee | Allied Waste Services d/b/a Republic Services of Melrose Park | Melrose Park | IL |
| b992dc87dc0a2f61 | Allied Waste Services of North America, LLC d/b/a Allied Waste Services of Melrose Park | Melrose Park | IL |
| 767cca78f20f5623 | Maywood/Melrose Park Sch. Dis.#89 Clerical Unit  | Melrose Park  | IL |
| 14d4bd25b9ccf125 | Maywood/Melrose Park School District #89 | Melrose Park  | IL |
| 6c5fec90faef51ae | Mel-Ro Construction | Colorado Springs | CO |
| 9a96a050576e176e | Melrose-Wakefield Hospital | Melrose | MA |
| 8205ccb6db13afb3 | Melrose Area Hospital and Pine Villa Care Center | Melrose | MN |
| b1eeac2188ae25e3 | Melrose Lumber, Co. Inc. | Ossining | NY |
| 4b5e186e10450370 | Melrose Wakefield Hospital | Melrose | MA |
| b865793f21bfb025 | MelroseWakefield Hospital | Boston | MA |
| be2e1e213b2eda8b | MelroseWakefield Hospital | Melrose | MA |
| 6ac39dce9aff84f4 | Navistar Inc International Truck & Engine Corp Melrose Park Engine Plant | Melrose Park | IL |
| c555a73aec4be17f | Republic-Allied Waste - Melrose Park | None | None |
| 49c90b21c3ef1f5d | Republic Services d/b/a Republic Services of Melrose Park | Melrose Park | IL |

## Total OSHA Match Count

**12** active OSHA matches for this employer.

## Match Method Distribution

| Match Method | Count | Pct |
| --- | --- | --- |
| FUZZY_SPLINK_ADAPTIVE | 12 | 100.0% |

## Spot Check Sample

Random sample of 12 matches (seed=42):

| F7_Name | OSHA_Name | City_Match | State_Match | Method | Confidence | Category |
| --- | --- | --- | --- | --- | --- | --- |
| Mel-Ro Construction | TREJO'S CONSTRUCTION | Yes | Yes | FUZZY_SPLINK_ADAPTIVE | 0.998 | SUSPECT |
| Mel-Ro Construction | JROD CONSTRUCTION | Yes | Yes | FUZZY_SPLINK_ADAPTIVE | 0.998 | SUSPECT |
| Mel-Ro Construction | J&E PRO CONSTRUCTION LLC | Yes | Yes | FUZZY_SPLINK_ADAPTIVE | 0.998 | SUSPECT |
| Mel-Ro Construction | ROSTRO CONSTRUCTION LLC | Yes | Yes | FUZZY_SPLINK_ADAPTIVE | 0.993 | SUSPECT |
| Mel-Ro Construction | ROSTRO CONSTRUCTION LLC | Yes | Yes | FUZZY_SPLINK_ADAPTIVE | 0.993 | SUSPECT |
| Mel-Ro Construction | LA & SONS CONSTRUCTION | Yes | Yes | FUZZY_SPLINK_ADAPTIVE | 0.992 | SUSPECT |
| Mel-Ro Construction | MERINO CONSTRUCTION | Yes | Yes | FUZZY_SPLINK_ADAPTIVE | 0.895 | SUSPECT |
| Mel-Ro Construction | MELGOZA CONSTRUCTION | No | Yes | FUZZY_SPLINK_ADAPTIVE | 0.872 | SUSPECT |
| Mel-Ro Construction | ROMA CONSTRUCTION LLC | Yes | Yes | FUZZY_SPLINK_ADAPTIVE | 0.850 | SUSPECT |
| Mel-Ro Construction | LA & SONS CONSTRUCTION | Yes | Yes | FUZZY_SPLINK_ADAPTIVE | 0.821 | SUSPECT |
| Mel-Ro Construction | MELARA CONSTRUCTION LLC | No | Yes | FUZZY_SPLINK_ADAPTIVE | 0.810 | SUSPECT |
| Mel-Ro Construction | JLV CONSTRUCTION | Yes | Yes | FUZZY_SPLINK_ADAPTIVE | 0.800 | SUSPECT |

## Category Summary

| Category | Count | Pct |
| --- | --- | --- |
| TRUE_MATCH | 0 | 0.0% |
| PLAUSIBLE | 0 | 0.0% |
| SUSPECT | 12 | 100.0% |

## False Positive Rate Estimate

Based on the 12-match sample:

- **SUSPECT** matches: 12 (100.0%)
- **PLAUSIBLE** matches: 0
- **TRUE_MATCH** matches: 0

Extrapolating to all 12 matches: ~**12** may be false positives.

## Implications

**High false-positive rate detected.** Many-to-one matching inflation is a significant concern for this employer. Consider:

- Reviewing SUSPECT matches for manual rejection
- Adding name-similarity floor to OSHA matching for high-volume targets
- Investigating whether multiple OSHA establishments are genuinely linked to this employer (multi-site operations)
- Cross-referencing with NAICS codes to validate industry alignment
