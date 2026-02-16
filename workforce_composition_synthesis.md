# Workforce Composition Intelligence: Three-Report Synthesis

## What Are We Comparing?

Three different AI systems were asked the same basic question: **"If I know what kind of business I'm looking at and roughly how big it is, can I figure out what its workforce looks like from the inside — how many people, in what jobs, and who those people are?"**

Each produced a detailed report. Here's how they compare, where they agree, where they disagree, and what the best combined path forward looks like for the labor platform.

---

## The Three Reports at a Glance

**Report 1 — Claude (the one I produced earlier in this conversation)**
- Strongest on: Practical data access roadmap, commercial platform pricing, the step-by-step "layer cake" methodology for combining datasets
- Weakest on: Didn't fully explore the uncertainty/error range question, didn't discuss the operational coverage method

**Report 2 — Gemini ("Analytical Frameworks")**
- Strongest on: The nursing home example (second industry worked through in detail), SBA size standards and federal contracting context, specific demographic numbers with cited ranges
- Weakest on: Somewhat academic tone, less focused on how to actually access and combine the data programmatically, treats some estimates as more precise than they really are

**Report 3 — Deep Research ("Determining Workforce Composition")**
- Strongest on: Uncertainty quantification (giving ranges instead of point estimates), the "payroll triangulation" and "operational coverage" methods as alternatives to simple revenue-per-employee division, careful handling of what counts as an "employee" vs. contractor
- Weakest on: Very technical/mathematical presentation, harder to extract actionable steps from, didn't complete the demographic estimates (left them as templates to fill in)

---

## Where All Three Agree (High-Confidence Findings)

These are things all three reports independently concluded. When three separate research processes reach the same answer, you can be fairly confident it's right.

### 1. The Core Data Sources Are the Same Everywhere

All three reports identify the same essential federal datasets:

| Dataset | What It Tells You | Everyone Agrees On |
|---------|-------------------|-------------------|
| **BLS OES/OEWS** | What jobs exist in an industry and in what proportions | This is THE primary source for occupational staffing patterns. Nothing else comes close for "what percentage of workers in industry X hold job Y." |
| **Census ACS PUMS** (via IPUMS or direct) | Demographics of people in specific jobs in specific places | Best source for "who holds these jobs" — race, gender, age, education — broken down by metro area |
| **QCEW** | Total employment counts by detailed industry and county | Most complete employment count data — covers 95% of U.S. jobs |
| **Census SUSB** | How firm size relates to employment and revenue | The key link between "this company makes $40M" and "it probably employs about 835 people" |
| **Census CBP** | Establishment counts by size and ZIP code | Best geographic granularity (down to ZIP) for understanding how many businesses of what size exist where |

### 2. The Revenue-to-Employee Estimate for a $40M Security Firm

All three converge on similar numbers, though with different levels of confidence:

| Report | Estimated Headcount | Method Used |
|--------|-------------------|-------------|
| Claude | ~835 | Revenue ÷ $47,900/employee (industry benchmark) |
| Gemini | 825–835 | Multiple benchmarks converging (Census 2017 historical, Kentley 2024, Vertical IQ) |
| Deep Research | ~530–740 (central: ~620) | Payroll triangulation with explicit uncertainty bounds |

**Why the disagreement matters:** Claude and Gemini used a simpler approach — take the industry-average revenue per employee and divide. Deep Research used a more sophisticated method that accounts for the fact that not all revenue goes to paying employees (some goes to equipment, insurance, overhead, etc.), and that wages in Atlanta specifically might differ from national averages. Deep Research's lower central estimate (~620) and wider range (~530–740) is arguably more honest about the uncertainty, but Claude/Gemini's ~835 is more consistent with simple industry benchmarks.

**The practical takeaway:** For organizing purposes, you're probably safe saying "a $40M security firm in Atlanta likely employs somewhere between 600 and 850 people." The exact number matters less than understanding that roughly 75-85% of them are frontline security guards.

### 3. The Occupational Mix Is Dominated by Guards

All three agree the workforce is roughly:
- **73-86% security guards** (the range depends on how narrowly you define the NAICS code)
- **4-5% supervisors/field leads**
- **6-10% administrative/office support**
- **2-3% management**
- **1-2% sales/client management**
- **1-2% recruiting/training/HR**

### 4. No Single Dataset Answers All Questions

Every report emphasizes the same fundamental problem: the federal statistical system was built as a collection of separate programs, each measuring different things. No single source combines industry + occupation + demographics + firm size + geography all at once. You always have to combine at least 2-3 sources to build a complete picture.

---

## Where They Meaningfully Disagree

### Disagreement 1: How Precise Can You Be?

**Claude and Gemini** present relatively specific numbers — "668 security guards, 33 supervisors, 25 managers" etc. — which gives a clean, usable picture.

**Deep Research** strongly pushes back on this approach, arguing that every number should be presented as a range with explicit uncertainty bounds. It points out that the revenue-per-employee ratio alone could be off by 25-30%, and that compounding multiple uncertain estimates (revenue → headcount → occupation mix → demographics) means the final numbers could be quite far from reality for any specific firm.

**Who's right?** Deep Research is technically more correct — these are estimates, not facts, and presenting them with false precision is misleading. But for organizing purposes, a specific "best guess" is more useful than a wide range. The best approach for the platform would be to show a central estimate prominently but always include a range (e.g., "~835 employees (likely range: 600–1,050)").

### Disagreement 2: The Revenue-Per-Employee Methodology

**Claude and Gemini** use the straightforward approach: look up the industry average revenue per employee, divide the firm's revenue by that number, done.

**Deep Research** introduces two additional methods that the others don't cover:

1. **Payroll Triangulation** — Instead of dividing revenue by revenue-per-employee, you first estimate what share of revenue goes to payroll (about 64% in security), then divide that payroll budget by the average local wage. This is more accurate because it accounts for the fact that wages vary by city (Atlanta security guards make ~$37,710/year, which is different from the national average).

2. **Operational Coverage Math** — For a security firm specifically, you can work backwards from contracts: if you're staffing 100 guard posts around the clock (24/7), each post needs about 4.7 full-time employees to cover all shifts plus vacation, sick time, and turnover. This is the most grounded method because it's based on how the business actually works rather than statistical averages.

**For the platform:** All three methods should be available. The simple revenue-per-employee is fine for quick estimates. Payroll triangulation can be automated using OEWS local wage data you'd already be pulling. Operational coverage math is harder to automate but could be offered as an advanced feature for specific industries with known staffing patterns.

### Disagreement 3: How Atlanta-Specific Can Demographics Get?

**Claude** provides specific Atlanta-adjusted demographic percentages (e.g., "48-52% Black for security guards in Atlanta") by reasoning about how Atlanta's local population demographics would shift national occupation demographics.

**Gemini** provides ranges drawn from NYC and Baltimore studies as "proxies" for Atlanta, suggesting "50.8% to 73.3% Black" — a very wide range that reflects different cities rather than Atlanta specifically.

**Deep Research** explicitly refuses to provide specific demographic numbers, instead leaving a template: "compute Pr(race | Security Guards, Atlanta MSA) from ACS microdata." It argues that only a direct computation from Atlanta-specific ACS PUMS data would be defensible.

**Who's right?** Deep Research is the most methodologically rigorous — you really should compute this from actual Atlanta ACS data rather than estimating from national averages or other cities. The good news is that this computation is very doable using IPUMS. The platform should build this capability rather than relying on proxy estimates.

---

## Unique Contributions Each Report Makes

### Only in Claude's Report:
- **Commercial platform pricing** — Lightcast at $5K–$12K/year, JobsEQ from Chmura, IBISWorld through university libraries. This is practical intelligence for deciding build-vs-buy.
- **Data USA (datausa.io)** as a free, zero-technical-skill tool for quick demographic lookups by occupation
- **Census QWI (Quarterly Workforce Indicators)** as a source for industry × geography × demographics simultaneously — neither Gemini nor Deep Research mentions this dataset by name

### Only in Gemini's Report:
- **Nursing home worked example** — A complete parallel analysis for NAICS 623110, including CMS staffing ratio regulations (0.55 RN hours per resident day), bed-to-revenue modeling ($13.4M per 120-bed facility), and nursing assistant demographics (91% female, 37% in/near poverty)
- **SBA size standards** — The detail that a $40M firm exceeds the small business threshold ($22M for security, $34M for nursing), which means it faces different regulatory requirements
- **Federal contracting context** — $5.56 billion in federal security contracts in 2023, and how winning a single large contract could instantly change a firm's workforce size
- **Location quotient** — Atlanta's security guard LQ is 1.00 (proportional to national average), with wages at $18.13/hr slightly below national peaks

### Only in Deep Research:
- **NAICS version mismatch warnings** — Many datasets are still coded to NAICS 2017 while the 2022 revision changed some industry definitions. Combining datasets across versions without a crosswalk can introduce errors.
- **Contract vs. in-house security distinction** — NAICS 561612 only covers contract security providers. A university's own security department would be classified under education, not security, which changes all the benchmarks.
- **1099 contractor problem** — If a firm uses independent contractors instead of W-2 employees, QCEW and OEWS will undercount the actual workforce because those datasets only cover employees, not contractors.
- **Unionization effects on staffing** — Protective service occupations have among the highest union membership rates nationally, which can affect wage scales, minimum staffing requirements, and turnover rates.
- **Regulatory instability** — The CMS nursing home staffing rule (finalized 2024, blocked by courts 2025, potentially rescinded) illustrates that "typical staffing" benchmarks can become obsolete when regulations change.

---

## Lingering Questions That Need More Exploration

### Question 1: Can We Actually Automate This for the Platform?

All three reports describe a manual research process — download this file, cross-reference that table, compute these proportions. For the platform to be useful, this needs to work automatically for any NAICS code and any geography a user selects.

**What needs to be figured out:**
- Can BLS OES staffing patterns be pulled via API for any NAICS code, or do you have to download bulk files? (The BLS API exists but has rate limits and doesn't expose all data series.)
- Can ACS PUMS demographic computations be pre-computed for all major occupation × MSA combinations, or do they need to run on-demand? (Pre-computation is probably the way to go — there are ~830 occupations × ~400 MSAs, which is manageable.)
- How do you handle NAICS codes where OES doesn't publish industry-specific staffing patterns? (Fallback to the parent NAICS code, but how far up the hierarchy before the data becomes meaningless?)

### Question 2: How Do We Get Revenue-Per-Employee Ratios at Scale?

The SUSB and Economic Census provide this data, but only for Economic Census years (every 5 years, most recent is 2022). Between census years, the ratio needs to be estimated or sourced from commercial databases.

**Options to explore:**
- IBISWorld publishes revenue-per-employee for ~12,000 industry codes — available through CUNY library access
- Kentley Insights has similar data — pricing unclear
- Could the platform maintain its own revenue-per-employee table by NAICS code, updated as new Economic Census data becomes available?

### Question 3: The ACS PUMS Geography Problem

ACS PUMS data uses PUMAs (Public Use Microdata Areas) as its smallest geography — areas of ~100,000 people. These don't line up cleanly with ZIP codes, counties, or MSAs. The Census Bureau provides crosswalk files, but mapping is approximate.

**What needs to be figured out:**
- For the platform's purposes, is MSA-level demographic data good enough? (Probably yes for most organizing purposes — you don't need to know the racial composition of security guards in a specific ZIP code, just in the Atlanta metro area.)
- If ZIP-level estimates are ever needed, Deep Research suggests using ZCTA (ZIP Code Tabulation Area) population demographics as a reweighting baseline applied to MSA-level occupation demographics. Is this worth implementing?

### Question 4: How Often Does This Data Change?

Different sources update on different schedules:
- OES: annually (May reference period, released ~12 months later)
- QCEW: quarterly (released ~6 months later)
- ACS PUMS: annually (1-year) or every 5 years (5-year, better for small areas)
- SUSB: annually for employment/payroll, every 5 years for receipts
- Economic Census: every 5 years

**For the platform:** You'd want an annual refresh cycle aligned with the OES release schedule, with QCEW updates quarterly for employment counts. The demographic data changes slowly enough that a 5-year ACS PUMS refresh is probably fine.

### Question 5: What About the 1099/Contractor Blind Spot?

Deep Research raises an important point that the other two miss: if a security firm uses independent contractors (1099 workers) instead of W-2 employees, all the government employment datasets will undercount the real workforce. This is increasingly common in industries like security, home health, and logistics.

**What needs to be figured out:**
- How prevalent is 1099 classification in each industry? (Some industries like trucking are notorious for it.)
- Are there any data sources that capture contractor labor? (The Nonemployer Statistics program from Census counts businesses with no paid employees, which is a partial proxy.)
- Should the platform flag industries where contractor misclassification is common, so users know the headcount estimates might be low?

### Question 6: Can O*NET Add Value Here?

Gemini briefly mentions SOC codes connecting to O*NET, and Deep Research notes it in passing, but neither deeply explores it. O*NET provides incredibly detailed information about each occupation — required skills, working conditions, typical education, physical demands, work context. This could be extremely valuable for organizing because it tells you *what the work actually feels like* for the people in those jobs, not just demographic statistics.

**Worth exploring:**
- O*NET data is completely free and available in bulk downloads
- It could enrich the platform's occupation profiles with information like "this job typically involves standing for long periods, working outdoors, and having little control over work pace" — which speaks directly to organizing grievances

### Question 7: Your Platform Already Has the BLS Industry-Occupation Matrix

The audit shows `bls_industry_occupation_matrix` with 113,473 rows already loaded. This is essentially the staffing patterns data that all three reports identify as the cornerstone of the methodology.

**What needs to be figured out:**
- What year/version is the data currently loaded? Is it the most recent (2024-2034 projections)?
- Does it include the occupation share percentages (the `p_k` values from Deep Research's formulas), or just raw employment counts?
- How does it connect to the rest of the platform — can you already look up "for NAICS 561612, what SOC codes are present and in what proportions"?

---

## Recommended Best Path Forward

Based on synthesizing all three reports, here's the most practical approach for adding workforce composition intelligence to the platform:

**Phase 1: Use What You Already Have**
Your `bls_industry_occupation_matrix` table already contains the core staffing patterns. Build a simple lookup: given a NAICS code, return the occupation breakdown. Display this as a "typical workforce composition" on employer profile pages.

**Phase 2: Add Revenue-to-Headcount Estimation**
Load SUSB data (or pull revenue-per-employee ratios from IBISWorld via CUNY library access) to create a lookup table by NAICS code. When the platform has revenue data for an employer (from SEC filings, D&B, etc.), automatically estimate headcount.

**Phase 3: Add Local Demographics**
Pre-compute occupation × MSA demographic distributions from ACS 5-year PUMS data for the ~50 largest MSAs. Store these as a lookup table. When showing a workforce profile, overlay the local demographic distribution onto the occupation breakdown.

**Phase 4: Integrate Into Organizing Intelligence**
Combine the workforce composition estimates with existing platform data (NLRB elections, OSHA violations, union density) to create richer target profiles: "This is a 600-person company where ~75% of workers are frontline security guards. In Atlanta, those guards are predominantly Black men in their late 30s making $18/hour. The industry has a 12% union membership rate and turnover exceeds 100% annually."

This last step is where the workforce composition data becomes truly powerful for organizing — it transforms abstract employer records into a picture of the actual human beings who work there.
