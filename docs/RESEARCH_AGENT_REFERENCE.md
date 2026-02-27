# Research Agent: Comprehensive Reference

> **Updated:** 2026-02-27 — Full Inventory of 24 Tools, Async Parallel Core, and Leverage Signals.

---

## 1. Strategic Inventory (24 Specialized Tools)

### 1.1 The Leverage Tier (New Phase 5.8)
*   **search_solidarity_network**: Walks the GLEIF corporate tree to find unionized sister facilities across all representation (Teamsters, SEIU, etc.).
*   **search_local_subsidies**: Unmasks taxpayer-funded IDA grants and tax abatements.
*   **search_worker_sentiment**: Social listening on Reddit/Glassdoor for toxic management signals.
*   **search_sos_filings**: Directly scrapes State SOS for Registered Agents and LLC Officers.
*   **compare_industry_wages**: Benchmarks target pay against local industry peers.

### 1.2 The Financial Tier
*   **search_political_donations**: Keyed FEC API access for hard dollar contribution totals.
*   **search_gleif_ownership**: Direct 12GB database query for corporate genealogy.
*   **search_sec / search_990**: Public and Nonprofit financial retrieval.

### 1.3 The Enforcement Tier
*   **search_osha / search_nlrb / search_whd**: Triple-check for Safety, Organizing, and Wage violations.
*   **search_warn_notices**: Checks for mass layoff filings.

---

## 2. Technical Capabilities

### 2.1 Async Parallel Execution
The engine is now fully asynchronous. Sequential bottlenecks in Phase 1.5/1.6 have been removed. 12+ tools now launch simultaneously, achieving a Gold Standard profile in **<45 seconds**.

### 2.2 Search Precision (Address-Aware)
The system now supports an optional `company_address`. 
- **DB Matching**: Stricter validation in `lookup_employer` via zip/street match.
- **Web Search**: Automatically injects `{address}` into gap-aware queries.

### 2.3 100% Field Coverage
The `_ensure_exhaustive_coverage` pass guarantees all 72 attributes are filled. 
- Positive finds are saved as JSON.
- Negative finds are marked `"Verified None ([Tool] searched)"`.
- Profiles consistently reach **Platinum Coverage** status.
