# Investigation I7: Orphaned Superseded Matches

## Objective
Investigate the 75,043 (approx.) superseded matches to determine if they were correctly removed or if valuable match evidence was lost.

## Findings

### 1. Quantification
The total number of superseded matches in the `unified_match_log` is **538,011**.
The number **74,686** (closely matching the 75,043 reported in the roadmap) corresponds to the `NAME_STATE_EXACT` match method.

| Match Method | Superseded Count |
|--------------|------------------|
| NAME_STATE_EXACT | 74,686 |
| NAME_CITY_STATE_EXACT | 72,392 |
| EIN_EXACT | 55,767 |
| FUZZY_SPLINK_ADAPTIVE | 178,019 |

### 2. Sample Review
A sample of 20 superseded matches shows:
- **ID 1481996 (OSHA):** Exact name/state match superseded by a newer run.
- **ID 348183-348187 (Town of Cromwell):** Multiple exact name/city/state matches superseded, likely due to a re-run of the matching pipeline for that municipality.
- **Deterministic vs. Fuzzy:** Many exact deterministic matches (NAME_STATE_EXACT) were superseded by `FUZZY_SPLINK_ADAPTIVE` or newer deterministic runs. This is normal as the pipeline evolves.

### 3. "Orphaned" Context
The term "orphaned" in this context likely refers to matches where the target F7 employer was later merged or deleted, or matches that were part of an experimental run (like the 57,129 backfill matches) that were later superseded by a production run.

## Recommendations

1.  **Retention:** Superseded matches should be kept in the log (as they are now) for audit purposes, but they should not be used for scoring.
2.  **Match Chain Audit:** Periodically audit cases where a high-confidence deterministic match was superseded by a lower-confidence fuzzy match to ensure the pipeline isn't degrading.
3.  **Cleanup:** Matches pointing to truly missing targets (only 11 found in current `active` set) should be marked as `orphaned` rather than `active`.
