# Data Source Expansion Plan — Merged Research & Implementation Roadmap

**Date:** February 26, 2026
**Purpose:** Synthesize three independent research reports into a unified plan for expanding company financial and location data in the Labor Relations Research Platform
**Source Reports:**
1. **Gemini Report:** "Advanced Frameworks for Global Corporate Intelligence" — Global registries, alternative signals, geospatial/supply chain intelligence
2. **OpenAI Report:** "Company and Site-Level Financial Intelligence" — Authoritative sources with code examples, uncertainty quantification, site-level datasets
3. **Claude Report:** "The Definitive Guide to US Company Data on a Budget" — US-focused free/low-cost sources, library access, proxy estimation models

---

## WHAT WE ALREADY HAVE (The Starting Point)

Before talking about what's new, here's a plain-English summary of what's already wired into the platform's PostgreSQL database. Think of these as the building blocks that new data sources will plug into.

| Data Source | What It Tells Us | Records | Status |
|---|---|---|---|
| **OSHA** | Workplace safety violations, inspections, accidents | 1M establishments, 2.2M violations | ✅ Fully loaded |
| **NLRB** | Union elections, unfair labor practice cases, voluntary recognitions | 33K elections, 477K cases | ✅ Fully loaded |
| **DOL Wage & Hour** | Wage theft cases, back wages owed | 363K cases | ✅ Fully loaded |
| **SEC EDGAR** | Public company filings — names, CIK, EIN, SIC codes | 517K companies | ⚠️ Basic — company list loaded, but NOT full financials (no revenue, no XBRL data yet) |
| **SAM.gov** | Federal contractor registrations — UEI, CAGE code, NAICS, business type | 826K entities | ✅ Fully loaded |
| **IRS Form 990** | Nonprofit financial data — revenue, expenses, compensation | 586K filers + 1M deduped | ✅ Fully loaded |
| **Mergent Intellect** | Business data — revenue, employees, NAICS, addresses | 56K employers | ✅ Loaded (via NYPL) |
| **GLEIF** | Corporate ownership chains — who owns whom | 379K US entities, 499K links | ✅ Fully loaded |
| **BLS** | Industry-level union density, occupation-industry staffing patterns | 67K+ patterns | ✅ Fully loaded |
| **USASpending** | Federal contract dollar amounts by recipient | 47K recipients | ✅ Loaded |
| **F-7 Employers** | Employers with union contracts (FMCS bargaining notices) | 146K total (67K current) | ✅ Core table |
| **Entity Matching** | Cross-references linking the same company across different databases | 1.16M match log entries | ✅ Working (96.2% F7-OLMS match rate) |

**What this means in plain English:** We already know a LOT about employers that have union contracts, government contracts, safety violations, or are publicly traded. The big gaps are: (1) financial data for private companies, (2) employee counts at specific locations, and (3) companies that have NONE of the above — the "invisible" employers that might be great organizing targets but don't show up in any government database yet.

---

## THE BIG PICTURE: What All Three Reports Agree On

Despite being produced by three different AI systems with different research approaches, they converge on the same core strategy. Here's what they all found:

**1. Layer free government data first, then enrich with commercial and alternative sources.**
All three reports rank the same free government sources as the foundation: SEC EDGAR (for public companies), Census Bureau (for industry benchmarks), BLS QCEW (for employment data by geography), USASpending (for government contracts), and Form 5500 (for employee benefit plan data that reveals employee counts).

**2. A library card is worth more than a $50K data subscription.**
All three reports highlight that NYPL and CUNY library access provides free entry to Data Axle (44-60M businesses), Mergent Intellect (100M+ businesses), and PrivCo (940K private companies with actual revenue/EBITDA data). This is the single most cost-effective data strategy.

**3. Private company financials are always estimates — and that's okay.**
No source has "real" financial data for most private companies. Even expensive providers like D&B and ZoomInfo use models and estimates. The key is being transparent about confidence levels and using multiple signals to triangulate, not pretending any single source is ground truth.

**4. Proxy signals (job postings, web traffic, real estate footprint) can fill gaps.**
When you can't get direct financial data, you can estimate it. If a company is hiring aggressively, their revenue is probably growing. If they have 10 locations with 50K sq ft each, they probably have a certain number of employees. These aren't perfect but they're better than nothing.

**5. The "micro-business" gap is real and probably unsolvable at scale.**
Businesses with fewer than 10 employees make up the majority of America's ~33M businesses but are poorly covered by every data source. For the platform's organizing use case, this matters less — most organizing targets are mid-size to large employers.

---

## WHAT EACH REPORT UNIQUELY FOUND

These are insights that appeared in only one or two of the three reports — the unique value from each research approach.

### Only in the Gemini Report
- **Supply chain intelligence via Bills of Lading (BOL):** Import/export shipping records reveal which companies are dependent on overseas suppliers, how much they're importing, and from where. Providers like Descartes Datamyne and manifestDB make this data accessible. For organizing, this could reveal financial vulnerability or offshoring risk.
- **Patent filing velocity as a strategic signal:** The speed and subject matter of a company's patent filings predict their future direction. A company filing lots of AI patents is probably expanding that division. Free via USPTO Patent Public Search.
- **Satellite imagery for physical activity monitoring:** Parking lot car counts, construction activity, and night-light intensity as economic indicators. Landsat and Sentinel data are free. Practical for tracking whether a factory is actually operating or idle.
- **Social sentiment as a leading financial indicator:** Tracking brand mentions and sentiment on social media can predict revenue changes 1-2 quarters ahead. Tools like Talkwalker and Awario make this accessible.
- **Granger causality testing:** A statistical method for verifying that an alternative signal actually PREDICTS financial outcomes rather than just happening to move at the same time. This is important for building credible estimation models.

### Only in the OpenAI Report
- **Uncertainty quantification with Monte Carlo simulation:** Instead of giving a single revenue estimate ("Company X makes $50M"), give a range with confidence ("Company X makes $30M-$70M, with 80% confidence the true value is in that range"). This is more honest and more useful for decision-making. The report includes working Python code for this.
- **Overture Maps Foundation as a standardized POI layer:** A newer alternative to OpenStreetMap for "points of interest" data (store locations, offices, etc.), backed by Microsoft, Meta, and Amazon. Uses persistent GERS IDs that make it easy to join location data across sources.
- **GLEIF Level 2 ownership data:** Beyond basic corporate identifiers, GLEIF's "Level 2" relationship data reveals who owns whom across borders. We already have GLEIF loaded — this is about extracting more value from it.
- **Form 990 as a nonprofit benchmarking tool:** Not just for finding unions, but for understanding the financial health of nonprofit employers (hospitals, universities, social services) that are major organizing targets. We already have this data — the insight is using it differently.
- **Business credit scores (D&B PAYDEX, Experian Intelliscore) as financial health proxies:** These don't give you revenue directly, but they indicate whether a company pays its bills on time, which correlates with financial stability. Paid but sometimes accessible through library databases.

### Only in the Claude Report
- **DOL Form 5500 as an employee count proxy:** About 800K employee benefit plans file annually, revealing the plan sponsor's name, EIN, address, and number of plan participants. Free bulk download. Participant counts are a meaningful (though imperfect) proxy for employee headcount.
- **UCC filings as debt/lending signals:** When a company takes out a loan, a UCC filing gets recorded with the state Secretary of State, revealing the existence of secured debt, who the lender is, and what collateral backs the loan. Each state has its own database with varying accessibility.
- **SBA PPP loan data:** 4.9M borrower records from the COVID PPP program, with company names, addresses, loan amounts, NAICS codes, and "jobs retained" — one of the few sources with individual company-level data for very small businesses.
- **State-level business registry bulk downloads:** Some states (Florida, New York, California) publish their full business registries in bulk, allowing you to match your employer database against the complete list of registered businesses in those states.
- **Revenue-per-employee estimation model using Census NAICS benchmarks:** A specific methodology where you take an industry's average revenue per employee (from Census Economic Census data), estimate the company's employee count (from LinkedIn, Form 5500, or other signals), and multiply. Critical caveat: private companies typically trade at a 30-40% discount to public company multiples.
- **JobSpy open-source scraper:** A free Python library (GitHub: speedyapply/JobSpy) that scrapes Indeed, LinkedIn, Glassdoor, Google, and ZipRecruiter simultaneously for job postings. Job posting volume is a growth signal.

---

## WHAT'S NEW VS. WHAT NEEDS EXPANDING

This table maps every data source mentioned across all three reports against our current platform, showing what's already done, what needs to be expanded, and what's entirely new.

### Already Integrated — Needs Expansion

| Source | What We Have Now | What We're Missing | Effort to Expand | Priority |
|---|---|---|---|---|
| **SEC EDGAR** | Company list (517K CIK/EIN/SIC) | Full XBRL financials (revenue, income, debt, cash flow), DEF 14A executive compensation, 10-K text sections for labor-related analysis | Medium (8-12 hrs for XBRL; 12-16 for text extraction) | **HIGH** |
| **SAM.gov** | Entity registrations (826K) | Revenue ranges and employee counts from FOUO extracts (if obtainable), business type classifications for scoring | Low (2-4 hrs to parse existing fields better) | Medium |
| **GLEIF** | Entities + ownership links (379K + 499K) | Level 2 relationship analysis — building full corporate family trees for organizing campaigns | Medium (8-12 hrs) | Medium |
| **BLS** | Industry density + occupation-industry matrix | QCEW county-level employment data (would give geographic employment context), BLS growth projections by industry | Medium (6-10 hrs for QCEW bulk load) | **HIGH** |
| **Mergent Intellect** | 56K employer records | Broader extraction — current 56K is a subset of NYPL's 100M+ available records. Need systematic extraction by NAICS/geography | High (ongoing manual extraction due to library limits) | Medium |
| **USASpending** | 47K recipients | Executive compensation data (top 5 officers for entities receiving $30M+), more granular contract-level data | Low-Medium (4-8 hrs) | Medium |

### Entirely New — Not Yet in the Platform

| Source | What It Provides | Cost | Effort | Priority |
|---|---|---|---|---|
| **DOL Form 5500** | Employee benefit plan data — participant counts as employee proxy, plan sponsor EIN | Free bulk download | Low (4-6 hrs) | **HIGH** |
| **Census County Business Patterns** | Establishment counts + employment + payroll by NAICS at county/ZIP level | Free API | Medium (6-8 hrs) | **HIGH** |
| **PrivCo (via NYPL)** | Revenue, EBITDA, valuations for ~940K private companies with $1M+ revenue | Free at NYPL | Medium (ongoing manual extraction) | **HIGH** |
| **Data Axle / Reference Solutions (via NYPL)** | 44-60M US businesses — revenue ranges, employee ranges, lat/long, exec names, NAICS | Free at NYPL | Medium (500/search limit requires segmented extraction) | **HIGH** |
| **OpenCorporates** | Legal entity status, incorporation date, registered agent, officers for 90M+ US entities | Free (200 req/mo) or paid ($2,800/yr) | Low-Medium (4-8 hrs for API integration) | Medium |
| **SBA PPP Loan Data** | 4.9M small business borrower records with employee counts and NAICS | Free download | Low (3-5 hrs) | Medium |
| **Glassdoor** | Revenue ranges, employee ranges, CEO approval, salary data for 2M+ employers | Free (login wall) | Low for manual, High for systematic | Medium |
| **OpenStreetMap / Overpass API** | Physical locations of businesses — lat/long, addresses, business type | Free | Medium (6-10 hrs for integration pipeline) | Medium |
| **Overture Maps Foundation** | Standardized POI data with persistent IDs — better for joining than OSM | Free download | Medium (8-12 hrs) | Low-Medium |
| **JobSpy (job posting scraper)** | Job posting volume and details from Indeed/LinkedIn/Glassdoor/etc. | Free (open source) | Medium (6-10 hrs to build pipeline) | Medium |
| **Wikidata** | Structured financial data for ~5-15K major companies (CC0 license) | Free SPARQL API | Low (2-4 hrs) | Low |
| **Google Trends API** | Search interest trends by company/industry/geography | Free (alpha API) | Low (2-4 hrs) | Low |
| **State Business Registries** | Full registered business lists for specific states (FL, NY, CA, etc.) | Free-$900 depending on state | High (varies by state) | Low-Medium |
| **DOL UCC Filings** | Secured debt records indicating company borrowing activity | $10-20/search or free in some states | High (50 different systems) | Low |
| **VIIRS Nighttime Lights** | Regional economic activity proxy from satellite imagery | Free (NASA/NOAA) | Medium (specialized processing) | Low |
| **Kaggle/People Data Labs** | 7M+ company baseline dataset with domain, industry, size, LinkedIn URL | Free download | Low (2-3 hrs) | Low-Medium |

---

## THE IMPLEMENTATION PLAN

Here's how to actually do this, organized by wave. Each wave builds on the previous one and produces something useful on its own.

### Wave 1: Expand What We Already Have (Weeks 1-3)
**Why this comes first:** These sources are already in the database. We're just pulling more value out of them, which is much faster and lower-risk than adding entirely new data sources.

**1A. SEC EDGAR Full XBRL Financials**
- **What we'll do:** Download the `companyfacts.zip` bulk file (all XBRL data for all SEC filers), parse it, and load structured financial facts into a new `xbrl_facts` table. This gives us revenue, net income, total assets, total debt, and cash flow for ~8,000+ actively traded public companies.
- **Why it matters:** Right now we know that an employer is an SEC filer, but we don't know their actual financials. After this, we'll know exactly how much revenue Walmart or Amazon reports, what their profit margins are, etc. For public companies that also appear in our F-7 data, this completes the financial picture.
- **How it works, simply:** The SEC requires public companies to file their financial statements in a structured format called XBRL. Think of it like a spreadsheet that follows strict rules — every number has a label (like "Revenue" or "TotalDebt") and a time period. The SEC makes ALL of these available as one giant download. We parse that download and store each labeled number in our database.
- **Estimated effort:** 8-12 hours
- **Schema already designed:** Yes — see `SEC_EDGAR_Data_for_Labor_Relations_Research.md` in project knowledge

**1B. BLS QCEW Bulk Data Load**
- **What we'll do:** Download the Quarterly Census of Employment and Wages (QCEW) bulk CSV files from BLS. This gives us total employment and average wages broken down by industry AND county, covering 95%+ of US jobs.
- **Why it matters:** Right now we can say "the healthcare industry in New York has X% union density." After this, we can say "there are 45,000 healthcare workers in Queens County, earning an average of $62,000, and only 18% are unionized." That's much more actionable for targeting.
- **How it works, simply:** Every employer in America has to report how many workers they have and what they pay them, as part of their unemployment insurance. The BLS collects all of this and publishes aggregate totals (not individual company data) by county and industry. The files are just CSVs — we download them and load them into a new `bls_qcew` table.
- **Estimated effort:** 6-10 hours

**1C. USASpending Executive Compensation Expansion**
- **What we'll do:** Query the USASpending API for executive compensation data, which reveals the top 5 officers' compensation at any entity receiving over $30M in federal awards.
- **Why it matters:** Executive pay is a powerful organizing talking point ("Your CEO made $X while you made $Y"). This data is free and already linked to companies we track.
- **Estimated effort:** 4-8 hours

### Wave 2: Add High-Value New Free Sources (Weeks 3-6)
**Why this comes second:** These are entirely new data sources, but they're all free and fill critical gaps — especially employee counts for private companies and industry benchmarks for estimation.

**2A. DOL Form 5500 Bulk Load**
- **What we'll do:** Download the Form 5500 FOIA dataset from the Department of Labor. Load plan sponsor names, EINs, addresses, and participant counts. Match against our existing employer database using EIN as the primary key.
- **Why it matters:** This is one of the very few free sources where we can get an employee-count proxy for private companies. If "Acme Corp" sponsors a 401(k) plan with 500 participants, we have a reasonable estimate that Acme has roughly 500 employees. Not perfect (it includes retirees, and not all employers sponsor plans), but much better than nothing.
- **How it works, simply:** Federal law requires companies that offer retirement plans, health insurance, or other employee benefits to file a form (Form 5500) with the Department of Labor every year. That form says how many people are in the plan. The DOL publishes ALL of these forms in a downloadable dataset. We match them to our employer records by their tax ID number (EIN).
- **Estimated effort:** 4-6 hours
- **Key caveat:** Only covers employers that sponsor qualifying benefit plans (~800K plans)

**2B. Census County Business Patterns API Integration**
- **What we'll do:** Pull establishment counts, employment, and payroll by NAICS code at the county and ZIP code level from the Census Bureau's free API. Store in a `census_cbp` table.
- **Why it matters:** This lets us build a "revenue per employee" estimation model. If we know a company's NAICS code and approximate employee count, we can estimate their revenue using industry benchmarks. Census CBP provides the denominator for these calculations.
- **How it works, simply:** Every 5 years the Census Bureau surveys virtually every business in America (the Economic Census). In between, they publish annual estimates called County Business Patterns. These tell you things like "In Cook County, IL, there are 340 establishments in NAICS 722511 (Full-Service Restaurants) employing a total of 28,000 people with an annual payroll of $820 million." We use these numbers as benchmarks for estimating individual company financials.
- **Estimated effort:** 6-8 hours

**2C. SBA PPP Loan Data Load**
- **What we'll do:** Download the PPP loan dataset (4.9M records). Load company names, addresses, NAICS codes, loan amounts, and "jobs retained" figures. Match against existing employers.
- **Why it matters:** This is the rare dataset that covers very small businesses with actual employee counts. The "jobs retained" field tells us how many workers the company had at the time of the loan. While it's a 2020-2021 snapshot, it's one of the only ways to get individual company-level data for small employers.
- **Estimated effort:** 3-5 hours

### Wave 3: Library-Accessible Commercial Data (Weeks 6-10)
**Why this comes third:** Library data requires manual extraction sessions at NYPL, which means it's an ongoing process rather than a one-time download. Start the process early, but expect it to take weeks of incremental work.

**3A. PrivCo Deep Extraction (via NYPL)**
- **What we'll do:** Use NYPL's free PrivCo access to systematically research private companies in our database that lack financial data. Focus on employers in the F-7 list and NLRB target list that have $1M+ revenue.
- **Why it matters:** PrivCo provides actual revenue and EBITDA estimates for ~940K private US companies. This is the single best free source for private company financials. 85%+ of its coverage is bootstrapped and family-owned companies that PitchBook and Crunchbase miss entirely.
- **Estimated effort:** Ongoing (2-3 NYPL sessions per week, extracting 50-100 company profiles per session)

**3B. Data Axle Segmented Extraction (via NYPL)**
- **What we'll do:** Use NYPL's free Data Axle Reference Solutions access to extract business records in segments — by state, industry, and size range — building up a comprehensive small-business dataset.
- **Why it matters:** Data Axle covers 44-60M US businesses including very small ones. Each record includes estimated revenue ranges, employee size ranges, lat/long coordinates, executive names, and NAICS codes. This is the broadest coverage of any single source for small businesses.
- **How the extraction works:** The library version limits each search export to 500-1,000 records. So we search strategically — "all restaurants in Queens, NY with 50+ employees" gives a manageable batch. Repeat for every state × industry × size combination that matters.
- **Estimated effort:** Ongoing (systematic campaign over weeks/months)

### Wave 4: Alternative Signals and Estimation Models (Weeks 10-14)
**Why this comes last:** These are enrichment signals that become much more useful once you have the foundational data from Waves 1-3. They're about estimating what you can't directly measure.

**4A. Revenue-Per-Employee Estimation Model**
- **What we'll do:** Build a model that estimates private company revenue using: (1) their NAICS code, (2) their estimated employee count (from Form 5500, Data Axle, LinkedIn, or other sources), and (3) Census Economic Census benchmarks for revenue per employee by industry.
- **Why it matters:** This gives us a revenue estimate for ANY private company where we know the industry and approximate size. It's not precise (30-50% error margin), but it's the standard approach used by D&B, ZoomInfo, and every other commercial data provider.
- **How it works, simply:** Different industries have very different relationships between employees and revenue. A software company might generate $200K per employee, while a gas station generates $1M per employee. If we know a company is in the "gasoline station" industry and has about 50 employees, we can estimate they do about $50M in revenue. We adjust downward 30-40% because private companies typically earn less per employee than public ones.
- **Estimated effort:** 6-10 hours

**4B. Job Posting Volume Pipeline (via JobSpy)**
- **What we'll do:** Set up the open-source JobSpy library to periodically scrape job postings for employers in our database. Track posting volume over time as a growth/hiring signal.
- **Why it matters:** A company that suddenly doubles its job postings is probably growing fast or has high turnover — both are interesting for organizing. A company that stops posting entirely might be in financial trouble.
- **Estimated effort:** 6-10 hours

**4C. OpenCorporates Entity Verification**
- **What we'll do:** Use OpenCorporates' API (200 free requests/month, or paid plan) to verify legal entity status, incorporation dates, and registered officers for employers in our database.
- **Why it matters:** This helps catch companies that have dissolved, merged, or changed names — cleaning up stale records. It also adds officer/director names, which can reveal connections between seemingly unrelated companies.
- **Estimated effort:** 4-8 hours

**4D. OpenStreetMap / Overture POI Location Layer**
- **What we'll do:** Query OpenStreetMap's Overpass API (or download Overture Maps data) to get physical locations of businesses — store locations, offices, factories, warehouses. Match these against our employer database.
- **Why it matters:** Knowing that "Acme Corp" has 47 retail locations in the New York metro area is much more actionable for organizing than just knowing their headquarters address. Physical footprint also correlates with employee count.
- **Estimated effort:** 8-12 hours

---

## THE "REVENUE ESTIMATION STACK" — How This All Fits Together

Here's how the different data sources combine to estimate financial information for different types of companies:

### Public Companies (SEC Filers) — Best Coverage
- **Revenue, income, debt:** Direct from SEC EDGAR XBRL filings (Wave 1A) ✅ Exact
- **Executive compensation:** From SEC DEF 14A proxy filings + USASpending (Wave 1C) ✅ Exact
- **Employee count:** From 10-K filings + Form 5500 (Wave 2A) ✅ Exact or very close
- **Locations:** From 10-K segment disclosures + OpenStreetMap (Wave 4D) ⚠️ Partial
- **Corporate ownership:** From GLEIF + SEC filings ✅ Comprehensive

### Large Private Companies ($1M+ Revenue) — Good Coverage
- **Revenue:** From PrivCo (Wave 3A) or revenue-per-employee model (Wave 4A) ⚠️ Estimated (±30%)
- **Employee count:** From Form 5500 (Wave 2A) + Data Axle (Wave 3B) + LinkedIn ⚠️ Range estimate
- **Financial health:** From business credit scores (if accessible) + USASpending contract data ⚠️ Proxy
- **Locations:** From Data Axle (Wave 3B) + OpenStreetMap (Wave 4D) ⚠️ Partial
- **Growth signals:** From job postings (Wave 4B) ⚠️ Directional

### Mid-Size Private Companies ($100K-$1M) — Moderate Coverage
- **Revenue:** Revenue-per-employee model (Wave 4A) only ⚠️ Estimated (±50%)
- **Employee count:** From PPP data (Wave 2C) + Data Axle (Wave 3B) + Form 5500 (Wave 2A) ⚠️ Snapshot or range
- **Locations:** From Data Axle (Wave 3B) ⚠️ Usually just one
- **Everything else:** Limited — this is where proxy signals become critical

### Small/Micro Businesses (<$100K, <10 employees) — Poor Coverage
- **Revenue:** Data Axle revenue range (if available) or NAICS industry average ⚠️ Very rough
- **Employee count:** Data Axle or PPP data ⚠️ Often missing
- **Note:** These are usually not organizing targets, so the gap matters less for the platform

---

## COST SUMMARY

| Item | Cost | Notes |
|---|---|---|
| SEC EDGAR XBRL data | Free | Bulk download, no API key needed |
| BLS QCEW data | Free | Bulk CSV download |
| DOL Form 5500 data | Free | Bulk download from DOL |
| Census County Business Patterns | Free | API (free key required) |
| SBA PPP loan data | Free | Bulk download |
| USASpending executive comp | Free | REST API |
| Data Axle / Reference Solutions | Free | Via NYPL library card |
| PrivCo | Free | Via NYPL library card |
| Mergent Intellect (expanded) | Free | Via NYPL library card |
| OpenCorporates | Free (200/mo) or $2,800/yr | API |
| OpenStreetMap / Overture | Free | API or bulk download |
| JobSpy job scraper | Free | Open source Python library |
| Wikidata | Free | SPARQL API |
| **Total for Waves 1-4:** | **$0 - $2,800/yr** | Only cost is OpenCorporates if paid tier needed |

---

## DECISION POINTS FOR JACOB

Before we start implementing, here are the key decisions you need to make:

**Decision 1: Start with Wave 1A (SEC XBRL) or Wave 2A (Form 5500)?**
Both are high priority. SEC XBRL gives you deep financials on ~8K public companies. Form 5500 gives you employee count proxies for ~800K private companies. The platform's organizing use case probably benefits more from Form 5500 (since many organizing targets are private), but SEC XBRL is technically simpler.

**Decision 2: How much time per week for NYPL library extraction?**
Waves 3A and 3B require in-person or remote NYPL sessions to extract PrivCo and Data Axle data. This is the highest-value free data available, but it requires ongoing manual effort. Even 2 sessions per week (extracting 100+ company profiles per session) would build up significant data over a month.

**Decision 3: Do we want OpenCorporates on the free tier or paid?**
The free tier (200 requests/month) is enough for spot-checking individual companies. If we want to systematically verify all 67K current F-7 employers, we'd need the paid tier (~$2,800/year) or spread the work over many months.

**Decision 4: How do we handle estimation uncertainty in the UI?**
When we show estimated revenue for a private company, do we show a single number ("~$50M"), a range ("$30M-$70M"), or a confidence indicator ("$50M ●●○○")? The OpenAI report strongly recommends ranges with explicit uncertainty. This is a design decision that affects how organizers interpret the data.

---

## WHAT THIS DOESN'T COVER (Future Considerations)

These items came up in the research but are deferred for now:

- **Satellite imagery analysis** — Powerful but requires specialized processing infrastructure. Best for a future "Phase 5" after core data is solid.
- **Transaction data providers** (Bloomberg Second Measure, Consumer Edge) — Enterprise-priced ($50K+/year). Only worth considering with dedicated funding.
- **International registries** (UK Companies House, EU BRIS, etc.) — US-only scope for now.
- **Social sentiment monitoring** — Interesting for real-time alerts but not core to the organizing use case yet.
- **Supply chain / Bills of Lading data** — Relevant for manufacturing-heavy targets but niche. Defer until there's specific demand.
- **Full Dun & Bradstreet or ZoomInfo subscriptions** — $15K-$100K+/year. The library-accessible free sources cover 80%+ of what these provide.
