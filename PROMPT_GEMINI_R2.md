# Gemini — Deep Research Round 2
## February 26, 2026

---

## CONTEXT

You just completed a strategic audit of this platform (GEMINI_AUDIT_REPORT_2026_02_25.md). This is a follow-up research assignment that digs deeper into the most important strategic and data questions from that audit and from the three-audit synthesis.

Your job is different from the other two tools. Claude Code checks the database. Codex reads the code. **Your job is to research the outside world** — what organizers actually do, what academic research says, what data sources exist, and what would make this platform genuinely useful rather than just technically impressive.

**Context files you should have:**
- Your own audit report (GEMINI_AUDIT_REPORT_2026_02_25.md)
- THREE_AUDIT_SYNTHESIS_2026_02_26.md — the synthesis of all three audits

**Rules:**
1. Cite specific sources — academic papers, published reports, named tools, specific URLs. "Research suggests" is not acceptable; "A 2023 study by Bronfenbrenner at Cornell ILR found that..." is.
2. Distinguish between what you found through research and what you're reasoning about. Label each clearly.
3. Be honest about gaps — if you can't find research on a question, say so rather than speculating.
4. Think like an organizer throughout. Every recommendation should answer: "Would a real organizer at a real union care about this?"

---

## Research 1: How Do Organizers Actually Pick Targets?

The platform assumes organizers want a scoring system that ranks employers. But we've never verified that this matches how organizers actually work.

**What to research:**

1. **The actual target selection workflow.** How do unions like SEIU, UNITE HERE, CWA, UAW, and Teamsters decide where to run their next campaign? Is it top-down (research department picks targets) or bottom-up (workers come to the union asking for help)? Or some mix? Find published accounts, interviews, case studies, or academic descriptions of this process.

2. **What information do organizers look for?** When evaluating a potential target, what do experienced organizers want to know? Look for:
   - Published organizing manuals or training materials
   - Academic studies of organizing campaign decision-making
   - Interviews with organizers about their research process
   - Union training program curricula (some are public)

3. **Where do they currently get information?** Before our platform exists, how do organizers research a potential target? What government databases do they check? What commercial tools do they use? How much time does research typically take?

4. **What's the bottleneck?** Is the bottleneck finding targets (they don't know where to look), researching targets (they know where to look but it takes too long), or something else entirely (they have targets but lack staff/resources to run campaigns)?

**Why this matters:** If organizers primarily work bottom-up (workers come to them), then a scoring/ranking system is less valuable than a research tool that quickly assembles a profile on a specific employer. If they work top-down, scoring matters a lot. The platform's entire design depends on the answer to this question.

**Deliverable:** A 2-3 page summary of how target selection actually works in practice, with citations, that we can use to validate or redirect the platform's design.

---

## Research 2: What Predicts Successful Organizing Campaigns?

The platform's scoring system uses 8 factors. The backtest from the previous audit suggests these factors don't predict real organizing wins. We need to know what the academic and practitioner literature says about what actually predicts success.

**What to research:**

1. **Academic literature on organizing campaign success factors.** Key researchers to look for:
   - Kate Bronfenbrenner (Cornell ILR) — extensive research on organizing success/failure
   - John-Paul Ferguson — research on NLRB elections
   - Any meta-analyses or literature reviews on organizing outcomes
   - Recent dissertations on organizing in the 2020s (Starbucks, Amazon era)

2. **For each factor in our scoring system, find evidence for or against its predictive value:**

   | Our Factor | Research Question |
   |-----------|-------------------|
   | OSHA violations | Does workplace safety record predict organizing interest or success? |
   | NLRB nearby activity | Does nearby organizing momentum predict new campaigns? (The "hot shop effect") |
   | Wage theft (WHD) | Does wage theft correlate with organizing activity? |
   | Government contracts | Do government contractors face different organizing dynamics? |
   | Union density (industry/area) | Does being in a highly unionized industry/area predict new organizing? |
   | Employer size | What employer sizes are most organizable? |
   | Employer similarity | Does similarity to unionized employers predict organizing potential? |
   | Industry growth | Do growing industries see more organizing? |

3. **What factors are we missing that research says matter?**
   - Management response (anti-union consultants, captive audience meetings)
   - Worker demographics (age, education, race — documented correlations with organizing propensity)
   - Turnover rates
   - Wage levels relative to area cost of living
   - Benefits quality
   - Worker communication networks (shared housing, social media groups)
   - Community support/opposition
   - Political climate (state labor laws, local government stance)
   - Recent layoffs, pay cuts, or benefit reductions ("trigger events")

4. **Is a scoring/ranking approach even the right model?** Some alternatives:
   - **Checklist model:** Instead of a score, show which "readiness indicators" are present
   - **Trigger event model:** Monitor for sudden changes (new OSHA violations, layoffs, management changes) rather than static scores
   - **Cluster model:** Group similar employers and highlight ones where organizing has succeeded in the cluster

**Deliverable:** A literature review organized by factor, with specific citations, that tells us which of our 8 factors have research support and which are unsupported. Include a section on missing factors and alternative modeling approaches.

---

## Research 3: State PERB Data Inventory

7 million public sector workers are invisible on the platform. The previous audit noted that research on state PERB data was done but implementation stalled. We need a concrete, state-by-state inventory.

**What to research:**

For each of the 15 largest public-sector union states (roughly: CA, NY, NJ, IL, WA, OR, MA, CT, MN, OH, PA, MI, WI, MD, HI):

1. **Does the state have a PERB or equivalent agency?** (Name and URL)
2. **Is election/certification data publicly available online?**
3. **Is it machine-readable (API, CSV, database) or PDF/HTML-only?**
4. **What data fields are available?** (Employer name, union name, election date, outcome, bargaining unit size, location)
5. **How far back does data go?**
6. **How frequently is it updated?**
7. **Are there ULP (unfair labor practice) records available?**
8. **Is there contract/agreement data available?**

**Format as a table:**

| State | Agency | URL | Data Available | Format | Fields | History | ULP? | Contracts? | Ingestion Difficulty |
|-------|--------|-----|----------------|--------|--------|---------|------|------------|---------------------|

Rate "Ingestion Difficulty" as:
- **Easy:** API or downloadable CSV/database with structured fields
- **Medium:** HTML tables or structured PDFs that can be scraped
- **Hard:** Unstructured PDFs, scanned documents, or data only available by FOIA request

**Also research:**
- Are there any aggregator projects that have already collected multi-state PERB data?
- Has the Labor Action Tracker or similar project done this work?
- Are there academic datasets of public sector elections/certifications?

**Deliverable:** A complete state-by-state inventory table, plus a recommendation for which 3-5 states to prioritize first (based on data availability, public sector union membership, and ingestion difficulty).

---

## Research 4: Job Posting Data as an Organizing Signal

Your audit proposed using job posting frequency as a proxy for turnover, which correlates with organizing interest. Research the feasibility.

**What to research:**

1. **The turnover-organizing connection.** Is there published research linking high employee turnover to organizing activity? What's the mechanism? (Dissatisfied workers leave OR dissatisfied workers organize — which comes first?)

2. **Available job posting data sources.**
   - **Indeed:** Does Indeed have a public API? What data is available? Is there an academic/research access program?
   - **LinkedIn:** Job posting data availability?
   - **Google Jobs:** Aggregation API?
   - **Bureau of Labor Statistics JOLTS data:** Job openings and turnover by industry — available at what granularity? (National? State? Employer-level?)
   - **State workforce agencies:** Do any states publish employer-level hiring data?
   - **Glassdoor:** Company reviews, ratings, salary data — API availability?
   - **Commercial providers:** Burning Glass/Lightcast, Revelio Labs, etc. — what do they offer and at what cost?

3. **How would you calculate a "turnover signal"?**
   - Job postings per employee over time?
   - Comparison to industry average?
   - Sudden increases (indicating mass departures)?
   - What would a scoring formula look like?

4. **Practical concerns:**
   - How often would data need to be refreshed to be useful?
   - What's the coverage like for the types of employers organizers care about? (Healthcare, warehousing, hospitality, food service — often posted on different platforms than tech jobs)
   - Would this create bias toward employers that post jobs online vs. those that hire through staffing agencies or word of mouth?

**Deliverable:** A feasibility assessment with specific data sources, availability, cost, and a recommended approach if we decide to pursue this. Include a clear "yes, feasible at reasonable cost" or "no, not practical right now" recommendation.

---

## Research 5: How Do Organizers Build Trust in Data Tools?

If we build the perfect platform but organizers don't trust it, it fails. Research the adoption question.

**What to research:**

1. **Examples of data tools adopted by organizers.**
   - **LaborAction Tracker** — how widely used is it? By whom? What makes it trusted?
   - **Union contract databases** (BNA, Bloomberg Law) — who uses these? How are they regarded?
   - **Coworker.org** — worker-initiated campaigns. How do they use data?
   - **Jobs With Justice** or other advocacy data projects
   - **Political campaign analytics** (as an analogy) — how did campaigns go from gut-feeling targeting to data-driven targeting? What made organizers trust the data?

2. **Trust barriers specific to labor organizing.**
   - Security concerns (does management learn about the tool? Can employer data be used against organizers?)
   - "We know our communities" resistance (experienced organizers may distrust algorithmic recommendations)
   - Data literacy gaps (can organizers interpret scores and confidence levels?)
   - Institutional inertia (unions have established processes — why change?)

3. **What builds trust?**
   - Transparency (showing the data behind the score)?
   - Accuracy track record (the tool was right about X campaign)?
   - Endorsement from respected organizers/unions?
   - Simplicity (easy to understand = easier to trust)?
   - Control (organizers can adjust weights or filter by their own criteria)?
   - Feedback loops (organizers can flag errors and see them corrected)?

4. **The "one bad match" problem.**
   The synthesis notes that if an organizer discovers ONE piece of incorrect information, it could undermine trust in the entire platform. Research whether this is a documented pattern in data tool adoption. How do other tools handle data quality issues while maintaining user trust?

**Deliverable:** A summary of trust dynamics for data tools in organizing contexts, with specific examples and recommendations for how our platform should handle transparency, error communication, and user feedback.

---

## Research 6: Contract Expiration Data Sources

Your audit mentioned contract expirations as a missing factor — when a union contract expires, non-union competitors become targets. Research where this data lives.

**What to research:**

1. **Are contract expiration dates in F7 filings?**
   - F7 forms (available from OLMS) report union-employer relationships. Do they include contract duration or expiration dates? Check the actual F7 form fields.
   - If yes, this data may already be in our database. Describe which field and what it looks like.

2. **Federal Mediation and Conciliation Service (FMCS).**
   - FMCS requires filing of notice when contracts expire (F-7 notice). Is this different from the DOL F7?
   - Is FMCS contract expiration data publicly available? In what format?
   - How comprehensive is it? (All contracts or only those above a size threshold?)

3. **BNA/Bloomberg Law contract database.**
   - What contract data is available?
   - Is there academic/library access? (The project has CUNY library access)
   - Can expiration dates be extracted?

4. **Other sources.**
   - Do state labor boards track contract expirations?
   - Is there a public database of collective bargaining agreements with dates?
   - The platform has a CBA (Collective Bargaining Agreement) processing pipeline (test files suggest rule engine, article finder, party extractor) — is this related?

5. **The strategic value.**
   - How would organizers use contract expiration data?
   - When a contract expires at Employer A (unionized), why does that create an opportunity at Employer B (non-union) in the same industry/area?
   - How far in advance is the information useful? (6 months before expiration? 1 year?)

**Deliverable:** An inventory of contract expiration data sources with availability, format, and coverage. Plus a strategic assessment of how valuable this would be as a scoring factor or as a standalone feature (e.g., "upcoming expirations near you" alert).

---

## OUTPUT FORMAT

For each research topic:
1. **The question** (one sentence)
2. **What I found** (organized findings with specific citations)
3. **What I couldn't find** (honest gaps)
4. **Recommendation** (clear, actionable)
5. **How this affects the platform** (design implications)

End with a section called **"If I Were Advising the Project"** — your overall strategic recommendations for the project direction based on everything you've learned across both the audit and this research round. Be honest, be specific, and prioritize ruthlessly. What are the 3 things that would make the biggest difference for real organizers?
