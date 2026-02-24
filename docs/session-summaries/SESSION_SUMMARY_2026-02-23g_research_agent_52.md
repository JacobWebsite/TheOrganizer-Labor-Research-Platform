# Session Summary: 2026-02-23g — Research Agent Phase 5.2

**Duration:** ~1 hour
**Focus:** Research Agent reliability, caching, gap-aware web search

---

## What Was Done

### Part A: Fix Dossier Reliability (10.6% zero-fact failure rate)

**Problem:** 5 of 47 completed runs produced 0 saved facts because the fallback extractor (`_extract_fallback_facts`) used attribute names not in the vocabulary table, so `_save_facts` silently dropped them.

**Fixes applied:**
- Fixed 5 broken `_TOOL_FACT_MAP` entries:
  - `nonprofit_employees` -> `employee_count` (already in vocab)
  - `nonprofit_ein` -> removed (EIN is an identifier, not a research fact)
  - `annual_revenue` -> `revenue` (already in vocab)
  - `company_website` -> `website_url` (already in vocab, 2 occurrences)
- Added `federal_contract_status` to vocabulary (SQL seed + runtime `_ensure_vocab_entries()`)
- Updated `_ATTR_SECTION` map to match corrected `_TOOL_FACT_MAP`
- Added JSON repair Strategy 4: strips non-JSON prefix before first `{` (handles Gemini prefixing explanatory text before JSON)

### Part B: Result Caching

**Problem:** Re-running an employer repeated all 10 DB queries (~5s). Tool results were already persisted in `research_actions` but never reused.

**Solution:**
- Added `_check_cache(employer_id, tool_name)` — looks up `research_actions` for recent successful results within 7-day window (configurable via `RESEARCH_CACHE_HOURS` env var)
- Cache check runs before each tool dispatch in the agent loop
- Cached results logged with `(cached)` indicator in tool_name

**Verification (Starbucks repeat run):**
- Run 52: 120s, 45,560 tokens, 6 cents
- Run 53 (cached): 100s, 32,711 tokens, 4 cents
- 5 cache hits: search_osha, search_nlrb, search_whd, get_industry_profile, get_similar_employers

### Part C: Gap-Aware Web Search with Learning

**Problem:** Static 6-query web search ran the same queries regardless of which DB tools hit or missed. When Mergent missed (48% miss rate), there was no compensating query for employee count, revenue, or website.

**Solution:**
- `_GAP_QUERY_TEMPLATES`: 10 gap types with 1-3 targeted search templates each
- `_TOOL_GAP_MAP`: Maps tool names (search_mergent, search_osha, etc.) to gap types they cover
- `_build_web_search_queries()`: Generates 8-15 targeted queries based on which DB tools missed, capped at 15
- `_get_best_queries()`: Queries `research_query_effectiveness` table for proven templates (min 3 uses)
- `_update_query_effectiveness()`: Tracks hit rates per gap_type + template after each run
- Web prompt now uses dynamically built query list instead of static 6

**Verification (Starbucks run 52):**
- 5 DB gaps: SEC, SAM, contracts, Mergent, scraper
- 8 targeted queries generated (vs old static 6)
- Google Search queries included: "Starbucks number of employees", "Starbucks workforce size headcount", "Starbucks annual revenue sales", "Starbucks revenue financial results 2025", "Starbucks official website CA"
- Merged: 40 sources, 8 news items, 8 organizing, 5 worker issues

**Learning table after 2 runs:**
- `labor_stance` queries: 2/2 (100% hit rate)
- `recent_news` queries: 2/2 (100% hit rate)
- `worker_conditions` queries: 2/2 (100% hit rate)
- `employee_count` queries: 0/3 (structured fact extraction issue, not search issue)

---

## Files Changed

| File | Change |
|------|--------|
| `scripts/research/agent.py` | Fixed vocabulary, added caching, gap-aware search, query learning (+715 lines) |
| `sql/create_research_agent_tables.sql` | Added `federal_contract_status` vocab, `research_query_effectiveness` table |
| `tests/test_research_agent_52.py` | **New** — 31 tests across 7 test classes |

## New DB Table

- `research_query_effectiveness` — Tracks web search query template effectiveness per gap type. UNIQUE on (gap_type, query_template). Auto-creates on first use.

## Test Results

- **31 new tests** (7 classes): TestToolFactMapVocabulary (5), TestJsonRepair (8), TestCheckCache (3), TestBuildWebSearchQueries (7), TestQueryEffectiveness (4), TestGapQueryTemplates (4)
- **549 total pass / 1 skip** (was 518 pass / 1 skip) — zero regressions
- Committed: `5d343fb`, pushed to origin/master

## Impact Summary

| Metric | Before | After |
|--------|--------|-------|
| Runs with 0 facts | 10.6% (5/47) | ~0% (fallback fixed) |
| Repeat employer time | ~120s | ~100s (cached, -17%) |
| Repeat employer tokens | ~45K | ~33K (cached, -28%) |
| Repeat employer cost | 6 cents | 4 cents (-33%) |
| Web search queries | 6 static | 8-15 gap-targeted |
| Query improvement | None | Automatic via effectiveness tracking |
