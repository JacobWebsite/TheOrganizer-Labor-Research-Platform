# Labor Relations Research Platform — Strategic Roadmap v11

**Date:** February 6, 2026
**Audience:** Labor Organizations & Organizers
**Approach:** Multi-tiered timeline with data source expansion as primary engine
**Methodology:** Checkpoint-based development with validation at each stage

---

## Part I: What Organizers Can Do Today

The platform currently answers questions that previously required weeks of manual research or simply couldn't be answered at all.

### Questions the Platform Answers Now

**"Which employers in my city/state have unions?"**
Search 99,907 employers across private sector (F-7 bargaining notices), public sector (7,987 government employers), and NLRB election records. Filter by city, metro area, state, NAICS industry, or union affiliation. Every employer links to the union local that represents its workers.

**"Where is my union organizing — and where should we be?"**
For any of 26,665 unions tracked through OLMS filings, see every employer covered by a bargaining agreement, the number of workers at each site, OSHA safety violations, NLRB election history, and government contracts. The 6-factor organizing scorecard (0-100 points) ranks potential targets by safety violations, industry density, establishment size, NLRB momentum, and government contract leverage.

**"How has union membership changed over time in my state?"**
16 years of historical membership data (2010-2024) with national, state, and affiliation breakdowns. Compare growth/decline across unions, industries, and geographies.

**"Which non-union employers should we target?"**
14,240 employers across 11 sectors scored on a 62-point organizing scorecard. Identifies TOP/HIGH/MEDIUM priority targets using OSHA violations, wage theft records, NLRB activity, government contracts, and industry density. The AFSCME NY case study identified 5,428 targets with $18.35B in government funding.

**"What's the union density in my area?"**
Industry-weighted density estimates for all 50 states, 3,144 counties, and (for New York) 1,826 ZIP codes and 5,411 census tracts. See how your area compares to national rates and whether the local "union climate" is strong or weak.

**"Which employers have the worst safety records?"**
1,007,217 OSHA-covered workplaces and 2,245,020 violations ($3.52B in penalties) linked to employer bargaining data. Search by severity, penalty amount, or violation type.

### Current Data Assets

| Asset | Records | What It Provides |
|-------|---------|-----------------|
| OLMS Union Filings | 26,665 unions | Membership, finances, leadership, hierarchy |
| F-7 Employer Notices | 63,118 employers | Private sector bargaining relationships |
| NLRB Elections | 33,096 elections | Win rates, petitioning unions, outcomes |
| OSHA Establishments | 1,007,217 | Workplace safety records, violations |
| Public Sector | 1,520 locals, 7,987 employers | State/local/federal government unions |
| Mergent Employers | 14,240 (11 sectors) | Corporate data for organizing targets |
| NYC Violations | 8,800+ records | Wage theft, ULP, discrimination |
| Historical Trends | 16 years (2010-2024) | Membership growth/decline over time |
| Geographic Mapping | 3,144 counties | Density estimates, metro area analysis |

### Benchmark Alignment

| Sector | Platform | Benchmark | Coverage |
|--------|----------|-----------|----------|
| Total Members | 14.5M | 14.3M (BLS) | 101.4% |
| Private Sector | 6.65M | 7.2M (BLS) | 92% |
| Federal Sector | 1.28M | 1.1M (OPM) | 116% |
| State/Local Public | 6.9M | 7.0M (EPI) | 98.3% |
| States Reconciled | 50/51 | — | 98% |

---

## Part II: Data Integrity & Deduplication (Priority: CRITICAL)

**Why this comes first:** Every feature built on top of duplicated or mislinked data compounds the error. For organizers who need to trust that searching "SEIU Local 32BJ" returns every employer — and only those employers — without double-counting workers, data integrity is the foundation.

### 2.1 Employer Deduplication (Known Issues)

The platform has identified but not fully resolved several categories of employer duplicates:

**A. F-7 Internal Duplicates (11,815 near-exact pairs)**
These are employers in `f7_employers_deduped` that appear multiple times due to case differences, punctuation variations, or corporate suffix inconsistencies. Examples: "KOCH FOODS LLC" vs "Koch Foods LLC", "Colaska, Inc. dba Aggpro" vs "Colaska, Inc dba Aggpro".

| Similarity Score | Pairs | Status | Action |
|-----------------|-------|--------|--------|
| 0.9+ (near exact) | 11,815 | Identified, not merged | Auto-merge with audit log |
| 0.8-0.9 | 3,753 | Identified | Review + selective merge |
| 0.7-0.8 | 6,712 | Identified | Manual review required |
| <0.7 | 46,309 | Identified | Skip (too many false positives) |

*Resolution plan:*
- Merge 0.9+ pairs automatically (keep record with larger unit size, update all foreign keys, create merge audit log)
- Review 0.8-0.9 pairs in batches of 50, categorize as: TRUE_DUPLICATE, MULTI_LOCATION, or DIFFERENT_ENTITY
- For multi-location employers (same company, different sites), keep separate records but link via corporate parent ID
- Estimated effort: 4-6 hours for auto-merge, 8-12 hours for manual review

**B. True Duplicate Groups (234 groups from Feb 6 audit)**
These are groups where the same employer appears with slight name variations at the same address. Already identified, need merge execution.

| Category | Groups | Action |
|----------|--------|--------|
| True duplicates (same entity) | 234 | Merge, keep best record |
| Multi-location (same company) | 142 | Link via parent, keep separate |
| Generic names (ambiguous) | 44 | Manual research to disambiguate |

**C. Multi-Employer Agreement Overcounting**
Building trades, SAG-AFTRA, and association-based bargaining create systematic overcounting where one union files F-7 notices for many employers but the worker count is repeated across all entries.

*Current handling:* Multi-employer groups identified, primaries marked (`is_primary_in_group = TRUE`), secondary records excluded from BLS counts. Building trades use 0.15 adjustment factor.

*Remaining work:*
- Verify all multi-employer groups have correct primary designation
- Ensure UI shows all employers in a group when clicking the union, but only counts workers once
- Add explicit "Part of multi-employer agreement with [X] other employers" notation in employer detail view
- Estimated effort: 4-6 hours

**D. Cross-Source Employer Reconciliation**
The same employer may appear in F-7, NLRB, OSHA, and public sector tables under slightly different names. The unified employer matching module handles this, but gaps remain:

| Match Scenario | Current Rate | Target | Gap |
|---------------|-------------|--------|-----|
| F-7 to OLMS unions | 96.2% | 98%+ | ~1,200 employers |
| NLRB to F-7 | 14.7% | 20%+ | Complex — many NLRB employers don't have F-7 yet |
| OSHA to F-7 | 44.6% | 50%+ | ~3,400 employers recoverable |
| Mergent to F-7 | ~6% | 15%+ | Needs corporate name normalization |

*Resolution plan:*
- Run address-based matching (Tier 3) for remaining unmatched OSHA employers
- Implement corporate parent linkage for Mergent records (subsidiary → parent → F-7 match)
- EIN-based matching where available (~55% of Mergent records have EIN)
- Estimated effort: 8-12 hours

### 2.2 Union Data Quality

**A. Union Name Normalization**
F-7 filings use free-text union names, creating variants: "SEIU-32BJ", "SEIU Local 32BJ", "Service Employees International Union 32BJ" are the same union (file number 501867). The platform resolves this by joining on `f_num` rather than name, but the display layer must consistently show the canonical name from `unions_master` or `lm_data`.

*Known issues:*
- 29 empty `employer_name_aggressive` fields in F-7 data
- 428 short employer names (under 3 characters) that may be data entry errors
- 211 case-sensitive JOIN misses fixed in Feb 6 cleanup (Mergent `company_name_normalized` lowercased)

*Resolution plan:*
- Ensure all employer search views join to `unions_master` for canonical union name display
- Add `union_display_name` computed column: `{aff_abbr} Local {local_number}{desig_name}`
- Create union alias/variant lookup table for search: "Teamsters" → "International Brotherhood of Teamsters" → f_num
- Estimated effort: 3-4 hours

**B. Union Hierarchy Consistency**
The `union_hierarchy` table tracks parent-child relationships and controls which unions' members get counted toward BLS totals. Issues:

- Orphan locals (locals with no parent international linked)
- Inactive unions (no LM filing since 2020) still counted as active
- Merged/renamed locals (e.g., 1199SEIU merger history) need explicit handling

*Resolution plan:*
- Audit `union_hierarchy` for orphan locals, link to parents
- Flag unions with no filing since 2020 as POTENTIALLY_INACTIVE
- Create merger/rename tracking table for historical continuity
- Estimated effort: 6-8 hours

**C. Sector Classification**
Every union and employer needs accurate sector classification (PRIVATE, PUBLIC_STATE, PUBLIC_LOCAL, PUBLIC_FEDERAL) to prevent contamination in BLS comparisons. Known contamination includes federal employers (VA, USPS) appearing in private sector F-7 counts.

*Current handling:* `exclude_from_counts` and `exclude_reason` flags on F-7 employers. Federal contamination patterns identified and flagged.

*Remaining work:*
- Verify all federal employers in F-7 are properly excluded
- Verify state/local government employers in F-7 are classified correctly
- Cross-validate sector assignments against NAICS codes (public admin = 92xxxx)
- Estimated effort: 3-4 hours

### 2.3 Geocoding & Address Completion

| Issue | Records | Source for Fix |
|-------|---------|---------------|
| Missing geocodes (have address) | 16,104 | Census Bureau geocoder batch API |
| Missing addresses (have f_num) | 211 | Recoverable from `lm_data` historical filings |
| Missing NAICS codes | 7,953 | OSHA matches, NLRB data, BLS QCEW |

*Resolution plan:*
- Batch geocode 16,104 records through Census Bureau API (rate-limited, ~2 hours processing)
- Recover 211 addresses from LM filings historical data
- Fill remaining NAICS gaps from BLS QCEW establishment data (see Part III)
- Estimated effort: 4-6 hours

### 2.4 Data Integrity Validation Framework

Create automated validation that runs after every data import or merge:

```
Validation Checks:
1. No duplicate employer_id values across all employer tables
2. Every F-7 employer has exactly one union linkage (via f_num)
3. Worker counts sum correctly (no double-counting in multi-employer groups)
4. BLS coverage stays within 90-110% after any data change
5. No orphan records (employers without unions, unions without employers)
6. Geographic coordinates within valid US boundaries
7. NAICS codes are valid 2-6 digit codes
8. State codes are valid US states/territories
```

*Estimated effort:* 4-6 hours for automated validation script, then runs in <30 seconds per check

---

## Part III: Immediate Expansion — Weeks 1-4

These items use data already downloaded or easily accessible, requiring integration work rather than new data acquisition.

### 3.1 National WHD Wage Violations Load

**Data:** 363,000+ records from DOL Wage and Hour Division (already downloaded: `whd_whisard.csv`)
**What it adds:** Minimum wage violations, overtime violations, back wages owed, employer penalty amounts across all US employers investigated since 2005.
**Value to organizers:** "This employer owes $X in back wages to Y workers" is a powerful organizing message. Currently only NYC violations are scored; national load extends this to all 50 states.

*Implementation:*
- Load full WHD dataset into PostgreSQL (schema already designed for NYC subset)
- Match to existing employers via name + state + city normalization
- Add WHD violation scores to organizing scorecard (extend existing `score_labor_violations` component)
- Add WHD tab to employer detail view in frontend
- Estimated effort: 8-10 hours

### 3.2 OSHA Match Rate Push to 50%+

**Current:** 44.6% of F-7 employers matched to OSHA establishments (28,137 of 63,118)
**Target:** 50%+ (31,500+)
**Gap:** ~3,400 employers recoverable

*Methods:*
- Run address-based matching (Tier 3) on remaining unmatched pairs
- Apply corporate suffix stripping more aggressively (DBA, formerly, trading as)
- ZIP code cross-validation where city names differ but ZIP matches
- Estimated effort: 6-8 hours

### 3.3 Union Discovery Pipeline Automation

**Current:** One-time manual run identified 77 new organizing events (174,357 workers) inserted into `manual_employers`
**Improvement:** Automate the 3-script pipeline (catalog → crosscheck → insert) to run on a schedule

*Implementation:*
- NLRB FOIA/RSS feed monitor for new election petitions
- NLRB voluntary recognition filing scraper (monthly)
- News API keyword monitoring ("union vote", "organizing drive", "[union name] election")
- Cross-check against all existing tables before insert
- Estimated effort: 12-16 hours for full automation; 4-6 hours for NLRB-only monitor

### 3.4 Employer Review Interface

**Current:** `employer_review_flags` table exists with ALREADY_UNION, DUPLICATE, etc. flags, but no UI for organizer review.
**Improvement:** Simple review queue where organizers can flag employers as: confirmed union, not a real employer, duplicate of [X], needs research.

*Value to organizers:* Crowdsourced data quality from people who actually know these workplaces.
*Estimated effort:* 6-8 hours

---

## Part IV: Medium-Term Expansion — Months 2-4

Three parallel tracks. Each can be pursued independently; recommend pursuing at least two simultaneously.

### Track A: Employer Intelligence (Corporate Depth)

**Goal:** Know who you're organizing against — corporate parents, subsidiaries, revenue, executive compensation, political spending.

#### A1. Expanded Mergent Intellect Integration
**Data:** DUNS numbers, revenue, employee counts, corporate parent-subsidiary links, executive contacts, accurate NAICS codes
**Access:** CUNY Library subscription (confirmed available)
**Current state:** 14,240 employers loaded across 11 sectors (NY-focused). National expansion possible.

*What it adds:*
- Corporate hierarchy: "This nursing home is owned by [private equity firm] which also owns [30 other facilities]"
- Revenue context: "This company made $X billion last year but pays workers $Y"
- Subsidiary mapping: Find all locations of a corporate parent
- Better NAICS classification for organizing scorecard

*Implementation:*
- Expand Mergent queries beyond 11 current sectors to national scope
- Build corporate parent → subsidiary linkage table
- Match Mergent records to F-7 employers via DUNS, EIN, and name matching
- Add corporate hierarchy view to employer detail
- Estimated effort: 15-20 hours

#### A2. SEC EDGAR Public Company Disclosures
**Data:** Annual reports (10-K) for ~8,000 public companies. Item 1 contains employee counts, CBA mentions, labor relations disclosures.
**Access:** Free API (SEC EDGAR)

*What it adds:*
- "This company discloses [X]% of workforce is covered by CBAs"
- Risk factor mentions of organizing activity
- Historical employee count trends
- Pension and benefit obligation data

*Implementation:*
- Download 10-K filings for companies matching F-7 employers (CIK lookup)
- NLP extraction of labor-related sections (Item 1, Risk Factors)
- Match to F-7 via CIK → EIN → employer_id
- Estimated effort: 12-16 hours

#### A3. IRS Form 990 Nonprofit Employer Data
**Data:** Revenue, employee counts, executive compensation for nonprofit employers (hospitals, universities, social services)
**Access:** ProPublica Nonprofit Explorer API (free)
**Current state:** 5,942 employers loaded for NY; 37,480 NY 990 filers in `ny_990_filers`

*What it adds:*
- "The CEO of this nonprofit makes $X while frontline workers make $Y"
- Revenue trends for nonprofit employers
- EIN-based matching to F-7 bargaining data
- Board member information for research

*Implementation:*
- Expand 990 queries nationally (ProPublica API handles this)
- Match to F-7 employers via EIN (most reliable nonprofit identifier)
- Add executive compensation tab to employer detail
- Estimated effort: 10-14 hours

### Track B: Worker Protection Data (Safety & Violations)

**Goal:** Build the case that workers need a union by documenting employer violations across multiple agencies.

#### B1. National WHD Scoring (Extension of 3.1)
After loading the full WHD dataset (Part III), extend the scoring methodology nationally:

*What it adds:*
- Every employer gets a "labor violations" score based on wage theft, overtime violations, child labor violations
- Historical trend: "This employer has been investigated X times in Y years"
- Industry benchmarks: "Restaurants in this city average $X in back wages owed"

*Implementation:*
- Extend scoring from NYC-only to national
- Add industry-normalized violation rates
- Create "worst employers" rankings by state, city, industry
- Estimated effort: 6-8 hours (after WHD load)

#### B2. EEOC Discrimination Complaints
**Data:** EEOC litigation, settlements, and consent decrees. Not individual charges (confidential), but public enforcement actions.
**Access:** EEOC public data portal + litigation database

*What it adds:*
- Discrimination patterns as organizing leverage
- Settlement amounts for major cases
- Industry concentration of complaints

*Estimated effort:* 8-10 hours

#### B3. State OSHA Plans
**Data:** 22 states run their own OSHA programs with separate inspection/violation databases
**Access:** Varies by state (some have APIs, most have downloadable data)

*Priority states (by union density and data availability):*
- California (Cal/OSHA) — largest state workforce
- Washington (DOSH) — strong union state
- Michigan (MIOSHA) — manufacturing base
- Oregon (Oregon OSHA) — accessible data

*What it adds:*
- Fills OSHA gaps for state-plan states where federal OSHA data is incomplete
- Additional violation records for organizing scorecard
- State-specific safety standards violations

*Estimated effort:* 8-12 hours per state; recommend starting with CA and WA

#### B4. MSHA Mining Safety
**Data:** Mine Safety and Health Administration violations, inspections, fatalities
**Access:** MSHA public data (free download)

*What it adds:*
- Complete safety picture for mining/extraction employers
- MSHA violations tend to be more severe than OSHA
- Relevant for UMWA and Steelworkers organizing

*Estimated effort:* 6-8 hours

### Track C: Public Sector Depth (Filling Gaps)

**Goal:** The 8% private sector gap (6.65M vs 7.2M BLS) and remaining state coverage gaps require systematic expansion.

#### C1. State PERB Systematic Scraping
**Data:** State Public Employment Relations Boards track every public sector bargaining unit — teachers, police, firefighters, state employees, municipal workers.
**Access:** Varies by state; some have online databases, most require PDF scraping or FOIA

*Priority states (largest gaps + data availability):*

| State | Current Coverage | Gap | Data Source |
|-------|-----------------|-----|-------------|
| California | 25 manual records | Largest state workforce | PERB online database |
| New York | 18 manual records | Partial | NY PERB case search |
| Illinois | Not started | Large public workforce | ILRB website |
| New Jersey | 14 manual records | Partial | PERC database |
| Ohio | Not started | Significant | SERB database |
| Pennsylvania | Not started | Significant | PLRB database |
| Massachusetts | Not started | Strong union state | DLR database |
| Washington | Not started | Strong union state | PERC database |

*What it adds:*
- Comprehensive public sector bargaining unit lists (every school district, police dept, fire dept, etc.)
- Exact worker counts per unit (not estimates)
- Union representation details (which AFSCME local, which NEA affiliate)
- Contract expiration dates (where available)

*Implementation:*
- Build state-specific scrapers (each state has different database format)
- Standardize into `ps_bargaining_units` schema
- Match to existing public sector employer/local records
- Estimated effort: 10-15 hours per state; recommend starting with CA and IL

#### C2. FLRA Enhancement (Federal Sector)
**Data:** Federal Labor Relations Authority tracks every federal bargaining unit
**Access:** FLRA database (public)
**Current state:** 1.28M federal workers at 116% of OPM benchmark — some overcounting

*What it adds:*
- Exact bargaining unit designations for federal agencies
- Which AFGE/NFFE/NTEU local represents which federal office
- Certification/decertification history

*Estimated effort:* 8-10 hours

#### C3. BLS QCEW Establishment Data
**Data:** Quarterly Census of Employment and Wages — 10M+ establishment records with NAICS, geography, employee counts, wages
**Access:** BLS public data (bulk download)

*What it adds:*
- Fill NAICS gaps for 7,953 employers currently without industry codes
- Employment size validation (compare QCEW employee counts to F-7 unit sizes)
- Industry composition data at county level for density calculations
- Establishment counts for "market share" analysis (what % of an industry is unionized)

*Estimated effort:* 12-16 hours (large dataset, needs careful matching)

---

## Part V: Long-Term Vision — Months 5-12

### 5.1 Predictive Organizing Intelligence

**Goal:** Move from "here's what happened" to "here's where organizing is most likely to succeed next."

*Prerequisites:* Tracks A + B data integrated (employer financials + safety violations + labor violations)

*Model inputs:*
- NLRB election win rates by industry, geography, employer size, union
- OSHA violation severity and frequency
- WHD violation history
- Employer revenue and growth trends
- Industry density trends
- Geographic density and "union climate" multiplier
- Recent organizing momentum in sector/geography

*Model outputs:*
- Probability of successful organizing election at employer X
- Ranked list of "most organizable" employers in a geography
- Early warning for industries/regions with declining coverage

*Estimated effort:* 30-40 hours (requires ML expertise)

### 5.2 Real-Time Monitoring

**Goal:** Know about organizing activity as it happens, not months later.

*Components:*

| Feed | Source | Frequency | What It Catches |
|------|--------|-----------|-----------------|
| NLRB petition filings | NLRB website/RSS | Daily | New organizing petitions |
| NLRB election results | NLRB case search | Weekly | Election outcomes |
| OSHA inspections | OSHA search | Weekly | New workplace inspections |
| News monitoring | NewsAPI, Labor Notes, GDELT | Daily | Organizing drives, strikes, settlements |
| Voluntary recognition | NLRB VR filings | Monthly | Card-check recognitions |

*Implementation:*
- Build RSS/API polling service for each source
- De-duplicate against existing database records
- Alert system: "New NLRB petition filed at [employer] in [city]"
- Weekly digest email for organizers
- Estimated effort: 20-30 hours

### 5.3 FEC Political Spending Integration

**Data:** Federal Election Commission records — PAC contributions, corporate political spending, union political spending
**Access:** FEC API (free)

*What it adds:*
- "This employer spent $X on anti-union candidates"
- Corporate PAC → candidate → labor voting record chain
- Union political spending transparency
- Contrast: employer CEO gave $X to [politician] who voted against [labor bill]

*Estimated effort:* 12-16 hours

### 5.4 Contract Database Partnership

**Note:** Systematic CBA tracking is handled by Bargaining for the Common Good and Bloomberg Law. Rather than rebuilding this, the platform should:
- Link to external CBA databases where available
- Track contract expiration dates from public filings (F-7 notices include some dates)
- Monitor for contract fights/strikes via news monitoring
- Potential API integration with existing CBA repositories

### 5.5 Public API for Researchers

**Goal:** Make the platform's data available to labor researchers, academics, and allied organizations.

*Implementation:*
- Read-only API with rate limiting
- Documentation and data dictionary
- Bulk data export for researchers (anonymized where needed)
- Academic citation format and methodology paper
- Estimated effort: 15-20 hours

### 5.6 Hosted Deployment

**Current:** Runs locally on developer machine (localhost:8001)
**Goal:** Cloud-hosted, accessible by multiple organizers simultaneously

*Options:*

| Option | Monthly Cost | Pros | Cons |
|--------|-------------|------|------|
| DigitalOcean Droplet | $24-48 | Simple, full control | Self-managed |
| Railway/Render | $20-40 | Easy deploy, managed | Less control |
| AWS RDS + EC2 | $50-100 | Scalable, enterprise | Complex |
| Supabase + Vercel | $25-50 | Modern, fast | PostgreSQL limits |

*Estimated effort:* 10-15 hours for initial deployment; ongoing maintenance

---

## Part VI: Frontend & Delivery

### 6.1 Organizer-First UX Redesign

The current interface is built for researchers. An organizer-first redesign would prioritize:

**Primary workflow:** "I work for [union]. Show me my employers, my jurisdiction, and my targets."

*Key changes:*
- Union-first entry point: Select your union, see all your employers immediately
- Geographic cascade: State → Metro → City (not separate dropdowns)
- Industry filter in plain English (not NAICS codes): "Healthcare", "Building Services", "Education"
- Target recommendations: "Based on your union's jurisdiction, here are the top 10 unorganized employers"
- Mobile-responsive: Organizers are in the field, not at desks

*Design priorities from Jan 31 planning session:*
- Typeahead search for both unions and employers
- Result density: show enough data in list view to avoid clicking into every record
- Secondary data (OSHA, NLRB, financials) as expandable cards, not separate tabs
- Export to CSV/PDF for offline use

*Estimated effort:* 20-30 hours for full redesign

### 6.2 Export & Reporting

Organizers need to take data out of the platform for:
- Presentations to membership ("here's why we should organize [employer]")
- Grant applications (demonstrating geographic/industry coverage)
- Board reports (organizing progress metrics)
- Leaflets and campaign materials (employer violation summaries)

*Implementation:*
- One-click export of any search result to CSV
- Employer profile PDF (summary of violations, workforce, union history)
- State/metro summary report (density, trends, top targets)
- Estimated effort: 8-12 hours

---

## Part VII: Expansion Options Matrix

Every potential data source rated on four dimensions:

| Data Source | Value to Organizers | Accessibility | Effort (hrs) | Dependencies | Priority |
|------------|-------------------|---------------|-------------|-------------|----------|
| **National WHD Wage Violations** | ★★★★★ | Already downloaded | 8-10 | None | **IMMEDIATE** |
| **F-7 Duplicate Merge (11.8K pairs)** | ★★★★★ | In database | 4-6 | None | **IMMEDIATE** |
| **Employer dedup audit (234 groups)** | ★★★★★ | In database | 8-12 | None | **IMMEDIATE** |
| **Union hierarchy audit** | ★★★★☆ | In database | 6-8 | None | **IMMEDIATE** |
| **OSHA match rate improvement** | ★★★★☆ | In database | 6-8 | None | IMMEDIATE |
| **Geocoding backfill (16K records)** | ★★★☆☆ | Census API | 4-6 | None | IMMEDIATE |
| **CA PERB scraping** | ★★★★★ | Public website | 10-15 | None | SHORT-TERM |
| **Mergent national expansion** | ★★★★☆ | CUNY library | 15-20 | Library access | SHORT-TERM |
| **IRS 990 national expansion** | ★★★★☆ | ProPublica API | 10-14 | None | SHORT-TERM |
| **SEC EDGAR labor disclosures** | ★★★☆☆ | Free API | 12-16 | NLP pipeline | MEDIUM-TERM |
| **BLS QCEW establishments** | ★★★★☆ | Free download | 12-16 | None | MEDIUM-TERM |
| **EEOC enforcement data** | ★★★☆☆ | Public portal | 8-10 | None | MEDIUM-TERM |
| **State OSHA plans (CA, WA)** | ★★★★☆ | Varies | 8-12/state | None | MEDIUM-TERM |
| **MSHA mining safety** | ★★☆☆☆ | Free download | 6-8 | None | MEDIUM-TERM |
| **IL/OH/PA PERB scraping** | ★★★★☆ | Varies | 10-15/state | None | MEDIUM-TERM |
| **FLRA federal enhancement** | ★★★☆☆ | Public database | 8-10 | None | MEDIUM-TERM |
| **Predictive ML model** | ★★★★★ | Requires Tracks A+B | 30-40 | Multiple sources | LONG-TERM |
| **Real-time NLRB monitor** | ★★★★★ | NLRB website | 12-16 | Hosting | LONG-TERM |
| **News monitoring** | ★★★★☆ | NewsAPI/GDELT | 15-20 | API costs | LONG-TERM |
| **FEC political spending** | ★★★☆☆ | Free API | 12-16 | None | LONG-TERM |
| **Public API** | ★★★☆☆ | Build required | 15-20 | Hosting | LONG-TERM |
| **Frontend redesign** | ★★★★★ | Build required | 20-30 | UX planning | LONG-TERM |
| **Hosted deployment** | ★★★★☆ | Cloud services | 10-15 | Ongoing cost | LONG-TERM |

---

## Part VIII: Recommended Execution Sequence

### Tier 1: Data Integrity Sprint (Weeks 1-2)

**Rationale:** Everything else is more valuable when the foundation is clean.

| # | Task | Hours | Outcome |
|---|------|-------|---------|
| 1 | Merge 11,815 F-7 near-exact duplicate pairs | 4-6 | Cleaner employer counts |
| 2 | Review/resolve 234 true duplicate groups | 8-12 | No double-counted employers |
| 3 | Audit union hierarchy (orphans, inactive, mergers) | 6-8 | Accurate union-employer links |
| 4 | Verify multi-employer group primaries | 4-6 | Workers counted once |
| 5 | Sector classification cross-validation | 3-4 | No federal contamination |
| 6 | Geocoding backfill (16K records) | 4-6 | Better geographic search |
| 7 | Build automated validation framework | 4-6 | Prevents future regressions |

**Total:** 34-48 hours
**Checkpoint:** Run BLS coverage validation after completion. All sectors should remain within 90-110%.

### Tier 2: Quick Wins (Weeks 3-4)

| # | Task | Hours | Outcome |
|---|------|-------|---------|
| 8 | Load national WHD wage violations (363K records) | 8-10 | Wage theft data for all 50 states |
| 9 | OSHA match rate push to 50%+ | 6-8 | Better safety linkage |
| 10 | NAICS gap filling from OSHA + QCEW | 4-6 | Industry codes for 7,953 employers |

**Total:** 18-24 hours
**Checkpoint:** Organizing scorecard scores should improve (more data inputs per employer).

### Tier 3: New Source Integration (Months 2-3)

Pick 2 of 3 tracks to pursue simultaneously:

| Track | Focus | Hours | Outcome |
|-------|-------|-------|---------|
| A | Employer Intelligence (Mergent + 990 + SEC) | 37-50 | Corporate depth |
| B | Worker Protection (WHD scoring + EEOC + State OSHA) | 22-30 | Violations case-building |
| C | Public Sector (CA/IL/NY PERB + FLRA + QCEW) | 30-46 | Coverage gaps filled |

**Recommended combination:** Track B + Track C (strongest value for organizers)

### Tier 4: Intelligence Layer (Months 4-6)

| # | Task | Hours | Outcome |
|---|------|-------|---------|
| 14 | NLRB real-time petition monitor | 12-16 | Know about elections as filed |
| 15 | Predictive organizing model (v1) | 30-40 | "Most organizable" employer rankings |
| 16 | Organizer-first frontend redesign | 20-30 | Usable by field organizers |

### Tier 5: Platform Maturity (Months 6-12)

| # | Task | Hours | Outcome |
|---|------|-------|---------|
| 17 | News monitoring integration | 15-20 | Campaign awareness |
| 18 | FEC political spending | 12-16 | Anti-union spending transparency |
| 19 | Hosted deployment | 10-15 | Multi-user access |
| 20 | Public API + documentation | 15-20 | Researcher access |
| 21 | Export/reporting suite | 8-12 | Campaign materials |

---

## Appendix: Decision Framework for Prioritization

When choosing what to build next, weight these factors:

1. **Does it improve data accuracy?** (40% weight) — If the foundation is wrong, features on top make it worse. Deduplication and validation always come first.

2. **Does it help an organizer in the field?** (30% weight) — The platform exists to support organizing. Features that directly answer organizer questions rank higher than analytical depth.

3. **What's the effort-to-value ratio?** (20% weight) — A 4-hour task that fills a major gap beats a 40-hour task that adds marginal insight.

4. **Does it compound?** (10% weight) — Some work makes future work easier (matching modules, geocoding, NAICS classification). These investments pay dividends across every subsequent data source integration.

---

*This roadmap is a living document. Update after each development sprint with completed items, revised estimates, and new priorities identified during implementation.*
