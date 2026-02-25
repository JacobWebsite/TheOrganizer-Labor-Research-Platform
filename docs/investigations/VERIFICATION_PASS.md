# Verification Pass: Completed Investigations

Generated: 2026-02-24 19:05:24

## Summary

- **5** of **11** checks passed (OK)
- **5** stale (delta > 5%)
- **1** errors

## Verification Results

| # | Investigation | Metric | Original | Current | Delta | Status |
|--:|:-------------|:-------|:---------|:--------|:------|:-------|
| 1 | I1 | Proximity uses only groups+corp (should be 0) | 0 | 0 | 0.0% | OK |
| 2 | I3 | Active dangling UML (target not in f7) | 1 | 0 | 100.0% | **STALE** |
| 3 | I4 | Generic placeholder names | 6 | 4 | 33.3% | **STALE** |
| 4 | I4 | Very short names (<=2 alnum chars) | 31 | 31 | 0.0% | OK |
| 5 | I6 | Membership overcounting (v_union_members_deduplicated SUM) | 71,950,779 | N/A | - | **ERROR** |
| 6 | I7 | Superseded UML matches | 538,011 | 626,888 | 16.5% | **STALE** |
| 7 | I8 | Large employer groups (>50 members) | 51 | 40 | 21.6% | **STALE** |
| 8 | I10 | Multi-employer agreements (is_multi_employer or name pattern) | 3,039 | 44 | 98.6% | **STALE** |
| 9 | I13 | is_labor_org flagged | 1,843 | 1,843 | 0.0% | OK |
| 10 | BASELINE | Total F7 employers | 146,863 | 146,863 | 0.0% | OK |
| 11 | BASELINE | Total active UML matches | 135,430 | 128,870 | 4.8% | OK |

## Stale Checks (delta > 5%)

### I3 - Active dangling UML (target not in f7)

- Original value: 1
- Current value: 0
- Delta: 100.0%
- **Action:** Investigate whether this change is expected (data reload, pipeline re-run) or indicates a regression.

### I4 - Generic placeholder names

- Original value: 6
- Current value: 4
- Delta: 33.3%
- **Action:** Investigate whether this change is expected (data reload, pipeline re-run) or indicates a regression.

### I7 - Superseded UML matches

- Original value: 538,011
- Current value: 626,888
- Delta: 16.5%
- **Action:** Investigate whether this change is expected (data reload, pipeline re-run) or indicates a regression.

### I8 - Large employer groups (>50 members)

- Original value: 51
- Current value: 40
- Delta: 21.6%
- **Action:** Investigate whether this change is expected (data reload, pipeline re-run) or indicates a regression.

### I10 - Multi-employer agreements (is_multi_employer or name pattern)

- Original value: 3,039
- Current value: 44
- Delta: 98.6%
- Note: name pattern fallback (building trades only)
- **Action:** Investigate whether this change is expected (data reload, pipeline re-run) or indicates a regression.


## Errors

### I6 - Membership overcounting (v_union_members_deduplicated SUM)

- Error: `column "members_2024" does not exist
LINE 2:             SELECT SUM(members_2024) AS total
                               ^
`
- **Action:** Check whether the table/view/column still exists or was renamed.

