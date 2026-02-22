# Research Report: Corporate Hierarchy Alternatives

**Project:** SEC EDGAR Integration
**Date:** February 17, 2026
**Author:** Gemini

## 1. Research Question

As per the `GEMINI_RESEARCH_HANDOFF.md` document, the final research task for the "SEC EDGAR Integration" project was to evaluate alternatives to parsing EDGAR Exhibit 21 for corporate hierarchy data. The key questions were:
1.  Evaluate the practical accessibility of OpenCorporates, GLEIF, and state Secretary of State records.
2.  Is there a free or low-cost API that provides parent-subsidiary mappings already parsed?

## 2. Summary of Findings

For building a corporate hierarchy (i.e., "who owns whom"), parsing the unstructured text of EDGAR Exhibit 21 filings is **not the recommended approach**.

A far superior alternative exists: the **Global Legal Entity Identifier Foundation (GLEIF) API**.

- **GLEIF API is the clear winner.** It is a free, public, and well-documented API that provides structured, machine-readable data on parent-subsidiary relationships. It is the ideal solution for this project's needs.
- **OpenCorporates** is also a powerful source, but its API is a premium, high-cost product that does not fit the "free or low-cost" requirement.
- **State Secretary of State records** are not a viable option. There is no unified, multi-state API, which would necessitate building and maintaining 50 separate and distinct integrations.

The answer to the second research question is a definitive **yes**: the GLEIF API is a free API that provides already-parsed parent-subsidiary mappings.

## 3. Evaluation of Alternatives

### GLEIF API (Recommended)
The Global Legal Entity Identifier Foundation (a non-profit) provides a public API to access its database of Legal Entity Identifiers (LEIs).

- **Direct Hierarchy Data:** The API explicitly provides "Level 2" data, which is "who owns whom" information. It has dedicated endpoints to query for the direct and ultimate parents and children of any legal entity.
- **Structured & Easy to Use:** The API returns data in a clean, well-documented JSON format. This eliminates the need for any complex parsing. GLEIF also provides a Postman collection to make development and integration even easier.
- **Free and Public:** The API is free to use, aligning perfectly with the project's requirements.
- **Broader Coverage:** The LEI system includes public and private companies, non-profits, and international entities, offering broader coverage than the SEC's database, which is limited to public filers.

**Recommendation:** The GLEIF API should be the **primary source** for corporate hierarchy data for the platform. It is more reliable, easier to use, and more comprehensive than parsing Exhibit 21.

### OpenCorporates
- **Powerful Data:** OpenCorporates has extensive data on corporate structures.
- **High Cost:** Access to their API is a premium service with a high price tag, making it unsuitable for this project. The free tier is likely too limited for any meaningful use.

### State Secretary of State Records
- **Highly Fragmented:** Each state maintains its own database and has its own method of access (or lack thereof).
- **No Unified API:** There is no single API to access business data across all 50 states.
- **Impractical to Integrate:** Building and maintaining 50 separate integrations would be a massive undertaking and is not a feasible strategy.

## 4. Conclusion

The discovery of the GLEIF API significantly changes the recommended approach for building corporate hierarchies. Instead of a complex, multi-stage parsing process for EDGAR Exhibit 21, the platform can use a simple and direct API call to a free, structured data source.

This concludes the research for the "SEC EDGAR Integration" project.
---
