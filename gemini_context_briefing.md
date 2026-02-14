# Gemini Research Briefing — Labor Relations Research Platform
## Paste this at the start of any Gemini session where you need research help

---

## What This Project Is

I'm building a research platform that brings together data from many U.S. government databases to help unions make better decisions about where to organize workers. The platform connects employers, unions, safety records, election results, wage theft cases, and government contracts into a single searchable system.

**Why this matters:** Right now, if a union wants to research a company before launching an organizing campaign, they have to search 10+ different government websites manually. My platform does that automatically and scores companies based on how good a target they might be for organizing.

---

## The Government Data Sources We Use

These are the agencies and databases the platform pulls from. When I ask you to research something, it'll usually relate to one of these:

### Currently Integrated (Already in our database)

| Source | Agency | What It Contains | Why We Use It |
|--------|--------|-----------------|---------------|
| **OLMS LM Filings** | Dept. of Labor | Union financial reports — income, spending, membership counts | Core source: tells us which unions exist and how big they are |
| **F-7 Employer Bargaining Notices** | Dept. of Labor | Employers with active union contracts | Tells us which companies already have unions |
| **NLRB Election Records** | Natl. Labor Relations Board | Union election results — who won, vote counts | Shows where workers tried to organize and whether they succeeded |
| **OSHA Enforcement Data** | Dept. of Labor | Workplace safety inspections and violations | Bad safety = unhappy workers = organizing opportunity |
| **WHD WHISARD** | Dept. of Labor | Wage theft cases — stolen wages, child labor | Another indicator of worker mistreatment |
| **BLS Employment Data** | Bureau of Labor Statistics | Industry employment counts, union density rates | Benchmarks — tells us the "normal" level of unionization by industry |
| **EPI State Data** | Economic Policy Institute | State-level union membership estimates | Validates our state-by-state counts |
| **GLEIF/Open Ownership** | Global LEI Foundation | Corporate ownership chains using LEI identifiers | Helps map who owns who in corporate families |
| **SEC EDGAR** | Securities & Exchange Commission | Public company filings, CIK/EIN identifiers | Connects publicly traded companies to our employer list |
| **USASpending** | Treasury/GSA | Federal contracts and grants | Identifies employers getting taxpayer money (organizing leverage) |
| **SAM.gov** | GSA | Federal contractor registration | More contractor identification |
| **QCEW** | Bureau of Labor Statistics | Quarterly employment counts by industry and county | Local-level industry employment data |
| **IRS Form 990** | IRS | Nonprofit financial data | Identifies nonprofit employers and their budgets |
| **Mergent Intellect** | Commercial (Dun & Bradstreet) | Private company data — employees, revenue, DUNS numbers | Fills gaps for non-public companies |

### Exploring / Not Yet Integrated

| Source | What We'd Get | Status |
|--------|--------------|--------|
| **FLRA Bargaining Units** | Federal employee union data (separate from private sector) | Partially integrated |
| **State labor boards** | State-level union filings (not covered by federal NLRB) | Research phase |
| **Prevailing wage databases** | Davis-Bacon wage determinations by area | Exploring as organizing intelligence |
| **Census NAICS files** | Official industry classification codes | Used for reference |

---

## Key Concepts You Should Know

### How U.S. Labor Law Splits Into Different Systems

This is important because different types of workers are covered by completely different laws and databases:

- **Private sector workers** → Covered by the **NLRA** (National Labor Relations Act) → Data from **NLRB** (elections) and **OLMS** (union filings)
- **Federal employees** → Covered by the **FSLMRA** (Federal Service Labor-Management Relations Act) → Data from **FLRA** (Federal Labor Relations Authority)
- **State/local public employees** → Covered by **state laws** (varies wildly by state) → Data from individual **state labor boards**
- **Railroad and airline workers** → Covered by the **RLA** (Railway Labor Act) → Data from **NMB** (National Mediation Board)

**Why this matters:** When I ask "does database X cover federal employees?", the answer is usually "no, that's a completely different legal system." Don't assume one database covers everything.

### Union Hierarchy (Why Membership Numbers Get Complicated)

Unions are organized in layers:
- **International/National union** (e.g., SEIU, AFSCME, UAW) — the parent organization
- **Intermediate bodies** (districts, regions, councils) — administrative middle layer
- **Local unions** — the actual workplace-level unit

The problem: Each level files separate financial reports with OLMS, and they all report their membership. So if SEIU International says "2 million members" and then 500 SEIU locals each report their members too, you can't just add those numbers up — you'd be counting the same people multiple times. Our platform solves this by deduplicating (removing double-counts) using a hierarchy tree.

### Employer Matching Across Databases

The same company might appear differently in each database:
- OSHA: "WALMART SUPERCENTER #4523"
- NLRB: "WAL-MART STORES, INC."  
- F-7 filings: "Walmart Associates Inc"
- SEC: "Walmart Inc" (CIK: 0000104169)

We use a combination of text matching (comparing how similar names look), geographic checks (same city and state?), and unique identifiers (EIN, DUNS, CIK) to link these together. Current match rates: OSHA 13.7%, WHD 6.8%, IRS 990 2.4%. Improving these rates (via SEC EDGAR full index, IRS BMF data) is a key goal.

---

## Current Platform Numbers

| What | Count |
|------|-------|
| Total union members tracked | 14.5 million (validated against BLS benchmark of 14.3M) |
| Unions in database | 26,665 |
| Employers (private sector, current + historical) | ~113,700 |
| Employers (all sources combined) | ~120,000 |
| OSHA workplaces | 1,007,217 |
| Safety violations | 2,245,020 ($3.52B in penalties) |
| Wage theft cases | 363,365 ($4.7B in stolen wages) |
| Union elections | 33,096 |
| API endpoints | 142+ (across 16 routers) |
| Database tables | 207 |
| Automated tests | 63 (47 API + 16 auth) |

---

## What I Need From You (Gemini)

Your job is **research assistant and fact-checker**. Specifically:

### 1. Verify Claims About Government Data
When Claude (my primary AI) tells me something about how a government database works, I may ask you to confirm it. Example: "Claude says SEC EDGAR organizes companies by CIK number. Is that right? What other identifiers does EDGAR use?"

### 2. Research New Data Sources  
When I'm considering adding a new data source, I need you to help me understand what's actually in it. Example: "What data fields does the FLRA maintain about federal bargaining units? Can it be downloaded in bulk?"

### 3. Explain Government Processes
Help me understand the bureaucratic context behind the data. Example: "When exactly does an F-7 notice get filed? What triggers it? How often is it updated?"

### 4. Compare Approaches
When there are multiple ways to do something, help me think through the options. Example: "What are the pros and cons of matching employers by EIN vs. DUNS number vs. name matching?"

### 5. Summarize Long Documents
I'll sometimes paste or link to lengthy government reports, regulations, or research papers. Example: "Summarize the key points of this NLRB annual report that relate to election processing times."

### 6. Cross-Check Statistics
If I have numbers that seem off, help me investigate. Example: "BLS says 14.3M union members nationally, but when I add up the states I get 14.8M. What could explain the gap?"

---

## Important Ground Rules

- **Be specific about what you don't know.** If you're not sure about a data format or a government process, say so rather than guessing. Incorrect information about government databases leads to broken code.
- **Distinguish between what WAS true and what IS true.** Government systems change. Tell me if your knowledge might be outdated and I should verify directly.
- **When I ask about a government API or bulk download**, try to point me to the actual URL or documentation page, not just a general description.
- **Don't suggest building things.** That's Claude's job. Your job is to give me accurate information so Claude can build the right thing.

---

## Recent Platform Improvements (February 2026)

For context on questions about current platform capabilities:

1. **Orphan fix** — 60,000 orphaned union-employer relations resolved by adding 52,760 historical employers. The `f7_employers_deduped` table now has 113,713 rows (61K current + 53K historical, tracked via `is_historical` flag).
2. **Organizing scorecard** — Now a materialized view (`mv_organizing_scorecard`) with 9 scoring factors computed in SQL. Score range 10-78, average 32.3. Replaces earlier on-the-fly Python scoring.
3. **JWT authentication** — Added to the API (disabled by default, enabled via environment variable).
4. **API decomposition** — Monolith split into 16 focused routers. 63 automated tests passing.
5. **Match rates remain low** — OSHA 13.7%, WHD 6.8%, 990 2.4%. Key data gaps: SEC EDGAR full index (300K+ companies), IRS BMF (all nonprofits), SEC 10-K Exhibit 21 (subsidiary lists).

*Last updated: February 14, 2026 (after Sprint 3 completion)*
*Context: This briefing was written so you can effectively research and fact-check without needing our full technical history.*
