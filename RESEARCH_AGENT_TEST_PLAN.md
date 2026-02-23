# Research Agent — Test Batch Plan (Phase 5.1.6)

**Created:** 2026-02-23
**Purpose:** 15 companies across 6 industries to evaluate dossier quality, identify tool gaps, and generate diverse data for the strategy memory system (Phase 5.2).

**Run order:** Start with high-confidence companies (HCA, Starbucks, ABM), then move to harder edge cases (Marlin Steel, Amazon, Kindred). Check results after every 3-4 runs before continuing.

**What to evaluate for each run:**
- Did every relevant tool find data? If not, why?
- Are the facts in the dossier actually correct? (Spot-check 3-4 facts per run)
- Does the assessment section synthesize the data into useful organizing intelligence?
- Did web search add information the database tools missed?
- How long did it take? How much did it cost?
- Were there any name matching failures?

---

## Healthcare (3 companies)

### 1. HCA Healthcare
- **Type:** Public, for-profit hospital chain
- **Size:** ~280,000 employees
- **Primary test:** Full-stack baseline — every tool should return data
- **Why:** Largest for-profit hospital operator. SEC has financials. OSHA has violations (hospitals always do). NLRB likely has election history. SAM likely has Medicare/Medicaid-related contracts. If any tool fails here, something is broken.
- **Secondary test:** Whether the agent identifies subsidiaries — HCA owns hundreds of individual hospitals under different names.
- **Expected strong tools:** SEC, OSHA, NLRB, SAM, contracts, Mergent, web search
- **Expected weak tools:** 990 (for-profit, not applicable)

### 2. Montefiore Medical Center
- **Type:** Nonprofit hospital system, Bronx NY
- **Size:** ~40,000 employees
- **Primary test:** 990 as lead financial source when SEC doesn't apply
- **Why:** No SEC data (nonprofit), but should have rich IRS 990 filings. SEIU and NYSNA have contracts here. Major OSHA presence. Tests whether the agent correctly shifts strategy for nonprofits.
- **Secondary test:** Contract tool with a multi-union employer. Whether the agent handles nonprofit vs for-profit correctly and doesn't waste time on SEC.
- **Expected strong tools:** 990, OSHA, contracts, NLRB, web search
- **Expected weak tools:** SEC (nonprofit, should be skipped)

### 3. Kindred Healthcare / ScionHealth
- **Type:** Public, post-acute care — recently restructured
- **Size:** ~15,000 employees (ScionHealth)
- **Primary test:** Name matching across corporate changes
- **Why:** Kindred became ScionHealth in 2022. Does the agent find historical data under the old name? Does web search catch the name change? Deliberate stress test for name matching.
- **Secondary test:** Whether web search fills gaps that database tools miss due to stale names.
- **Expected challenge:** Database tools may find "Kindred" data but miss "ScionHealth" or vice versa. Watch for split/incomplete results.

---

## Manufacturing (2 companies)

### 4. Smithfield Foods
- **Type:** Public (owned by WH Group, China), meat processing
- **Size:** ~55,000 employees
- **Primary test:** OSHA tool with a heavy-violation employer
- **Why:** Meat processing has the worst OSHA violation rates of any industry. Should generate a massive OSHA section. Also has significant NLRB history (UFCW campaigns) and WHD cases. Foreign parent company (WH Group) tests corporate hierarchy detection.
- **Secondary test:** Whether all three workplace tools (OSHA + WHD + NLRB) produce complementary rather than redundant information. Parent company detection across international borders.
- **Expected strong tools:** OSHA (heavy), WHD, NLRB, SEC, web search
- **Expected challenge:** International parent company may not appear in GLEIF/crosswalk

### 5. Marlin Steel Wire Products
- **Type:** Private, small manufacturer, Baltimore MD
- **Size:** ~50 employees
- **Primary test:** Small employer data sparsity
- **Why:** Most test runs so far are large employers with data everywhere. A 50-person manufacturer might have zero SEC, zero 990, maybe one OSHA inspection, no NLRB history. Does the agent handle sparse data gracefully? Does the dossier still say something useful?
- **Secondary test:** Web search as primary data source when database tools return little. Whether the agent writes useful assessments with limited data rather than just saying "no data found."
- **Expected strong tools:** Web search, maybe Mergent
- **Expected weak tools:** Most database tools will likely return nothing — that's the point

---

## Hospitality / Food Service (2 companies)

### 6. Marriott International
- **Type:** Public, hotel chain
- **Size:** ~380,000 employees (including managed properties)
- **Primary test:** WHD tool in a high-violation industry
- **Why:** Hotels have high WHD violation rates (wage theft in housekeeping, tipped workers). UNITE HERE has contracts at many Marriott properties. SEC data available. SAM likely has government lodging contracts.
- **Secondary test:** Whether the contracts tool finds contracts across multiple union locals at different properties. Multi-location complexity.
- **Expected strong tools:** SEC, WHD, OSHA, contracts, SAM, web search
- **Expected challenge:** Franchise model may complicate matching — many Marriott-branded hotels are independently owned

### 7. Shake Shack
- **Type:** Public, fast-casual restaurant chain
- **Size:** ~10,000 employees
- **Primary test:** Whether industry context fills gaps when employer-specific labor data is thin
- **Why:** Smaller fast-casual chain. SEC data exists. Probably minimal NLRB/OSHA/WHD activity specific to Shake Shack. Tests whether the industry profile tool and web search provide useful context about fast food organizing broadly (Fight for $15, etc.) even when this specific company has little labor history.
- **Secondary test:** Whether the assessment section can identify organizing potential based on industry trends rather than employer-specific violations.
- **Expected strong tools:** SEC, industry profile, web search
- **Expected weak tools:** NLRB, WHD, OSHA (probably little employer-specific data)

---

## Building Services / Security (2 companies)

### 8. ABM Industries
- **Type:** Public, facility services (janitorial, HVAC, parking)
- **Size:** ~100,000 employees
- **Primary test:** Full-stack in building services industry
- **Why:** SEIU's Justice for Janitors campaign has organized ABM workers for decades. Should have F-7 contracts, NLRB history, SAM federal contracts (they clean federal buildings), SEC data, AND significant web search results about organizing. Another "everything should work" company but in a completely different industry than HCA.
- **Secondary test:** Whether the contracts tool handles an employer with dozens of different union locals. SAM tool for a service contractor.
- **Expected strong tools:** All tools — contracts (heavy), NLRB, OSHA, SEC, SAM, web search

### 9. Allied Universal
- **Type:** Private, security services
- **Size:** ~800,000 employees
- **Primary test:** Private company financial data gaps
- **Why:** Huge employer but privately held — no SEC data. Tests whether Mergent or web search can find revenue and employee count for a very large private company. Also has NLRB and OSHA activity.
- **Secondary test:** Name matching across mergers — Allied Universal is the result of multiple mergers (AlliedBarton + Universal Services + G4S). Do database tools find historical data under old names?
- **Expected strong tools:** OSHA, NLRB, SAM, Mergent, web search
- **Expected weak tools:** SEC (private, should be skipped), 990 (for-profit)
- **Expected challenge:** Historical data under AlliedBarton, Universal Protection Service, G4S names

---

## Retail (2 companies)

### 10. Starbucks
- **Type:** Public, coffee retail/restaurant
- **Size:** ~380,000 employees
- **Primary test:** High-volume NLRB + recent organizing news
- **Why:** Starbucks Workers United has filed hundreds of NLRB petitions since 2021. Should generate the most NLRB-heavy dossier of any test. Also tests whether web search captures the enormous volume of recent organizing news. If the agent doesn't produce a strong dossier for Starbucks, something is seriously wrong.
- **Secondary test:** Whether the assessment section synthesizes a complex, ongoing, multi-location campaign. Whether NLRB data and web search complement each other rather than repeating the same facts.
- **Expected strong tools:** NLRB (massive), SEC, OSHA, WHD, web search (massive)

### 11. Dollar General
- **Type:** Public, discount retail
- **Size:** ~170,000 employees
- **Primary test:** WHD heavy violator + unorganized target identification
- **Why:** Called the worst wage theft violator in retail. Huge WHD case history. Minimal NLRB activity (few organizing attempts). OSHA has cited them for locked fire exits. Tests whether the agent identifies an employer as a PROMISING organizing target based on workplace issues even when there's no existing union presence.
- **Secondary test:** Whether the assessment section correctly flags "no union activity but strong grievances" as an opportunity rather than a negative.
- **Expected strong tools:** WHD (heavy), OSHA, SEC, web search
- **Expected weak tools:** Contracts (none expected), NLRB (minimal)

---

## Transportation / Logistics (2 companies)

### 12. Amazon
- **Type:** Public, warehousing/delivery/retail
- **Size:** ~1,500,000 employees
- **Primary test:** Missing from database — expose matching gaps
- **Why:** The audit noted Amazon is "entirely absent" from the database. Largest private employer in the US should have OSHA data, NLRB data (ALU, Teamsters), WHD data, SEC data. If the agent can't build a strong dossier, it exposes name matching failures.
- **Secondary test:** Whether the agent handles a company operating under many names (Amazon.com Inc, Amazon Fulfillment LLC, Amazon Logistics Inc, Amazon Web Services Inc, Whole Foods Market).
- **Expected strong tools:** SEC, web search (massive)
- **Expected challenge:** Database tools may fail to match due to name variants. This is a diagnostic run — failures here tell you what to fix.

### 13. XPO Logistics
- **Type:** Public, trucking/freight
- **Size:** ~38,000 employees (post-split)
- **Primary test:** Corporate spin-off matching
- **Why:** XPO spun off GXO Logistics in 2021, similar to Kindred/ScionHealth but in transportation. Teamsters have active campaigns. Tests whether the agent finds data under both old and new corporate structures.
- **Secondary test:** Trucking/freight industry data coverage.
- **Expected strong tools:** SEC, OSHA, NLRB (Teamsters), web search
- **Expected challenge:** Pre-2021 data under "XPO" includes GXO operations. Agent needs to distinguish.

---

## Edge Cases (2 companies)

### 14. University of Pittsburgh Medical Center (UPMC)
- **Type:** Nonprofit health system, behaves like a corporation
- **Size:** ~95,000 employees
- **Primary test:** Anti-union nonprofit + ULP depth
- **Why:** UPMC is technically nonprofit but operates like a for-profit. Has fought organizing campaigns intensely — multiple NLRB ULP charges and significant news coverage. 990 data should show enormous revenue and executive pay. Tests whether the assessment section catches the anti-union history.
- **Secondary test:** Whether ULP charge details produce useful campaign intelligence. Complex entity (hospital + insurer + research). Whether "nonprofit CEO makes $X million" contrast appears in the financial section.
- **Expected strong tools:** 990 (big nonprofit), NLRB (ULPs), OSHA, web search
- **Expected weak tools:** SEC (nonprofit)

### 15. Gundersen Health System
- **Type:** Nonprofit hospital, La Crosse WI
- **Size:** ~6,000 employees
- **Primary test:** Realistic mid-size regional employer
- **Why:** Not a household name. Tests whether the agent can build a useful dossier for the TYPICAL employer an organizer would research — not a Fortune 500 giant, but a regional institution with a few thousand employees. Probably has 990 data, some OSHA, maybe NLRB.
- **Secondary test:** Whether web search returns anything useful for companies that aren't national news. Whether the dossier is still helpful with moderate data coverage.
- **Expected strong tools:** 990, OSHA, industry profile
- **Expected moderate tools:** Web search (may return limited results)
- **Expected weak tools:** SEC (nonprofit), SAM (unlikely)

---

## Suggested Run Order

**Wave 1 — High confidence (verify system works):**
1. HCA Healthcare
2. Starbucks
3. ABM Industries
4. Dollar General

→ STOP. Review all 4 dossiers. Check: Are facts correct? Did expected tools find data? Are assessments useful? Any systematic prompt issues?

**Wave 2 — Industry breadth (cover new sectors):**
5. Smithfield Foods
6. Marriott International
7. Montefiore Medical Center
8. Allied Universal

→ STOP. Review. Compare healthcare nonprofit (Montefiore) to healthcare for-profit (HCA). Compare private (Allied) to public (ABM). Note which tools failed and why.

**Wave 3 — Stress tests (hard edge cases):**
9. Amazon
10. Kindred / ScionHealth
11. XPO Logistics
12. Shake Shack

→ STOP. Review. Focus on name matching failures and sparse data handling.

**Wave 4 — Realistic cases:**
13. UPMC
14. Gundersen Health System
15. Marlin Steel Wire Products

→ Final review. The Gundersen and Marlin Steel runs are the most important quality check — if the agent produces useful dossiers for mid-size and small employers (not just Fortune 500 giants), it's ready for real use.

---

## Tracking Template

For each completed run, record:

| Field | Value |
|-------|-------|
| Company | |
| Run ID | |
| Duration (seconds) | |
| Estimated cost | |
| Tools that found data | |
| Tools that found nothing | |
| Tools that errored | |
| Sections filled (of 7) | |
| Fact spot-check (3 facts: correct/incorrect) | |
| Assessment quality (1-5) | |
| Name matching issues? | |
| Web search added value? | |
| Biggest gap in dossier | |
| Prompt improvement needed? | |
