# Self-Improving Research Agent — Implementation Plan

**Date:** February 23, 2026
**Project:** Labor Relations Research Platform
**Purpose:** Build a system that automatically researches companies and gets smarter with every run

---

## WHAT THIS DOCUMENT IS

This is a step-by-step plan for building a research agent that:
1. Takes a company name and automatically gathers intelligence about it
2. Logs everything it does — which sources it checked, what it found, what was a dead end
3. Before each NEW research run, checks its logs to see what worked for similar companies
4. Over time, becomes faster and more accurate because it learns from experience

This plan identifies every place where you need to make a decision, what the options are, and what conditions would make each option work best.

---

## HOW THIS CONNECTS TO WHAT YOU ALREADY HAVE

You are NOT starting from scratch. Your platform already has enormous assets that this system builds on top of:

**Data sources already wired up:**
- OSHA violations (1M+ establishments, 2.2M violations)
- NLRB elections and cases (33K elections, 477K cases)
- DOL Wage & Hour violations (363K cases)
- SEC EDGAR filings (517K companies)
- SAM.gov federal contractors (826K entities)
- IRS Form 990 nonprofits (586K filers)
- Mergent business data (56K employers)
- BLS occupation/industry data (67K+ staffing patterns)
- GLEIF corporate ownership (379K US entities)

**Infrastructure already built:**
- Entity matching at 96.2% accuracy across sources
- PostgreSQL database with 207+ tables
- FastAPI backend with 144 working endpoints
- Crawl4AI already set up for web scraping
- A Claude "union-research" skill that generates employer research documents
- A Deep Dive tool already designed (not yet built) in the platform spec

**The research agent is essentially the Deep Dive tool + a learning layer on top.**

---

## THE FOUR PHASES

### Overview

| Phase | What It Does | Time | What You Get |
|-------|-------------|------|-------------|
| **Phase 1** | Build the research agent that can investigate a company | 4-6 weeks | Working "Run Deep Dive" button that produces a report |
| **Phase 2** | Add the strategy memory so it remembers what worked | 2-3 weeks | Agent checks past results before each run, skips dead ends |
| **Phase 3** | Add automatic scoring so it can grade its own work | 3-4 weeks | Agent knows which runs were good vs. bad, updates its strategies |
| **Phase 4** | Add query refinement so it learns HOW to search, not just WHERE | 4-6 weeks | Agent experiments with search strategies and keeps what works |

Each phase produces something useful on its own. You don't need Phase 4 to get value from Phase 1.

---

## PHASE 1: BUILD THE RESEARCH AGENT

### What This Phase Produces

An organizer clicks "Run Deep Dive" on an employer profile. The system:
1. Pulls government data from your existing database (fast — seconds)
2. Sends Claude a list of "tools" it can use (web search, OSHA lookup, NLRB lookup, etc.)
3. Claude decides which tools to use, in what order, based on what it knows about the company
4. Results get saved to the employer profile
5. EVERYTHING gets logged — what Claude tried, what it found, how long it took

### The Key Concept: "Tool Use"

This is the most important technical concept to understand, so let me explain it carefully.

When you chat with Claude in this window, you type questions and Claude types answers. But Claude can also be given "tools" — basically buttons it can push to go get information. When Claude has tools, instead of just answering from memory, it can say "let me go check" and actually look things up.

For your research agent, the "tools" would be things like:
- "Search OSHA for violations at this company"
- "Search NLRB for union elections involving this company"
- "Search the web for recent news about this company"
- "Look up this company's SEC filings"
- "Check if this company has federal contracts"

You define these tools, and Claude decides which ones to use and in what order. This is different from a simple script that always checks every source in the same order — Claude can reason about which sources are most likely to have useful information for THIS specific company.

For example, if Claude knows the company is a small private restaurant chain, it might skip SEC (only public companies file there) and prioritize OSHA (restaurants have lots of safety violations) and DOL Wage & Hour (restaurants have lots of wage theft). If the company is a large publicly traded hospital chain, Claude might start with SEC filings (to get financials) and CMS data (Medicare/Medicaid participation).

### What You Need to Build

#### 1A. The Tool Definitions

Each "tool" is a function that goes and gets information from one of your data sources. Most of these are just wrappers around database queries you already have.

**Internal tools (your existing database):**

| Tool Name | What It Does | Data Source |
|-----------|-------------|-------------|
| `search_osha` | Finds OSHA violations for this employer | `osha_establishments` + `osha_violations_detail` tables |
| `search_nlrb` | Finds NLRB elections and ULP charges | `nlrb_elections` + `nlrb_cases` tables |
| `search_whd` | Finds wage theft / DOL enforcement actions | `whd_cases` table |
| `search_sec` | Finds SEC filings (revenue, employees, executives) | `sec_companies` table |
| `search_sam` | Checks federal contractor status | `sam_entities` table |
| `search_990` | Finds nonprofit financial filings | `national_990_filers` + `employers_990_deduped` tables |
| `search_contracts` | Finds existing union contracts | `f7_union_employer_relations` table |
| `get_industry_profile` | Gets BLS occupation/wage data for this industry | `bls_industry_occupation_matrix` table |
| `get_similar_employers` | Finds comparable employers | `industry_occupation_overlap` table |
| `search_mergent` | Gets business intelligence (revenue, employees, parent company) | `mergent_employers` table |

**External tools (web-based, require API calls):**

| Tool Name | What It Does | Source |
|-----------|-------------|--------|
| `search_web` | General web search for company info | Web search API |
| `search_news` | Recent news articles about this company | Web search with date filter |
| `scrape_employer_website` | Reads the company's own website (About, Careers pages) | Crawl4AI |
| `search_job_postings` | Finds current job postings (signals about workforce) | Indeed MCP or Adzuna API |

> **🔴 DECISION POINT 1: Which external search API to use**
>
> Your tools need a way to search the web. Options:
>
> | Option | Cost | Quality | Complexity |
> |--------|------|---------|------------|
> | **Claude's built-in web search** | Included with Claude API | Good for general queries | Lowest — no extra setup |
> | **Tavily** | $0.001/search (1000 free/month) | Optimized for AI agents | Low — simple API |
> | **Exa.ai** | $0.001/search (1000 free/month) | Best for "find pages similar to X" | Low — simple API |
> | **SerpAPI** | $50/month for 5000 searches | Google results directly | Low — simple API |
>
> **My recommendation:** Start with Claude's built-in web search (zero additional cost, zero additional setup). Switch to Tavily or Exa later if the search quality isn't good enough. You can always swap this out — the rest of the system doesn't care which search engine is behind the "search_web" tool.
>
> **What makes this successful:** You're only doing a few hundred deep dives total, not thousands. At that volume, even the paid options are cheap (under $10/month). The decision is really about simplicity vs. search quality.

#### 1B. The "Dossier" — What the Report Looks Like

Before you build the agent, you need to define exactly what a finished research report contains. This is critical because without a clear target, the agent can't know when it's "done" or how well it did.

Your Deep Dive spec already defines most of this. Here's the complete structure:

**Section 1: Company Identity**
- Legal name, DBA names, parent company
- Industry (NAICS code and description)
- Headquarters address, major locations
- Public/private/nonprofit/government
- Website URL

**Section 2: Financial Profile**
- Revenue (or revenue range)
- Number of employees (or estimate)
- Recent financial trends (growing/shrinking)
- Executive compensation (if public)
- Government contracts (amount, agencies)

**Section 3: Workforce Intelligence**
- Estimated workforce composition (job types, from BLS data)
- Demographic profile of typical workers in this industry/area (from ACS data)
- Job posting activity (hiring signals, turnover signals)
- Pay ranges for key positions

**Section 4: Labor Relations History**
- Existing union contracts (from F-7 data)
- NLRB election history (wins, losses, dates)
- Unfair labor practice charges (filed by whom, outcomes)
- Any recent organizing activity (from news)

**Section 5: Workplace Issues**
- OSHA violations (types, severity, penalties)
- Wage & Hour violations (amounts, types)
- Safety incidents and accidents
- Worker complaints or lawsuits (from news)

**Section 6: Organizing Assessment**
- AI-generated summary of organizing potential
- Key strengths for a campaign (e.g., "chronic safety violations suggest worker dissatisfaction")
- Key challenges (e.g., "company has successfully fought 3 prior organizing attempts")
- Similar employers that have been organized

**Section 7: Sources & Confidence**
- Every fact linked to its source
- Confidence rating for each section (High/Medium/Low/No Data)
- Date each source was checked
- What was NOT found (important for knowing where gaps are)

> **🔴 DECISION POINT 2: How detailed should the dossier be?**
>
> You have two options:
>
> **Option A: Full dossier (all 7 sections).** More comprehensive, but takes longer to run (estimated 2-4 minutes per company) and costs more in API calls. Best if deep dives are rare (< 50 per month).
>
> **Option B: Tiered dossier.** Quick scan first (Sections 1-2, database only, 10 seconds). Full dive only on request (adds Sections 3-7, includes web research, 2-4 minutes). Best if users want to quickly screen companies before investing in full research.
>
> **My recommendation:** Option B (tiered). Your spec already has this — Step 1 (government data) runs fast and Step 2 (web research) runs in background. The tiered approach means users get instant value while the deeper research loads.
>
> **What makes this successful:** The dossier structure needs to be stored in your database in a way that's consistent across all companies. Every fact should have: the value, the source it came from, the date it was found, and a confidence rating. This consistency is what enables the learning in Phase 2.

#### 1C. The Logging System

This is the foundation that everything else builds on. Without good logs, the system can never learn.

**What gets logged for every single research run:**

**Run-level log (one row per deep dive):**
- Which company was researched
- Company characteristics (industry NAICS, public/private, size, state)
- When the run started and ended
- How many tools were called total
- How many sections of the dossier were successfully filled
- Total cost (API tokens used)
- Who triggered it (which user)

**Action-level log (one row per tool call within a run):**
- Which tool was called (e.g., "search_osha")
- What parameters were used (e.g., company name, NAICS code)
- Whether the tool found useful data (yes/no)
- How useful the data was (quality score, 0.0 to 1.0)
- How long the tool call took
- How much it cost (for API-based tools)
- What order it was called in (was this the 1st tool, 5th tool, etc.)
- What company characteristics were known at the time

**Fact-level log (one row per piece of information extracted):**
- The fact itself (e.g., "revenue = $45M")
- Which section of the dossier it belongs to
- Which tool found it
- Source URL or database table
- Confidence rating
- Whether it agrees with or contradicts other facts

**Database tables for this:**

```
research_runs
├── id (unique identifier for each run)
├── employer_id (links to your f7_employers_deduped table)
├── company_name
├── industry_naics
├── company_type (public/private/nonprofit/government)
├── company_state
├── started_at
├── completed_at
├── total_tools_called
├── total_facts_found
├── sections_filled (how many of the 7 dossier sections got data)
├── total_cost_cents
├── triggered_by (user ID)
├── overall_quality_score (filled in later, during Phase 3)
└── strategy_used (which strategy was recommended, for Phase 2)

research_actions
├── id
├── run_id (links to research_runs)
├── tool_name (e.g., "search_osha")
├── tool_params (what was searched for — stored as JSON)
├── execution_order (1st call, 2nd call, etc.)
├── data_found (true/false)
├── data_quality (0.0 to 1.0)
├── facts_extracted (how many facts came from this tool call)
├── latency_ms (how long it took)
├── cost_cents (how much it cost)
├── error_message (if something went wrong)
└── created_at

research_facts
├── id
├── run_id (links to research_runs)
├── action_id (links to research_actions — which tool found this)
├── employer_id
├── dossier_section (identity/financial/workforce/labor/workplace/assessment)
├── attribute_name (e.g., "revenue", "employee_count", "osha_violations")
├── attribute_value (the actual data)
├── source_url (where it came from)
├── source_type (database/web/scrape)
├── confidence (0.0 to 1.0)
├── as_of_date (when this fact was true — e.g., "2024 fiscal year")
├── contradicts_fact_id (if this conflicts with another fact, link to it)
└── created_at
```

> **🔴 DECISION POINT 3: Where does the research agent run?**
>
> The agent needs to make API calls to Claude, run database queries, and potentially scrape websites. Where does this code actually execute?
>
> **Option A: Inside your existing FastAPI server.** The agent is just another API endpoint. When a user clicks "Run Deep Dive," it starts a background task on your server that makes Claude API calls and runs the research.
>
> - Pro: Everything is in one place, easy to manage
> - Con: Long-running tasks (2-4 minutes) tie up your server
> - Best if: You have a small number of concurrent users (< 10)
>
> **Option B: Separate worker process with a task queue.** The FastAPI server puts the request into a queue (like Celery + Redis). A separate worker process picks it up and runs the research. The frontend polls for updates.
>
> - Pro: Doesn't slow down the main server, can run multiple deep dives at once
> - Con: More complex to set up (need Redis, Celery, worker management)
> - Best if: You expect multiple users running deep dives simultaneously
>
> **Option C: Run it manually from the command line first.** Build the agent as a Python script you run yourself. No web integration yet. Focus on getting the research quality right.
>
> - Pro: Simplest to build, fastest to iterate on
> - Con: Not integrated into the platform, only you can use it
> - Best if: You want to get the agent working and collect training data before investing in web integration
>
> **My recommendation:** Start with Option C, then move to Option A. Build the agent as a standalone script, run it on 20-30 companies manually, look at the results, tune the prompts and tools. Once you're happy with the quality, wire it into the FastAPI server as a background task. You designed the Deep Dive to be async (background job with progress indicator) anyway, so Option A with async tasks is the natural fit.
>
> **What makes this successful:** The agent will need a Claude API key (separate from your chat usage). The API charges per token — a typical research run might use 10,000-50,000 tokens, costing roughly $0.10-$0.50 per run depending on how many tools are called. At 500 runs that's $50-$250 total, well within budget for the value you get.

#### 1D. The Agent Prompt

This is the instruction set that tells Claude how to conduct the research. It's essentially the "playbook" — the detailed instructions that a research director would give a new analyst on their first day.

The prompt would include:
- The dossier template (what information to find)
- The list of available tools and when to use each one
- Instructions for how to handle different types of companies (public vs. private, large vs. small, etc.)
- Quality standards (always cite sources, note confidence levels, flag contradictions)
- Budget awareness (don't call expensive tools when cheap ones will do)

> **🔴 DECISION POINT 4: How much autonomy should Claude have?**
>
> **Option A: High autonomy.** Give Claude the dossier template and tools, and let it decide the strategy entirely. "Research this company. Here are your tools. Fill in as much of the dossier as you can."
>
> - Pro: Claude can adapt to unusual companies, might find creative approaches
> - Con: Harder to predict costs, might go down rabbit holes, less consistent results
>
> **Option B: Guided autonomy.** Give Claude a recommended order of operations, but let it skip or reorder based on what it learns. "Start with database lookups, then check SEC/OSHA/NLRB, then do web research. Skip sources that won't apply to this company type."
>
> - Pro: More predictable, easier to debug, still flexible
> - Con: Might miss opportunities that a fully autonomous agent would find
>
> **Option C: Scripted with escape hatch.** Fixed order for the first pass, but if key sections are still empty, let Claude do a second "creative" pass with full autonomy to fill gaps.
>
> - Pro: Most predictable costs and timing, guaranteed coverage of basics
> - Con: Two-pass approach takes longer
>
> **My recommendation:** Option B (guided autonomy). This gives Claude the intelligence to make good decisions while keeping the process predictable enough to learn from. The prompt would say something like: "Here's the recommended research order based on past experience. Follow this order unless you have a specific reason to deviate. If you skip a step, explain why."
>
> **What makes this successful:** The prompt needs to be very explicit about what "useful data" looks like. Vague instructions produce vague results. For example, instead of "find financial information," say "find annual revenue (exact figure or range), number of employees, and whether the company is growing or shrinking — cite a specific source for each."

### Phase 1 Success Conditions

You know Phase 1 is working when:
- You can give it any company name and get a structured dossier back
- The dossier consistently fills in at least 4 of 7 sections for well-known companies
- Every fact has a source citation
- Every tool call is logged with timing and outcome data
- You have run it on at least 20-30 companies across different industries
- The results are good enough that an organizer would find them useful

### Phase 1 Estimated Effort

| Task | Hours | Notes |
|------|-------|-------|
| Define and build internal tools (database wrappers) | 10-15 | Most queries already exist in your API |
| Define and build external tools (web search, scraping) | 8-12 | Crawl4AI is already set up |
| Create the logging database tables | 3-4 | Straightforward schema creation |
| Write the agent prompt | 4-6 | The most important creative work |
| Build the agent orchestration code | 8-12 | Claude API + tool use loop |
| Test on 20-30 companies and iterate | 10-15 | Manual review and prompt tuning |
| **Total** | **43-64 hours** | **~4-6 weeks at 10-12 hrs/week** |

---

## PHASE 2: ADD THE STRATEGY MEMORY

### What This Phase Produces

Before each research run, the agent checks: "For companies like this one (same industry, same type, same size), which tools have historically produced the most useful data?" Then it prioritizes those tools and deprioritizes or skips tools that have a poor track record for this type of company.

### How This Works in Plain English

Imagine after Phase 1 you've run deep dives on 50 companies. Your logs show:

For **manufacturing companies**:
- OSHA found useful data 94% of the time (almost always have violations)
- WHD (wage theft) found data 71% of the time
- SEC found data only 23% of the time (most are private)
- Job postings found data 45% of the time

For **hospitals/healthcare**:
- OSHA found useful data 87% of the time
- 990 filings found data 68% of the time (many are nonprofits)
- SEC found data 42% of the time
- NLRB found data 31% of the time

The strategy memory turns these patterns into recommendations. Before researching a new manufacturing company, Claude gets told: "Based on 50 past research runs, here are the most productive sources for manufacturing companies, ranked by success rate..." This means Claude wastes less time on low-yield sources and gets to the good stuff faster.

### What You Need to Build

#### 2A. The Strategy Table

This is a summary table that aggregates all the action-level logs from Phase 1 into easy-to-query success rates.

```
research_strategies
├── id
├── industry_naics_2digit (e.g., "62" for healthcare, "31-33" for manufacturing)
├── company_type (public/private/nonprofit/government)
├── company_size_bucket (small < 100 employees / medium 100-1000 / large > 1000)
├── tool_name (e.g., "search_osha")
├── times_tried (how many runs used this tool for this type of company)
├── times_found_data (how many times it actually returned useful info)
├── hit_rate (times_found_data / times_tried — the key metric)
├── avg_quality (average quality score when it DID find data)
├── avg_latency_ms (how long it typically takes)
├── avg_cost_cents (how much it typically costs)
├── recommended_order (suggested position in the research sequence)
└── last_updated
```

This table gets rebuilt/updated after every research run. It's essentially a leaderboard of "which tools work best for which types of companies."

#### 2B. The Strategy Injection

Before each run, the system:
1. Looks up the company's industry, type, and size
2. Queries the strategy table for matching records
3. Ranks the tools by hit_rate × avg_quality (best ones first)
4. Formats this as a recommendation list
5. Adds it to Claude's prompt as context

The prompt addition would look something like:

```
Based on 47 previous research runs on similar healthcare/nonprofit companies:

HIGHLY RECOMMENDED (>80% hit rate):
1. search_osha — 87% hit rate, avg quality 0.78
2. search_990 — 82% hit rate, avg quality 0.71
3. search_web — 80% hit rate, avg quality 0.65

RECOMMENDED (50-80% hit rate):
4. search_nlrb — 64% hit rate, avg quality 0.72
5. search_whd — 58% hit rate, avg quality 0.69
6. search_job_postings — 52% hit rate, avg quality 0.55

LOW PRIORITY (<50% hit rate):
7. search_sec — 31% hit rate, avg quality 0.82 (high quality when found, but rarely applicable)
8. search_sam — 18% hit rate, avg quality 0.45

Prioritize highly recommended tools first. Skip low priority tools
unless you have specific reason to believe they'll be productive
(e.g., skip SEC unless you know the company is publicly traded).
```

> **🔴 DECISION POINT 5: How should the system handle companies it's never seen a type of before?**
>
> What happens when you research a company in an industry you've never researched before? The strategy table has no data for that industry.
>
> **Option A: Fall back to overall averages.** Use the success rates across ALL industries when industry-specific data isn't available.
>
> **Option B: Fall back to the closest related industry.** If you've never researched NAICS 722 (restaurants), but you have data for NAICS 72 (hospitality broadly), use that.
>
> **Option C: Use no recommendations.** Let Claude use its own judgment with no strategy guidance. This is essentially what Phase 1 does.
>
> **My recommendation:** Option B with Option A as a backup. Try to find the closest industry match first (using the 2-digit NAICS prefix), and if that's not available either, fall back to overall averages. This way you always have some guidance, but it's as specific as possible.
>
> **What makes this successful:** You need at least 3-5 research runs per industry/company-type combination before the strategy recommendations become meaningful. With fewer than that, the data is too noisy — one bad run could make a great source look terrible. The strategy table should have a minimum threshold (e.g., "only show recommendations based on 3+ runs").

#### 2C. The Feedback Loop

After each run completes, automatically update the strategy table:

1. Look at every tool that was called during this run
2. For each tool, check: did it find useful data? What quality score?
3. Update the strategy table: increment `times_tried`, update `hit_rate`, recalculate `avg_quality`

This happens automatically — no human intervention needed. The strategy table is always current.

### Phase 2 Success Conditions

You know Phase 2 is working when:
- The agent's tool selection visibly changes based on company type (it checks different sources for a hospital vs. a factory)
- Research runs for well-studied company types (industries you've researched many times) are faster than for new industries
- The strategy table shows clear patterns (some tools have much higher hit rates for certain industries)
- There's a measurable improvement in dossier completeness compared to Phase 1 (more sections filled, on average)

### Phase 2 Estimated Effort

| Task | Hours | Notes |
|------|-------|-------|
| Create the strategy summary table | 2-3 | SQL + rebuild script |
| Build the strategy query function | 3-4 | Query + formatting for Claude's prompt |
| Modify the agent prompt to include strategy context | 2-3 | Prompt engineering |
| Build the automatic strategy updater | 4-6 | Post-run processing |
| Build a strategy dashboard (view hit rates by industry) | 4-6 | Simple web page or report |
| Test and validate on 20+ runs | 6-8 | Compare with/without strategy |
| **Total** | **21-30 hours** | **~2-3 weeks at 10-12 hrs/week** |

---

## PHASE 3: ADD AUTOMATIC SCORING

### What This Phase Produces

Right now (after Phases 1-2), the system can log what it did and recommend good strategies, but it doesn't really know how WELL it did. Quality scores are assigned manually or estimated loosely. Phase 3 adds a proper evaluation system that automatically grades each research run.

### Why This Matters

Without automatic scoring, the strategy memory (Phase 2) can learn the wrong lessons. Example: maybe "search_web" always returns SOMETHING (high hit rate), but the information is often outdated or inaccurate (low actual quality). Without scoring, the system would keep recommending web search as a top source because it "finds data" — even though the data isn't very good.

Automatic scoring fixes this by asking: "Not just did you find data, but was the data ACTUALLY useful, accurate, and complete?"

### How It Works

After each research run completes, a separate Claude call acts as a "grader." It reads the completed dossier and evaluates it:

**Coverage score (0-10):** How many of the 7 dossier sections were filled in?
- 7/7 sections = 10
- 5/7 sections = 7
- 3/7 sections = 4
- 1/7 sections = 1

**Source quality score (0-10):** How credible are the sources?
- Government databases (OSHA, NLRB, SEC) = highest
- Company's own website = medium-high
- News articles from major outlets = medium
- Random web pages = low
- No source cited = zero

**Consistency score (0-10):** Do the facts agree with each other?
- Revenue from SEC matches revenue from Mergent = high
- Employee count from one source wildly contradicts another = low
- Financial data says company is growing but job postings show mass layoffs = flag it

**Freshness score (0-10):** How recent is the information?
- Data from last 12 months = highest
- Data from 1-3 years ago = medium
- Data from 5+ years ago = low

**Efficiency score (0-10):** How much effort did it take?
- Found everything quickly and cheaply = high
- Called many tools that returned nothing = low
- Spent a lot of time/money on low-value sources = low

**Overall score:** Weighted combination of the above.

> **🔴 DECISION POINT 6: How should you weight the scoring factors?**
>
> Different weights produce different agent behaviors. This is a values question — what matters most to your users?
>
> **Weight Option A: Coverage-first**
> `overall = 0.40 × coverage + 0.25 × source_quality + 0.15 × consistency + 0.10 × freshness + 0.10 × efficiency`
> Makes the agent prioritize filling in every section, even if it has to use lower-quality sources. Best if organizers need a complete picture and can evaluate source quality themselves.
>
> **Weight Option B: Quality-first**
> `overall = 0.20 × coverage + 0.35 × source_quality + 0.20 × consistency + 0.15 × freshness + 0.10 × efficiency`
> Makes the agent prioritize having fewer but more reliable facts. Best if organizers make high-stakes decisions based on the reports and can't afford to act on bad data.
>
> **Weight Option C: Balanced**
> `overall = 0.25 × coverage + 0.25 × source_quality + 0.20 × consistency + 0.15 × freshness + 0.15 × efficiency`
> Middle ground. Best as a starting point — you can adjust later based on user feedback.
>
> **My recommendation:** Start with Option C (balanced), then adjust based on actual user feedback. Ask your beta testers: "What was more frustrating — reports that were incomplete, or reports that had inaccurate information?" If they say incomplete, shift toward Coverage-first. If they say inaccurate, shift toward Quality-first.
>
> **What makes this successful:** The scoring needs to be automated enough that you're not manually grading every run, but you should manually review a sample (maybe 1 in 10 runs) to make sure the automatic grading matches your judgment. If the auto-grader consistently rates a mediocre report as "excellent," you need to tune the grading prompt.

### The Grading Process

After a research run completes:

1. The system collects the full dossier and all action logs
2. It sends this to Claude with a grading prompt: "You are a quality evaluator. Review this research report and score it on coverage, source quality, consistency, freshness, and efficiency. Return scores 0-10 for each with brief explanations."
3. Claude returns the scores
4. The scores get saved to `research_runs.overall_quality_score`
5. The scores flow back into the strategy table — tools that contributed to high-scoring runs get their `avg_quality` boosted

**Important:** The grading call uses a cheaper, faster model (Claude Sonnet instead of Opus). The grading doesn't need to be brilliant — it just needs to be consistent.

> **🔴 DECISION POINT 7: Should humans also grade some runs?**
>
> **Option A: Fully automatic grading.** Claude grades everything. You never review.
> - Risk: The grader might have blind spots you never discover
>
> **Option B: Automatic grading + periodic human audit.** Claude grades everything, but you manually review and re-grade 10% of runs. Compare your grades to Claude's grades. If they diverge, tune the grading prompt.
> - Best practice: Build a simple review page where you can see Claude's grades and override them
>
> **Option C: Human grading only.** You grade every run yourself.
> - Not scalable past 50-100 runs
>
> **My recommendation:** Option B. The human audits are how you catch grading errors before they compound. But you only need to do this for the first 100 or so runs — once you're confident the auto-grader is well-calibrated, you can reduce the audit rate.

### Building a "Gold Standard" Set

To validate that the whole system is working, you need a small set of companies where you KNOW what the right answer is. This is called a "gold standard" or "ground truth" dataset.

Pick 10-15 companies across different industries and sizes where you personally know a lot about them (or can easily verify). For each one:
- Write what the "perfect" dossier would contain
- Note which sources should have data
- Document any tricky aspects (company changed names, has subsidiaries, etc.)

Then run the agent on these companies and compare the output to your gold standard. This tells you:
- Is the agent finding what it should? (coverage)
- Is the agent reporting accurate information? (quality)
- Is the agent checking the right sources? (strategy)

> **🔴 DECISION POINT 8: How big does the gold standard set need to be?**
>
> **Minimum viable:** 10 companies (2 per major industry type). Enough to spot major problems.
>
> **Ideal:** 25-30 companies covering your most important industries, both large and small, public and private. This gives you statistical confidence.
>
> **Over-engineered:** 100+ companies with detailed scoring rubrics. This is what a commercial ML team would do, but it's overkill for your use case right now.
>
> **My recommendation:** Start with 15 companies. You probably already have strong knowledge about many employers from your existing platform work. Pick companies where you can easily verify the facts.

### Phase 3 Success Conditions

You know Phase 3 is working when:
- Every research run gets an automatic quality score
- The scores are consistent (similar-quality reports get similar scores)
- Your manual spot-checks mostly agree with the auto-grader (within 1-2 points on a 10-point scale)
- The strategy memory is now weighted by quality, not just hit rate — good sources rise, mediocre sources drop
- You can see a trend: average quality scores improve over the first 100 runs as the strategy memory gets smarter

### Phase 3 Estimated Effort

| Task | Hours | Notes |
|------|-------|-------|
| Design the scoring rubric and weights | 3-4 | Deciding what "good" means |
| Write the auto-grading prompt | 3-4 | Prompt engineering for the evaluator |
| Build the grading pipeline (post-run evaluation) | 4-6 | Code to run the grader and save scores |
| Connect scores back to strategy table updates | 3-4 | Weight strategies by quality, not just hit rate |
| Build gold standard set (15 companies) | 8-12 | Research + documentation |
| Build human audit interface | 4-6 | Simple page to review and override grades |
| Calibrate auto-grader against human grades | 4-6 | Compare, adjust prompt, repeat |
| **Total** | **29-42 hours** | **~3-4 weeks at 10-12 hrs/week** |

---

## PHASE 4: QUERY REFINEMENT

### What This Phase Produces

Phases 1-3 teach the system WHICH sources to check. Phase 4 teaches it HOW to search each source.

For example, the system might learn:
- "For restaurant chains, searching OSHA by NAICS code 722 finds 3x more violations than searching by company name" (because restaurants often operate under DBA names that don't match the parent company)
- "For companies with common names like 'National Services Inc', adding the state to the search reduces false matches by 80%"
- "When searching news, the query 'company + workers + complaints' finds more relevant results than 'company + union'" (because not all labor issues are union-related)

### How This Works

**Query Templates:** Instead of just saying "search OSHA," the tool stores multiple ways to search OSHA:

| Template | Example | When It Works Best |
|----------|---------|-------------------|
| Search by exact company name | "Walmart Inc" | Large companies with unique names |
| Search by name + state | "National Services + NY" | Companies with common names |
| Search by NAICS code + city | "722 + Chicago" | Finding industry peers, catching DBAs |
| Search by parent company name | "Kindred Healthcare" | When you know the corporate parent |

**Learning which templates work:** Each template gets its own hit rate and quality score, broken down by company characteristics. Over time, the system learns which search approach works best for which situation.

**Template mutation:** This is an advanced technique where the system tries small variations on successful templates:
- Original: "company name + OSHA violation"
- Mutation 1: "company name + OSHA citation"
- Mutation 2: "company name + workplace safety fine"

If a mutation performs better than the original, it gets promoted.

> **🔴 DECISION POINT 9: How far to go with query refinement?**
>
> **Option A: Template selection only.** Build a library of 3-5 query templates per tool. The system learns which template to use based on company characteristics. No mutation/experimentation.
> - Simpler, more predictable
> - Good enough for most use cases
>
> **Option B: Template selection + mutation.** The system can also create and test new query variations automatically.
> - More powerful long-term
> - Requires more runs to validate (each mutation needs to be tried several times)
> - Risk of generating weird/useless queries that waste time
>
> **My recommendation:** Start with Option A. Query templates are powerful and predictable. Only move to Option B if you notice that your existing templates are consistently failing for certain types of companies and you think better query formulations could solve it.

### Phase 4 Success Conditions

- The agent uses different search queries for different types of companies
- Hit rates improve measurably over Phase 2 (finding data in sources that Phase 2 was missing)
- The system can explain WHY it chose a particular search approach (transparency)
- Research run time decreases because the system gets to useful results faster

### Phase 4 Estimated Effort

| Task | Hours | Notes |
|------|-------|-------|
| Build query template library (3-5 templates per tool) | 8-12 | Requires understanding each source's search behavior |
| Add template tracking to the logging system | 3-4 | Record which template was used per action |
| Build template selection logic | 4-6 | Choose template based on company characteristics |
| Connect to strategy table (template-level hit rates) | 4-6 | More granular than tool-level tracking |
| Test and validate across 30+ runs | 8-12 | Compare template selection to fixed templates |
| (Optional) Add template mutation | 10-15 | Only if Option B is chosen |
| **Total** | **27-40 hours** | **~4-6 weeks at 10-12 hrs/week** |

---

## OVERALL TIMELINE AND DEPENDENCIES

```
Phase 1: Build the Agent (weeks 1-6)
    ↓
Phase 2: Strategy Memory (weeks 7-9)
    ↓ (needs 30+ logged runs from Phase 1)
Phase 3: Auto Scoring (weeks 9-13)
    ↓ (needs 50+ logged runs, strategy memory working)
Phase 4: Query Refinement (weeks 13-19)
    ↓ (needs 100+ logged runs, scoring working)
```

**Total estimated effort: 120-176 hours over 4-5 months**

**Key dependency:** Each phase needs data from the previous phase. Phase 2 needs logged runs. Phase 3 needs strategies to evaluate. Phase 4 needs scores to optimize. You can't skip ahead.

**Most important thing:** Run the agent on real companies as early as possible, even if it's not perfect. Every run generates data that makes future phases better.

---

## CONDITIONS FOR SUCCESS

These are the things that will make or break this project:

### 1. The Claude API Key and Budget

You need an Anthropic API account separate from your chat usage. Estimated costs:
- Phase 1 testing (30 runs): ~$15-$50
- Phase 2 testing (30 runs): ~$10-$30
- Phase 3 calibration (50 runs): ~$25-$75
- Phase 4 experiments (50 runs): ~$25-$75
- Ongoing usage (200 runs/month): ~$100-$300/month

Total R&D cost: ~$75-$230 for development. This is very cheap for what you get.

### 2. Consistent Dossier Structure

The dossier format MUST be the same for every company. If you keep changing what information you want, the learning system can't compare across runs. Lock down the dossier structure before Phase 1 and commit to it for at least 100 runs.

### 3. Industry Diversity in Early Runs

If you only test on healthcare companies in Phase 1, the strategy memory will only know about healthcare. Deliberately spread your early runs across at least 5-6 different industries to build broad knowledge. A good mix: healthcare, manufacturing, hospitality/food service, building services/security, transportation, retail.

### 4. Honest Evaluation

The auto-grader (Phase 3) will only work if you're honest in your calibration. If you rate a mediocre report as "great" because you're in a hurry, the system learns to produce mediocre work. The gold standard set and human audits are your quality control.

### 5. Patience with Early Results

The first 20-30 runs will not be impressive. The agent won't know what it's doing yet. That's fine — those runs are building the data that makes runs 50-200 dramatically better. Don't give up because the early outputs are rough.

### 6. Data Quality in Your Existing Database

The research agent is only as good as the data sources it can access. The audit found some issues (50.4% orphaned F-7 relationships, broken corporate endpoints, etc.) that should ideally be fixed before or during Phase 1 development. The agent will produce better results if the underlying data is clean.

---

## DECISION SUMMARY

All decisions in one place for easy reference:

| # | Decision | My Recommendation | When to Decide |
|---|----------|-------------------|----------------|
| 1 | Which web search API? | Claude's built-in, upgrade later if needed | Before Phase 1 |
| 2 | Full dossier or tiered? | Tiered (quick scan first, full dive on request) | Before Phase 1 |
| 3 | Where does the agent run? | Command line first, then FastAPI background task | Before Phase 1 |
| 4 | How much autonomy for Claude? | Guided autonomy (recommended order, can deviate) | Before Phase 1 |
| 5 | Handling unknown industries? | Fall back to closest NAICS match, then overall averages | Before Phase 2 |
| 6 | How to weight scoring? | Balanced (0.25/0.25/0.20/0.15/0.15), adjust later | Before Phase 3 |
| 7 | Should humans also grade? | Yes, audit 10% of runs to calibrate the auto-grader | Before Phase 3 |
| 8 | Gold standard set size? | 15 companies across key industries | Before Phase 3 |
| 9 | How far with query refinement? | Template selection only, no mutation (for now) | Before Phase 4 |

---

## WHAT TO DO NEXT

If you want to start building this:

1. **Decide on Decision Points 1-4** (all are needed before Phase 1 can begin)
2. **Get a Claude API key** if you don't already have one
3. **Pick 5-6 employers you know well** as initial test cases
4. **I'll build the tool definitions and agent prompt** as the first concrete deliverable

The natural starting point is writing the tool definitions — turning your existing database queries into the "menu" that Claude can choose from. That's the foundation everything else builds on.
