# Session Handoff: CBA Extraction & LangExtract Integration
**Target Agent:** Codex / Development Team
**Date:** February 22, 2026
**Project:** Labor Relations Research Platform

## 1. Executive Summary
We have successfully scaffolded the **CBA Searcher Tool**, which uses Google’s `langextract` library and Gemini to perform structured extraction of union contract provisions. The database schema is live, the core processing classes are implemented, and the system is verified to work with the `models/gemini-flash-latest` model.

## 2. Technical Stack & File Map
*   **Core Processor:** `src/python/cba_tool/cba_processor.py`
    *   Handles PDF assessment (digital vs. scanned).
    *   Orchestrates metadata saving and extraction workflow.
*   **AI Engine:** `src/python/cba_tool/langextract_processor.py`
    *   Wrapper for Google's `langextract` library.
    *   Uses Few-Shot examples to guide Gemini in tagging provisions.
*   **Database Schema:** `sql/schema/cba_extraction_schema.sql`
    *   `cba_documents`: Metadata and processing state.
    *   `cba_provisions`: Extracted clauses with character-level grounding.
*   **Taxonomy & Config:**
    *   `CBA_PROVISION_TAXONOMY.md`: Deep research on provision types.
    *   `config/cba_extraction_classes.json`: Structural definitions for the AI.

## 3. Current Status
*   **Database:** Tables are live in `olms_multiyear`.
*   **Tests:** `test_processor.py` is the primary test script. It successfully processes the 210-page League CBA booklet located in the `archive/` folder.
*   **Model ID Fix:** We resolved 404 errors by settling on `models/gemini-flash-latest`. Previous attempts at `gemini-1.5-flash` or `gemini-2.0-flash` failed due to API versioning or user permission restrictions.

## 4. Challenges & Known Risks
*   **Model ID Fragility:** The Gemini API in this environment is sensitive to model IDs. If `models/gemini-flash-latest` fails, run `python list_models.py` to check for currently supported aliases.
*   **OCR Implementation:** The pipeline currently identifies scanned PDFs but does not yet route them through an OCR engine (e.g., Mistral OCR or Docling).
*   **Example Diversity:** The `LangExtractCBAProcessor` currently uses hardcoded examples. These should be moved to `config/cba_few_shot_specs.json` for better maintainability.

## 5. Next Steps for Codex
1.  **Provision Expansion:** Populate the `examples` list in `langextract_processor.py` for all 10 priority classes defined in `config/cba_extraction_classes.json`.
2.  **Verification:** Run `test_processor.py` and query the `cba_provisions` table to ensure `char_start` and `char_end` are being populated correctly.
3.  **Search View API:** Expose the `v_cba_provision_search` view through a new FastAPI router (`api/routers/cba.py`).
4.  **UI Integration:** Create a simple frontend view to display extracted clauses (e.g., "Show me all Just Cause provisions in NY healthcare contracts").

---
**Key Sample Document:**
`archive\Claude Ai union project\2021-2024_League_CBA_Booklet_PDF_1.pdf`
