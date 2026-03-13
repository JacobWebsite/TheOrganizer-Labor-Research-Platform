# CBA Tool Architecture (Phase 4)

## Overview
Rule-based CBA (Collective Bargaining Agreement) provision extraction. Replaced AI-at-runtime (Gemini/LangExtract) with standalone Python scripts + regex rule engine. No API cost per contract.

## Pipeline Scripts (in order)
1. `scripts/cba/01_extract_text.py` — PDF text extraction via pdfplumber. `--pdf`, `--employer`, `--union`. Inserts into `cba_documents` with `full_text`, `extraction_method='rule_engine'`.
2. `scripts/cba/02_extract_parties.py` — Pattern-matches first ~15K chars for party names, dates, local number, geography, bargaining unit. `--cba-id N`
3. `scripts/cba/03_find_articles.py` — 6-priority heading detection (ARTICLE N, Roman numerals, Section X.Y, numbered headings, all-caps). Stores `structure_json` in DB. `--cba-id N [--verbose]`
4. `scripts/cba/04_tag_category.py` — Rule engine matching. `--cba-id N --all [--dry-run] [--min-confidence 0.50]`. Also `--category <name>` or `--categories a,b,c`.
5. `scripts/cba/review_provisions.py` — Interactive CLI review. Enter=approve, d=delete, c <cat>=recategorize, s=skip, n <note>=note, q=quit. Logs to `cba_reviews`.
6. `scripts/cba/process_contract.py` — Full pipeline orchestrator (Steps 1-4). `--pdf`, `--dry-run`, `--categories`.

## Shared Code
- `scripts/cba/models.py` — `PageSpan`, `DocumentText`, `ContractMetadata`, `ArticleChunk`, `RuleMatch`
- `scripts/cba/rule_engine.py` — Core matching engine (two-pass: heading signals then text patterns)

## Rule Files: `config/cba_rules/*.json` (14 files)
- healthcare, wages, grievance, leave, pension, seniority, management_rights, union_security, scheduling, job_security, childcare, training, technology, other
- Each file has: `heading_signals` (title score), `text_patterns` (regex + confidence + provision_class), `negative_patterns` (reject matches)
- 97 total text patterns across all categories

## DB Schema (migration: `sql/schema/cba_phase4_migration.sql`)
- **`cba_categories`** — 14 rows, master list of valid categories
- **`cba_reviews`** — Human correction audit trail (provision_id FK, original/corrected category, review_action)
- **`cba_documents` columns added:** `full_text TEXT`, `extraction_method VARCHAR(20)`, `structure_json JSONB`
- **`cba_provisions` columns added:** `article_reference VARCHAR(200)`, `extraction_method VARCHAR(20)`, `rule_name VARCHAR(100)`

## Rule Engine Details
- **Two-pass matching:** 1) Score article headings against `heading_signals` (0-1). 2) Scan paragraph text for `text_patterns`, boost confidence if heading matched.
- **Confidence scoring:** 0.90+ = heading + strong pattern, 0.70-0.89 = pattern with boost, 0.50-0.69 = weak/flagged, <0.50 = rejected
- **Modal verb extraction:** shall/must=0.90, will=0.80, may=0.40, shall not=0.95
- **Dedup:** Two-stage: overlapping char spans (>50%) OR near-identical text (>80% character overlap). Keeps highest confidence.
- **TOC/Index filter:** Skips first ~5% pages (TOC) and last ~3% (Index). Also detects dotted-line patterns (`....97`).
- **Article reference parser:** Section numbers >100 treated as statutory refs (e.g., Section 1981 = Civil Rights Act), uses parent article instead.
- **Text truncation fix:** Extends sentence extraction up to 200 chars past boundary to find sentence-ending punctuation.
- **Context window:** `extract_context_window()` captures ~100 chars before/after matched text.

## 9 Fixes Applied (from human review of 32BJ contract)
1. **Page-range filter** — TOC/Index detection (11 false positives eliminated)
2. **coverage_tiers** — Requires health-context words within 100 chars of "individual"/"family" (15 FPs fixed)
3. **just_cause** — Split into `just_cause_exact` (0.92), `proper_cause` (0.88), `good_cause_discipline` (0.75, requires discipline words). Negative patterns block procedural "good cause" (4 FPs fixed)
4. **training_program** — Requires employee-as-trainee context. Blocks "Training Fund" listings (5 FPs fixed)
5. **jury_duty** — Blocks matches in comma-separated topic lists (2 FPs fixed)
6. **Enhanced dedup** — Catches near-identical text from different rules (2 duplicates fixed)
7. **Text truncation** — Extends past page breaks to find sentence boundaries (3 truncated provisions fixed)
8. **Article references** — Statutory section numbers (>100) use parent article (18 wrong refs fixed)
9. **Context window** — 100-char before/after captured for reviewer context

## Test Contract Results: 32BJ Apartment Building Agreement
- **cba_id=26**, 162 pages, 37 articles, SEIU Local 32BJ / Realty Advisory Board, 2022-2026
- **First pass:** 82 provisions extracted (44% accuracy: 36 approved, 13 deleted, 22 recategorized, 11 flagged)
- **After fixes:** 33 provisions on dry run (high precision, lower recall). Recall gap in leave/other/grievance — expected for conservative v1 rules.
- **DB state:** 69 human-verified provisions, 35 review log entries in `cba_reviews`
- **Ground truth files:** `32bj_provisions_FINAL.json` (69 provisions), `32bj_review_decisions.json` (82 original), `claude_code_extractor_fixes.md` (9 fix specs)

## Archived AI Files
Moved to `archive/cba_ai_extraction/`: langextract_processor.py, cba_analyzer.py, cba_few_shot_specs.json, cba_system_prompt.md

## Key Technical Lessons
- **Python numeric-prefix module imports** — `01_extract_text.py` etc. can't use dot-import. Must use `importlib.import_module("scripts.cba.01_extract_text")`.
- **psql password with `!` on Windows** — `PGPASSWORD='Juniordog33!'` fails in bash due to `!` expansion. Run SQL via Python script with psycopg2 instead.
- **FK constraint on review logging** — Must log cba_reviews BEFORE deleting provisions (provision_id FK). Order: log reviews -> apply recategorizations -> delete provisions.
- **`cba_processor.py` AI made optional** — `use_ai=False` default. Lazy-imports LangExtractProcessor only when `use_ai=True`. `ProvisionExtraction` dataclass moved into cba_processor.py.
- **coverage_tiers lookahead regex** — `(?=.{0,100}(?:plan|coverage|premium|...))` requires health context within 100 chars. Negative patterns block "individual" near attorney/locker/arbitration/etc.
- **"good cause" is NOT "just cause"** — In CBAs, "good cause" appears in dozens of procedural contexts (arbitrator extensions, waiver provisions, deadline exceptions). Only match as discipline when discharge/termination words are nearby.

## Tests
- `tests/test_cba_rule_engine.py` — 53 tests (26 original + 27 for fixes 1-9)
- `tests/test_cba_article_finder.py` — 13 tests
- `tests/test_cba_party_extractor.py` — 17 tests
- Total: **83 CBA tests**, all passing

## Next Steps
- Process a second CBA from different sector to improve recall and test generalization
- Tune rules for leave/other/grievance categories (biggest recall gaps)
- Phase 5 plan: refactor `bulk_load_cbas.py` to use new pipeline
