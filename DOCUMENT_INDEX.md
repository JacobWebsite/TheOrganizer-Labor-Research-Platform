# Document Index

> Last updated: 2026-03-12
> Status key: **ACTIVE** (in use) | **REFERENCE** (useful background) | **ARCHIVE** (superseded, will move to `archive/`)

---

## Tier 1: Auto-Loaded Context
| File | Status | Purpose |
|------|--------|---------|
| `CLAUDE.md` | ACTIVE | Constitution -- auto-loaded every session (~434 lines) |
| `MEMORY.md` (auto-memory) | ACTIVE | Slim index with pointers to topic files (~72 lines) |

## Core Project Documents
| File | Status | Purpose |
|------|--------|---------|
| `COMPLETE_PROJECT_ROADMAP_2026_03.md` | ACTIVE | Authoritative roadmap (62 tasks, 36 open questions) |
| `docs/DEMOGRAPHICS_METHODOLOGY_COMPARISON.md` | REFERENCE | Initial 200-company comparison (6 methods). Superseded by V5. |
| `scripts/analysis/demographics_comparison/V5_COMPLETE_RESULTS.md` | ACTIVE | V5 complete results: 30 methods, 997 training + 208 holdout, Gate v1 pipeline |
| `scripts/analysis/demographics_comparison/V5_FINAL_REPORT.md` | ACTIVE | V5 final validation summary (acceptance criteria) |
| `scripts/analysis/demographics_comparison/GATE_V0_EVALUATION.md` | REFERENCE | Gate v0 evaluation (rejected, M8 retained) |
| `scripts/analysis/demographics_comparison/V9_1_METHODOLOGY_AND_RESULTS.md` | ACTIVE | V9.1 full methodology, results, tail analysis, and conclusions |
| `scripts/analysis/demographics_comparison/run_v9_1_partial_lock.py` | ACTIVE | V9.1 hybrid architecture: D race + industry+adaptive Hispanic + F gender |
| `scripts/analysis/demographics_comparison/test_dampening_grid.py` | ACTIVE | Dampening grid search + gender calibration (key breakthrough) |
| `scripts/analysis/demographics_comparison/analyze_tails.py` | ACTIVE | Tail error distribution by sector, region, county diversity, state |
| `scripts/analysis/demographics_comparison/analyze_tails_bias.py` | ACTIVE | Signed bias per race category for every bucket and error tier |
| `scripts/analysis/demographics_comparison/run_v10.py` | ACTIVE | V10 pipeline: Hispanic calibration hierarchy, gender dampening, confidence tiers |
| `scripts/analysis/demographics_comparison/select_v10_holdout.py` | ACTIVE | V10 sealed holdout (1000 companies) + training set creation |
| `scripts/analysis/demographics_comparison/estimate_confidence.py` | ACTIVE | Standalone GREEN/YELLOW/RED confidence tier classifier |
| `scripts/analysis/demographics_comparison/gen_v10_error_report.py` | ACTIVE | V10 error distribution by sector, region, tier, confidence |
| `scripts/analysis/demographics_comparison/V10_ERROR_DISTRIBUTION.md` | ACTIVE | V10 full error analysis report with per-dimension breakdowns |
| `scripts/analysis/demographics_comparison/test_v11_signals.py` | ACTIVE | V11 signal testing: education-weighted demographics + SimplyAnalytics gender (neither improved over V10) |
| `V10_CLAUDE_CODE_PROMPT.md` | REFERENCE | V10 implementation specification (6 phases, acceptance criteria) |
| `docs/UNION_WEB_SCRAPER.md` | ACTIVE | Consolidated scraper docs (pipeline, schema, extraction, expansion) |
| `README.md` | ACTIVE | Project overview |
| `DOCUMENT_INDEX.md` | ACTIVE | This file -- master catalog |
| `PROJECT_CATALOG.md` | ACTIVE | Comprehensive file catalog (~755 code files, all sections) |
| `PIPELINE_MANIFEST.md` | REFERENCE | Script inventory with run order (superseded by PROJECT_CATALOG) |
| `PLATFORM_HELP_COPY.md` | ACTIVE | UI help text for frontend |
| `RESEARCH_AGENT_ROADMAP.md` | ACTIVE | Active research agent task list |
| `FRONTEND_REDESIGN_INSTRUCTIONS.md` | ACTIVE | Aged Broadsheet design reference |
| `CBA_DATABASE_BUILD_PLAN.md` | ACTIVE | Active CBA pipeline work |
| `CBA_PROVISION_TAXONOMY.md` | ACTIVE | Active CBA taxonomy |
| `CODEX_INVESTIGATION_REPORT_2026_03.md` | REFERENCE | Recent (Mar 3) Codex investigation |
| `deep-research-report.md` | REFERENCE | Foundational deep research |
| `deep-research-report_RPE.md` | REFERENCE | RPE-specific deep research |

## Superseded Roadmaps
| File | Status | Superseded By |
|------|--------|---------------|
| `MASTER_ROADMAP_2026_02_23.md` | ARCHIVE | `COMPLETE_PROJECT_ROADMAP_2026_03.md` |
| `UNIFIED_ROADMAP_FINAL_2026_02_26.md` | ARCHIVE | `COMPLETE_PROJECT_ROADMAP_2026_03.md` |
| `SCORECARD_REVISION.md` | ARCHIVE | Scoring spec in agents/scoring.md |
| `SCORING_SPECIFICATION.md` | ARCHIVE | Scoring spec in agents/scoring.md |
| `DATA_SOURCE_EXPANSION_PLAN.md` | ARCHIVE | Absorbed into March roadmap |
| `Future_Projects_Post_Launch_Goals.md` | ARCHIVE | Absorbed into March roadmap |

## Audit Reports & Prompts
| File | Status | Purpose |
|------|--------|---------|
| `AUDIT_CLAUDE_CODE_2026-02-18.md` | ARCHIVE | Round 1 audit report |
| `AUDIT_REPORT_GEMINI_2026-02-18.md` | ARCHIVE | Round 1 Gemini audit |
| `AUDIT_PROMPT_CLAUDE_CODE.md` | ARCHIVE | Round 1 prompt |
| `AUDIT_PROMPT_CODEX.md` | ARCHIVE | Round 1 prompt |
| `AUDIT_PROMPT_GEMINI.md` | ARCHIVE | Round 1 prompt |
| `INDEPENDENT_AI_AUDIT_PROMPT_2026-02-18.md` | ARCHIVE | Round 1 unified prompt |
| `THREE_AGENT_AUDIT_PROMPTS_v2.md` | ARCHIVE | Round 2 prompts |
| `FOUR_AUDIT_SYNTHESIS_v3.md` | ARCHIVE | Round 2 synthesis |
| `ROUND_3_AUDIT_PLAN_v3.md` | ARCHIVE | Round 3 plan |
| `ROUND_3_AUDIT_REPORT_CODEX.md` | ARCHIVE | Round 3 Codex report |
| `ROUND_3_AUDIT_REPORT_GEMINI.md` | ARCHIVE | Round 3 Gemini report |
| `ROUND_4_UNIFIED_AUDIT_PROMPT.md` | ARCHIVE | Round 4 prompt |
| `ROUND_4_AUDIT_REPORT_CLAUDE_CODE.md` | ARCHIVE | Round 4 Claude report |
| `ROUND_4_AUDIT_REPORT_CODEX.md` | ARCHIVE | Round 4 Codex report |
| `ROUND_4_AUDIT_REPORT_GEMINI.md` | ARCHIVE | Round 4 Gemini report |

## Prompt Files
| File | Status | Purpose |
|------|--------|---------|
| `PROMPT_CLAUDE_CODE.md` | ARCHIVE | Old Claude Code prompt |
| `PROMPT_CLAUDE_CODE_R2.md` | ARCHIVE | R2 Claude Code prompt |
| `PROMPT_CODEX.md` | ARCHIVE | Codex prompt |
| `PROMPT_CODEX_R2.md` | ARCHIVE | R2 Codex prompt |
| `PROMPT_GEMINI.md` | ARCHIVE | Gemini prompt |
| `PROMPT_GEMINI_R2.md` | ARCHIVE | R2 Gemini prompt |
| `CODEX_CODE_INVESTIGATION_PROMPT.md` | ARCHIVE | One-time investigation prompt |

## Research Agent Documents
| File | Status | Purpose |
|------|--------|---------|
| `RESEARCH_AGENT_AUDIT_2026_02_25.md` | ARCHIVE | One-time audit |
| `RESEARCH_AGENT_EVALUATION_SCORECARDS.md` | ARCHIVE | Evaluation results |
| `RESEARCH_AGENT_HANDOFF.md` | ARCHIVE | Implementation handoff |
| `RESEARCH_AGENT_IMPLEMENTATION_PLAN.md` | ARCHIVE | Completed plan |
| `RESEARCH_AGENT_QUALITY_FIXES.md` | ARCHIVE | Completed fixes |
| `RESEARCH_AGENT_TEST_PLAN.md` | ARCHIVE | Completed test plan |
| `RESEARCH_AGENT_TOOL_SPECS.md` | ARCHIVE | Tool specifications |

## Frontend & Design Documents
| File | Status | Purpose |
|------|--------|---------|
| `PLATFORM_REDESIGN_SPEC.md` | ARCHIVE | Superseded by Start each AI/ version |
| `PLATFORM_REDESIGN_INTERVIEW.md` | ARCHIVE | One-time interview notes |
| `PLATFORM_REDESIGN_ADDENDUM.md` | ARCHIVE | Addendum to old spec |
| `REACT_IMPLEMENTATION_PLAN.md` | ARCHIVE | Completed React migration plan |

## SEC EDGAR Scripts & Data
| File | Status | Purpose |
|------|--------|---------|
| `SEC_FINANCIAL_DATA_ROADMAP.md` | ACTIVE | SEC financial data integration roadmap: 7 phases, API/research/frontend/employee counts/Mergent/exec comp |
| `scripts/etl/load_sec_xbrl.py` | ACTIVE | XBRL ETL: companyfacts.zip -> sec_xbrl_financials (249K records, 14.6K companies) |
| `scripts/etl/load_sec_edgar.py` | ACTIVE | SEC submissions.zip -> sec_companies (517K companies) |
| `scripts/etl/sec_edgar_full_index.py` | ACTIVE | Full index ETL with UPSERT support |
| `scripts/etl/create_sec_companies_table.sql` | ACTIVE | Schema for sec_companies table |
| `docs/data-sources/SEC_EDGAR_RESEARCH.md` | REFERENCE | Phase 4 Block A bulk submissions strategy |
| `docs/data-sources/SEC_ETL_COMPLETION.md` | REFERENCE | Metadata ETL completion report (2026-02-16) |
| `docs/data-sources/EDGARTOOLS_EVALUATION.md` | REFERENCE | edgartools library evaluation |
| `docs/data-sources/EXHIBIT_21_PARSING_RESEARCH.md` | REFERENCE | LLM-based subsidiary extraction strategy |

## CBA Pipeline Scripts & Tools
| File | Status | Purpose |
|------|--------|---------|
| `scripts/cba/05_parse_toc.py` | ACTIVE | 3-tier TOC parser (explicit header, dotted-leader, heading heuristic) |
| `scripts/cba/06_split_sections.py` | ACTIVE | Section splitter using parsed TOC entries |
| `scripts/cba/07_extract_page_images.py` | ACTIVE | PDF page-to-PNG extractor (pdfplumber) |
| `scripts/cba/08_enrich_sections.py` | ACTIVE | Section attribute enrichment (categories, wage tables, linked provisions) |
| `scripts/cba/09_decompose_contract.py` | ACTIVE | Orchestrator for progressive decomposition pipeline |
| `cba_search.html` | ACTIVE | Standalone CBA search UI (served at `/cba-search`) |
| `sql/schema/cba_sections_migration.sql` | ACTIVE | Migration for cba_sections + cba_page_images tables |
| `tests/test_cba_toc_parser.py` | ACTIVE | 27 tests for TOC parser |
| `tests/test_cba_section_splitter.py` | ACTIVE | 20 tests for section splitter |

## CBA & Gemini Prompts
| File | Status | Purpose |
|------|--------|---------|
| `GEMINI_CBA_SOURCE_MAPPING_PROMPT.md` | ARCHIVE | CBA Gemini prompt |
| `GEMINI_CBA_UNIFIED_PROMPT.md` | ARCHIVE | CBA Gemini unified prompt |
| `GEMINI_CBA_UNIFIED_PROMPT_POINTER.md` | ARCHIVE | CBA prompt pointer |
| `GEMINI_RESEARCH_HANDOFF.md` | ARCHIVE | Research handoff to Gemini |

## Misc & Analysis
| File | Status | Purpose |
|------|--------|---------|
| `PROJECT_STATE.md` | ARCHIVE | Superseded by Start each AI/ version |
| `claude_code_extractor_fixes.md` | ARCHIVE | One-time fixes log |
| `claude_code_folder_reorg_prompt.md` | ARCHIVE | One-time reorg prompt |
| `compass_artifact_wf-a3ac40f7-3c40-4cb1-9f99-058887658ee3_text_markdown.md` | ARCHIVE | Compass artifact |
| `compass_artifact_wf-cfb3bf88-974d-46a4-ace5-56639d1b6bac_text_markdown.md` | ARCHIVE | Compass artifact |
| `gemini-Analytical Frameworks for Determining Workforce Composition_ A Multidimensional Synthesis of Industrial, Financial, and Demographic Data.md` | ARCHIVE | Gemini analysis output |
| `workforce_estimation_model_plan.md` | ARCHIVE | Superseded by RPE implementation |
