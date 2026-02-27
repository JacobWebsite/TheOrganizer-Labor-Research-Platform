# Research Agent Deep Audit Report
**Date:** 2026-02-25
**Scope:** Full system audit of Research Agent (Phases 5.1-5.7)
**Auditor:** Claude Code (Opus 4.6)

---

## 1. Executive Summary

The Research Agent has completed **96 runs** (92 completed, 4 failed) across **92 unique employers** with an average quality score of **7.93/10**. Phase 5.7 made significant improvements to actionability (introduced 6th grading dimension, enabled `recommended_approach`, contradiction resolver, financial trend extraction) but **average scores actually dropped from 8.25 to 7.80** because the grader is now more honest — it scores field-level coverage instead of section-level, and penalizes placeholder values.

### Key Findings

| Area | Status | Verdict |
|------|--------|---------|
| DB Tools (search_osha, nlrb, whd, sec, sam, 990, contracts) | Working | 7/7 functional, name-matching limits well-understood |
| Scraper | Working | Forced in every run, URL found for most employers |
| search_sec_proxy | Improved | 2/3 public company runs now find exec pay (was 0/5) |
| search_job_postings | Working | 10/10 last runs have job posting data |
| get_workforce_demographics | Working | Always returns data but only 6 NAICS sectors + generic fallback |
| Post-processing chain | Working | 5 functions run in correct order; contradiction resolver effective |
| Auto-grader | Improved | 6 dimensions; field-level coverage; but still has blind spots |
| Fact provenance | **GAP** | 0 web/scraper facts saved in last 10 runs (all classified as "database") |
| Employee count | **GAP** | NULL in 10/10 last runs (financial.employee_count) |
| Financial trend | **GAP** | "unknown" in 7/10 last runs despite web text containing growth keywords |

### Critical Issue
**Zero web/scraper facts are being persisted** to `research_facts`. All 10 last runs show DB={8-23} Web=0 Scraper=0. This means the grader's source_quality score is inflated (all facts are "database" = 1.0 rank) and fact provenance tracking is broken for web-sourced data.

---

## 2. What Changed Since the Reference Doc

### Phase 5.7 Changes (runs 89-96)
| Change | Impact | Measured Result |
|--------|--------|-----------------|
| Enabled `recommended_approach` in system prompt | All runs now have strategy guidance | 8/8 runs have 100+ char recommendations |
| Contradiction resolver (`_resolve_contradictions`) | DB-web mismatches flagged | 7/8 runs have `source_contradictions` (1 run had no contradictions to find) |
| Financial trend extractor (`_extract_financial_trend`) | Regex scans web text for growth/decline keywords | 3/8 runs have trends; 5/8 still "unknown" (keyword matching too narrow) |
| SEC proxy prompt: JSON -> pipe-delimited format | Gemini returns parseable exec pay | 2/3 public runs now have exec_compensation (was 0/5) |
| Demographics overwrite: always apply labeled version | Honest "INDUSTRY BASELINE" prefix | 6/8 labeled (2 runs: Gemini overwrote with its own dict format) |
| Employee count validation | Flags suspiciously low counts | Works, but employee_count itself is NULL in 10/10 last runs |
| Field-level coverage grading | Honest fill rate instead of section-level | Coverage scores dropped ~2 points (e.g., 8.86 -> 5.35) |
| Actionability dimension (15% weight) | Rewards complete assessments | avg 8.75/10 across last 8 runs (high because most have recommendations) |
| Placeholder penalty in coverage | Deducts for "unknown", "N/A", generic baselines | Up to -2.0 penalty observed |

### Score Evolution
| Batch | Runs | Avg Score | Notes |
|-------|------|-----------|-------|
| Runs 1-50 | 46 | 7.75 | Phase 5.1-5.3 baseline |
| Runs 51-80 | 30 | 8.15 | Phase 5.4 improvements |
| Runs 81-88 (5.6) | 8 | 8.25 | Pre-5.7 peak (inflated) |
| Runs 89-96 (5.7) | 8 | 7.80 | Post-5.7 (honest scoring) |

**Interpretation:** The score drop is healthy — it reflects the grader penalizing real problems (empty fields, placeholders) that were previously hidden by section-level counting.

---

## 3. Tool-by-Tool Findings

### 3.1 Database Tools (11 tools)

| Tool | Hit Rate | Avg Facts | Issues |
|------|----------|-----------|--------|
| **search_osha** | ~75% (matched employers) | 3-5 | Works well. Name matching via `_name_like_clause` + acronym fallback. False positives filtered by `_filter_by_name_similarity(threshold=0.50)`. Known gap: subsidiaries (Amazon warehouses under different names). |
| **search_nlrb** | ~70% | 2-4 | Works. Queries both `nlrb_elections` and `nlrb_participants` for ULP. Same subsidiary name problem as OSHA. |
| **search_whd** | ~60% | 2-3 | Works. Lower hit rate because many employers have no WHD cases. |
| **search_sec** | ~40% | 1-2 | Only finds public companies in SEC database. Hit rate reflects mix of public/private test companies. |
| **search_sam** | ~55% | 1-2 | Federal contractor lookup. `sam_entities` table uses UEI not name — **G1: falls back to name match which has false-positive risk**. |
| **search_990** | ~35% | 1-3 | Nonprofit only. Works for Kaiser but not Amazon/Dollar General. |
| **search_contracts** | ~50% | 1-2 | Federal contracts from `usa_spending_awards`. Depends on crosswalk match. |
| **get_industry_profile** | ~95% | 3-5 | Always works if NAICS known. Returns BLS occupation matrix + union density. **G2: NAICS-to-density mapping hardcoded for 6 sectors only.** |
| **get_similar_employers** | ~85% | 2-4 | Finds F7 employers in same state/NAICS. **G3: "recent elections" subquery has NO industry filter** — returns random elections from any industry. |
| **search_mergent** | ~30% | 1-2 | Mergent DB is 56K mostly small NY firms. Miss rate expected for large national employers. |
| **scrape_employer_website** | ~80% | 0 (no facts saved) | Scraper works (Crawl4AI + 4-tier URL). Forced in every run. **G4: Scraped content is used for context but NO facts are extracted and saved from scraper results.** |

### 3.2 Gemini Google Search Grounding Tools (3 tools)

| Tool | Hit Rate (last 10) | Issues |
|------|-------------------|--------|
| **search_sec_proxy** | 2/3 public | **Improved.** Pipe-delimited prompt + regex fallback. XPO still fails because SEC search doesn't find "XPO Logistics" (name mismatch with SEC filing name). Amazon and Dollar General both produced exec compensation. |
| **search_job_postings** | 10/10 | **Working well.** Returns count estimates (80-3489) and turnover signals. JSON parsing fails sometimes but regex fallback catches the data. |
| **get_workforce_demographics** | 10/10 | **Working but shallow.** Only 6 NAICS-to-profile mappings. NAICS 45 (Dollar General, retail-general) falls through to generic baseline. NAICS 33 (manufacturing) exists but NAICS 32 doesn't. No state-level variation. |

### 3.3 Tool Call Patterns
- Gemini calls 10-15 tools per run organically
- 3-4 additional forced tools per run (scraper + sec_proxy + job_postings + demographics)
- Total: 12-21 tool calls per run
- Gemini **never voluntarily calls** search_sec_proxy, search_job_postings, or get_workforce_demographics — these are always forced. This is expected behavior and the forced-call pattern works correctly.

### 3.4 Tool Bugs and Gaps Summary

| ID | Severity | Tool | Issue |
|----|----------|------|-------|
| G1 | Medium | search_sam | Name-based fallback has false-positive risk (no SAM entity-to-F7 match validation) |
| G2 | Low | get_industry_profile | NAICS-to-union-density mapping covers only 6 sectors; others get NULL |
| G3 | Medium | get_similar_employers | "Recent elections" subquery returns elections from ANY industry, not filtered to employer's NAICS |
| G4 | **High** | scrape_employer_website | Scraper runs and returns content but **zero facts are saved to research_facts** from scraper source |
| G5 | Low | search_mergent | 56K records is too small for reliable coverage — but can't be fixed without more data |
| G6 | Medium | get_workforce_demographics | Only 6 NAICS profiles + generic fallback. NAICS 32, 45, 49, 51, 52, 54, 56 all fall to generic. |
| G7 | Low | All DB tools | No in-memory caching — each tool opens/closes a DB connection. Fine for current throughput but would matter at scale. |

---

## 4. Post-Processing Chain Assessment

The post-processing chain runs 5 deterministic functions after the Gemini loop and forced tool calls:

```
1. _patch_dossier_financials(dossier_data, web_text)     # line 690
2. _validate_employee_count(dossier_data, run)            # line 1092
3. _resolve_contradictions(dossier_data)                  # line 876
4. _extract_financial_trend(dossier_data, web_text)       # line 998
5. _fill_dossier_gaps(run_id, dossier_data, web_text, vocabulary)  # line 755
```

### Assessment by Function

| Function | Effectiveness | Issues |
|----------|--------------|--------|
| `_patch_dossier_financials` | Medium | Regex extracts employee_count and revenue from web text. But employee_count is NULL in 10/10 last runs, suggesting the regex patterns aren't matching actual web text format. |
| `_validate_employee_count` | Working but moot | Correctly flags suspiciously low counts, but with employee_count NULL everywhere, it rarely fires. |
| `_resolve_contradictions` | **High** | 7/8 runs found contradictions. Correctly identifies DB-zero vs web-nonzero for OSHA, NLRB, WHD. Annotates DB values with "(DB name match -- see source_contradictions)". |
| `_extract_financial_trend` | Low | Only 3/8 runs extracted a trend. 5/8 are "unknown". The keyword patterns are too strict — "layoffs" matches declining but many declining companies have subtler indicators. Also, `financial_trend` field lives in `assessment` dict (line 1085) but the grader checks `financial.financial_trend` (line 315), and both `assessment.financial_trend` and `financial.financial_trend` appear in dossiers — inconsistent location. |
| `_fill_dossier_gaps` | Medium | Second-pass gap filler. Helps but can't fix what the tools didn't find. |

### Post-Processing Issues

| ID | Severity | Issue |
|----|----------|-------|
| PP1 | **High** | `financial_trend` stored in `assessment.financial_trend` (line 1085) but grader checks both locations inconsistently. Field appears in both `assessment` and `financial` sections across different runs. |
| PP2 | Medium | `_patch_dossier_financials` regex doesn't match Gemini's web search output format — employee counts found by Gemini's tool calls are in the dossier but `financial.employee_count` is still NULL because the field is set under `identity.employee_count` or `basic_info.employee_count` inconsistently. |
| PP3 | Medium | Contradiction resolver only checks 3 categories (OSHA, NLRB, WHD). Could also check contracts (DB says 0 but web mentions federal contracts) and financial data. |
| PP4 | Low | `_extract_financial_trend` prioritizes "declining" over "growing" — if both keywords appear in web text, it reports declining. This bias may be intentional (conservative for organizing assessment) but isn't documented. |

---

## 5. Data Gap Analysis

### 5.1 Field Fill Rates (All 92 Completed Runs)

**Consistently Filled (>80%):**
- `identity.legal_name` (100%), `identity.naics_code` (99%), `identity.company_type` (98%)
- `workforce.workforce_composition` (98%), `assessment.organizing_summary` (99%)
- `assessment.campaign_strengths` (98%), `assessment.campaign_challenges` (98%)
- `assessment.recommended_approach` (81%) — jumped from 0% pre-5.7

**Moderate Fill (40-80%):**
- `workplace.osha_violation_count` (74%), `workplace.whd_case_count` (77%)
- `labor.nlrb_election_count` (70%), `labor.existing_contracts` (73%)
- `workforce.demographic_profile` (53%), `workplace.safety_incidents` (52%)

**Poorly Filled (<40%):**
- `financial.exec_compensation` (3.2%) — only 2 runs ever
- `financial.financial_trend` (4.6%) — 3 runs
- `financial.revenue_range` (10.9%), `financial.nonprofit_assets` (15.6%)
- `workforce.pay_ranges` (18.8%), `workforce.job_posting_count` (20.3%)
- `workforce.turnover_signals` (25.0%), `identity.major_locations` (28.1%)
- `identity.website_url` (34.4%), `identity.parent_company` (34.4%)

**Never Filled (0%):**
- `workplace.osha_vilation_details` [sic] — typo in field name (should be "violation")

### 5.2 Critical Field Analysis

| Field | Fill Rate | Root Cause | Fix Complexity |
|-------|-----------|------------|----------------|
| `financial.employee_count` | 49% (73 runs) | Web search finds it but stores under identity or basic_info inconsistently | Low — normalize field location in post-processing |
| `financial.exec_compensation` | 3.2% | Only works for public companies where search_sec_proxy succeeds | Medium — need better SEC name matching |
| `financial.financial_trend` | 4.6% | Keyword matching too narrow; field stored in wrong section sometimes | Low — expand keywords, normalize location |
| `workforce.job_posting_count` | 20.3% | Forced tool was added in Phase 5.5; only recent runs have it | Already fixed — 10/10 last runs have data |
| `workforce.pay_ranges` | 18.8% | Only `get_industry_profile` provides this; depends on NAICS match to BLS matrix | Low — tool works, just needs more NAICS coverage |
| `identity.website_url` | 34.4% | Scraper finds URLs but doesn't save them as facts | Low — save scraper URL as fact |

### 5.3 Fact Provenance Gap

**Critical finding:** The `research_facts` table shows **0 web facts and 0 scraper facts** in the last 10 runs. All facts are categorized as `source_type='database'`. This means:

1. Web intelligence (organizing activity, recent news, safety violations from Google Search) is merged into the dossier JSON but **not saved as individual facts**
2. The grader's `_score_source_quality` function sees only DB facts (rank=1.0) making source diversity appear perfect
3. Historical fact tracking is incomplete — we can't query "what did web search find about Amazon?"

**Root cause:** Facts are only created from the Gemini tool-call results (which are all DB tools). The web search phase (Phase 3 in agent.py) adds items to `dossier_body["workplace"]["recent_labor_news"]` etc. but the fact-creation loop at line 2386-2465 appends to `original_dossier["facts"]` which gets serialized into `dossier_json` but the `_save_facts()` function at line 2658 may not be picking these up if the facts array reference was lost during JSON re-serialization.

---

## 6. ABS Integration Plan

### Census Annual Business Survey (ABS) — Full Investigation

**API Base URL:** `https://api.census.gov/data/{YEAR}/{DATASET}`
**Documentation:** https://www.census.gov/data/developers/data-sets/abs.html

#### 6.1 What ABS Provides

Four datasets available via API:
- **`abscs`** (Company Summary): Firm counts, employment, payroll, revenue by owner demographics
- **`abscb`** (Characteristics of Businesses): Firm age, urban/rural, revenue size
- **`abscbo`** (Owner Characteristics): Owner education, age, acquisition method
- **`absmcb`** (Module): R&D, innovation, digitization (rotated annually)

**Demographic dimensions (of business OWNERS, not workforce):**
- Owner race (White, Black, AIAN, Asian, NHPI, Minority/Nonminority)
- Owner ethnicity (Hispanic/Non-Hispanic)
- Owner gender (Female/Male/Equally)
- Veteran status

**Geography:** National, State, County, MSA, Congressional District
**NAICS:** 2-digit to 4-digit sectors
**Firm size:** 10 buckets (0 to 500+)
**Firm age:** 6 buckets (<2yr to 16+yr)
**Most recent available:** 2023 (survey year 2022). API key: free.

#### 6.2 Critical Limitation

**ABS measures business OWNER demographics, NOT workforce demographics.** A Black-owned manufacturing firm with 200 employees could have any workforce composition. This is fundamentally different from what our `get_workforce_demographics` tool needs.

No individual firm identification — data is aggregated by NAICS x geography x firm size. Cell suppression at high granularity (4-digit NAICS + state + race + firm size often suppressed below 3 firms).

#### 6.3 Integration Assessment

| Factor | Assessment |
|--------|-----------|
| Replaces BLS baselines? | **No.** ABS is owner demographics, not worker demographics. Different data entirely. |
| Useful additions? | **Yes.** Firm size/age distributions, payroll benchmarks, minority-ownership rates by NAICS/state. Useful for "industry context" enrichment. |
| Granularity improvement | High for firm counts/revenue (NAICS x state x size). Low for demographics (wrong kind). |
| API access | Free key, 500/day unauthenticated. No OAuth. |
| Implementation effort | ~8-12 hours: bulk download, load into PostgreSQL, add lookup function. |
| Data freshness | 2-year lag (latest API year = 2023, referencing 2022 data). |

#### 6.4 Recommendation

**Priority: Low.** ABS fills a niche (industry context, firm density, ownership demographics) but does NOT solve our workforce demographics problem.

**Better alternatives for worker demographics (in priority order):**

1. **BLS CPS Detailed Tables** (free, ~20 industry sectors, national-level worker race/gender/age) — **recommended for Phase 6**
2. **ACS PUMS** (Census microdata, individual-level worker demographics, can be aggregated by industry/geography)
3. **EEO-1 data** (actual employer-level workforce demographics but NOT publicly available at firm level)
4. **Census ABS** (owner demographics only — use for industry context if Phase 6 needs supplemental data)

**Example ABS API call (for reference):**
```
https://api.census.gov/data/2023/abscs?get=NAICS2022_LABEL,RACE_GROUP_LABEL,FIRMPDEMP,EMP,PAYANN&for=state:*&NAICS2022=31-33&SEX=001&ETH_GROUP=001&VET_GROUP=001&EMPSZFI=001
```

---

## 7. New Data Source Recommendations

### 7.1 High-Priority Sources

| Source | Data Type | Integration Effort | Impact |
|--------|-----------|-------------------|--------|
| **BLS CPS Detailed Tables** | Workforce demographics (race, gender, age) by industry | 8-12 hrs | Replaces 6-profile hardcoded demographics with 20+ industry-specific worker profiles |
| **Glassdoor/Indeed Reviews API** | Employee sentiment, salary data, company culture | 16-24 hrs | Fills turnover_signals, pay_ranges, worker_complaints gaps |
| **OSHA Establishment Search** (direct API) | Real-time OSHA inspection lookup | 4-8 hrs | Supplements DB which may lag 6-12 months |
| **SEC EDGAR XBRL** | Structured financial data for public companies | 12-16 hrs | Employee count, revenue, exec pay — directly from filings, no LLM parsing needed |

### 7.2 Medium-Priority Sources

| Source | Data Type | Integration Effort | Impact |
|--------|-----------|-------------------|--------|
| **BLS Quarterly Census of Employment & Wages (QCEW)** | Establishment-level employment counts by NAICS/county | 8-12 hrs | Better employee count estimates by industry/geography |
| **Census County Business Patterns** | Firm counts by NAICS/county/size | 4-8 hrs | Competitor density, market saturation analysis |
| **DOL Union Financial Reports (LM-2/3/4)** | Union financial health, membership trends | 4-8 hrs | Already partially in F7; could add financial health of nearby unions |
| **NLRB Case Activity Reports** (direct scrape) | Real-time case filings | 8-12 hrs | Faster than DB load cycle; catches cases filed in last 30 days |

### 7.3 Low-Priority / Speculative

| Source | Notes |
|--------|-------|
| Census ABS | Owner demographics, not worker demographics. See Section 6. |
| LinkedIn Company API | Expensive, TOS restrictions. Duplicate of job posting data. |
| State OSHA plans | 22 states have separate OSHA programs. Would require per-state scraping. |

---

## 8. Grading System Assessment

### 8.1 Current Architecture

6 dimensions, weighted:

| Dimension | Weight | Method | Score Range |
|-----------|--------|--------|-------------|
| Coverage | 20% | Field-level fill rate (Phase 5.7) | 0-10, avg 6.5 |
| Source Quality | 35% | Source type rank x confidence avg | 0-10, avg 8.0 |
| Consistency | 15% | Start at 10, deduct for contradictions | 0-10, avg 8.5 |
| Actionability | 15% | Checklist (recommended_approach, strengths, etc.) | 0-10, avg 8.8 |
| Freshness | 10% | Fact age buckets | 0-10, avg 6.5 |
| Efficiency | 5% | Facts-per-tool + speed bonus | 0-10, avg 7.5 |

### 8.2 Grader Bugs and Issues

| ID | Severity | Issue | Fix |
|----|----------|-------|-----|
| GR1 | **High** | Source quality is inflated: all facts are "database" (rank 1.0) because web facts aren't saved to research_facts. Avg source_quality = 8.0 but should be ~6.5 if web sources (rank 0.6) were included. | Fix fact provenance (save web facts to research_facts with source_type='web_search') |
| GR2 | Medium | Coverage doesn't weight fields. `identity.legal_name` (always filled, low value) counts the same as `financial.exec_compensation` (rarely filled, high value). | Add field importance weights (critical=2x, standard=1x, optional=0.5x) |
| GR3 | Medium | Consistency starts at 10.0 and only deducts. Sparse dossiers get 10/10 consistency because there's nothing to contradict. A dossier with 5 fields and no contradictions scores higher than one with 50 fields and 1 contradiction. | Add a minimum-data threshold: consistency = 5.0 if fewer than 15 facts. |
| GR4 | Low | Actionability scoring is too easy to max out. Getting 10/10 requires: recommended_approach (3) + 3 strengths (2) + 3 challenges (2) + contradictions (1) + trend (1) + exec_comp (1) = 10. But 8/10 is possible without trend or exec_comp, and all runs get 3+ strengths/challenges. | Raise thresholds: require 5+ items, require recommended_approach > 200 chars, require financial data. |
| GR5 | Low | Freshness doesn't distinguish government data (OSHA/NLRB ages are fine at 2-3 years) from web data (stale at 6+ months). A 2023 OSHA record should score the same as a 2025 one. | Add source-type-aware freshness: gov/DB facts get a 3-year window at full score; web facts get a 6-month window. |
| GR6 | Low | Efficiency speed bonus (<500ms average) is nearly impossible — Gemini API calls take 2-10 seconds each, making average latency always >1000ms. The bonus never fires. | Remove speed bonus or set threshold to <5000ms avg latency. |
| GR7 | Low | `financial_trend` checked in wrong location — grader checks `assessment.financial_trend` (line 315-317) but some dossiers store it in `financial.financial_trend`. Both locations should be checked. | Check both `assessment.financial_trend` and `financial.financial_trend`. |

### 8.3 Score Calibration

Current score distribution (92 completed runs):
- Min: 3.35, Max: 8.75, Mean: 7.93, StdDev: 1.15
- 90th percentile: ~8.5
- 10th percentile: ~6.5

**Issue:** The distribution is compressed between 6.5-8.5 (80% of runs). There's insufficient differentiation between a genuinely excellent dossier and a mediocre one. This is partly because source_quality (35% weight) has very low variance — all runs score 7.5-8.5 on source quality since all facts are "database".

**After fixing GR1 (web fact provenance)**, source_quality variance should increase, naturally spreading the score distribution.

---

## 9. Architecture Recommendations

### 9.1 Prioritized Fixes (by impact/effort ratio)

| Priority | Rec | What | Why | Effort | Dependencies |
|----------|-----|------|-----|--------|--------------|
| **P0** | Fix web fact persistence | Save web-sourced facts (news, organizing, violations, financial) to `research_facts` with correct `source_type` | Fixes grader inflation (GR1), enables fact provenance tracking, provides web source diversity for source_quality scoring | 2-4 hrs | None |
| **P0** | Normalize `employee_count` field location | Post-processing should check `identity.employee_count`, `basic_info.employee_count`, and `financial.employee_count`, then normalize to `financial.employee_count` | 10/10 last runs have NULL `financial.employee_count` despite web search finding the data | 1-2 hrs | None |
| **P1** | Normalize `financial_trend` field location | Same issue — appears in both `assessment` and `financial` sections. Pick one canonical location and patch both post-processing and grader. | 4.6% fill rate is partly a location mismatch | 1 hr | None |
| **P1** | Expand workforce demographics profiles | Add NAICS codes 32, 45, 49, 51, 52, 54, 56 to the `_PROFILES` dict. Use BLS CPS industry tables. | Currently 6 sectors, 13 of 20 NAICS sectors fall to generic baseline | 4-6 hrs | BLS CPS data download |
| **P1** | Fix grader source_quality after P0 | Once web facts are saved, adjust source_quality scoring to properly weight database (1.0) vs web (0.6) vs scraper (0.7) facts | Currently inflated due to all-database facts | 1 hr | P0 |
| **P2** | Fix `get_similar_employers` election query | Add NAICS filter to the "recent elections" subquery in the similar employers tool | Returns random elections from any industry, misleading in dossier | 1 hr | None |
| **P2** | Add grader field importance weights | Critical fields (recommended_approach, osha_violation_count, nlrb_election_count, employee_count) should count 2x in coverage | Equal weighting means identity.legal_name = exec_compensation | 2-3 hrs | None |
| **P2** | Tighten actionability thresholds | Require recommended_approach > 200 chars, 5+ strengths/challenges, financial_trend non-"unknown" | Currently too easy to max out at 9-10 | 1-2 hrs | None |
| **P3** | Add SEC EDGAR XBRL integration | Direct structured data for public companies — employee count, revenue, exec pay without LLM parsing | Would fix exec_compensation for all public companies | 12-16 hrs | SEC EDGAR API access |
| **P3** | Add BLS CPS detailed tables | Replace hardcoded demographics with actual worker demographic data by industry | Fixes G6 (demographics tool limitations) | 8-12 hrs | BLS data download |
| **P3** | Add consistency minimum-data floor | Score = 5.0 if fewer than 15 facts, preventing sparse dossiers from getting 10/10 | Sparse dossiers currently rewarded | 1 hr | None |

### 9.2 Architecture Questions

**Q: Should the agent use a different LLM for different phases?**
Currently Gemini 2.5 Flash handles everything — tool selection, synthesis, and assessment writing. For a multi-model approach:
- **Tool selection + fact gathering:** Gemini Flash is fine (fast, cheap)
- **Assessment writing:** A larger model (Gemini Pro, GPT-4o) would produce better `recommended_approach` text
- **Recommendation:** Not worth the complexity yet. Fix data gaps first — a better model can't help if the input data is missing.

**Q: Should forced tool calls be replaced with better prompting?**
No. Testing confirmed Gemini never voluntarily calls search_sec_proxy, search_job_postings, or get_workforce_demographics despite them being in TOOL_DEFINITIONS. The forced-call pattern is reliable and predictable. Keep it.

**Q: Is the 25-turn Gemini loop sufficient?**
Yes. Most runs complete in 8-15 turns. The 25-turn limit was only hit in early runs with broken tools. The loop-exit detection (2 consecutive web-only turns = stuck) works correctly.

**Q: Should dossier JSON schema be enforced?**
Currently Gemini sometimes puts fields in wrong sections (`employee_count` in `identity` vs `financial`). A JSON Schema validator in post-processing would catch this, but the better fix is the normalization post-processing (P0 recommendation above). Schema enforcement adds complexity without solving the root cause.

---

## Appendix A: Dossier Field Inventory

### Fields by Fill Rate (all 92 runs)

**Always filled (>95%):** legal_name, naics_code, naics_description, company_type, workforce_composition, organizing_summary, campaign_strengths, campaign_challenges, sources.source_list, sources.section_confidence, sources.data_gaps

**Usually filled (60-95%):** osha_violation_count, whd_case_count, osha_violation_details, osha_penalty_total, whd_employees_affected, nlrb_election_count, nlrb_election_details, existing_contracts, union_names, recommended_approach, similar_organized

**Sometimes filled (30-60%):** demographic_profile, safety_incidents, whd_backwages, worker_complaints, source_contradictions, dba_names, hq_address, recent_organizing, osha_serious_count, web_intelligence

**Rarely filled (<30%):** website_url, parent_company, major_locations, turnover_signals, job_posting_count, pay_ranges, whd_penalties, whd_repeat_violator, recent_labor_news, financial.revenue, employee_count, revenue_range, nonprofit_assets, nonprofit_revenue

**Almost never filled (<5%):** exec_compensation (3.2%), financial_trend (4.6%), job_posting_details (1.6%)

### Appendix B: Last 10 Run Dimension Scores

| Run | Company | Overall | Coverage | SrcQual | Consist | Action | Fresh | Effic |
|-----|---------|---------|----------|---------|---------|--------|-------|-------|
| 96 | XPO Logistics | 7.80 | 5.35 | 7.54 | 10.0 | 9.0 | 7.4 | 10.0 |
| 95 | Dollar General | 8.40 | 8.25 | 7.92 | 8.5 | 10.0 | 7.08 | 10.0 |
| 94 | Amazon | 8.44 | 8.28 | 7.98 | 9.5 | 10.0 | 6.65 | 8.0 |
| 93 | XPO Logistics | 7.77 | 7.19 | 8.00 | 7.0 | 9.0 | 7.29 | 8.0 |
| 92 | Dollar General | 7.75 | 5.82 | 8.83 | 10.0 | 8.0 | 5.0 | 6.0 |
| 91 | Marlin Steel | 7.42 | 6.83 | 7.49 | 5.5 | 9.0 | 7.56 | 10.0 |
| 90 | Kaiser | 7.61 | 5.53 | 8.48 | 10.0 | 8.0 | 5.36 | 6.0 |
| 89 | Amazon | 7.21 | 4.33 | 7.94 | 10.0 | 9.0 | 5.19 | 4.0 |
| 88 | XPO Logistics | 7.89 | 8.46 | 7.88 | 8.0 | — | 6.95 | 8.0 |
| 87 | Dollar General | 8.09 | 6.91 | 8.98 | 10.0 | — | 5.09 | 6.0 |

*Note: Runs 87-88 predate Phase 5.7 and don't have actionability scores.*
