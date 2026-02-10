# Making the Organizing Scorecard Smarter — A Plain-Language Roadmap

**Date:** February 8, 2026  
**Status:** Planning  
**Related:** `docs/METHODOLOGY_SUMMARY_v8.md`, `LABOR_PLATFORM_ROADMAP_v11.md`

---

## What the Scorecard Does Now (and Why It's Limited)

Right now, your scorecard looks at a non-union employer and asks six separate questions:

1. **How big is the workplace?** (more workers = more potential members)
2. **How unionized is this industry?** (if 16% of trucking is union, a non-union trucking company is a natural target)
3. **Are other employers nearby winning NLRB elections?** (organizing momentum in the area)
4. **Does this employer have OSHA safety violations?** (angry workers = receptive workers)
5. **Does this employer have government contracts?** (leverage — they need to look good)
6. **Has this employer committed wage theft or other labor violations?** (more anger, more leverage)

Each question gets a number, you add them up, and the total is the score. An employer scoring 45 is a better target than one scoring 12.

**The limitation:** Each factor is scored independently. The scorecard doesn't ask the most powerful question an organizer actually asks: *"Which non-union employer looks the most like an employer that already has a union?"*

That's what this roadmap is about — moving from a checklist to a comparison engine.

---

## The Three Big Ideas (In Plain English)

### Idea 1: "How Similar Are These Two Employers?" (Gower Distance)

Right now, when you compare two employers by industry, it's binary — either they share the same NAICS code or they don't. A hospital and a nursing home are "different industries" even though they employ many of the same kinds of workers.

**Gower Distance** is a math formula that asks: "Across ALL the things I know about these two employers — their industry, their size, their state, their violation history, whether they have government contracts — how similar are they overall?" It spits out a number between 0 (completely different) and 1 (basically twins).

**Why it matters for organizing:** Instead of scoring each employer in isolation, you could say "This non-union nursing home in Queens with 200 employees and 3 OSHA violations is 87% similar to this unionized nursing home in Brooklyn with 180 employees and 4 OSHA violations that SEIU already represents." That's a much more compelling case than "this employer scored 35 out of 62."

**Why it works with messy data:** The biggest practical advantage is that Gower handles missing information gracefully. If you don't know an employer's revenue but you know everything else, it just skips that factor and compares on everything it does have. With government data, you're *always* missing something — so this matters a lot.

**What it takes to implement:** One Python library (`gower`), and your existing database tables. You'd feed it a spreadsheet-like table where each row is an employer and each column is a characteristic. It does the rest.

### Idea 2: "What's the Probability This Employer Should Be Union?" (Propensity Score)

This is the most powerful idea, and it's conceptually simple:

You have thousands of employers where you *know* whether they're unionized (from F-7 filings, NLRB election wins, etc.). You also know things about those employers — their industry, size, location, violation history. A statistical model can learn the pattern: "Employers that look like THIS tend to be unionized."

Then you apply that pattern to non-union employers. The model says: "Based on everything I know about this employer, there's a 78% chance it 'should' be unionized — meaning it looks almost identical to employers that are." That 78% *is* the organizing score.

**Why it matters:** It replaces your hand-picked weights (size gets 5 points, industry density gets 10 points, etc.) with weights the *data* picks. Maybe OSHA violations matter way more than you thought. Maybe employer size matters less. The model figures this out from the actual patterns in your 63,000+ employer database.

**The catch:** This only works well if you have enough examples of both unionized AND non-unionized employers with similar characteristics. Your database is heavily weighted toward *unionized* employers (that's what F-7 filings track). You'd need a good reference set of non-union employers too — which is where your Mergent data (14,240 employers, most non-union) and OSHA establishments (1 million+) come in.

### Idea 3: "Is This the Same Employer Across Databases?" (Entity Resolution)

This isn't a scoring improvement — it's the plumbing that makes everything else reliable.

The same employer appears differently in every government database:

- OSHA: `WALMART INC`
- NLRB: `Wal-Mart Stores, Inc.`
- Wage theft records: `WAL MART STORES INC`
- Your F-7 data: `WALMART INC.`

Your matching module already handles this with a 5-tier pipeline (EIN match → normalized name → address → aggressive name → fuzzy). The research document suggests a tool called **Splink** that does this probabilistically — instead of "match or no match," it says "92% chance these are the same entity."

**You've already built a lot of this.** Your matching module runs 9 scenarios and achieves strong results (96.2% F-7 to OLMS, 44.6% OSHA to F-7). The question is whether switching to or supplementing with Splink would push those rates higher, especially for the harder matches.

---

## What Would Actually Change for an Organizer?

Today, an organizer using your platform sees:

> **ABC Healthcare Corp** — Score: 28/62 (HIGH priority)
> - Size: 3/5
> - Industry density: 7/10
> - NLRB momentum: 5/10
> - OSHA violations: 2/4
> - Government contracts: 8/15
> - Labor violations: 3/10

With the improvements, they'd see something more like:

> **ABC Healthcare Corp** — Organizing Opportunity: 78%
> - **Most similar unionized employers:** 1199SEIU at XYZ Hospital (91% match), AFSCME at DEF Nursing Home (87% match), SEIU at GHI Home Care (84% match)
> - **Why this employer looks organizable:** Same size range, same industry, same geography, similar violation profile as employers that are already union
> - **Key leverage points:** 3 OSHA violations (2× industry average), $45K in back wages owed, $12M in NYC contracts
> - **Risk factors:** 450 employees (larger units are harder to win), employer is in a right-to-work state

The shift is from "here's a number" to "here's a story about why this employer is a natural target, backed by data about employers just like it."

---

## Roadmap: Three Options

### Option A: "Quick Wins" — Improve the Existing Scorecard (2-4 weeks)

This keeps your current structure but makes it smarter without rebuilding anything.

#### Step 1: Hierarchical NAICS Scoring (replaces binary match)

Right now, two employers either share a NAICS code or they don't. Instead:

| How closely they match | Score |
|---|---|
| Same 6-digit NAICS (exact same business type) | 10/10 |
| Same 5-digit (very close) | 8.5/10 |
| Same 4-digit (same industry group) | 6.5/10 |
| Same 3-digit (same subsector) | 4/10 |
| Same 2-digit (same broad sector) | 2/10 |
| Different sector entirely | 0/10 |

This means a general freight trucking company (484121) scores high against a specialized freight company (484122), medium against a school bus operator (485410), and zero against a software company. Right now they'd all score the same unless they share the exact code.

**Effort:** A few hours of SQL changes to the scoring logic.

#### Step 2: "Sibling Employer" Display

For each non-union target, find the 3-5 most similar *unionized* employers already in your database. Show them in the detail view: "Employers like this one that already have unions." This doesn't change the score — it just makes the existing score more meaningful by showing *who* the comparable employers are.

**Effort:** A new SQL query joining the target's characteristics against unionized employers, ranked by how many characteristics match. Maybe a day of work.

#### Step 3: OSHA Violation Normalization

Instead of raw violation counts (which penalizes big employers unfairly and lets small ones off easy), divide violations by industry average. An employer with 2× their industry's average violation rate is worse than one with 0.5×, regardless of raw numbers.

BLS publishes industry-average injury/illness rates by NAICS code for free. You'd download that reference table, join it to your OSHA data, and replace raw counts with "how much worse than average is this employer?"

**Effort:** Download one BLS dataset, create one reference table, modify the scoring SQL. A few hours.

#### Option A Total

~15-25 hours. No new tools or libraries needed.

---

### Option B: "Gower Distance Upgrade" — Add Similarity Scoring (1-2 months)

This adds the "how similar is this employer to unionized ones" capability on top of your existing scorecard.

#### Step 1: Build the Comparison Table

Create a single table where every employer (union and non-union) has the same set of columns:

| Column | Source | Type |
|---|---|---|
| NAICS 2-digit sector | F-7, OSHA, Mergent | Category |
| Employee count (binned) | F-7, Mergent, OSHA | Number |
| State | All sources | Category |
| Metro area (CBSA) | Your zip_geography table | Category |
| Industry union density | BLS/your density tables | Number (%) |
| OSHA violation rate | Your OSHA tables | Number |
| Has government contracts | Your contract tables | Yes/No |
| Has wage theft violations | Your WHD/NYC tables | Yes/No |
| Union status | F-7, NLRB wins | Yes/No (this is what you're comparing against) |

**Why this step matters:** Gower distance needs all employers described in the same format. Right now your data is spread across many tables with different schemas. This step is mostly SQL — creating a view or materialized view that pulls everything together.

#### Step 2: Run Gower Distance

A Python script reads the comparison table, runs Gower distance between every non-union employer and every unionized employer, and stores the results: "For non-union employer X, the 5 most similar unionized employers are A (92%), B (87%), C (84%), D (81%), E (79%)."

**What the weights mean:** You can tell Gower "industry matters 3× as much as state" by setting weights. Start with reasonable guesses, then adjust based on whether organizers find the results useful.

#### Step 3: Create a "Similarity Score"

For each non-union target, average the similarity to its 5 nearest unionized neighbors. That average becomes the similarity score (0-100). Add it to your existing scorecard as a new component, or display it alongside.

#### Step 4: Add to Frontend

In the employer detail view, add a "Similar Unionized Employers" section showing the top matches with their union affiliation, location, and similarity percentage.

#### Option B Total

~40-60 hours. Requires writing Python scripts and learning the `gower` library, but no fundamentally new infrastructure.

---

### Option C: "Full Statistical Model" — Propensity Score Approach (2-4 months)

This is the most powerful option but requires the most work and the most comfort with statistical concepts.

#### Step 1: Build a Training Dataset

You need a table of employers where you know the answer — union or not — along with their characteristics. Your database already has:

- **Union side:** 63,118 F-7 employers (definitely have unions), plus NLRB election winners
- **Non-union side:** This is the hard part. Your Mergent employers where `has_union = FALSE` (about 13,000), plus NLRB election *losers* (employers where a union tried and failed)

The model learns from both sides: "What makes union employers look different from non-union ones?"

#### Step 2: Train the Model

A logistic regression (the simplest statistical model for yes/no outcomes) takes in all the employer characteristics and outputs a probability. It automatically figures out which factors matter most and how much.

For example, it might learn:

- Being in the transportation industry increases union probability by 25%
- Each OSHA violation above industry average increases it by 3%
- Being in a right-to-work state decreases it by 15%
- Having government contracts increases it by 10%

You don't set these numbers — the model derives them from your data.

#### Step 3: Score All Non-Union Employers

Run every non-union employer through the model. Each gets a probability: "78% likely to be unionized based on its characteristics." Sort by probability. The top of the list is your best targets.

#### Step 4: Validate

The critical question: does the model actually predict organizing success, or just which employers *look like* they should be union? You'd want to check its predictions against recent NLRB election outcomes. If employers with high propensity scores actually win elections more often, the model is working.

**The honest challenge:** Your database is built around employers that *already* have unions. The model might just learn "employers in New York with 100-500 employees in healthcare tend to be union" — which is true but not necessarily actionable. You need enough non-union employer data (Mergent, OSHA establishments) to give the model contrast.

#### Option C Total

~80-120 hours. Requires comfort with Python's scikit-learn library, statistical thinking about what makes a good training set, and careful validation.

---

## Recommendation

**Start with Option A** (2-4 weeks). The hierarchical NAICS scoring and sibling employer display are low-risk improvements that make the scorecard immediately more useful without introducing new tools. You can do all of it in SQL and your existing API.

**Then pursue Option B** (month 2-3). The Gower distance calculation is the sweet spot — powerful enough to fundamentally change how the scorecard works, but simple enough that one Python script can do it. The results feed directly into your existing frontend.

**Defer Option C** until you have more non-union employer data. The propensity score model is the ultimate destination, but it needs a balanced training set. As you expand Mergent nationally and load WHD/QCEW data, you'll build the non-union reference set it requires.

---

## Dependencies and Prerequisites

| Option | Requires | Already Have |
|---|---|---|
| A | SQL changes to scoring views, BLS injury rate data | NAICS codes on employers, OSHA data, existing scorecard |
| B | Python `gower` library, unified employer comparison table | All underlying data tables, matching module |
| C | Python `scikit-learn`, balanced union/non-union training set | Union employer data (F-7); need more non-union data |

---

## Key Data Gaps to Fill (Any Option)

| Gap | Why It Matters | How to Fill |
|---|---|---|
| Non-union employer reference set | Can't compare without both sides | Expand Mergent nationally, load OSHA establishments as non-union baseline |
| National WHD wage violations | Only NYC scored currently | Load `whd_whisard.csv` (already downloaded, 363K records) |
| BLS injury/illness rates by NAICS | Needed for OSHA normalization | Free download from BLS SOII program |
| NAICS codes for 7,953 employers | Can't compare by industry without codes | Fill from OSHA matches, BLS QCEW |

---

*This document should be updated after each implementation phase with completed items, revised estimates, and lessons learned.*
