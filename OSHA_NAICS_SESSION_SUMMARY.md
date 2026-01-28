# OSHA Integration Plan & NAICS Crosswalk Summary

**Date:** January 28, 2026  
**Status:** NAICS Crosswalks Loaded, OSHA Integration Ready to Begin

---

## What Was Accomplished

### NAICS Crosswalks Downloaded & Loaded

Downloaded official Census Bureau crosswalk files from census.gov and created 3 new PostgreSQL tables in `olms_multiyear` database:

| Table | Records | Purpose |
|-------|---------|---------|
| `naics_version_crosswalk` | 4,607 | Chains NAICS versions: 2022→2017→2012→2007→2002 |
| `naics_sic_crosswalk` | 2,163 | SIC (1987) → NAICS 2002 |
| `naics_codes_reference` | 4,323 | Full NAICS 2022 + 2017 codes with titles |

### Version Crosswalk Chain
- **2022 → 2017**: 1,151 mappings
- **2017 → 2012**: 1,070 mappings  
- **2012 → 2007**: 1,185 mappings
- **2007 → 2002**: 1,201 mappings

### Files Created
- `C:\Users\jakew\Downloads\labor-data-project\naics_crosswalks\` - Raw Excel files from Census
- `load_naics_crosswalks.py` - Script to parse and load crosswalks
- `verify_naics_crosswalks.py` - Verification script

---

## OSHA Database Overview

**Source Database:** `C:\Users\jakew\Downloads\osha_enforcement.db` (4.5 GB SQLite)  
**Data Currency:** Through January 22, 2026 (current)

### Data Coverage
| Metric | Count |
|--------|-------|
| Time Span | June 1970 → January 2026 (56 years) |
| Inspections | 5.15 million |
| Unique Establishments | 2.65 million |
| Violations | 13.18 million |
| Total Penalties | $7.5 billion |
| Accidents | 165,622 |
| Fatality-Related | 72,457 |

### Historical Coverage by Decade
| Decade | Inspections | Establishments |
|--------|-------------|----------------|
| 1970s | 508K | 251K |
| 1980s | 1.13M | 680K |
| 1990s | 1.12M | 633K |
| 2000s | 1.07M | 634K |
| 2010s | 917K | 631K |
| 2020s | 409K | 304K |

### Key OSHA Fields for Matching
- `estab_name`, `site_address`, `site_city`, `site_state`, `site_zip`
- `naics_code`, `sic_code` (for industry classification)
- `union_status` (Y/N/B/A)
- `nr_in_estab` (employee count)
- `activity_nr` (case number for external lookup)

### Union Status Distribution
| Status | Inspections | Description |
|--------|-------------|-------------|
| Y | 556,567 | Union workplace |
| N | 1,866,550 | Non-union (organizing targets) |
| B | 1,935,412 | Both/Mixed |
| A | 631,715 | Unknown/All |
| NULL | 164,287 | Not recorded |

### Violation Severity
| Type | Count | Avg Penalty | Priority |
|------|-------|-------------|----------|
| W (Willful) | 53,131 | $13,395 | ⚠️ CRITICAL |
| R (Repeat) | 276,697 | $2,809 | 🔴 HIGH |
| S (Serious) | 6,056,744 | $756 | 🟡 MODERATE |
| O (Other) | 6,787,407 | $83 | ⚪ LOW |
| U (Unclassified) | 10,097 | $12,518 | - |

### Recent Violations (2020+)
- 195,754 establishments with violations
- 239,570 inspections with violations
- 772,341 total violations
- $1.74B in penalties

---

## PostgreSQL Schema Design

```sql
-- Core establishment data (2.65M records)
CREATE TABLE osha_establishments (
    establishment_id VARCHAR(32) PRIMARY KEY,  -- hash of name+address
    estab_name TEXT NOT NULL,
    site_address TEXT,
    site_city VARCHAR(100),
    site_state VARCHAR(2),
    site_zip VARCHAR(10),
    naics_code VARCHAR(10),
    sic_code VARCHAR(10),
    union_status VARCHAR(1),  -- Y/N/B/A
    employee_count INTEGER,
    first_inspection_date DATE,
    last_inspection_date DATE,
    total_inspections INTEGER
);

-- Aggregated violations by type
CREATE TABLE osha_violation_summary (
    id SERIAL PRIMARY KEY,
    establishment_id VARCHAR(32) REFERENCES osha_establishments,
    violation_type VARCHAR(1),  -- W/R/S/O/U
    violation_count INTEGER,
    total_penalties NUMERIC(15,2),
    first_violation_date DATE,
    last_violation_date DATE
);

-- Detail for 2020+ violations (772K records)
CREATE TABLE osha_violations_recent (
    id SERIAL PRIMARY KEY,
    activity_nr BIGINT,  -- OSHA case number
    establishment_id VARCHAR(32) REFERENCES osha_establishments,
    violation_type VARCHAR(1),
    issuance_date DATE,
    current_penalty NUMERIC(12,2),
    standard VARCHAR(50)
);

-- Fatalities/injuries (165K records)
CREATE TABLE osha_accidents (
    id SERIAL PRIMARY KEY,
    summary_nr BIGINT,
    establishment_id VARCHAR(32) REFERENCES osha_establishments,
    event_date DATE,
    is_fatality BOOLEAN,
    injury_count INTEGER,
    event_description TEXT
);

-- Link to F-7 employers
CREATE TABLE osha_f7_matches (
    id SERIAL PRIMARY KEY,
    establishment_id VARCHAR(32) REFERENCES osha_establishments,
    f7_employer_id VARCHAR(32) REFERENCES f7_employers(employer_id),
    match_method VARCHAR(20),  -- exact/fuzzy/address
    match_confidence NUMERIC(3,2)
);

-- Indexes
CREATE INDEX idx_osha_est_name ON osha_establishments(estab_name);
CREATE INDEX idx_osha_est_state ON osha_establishments(site_state);
CREATE INDEX idx_osha_est_naics ON osha_establishments(naics_code);
CREATE INDEX idx_osha_est_union ON osha_establishments(union_status);
CREATE INDEX idx_osha_viol_est ON osha_violation_summary(establishment_id);
CREATE INDEX idx_osha_recent_est ON osha_violations_recent(establishment_id);
CREATE INDEX idx_osha_acc_est ON osha_accidents(establishment_id);
CREATE INDEX idx_osha_f7_est ON osha_f7_matches(establishment_id);
CREATE INDEX idx_osha_f7_emp ON osha_f7_matches(f7_employer_id);
```

---

## Integration Views

```sql
-- F-7 employers with OSHA violation history
CREATE VIEW v_employer_safety_profile AS
SELECT 
    e.employer_id,
    e.employer_name,
    e.city,
    e.state,
    o.estab_name AS osha_name,
    o.union_status AS osha_union_status,
    o.total_inspections,
    o.last_inspection_date,
    vs.willful_count,
    vs.repeat_count,
    vs.serious_count,
    vs.total_penalties,
    a.fatality_count,
    m.match_confidence
FROM f7_employers e
JOIN osha_f7_matches m ON e.employer_id = m.f7_employer_id
JOIN osha_establishments o ON m.establishment_id = o.establishment_id
LEFT JOIN (
    SELECT establishment_id,
           SUM(CASE WHEN violation_type = 'W' THEN violation_count ELSE 0 END) as willful_count,
           SUM(CASE WHEN violation_type = 'R' THEN violation_count ELSE 0 END) as repeat_count,
           SUM(CASE WHEN violation_type = 'S' THEN violation_count ELSE 0 END) as serious_count,
           SUM(total_penalties) as total_penalties
    FROM osha_violation_summary
    GROUP BY establishment_id
) vs ON o.establishment_id = vs.establishment_id
LEFT JOIN (
    SELECT establishment_id, COUNT(*) as fatality_count
    FROM osha_accidents WHERE is_fatality = true
    GROUP BY establishment_id
) a ON o.establishment_id = a.establishment_id;

-- Non-union establishments with violations (organizing targets)
CREATE VIEW v_osha_organizing_targets AS
SELECT 
    o.establishment_id,
    o.estab_name,
    o.site_city,
    o.site_state,
    o.naics_code,
    o.employee_count,
    o.total_inspections,
    o.last_inspection_date,
    vs.willful_count,
    vs.repeat_count,
    vs.serious_count,
    vs.total_penalties
FROM osha_establishments o
LEFT JOIN (
    SELECT establishment_id,
           SUM(CASE WHEN violation_type = 'W' THEN violation_count ELSE 0 END) as willful_count,
           SUM(CASE WHEN violation_type = 'R' THEN violation_count ELSE 0 END) as repeat_count,
           SUM(CASE WHEN violation_type = 'S' THEN violation_count ELSE 0 END) as serious_count,
           SUM(total_penalties) as total_penalties
    FROM osha_violation_summary
    GROUP BY establishment_id
) vs ON o.establishment_id = vs.establishment_id
WHERE o.union_status = 'N'
AND o.last_inspection_date >= '2020-01-01'
AND (vs.willful_count > 0 OR vs.repeat_count > 0 OR vs.serious_count >= 5);
```

---

## Implementation Phases

| Phase | Task | Est. Time |
|-------|------|-----------|
| 1 | Create OSHA schema in PostgreSQL | 10 min |
| 2 | Extract 2.65M unique establishments from SQLite | 2-3 hrs |
| 3 | Aggregate 13M violations by establishment | 3-4 hrs |
| 4 | Load 772K recent violations (2020+) | 1-2 hrs |
| 5 | Load 165K accidents/fatalities | 30 min |
| 6 | F-7 matching (exact + fuzzy) | 4-6 hrs |
| 7 | Create views and indexes | 30 min |
| **Total** | | **~12-16 hrs** |

---

## F-7 Matching Strategy

### Multi-Pass Approach
1. **Exact name + state match** (highest confidence)
2. **Fuzzy name + city + state** (medium confidence)
3. **Address-based matching** (medium confidence)
4. **NAICS + employee size + location** (lower confidence)

### Geographic Overlap (Top States)
| F-7 Data | OSHA Data (2020+) |
|----------|-------------------|
| CA (7,350) | CA (42,597) |
| NY (7,306) | WA (32,100) |
| IL (6,828) | TX (23,044) |
| PA (4,143) | MI (21,580) |

### NAICS Overlap
| F-7 Top Industries | OSHA Top Industries (2020+) |
|--------------------|---------------------------|
| 23 Construction (12,119) | 23 Construction (175,205) |
| 31 Manufacturing (9,402) | 33 Manufacturing (37,568) |
| 62 Healthcare (7,173) | 62 Healthcare (15,797) |

### Expected Match Rates
- Initial exact name+state: ~22%
- After fuzzy matching: ~40-50%
- With address/NAICS: ~50-60%

---

## Web Interface Display (Per Employer)

| Field | Display |
|-------|---------|
| Has OSHA violations | ✅ Yes/No flag |
| Severity indicator | ⚠️ Willful / 🔴 Repeat / 🟡 Serious |
| Most recent violation | 📅 Date |
| Total penalties | 💰 Amount (if significant) |
| Union status from OSHA | 🏭 Y/N/B/A |
| Case number | 🔗 activity_nr for external lookup |

### NOT Displayed (User Looks Up Externally)
- Full violation details
- Standard citations
- Abatement information
- Full inspection history
- Accident narratives

### Search Filters to Add
- Union status
- Violation severity
- Recent violations (1/2/5 years)
- Penalty threshold
- State/region
- NAICS/industry

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

## Key Files Reference

| File | Location |
|------|----------|
| OSHA Database | `C:\Users\jakew\Downloads\osha_enforcement.db` |
| NAICS Crosswalks | `C:\Users\jakew\Downloads\labor-data-project\naics_crosswalks\` |
| Project Database | PostgreSQL `olms_multiyear` (localhost) |
| Load Script | `load_naics_crosswalks.py` |
| Verify Script | `verify_naics_crosswalks.py` |

### Database Connection
```
host: localhost
dbname: olms_multiyear
user: postgres
password: Juniordog33!
```

---

## Scripts Created This Session

| Script | Purpose |
|--------|---------|
| `download_naics_crosswalks.py` | Downloads Census crosswalk files |
| `download_remaining_naics.py` | Downloads older format .xls files |
| `parse_naics_crosswalks.py` | Inspects Excel file structure |
| `load_naics_crosswalks.py` | Parses and loads into PostgreSQL |
| `verify_naics_crosswalks.py` | Verifies loaded data and tests chained lookups |

---

## Next Steps

1. **Create OSHA schema** in PostgreSQL (run schema SQL above)
2. **Extract establishments** from SQLite → PostgreSQL
3. **Aggregate violations** by establishment
4. **Run F-7 matching** using multi-pass approach
5. **Create API endpoints** for safety data
6. **Update web interface** with OSHA indicators
