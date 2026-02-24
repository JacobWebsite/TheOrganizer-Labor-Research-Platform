# Session Summary 2026-02-24a: CBA Bulk Load

## What Was Done

### 1. CBA Status Assessment
- Reviewed full Phase 4 (CBA Tool) status: ~25-30% complete
- Scaffolding done by Codex (2026-02-22): schema, processor, langextract integration, basic API, HTML search UI
- 1 test document loaded (League of Voluntary Hospitals, 210pg, 208 provisions)
- Remaining: OCR (4.1), expanded examples (4.2), API hardening (4.3), React integration (4.4), human verification (4.5)

### 2. Cleaned Up Duplicate Test Data
- Deleted 16 duplicate `cba_documents` entries (all League CBA test runs)
- Kept cba_id=21 (completed, 208 provisions)

### 3. Fixed Bulk Loader (`scripts/etl/bulk_load_cbas.py`)
- **Bug fix:** `process_cba()` -> `process_pdf()` with correct keyword arguments
- **Improved filename parsing:** Pattern-based detection for known unions (AFGE, NFFE, NTEU, APWU, SEIU, UNITE HERE, POAM, NBA) and employers (USDA ARS, DOT SLSDC, CFPB, Accenture, Abbott House, etc.)
- **Added duplicate detection:** Checks `cba_documents.file_path` before processing
- **Added `--dry-run` mode** for previewing without loading
- **Added `.PDF` (uppercase) glob** for case-insensitive file detection
- **Default directory** changed to `C:\Users\jakew\Downloads\CBAs`

### 4. Fixed AI Extraction Limit (`src/python/cba_tool/cba_processor.py`)
- `_extract_ai_best_effort()` had a 50K char limit that silently skipped most real CBAs
- Raised to 500K chars (~250 pages) since langextract handles chunking via `max_char_buffer=6000`

### 5. Ran Bulk Load (Partial)
- 38 PDFs in `C:\Users\jakew\Downloads\CBAs` (~55 MB total)
- 1 skipped (League CBA already loaded)
- **3 documents completed before Gemini rate limiting stalled the process:**

| cba_id | Employer | Union | Pages | Provisions | Status |
|--------|----------|-------|-------|------------|--------|
| 21 | League of Voluntary Hospitals | (test) | 210 | 208 | completed |
| 22 | 10 Roads Express | Unknown | 62 | 250 | completed |
| 23 | USDA Agricultural Research Service | NFFE | 76 | 154 | completed |

- **35 files remain unprocessed**

### 6. Gemini Rate Limiting Issue
- Free tier Gemini Flash API returns frequent 503 Service Unavailable
- langextract retries automatically but with exponential backoff, making it very slow (~10 min/file)
- Process stalled on file 3 (USDA ARS Peoria / AFGE) after extended 503 retry loop
- Process killed; DB data is safe

## Current CBA Database State
- **3 documents**, 612 provisions, 348 pages
- **Provision class distribution:** job_security_layoff_recall (138), seniority (124), grievance_and_arbitration (78), hours_and_scheduling (75), union_security_and_dues (57), discipline_and_discharge (46), health_insurance (42), wages_base_pay (23), overtime (22), retirement_pension (7)

## Files Modified
- `scripts/etl/bulk_load_cbas.py` — rewritten with fixes
- `src/python/cba_tool/cba_processor.py` — raised AI extraction char limit

## To Resume Later
```bash
cd "C:\Users\jakew\.local\bin\Labor Data Project_real"
py scripts/etl/bulk_load_cbas.py
```
- Duplicate detection will skip the 3 already-loaded files
- Consider: paid Gemini API key, or adding inter-request delays to avoid 503s
- Alternative: add a `--delay` flag to the bulk loader for throttling

## Deferred / Not Started
- OCR for scanned PDFs (Decision D15 needed: Docling vs Mistral OCR)
- Expanded few-shot examples (only 3 of 14 provision classes covered)
- API Pydantic models and tests
- React frontend integration
- Human verification workflow
- Employer/union linking to master_employers and unions_master
