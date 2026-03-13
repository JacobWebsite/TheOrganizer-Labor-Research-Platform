# PROJECT_STATE.md — Labor Relations Research Platform

> **Document Purpose:** Shared context for all AI tools (Claude Code, Codex, Gemini). Current status, active decisions, and what to work on next. For technical details, see `CLAUDE.md` in this directory. For the roadmap, see `COMPLETE_PROJECT_ROADMAP_2026_03.md` (59 tasks, 34 open questions — supersedes the Feb 26 roadmap). For redesign decisions, see `UNIFIED_PLATFORM_REDESIGN_SPEC.md`.
>
> **Detailed Sub-Roadmaps (in-depth plans for major workstreams):**
> - **Research Agent:** `RESEARCH_AGENT_ROADMAP.md` — 5 phases (R0-R5): cross-run memory, human feedback, industry synthesis, outcome tracking, deep intelligence (RAG/specialization)
> - **Union Web Scraper:** `UNION_SCRAPER_UPGRADE_ROADMAP.md` — 9 phases: 4-tier extraction (WordPress API → HTML parser → PDF cataloger → sitemap discovery) + Gemini fallback
> - **SEC EDGAR + Mergent:** `SEC_FINANCIAL_DATA_ROADMAP.md` — 7 phases: XBRL ETL (done), API integration, research agent, frontend, employee counts, Mergent full load, exec comp
> - **CBA Database Scaling:** Needs roadmap (Task 8-2)
> - **State PERB Pilot:** Needs roadmap (Task 5-3)

**Last updated:** 2026-03-12

---

## Conceptual Framework

**Non-union employers are the targets. Union employers are reference data.**

The platform helps organizers identify and evaluate non-union employers as organizing targets. Union employers (F7, NLRB wins, VR) are a reference dataset — "training data" showing what organized workplaces look like. Non-union employers are "candidates."

**Key implications:**
- The scorecard evaluates non-union employers, not union employers
- Size is a filter dimension (weight = 0), not a scoring signal
- Better union data improves targeting quality (the two pools are linked)
- Scoring uses pillar-based formula: `weighted_score = (anger*3 + leverage*4) / active_weights` (stability zeroed, dynamic denominator)
- **Stability pillar zeroed** (was weight 3, now 0) — demote to flags decision pending (D13)

---

## Current Status (2026-03-12)

| Component | Status |
|-----------|--------|
| V11 Signal Testing | **TESTED, NO IMPROVEMENT** — Education-weighted demographics (77% coverage) and SimplyAnalytics county-industry gender (100% coverage) both tested. Neither improved over V10. Education signal is industry-level (already captured). SA gender too coarse (13 sectors). Next candidate: tract-level education as geographic modifier. |
| V10 Demographics | **DONE** — Gender MAE 10.550 (best ever, replicated on sealed holdout). Hispanic calibration enabled but didn't replicate. Confidence tiers (GREEN/YELLOW/RED). See `V10_ERROR_DISTRIBUTION.md`. |
| SEC XBRL Financials (Phase 1) | **DONE** — `sec_xbrl_financials` loaded: 249K records, 14.6K companies. Revenue/NI/Assets/Liabilities/Cash/Debt. Employee counts useless (0.1%). ~490 union-linked. Next: API integration. |
| V9.2 Demographics | **SUPERSEDED by V10** — 7/7 on perm holdout. D+A race blend, d=0.85/0.05/0.5. |
| V9.1 Demographics (Hybrid) | **DONE** — 5/7 acceptance criteria pass. D race + industry+adaptive Hispanic + F gender + 3-dim calibration. P>20pp and P>30pp fail (census-based ceiling). |
| V5 Demographics (Gate v1) | **DONE** — 4-run pipeline: PUMS metro, Expert A/B/D, Gate v1 routing, OOF calibration. All 5 acceptance criteria pass on 208 fresh holdout. API integrated. |
| CBA Tool (Phases 1-4 + Decomp) | **DONE** — batch processing, OCR, frontend module, progressive decomposition (scripts 05-09), standalone search UI (`/cba-search`), 132 CBA tests |
| Batch: Union Quality + Export + NLRB Sync | **DONE** — Tasks 7-4, 7-1, 6-1, 6-2, 5-1 (see below) |
| Phase R2: Improved HITL Review UX | **DONE** — run usefulness, flag-only review, A/B comparison, section review, active learning prompts |
| Phase R1: Research Agent Learning Loop | **DONE** — contradiction detection, human fact review, learning propagation |
| Phase 5: Frontend Redesign | **DONE** — all pages with "Aged Broadsheet" theme |
| Phase 4: Target Scorecard | **DONE** — 4.4M non-union targets scored |
| Phase 3: Strategic Enrichment (A+B+C+D) | **DONE** — research quality, similarity, wage outliers, demographics |
| Phase 0-1: Trust Foundations | **DONE** — scoring fixes, NLRB ULP, momentum |
| Backend tests | **1260 pass**, 0 failures, 3 skipped |
| Frontend tests | **264 pass**, 0 failures (1 pre-existing SettingsPage) |

### Key Data Counts

| Table/MV | Rows |
|----------|------|
| f7_employers_deduped | 146,863 (67K post-2020 + 79K historical) |
| master_employers | ~4.4M (post-dedup) |
| mv_unified_scorecard | 146,863 |
| mv_target_scorecard | 4,386,205 |
| mv_employer_search | 107,321 |
| unified_match_log | ~2.2M |
| corporate_identifier_crosswalk | 17,111 |
| unions_master | 26,693 (6,053 flagged inactive) |
| cba_documents | 4 (all rule-engine-extracted) |
| cba_provisions | 267 (14-category taxonomy) |
| cba_sections | 62 (32BJ decomposed, 98.1% text coverage) |
| pums_metro_demographics | 6,538 (metro x 2-digit NAICS) |
| bds_hc_estimated_benchmarks | 630 (sector/state bracket estimates) |
| sec_xbrl_financials | 249,437 (14,638 companies, FY 2003-2025) |

---

## Active Decisions

| ID | Decision | Status |
|----|----------|--------|
| D1/D7 | No enforcement gate for any tier | **CLOSED** |
| D3 | Size weight zeroed | **DONE** |
| D6 | Kill propensity model | **DONE** |
| D4 | NLRB 25-mile: descoped | **CLOSED** |
| D5 | Industry Growth weight increase to 3x? | Open |
| D8 | Launch approach: beta with friendly unions | Open |
| D11 | Scoring framework overhaul (Anger/Stability/Leverage) | Investigating — see D13 |
| D12 | Union Proximity weight (3x despite zero power) | Open |
| D13 | **Stability pillar fate: rebuild / demote to flags / kill?** | **NEW** — leaning Option B (flags). See session notes below. |
| D14 | **Expand wage outlier coverage to 1.7M employers?** | **NEW** — bottleneck is employer-level wage data |
| D15 | ~~Form 5500 benefits integration~~ | **CLOSED** — Removed (Task 3-1). Benefits are a proxy for worker count, not a direct signal. NCS benchmarks cover industry comparisons. |

---

## Deferred Items (Do NOT Prompt About)

- Phase 2.2: Fuzzy match re-runs (SAM/WHD/990/SEC with RapidFuzz)
- Phase 2.4: Grouping quality audit
- Phase 2.5: Master dedup quality audit
- Deferred until most of the roadmap is done (user decision 2026-02-23).

---

## Next Phase: Independent Roadmap Creation

The remaining large tasks are largely independent workstreams. The next phase involves creating detailed, standalone roadmaps for each (similar to `RESEARCH_AGENT_ROADMAP.md` and `UNION_SCRAPER_UPGRADE_ROADMAP.md`). Priority order:

1. **SEC EDGAR + Mergent Full Load** (Task 8-1) — **Phase 1 DONE.** Full roadmap: `SEC_FINANCIAL_DATA_ROADMAP.md` (7 phases). Next: Phase 2 (API integration) + Phase 6 (Mergent full load) in parallel. ~12-15h for Phases 2-4 (make it visible). Mergent 1.75M employer bulk load for size/revenue/NAICS coverage.
2. **CBA Database Scaling** (Task 8-2) — Pipeline exists (4 contracts), needs sourcing strategy + batch processing plan to reach 5,000+.
3. **State PERB Pilot** (Task 5-3) — NY/CA/OH public sector data. Unlocks 5.4M public sector union members currently invisible.
4. **Union Web Scraper Expansion** (Task 8-3) — Extend AFSCME prototype to SEIU, Teamsters, UFCW, IBEW.

Each roadmap should be self-contained with phases, schema changes, scripts, validation checks, and success criteria — so any AI tool or human can execute independently.

---

## Completed — Phase R3: Research Dossier Gold Standard

All 9 tasks DONE (R3-1 through R3-9). Research dossier now covers 10 sections (up from 7): identity, corporate structure, locations, leadership, labor, workforce, workplace, financial, assessment, sources. BLS datasets (OES/SOII/JOLTS/NCS) wired into research tools. ActionLog collapses failed tools. For deeper research agent evolution, see `RESEARCH_AGENT_ROADMAP.md`.

---

## Recently Completed — Batch 2026-03-03

| Task | Summary | Files Changed |
|------|---------|---------------|
| **7-4: Stale union flags** | Added `is_likely_inactive` to `unions_master` (6,053 flagged). API `include_inactive` param. Frontend badges. | `api/routers/unions.py`, `AffiliationTree.jsx`, `UnionProfilePage.jsx`, `scripts/etl/flag_stale_unions.py` |
| **7-1: Union hierarchy** | New `GET /api/unions/hierarchy/{aff_abbr}` with intermediates (DC, JC, CONF, etc.). 4-level tree UI. | `api/routers/unions.py`, `AffiliationTree.jsx`, `shared/api/unions.js`, `scripts/etl/relink_orphan_locals.py` |
| **6-1: CSV export** | Server-side `GET /api/scorecard/unified/export` (33 cols, 10K cap). Profile CSV expanded to 33 fields. Export button on scorecard. | `api/routers/scorecard.py`, `UnifiedScorecardPage.jsx`, `ProfileActionButtons.jsx`, `shared/api/scorecard.js` |
| **6-2: Print profiles** | `@media print` CSS, `data-no-print` attributes, Print Profile button. | `index.css`, `NavBar.jsx`, `CollapsibleCard.jsx`, `ProfileActionButtons.jsx` |
| **5-1: NLRB sync** | 10-phase diff-based sync from SQLite to PG. Ready to run: `py scripts/etl/sync_nlrb_sqlite.py path.db --commit` | `scripts/etl/sync_nlrb_sqlite.py` (new) |

**New NLRB tables:** `nlrb_filings`, `nlrb_election_results`, `nlrb_voting_units`, `nlrb_sought_units` (created during initial load, expanded by sync).

**NLRB sync dry-run deltas:** ~180 elections, ~232K participants, ~24K cases, ~8K docket, ~4K allegations, ~356 tallies.

---

## Next Up — New Roadmap Triage (2026-03-01)

Working through `COMPLETE_PROJECT_ROADMAP_2026_03.md` (Round 4 audit synthesis, 62 tasks).

### Confirmed Broken (diagnostics run 2026-03-01)
| Item | Finding |
|------|---------|
| **Task 0-2: Contracts pipeline** | **0% coverage** — crosswalk has 0 federal contractors. `_match_usaspending.py` needs re-run. |
| **Task 1-1: Similarity pipeline** | **0% coverage** on unified scorecard — IDs drifted out of sync. |
| **Task 1-2: Stability pillar** | **99.6% get default 5.0** — only 515 employers have real data (wage outliers). Adds 1.5 free points to every score. |
| **Task 0-6: Matches below 0.75** | **70 active matches** — quick deactivation needed. |
| **Task 1-8: Union desig whitespace** | **5 untrimmed records** — 1-minute SQL fix. |

### Stability Pillar Investigation (2026-03-01 Session)

**Problem:** The stability pillar contributes 30% of weighted_score but has almost no real data. 99.6% of unified scorecard employers get a hardcoded 5.0 default. The pillar is supposed to measure "workforce stability" (workers stay long enough to organize) but we don't have turnover data.

**Data sources feeding stability (priority order):**
1. Research agent stability score (`rse_score_stability`) — **0 employers**
2. Research turnover rate (`turnover_rate_found`) — **0 employers**
3. QCEW wage outlier (`wage_outlier_score`) — **515 F7, 4,756 non-union** (expandable to ~128K F7 / 1.7M master with NAICS+state)
4. Research sentiment (`sentiment_score_found`) — **0 employers** (target scorecard only)

**Key insight: must work for 4.4M non-union targets, not just 147K F7 employers.**

Coverage on target scorecard:
- Form 5500 (benefits/pension): 48,663 targets (1.1%)
- PPP (workforce size, not stability): 141,415 targets (3.2%)
- Wage outliers: 4,756 non-union (0.1%), but 1.7M eligible for expansion
- Combined realistic: ~50-60K targets with real data

**Options under consideration:**

| Option | Description | Pros | Cons |
|--------|-------------|------|------|
| **A: Rebuild as "Workforce Investment"** | Combine wage outliers + Form 5500 benefits (pension, welfare, years filed) into new pillar | Measures something real and distinct from anger/leverage | Still only ~50-60K targets covered (1.3%) |
| **B: Demote to flags** | Add `has_pension`, `has_welfare`, `is_wage_outlier` as filterable boolean flags on target scorecard. Not a pillar. | Immediately useful for filtering ("show employers with no benefits"). No fake scores. | Loses pillar structure |
| **C: Kill entirely** | Zero the weight, revisit when WARN Act / actual turnover data available | Simplest. Stops the 5.0 damage immediately. | Loses the signal entirely |

**User leaning toward Option B** — make Form 5500 benefits and wage data into filterable flags rather than pretending to score 4.4M employers on workforce investment.

**Regardless of option chosen, stability weight should be zeroed immediately (Option A quick fix from Task 1-2) to stop the 5.0 default damage.**

### Pending Decisions (new from this session)

| ID | Decision | Context |
|----|----------|---------|
| D13 | Stability pillar: rebuild as "Workforce Investment", demote to flags, or kill? | See investigation above. User leaning toward flags (Option B). |
| D14 | Expand wage outlier coverage to all 1.7M NAICS+state employers? | Currently only 5.4K. Requires employer wage data (bottleneck). |
| D15 | Form 5500 benefits integration approach? | Task 3-1 in roadmap. 259K EINs available, ~48K already linked to targets. |

---

## Audit-Validated Findings

**Round 2 (Feb 25-26, 2026):** Full reports in `audits 2_25_2_26/`. Summary:
- **Score IS predictive** — win rates monotonic by tier (Priority 90.9% -> Low 74.1%)
- **NLRB strongest signal** (+10.2pp), Industry Growth underweighted (+9.6pp)
- **Data richness paradox** — fewer factors = higher win rate (2-factor 88.2% vs 8-factor 73.4%)
- **Selection bias** — only 34% of NLRB elections link to scored employers
- **Priority tier: 86% lack enforcement data** — enforcement gate rejected
- **Fuzzy match FP rates** — 0.80-0.85=40-50%, below-0.85 deactivated
- **Propensity model killed** — was hardcoded formula, coin-flip accuracy

**Round 4 (Mar 2026):** Full reports in project root (`ROUND_4_AUDIT_REPORT_*.md`). Key NEW findings:
- Contracts pipeline broken (0% coverage on unified scorecard)
- Similarity pipeline broken (0% coverage on unified scorecard)
- Stability pillar 99.6% default (investigated in detail this session)
- OSHA severity not weighted (willful vs other treated equally)
- Child labor + repeat violator flags unused
- Close election flag missing (5,356 elections lost by <=5 votes)
- NLRB docket data unused (2M rows)
- Union disbursement data unused (216K rows)

---

## Session History

Historical session updates (Feb 2026) archived to `archive/docs/session_history_2026_03.md`. See git log for change-by-change details.

### 2026-03-12: SEC XBRL Phase 1 ETL

- Downloaded `companyfacts.zip` (1.3GB, 19,298 companies) to `data/sec/`.
- Built `scripts/etl/load_sec_xbrl.py` — parses all company JSON files, extracts 7 financial concepts with tag variant mapping (6 revenue tags, 3 net income tags, etc.), loads via COPY.
- **`sec_xbrl_financials` table**: 249,437 rows, 14,638 unique companies, FY 2003-2025.
- **Coverage**: Revenue 73%, NetIncome 94%, Assets 46%, Liabilities 46%, Cash 51%, Debt 21%, Employees 0.1%.
- **Key finding**: Employee counts (262 companies) and CEO pay ratio are NOT in companyfacts.zip for most filers. Employee headcount is typically prose in 10-K Item 1, not a structured XBRL tag.
- **Union linkage**: ~490 companies via UML, ~290 with revenue since 2023.
- Spot-checked Walmart ($681B rev), Amazon ($717B), HCA ($75.6B), Starbucks ($37.2B) — all correct.
- Also evaluated DERA quarterly flat files (`2025q4.zip`) — easier for COPY but missing DEI tags. companyfacts.zip preferred.
- **Next**: Wire into API employer profiles (Phase 4), investigate employee count extraction from 10-K text.

### 2026-03-12: CBA Progressive Decomposition + Search UI

- Built complete progressive decomposition pipeline (scripts 05-09): TOC parser, section splitter, page image extractor, section enrichment, orchestrator.
- **DB migration:** `cba_sections` + `cba_page_images` tables, `toc_json`/`decomposition_status` columns on `cba_documents`.
- **32BJ validation:** 62 sections extracted, 98.1% text coverage, multi-line title fragmentation is known Round 0 limitation.
- **Standalone search UI** at `/cba-search`: smart query parsing (e.g., "Healthcare 32BJ"), 3 tabs (Provisions/Sections/Contracts), category auto-detect, section detail modal with linked provisions.
- **API endpoints:** `/api/cba/sections/search` (text + category + employer/union filters) + `/api/cba/sections/{id}` (full text + linked provisions).
- **47 new tests** (27 TOC parser + 20 section splitter), 132 CBA tests total, 0 failures.
- **Key technical findings:** `importlib.import_module()` required for numeric-prefixed Python modules; section splitter must skip TOC lines via dotted-leader detection; CORS file:// origin sends "null".
- **New files:** `05_parse_toc.py`, `06_split_sections.py`, `07_extract_page_images.py`, `08_enrich_sections.py`, `09_decompose_contract.py`, `cba_search.html`, `sql/schema/cba_sections_migration.sql`, 2 test files.

### 2026-03-11: V9.1 Demographics Hybrid Architecture

- Implemented V9.1 partial-lock IPF architecture with industry+adaptive Hispanic estimator. Partial-lock race assembly FAILED (Frankenstein vector problem, +4.6pp White bias from budget mismatch).
- **Hybrid architecture works:** D race intact + industry+adaptive Hispanic + F gender + 3-dimension calibration (race d=0.8, hisp d=0.3, gender d=1.0).
- **5/7 acceptance criteria pass** on 1,000 permanent holdout: Race=4.483, Hisp=6.697, Gender=10.798, AbsBias=0.330, HS_tail=13.9%.
- **P>20pp=17.1% and P>30pp=7.7% still fail** -- tail errors driven by county diversity (86% White overestimation in diverse counties). Census-based estimation ceiling confirmed.
- Industry+adaptive Hispanic: grid-searched weights for 5 high-bias industries + tier-adaptive by county Hispanic concentration. LODES Hispanic data 95.2% coverage.
- Gender calibration (71 region x industry buckets, d=1.0) was key breakthrough: 12.4 -> 10.8.
- Comprehensive tail analysis by sector, region, county diversity, state. Manual county-diversity adjustments can't fix (errors 30-80pp, linear shifts insufficient).
- **Scripts:** `run_v9_1_partial_lock.py`, `test_expert_combos.py`, `test_dampening_grid.py`, `analyze_tails.py`, `analyze_tails_bias.py`, `test_manual_adjustment.py`

### 2026-03-09: V5 Demographics Pipeline Execution

- Executed full V5 Demographics Estimation pipeline (4 sequential runs) implementing learned routing between 3 expert models.
- **Run 1:** Loaded PUMS metro data (6,538 profiles from 34.1M rows). Evaluated 30 methods on 997 companies. Fixed zero-collapse bug in `_blend_dicts()` code paths. Admin/Staffing routing fix confirmed. PUMS coverage 73.5%.
- **Run 2:** Gate v0 (5-class routing) failed -- collapsed to M3b for all companies. M8 retained.
- **Run 3:** Generated OOF predictions for Expert A/B/D. Expert D wins 52%, A 25%, B 23%.
- **Run 4:** Gate v1 (3-class, 59.8% CV accuracy) passes all 5 acceptance criteria on 208 fresh holdout companies. Race MAE 5.18 vs M3b 5.23, bias 1.35 vs 1.72.
- **BDS nudge analysis:** Net negative (+0.045 MAE). Bracket data too coarse for company-level corrections. Recommend using as validation flag only.
- **API integration:** `/api/profile/employers/{id}/workforce-profile` now uses V5 Gate v1 with old 60/40 blend as fallback.
- **Bug fixes:** sklearn `multi_class` removal, numpy dtype mixing, NoneType `.get()` in expert disagreement, `_floor_result()` for blend methods.
- **New DB tables:** `pums_metro_demographics`, `bds_hc_estimated_benchmarks`
- **Full report:** `scripts/analysis/demographics_comparison/V5_COMPLETE_RESULTS.md`
- Tests: 1213 backend, 264 frontend, all passing.

### 2026-03-08: Demographics Methodology Comparison Framework
- Built complete comparison framework: 6 estimation methods tested against 10 EEO-1 ground-truth companies (16,798 federal contractors, FY2016-2020).
- **Scripts:** `scripts/analysis/demographics_comparison/` (8 files: config, eeo1_parser, select_companies, data_loaders, methodologies, metrics, bds_hc_check, run_comparison).
- **Methods tested:** M1 Baseline (60/40), M2 Three-Layer (50/30/20), M3 IPF, M4 Occ-Weighted, M5 Variable-Weight, M6 IPF+Occ.
- **Winner: M1 Baseline (60/40 ACS/LODES)** -- avg race MAE 6.8, Hellinger 0.206. Simple blend is hardest to beat.
- **IPF (M3/M6) worst for race** -- overestimates White by avg +30pp due to multiplicative majority amplification. But best for gender (wins 6/10).
- **Systematic bias across ALL methods:** overestimates White by ~10pp, underestimates Black by ~10pp. ACS + LODES have structural White bias relative to EEO-1.
- **Hardest cases:** OSI Industries (60% Black, best MAE=13.7), Alexander & Baldwin HI (NHOPI gap, -33pp), staffing agency (20pp gender error).
- **10 companies span 7 benchmark axes:** industry-dominant (nursing, aerospace), geography-dominant (food processing), demographic stratification (hotels), size extremes (1K-121K), majority-minority county (HI), staffing agency (hard case).
- Tests: 1213 backend, 264 frontend, all passing.
- **Next:** Consider hybrid (M1 for race, M3 for gender), investigate White overestimation, wire winner into production API.

### 2026-03-07: CBA Tool Improvement (Phases 1-4)
- Implemented full CBA roadmap: schema migration, context expansion (600->1500 char cap, 100->500 context window), entity linking, batch processor, OCR support, 4 frontend pages + 4 API endpoints.
- **Re-processed contracts 21-23** from AI extraction to rule engine: 612 AI provisions -> 198 rule-engine provisions across 14 categories. All 4 contracts now consistent.
- **Batch processor** (`scripts/cba/batch_process.py`): drop PDFs in `data/cba_inbox/`, SHA-256 dedup, auto-processing, moves to `data/cba_processed/`.
- **Frontend CBA module**: Dashboard (/cbas), Detail (/cbas/:cbaId), Search (/cbas/search), Compare (/cbas/compare). Nav link added.
- **OCR fallback**: pytesseract integration in `01_extract_text.py` for scanned PDFs (requires system Tesseract install).
- Entity linking: matched employer_id for cba 21/22, f_num for cba 23.
- Tests: 1211 backend, 264 frontend, all passing.
- **Next:** Manual review checkpoint, then batch-process more CBAs. Phase 5 (rule improvements) after 10+ contracts.

### 2026-03-07: Full Scraper Pipeline Run + WP Employer Cleanup
- Ran full extraction pipeline (`run_extraction_pipeline.py --continue-on-error`) across all 103 union web profiles (~35 min).
- **Results:** 167 -> 2,208 employers, 72 -> 87/103 profiles covered (84%), 1,189 -> 37,241 pages discovered, 206 -> 909 PDF links.
- Employers by method: wp_api 2,006, ai_extract 160, gemini_fallback 37, auto_extract_v2 5. Gemini cost < $0.01.
- Built `scripts/scraper/clean_wp_employers.py` -- pattern-based filter for wp_api noise (person names, sentences, politicians, job descriptions, forms).
- Added `validated` BOOLEAN column to `web_union_employers`. Flagged 686 invalid, 1,522 validated.
- 16 profiles still have 0 employers. Known noisy profiles (HGEA, UDW, Harvard) deferred for second cleanup pass.
- **Next steps:** Second cleanup pass (deferred), fetch 37K discovered page HTML, PDF extraction, match validated employers against F7/OSHA.
- New file: `scripts/scraper/clean_wp_employers.py`

### 2026-03-05: Task 1-11 (Min-data threshold warning) + mark done tasks
- Added `factors_available`, `factors_total`, `weighted_score`, `score_tier` to `mv_employer_search` (joined from `mv_unified_scorecard` for F7; NULL for NLRB/VR/MANUAL).
- API `unified-search` now returns these 4 fields + supports `min_factors` filter parameter.
- `SearchResultCard` shows color-coded factors badge for F7 employers (green >=5, tan >=3, amber <3).
- Marked 4 tasks DONE in roadmap: R3-9 (BLS in research tools), 3-6 (union disbursements), 3-2 (USAspending tiers), 5-4 (BLS benefit surveys).
- Tests: 1160 backend (+3), 261 frontend (+3), all passing.

### 2026-03-04: R3-1 ActionLog collapse
- Refactored `ActionLog.jsx` from flat table to 3-category layout: found (full table), errored (red styling + AlertTriangle), not-found (collapsed summary line, click to expand)
- Summary bar shows counts: "3/6 tools found data | 1 error | 1.0s total"
- CollapsibleCard summary updated with category breakdown
- New test file `__tests__/ActionLog.test.jsx` (9 tests), updated `ResearchResult.test.jsx` mock data
- Frontend tests: 249 pass, 1 pre-existing failure (SettingsPage duplicate "osha" text)
- Not committed

### 2026-03-03: Research Gold Standard gap analysis + Phase R3 roadmap
- Compared organizer-defined "12 questions a gold standard report must answer" against current 30-tool research agent.
- **Well covered:** Company identity, NAICS, company type, union/NLRB (strongest area), worker sentiment, job postings, demographics, wages, federal enforcement (OSHA/WHD/SAM/PPP/5500), industry growth, latest news.
- **Major gaps identified:**
  - Q2 (corporate structure): No systematic parent/subsidiary/investor discovery. GLEIF coverage thin.
  - Q4a (multi-location): No tool to find all employer locations across geography.
  - Q6 (leadership): No CEO/C-suite/local management extraction. SOS filings only capture legal officers.
  - Q10b (geographic union density): Only national density available, no state/county/zip breakdown.
  - Q11a/d (state/local enforcement): Only federal + NYC. No state DOL or municipal procurement data.
- **UX issue:** ActionLog treats "not found" (expected) and "errored" (unexpected) identically. Failed tools consume as much visual space as successful ones, making the log mostly noise.
- Created **Phase R3: Research Dossier Gold Standard** (8 tasks) in roadmap between Phase 4 and Phase 5.
- Added 4 new open questions to Master Open Questions (17a-17d).
- No code changes; roadmap and project state updates only.

### 2026-03-03: Batch implementation (7-4, 7-1, 6-1, 6-2, 5-1)
- Implemented 5 tasks in parallel using 3 worktree-isolated agents (union-quality, export-print, nlrb-sync).
- **Task 7-4:** Added `is_likely_inactive` column to `unions_master` (6,053 of 26,693 flagged). API `include_inactive` param on national endpoints. Frontend badges in AffiliationTree + amber banner on UnionProfilePage.
- **Task 7-1:** New `GET /api/unions/hierarchy/{aff_abbr}` endpoint. Classification helper `_classify_union_level()` using `desig_name` codes (DC, JC, CONF, etc.). 4-level tree in AffiliationTree (Affiliation -> Intermediate -> State -> Local). Added `parent_fnum` column. Relink script for orphan locals.
- **Task 6-1:** Server-side `GET /api/scorecard/unified/export` (33 columns, 10K cap, StreamingResponse). Profile CSV expanded from 12 to 33 fields. Export button on UnifiedScorecardPage.
- **Task 6-2:** `@media print` CSS in index.css. `data-no-print` on NavBar/Layout. Print Profile button. CollapsibleCard forced open in print.
- **Task 5-1:** `sync_nlrb_sqlite.py` -- 10-phase diff-based sync from SQLite to PostgreSQL. Dry-run deltas: ~180 elections, ~232K participants, ~24K cases. Ready to run with `--commit`.
- **Bug fix:** Removed nonexistent `desig_num` column from hierarchy SELECT. Fixed test collision (`'12 locals'` appearing twice).
- **Tests:** 1135 backend (+32), 240 frontend (+7), all passing.

### 2026-03-03: Dual RPE validation
- Rewrote `scripts/analysis/validate_rpe_estimates.py` with two independent ground truths:
  - **GT-A (NLRB elections):** eligible_voters * BLS supervisor multiplier = actual employees. 625 whole-company cases after filtering, 530 with RPE match.
  - **GT-B (990 self-reported):** 990 filers with both total_revenue and total_employees. 8,759 records, 7,793 with RPE match.
- Built supervisor ratio lookup from `bls_industry_occupation_matrix` (355 NAICS prefixes, SOC 11-xxxx + first-line supervisors).
- **Key finding: both ground truths agree geographic RPE does NOT improve over national.** State/county are 1-2pp worse on Within50%.
- GT-B accuracy: National Med.Err=58.8%, W50%=49.1%. Healthcare best sector (50% err), Construction worst (64% err).
- GT-A accuracy much worse (95% median error) -- small nonprofits where BU size may not reflect whole company well.
- Wrote methodology summary: `docs/rpe_methodology_summary.md`
- All 23 existing RPE tests still pass.
- **Recommendation:** use national RPE only, drop geographic cascade from scoring CTEs.

### 2026-03-01: Roadmap merge + stability investigation
- Merged Round 2 roadmap items into `COMPLETE_PROJECT_ROADMAP_2026_03.md` (5 missing items added: launch strategy, RPE estimates, demographics, research quality frontend, PERB state alternatives). Now 62 tasks, 36 open questions (1-7 removed 2026-03-02).
- Ran diagnostics on Phase 0 emergency items: confirmed contracts (0%), similarity (0%), stability (99.6% default), 70 sub-0.75 matches, whitespace issues.
- Deep investigation of stability pillar: traced all 4 data sources, checked coverage on both scorecards, assessed Form 5500 / PPP / QCEW expansion potential for 4.4M targets.
- Decision pending: stability pillar fate (D13). Leaning toward demoting to filterable flags (Option B).
