# Research Agent — Tool Specifications

**Purpose:** Defines exactly what each tool looks for, what data points it returns, and why each matters for organizing. This is the detailed guide for Claude Code to build the tool functions.

---

## TOOL 1: search_osha

**What it does:** Searches your OSHA tables for workplace safety violations at this employer.

**Why organizers care:** Safety violations are one of the strongest concrete grievances. Workers who feel unsafe at work are more motivated to organize. Serious/willful violations suggest management doesn't care about worker safety. Repeat violations suggest the problems are systemic, not one-off mistakes.

**Tables to query:**
- `osha_f7_matches` → to find the link between employer and OSHA establishments
- `osha_establishments` → to get establishment details
- `osha_violations_detail` → to get individual violations
- `osha_accidents` → to get workplace accident reports

**How to find matches:** 
1. If `employer_id` is provided → join through `osha_f7_matches` (or `unified_match_log` where source='osha' and status='active')
2. If no employer_id → fuzzy search `osha_establishments.estab_name` by company name + state

**Return these specific data points:**

| Data Point | Vocabulary Attribute | Why It Matters |
|-----------|---------------------|----------------|
| Total violation count | `osha_violation_count` | Raw scale of problems |
| Serious violations count | `osha_serious_count` | Serious/willful/repeat are the worst — OSHA only labels these when management is clearly at fault or the danger is severe |
| Total penalties in dollars | `osha_penalty_total` | Big fines = big problems. Also useful context for "this company was fined $X for putting workers at risk" |
| Most recent violation date | (part of `osha_violation_details`) | Recency matters — violations from last 2 years are much more relevant than ones from 10 years ago |
| Top 5 most common violation types | (part of `osha_violation_details`) | Reveals patterns — "this company keeps getting cited for fall protection" tells a story |
| Number of OSHA inspections | (part of `osha_violation_details`) | Many inspections = OSHA keeps coming back, which means ongoing problems |
| Any workplace accidents/fatalities | `safety_incidents` | Deaths or hospitalizations are the most powerful organizing facts |
| Number of establishments found | (metadata) | A company with 50 OSHA-inspected locations tells you about scale |

**Example output structure:**
```json
{
  "found": true,
  "source": "database:osha_violations_detail",
  "summary": "47 OSHA violations across 3 establishments, including 8 serious. $234,500 in penalties. Most recent: 2025-03-15. Pattern: fall protection (12), electrical (8), machine guarding (7). 1 workplace accident with hospitalization.",
  "data": {
    "violation_count": 47,
    "serious_count": 8,
    "willful_count": 1,
    "repeat_count": 2,
    "penalty_total": 234500,
    "establishment_count": 3,
    "most_recent_date": "2025-03-15",
    "inspection_count": 12,
    "top_violation_types": [
      {"type": "Fall Protection", "count": 12},
      {"type": "Electrical", "count": 8},
      {"type": "Machine Guarding", "count": 7}
    ],
    "accidents": [
      {"date": "2024-08-20", "type": "hospitalization", "description": "Worker fell from scaffold"}
    ]
  }
}
```

---

## TOOL 2: search_nlrb

**What it does:** Searches NLRB tables for union election history and unfair labor practice (ULP) charges involving this employer.

**Why organizers care:** Past elections tell you whether workers here have tried to organize before. A recent win means there's already a union (maybe at a different location). A recent loss is a warning sign — the company knows how to fight unions. ULP charges tell you how the company behaves — do they fire union supporters? Threaten workers? Refuse to bargain? The TYPE of ULP matters as much as the count.

**Tables to query:**
- `nlrb_employer_xref` → links employer names to NLRB case numbers
- `nlrb_elections` → election dates, outcomes, vote counts
- `nlrb_tallies` → detailed vote tallies
- `nlrb_cases` → case metadata (type, status, dates)
- `nlrb_participants` → who was involved (employer, union, individuals)
- `nlrb_allegations` → specific ULP allegation types
- `nlrb_voluntary_recognition` → voluntary recognitions (employer agreed to union without election)

**How to find matches:**
1. If `employer_id` → use `nlrb_employer_xref` 
2. Also search `nlrb_participants` where `participant_type` contains 'Employer' and name matches

**Return these specific data points:**

| Data Point | Vocabulary Attribute | Why It Matters |
|-----------|---------------------|----------------|
| Number of elections | `nlrb_election_count` | Volume of organizing attempts |
| Election details (date, union, outcome, vote count) | `nlrb_election_details` | The specifics — who tried, when, did they win, by how much |
| Win/loss record | (part of details) | Pattern of success or failure |
| Most recent election date and outcome | (part of details) | Recency is critical — a loss 2 years ago vs 15 years ago means very different things |
| Vote margins | (part of details) | A narrow loss (48-52) is very different from a blowout (20-80) — narrow losses suggest ripe conditions |
| ULP charge count | `nlrb_ulp_count` | How often the company gets accused of illegal anti-union behavior |
| ULP types/allegations | `nlrb_ulp_details` | "8(a)(3) discrimination" = they fire union supporters. "8(a)(5) refusal to bargain" = they won't negotiate. Each type tells a different story |
| ULP outcomes (settled, withdrawn, complaint issued) | (part of ulp_details) | A complaint actually issued by the NLRB means they investigated and found merit. Settlements often mean the company paid to make it go away |
| Voluntary recognitions | `voluntary_recognition` | Company agreed to recognize union without a fight — rare and significant |
| Which unions were involved | (part of details) | Tells you who has already tried to organize here — potential allies or competitors |

---

## TOOL 3: search_whd

**What it does:** Searches DOL Wage & Hour Division records for wage theft cases.

**Why organizers care:** Wage theft is personal — it means the company literally stole money from workers. Back wages owed, overtime violations, and minimum wage violations are concrete grievances that resonate with every worker. Repeat violators show a pattern of exploitation. Child labor violations are particularly powerful in public campaigns.

**Tables to query:**
- `whd_f7_matches` or `unified_match_log` (source='whd') → employer linkage
- `whd_cases` → individual cases
- `mv_whd_employer_agg` → pre-aggregated stats

**Return these specific data points:**

| Data Point | Vocabulary Attribute | Why It Matters |
|-----------|---------------------|----------------|
| Total case count | `whd_case_count` | Scale of wage theft |
| Total back wages owed | `whd_backwages` | Dollar amount stolen from workers — powerful talking point |
| Total civil penalties | `whd_penalties` | Government punishment level |
| Employees affected | `whd_employees_affected` | How many workers were cheated |
| Repeat violator flag | `whd_repeat_violator` | FLSA repeat = company keeps doing it even after getting caught |
| Child labor violations | (part of details) | Extremely powerful in public campaigns |
| Types of violations (FLSA overtime, min wage, H-2A, etc.) | (part of details) | Overtime theft vs minimum wage theft tells different stories about which workers are affected |
| Date range of violations | (part of details) | Recent vs old matters |
| Trade name vs legal name | (metadata) | Often reveals DBA names that help identify the company |

---

## TOOL 4: search_sec

**What it does:** Searches SEC EDGAR for public company financial data.

**Why organizers care:** For publicly traded companies, SEC filings reveal how much money the company makes, how much executives get paid, how many employees they have, and what they say about labor risks. The contrast between "CEO made $15M" and "average worker makes $32K" is one of the most powerful organizing messages. Also, if the company mentions "union activity" as a risk factor in their 10-K filing, that's direct evidence they're worried about organizing.

**Tables to query:**
- `sec_companies` → basic company data (CIK, SIC code, state)
- `corporate_identifier_crosswalk` → links to F7 employer via EIN/name
- `filing_sections` → text of filings (if loaded) for human capital disclosures
- `xbrl_facts` → structured financial data (revenue, employees)

**When to skip:** If company_type is known to be 'private' or 'nonprofit' — private companies don't file with SEC. The agent should note it skipped this and why.

**Return these specific data points:**

| Data Point | Vocabulary Attribute | Why It Matters |
|-----------|---------------------|----------------|
| Revenue | `revenue` | Company size and ability to pay |
| Employee count | `employee_count` | Workforce size from official filings |
| SIC/NAICS industry code | `naics_code` | Official industry classification |
| Executive compensation (top 5) | `exec_compensation` | The "CEO makes X while workers make Y" comparison |
| Human capital disclosures | (part of assessment) | What the company says about its workforce in SEC filings |
| Labor risk mentions | (part of assessment) | If "union" or "collective bargaining" appears in risk factors |
| Recent financial trend (revenue YoY) | `financial_trend` | Growing companies have more to share; shrinking companies may resist harder |

---

## TOOL 5: search_sam

**What it does:** Searches SAM.gov for federal contractor registration.

**Why organizers care:** Federal contractors must follow specific labor laws and executive orders. They can't retaliate as freely against organizing. Government contracts also represent revenue that depends on maintaining a good reputation — a public campaign about labor abuses at a federal contractor gets attention from Congress and contracting officers. Large contract amounts mean the company has a lot to lose.

**Tables to query:**
- `sam_entities` → contractor registration data
- `federal_contract_recipients` → USASpending contract amounts
- Match via `unified_match_log` (source='sam') or `corporate_identifier_crosswalk`

**Return these specific data points:**

| Data Point | Vocabulary Attribute | Why It Matters |
|-----------|---------------------|----------------|
| Is a federal contractor (yes/no) | (derived) | Binary but important — changes the legal landscape |
| Total federal obligation dollars | `federal_obligations` | Scale of government dependency |
| Number of contracts | `federal_contract_count` | Single contract vs many = different leverage |
| Contracting agencies | (part of details) | Which agencies — DOD, HHS, VA etc. Determines which pressure points exist |
| NAICS codes registered for | (metadata) | What services they sell to government |
| Small business status | (metadata) | SBA designations affect contracting rules |
| Active/inactive registration | (metadata) | Currently active = currently getting government money |

---

## TOOL 6: search_990

**What it does:** Searches IRS Form 990 data for nonprofit financial information.

**Why organizers care:** Nonprofits (hospitals, universities, social service agencies) are major organizing targets. 990s reveal total revenue, executive pay, assets, and tax-exempt status. The "your nonprofit CEO makes $800K while aides make $15/hr" message is devastating. Also, 990 data confirms whether an employer actually IS a nonprofit — some companies that seem private are actually nonprofits with public financial records.

**Tables to query:**
- `national_990_filers` → nationwide 990 filer data
- `employers_990_deduped` → deduplicated 990 employer records  
- Match via `unified_match_log` (source='990') or `national_990_f7_matches`

**When to skip:** If company_type is known to be 'public' (publicly traded companies don't file 990s). Note: some large health systems have both for-profit and nonprofit subsidiaries.

**Return these specific data points:**

| Data Point | Vocabulary Attribute | Why It Matters |
|-----------|---------------------|----------------|
| Total revenue | `nonprofit_revenue` | Size and financial capacity |
| Total assets | `nonprofit_assets` | Wealth of the organization |
| EIN | (metadata) | Confirms identity and enables cross-referencing |
| Tax-exempt type (501c3 vs 501c5 etc.) | (metadata) | c3 = charity/hospital/school, c5 = labor org, c6 = business league |
| NTEE code (nonprofit category) | (metadata) | E = healthcare, B = education, P = human services, etc. |
| Ruling date | (metadata) | How long they've been tax-exempt |

---

## TOOL 7: search_contracts

**What it does:** Searches F-7 data for existing union contracts at this employer.

**Why organizers care:** This is the most directly relevant data. If the employer already has union contracts (even at other locations or with different unions), that changes everything. It means: (1) the company already knows how to deal with unions, (2) there may be existing relationships to build on, (3) other workers at the same company have successfully organized. If there are NO contracts, that's also valuable — it confirms this would be new territory.

**Tables to query:**
- `f7_union_employer_relations` → the relationship between employers and unions
- `unions_master` → union details (name, affiliation, members)
- `f7_employers_deduped` → employer details

**Return these specific data points:**

| Data Point | Vocabulary Attribute | Why It Matters |
|-----------|---------------------|----------------|
| Existing contracts (yes/no) | (derived) | The fundamental question |
| Union names and affiliations | `union_names` | Who represents workers here — SEIU, Teamsters, UAW, etc. |
| Contract details (unit size, union local) | `existing_contracts` | How many workers are covered, which local represents them |
| Number of different unions | (part of details) | Multiple unions = complex labor environment |
| Total workers covered | (part of details) | What fraction of the workforce is already unionized |
| Historical vs current | (part of details) | Is this an active contract or one that expired years ago |

---

## TOOL 8: get_industry_profile

**What it does:** Gets BLS occupation and wage data for this employer's industry.

**Why organizers care:** Even if you know nothing else about a company, knowing its industry tells you a lot. BLS data reveals what jobs are most common (60% of hospital workers are nurses and aides), what they typically earn, and how the industry is projected to grow. This helps organizers understand what the workforce looks like before they ever walk in the door.

**Tables to query:**
- `bls_industry_occupation_matrix` → occupation mix by industry
- `naics_to_bls_industry` → maps NAICS codes to BLS industry codes
- `bls_national_industry_density` → union density by industry
- `estimated_state_industry_density` → state-level density estimates

**Return these specific data points:**

| Data Point | Vocabulary Attribute | Why It Matters |
|-----------|---------------------|----------------|
| Top 10 occupations and their share | `workforce_composition` | "40% of workers are cashiers, 20% are stock clerks" — who you're organizing |
| Median wages for those occupations | `pay_ranges` | What workers actually earn — establishes "are they underpaid?" |
| Industry union density (national) | (context) | "Only 4% of retail workers nationally are unionized" vs "65% of airline workers are" |
| State-level union density | (context) | Same industry can be very different in NY vs TX |
| Industry growth projection | (context) | Growing industries = more leverage for workers, more jobs to fill |

---

## TOOL 9: get_similar_employers

**What it does:** Finds comparable employers — companies in the same industry and size range that have been organized.

**Why organizers care:** "Workers at Company X, which is just like yours, voted for a union last year" is one of the most powerful organizing messages. Showing that similar companies have successfully organized makes it feel possible. This tool provides those comparisons.

**Tables to query:**
- `industry_occupation_overlap` → industry similarity scores
- `f7_employers_deduped` → to find employers in similar industries with union contracts
- `mv_unified_scorecard` → scores and tiers of similar employers

**Return these specific data points:**

| Data Point | Vocabulary Attribute | Why It Matters |
|-----------|---------------------|----------------|
| Top 5-10 most similar employers | `similar_organized` | Companies that look like this one |
| Which of those have unions | (part of details) | The key comparison |
| Their industries and sizes | (part of details) | Confirms they're actually comparable |
| Their organizing scores | (part of details) | How they compare on your scoring system |
| Recent NLRB elections at similar employers | (part of details) | Nearby momentum in the industry |

---

## TOOL 10: search_mergent

**What it does:** Searches Mergent Intellect business intelligence data.

**Why organizers care:** Mergent has data that government sources often lack — accurate employee counts, revenue figures, parent company relationships, executive names, and detailed industry classifications. For private companies that don't file with the SEC, Mergent may be the ONLY source of financial data.

**Tables to query:**
- `mergent_employers` → comprehensive business data (111 columns)

**Return these specific data points:**

| Data Point | Vocabulary Attribute | Why It Matters |
|-----------|---------------------|----------------|
| Employee count (site + total) | `employee_count` | Workforce size from commercial data |
| Revenue (actual or range) | `revenue` / `revenue_range` | Financial size |
| Parent company name | `parent_company` | Corporate hierarchy — who really controls this workplace |
| DUNS number | (metadata) | Unique business identifier for cross-referencing |
| Primary NAICS | `naics_code` | Industry classification |
| Year started | `year_founded` | Company age |
| Company status (active, branch, subsidiary) | (metadata) | Is this a standalone company or part of something bigger |

---

## TOOL 11: search_web

**What it does:** Uses Claude's built-in web search to find recent news, company information, and labor-related developments.

**Why organizers care:** Government databases are always months or years behind. Web search catches what's happening RIGHT NOW — recent layoffs, new organizing campaigns, strikes, management changes, expansion plans, worker complaints on social media or news sites. This is the "current events" layer on top of the historical database data.

**Search queries to run (in this order):**
1. `"{company_name}" workers OR employees OR labor` → labor-specific news
2. `"{company_name}" union OR organizing OR strike` → direct organizing news
3. `"{company_name}" layoffs OR hiring OR expansion` → workforce changes
4. `"{company_name}" wages OR pay OR benefits` → compensation news
5. `"{company_name}" OSHA OR safety OR violation` → safety news beyond the database

**Return these specific data points:**

| Data Point | Vocabulary Attribute | Why It Matters |
|-----------|---------------------|----------------|
| Recent labor-related news articles | `recent_labor_news` | Current events at this company |
| Evidence of recent organizing activity | `recent_organizing` | Is something already happening? |
| Layoff or expansion announcements | `turnover_signals` | Layoffs create anger; expansion creates leverage |
| Worker complaints (Glassdoor, Reddit, news) | `worker_complaints` | Unofficial grievances that don't show up in government data |
| Company self-description | (feeds into identity section) | How the company presents itself publicly |

---

## TOOL 12: scrape_employer_website

**What it does:** Uses Crawl4AI to read the company's own website — specifically the About, Careers, and Locations pages.

**Why organizers care:** The company's own website reveals things no government database has: how many locations they operate, what jobs they're currently hiring for (and how badly — "urgently hiring" signals high turnover), what they say about their culture and values (useful for holding them accountable), and executive/leadership names.

**Pages to target:**
1. Homepage → company description, size claims
2. About / About Us page → history, mission, leadership
3. Careers / Jobs page → current openings, pay ranges, locations hiring
4. Locations / Contact page → facility addresses
5. Leadership / Team page → executive names and titles

**Return these specific data points:**

| Data Point | Vocabulary Attribute | Why It Matters |
|-----------|---------------------|----------------|
| Company self-description | (feeds into identity) | What they say they do, in their own words |
| Self-reported employee count | `employee_count` | If they claim "5,000+ employees" on their site |
| Facility locations | `major_locations` | Where they operate — organizers need to know this |
| Current job openings count | `job_posting_count` | Lots of openings = high turnover = workers are unhappy |
| Job titles and pay ranges | `job_posting_details` | What positions exist, what they pay |
| Executive/leadership names | `exec_compensation` | Who runs the place |
| Year founded | `year_founded` | Company age and stability |
| Any mention of unions/labor | `recent_organizing` | Some companies have anti-union messaging right on their site |

