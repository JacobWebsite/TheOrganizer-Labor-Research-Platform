# Session Summary: Research Deep Dive — Frontend + Web Search + Name Matching
**Date:** 2026-02-23
**Duration:** ~4 hours (across 2 context windows)
**Agent:** Claude Opus

## What Was Done

### 1. Research Agent Frontend (13 new files + 6 modifications)

Built the complete frontend for the research deep dive system.

**New files:**
1. `frontend/src/shared/api/research.js` — 5 TanStack Query hooks (start, status polling, result, runs list, vocabulary)
2. `frontend/src/features/research/ResearchPage.jsx` — List page at `/research` with filters, table, "New Research" button
3. `frontend/src/features/research/useResearchState.js` — URL-driven filter/page state (status, q, page)
4. `frontend/src/features/research/ResearchFilters.jsx` — Status dropdown + company name search with 300ms debounce
5. `frontend/src/features/research/ResearchRunsTable.jsx` — Table with status badges, duration, facts, quality, pagination
6. `frontend/src/features/research/NewResearchModal.jsx` — Modal: company name (required) + optional NAICS/state/type
7. `frontend/src/features/research/ResearchResultPage.jsx` — Full dossier view at `/research/:runId`
8. `frontend/src/features/research/DossierHeader.jsx` — Run metadata, animated progress bar, "Run Again" button
9. `frontend/src/features/research/DossierSection.jsx` — Collapsible section with smart rendering for nested data
10. `frontend/src/features/research/FactRow.jsx` — Single fact row with confidence dots
11. `frontend/src/features/research/ActionLog.jsx` — Collapsible tool execution log table
12. `frontend/__tests__/ResearchPage.test.jsx` — 10 tests
13. `frontend/__tests__/ResearchResult.test.jsx` — 12 tests

**Modified files:**
1. `api/routers/research.py` — Fixed `employer_id` type `int`->`str` (DB uses hex TEXT), added `q` search param to `/runs`
2. `frontend/src/App.jsx` — Added `/research` and `/research/:runId` routes
3. `frontend/src/shared/components/NavBar.jsx` — Added "Research" nav item with Microscope icon
4. `frontend/src/shared/components/Breadcrumbs.jsx` — Added `research` label
5. `frontend/src/shared/components/PageSkeleton.jsx` — Added `research` + `research-result` skeleton variants
6. `frontend/src/features/employer-profile/ProfileActionButtons.jsx` — Added Deep Dive button with Sonner toast progress polling

### 2. Web Search via Gemini Google Search Grounding

Added web search capability to the research agent using Gemini's native Google Search grounding.

**Key changes to `scripts/research/agent.py`:**
- Three-phase approach: Phase 1 (DB function calling) → Phase 2 (Google Search grounding in separate API call) → Phase 3 (patch-based merge)
- `_build_google_search_tool()` — Returns `types.Tool(google_search=types.GoogleSearch())`
- System prompt step 3: Web search instructions with suggested queries
- Grounding metadata logging to `research_actions` table
- Fallback: saves original dossier before web merge, restores on failure

**Critical discovery:** Gemini API cannot combine `function_declarations` and `google_search` tools in the same request (returns 400 INVALID_ARGUMENT). Must use separate API calls.

**Patch-based merge:** Instead of asking Gemini to reproduce entire 40K+ char dossier JSON, it returns a small JSON patch (`assessment_additions`, `web_facts`, `web_sources`) applied programmatically. This solved the reliability problem where Gemini couldn't reproduce large JSON without syntax errors.

### 3. Name Matching Fix Across All 8 DB Tools

**Problem:** `LIKE '%FED EX%'` does NOT match `FEDEX` (no space). Same issue for all companies with space variants.

**Solution in `scripts/research/tools.py`:**
- `_name_like_clause()` helper generates both original and space-stripped LIKE patterns
- Applied to: `search_osha`, `search_nlrb` (participants + voluntary recognition), `search_whd`, `search_sec`, `search_sam` (entities + contract recipients), `search_990`, `search_contracts`, `search_mergent`
- SEC additionally sorts by `is_public DESC, LENGTH(company_name) ASC` to prefer real companies over ABS/derivative names

### 4. Dossier Rendering Bug Fix

Fixed `[object Object]` rendering in dossier sections:
- Data path: `dossier_json.dossier` not directly `dossier_json`
- `RenderValue` component handles: strings, arrays of strings (bullets), arrays of objects (auto tables), nested objects (key-value), booleans, numbers
- Empty sections auto-hidden

## Errors Encountered and Fixed

1. **400 INVALID_ARGUMENT** — Can't mix `function_declarations` + `google_search` → two-phase approach
2. **FedEx SEC finding Lehman ABS** — Space-stripped LIKE patterns + `is_public DESC` sort
3. **JSON parse failure on merge** — Full dossier rewrite too large → patch-based approach
4. **Patch extraction expecting "dossier" key** — Generic JSON extraction via regex + raw parse fallback
5. **API serving stale code** — Clear `__pycache__`, kill all Python processes, restart fresh

## Commits
- `12490dd` — Add research deep dive frontend: list page, dossier viewer, profile integration
- `40d2c4e` — Improve research dossier rendering with smart type-aware display
- `25f3d9d` — Add web search to research agent via Gemini Google Search grounding
- `d071bac` — Fix research agent name matching and web merge reliability
- `63b8f79` — Add research agent session summary and update OSHA checkpoint

## Test Results
- **156 frontend tests** (23 files), all passing (was 134 / 21 files)
- **492 backend tests**, 491 pass / 1 skip (unchanged)
- **~20 research runs** completed (Penske, FedEx, and others via frontend)

## Research Agent Phase 5 Status

| Sub-phase | Status | Notes |
|-----------|--------|-------|
| 5.1.1 Internal DB tools | DONE | 10 tools working |
| 5.1.2 External tools | PARTIAL | Web search DONE (Gemini grounding). `scrape_employer_website` + `search_job_postings` stubs only |
| 5.1.3 Logging tables | DONE | `research_runs`, `research_actions`, `research_facts` |
| 5.1.4 Agent prompt | DONE | 7-section dossier, guided autonomy, web search instructions |
| 5.1.5 Orchestration | DONE | Gemini tool use + web search + patch merge |
| 5.1.6 Test runs | ~20 done | Need 10-15 more across diverse industries |
| Frontend | DONE | List, dossier viewer, profile integration, progress polling |
| 5.2 Strategy Memory | NOT STARTED | Table exists, not populated or injected |
| 5.3 Auto Scoring | NOT STARTED | |
| 5.4 Query Refinement | DEFERRED | Needs 100+ runs |

## What's Next
- **5.1.6:** Run 10-15 more companies across diverse industries (healthcare, manufacturing, hospitality, building services, retail, transportation)
- **Employer website scraper:** `scrape_employer_website` Crawl4AI integration
- **5.2 Strategy Memory:** Aggregate action logs → `research_strategies`, inject into prompt
- **5.3 Auto Scoring:** Post-run quality grading
- **Phase 2 (Matching Quality Overhaul):** Available in parallel
