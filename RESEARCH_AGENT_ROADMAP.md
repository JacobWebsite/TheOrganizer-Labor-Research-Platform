# Research Agent Evolution Roadmap
## From Stateless Lookup Tool to Self-Improving Intelligence System

**Created:** 2026-03-01
**Context:** 118 runs completed, 44 distinct employers, 3,583 facts, 487 strategy entries, avg quality 7.88/10

---

## Current State Assessment

### What Works
- 25-tool orchestration (14 DB + 11 web/API) with async parallel execution
- 6-dimension auto-grading (coverage, source quality, consistency, actionability, freshness, efficiency)
- 86% publishable rate (102/118 runs score >= 7.0)
- Score enhancement pipeline feeds findings back into both scorecards
- Strategy table tracks tool hit rates by industry/type/size (487 entries across 10+ NAICS-2 codes)
- Query effectiveness tracking for web searches (24 templates, success rates 32-68%)
- ~5 cents avg cost per run

### What Doesn't Work
- **40 of 118 runs (34%) have NULL employer_id** — research can't connect to the employer it just investigated
- **All 41 score enhancements are `is_union_reference=TRUE`** — zero non-union targets have been enhanced (the MV JOIN bug from roadmap 0.5 may still be filtering these out)
- **No cross-run memory** — each run starts cold. Employer researched 7 times learns nothing from the first 6
- **No human feedback** — grading is purely structural. No one can say "this dossier was actually useful"
- **No outcome tracking** — no connection between research quality and organizing success
- **Strategy learning is tool-level only** — knows "search_mergent has 26% hit rate" but not "healthcare companies in the South tend to have OSHA clusters around ergonomic hazards"
- **Web scraping is slow and brittle** — scrape_employer_website averages 10.5 seconds, 58% hit rate

---

## Phase R0: Fix What's Broken (Days)
> *Prerequisite for everything else. No new features — make existing features actually work.*

### R0.1 — Fix employer_id auto-lookup
The agent should resolve company name to employer_id BEFORE creating the run, not after. 34% of runs are orphaned without this. The `employer_lookup.py` module exists and works — it's just not always called.

**Acceptance:** < 5% of new runs have NULL employer_id.

### R0.2 — Fix score enhancement path for non-union targets
All 41 enhancements are `is_union_reference=TRUE`. Either the batch runner is only selecting union employers, or the flag logic is wrong. Non-union target enhancements are the entire point of Path B research.

**Acceptance:** Running `batch_research.py --type non_union --limit 10` produces enhancements with `is_union_reference=FALSE`. Target scorecard reflects them.

### R0.3 — Fix the MV JOIN filter (Roadmap 0.5)
The view powering employer profiles filters `WHERE is_union_reference = false`, excluding all 41 existing enhancements. Either remove the filter or fix the data.

**Acceptance:** Research-enhanced employers show enriched data on their profile pages.

### R0.4 — Deduplicate repeat runs
One employer has 7 runs, three have 4 each. The system should detect existing runs for the same employer and either skip or explicitly supersede them, carrying forward confirmed facts.

**Acceptance:** `batch_research.py` skips employers with a completed run scored >= 7.0 in the last 30 days (configurable).

---

## Phase R1: Cross-Run Memory (1-2 Weeks)
> *Make each run aware of what's been learned before. The minimum viable "learning loop."*

### R1.1 — Employer research context table
Create `research_employer_context`:
```
employer_id (PK), company_name, last_researched, run_count,
confirmed_facts JSONB,    -- facts verified across 2+ runs
known_gaps TEXT[],         -- sections/attributes never found
quality_trajectory FLOAT[], -- quality scores over time
best_run_id UUID,         -- highest-quality run
key_findings_summary TEXT  -- AI-generated 3-sentence summary
```

Populated automatically after each completed run. Before starting a new run, load this context into the Gemini system prompt so it knows what's already confirmed and where to focus.

### R1.2 — Fact confirmation across runs
When the same fact (employer_id + attribute_name) appears in multiple runs with consistent values, mark it as `confirmed` in `research_facts` and bump its confidence. When values diverge across runs, flag as `contradicted` and surface in the dossier.

**Acceptance:** `research_facts` has a `confirmation_status` column (unconfirmed / confirmed / contradicted) and `confirmation_count`.

### R1.3 — Related employer injection
Before running research, query:
- `corporate_identifier_crosswalk` for parent/subsidiary relationships
- `employer_canonical_groups` for canonical group members
- Prior runs on related employers

Inject a "Related Employer Intelligence" section into the Gemini prompt: "Parent company X was researched on DATE — 3 OSHA violations, $2M revenue, union contract with SEIU."

**Acceptance:** Dossiers for subsidiaries reference parent company findings. Dossiers for group members reference sibling findings.

### R1.4 — Incremental research mode
Instead of re-running the full 25-tool suite, add a `--refresh` mode that:
1. Loads the best existing dossier
2. Identifies stale facts (> 6 months old) and known gaps
3. Runs only the tools needed to refresh stale data and fill gaps
4. Patches the existing dossier rather than building from scratch

**Acceptance:** `--refresh` runs are 40-60% cheaper and 50%+ faster than full runs while maintaining quality.

---

## Phase R2: Human Feedback Loop (1-2 Weeks)
> *Ground truth from actual users. The system can't improve without knowing what "good" means.*

### R2.1 — Feedback collection schema and API
Create `research_feedback`:
```
id SERIAL PK, run_id UUID FK, user_id INT FK,
rating INT (1-5),           -- overall usefulness
section_ratings JSONB,      -- per-section ratings {identity: 4, labor: 2, ...}
free_text TEXT,              -- what was useful, what was wrong
corrections JSONB,          -- {attribute: corrected_value}
was_actionable BOOLEAN,     -- "did this help you make a decision?"
created_at TIMESTAMP
```

API endpoints:
- `POST /api/research/feedback/{run_id}` — submit feedback
- `GET /api/research/feedback/summary` — aggregate feedback stats

### R2.2 — Frontend feedback UI
After viewing a dossier, show a feedback prompt:
- Star rating (1-5)
- Per-section thumbs up/down
- Free text box
- "Was this actionable?" toggle
- Inline fact correction (click a fact to propose a different value)

### R2.3 — Feedback-weighted grading
Adjust the auto-grader weights based on accumulated feedback:
- If users consistently rate "assessment" sections highly but "sources" sections poorly, shift weight toward assessment coverage
- If users report that dossiers with > 5 actionable recommendations score higher satisfaction, increase the actionability weight
- Minimum 20 feedback submissions before adjusting weights

**Acceptance:** `auto_grader.py` reads aggregate feedback and adjusts dimension weights. Weights are logged in `score_versions` for auditability.

### R2.4 — Fact corrections pipeline
When a user corrects a fact:
1. Store the correction in `research_fact_corrections`
2. Flag the original fact as `user_corrected`
3. On next research run for that employer, inject corrections as "known ground truth" in the prompt
4. Track correction patterns (e.g., "employee counts from Mergent are consistently 2x actual") to build source reliability adjustments

**Acceptance:** Corrected facts appear in subsequent dossiers. Source reliability coefficients are computed per source per attribute.

---

## Phase R3: Industry Knowledge Synthesis (2-3 Weeks)
> *Aggregate patterns across runs. This is the core "looped learning" — each run in an industry makes the next one smarter.*

### R3.1 — Industry insight aggregation job
After every 10 completed runs in a NAICS-2 industry, trigger an aggregation:

**Input:** All completed `research_facts` for that industry.

**Output:** `research_industry_insights` table:
```
naics_2 CHAR(2), insight_type TEXT, insight_text TEXT,
confidence FLOAT, supporting_run_count INT,
supporting_run_ids UUID[], created_at TIMESTAMP,
superseded_by INT  -- newer insight replaces this one
```

**Insight types to extract:**
- `violation_pattern` — "Healthcare employers in the Northeast average 3.2 OSHA violations, predominantly ergonomic and bloodborne pathogen categories"
- `union_strategy` — "SEIU wins 68% of elections in NAICS 62, compared to 45% for other unions"
- `employer_defense` — "Large retail employers (500+) run anti-union campaigns 82% of the time, typically hiring Jackson Lewis or Littler Mendelson"
- `data_availability` — "SEC filings available for 73% of NAICS 51 employers, but only 12% of NAICS 72"
- `financial_pattern` — "Nonprofit healthcare (NTEE E) median revenue $12M, typically have Form 5500 pension plans"

### R3.2 — Industry context injection
Before running research on a NAICS-62 employer, load the top 5 insights for NAICS 62 into the Gemini system prompt:
```
INDUSTRY INTELLIGENCE (from 47 prior investigations in Healthcare):
- OSHA violations in this industry cluster around ergonomic and bloodborne pathogen categories
- SEIU is the dominant union, winning 68% of elections
- Look for Form 5500 pension plans — 83% of healthcare employers have them
- SEC data is rare (12% coverage) — prioritize Mergent and 990 searches
```

This turns generic research into industry-informed investigation.

### R3.3 — Geographic pattern synthesis
Same as R3.1 but aggregated by state/region:
- "Right-to-work states have 40% lower NLRB petition rates but comparable ULP rates"
- "California employers have 2.3x more WHD cases than national average"
- "Northeast hospitals are 3x more likely to have existing union contracts"

Inject geographic insights alongside industry insights.

### R3.4 — Tool recommendation engine
Upgrade `research_strategies` from simple hit-rate tracking to information-gain scoring:

**Current:** "search_mergent has 26% hit rate for NAICS 62" → skip it.

**Upgraded:** "search_mergent produces 0.3 new confirmed facts per call for NAICS 62, but search_990 produces 2.1 new facts per call. For NAICS 62, run search_990 first, and only run search_mergent if the employer has > $10M revenue (then hit rate jumps to 71%)."

Track: facts_produced, novel_facts (not already known), assessment_changing_facts (facts that alter the recommended approach).

### R3.5 — Adaptive query generation
Replace static web search query templates with learned templates:
- After each web search, log (query_template, gap_type, industry, result_quality)
- After 50+ entries per gap_type, use the data to select the best-performing template for each industry/gap combination
- Generate new query variants based on successful patterns
- Kill templates with < 20% success rate after 10+ attempts

**Acceptance:** Average web search success rate increases from current 32-68% to 50-80%.

---

## Phase R4: Outcome Tracking & Predictive Feedback (2-3 Weeks)
> *Connect research to real-world outcomes. Does better research lead to better organizing?*

### R4.1 — Research-to-outcome linking
Match completed research runs to subsequent NLRB activity:
- `research_runs.employer_id` → `nlrb_elections` (via match tables)
- `research_runs.company_name` → `nlrb_cases` (via fuzzy name match)

Create `research_outcomes`:
```
run_id UUID FK, employer_id TEXT,
outcome_type TEXT,           -- 'election_filed', 'election_won', 'election_lost', 'ulp_filed', 'voluntary_recognition'
outcome_date DATE,
days_after_research INT,     -- how soon after research
outcome_details JSONB
```

### R4.2 — Quality-outcome correlation
Analyze: do higher-quality dossiers correlate with better organizing outcomes?
- Compare quality dimensions (actionability, coverage, etc.) against win rates
- Identify which dossier sections predict success: does a strong "assessment" section with specific campaign recommendations correlate with wins?
- Publish findings as a periodic report and use them to retune grading weights

### R4.3 — Predictive research prioritization
Use outcome data to answer: "which unresearched employers are most likely to benefit from research?"

Score unresearched employers by:
- Base score strength (high score + thin data = high research ROI)
- Industry research success rate (from R4.2)
- NLRB activity in their metro/industry (organizing momentum nearby)
- Employer size sweet spot (50-500 workers, where research has highest outcome impact)

Surface as `GET /api/research/recommended` — "these 20 employers would benefit most from research right now."

### R4.4 — Campaign monitoring
After an employer is researched, set up lightweight monitoring:
- Weekly check: any new NLRB cases filed?
- Monthly check: any new OSHA inspections or WHD cases?
- Quarterly: re-run incremental research (R1.4) if significant new data appears

Create `research_monitors`:
```
employer_id TEXT PK, monitor_type TEXT,
last_checked TIMESTAMP, check_frequency_days INT,
alert_conditions JSONB,  -- e.g., {"nlrb_case_filed": true}
active BOOLEAN
```

API: `POST /api/research/monitor/{employer_id}` to enable, `GET /api/research/alerts` for triggered alerts.

---

## Phase R5: Deep Intelligence (Months, High Impact)
> *The endgame: a system that builds institutional knowledge and reasons about the organizing landscape.*

### R5.1 — Vector search over dossiers (RAG)
Install pgvector. Embed completed dossiers and individual facts.

Before running research on a new employer, retrieve the 5 most similar past dossiers (by industry + size + geography embedding) and inject summaries as analogous cases:

"Companies similar to TARGET_CO that were recently organized:
- Company A (NAICS 6216, 200 employees, CA): SEIU won election 67-43. Key factor was OSHA violation history.
- Company B (NAICS 6214, 350 employees, OR): UFCW lost 89-112. Employer ran aggressive anti-union campaign with Littler."

This is the difference between "research this employer" and "research this employer in the context of everything we've learned about employers like it."

### R5.2 — Cross-employer pattern detection
Periodic batch job that scans all completed dossiers for emerging patterns:
- "3 employers in NAICS 4411 in Texas filed NLRB elections this quarter — possible organizing wave"
- "Average OSHA violations per employer in NAICS 62 increased 40% year-over-year"
- "Federal contract employers in this metro have 2x the WHD violation rate"

Surface as `GET /api/research/intelligence/trends` — actionable intelligence briefs for organizers scanning for opportunities.

### R5.3 — Collaborative dossier refinement
Allow organizers to annotate dossier facts with real-world knowledge:
- "This company actually has 3 locations, not 1"
- "The CEO is Jane Smith, not John (web scrape was wrong)"
- "They already have an IBEW contract at their Chicago plant"

Track corrections. Over time, build source reliability profiles:
- "Mergent employee counts are accurate within 20% for large employers but 2-3x inflated for small ones"
- "Website scrape finds correct HQ address 90% of the time but misidentifies subsidiaries as separate companies"

Feed reliability profiles into the auto-grader's source quality dimension.

### R5.4 — Research agent specialization
Instead of one generic research agent, create industry-specialized variants:
- **Healthcare agent:** Knows to look for CMS data, Joint Commission accreditation, nurse staffing ratios, Medicare cost reports
- **Construction agent:** Knows to look for prevailing wage projects, apprenticeship programs, Davis-Bacon coverage, project labor agreements
- **Retail/food service agent:** Knows to look for franchise structures, wage theft patterns, scheduling practices, high turnover signals

Each specialist inherits the base 25 tools but adds 3-5 industry-specific tools and carries industry-specific system prompts built from R3 insights.

### R5.5 — Natural language research interface
Let organizers ask questions in plain language:
- "What do we know about hospitals in New Jersey with recent OSHA violations?"
- "Show me non-union grocery stores in the Midwest with 200+ employees"
- "Which employers in NAICS 72 have had successful union elections recently?"

The system translates these into database queries + research agent invocations, combining structured data with AI-generated intelligence.

---

## Dependency Map

```
R0 (Fix Broken) ─────────────┬─── R1 (Cross-Run Memory)
                              │         │
                              │         ├─── R3 (Industry Synthesis)
                              │         │         │
                              │         │         └─── R5.1 (RAG)
                              │         │               R5.2 (Pattern Detection)
                              │         │               R5.4 (Specialization)
                              │         │
                              │         └─── R1.4 (Incremental) ── R4.4 (Monitoring)
                              │
                              ├─── R2 (Human Feedback)
                              │         │
                              │         └─── R4 (Outcome Tracking)
                              │                   │
                              │                   └─── R5.3 (Collaborative)
                              │                         R5.5 (NL Interface)
                              │
                              └─── R2.7 Backfill (existing roadmap)
```

R0 is the foundation. R1 and R2 are independent tracks that can run in parallel.
R3 depends on R1 (needs cross-run fact data). R4 depends on R2 (needs feedback data to correlate).
R5 items are the long game — each depends on having substantial data from earlier phases.

---

## Integration with Existing Roadmap

This document expands on items already in `UNIFIED_ROADMAP_FINAL_2026_02_26.md`:

| Existing Item | This Roadmap |
|---|---|
| 0.5 Fix Research Agent Connection | R0.1 - R0.3 |
| 2.7 Research Agent Backfill Sprint | Runs after R0 fixes, feeds R1/R3 with data |
| 2.8 Surface Research Quality in Frontend | R2.2 extends this with feedback UI |
| 3.7 Research Agent Learning Loop | R1 + R3 (much more detailed breakdown) |
| 3.8 Contradiction Adjudication Tool | R1.2 + R2.4 |
| 3.9 State Labor Board Tools | Fits into R5.4 (agent specialization) |

---

## Success Metrics by Phase

| Phase | Key Metric | Current | Target |
|---|---|---|---|
| R0 | Runs with NULL employer_id | 34% | < 5% |
| R0 | Non-union score enhancements | 0 | 50+ |
| R1 | Avg cost of re-research run | 5 cents | 2-3 cents |
| R1 | Facts confirmed across runs | 0 | 500+ |
| R2 | User feedback submissions | 0 | 50+ |
| R2 | Grading weight adjustments | 0 (static) | Data-driven |
| R3 | Industry insights generated | 0 | 100+ across 10 industries |
| R3 | Avg run quality after insights | 7.88 | 8.5+ |
| R4 | Research-to-outcome links | 0 | 30+ |
| R4 | Research-recommended employers acted on | 0 | measurable |
| R5 | Similar dossier retrieval accuracy | N/A | 80%+ relevant |

---

## Cost Projections

Current: ~5 cents/run (Gemini API). At scale:
- R0 fixes: No cost change, just fewer wasted runs
- R1 incremental mode: 40-60% reduction per refresh → ~2-3 cents
- R3 industry injection: Slightly longer prompts (+5-10% token cost) but fewer tool calls (-20-30%)
- R5 RAG: pgvector embedding cost is negligible; retrieval adds ~1 cent per run
- **Biggest cost driver is web scraping** (10.5s avg, 58% hit rate). R3.4 tool recommendation should cut wasted scrape attempts by 30-50%.

At 1,000 runs/month: ~$50/month Gemini API + negligible DB/compute costs.
