# Full Platform Audit Prompt — For Claude, Codex, and Gemini
## Labor Relations Research Platform
**Date:** February 16, 2026
**Version:** Comprehensive (includes future plans, tools, and next steps)

---

## READ THIS FIRST — What This Project Is (Plain Language)

This is a research platform that helps union organizers figure out where to focus their efforts. It works by pulling data from many different government databases — the Department of Labor, the NLRB (which handles union elections), OSHA (workplace safety), the SEC (publicly traded companies), the IRS (nonprofit organizations), and several others — and connecting all of that data together so you can see the full picture of any employer.

The core idea: if a union organizer is looking at a workplace and wondering "should we try to organize here?", the platform gives them evidence-based answers. It shows them things like: Does this employer have safety violations? Are similar employers already unionized? Has there been NLRB activity here before? What's the company's corporate ownership structure? How does this employer compare to similar ones that already have unions?

The platform runs on PostgreSQL (a database system), has a Python backend using FastAPI (which serves data to the website), and a web frontend (the actual screens organizers interact with). It currently tracks about 100,000 employers across multiple data sources, with 14.5 million union members accounted for — which matches federal benchmarks within 1.5%.

---

## YOUR ROLE AS AUDITOR

You are performing an independent audit of this platform. Your job is to be **thorough and honest**. Don't assume things work just because they exist. Don't skip areas that seem complicated. Actually test things where possible. The goal is a complete, accurate picture of:

1. **What works well** — features, data, connections that are solid
2. **What's broken** — crashes, bad data, missing connections
3. **What's risky** — security issues, data quality gaps, technical debt
4. **What's missing** — important capabilities not yet built
5. **What should come next** — prioritized recommendations

**Communication style:** Explain everything in plain, simple language. Assume the person reading this has limited coding and database knowledge. When you reference a technical concept, explain what it means and why it matters in practical terms. For example, don't just say "foreign key constraint violated" — say "this means 824 employer records are pointing to unions that don't exist in the system, so when someone looks up those employers, the union information will be wrong or missing."

---

## HOW EACH AI SHOULD USE THIS PROMPT

### Claude (Primary Auditor — The Deep Dive)
You have direct access to the database and codebase. Run actual queries. Test actual endpoints. Read actual code. Your audit should be the most detailed and data-backed. Create your report at `docs/AUDIT_REPORT_CLAUDE_2026.md`.

**Your strengths for this task:** You know the full project context, can run multi-step investigations, and can trace problems across different parts of the system.

### Codex (Code & Logic Auditor — The Inspector)
Focus on code quality, logic correctness, and technical debt. Read through the API code, the matching scripts, and the frontend JavaScript. Your audit should catch bugs, security issues, and architectural problems. Create your report at `docs/AUDIT_REPORT_CODEX_2026.md`.

**Your strengths for this task:** You're excellent at reading code, finding logic errors, and spotting patterns that could cause problems later.

### Gemini (Research & Verification Auditor — The Fact-Checker)
Focus on data accuracy, methodology validation, and external verification. Cross-check claims against public data sources. Validate that the platform's benchmarks and methodologies are sound. Verify that documented data sources are being used correctly. Create your report at `docs/AUDIT_REPORT_GEMINI_2026.md`.

**Your strengths for this task:** You're excellent at research, summarization, and cross-referencing claims against external sources.

---

## DATABASE CONNECTION

```python
import psycopg2
conn = psycopg2.connect(
    host='localhost',
    dbname='olms_multiyear',
    user='postgres',
    password='Juniordog33!'
)
```

---

## WHAT THE PLATFORM LOOKS LIKE TODAY

### Platform by the Numbers

| What | Count |
|------|-------|
| Database size | ~20 GB (12 GB is bulk GLEIF corporate data that should be archived) |
| Total tables | 169 |
| Total views | 186 |
| Total rows | ~23.9 million (public) / ~76.7 million (with GLEIF raw data) |
| API endpoints | 152 across 17 route groups |
| Automated tests | 165 (all passing) |
| Current employers tracked | 60,953 |
| Historical employers (expired contracts) | 52,760 |
| Python scripts | ~494 |
| Frontend files | 12 (split from 1 monolith) |

### Core Tables and What They Hold

| Table | Records | What it is |
|-------|---------|------------|
| `unions_master` | 26,665 | Every union local/affiliate that files with the Department of Labor. The master list of unions. |
| `f7_employers_deduped` | 63,118 | Private sector employers that have active union contracts (from Form F-7 filings) |
| `nlrb_elections` | 33,096 | Union election records from the NLRB — who petitioned, who voted, who won |
| `nlrb_participants` | 30,399 | Unions and employers involved in NLRB cases (95.7% matched to OLMS unions) |
| `lm_data` | 2.6M+ | Historical union financial filings (2010-2024) — the raw data over time |
| `osha_establishments` | 1,007,217 | Every workplace OSHA has visited or has records for |
| `osha_violations_detail` | 2,245,020 | Individual safety violations ($3.52 billion in penalties total) |
| `osha_f7_matches` | 79,981 | Links between OSHA workplaces and unionized employers (44.6% match rate) |
| `unified_employers_osha` | 100,768 | All employer sources combined into one table |
| `manual_employers` | 509 | Public sector employers and research discoveries added by hand |
| `mergent_employers` | 14,240 | Commercial employer data across 11 industry sectors with organizing scores |
| `mv_employer_search` | 120,169 | Pre-built search index combining all employer sources |

### What "Matching" Means (This Is the Core Technical Challenge)

Different government agencies don't share a single employer ID system. The Department of Labor knows "Walmart Inc." by one file number, OSHA knows the same Walmart store by a different establishment ID, the NLRB has its own case numbers, and the SEC has a different company identifier (CIK). Even the employer names are often slightly different across databases — one might say "WALMART INC" while another says "Wal-Mart Stores, Inc." and a third says "WAL MART STORES INC."

The platform uses a **5-tier matching pipeline** to connect these records:

| Tier | Method | What it does | Confidence |
|------|--------|--------------|------------|
| 1 | EIN exact match | If two records have the same tax ID number (EIN), they're the same entity. Most reliable. | HIGH |
| 2 | Normalized name + state | Clean up the company name (remove Inc., LLC, extra spaces, etc.) and match on cleaned name + state | HIGH |
| 3 | Address match | Fuzzy name match + exact street number + city + state | HIGH |
| 4 | Aggressive name + city | Strip the name down even further (remove common words) + match on city | MEDIUM |
| 5 | Trigram fuzzy + state | Use a statistical text similarity method (pg_trgm) to find names that are similar but not identical | LOW |

**Current match rates (what percentage of employers can be connected to each data source):**

| Data Source | Match Rate (Current Employers) | Match Rate (All Employers) |
|-------------|-------------------------------|---------------------------|
| OSHA safety records | 47.3% | 25.37% |
| Wage theft records | 16% | — |
| 990 nonprofit filings | 11.9% | — |
| NLRB election records | 28.7% | — |

### The Scoring System

The platform assigns a score to each employer to help organizers prioritize. The current system has **9 factors**, maxing out at 100 points:

| Factor | Max Points | What it measures |
|--------|-----------|-----------------|
| Safety violations (OSHA) | 25 | More violations = higher score (more organizing leverage) |
| Industry union density (BLS) | 15 | How unionized is this industry already? |
| Geographic density | 15 | How unionized is this area? |
| Employer size | 15 | Bigger workplaces = more impact |
| NLRB momentum | 15 | Recent election activity in this industry/area |
| Government contracts | 15 | Public money = public accountability leverage |
| *Plus 3 additional factors in the Mergent sector scorecards* | | |

### Known Issues Right Now

| Problem | Severity | What it means in practice |
|---------|----------|--------------------------|
| 3 density endpoints crash | CRITICAL | Map views of union concentration crash because code reads data columns by number instead of name |
| Authentication disabled by default | CRITICAL | No login required — anyone with the URL can access everything |
| 824 union file number orphans | HIGH | 824 employers point to union file numbers that don't exist, so their union connections silently fail |
| 29 scripts have a password bug | HIGH | They send the literal code text as the password instead of executing it to get the actual password |
| GLEIF raw schema is 12 GB | HIGH | Massive unused corporate data taking up most of the database |
| Only 37.7% of employers have industry codes | MEDIUM | Without NAICS codes, the scoring system can't calculate industry unionization rates |
| 299 unused database indexes (1.67 GB wasted) | MEDIUM | Like a book with 299 index entries nobody ever looks up — wastes space and slows updates |
| Documentation is ~55% accurate | MEDIUM | README has wrong commands, wrong file paths, wrong scoring descriptions |
| modals.js is 2,598 lines | MEDIUM | One file handles all popup windows — hard to change without breaking other things |

---

## AUDIT SECTIONS

### SECTION 1: Database Table Inventory

**What this does:** Creates a complete list of every table in the database with real, current row counts — not what the documentation says, but what's actually there right now.

**Why it matters:** Over time, tables get created for experiments, one-off analyses, or features that never got finished. Some might be empty. Some might have millions of rows but never get used. We need to know what we're working with.

**Steps:**
1. Connect to the `olms_multiyear` database
2. Get EVERY table and view (not just ones mentioned in documentation)
3. For each table, get: actual current row count, number of columns, whether it has a primary key, when it was last modified
4. Compare actual counts against documented counts — flag discrepancies
5. Flag tables with ZERO rows
6. Flag tables not mentioned in any documentation (these are "undocumented" or orphaned)
7. Group tables into categories: Core, OSHA, Public Sector, NLRB, Corporate/Financial, Mergent, Geography, Views, Unknown/Orphan

**What to look for:** Tables that exist but serve no purpose. Tables documented as having 60,000 rows but actually having 10,000. Tables with no primary key (these are prone to duplicate records). Tables that haven't been updated in months but should be current.

**CHECKPOINT: Stop and report findings before continuing.**

---

### SECTION 2: Data Quality Deep Dive

**What this does:** Looks inside the most important tables to check if the data itself is healthy.

**Why it matters:** A table can have 60,000 rows but if half the important columns are empty, it's not as useful as it looks. We need to know actual quality, not just quantity.

**Steps:**
1. For each core table, check every important column: how many rows have data vs. how many are blank or null
2. Check for duplicate records (same employer name + state appearing multiple times)
3. Validate relationships between tables — when one table points to another, does the target record actually exist?
4. Count "orphaned" records — records pointing to things that don't exist
5. Check for data consistency — do worker counts add up? Do state totals match national totals?

**Specific tables to examine:**
- `f7_employers_deduped` — employer_name, city, state, naics, lat/lon, latest_unit_size
- `unions_master` — union_name, aff_abbr, members, city, state
- `nlrb_elections` — employer_name, city, state, eligible_voters, votes_for, votes_against
- `osha_establishments` — estab_name, city, state, sic_code, naics_code
- `mergent_employers` — company_name, duns, ein, employees_site, naics_primary, organizing_score

**What to look for:** Columns that should be filled but aren't (like NAICS industry codes). Duplicate employer records. Foreign key relationships that point to nowhere. Membership numbers that don't add up.

**CHECKPOINT: Stop and report findings before continuing.**

---

### SECTION 3: Materialized Views & Indexes

**What this does:** Checks the pre-built summary tables (materialized views) and database lookup tools (indexes).

**Plain language:**
- A **materialized view** is like a saved search result. Instead of re-running a complex calculation every time someone asks for it, the database saves the answer and serves it instantly. But if the underlying data changes and the view isn't refreshed, it shows stale answers.
- An **index** is like the index in the back of a book — it helps the database find things faster. But unnecessary indexes waste space and slow down data updates because every change to the data also has to update all the indexes.

**Steps:**
1. List all materialized views with: row count, disk size, when last refreshed, what tables they depend on
2. List all regular views and test if they actually work (run a simple query on each)
3. List all indexes with: which table, which columns, disk size, whether they've ever been used
4. Flag: unused indexes (wasting space), missing indexes (tables that should be faster but aren't), stale views, broken views

**CHECKPOINT: Stop and report findings before continuing.**

---

### SECTION 4: Cross-Reference Integrity (The Core Value Test)

**What this does:** Tests whether the connections BETWEEN different data sources actually work. This is the whole point of the platform — linking employers to unions to OSHA violations to NLRB elections.

**Why it matters:** If these connections are broken or incomplete, the platform's analysis is unreliable and organizers make decisions based on incomplete information.

**Steps:**
1. **Corporate Identifier Crosswalk** — How many employers have connections to: GLEIF (corporate ownership), Mergent (commercial data), SEC (public company filings), IRS (tax IDs)?
2. **OSHA Matching** — How many employers have at least one OSHA match? What's the average confidence? How many OSHA records are unmatched?
3. **NLRB Coverage** — How many NLRB elections connect to known unions? How many NLRB employer names connect to the main employer table?
4. **Public Sector Linkage** — How many public sector union locals connect to the master union list? How many public employers have documented bargaining relationships?
5. **Unified Employer View** — Source breakdown (how many from each source), geographic coverage (how many have coordinates), industry coverage (how many have NAICS codes), OSHA coverage
6. **Scoring Coverage** — How many employers have a non-zero score? Distribution across priority tiers (TOP, HIGH, MEDIUM, LOW)? Which score components are most often missing?

**What to look for:** Data sources that are barely connected to the rest of the platform. Match rates that are suspiciously high or low. Gaps in coverage that could be filled with existing data.

**CHECKPOINT: Stop and report findings before continuing.**

---

### SECTION 5: API Endpoint Audit

**What this does:** Checks whether the software that serves data to the website actually works.

**Plain language:** The API is like a waiter in a restaurant. The frontend (website) asks for data, the API goes to the database kitchen, gets the data, and brings it back. If a waiter doesn't know a menu item exists, the customer gets nothing even though the kitchen has the food.

**Steps:**
1. Read `api/labor_api_v6.py`
2. List every endpoint (URL) with: what data it serves, what database tables it reads from
3. Flag endpoints that reference tables or columns that don't exist
4. Flag any security vulnerabilities (especially SQL injection — where someone could manipulate the database through the search box)
5. Count: working endpoints, likely broken endpoints, security risks
6. Check for database tables that have NO API endpoint (data that exists but can't be accessed through the website)

**CHECKPOINT: Stop and report findings before continuing.**

---

### SECTION 6: File System & Script Inventory

**What this does:** Catalogs all the code files, figuring out which are essential vs. which are old experiments.

**Steps:**
1. List all directories with file counts
2. For each Python script, check: does it connect to the database? Which tables does it use? Is it a one-time data loader or a recurring process?
3. Identify scripts that reference tables that no longer exist
4. Check for hardcoded passwords or credentials (security risk)
5. Identify the "critical path" scripts — the ones needed to rebuild the database from scratch

**CHECKPOINT: Stop and report findings before continuing.**

---

### SECTION 7: Documentation Accuracy Check

**What this does:** Compares what documentation says against what's actually true.

**Steps:**
1. Read `CLAUDE.md` and compare every table name and row count against the actual database
2. Check the README for correct startup commands, file paths, and feature descriptions
3. Flag documentation that claims features exist which don't work
4. Note where documentation is missing for existing tables or features
5. Check if the roadmap documents (`Roadmap_TRUE_02_15.md`) accurately reflect current state

---

### SECTION 8: Frontend & User Experience Audit

**What this does:** Checks the website that organizers actually see and interact with.

**Steps:**
1. Read the frontend code files (starting with `files/organizer_v5.html` and its JavaScript files)
2. Check for: old scoring scale references (0-62, 0-100, 6-factor), hardcoded localhost URLs, broken links
3. Assess the navigation structure — can an organizer easily find targets, view employer profiles, export data?
4. Check if confidence levels and data freshness are shown to users
5. Flag any user-facing inconsistencies (different numbers shown in different places for the same thing)

---

### SECTION 9: Security Audit

**What this does:** Checks for security vulnerabilities that could expose data or allow unauthorized access.

**Steps:**
1. Check authentication status — is login enforced? Can anyone access the API without credentials?
2. Search all code for hardcoded passwords or API keys
3. Check for SQL injection vulnerabilities in API endpoints
4. Verify that the JWT authentication system (the login token system) works correctly
5. Check if sensitive data (employer details, union membership) is protected appropriately

---

## FUTURE PLANS — What's Being Built Next

The auditor should be aware of planned expansions, because audit findings should be evaluated in the context of where the platform is heading. The roadmap has 7 phases over 14 weeks:

### Phase 1: Fix What's Broken (Week 1)
Fix crashing endpoints, the password bug in 29 scripts, 824 orphan records, enforce authentication, archive the 12 GB GLEIF data, update documentation, and backfill NAICS codes from OSHA matches.

### Phase 2: Frontend Cleanup (Weeks 2-4)
Reorganize the interface into 4 clear screens (Territory Overview, Employer Profile, Union Profile, Admin/Review Queue). Remove all old scoring scale references. Split the 2,598-line modals.js into focused files. Add confidence and data freshness indicators.

### Phase 3: Matching Pipeline Overhaul (Weeks 3-7)
Standardize all matching so every match — regardless of source — produces the same output format with method, confidence level, and evidence. Create one name-cleaning function used everywhere. Add Splink probabilistic matching for cases that exact matching can't resolve. Build a match quality dashboard.

### Phase 4: New Data Sources (Weeks 8-10)
Add SEC EDGAR (300,000+ public companies with EIN matching), IRS Business Master File (1.8 million tax-exempt orgs), CPS Microdata via IPUMS (granular union density by metro area), and OEWS staffing patterns (occupation mix by industry).

### Phase 5: Scoring Evolution (Weeks 10-12)
Add temporal decay (recent violations matter more than old ones). Implement NAICS hierarchy similarity (two employers sharing 5 of 6 industry code digits are much more comparable than two sharing only 2). Add score version tracking. Experimental: Gower distance engine and propensity model.

### Phase 6: Deployment (Weeks 11-14)
Docker containerization, CI/CD pipeline, automated data refresh scheduling.

### Phase 7: Strategic Intelligence (Week 14+)
Web scraper expansion (Teamsters, SEIU, UFCW), state PERB data, "union-lost" historical analysis, board report generation, occupation-based similarity.

---

## POTENTIAL TOOLS & DATA SOURCES IDENTIFIED FOR FUTURE USE

The following tools and data sources have been researched and documented. The auditor should note whether current infrastructure would support their integration:

### Data Integration Tools
| Tool | What it does | Why it matters |
|------|-------------|---------------|
| **edgartools** (Python) | Parses SEC EDGAR filings, extracts financial data, reads XBRL tags | Would connect 300,000+ public companies by EIN — no fuzzy matching needed |
| **Splink** (Python) | Probabilistic record matching — calculates probability that two records are the same entity | Would handle the cases that exact matching can't resolve |
| **ipumspy** (Python) | Accesses Census microdata including union membership | Would enable metro-level union density calculations instead of broad national averages |
| **Crawl4AI** (Python) | AI-powered web scraping — visits websites and extracts structured data | Would enable scraping union and employer websites at scale |
| **Firecrawl** (SaaS) | Commercial web scraping with AI extraction — 87-94% accuracy on benchmarks | Higher accuracy than Crawl4AI but costs money |
| **sec-edgar-downloader** (Python) | Bulk downloads SEC filings with rate limiting | Companion to edgartools for getting the raw filings |

### Data Sources Not Yet Integrated
| Source | Records Available | Key Benefit |
|--------|------------------|-------------|
| **SEC EDGAR Full Index** | 800,000+ entities | EIN-based matching to existing employers, corporate hierarchy, Exhibit 21 subsidiary lists |
| **IRS Business Master File** | 1.8 million tax-exempt orgs | Could double 990 match rate from 11.9% to 25%+ |
| **CPS Microdata (IPUMS)** | Monthly survey data | Metro-level union density instead of broad national averages |
| **OEWS Staffing Patterns** | Occupation mix by industry | Find comparable employers by workforce composition, not just industry code |
| **State PERB data** (NY, CA, IL) | Thousands of public-sector records | No open-source tools exist for this — would be first-ever dataset |
| **Good Jobs First Subsidy Tracker** | 722,000+ entries | Cross-reference subsidy recipients with employer data |
| **ProPublica Nonprofit Explorer** | API access | Broader 990 coverage than current dataset |
| **DOL contract database** | 25,000+ union contracts | Searchable contract language using AI extraction |

### Web Scraping Targets Researched
| Union | Scraping Difficulty | Key Data Available |
|-------|--------------------|--------------------|
| **Teamsters** | Easy — single-page directory | Officers, phone, email, 22 industry divisions |
| **AFSCME** | Easy — local names contain employer names | Direct path to thousands of public-sector employers |
| **UNITE HERE** | Easy — detailed officer info per local | Officer data, jurisdiction info |
| **CWA** | Medium — filterable by district/sector | District and sector affiliations |
| **SEIU** | Medium — national finder shows limited info | Local names and states only |
| **AFT** | Hard — requires member login | Behind authentication wall |
| **IBEW** | Hard — JavaScript-rendered directory | Requires full browser simulation |
| **UAW** | Hard — JavaScript-rendered directory | Same issue as IBEW |

---

## KEY METHODOLOGICAL CONCEPTS THE AUDITOR SHOULD UNDERSTAND

### The Deduplication Problem
The raw data shows 70.1 million union members. The actual number is about 14.3 million (per BLS). The difference is because the same union members get counted multiple times — once in each annual filing, once in each data source, and sometimes multiple times within a single filing when multi-employer agreements are involved. The platform's deduplication brought 70.1M down to 14.5M (within 1.5% of BLS). The auditor should verify this math.

### Multi-Employer Agreements
Some union contracts cover multiple employers under a single agreement. This creates a counting problem: if one contract covers 100 employers with 5,000 total workers, you can't just divide (50 per employer) because the workers might be distributed unevenly. The platform handles this through the `f7_union_employer_relations` table and special aggregation logic. The auditor should check if this logic produces sensible results.

### The NLRB Data Structure Quirk
92.34% of NLRB participant records don't connect to election records. This sounds broken but is actually how the data works — the NLRB participants table includes ALL case types (unfair labor practice complaints, representation petitions, decertification attempts), not just elections. Only a small fraction are actual elections. The auditor should NOT flag this as a bug, but SHOULD flag the lack of a unified NLRB view that bridges case types.

### Density Estimation
Union density (what percentage of workers are unionized) is estimated at multiple geographic levels: national, state, county, ZIP code, and census tract. The methodology uses BLS industry-level rates applied to local employment counts, with calibration multipliers to match known totals. The auditor should check whether these estimates produce sensible results (e.g., no county should show 95% union density).

### The Historical Employer Problem
52,760 employers have expired union contracts — they were once unionized but no longer are. These records create confusion in dashboards because they inflate totals without being relevant to active organizing. The auditor should check whether dashboards clearly distinguish current vs. historical employers.

---

## SECTION 10: Summary & Recommendations

Pull everything together:

1. **Health Score:** Rate overall platform health: Critical / Needs Work / Solid / Excellent — with justification
2. **Top 10 Issues:** Most important problems, ranked by impact on organizers
3. **Quick Wins:** Things fixable in under an hour each
4. **Tables to Consider Dropping:** Truly orphaned tables with no connections
5. **Missing Indexes:** Specific recommendations
6. **Documentation Corrections:** Specific errors in CLAUDE.md and README
7. **Data Quality Priorities:** Which tables need the most cleanup
8. **Future Integration Readiness:** How prepared is the platform for the planned Phase 4 data source integrations? What infrastructure needs to be in place first?
9. **Matching Pipeline Assessment:** Is the current matching approach scalable, or does it need the Phase 3 overhaul before anything else?
10. **Scoring Model Assessment:** Is the current 9-factor scoring model producing useful results? What would make it more accurate?

---

## OUTPUT FORMAT

Write your report in clear, plain language with actual numbers and evidence. When something is broken, explain what it means practically — "this means when an organizer searches for employers in Queens, they won't see 47 employers that actually have OSHA violations" rather than just "47 records have null OSHA match IDs."

Include the actual queries or code you used to verify findings, so the results can be independently confirmed.

Organize findings by severity: CRITICAL (blocks basic use), HIGH (significant gap), MEDIUM (should be fixed soon), LOW (nice to have).

---

## CROSS-AUDIT COMPARISON INSTRUCTIONS

After all three auditors complete their reports, the project owner will compare them. To make this easier:

1. **Use consistent severity labels:** CRITICAL, HIGH, MEDIUM, LOW
2. **Number your findings** (e.g., Finding 1.1, Finding 1.2) so they can be cross-referenced
3. **State your confidence** in each finding: Verified (tested it), Likely (strong evidence), Possible (inferred)
4. **Note disagreements** with previous audit reports if you're aware of them. The last round of audits had disagreements about OSHA match rates (47.3% vs 25.37% — both correct but measured different populations), WHD matching (fixed on the main path but broken on a legacy path), and GLEIF storage (396 MB of useful data vs 12 GB of raw bulk data). If you encounter similar ambiguities, explain both interpretations.

---

*This prompt was built from: CLAUDE.md, Roadmap_TRUE_02_15.md, multi_ai_workflow.md, claude_code_audit_prompt.md, audit_resolution_prompt.md, Future_Projects_Post_Launch_Goals.docx, workforce_composition_synthesis.md, three_audit_comparison.md, and the platform's actual database schema.*
