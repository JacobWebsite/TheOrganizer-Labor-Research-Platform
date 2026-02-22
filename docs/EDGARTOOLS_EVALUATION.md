# Research Report: `edgartools` Library Evaluation

**Project:** SEC EDGAR Integration
**Date:** February 17, 2026
**Author:** Gemini

## 1. Research Question

As per the `GEMINI_RESEARCH_HANDOFF.md` document, the second research task for the "SEC EDGAR Integration" project was to evaluate the `edgartools` Python library. The key questions were:
1.  Is it actively maintained and what are its strengths and weaknesses?
2.  Can it extract Exhibit 21 subsidiary lists?
3.  How does it compare to SEC bulk data downloads for the platform's on-demand needs?

## 2. Summary of Findings

`edgartools` is a modern, well-maintained, and powerful library for **accessing** SEC filing data. Its primary strength lies in providing a high-level Pythonic interface for retrieving filings and their contents for specific companies. For the platform's "on-demand, deep-dive" use case, it is **superior to a bulk-download approach**.

However, it is crucial to understand that `edgartools` is primarily a **retrieval tool, not a parsing tool** for unstructured text. It can retrieve the raw text of an exhibit or a filing, but it does not have built-in functionality to understand or extract structured information from that text (e.g., parsing a list of subsidiaries from the Exhibit 21 HTML).

## 3. Detailed Evaluation

### Maintenance and Capabilities
- **Maintenance:** The library is **very actively maintained**, with recent commits and frequent releases. This makes it a reliable choice for a long-term project.
- **Strengths:**
    - **Ease of Use:** Provides a simple, object-oriented API (`Company`, `Filing`) for interacting with EDGAR data.
    - **On-Demand Focus:** Perfectly suited for the project's stated goal of fetching data for a specific company in real-time.
    - **Rich Feature Set:** Handles filing discovery, text extraction, XBRL parsing, and provides data in convenient formats like Pandas DataFrames.
    - **Compliance:** Helps manage SEC fair access policies by making it easy to set a User-Agent.
- **Weaknesses:**
    - **Lack of Unstructured Parsing:** It does not interpret the content of text-based exhibits like Exhibit 21. This is not a "weakness" of the library so much as a design choice; it focuses on providing the raw data for other tools to process.

### Exhibit 21 Support
- `edgartools` **can retrieve Exhibit 21**, but only as a raw text or HTML file. It does not have a function to parse the list of subsidiaries from that file. The developer would need to implement a separate parsing step.

### Comparison to SEC Bulk Data Downloads

| Feature | `edgartools` | SEC Bulk Download | Recommendation for Platform |
| :--- | :--- | :--- | :--- |
| **Use Case** | On-demand, targeted retrieval for a single company. | Bulk processing of all filings for offline analysis. | **`edgartools`** |
| **Ease of Use**| High-level Python API. | Requires manual handling of FTP/HTTP and file organization. | **`edgartools`** |
| **Infrastructure** | Minimal; can be run in a simple script. | Requires significant storage and a robust pipeline for downloading and managing terabytes of data. | **`edgartools`** |
| **Parsing** | Provides raw text; parsing is a separate step. | Provides raw text; parsing is a separate step. | (Tied) |

For the platform's specific needs of on-demand deep dives, `edgartools` is the clear winner for the data retrieval step.

## 4. Recommended Hybrid Strategy

The most effective and efficient strategy is a **hybrid approach** that combines the strengths of `edgartools` with the LLM-based parsing strategy identified in the previous research report (`EXHIBIT_21_PARSING_RESEARCH.md`).

**Workflow:**
1.  **Identify Target:** The platform identifies a target employer.
2.  **Fetch with `edgartools`:** Use `edgartools` to retrieve the latest 10-K filing and its associated Exhibit 21 for the target company. `filing.text()` and `exhibit.text()` methods can be used to get the raw HTML/text content.
3.  **Parse with LLM:** Pass the retrieved text content to the LLM-based parsing function (as demonstrated in `scripts/scraper/extract_ex21.py`). This function will extract the required structured data (subsidiaries, employee counts, CBA mentions, etc.).
4.  **Store Data:** Save the structured JSON output from the LLM to the platform's database.

This approach leverages `edgartools` for what it does best—efficiently fetching the correct documents—and uses the power and flexibility of an LLM for the complex task of parsing unstructured text.
---
