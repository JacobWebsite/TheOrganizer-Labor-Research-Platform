# Investigation I8: Employer Grouping Problem

## Objective
Review employer groups with >50 members to quantify the extent of over-merging (generic names) and under-merging (fragmented large employers).

## Findings

### 1. Over-Merging (Generic Name Collisions)
Several groups consist of hundreds of members that are likely unrelated entities sharing a common or generic name.

| Group ID | Canonical Name | Members | State | Issue |
|----------|----------------|---------|-------|-------|
| 7617     | D. CONSTRUCTION, INC. | 249 | IL | Likely many unrelated "D." initials |
| 1446     | Building Service, Inc. | 164 | None | Generic name |
| 16039    | Construction Co. | 140 | None | Extremely generic |
| 72       | National Equipment Corp.| 137 | None | Generic |

### 2. Under-Merging (Fragmented Large Employers)
Large national employers are often fragmented into dozens of groups due to state-level grouping or slight naming variations.

**Example: Healthcare Services Group**
This entity is split into at least 7 major groups (and likely many smaller ones):
- Group 4350: 167 members (CA)
- Group 6480: 165 members (CA)
- Group 3930: 119 members (PA)
- Group 11465: 94 members (IL)
- Group 2540: 75 members (MN)
- Group 14297: 66 members (NJ)
- Group 11044: 51 members (MI)
*Total across these groups: 737 members*

**Example: Aramark / First Student / MV Transportation**
These also show similar fragmentation across states (e.g., First Student has groups in CT and IL).

### 3. Summary of Group Sizes
| Group Size | Count |
|------------|-------|
| 50+ members| 51    |
| 10-49 members| 711 |
| 5-9 members | 2,289 |
| 2-4 members | 13,730|

## Recommendations

1.  **Stricter Generic Name Handling:** For names like "Construction Co." or "Building Service", require a city-level match for grouping, not just state or national.
2.  **Cross-State Merging for Major Brands:** Implement a "Brand Resolver" that merges known national entities (Starbucks, Aramark, Healthcare Services Group) across states regardless of minor suffix variations.
3.  **Normalizer Improvements:** Address double-spaces and "dba" variations that prevent clean matching.
4.  **Manual Group Fixes:** Use a manual override table to break the top 10 false groups and merge the top 10 fragmented entities.
