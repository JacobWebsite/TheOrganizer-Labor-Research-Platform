# Investigation I6: Membership View (v_union_members_deduplicated)

## Objective
Investigate why `v_union_members_deduplicated` produces 72M rows (summed members) instead of the BLS-reported 14.5M, and determine if it should be fixed or dropped.

## Findings

### 1. Root Cause of Overcounting
The view `v_union_members_deduplicated` is a simple join between `union_hierarchy`, `unions_master`, and `lm_data`. The overcounting (71.9M total members) is caused by summing membership across all levels of the union hierarchy (Federations, Internationals, and Locals) without filtering for a single "primary" level.

| hierarchy_level | Count | SUM(members_2024) |
|-----------------|-------|-------------------|
| INTERMEDIATE    | 3     | 89,102            |
| INTERNATIONAL   | 1,399 | 17,085,830        |
| FEDERATION      | 386   | 32,100,901        |
| LOCAL           | 24,877| 22,674,946        |
| **TOTAL**       | **26,665** | **71,950,779**    |

### 2. Breakdown by Count Reason
The `union_hierarchy` table includes a `count_reason` column that explains whether a record is a "primary count level" or has been "already counted" at another level.

**Primary Count Levels (Sum = 13,447,347):**
These are mostly International/National unions. Summing these alone gets very close to the BLS 14.5M total.

**Significant Non-Primary Levels (Double Counting):**
- `Federation - aggregates other unions`: 30.3M (e.g., AFL-CIO)
- `Local - members counted at international level`: 14.6M
- `Independent local - no international`: 1.06M (Should likely be included in primary)
- `DATA QUALITY: Reports 3.6M but actual membership ~22K`: 3.6M (Outlier)

### 3. State-Level Reliability Issue
Because the "Primary Count Level" is usually the International Union, state-level membership becomes wildly distorted (DC has 141,000% of its BLS-reported membership because many Internationals are headquartered there).

To get accurate state-level data, the platform must use Local-level membership, but 8,770 locals (representing 14.6M members) are marked as "members counted at international level" and may have NULL or unreliable membership numbers in their own rows, or they are correctly reported but would double-count if the International is also included.

## Recommendations

### Option A: Fix the View (Recommended)
Update the view to only include "Primary" records. This will fix the national total but will NOT fix the state-level distortion.

**Query logic:**
```sql
SELECT ...
FROM union_hierarchy h
WHERE (count_reason ILIKE '%primary count level%' 
   OR count_reason = 'Independent local - no international')
  AND count_reason NOT ILIKE '%DATA QUALITY%'
```

### Option B: Create a State-Allocated View
For state-level analysis, we should use a view that sums only `LOCAL` and `INTERMEDIATE` records, even if it slightly undercounts compared to the International total, as it will be geographically more accurate.

### Conclusion
The view is "fundamentally broken" because it lacks a filter on the hierarchy level. It should be updated to use the `count_reason` logic or dropped in favor of explicit queries that choose a hierarchy level based on the use case (National vs. State).
