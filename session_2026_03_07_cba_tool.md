# Session 2026-03-07: CBA Tool Improvement (Phases 1-4)

## What Was Done
Implemented the full CBA Tool Improvement Roadmap (Phases 1-4) from the plan file.

### Phase 1: Clean Foundation
- **Schema migration** (`sql/schema/cba_improvement_migration.sql`): Added `context_before`/`context_after` to `cba_provisions`, `file_hash`/`processing_status`/`processing_error` to `cba_documents`. Rebuilt `v_cba_provision_search` view.
- **Context expansion**: Increased `_extract_sentence_context()` cap 600->1500 chars, `extract_context_window()` default 100->500 chars. Added `populate_context()` helper to `rule_engine.py`.
- **Entity linking** (`02_extract_parties.py`): Added `link_employer()`, `link_union()`, `link_entities()`. Matches against `f7_employers_deduped` and `unions_master`.
- **Re-processed all 3 AI-extracted contracts** with rule engine:
  - cba_id=21 (League/1199SEIU): 208 -> 76 provisions, 12 categories
  - cba_id=22 (10 Roads Express): 250 -> 63 provisions, 10 categories
  - cba_id=23 (USDA ARS/NFFE): 154 -> 59 provisions, 9 categories
- All 4 contracts now use consistent 14-category taxonomy (267 total provisions)
- Fixed `process_contract.py` `--reprocess` to not require `--pdf`/`--employer`/`--union`, and to re-extract from PDF when `full_text` is NULL

### Phase 2: Batch Folder Watcher
- **New script** `scripts/cba/batch_process.py` (322 lines): scans `data/cba_inbox/` for PDFs, SHA-256 dedup, full pipeline processing, moves to `data/cba_processed/`
- **Duplicate detection**: `compute_file_hash()` in `01_extract_text.py`, `file_hash` column in `cba_documents`
- **Processing status tracking**: `processing_status` enum (pending/extracting/parsed/tagged/completed/failed), `processing_error` column
- Created `data/cba_inbox/` and `data/cba_processed/` directories

### Phase 3: OCR Support
- **OCR integration** in `01_extract_text.py`: `ocr_pdf()`, `load_pdf_text_with_ocr()` with pytesseract fallback
- **Scanned detection**: Enhanced `is_scanned_document()` with per-page threshold (<100 chars = scanned, majority vote)
- **Quality scoring**: `ocr_quality_score()` using dictionary word matching

### Phase 4: Frontend CBA Module + API
- **4 new API endpoints** in `api/routers/cba.py`:
  - `GET /api/cba/documents` -- list with filters, stats, provision counts
  - `GET /api/cba/categories` -- categories with counts
  - `GET /api/cba/compare` -- compare up to 10 contracts by category
  - `GET /api/cba/documents/{cba_id}` -- detail with provisions (updated with context)
- **4 new frontend pages**:
  - `CBADashboard.jsx` (/cbas) -- stats cards, category breakdown, contracts table
  - `CBADetail.jsx` (/cbas/:cbaId) -- provisions by category with expandable context
  - `CBASearch.jsx` (/cbas/search) -- full-text search with filters
  - `CBACompare.jsx` (/cbas/compare) -- side-by-side comparison
- **API hooks**: `frontend/src/shared/api/cba.js` (6 hooks)
- **Nav integration**: Added "Contracts" link in NavBar
- **Routes**: 4 lazy-loaded routes in App.jsx

### Tests
- 55 CBA rule engine tests pass (updated caps, added populate_context tests)
- All backend tests pass
- All frontend tests pass (1 pre-existing SettingsPage failure)

## Key Technical Notes
- `DROP VIEW` required before `CREATE VIEW` when adding columns (can't use `CREATE OR REPLACE` if column order changes)
- Old AI-extracted contracts (21-23) had no `full_text` stored -- reprocess mode now re-extracts from PDF
- Contract 21 PDF had moved -- updated `file_path` in DB
- Entity linking: cba_id=21 linked to employer_id, cba_id=23 linked to f_num=515865

## Files Created/Modified
- New: `scripts/cba/batch_process.py`, `sql/schema/cba_improvement_migration.sql`, `frontend/src/features/cba/CBADashboard.jsx`, `CBADetail.jsx`, `CBASearch.jsx`, `CBACompare.jsx`, `frontend/src/shared/api/cba.js`
- Modified: `scripts/cba/rule_engine.py`, `scripts/cba/04_tag_category.py`, `scripts/cba/process_contract.py`, `scripts/cba/01_extract_text.py`, `scripts/cba/02_extract_parties.py`, `scripts/cba/models.py`, `api/routers/cba.py`, `frontend/src/App.jsx`, `frontend/src/shared/components/NavBar.jsx`, `tests/test_cba_rule_engine.py`

## Next Steps
- **Manual review checkpoint**: Review rule engine output across all 4 contracts before Phase 5
- **Batch process new CBAs**: Drop PDFs into `data/cba_inbox/`, run `py scripts/cba/batch_process.py`
- **Phase 5 (Rule Engine Improvements)**: Deferred until 10+ contracts loaded
- **Install Tesseract**: If OCR needed for scanned PDFs (`pip install pytesseract Pillow` + system binary)
