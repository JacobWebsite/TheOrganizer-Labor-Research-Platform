# Labor Relations Research Platform — Brainstorming Response

**Generated:** March 4, 2026

---

## 0. The Proof Point: This Actually Works

Before diving into what the platform *could* do, it's worth leading with what it already *does.* The scoring system has been validated against 6,403 NLRB election outcomes. Win rates are monotonically increasing by tier:

| Tier | Win Rate | Employer Count |
|------|----------|----------------|
| Priority | 90.9% | ~2,891 |
| Strong | 84.7% | ~15,000 |
| Promising | 80.2% | ~40,700 |
| Moderate | 77.8% | ~50,400 |
| Low | 74.1% | ~37,900 |

This isn't theoretical. The data linkages across 30+ government sources produce a scoring system that correctly rank-orders employers by organizing potential. The base win rate for NLRB elections overall is ~79.9%; the platform identifies a subset where unions win 91% of the time, and another where they win only 74%. That 17-point spread, produced entirely from public data, is the foundation everything else builds on.

Any pitch, landing page, grant application, or partnership conversation should lead with this number.

---

## I. For Union Organizers

### The Target Selection Engine: "Where Should We Organize Next?"

The most valuable screen in the entire platform is a **filtered, ranked list of non-union employers** that an organizer can customize to their specific union's jurisdiction and capacity. Here's what that looks like concretely:

**The Inputs (left sidebar filters):**
- Industry (NAICS, with plain-English labels — "Nursing Homes" not "623110")
- Geography (state, metro, county, or radius from a zip code)
- Employer size range (50-500, 500-2000, etc.)
- Union already present at parent company? (yes/no/either)
- Minimum signal count (how much do we know about this employer?)

**The Ranked Output (main panel):**

Each employer card shows a **heat signature** — not a single score, but a visual pattern:

| Signal | Status |
|--------|--------|
| OSHA violations | 12 violations, $340K penalties (3x industry avg) |
| Wage theft | 2 WHD cases, $180K backwages |
| NLRB history | Election lost 47-52 in 2022 |
| Sister facilities unionized | 3 of 7 subsidiaries have CBAs |
| Industry turnover | JOLTS quit rate 4.1% (vs 2.2% industry avg) |
| Federal contracts | $12M USAspending (leverage point) |
| Injury rate | SOII rate 8.4/100 FTE (industry avg 6.3) |
| Benefits gap | NCS: no retirement plan access |

**What makes this different from anything else available:** No single government website shows you this. OSHA's site shows violations. DOL's site shows wage cases. NLRB's site shows elections. A journalist can spend two weeks pulling these threads together for one employer. This platform does it for 4.4 million employers simultaneously.

**The "Near Miss" Filter** — This is the killer feature for organizers, and it's **buildable today as a day-one feature.** The data already exists: NLRB elections have vote tallies, OSHA/WHD records have dates, and the matching system links them. A single SQL query can produce the list.

Filter for employers where:
- An NLRB election was held in the last 5 years AND lost by <10% margin
- AND the employer has accumulated new OSHA/WHD violations since that election
- AND injury rates have worsened (SOII trend data)

These are second-chance campaigns. The workers already showed interest. Conditions have gotten worse. The data tells you exactly which ones to revisit. With 33K NLRB elections and 2.2M OSHA violations, there are hundreds of these hiding in the data right now. This isn't a roadmap item — it's a query away from being a live feature.

**The "Corporate Domino" View** — When an organizer identifies a corporate parent (via GLEIF/SEC/CorpWatch) that owns multiple facilities:
- Show a map with pins: green = unionized subsidiary, red = non-union
- For each non-union facility, show its violation profile compared to the unionized siblings
- Surface the pattern: "Parent company XYZ has 15 facilities. The 8 unionized ones average 2.1 OSHA violations/year. The 7 non-union ones average 6.8." That's not just data — that's an organizing argument.

### The Campaign Dossier: "Tell Me Everything About This Employer"

When an organizer clicks into a specific employer, they need a **one-page brief** they can print and bring to a meeting. Not a data dump — a narrative.

**Page 1: The Story (auto-generated summary)**

> **Sunrise Healthcare Holdings** operates 7 nursing homes across NJ and PA. 3 facilities are unionized (SEIU 1199). The 4 non-union facilities have collectively received 47 OSHA citations ($890K penalties) and 3 wage theft cases ($210K backwages) since 2020. The parent company received $8.2M in PPP loans during COVID, reporting 1,200 employees. Industry injury rates at nursing facilities spiked from 6.3 to 13.1/100 FTE during the pandemic. Workers in this region earn a median of $39K (nursing assistants) vs. $82K nationally for RNs. The company is a federal contractor (Medicare/Medicaid) receiving $22M annually.

This paragraph combines F7, OSHA, WHD, GLEIF, PPP, SOII, OES, and USAspending data into a coherent story. No human researcher assembled this. The platform did.

**Page 2: The Comparison**

A side-by-side table: this employer vs. industry average vs. unionized peers in the same industry/region:

| Metric | This Employer | Industry Avg | Unionized Peers |
|--------|--------------|--------------|-----------------|
| OSHA violations/year | 6.7 | 3.2 | 1.8 |
| Avg penalty amount | $18,900 | $8,200 | $5,100 |
| Wage theft cases | 3 | 0.8 | 0.3 |
| Injury rate (SOII) | 8.4/100 | 6.3/100 | 4.9/100 |
| Quit rate (JOLTS proxy) | ~4.1% | 2.2% | 1.8% |
| Benefits access (NCS) | No retirement | 64% | 89% |
| Worker median wage (OES) | ~$39K | $42K | $48K |

The Gower similarity engine (270K comparable pairs) makes the "peers" column possible. This table alone could change an organizing conversation.

**Page 3: The Leverage Points**

- **Federal contracts:** $22M in Medicare/Medicaid. Davis-Bacon and prevailing wage implications. Government can exert pressure.
- **Tax-exempt status:** 990 filing shows CEO compensation of $1.2M. Nonprofit mission vs. worker treatment is a powerful narrative.
- **Corporate parent:** Owned by PE firm (GLEIF chain). 3 unionized facilities proves the company *can* work with unions — they just choose not to at these 4 locations.
- **NLRB history:** Lost election at Facility B in 2022 by 5 votes. 12 new OSHA violations since then.

### Mid-Campaign Intelligence

Once a campaign is active, the platform becomes a **monitoring dashboard:**

- **OSHA alert:** New violations filed against the employer during the campaign. Real-time ammunition.
- **NLRB filing tracker:** ULP charges, election petitions, objections — all from NLRB data.
- **Corporate restructuring detection:** If GLEIF/SEC data shows ownership changes, name changes, or subsidiary restructuring during a campaign, that's a red flag (and potentially illegal).
- **Wage comparison tool:** "Workers at [employer] earn $14.20/hr. The union contract at [comparable employer] specifies $18.50/hr for the same job classification." OES + CBA provision data makes this automatic.

### The Contract Comparison Engine

The CBA provisions database (14 categories of extracted contract language) is an underappreciated standalone product. For bargaining prep teams, this could be the most-used feature on the platform:

**"What do other unions in my industry negotiate for?"**
- Search by industry, geography, union, or employer
- Compare provisions side-by-side across contracts: wage scales, grievance timelines, seniority rules, health insurance contributions, PTO accrual, just-cause protections
- Show the range: "In healthcare CBAs in the Northeast, grievance procedures range from 3 to 5 steps, with arbitration timelines between 30 and 90 days"
- Identify outliers: "This contract's health insurance contribution is in the bottom 10% for the industry"

**For first-contract negotiations**, this is invaluable. A newly organized workplace has no baseline — they don't know what's "normal" to ask for. The platform can show them: "Here are 15 contracts at similar employers. Here's what they all include. Here's where you have room to push."

**For contract renewals**, it enables: "Since your last contract, 8 comparable employers have negotiated wage increases averaging 4.2%. Your current proposal of 2.5% is below the market."

No centralized, searchable CBA provision database exists publicly. Union researchers currently share contracts informally or through expensive subscription services. This alone could drive platform adoption among union staff.

---

## II. For Researchers and Journalists

### Research Questions Nobody Has Been Able to Answer (Until Now)

**1. "Does unionization actually improve workplace safety?"**

You have the data to answer this rigorously for the first time outside academia:
- 146K unionized employers (F7) matched to OSHA violations
- 4.4M non-union employers also in OSHA
- SOII industry injury rates as baseline
- Gower similarity to control for industry/size/geography

The study design: Compare OSHA violation rates between F7-matched employers and their Gower-nearest non-union comparables, controlling for NAICS and geography. You already know from audit findings that unionized OSHA establishments have different violation patterns. The SOII data lets you benchmark against national industry rates.

**This has never been done at this scale.** Academic studies typically look at one industry or one state. You have national coverage across every industry.

**2. "The Private Equity Labor Impact Study"**

Using GLEIF ownership chains + CorpWatch relationships:
- Identify employers acquired by PE firms (ownership change events)
- Track OSHA violations, WHD cases, JOLTS-proxied turnover, and NLRB activity before and after acquisition
- Compare injury rates (SOII) at PE-owned facilities vs. independently owned in the same industry
- Check whether PE-owned facilities are more or less likely to have unions (F7 presence)

This is a *major* investigative story. PE ownership of healthcare, retail, and manufacturing is a hot political topic. Your data can show whether PE ownership correlates with worse worker outcomes across thousands of employers, not just anecdotes.

**3. "The Geography of Worker Exploitation"**

Combine at the county level:
- OSHA violation density (per capita or per establishment from CBP)
- WHD wage theft totals
- Union density (BLS state/industry)
- LODES commuting patterns (who's commuting INTO high-violation areas?)
- ACS demographics (who are the workers? race, education, age)
- QCEW average wages

Build a **county-level index of worker vulnerability.** Map it. The story writes itself: "In [County], workers earn 30% below the national average, face 2x the injury rate, have zero union representation, and 40% commute from neighboring counties with even fewer protections."

**4. "Federal Contractors Behaving Badly"**

Cross-reference SAM.gov/USAspending recipients with:
- OSHA serious/willful violations
- WHD repeat offenders
- NLRB ULP charges

"The federal government awarded $X billion in contracts to employers with active wage theft cases." This is a straightforward FOIA-style analysis that becomes trivial with your crosswalk.

### The Journalist's Interface

A journalist doesn't want filters and scores. They want **story leads.**

**"Story Finder" Mode:**
- Input: Industry or geography or company name
- Output: Pre-computed anomalies ranked by newsworthiness:
  - "Company X received $50M in federal contracts while owing $2M in unpaid wages"
  - "This hospital chain's non-union facilities have 4x the injury rate of its unionized ones"
  - "In [County], wage theft cases increased 300% since 2020 while OSHA inspections decreased 40%"
  - "This employer lost 3 union elections in 5 years and has been cited for 8 ULPs"

Each story lead links to the underlying data with source citations. The journalist verifies, adds context, and publishes. The platform isn't writing the story — it's finding the needle in 4.4 million haystacks.

**The "Company Check" for Journalists:**

Type in any company name. Get a one-page profile combining every source that matches. Journalists already do this manually — they check OSHA, then DOL, then NLRB, then SEC. Your platform does all of it in one search. The 96% accuracy matching system is what makes this possible; no other tool links these sources.

---

## III. For Workers

### The Employer Report Card

A worker types in their employer name (or finds them via location). They see a **simple, visual report card** — not scores or percentages, but plain-language assessments:

**Workplace Safety: D+**
> Your employer has been cited for 12 OSHA violations in the last 5 years, including 3 classified as "serious." That's 3x the average for similar companies in your industry. The most recent citation was for [specific violation type] in [month/year].

**Wage Compliance: C**
> Your employer has 1 wage theft case on record with the Department of Labor, involving $45,000 in unpaid wages. While not the worst in the industry, similar-sized companies in your area average 0.3 cases.

**Worker Benefits: Below Average**
> Based on industry data, only 52% of workers at companies like yours have access to both medical insurance and a retirement plan. The national average for your industry is 64%.

**Union Status: Not Unionized**
> Your employer does not currently have a union contract on file. However, 3 similar companies in your area do. Workers at unionized companies in your industry earn an average of $6,200 more per year.

**Key context that makes this work:**
- OES tells them what workers in their job/area actually earn (not what their employer says is competitive)
- SOII tells them whether their workplace injury rate is normal
- NCS tells them whether their benefits package is typical
- The Gower comparables show them what "similar companies" actually look like

### The "Am I Underpaid?" Tool

This is potentially the single most viral feature:
- Worker inputs: job title, location, employer (optional)
- Platform returns: OES percentile data for that occupation x area
  - "Nursing assistants in Bergen County, NJ earn between $33,200 (25th percentile) and $46,100 (75th percentile). The median is $39,100."
  - If employer provided: "Workers at unionized nursing homes in NJ earn a median of $43,800 — 12% more than the industry median."

This exists in fragments (BLS wage data is public), but combining it with CBA provision data (actual union contract wage rates) and employer-specific context is new. The comparison to unionized peers is the unique value.

### The "What Would a Union Mean for Me?" Calculator

Based on CBA provisions data + OES + NCS:
- Show average wage differential between union and non-union in their industry/occupation
- Show typical CBA provisions (grievance procedure, seniority protections, health insurance, PTO)
- Show NLRB election outcomes for their industry ("In your industry, unions win X% of elections")
- Link to any near-miss elections at their specific employer

This transforms abstract "should I support a union?" into concrete, personalized data.

---

## III-B. For Public Sector Workers and Unions

The platform contains a separate public sector dataset — 24 parent unions, 1,520 locals, 7,987 public employers, 438 bargaining units — that deserves its own treatment because **public sector organizing operates under fundamentally different rules.**

### What's Different About Public Sector

- **Different legal frameworks:** Public sector bargaining is governed by state law, not the NLRA. Some states have robust collective bargaining rights; others ban it entirely. The platform should map which legal regime each public employer falls under.
- **Different leverage points:** Public employers answer to taxpayers and elected officials, not shareholders. The leverage isn't "bad OSHA record" — it's "this school district spends $X on administrator salaries while teachers earn $Y" (990/budget data + OES wage comparisons).
- **Different transparency:** Public employers have FOIA/open records obligations. Budget documents, salary schedules, and board meeting minutes are all public. The platform could link to or index these.
- **Different organizing dynamics:** Public sector union density is ~33% nationally vs. ~6% private sector (BLS density data). The question isn't "should we organize?" — it's often "how do we strengthen an existing unit?" or "how do we resist decertification?"

### Public Sector Features

**The "Government Employer Accountability" Profile:**
- Budget data (where available) showing how taxpayer money is allocated
- OES wage data compared to private sector equivalents in the same area
- OSHA violations at government facilities (yes, governments get OSHA citations too)
- ACS workforce demographics for the public sector in that geography
- CBA provisions at comparable government employers

**The "State Labor Law Map":**
- Visual map showing collective bargaining rights by state and sector (education, public safety, general government)
- Overlay with BLS state density data and QCEW public sector wages
- Track legislative changes (right-to-work, collective bargaining restrictions) and correlate with outcomes

**Anti-Privatization Intelligence:**
- When a public service is contracted out, the private contractor enters the platform's private-sector databases (SAM.gov, OSHA, WHD)
- Compare the contractor's labor record to the public agency it replaced
- "The city outsourced waste collection to Company X, which has 8 OSHA violations and 2 wage theft cases. The city's own workforce had zero."

---

## IV. For Policymakers and Advocates

### The Policy Dashboard

**"Right-to-Work Impact Tracker"**

Compare across states with different labor laws:
- Union density trends (BLS state density, 1978-2025) — 47 years of data
- OSHA violation rates per establishment (your data + CBP establishment counts)
- WHD wage theft totals per worker (your data + QCEW employment)
- Average wages by industry (QCEW/OES)
- Injury rates (SOII)

The analysis: "In the 10 years after [State] passed right-to-work, union density dropped X%, while workplace injuries increased Y% and average wages grew Z% slower than neighboring states." You have all the data to compute this.

**"Federal Contractor Accountability Dashboard"**

For congressional staff and advocacy organizations:
- Total federal contract dollars going to employers with OSHA serious/willful violations
- Total going to employers with WHD cases
- Total going to employers with NLRB ULP charges
- Trend over time (USAspending fiscal years)
- Breakdowns by agency, industry, state

This directly supports policy arguments about contractor debarment, prevailing wage, and procurement reform.

**"Industry Early Warning System"**

Monitor for emerging labor crises by industry x geography:
- Spike in OSHA violations (rolling 12-month vs. prior year)
- Spike in WHD complaints
- Spike in NLRB petitions (organizing surge = something is wrong)
- JOLTS quit rates exceeding historical norms
- SOII injury rates trending up
- QCEW employment dropping (layoffs)

When multiple signals fire simultaneously in the same industry/geography, that's a leading indicator. Healthcare in rural counties. Meatpacking in the Midwest. Warehousing in inland distribution hubs. The platform can surface these automatically.

### The Advocacy Toolkit

**"The Cost of Union Avoidance" Report Generator**

For a given employer or industry:
- Total OSHA penalties paid
- Total WHD backwages owed
- Total legal fees implied by NLRB ULP cases
- Compare to estimated cost of a union contract (CBA wage differentials x employee count)
- Argument: "This company spent $X fighting workers and paying fines. A union contract would have cost $Y and prevented Z injuries."

**"Public Funding and Labor Compliance" Analysis**

Cross-reference PPP loans + USAspending + 990 tax exemptions with enforcement records. Present the data neutrally and let users draw conclusions:
- For any employer: show total public funding received (PPP loans, federal contracts, tax-exempt status) alongside their OSHA, WHD, and NLRB record
- Aggregate by industry, state, or federal agency: "Of the 500 largest federal contractors in healthcare, X% have open OSHA violations and Y% have WHD cases on record"
- Trend analysis: how has enforcement activity changed over time among publicly funded employers?

The framing matters here. If the platform wants credibility with journalists and academics, the tone should be neutral — present the juxtaposition of public funding and labor compliance data, and let researchers, reporters, and advocates draw their own conclusions. Editorializing reduces the platform's utility as a trusted data source.

---

## V. Big-Picture Platform Design

### 1. The Single Most Valuable Thing

**The cross-source employer profile that doesn't exist anywhere else.**

Every piece of data in your platform is publicly available somewhere. The OSHA data is on OSHA's website. The NLRB data is on the NLRB website. The wage data is on BLS. But nobody — not the government, not academia, not any existing tool — links all of these together for the same employer and presents them in one view.

The 2.2M-row match audit trail and the corporate crosswalk are the actual intellectual property here. The data is commodity. The linkage is the moat.

The single most valuable action: **letting someone type in an employer name and see everything the federal government knows about how that employer treats workers, in one place, in 3 seconds.**

### 2. Missing Data That Would Be Transformative

**Tier 1 (would dramatically change the platform):**
- **State-level workers' comp claims data** — many states publish this. It's the most direct measure of workplace injuries at the employer level, far more granular than SOII industry averages.
- **NLRB ULP case details** — you have elections, but the full docket of unfair labor practice charges (employer intimidation, illegal firings during campaigns) would be enormously valuable. NLRB publishes these.
- **State attorney general wage theft actions** — many states have enforcement beyond federal WHD. California, New York, Illinois all publish these.
- **Glassdoor/Indeed reviews** (scraped or API) — worker sentiment at the employer level. Combined with your enforcement data, low reviews + high violations = strong signal.

**Tier 2 (valuable additions):**
- **EEOC discrimination charges** by employer — adds a "discrimination" signal
- **MSHA** (Mine Safety) data — equivalent of OSHA for mining, 200K+ violations
- **State OSHA plan data** — 22 states run their own OSHA programs with separate databases
- **Bankruptcy filings** — employers entering/exiting bankruptcy during organizing campaigns
- **Lobbying disclosure** — employers spending money to fight labor legislation (OpenSecrets data)

**Tier 3 (ambitious but high-impact):**
- **Real-time NLRB petition filings** — currently there's a lag. Real-time data would let the platform alert organizers to active campaigns nearby
- **Health insurance plan quality data** (CMS) — for healthcare employers especially, what insurance do they offer their own workers vs. what they provide patients?
- **Prevailing wage determinations** (DOL Davis-Bacon) — what the government says workers on federal projects should earn, compared to what contractors actually pay

### 3. AI Integration: The Compounding Knowledge Base

The platform already has a research agent with a **human-in-the-loop learning system** (Gemini-powered dossier generation with quality gates, human fact validation, contradiction detection, and score feedback loops). This is a genuine competitive moat that most data platforms lack.

**How the learning loop works:**
- AI generates research dossiers on employers, extracting structured facts
- Human reviewers validate, correct, or reject individual facts
- Validated facts at quality >= 7.0 feed back into employer scores; facts < 5.0 are rejected
- The system tracks which research patterns produce high-quality vs. low-quality outputs
- Each research cycle makes the next one better — the platform literally gets smarter with use

This compounding knowledge base means that after 1,000 research runs, the platform has 1,000 employer dossiers that no other dataset contains — human-validated intelligence layered on top of government data. After 10,000 runs, it's an irreplaceable corpus. This is the kind of asset that takes years to replicate.

**Where LLMs add additional value:**

- **Natural language search:** "Show me nursing homes in New Jersey with OSHA violations and no union" translates to filters and returns results. This is the accessibility layer that makes the platform usable by non-technical people.

- **Dossier narrative generation:** You already have this with Gemini. The key is that the AI writes the *story* connecting the data points. Raw data says "12 OSHA violations, 2 WHD cases, lost election 2022." The AI says "This employer has a pattern of workplace safety failures and wage theft that has worsened since workers narrowly lost a union election in 2022."

- **Anomaly detection:** AI can scan millions of employer profiles for unusual patterns that humans wouldn't search for: "This employer's OSHA violations dropped to zero the year before an NLRB election, then spiked immediately after the union lost." That's a pattern that implies strategic behavior.

- **Question answering over CBA provisions:** "What's the typical grievance procedure timeline in healthcare CBAs?" — the AI can analyze the CBA text corpus and synthesize answers. This is directly useful for bargaining preparation.

- **Automated report generation:** Monthly/quarterly reports for union leadership: "Here are the 10 employers in your jurisdiction whose profiles changed most this quarter" — new violations, new NLRB activity, ownership changes, contract expirations.

**Where LLMs should NOT be used:**
- Scoring or ranking employers (keep this deterministic and auditable)
- Making causal claims ("this employer will lose a union election")
- Generating content that could be used in legal proceedings without human review

### 4. Biggest Risks

**Ethical:**
- **Employer retaliation:** If employers discover the platform is being used to target them, they may preemptively retaliate against workers. The platform should never expose which specific workers or organizers are researching which employers. Privacy-by-design.
- **Data weaponization by employers:** An anti-union employer could use the same data to identify which of their facilities are "at risk" and deploy union avoidance consultants preemptively. Consider whether some features should be access-controlled.
- **Accuracy liability:** If an organizer relies on a match that's in the 4% error rate and makes claims about an employer based on another company's violations, that's a credibility problem. Every cross-source link needs a visible confidence indicator.

**Practical:**
- **Data freshness:** Government data lags by months to years. An employer could have resolved violations, changed ownership, or improved conditions — and the platform still shows old data. Timestamps and "as of" dates must be prominent.
- **The "big number" problem:** 4.4M employers is impressive but most have very thin profiles (1-2 data sources). The most useful employer profiles are the ones with 5+ sources linked — but that's maybe 50K-100K employers. Managing user expectations about coverage.

**Strategic:**
- **Legal challenges:** Employers or industry groups might argue the platform constitutes defamation or tortious interference. Everything must be clearly sourced to public government data with citations.
- **Government data access:** If a hostile administration restricts access to OSHA, NLRB, or WHD data (this has happened), the platform's pipeline breaks. Consider data archiving and redundancy.

### 5. Correlation vs. Causation

This is critical. The platform should adopt a clear framework:

**Language discipline:**
- Never say "X causes Y." Say "X is associated with Y" or "employers with X tend to also have Y."
- Always show the base rate. "This employer has 12 OSHA violations" means nothing without "the average for this industry/size is 3.2."
- When showing trends, note confounders. "OSHA violations increased after the union lost the election" could mean conditions worsened OR could mean the new safety committee started reporting more.

**The "reporting bias" disclosure:**
Every employer profile should include a note: "Unionized workplaces often have higher reported violation rates because union safety committees are more likely to file complaints. Higher violation counts at unionized employers may reflect better reporting, not worse conditions."

**The scoring system already handles this correctly** — it flags for investigation, not prediction. This framing should be front-and-center in every user-facing output. "This score indicates this employer is worth investigating, not that a union campaign will succeed here."

### 6. Sustainability and Revenue

The OpenSecrets comparison is apt, but OpenSecrets has foundation donors and a 40-year head start. A realistic sustainability plan:

**Freemium Model:**
- **Free tier (public good):** Basic employer search, report cards, wage lookup. No login. This drives traffic, media citations, and public trust.
- **Pro tier (union staff, $50-200/month per seat):** Full dossier generation, CBA provision search, near-miss filters, campaign monitoring dashboards, API access with higher rate limits.
- **Enterprise/API tier (research institutions, law firms, $500-2000/month):** Bulk data exports, custom analyses, white-label embeds, priority support.

**Grant Funding:**
- Labor-focused foundations (Ford Foundation, Kalmanovitz Initiative, Worker Institute at Cornell) actively fund exactly this kind of infrastructure
- Academic partnerships (ILR schools) could co-fund in exchange for research API access
- Government contracts (DOL, state labor departments) for data integration services

**Earned Revenue:**
- Custom research reports for unions preparing major campaigns ($2-10K per engagement)
- Training/workshops on platform usage for union organizer cohorts
- "State of Labor" annual report sponsorships

The key insight: the free tier is not charity — it's the growth engine. Every journalist who embeds a report card, every worker who shares a wage comparison, every researcher who cites the API drives organic traffic that funds the platform.

### 7. Data Freshness Pipeline

Government data lags, but the lag varies by source and managing it is a feature, not just a risk:

**Automated Refresh Schedule:**
| Source | Update Frequency | Typical Lag | Freshness Strategy |
|--------|-----------------|-------------|-------------------|
| OSHA violations | Weekly | 2-4 weeks | Incremental sync, new records only |
| WHD cases | Monthly | 1-3 months | Full refresh, diff report |
| NLRB elections | Weekly | 1-2 weeks | RSS/scrape for new filings |
| BLS (OES/SOII/JOLTS/NCS) | Annual | 6-12 months | Annual bulk load + vintage tagging |
| SEC/GLEIF | Quarterly | 1-3 months | Delta downloads |
| QCEW | Quarterly | 6 months | Quarterly bulk load |
| USAspending | Monthly | 1-2 months | API-based incremental |

**User-Facing Freshness Indicators:**
- Every data point shows "Source: OSHA | As of: Jan 2026"
- Stale data (>6 months) gets a visual indicator
- Profile-level "data freshness score" — how recent is the most recent data we have on this employer?
- Change detection alerts: "This employer's profile changed since your last visit" (new violations, ownership change, NLRB activity)

**Archival Strategy:**
- Snapshot all source data monthly
- If a source becomes unavailable (hostile administration restricts access), the platform continues serving cached data with a disclaimer
- Historical data has independent value — even if OSHA stops publishing, 10 years of violation history remains useful

### 8. Becoming the OpenSecrets of Labor

OpenSecrets succeeded because of three things: **comprehensiveness, accessibility, and embeddability.** Apply the same playbook:

**Comprehensiveness:** You're already here. 30+ sources, 4.4M employers, 2.2M cross-references. No one else has this.

**Accessibility:**
- **Free tier:** Let anyone search and view basic employer profiles. No login required.
- **Embed widgets:** Let journalists embed an employer's "labor report card" in their articles, the way OpenSecrets lets you embed donation data. `<iframe src="labordata.org/embed/employer/12345">` — shows the quick profile.
- **API:** Let researchers and apps pull data programmatically. Academic researchers will build on this if you let them.
- **Annual reports:** Publish "State of Labor" reports using the data. "The 100 Worst Employers for Worker Safety." "Industries Where Unionization Would Have the Biggest Impact." These generate press coverage and backlinks.

**Embeddability (the network effect):**
- Every time a journalist cites the platform, that's a backlink.
- Every time a union shares an employer profile on social media, that's distribution.
- Every time a researcher publishes using your API, that's credibility.
- The CBA provision search alone could become the go-to reference for labor contract research.

**The name matters.** OpenSecrets works because it's memorable and implies a mission. "Labor Data Platform" doesn't. Consider something like **WorkerFile**, **LaborLens**, **ShopWatch**, or **UnionReady** — something a journalist can cite and a worker can Google.

**The ultimate test:** When a New York Times reporter is writing a story about a specific employer's labor practices, do they check your platform first? When a congressional staffer needs data for a hearing on workplace safety, do they pull it from your API? When a worker Googles their employer's name and finds your report card on page one — that's when you've won.

---

*The data you've assembled is genuinely unprecedented. The challenge isn't having enough data — it's making the connections between sources visible, the insights actionable, and the platform indispensable to the people who need it most.*
