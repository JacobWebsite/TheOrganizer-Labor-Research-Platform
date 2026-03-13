# EEO-1 and BDS-HC: What They Are and How to Integrate Them

**Written for:** Jacob's Labor Relations Research Platform  
**Date:** March 2026  
**Purpose:** Plain-English guide to two new demographic data sources and how they fit into the existing platform

---

## Quick Summary

The platform currently **estimates** what an employer's workforce looks like demographically — using Census and government labor statistics blended together as a best guess. Two datasets exist that can dramatically improve or validate those estimates:

| Dataset | What It Is | Key Limitation |
|---|---|---|
| **EEO-1** (OFCCP FOIA Release) | Actual company-specific headcounts by race, gender, and job category | Only covers **federal contractors** (companies with government contracts); data is from 2016–2020 |
| **BDS-HC** (Census Bureau) | Average demographic composition of employers by industry, size, state, and age | Not company-specific — shows what employers of a given **type** look like, not individual companies |

Together, these two datasets cover a gap from two different directions: BDS-HC improves your benchmark estimates for all employers, while EEO-1 provides ground truth for the specific subset that are federal contractors.

---

## Part 1: EEO-1 Data

### What Is EEO-1?

The federal government requires certain employers to file a form called the **EEO-1** (Equal Employment Opportunity Report) every year. Think of it as an annual demographic snapshot — a company fills out a grid showing exactly how many of their workers are in each combination of race, gender, and job level.

For example, a hospital filing their EEO-1 might report:
- 12 White men in executive roles
- 43 White women in professional roles
- 87 Black women in service roles
- 29 Hispanic men in production/operations roles
- ...and so on across all combinations

This is **actual self-reported company data**, not an estimate. The employer counted their own employees and submitted the numbers directly to the federal government.

### Who Has to File?

Two groups:
1. **Private employers with 100+ employees** — required to file annually
2. **Federal contractors with 50+ employees** — required to file if they have government contracts worth $50,000 or more

Everyone files with the EEOC (Equal Employment Opportunity Commission). Federal contractors also send a copy to OFCCP (the Office of Federal Contract Compliance Programs), which is part of the Department of Labor.

### What's in the Form?

The EEO-1 grid covers:

**Race/Ethnicity Categories (9):**
- White (non-Hispanic)
- Black or African American
- Hispanic or Latino
- Asian
- American Indian or Alaska Native
- Native Hawaiian or Other Pacific Islander
- Two or More Races
- Middle Eastern or North African *(added in 2024 revision)*
- Non-Hispanic or Latino

**Gender:** Male, Female *(non-binary removed in 2025 revision)*

**Job Categories (10):**
1. Executive/Senior Level Officials & Managers
2. First/Mid Level Officials & Managers
3. Professionals
4. Technicians
5. Sales Workers
6. Administrative Support Workers
7. Craft Workers
8. Operatives
9. Laborers & Helpers
10. Service Workers

Every employer submits a separate report for each physical location, plus a consolidated "Type 2" report that rolls everything up to the company level. The data you can download publicly is the consolidated/company-level version.

That means if McDonald's has 3,000 restaurants, there are 3,000 establishment-level reports — but what's publicly released is the one consolidated report showing McDonald's Corporation total workforce demographics across all locations.

### Why Isn't This Data Normally Public?

The law that created the EEO-1 system (Title VII of the Civil Rights Act) includes a confidentiality provision. The EEOC is actually **prohibited** from releasing individual company data. They only publish aggregated summaries — like "healthcare companies in the South employ X% minority workers" — without naming specific companies.

This is a deliberate legal protection, meant to encourage honest reporting without fear of public embarrassment or competitor analysis.

### What Changed — The FOIA Release

In 2019, a journalist organization called the **Center for Investigative Reporting** filed a Freedom of Information Act (FOIA) request — a legal demand — specifically targeting **OFCCP's** copy of the data (not the EEOC's). The distinction matters: OFCCP receives the data specifically because it enforces equal opportunity rules on federal contractors, and OFCCP is subject to somewhat different rules than the EEOC.

After years of court battles, the federal courts ruled that this data is **not** protected commercial information and must be released. The result:

- **April 2023:** ~19,277 contractors who never objected to disclosure had their 2016–2020 data released
- **February 11, 2026:** 5 "bellwether" test companies' data released
- **February 25, 2026:** The remaining ~4,500 contractors who fought disclosure in court had their data released — courts ruled against them

All of this data is now on the Department of Labor's public FOIA library website, free to download.

**Important caveat:** This release is a one-time historical snapshot. The Trump administration's Executive Order 14173 (January 2025) rescinded the executive order that required federal contractors to share EEO-1 data with OFCCP in the first place. OFCCP will likely stop receiving contractor EEO-1 filings going forward, meaning **2016–2020 may be the only window of company-specific EEO-1 data that ever becomes public.**

### What the Download Files Look Like

The main data file is a large Excel spreadsheet (~50 MB). Each row is one company-year combination. Key columns include:

- **Company name and address**
- **EEOC Unit Number** (a unique company identifier within the EEO system)
- **EIN** (tax ID — this is your linking key to match against other databases)
- **DUNS number** (another identifier used in contracting)
- **NAICS code** (industry)
- **Filing year** (2016 through 2020 — so up to 5 rows per company)
- **~180 data columns** of headcounts in the format: `[Race Code][Gender Code][Job Category Code]`
  - Example: `BHF2` = Black (B), Hispanic (H), Female (F), Job Category 2 (Mid-Level Managers)
  - The data dictionary CSV explains every column name

**Download Links:**
- Main FOIA Library page: https://www.dol.gov/agencies/ofccp/foia/library/Employment-Information-Reports
- Data dictionary (read this first): https://www.dol.gov/sites/dolgov/files/OFCCP/foia/files/DataSetDictionary-EEO1FY2016-2020.csv
- Consolidated data file (~50 MB): https://www.dol.gov/sites/dolgov/files/OFCCP/foia/files/Consolidated-Non-Exempt-EEO-1-Reports-508c.xlsx

### Who Is Covered?

The released data covers **federal contractors** — companies that supply goods or services to the federal government. This is a substantial but specific subset of all U.S. employers. It skews heavily toward:

- **Defense and aerospace** (Lockheed, Raytheon, Boeing)
- **Healthcare** (hospitals and health systems with Medicare/Medicaid are often considered contractors)
- **IT and professional services** (consulting firms, government IT providers)
- **Construction** (building government facilities)
- **Staffing firms**
- **Universities** (many receive federal research grants that trigger contractor status)

It **underrepresents:**
- Purely private-sector retail and food service
- Small and mid-size businesses without government contracts
- Entertainment, media, and many consumer-facing industries

This matters for your platform because many of the most important organizing targets — logistics warehouses, retail stores, fast food, janitorial services — may not be in this dataset.

---

## Part 2: BDS-HC Data

### What Is BDS-HC?

BDS-HC stands for **Business Dynamics Statistics of Human Capital**. It's a new experimental dataset released by the U.S. Census Bureau in April 2025.

Here's the key thing to understand about where this data comes from: The Census Bureau has always had a massive database called the **Longitudinal Business Database (LBD)** — basically a complete roster of every employer in America, updated yearly, going back to 1976. They knew *about* businesses (size, industry, location, age) but they didn't know *about the workers* at those businesses.

To create BDS-HC, the Census Bureau did something clever. The IRS requires every employer to file a **W-2 form** for every employee every year. Those W-2 forms contain the employer's tax ID (EIN) and the employee's Social Security Number (SSN). The Census Bureau matched those W-2 records against:
1. Their business database (using the EIN) → to identify the employer
2. Their population demographics database (using the SSN) → to identify the worker's demographics

The result: the first-ever public dataset that combines actual employer records with actual worker demographics, covering 98% of all employment in America, from 2006 through 2022.

### What BDS-HC Is NOT

This is very important to understand upfront: **BDS-HC does not let you look up individual companies.**

You cannot type "Walmart" into BDS-HC and see Walmart's demographics. Instead, BDS-HC tells you what **types** of companies look like. The data is published in aggregate tables — like "here's what healthcare employers with 50–249 workers in the South look like demographically."

Think of it like this analogy: BDS-HC is like a study that says "men aged 30–40 who work in finance tend to earn between $80K–$120K." It's useful for understanding the pattern, but it won't tell you what *your specific neighbor* who works in finance earns. EEO-1 is more like finding your neighbor's actual pay stub.

### How the Data Is Structured

For each of six demographic characteristics, every employer in America is sorted into one of six buckets based on what **share** of their workers belong to that demographic group:

| Bucket | Meaning |
|---|---|
| 0–10% | Almost none of their workers are in this group |
| 10–25% | A small minority |
| 25–50% | Between a quarter and half |
| 50–75% | A majority |
| 75–90% | A strong majority |
| 90–100% | Almost all workers are in this group |

**The six demographic dimensions:**
1. Age (specifically: share of workers over 55)
2. Sex (share female)
3. Race (separate tables for each racial group: White, Black, Hispanic, Asian, Other)
4. Ethnicity (share Hispanic/Latino)
5. Nativity (share foreign-born)
6. Education (share with college degree)

Each dimension is further broken down by:
- **Firm size** (5 categories: 1–19, 20–49, 50–249, 250–999, 1000+)
- **Firm age** (startup vs. established)
- **State** (all 50 states)
- **Industry sector** (broad NAICS categories)

So for example, one table might tell you: "In 2022, among healthcare employers in the South with 50–249 workers, 38% were in the '75–90% female workforce' bucket and 22% were in the '50–75% female' bucket."

### Key Findings from the Data

The Census Bureau researchers who built BDS-HC published a companion paper with major findings. These findings are directly relevant to your platform:

1. **Workplaces are more racially homogeneous than you'd expect.** If workers and employers matched randomly, you'd expect random mixing of demographic groups across employers. But actual W-2 data shows employers cluster — they tend to hire workers who look similar to their existing workforce. This validates your assumption that industry + geography + size predicts workforce composition.

2. **Firm demographics changed substantially from 2006–2022.** The shift toward older, more racially diverse, more educated workforces happened mostly through existing companies *changing who they hire* — not through new companies replacing old ones. This means demographic estimates using industry averages from older data may be off.

3. **Different demographic groups face systematically different economic conditions based on who employs them:**
   - Workers at employers with mostly college-educated workforces: +2.7% job growth/year
   - Workers at employers with high shares of workers over 55: −1.9% job growth/year
   - Workers at employers with lower shares of White workers: higher job creation BUT also higher job destruction (more volatile employment)
   - These differences persist even after controlling for industry, state, and firm size

4. **Startup firms skew younger and more racially diverse** than older firms in the same industry.

**Download Links:**
- BDS-HC landing page (with data section): https://www.census.gov/data/experimental-data-products/bds-human-capital.html
- BDS general datasets page (where CSV files are hosted): https://www.census.gov/programs-surveys/bds/data.Datasets.html
- Release announcement: https://www.census.gov/programs-surveys/ces/news-and-updates/updates/04032025.html
- Working paper with full methodology: https://www2.census.gov/library/working-papers/2025/adrm/ces/CES-WP-25-20.pdf

---

## Part 3: How to Integrate Both Into This Platform

### The Current Gap They Fill

The platform currently estimates employer workforce demographics using a blended formula:

```
blended_estimate = (ACS industry × state average × 60%) + (LODES county data × 40%)
```

This is a reasonable approach but has known weaknesses:
- It treats all employers in the same industry the same, regardless of size or age
- The ACS and LODES data lags 2–3 years behind reality
- There's no way to check whether the estimates are right

Both new datasets address these weaknesses in different ways.

---

### Integration Path 1: BDS-HC as a Calibration Benchmark

**What problem it solves:** Your demographic estimates may be systematically too high or too low for certain types of employers. BDS-HC tells you what those employers should actually look like according to real W-2 data.

**How it works in practice:**

Step 1 — Download the BDS-HC CSV tables for race and ethnicity, filtered to the industries and states where your organizing targets concentrate.

Step 2 — For a sample of employers in your database (say, 500 healthcare employers in the Southeast), compare:
  - What your ACS + LODES blended estimate says their workforce looks like
  - What the BDS-HC distribution says employers of that type (healthcare × Southeast × 50–249 workers) actually look like

Step 3 — If your estimates cluster in the "25–50% Black workers" bucket but BDS-HC shows most employers of that type are in the "50–75% Black workers" bucket, you have a systematic bias. You can apply a correction factor.

**How to add this to the database:** Create a new table called something like `bds_hc_benchmarks` that stores the BDS-HC distributions for each industry × state × firm size combination. Then update the workforce composition estimation function to check this table when generating estimates, adjusting the blended estimate toward the BDS-HC distribution.

**The plain-English version of what this does:** Right now, if you're estimating the demographics of a medium-sized healthcare employer in Georgia, you're using a general "healthcare in Georgia" average from the Census. BDS-HC lets you say "here's what medium-sized healthcare employers in Georgia specifically look like." It's a more precise target to aim for.

---

### Integration Path 2: EEO-1 as Ground Truth for Federal Contractors

**What problem it solves:** For employers who are federal contractors, you no longer need to estimate their workforce demographics — you can look up the actual numbers they filed with the government.

**How it works in practice:**

Step 1 — Download the consolidated EEO-1 data file (~50 MB Excel).

Step 2 — Match it to your existing employer records using **EIN** (tax ID number). Your platform already stores EINs from multiple sources (OSHA, WHD, SAM.gov). EIN matching is your highest-confidence matching method — it's a unique number assigned to each employer by the IRS, so there's very little ambiguity.

Step 3 — For any employer that matches, store their actual EEO-1 headcounts in a new table and flag that this employer has verified demographic data. When displaying or scoring that employer, use the actual data instead of the estimate.

Step 4 — Create a new `demographic_data_source` flag on each employer record:
- `eeo1_verified` — actual 2016–2020 EEO-1 filing found and matched
- `bds_hc_calibrated` — estimate adjusted using BDS-HC benchmarks
- `blended_estimate` — original ACS + LODES approach (no enhancement)

**Coverage expectations:** Your SAM.gov integration already identifies federal contractors. Of your ~50,000 priority organizing targets, a meaningful portion will be federal contractors, particularly in healthcare, defense supply chains, construction, and professional services. Realistically, you might find EEO-1 matches for somewhere between 5,000 and 15,000 of your priority targets — which is a significant upgrade in data quality for those specific employers.

**The plain-English version:** Instead of guessing "this defense contractor probably has a workforce that's about 25% minority," you can say "this defense contractor's own 2018 EEO-1 filing shows 31% minority workers, with most minority workers concentrated in Operative and Service roles, not management." That's a completely different level of specificity.

---

### Integration Path 3: EEO-1 Job Category Breakdown as an Organizing Signal

This is the most strategically interesting integration for organizing purposes — and it's something neither BLS data nor ACS estimates can give you.

**What problem it solves:** Knowing a company is 40% minority overall tells you something. But knowing that a company is 40% minority *but 95% of those minority workers are in the lowest-paid service and laborer categories, while management is 92% White* — that tells you something much more actionable.

The EEO-1 form captures exactly this. The grid of race × gender × job category reveals the shape of workplace inequality, not just the total number.

**Proposed new scoring signal: "Demographic Stratification Index"**

Concept: For any employer with EEO-1 data, calculate how unequal the demographic distribution is across job levels. A company where the racial composition of management closely mirrors the racial composition of line workers scores low (less stratified). A company where management is predominantly White and line/service workers are predominantly minority scores high (more stratified).

High stratification = workers facing more apparent inequality = stronger potential organizing grievance.

Formula sketch:
```
stratification_score = 
  (% minority in bottom 3 job categories) 
  - (% minority in top 3 job categories)
```

A score near 0 means roughly equal representation across levels. A score of 50+ means minority workers are heavily concentrated in the lowest job tiers. This is a measurable, defensible indicator of workplace inequality that organizing researchers would find directly useful.

**Where this goes in the platform:** This would be a new signal in the "Anger" pillar of the scoring system, joining OSHA violations and wage theft as indicators of worker grievances. It's based on actual employer-reported data, so it's more defensible than an estimated signal.

---

### Integration Path 4: BDS-HC Growth Rates for the Scorecard

The scoring roadmap already identifies adding a **BLS growth signal** as a planned improvement. BDS-HC provides a related but different signal.

**What it adds:** BDS-HC shows that employers with certain workforce compositions systematically grow or contract faster than others. Specifically:

- Employers with mostly college-educated workers: +2.7%/year growth
- Employers with majority-minority workforces: higher volatility (both faster growth AND faster decline)
- Employers with mostly older workers: −1.9%/year

**How to use this in scoring:** When assessing an organizing target, an employer in a contracting sector (negative job growth) is generally a worse organizing target than one in a growing sector — workers at a shrinking employer feel more precarious, which *can* motivate organizing but *also* makes winning a contract harder because the employer has less to give.

The BDS-HC growth rates by workforce composition can be loaded as a lookup table and used to adjust the existing industry growth factor in the scorecard.

---

## Part 4: Side-by-Side Comparison

| Feature | EEO-1 | BDS-HC |
|---|---|---|
| **Who it covers** | ~23,000+ federal contractors (employer-specific) | Nearly all ~7 million US non-farm employers (in aggregate buckets) |
| **Specificity** | Individual company data | Industry × state × size averages |
| **Demographics covered** | Race, ethnicity, gender | Age, sex, race, ethnicity, nativity, education |
| **Job breakdown** | Yes — 10 job category levels | No — only company-level totals |
| **Years available** | 2016–2020 (historical snapshot) | 2006–2022 annual time series |
| **Recency** | Data is 6–10 years old | Most recent year is 2022 |
| **Free to download** | Yes | Yes |
| **File format** | Excel (.xlsx) + CSV data dictionary | Multiple CSV files |
| **How to link to your DB** | EIN number (direct match) | NAICS code + state + firm size (lookup table match) |
| **Best use in platform** | Ground truth for contractor employers + inequality signal | Calibration benchmark for all employer estimates |
| **Who it's most useful for** | Defense, healthcare, IT, construction contractors | All industries equally |

---

## Part 5: What to Build — Recommended Order

Given the project's current priorities (fix JOIN bug, improve scoring, expand data), here's a suggested integration order:

**Phase 1 — Quick win, high value:**
Download the EEO-1 data dictionary and main file. Write a Python script that loads it into a new PostgreSQL table (`eeo1_filings`) and runs EIN matching against your existing employer records. Flag any matches. Estimated time: 1–2 Claude Code sessions.

**Phase 2 — Calibration improvement:**
Download the BDS-HC CSV files for race and ethnicity by industry × state × firm size. Load them into a `bds_hc_benchmarks` table. Update the demographic estimation function to use BDS-HC distributions as a prior (a starting point) instead of pure ACS averages. Estimated time: 2–3 Claude Code sessions.

**Phase 3 — New scoring signal:**
For any employer with EEO-1 data, calculate the demographic stratification index (inequality across job levels). Add this as a new factor in the "Anger" pillar of the scoring system. This requires both the EEO-1 integration from Phase 1 and a scoring pipeline update. Estimated time: 1–2 Claude Code sessions.

**Phase 4 — Validation:**
Use the now-verified EEO-1 data to check your ACS + LODES estimates. For each employer with EEO-1 data, compare the estimated vs. actual workforce demographics. Measure the systematic bias. Use BDS-HC to understand whether the bias varies by industry or employer size. Write up the findings. Estimated time: 1 session.

---

## Part 6: Important Caveats

**The EEO-1 data is old.** The most recent year available (2020) is now 6 years ago. A lot can change in 6 years — mergers, layoffs, demographic shifts. Treat EEO-1 data as a strong indicator of patterns, not a current headcount. Flag it clearly in the UI: "Workforce demographics based on 2016–2020 EEO-1 filing."

**The EEO-1 is self-reported.** Employers fill this out themselves. Some categorize workers inaccurately. Some had data errors (the OFCCP actually found and corrected errors in the 2017 data after release). It's much better than an estimate, but it's not perfect.

**The EEO-1 only covers the consolidated (company-wide) report.** Individual establishment-level EEO-1 data was not part of the FOIA release. So you'll know what a company looks like overall, but not what a specific warehouse or hospital location looks like demographically. Your OSHA and WHD data operates at the establishment level; the EEO-1 integration will require thinking about how to handle that mismatch.

**BDS-HC education data has high missing rates.** About 85% of workers in the BDS-HC data have no education information, because the Census only collects education through decennial census long forms and the ACS — both of which miss many people. The age, sex, race, ethnicity, and nativity tables are much more complete.

**The political situation is uncertain.** The Trump administration's rollback of EO 11246 means no new EEO-1 data will flow to OFCCP going forward, making future releases like this less likely. The window to work with this data is now.

---

## Appendix: Key Links

| Resource | URL |
|---|---|
| EEO-1 FOIA Library (all releases) | https://www.dol.gov/agencies/ofccp/foia/library/Employment-Information-Reports |
| EEO-1 Data Dictionary | https://www.dol.gov/sites/dolgov/files/OFCCP/foia/files/DataSetDictionary-EEO1FY2016-2020.csv |
| EEO-1 Consolidated Data File (~50MB) | https://www.dol.gov/sites/dolgov/files/OFCCP/foia/files/Consolidated-Non-Exempt-EEO-1-Reports-508c.xlsx |
| BDS-HC Landing Page | https://www.census.gov/data/experimental-data-products/bds-human-capital.html |
| BDS Datasets Page (CSV downloads) | https://www.census.gov/programs-surveys/bds/data.Datasets.html |
| BDS-HC Working Paper (full methodology) | https://www2.census.gov/library/working-papers/2025/adrm/ces/CES-WP-25-20.pdf |
| BDS-HC Release Announcement | https://www.census.gov/programs-surveys/ces/news-and-updates/updates/04032025.html |
| EEOC Explore (public aggregate tool) | https://www.eeoc.gov/data/eeo-data-collections |
