# Research Agent: Comprehensive Reference & Scorecard Integration Guide

> **Purpose:** Complete inventory of the research agent's capabilities, data flows, and
> integration with the scorecard system. The strategic vision: initial scorecard scoring
> signals which employers deserve deeper investigation, research runs fill in the blanks,
> and the more columns of research that are filled, the closer to a **Gold Standard** profile.
>
> **Updated:** 2026-02-27 — Includes Phase 5.1-5.7 completions, research-to-scorecard
> feedback loop, target scorecard integration roadmap, and Gold Standard model.

---

## Table of Contents

1. [Strategic Vision: Scoring → Research → Gold Standard](#1-strategic-vision)
2. [Architecture Overview](#2-architecture-overview)
3. [The 14 Research Tools](#3-the-14-research-tools)
4. [Database Schema (7 Tables)](#4-database-schema)
5. [Dossier Structure (7 Sections, 72 Attributes)](#5-dossier-structure)
6. [Auto-Grader (6 Dimensions)](#6-auto-grader)
7. [Research-to-Scorecard Feedback Loop](#7-feedback-loop)
8. [Gold Standard Model](#8-gold-standard-model)
9. [API Endpoints](#9-api-endpoints)
10. [Crawl4AI Web Scraper](#10-crawl4ai-web-scraper)
11. [Configuration & Environment](#11-configuration)
12. [Test Coverage](#12-test-coverage)
13. [Integration Roadmap: Target Scorecard](#13-target-scorecard-integration)
14. [Performance Metrics](#14-performance-metrics)
15. [Known Issues & Open Questions](#15-known-issues)
16. [File Map & Diagnostics](#16-file-map)

---

## 1. Strategic Vision: Scoring → Research → Gold Standard

The platform operates in two phases for every employer:

### Phase A: Signal Detection (Scorecard — fast, broad, shallow)

The initial scorecard assigns 0-10 scores across 8 signal dimensions using **only
structured database data** (OSHA, NLRB, WHD, contracts, financials, BLS, size). This is
fast and covers millions of employers, but inherently incomplete. 49% of F7 employers
have zero external data sources. The scorecard tells you *who* is worth looking at — it
does NOT tell you enough to plan a campaign.

### Phase B: Deep Investigation (Research Agent — slow, targeted, deep)

The research agent performs a 25-turn deep dive using 14 tools: 6 enforcement/corporate
databases, 3 industry/comparable tools, and 5 web/external tools. It fills in the gaps
that make the difference: employee counts, revenue, executive pay, job postings, labor
news, website intelligence, workforce composition, and — critically — a synthesized
organizing assessment narrative.

### Phase C: Gold Standard Convergence

Each research column filled moves the employer profile closer to a **Gold Standard** — a
complete, multi-source, cross-validated profile where an organizer can make a confident
go/no-go decision. The quality score (0-10) measures how close to Gold Standard a profile
is. Research findings feed back into the scorecard via `research_score_enhancements`,
upgrading factor scores where research found better data than the DB alone provided.

```
  Structured DB Data          Research Agent              Gold Standard
  ┌─────────────────┐     ┌──────────────────┐     ┌──────────────────────┐
  │ OSHA violations  │     │ 14 tools run     │     │ All 72 attributes    │
  │ NLRB elections   │     │ Website scraped   │     │ Cross-validated      │
  │ WHD backwages    │ ──► │ Financials found  │ ──► │ Quality >= 7.0       │
  │ Federal contracts│     │ Workforce sized   │     │ Multiple sources     │
  │ (sparse, fast)   │     │ Assessment written│     │ Actionable narrative │
  └─────────────────┘     └──────────────────┘     └──────────────────────┘
      ~2-3 signals             +15-40 facts            72 possible fields
      Coverage: 20-30%         Coverage: 50-80%        Coverage: 80-100%
```

**Key principle:** The scorecard identifies *who* to investigate. The research agent
investigates *deeply*. The more columns filled (and the higher the quality), the more
confidence an organizer has in the recommendation. A Gold Standard profile has enough
data to build an actual organizing plan, not just a hunch.

---

## 2. Architecture Overview

### Core Files

| File | Size | Purpose |
|------|------|---------|
| `scripts/research/agent.py` | ~117KB, ~3,500 lines | Core orchestration loop (Gemini tool-use → dossier assembly → web merge → validation) |
| `scripts/research/tools.py` | ~97KB, ~2,400 lines | 14 research tools (DB queries, web scraping, Google Search grounding) |
| `scripts/research/auto_grader.py` | ~36KB, ~850 lines | 6-dimension quality grading + scorecard enhancement computation |
| `scripts/research/employer_lookup.py` | ~7KB, ~220 lines | Auto-link research runs to F7 employers (3-tier: exact → prefix → trigram) |
| `api/routers/research.py` | — | 6 API endpoints (run, status, result, runs, candidates, vocabulary) |
| `sql/create_research_agent_tables.sql` | — | 6 table schemas + 72-row vocabulary seed data |
| `scripts/scoring/create_research_enhancements.py` | — | Enhancement table schema + UPSERT logic |

### End-to-End Data Flow

```
User/System triggers research run
    │
    ▼
research_runs (status='pending')
    │
    ▼
agent.py: Phase 1 — Tool-Use Loop (up to 25 Gemini turns)
    │
    ├── Tool calls dispatched to tools.py
    │   ├── 6 DB enforcement/corporate tools (OSHA, NLRB, WHD, SEC, SAM, 990)
    │   ├── 3 industry/comparable tools (contracts, BLS profile, similar employers)
    │   ├── 2 business data tools (Mergent, employer website scraper)
    │   ├── 2 Google Search grounding tools (SEC proxy, job postings)
    │   └── 1 demographics baseline tool
    │   │
    │   └── Results cached 7 days per (employer_id, tool_name)
    │
    ├── research_actions logged (per-tool audit trail)
    ├── research_facts saved (individual facts with provenance)
    │
    ▼
agent.py: Phase 1.5 — Forced Scraper (if Gemini didn't call it)
    │   └── Crawl4AI: homepage + /about + /careers + /news + /locations + /investors
    │
    ▼
agent.py: Phase 2 — Web Search (separate Gemini call with Google Search grounding)
    │   └── Gap-aware queries built from Phase 1 misses (8-15 targeted queries)
    │
    ▼
agent.py: Phase 3 — Web Merge (deterministic, no LLM)
    │   └── Parse web JSON → map to vocabulary → regex fallback for financials
    │
    ▼
agent.py: Phase 4 — Post-Merge Validation (deterministic)
    │   └── Copy facts to dossier body where missing, log remaining gaps
    │
    ▼
Dossier JSON assembled (7 sections, up to 72 attributes)
    │
    ▼
auto_grader.py: Grade Quality (6 dimensions → weighted 0-10 overall)
    │
    ▼
research_runs.overall_quality_score + quality_dimensions UPDATED
    │
    ├── Quality < 7.0  →  STOP (too sparse/unreliable for scorecard)
    │
    ▼ Quality >= 7.0 AND employer_id NOT NULL
auto_grader.py: compute_research_enhancements()
    │   ├── Extract 6 factor scores from dossier (OSHA, NLRB, WHD, contracts, financial, size)
    │   ├── Extract assessment fields (approach, strengths, challenges, contradictions, trend)
    │   └── Extract raw values (violations found, employee count, revenue, etc.)
    │
    ▼
research_score_enhancements UPSERT (one row per employer, only if quality >= existing)
    │
    ▼
mv_unified_scorecard REFRESH (LEFT JOIN picks up enhancements)
    │   ├── GREATEST(DB_score, research_score) per factor
    │   ├── has_research, research_quality, strategic_delta columns
    │   └── research_approach, research_trend, research_contradictions columns
    │
    ▼
API returns enhanced scores + delta + research narrative to frontend
```

---

## 3. The 14 Research Tools

All tools return a standardized response dict:
```python
{
    "found": bool,          # Whether any data was found
    "source": str,          # e.g., "database:osha_violations_detail"
    "summary": str,         # Human-readable one-paragraph summary
    "data": dict,           # Structured findings (varies per tool)
    "error": str | None     # Only present on failure
}
```

### 3.1 Enforcement Tools

#### Tool 1: `search_osha`
- **Source:** `database:osha_violations_detail`, `osha_inspections`
- **Match paths:** `osha_f7_matches` table → `unified_match_log` (source_system='osha') → name LIKE fallback + RapidFuzz (>=0.50) post-filter
- **Key outputs:** `violation_count`, `serious_count`, `willful_count`, `repeat_count`, `penalty_total`, `inspection_count`, `establishment_count`, `most_recent_date`, `top_violation_types` (5), `accidents` (10)
- **Hit rate:** 87% | **Avg latency:** 915ms
- **Dossier contribution:** `osha_violation_count`, `osha_violation_details`, `osha_penalty_total`, `osha_serious_count`, `safety_incidents`

#### Tool 2: `search_nlrb`
- **Source:** `database:nlrb_cases` (elections + ULP)
- **Match paths:** `nlrb_employer_xref` → `nlrb_participants.matched_employer_id` → name LIKE + RapidFuzz
- **Key outputs:** `election_count`, `elections` (up to 20 with vote margins, union names), `wins`, `losses`, `ulp_count`, `ulp_cases` (up to 20), `ulp_allegations` (30), `voluntary_recognitions`, `unions_involved`, `total_cases`
- **Deduplication:** Groups by case_number to avoid duplicate elections
- **Hit rate:** 75% | **Avg latency:** 645ms
- **Dossier contribution:** `nlrb_election_count`, `nlrb_election_details`, `nlrb_ulp_count`, `nlrb_ulp_details`, `recent_organizing`, `voluntary_recognition`

#### Tool 3: `search_whd`
- **Source:** `database:whd_cases`
- **Match paths:** `whd_f7_matches` → `unified_match_log` (source_system='whd') → name LIKE on `legal_name` OR `trade_name` (dual-clause) + RapidFuzz
- **Key outputs:** `case_count`, `total_backwages`, `total_penalties`, `employees_affected`, `is_repeat_violator`, `child_labor_violations`, `child_labor_minors`, `flsa_violation_count`, `overtime_backwages`, `min_wage_backwages`, `earliest_date`, `latest_date`, `trade_names`
- **Hit rate:** 74% | **Avg latency:** 594ms
- **Dossier contribution:** `whd_case_count`, `whd_backwages`, `whd_penalties`, `whd_employees_affected`, `whd_repeat_violator`

### 3.2 Corporate Tools

#### Tool 4: `search_sec`
- **Source:** `database:sec_companies` + `corporate_identifier_crosswalk`
- **Type check:** Skips non-public companies (private, nonprofit)
- **Match paths:** crosswalk (sec_cik) → LIKE on company_name (prefer is_public, shorter names)
- **Crosswalk enrichment:** federal_contractor flag, obligations, contract_count
- **Key outputs:** `cik`, `company_name`, `ticker`, `exchange`, `sic_code`, `sic_description`, `state`, `is_public`, `ein`, `federal_contractor`, `federal_obligations`
- **Hit rate:** 81% | **Avg latency:** 495ms
- **Dossier contribution:** `company_type`, `federal_contract_status`

#### Tool 5: `search_sam`
- **Source:** `database:sam_entities` + `federal_contract_recipients`
- **Match paths:** `unified_match_log` (source_system='sam', source_id=uei) → LIKE on `legal_business_name` + RapidFuzz
- **Contract enrichment:** Joins `federal_contract_recipients` for total_obligations, contract_count, latest_year
- **Key outputs:** `is_federal_contractor`, `uei`, `legal_name`, `dba_name`, `status_active`, `registration_date`, `naics_primary`, `naics_all`, `entity_structure`, `total_obligations`, `total_contracts`, `latest_contract_year`
- **Hit rate:** 57% | **Avg latency:** 470ms
- **Dossier contribution:** `federal_obligations`, `federal_contract_count`, `federal_contract_status`

#### Tool 6: `search_990`
- **Source:** `database:national_990_filers`
- **Type check:** Skips public companies (they don't file 990s)
- **Match paths:** `national_990_f7_matches` table → LIKE on `business_name`
- **Key outputs:** `ein`, `business_name`, `total_revenue`, `total_assets`, `total_expenses`, `total_employees`, `tax_year`, `form_type`, `ntee_code`, `years_available`
- **Hit rate:** 82% (for nonprofits) | **Avg latency:** 484ms
- **Dossier contribution:** `nonprofit_revenue`, `nonprofit_assets`, `employee_count`, `revenue`

### 3.3 Industry & Comparables Tools

#### Tool 7: `search_contracts`
- **Source:** `database:f7_union_employer_relations` + `unions_master`
- **Match paths:** employer_id direct → name LIKE + RapidFuzz
- **Key outputs:** `has_contracts`, `contract_count`, `contracts` (up to 20), `union_names`, `affiliations`, `total_workers_covered`, `distinct_unions`
- **Hit rate:** 78% | **Avg latency:** 221ms
- **Dossier contribution:** `existing_contracts`, `union_names`

#### Tool 8: `get_industry_profile`
- **Source:** `database:bls_industry_occupation_matrix` + `bls_state_density`
- **Requires:** NAICS code (cascading fallback: 6-digit → 4-digit → 3-digit → 2-digit)
- **Hard-coded NAICS→density sector mapping** (23→CONST, 31-33→MFG, 62→EDU_HEALTH, etc.)
- **Key outputs:** `naics_code`, `bls_industry_code`, `top_occupations` (10 by employment %), `pay_ranges` (occupation, soc_code, median_annual_wage, typical_education), `national_density`, `state_density`
- **Hit rate:** 100% | **Avg latency:** 50ms
- **Dossier contribution:** `workforce_composition`, `pay_ranges`

#### Tool 9: `get_similar_employers`
- **Source:** `database:f7_employers_deduped` + `mv_unified_scorecard` + `nlrb_elections`
- **Logic:** F7 employers with union contracts in same 4-digit NAICS, ordered by weighted_score DESC
- **Bonus:** Recent NLRB elections in similar industries (last 3 years)
- **Key outputs:** `similar_employers` (10), `naics_prefix`, `recent_industry_elections` (10)
- **Hit rate:** 90% | **Avg latency:** 345ms
- **Dossier contribution:** `similar_organized`

### 3.4 External & Web Tools

#### Tool 10: `search_mergent`
- **Source:** `database:mergent_employers` + `unified_match_log`
- **Match paths:** unified_match_log (source_system='mergent', source_id=duns) → LIKE on `company_name` + RapidFuzz
- **Key outputs:** `company_name`, `duns`, `ein`, `employees_site`, `employees_all_sites`, `sales_amount`, `parent_name`, `domestic_parent_name`, `year_founded`, `company_type`, `subsidiary_status`, `website`, `minority_owned`, `line_of_business`, `former_name`, `trade_name`
- **Hit rate:** 39% (low — only 1,045 matched) | **Avg latency:** 852ms
- **Dossier contribution:** `employee_count`, `revenue`, `parent_company`, `year_founded`, `website_url`, `major_locations`

#### Tool 11: `search_web` (stub — removed)
- Web search is handled entirely by Gemini Google Search grounding in Phase 2 (separate API call). If Gemini tries to call `search_web` during Phase 1, it's silently rejected.

#### Tool 12: `scrape_employer_website`
- **Source:** Live web via Crawl4AI async scraper
- **URL resolution (4-tier):** provided URL → Mergent DB (via employer_id) → Mergent name search → Google Search fallback (~$0.001)
- **7 page types:** homepage (3KB), about (2.5KB), careers (1.5KB), news (1KB), locations (1KB), contact (1KB), investors (1.5KB). Total budget: 12KB.
- **Timeout:** 35 seconds. Multiple paths tried per page type (e.g., /about, /about-us, /company, /our-story).
- **Key outputs:** `url`, `url_source`, `homepage_text`, `about_text`, `careers_text`, `news_text`, `locations_text`, `contact_text`, `investors_text`, `pages_scraped`, `total_chars`
- **Hit rate:** 19% (fails often due to URL resolution) | **Avg latency:** 2,686ms
- **Dossier contribution:** `website_url`, `major_locations`, `turnover_signals`, `recent_labor_news`, identity fields

#### Tool 13: `search_sec_proxy`
- **Source:** Gemini Google Search grounding → SEC EDGAR DEF 14A proxy statement
- **Extraction:** Regex fallback for pipe-delimited or narrative executive pay (name|title|$pay)
- **Key outputs:** `executives` (list of {name, title, total_pay}), `year`
- **Avg latency:** ~2,000ms
- **Dossier contribution:** `exec_compensation`

#### Tool 14: `search_job_postings`
- **Source:** Gemini Google Search grounding (major job boards)
- **Extraction:** Regex fallback for count patterns ("approximately 5,000 positions") and sample titles
- **Key outputs:** `count_estimate`, `sample_postings` (list of {title, location, pay})
- **Avg latency:** ~2,000ms
- **Dossier contribution:** `job_posting_count`, `job_posting_details`

#### Bonus Tool: `get_workforce_demographics`
- **Source:** Hard-coded BLS industry baselines by NAICS 2-digit (6 industries + generic fallback)
- **Key outputs:** `naics_2`, `demographic_profile`, `demographic_raw`, `is_estimate`, `is_generic_fallback`
- **Latency:** <5ms
- **Dossier contribution:** `demographic_profile`
- **Note:** Placeholder for Phase 6 — uses static data, not real BLS queries.

### 3.5 Tool Summary Matrix

| # | Tool | Source Type | Match Strategy | Hit Rate | Latency | Primary Dossier Fields |
|---|------|-----------|---------------|----------|---------|----------------------|
| 1 | search_osha | database | F7 match → UML → name LIKE | 87% | 915ms | osha_violation_count, osha_penalty_total, safety_incidents |
| 2 | search_nlrb | database | employer xref → participant match → name LIKE | 75% | 645ms | nlrb_election_count, nlrb_ulp_count, recent_organizing |
| 3 | search_whd | database | F7 match → UML → dual name LIKE | 74% | 594ms | whd_case_count, whd_backwages, whd_repeat_violator |
| 4 | search_sec | database+crosswalk | crosswalk CIK → name LIKE | 81% | 495ms | company_type, federal_contract_status |
| 5 | search_sam | database | UML → name LIKE | 57% | 470ms | federal_obligations, federal_contract_count |
| 6 | search_990 | database | 990 match table → name LIKE | 82% | 484ms | nonprofit_revenue, employee_count |
| 7 | search_contracts | database | employer_id → name LIKE | 78% | 221ms | existing_contracts, union_names |
| 8 | get_industry_profile | database (BLS) | NAICS code | 100% | 50ms | workforce_composition, pay_ranges |
| 9 | get_similar_employers | database (F7+MV) | NAICS 4-digit | 90% | 345ms | similar_organized |
| 10 | search_mergent | database | UML → name LIKE | 39% | 852ms | employee_count, revenue, parent_company |
| 11 | search_web | (removed) | — | 0% | — | — |
| 12 | scrape_employer_website | web (Crawl4AI) | 4-tier URL resolution | 19% | 2,686ms | website_url, turnover_signals, recent_labor_news |
| 13 | search_sec_proxy | web (Gemini+Google) | Google Search grounding | NEW | ~2,000ms | exec_compensation |
| 14 | search_job_postings | web (Gemini+Google) | Google Search grounding | NEW | ~2,000ms | job_posting_count, job_posting_details |
| B | get_workforce_demographics | hardcoded | NAICS 2-digit lookup | 100% | <5ms | demographic_profile |

### 3.6 Helper Functions in tools.py

| Function | Purpose |
|----------|---------|
| `_conn()` | Get RealDictCursor connection |
| `_safe(val)` / `_safe_dict(d)` / `_safe_list(rows)` | JSON-safe type conversion (Decimal, datetime) |
| `_error_result(source, err)` | Standardized error response |
| `_make_acronym(company_name)` | Generate acronym (e.g., "UPMC" from "University of Pittsburgh Medical Center") |
| `_name_like_clause(column, company_name)` | Flexible LIKE clause handling spaces and acronyms (e.g., "Fed Ex" → "FEDEX") |
| `_filter_by_name_similarity(rows, name, threshold=0.50)` | RapidFuzz post-filter to remove false positives |
| `_normalize_url(raw)` | Clean URLs from Mergent (e.g., `WWW.COMPANY.COM` → `https://www.company.com`) |
| `_resolve_employer_url(name, url, employer_id, state)` | 4-tier URL resolution (provided → Mergent ID → Mergent name → Google) |
| `_google_search_url(name, industry, state)` | Gemini + Google Search grounding to find official website |
| `_sanitize_markdown(text)` | Replace Unicode chars that break Windows cp1252 |
| `_truncate_markdown(text, limit)` | Truncate at paragraph/sentence/word boundary |
| `_scrape_pages(base_url)` | Async Crawl4AI core (7 page types, 12KB budget, 35s timeout) |
| `_extract_exec_pay_from_text(text)` | Regex fallback for executive compensation |
| `_extract_job_postings_from_text(text)` | Regex fallback for job count and sample titles |

---

## 4. Database Schema (7 Tables)

### 4.1 `research_fact_vocabulary` — Dictionary (72 rows)

Defines the canonical attribute names for all dossier fields.

| Column | Type | Purpose |
|--------|------|---------|
| `id` | SERIAL PK | |
| `attribute_name` | VARCHAR(100) UNIQUE | Machine-readable key (e.g., `employee_count`) |
| `display_name` | VARCHAR(200) | Human-readable label (e.g., "Employee Count") |
| `dossier_section` | VARCHAR(50) | identity/financial/workforce/labor/workplace/assessment/sources |
| `data_type` | VARCHAR(30) | text/number/currency/date/boolean/json |
| `existing_column` | VARCHAR(200) | Maps to existing DB column (if any) |
| `existing_table` | VARCHAR(200) | Source table for existing column |
| `description` | TEXT | What this attribute means |

### 4.2 `research_runs` — One row per deep dive

| Column | Type | Purpose |
|--------|------|---------|
| `id` | SERIAL PK | Run identifier |
| `employer_id` | INTEGER | FK to f7_employers_deduped (NULL if unlinked) |
| `company_name` | VARCHAR(500) NOT NULL | Search target |
| `company_name_normalized` | VARCHAR(500) | Standardized name |
| `industry_naics` | VARCHAR(6) | NAICS code |
| `company_type` | VARCHAR(30) | public/private/nonprofit/government |
| `company_state` | VARCHAR(2) | State abbreviation |
| `employee_size_bucket` | VARCHAR(20) | small/medium/large |
| `status` | VARCHAR(20) NOT NULL | pending → running → completed/failed |
| `started_at` / `completed_at` | TIMESTAMP | Run timing |
| `duration_seconds` | INTEGER | Wall-clock duration |
| `total_tools_called` | INTEGER | Count of tool invocations |
| `total_facts_found` | INTEGER | Count of facts extracted |
| `sections_filled` | INTEGER | Count of dossier sections with data (0-7) |
| `dossier_json` | JSONB | **The complete dossier** (7 sections, up to 72 fields) |
| `total_tokens_used` | INTEGER | Gemini token consumption |
| `total_cost_cents` | INTEGER | Estimated API cost |
| `triggered_by` | VARCHAR(100) | User ID or 'system' |
| `strategy_used` | JSONB | Phase 2+ strategy metadata |
| `overall_quality_score` | DECIMAL(4,2) | Auto-graded 0-10 (the Gold Standard measure) |
| `human_quality_score` | DECIMAL(4,2) | Human override |
| `quality_dimensions` | JSONB | 6-dimension breakdown |
| `current_step` | VARCHAR(200) | Progress UI text |
| `progress_pct` | INTEGER | 0-100 for progress bar |

**Indexes:** employer_id, status, industry_naics, created_at DESC

### 4.3 `research_actions` — Tool call audit trail

| Column | Type | Purpose |
|--------|------|---------|
| `id` | SERIAL PK | |
| `run_id` | INTEGER FK (CASCADE) | Parent run |
| `tool_name` | VARCHAR(100) | Which tool was called |
| `tool_params` | JSONB | Parameters passed |
| `execution_order` | INTEGER | Sequence number (1st, 2nd, ...) |
| `data_found` | BOOLEAN | Did the tool return data? |
| `data_quality` | DECIMAL(3,2) | 0.0-1.0 quality rating |
| `facts_extracted` | INTEGER | Fact count from this call |
| `result_summary` | TEXT | Human-readable summary |
| `latency_ms` | INTEGER | Execution time |
| `cost_cents` | INTEGER | API cost |
| `error_message` | TEXT | Error details (if failed) |
| `company_context` | JSONB | Company state at time of call |

**Indexes:** run_id, tool_name, data_found

### 4.4 `research_facts` — Individual extracted facts

| Column | Type | Purpose |
|--------|------|---------|
| `id` | SERIAL PK | |
| `run_id` | INTEGER FK (CASCADE) | Parent run |
| `action_id` | INTEGER FK | Which tool call produced this |
| `employer_id` | INTEGER | FK to f7_employers_deduped |
| `dossier_section` | VARCHAR(50) | identity/financial/workforce/labor/workplace/assessment/sources |
| `attribute_name` | VARCHAR(100) | FK to vocabulary |
| `attribute_value` | TEXT | Actual value (stored as text) |
| `attribute_value_json` | JSONB | Complex values (lists, nested objects) |
| `source_url` | TEXT | URL or "database:table_name" |
| `source_type` | VARCHAR(30) | database/web_search/web_scrape/news/api |
| `source_name` | VARCHAR(200) | Human-readable source |
| `confidence` | DECIMAL(3,2) | 0.0-1.0 confidence rating |
| `as_of_date` | DATE | When this fact was current |
| `contradicts_fact_id` | INTEGER | Self-FK for contradictions |

**Indexes:** run_id, employer_id, dossier_section, attribute_name

### 4.5 `research_score_enhancements` — Feedback bridge to scorecard

**One row per employer.** Only populated when a research run scores >= 7.0 quality.

| Column | Type | Purpose |
|--------|------|---------|
| `id` | SERIAL PK | |
| `employer_id` | TEXT UNIQUE | One enhancement per employer |
| `run_id` | INTEGER FK | Best research run for this employer |
| `run_quality` | NUMERIC(4,2) | Quality score from auto-grader |
| `is_union_reference` | BOOLEAN | Union (Path A) vs non-union (Path B) |
| **Factor Scores (0-10, nullable):** | | |
| `score_osha` | NUMERIC(4,2) | Research-derived OSHA signal score |
| `score_nlrb` | NUMERIC(4,2) | Research-derived NLRB signal score |
| `score_whd` | NUMERIC(4,2) | Research-derived WHD signal score |
| `score_contracts` | NUMERIC(4,2) | Research-derived contracts signal score |
| `score_financial` | NUMERIC(4,2) | Research-derived financial signal score |
| `score_size` | NUMERIC(4,2) | Research-derived size signal score |
| `score_stability` | NUMERIC(4,2) | Stability pillar (Phase 1) |
| `score_anger` | NUMERIC(4,2) | Anger/motivation pillar (Phase 1) |
| **Raw Extracted Values:** | | |
| `osha_violations_found` | INTEGER | Actual violation count found |
| `osha_serious_found` | INTEGER | Serious violations found |
| `osha_penalty_total_found` | NUMERIC | Total penalties found |
| `nlrb_elections_found` | INTEGER | Election count found |
| `nlrb_ulp_found` | INTEGER | ULP count found |
| `whd_cases_found` | INTEGER | WHD case count found |
| `employee_count_found` | INTEGER | Employee count found |
| `revenue_found` | BIGINT | Revenue found |
| `federal_obligations_found` | BIGINT | Federal contract dollars found |
| `year_founded_found` | INTEGER | Year founded |
| `naics_found` | VARCHAR(10) | NAICS code found |
| `turnover_rate_found` | NUMERIC(4,2) | Turnover rate (if web-sourced) |
| `sentiment_score_found` | NUMERIC(4,2) | Sentiment score (if web-sourced) |
| `revenue_per_employee_found` | NUMERIC | Revenue-per-employee ratio |
| **Assessment Fields (display, not scored):** | | |
| `recommended_approach` | TEXT | Organizing strategy narrative |
| `campaign_strengths` | JSONB | List of strengths |
| `campaign_challenges` | JSONB | List of challenges |
| `source_contradictions` | JSONB | Conflicting data points |
| `financial_trend` | TEXT | Revenue/growth trajectory narrative |
| `confidence_avg` | NUMERIC(3,2) | Average fact confidence |

**Constraint:** `UNIQUE (employer_id)` — one best run per employer
**UPSERT rule:** Only update if `new_quality >= existing_quality`
**Indexes:** employer_id, is_union_reference (partial WHERE TRUE), run_id

### 4.6 `research_strategies` — Learned tool effectiveness (Phase 2+)

| Column | Type | Purpose |
|--------|------|---------|
| `industry_naics_2digit` | VARCHAR(4) | 2-digit NAICS prefix |
| `company_type` | VARCHAR(30) | public/private/nonprofit/government |
| `company_size_bucket` | VARCHAR(20) | small/medium/large |
| `tool_name` | VARCHAR(100) | Tool that was tried |
| `times_tried` / `times_found_data` | INTEGER | Usage + success counts |
| `hit_rate` | DECIMAL(5,4) | Success rate |
| `avg_quality` | DECIMAL(3,2) | Avg quality when tool found data |
| `avg_latency_ms` | INTEGER | Average execution time |
| `recommended_order` | INTEGER | Suggested call order |

**Constraint:** UNIQUE(industry_naics_2digit, company_type, company_size_bucket, tool_name)

### 4.7 `research_query_effectiveness` — Web search learning (Phase 5.2)

| Column | Type | Purpose |
|--------|------|---------|
| `gap_type` | TEXT | e.g., employee_count, revenue, nlrb_activity |
| `company_type` | VARCHAR(30) | Segmentation (NULL = all) |
| `industry_sector` | VARCHAR(10) | 2-digit NAICS (NULL = all) |
| `query_template` | TEXT | Template with {company} placeholder |
| `times_used` / `times_produced_result` | INTEGER | Usage + success counts |
| `avg_facts_produced` | REAL | Average yield |

**Constraint:** UNIQUE(gap_type, query_template)

---

## 5. Dossier Structure (7 Sections, 72 Attributes)

The dossier is stored as JSON in `research_runs.dossier_json`. Each section maps to vocabulary attributes. **The more filled, the closer to Gold Standard.**

### Section 1: Identity (10 attributes)
| Attribute | Type | Primary Tool Sources |
|-----------|------|---------------------|
| `legal_name` | text | search_sec, search_sam, search_mergent |
| `dba_names` | json | search_whd (trade_names), search_mergent |
| `parent_company` | text | search_mergent (parent_name) |
| `naics_code` | text | search_sam, search_mergent, get_industry_profile |
| `naics_description` | text | get_industry_profile |
| `hq_address` | json | search_mergent, scrape_employer_website |
| `company_type` | text | search_sec (public), search_990 (nonprofit) |
| `website_url` | text | scrape_employer_website, search_mergent |
| `year_founded` | number | search_mergent |
| `major_locations` | json | scrape_employer_website (locations page) |

### Section 2: Financial (10 attributes)
| Attribute | Type | Primary Tool Sources |
|-----------|------|---------------------|
| `employee_count` | number | search_mergent, search_990, scrape_employer_website |
| `revenue` | currency | search_mergent (sales_amount), search_990 (total_revenue) |
| `revenue_range` | text | Derived from revenue |
| `financial_trend` | text | scrape_employer_website (investors), web search |
| `exec_compensation` | json | search_sec_proxy (DEF 14A) |
| `federal_obligations` | currency | search_sam, search_sec (crosswalk) |
| `federal_contract_count` | number | search_sam, search_sec (crosswalk) |
| `nonprofit_revenue` | currency | search_990 |
| `nonprofit_assets` | currency | search_990 |
| `federal_contract_status` | text | search_sam (active/inactive) |

### Section 3: Workforce (6 attributes)
| Attribute | Type | Primary Tool Sources |
|-----------|------|---------------------|
| `workforce_composition` | json | get_industry_profile, get_workforce_demographics |
| `pay_ranges` | json | get_industry_profile (BLS wage data) |
| `job_posting_count` | number | search_job_postings |
| `job_posting_details` | json | search_job_postings (titles, locations, pay) |
| `turnover_signals` | text | scrape_employer_website (careers page patterns) |
| `demographic_profile` | json | get_workforce_demographics (BLS baselines) |

### Section 4: Labor (8 attributes)
| Attribute | Type | Primary Tool Sources |
|-----------|------|---------------------|
| `existing_contracts` | json | search_contracts |
| `union_names` | json | search_contracts, search_nlrb |
| `nlrb_election_count` | number | search_nlrb |
| `nlrb_election_details` | json | search_nlrb (vote margins, dates, unions) |
| `nlrb_ulp_count` | number | search_nlrb (CA case type) |
| `nlrb_ulp_details` | json | search_nlrb (allegations, dates) |
| `recent_organizing` | json | search_nlrb, web search |
| `voluntary_recognition` | json | search_nlrb |

### Section 5: Workplace (12 attributes)
| Attribute | Type | Primary Tool Sources |
|-----------|------|---------------------|
| `osha_violation_count` | number | search_osha |
| `osha_violation_details` | json | search_osha (types, dates, penalties) |
| `osha_penalty_total` | currency | search_osha |
| `osha_serious_count` | number | search_osha |
| `whd_case_count` | number | search_whd |
| `whd_backwages` | currency | search_whd |
| `whd_penalties` | currency | search_whd |
| `whd_employees_affected` | number | search_whd |
| `whd_repeat_violator` | boolean | search_whd |
| `safety_incidents` | json | search_osha (accidents) |
| `worker_complaints` | text | web search, scrape_employer_website (news) |
| `recent_labor_news` | json | web search, scrape_employer_website (news page) |

### Section 6: Assessment (5+ attributes)
| Attribute | Type | Primary Tool Sources |
|-----------|------|---------------------|
| `organizing_summary` | text | Gemini synthesis (all tools) |
| `campaign_strengths` | json | Gemini synthesis |
| `campaign_challenges` | json | Gemini synthesis |
| `similar_organized` | json | get_similar_employers |
| `recommended_approach` | text | Gemini synthesis |
| `data_summary` | text | Gemini synthesis |
| `web_intelligence` | text | Web findings beyond DB records |
| `source_contradictions` | json | Cross-source validation |
| `data_gaps` | json | Missing/unverifiable information |

### Section 7: Sources (3 attributes)
| Attribute | Type | Primary Tool Sources |
|-----------|------|---------------------|
| `section_confidence` | json | Per-section confidence (high/medium/low) |
| `data_gaps` | json | What was NOT found |
| `source_list` | json | Every source checked with types + timestamps |

---

## 6. Auto-Grader (6 Dimensions)

File: `scripts/research/auto_grader.py`

The auto-grader runs after every completed research run. It produces a quality score
(0-10) that serves two purposes:
1. **Quality gate for scorecard enhancement** (>= 7.0 required)
2. **Gold Standard measure** (how complete and reliable is this profile?)

### 6.1 Dimension Weights (Phase 5.7 — D16 Decision)

| Dimension | Weight | What it Measures | Avg Score |
|-----------|--------|-----------------|-----------|
| **Source Quality** | 35% | Are facts from authoritative sources? | 7.90 |
| **Coverage** | 20% | How many of 72 attributes were filled? | 7.02 |
| **Actionability** | 15% | Does it give organizers a clear strategy? | varies |
| **Consistency** | 15% | Do sources agree? Any contradictions? | 10.00 |
| **Freshness** | 10% | How recent is the data? | 4.84 |
| **Efficiency** | 5% | How many facts per tool call? | 8.28 |

### 6.2 Scoring Details

**Source Quality (0-10, weight 35%):**
```
Source type ranks:
  database    = 1.0  (most reliable — OSHA, NLRB, WHD, SEC, etc.)
  api         = 0.9  (SEC EDGAR API, SAM API)
  web_scrape  = 0.7  (employer website)
  web_search  = 0.6  (Google Search results)
  news        = 0.5  (news articles)

Score = (0.5 * avg_source_rank + 0.5 * avg_confidence) * 10
Penalty: >30% facts missing source_name → -1.0
```

**Coverage (0-10, weight 20%):**
```
Score = (filled_fields / total_fields) * 10
Penalty: -0.5 per placeholder value (e.g., "N/A", "Unknown", "Not available")
Max penalty: -2.0
```

**Actionability (0-10, weight 15%) — NEW Phase 5.7:**
```
Bonuses (additive):
  + recommended_approach present and >50 chars:     +3.0
  + campaign_strengths list with 3+ items:           +2.0
  + campaign_challenges list with 3+ items:          +2.0
  + source_contradictions non-null:                  +1.0
  + financial_trend non-null:                        +1.0
  + exec_compensation non-null (public companies):   +1.0
Cap: 10.0
```

**Consistency (0-10, weight 15%):**
```
Base = 10.0
Penalties:
  - Each contradicted fact:                          -2.0
  - Employee count >2x spread across sources:        -2.0
  - Revenue >2x spread across sources:               -2.0
  - DB says 0 violations but web mentions violations: -1.0 per (max -4.0)
  - DB says no NLRB but web mentions organizing:     -0.5
Floor: 0.0
```

**Freshness (0-10, weight 10%):**
```
Per-fact score by age:
  < 6 months:  10
  6-12 months:  8
  1-2 years:    6
  2-3 years:    4
  3-5 years:    2
  > 5 years:    1
  No date:      5 (neutral)

Score = average across all facts
```

**Efficiency (0-10, weight 5%):**
```
Facts per tool call:
  >= 3:   10
  >= 2:    8
  >= 1:    6
  >= 0.5:  4
  < 0.5:   2
Speed bonus: avg latency < 500ms → +1.0
Cap: 10.0
```

### 6.3 Overall Quality Score (Weighted)

```
overall = (coverage     * 0.20)
        + (source_quality * 0.35)
        + (consistency    * 0.15)
        + (actionability  * 0.15)
        + (freshness      * 0.10)
        + (efficiency     * 0.05)
```

**Current average across 68 completed runs: 7.81/10**

### 6.4 Quality Gate

**Minimum threshold for scorecard enhancement: overall_quality_score >= 7.0 AND employer_id IS NOT NULL**

Below 7.0, the research is too sparse or unreliable to upgrade the scorecard. The dossier
is still saved and accessible for human review, but it won't change any scores.

---

## 7. Research-to-Scorecard Feedback Loop

File: `scripts/research/auto_grader.py` → `compute_research_enhancements(run_id)`

### 7.1 Factor Score Formulas (dossier → 0-10 score)

| Factor | Formula | Notes |
|--------|---------|-------|
| **score_osha** | `violations / 2.23 (industry avg) + serious_boost`, capped at 10 | Industry-normalized |
| **score_nlrb** | `elections*2 + ULP_boost (1→2, 2-3→4, 4-9→6, 10+→8)`, capped at 10 | Combines elections + ULP |
| **score_whd** | Tiered: `1 case→5, 2-3→7, 4+→10` | Step function |
| **score_contracts** | Fed obligation tiers: `<100K→2, <1M→4, <10M→6, <100M→8, >=100M→10` | Dollar thresholds |
| **score_financial** | Revenue + employee count combination | Multi-factor |
| **score_size** | Linear scale: `15-500 employees (0→10)` | Sweet spot model |

**Important:** If research finds 0 for a metric (e.g., 0 OSHA violations), it does NOT
override the DB-derived score. Only positive findings upgrade scores.

### 7.2 UPSERT Strategy

```sql
INSERT INTO research_score_enhancements (employer_id, run_id, run_quality, ...)
ON CONFLICT (employer_id) DO UPDATE SET
  run_id = EXCLUDED.run_id,
  run_quality = EXCLUDED.run_quality,
  score_osha = COALESCE(EXCLUDED.score_osha, existing.score_osha),
  -- NULL-preserving: new NULLs don't overwrite old data
  ...
WHERE EXCLUDED.run_quality >= COALESCE(existing.run_quality, 0)
  -- Only update if new run has equal or better quality
```

### 7.3 Scorecard MV Integration

The unified scorecard MV (`mv_unified_scorecard`) LEFT JOINs `research_score_enhancements`
and applies **GREATEST()** logic — taking the higher of DB-derived or research-derived
scores for each factor:

```sql
-- Enhanced factors (research can only UPGRADE, never downgrade)
GREATEST(db_score_osha,      rse.score_osha)      AS enh_score_osha,
GREATEST(db_score_nlrb,      rse.score_nlrb)      AS enh_score_nlrb,
GREATEST(db_score_whd,       rse.score_whd)       AS enh_score_whd,
GREATEST(db_score_contracts,  rse.score_contracts)  AS enh_score_contracts,
GREATEST(db_score_financial,  rse.score_financial)  AS enh_score_financial,
COALESCE(db_score_size,       rse.score_size)       AS enh_score_size
```

### 7.4 Research Columns on Unified Scorecard MV

| Column | Type | Source |
|--------|------|--------|
| `has_research` | BOOLEAN | `rse.run_id IS NOT NULL` |
| `research_run_id` | INTEGER | `rse.run_id` |
| `research_quality` | NUMERIC(4,2) | `rse.run_quality` |
| `strategic_delta` | NUMERIC(4,2) | `weighted_score - legacy_weighted_score` |
| `research_approach` | TEXT | `rse.recommended_approach` |
| `research_trend` | TEXT | `rse.financial_trend` |
| `research_contradictions` | JSONB | `rse.source_contradictions` |

**Indexed:** `idx_mv_us_has_research` on (has_research) WHERE has_research = TRUE

### 7.5 How `strategic_delta` is Computed

```sql
ROUND((weighted_score - COALESCE(legacy_weighted_score, 0))::numeric, 2)
    AS strategic_delta
```

- `weighted_score` = New 3-pillar model (Anger, Stability, Leverage)
- `legacy_weighted_score` = Old 8-factor weighted model
- Positive delta = new model scores employer higher (more promising)
- Negative delta = new model scores employer lower
- Available for API sorting and filtering

---

## 8. Gold Standard Model

### 8.1 Coverage Tiers

| Tier | Filled Attrs | % of 72 | Profile State | Organizer Confidence |
|------|-------------|---------|---------------|---------------------|
| **Stub** | 0-4 | 0-6% | DB-only, no research. Scorecard signals only. | Low — signals only, can't plan |
| **Bronze** | 5-15 | 7-20% | Partial DB data. 1-2 enforcement signals + basic identity. | Low-Medium — interesting but thin |
| **Silver** | 16-35 | 22-49% | Partial research. Key financials + some enforcement detail. Assessment section thin. | Medium — enough to warrant deeper look |
| **Gold** | 36-54 | 50-75% | Solid research. Financials, enforcement, workforce all covered. Assessment narrative complete. | High — can start planning a campaign |
| **Platinum** | 55-72 | 76-100% | Exceptional. Cross-validated. Multiple web sources. Exec pay. Job postings. Full assessment. | Very High — full campaign intelligence |

### 8.2 Quality + Coverage Matrix

The Gold Standard isn't just about filling fields — it's about quality:

```
                        Quality Score
                    Low (<5)    Medium (5-7)    High (7-10)
Coverage   Low     +----------+-------------+-----------+
           (0-20%) | Stub     | Incomplete  | Sparse+OK |
                   +----------+-------------+-----------+
           Medium  | Noisy    | Working     | Strong    |
           (20-50%)| Profile  | Draft       | Profile   |
                   +----------+-------------+-----------+
           High    | Junk     | Nearly      | * GOLD *  |
           (50%+)  | (rare)   | There       | STANDARD  |
                   +----------+-------------+-----------+
```

**Gold Standard = Coverage >= 50% AND Quality >= 7.0**

### 8.3 What Makes a Gold Standard Profile

An employer profile reaches Gold Standard when:

1. **Identity verified:** Legal name, company type, NAICS, HQ, website — all confirmed from 2+ sources
2. **Financials validated:** Employee count AND revenue from 2+ sources (e.g., Mergent + 990, or Mergent + SEC + web)
3. **Enforcement documented:** All 3 enforcement tools queried (OSHA + NLRB + WHD), even if no findings — "no violations found" is itself valuable data
4. **Federal contractor status:** SAM.gov queried, contract status confirmed or denied
5. **Industry context:** BLS occupation/wage data + union density + similar organized employers listed
6. **Web intelligence:** Website scraped, recent news checked (or confirmed absent)
7. **Assessment actionable:** `recommended_approach` (50+ chars), 3+ strengths, 3+ challenges
8. **Sources transparent:** All data sourced with URLs and confidence ratings per section

### 8.4 Columns That Signal Gold Standard Progress

Each of these columns being non-NULL moves the profile closer to Gold Standard:

**Identity Section (10 columns):**
- [ ] legal_name, dba_names, parent_company, naics_code, naics_description
- [ ] hq_address, company_type, website_url, year_founded, major_locations

**Financial Section (10 columns):**
- [ ] employee_count, revenue, revenue_range, financial_trend, exec_compensation
- [ ] federal_obligations, federal_contract_count, nonprofit_revenue, nonprofit_assets, federal_contract_status

**Workforce Section (6 columns):**
- [ ] workforce_composition, pay_ranges, job_posting_count, job_posting_details
- [ ] turnover_signals, demographic_profile

**Labor Section (8 columns):**
- [ ] existing_contracts, union_names, nlrb_election_count, nlrb_election_details
- [ ] nlrb_ulp_count, nlrb_ulp_details, recent_organizing, voluntary_recognition

**Workplace Section (12 columns):**
- [ ] osha_violation_count, osha_violation_details, osha_penalty_total, osha_serious_count
- [ ] whd_case_count, whd_backwages, whd_penalties, whd_employees_affected
- [ ] whd_repeat_violator, safety_incidents, worker_complaints, recent_labor_news

**Assessment Section (5+ columns):**
- [ ] organizing_summary, campaign_strengths, campaign_challenges
- [ ] similar_organized, recommended_approach

**Sources Section (3 columns):**
- [ ] section_confidence, data_gaps, source_list

### 8.5 How Scoring Drives Research Priority

The `/api/research/candidates` endpoint computes **research priority** as:

```
research_priority = weighted_score * (8 - factors_available)
```

This means:
- **High-scoring employers with thin profiles** rank highest for research
- An employer scoring 7.5 with only 2 factors → priority = 7.5 * 6 = 45
- An employer scoring 4.0 with 6 factors → priority = 4.0 * 2 = 8

The system naturally pushes toward Gold Standard by always investigating the most
promising but least-known employers first. Scorecard signals are the triage layer;
research is the deep dive.

---

## 9. API Endpoints

### `POST /api/research/run`
Start a new research deep dive.
- **Request:** `{ company_name, employer_id?, naics_code?, company_type?, state? }`
- **Response:** `{ run_id, status: "pending", message }`
- Auto-lookup via `employer_lookup.py` if employer_id not provided (3-tier: exact → prefix → trigram match against F7)

### `GET /api/research/status/{run_id}`
Poll progress during a running research.
- **Response:** `{ id, company_name, status, current_step, progress_pct, started_at, completed_at, duration_seconds, total_tools_called, total_facts_found, sections_filled, total_cost_cents, overall_quality_score, quality_dimensions }`

### `GET /api/research/result/{run_id}`
Get completed dossier and all supporting data.
- **Response:** `{ run_id, company_name, status, duration_seconds, sections_filled, total_facts, dossier (JSON), facts_by_section, action_log (tool calls), quality_score, quality_dimensions }`

### `GET /api/research/runs`
List all research runs with filters.
- **Params:** `status`, `employer_id`, `naics`, `q` (company name search), `limit` (default 20), `offset`
- **Sort:** Most recent first (created_at DESC)

### `GET /api/research/candidates`
Suggest employers where research would have the most impact.
- **Params:** `type` (non_union | union_reference), `limit` (default 50)
- **non_union:** High-scoring employers with few data sources and no research, sorted by `weighted_score * (8 - factors_available)`
- **union_reference:** F7 employers with thin profiles (<=2 sources) that appear as Gower comparables for many non-union targets. Enriching these improves similarity scores.
- **Response:** `{ candidates, total, type }`

### `GET /api/research/vocabulary`
List all 72 valid fact attribute names.
- **Params:** `section` (optional filter by dossier_section)
- **Response:** `{ vocabulary (list of {attribute_name, display_name, dossier_section, data_type, description}), total }`

---

## 10. Crawl4AI Web Scraper

### Page Types & Budgets

| Page | Paths Tried | Char Budget |
|------|-------------|-------------|
| Homepage | `/` | 3,000 |
| About | `/about`, `/about-us`, `/company`, `/our-story` | 2,500 |
| Careers | `/careers`, `/jobs`, `/work-with-us` | 1,500 |
| News | `/news`, `/press`, `/newsroom`, `/media` | 1,000 |
| Locations | `/locations`, `/facilities`, `/our-offices` | 1,000 |
| Contact | `/contact`, `/contact-us`, `/get-in-touch` | 1,000 |
| Investors | `/investors`, `/investor-relations`, `/financials` | 1,500 |

**Total budget:** 12KB per employer | **Timeout:** 35 seconds

### URL Resolution (4-tier)

1. **Provided URL** — from user or previous tool result
2. **Mergent DB** — via employer_id → unified_match_log → mergent_employers.website
3. **Mergent name search** — LIKE on company_name + state
4. **Google Search fallback** — Gemini + Google Search grounding (~$0.001/call)

### Technical Details

- **Framework:** Crawl4AI AsyncWebCrawler, headless browser
- **User-Agent:** "LaborResearchPlatform/1.0"
- **Page timeout:** 15 seconds per page, domcontentloaded wait
- **Robots.txt:** Respected (check_robots_txt=True)
- **HTML→Markdown:** Crawl4AI raw_markdown extractor
- **Windows cp1252 workaround:** Redirect stdout/stderr to UTF-8 TextIOWrapper during asyncio.run(), restore after (Crawl4AI prints Unicode arrows during browser init)
- **Sanitization:** `_sanitize_markdown()` replaces Unicode chars (arrows, bullets, quotes, ellipsis) with ASCII equivalents
- **Truncation:** `_truncate_markdown()` cuts at paragraph → sentence → word boundary

---

## 11. Configuration & Environment

### Environment Variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `RESEARCH_AGENT_MODEL` | `gemini-2.5-flash` | Gemini model for orchestration |
| `RESEARCH_AGENT_MAX_TURNS` | 25 | Max tool-use turns per run |
| `RESEARCH_AGENT_MAX_TOKENS` | 65536 | Max output tokens |
| `RESEARCH_CACHE_HOURS` | 168 (7 days) | Tool result cache window |
| `RESEARCH_SCRAPER_GOOGLE_FALLBACK` | `true` | Enable Tier-4 Google URL lookup |
| `GOOGLE_API_KEY` | (required) | Gemini API key for all Gemini calls |

### Cost Model

| Component | Rate |
|-----------|------|
| Input tokens | $0.30 per 1M |
| Output tokens | $2.50 per 1M |
| Google Search grounding | ~$0.001 per call |
| Typical run total | $0.05-0.15 |

### Caching

Tool results are cached for 7 days per `(employer_id, tool_name)` in `research_actions`.
Cache hits skip the DB query and return the stored summary. Configurable via
`RESEARCH_CACHE_HOURS`.

### Gap Query Templates (Phase 5.2 learning system)

The agent builds gap-aware web searches when DB tools miss. Templates are tracked in
`research_query_effectiveness` for learning which templates work best:

```python
_GAP_QUERY_TEMPLATES = {
    "employee_count": [...],
    "revenue": [...],
    "website_url": [...],
    "osha_violations": [...],
    "nlrb_activity": [...],
    "whd_violations": [...],
    "nonprofit_financials": [...],
    "recent_news": [...],
    "labor_stance": [...],
    "worker_conditions": [...],
}
```

---

## 12. Test Coverage

| Test File | Tests | Scope |
|-----------|-------|-------|
| `test_research_agent_52.py` | ~140 | Vocabulary mapping (TOOL_FACT_MAP, _ATTR_SECTION), JSON repair (_try_parse_json), cache behavior, gap-aware web search queries |
| `test_research_enhancements.py` | 31 | Score computation, quality gates, non-union path, UPSERT logic, MV column verification, API endpoint tests (filter, sort, stats, detail, candidates) |
| `test_research_scraper.py` | ~6 | Crawl4AI mocking, URL normalization, URL resolution, text truncation, tool registration |
| **Total** | **177** | All passing as of Phase 5.7 |

### Key Test Scenarios in test_research_enhancements.py

- Quality gate rejection (score < 7.0)
- Missing employer_id rejection
- Non-union path (direct score enhancement)
- Union reference path (enriches Gower pool)
- Factor score formulas (OSHA, NLRB, WHD, contracts, financial, size)
- No score when research finds 0 (don't override DB with "not found")
- Assessment fields extracted (recommended_approach, campaign_strengths/challenges)
- UPSERT skip logic (lower quality doesn't overwrite higher quality)
- MV has all 7 research columns + index
- API filters: `has_research`, `sort=score_delta`, stats include `research_coverage`

---

## 13. Integration Roadmap: Target Scorecard

The **target scorecard** (`mv_target_scorecard`) covers 3.26M non-union employers and
currently has 8 signal dimensions but **no research integration yet**. This is the key
integration needed to complete the vision.

### 13.1 Current State (Target Scorecard)

```
mv_target_scorecard (3.26M rows)
+-- signal_osha (0-10)           <- structured DB only
+-- signal_whd (0-10)            <- structured DB only
+-- signal_nlrb (0-10)           <- structured DB only
+-- signal_contracts (0-10)      <- structured DB only
+-- signal_financial (0-10)      <- structured DB only
+-- signal_union_density (0-10)  <- BLS only
+-- signal_industry_growth       <- BLS only
+-- signal_size (0-10)           <- structured DB only
+-- signals_present (0-8)
+-- has_enforcement (bool)
+-- NO research columns yet
```

### 13.2 Proposed Research Columns for Target Scorecard

```sql
-- Research enhancement columns (mirror union scorecard pattern)
has_research              BOOLEAN,
research_run_id           INTEGER,
research_quality          NUMERIC(4,2),
research_coverage_pct     NUMERIC(5,2),  -- NEW: 0-100% of 72 attributes filled
research_approach         TEXT,
research_trend            TEXT,
research_contradictions   JSONB,

-- Enhanced signals (GREATEST of DB signal + research signal)
enh_signal_osha           NUMERIC(4,2),
enh_signal_whd            NUMERIC(4,2),
enh_signal_nlrb           NUMERIC(4,2),
enh_signal_contracts      NUMERIC(4,2),
enh_signal_financial      NUMERIC(4,2),
enh_signal_size           NUMERIC(4,2),

-- Gold Standard tracking
gold_standard_tier        TEXT,  -- stub/bronze/silver/gold/platinum
gold_standard_score       NUMERIC(4,2),  -- composite of quality + coverage

-- Pillar scores (computed from enhanced signals + research)
pillar_anger              NUMERIC(4,2),  -- avg of enforcement signals
pillar_leverage           NUMERIC(4,2),  -- avg of leverage signals
pillar_stability          NUMERIC(4,2),  -- NULL until turnover data available
```

### 13.3 Candidate Selection for Target Scorecard Research

Priority formula for non-union targets:
```
research_priority = signals_present
                  * has_enforcement (bool → 0 or 1)
                  * (8 - signals_present)
```

This selects employers that:
- Have at least some signals (not completely unknown)
- Have enforcement data (OSHA, WHD, or NLRB)
- Still have significant data gaps (room for research to add value)

### 13.4 The Complete Loop

```
Target Scorecard (3.26M employers, 8 signals)
    |
    v  Filter: signals_present >= 2, has_enforcement
    |
Research Candidates (~50K-100K employers)
    |
    v  Prioritize: high signals * low coverage
    |
Research Agent Run (25 turns, 14 tools, ~$0.10)
    |
    v  Auto-grade (6 dimensions -> quality 0-10)
    |
    +-- Quality < 7.0 -> log but don't enhance
    |
    v  Quality >= 7.0
    |
research_score_enhancements UPSERT
    |
    v
Target Scorecard REFRESH
    |
    +-- Enhanced signal scores (GREATEST)
    +-- Gold Standard tier computed
    +-- Coverage % updated
    +-- Pillar scores computed (if enough data)
    |
    v
Organizer sees: "This employer is Gold Standard: 62% coverage, quality 8.3,
                 recommended approach: focus on safety issues..."
```

---

## 14. Performance Metrics (68 Completed Runs)

| Metric | Value |
|--------|-------|
| Completion rate | 68/72 (94%) |
| Avg quality score | 7.81/10 |
| Avg facts per run | 29.0 |
| Avg sections filled | 6.0/7 |
| Avg duration | 1.9 min |
| Avg cost | ~$0.05/run |
| Avg tools called | ~12/run |

### Section Fill Rates

| Section | Avg Fill Rate | Notes |
|---------|--------------|-------|
| sources | 91% | Almost always populated |
| workplace | 67% | Strong from OSHA/WHD |
| labor | 61% | Good for union employers |
| assessment | 57% | AI-generated, inconsistent |
| identity | 55% | Missing: website, locations, year_founded |
| financial | 23% | Worst — revenue/employee_count rarely filled from web |
| workforce | 21% | Worst — only BLS composition works reliably |

### Implication for Gold Standard

With current fill rates, the average run fills ~29 of 72 attributes (40% coverage).
This puts most runs in the **Silver** tier. To reach Gold Standard (50%+), the financial
and workforce sections need improvement — exactly the kind of data that becomes available
when the research agent has a company name and can hit Mergent, SEC, and web sources.

---

## 15. Known Issues & Open Questions

### Resolved

1. Financial data fill rate improved via regex post-patching (`_patch_dossier_financials`)
2. Scraper reliability improved with expanded page types and Tier-4 Google URL fallback
3. Consistency scoring functional with `_extract_numeric` for divergence checks
4. Workforce section has dedicated tools (search_job_postings, get_workforce_demographics)
5. Second-pass gap filler implemented (`_fill_dossier_gaps`)
6. Executive compensation supported via `search_sec_proxy`

### Remaining

7. **Scraper timeout:** Large websites may hit 35s limit.
8. **Freshness averages 4.84/10.** Government data is 1-3 years old. Only web search produces recent facts.
9. **`get_workforce_demographics` uses hardcoded baselines.** 6 NAICS codes only. Phase 6 placeholder.
10. **`search_sec_proxy` accuracy unverified on live runs.** May hallucinate for small-cap companies.
11. **`search_job_postings` returns estimates, not counts.** No direct Indeed/LinkedIn API.
12. **Financial/workforce fill rates are lowest (23%/21%).** These sections are critical for Gold Standard but depend heavily on web sources which are noisy.
13. **Target scorecard has no research integration yet.** This is the key gap described in Section 13.
14. **No automated research scheduling.** Runs are manual (POST /api/research/run). System could auto-trigger research for top candidates.

### Open Design Questions

1. **Should target scorecard research candidates be auto-queued?** e.g., top 100 candidates per day.
2. **Should Gold Standard tier be a first-class API field?** Currently derivable from quality + coverage, but not stored.
3. **Should `get_workforce_demographics` use real BLS data?** Currently hardcoded.
4. **What threshold of Gold Standard justifies action?** Silver tier may be enough for initial outreach.
5. **Should research quality influence scorecard tier?** Currently tiers are purely percentile-based on weighted_score.

---

## 16. File Map & Diagnostics

### File Map

```
scripts/research/
    agent.py              (~3,500 lines)  Core orchestration: Gemini loop, web merge, validation
    tools.py              (~2,400 lines)  14 tool implementations + TOOL_REGISTRY + TOOL_DEFINITIONS
    auto_grader.py          (~850 lines)  6-dimension grading + scorecard enhancement computation
    employer_lookup.py      (~220 lines)  3-tier employer matching (exact/prefix/trigram)
    __init__.py

api/routers/
    research.py                           6 REST endpoints

scripts/scoring/
    build_unified_scorecard.py            Unified MV with research LEFT JOIN
    create_research_enhancements.py       Enhancement table schema
    build_target_data_sources.py          Target MV (research integration pending)
    build_target_scorecard.py             Target scorecard MV (research integration pending)

sql/
    create_research_agent_tables.sql      6 table schemas + 72-row vocabulary seed

scripts/analysis/
    research_diagnostic.py                Overall metrics report
    research_dossier_audit.py             Per-run field completeness audit
    research_gap_analysis.py              Web search effectiveness analysis

tests/
    test_research_agent_52.py             ~140 tests for agent logic
    test_research_enhancements.py         31 tests for feedback loop
    test_research_scraper.py              ~6 tests for scraper/URL resolution
```

### Diagnostic Commands

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

# Backfill employer IDs for unlinked runs
py -c "from scripts.research.employer_lookup import backfill_employer_ids; backfill_employer_ids(None, dry_run=False)"

# Backfill enhancements from all graded runs
py -c "from scripts.research.auto_grader import backfill_enhancements; backfill_enhancements()"

# Run tests
py -m pytest tests/test_research_agent_52.py tests/test_research_enhancements.py tests/test_research_scraper.py -v
```

---

*Generated 2026-02-27. Source files: scripts/research/{agent,tools,auto_grader,employer_lookup}.py,
api/routers/research.py, sql/create_research_agent_tables.sql,
scripts/scoring/{build_unified_scorecard,create_research_enhancements,build_target_scorecard}.py*
