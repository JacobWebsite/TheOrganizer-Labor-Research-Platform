# Database Audit Report - Labor Relations Research Platform
## Date: 2026-02-10

---

## 1. DATABASE OVERVIEW

- **Database**: olms_multiyear (PostgreSQL)
- **Total Size**: 21 GB
- **Total Tables**: 157
- **Materialized Views**: 3
- **Regular Views**: 187
- **Reference Tables**: 5

---

## 2. TABLE INVENTORY (157 tables, sorted by row count)

### Tier 1: Large Tables (>500K rows)
| Table | Estimated Rows | Total Size |
|---|---|---|
| splink_match_results | 5,762,126 | 1,591 MB |
| nlrb_docket | 2,046,151 | 281 MB |
| osha_violations_detail | 2,045,031 | 431 MB |
| qcew_annual | 1,943,426 | 362 MB |
| nlrb_participants | 1,905,674 | 600 MB |
| epi_union_membership | 1,420,064 | 322 MB |
| employers_990_deduped | 1,046,167 | 265 MB |
| osha_establishments | 1,006,299 | 726 MB |
| osha_violation_summary | 872,696 | 151 MB |
| nlrb_allegations | 715,805 | 124 MB |
| national_990_filers | 586,767 | 316 MB |
| sec_companies | 522,370 | 374 MB |

### Tier 2: Medium Tables (50K-500K rows)
| Table | Estimated Rows | Total Size |
|---|---|---|
| gleif_ownership_links | 498,963 | 87 MB |
| nlrb_filings | 498,749 | 89 MB |
| nlrb_cases | 477,688 | 91 MB |
| gleif_us_entities | 379,192 | 342 MB |
| whd_cases | 363,365 | 133 MB |
| employer_comparables | 269,785 | 135 MB |
| union_names_crosswalk | 171,481 | 51 MB |
| f7_employers (raw) | 146,863 | 117 MB |
| corporate_hierarchy | 125,120 | N/A |
| f7_industry_scores | 121,433 | N/A |
| bls_industry_occupation_matrix | 113,473 | N/A |
| unified_employers_osha | 100,766 | N/A |
| osha_f7_matches | 79,979 | N/A |
| nlrb_tallies | 67,779 | N/A |
| osha_accidents | 63,066 | N/A |
| f7_employers_deduped | 60,953 | 143 MB |
| mergent_employers | 57,642 | 561 MB |
| nlrb_sought_units | 52,078 | N/A |
| ny_state_contracts | 51,500 | N/A |

### Tier 3: Small Tables (<50K rows)
| Table | Estimated Rows |
|---|---|
| nyc_contracts | 49,767 |
| ny_990_filers | 47,614 |
| federal_contract_recipients | 47,193 |
| osha_unified_matches | 42,812 |
| census_occupation_soc_xwalk | 34,540 |
| nlrb_elections | 33,096 |
| nlrb_voting_units | 31,643 |
| unions_master | 26,665 |
| union_hierarchy | 26,665 |
| census_industry_naics_xwalk | 24,373 |
| f7_employer_merge_log | 21,608 |
| labor_orgs_990 | 19,367 |
| labor_orgs_990_deduped | 15,172 |
| corporate_identifier_crosswalk | 14,489 |
| usaspending_f7_matches | 9,305 |
| f7_federal_scores | 9,305 |
| contract_employer_matches | 8,954 |
| ps_employers | 7,987 |
| qcew_industry_density | 7,143 |
| (and 65 more small/reference tables) |

### pg_stat Stale Tables (showed 0 but actually have data)
These 35 tables have stale pg_stat estimates. Real counts:
| Table | Actual Rows |
|---|---|
| ar_disbursements_emp_off | 2,813,248 |
| lm_data | 331,238 |
| ar_assets_investments | 304,816 |
| ar_disbursements_total | 216,372 |
| ar_membership | 216,508 |
| nlrb_employer_xref | 179,275 |
| f7_union_employer_relations | 119,844 |
| nlrb_union_xref | 73,326 |
| crosswalk_unions_master | 50,039 |
| nlrb_election_results | 33,096 |
| bls_union_data | 31,007 |
| union_organization_level | 19,536 |
| unionstats_state | 10,710 |
| union_naics_mapping | 7,624 |
| bls_union_series | 1,232 |
| unionstats_industry | 281 |
| crosswalk_affiliation_sector_map | 111 |
| crosswalk_f7_only_unions | 167 |
| f7_adjustment_factors | 76 |
| bls_fips_lookup | 52 |
| state_abbrev | 51 |
| bls_industry_lookup | 39 |
| bls_occupation_lookup | 30 |
| naics_sectors | 24 |
| f7_name_inference_rules | 23 |
| bls_naics_mapping | 22 |
| nhq_reconciled_membership | 132 |
| deduplication_methodology | 11 |
| union_match_status | 6 |
| crosswalk_sector_lookup | 6 |
| match_status_lookup | 6 |
| sector_lookup | 6 |
| union_sector | 6 |

**RECOMMENDATION**: Run `ANALYZE` on these 35 tables to update statistics. This will improve query planner decisions.

### Truly Empty Tables (confirmed 0 rows)
| Table | Notes |
|---|---|
| employer_ein_crosswalk | Unused - EIN data went to crosswalk |
| sic_naics_xwalk | Unused - using naics_sic_crosswalk instead |
| union_affiliation_naics | Never populated |
| union_employer_history | Never populated |
| vr_employer_match_staging | Staging table, cleared |
| vr_union_match_staging | Staging table, cleared |

**6 confirmed empty tables** - candidates for cleanup.

---

## 3. MATERIALIZED VIEWS

| View | Rows | Notes |
|---|---|---|
| mv_whd_employer_agg | 330,419 | WHD aggregated by employer |
| mv_employer_search | 118,015 | Employer search index |
| mv_employer_features | 54,973 | Features for Gower similarity |

**187 regular views** exist, including ~60 sector-specific organizing target views (healthcare, transit, education, etc.) and ~30 sector-specific union presence views.

---

## 4. MATCH RATES

### Core Entity Matching
| Match Type | Matched | Total | Rate |
|---|---|---|---|
| OSHA -> F7 | 79,979 | 1,007,217 | **7.94%** |
| Mergent -> F7 | 856 | 56,426 | **1.52%** |
| WHD -> F7 | N/A (no link column) | 363,365 | **0% (not linked)** |

### Corporate Crosswalk (14,489 rows)
| Identifier | Count | Coverage |
|---|---|---|
| Federal contractors | 9,238 | 63.8% |
| Mergent DUNS | 3,361 | 23.2% |
| GLEIF LEI | 3,260 | 22.5% |
| EIN | 2,596 | 17.9% |
| SEC CIK | 1,948 | 13.4% |

### 990 Filers
- Total: 586,767
- No F7 link column detected on national_990_filers

### Key Observations
- **OSHA match rate is only 7.94%** - many OSHA establishments are not in the F7 filing database (F7 = union-represented employers only)
- **Mergent match rate is 1.52%** - extremely low. Mergent has 56K employers but only 856 matched to F7. This is because Mergent is a general business directory while F7 is union-specific.
- **WHD has no F7 link column** - matching appears to go through name-based aggregation (mv_whd_employer_agg) rather than direct foreign key
- **990 filers are not linked to F7** - 587K filers with no cross-reference

---

## 5. DATA QUALITY METRICS

### F7 Employers (60,953 records)
| Metric | Count | Pct |
|---|---|---|
| Has NAICS | 60,455 | 99.2% |
| NULL NAICS | 498 | 0.8% |
| Has latitude | 60,843 | 99.8% |
| NULL latitude | 110 | 0.2% |
| Has state | 60,654 | 99.5% |
| NULL state | 299 | 0.5% |
| NULL city | 43 | 0.1% |

**F7 data quality is excellent** - >99% coverage on all key fields.

### Mergent Employers (56,426 records)
| Metric | Count | Pct |
|---|---|---|
| Has NAICS primary | 54,889 | 97.3% |
| NULL NAICS | 1,537 | 2.7% |
| Has state | 56,426 | 100% |
| Has organizing_score | 55,441 | 98.3% |
| Has nlrb_predicted_win_pct | 56,426 | 100% |
| Has similarity_score | 53,957 | 95.6% |

### OSHA Establishments
- NULL naics_code: 1,856 (0.18% of 1M)

### NLRB
- Elections: 33,096
- Participants: 1,906,542

---

## 6. SCORING DISTRIBUTION

| Tier | Count | Avg Score | Min | Max |
|---|---|---|---|---|
| TOP (>=30) | 7,310 | 31.73 | 30 | 57 |
| HIGH (25-29) | 11,295 | 26.33 | 25 | 29 |
| MEDIUM (20-24) | 29,936 | 21.77 | 20 | 24 |
| LOW (<20) | 6,900 | 17.13 | 17 | 19 |
| **Total scored** | **55,441** | | | |

- 985 employers unscored (56,426 - 55,441)
- Distribution is heavily weighted toward MEDIUM tier (54%)
- TOP tier has the widest range (30-57), suggesting some outlier high-scorers

---

## 7. GEOGRAPHIC COVERAGE (F7)

| State | Employers | | State | Employers |
|---|---|---|---|---|
| CA | 7,071 | | MA | 1,687 |
| NY | 7,061 | | IN | 1,682 |
| IL | 6,556 | | WI | 1,437 |
| PA | 4,000 | | FL | 1,190 |
| NJ | 2,931 | | TX | 1,140 |
| OH | 2,778 | | | |
| MI | 2,727 | | | |
| MN | 2,481 | | | |
| WA | 2,474 | | | |
| MO | 2,304 | | | |

Strong in traditional union states (CA, NY, IL, PA, NJ, OH, MI). Light in Sun Belt / Right-to-Work states (FL, TX much lower).

---

## 8. NAICS COVERAGE (F7)

| NAICS | Description | Count |
|---|---|---|
| 23 | Construction | 13,474 |
| 31 | Manufacturing | 10,428 |
| 62 | Healthcare | 8,366 |
| 48 | Transportation | 6,899 |
| 72 | Accommodation/Food | 3,216 |
| 71 | Arts/Entertainment | 2,759 |
| 44 | Retail Trade | 2,566 |
| 81 | Other Services | 1,692 |
| 54 | Professional Services | 1,683 |
| 92 | Government | 1,554 |

All NAICS are 2-digit level only.

---

## 9. DATA FRESHNESS

| Source | Latest Data |
|---|---|
| WHD | 2025-12-30 |
| NLRB Elections | 2026-01-20 |
| F7 filing year | (column name differs - needs check) |
| OSHA close date | (column name differs - needs check) |

---

## 10. INDEX COVERAGE

### Well-Indexed Tables
| Table | Index Count | Notes |
|---|---|---|
| f7_employers_deduped | 13 | Including 3 GIN trigram indexes |
| osha_establishments | 11 | Including 2 GIN trigram indexes |
| nlrb_participants | 10 | 2 duplicate indexes detected |
| corporate_identifier_crosswalk | 10 | Partial indexes on non-null |
| mergent_employers | 9 | Good coverage |
| whd_cases | 6 | |
| union_hierarchy | 5 | |

### Under-Indexed Tables (0 indexes)
| Table | Rows | Size | Risk |
|---|---|---|---|
| gleif_entities | ~379K | ~342 MB | HIGH - large table, no indexes |
| usaspending_recipients | ~47K | N/A | MEDIUM |
| qcew_annual_averages | ~1.9M | ~362 MB | HIGH - very large, no indexes |

### Duplicate Indexes Detected
- `nlrb_participants`: `idx_nlrb_part_employer` and `idx_nlrb_part_matched_emp` are identical (both on `matched_employer_id`)
- `nlrb_participants`: `idx_nlrb_part_matched_union` and `idx_nlrb_part_olms` are identical (both on `matched_olms_fnum`)
- `f7_employers_deduped`: `idx_f7_emp_trgm` and `idx_f7_employer_name_trgm` are identical (both GIN on `employer_name`)
- `f7_employers_deduped`: `idx_f7_deduped_union_fnum` and `idx_f7_reconciled_affiliation` are identical (both on `latest_union_fnum`)
- `f7_employers_deduped`: `idx_f7_deduped_state` and `idx_f7_reconciled_state` are identical (both on `state`)

**5 duplicate indexes consuming unnecessary disk space and write overhead.**

---

## 11. KEY FINDINGS AND RECOMMENDATIONS

### Critical Issues
1. **39 tables have stale pg_stat** - run `ANALYZE` to update planner statistics
2. **5 duplicate indexes** on nlrb_participants and f7_employers_deduped - wasting disk and slowing writes
3. **3 large tables have ZERO indexes** (gleif_entities, usaspending_recipients, qcew_annual_averages)
4. **WHD has no F7 link column** - matching only via name aggregation view
5. **Mergent match rate is only 1.52%** - 56K employers with just 856 F7 matches
6. **mergent_employers is 561 MB for 57K rows** (111 columns!) - possible denormalization bloat

### Data Quality Gaps
1. **F7 NAICS is 2-digit only** - limits industry analysis granularity
2. **6 confirmed empty tables** - candidates for removal
3. **990 filers (587K) have no F7 cross-reference** - large untapped dataset
4. **splink_match_results (5.7M rows, 1.6GB)** - largest table; may be intermediate/staging data that could be archived

### Architecture Observations
1. **187 views** is extremely high - many appear to be sector-specific variants of the same pattern. Consider consolidating with parameterized queries.
2. **mergent_employers has 111 columns** - heavy denormalization. Score columns, match columns, contract columns, WHD columns all on one table.
3. **Database is 21 GB** - manageable but splink_match_results alone is 1.6 GB (7.6% of total).

### Quick Wins
1. Run `ANALYZE` on all tables (5 minutes, improves query plans)
2. Drop 5 duplicate indexes (saves ~200MB+ disk, improves write speed)
3. Add indexes to gleif_entities (at minimum on LEI and entity name)
4. Drop 6 confirmed empty tables
5. Consider archiving splink_match_results if no longer needed for active queries

---

## 12. COLUMN INVENTORIES

### f7_employers_deduped: 35 columns
Key: employer_id (PK), employer_name, city, state, naics, latitude, longitude, latest_union_fnum, latest_unit_size, filing_count, corporate_parent_id, whd_* (5 columns), cbsa_code

### mergent_employers: 111 columns
Key: id (PK), duns, ein, company_name, state, naics_primary, employees_site, sales_amount, year_founded.
Match columns: matched_f7_employer_id, osha_establishment_id, nlrb_case_number, matched_990_id.
Score columns: organizing_score, score_* (14 columns), similarity_score, nlrb_predicted_win_pct.
WHD/OSHA/contract columns: 20+ denormalized fields.

### osha_establishments: 15 columns
Key: establishment_id (PK), estab_name, site_city, site_state, naics_code, union_status, employee_count, total_inspections, last_inspection_date

### whd_cases: 25 columns
Key: id (PK), case_id, trade_name, legal_name, name_normalized, state, naics_code, total_violations, civil_penalties, backwages_amount. No F7 link column.

### corporate_identifier_crosswalk: 19 columns
Key: id (PK), f7_employer_id, gleif_lei, mergent_duns, sec_cik, ein, is_federal_contractor, federal_obligations
