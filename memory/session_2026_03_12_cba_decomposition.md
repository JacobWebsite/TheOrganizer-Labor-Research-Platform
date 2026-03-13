# Session 2026-03-12: CBA Progressive Decomposition + Search UI

## Changes Made

### New Files
| File | Purpose |
|------|---------|
| `sql/schema/cba_sections_migration.sql` | Migration: `cba_sections`, `cba_page_images` tables + `toc_json`/`decomposition_status` columns on `cba_documents` |
| `scripts/cba/05_parse_toc.py` | 3-tier TOC parser (explicit header, dotted-leader cluster, heading heuristic fallback) |
| `scripts/cba/06_split_sections.py` | Section splitter using parsed TOC, fuzzy heading search, TOC-line skip logic |
| `scripts/cba/07_extract_page_images.py` | PDF page-to-PNG extractor using pdfplumber, auto-detects wage table pages |
| `scripts/cba/08_enrich_sections.py` | Section enrichment: word_count, categories, has_wage_table, linked_provision_ids, key_terms |
| `scripts/cba/09_decompose_contract.py` | Orchestrator for full progressive decomposition pipeline |
| `tests/test_cba_toc_parser.py` | 27 tests for TOC parser |
| `tests/test_cba_section_splitter.py` | 20 tests for section splitter |
| `cba_search.html` | Standalone HTML search page with smart query parsing (Provisions/Sections/Contracts tabs) |

### Modified Files
| File | Change |
|------|--------|
| `scripts/cba/models.py` | Added `TOCEntry` and `SectionRow` dataclasses |
| `api/routers/cba.py` | Added `/api/cba/sections/search` and `/api/cba/sections/{section_id}` endpoints |
| `api/main.py` | Added `/cba-search` route serving standalone HTML via FileResponse |
| `api/config.py` | Added `"null"` to ALLOWED_ORIGINS for file:// origin support |

## Key Findings

### 32BJ Contract Validation (cba_id=26)
- **62 sections** extracted from 162-page contract
- **98.1% text coverage** (char coverage of full_text)
- Multi-line article titles fragment into orphaned entries (known Round 0 limitation)
- Article 19 appears twice due to continuation header ("cont'd")

### Technical Discoveries
- Python modules starting with digits (e.g., `05_parse_toc.py`) require `importlib.import_module()` for imports
- Section splitter must skip TOC lines when searching for body headings (dotted-leader detection)
- Page offset detection needed: printed page numbers from TOC != PDF page numbers
- CORS with file:// origins sends "null" as Origin header -- needs explicit allowlist entry

### Test Results
- **132 CBA tests** (47 new + 85 existing), 0 failures
- All existing tests unaffected (no regressions)

## Debugging Notes
- Sub-section regex must be checked BEFORE article regex when `current_article_num` is set (otherwise `5. Voting Time` matches as article 5)
- `text[:len(text) // 4]` is dangerously small for short test texts -- use `max(len(text) // 4, 2000)`
- Compiled regex patterns cannot be passed to `re.search()` with flags argument -- use `pattern.search()` instead
- Zombie uvicorn processes on Windows can be very stubborn to kill; sometimes easier to switch ports
