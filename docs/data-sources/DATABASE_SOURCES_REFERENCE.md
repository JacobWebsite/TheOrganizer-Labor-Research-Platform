# Database Sources Reference

> Comprehensive catalog of all 257 database objects (244 tables + 13 materialized views) in the `olms_multiyear` database, organized by functional category.
>
> **Last updated:** 2026-03-04

---

## Table of Contents

1. [Core Union Data](#1-core-union-data)
2. [NLRB Elections & Cases](#2-nlrb-elections--cases)
3. [Enforcement & Workplace Conditions](#3-enforcement--workplace-conditions)
4. [BLS Labor Statistics](#4-bls-labor-statistics)
5. [O*NET Occupational Data](#5-onet-occupational-data)
6. [Corporate Identity & Hierarchy](#6-corporate-identity--hierarchy)
7. [Federal Contracting & Tax Data](#7-federal-contracting--tax-data)
8. [Census & Demographics](#8-census--demographics)
9. [Geographic & NAICS Reference](#9-geographic--naics-reference)
10. [Union Density & Benchmarks](#10-union-density--benchmarks)
11. [Master Employer & Deduplication](#11-master-employer--deduplication)
12. [Matching Infrastructure](#12-matching-infrastructure)
13. [Scoring Pipeline (Materialized Views)](#13-scoring-pipeline-materialized-views)
14. [Research Agent & CBA](#14-research-agent--cba)
15. [Public Sector](#15-public-sector)
16. [NYC & NY State Regional](#16-nyc--ny-state-regional)
17. [Web Scraping & Discovery](#17-web-scraping--discovery)
18. [Platform & System](#18-platform--system)

---

## 1. Core Union Data

### unions_master
**26,693 rows** -- Canonical union registry with FNUM, name, affiliation, organization level, and activity status.
Master reference for all unions in the system. Contains `is_likely_inactive`, `parent_fnum`, `desig_name` (NHQ/LU/DC/etc. codes).
Linked to `f7_union_employer_relations` and all union crosswalk tables.

### lm_data
**331,238 rows** -- Historical union LM financial reports (2010-2024) from OLMS.
Supplements F7 data with longitudinal filing history for union membership and revenue trends.
One row per union per filing year.

### f7_employers
**146,863 rows** -- Raw F7 employer records before deduplication.
Source table for the deduplication pipeline. Contains employer name, address, NAICS, unit size.
Superseded by `f7_employers_deduped` for most queries.

### f7_employers_deduped
**146,863 rows** -- Deduplicated F7 employer records with standardized names and addresses.
The primary employer table for all scoring and matching. Column `latest_unit_size` (not `company_size`).
`f7_employer_id` is TEXT everywhere -- never cast to integer.

### f7_union_employer_relations
**119,445 rows** -- Links unions (by FNUM) to their organized employers.
Many-to-many relationship: one employer can have multiple unions, one union can have multiple employers.
Core training data for the scoring model -- "what does an organized workplace look like?"

### ar_membership
**216,508 rows** -- Annual Report membership counts by union and year.
Historical membership numbers from OLMS filings.
Used for trend analysis and union size tracking.

### ar_assets_investments
**304,816 rows** -- Annual Report financial data: union assets and investments.
Balance sheet items from OLMS filings.
Used for union financial health analysis.

### ar_disbursements_emp_off
**2,813,248 rows** -- Annual Report disbursements to employees and officers.
Detailed compensation data for union staff and elected officials.
Largest AR table; used for union governance/transparency analysis.

### ar_disbursements_total
**216,372 rows** -- Annual Report total disbursements by category.
Summarized spending: representation, political, overhead, admin, etc.
One row per union per year per disbursement category.

### f7_fnum_crosswalk
**2,693 rows** -- Maps variant FNUMs to canonical union identifiers.
Handles FNUM changes from mergers, rechartering, or data entry inconsistencies.
Must be consulted when resolving union identity.

### f7_name_inference_rules
**23 rows** -- Rules for standardizing union names from F7 filings.
Maps abbreviations and variants to canonical forms (e.g., "INTL" -> "International").
Used during ETL ingestion.

### f7_adjustment_factors
**76 rows** -- Score adjustment multipliers by industry or category.
Calibrates raw scores to account for industry-specific organizing patterns.
Applied during unified scorecard computation.

### f7_federal_scores
**9,305 rows** -- Pre-computed scores for federal-sector employers.
Federal employers scored separately due to different bargaining framework (FLRA vs. NLRB).
Joined into the unified scorecard pipeline.

### f7_industry_scores
**121,433 rows** -- Industry-level scoring factors per employer.
Pre-computed NAICS-based signals: density, growth rate, comparable activity.
Fed into the unified scorecard's Industry pillar.

### f7_employer_merge_log
**21,608 rows** -- Audit trail of employer deduplication merges.
Records which raw `f7_employers` records were merged and why.
Used for data lineage and merge reversal.

### union_hierarchy
**26,665 rows** -- Parent-child relationships between unions.
Maps locals to their internationals, districts, and joint councils.
Essential for aggregating membership and activity up the union tree.

### union_names_crosswalk
**171,481 rows** -- Maps variant union name spellings to canonical identifiers.
Handles abbreviations, misspellings, and historical name changes.
Used by the matching pipeline for union name resolution.

### union_name_variants
**43 rows** -- Known alternate names/abbreviations for major unions.
Manual reference table for common variant mappings (e.g., "SEIU" vs "Service Employees").
Supplements the automated crosswalk.

### union_naics_mapping
**7,624 rows** -- Maps unions to their primary NAICS industries.
Derived from F7 employer data -- which industries each union organizes in.
Used for industry-based scoring and research targeting.

### union_organization_level
**19,536 rows** -- Classifies unions by level: national, intermediate, local.
Derived from `desig_name` codes in `unions_master`.
Used for filtering and aggregation.

### union_sector
**6 rows** -- Sector lookup: private, federal, state, local, mixed, unknown.
Reference table mapping sector codes to labels.
Joined to employer records for sector-based analysis.

### union_match_status
**6 rows** -- Status codes for union identity resolution.
Lookup table: matched, unmatched, ambiguous, manual, etc.
Used by the union crosswalk pipeline.

### union_fnum_resolution_log
**166 rows** -- Audit trail of FNUM resolution decisions.
Records when and why an FNUM was mapped to a canonical union.
Data lineage for union identity resolution.

### nhq_reconciled_membership
**132 rows** -- Reconciled membership numbers for national headquarters unions.
Aggregated membership from locals vs. NHQ-reported totals.
Used to validate membership data consistency.

### crosswalk_unions_master
**50,039 rows** -- Extended union crosswalk with affiliation and sector mappings.
Links unions across naming conventions and data sources.
Broader than `unions_master` -- includes historical/inactive entries.

### crosswalk_affiliation_sector_map
**111 rows** -- Maps union affiliations (AFL-CIO, CtW, independent) to sectors.
Reference table for union political/organizational alignment.
Used in research agent dossier generation.

### crosswalk_f7_only_unions
**167 rows** -- Unions that appear only in F7 data, not in other sources.
Identifies unions with no NLRB, public sector, or web presence.
Used for coverage gap analysis.

### crosswalk_sector_lookup
**6 rows** -- Sector code definitions.
Simple lookup: private, public-federal, public-state, public-local, etc.
Shared across crosswalk tables.

### teamsters_official_locals
**338 rows** -- Official Teamsters local union directory.
Manually curated list with local numbers, cities, and jurisdictions.
Used for Teamsters-specific research and validation.

---

## 2. NLRB Elections & Cases

### nlrb_elections
**33,096 rows** -- NLRB representation election records with outcomes.
Win/loss, vote tallies, dates, employer, and petitioning union.
Core input to the NLRB scoring factor and win-rate reference tables.

### nlrb_participants
**1,906,542 rows** -- Parties involved in NLRB cases (unions, employers, individuals).
Links cases to specific unions and employers.
Used for employer-union relationship mapping.

### nlrb_cases
**477,688 rows** -- All NLRB case records: ULP charges, elections, amendments.
Master case table with case number, type, status, region, dates.
Parent table for allegations, docket entries, and filings.

### nlrb_allegations
**715,805 rows** -- Individual allegations within NLRB cases.
Specific ULP charges: Section 8(a)(1), 8(a)(3), 8(a)(5), etc.
Used for enforcement pattern analysis and allegation weighting.

### nlrb_case_types
**13 rows** -- NLRB case type codes: RC (certification), CA (ULP-employer), CB (ULP-union), etc.
Lookup table for case classification.
Joined to `nlrb_cases` for filtering.

### nlrb_docket
**2,046,151 rows** -- NLRB case docket entries (filings, orders, decisions).
Chronological case activity log.
Used for case timeline analysis and status tracking.

### nlrb_election_results
**33,096 rows** -- Detailed election outcome data.
Vote counts by union, challenges, objections, runoff indicators.
Companion to `nlrb_elections` with additional result detail.

### nlrb_filings
**498,749 rows** -- Documents filed in NLRB cases.
Charges, petitions, responses, and briefs.
Used for case progression analysis.

### nlrb_regions
**31 rows** -- NLRB regional office lookup.
Region number, city, states covered.
Reference table for geographic analysis of NLRB activity.

### nlrb_sought_units
**52,078 rows** -- Bargaining units sought in NLRB petitions.
Job classifications, unit size, and scope proposed by petitioning unions.
Used for unit size analysis and win-rate modeling.

### nlrb_tallies
**67,779 rows** -- Vote tallies from NLRB elections.
Votes for/against, challenged ballots, eligible voters.
Primary source for election outcome statistics.

### nlrb_union_xref
**73,326 rows** -- Cross-reference between NLRB union identifiers and canonical FNUMs.
Maps NLRB union names/codes to `unions_master` records.
Essential for linking NLRB data to the rest of the system.

### nlrb_employer_xref
**13,031 rows** -- Cross-reference between NLRB employer records and F7 employers.
Maps NLRB employer names to `f7_employers_deduped` via deterministic matching.
Enables NLRB scoring factor computation.

### nlrb_voluntary_recognition
**1,681 rows** -- Voluntary recognition events (card check).
Employers that recognized unions without an NLRB election.
Important organizing outcome data outside the election pipeline.

### nlrb_voting_units
**31,643 rows** -- Certified/established bargaining units from NLRB elections.
Unit descriptions, included/excluded classifications, unit size.
Used for unit composition analysis.

### ref_nlrb_industry_win_rates
**24 rows** -- NLRB election win rates by industry sector.
Pre-computed reference: healthcare 65%, manufacturing 48%, etc.
Used in the scorecard's NLRB factor.

### ref_nlrb_size_win_rates
**8 rows** -- NLRB election win rates by unit size bracket.
Smaller units win more often: <25 employees ~72%, 500+ ~38%.
Used in the scorecard's NLRB factor.

### ref_nlrb_state_win_rates
**54 rows** -- NLRB election win rates by state.
Geographic variation in election outcomes.
Used in the scorecard's NLRB factor.

---

## 3. Enforcement & Workplace Conditions

### osha_establishments
**1,007,217 rows** -- OSHA-inspected establishments with name, address, NAICS, size.
Primary workplace safety data. Columns: `site_city`, `site_state`, `site_zip` (not plain city/state/zip).
Matched to F7 employers; feeds the "Anger" scoring pillar.

### osha_violations_detail
**2,245,020 rows** -- Individual OSHA violation records with penalties and severity.
Willful, serious, repeat, and other-than-serious violations.
Joined to establishments for per-employer violation profiles.

### osha_violation_summary
**872,163 rows** -- Aggregated violation statistics per establishment.
Total violations, penalties, inspection count. Joins on `establishment_id` (not `activity_nr`).
Pre-computed summary for scorecard consumption.

### osha_accidents
**63,066 rows** -- OSHA accident/fatality reports.
Workplace deaths, hospitalizations, and amputations.
Highest-severity enforcement signal.

### osha_unified_matches
**42,812 rows** -- OSHA establishments matched to F7 employers via unified pipeline.
Result of the 6-tier deterministic matching cascade.
Links enforcement data to union employer records.

### osha_f7_matches
**83,763 rows** -- Direct OSHA-to-F7 match results with confidence scores.
Broader than unified matches; includes lower-confidence matches.
Used for the Anger pillar scoring.

### unified_employers_osha
**100,766 rows** -- Deduplicated OSHA employers with canonical names.
Intermediate table in the OSHA matching pipeline.
Groups OSHA establishments by employer identity.

### ref_osha_industry_averages
**340 rows** -- Average OSHA violation rates by NAICS industry.
Benchmark: is an employer's violation rate above/below industry norm?
Used for relative scoring in the Anger pillar.

### whd_cases
**363,365 rows** -- DOL Wage & Hour Division cases (2005-2025).
FLSA violations, backwages, civil monetary penalties by employer.
Second Anger pillar signal -- wage theft correlates with organizing potential.

### whd_f7_matches
**17,145 rows** -- WHD cases matched to F7 employers.
Deterministic match results with confidence tiers.
Enables wage violation scoring.

### mv_whd_employer_agg *(Materialized View)*
**330,419 rows** -- Aggregated WHD case statistics per employer.
Total backwages, penalty amounts, case counts, violation types.
Ready-to-join summary for the scorecard pipeline.

---

## 4. BLS Labor Statistics

### oes_occupation_wages
**414,437 rows** -- Occupational Employment & Wage Statistics (2024).
Wage percentiles (10th-90th), means, employment counts by occupation x area x industry.
Shows what workers earn: nursing assistants median $39K, RNs $82K, etc.

### mv_oes_area_wages *(Materialized View)*
**224,039 rows** -- OES data pivoted for area-level wage comparisons.
Pre-computed area x occupation wage benchmarks for scorecard and research.
Enables "what do workers earn in this area?" queries.

### bls_soii_series
**891,324 rows** -- Survey of Occupational Injuries & Illnesses series definitions.
Series metadata: industry, case type, data type, area.
Lookup table for `bls_soii_data`.

### bls_soii_data
**5,691,796 rows** -- SOII data points (2014-2024).
Injury/illness rates, counts, and days away by industry.
Nursing homes: 6.3/100 FTE (2024), spiked to 13.1 during COVID.

### mv_soii_industry_rates *(Materialized View)*
**45,592 rows** -- Pre-computed industry injury rates from SOII.
Total recordable, DART, and DAFW rates by NAICS and year.
Ready-to-join for scorecard and research dossiers.

### bls_soii_area
**236 rows** -- SOII geographic area codes.
State FIPS and area name lookup.
Reference table for SOII series.

### bls_soii_case_type
**20 rows** -- SOII case type codes (total, DART, DAFW, etc.).
Lookup table for injury classification.
Joined to SOII series for filtering.

### bls_soii_data_type
**36 rows** -- SOII data type codes (rate, count, median days, etc.).
Lookup table for measurement type.
Joined to SOII series for filtering.

### bls_soii_industry
**1,305 rows** -- SOII industry codes and names.
Industry lookup for SOII. Note: `623100` = nursing care (not `623110`), `623000` = nursing + residential.
Reference table for SOII series.

### bls_soii_supersector
**14 rows** -- SOII supersector codes (goods-producing, service-providing, etc.).
High-level industry grouping.
Reference table for SOII series.

### bls_jolts_series
**1,984 rows** -- Job Openings & Labor Turnover Survey series definitions.
Series metadata: industry, data element, rate/level, state, size class.
Lookup table for `bls_jolts_data`.

### bls_jolts_data
**369,636 rows** -- JOLTS data points: hires, quits, separations, openings.
Monthly turnover metrics by industry (2000-2024).
Healthcare quit rate 2.2%, job opening rate 6.5%.

### mv_jolts_industry_rates *(Materialized View)*
**63,012 rows** -- Pre-computed JOLTS turnover rates by industry and period.
Quit rate, hire rate, separation rate, openings rate.
High turnover = organizing opportunity signal.

### bls_jolts_dataelement
**8 rows** -- JOLTS data element codes: JO, HI, QU, TS, LD, OS.
Lookup: job openings, hires, quits, total separations, layoffs, other separations.
Reference table for JOLTS series.

### bls_jolts_industry
**28 rows** -- JOLTS industry codes and names.
Broad industry groupings for turnover data.
Reference table for JOLTS series.

### bls_jolts_ratelevel
**2 rows** -- JOLTS rate vs. level indicator.
R = rate (per 100), L = level (thousands).
Reference table for JOLTS series.

### bls_jolts_sizeclass
**7 rows** -- JOLTS establishment size classes.
1-9, 10-49, 50-249, 250-999, 1000-4999, 5000+ employees.
Reference table for JOLTS series.

### bls_jolts_state
**56 rows** -- JOLTS state/region codes.
State FIPS + regions (NE, SO, MW, WE) + national.
Reference table for JOLTS series.

### bls_ncs_series
**100,124 rows** -- National Compensation Survey series definitions.
Series metadata: industry, ownership, provision type, estimate type.
Lookup table for `bls_ncs_data`.

### bls_ncs_data
**768,207 rows** -- NCS data points: benefit access, participation, take-up rates.
What benefits workers get (or don't). Healthcare industry: only 64% have medical + retirement.
Used for benefits gap analysis.

### mv_ncs_benefits_access *(Materialized View)*
**592,896 rows** -- Pre-computed NCS benefits access rates by industry.
Medical, retirement, paid leave, life insurance access percentages.
Ready-to-join for scorecard and research.

### bls_ncs_datatype
**16 rows** -- NCS data type codes (access, participation, take-up rate, etc.).
Lookup table for measurement classification.
Reference table for NCS series.

### bls_ncs_estimate
**44 rows** -- NCS estimate type codes.
Lookup: percent of workers, median, mean, flat rate, etc.
Reference table for NCS series.

### bls_ncs_industry
**30 rows** -- NCS industry codes and names.
Broad industry groupings for compensation data.
Reference table for NCS series.

### bls_ncs_ownership
**5 rows** -- NCS ownership codes: private, state/local, all.
Reference table for NCS series.
Distinguishes private-sector from public-sector compensation.

### bls_ncs_provision
**1,219 rows** -- NCS provision codes (specific benefit types).
Detailed benefit categories: medical plan type, retirement plan type, leave type.
Reference table for NCS series.

### bls_ncs_subcell
**53 rows** -- NCS subcell codes for benefit breakdown dimensions.
Cross-tabs: by occupation group, wage quartile, union status, etc.
Reference table for NCS series.

### qcew_annual
**1,943,426 rows** -- Quarterly Census of Employment & Wages (annual averages).
Employment, wages, and establishment counts by county x NAICS industry.
Contextual benchmark for local labor market conditions.

### mv_qcew_state_industry_wages *(Materialized View)*
**4,142 rows** -- Pre-computed QCEW state x industry average wages.
State-level wage benchmarks by NAICS sector.
Used for geographic wage comparisons.

### qcew_industry_density
**7,143 rows** -- Union density estimates derived from QCEW + BLS density data.
Industry-level union membership rates at state granularity.
Feeds the Union Proximity scoring factor.

### bls_industry_density
**12 rows** -- National union density by broad industry sector.
BLS Current Population Survey data: construction 12.4%, healthcare 6.1%, etc.
Core reference for industry-level union presence.

### bls_state_density
**51 rows** -- Union membership rates by state.
BLS CPS data: NY 21.5%, SC 1.7%, etc.
Core reference for geographic union presence.

### bls_national_industry_density
**9 rows** -- National union density by major industry group.
Broader grouping than `bls_industry_density`.
Used for high-level industry comparisons.

### state_sector_union_density
**6,191 rows** -- Union density by state x sector (private/public) x year.
Time-series density data for trend analysis.
Feeds the Union Proximity scoring factor.

### bls_union_series
**1,232 rows** -- BLS union membership survey series definitions.
Series metadata linking to `bls_union_data`.
Reference table for CPS union data.

### bls_union_data
**31,007 rows** -- BLS union membership data points by series and year.
Historical union membership rates, counts, and coverage (1978-2025).
Primary source for density trends.

### bls_industry_occupation_matrix
**67,699 rows** -- BLS staffing patterns: NAICS x SOC employment shares.
Maps industries to their typical occupations with employment percentages.
Used for occupation similarity scoring (Gower distance) and industry profiling.

### bls_occupation_lookup
**30 rows** -- BLS occupation group codes and names.
Reference table for occupation classifications.
Used in staffing pattern analysis.

### bls_occupation_projections
**1,113 rows** -- BLS employment projections by occupation (2023-2033).
Projected growth/decline rates and job openings.
Contextual data for occupation trend analysis.

### bls_industry_lookup
**39 rows** -- BLS industry codes used in density tables.
Maps BLS industry codes to descriptive names.
Reference table for density data.

### bls_industry_projections
**423 rows** -- BLS employment projections by industry (2023-2033).
Projected employment changes and growth rates.
Contextual data for industry trend analysis.

### bls_fips_lookup
**52 rows** -- FIPS codes for states/territories.
State FIPS to name/abbreviation mapping.
Reference table for geographic lookups.

### bls_naics_mapping
**22 rows** -- Maps BLS industry codes to NAICS sectors.
Crosswalk between BLS industry classification and standard NAICS.
Used when joining BLS density data to NAICS-coded records.

### bls_naics_sector_map
**231 rows** -- Broader NAICS-to-BLS sector mapping.
Maps 2-6 digit NAICS codes to BLS density sectors.
Used for industry-level density lookups.

---

## 5. O*NET Occupational Data

### onet_occupations
**1,016 rows** -- O*NET SOC occupation definitions.
Occupation codes, titles, and descriptions from O*NET 29.1.
Master reference for all O*NET content.

### onet_skills
**62,580 rows** -- Skill requirements by occupation (importance + level).
35 skills rated for each SOC code: critical thinking, negotiation, etc.
Used for occupation similarity and workforce profiling.

### onet_knowledge
**59,004 rows** -- Knowledge domain requirements by occupation.
33 knowledge areas: administration, customer service, law, medicine, etc.
Used for occupation profiling.

### onet_abilities
**92,976 rows** -- Cognitive and physical ability requirements by occupation.
52 abilities: oral comprehension, manual dexterity, stamina, etc.
Used for occupation similarity scoring.

### onet_tasks
**18,796 rows** -- Specific work tasks by occupation.
Detailed task descriptions with importance ratings.
Used for job content analysis.

### onet_work_activities
**73,308 rows** -- Generalized work activities by occupation.
41 activity dimensions: communicating, decision-making, inspecting, etc.
Used for occupation clustering and similarity.

### onet_work_context
**297,676 rows** -- Work environment conditions by occupation.
Physical conditions, interpersonal relationships, structural characteristics.
Used for workplace condition analysis.

### onet_work_values
**7,866 rows** -- Work values/needs by occupation (achievement, independence, etc.).
6 value dimensions rated for each occupation.
Contextual data for occupation profiling.

### onet_education
**37,125 rows** -- Education requirements by occupation.
Typical education level, related experience, on-the-job training.
Used for workforce education profiling.

### onet_job_zones
**923 rows** -- O*NET job zone classifications (1-5 scale of preparation needed).
Maps occupations to experience/education/training requirements.
Reference table for occupation complexity.

### onet_alternate_titles
**57,543 rows** -- Alternative occupation titles and keywords.
Maps common job titles to SOC codes (e.g., "CNA" -> 31-1131).
Used for occupation name resolution in matching.

### onet_content_model
**630 rows** -- O*NET content model element definitions.
Taxonomy of skills, knowledge, abilities, and work context dimensions.
Metadata reference for O*NET data structure.

### onet_scales
**31 rows** -- O*NET rating scale definitions (importance, level, extent).
Scale IDs and descriptions used across O*NET tables.
Reference table for interpreting O*NET ratings.

### occupation_similarity
**8,731 rows** -- Pre-computed Gower distance between occupation pairs.
Top-N most similar SOC pairs for each occupation.
Used in employer comparables and scoring.

### industry_occupation_overlap
**130,638 rows** -- Shared occupation profiles between industry pairs.
Measures how similar two industries are based on workforce composition.
Used for industry similarity scoring.

---

## 6. Corporate Identity & Hierarchy

### sec_companies
**517,403 rows** -- SEC EDGAR company registrations.
CIK, EIN, LEI, SIC code, name, state of incorporation.
Links public companies to F7 employers via the corporate crosswalk.

### gleif_us_entities
**379,192 rows** -- US legal entities from the GLEIF LEI database.
Legal Entity Identifier, legal name, headquarters address, entity status.
Used for LEI-based exact matching in the corporate crosswalk.

### gleif_ownership_links
**498,963 rows** -- Parent-subsidiary ownership relationships from GLEIF.
Direct/ultimate parent LEI links with ownership percentages.
Maps corporate parent-subsidiary hierarchies.

### corpwatch_companies
**1,421,198 rows** -- Companies parsed from SEC filings by CorpWatch.
CIK, name, SIC code, filing year, IRS number.
Deepest corporate genealogy data available.

### corpwatch_relationships
**3,517,388 rows** -- Parent-subsidiary relationships from CorpWatch.
Links company IDs with relationship type and year.
Multi-year corporate family tree.

### corpwatch_subsidiaries
**4,463,030 rows** -- Subsidiary records from SEC Exhibit 21 filings.
Subsidiary name, state/country of incorporation, parent CIK.
Largest corporate structure table.

### corpwatch_names
**2,435,330 rows** -- Historical company names from SEC filings.
Name, CIK, filing date -- tracks name changes over time.
Used for historical name matching.

### corpwatch_locations
**2,622,962 rows** -- Company addresses from SEC filings.
Street, city, state, zip, country by CIK and year.
Used for geographic matching.

### corpwatch_filing_index
**208,503 rows** -- SEC filing index from CorpWatch.
Filing type, date, CIK -- metadata for CorpWatch data provenance.
Tracks which filings were parsed.

### corpwatch_f7_matches
**3,057 rows** -- CorpWatch companies matched to F7 employers.
Match results linking SEC/CIK data to union employer records.
Part of the corporate identity crosswalk.

### corporate_identifier_crosswalk
**25,113 rows** -- Rosetta Stone linking SEC CIK, GLEIF LEI, Mergent DUNS, CorpWatch ID, F7 employer_id.
Connects disparate corporate identifiers across data sources.
Enables financial and governance data to flow to union employer records.

### corporate_hierarchy
**129,103 rows** -- Resolved corporate parent-child relationships.
Unified hierarchy from SEC, GLEIF, and CorpWatch sources.
Used for roll-up analysis and corporate family identification.

### mergent_employers
**70,426 rows** -- Companies from Mergent/D&B with DUNS, EIN, sales, employees.
Financial signal source: annual sales and employee counts.
Mergent xlsx files have .csv extension; dirs 37+ have Sales/Employee/NAICS columns.

### mergent_import_progress
**127 rows** -- Tracks Mergent data import status by directory.
Records which Mergent directories have been imported and row counts.
ETL management table.

---

## 7. Federal Contracting & Tax Data

### sam_entities
**826,042 rows** -- SAM.gov federal contractor registrations.
UEI, CAGE code, NAICS, entity structure, physical address.
Columns: `physical_city`, `physical_state`, `physical_zip` (not plain city/state/zip).

### sam_f7_matches
**24,208 rows** -- SAM entities matched to F7 employers.
Federal contractor-to-union employer links.
Very low match rate; mostly identifies government contractor status.

### federal_agencies
**192 rows** -- Federal agency names and codes.
Reference table for federal employer identification.
Used in federal bargaining unit analysis.

### federal_bargaining_units
**2,183 rows** -- Federal-sector bargaining units recognized by FLRA.
Agency, union, unit description, exclusive recognition status.
Separate from NLRB private-sector pipeline.

### federal_contract_recipients
**47,193 rows** -- Employers receiving federal contracts.
Aggregated from USAspending data by employer.
Identifies government-dependent employers.

### national_990_filers
**586,767 rows** -- Tax-exempt organizations filing Form 990.
EIN, name, NTEE code, total revenue, total assets, filing year.
Identifies nonprofit employers (hospitals, universities).

### national_990_f7_matches
**20,005 rows** -- Form 990 filers matched to F7 union employers.
Links nonprofit tax data to union employer records.
Enables nonprofit governance and compensation analysis.

### employers_990
**5,942 rows** -- Employers identified through Form 990 data.
Subset of 990 filers confirmed as employers with union relationships.
Pre-deduplication table.

### employers_990_deduped
**1,046,167 rows** -- Deduplicated 990-sourced employer records.
Cleaned and standardized nonprofit employer data.
Feeds into master employer pipeline.

### employer_990_matches
**514 rows** -- Direct employer-to-990 matches.
High-confidence links between employer records and 990 filings.
Used for nonprofit financial data enrichment.

### form_990_estimates
**39 rows** -- Estimated financial metrics derived from Form 990.
Revenue, compensation, and program expense estimates by category.
Reference data for nonprofit benchmarking.

### labor_orgs_990
**19,367 rows** -- Labor organizations filing Form 990.
Unions and labor councils that file as 501(c)(5) organizations.
Links union financial data from IRS to OLMS data.

### labor_orgs_990_deduped
**15,172 rows** -- Deduplicated labor organization 990 records.
Cleaned union 990 data with canonical identifiers.
Used for union financial analysis.

### labor_990_olms_crosswalk
**5,522 rows** -- Links labor org 990 EINs to OLMS FNUMs.
Crosswalk between IRS and DOL union identifiers.
Enables combined financial analysis.

### irs_bmf
**2,043,472 rows** -- IRS Business Master File of tax-exempt organizations.
EIN, name, NTEE code, subsection, ruling date, asset/revenue codes.
Broadest tax-exempt org data; supplements 990s with classification info.

### cur_form5500_sponsor_rollup
**259,645 rows** -- Form 5500 plan sponsors aggregated by EIN.
Pension/welfare plan count, participant totals, collectively bargained flag.
Shows whether employers offer retirement/health benefits.

### cur_ppp_employer_rollup
**9,553,556 rows** -- PPP loan borrowers with amounts, forgiveness, jobs.
COVID-era employer size/financial signal.
Reveals actual employee counts and federal aid received.

### cur_usaspending_recipient_rollup
**94,189 rows** -- Federal contract recipients from USAspending.
Obligated amounts, fiscal years, agency, recipient name.
Federal contract dependency signal.

### usaspending_f7_matches
**9,305 rows** -- USAspending recipients matched to F7 employers.
Links federal contract data to union employer records.
Used for government contractor scoring.

### contract_employer_matches
**8,954 rows** -- Matches between government contracts and employers.
Cross-source contract-to-employer linkages.
Supplements SAM and USAspending matching.

### flra_olms_union_map
**40 rows** -- Maps FLRA union identifiers to OLMS FNUMs.
Crosswalk for federal-sector union identity resolution.
Used when linking FLRA bargaining data to OLMS records.

---

## 8. Census & Demographics

### cur_acs_workforce_demographics
**11,478,933 rows** -- ACS workforce demographics by state x metro x industry x occupation x demographics.
Gender, race, age, education distributions. 77% female in NJ healthcare, etc.
Insurance columns pending pipeline re-run.

### cur_cbp_geo_naics
**1,488,919 rows** -- County Business Patterns: establishments, employment, payroll by county x NAICS.
Local market context: how many nursing homes in a county, how many employees.
Used for employer density and market saturation analysis.

### cur_lodes_geo_metrics
**3,029 rows** -- LEHD Origin-Destination Employment Statistics by county.
Commuting patterns, earnings tiers, industry mix.
Passaic County: 707K jobs, 15.7% healthcare.

### cur_abs_geo_naics
**112,483 rows** -- Annual Business Survey: firm demographics by state x NAICS.
Owner race, sex, veteran status.
Business ownership diversity data for contextual research.

### census_rpe_ratios
**261,853 rows** -- Revenue-per-employee ratios from Economic Census.
RPE by NAICS x geography for benchmarking.
Identifies employers with abnormal revenue/employee ratios.

### census_industry_naics_xwalk
**24,373 rows** -- Census industry codes to NAICS crosswalk.
Maps Census industry classification to standard NAICS.
Used when ingesting ACS/Census data.

### census_occupation_soc_xwalk
**34,540 rows** -- Census occupation codes to SOC crosswalk.
Maps Census occupation classification to standard SOC.
Used when ingesting ACS/Census data.

### cbsa_definitions
**935 rows** -- Core-Based Statistical Area definitions.
CBSA code, name, type (metropolitan/micropolitan), principal city.
Reference table for metro area geography.

### cbsa_counties
**1,915 rows** -- Counties within each CBSA.
Maps FIPS county codes to CBSA metro/micro areas.
Used for geographic aggregation.

---

## 9. Geographic & NAICS Reference

### state_lookup
**52 rows** -- State/territory name and abbreviation lookup.
FIPS, abbreviation, full name.
Primary state reference table.

### state_abbrev
**51 rows** -- State abbreviation to full name mapping.
Simple two-column reference.
Used for display and normalization.

### state_fips_map
**54 rows** -- State FIPS codes to names/abbreviations.
Includes territories (PR, GU, VI, AS, MP).
Used for FIPS-based geographic joins.

### zip_county_crosswalk
**39,366 rows** -- ZIP code to county FIPS mapping.
Column is `zip_code` (not `zip`). Many-to-many: ZIPs can span counties.
Essential for geographic normalization.

### naics_codes_reference
**4,323 rows** -- NAICS code definitions (2-6 digit).
Code, title, description for all NAICS levels.
Primary industry classification reference.

### naics_sectors
**24 rows** -- NAICS 2-digit sector codes and names.
Top-level industry grouping: 62=Healthcare, 23=Construction, etc.
Used for sector-level aggregation.

### naics_sic_crosswalk
**2,163 rows** -- NAICS to SIC code crosswalk.
Maps modern NAICS to legacy SIC codes.
Used when integrating older data sources (SEC, CorpWatch).

### naics_to_bls_industry
**2,035 rows** -- NAICS codes to BLS industry classification.
Maps NAICS to BLS density data industry codes.
Used for union density lookups by NAICS.

### naics_version_crosswalk
**4,607 rows** -- Crosswalk between NAICS vintages (2012, 2017, 2022).
Maps codes across NAICS revision years.
Used when reconciling data from different NAICS eras.

### sector_lookup
**6 rows** -- Sector code definitions (private, public, etc.).
Simple reference table.
Shared across scoring and classification tables.

### ref_rtw_states
**27 rows** -- Right-to-work state list.
States with right-to-work laws (affects organizing dynamics).
Used as a scoring factor modifier.

---

## 10. Union Density & Benchmarks

### epi_union_membership
**1,420,064 rows** -- Economic Policy Institute union membership microdata.
Individual-level CPS records with union status, demographics, wages.
Richest union membership dataset for research analysis.

### epi_state_benchmarks
**51 rows** -- EPI state-level benchmark statistics.
Union coverage, wage premiums, benefit differentials by state.
Used for state-level organizing context.

### unionstats_state
**10,710 rows** -- UnionStats.com state-level density by year.
Historical union density time series (1964-2024) by state.
Primary source for state density trends.

### unionstats_industry
**281 rows** -- UnionStats.com industry-level density.
Union density by CPS industry classification.
Historical industry density reference.

### estimated_state_industry_density
**459 rows** -- Estimated union density by state x industry.
Modeled estimates where direct measurement is unavailable.
Fills gaps in BLS density data.

### county_union_density_estimates
**3,144 rows** -- Estimated union density at the county level.
Modeled from state/industry data + geographic proxies.
Used for sub-state geographic scoring.

### county_industry_shares
**3,144 rows** -- Industry employment shares by county.
Distribution of employment across NAICS sectors per county.
Used for county-level industry profiling.

### county_workforce_shares
**3,144 rows** -- Workforce characteristic shares by county.
Demographic and occupational composition per county.
Companion to `county_industry_shares`.

### state_industry_shares
**51 rows** -- Industry employment distribution by state.
Share of employment in each NAICS sector per state.
Used for state-level industry context.

### state_workforce_shares
**51 rows** -- Workforce characteristics by state.
Education, occupation, demographic distributions per state.
Used for state-level workforce profiling.

### state_coverage_comparison
**51 rows** -- Comparison of union coverage vs. membership by state.
Highlights "free rider" gap between coverage and dues-paying membership.
Used for right-to-work analysis.

### state_industry_density_comparison
**51 rows** -- State industry density vs. national benchmarks.
Shows whether a state's industry unionization is above/below national average.
Used for relative positioning analysis.

### state_govt_level_density
**51 rows** -- Union density by government level (federal, state, local) per state.
Public-sector density breakdown.
Supplements private-sector density data.

### msa_union_stats
**1,505 rows** -- Union statistics by Metropolitan Statistical Area.
Membership, coverage, and density at the MSA level.
Used for metro-level geographic analysis.

### public_sector_benchmarks
**51 rows** -- Public sector union density and compensation benchmarks by state.
Reference data for public-sector organizing context.
Used alongside private-sector benchmarks.

### vr_affiliation_patterns
**29 rows** -- Voluntary recognition patterns by union affiliation.
Win rates and frequency of card-check recognition by union.
Reference data for organizing strategy analysis.

### vr_status_lookup
**4 rows** -- Voluntary recognition status codes.
Active, withdrawn, pending, resolved.
Reference table for `nlrb_voluntary_recognition`.

---

## 11. Master Employer & Deduplication

### master_employers
**4,546,912 rows** -- Canonical employer registry across all sources.
PK is `master_id` (not `id`), name is `display_name` (not `name`).
The unified employer table -- every employer from every source deduplicated.

### master_employer_source_ids
**6,215,181 rows** -- Links master employer records to source system IDs.
Maps `master_id` to F7, OSHA, WHD, SAM, NLRB, 990, etc. source records.
Essential for tracing data lineage.

### master_employer_merge_log
**699,191 rows** -- Audit trail of master employer merges.
Records which source records were merged into which master records.
Used for data lineage and merge quality analysis.

### master_employer_dedup_progress
**4 rows** -- Tracks deduplication pipeline progress.
Records batch numbers and completion status.
ETL management table.

### employer_canonical_groups
**16,647 rows** -- Groups of employers identified as the same entity.
Clustering results from the deduplication pipeline.
Used for merge candidate review.

### historical_merge_candidates
**5,128 rows** -- Historical merge candidate pairs for review.
Employer pairs flagged as potential duplicates but not yet merged.
Used in the HITL review pipeline.

### deduplication_methodology
**11 rows** -- Documentation of deduplication rules and thresholds.
Records the matching criteria used for each dedup pass.
Metadata/audit table.

### manual_employers
**520 rows** -- Manually entered or corrected employer records.
User-contributed employer data outside automated ETL.
Reviewed and merged into master employers.

### discovered_employers
**32 rows** -- Newly discovered employers from research or web scraping.
Employers found through the research agent or web pipeline.
Pending review and integration.

### employer_review_flags
**13 rows** -- Employers flagged for human review.
Quality issues, ambiguous matches, or data conflicts.
Used in the HITL review workflow.

### employer_wage_outliers
**5,405 rows** -- Employers with wage data significantly above/below norms.
Statistical outliers in wage distributions by industry/geography.
Used for data quality checks and research targeting.

### employer_comparables
**329,785 rows** -- Pre-computed comparable employer pairs (Gower distance).
Top-5 most similar employers for each record.
Feeds the Similarity scoring factor.

---

## 12. Matching Infrastructure

### match_runs
**93 rows** -- Metadata for matching pipeline executions.
Run ID, source, timestamp, parameters, match counts.
Tracks each matching batch for reproducibility.

### match_run_results
**1,175 rows** -- Summary statistics for each match run.
Match rates, tier distributions, quality metrics per run.
Used for match quality monitoring.

### match_rate_baselines
**3 rows** -- Baseline match rates by source.
Expected match rates for OSHA, WHD, SAM -- used for regression detection.
Alerts when match rates drop below baseline.

### match_status_lookup
**6 rows** -- Match status codes: matched, unmatched, ambiguous, manual, rejected, pending.
Reference table for match pipeline status tracking.
Used across all match result tables.

### unified_match_log
**2,207,505 rows** -- Complete audit trail of all matching decisions.
Source record, target record, match tier, confidence score, timestamp.
Master matching log across all source systems.

### splink_match_results
**0 rows** -- Probabilistic matching results from Splink.
Reserved for future probabilistic matching pipeline.
Currently unused; deterministic 6-tier cascade used instead.

### organizing_targets
**5,428 rows** -- Identified organizing targets with scores and status.
Employers flagged as high-potential organizing targets.
Feeds the target scorecard and research pipeline.

### data_source_freshness
**24 rows** -- Tracks last update timestamp for each data source.
Source name, last loaded date, row count, staleness indicator.
Used for monitoring data pipeline health.

### score_versions
**146 rows** -- Score computation version history.
Records parameters and timestamps for each scoring run.
Used for score reproducibility and regression testing.

---

## 13. Scoring Pipeline (Materialized Views)

### mv_organizing_scorecard *(Materialized View)*
**215,303 rows** -- Scores for OSHA establishments as organizing targets.
OSHA-centric scoring: violations, penalties, industry context.
Broader than F7-matched employers.

### mv_unified_scorecard *(Materialized View)*
**146,863 rows** -- Unified scores for F7 union employers across 10 factors, 3 pillars.
The primary scoring output. Tier column is `score_tier` (not `tier`).
After corroboration, low-confidence matches may have `score_eligible=TRUE`.

### mv_target_scorecard *(Materialized View)*
**4,384,210 rows** -- Scores for non-union target employers across 8 signals.
Gold-standard scoring tiers for 4.4M employers.
Identifies high-potential organizing targets not yet unionized.

### mv_employer_search *(Materialized View)*
**107,321 rows** -- Searchable employer index for the API/frontend.
Pre-joined employer attributes optimized for text search.
Powers the frontend search and employer detail pages.

### mv_employer_features *(Materialized View)*
**66,889 rows** -- Feature vectors for employer similarity computation.
NAICS, size, location, industry, workforce attributes.
Input to the Gower distance calculation for comparables.

### mv_employer_data_sources *(Materialized View)*
**146,863 rows** -- Which data sources have records for each F7 employer.
Boolean flags: has_osha, has_whd, has_sam, has_990, etc.
Used for data completeness analysis.

### mv_target_data_sources *(Materialized View)*
**4,400,049 rows** -- Data source coverage for target (non-union) employers.
Boolean flags indicating which sources have data for each target.
Used for target data completeness analysis.

---

## 14. Research Agent & CBA

### research_runs
**138 rows** -- AI research session records.
Run ID, employer, union, timestamp, quality score, status.
Gemini-powered dossier generation tracking.

### research_facts
**4,353 rows** -- Extracted facts from research sessions.
Structured facts with source, confidence, category, validation status.
Human-validated facts feed back into scoring.

### research_score_enhancements
**59 rows** -- Score modifications from validated research.
Quality gate: >=7.0 enhances scores, <5.0 rejected.
Links research findings to scorecard adjustments.

### research_actions
**1,835 rows** -- Research agent actions and web queries.
Tracks what the research agent searched for and found.
Used for research quality analysis.

### research_strategies
**487 rows** -- Research strategy templates and effectiveness.
Predefined research approaches by employer type/industry.
Guides the research agent's query generation.

### research_query_effectiveness
**24 rows** -- Metrics on research query success rates.
Which query patterns yield the most useful facts.
Used for research agent optimization.

### research_notes
**0 rows** -- Free-text research notes by human reviewers.
Manual annotations on research quality.
Currently empty; available for HITL workflow.

### research_run_comparisons
**0 rows** -- Side-by-side comparisons of research run quality.
For A/B testing research agent versions.
Currently empty; reserved for future use.

### research_fact_vocabulary
**64 rows** -- Controlled vocabulary for research fact categories.
Standardized category labels: wages, benefits, safety, grievances, etc.
Ensures consistent fact classification.

### cba_documents
**4 rows** -- Collective bargaining agreement full-text documents.
Contract text with metadata: parties, effective dates, expiration.
Source data for provision extraction.

### cba_provisions
**681 rows** -- Extracted provisions from CBA documents.
Specific contract clauses across 14 categories: wages, grievance, seniority, etc.
Structured data from contract text analysis.

### cba_categories
**14 rows** -- CBA provision category definitions.
Wages, benefits, grievance, seniority, union security, management rights, etc.
Reference table for provision classification.

### cba_reviews
**35 rows** -- Human review records for CBA provision extraction.
Quality validation of automated provision extraction.
Used in the HITL review workflow.

### scrape_jobs
**112 rows** -- Web scraping job definitions and status.
URL patterns, selectors, schedules for automated data collection.
ETL management for web-sourced data.

---

## 15. Public Sector

### ps_parent_unions
**24 rows** -- Major public-sector parent unions.
AFSCME, AFT, NEA, IAFF, FOP, etc.
Reference table for public-sector union hierarchy.

### ps_union_locals
**1,520 rows** -- Public-sector union local chapters.
Local number, name, parent union, state, jurisdiction.
Separate from private-sector F7 data.

### ps_employers
**7,987 rows** -- Public-sector employers (government agencies, school districts).
Entity name, state, level (federal/state/local/school).
Separate employer pipeline from private-sector master employers.

### ps_bargaining_units
**438 rows** -- Public-sector bargaining units.
Unit description, employer, union, recognition date, employee count.
Equivalent of NLRB certification for public sector.

---

## 16. NYC & NY State Regional

### ny_990_filers
**47,614 rows** -- New York State 990 filers.
State-filtered subset of national 990 data.
Used for NY-specific nonprofit research.

### ny_state_contracts
**51,500 rows** -- New York State government contracts.
Contractor name, amount, agency, purpose.
State-level procurement data.

### ny_county_density_estimates
**62 rows** -- Union density estimates for NY counties.
Modeled county-level density for New York State.
Used for NY geographic analysis.

### ny_tract_density_estimates
**5,411 rows** -- Union density estimates at the Census tract level (NY).
Highest-resolution geographic density data.
Used for hyperlocal organizing research.

### ny_zip_density_estimates
**1,826 rows** -- Union density estimates by ZIP code (NY).
ZIP-level density for New York State.
Used for neighborhood-level analysis.

### nyc_contracts
**49,767 rows** -- New York City government contracts.
Vendor name, amount, agency, registration date.
City-level procurement data.

### nyc_debarment_list
**210 rows** -- NYC debarred contractors/employers.
Companies barred from city contracts for labor violations.
Strong signal of employer misconduct.

### nyc_discrimination
**111 rows** -- NYC discrimination complaints/findings.
Employment discrimination records from city agencies.
Used for workplace fairness analysis.

### nyc_local_labor_laws
**568 rows** -- NYC local labor law violation records.
Paid sick leave, freelance protection, fair scheduling violations.
City-specific enforcement data.

### nyc_osha_violations
**3,454 rows** -- OSHA violations in New York City.
NYC-filtered subset of federal OSHA data.
Used for hyperlocal safety analysis.

### nyc_prevailing_wage
**46 rows** -- NYC prevailing wage determinations.
Wage rates for construction and building service trades.
Reference data for NYC labor standards.

### nyc_ulp_closed
**260 rows** -- NYC closed unfair labor practice cases.
Resolved ULP complaints at the city level.
Used for NYC-specific enforcement analysis.

### nyc_ulp_open
**660 rows** -- NYC open/pending unfair labor practice cases.
Active ULP complaints at the city level.
Used for current enforcement activity monitoring.

### nyc_wage_theft_litigation
**54 rows** -- NYC wage theft litigation records.
Court cases involving wage theft in New York City.
Used for enforcement severity analysis.

### nyc_wage_theft_nys
**3,281 rows** -- New York State wage theft enforcement in NYC.
State-level wage theft actions in the city.
Supplements federal WHD data.

### nyc_wage_theft_usdol
**431 rows** -- Federal DOL wage theft enforcement in NYC.
NYC-filtered subset of WHD cases.
Federal enforcement data for the city.

---

## 17. Web Scraping & Discovery

### web_union_profiles
**295 rows** -- Scraped union website profiles.
Union name, URL, mission statement, leadership, contact info.
Qualitative intelligence supplementing structured data.

### web_union_employers
**160 rows** -- Employer mentions found on union websites.
Companies named in union communications, bargaining updates, or contract pages.
Supplements F7 employer data with web-sourced relationships.

### web_union_news
**183 rows** -- News articles and press releases from union websites.
Organizing announcements, contract ratifications, strike notices.
Real-time intelligence on union activity.

### web_union_contracts
**120 rows** -- Contract documents found on union websites.
Links to full-text CBAs and summary pages.
Supplements `cba_documents` with web-sourced contracts.

### web_union_membership
**31 rows** -- Membership data from union websites.
Self-reported membership numbers from union communications.
Used for cross-referencing against OLMS-reported figures.

---

## 18. Platform & System

### platform_users
**0 rows** -- Application user accounts.
Authentication and authorization for the web platform.
Currently empty; platform in development.

---

## Summary Statistics

| Category | Tables | MVs | Total Rows |
|----------|--------|-----|-----------|
| Core Union Data | 29 | 0 | ~4.1M |
| NLRB Elections & Cases | 18 | 0 | ~5.5M |
| Enforcement & Workplace | 10 | 1 | ~7.0M |
| BLS Labor Statistics | 38 | 5 | ~12.6M |
| O*NET Occupational | 15 | 0 | ~848K |
| Corporate Identity | 14 | 0 | ~16.0M |
| Federal Contracting & Tax | 18 | 0 | ~15.3M |
| Census & Demographics | 8 | 0 | ~13.4M |
| Geographic & NAICS Reference | 11 | 0 | ~93K |
| Union Density & Benchmarks | 18 | 0 | ~1.5M |
| Master Employer & Dedup | 11 | 0 | ~11.8M |
| Matching Infrastructure | 8 | 0 | ~2.2M |
| Scoring Pipeline | 0 | 7 | ~5.5M |
| Research Agent & CBA | 12 | 0 | ~7.7K |
| Public Sector | 4 | 0 | ~10K |
| NYC & NY State Regional | 15 | 0 | ~166K |
| Web Scraping & Discovery | 5 | 0 | ~789 |
| Platform & System | 1 | 0 | 0 |
| **Total** | **235** | **13** | **~96M** |

> **Note:** 9 additional tables exist in the database beyond what's cataloged in the 18 categories above (utility/temp tables). The `newsrc_acs_occ_demo_profiles` staging table is consumed by `cur_acs_workforce_demographics` and not listed separately.
