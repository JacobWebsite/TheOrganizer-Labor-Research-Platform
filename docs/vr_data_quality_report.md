# Voluntary Recognition Data Quality Report
## Checkpoint 1.5 - Data Analysis Summary
## Generated: January 26, 2025

---

## DATA SOURCE OVERVIEW

| Property | Value |
|----------|-------|
| **File** | voluntary_recognitions.csv |
| **Raw Lines** | 5,617 |
| **Parsed Records** | 1,682 |
| **Date Range** | 2007-2024 |
| **Columns** | 17 |

**Note**: The discrepancy between raw lines and parsed records is due to multiline unit descriptions that span multiple CSV rows.

---

## FIELD COMPLETENESS

| Field | Non-Empty | Percentage |
|-------|-----------|------------|
| VR Case Number | 1,682 | 100.0% |
| Employer | 1,682 | 100.0% |
| Union | 1,681 | 99.9% |
| Date VR Request Received | 1,680 | 99.9% |
| Unit Description | 1,676 | 99.6% |
| Date VR Notice Sent | 1,590 | 94.5% |
| Date Notice Posted | 1,036 | 61.6% |
| Date Posting Closes | 993 | 59.0% |
| Regional Office | 732 | 43.5% |
| Unit City | 721 | 42.9% |
| Unit State | 721 | 42.9% |
| Date Voluntary Recognition | 719 | 42.7% |
| Number of Employees | 708 | 42.1% |
| Date R Case Petition Filed | 103 | 6.1% |
| R Case Number | 96 | 5.7% |
| Case Filed Date | 54 | 3.2% |
| Notes | 17 | 1.0% |

---

## CASE NUMBER FORMATS

| Format | Count | Description |
|--------|-------|-------------|
| XX-VR-XXX (old) | 949 | Traditional format (e.g., "14-VR-017") |
| 1-XXXXXXXXXX (new) | 729 | New format (e.g., "1-3528389153") |
| Other | 4 | Irregular formats |

---

## DATE FORMAT ANALYSIS

All dates use **M/D/YYYY** format with minor exceptions:

| Field | Clean Dates | Exceptions |
|-------|-------------|------------|
| Date VR Request Received | 1,680 | 0 |
| Date Voluntary Recognition | 716 | 3 (typos: "20021-12-13", "20222-01-27") |
| Date VR Notice Sent | 1,587 | 3 (text mixed in: "6/2/2022 mailed; 6/3...") |

---

## TEMPORAL DISTRIBUTION

| Year | Cases | Notes |
|------|-------|-------|
| 2007 | 71 | VR notification system began |
| 2008 | 475 | Peak early period |
| 2009 | 402 | Strong activity |
| 2010-2019 | 0 | **DATA GAP** - Collection changed |
| 2020 | 31 | Collection resumed (COVID year) |
| 2021 | 127 | Post-COVID surge |
| 2022 | 209 | Strong growth |
| 2023 | 182 | Consistent activity |
| 2024 | 183 | Through current |

**Note**: The 2010-2019 gap reflects a change in NLRB data collection practices, not an absence of voluntary recognitions during that period.

---

## GEOGRAPHIC DISTRIBUTION

### Top 15 States by VR Cases

| Rank | State | Cases |
|------|-------|-------|
| 1 | NY | 107 |
| 2 | CA | 97 |
| 3 | IL | 42 |
| 4 | WA | 39 |
| 5 | CT | 26 |
| 6 | MI | 25 |
| 7 | TX | 24 |
| 8 | OR | 24 |
| 9 | OH | 23 |
| 10 | NJ | 20 |
| 11 | WI | 20 |
| 12 | DC | 19 |
| 13 | MD | 18 |
| 14 | MA | 17 |
| 15 | MO | 16 |

**Total states covered**: 47

### Top NLRB Regions

| Region | Cases | Description |
|--------|-------|-------------|
| 19 | 157 | Seattle (AK, ID, MT, OR, WA) |
| 02 | 111 | New York |
| 29 | 101 | Brooklyn |
| 05 | 95 | Baltimore (DC, MD, VA, WV) |
| 13 | 75 | Chicago |

---

## UNION AFFILIATION ANALYSIS

### Recognized Affiliations (62.5% of cases)

| Affiliation | Cases | % of Total |
|-------------|-------|------------|
| IBT (Teamsters) | 241 | 14.3% |
| UNITE HERE | 109 | 6.5% |
| IUOE | 95 | 5.7% |
| SEIU | 94 | 5.6% |
| IAM | 86 | 5.1% |
| UFCW | 77 | 4.6% |
| UAW | 76 | 4.5% |
| CWA | 72 | 4.3% |
| IBEW | 68 | 4.0% |
| OPEIU | 34 | 2.0% |
| AFT | 24 | 1.4% |
| LIUNA | 21 | 1.2% |
| USW | 18 | 1.1% |
| AFSCME | 12 | 0.7% |

### Independent/Other Unions (37.5%)

| Cases | 630 |
|-------|-----|

Sample independent unions:
- National Air Traffic Controllers Association (NATCA)
- International Union of Painters and Allied Trades
- Professional Air Traffic Controllers Organization (PATCO)
- Engineers and Scientists of California, IFPTE

---

## EMPLOYEE COUNT ANALYSIS

| Metric | Value |
|--------|-------|
| Records with count | 706 |
| Total employees | 47,081 |
| Average unit size | 66.7 |
| Median unit size | 15 |
| Minimum | 1 |
| Maximum | 3,700 |

### Unit Size Distribution

| Size Range | Count | Percentage |
|------------|-------|------------|
| 1-10 | 275 | 39.0% |
| 11-25 | 190 | 26.9% |
| 26-50 | 90 | 12.7% |
| 51-100 | 64 | 9.1% |
| 101-250 | 57 | 8.1% |
| 251-500 | 15 | 2.1% |
| 500+ | 15 | 2.1% |

**Note**: Most VR cases involve small bargaining units (65.9% have 25 or fewer employees).

---

## R CASE LINKAGE

| Metric | Value |
|--------|-------|
| VR cases with election petition | 96 |
| Percentage of total | 5.7% |

These cases had employees file for a formal NLRB election during the waiting period after VR was announced. This links to existing NLRB election data.

---

## DATA QUALITY ISSUES IDENTIFIED

### Issues Requiring Handling

1. **Multiline unit descriptions**: 
   - Unit description field spans multiple CSV rows
   - Requires careful parsing to reconstruct records

2. **Date typos** (3 records):
   - "20021-12-13" should be "2021-12-13"
   - "20222-01-27" should be "2022-01-27"

3. **Non-numeric employee counts** (2 records):
   - "Z" - invalid
   - "approx. 29" - can extract numeric

4. **Address in employer field** (occasional):
   - Some records have addresses appended to employer names
   - Example: "Dana Corporation\nAttn: Ms. Bridget Gaff, Plant Manager\n401 East Park Drive..."

5. **Regional Office variations**:
   - Old format: Region number only (in case number)
   - New format: Full regional office name (e.g., "Region 20, San Francisco, California")

---

## MATCHING POTENTIAL ASSESSMENT

### Employer Matching
- **Expected match rate**: 15-25%
- **Reason**: VR typically precedes F-7 filing (new bargaining relationships)
- **Strategy**: Exact match on normalized name + city + state, then fuzzy

### Union Matching
- **Expected match rate**: 60-80%
- **Reason**: Most are established affiliations with existing OLMS filings
- **Strategy**: 
  1. Extract affiliation code from name
  2. Extract local number if present
  3. Match to unions_master by affiliation + local
  4. Fuzzy name match for independents

---

## SCHEMA OBJECTS CREATED

### Tables (6)
- `nlrb_voluntary_recognition` - Core VR data
- `vr_status_lookup` - VR status codes
- `nlrb_regions` - NLRB regional office reference
- `vr_affiliation_patterns` - Regex patterns for union parsing
- `vr_employer_match_staging` - Employer match candidates
- `vr_union_match_staging` - Union match candidates

### Views (4)
- `v_vr_by_year` - Cases by year
- `v_vr_by_state` - Cases by state
- `v_vr_by_affiliation` - Cases by union affiliation
- `v_vr_data_quality` - Data quality metrics

### Reference Data Loaded
- 31 NLRB regions
- 29 affiliation patterns

---

## NEXT STEPS

**Checkpoint 2**: Data Load & Cleaning
- Parse CSV with multiline field handling
- Clean and normalize employer/union names
- Parse dates and handle exceptions
- Extract region from case numbers
- Load into `nlrb_voluntary_recognition` table

**Continue command**: `Continue from Checkpoint 2 - Begin data loading`

---

*Report generated: January 26, 2025*
