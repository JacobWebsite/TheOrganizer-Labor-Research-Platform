# SEC Financial Data Integration Roadmap

> **Task 8-1** from `COMPLETE_PROJECT_ROADMAP_2026_03.md`
> **Last updated:** 2026-03-12
> **Status:** Phase 1 complete, Phases 2-6 open

---

## What We Have Now

### Data
| Asset | Status | Detail |
|-------|--------|--------|
| `sec_companies` table | Loaded | 517K companies — CIK, EIN, SIC, address, filing date (identity only) |
| `sec_xbrl_financials` table | **Loaded** | 249K annual records, 14.6K companies, FY 2003-2025 |
| `companyfacts.zip` | Downloaded | 1.3GB, 19,298 company JSON files at `data/sec/` |
| `submissions.zip` | Downloaded | 1.4GB at `~/Downloads/` (source for sec_companies) |
| Union linkage | Working | ~490 companies matched via UML, ~290 with revenue since 2023 |

### XBRL Financial Coverage (of 249K records)
| Concept | Records | Coverage | Notes |
|---------|---------|----------|-------|
| Revenue | 182,146 | 73% | 6 tag variants mapped |
| Net Income | 233,883 | 94% | 3 tag variants |
| Total Assets | 114,248 | 46% | Balance sheet |
| Total Liabilities | 114,737 | 46% | Balance sheet |
| Cash | 126,478 | 51% | |
| Long-Term Debt | 53,255 | 21% | |
| Employee Count | 262 | 0.1% | Essentially useless — see Phase 5 |

### What Does NOT Exist in companyfacts.zip
- Employee headcount for most companies (reported in 10-K prose, not XBRL tags)
- CEO pay ratio / median worker pay (not in this bulk file)
- Detailed executive compensation (lives in DEF 14A proxy statements)
- Human capital disclosures (unstructured text in 10-K Item 1)

---

## Integration Architecture

```
sec_xbrl_financials (249K rows)
        |
        |--- JOIN on CIK
        v
sec_companies (517K rows)
        |
        |--- JOIN on CIK via unified_match_log (source_system='sec')
        |--- JOIN on CIK via corporate_identifier_crosswalk
        v
f7_employers_deduped / master_employers
        |
        v
  API endpoints --> Frontend profile cards
  Research agent --> Dossier financial section
```

### Current Integration Points (where financial data plugs in)

| Component | File | Current State | What Changes |
|-----------|------|---------------|--------------|
| Employer Profile API | `api/routers/profile.py` | Returns scorecard, OSHA, NLRB, demographics | Add financial data section |
| Corporate API | `api/routers/corporate.py` | Returns CIK, ticker, public flag | Add financial summary |
| Data Source Catalog | `api/data_source_catalog.py` | Lists sec_edgar (identity only) | Add sec_xbrl_financials entry |
| Research Agent | `scripts/research/tools.py` `search_sec()` | Returns CIK, ticker, SIC code | Query XBRL for revenue/income |
| Frontend Card | `FinancialDataCard.jsx` | Shows BLS growth, 990 revenue, public flag | Show SEC revenue, income, trends |
| Data Sources MV | `mv_employer_data_sources` | `is_public` flag | Add `has_sec_financials` flag |

---

## Phases

### Phase 1: Core XBRL ETL -- COMPLETE
- Downloaded `companyfacts.zip` (1.3GB)
- Built `scripts/etl/load_sec_xbrl.py` with tag variant mapping
- Loaded `sec_xbrl_financials`: 249,437 rows, 14,638 companies
- Spot-checked Walmart, Amazon, HCA, Starbucks, Apple — all correct

---

### Phase 2: API Integration (4-6 hours)
**Goal:** Expose financial data through existing API endpoints so profiles show revenue, income, assets.

#### 2A: New Financial Endpoint
Create `GET /api/employers/{employer_id}/financials` returning:
```json
{
  "sec_xbrl": {
    "cik": 860730,
    "company_name": "HCA Healthcare Inc",
    "latest": {
      "fiscal_year_end": "2025-12-31",
      "revenue": 75600000000,
      "net_income": 6800000000,
      "total_assets": 60700000000,
      "total_liabilities": null,
      "cash": null,
      "long_term_debt": null
    },
    "trend": [
      {"year": "2025-12-31", "revenue": 75600000000, "net_income": 6800000000},
      {"year": "2024-12-31", "revenue": 70600000000, "net_income": 5800000000},
      {"year": "2023-12-31", "revenue": 65000000000, "net_income": 5200000000}
    ]
  },
  "form_990": null,
  "is_public": true,
  "ticker": "HCA"
}
```

**Implementation:**
1. Look up SEC CIK via `corporate_identifier_crosswalk` or `unified_match_log`
2. Query `sec_xbrl_financials` for latest 5 years ordered by fiscal_year_end DESC
3. For nonprofits without SEC data, fall back to `national_990_filers`
4. Return unified financial view

**Files to modify:**
- `api/routers/profile.py` — add financial data to profile response OR create new endpoint
- `api/routers/corporate.py` — add financial summary to corporate family view

#### 2B: Data Source Catalog Update
- Add `sec_xbrl_financials` to `api/data_source_catalog.py`
- Add `has_sec_financials` flag to `mv_employer_data_sources` materialized view

#### 2C: Validation Queries
- Verify 5-year trend data looks reasonable (no sign flips, no order-of-magnitude jumps)
- Check for fiscal year duplicates or anomalies (the FY range shows 1927–2201, clean outliers)
- Cross-check 990 revenue vs SEC revenue for companies that file both

**Success criteria:**
- `/api/employers/{id}/financials` returns financial data for any SEC-linked employer
- Revenue/income trends cover at least 3 years for 80%+ of XBRL companies
- Data source catalog updated

---

### Phase 3: Research Agent Integration (2-3 hours)
**Goal:** Research dossiers automatically include financial data for public companies.

#### 3A: Extend `search_sec()` Tool
Currently returns: CIK, ticker, SIC code, exchange, is_public flag.

Add to return: latest revenue, net income, total assets, 3-year revenue trend, revenue growth rate.

**Implementation:**
- In `scripts/research/tools.py`, after the existing `sec_companies` lookup, query `sec_xbrl_financials` for the matched CIK
- Return financial summary inline with existing SEC metadata

#### 3B: Financial Section in Dossier
The research agent's financial section currently shows:
- BLS industry growth
- 990 revenue (if nonprofit)
- Federal contract amounts

Add:
- SEC revenue + net income (latest year)
- Revenue trend (3-5 year)
- Profit margin (net_income / revenue)
- Asset base

**Files to modify:**
- `scripts/research/tools.py` — extend `search_sec()` return
- `scripts/research/report_builder.py` or equivalent — include financials in dossier output

**Success criteria:**
- Research dossier for HCA includes "$75.6B revenue, $6.8B net income"
- Financial section populated for any employer linked to a public company

---

### Phase 4: Frontend Display (3-4 hours)
**Goal:** Employer profile page shows financial data visually.

#### 4A: Update FinancialDataCard
Currently shows: BLS growth %, financial factor score, 990 revenue, public/contractor flags.

Add:
- Revenue with dollar formatting (e.g., "$75.6B")
- Net income with positive/negative styling
- 3-year revenue trend (simple sparkline or table)
- Profit margin percentage
- Total assets

**Implementation:**
- Fetch from new `/api/employers/{id}/financials` endpoint
- Display in existing `FinancialDataCard.jsx` component
- Format large numbers: $75,600,000,000 → "$75.6B"

#### 4B: Comparison Context
For organizer value, show contextual comparisons:
- "Revenue grew 15% in 3 years"
- "Net income: $6.8B (9% profit margin)"
- If CEO pay ratio available: "CEO earns Xm vs median worker $Y"

**Files to modify:**
- `frontend/src/features/employer-profile/FinancialDataCard.jsx`
- Possibly a new `FinancialTrend.jsx` sub-component

**Success criteria:**
- Profile page for SEC-linked employers shows revenue, income, assets
- Numbers formatted for readability
- Graceful fallback when no financial data available

---

### Phase 5: Employee Count Extraction (8-12 hours, separate effort)
**Goal:** Get employee headcount for public companies — the one metric XBRL can't provide.

**The problem:** Only 262 of 19,298 companies report `EntityNumberOfEmployees` via XBRL. Most companies report employee counts in prose in their 10-K filing (Item 1, "Human Capital Resources"), e.g., "As of December 31, 2024, we employed approximately 309,000 full-time equivalents."

**Approach options:**

| Option | Effort | Coverage | Accuracy |
|--------|--------|----------|----------|
| A: LLM extraction from 10-K text | 8-12 hrs | ~7,000 active filers | High (structured prompt) |
| B: edgartools + regex patterns | 4-6 hrs | ~5,000 | Medium (regex fragile) |
| C: Use Mergent employee counts instead | 2-3 hrs | ~1.75M (if full load done) | Medium (often stale) |
| D: Hybrid (Mergent default + LLM for SEC filers) | 10-15 hrs | Best | Best |

**Recommended: Option D (Hybrid)**
1. Load Mergent full dataset (Phase 6) for broad employee count coverage
2. For SEC-linked employers, use LLM extraction from latest 10-K to get authoritative count
3. Prefer SEC-sourced count over Mergent when both available (more recent, self-reported)

**Implementation (Option A detail):**
- Use `edgartools` to fetch latest 10-K filing for each of ~7,000 active filers
- Extract Item 1 / "Human Capital" section
- LLM prompt: "Extract the total number of employees. Return just the number."
- Cost estimate: ~$0.02/filing × 7,000 = ~$140 one-time
- Store in `sec_xbrl_financials.employee_count` or new column

**Dependencies:** Phase 6 (Mergent) for broad coverage; edgartools for 10-K retrieval

---

### Phase 6: Mergent Full Load (6-8 hours, parallel track)
**Goal:** Expand Mergent from 56K to ~1.75M employer records with employee counts, revenue, NAICS.

**Current state:**
- `load_mergent_al_fl.py` loads partial data (AL-FL states only, 56K records)
- Full dataset available but not loaded
- Research agent's `search_mergent()` tool has 26% hit rate (open question: data quality or matching?)

**Implementation:**
1. Extend ETL script to load all states
2. Create/update `mergent_employers` table (~1.75M rows)
3. Run matching pipeline against `master_employers`
4. Validate coverage: how many of 4.4M target employers gain employee counts?

**Key data from Mergent:**
- Employee count (self-reported, may be stale)
- Annual revenue
- DUNS number (for D&B crosswalk)
- NAICS code
- Headquarters address

**Value:** Mergent fills the gap that XBRL can't — employee counts for thousands of companies. Even if counts are 1-2 years stale, "approximately 15,000 employees" is far more useful than no data.

**Files to modify:**
- `scripts/etl/load_mergent_al_fl.py` → generalize to `load_mergent.py`
- `api/data_source_catalog.py` — update record count
- Research agent `search_mergent()` — improve hit rate

**Success criteria:**
- Mergent table grows from 56K to ~1.75M
- Employee count coverage for target employers increases measurably
- Research agent hit rate improves

---

### Phase 7: CEO Pay Ratio & Executive Compensation (20-30 hours, separate project)
**Goal:** Extract CEO compensation and pay ratio data from SEC proxy statements.

**Two tiers:**

#### Tier 1: Pay Ratio from XBRL (low-hanging fruit, 3-4 hours)
Since 2018, public companies must disclose CEO-to-median-worker pay ratio. This data MAY be available via the SEC XBRL API (individual company endpoint, not companyfacts.zip). Tags:
- `ecd:PayVsPerformanceTable` (ECD taxonomy, post-2022)
- Custom company-specific tags for pay ratio

**Action:** Test whether the SEC XBRL API returns pay ratio data for known companies (Walmart, Amazon, HCA). If yes, batch-extract for all filers. If no, move to Tier 2.

#### Tier 2: Full Proxy Statement Parsing (20-30 hours)
Parse DEF 14A proxy statements for:
- Named executive officer compensation tables
- CEO total compensation
- Median worker pay
- Pay ratio

**Implementation:**
- Use `edgartools` to retrieve latest DEF 14A for each active filer
- LLM-based extraction (similar architecture to Exhibit 21 PoC)
- Cost: ~$0.02-0.05/filing × ~7,000/year = ~$140-350
- Store in new `sec_exec_compensation` table

**Organizer value:** "The CEO made $30M last year while the median worker earned $32,000 — a 937:1 ratio." This is among the most powerful data points for organizing campaigns.

---

## Phase Summary

| Phase | Effort | Status | Dependencies | Value |
|-------|--------|--------|--------------|-------|
| 1. Core XBRL ETL | 8-12 hrs | **DONE** | None | Foundation data (14.6K companies) |
| 2. API Integration | 4-6 hrs | Open | Phase 1 | Financial data visible in profiles |
| 3. Research Agent | 2-3 hrs | Open | Phase 1 | Dossiers include financials |
| 4. Frontend Display | 3-4 hrs | Open | Phase 2 | Users see revenue/income/trends |
| 5. Employee Counts | 8-12 hrs | Open | Phase 6 | Headcount for public companies |
| 6. Mergent Full Load | 6-8 hrs | Open | None | 1.75M employers with size data |
| 7. Exec Compensation | 20-30 hrs | Open | None | CEO pay, pay ratios |

**Critical path:** Phases 2→3→4 are sequential (API first, then research agent, then frontend). Phases 5, 6, and 7 are independent and can run in parallel.

**Recommended execution order:**
1. Phase 2 (API) + Phase 6 (Mergent) — in parallel
2. Phase 3 (Research Agent) — immediately after Phase 2
3. Phase 4 (Frontend) — immediately after Phase 2
4. Phase 5 (Employee Counts) — after Phase 6, informed by Mergent coverage
5. Phase 7 (Exec Comp) — standalone project, schedule when ready

**Total remaining effort:** ~45-65 hours for everything, or ~12-15 hours for Phases 2-4 (the "make it visible" work that delivers 80% of user value).

---

## Open Questions

| ID | Question | Status |
|----|----------|--------|
| Q1 | Is CEO pay ratio data available via SEC XBRL API (not companyfacts.zip)? | Needs testing |
| Q2 | Mergent data quality: is 26% research agent hit rate a data or matching problem? | From roadmap Q1301 |
| Q3 | For ~290 union-linked companies with recent financials, is that enough to justify Phase 4 frontend work? | User decision |
| Q4 | Should we clean the FY outliers (1927, 2201) in sec_xbrl_financials? | Minor, Phase 2 |
| Q5 | Private company financials: any viable source beyond Mergent and 990? | From roadmap Q17d |

---

## Data Files & Scripts

| File | Purpose |
|------|---------|
| `data/sec/companyfacts.zip` | 1.3GB SEC XBRL bulk data (19,298 companies) |
| `data/sec/submissions.zip` or `~/Downloads/submissions.zip` | SEC company metadata |
| `scripts/etl/load_sec_xbrl.py` | Phase 1 ETL (companyfacts.zip → sec_xbrl_financials) |
| `scripts/etl/load_sec_edgar.py` | Existing ETL (submissions.zip → sec_companies) |
| `scripts/etl/create_sec_companies_table.sql` | Schema for sec_companies |
| `docs/data-sources/SEC_EDGAR_RESEARCH.md` | Bulk submissions strategy |
| `docs/data-sources/EDGARTOOLS_EVALUATION.md` | edgartools library evaluation |
| `docs/data-sources/EXHIBIT_21_PARSING_RESEARCH.md` | LLM subsidiary extraction |
