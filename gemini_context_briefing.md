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
| Automated tests | 162 (30 API + 16 auth + 24 data integrity + 51 matching + 39 scoring) |

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

### Sprints 1-4 (Complete)
1. **Orphan fix (Sprint 1)** — 60,000 orphaned union-employer relations resolved by adding 52,760 historical employers. The `f7_employers_deduped` table now has 113,713 rows (61K current + 53K historical, tracked via `is_historical` flag).
2. **JWT authentication (Sprint 2)** — Added to the API (disabled by default, enabled via `LABOR_JWT_SECRET` env var). CORS restricted.
3. **Organizing scorecard (Sprint 3)** — Now a materialized view (`mv_organizing_scorecard`) with 9 scoring factors computed in SQL. Score range 10-78, average 32.3.
4. **Test coverage (Sprint 4)** — 162 automated tests (matching pipeline + scoring engine + data integrity).

### Sprint 6 (Complete) — Frontend & Score Explanations
5. **Frontend split** — 10,506-line monolith HTML split into 2,139 lines markup + CSS + 10 JS files. Uses plain `<script>` tags (not ES modules) because 103 inline `onclick=` handlers require global functions.
6. **Score explanations** — API now returns `score_explanations` dict with plain-language reasons for each of the 9 scoring factors (e.g., "150 employees -- in the 50-250 organizing sweet spot").
7. **F7 public-sector banner** — UI now documents that F7 data only covers private-sector employers. Public-sector unions (5.4M members) are tracked through separate state PERB systems.

### Known Data Quality Issues
8. **Match rates remain low** — OSHA 13.7%, WHD 6.8%, 990 2.4%. Key data gaps: SEC EDGAR full index (300K+ companies), IRS BMF (all nonprofits), SEC 10-K Exhibit 21 (subsidiary lists).
9. **F7 employer duplicates** — Multi-employer agreements (e.g., SAG-AFTRA with 5+ filings for different contract types) create duplicate rows in search results, all showing the same ~165K workers. F7 `unit_size` is bargaining unit size, not actual employer employees.
10. **No FMCS data** — Contract expiration dates (#1 timing signal for organizing) not yet integrated.
11. **No national ULP data** — Unfair labor practice tracking limited to NYC tables.

## Architecture Review History

**Sprint 6 review** (`docs/review_gemini.md`): You reviewed the frontend split architecture. Key decisions:

**Accepted:**
- Plain scripts over ES modules was the correct pragmatic call
- Don't put score explanations in the materialized view
- Cache-until-reload is acceptable for a research tool

**Rejected (with rationale):**
- Split modals.js into 11 files — more script tags + load-order complexity for no functional benefit
- Split detail.js into renderer files — same reasoning
- Global Decimal->float conversion — only 2 occurrences, not worth an abstraction
- HTML templates loaded via fetch — over-engineering for internal tool
- Raw data columns in MV for explanations — adds MV complexity for marginal benefit

When reviewing future sprints, check `docs/review_gemini.md` for the response table format we use.

---

## What I Also Need From You (Gemini) — Expanded Role

In addition to research and fact-checking, you now serve as **architecture reviewer** for major platform changes. When I send you code for review:

1. **Evaluate architectural decisions** — Was the right approach chosen? What are the trade-offs?
2. **Assess file organization** — Are concerns well-separated? Any files too large or too fragmented?
3. **State management** — Is state handled cleanly? Any risk of stale data or race conditions?
4. **API design** — Are endpoints well-structured? Do response shapes make sense for the frontend?
5. **Suggest improvements** — But be pragmatic. This is an internal research tool, not a SaaS product. Over-engineering is worse than under-engineering.

*Last updated: February 14, 2026 (after Sprint 6 completion + review fixes)*
*Context: This briefing was written so you can effectively research, fact-check, and review architecture without needing our full technical history.*
