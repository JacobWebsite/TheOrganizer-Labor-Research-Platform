# Research Agent Reference

> **For AI evaluators:** This document describes the complete architecture, data flow, tools, schema, and known issues of the Labor Relations Research Agent. It is self-contained — you should not need additional context to evaluate or improve the system.

## 1. What It Does

The Research Agent conducts automated deep-dive research on a single employer to compile a **labor-relations organizing dossier**. It queries 11 internal government/business databases, scrapes the employer's website, searches the web for current news and job postings, and synthesizes everything into a structured JSON report with 57 vocabulary fields across 7 sections.

**Use case:** A labor organizer enters "Xerox" in the frontend. The agent spends ~2 minutes querying OSHA violations, NLRB elections, wage theft cases, SEC filings, federal contracts, nonprofit 990s, Mergent business data, BLS industry profiles, and Google Search — then produces a dossier with facts, sources, confidence scores, and an assessment.

## 2. Architecture Overview

```
Frontend (React)
    |
    | POST /api/research/run  {company_name, employer_id?, naics?, type?, state?}
    v
FastAPI Router (api/routers/research.py)
    |
    | BackgroundTask
    v
Agent Orchestration (scripts/research/agent.py, 2,023 lines)
    |
    |-- Phase 1: Tool-use loop (Gemini 2.5 Flash + function calling)
    |     |-- 14 local tools dispatched via TOOL_REGISTRY
    |     |-- Each tool queries PostgreSQL or Gemini (scripts/research/tools.py, 2,189 lines)
    |     |-- Results cached 7 days per (employer_id, tool_name)
    |     |-- Max 25 turns
    |
    |-- Phase 1.5: Forced scraper (if Gemini didn't call it)
    |     |-- Crawl4AI scrapes homepage, /about, /careers, /news
    |     |-- 4-tier URL resolution (provided > Mergent DB > Mergent name > Google)
    |
    |-- Phase 2: Web search (separate Gemini call with Google Search grounding)
    |     |-- Gap-aware queries built from Phase 1 misses
    |     |-- 8-15 targeted queries per run
    |     |-- Returns JSON with news, organizing activity, financial data, etc.
    |
    |-- Phase 3: Web merge (deterministic, no LLM)
    |     |-- Parses web JSON, maps to vocabulary field names
    |     |-- Regex fallback for employee count and revenue extraction
    |     |-- Turnover signal extraction from worker issues
    |
    |-- Phase 4: Post-merge validation (deterministic)
    |     |-- Copies facts from facts array to dossier body where missing
    |     |-- Logs remaining gaps
    |
    |-- Auto-grading (scripts/research/auto_grader.py, 442 lines)
    |     |-- 5 dimensions: Coverage, Source Quality, Consistency, Freshness, Efficiency
    |     |-- Weighted overall score persisted to research_runs
    |
    v
PostgreSQL (olms_multiyear)
    |-- research_runs          (run metadata, dossier JSON, quality scores)
    |-- research_actions       (per-tool audit trail)
    |-- research_facts         (individual facts with provenance)
    |-- research_strategies    (learned tool effectiveness by industry)
    |-- research_query_effectiveness  (web query hit rates)
    |-- research_fact_vocabulary      (57 canonical field definitions)
```

## 3. Configuration

| Variable | Default | Description |
|---|---|---|
| `RESEARCH_AGENT_MODEL` | `gemini-2.5-flash` | Gemini model for orchestration |
| `RESEARCH_AGENT_MAX_TURNS` | `25` | Max tool-call turns before forced stop |
| `RESEARCH_AGENT_MAX_TOKENS` | `65536` | Max output tokens per Gemini call |
| `GOOGLE_API_KEY` | (required) | Gemini API key |
| `MATCH_MIN_NAME_SIM` | `0.80` | RapidFuzz minimum similarity for name matching |

**Cost:** ~$0.05/run (Gemini 2.5 Flash pricing: $0.30/M input, $2.50/M output).

## 4. The 14 Tools

Each tool is a Python function in `scripts/research/tools.py` that queries PostgreSQL (or Gemini grounding) and returns a standardized dict:

```python
{
    "found": bool,          # Whether any data was found
    "source": str,          # e.g., "database:osha_violations_detail"
    "summary": str,         # Human-readable summary (up to 1000 chars)
    "data": dict,           # Structured findings (varies per tool)
    "error": str | None     # Only present on failure
}
```

### Tool Reference

| # | Tool | Data Source | Hit Rate | Avg Latency | What It Returns |
|---|---|---|---|---|---|
| 1 | `search_osha` | `osha_violations_detail`, `osha_inspections` | 87% | 915ms | Violation counts, penalty totals, serious/willful/repeat breakdowns, top violation types, workplace accidents |
| 2 | `search_nlrb` | `nlrb_elections`, `nlrb_participants`, `nlrb_ulp_charged_party` | 75% | 645ms | Election outcomes, vote counts, ULP charges, voluntary recognitions, union names |
| 3 | `search_whd` | `whd_cases` | 74% | 594ms | Case counts, back wages owed, civil penalties, employees affected, repeat violator status, child labor violations |
| 4 | `search_sec` | `sec_companies`, `corporate_identifier_crosswalk` | 81% | 495ms | Company info, SIC code, ticker, exchange, federal contractor status |
| 5 | `search_sam` | `sam_entities`, `usaspending_awards` | 57% | 470ms | Registration status, contract totals, NAICS codes, entity structure |
| 6 | `search_990` | `irs_990_organizations`, `irs_990_financials` | 82% | 484ms | Revenue, assets, employees, NTEE code. Skipped for public companies. |
| 7 | `search_contracts` | `f7_employers_deduped`, `f7_bargaining_units` | 78% | 221ms | Contract counts, union names, bargaining unit sizes, affiliations |
| 8 | `get_industry_profile` | `bls_industry_occupation_matrix`, `bls_occupation_projections`, `bls_national_industry_density`, `estimated_state_industry_density` | 100% | 50ms | Top 10 occupations with employment %, pay ranges (median wages), national/state union density |
| 9 | `get_similar_employers` | `mv_unified_scorecard`, `f7_employers_deduped`, `nlrb_elections` | 90% | 345ms | Comparable organized employers in same NAICS, recent elections in similar industries |
| 10 | `search_mergent` | `mergent_employers`, `unified_match_log` | 39% | 852ms | Employee counts, revenue, parent company, DUNS number, website URL. Low coverage (only 1,045 matched employers). |
| 11 | `scrape_employer_website` | Live web via Crawl4AI | 19% | 2,686ms | Homepage, /about, /careers, /news text. 4-tier URL resolution. Fails often due to URL resolution issues. |
| 12 | `search_sec_proxy` | Gemini + Google Search grounding | NEW | ~2,000ms | Executive compensation from SEC DEF 14A proxy statements. Top 3 exec pay for public companies. |
| 13 | `search_job_postings` | Gemini + Google Search grounding | NEW | ~2,000ms | Estimated job posting counts, sample titles, locations, pay ranges from major job boards. |
| 14 | `get_workforce_demographics` | Hardcoded baselines (6 NAICS) | NEW | <5ms | Industry-typical race, gender, age demographics. Placeholder — uses static data, not real BLS queries. |

### Tool Not Available During Phase 1

| Tool | Why |
|---|---|
| `google_search` | Gemini's built-in search — used only in Phase 2 (separate API call with Google Search grounding). Rejected with explicit error if Gemini tries to call it as a function. |
| `search_web` | Removed from registry. Was a stub. Gemini occasionally hallucinated this tool name. |

### How Tools Are Called

Gemini decides which tools to call and in what order via function calling. The agent provides all 14 tool schemas as `FunctionDeclaration` objects. Gemini typically calls 12-15 tools per run (all DB tools + industry profile + similar employers + optional proxy/jobs/demographics). The agent dispatches each call to the local `TOOL_REGISTRY` and returns results to Gemini for synthesis.

**Caching:** Results are cached for 7 days per `(employer_id, tool_name)` in `research_actions`. Cache hits skip the DB query and return the stored summary.

**google_search rejection:** If Gemini calls `google_search` or `search_web` during Phase 1, the call is silently rejected (not counted, not logged). After 2 consecutive turns of only web-search calls, the loop breaks automatically.

## 5. The Dossier

The output is a structured JSON with 7 sections and 57 vocabulary fields:

### 5.1 identity (10 fields)
| Field | Type | Description |
|---|---|---|
| `legal_name` | text | Official legal name |
| `dba_names` | json | Other operating names |
| `company_type` | text | public/private/nonprofit/government |
| `naics_code` | text | 2-6 digit industry code |
| `naics_description` | text | Human-readable industry name |
| `hq_address` | json | Full headquarters address |
| `major_locations` | json | Key facilities beyond HQ |
| `website_url` | text | Primary website URL |
| `year_founded` | number | Year established |
| `parent_company` | text | Corporate parent name |

### 5.2 financial (10 fields)
| Field | Type | Description |
|---|---|---|
| `employee_count` | number | Total employee count or best estimate |
| `revenue` | currency | Annual revenue (exact or range) |
| `revenue_range` | text | Revenue bracket if exact unavailable |
| `financial_trend` | text | growing/stable/shrinking/unknown |
| `nonprofit_revenue` | currency | Total revenue from IRS Form 990 |
| `nonprofit_assets` | currency | Total assets from IRS Form 990 |
| `federal_contract_status` | boolean | Is a federal contractor? |
| `federal_contract_count` | number | Number of federal contracts |
| `federal_obligations` | currency | Total federal contract dollars |
| `exec_compensation` | json | Top exec pay (public companies) |

### 5.3 workforce (6 fields)
| Field | Type | Description |
|---|---|---|
| `workforce_composition` | json | Job types and percentages from BLS |
| `pay_ranges` | json | Salary ranges for key positions |
| `demographic_profile` | json | Typical demographics for industry/area |
| `job_posting_count` | number | Current job listings found |
| `job_posting_details` | json | Sample titles, pay, locations |
| `turnover_signals` | text | Evidence of high/low turnover |

### 5.4 labor (8 fields)
| Field | Type | Description |
|---|---|---|
| `existing_contracts` | json | Current/recent union contracts |
| `union_names` | json | Names of unions with contracts |
| `nlrb_election_count` | number | NLRB elections involving this employer |
| `nlrb_election_details` | json | Dates, outcomes, vote counts |
| `nlrb_ulp_count` | number | Unfair labor practice charges |
| `nlrb_ulp_details` | json | Types, filers, outcomes of ULPs |
| `recent_organizing` | text | Recent organizing news/campaigns |
| `voluntary_recognition` | json | Voluntary union recognitions |

### 5.5 workplace (12 fields)
| Field | Type | Description |
|---|---|---|
| `osha_violation_count` | number | Total OSHA violations |
| `osha_serious_count` | number | Serious/willful/repeat violations |
| `osha_penalty_total` | currency | Total OSHA penalty dollars |
| `osha_violation_details` | json | Types, severity, penalties |
| `safety_incidents` | json | Workplace accidents and incidents |
| `whd_case_count` | number | DOL Wage & Hour cases |
| `whd_backwages` | currency | Total back wages assessed |
| `whd_employees_affected` | number | Workers affected |
| `whd_penalties` | currency | Civil penalties from wage cases |
| `whd_repeat_violator` | boolean | FLSA repeat violator flag |
| `recent_labor_news` | json | News articles about labor issues |
| `worker_complaints` | text | Complaints/lawsuits from news |

### 5.6 assessment (8 fields)
| Field | Type | Description |
|---|---|---|
| `data_summary` | text | 2-3 paragraph factual summary |
| `organizing_summary` | text | Key organizing intelligence |
| `campaign_strengths` | json | Factors favorable for organizing |
| `campaign_challenges` | json | Obstacles to organizing |
| `web_intelligence` | text | Web findings beyond DB records |
| `source_contradictions` | json | Contradictions between sources |
| `data_gaps` | json | Missing/unverifiable information |
| `recommended_approach` | text | (deprecated, set to null) |
| `similar_organized` | json | (deprecated, set to null) |

### 5.7 sources (3 fields)
| Field | Type | Description |
|---|---|---|
| `section_confidence` | json | Per-section confidence (high/medium/low) |
| `data_gaps` | json | What was NOT found |
| `source_list` | json | Every source checked with timestamps |

## 6. Database Schema

### research_runs
The master record for each research session.

| Column | Type | Description |
|---|---|---|
| `id` | integer (PK) | Auto-incrementing run ID |
| `employer_id` | text | F7 employer hex ID (nullable) |
| `company_name` | varchar | Company name as entered |
| `company_name_normalized` | varchar | Uppercased/cleaned name |
| `industry_naics` | varchar | NAICS code |
| `company_type` | varchar | public/private/nonprofit |
| `company_state` | varchar | 2-letter state |
| `employee_size_bucket` | varchar | small/medium/large |
| `status` | varchar | pending/running/completed/failed |
| `started_at` / `completed_at` | timestamp | Run timing |
| `duration_seconds` | integer | Wall-clock duration |
| `total_tools_called` | integer | Number of tool calls |
| `total_facts_found` | integer | Facts saved to research_facts |
| `sections_filled` | integer | Dossier sections with data (0-7) |
| `dossier_json` | jsonb | The complete dossier output |
| `total_tokens_used` | integer | Gemini tokens consumed |
| `total_cost_cents` | integer | Estimated cost in cents |
| `overall_quality_score` | numeric | Auto-graded score (0-10) |
| `quality_dimensions` | jsonb | Per-dimension scores |
| `current_step` | varchar | Progress description for UI |
| `progress_pct` | integer | Progress bar value (0-100) |

### research_actions
Per-tool audit trail — every tool call in every run.

| Column | Type | Description |
|---|---|---|
| `id` | integer (PK) | |
| `run_id` | integer (FK) | Links to research_runs |
| `tool_name` | varchar | e.g., "search_osha", "google_search" |
| `tool_params` | jsonb | Parameters passed to the tool |
| `execution_order` | integer | Order within the run |
| `data_found` | boolean | Whether the tool returned data |
| `result_summary` | text | Truncated summary of results |
| `latency_ms` | integer | Execution time |
| `error_message` | text | Error details if failed |

### research_facts
Individual facts extracted from the dossier, with provenance.

| Column | Type | Description |
|---|---|---|
| `id` | integer (PK) | |
| `run_id` | integer (FK) | Links to research_runs |
| `employer_id` | text | F7 employer ID |
| `dossier_section` | varchar | One of 7 sections |
| `attribute_name` | varchar | Vocabulary field name |
| `attribute_value` | text | Simple value |
| `attribute_value_json` | jsonb | Complex value (lists, dicts) |
| `source_type` | varchar | database/web_search/web_scrape/api |
| `source_name` | varchar | e.g., "search_osha", "google_search" |
| `confidence` | numeric | 0.0-1.0 confidence score |
| `as_of_date` | date | When the data was current |
| `contradicts_fact_id` | integer | FK to contradicting fact |

### research_fact_vocabulary
Canonical definitions for the 57 allowed field names.

| Column | Type | Description |
|---|---|---|
| `attribute_name` | varchar | e.g., "employee_count" |
| `display_name` | varchar | Human-friendly label |
| `dossier_section` | varchar | Which section it belongs to |
| `data_type` | varchar | text/number/currency/boolean/json |
| `description` | text | What this field represents |

### research_strategies
Learned tool effectiveness per industry/type/size combination. Updated after each graded run via UPSERT.

| Column | Type | Description |
|---|---|---|
| `industry_naics_2digit` | varchar | 2-digit NAICS prefix |
| `company_type` | varchar | public/private/nonprofit |
| `company_size_bucket` | varchar | small/medium/large |
| `tool_name` | varchar | Tool that was tried |
| `times_tried` | integer | Total attempts |
| `times_found_data` | integer | Attempts that returned data |
| `hit_rate` | numeric | times_found_data / times_tried |
| `avg_quality` | numeric | Avg overall_quality_score when tool found data |
| `avg_latency_ms` | integer | Average execution time |

### research_query_effectiveness
Tracks which web search query templates produce results, per gap type.

| Column | Type | Description |
|---|---|---|
| `gap_type` | text | e.g., "employee_count", "revenue", "nlrb_activity" |
| `query_template` | text | Template like `"{company}" employees site:linkedin.com` |
| `times_used` | integer | How often this template was used |
| `times_produced_result` | integer | How often it found data |

## 7. API Endpoints

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/research/run` | Start a new deep dive. Body: `{company_name, employer_id?, naics_code?, company_type?, state?}`. Returns `{run_id, status}`. |
| `GET` | `/api/research/status/{run_id}` | Poll progress. Returns `{status, progress_pct, current_step, ...}`. |
| `GET` | `/api/research/result/{run_id}` | Get completed dossier + facts + action log + quality scores. |
| `GET` | `/api/research/runs` | List runs with filters: `?status=&employer_id=&naics=&q=&limit=&offset=`. |
| `GET` | `/api/research/vocabulary` | List all 57 valid fact attribute names. |

## 8. Auto-Grading System

Every completed run is graded by `scripts/research/auto_grader.py` on 5 dimensions:

| Dimension | Weight | How It's Scored | Current Avg |
|---|---|---|---|
| **Coverage** | 20% | (sections_with_facts / 7) * 8 + bonus for rich sections (3+ facts each, max +2) | 7.02 |
| **Source Quality** | 35% | Avg of (source_type_rank * 0.5 + confidence * 0.5) * 10. Ranks: database=1.0, api=0.9, web_scrape=0.7, web_search=0.6, news=0.5. Penalty -1 if >30% facts lack source_name. | 7.90 |
| **Consistency** | 25% | Starts at 10. -2 per contradiction flag. -2 if employee_count values diverge >2x. -2 if revenue values diverge >2x. | 10.00 |
| **Freshness** | 15% | Avg per-fact age score: <6mo=10, 6-12mo=8, 1-2yr=6, 2-3yr=4, 3-5yr=2, >5yr=1. Undated=5 (neutral). | 4.84 |
| **Efficiency** | 5% | facts_per_tool: >=3->10, >=2->8, >=1->6, >=0.5->4, <0.5->2. +1 bonus if avg_latency<500ms. | 8.28 |

**Overall = weighted sum.** Current average: **7.81/10** across 68 completed runs.

## 9. Performance Metrics (68 Completed Runs)

| Metric | Value |
|---|---|
| Completion rate | 68/72 (94%) |
| Avg quality score | 7.81/10 |
| Avg facts per run | 29.0 |
| Avg sections filled | 6.0/7 |
| Avg duration | 1.9 min |
| Avg cost | ~$0.05/run |
| Avg tools called | ~12/run |

### Section Fill Rates

| Section | Avg Fill Rate | Notes |
|---|---|---|
| sources | 91% | Almost always populated |
| workplace | 67% | Strong from OSHA/WHD |
| labor | 61% | Good for union employers |
| assessment | 57% | AI-generated, inconsistent |
| identity | 55% | Missing: website, locations, year_founded |
| financial | 23% | Worst. Revenue/employee_count rarely filled from web |
| workforce | 21% | Worst. Only BLS composition works |

## 10. Known Issues & Status

### Resolved (2026-02-24)
1.  **Financial data fill rate improved.** Added regex-based post-patching (`_patch_dossier_financials`) that recovers employee count and revenue from narrative summaries.
2.  **Scraper reliability and scope improved.** Enhanced Tier-4 Google Search resolution with industry/state context. Expanded scope to include `/locations`, `/contact`, and `/investors` to improve identity and workforce section fill rates.
3.  **Consistency score is now functional.** Added `_extract_numeric` to the auto-grader for real numeric divergence checks. Implemented a two-pass save in the agent to resolve `contradicts_fact_id` using Gemini-provided hints.
4.  **Workforce section now has dedicated data sources.** Added `search_job_postings` (Google Search grounding) and `get_workforce_demographics` (baseline profiles) to fill previously empty fields.
5.  **Second-pass gap filler implemented.** Added `_fill_dossier_gaps` which uses a targeted Gemini pass to specifically hunt for any remaining `null` fields in the raw web text.
6.  **Executive compensation now supported.** Added `search_sec_proxy` tool to extract top exec pay from SEC DEF 14A proxy statements.

### Remaining
7. **Scraper timeout.** Large websites may occasionally hit the 35s timeout limit.
8. **Freshness score averages 4.84/10.** Most government data is 1-3 years old. Only web search produces recent facts.
9. **`get_workforce_demographics` uses hardcoded baselines.** Only 6 NAICS 2-digit codes covered with static data, not real BLS queries. Placeholder for Phase 6.
10. **`search_sec_proxy` accuracy unverified on live runs.** Uses Gemini Google Search grounding to find proxy statements — may hallucinate for small-cap companies.
11. **`search_job_postings` returns estimates, not counts.** Gemini approximates posting counts from web results. No direct Indeed/LinkedIn API integration.
12. **`_fill_dossier_gaps` (second Gemini pass) not yet measured.** Adds ~$0.01/run. Expected to push fill rates from ~53% toward 70%.
13. **Financial regex fallback (`_patch_dossier_financials`) not yet measured on live runs.** Employee_count/revenue gap types had 0% hit rate before; regex extraction is the fix.

### Historical (fixed)
14. **`search_web` calls appear in historical data** with 0% hit rate. Broken stub removed from registry.
15. **`get_similar_employers` failed on runs 66-70** due to dropped materialized view. Rebuilt 2026-02-24.
16. **`exec_compensation` was never filled.** Now addressed by `search_sec_proxy` tool (Resolved #6).

## 11. File Map

```
scripts/research/
    agent.py          (2,267 lines)  Core orchestration: Gemini loop, web merge, validation
    tools.py          (2,189 lines)  14 tool implementations + TOOL_REGISTRY + TOOL_DEFINITIONS
    auto_grader.py      (457 lines)  5-dimension quality grading
    __init__.py           (2 lines)

api/routers/
    research.py                      REST endpoints for starting/monitoring/viewing runs

scripts/analysis/
    research_diagnostic.py           Overall metrics report (run: py scripts/analysis/research_diagnostic.py)
    research_dossier_audit.py        Per-run field completeness audit
    research_gap_analysis.py         Web search effectiveness analysis

tests/
    test_research_agent_52.py        45 tests for agent logic
    test_research_scraper.py         21 tests for scraper/URL resolution
    test_auto_grader.py              32 tests for grading system
```

## 12. How to Run Diagnostics

```bash
# Overall metrics
py scripts/analysis/research_diagnostic.py
py scripts/analysis/research_diagnostic.py --recent 10

# Per-run field audit
py scripts/analysis/research_dossier_audit.py --recent 5
py scripts/analysis/research_dossier_audit.py --run-id 70

# Web search effectiveness
py scripts/analysis/research_gap_analysis.py

# Re-grade all runs
py scripts/research/auto_grader.py

# Run tests
py -m pytest tests/test_research_agent_52.py tests/test_research_scraper.py tests/test_auto_grader.py -v
```

## 13. Open Design Questions

1. ~~**Should we add a job posting scraper?**~~ **Implemented** as `search_job_postings` using Google Search grounding. Not yet measured on live runs.
2. ~~**Should we add SEC proxy statement parsing?**~~ **Implemented** as `search_sec_proxy`. Not yet validated for accuracy.
3. **Should consistency scoring cross-check DB vs web?** e.g., DB says 0 OSHA violations but web says "OSHA fined them $500K." Not yet implemented.
4. ~~**Should the scraper visit more pages?**~~ Claimed as expanded to include /locations, /contact, /investors (Resolved #2). Needs verification on live runs.
5. ~~**Should we add a second Gemini pass?**~~ **Implemented** as `_fill_dossier_gaps`. Adds ~$0.01/run. Not yet measured.
6. **Should `get_workforce_demographics` use real BLS data?** Currently hardcoded for 6 industries. Phase 6 placeholder.
7. **How accurate is `search_sec_proxy`?** Uses Gemini web search to find proxy statements — needs validation against known SEC filings (e.g., Apple, Amazon).
8. **What is the real cost impact of the 3 new Gemini calls?** `search_sec_proxy` + `search_job_postings` (Phase 1) + `_fill_dossier_gaps` (post-merge) could add ~$0.02-0.03/run.
