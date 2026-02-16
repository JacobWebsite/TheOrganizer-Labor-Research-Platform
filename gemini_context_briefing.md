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

### Exploring / Not Yet Integrated (Phase 4 Targets)

| Source | What We'd Get | Status |
|--------|--------------|--------|
| **SEC EDGAR Full Index** | 300K+ companies with CIK/EIN for matching | Phase 4 priority |
| **IRS Business Master File** | ~1.8M tax-exempt orgs, bulk download | Phase 4 priority |
| **CPS Microdata (IPUMS)** | Union membership variables, geographic granularity | Phase 4 planned |
| **OEWS Staffing Patterns** | Occupation-by-industry matrix | Phase 4 planned |
| **FLRA Bargaining Units** | Federal employee union data | Partially integrated |
| **State labor boards** | State-level union filings (NY PERB, CA PERB, IL ILRB) | Phase 7 research |
| **FMCS Contract Data** | Contract expiration dates (#1 timing signal) | Not yet explored |

---

## Key Concepts You Should Know

### How U.S. Labor Law Splits Into Different Systems

This is important because different types of workers are covered by completely different laws and databases:

- **Private sector workers** -> Covered by the **NLRA** (National Labor Relations Act) -> Data from **NLRB** (elections) and **OLMS** (union filings)
- **Federal employees** -> Covered by the **FSLMRA** (Federal Service Labor-Management Relations Act) -> Data from **FLRA** (Federal Labor Relations Authority)
- **State/local public employees** -> Covered by **state laws** (varies wildly by state) -> Data from individual **state labor boards**
- **Railroad and airline workers** -> Covered by the **RLA** (Railway Labor Act) -> Data from **NMB** (National Mediation Board)

**Why this matters:** When I ask "does database X cover federal employees?", the answer is usually "no, that's a completely different legal system." Don't assume one database covers everything.

### Union Hierarchy (Why Membership Numbers Get Complicated)

Unions are organized in layers:
- **International/National union** (e.g., SEIU, AFSCME, UAW) — the parent organization
- **Intermediate bodies** (districts, regions, councils) — administrative middle layer
- **Local unions** — the actual workplace-level unit

The problem: Each level files separate financial reports with OLMS, and they all report their membership. So if SEIU International says "2 million members" and then 500 SEIU locals each report their members too, you can't just add those numbers up — you'd be counting the same people multiple times. Our platform solves this by deduplicating using a hierarchy tree.

### Employer Matching Across Databases

The same company might appear differently in each database:
- OSHA: "WALMART SUPERCENTER #4523"
- NLRB: "WAL-MART STORES, INC."
- F-7 filings: "Walmart Associates Inc"
- SEC: "Walmart Inc" (CIK: 0000104169)

We use a combination of text matching (trigram similarity), geographic checks (same city and state?), and unique identifiers (EIN, DUNS, CIK) to link these together.

**Current match rates (F7 employer perspective):** OSHA 28.0%, WHD 9.7%, 990 6.7%, SAM 10.2%, NLRB 8.2%. Overall: 42.6% of F7 employers matched to at least one source.

**Matching pipeline (Phase 3 — COMPLETE):**
- Canonical name normalization (3 levels: standard, aggressive, fuzzy/phonetic)
- Deterministic matcher v3 (6-tier cascade, batch-optimized)
- Probabilistic matching via Splink
- Unified match log (258K entries with confidence scoring)
- Employer canonical grouping (16,179 groups deduplicating 40K+ rows)

---

## Current Platform Numbers (updated Feb 15, 2026)

| What | Count |
|------|-------|
| Total union members tracked | 14.5 million (validated against BLS benchmark of 14.3M) |
| Unions in database | 26,665 |
| Employers (current, non-historical) | ~67,552 |
| Employers (historical, expired contracts) | ~79,311 |
| Employers (total in f7_employers_deduped) | 146,863 |
| Employer canonical groups | 16,179 (covering 40,304 grouped employers) |
| Signatory entries excluded | 170 (e.g., "All Signatories to SAG-AFTRA...") |
| OSHA workplaces | 1,007,217 |
| Safety violations | 2,245,020 ($3.52B in penalties) |
| Wage theft cases | 363,365 ($4.7B in stolen wages) |
| Union elections | 33,096 |
| Unified match log entries | ~258,000 (253K active + 5K rejected) |
| Organizing scorecard rows | 22,389 (**union shops excluded**) |
| API endpoints | 152+ (across 17 routers) |
| Database tables | ~161 |
| Views | 186 |
| Materialized views | 4 |
| Database size | ~20 GB |
| Automated tests | 240 passing |

---

## What I Need From You (Gemini)

Your job is **research assistant, fact-checker, and architecture reviewer**. Specifically:

### 1. Verify Claims About Government Data
When Claude (my primary AI) tells me something about how a government database works, I may ask you to confirm it.

### 2. Research New Data Sources
When I'm considering adding a new data source, I need you to help me understand what's actually in it.

### 3. Explain Government Processes
Help me understand the bureaucratic context behind the data.

### 4. Compare Approaches
When there are multiple ways to do something, help me think through the options.

### 5. Summarize Long Documents
I'll sometimes paste or link to lengthy government reports, regulations, or research papers.

### 6. Cross-Check Statistics
If I have numbers that seem off, help me investigate.

### 7. Architecture Review
Evaluate major platform changes: file organization, state management, API design, trade-offs.

---

## Important Ground Rules

- **Be specific about what you don't know.** If you're not sure about a data format or a government process, say so rather than guessing.
- **Distinguish between what WAS true and what IS true.** Government systems change. Tell me if your knowledge might be outdated.
- **When I ask about a government API or bulk download**, try to point me to the actual URL or documentation page.
- **Don't suggest building things.** That's Claude's job. Your job is to give me accurate information so Claude can build the right thing.
- **Be pragmatic in architecture reviews.** This is an internal research tool, not a SaaS product. Over-engineering is worse than under-engineering.

---

## Completed Work (Phases 1-3 DONE)

### Phase 1: Fix Broken (COMPLETE)
- 6 density endpoint crashes fixed
- 29 literal-string password bugs fixed (migrated to `db_config.get_connection()`)
- Auth enforced by default
- NAICS backfill, ANALYZE, README rewrite

### Phase 2: Frontend Cleanup (COMPLETE)
- 10,506-line monolith split into 2,300 line HTML + 21 JS files + CSS
- Unified scoring system (8 factors in `SCORE_FACTORS` config)
- modals.js split into 8 modal files
- 68 inline onclick handlers migrated to `data-action` event delegation
- 5 app modes: territory, search, deepdive, uniondive, admin
- Confidence/freshness indicators, metrics glossary

### Phase 3: Matching Overhaul (COMPLETE)
- Unified match log (258K entries) with confidence scoring
- Canonical name normalization (3 levels + phonetic)
- Deterministic matcher v3 (6-tier cascade, 868K OSHA in ~20s)
- Splink probabilistic matching (Mergent, GLEIF, F7 self-dedup)
- Match quality dashboard + API endpoints
- NLRB bridge view (13K rows linking elections to employers)
- Historical employer resolution (5,128 merge candidates)
- **Employer canonical grouping** — 16,179 groups deduplicating 40K+ employer rows
- **Scorecard misclassification fix** — union shops (2,452 establishments) removed from organizing scorecard; `score_company_unions` factor eliminated; 170 signatory entries excluded

### Key Fix: Scorecard No Longer Shows Union Shops as Targets
The organizing scorecard (`mv_organizing_scorecard`) previously included 2,395 establishments matched to F7 employers — meaning already-unionized workplaces were being scored and displayed as organizing targets. The old `score_company_unions` factor actually gave these 20 bonus points. This has been fixed:
- Union shops filtered out via `WHERE fm.establishment_id IS NULL`
- Scorecard: 24,841 -> 22,389 rows
- Score factors: 9 -> 8 (company_unions removed, max score 80 instead of 100)
- 170 "signatory" entries (e.g., "All Signatories to SAG-AFTRA...") excluded from counts

---

## Current Roadmap (TRUE Roadmap — February 15, 2026)

**Source document:** `Roadmap_TRUE_02_15.md`

| Phase | Status | Weeks |
|-------|--------|-------|
| 1: Fix Broken | **COMPLETE** | Week 1 |
| 2: Frontend Cleanup | **COMPLETE** | Weeks 2-4 |
| 3: Matching Overhaul | **COMPLETE** | Weeks 3-7 |
| 4: New Data Sources | **NEXT** | Weeks 8-10 |
| 5: Scoring Evolution | Planned | Weeks 10-12 |
| 6: Deployment Prep | Planned | Weeks 11-14 |
| 7: Intelligence | Planned | Week 14+ |

**Phase 4 research needs (where Gemini's help is critical):**
- **SEC EDGAR full index** — confirm bulk access patterns via `edgartools`, EIN availability in XBRL filings, CIK-to-company mapping completeness
- **IRS Business Master File** — confirm coverage (~1.8M tax-exempt orgs), available fields, bulk download vs API (ProPublica vs IRS direct)
- **CPS microdata via IPUMS (`ipumspy`)** — confirm union membership variables, geographic granularity, academic registration requirements
- **OEWS staffing patterns** — confirm occupation-by-industry matrix availability, geographic levels, update frequency

**Phase 5:** Research logistic regression approaches for organizing propensity scoring. What AUC thresholds are meaningful? How have similar models been built in political/social organizing?

**Phase 7:** Research state PERB data availability — NY PERB, CA PERB, IL ILRB. What data do they publish? Any APIs or bulk downloads?

**Critical path:** P1 -> P3 -> P4 -> P5 Advanced. P6 independent after P1.

**Key owner decisions:**
1. 14-week timeline (thorough) over 6-week (rushed)
2. Frontend cleanup EARLY — organizers need trust in what they see
3. New data sources WAIT until matching is standardized (Phase 3 now done)
4. Scoring model planned but doesn't block release
5. Deployment planned but not urgent
6. Start with 4 screens, architect for 5-area expansion later

---

## Architecture Review History

**Sprint 6 review** (`docs/review_gemini.md`):

**Accepted:**
- Plain scripts over ES modules was the correct pragmatic call
- Don't put score explanations in the materialized view
- Cache-until-reload is acceptable for a research tool

**Rejected (with rationale):**
- Split modals.js into 11 files — more script tags + load-order complexity for no functional benefit
- Split detail.js into renderer files — same reasoning
- Global Decimal->float conversion — only 2 occurrences, not worth an abstraction

When reviewing future work, check `docs/review_gemini.md` for the response table format we use.

---

## Audit Conflict Resolutions (Reference for Future Fact-Checking)

- OSHA match rate: 28.0% (all F7 employers) and 47.3% (current only) — both correct, different denominators
- WHD/990 matching: IMPROVED via Phase 3 deterministic matcher
- NAICS coverage: 37.7% is the real number for scoring
- NLRB participant "orphans" (92.34%): structurally expected — participants table includes ALL case types
- GLEIF storage: 396 MB useful + 12 GB raw. Archive the raw.
- F7 `unit_size` is bargaining unit size, not actual employee count — sometimes misleading

---

*Last updated: February 15, 2026 (Phase 3 complete, scorecard misclassification fixed)*
*Context: This briefing was written so you can effectively research, fact-check, and review architecture without needing our full technical history.*
