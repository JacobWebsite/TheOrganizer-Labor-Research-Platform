# Workforce Estimation Model: Three-Report Comparison & Implementation Plan

## How This Document Works

You asked three different AI systems the same question: "How can I estimate a company's workforce size and composition from the outside?" Each came back with a detailed report. This document does three things:

1. **Compares** all three reports — where they agree, where they disagree, and who got what right
2. **Extracts** the best ideas from each into a unified understanding
3. **Builds** a concrete, phased model plan that you can actually implement on your platform

The goal isn't just "know about estimation methods." It's to build a working system that takes an employer name and produces: *how many people work there, what jobs they hold, and how confident we are in those numbers.*

---

## Part 1: Who Said What — The Three Reports at a Glance

### ChatGPT (Workforce_Size_Estimation_Research_Report.txt)
- **Strongest on:** Practical recipes, the NLRB calibration methodology, creative ideas (shift-work prediction from review timing, satellite parking lot counting)
- **Unique contributions:** The "vacancy rate math" formula using JOLTS data, the "1.15 multiplier" for parking lot counts, the concept of "Union2Vec" embeddings trained on CBAs
- **Weaknesses:** Some accuracy claims feel optimistic (±0-5% for SEC filings doesn't account for definition problems), less careful about uncertainty ranges, treats some methods as more reliable than they are

### Gemini Deep Research (deep-research-report.md)
- **Strongest on:** Uncertainty quantification — every method gets a realistic accuracy range. The insistence on storing estimates as *distributions* (a range, not a single number). The clearest explanation of *why* each method fails
- **Unique contributions:** The Mermaid data-flow diagram, the concept of "definition tags" (is this headcount vs FTE vs jobs?), the explicit callout that Industry2Vec is archived and shouldn't be relied on, the most comprehensive open-source tool table with maintenance status
- **Weaknesses:** Most cautious — sometimes so cautious it's hard to know what to actually *do*. Accuracy ranges are sometimes so wide they're not useful (±30-70% for LinkedIn on blue-collar firms)

### Claude Research (compass_artifact)
- **Strongest on:** Concise synthesis of the commercial provider landscape, the clearest "priority order" for what to build, the strongest explanation of why NLRB data is your secret weapon
- **Unique contributions:** The LEHD/LODES block-level data as a validation layer, EEO-1 data becoming publicly available, the `naicskit` ML-based NAICS classifier, the explicit identification that "no one has assembled the full pipeline" as the key gap
- **Weaknesses:** Less detailed on individual method mechanics, less creative on novel approaches, accuracy ranges tend to cluster toward the optimistic end

---

## Part 2: Where All Three Agree (High-Confidence Consensus)

When three separate research processes independently reach the same conclusion, you can be quite confident it's right. Here's what all three converged on:

### The same six core methods, in the same reliability order

All three reports identify the same estimation methods and rank them in essentially the same order from most to least reliable:

| Method | All Three Agree On | Consensus Accuracy |
|--------|-------------------|-------------------|
| **SEC 10-K employee count** | Gold standard for public companies. Legally mandated, audited numbers. | ±2-5% for total headcount |
| **QCEW** | Best government source. Near-census quality for industry/geography totals. | ±1-5% at aggregate level |
| **BLS Staffing Patterns** | THE source for "what jobs exist in what proportions." Nothing else comes close. | ±15-25% for major occupations |
| **Payroll triangulation** | Strong when you have clean compensation data. | ±10-30% |
| **Operational coverage math** | Excellent for hospitals, schools, warehouses — anywhere with measurable capacity. | ±10-30% |
| **Revenue-per-employee** | Weakest traditional method. Huge within-industry variation. | ±25-50% |

### NLRB data is your most valuable unique asset

This is the single strongest point of agreement. Every report — and the earlier three-report synthesis — independently concluded that your NLRB bargaining unit records give you something that commercial providers like Revelio Labs and People Data Labs *don't have*: ground-truth employee counts at specific physical workplaces. ChatGPT explicitly called this your "Truth Set." Gemini said it "turns your platform from clever heuristics into a continuously improving measurement system." Claude called it "uniquely valuable calibration points that most commercial workforce intelligence providers lack."

**Why this matters in plain language:** Imagine you're trying to guess how many people work at a warehouse. You have five different methods, each giving you a different answer. Without a way to check who's right, you're just averaging guesses. But if you *know* the exact count at 500 similar warehouses from NLRB elections, you can measure which method is closest for warehouses specifically, and then apply a correction factor to all future warehouse estimates. That's calibration — and it's what separates a serious estimation system from guesswork.

### Entity resolution is the prerequisite for everything

All three reports identify the same fundamental problem: your data lives in separate government databases that don't talk to each other. "Target Corp" in OSHA records, "Target Corporation" in NLRB records, and "TGT" in SEC filings are all the same company, but a computer doesn't know that without help. All three recommend Splink as the primary tool for solving this. All three note that this matching problem is the single biggest technical hurdle.

### No single method works — you have to layer them

Every report emphasizes "triangulation" or "ensemble" approaches. The logic is simple: each method has different blind spots. LinkedIn undercounts warehouse workers. Revenue-per-employee is thrown off by automation. QCEW data is delayed by months. But when three independent methods with *different* blind spots all converge on similar numbers, you can be much more confident. All three reports provide "recipes" for combining methods, and they're remarkably similar.

### The same open-source tools keep appearing

Splink (entity resolution), JobSpy (job posting scraping), skills-ml (occupation classification), Company2Vec/Industry2Vec (company similarity), edgartools (SEC filing parsing), and the census/BLS API wrappers appear in all three reports. This convergence suggests these are genuinely the best available tools, not just the first ones each AI found.

---

## Part 3: Where They Meaningfully Disagree

### Disagreement 1: How precise can you realistically be?

This is the biggest split across the three reports.

**ChatGPT** is the most optimistic. It presents SEC filing accuracy as "±0-5%" and frames the combined estimation approach as producing clean, defensible numbers. It gives specific formulas and multipliers (like "multiply parking lot cars by 1.15").

**Gemini** is the most cautious. It pushes hard on the idea that every number should be a *range*, not a point estimate. It argues that even SEC filings carry ±5-15% uncertainty because of definitional ambiguity (does "employees" include contractors? Is it global or U.S. only?). It gives the widest accuracy ranges across the board.

**Claude** falls in the middle — giving ranges but generally toward the optimistic end.

**Who's right?** Gemini's caution is technically more honest. Here's why: even when a company says "we have 10,000 employees" in their SEC filing, the question of *what that means* (does it include 2,000 part-timers counted as half? 3,000 contractors? The subsidiary they acquired in November?) introduces real uncertainty for your purposes. For organizing, you need to know how many people work at a *specific location doing specific jobs* — and a company-wide number from a filing is just the starting point.

**Practical takeaway for the model:** Store every estimate as a median plus a range (Gemini's recommendation), but display the median prominently (ChatGPT's instinct that organizers need a usable number). Show the range as a confidence indicator, not the primary display.

### Disagreement 2: How useful is LinkedIn data really?

**ChatGPT** treats LinkedIn as a core data source worth investing in — reweighting by occupation to correct for bias, using it for geographic distribution of employees at large firms.

**Gemini** is much more skeptical, giving it ±30-70% accuracy for blue-collar/service firms and warning it can be essentially useless for the kinds of workers organizers most care about.

**Claude** takes a middle position — useful with correction factors, but noting extreme examples of entity-matching errors (a cloud company called "Railway" showing 4,000 LinkedIn profiles from railroad workers).

**Who's right?** For *your* platform specifically, Gemini is closer to correct. The workers organizers care most about — warehouse workers, security guards, janitors, food service workers, nursing assistants — are exactly the populations LinkedIn dramatically undercounts. It's worth having as one signal among many, but it should get very low weight in your estimation model for blue-collar industries and high weight only for white-collar/tech companies.

### Disagreement 3: How much to invest in satellite imagery

**ChatGPT** is enthusiastic — presents specific methods (computer vision models, shift-time estimation from time-series images, the 1.15 carpooling multiplier).

**Gemini** is pragmatic — notes it exists but warns about "shared lots, multi-tenant sites" and rates it ±15-40% even for ideal cases.

**Claude** is dismissive — mentions it but notes it's "expensive for commercial imagery and increasingly irrelevant as remote work grows."

**Who's right?** For your platform's current stage, satellite imagery is a distraction. It's technically interesting but requires specialized computer vision skills, commercial image subscriptions, and only works for a subset of workplaces. The ROI is much higher on getting entity resolution and government data integration right first. Revisit this in a later phase if specific use cases emerge (like monitoring a warehouse complex where you need shift-level estimates).

### Disagreement 4: Job posting sustainability

**ChatGPT** treats JobSpy as a straightforward tool — use it, get data, integrate it.

**Gemini** raises the most important warning: scraping job boards violates terms of service, scrapers break constantly, and a sustainable strategy should shift toward scraping *employer-owned career pages* and using public APIs/feeds rather than depending on Indeed and LinkedIn access that could disappear.

**Claude** mentions JobSpy positively but doesn't flag the legal/operational risk.

**Who's right?** Gemini's caution is important. Building a core platform feature on data access that could be cut off at any time is risky. The smarter approach: use JobSpy for initial research and model training, but build the production system around employer career pages (which are public and intended to be read) supplemented by public job APIs where available.

---

## Part 4: Unique Ideas Worth Keeping From Each Report

### From ChatGPT (ideas the others missed)

1. **Vacancy Rate Math using JOLTS data.** The formula: if a company has 100 open job postings and the industry vacancy rate is 5%, the implied total workforce is ~1,900. This is a clever indirect estimation method that neither Gemini nor Claude mentioned. It's not highly accurate (ChatGPT says ±20-30%), but it's another independent signal to add to the ensemble.

2. **"Union2Vec" — labor-specific embeddings.** The idea of training an embedding model on Collective Bargaining Agreements and NLRB decisions so organizers can search semantically ("find contracts with strong subcontracting protections") rather than by keywords. This is a genuinely novel idea that directly serves organizing intelligence.

3. **Review timing as shift-work predictor.** Looking at *when* Glassdoor/Indeed reviews are posted (clusters at 3 AM suggest night-shift workers) to estimate shift schedules. Creative and low-cost — useful for planning leafleting campaigns.

4. **The "big fish in a small pond" logic.** If SUSB shows only one firm with 500+ employees in a specific county-industry, and you know your target is in that industry, the SUSB count effectively reveals that company's headcount. This is a simple, practical technique for narrowing down aggregated data.

### From Gemini (ideas the others missed)

1. **Store every estimate as a distribution, not a point.** This is the most important methodological recommendation from any of the three reports. A system that says "~850 employees (likely range: 600-1,050, based on 3 independent estimates)" is fundamentally more useful than one that says "835 employees" — because it tells the organizer how confident to be.

2. **"Definition tags" on every estimate.** Is this headcount or FTE? Employees-only or including contractors? Global or domestic? March 12 snapshot or annual average? Tracking these metadata tags prevents apples-to-oranges comparisons and makes the model's reasoning auditable.

3. **Calibration engine as the highest-leverage custom build.** Gemini explicitly says: "If you build only one bespoke component, the highest leverage is a calibration engine that learns proxy corrections by NAICS × region × job-type using your NLRB headcounts." This is the clearest single recommendation from any report.

4. **The comprehensive tool maintenance assessment.** Gemini is the only report that checked whether each open-source tool is actually maintained, noting that Industry2Vec was archived in 2020 and several other tools are likely stale. This matters enormously for building a production system.

5. **Domain adaptation warning.** Your NLRB ground truth is concentrated in unionized workplaces, which are not representative of all workplaces. Models trained on this data could overfit to union-heavy industries. Gemini flags this explicitly; the others don't.

### From Claude (ideas the others missed)

1. **LEHD/LODES block-level employment data.** Census publishes employment counts at the census block level — fine enough to isolate individual large facilities. Neither ChatGPT nor Gemini mentioned this. It's a powerful validation layer for establishment-level estimates.

2. **EEO-1 data becoming publicly available.** A February 2025 legal settlement is forcing release of federal contractors' EEO-1 workforce demographic data (2016-2020). This is directly useful for demographic composition estimates and wasn't mentioned by the other two.

3. **`naicskit` for ML-based NAICS classification.** When a company's industry code is wrong (or missing), everything downstream breaks. `naicskit` can classify companies from text descriptions with 87% accuracy. This addresses the problem all three reports identified ("NAICS misclassification is the single largest error source") with a concrete tool.

4. **The pipeline gap.** Claude explicitly states that every piece of the estimation pipeline exists as an open-source component, but nobody has assembled them end-to-end. Building that assembly is itself the most valuable open-source contribution your platform could make.

---

## Part 5: The Unified Model Plan

Based on the best ideas from all three reports, plus your platform's existing capabilities, here is a concrete phased plan for building the workforce estimation model.

### What the model does (in plain language)

An organizer types in an employer name. The system:
1. Figures out which records in OSHA, NLRB, SEC, DOL, and other databases belong to that employer
2. Estimates how many people work there (total headcount)
3. Estimates what jobs those people hold (occupational composition)
4. Estimates the demographics of the workforce (race, gender, age, education)
5. Shows confidence levels for each estimate
6. Gets smarter over time by comparing its estimates against known NLRB election data

### Phase 1: Foundation — Entity Resolution & Data Wiring (builds on existing roadmap Phase A-B)

**What you're building:** The ability to look up "Amazon" and see records from all your databases unified under one identity.

**Why it has to come first:** Every estimation method depends on knowing *which company* you're estimating. If OSHA records for "Amazon.com Services LLC" and NLRB records for "Amazon Fulfillment Center BFI4" aren't linked, you can't combine their signals.

**How it works (simply):**
- Splink looks at company names, addresses, cities, and industry codes across your databases
- For each pair of records, it calculates a probability that they're the same entity
- High-probability matches get linked automatically; borderline cases get flagged for review
- The result is a "canonical employer ID" — one number that connects all records for that employer

**Key tools:** Splink (for probabilistic matching), libpostal or usaddress (for cleaning messy addresses), cleanco (for stripping "Inc/LLC/Corp" noise from company names)

**Success metric:** Can you type "Target" and get back a unified view showing their OSHA violations, NLRB elections, SEC filings, and DOL records on one page?

**What your platform already has that helps:** 96.2% employer-to-union linkage rate, existing matching pipeline, 207+ tables with records to link

### Phase 2: The Headcount Estimation Engine

**What you're building:** A system that produces a headcount estimate (with confidence range) for any employer, using whatever data is available for that employer.

**How it works (the "layer cake"):**

Think of this like building a case in court — you gather evidence from multiple independent witnesses, weigh how reliable each witness typically is, and arrive at a verdict.

**Layer 1 — Direct evidence (highest confidence):**
- SEC 10-K employee count (for public companies) → ±2-10%
- NLRB bargaining unit size (for specific workplaces with election records) → near exact
- OSHA inspection records (inspectors sometimes note facility size) → ±10-20%

**Layer 2 — Government statistical evidence (medium-high confidence):**
- QCEW county × NAICS employment totals → good for "big fish in small pond" situations
- CBP establishment size class → constrains the range ("this type of workplace in this area typically has 100-249 employees")
- SUSB enterprise size data → constrains plausible firm size

**Layer 3 — Financial triangulation (medium confidence):**
- Revenue ÷ industry RPE ratio → ±25-50%
- Payroll ÷ average wage → ±10-30% (when payroll data exists)
- CEO pay ratio median comp × headcount range → ±15-25% for public companies

**Layer 4 — Digital trace evidence (lower confidence, but timely):**
- Job posting count ÷ industry vacancy rate → ±20-40%
- LinkedIn profile count × occupation-specific correction factor → ±15-70% depending on industry
- Indeed/Glassdoor review volume → directional only, ±50%+

**Layer 5 — Operational capacity evidence (variable confidence):**
- Hospital beds × 5.0-6.0 FTEs/bed → ±10-20%
- School enrollment ÷ 7.1-7.3 staff ratio → ±10-15%
- Warehouse square footage ÷ industry sq.ft/employee → ±20-40%

**How the layers combine:**
Each layer produces an estimate and a confidence range. The system averages them, giving more weight to higher-confidence estimates. Technically this is called "inverse-variance weighting" — but in simple terms, it means the most reliable sources count more.

Example for a public hospital:
- SEC filing says 2,100 employees globally (±5%) → weight: high
- The local facility had an NLRB election showing 850 nurses in the bargaining unit (near exact) → weight: very high for that unit
- The hospital has 400 beds, implying ~2,000-2,400 staff total (±15%) → weight: medium-high
- LinkedIn shows 1,200 profiles (but hospital workers have low LinkedIn rates, so corrected estimate is ~1,800-2,500) → weight: low
- CBP says establishments of this type in this county have 500-999 employees → weight: medium (provides a sanity check)

Combined estimate: ~2,100 employees total, ~850 in the nursing unit, likely range 1,900-2,300.

**Key implementation detail from Gemini:** Store every estimate with metadata: `{method: "sec_10k", value: 2100, low: 1995, high: 2205, definition: "global_employees_only", date: "2025-03-15", source_doc: "0001234567-25-000123.htm"}`

### Phase 3: The Composition Model (what jobs people hold)

**What you're building:** The ability to say not just "this employer has ~850 employees" but "roughly 520 are registered nurses, 170 are nursing assistants, 60 are administrative staff, 40 are facilities/maintenance, and 60 are management."

**How it works:**

**Step 1 — Start with the BLS staffing pattern.**
You already have the `bls_industry_occupation_matrix` table (113,473 rows). For any NAICS code, this tells you the *typical* occupational breakdown. For NAICS 622110 (hospitals): 26% RNs, 15% nursing assistants, 5% janitors, etc.

**Step 2 — Adjust for what you actually know.**
The BLS pattern is the default, but real companies differ from the average. Adjust using:
- **NLRB unit descriptions:** If an election petition describes a unit of "all security officers" at a facility, you know that facility has security officers (and roughly how many were in the unit)
- **Job postings:** If the employer is currently hiring 20 warehouse associates and 2 managers, that tells you something about the ratio
- **OSHA violation narratives:** An OSHA report about a forklift accident tells you the facility has forklift operators
- **SEC human capital disclosures:** Some companies mention workforce segments ("our 15,000 drivers and 8,000 warehouse associates")

**Step 3 — Apply local demographics.**
Once you know the occupational mix, overlay Census ACS PUMS data for the local metro area. If 60% of security guards in the Atlanta metro are Black men in their 30s-40s, and this is a security company in Atlanta, that demographic profile likely applies.

**What this looks like to the organizer:**
"XYZ Security Services, Atlanta GA — Estimated 835 employees. Workforce is approximately 75% security guards ($18/hr median), 5% supervisors, 10% admin, 3% management. In the Atlanta metro, security guards are predominantly Black men (62%), median age 37, with a high school diploma. Industry union density: 12%. Annual turnover: estimated 100%+."

That transforms an abstract employer record into a picture of actual human beings with real working conditions.

### Phase 4: The Calibration Engine (what makes it get smarter)

This is Gemini's "if you build only one thing" recommendation, and all three reports independently validate it.

**What you're building:** A system that continuously measures how accurate each estimation method is, broken down by industry and region, and automatically applies correction factors.

**How it works (in plain language):**

You have ~50,000+ NLRB election records with real employee counts at specific workplaces. That's your answer key. For each of those workplaces, you can also run all your other estimation methods and see how close they get.

Over time, you learn things like:
- "LinkedIn undercounts warehouse employees by a factor of 8 in the Southeast"
- "Revenue-per-employee ratios overestimate headcount by 20% for fast-food chains"
- "OSHA inspection notes are within 10% of actual headcount for manufacturing plants"
- "Job posting math overestimates by 15% across all industries" (probably due to ghost postings)

These learned correction factors get applied automatically to new estimates. When a new security company with no NLRB history shows up, the system says: "Based on how our methods perform for other security companies in this region, we estimate 600-850 employees with medium confidence."

**The domain adaptation problem (Gemini's warning):**
Your NLRB ground truth is concentrated in industries with high union activity — healthcare, manufacturing, education, hospitality, public sector. It's thinner in tech, finance, and professional services. The calibration engine needs to be honest about where it has good calibration data and where it's extrapolating. The confidence ranges should widen automatically for industries where you have few NLRB benchmarks.

**What this looks like technically:**
A table that stores: `{naics_2digit: "56", region: "south_atlantic", method: "linkedin_corrected", bias: -0.62, rmse: 0.34, n_calibration_points: 47, last_updated: "2026-01-15"}`

The system looks up the relevant correction factors whenever it produces an estimate, applies them, and reports the calibrated range.

### Phase 5: Data Ingestion Priorities (what new data to bring in)

Based on all three reports' recommendations, ranked by impact-to-effort ratio:

| Priority | Data Source | What It Adds | Effort |
|----------|-----------|-------------|--------|
| **1** | QCEW bulk data (via BLS) | Industry/county employment benchmarks | Medium — bulk download, schema mapping |
| **2** | CBP/SUSB (via Census API) | Establishment size priors | Low — API wrapper exists (`census` package) |
| **3** | O*NET bulk download | Working conditions, job characteristics | Very low — clean CSV files, 2-3 hours |
| **4** | LEHD/LODES WAC files | Block-level employment counts for validation | Medium — spatial join to establishment addresses |
| **5** | SEC human capital extraction | Structured headcount from 10-K narratives | Medium-high — NLP extraction needed |
| **6** | ACS PUMS demographic data | Occupation × metro demographic distributions | Medium — pre-computation for top 50 MSAs |
| **7** | Job postings (employer career pages) | Composition clues, growth/decline signals | High — requires scraping infrastructure |
| **8** | EEO-1 public release data | Workforce demographics by job category | Unknown — depends on when data is released |

### Phase 6: Open Source Tools to Integrate

Combining all three reports' tool recommendations, filtered for maintenance status:

**Definitely integrate (actively maintained, high value):**
- **Splink** — entity resolution across all your datasets
- **edgartools** — SEC filing parsing for employee counts and human capital text
- **libpostal** — address normalization (critical for establishment matching)
- **RapidFuzz** — fast fuzzy string matching for candidate generation
- **census** (Python wrapper) — programmatic Census API access for CBP/ACS/PUMS

**Likely integrate (good value, moderate effort):**
- **usaddress** — US-specific address parsing for messier address fields
- **cleanco** — company name cleaning (strip "Inc/LLC/Corp")
- **Scrapy** — backbone for building your own employer career page scraper
- **SkillNER** — skill extraction from job postings
- **sockit** — SOC classification from job titles

**Use as reference/research only (stale or archived):**
- **Industry2Vec** — archived since 2020, useful conceptually but fork before depending on it
- **skill2vec** — likely stale, but the dataset could seed your embedding layer
- **Company2Vec** — unknown maintenance, useful for "find similar companies" feature

**Avoid or use cautiously:**
- **JobSpy** — operationally brittle, TOS risk. Use for research, not production
- **pyBLS** — thinly maintained. Use `requests` directly against BLS API v2 instead

---

## Part 6: What Has to Be Built From Scratch

All three reports converge on several gaps that no existing open-source tool fills:

### 1. The Calibration Engine (highest priority)

**What:** A system that takes your NLRB ground truth, measures how each estimation method performs by industry and region, learns correction factors, and applies them automatically.

**Why no one's built it:** Commercial providers (Revelio Labs, PDL) have their own proprietary calibration, but it's not open source. And nobody else has the NLRB ground truth you have.

**Why it matters:** This is what turns your platform from "a collection of data sources" into "a measurement system that gets smarter over time."

### 2. The SEC Human Capital Extractor

**What:** A tool that reads the "Human Capital" section of a 10-K filing and extracts structured data: total employees, FT/PT split, unionization percentage, contractor mentions, turnover data.

**Why no one's built it:** The SEC disclosure rule is principles-based (companies decide what to say), so every filing is different. Extracting comparable numbers requires NLP that understands the many ways companies phrase this information.

**Why it matters:** ~3,700 public companies file 10-Ks. Extracting structured workforce data from all of them gives you the best headcount anchor for every major employer.

### 3. The Corporate Hierarchy Graph

**What:** A system that maps parent companies to subsidiaries to individual workplaces. "Walmart Inc. owns Sam's Club, which operates a warehouse at 123 Main St in Bentonville, AR."

**Why no one's built it:** SEC Exhibit 21 lists subsidiaries, but it's often a flat text file that's hard to parse. Connecting those subsidiaries to physical workplaces requires matching across multiple databases.

**Why it matters:** Organizers need to know who they're really dealing with. The company name on the OSHA violation might be a subsidiary that's hard to connect to the parent corporation without this graph.

### 4. The Estimation Assembler

**What:** The glue layer that takes an employer, runs all available estimation methods, combines them with learned weights, and produces the final output with confidence ranges.

**Why no one's built it:** This is exactly Claude's observation: "every piece of the pipeline exists as an open-source component; no one has assembled them." Your platform would be the first to do this for labor market analysis.

---

## Part 7: How This Fits Your Current Roadmap

Your UNIFIED_ROADMAP_2026_02_17.md already plans for workforce composition as a post-launch expansion feature. Here's how this model plan maps to your existing phases:

**Phase A (F-7 orphan fix) → directly enables Phase 1 here.** Fixing the 50.4% broken employer links is literally the entity resolution work that the estimation model requires.

**Phase B (matching pipeline improvements) → directly enables Phase 1-2 here.** Better matching = better entity resolution = better estimation.

**Wave 1 (post-launch enrichment) → maps to Phase 2-3 here.** Your roadmap already plans to "expose the BLS occupation matrix on employer profiles" — that's exactly Phase 3 Step 1 of this plan.

**Wave 2 (expand coverage) → maps to Phase 4-5 here.** Revenue-to-headcount estimation and ACS PUMS demographic overlay are already on your roadmap.

The main thing this model plan adds to the roadmap is **the calibration engine (Phase 4)** and the explicit **multi-method layering logic (Phase 2)**. These aren't currently in the roadmap but would dramatically increase the value of the workforce composition features you're already planning.

---

## Summary: The Three Things That Matter Most

If you take nothing else from this three-report comparison, remember these three points that every report independently validated:

1. **Your NLRB data is irreplaceable.** No commercial provider has establishment-level ground truth like this. Build the calibration engine around it.

2. **Layer multiple methods, weight by confidence.** No single method is reliable alone. But three independent estimates with different blind spots, combined with learned correction factors, produce genuinely useful numbers.

3. **Get entity resolution right first.** Nothing else works until you can reliably say "these records across five databases all refer to the same employer." This is already your Phase A priority — and it's the right priority.
