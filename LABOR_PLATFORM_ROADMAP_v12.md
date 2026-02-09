# Labor Relations Research Platform — Roadmap v12

**Date:** February 8, 2026
**Audience:** Union leadership making strategic decisions
**Time commitment:** 15+ hours/week
**Approach:** Plain language throughout — every step explains *what*, *why*, and *how*

---

## How to Read This Roadmap

This document is organized into four phases that build on each other like floors of a building. You can't put furniture in a room that doesn't have walls yet, so the order matters. Each phase has a clear goal, a list of tasks explained in plain English, and a "you'll know it's working when..." check at the end.

**The four phases:**

1. **Clean the Foundation** (Weeks 1–3) — Fix known data problems so everything built on top is trustworthy
2. **Add New Intelligence** (Weeks 4–8) — Bring in new data sources that make the platform smarter
3. **Upgrade the Scorecard** (Weeks 6–10) — Make the "which employers should we organize?" tool significantly better
4. **Rebuild the Interface** (Weeks 8–14) — Redesign what people actually see and use, optimized for leadership decisions

Phases 2 and 3 overlap intentionally — some scorecard improvements depend on new data arriving from Phase 2.

---

## What You Have Right Now (The Starting Point)

Before diving into what's next, here's an honest snapshot of where the platform stands today:

### What's working well

- **Membership tracking is accurate.** The platform counts 14.5 million union members nationally. The government's official number (from the Bureau of Labor Statistics) is 14.3 million. That's a 1.4% difference — extremely close. This means when the platform says "SEIU represents 45,000 workers in New York healthcare," you can trust that number.

- **You can look up almost any unionized employer in the country.** The database has 63,118 employers with union contracts, and 96.2% of them are successfully linked to the union that represents their workers.

- **Workplace safety violations are connected.** Over 2.2 million OSHA violation records are in the system, covering $3.5 billion in penalties. About 45% of these are linked to specific employers in the union database.

- **Corporate ownership is mapped.** A new layer (added this week) connects SEC filings, a global business registry called GLEIF, and commercial business data to show who owns whom. This means if a private equity firm owns 30 nursing homes, you can see all 30 as one group — not 30 unrelated employers.

- **The organizing scorecard exists and works.** It scores non-union employers on a 0-62 point scale across six factors and assigns them a priority tier (TOP, HIGH, MEDIUM, LOW).

### What needs improvement

- **About 11,800 employer records are likely duplicates** — the same company appearing twice under slightly different names. This inflates counts and can mislead.

- **The scorecard is basic.** It treats each factor independently. It doesn't ask the most useful question: "Does this non-union employer look like the employers that already have unions?"

- **The web interface was built for testing, not for decision-making.** It works, but it requires clicking through many screens and doesn't surface the information a union president would want at a glance.

- **Some data gaps remain:** 16,000 employers don't have geographic coordinates (so they don't show up on maps), and about 8,000 employers are missing industry codes (so they can't be properly categorized).

---

## PHASE 1: Clean the Foundation

**Goal:** Make the existing data trustworthy enough that leadership can cite it with confidence
**Timeline:** Weeks 1–3
**Effort:** ~35–50 hours

### Why this comes first

Imagine you're presenting to your executive board: "We've identified 500 organizing targets in healthcare." If someone asks "How do you know that number is right?" you need a good answer. Right now, there are known issues — duplicates, missing codes, unmatched records — that could undermine credibility. Fixing these first means everything built afterward rests on solid ground.

### Task 1.1: Merge duplicate employers (4–6 hours)

**What this is:** The system has identified 11,815 pairs of employer records that are almost certainly the same company — for example, "WALMART INC" and "WAL-MART INC" appearing as two separate entries. These need to be combined into single records.

**How it works:** We've already identified which records are duplicates using a process called "fuzzy matching" — instead of requiring names to be spelled identically, it measures how similar two names are (like how close "WALMART" is to "WAL-MART") and flags pairs that are very close. Now we need to actually merge them: pick the better record as the "primary," move all the linked data (contracts, violations, etc.) over to it, and mark the duplicate as retired.

**Why it matters:** Without this, the same employer could show up twice in search results, their worker counts could be double-counted, and the scorecard might score them twice. For leadership looking at "how many employers are in our jurisdiction," duplicates make the numbers unreliable.

**You'll know it's done when:** The employer count drops slightly (reflecting removed duplicates), and searching for a company like Walmart returns exactly one result with all its data consolidated.

### Task 1.2: Audit the remaining 234 complex duplicates (8–12 hours)

**What this is:** Beyond the clear-cut duplicates, there are 234 groups of employers where the situation is ambiguous. For example, "City of New York — Department of Education" and "NYC Department of Education" might be the same employer, or they might be legitimately different bargaining units. These require human judgment.

**How it works:** Each group gets reviewed one by one. The system shows all the information it has about each potential duplicate — names, addresses, unions, worker counts — and a decision gets made: merge them, keep them separate, or flag for further research.

**Why it matters:** These edge cases are where data quality issues hide. Getting them right ensures that the "total workers covered" numbers and employer counts are accurate.

### Task 1.3: Fill in missing industry codes for ~8,000 employers (4–6 hours)

**What this is:** Every employer should have a NAICS code — a standardized number that tells you what industry they're in (hospitals are 622110, trucking is 484121, etc.). About 8,000 employers are missing this code.

**How it works:** Many of these employers already appear in OSHA records or Bureau of Labor Statistics data, where they DO have industry codes. This task cross-references the employer against those other databases and fills in the code. Think of it like looking up someone's phone number in a different directory when the first one didn't have it.

**Why it matters:** Without industry codes, these employers can't be properly categorized in the scorecard. An organizer can't search for "all non-union healthcare employers in New Jersey" if 8,000 employers aren't tagged with their industry.

### Task 1.4: Geocode the remaining 16,000 employers (4–6 hours)

**What this is:** "Geocoding" means turning a street address into a map coordinate (latitude and longitude). About 16,000 employers have addresses but no coordinates, so they don't appear on the platform's maps.

**How it works:** The Census Bureau offers a free service where you send it addresses and it sends back coordinates. We batch-send these 16,000 addresses and store the results. Some will fail (bad addresses, PO boxes), but most will succeed.

**Why it matters:** The platform has map-based search features — "show me all employers within 50 miles of Pittsburgh." Employers without coordinates are invisible on these maps, which means organizing opportunities could be missed.

### Task 1.5: Validate union hierarchy (clean up parent/child relationships) (6–8 hours)

**What this is:** Unions have a structure: SEIU is the parent, and Local 32BJ is one of its children. The database tracks these relationships, but some are outdated (locals that merged or disbanded), orphaned (locals not linked to any parent), or wrong (linked to the wrong parent).

**How it works:** Compare the database's union structure against known public records — OLMS filings, union websites, and recent merger announcements. Fix mislinks, mark disbanded locals, and ensure every active local is connected to its correct parent union.

**Why it matters:** When leadership asks "How many members does SEIU represent?" the answer is calculated by adding up all of SEIU's locals. If some locals are orphaned (not linked to SEIU), the total undercounts. If disbanded locals are still active in the system, it overcounts.

### Task 1.6: Cross-check sector classifications (3–4 hours)

**What this is:** Every employer is tagged as "private sector," "federal," or "state/local public." A small number are probably tagged wrong — for example, a military base contractor tagged as "federal" when they should be "private."

**How it works:** Run checks that look for mismatches: an employer tagged as "federal" but filing private-sector union paperwork, or an employer tagged as "private" but appearing in the federal employee database. Flag and fix these.

**Why it matters:** The platform's headline numbers — "92% private sector coverage" — are only meaningful if employers are in the right categories. Miscategorized employers skew the coverage percentages.

### Task 1.7: Build automated validation (4–6 hours)

**What this is:** Create a set of automated checks that run regularly and flag when something looks wrong — a sudden spike in membership, a new duplicate appearing, or a coverage number drifting outside the acceptable range.

**How it works:** This is like setting up alerts. Instead of manually reviewing the data every time something changes, the system automatically compares key metrics (total membership, sector coverage, match rates) against expected ranges and warns you if something is off.

**Why it matters:** Without this, data quality problems can creep in silently as new filings are added. The automated checks catch issues early before they compound.

### Phase 1 Checkpoint

**Run the BLS validation.** After completing all the above, re-check the platform's numbers against official government statistics. All sectors should be within 90–110% of the official benchmark. If any sector drifts outside that range, stop and investigate before moving on.

---

## PHASE 2: Add New Intelligence

**Goal:** Bring in new data sources that answer questions leadership actually asks
**Timeline:** Weeks 4–8
**Effort:** ~40–60 hours

### Why this phase matters for leadership

Union leadership making strategic decisions needs more than just "who has a union contract." They need answers to questions like:

- "Which employers in our jurisdiction have the worst wage theft records?"
- "Which of our current employers are federal contractors?" (This matters because federal contractors have additional labor obligations.)
- "What's the full corporate picture — who owns this employer, and what else do they own?"
- "How is our industry changing — are jobs growing or shrinking?"

Phase 2 adds data sources that answer these questions.

### Task 2.1: Load national wage theft data (8–10 hours)

**What this is:** The Department of Labor's Wage and Hour Division (WHD) tracks employers caught violating wage laws — unpaid overtime, minimum wage violations, misclassifying workers as independent contractors, etc. There are about 363,000 records nationally.

**How it works:** The data is already downloaded. This task loads it into the database and matches it against the existing employer records. The matching uses the same multi-step process that's worked well for other data sources: first try to match by employer ID number (EIN), then by exact name and location, then by approximate ("fuzzy") name matching.

**Why it matters for leadership:** Wage theft is one of the strongest organizing arguments. "Your employer stole $2.3 million from workers like you" is powerful in a campaign. It's also useful strategically — employers with chronic wage violations may be more vulnerable to organizing because workers are already angry.

**What it looks like when done:** An organizer can pull up any employer and see: "This employer was fined $450,000 for overtime violations in 2022 and $180,000 for minimum wage violations in 2024." This information feeds into the scorecard as well, boosting the scores of employers with violation histories.

### Task 2.2: Improve OSHA workplace safety matching (6–8 hours)

**What this is:** Right now, about 45% of OSHA violation records are successfully linked to employers in the union database. The other 55% can't be matched because the names or addresses don't align well enough. This task pushes that match rate above 50%.

**How it works:** Use the improved matching system (built in early February) that includes address-based matching as a fallback. When names don't match well enough, the system also compares street addresses — if two records have the same street number at the same address, they're probably the same employer even if the names are spelled differently.

**Why it matters:** More matched OSHA records means more employers get safety violation data in their profiles, which feeds into the scorecard and gives organizers more ammunition.

### Task 2.3: Expand Mergent business data nationally (15–20 hours)

**What this is:** Mergent Intellect is a commercial business database available through the CUNY library. It has detailed information on millions of employers: revenue, employee counts, corporate parent-subsidiary relationships, executive names, and accurate industry codes. Currently, only 14,240 employers have been loaded (focused on 11 sectors in New York). This task expands to a national scope.

**How it works:** Access the Mergent database through CUNY, run targeted queries for industries relevant to labor organizing (healthcare, hospitality, building services, manufacturing, transportation, etc.), and load the results into the platform. Each new employer record gets matched against existing records to link the Mergent data to the union contract database.

**Why it matters for leadership:** Mergent is the richest single source of employer intelligence. After this expansion:
- You'll know the revenue and size of most major employers in your jurisdiction
- You'll have corporate parent-subsidiary chains ("This nursing home is owned by Kindred Healthcare, which is owned by Humana, a Fortune 500 company")
- Industry codes from Mergent are more accurate than government records, improving the scorecard
- The platform goes from covering ~14,000 employers commercially to potentially 50,000+

**Why it works through CUNY:** Mergent normally costs thousands of dollars in subscription fees. CUNY's library system has institutional access, which means you can query it for free. The limitation is that you need to extract data in batches through the library's interface rather than having a direct data feed.

### Task 2.4: Expand IRS Form 990 nonprofit data nationally (10–14 hours)

**What this is:** IRS Form 990 is the financial disclosure that every nonprofit organization must file. It includes revenue, expenses, executive compensation, and program descriptions. This data is available for free through the ProPublica Nonprofit Explorer API.

**How it works:** Query the ProPublica API for nonprofits in industries relevant to organizing — hospitals, universities, social service agencies, cultural institutions. Load the financial data and match it to existing employer records.

**Why it matters for leadership:** Many major employers in the public and nonprofit sectors (hospitals, universities, museums, social service organizations) file 990s. Currently the platform has 990 data for New York only. National expansion means leadership can see:
- "This hospital's CEO makes $3.2 million while nurses start at $52,000" — useful for campaign messaging
- Revenue trends showing whether an employer is financially healthy or struggling
- Which nonprofits receive government grants (potential leverage)

### Task 2.5: Integrate QCEW establishment counts for context (4–6 hours)

**What this is:** The Bureau of Labor Statistics publishes the Quarterly Census of Employment and Wages (QCEW), which counts how many businesses exist in each industry in each state. Some of this data is already loaded (industry density scores for 121,000 employers). This task fills in remaining gaps and adds establishment-level context.

**How it works:** The QCEW tells you things like "There are 4,200 nursing homes in California employing 312,000 workers." When the platform knows there are 4,200 nursing homes and 800 are unionized, it can calculate that 19% of the industry is organized — and 3,400 nursing homes are potential targets.

**Why it matters:** This provides the denominator that leadership needs. Instead of just "here are 50 targets," it can say "there are 50 top-priority targets out of 3,400 non-union nursing homes in the state — here's why these 50 are the best starting points."

### Phase 2 Checkpoint

After loading new data sources, re-run the BLS validation to make sure the new data doesn't disturb existing accuracy. Then check that the new data sources are actually linking to existing employers at reasonable rates (ideally 30%+ of new records should match to existing employers).

---

## PHASE 3: Upgrade the Scorecard

**Goal:** Move from a simple checklist ("add up six scores") to a comparison engine ("which non-union employers look most like employers that already have unions?")
**Timeline:** Weeks 6–10 (overlaps with Phase 2)
**Effort:** ~30–45 hours

### Why this is the most impactful phase for leadership

The current scorecard answers: "On a scale of 0 to 62, how promising is this employer as an organizing target?"

The upgraded scorecard will answer: "This non-union employer is 87% similar to employers that are already unionized. Here are the three most similar unionized employers, and here's why the comparison makes sense."

That second answer is dramatically more useful for strategic decisions. It transforms abstract numbers into concrete comparisons that leadership can evaluate, debate, and act on.

### Task 3.1: Implement employer similarity scoring (12–16 hours)

**What this is:** A mathematical method for measuring how similar any two employers are across every characteristic the platform knows about — industry, size, location, violation history, government contracts, revenue, corporate structure.

**How it works (in plain English):** Imagine you're comparing two restaurants. You might check: Are they the same type of cuisine? About the same size? In the same city? Similar price range? Similar health inspection history? A method called "Gower Distance" does exactly this, but automatically and across dozens of characteristics at once. It produces a number between 0 (completely different) and 1 (practically identical).

The crucial advantage of this method is that it handles missing information well. If you know everything about Restaurant A but don't know Restaurant B's revenue, it simply compares on the characteristics it does have. This is critical because government data always has gaps — you'll never have complete information on every employer.

**What it means practically:** For any non-union employer, the system can find the 5 most similar unionized employers and show leadership: "This non-union warehouse in Memphis (500 workers, 4 OSHA violations, $80M revenue) is 91% similar to this unionized warehouse in Chicago that the Teamsters organized in 2023."

### Task 3.2: Add historical organizing success patterns (8–12 hours)

**What this is:** Use NLRB election data to learn which types of employers are more likely to vote "yes" for a union. The database has 33,096 NLRB elections — each one records the employer, the industry, the location, the union petitioning, the number of eligible voters, and the outcome.

**How it works:** Analyze the historical elections to find patterns. For example: "In the last 5 years, healthcare employers with 50–200 employees in the Northeast have voted yes for a union 58% of the time." Or: "OSHA violations in the year before an election correlate with a 12% higher win rate." These patterns become factors in the scorecard.

**Why it matters:** Instead of guessing which factors predict organizing success, the system learns from actual results. This is the difference between "our scorecard is based on reasonable assumptions" and "our scorecard is based on what actually happened in 33,000 elections."

### Task 3.3: Build the "comparables" display (6–8 hours)

**What this is:** For every scored employer, generate a list of the most similar unionized employers ("comparables"), showing why they're similar and which union represents them.

**How it works:** When someone views an employer's profile, the system runs the similarity calculation against all unionized employers in the same broad sector and returns the top matches. Each match shows the similarity score and which characteristics drove the match.

**What it looks like:** A union president looking at a target employer sees:

> **Best comparables for Target Employer:**
> 1. XYZ Healthcare (SEIU Local 1199) — 89% similar — Same industry, similar size (180 vs 200 employees), both in NY metro, both with recent OSHA violations
> 2. ABC Medical Center (NYSNA) — 83% similar — Same industry, similar revenue ($45M vs $52M), same state
> 3. Regional Hospital Group (AFSCME DC 37) — 79% similar — Same industry, similar government contract volume

This is enormously more useful than "Score: 38 out of 62."

### Task 3.4: Refresh and re-score all targets (4–6 hours)

**What this is:** Once the new scoring methodology is built, run it across every employer in the database and regenerate all the priority tiers.

**How it works:** Replace the old 0-62 point system with the new similarity-based system. Employers are still ranked and tiered, but the ranking is now driven by "how much does this employer resemble successful organizing targets?" rather than a simple checklist.

### Phase 3 Checkpoint

Compare the new scorecard's top-ranked targets against the old scorecard's top targets. They should overlap significantly (maybe 70-80%), but the new scorecard should surface some employers the old one missed — particularly employers in industries where organizing has been especially successful recently.

If possible, test the new rankings against a few real organizers: "Do these top 20 targets make sense to you?" Their feedback is the ultimate validation.

---

## PHASE 4: Rebuild the Interface for Leadership

**Goal:** Create a decision-ready interface that a union president or organizing director can use directly
**Timeline:** Weeks 8–14
**Effort:** ~35–50 hours

### Why this is the last phase (but not the least important)

Everything in Phases 1–3 built the engine. Phase 4 builds the dashboard. It comes last because you can only design a good interface once you know what data you have and what questions it can answer. Now you know.

### The leadership use case

A union president or organizing director typically needs answers to these questions:

1. **"What does our territory look like?"** — How many organized vs. non-organized workers, by geography and industry
2. **"Where should we focus next?"** — Top organizing targets, ranked and explained
3. **"What's the story on this specific employer?"** — Full profile with violations, corporate structure, comparable employers, election history
4. **"How are we trending?"** — Membership trends over time, organizing wins/losses, industry shifts
5. **"Give me something I can present."** — Exportable reports, charts, and summaries for board meetings

The redesigned interface should answer all five with minimal clicking.

### Task 4.1: Design the "Territory Dashboard" (8–10 hours)

**What this is:** A landing page that shows the big picture for a selected union or geographic area.

**What it shows:**
- Total organized workers vs. total workforce (with a percentage)
- Map showing organized and non-organized employers
- Top 10 organizing targets with their scores and comparable employers
- Recent NLRB election activity in the area
- Industry breakdown (pie chart or bar chart showing which industries are most and least organized)

**How it works:** The user selects their union (or a geographic area) and the dashboard populates. All the underlying data already exists from Phases 1-3 — this is about presenting it clearly.

**What makes this different from the current interface:** Right now, a user has to click through separate tabs for employers, unions, OSHA data, and NLRB elections. The dashboard combines them into one view focused on strategic decision-making.

### Task 4.2: Build the "Employer Deep Dive" profile (8–10 hours)

**What this is:** A single-page profile for any employer that shows everything the platform knows.

**What it shows:**
- Basic info (name, location, industry, employee count, revenue)
- Union status (which union, how many members, when organized)
- Corporate structure (parent company, subsidiaries, other locations)
- Violation history (OSHA violations, wage theft, with dollar amounts and dates)
- Organizing scorecard (score, tier, breakdown of each factor with plain-English explanation)
- Comparable employers (the similarity-based matches from Phase 3)
- NLRB election history (any past elections at this employer or similar employers nearby)
- Government contracts (dollar amounts, agencies)

**How it works:** Instead of separate screens for different data points, everything about one employer appears on a single scrollable page with expandable sections. A leadership member can open this profile and understand the full picture in 2 minutes.

### Task 4.3: Create the "Board Report" export (6–8 hours)

**What this is:** One-click export of platform data into formats useful for presentations and reports.

**What it produces:**
- **PDF employer profile** — a printable summary of any employer for campaign planning
- **CSV data export** — any search result or target list, downloadable as a spreadsheet
- **Territory summary** — a one-page overview of a union's or region's organizing landscape, suitable for board presentations
- **Trend charts** — membership and organizing activity charts ready to paste into slides

**Why it matters for leadership:** Leaders don't just consume data on a screen — they present it to boards, membership meetings, and potential coalition partners. Right now, getting data out of the platform requires manual copy-paste. This makes it one click.

### Task 4.4: Implement union-first navigation (6–8 hours)

**What this is:** Redesign the entry point so it starts with "Who are you?" rather than "What are you looking for?"

**How it works:** The first thing a user sees is "Select your union." Once selected, the interface immediately shows their employers, their jurisdiction, and their targets — no need to separately search by state, industry, and union. Geographic filters (state → metro → city) cascade naturally rather than requiring separate dropdown selections.

**Why this design matters:** The current interface was designed for a researcher exploring the data. Leadership doesn't want to explore — they want to see their territory and their targets immediately.

### Task 4.5: Mobile-responsive design (6–8 hours)

**What this is:** Make the interface work well on phones and tablets, not just desktop computers.

**Why it matters:** Organizers and even leadership increasingly work from mobile devices. A quick check of target employers on a phone before a meeting is a realistic use case. The current interface doesn't resize well for smaller screens.

### Phase 4 Checkpoint

The test here is practical: Can a union organizing director sit down with the platform for the first time and, within 5 minutes, find their union's top organizing targets, understand why they're ranked that way, and export a summary for their next board meeting? If yes, Phase 4 is successful.

---

## Beyond Phase 4: What Could Come Next

These are possibilities for after the core four phases are complete. They're listed here for planning purposes but don't need decisions now.

### Real-time monitoring
Set up automated alerts when new NLRB petitions are filed, new OSHA violations are issued, or new union election results come in. This turns the platform from a reference tool into a surveillance system that proactively notifies leadership of organizing opportunities.

**What it would take:** A scheduled process that checks government databases daily and sends email or text alerts when something relevant happens. Estimated effort: 12–16 hours.

### Predictive modeling
Use machine learning to predict which employers are most likely to see organizing activity in the next 12 months, based on patterns in the historical data. This goes beyond the scorecard (which ranks existing targets) to identify emerging opportunities before they're obvious.

**What it would take:** A trained model using the 33,000+ NLRB election records as the learning set. Estimated effort: 30–40 hours, and the results are only as good as the patterns in the data.

### Multi-user deployment
Put the platform on a web server so multiple people can access it simultaneously from different locations, rather than running it on a single computer.

**What it would take:** A cloud hosting setup (likely $50–150/month for server costs) and login/authentication so different users see appropriate data. Estimated effort: 10–15 hours for initial setup.

### News and media monitoring
Automatically scan news sources for labor-related stories — strikes, organizing drives, employer controversies — and link them to employers in the database.

**What it would take:** Integration with a news API service and some natural language processing to extract employer names from articles. Estimated effort: 15–20 hours.

### Political spending transparency
Connect FEC (Federal Election Commission) data to show which employers or their executives donate to anti-union political causes.

**What it would take:** FEC data is free and publicly available. The challenge is matching donor names to employer records. Estimated effort: 12–16 hours.

---

## Summary Timeline

| Weeks | Phase | What's happening | Key deliverable |
|-------|-------|-----------------|-----------------|
| 1–3 | Clean the Foundation | Fixing duplicates, filling gaps, validating accuracy | All data passes BLS benchmark check |
| 4–8 | Add New Intelligence | Wage theft, expanded Mergent, 990s, QCEW | 4+ new data sources feeding into employer profiles |
| 6–10 | Upgrade the Scorecard | Similarity scoring, historical patterns, comparables | "Which employers look like successful organizing targets?" |
| 8–14 | Rebuild the Interface | Territory dashboard, employer profiles, exports | A union president can use it in 5 minutes |

**Total estimated effort:** 140–205 hours over 14 weeks (~10–15 hours/week average)

---

## How We'll Work Together

Each session, I'll:
1. Remind you where we are in the roadmap
2. Explain what we're doing that day and why it matters
3. Walk through the technical steps in plain language
4. Check results together before moving forward
5. Update this document with what got done

You don't need to understand the code. You need to understand what the platform can do, what it can't do yet, and whether the results make sense for organizing strategy. That's what I'll focus on.

---

*This roadmap is a living document. It will be updated after each work session with completed items, revised estimates, and any new priorities that emerge.*
