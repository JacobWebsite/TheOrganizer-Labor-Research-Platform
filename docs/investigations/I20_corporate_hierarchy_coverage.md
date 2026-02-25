# I20 - Corporate Hierarchy (Factor 1) Coverage

Generated: 2026-02-24 19:05

## Summary

**3,317** / **146,863** F7 employers (2.3%) have a `corporate_family_id`. The corporate identifier crosswalk contains **26,705** entries spanning **5,764** distinct corporate families.

## Corporate Family Coverage

| Metric | Value |
|--------|------:|
| Total F7 employers (in mv_employer_data_sources) | 146,863 |
| With corporate_family_id | 3,317 |
| Without corporate_family_id | 143,546 |
| Coverage rate | 2.3% |

## Crosswalk Statistics

| Metric | Value |
|--------|------:|
| Total crosswalk entries | 26,705 |
| Distinct employers | 18,808 |
| Distinct corporate families | 5,764 |
| Avg entries per family | 4.6 |

## Corporate Hierarchy

*`corporate_hierarchy` table does not exist.* Error: `column "parent_id" does not exist
LINE 3:                        COUNT(DISTINCT parent_id) AS distinct...
                                              ^
HINT:  Perhaps you meant to reference the column "corporate_hierarchy.parent_cik".
`

## Score Union Proximity Distribution

The `score_union_proximity` factor from `mv_unified_scorecard` uses canonical group size and corporate family membership:

| Score Value | Count | % |
|------------|------:|--:|
| 10 (group >= 3) | 50,872 | 34.6% |
| 5 (group = 2 or corp family) | 16,308 | 11.1% |
| 0 (no group, no corp) | 0 | 0.0% |
| NULL | 79,683 | 54.3% |

## Canonical Group vs Corporate Family Overlap

| Category | Count | % |
|----------|------:|--:|
| Both canonical_group_id AND corporate_family_id | 1,327 | 0.9% |
| canonical_group_id only | 63,863 | 43.5% |
| corporate_family_id only | 1,990 | 1.4% |
| Neither | 79,683 | 54.3% |

## How Factor 1 (score_union_proximity) Actually Works

From `build_unified_scorecard.py`, the SQL formula is:

```sql
CASE
    WHEN up.member_count IS NULL AND eds.corporate_family_id IS NULL THEN NULL
    WHEN GREATEST(COALESCE(up.member_count, 1) - 1, 0) >= 2 THEN 10
    WHEN GREATEST(COALESCE(up.member_count, 1) - 1, 0) = 1
         OR eds.corporate_family_id IS NOT NULL THEN 5
    ELSE 0
END AS score_union_proximity
```

Logic breakdown:

- **Score 10**: Employer is in a canonical group with 3+ members (i.e., `member_count - 1 >= 2`, meaning at least 2 other union-represented locations).
- **Score 5**: Employer is in a canonical group with exactly 2 members (1 peer), OR has a `corporate_family_id` (identified as part of a corporate family via SEC/GLEIF/CorpWatch data).
- **Score 0**: Employer has a canonical group or corporate family entry but no peers.
- **NULL**: No canonical group data and no corporate family data.

## Implications

- **Low corporate coverage (2.3%)**: The corporate_family_id data covers fewer than 5% of employers. This means the corporate hierarchy contributes minimally to score_union_proximity for most employers. Consider reducing the weight of the corporate component or investing in additional corporate data enrichment (e.g., more CorpWatch/SEC/GLEIF matching).
- Employers with `corp_only` (corporate family but no canonical group) receive score_union_proximity = 5 solely from the corporate crosswalk. This is a binary boost, not a graduated signal.
- The NULL population receives no proximity score at all, which means the weighted average excludes this factor for them (reducing their factors_available count).
- If the canonical grouping pipeline already covers most multi-location employers, the marginal value of corporate hierarchy is limited to single-location employers that happen to be subsidiaries.
