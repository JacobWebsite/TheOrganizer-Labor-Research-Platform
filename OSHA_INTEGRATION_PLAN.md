# OSHA Data Integration Plan
## Labor Relations Research Platform

**Date:** January 28, 2026  
**Database:** `C:\Users\jakew\Downloads\osha_enforcement.db` (4.5 GB)  
**Data Currency:** Through January 22, 2026 (6 days old)

---

## Executive Summary

The OSHA enforcement database contains **5.15 million inspections** covering **2.65 million unique establishments** with **13.18 million violations** totaling **$7.5 billion in penalties**. This data offers significant integration potential for:
- Identifying non-union employers with safety issues (organizing targets)
- Adding violation history to existing F-7 unionized employers
- Geographic expansion beyond current F-7 coverage
- Industry-specific risk profiling

---

## Database Overview

### Key Tables

| Table | Records | Use Case |
|-------|---------|----------|
| **inspection** | 5,154,531 | Main employer data - names, addresses, NAICS, union status |
| **violation** | 13,184,104 | Violation details - type, penalty, dates |
| **accident** | 165,622 | Accident reports - fatalities, injuries |
| **accident_injury** | 231,628 | Injury details - severity, body part, cause |
| **related_activity** | 2,454,235 | Links between inspections |

### Union Status Field

| Code | Count | Meaning | Value for Platform |
|------|-------|---------|-------------------|
| **Y** | 556,567 | Union workplace | High - validate against F-7 |
| **N** | 1,866,550 | Non-union | High - organizing targets |
| **B** | 1,935,412 | Both/Mixed | Medium - investigate |
| **A** | 631,715 | Unknown/All | Medium - may need research |
| NULL | 164,287 | Missing | Low - incomplete data |

### Violation Types (Priority Order)

| Type | Count | Avg Penalty | Description | Platform Flag |
|------|-------|-------------|-------------|---------------|
| **W** | 53,131 | $13,395 | Willful | ⚠️ CRITICAL |
| **R** | 276,697 | $2,809 | Repeat | 🔴 HIGH |
| **S** | 6,056,744 | $756 | Serious | 🟡 MODERATE |
| **O** | 6,787,407 | $83 | Other | ⚪ LOW |

---

## Integration Value

### 1. Company Identification
- `estab_name` - Employer name (2.65M unique)
- `site_address`, `site_city`, `site_state`, `site_zip` - Physical location
- `mail_street`, `mail_city`, `mail_state`, `mail_zip` - Mailing address
- `nr_in_estab` - Employee count at establishment

### 2. Industry Classification
- `sic_code` - SIC code (legacy, good coverage)
- `naics_code` - NAICS code (partial coverage - 2.1M of 5.15M have codes)
- Maps directly to BLS projections data

### 3. Violation Flags
- Willful violations (W) - most severe
- Repeat violations (R) - pattern of non-compliance
- Serious violations (S) - substantial risk of harm
- Penalty amounts - financial impact indicator
- `issuance_date`, `abate_date` - timing of issues

### 4. Safety Events
- Fatalities (72,457 records)
- Injuries by severity
- Accident descriptions

### 5. Activity Identifiers
- `activity_nr` - OSHA case number (for external lookup)
- `reporting_id` - Regional identifier

---

## Integration Schema

### New PostgreSQL Tables

```sql
-- Core establishment data
CREATE TABLE osha_establishments (
    establishment_id VARCHAR(32) PRIMARY KEY,  -- Hash of name+address
    estab_name TEXT NOT NULL,
    site_address TEXT,
    site_city VARCHAR(50),
    site_state VARCHAR(2),
    site_zip VARCHAR(10),
    naics_code VARCHAR(6),
    sic_code VARCHAR(4),
    union_status VARCHAR(1),  -- Y, N, B, A
    employee_count INTEGER,
    first_inspection_date DATE,
    last_inspection_date DATE,
    total_inspections INTEGER,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Violation summary per establishment
CREATE TABLE osha_violation_summary (
    establishment_id VARCHAR(32) REFERENCES osha_establishments,
    violation_type VARCHAR(1),  -- W, R, S, O
    violation_count INTEGER,
    total_penalties NUMERIC(15,2),
    first_violation_date DATE,
    last_violation_date DATE,
    PRIMARY KEY (establishment_id, violation_type)
);

-- Recent violations (detail for last 5 years)
CREATE TABLE osha_violations_recent (
    activity_nr BIGINT,
    establishment_id VARCHAR(32) REFERENCES osha_establishments,
    violation_type VARCHAR(1),
    issuance_date DATE,
    current_penalty NUMERIC(12,2),
    standard TEXT,  -- OSHA standard violated
    PRIMARY KEY (activity_nr, establishment_id)
);

-- Accidents/fatalities
CREATE TABLE osha_accidents (
    summary_nr BIGINT PRIMARY KEY,
    establishment_id VARCHAR(32) REFERENCES osha_establishments,
    event_date DATE,
    is_fatality BOOLEAN,
    injury_count INTEGER,
    event_description TEXT
);

-- Match to F-7 employers
CREATE TABLE osha_f7_matches (
    establishment_id VARCHAR(32) REFERENCES osha_establishments,
    f7_employer_id VARCHAR(32),  -- Hash ID from f7_employers_deduped
    match_method VARCHAR(20),    -- exact, fuzzy, address
    match_confidence NUMERIC(4,2),
    verified BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT NOW(),
    PRIMARY KEY (establishment_id, f7_employer_id)
);

-- Indexes for search
CREATE INDEX idx_osha_estab_name ON osha_establishments(LOWER(estab_name));
CREATE INDEX idx_osha_estab_state ON osha_establishments(site_state);
CREATE INDEX idx_osha_estab_naics ON osha_establishments(naics_code);
CREATE INDEX idx_osha_estab_union ON osha_establishments(union_status);
CREATE INDEX idx_osha_viol_date ON osha_violation_summary(last_violation_date);
```

---

## Data Extraction Plan

### Phase 1: Core Establishment Load (Priority)
**Estimated time:** 2-3 hours  
**Records:** ~2.65M unique establishments

```python
# Extract unique establishments with aggregated stats
SELECT 
    estab_name,
    site_address,
    site_city,
    site_state,
    site_zip,
    naics_code,
    sic_code,
    union_status,
    AVG(nr_in_estab) as avg_employees,
    MIN(open_date) as first_inspection,
    MAX(open_date) as last_inspection,
    COUNT(*) as total_inspections
FROM inspection
GROUP BY estab_name, site_address, site_city, site_state, site_zip,
         naics_code, sic_code, union_status
```

### Phase 2: Violation Summary (Priority)
**Estimated time:** 3-4 hours  
**Records:** ~13M violations → aggregated summaries

```python
# Aggregate violations by establishment and type
SELECT 
    i.estab_name, i.site_address, i.site_city, i.site_state,
    v.viol_type,
    COUNT(*) as violation_count,
    SUM(v.current_penalty) as total_penalties,
    MIN(v.issuance_date) as first_violation,
    MAX(v.issuance_date) as last_violation
FROM violation v
JOIN inspection i ON v.activity_nr = i.activity_nr
GROUP BY i.estab_name, i.site_address, i.site_city, i.site_state, v.viol_type
```

### Phase 3: Recent Violations Detail (2020+)
**Estimated time:** 1-2 hours  
**Records:** ~772K violations since 2020

```python
# Keep detail for recent violations only (2020+)
SELECT 
    v.activity_nr,
    i.estab_name, i.site_address, i.site_city, i.site_state,
    v.viol_type,
    v.issuance_date,
    v.current_penalty,
    v.standard
FROM violation v
JOIN inspection i ON v.activity_nr = i.activity_nr
WHERE v.issuance_date >= '2020-01-01'
```

### Phase 4: Accidents/Fatalities
**Estimated time:** 30 minutes  
**Records:** ~165K accidents

```python
# Link accidents to establishments
SELECT 
    a.summary_nr,
    i.estab_name, i.site_address, i.site_city, i.site_state,
    a.event_date,
    a.fatality,
    a.abstract_text
FROM accident a
JOIN inspection i ON a.rel_insp_nr = i.activity_nr
```

### Phase 5: F-7 Matching
**Estimated time:** 4-6 hours  
**Method:** Multi-pass matching

1. **Exact name + state match** (highest confidence)
2. **Normalized name + city + state** (fuzzy)
3. **Address-based matching** (geocoded)
4. **NAICS + city + size filtering** (industry context)

---

## Web Interface Requirements

### Display Fields (Per Employer)
- ✅ Has OSHA violations (yes/no flag)
- ⚠️ Severity indicator (willful/repeat/serious)
- 📅 Most recent violation date
- 💰 Total penalties (if significant)
- 🏭 Union status from OSHA (Y/N/B/A)
- 🔗 Case number for external lookup

### NOT Displayed (External Lookup)
- Full violation details
- Standard citations
- Abatement information
- Full inspection history
- Accident narratives

### Search Filters
- Union status (OSHA-reported)
- Violation severity
- Recent violations (last 1/2/5 years)
- Penalty threshold
- State/region
- NAICS/industry

---

## Integration Views

### v_employer_safety_profile
Combines F-7 employer data with OSHA violation history:
```sql
CREATE VIEW v_employer_safety_profile AS
SELECT 
    f.employer_id,
    f.employer_name,
    f.city,
    f.state,
    f.naics,
    f.latest_unit_size as workers,
    o.union_status as osha_union_status,
    o.total_inspections,
    o.last_inspection_date,
    vs.willful_count,
    vs.repeat_count,
    vs.serious_count,
    vs.total_penalties,
    vs.last_violation_date,
    CASE 
        WHEN vs.willful_count > 0 THEN 'CRITICAL'
        WHEN vs.repeat_count > 0 THEN 'HIGH'
        WHEN vs.serious_count > 5 THEN 'MODERATE'
        ELSE 'LOW'
    END as safety_risk_level
FROM f7_employers_deduped f
LEFT JOIN osha_f7_matches m ON f.employer_id = m.f7_employer_id
LEFT JOIN osha_establishments o ON m.establishment_id = o.establishment_id
LEFT JOIN (
    SELECT establishment_id,
           SUM(CASE WHEN violation_type='W' THEN violation_count ELSE 0 END) as willful_count,
           SUM(CASE WHEN violation_type='R' THEN violation_count ELSE 0 END) as repeat_count,
           SUM(CASE WHEN violation_type='S' THEN violation_count ELSE 0 END) as serious_count,
           SUM(total_penalties) as total_penalties,
           MAX(last_violation_date) as last_violation_date
    FROM osha_violation_summary
    GROUP BY establishment_id
) vs ON o.establishment_id = vs.establishment_id;
```

### v_osha_organizing_targets
Non-union OSHA establishments with violations:
```sql
CREATE VIEW v_osha_organizing_targets AS
SELECT 
    o.establishment_id,
    o.estab_name,
    o.site_city,
    o.site_state,
    o.naics_code,
    o.employee_count,
    o.last_inspection_date,
    vs.willful_count + vs.repeat_count as severe_violations,
    vs.total_penalties,
    vs.last_violation_date,
    'NON_UNION_WITH_VIOLATIONS' as target_reason
FROM osha_establishments o
JOIN osha_violation_summary vs ON o.establishment_id = vs.establishment_id
WHERE o.union_status = 'N'
  AND (vs.willful_count > 0 OR vs.repeat_count > 0 OR vs.serious_count >= 3)
  AND o.last_inspection_date >= '2020-01-01';
```

---

## Implementation Timeline

| Phase | Task | Hours | Priority |
|-------|------|-------|----------|
| 1 | Create PostgreSQL schema | 1 | HIGH |
| 2 | Extract establishments (2.65M) | 3 | HIGH |
| 3 | Extract violation summaries | 4 | HIGH |
| 4 | Extract recent violations (2020+) | 2 | HIGH |
| 5 | Extract accidents/fatalities | 1 | MEDIUM |
| 6 | Build F-7 matching pipeline | 6 | HIGH |
| 7 | Create integration views | 2 | HIGH |
| 8 | Update web interface | 4 | MEDIUM |
| **Total** | | **~23 hours** | |

---

## Success Metrics

| Metric | Target |
|--------|--------|
| OSHA establishments loaded | 2.65M |
| F-7 to OSHA match rate | 50%+ |
| Violations linked to F-7 employers | 500K+ |
| Non-union targets identified | 100K+ |
| Fatalities linked | 50K+ |

---

## Risk Considerations

1. **Data size** - 4.5GB SQLite may need chunked processing
2. **Name matching** - Company names vary significantly, need fuzzy matching
3. **Duplicate establishments** - Same company, multiple addresses
4. **NAICS coverage** - 40% of OSHA records missing NAICS codes
5. **Union status reliability** - OSHA-reported vs. actual may differ

---

## Appendix: Field Reference

### Union Status Codes
- **Y** = Union establishment (employees represented)
- **N** = Non-union establishment
- **B** = Both (union and non-union employees)
- **A** = All employees/Unknown status

### Violation Type Codes
- **W** = Willful (intentional disregard)
- **R** = Repeat (same employer, same standard)
- **S** = Serious (substantial probability of harm)
- **O** = Other-than-serious
- **U** = Unclassified

### Owner Type Codes
- **A** = Private sector
- **B** = Local government
- **C** = State government
- **D** = Federal government

---

*Plan created: January 28, 2026*
