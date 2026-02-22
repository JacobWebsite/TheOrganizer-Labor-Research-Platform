# Gemini Research Handoff: Future Projects
## Labor Relations Research Platform — February 2026

### What This Document Is

This is a research assignment for Gemini. The projects below have been ranked by priority based on an interview with the project lead. For each project, there are specific research questions that need answers before Claude (the primary builder) can start implementation.

**What Gemini should do for each project:**
1. Find data sources and evaluate how accessible they are
2. Evaluate tools and methods — are they realistic for a solo developer?
3. Find academic research or prior art that's relevant
4. Where possible, draft implementation plans that Claude can execute

**Important context:**
- The platform runs on PostgreSQL with a FastAPI backend and Python data processing
- There are 207+ tables, 13.5+ million records, tracking ~100,000 employers and ~26,665 workplace organizations
- The developer has limited coding experience — Claude writes most of the code
- "On-demand deep dive" means: the scorecard flags promising targets, the user clicks on one, and the platform goes and gathers deeper intelligence about that specific employer in real time. This is NOT bulk scraping — it's targeted, user-triggered research for maybe 25-50 employers at a time

---

## Project 1: SEC EDGAR Integration (ESSENTIAL)

### What it does
Connects the platform to SEC's public company database to reveal corporate hierarchies (who really owns an employer), employee counts, executive pay, union contract mentions, and financial data. This feeds directly into the scorecard.

### What already exists in the project
- A detailed integration guide has already been written covering API endpoints, bulk downloads, XBRL tags, and matching strategy
- The matching plan: EIN join first, then fuzzy name matching, then Exhibit 21 subsidiary resolution
- Estimated overlap: 500-3,000 matches among unionized employers, 4,000-8,000 among Mergent employers
- Exhibit 21 parsing for subsidiaries is deferred to medium-term (format is messy and inconsistent)

### Research questions for Gemini

**1. Exhibit 21 parsing — what's the current best approach?**
- The project guide mentions CorpWatch API (~90% accuracy, Perl/MySQL, covers 2003+) and sec-api.io (paid, <0.1% error). Are there newer open-source tools that have emerged since?
- Has anyone built a modern Python-based Exhibit 21 parser using LLMs? Given that the format varies wildly (HTML tables, plain text, PDFs), an AI approach might work better than regex. Research what exists.
- What would it cost to use an LLM (like Claude or Mistral) to parse Exhibit 21 filings at scale? Estimate cost per filing and for the full ~7,000 annual filings.

**2. edgartools — evaluate this library**
- The project mentions `edgartools` (1,400 GitHub stars, 24 releases in 60 days). Is this still actively maintained? What can it actually do well, and where does it fall short?
- Can it extract Exhibit 21 subsidiary lists, or just structured XBRL data?
- How does it compare to the SEC's own bulk data downloads for the platform's specific needs (employee counts, EIN matching, CBA mentions)?

**3. Human capital disclosures — what's extractable?**
- Since 2020, the SEC requires human capital disclosures in 10-K filings. How standardized are these in practice? What percentage of filers include specific data like union membership rates, turnover, workforce demographics?
- Has anyone built a dataset or tool specifically for extracting human capital disclosures? Any academic papers analyzing the quality or consistency of these disclosures?

**4. Corporate hierarchy alternatives beyond EDGAR**
- OpenCorporates, GLEIF (Legal Entity Identifiers), and state Secretary of State records are other sources of corporate structure. Evaluate which of these are practically accessible and how they compare to EDGAR Exhibit 21 for the platform's needs.
- Is there a free or low-cost API that provides parent-subsidiary mappings already parsed?

---

## Project 2: State PERB Data (HIGH PRIORITY)

### What it does
Public Employment Relations Boards in states like New York, California, and Illinois oversee public-sector labor relations — elections, certifications, unfair labor practices for government workers. No one has ever built a unified dataset from these. This would be the first.

### What already exists in the project
- The future projects document identifies this as an original contribution — no open-source projects exist for state PERB data
- The plan involves FOIA/FOIL requests plus web scraping
- Estimated effort: 6-8 weeks

### Research questions for Gemini

**1. Inventory every state PERB and what data they publish online**
- For each of the following states, find: (a) the agency name and website, (b) what data is publicly available online without a records request, (c) whether they have a searchable database, (d) what file formats are available, (e) any known APIs or bulk download options:
  - New York (PERB)
  - California (PERB)
  - Illinois (ILRB)
  - Massachusetts (DLR)
  - New Jersey (PERC)
  - Ohio (SERB)
  - Pennsylvania (PLRB)
  - Michigan (MERC)
  - Washington (PERC)
  - Minnesota (BMS)
  - Connecticut (SBLR)
  - Oregon (ERB)
- For each, note: how many cases/certifications are in their online system, and how far back the records go

**2. What fields would we get?**
- What does a typical PERB certification record contain? (e.g., employer name, union name, unit description, number of employees, date, outcome)
- How standardized is this across states? Do they all track the same information, or is every state different?
- Are there any states that publish bulk data files (CSV, Excel) that could be loaded directly?

**3. FOIA/FOIL logistics**
- For the states that DON'T publish data online, what's the FOIA/FOIL process? Typical response times? Fees?
- Are there any states known to be particularly difficult or slow with records requests?
- Has anyone (academic researchers, journalists, other organizations) previously obtained PERB data through records requests? Any published datasets?

**4. Prior art and academic research**
- Has anyone attempted to build a multi-state PERB database before? Any academic papers analyzing state-level public sector labor board data?
- The FMCS (Federal Mediation and Conciliation Service) maintains some data on public sector disputes — how does this overlap with state PERB data?

---

## Project 3: Occupation-Based Similarity + Workforce Estimation (HIGH PRIORITY)

### What it does
Two related capabilities:
1. **Occupation similarity:** Comparing employers across different industries by what jobs their workers actually hold. A hospital and a university both employ janitors, food workers, and security guards — they might be in different industries but the organizing approach is similar.
2. **Workforce estimation:** For any employer, estimate how many people work there and what jobs they hold, even when no one has published that information directly.

### What already exists in the project
- The BLS industry-occupation matrix is already loaded (113,473 rows) — this shows the typical job breakdown for each industry
- Three separate AI research reports were synthesized into a detailed plan with 4 phases: display existing data → add headcount estimation → add composition model → add calibration engine
- Revenue-to-headcount formulas have been developed and cross-validated
- A "layer cake" approach combines evidence from SEC filings, NLRB records, OSHA inspections, financial data, and digital traces
- O*NET working conditions data has been identified as a quick win (free bulk CSV download, 2-3 hours to integrate)

### Research questions for Gemini

**1. BLS OEWS data — what's the latest and how to keep it current?**
- The platform already has the industry-occupation matrix loaded. What year is the most recent available release? How often does BLS update it?
- Is there an API to pull this data programmatically, or is it bulk-download only?
- The data uses NAICS and SOC codes. Are there known problems with NAICS codes being too broad (e.g., does "general hospitals" give a useful staffing pattern, or is it too generic)?

**2. Cosine similarity for occupation vectors — find examples**
- The plan calls for using "cosine similarity" to compare the job mix between two employers. Has anyone published code or a paper doing exactly this with BLS OEWS data?
- Are there alternative similarity measures that might work better for this specific use case (comparing proportions of different job types)?

**3. Revenue-per-employee ratios — best free sources**
- The plan mentions SUSB (Census), IBISWorld (via CUNY library), and Economic Census as sources for industry-specific revenue-per-employee ratios. Which of these is actually accessible right now, and what's the most recent year of data?
- Are there free, downloadable datasets of revenue-per-employee by NAICS code? The Census SUSB is supposed to have this — verify what's actually available.

**4. ACS PUMS demographics — practical feasibility**
- Phase 3 of the workforce estimation plan calls for overlaying Census demographic data onto occupation estimates. How large are the ACS PUMS files? Is it realistic to pre-compute occupation × metro area demographic profiles for the 50 largest metros?
- IPUMS is mentioned as an easier interface than raw Census files. What does IPUMS access require (registration, fees, terms of use)?
- Are there any pre-computed demographic profiles by occupation and metro area that someone has already published?

**5. The calibration engine — is it realistic?**
- The plan says to use ~50,000 NLRB election records (which have real employee counts) as an "answer key" to test estimation accuracy. Has anyone done something like this before — using NLRB data to validate workforce estimates?
- What's the minimum number of validated data points per industry needed for calibration to be meaningful?

**6. O*NET integration — verify ease of access**
- Confirm that O*NET bulk CSV downloads are still freely available with no scraping needed
- What specific tables would be most useful? (Work Context, Job Zones, and what else?)
- How do O*NET occupation codes map to SOC codes? Is the mapping 1:1 or does it require a crosswalk?

---

## Project 4: On-Demand Deep Dive System (HIGH PRIORITY)

### What it does
When the scorecard flags a promising target, the user clicks a button and the platform automatically goes and gathers deeper intelligence about that specific employer. This combines three capabilities that were originally separate projects:
- **Contract analysis:** Find and analyze any union contracts associated with the employer
- **Union/employer website scraping:** Visit relevant websites to pull public information
- **Employer embeddings:** Read company descriptions and job postings to find similar employers

All of this happens on-demand for maybe 25-50 specific employers, not in bulk.

### What already exists in the project
- Crawl4AI is already in use on the platform for web scraping
- Research docs exist on Firecrawl (87-94% accuracy on company profiles, 81K GitHub stars) and a "two-tool architecture" combining Crawl4AI with Firecrawl
- An AFSCME prototype for union site scraping already works
- The CBA analysis research identified 25,000+ freely available contracts from public sources
- LLM-based clause extraction achieves ~86% accuracy without training

### Research questions for Gemini

**1. On-demand scraping — what's realistic in real time?**
- If a user clicks "deep dive" on an employer, how long would it realistically take to scrape their website, find relevant contracts, and run employer similarity analysis? 10 seconds? 60 seconds? 5 minutes?
- What's the best architecture for this — run everything synchronously (user waits), or kick off background jobs and notify when done?
- Are there rate-limiting or legal concerns with scraping employer websites on-demand? Do most company websites have robots.txt restrictions that would block this?

**2. Finding contracts for a specific employer**
- If you know an employer's name and location, what's the fastest way to find their union contracts? Which of the 25,000+ public contract sources are searchable by employer name?
- SeeThroughNY (17,000 contracts), NJ PERC (6,366), Ohio SERB (3,000-5,000) — do any of these have APIs or search endpoints, or would you need to pre-index them?
- Is there a way to search across multiple contract repositories with a single query?

**3. Employer embeddings — practical implementation**
- The plan mentions using sentence-transformers to create "embeddings" (numerical representations) of company descriptions. What's the best current model for this? How fast is it?
- Where do company descriptions come from for non-public companies? LinkedIn? Google Business profiles? State Secretary of State filings?
- Has anyone published a dataset of company descriptions matched to NAICS codes or other industry classifiers?

**4. Job posting data for employer intelligence**
- Indeed MCP connector is already available. What data can it actually return for a specific employer? (Job titles, descriptions, salary ranges, posting dates?)
- Are there other free or low-cost sources for job posting data by employer? (Glassdoor, LinkedIn, government job boards?)
- Can job posting data realistically help estimate workforce size or composition? (e.g., if a company is hiring 20 warehouse workers, does that tell you anything about their current workforce?)

**5. Firecrawl vs Crawl4AI for on-demand use**
- Crawl4AI is already set up. Firecrawl has higher accuracy for structured data extraction. For on-demand company profile extraction (not bulk), which is better?
- What does Firecrawl actually cost for on-demand use? The project docs mention 81K GitHub stars but don't clarify if there's a free tier for small-scale use.
- Can either tool handle JavaScript-heavy employer websites (like those built with React or Angular)?

---

## Project 5: 5-Area Frontend Expansion (HIGH PRIORITY)

### What it does
Builds out the full navigation structure the platform was designed for: Territory (geographic view), Workplace Organizations (union side), Employers (company side), Organizing Targets (scorecard and comparisons), and Data Explorer (density, trends, analytics).

### What already exists in the project
- The initial frontend architecture was designed to allow this expansion
- Some areas likely have partial implementation already

### Research questions for Gemini

**1. Frontend frameworks and patterns for data-heavy dashboards**
- The platform uses FastAPI backend with a web frontend. What frontend frameworks are best suited for data-dense dashboards with lots of tables, maps, and filtering? Evaluate: React + a component library vs. a pre-built dashboard framework.
- Are there open-source admin/dashboard templates that could accelerate this? (e.g., Tremor, Refine, AdminJS, Retool-like tools)
- What are the best practices for building a geographic "territory" view with filtering by state, metro area, and county? What mapping libraries work well with React?

**2. Similar platforms to study**
- Are there any existing labor relations or organizing platforms (commercial or nonprofit) that have published their UI/UX patterns? LaborAction Tracker, UnionElections.org, etc.?
- What about adjacent domains — political campaign tools, community organizing platforms, investigative journalism tools — that solve similar "research a target entity" problems? How do they structure navigation and workflows?

**3. Data export and reporting patterns**
- Even though "Board Report Generation" as a standalone project cooled off, users will still need to export data. What are lightweight patterns for generating PDF or Excel exports from a web dashboard without building a whole reporting system?

---

## Project 6: Splink Entity Resolution (NEEDS RESEARCH)

### What it does
Replaces or upgrades the current name-matching system with a more sophisticated tool that can connect records across databases even when names are spelled differently, addresses are formatted differently, etc. Better matching means more complete data everywhere.

### What already exists in the project
- The platform already has a matching pipeline that achieves 96.2% employer-to-union linkage
- Splink (1,800 GitHub stars, UK Ministry of Justice) has been identified as the recommended tool
- Research docs describe it as "the highest-impact infrastructure investment"

### Research questions for Gemini

**1. Is Splink worth switching to given current match rates?**
- Current matching achieves 96.2%. What would Splink realistically add? Going from 96% to 98% sounds small, but it could mean thousands of additional matched records. Estimate the marginal gain.
- What's the learning curve for Splink? How much effort to integrate it into an existing PostgreSQL pipeline?
- Are there simpler alternatives that could push match rates higher without a full tool switch? (e.g., better name normalization, address standardization libraries)

**2. Splink practical evaluation**
- Is Splink still actively maintained? What's the release cadence?
- Does it work well with PostgreSQL directly, or does it require DuckDB or Spark?
- Find case studies or blog posts from organizations that adopted Splink — what were their results and pain points?

---

## Project 7: News & Media Monitoring (NEEDS RESEARCH)

### What it does
Automatically detects labor-related news about employers in the database — strikes, layoffs, lawsuits, organizing drives, NLRB complaints.

### Research questions for Gemini

**1. What are the realistic options?**
- newsapi.org ($449/month) was mentioned. Are there cheaper or free alternatives for monitoring labor news? Google Alerts, RSS feeds, government press releases?
- NLRB publishes its own decisions and complaints. Can these be monitored automatically via RSS or API?
- Are there any labor-specific news aggregation services that already exist?

**2. Entity matching problem**
- The hard part isn't finding news — it's matching a news article about "Amazon warehouse workers in Bessemer" to the right employer record in the database. How do news monitoring tools typically handle this? Is there an NLP approach that's practical for a solo developer?

---

## Summary: Priority Ranking

| Rank | Project | Gemini's Main Task |
|------|---------|-------------------|
| 1 | SEC EDGAR Integration | Evaluate Exhibit 21 parsers, edgartools library, human capital disclosure extractability |
| 2 | Occupation Similarity + Workforce Estimation | Verify data sources, find pre-built tools/examples, assess ACS PUMS feasibility |
| 3 | State PERB Data | Inventory every state agency, assess online availability, research FOIA logistics |
| 4 | On-Demand Deep Dive System | Evaluate real-time scraping feasibility, contract search methods, embedding tools |
| 5 | 5-Area Frontend Expansion | Find dashboard frameworks, study similar platforms, identify UI patterns |
| 6 | Splink Entity Resolution | Assess whether it's worth the switch given 96.2% current rates |
| 7 | News & Media Monitoring | Find affordable monitoring options, evaluate entity matching approaches |

---

*Generated from priority interview — February 17, 2026*
*For Gemini research use. Findings should be returned as structured reports that Claude can act on.*
