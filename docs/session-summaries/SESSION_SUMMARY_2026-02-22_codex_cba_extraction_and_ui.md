# Session Summary - CBA Extraction + API + Local UI
Date: 2026-02-22  
Agent: Codex  
Repo: `C:\Users\jakew\Downloads\labor-data-project`

## Objective
Implement and validate a CBA extraction pipeline (LangExtract/Gemini), persist extracted provisions in PostgreSQL, expose CBA search/detail APIs, and provide a basic local frontend to query results.

## What Was Completed

### 1. CBA toolchain implemented
- Added `src/python/cba_tool/langextract_processor.py`
  - Config-driven extraction class loading from JSON.
  - Default model set to `models/gemini-flash-latest`.
  - Model-ID normalization for LangExtract provider routing (`models/...` -> `...`).
  - Added built-in `ExampleData` samples required by LangExtract.
- Added `src/python/cba_tool/cba_processor.py`
  - PDF text extraction via `pdfplumber`.
  - Scanned-document detection.
  - Document insert/update flow for `cba_documents`.
  - Provision insert flow for `cba_provisions`.
  - Char-offset to page mapping for `page_start/page_end`.
  - Status logic:
    - `needs_ocr` for scanned docs.
    - `completed` when rows inserted.
    - `completed_empty` when no rows inserted.
    - `failed` on exceptions.
  - Added optional `max_pages` for controlled test runs.
  - Added deterministic heuristic fallback extractor when AI extraction is unavailable/slow.
- Added `src/python/cba_tool/test_processor.py`
  - CLI harness targeting the League CBA sample by default.

### 2. Extraction taxonomy/config expanded
- Added `config/cba_extraction_classes.json`
  - 14 provision classes with categories.
  - Alias map for normalization.

### 3. API endpoints added
- Added `api/routers/cba.py` with:
  - `GET /api/cba/provisions/search`
  - `GET /api/cba/provisions/classes`
  - `GET /api/cba/documents/{cba_id}` (document metadata + summary + class counts + provisions)
- Wired router into `api/main.py`.

### 4. Local frontend created
- Added `files/cba_search.html`
  - Search UI for CBA provisions.
  - Document detail panel for a selected `cba_id`.
  - Uses:
    - `/api/cba/provisions/search`
    - `/api/cba/documents/{cba_id}`
  - Optional Bearer token input.

### 5. Launch helper added
- Added `start-cba-search.bat`
  - Opens CBA search page and launches API on port `8001`.

## Validation Results

### Database verification
- Confirmed schema objects exist:
  - `cba_documents`
  - `cba_provisions`
  - `v_cba_provision_search`
- Successful extraction run recorded:
  - `cba_id = 21`
  - `provisions_inserted = 208`
  - status `completed`
- Current data check (at validation time):
  - `cba_provisions_count = 208`
  - provisions present for `cba_id=21`
  - `page_start/page_end` populated from char offsets.

### API verification (in-process/import)
- `api.main` imports include CBA routes.
- Router functions return expected payload shape for `cba_id=21` when called directly in Python context.

## Known Issues Encountered

1. **Initial 404s on `/api/cba/*`**
- Cause: stale server process on port `8001` without the new router loaded.

2. **`uvicorn --reload` instability in this environment**
- Repeated Windows multiprocessing pipe permission errors (`WinError 5`) observed under tool/sandbox conditions.
- Recommendation: run without `--reload` for reliability in this environment.

3. **LangExtract/Gemini runtime constraints**
- LangExtract requires `ExampleData` (fixed).
- Provider model routing needed non-prefixed model ID (fixed normalization).
- Full 210-page AI extraction can be slow; fallback extractor was added for robustness.

4. **API key security**
- `GOOGLE_API_KEY` was entered during session; rotate key after testing and update `.env`.

## Files Added/Modified

### Added
- `config/cba_extraction_classes.json`
- `src/__init__.py`
- `src/python/__init__.py`
- `src/python/cba_tool/__init__.py`
- `src/python/cba_tool/langextract_processor.py`
- `src/python/cba_tool/cba_processor.py`
- `src/python/cba_tool/test_processor.py`
- `api/routers/cba.py`
- `files/cba_search.html`
- `start-cba-search.bat`

### Modified
- `api/main.py`
- `requirements.txt`
- `pyproject.toml`

## Suggested Future Modifications (Prioritized)

1. **Production extraction quality**
- Replace/augment heuristic fallback with robust OCR + structured LLM pass:
  - Add OCR path for scanned PDFs (Docling or Mistral OCR).
  - Add chunk-level extraction with controlled parallelism and retries.

2. **Pipeline observability**
- Add per-run logs and `cba_documents` diagnostics fields:
  - model used, run duration, extraction mode (`ai`, `heuristic`, `ocr+ai`), error text.

3. **API hardening**
- Add typed Pydantic response models for CBA endpoints.
- Add endpoint tests (`tests/test_cba_api.py`) covering:
  - search filters
  - pagination
  - document detail payload
  - 404 behavior.

4. **Frontend enhancements**
- Add provision row click -> show full excerpt and surrounding context.
- Add CSV export and class filter dropdown sourced from `/api/cba/provisions/classes`.
- Add paging controls and persisted query state in URL params.

5. **Data governance**
- Add `is_human_verified` workflow endpoint for analyst QA.
- Add dedupe logic for repeated near-identical clause spans.

6. **Run/ops quality**
- Add non-reload launch script variant for environments that block multiprocessing.
- Add health check endpoint note to detect stale server binaries/working directories.

## Quick Runbook (next operator)

1. Start API from repo root (prefer no reload):
```powershell
cd C:\Users\jakew\Downloads\labor-data-project
python -m uvicorn api.main:app --port 8001
```

2. Open UI:
- `http://localhost:8001/files/cba_search.html`

3. Direct API checks:
- `http://localhost:8001/api/cba/provisions/search?cba_id=21&page=1&limit=25&sort=page_start&order=asc`
- `http://localhost:8001/api/cba/documents/21?include_provisions=true&limit=30`

4. Re-run test extraction:
```powershell
python -m src.python.cba_tool.test_processor --pdf "archive\Claude Ai union project\2021-2024_League_CBA_Booklet_PDF_1.pdf"
```

