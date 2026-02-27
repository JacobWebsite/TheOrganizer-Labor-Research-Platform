# Research Agent Architecture

The research agent is a Gemini-powered AI orchestration loop that conducts deep-dive investigations on individual employers. It queries 18 internal database and API tools + web scraping, produces a structured dossier, auto-grades the result, and feeds enhanced scores back into both scorecards.

---

## End-to-End Flow

```
User clicks "New Research" in frontend
  → POST /api/research/run {company_name, employer_id?, naics?, state?}
  → Creates research_runs row (status=pending)
  → Background task: run_research(run_id)
      → Builds system prompt with company context + tool list + vocabulary
      → Gemini 2.5 Flash agent loop (max 25 turns):
          1. Check internal databases (OSHA, NLRB, WHD, SEC, SAM, 990, contracts, Mergent, GLEIF)
          2. Get industry context (BLS profiles, similar employers)
          3. Additional enrichment (SEC proxy, job postings, workforce demographics)
          4. Forced Enrichment (FEC Donations, Local Demographics, WARN notices)
          5. Scrape employer website (Crawl4AI)
          6. Gap-Aware Web Search (Google Grounding)
      → Final Pass: Exhaustive Coverage Validation
          - Checks all 72 fields. If null, populates with "Verified None ([Tool] searched)"
      → Parse facts → research_facts table
      → Auto-grade (6 dimensions) → research_runs.overall_quality_score
      → Compute score enhancements → research_score_enhancements table
  → Frontend polls GET /api/research/status/{run_id} for progress
  → On completion: GET /api/research/result/{run_id} for full dossier
```

---

## Database Tables

(See `RESEARCH_AGENT_REFERENCE.md` for full schema details)

### `research_runs`
The "cover page" for a research session. Now tracks `overall_quality_score` which rewards exhaustive "Verified None" responses.

### `research_facts`
Individual pieces of information. Now includes specific attributes for `political_donations`, `warn_notices`, and `parent_company` (from GLEIF).

---

## Tool Inventory (18 tools)

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
| 9 | `search_sec_proxy` | API/Web | SEC DEF 14A proxy — executive compensation |
| 10 | `search_job_postings` | API/Web | Active job listings, posting counts, pay ranges |
| 11 | `get_workforce_demographics`| database | BLS industry-level demographics (race, gender, age) |
| 12 | `get_industry_profile` | database | BLS occupation mix, wages, union density by NAICS |
| 13 | `get_similar_employers` | database | Comparable organized employers |
| 14 | `scrape_employer_website` | web | Crawl4AI scrape of homepage, about, news, etc. |
| 15 | `search_gleif_ownership` | database | **NEW:** Corporate genealogy, parents, and subsidiaries |
| 16 | `search_political_donations`| FEC API | **NEW:** PAC and individual contributions (FEC Keyed) |
| 17 | `search_local_demographics` | Web/ACS | **NEW:** City-specific racial and income data |
| 18 | `search_warn_notices` | Web | **NEW:** Mass layoff (WARN Act) filings |

---

## Exhaustive Coverage Logic

To reach the **Gold Standard**, the agent no longer leaves fields blank. 
1. **Verified None**: If a tool (e.g., OSHA) runs and returns "No Data," the field is marked `"Verified None (search_osha searched)"`.
2. **Not Searched**: If a tool is skipped due to strategy (e.g., skip SEC for a nonprofit), the field is marked `"Not searched (No strategy match)"`.
3. **Scoring**: The Auto-Grader rewards "Verified None" as a successful research result, while penalizing "Not searched".

---

## Key Files

| File | Purpose |
|------|---------|
| `scripts/research/agent.py` | Core loop + Exhaustive Coverage validation |
| `scripts/research/tools.py` | 18 tool implementations (including FEC API integration) |
| `scripts/research/auto_grader.py` | 6-dimension scoring (rewards Verified None) |
