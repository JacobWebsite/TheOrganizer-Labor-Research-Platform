# Membership Deduplication Analysis & Plan
## January 23, 2026

---

## Executive Summary

The OLMS LM filing data reports **70.1 million members** for 2024, but actual US union membership is approximately **14.3 million** (per BLS). This ~5x over-count is caused by:

1. **Federation aggregation**: AFL-CIO reports 13.4M members who are already counted by their constituent unions
2. **National/Local double-counting**: National headquarters report total membership, while locals report the same members individually
3. **Intermediate body aggregation**: Joint councils, district councils aggregate their locals' members
4. **Specialized unit duplication**: LEADC, SA, BCTC units often represent the same workers

---

## Key Findings

### 1. Organization Type Distribution (2024)

| Type | Count | Reported Members | Notes |
|------|-------|------------------|-------|
| National HQ | 144 | 37.2M | Aggregates - EXCLUDE |
| Local Union (LU) | 13,795 | 16.9M | Primary count source |
| Chapter/Association | 511 | 4.8M | Mixed - analyze by affiliation |
| Specialized Unit | 909 | 4.7M | Often duplicates |
| Joint/District Council | 185 | 2.0M | Aggregates - EXCLUDE |
| Conference/State | 132 | 1.0M | Aggregates - EXCLUDE |
| Branch | 2,096 | 0.6M | May be leaf level |
| Division | 716 | 0.3M | May be leaf level |
| No Designation | 743 | 0.8M | Analyze by size |

### 2. Major Double-Counting Sources

#### AFL-CIO Federation (f_num 106)
- Reports: 13.4M members
- Reality: These are members of constituent unions (SEIU, IBT, UFCW, etc.)
- Action: **EXCLUDE** - members counted elsewhere

#### Teacher Unions (AFT + NEA)
- AFT Total reported: 7.3M
  - AFT NHQ: 1.8M
  - AFT Locals: 5.2M (duplicates of NHQ)
- Actual AFT membership: ~1.7M
- NEA NHQ: 2.8M (actual NEA membership: ~3M)
- Action: **Count NHQ only** for teacher unions (different structure)

#### Teamsters (IBT)
- Total reported: 3.6M
- National HQ: 1.25M
- Joint Councils: 1.2M (aggregates)
- Locals (LU): 1.2M
- Actual IBT membership: ~1.3M
- Action: **Count LU only**

#### SEIU
- Total reported: 4.9M
- National HQ: 1.9M
- LEADC units: 990K
- Locals (LU): 1.7M
- Actual SEIU membership: ~2M
- Action: **Count LU only**

### 3. Deduplication Strategy by Union Type

| Union Type | Counting Rule | Rationale |
|------------|---------------|-----------|
| Traditional (IBT, UFCW, IBEW, etc.) | Count LU/LG only | Clear local structure |
| Teacher (AFT, NEA) | Count NHQ only | Locals report to NHQ, not direct members |
| Carpenters (CJA) | Count LU only | Regional councils aggregate |
| Entertainment (IATSE) | Count LU only | Clear local structure |
| Railroad/Airline (RLA) | Count DIV/LG | Different structure under Railway Labor Act |
| Independent (UNAFF) | Count if <10K members | Large independents may be aggregates |
| Federations (AFLCIO, SOC, TTD) | Exclude all | Pure aggregates |

---

## Proposed Database Schema Enhancement

### New Table: `union_organization_level`

```sql
CREATE TABLE union_organization_level (
    f_num VARCHAR(20) PRIMARY KEY,
    org_level VARCHAR(20) NOT NULL,  -- 'federation', 'national', 'intermediate', 'local'
    is_leaf_level BOOLEAN,           -- TRUE if members should be counted
    parent_f_num VARCHAR(20),        -- Parent organization if known
    dedup_category VARCHAR(30),      -- Classification for dedup logic
    members_adjusted INTEGER,        -- Deduplicated member count
    notes TEXT
);
```

### New Table: `union_parent_child`

```sql
CREATE TABLE union_parent_child (
    parent_f_num VARCHAR(20),
    child_f_num VARCHAR(20),
    relationship_type VARCHAR(30),  -- 'national-local', 'council-local', etc.
    PRIMARY KEY (parent_f_num, child_f_num)
);
```

### New View: `v_deduplicated_membership`

```sql
CREATE VIEW v_deduplicated_membership AS
SELECT 
    l.f_num,
    l.union_name,
    l.aff_abbr,
    ol.org_level,
    ol.is_leaf_level,
    CASE WHEN ol.is_leaf_level THEN l.members ELSE 0 END as counted_members,
    l.members as reported_members
FROM lm_data l
LEFT JOIN union_organization_level ol ON l.f_num = ol.f_num
WHERE l.yr_covered = 2024;
```

---

## Implementation Plan

### Phase 1: Classification (This session)
1. ✅ Analyze organization types by desig_name
2. ✅ Identify federation, national, intermediate, local patterns
3. ✅ Develop classification rules by affiliation

### Phase 2: Schema & Rules
1. Create `union_organization_level` table
2. Populate with classification rules based on:
   - `desig_name` patterns
   - Affiliation-specific logic
   - Size thresholds
3. Create parent-child relationship table

### Phase 3: Validation
1. Compare deduplicated totals to BLS data
2. Analyze by affiliation to spot remaining duplicates
3. Refine rules iteratively

### Phase 4: Integration
1. Add `is_leaf_level` flag to `unions_master`
2. Create deduplicated views for analysis
3. Update F-7 linkage to use deduplicated counts

---

## Expected Outcome

| Metric | Current | Target |
|--------|---------|--------|
| Total reported | 70.1M | 70.1M (unchanged) |
| Deduplicated count | N/A | ~14-15M |
| Variance from BLS | 5x over | <10% variance |

---

## Next Steps

1. **Create classification table** with org_level for each f_num
2. **Build parent-child relationships** where identifiable
3. **Validate against BLS** state-level data
4. **Document edge cases** for manual review
