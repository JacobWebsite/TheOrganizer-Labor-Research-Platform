# Research Agent Architecture

The research agent is a Gemini-powered AI orchestration loop that conducts deep-dive investigations on individual employers. It queries 13 internal database tools + web scraping, produces a structured dossier, auto-grades the result, and feeds enhanced scores back into both scorecards.

---

## End-to-End Flow

```
User clicks "New Research" in frontend
  → POST /api/research/run {company_name, employer_id?, naics?, state?}
  → Creates research_runs row (status=pending)
  → Background task: run_research(run_id)
      → Builds system prompt with company context + tool list + vocabulary
      → Gemini 2.5 Flash agent loop (max 25 turns):
          1. Check internal databases (OSHA, NLRB, WHD, SEC, SAM, 990, contracts, Mergent)
          2. Get industry context (BLS profiles, similar employers)
          3. Additional enrichment (SEC proxy, job postings, workforce demographics)
          4. Scrape employer website (Crawl4AI)
          5. Synthesize into 7-section dossier JSON
      → Parse facts → research_facts table
      → Auto-grade (6 dimensions) → research_runs.overall_quality_score
      → Compute score enhancements → research_score_enhancements table
  → Frontend polls GET /api/research/status/{run_id} for progress
  → On completion: GET /api/research/result/{run_id} for full dossier
```

---

## Database Tables

### `research_runs` — One row per deep dive

The "cover page" for a research session.

| Column | Type | Notes |
|--------|------|-------|
| id | SERIAL PK | |
| employer_id | INTEGER | FK to f7_employers_deduped |
| company_name | VARCHAR(500) | Target company |
| company_name_normalized | VARCHAR(500) | Cleaned for matching |
| industry_naics | VARCHAR(6) | NAICS code |
| company_type | VARCHAR(30) | public/private/nonprofit/government |
| company_state | VARCHAR(2) | |
| employee_size_bucket | VARCHAR(20) | small/medium/large |
| status | VARCHAR(20) | pending/running/completed/failed |
| started_at / completed_at | TIMESTAMP | |
| duration_seconds | INTEGER | |
| total_tools_called | INTEGER | |
| total_facts_found | INTEGER | |
| sections_filled | INTEGER | Out of 7 |
| dossier_json | JSONB | Complete structured report |
| total_tokens_used | INTEGER | Gemini tokens |
| total_cost_cents | INTEGER | Estimated cost |
| triggered_by | VARCHAR(100) | User ID or 'system' |
| strategy_used | JSONB | Phase 2 strategy hints |
| overall_quality_score | DECIMAL(4,2) | Auto-graded 0-10 |
| human_quality_score | DECIMAL(4,2) | Human override |
| current_step | VARCHAR(200) | For progress bar |
| progress_pct | INTEGER | 0-100 |

**Indexes:** employer_id, status, industry_naics, created_at DESC.

### `research_actions` — One row per tool call

Detailed audit log of every tool invocation within a run.

| Column | Type | Notes |
|--------|------|-------|
| id | SERIAL PK | |
| run_id | INTEGER NOT NULL | FK to research_runs |
| tool_name | VARCHAR(100) | e.g. 'search_osha' |
| tool_params | JSONB | Search parameters |
| execution_order | INTEGER | 1st call, 2nd, etc. |
| data_found | BOOLEAN | |
| data_quality | DECIMAL(3,2) | 0.0-1.0 |
| facts_extracted | INTEGER | |
| result_summary | TEXT | |
| latency_ms | INTEGER | |
| cost_cents | INTEGER | |
| error_message | TEXT | |
| company_context | JSONB | |

Also serves as a **7-day cache** — before executing a tool, the agent checks for a recent successful result for the same employer + tool and reuses it.

### `research_facts` — One row per extracted fact

Individual pieces of information linked to run, tool call, and vocabulary.

| Column | Type | Notes |
|--------|------|-------|
| id | SERIAL PK | |
| run_id | INTEGER NOT NULL | FK to research_runs |
| action_id | INTEGER | FK to research_actions |
| employer_id | INTEGER | FK to f7_employers_deduped |
| dossier_section | VARCHAR(50) | identity/financial/workforce/labor/workplace/assessment/sources |
| attribute_name | VARCHAR(100) | Must match research_fact_vocabulary |
| attribute_value | TEXT | Stored as text |
| attribute_value_json | JSONB | For complex data |
| source_url | TEXT | URL or "database:table_name" |
| source_type | VARCHAR(30) | database/web_search/web_scrape/news/api |
| source_name | VARCHAR(200) | Human-readable source |
| confidence | DECIMAL(3,2) | 0.0-1.0 |
| as_of_date | DATE | |
| contradicts_fact_id | INTEGER | Self-reference for conflicts |

### `research_fact_vocabulary` — Allowed attribute names

~70 entries spanning 7 dossier sections. Acts as the dictionary enforcing consistent attribute naming.

**Sections:** identity (legal_name, dba_names, parent_company, website_url, year_founded...), financial (employee_count, revenue, revenue_range, financial_trend, exec_compensation...), workforce (workforce_composition, pay_ranges, job_posting_count, turnover_signals...), labor (existing_contracts, union_names, nlrb_election_count, nlrb_ulp_count, recent_organizing...), workplace (osha_violation_count, whd_case_count, safety_incidents, worker_complaints...), assessment (organizing_summary, campaign_strengths, campaign_challenges, recommended_approach), sources (section_confidence, data_gaps, source_list).

### `research_score_enhancements` — Scorecard feedback loop

Derived scorecard factor scores from research dossiers. One row per employer (UNIQUE constraint on employer_id). Higher-quality research replaces lower-quality via UPSERT.

| Column | Type | Notes |
|--------|------|-------|
| id | SERIAL PK | |
| employer_id | TEXT NOT NULL | |
| run_id | INTEGER NOT NULL | FK to research_runs |
| run_quality | NUMERIC(4,2) | Quality gate: skipped if < 3.0 |
| is_union_reference | BOOLEAN | Path A (union enrichment) vs Path B (non-union scoring) |
| score_osha | NUMERIC(4,2) | Factor scores (NULL if no data) |
| score_nlrb | NUMERIC(4,2) | |
| score_whd | NUMERIC(4,2) | |
| score_contracts | NUMERIC(4,2) | |
| score_financial | NUMERIC(4,2) | |
| score_size | NUMERIC(4,2) | |
| score_stability | NUMERIC(4,2) | Turnover-based (Pillar 2 input) |
| score_anger | NUMERIC(4,2) | Motivation-based (Pillar 1 input) |
| osha_violations_found | INTEGER | Raw extracted counts |
| nlrb_elections_found / nlrb_ulp_found | INTEGER | |
| whd_cases_found | INTEGER | |
| employee_count_found | INTEGER | |
| revenue_found | BIGINT | |
| federal_obligations_found | BIGINT | |
| turnover_rate_found | NUMERIC(4,2) | |
| sentiment_score_found | NUMERIC(4,2) | |
| revenue_per_employee_found | NUMERIC | |
| recommended_approach | TEXT | Display only |
| campaign_strengths / campaign_challenges | JSONB | |
| source_contradictions | JSONB | |
| financial_trend | TEXT | |
| confidence_avg | NUMERIC(3,2) | |

### `research_strategies` — Tool effectiveness learning (Phase 2, not yet populated)

Aggregated hit rates by industry/company_type/size/tool. Will inform future tool ordering.

### `research_query_effectiveness` — Web search template learning

Tracks which web search query templates produce results for each gap type. Partially used — effectiveness tracking updates after each run.

---

## Relationship Diagram

```
research_fact_vocabulary
    ↓ (constrains attribute_name)
research_facts ←── research_actions ←── research_runs
    ↓                                        ↓
    └──→ employer_id (f7_employers_deduped)   │
                                              ↓
                                    research_score_enhancements
                                              ↓
                              ┌────────────────┴────────────────┐
                              ↓                                 ↓
                    mv_unified_scorecard              mv_target_scorecard
                    (LEFT JOIN on employer_id)     (LEFT JOIN via F7 bridge)
```

---

## Integration with Scorecards

### Unified Scorecard (`mv_unified_scorecard`)

In `build_unified_scorecard.py`, the `research_enhanced` CTE LEFT JOINs `research_score_enhancements` on `employer_id`:

```sql
research_enhanced AS (
    SELECT s.*,
        rse.run_id AS research_run_id,
        rse.run_quality AS research_quality,
        GREATEST(s.score_osha, rse.score_osha) AS enh_score_osha,
        GREATEST(s.score_nlrb, rse.score_nlrb) AS enh_score_nlrb,
        GREATEST(s.score_whd, rse.score_whd) AS enh_score_whd,
        GREATEST(s.score_contracts, rse.score_contracts) AS enh_score_contracts,
        GREATEST(s.score_financial, rse.score_financial) AS enh_score_financial,
        COALESCE(s.score_size, rse.score_size) AS enh_score_size,
        rse.recommended_approach AS research_approach,
        rse.financial_trend AS research_trend,
        rse.source_contradictions AS research_contradictions,
        rse.score_stability AS rse_score_stability,
        rse.score_anger AS rse_score_anger,
        rse.turnover_rate_found, rse.sentiment_score_found,
        rse.revenue_per_employee_found,
        (rse.run_id IS NOT NULL) AS has_research
    FROM scored s
    LEFT JOIN research_score_enhancements rse ON rse.employer_id = s.employer_id
)
```

**Key behavior:** `GREATEST` means research can only **upgrade** a score, never downgrade it. The enhanced scores flow into the strategic pillars (Anger, Stability, Leverage) and the final weighted score.

**MV output columns from research:** `has_research`, `research_run_id`, `research_quality`, `research_weighted_score`, `score_delta`, `research_approach`, `research_trend`, `research_contradictions`.

### Target Scorecard (`mv_target_scorecard`)

Uses a `research_bridge` CTE that joins through `master_employer_source_ids` (where `source_system = 'f7'`) to link master_ids to F7-based research_score_enhancements. Same GREATEST logic for enhanced signals. Gold standard tiers (stub/bronze/silver/gold/platinum) based on research quality.

**Current state:** 0 research matches in target pool because researched employers are union F7, not in the non-union target pool.

---

## Tool Inventory (14 tools)

| # | Tool | Source | What it searches |
|---|------|--------|-----------------|
| 1 | `search_osha` | database | OSHA violations, inspections, penalties, accidents |
| 2 | `search_nlrb` | database | Elections (wins/losses), ULP charges, union names |
| 3 | `search_whd` | database | Wage theft cases, backwages, repeat violators |
| 4 | `search_sec` | database | SEC filings, CIK, ticker, exchange, SIC code |
| 5 | `search_sam` | database | SAM.gov registrations, DUNS, federal obligations |
| 6 | `search_990` | database | IRS 990 nonprofit financials (revenue, assets, employees) |
| 7 | `search_contracts` | database | F7 union contracts, bargaining units, union names |
| 8 | `search_mergent` | database | Mergent Intellect (employees, revenue, parent, DUNS, SIC) |
| 9 | `search_sec_proxy` | database | SEC DEF 14A proxy — executive compensation |
| 10 | `search_job_postings` | database | Active job listings, posting counts, pay ranges |
| 11 | `get_workforce_demographics` | database | BLS industry-level demographics (race, gender, age baselines) |
| 12 | `get_industry_profile` | database | BLS occupation mix, wages, union density by NAICS |
| 13 | `get_similar_employers` | database | Comparable organized employers, recent elections in same industry |
| 14 | `scrape_employer_website` | web | Crawl4AI scrape of homepage, about, careers, news, locations, contact, investors |

All tools return `{found: bool, source: str, summary: str, data: {...}, error?: str}`.

### Name Matching in Tools

`_name_like_clause(column, company_name)` generates flexible SQL LIKE patterns:
- Handles spaces: "Fed Ex" matches both "FED EX" and "FEDEX"
- Generates acronyms: "University of Pittsburgh Medical Center" also matches "UPMC%"

`_filter_by_name_similarity(rows, company_name, ...)` post-filters with RapidFuzz `token_sort_ratio >= 0.50` to remove false positives.

### Resolution Flow (typical for database tools)

1. If `employer_id` provided: direct lookup via match tables (e.g. `osha_f7_matches`)
2. Fallback: check `unified_match_log` for prior matches
3. Fallback: fuzzy LIKE search on source table's name column (with state filter)
4. Post-filter with RapidFuzz similarity

### Web Scraping (`scrape_employer_website`)

**URL Resolution (4-tier):**
1. Provided URL → normalize and use
2. Mergent via employer_id → `unified_match_log` → `mergent_employers.website`
3. Mergent by name+state → search `mergent_employers` table
4. Gemini + Google Search grounding (if enabled)

**Page Targets & Character Budgets:**

| Page | Paths tried | Budget |
|------|-------------|--------|
| homepage | `/` | 3,000 chars |
| about | `/about`, `/about-us`, `/company`, `/our-story` | 2,500 chars |
| careers | `/careers`, `/jobs`, `/work-with-us` | 1,500 chars |
| news | `/news`, `/press`, `/newsroom`, `/media` | 1,000 chars |
| locations | `/locations`, `/facilities`, `/our-offices` | 1,000 chars |
| contact | `/contact`, `/contact-us` | 1,000 chars |
| investors | `/investors`, `/investor-relations` | 1,500 chars |

Total budget: 12,000 chars. Timeout: 35 seconds.

**Markdown sanitized** to ASCII (Unicode arrows/quotes/bullets → ASCII equivalents). **Truncated** at paragraph/sentence boundaries to fit budget.

**Windows encoding workaround:** Crawl4AI prints Unicode during browser init. On Windows cp1252, this crashes stdout. Solved by redirecting `sys.stdout` to a UTF-8 `io.TextIOWrapper(io.BytesIO())` during `asyncio.run()`, restoring after.

---

## Auto-Grader (6-Dimension Quality Scoring)

**File:** `scripts/research/auto_grader.py`

Each dimension scores 0-10. Overall = weighted average.

| Dimension | Weight | What it measures |
|-----------|--------|-----------------|
| **Coverage** | 20% | Field fill rate across 7 dossier sections. Penalty for placeholder values ("unknown", "not found", "n/a"). |
| **Source Quality** | 35% | Average source type score (database=1.0, api=0.9, web_scrape=0.7, web_search=0.6, news=0.5) blended with average confidence. Penalty if >30% facts lack source_name. |
| **Consistency** | 15% | Starts at 10.0, deducts for: contradictions (-2.0 each), numeric divergence in employee_count or revenue (ratio > 2x = -2.0), DB-vs-web violation mismatches (-1.0 each). |
| **Actionability** | 15% | Points for organizer-relevant content: recommended_approach (+3), campaign_strengths >=3 items (+2), campaign_challenges >=3 items (+2), source_contradictions (+1), financial_trend (+1), exec_compensation for public companies (+1). |
| **Freshness** | 10% | Average recency of fact `as_of_date`: <6mo=10, 6-12mo=8, 1-2yr=6, 2-3yr=4, 3-5yr=2, >5yr=1, undated=5. |
| **Efficiency** | 5% | Facts per tool call: >=3=10, >=2=8, >=1=6, >=0.5=4, <0.5=2. Speed bonus +1 if avg latency <500ms. |

### Quality Gate

If `overall_quality_score < 3.0`, score enhancements are **skipped** — too low confidence to feed back into scorecards.

### Enhancement Computation

`compute_research_enhancements(run_id)` extracts numeric values from the dossier, computes factor scores using the same formulas as `build_unified_scorecard.py`, and UPSERTs into `research_score_enhancements`. Higher-quality research replaces lower-quality for the same employer.

---

## Gemini Integration

**Model:** `gemini-2.5-flash` (configurable via `RESEARCH_AGENT_MODEL` env var)
**Library:** `google-genai` (`genai.Client`)
**Max turns:** 25 (configurable via `RESEARCH_AGENT_MAX_TURNS`)
**Max tokens:** 65,536 (configurable via `RESEARCH_AGENT_MAX_TOKENS`)

### Pricing

```
Input:  $0.30 / 1M tokens  ($0.03 / 1K)
Output: $2.50 / 1M tokens  ($0.25 / 1K)
Typical run: ~$0.02-0.03
```

### Conversation Loop

```python
for turn in range(MAX_TOOL_TURNS):
    response = client.models.generate_content(
        model=MODEL,
        contents=contents,          # Full conversation history
        config=GenerateContentConfig(
            system_instruction=system_prompt,
            tools=gemini_tools,     # FunctionDeclarations built from TOOL_DEFINITIONS
            max_output_tokens=MAX_TOKENS,
        ),
    )
    function_calls = [p for p in parts if p.function_call]
    if not function_calls:
        # Gemini is done — extract final dossier JSON from text
        break
    # Execute each function call locally, build function responses
    contents.append(candidate.content)        # Gemini's requests
    contents.append(Content(role="user", parts=function_responses))  # Our results
```

### Tool Rejection

`google_search` and `search_web` calls are silently rejected with an error response directing Gemini to use database tools. After 2 consecutive all-web-search turns, the loop breaks.

### Limitation

Gemini cannot mix `function_declarations` and `google_search` tools in the same API request (returns 400 INVALID_ARGUMENT). Database tools and web search grounding require separate calls.

---

## API Endpoints

**Router:** `api/routers/research.py`

| Method | Endpoint | Purpose |
|--------|----------|---------|
| POST | `/api/research/run` | Start new deep dive. Returns `{run_id, status: "pending"}`. |
| GET | `/api/research/status/{run_id}` | Poll progress (status, current_step, progress_pct, duration). |
| GET | `/api/research/result/{run_id}` | Full results: dossier JSON, facts by section, action log, quality score. |
| GET | `/api/research/runs` | List runs. Filters: status, employer_id, naics, q (name search). Pagination. |
| GET | `/api/research/candidates` | Suggested employers for research (high-value targets missing research). |
| GET | `/api/research/vocabulary` | List all valid fact attribute names. |

### Scorecard Detail Integration

`GET /api/scorecard/unified/{employer_id}` includes research data in explanations when `has_research=true`:
- `research_dossier_url` → `/api/research/result/{run_id}`
- `score_delta` → how much research shifted the score
- Explanation text includes research run ID and delta

---

## Frontend Components

**Directory:** `frontend/src/features/research/`

| Component | Purpose |
|-----------|---------|
| `ResearchPage.jsx` | Main page — list all runs with filtering |
| `ResearchFilters.jsx` | Filter bar (status, name search) |
| `ResearchRunsTable.jsx` | Table of runs (status, duration, quality) |
| `NewResearchModal.jsx` | Form to start new research (company name, state, NAICS, type) |
| `ResearchResultPage.jsx` | Detail view — polls status, renders dossier on completion |
| `DossierHeader.jsx` | Title, metadata, download button |
| `DossierSection.jsx` | Collapsible section renderer (facts grouped by attribute) |
| `FactRow.jsx` | Single fact (attribute, value, source, confidence) |
| `ActionLog.jsx` | Tool call log (what the agent did, latency, findings) |
| `useResearchState.js` | Zustand hook for filter state in URL |

### User Workflow

1. Click "New Research" → `NewResearchModal`
2. Enter company_name (+ optional state, NAICS, type)
3. POST `/api/research/run` → get `run_id`
4. Navigate to `/research/{run_id}`
5. `ResearchResultPage` polls status every 2-3s, shows progress bar + `current_step`
6. On `status=completed`, fetches full result and renders dossier sections + facts + action log

---

## Tests

| File | Tests | Covers |
|------|-------|--------|
| `tests/test_research_agent_52.py` | ~80 | Vocabulary mapping, JSON repair, cache hit/miss, gap-aware query builder, query effectiveness |
| `tests/test_research_enhancements.py` | 31 | Schema, compute_research_enhancements quality gate/path detection/scoring, UPSERT logic, MV columns, API endpoints |
| `tests/test_research_scraper.py` | ~20 | Crawl4AI scraper, URL resolution (4-tier), page scraping with budgets, markdown sanitization, timeout handling |
| `tests/test_auto_grader.py` | ~46 | All 6 grading dimensions, edge cases, grade_and_save integration |

**Total:** ~177 tests across 4 files.

---

## Key Files

| File | Purpose |
|------|---------|
| `scripts/research/agent.py` | Core orchestration loop, Gemini integration, system prompt builder |
| `scripts/research/tools.py` | 14 tool implementations + TOOL_REGISTRY + TOOL_DEFINITIONS |
| `scripts/research/auto_grader.py` | 6-dimension quality scoring + grade_and_save + compute_research_enhancements |
| `scripts/scoring/create_research_enhancements.py` | Schema for research_score_enhancements table |
| `sql/create_research_agent_tables.sql` | Schema for all research tables (runs, actions, facts, vocabulary, strategies, query_effectiveness) |
| `api/routers/research.py` | API endpoints (run, status, result, runs, candidates, vocabulary) |
| `frontend/src/features/research/` | 10 React components for research UI |
