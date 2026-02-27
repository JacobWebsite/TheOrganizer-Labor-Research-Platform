# Research Agent: Comprehensive Reference & Scorecard Integration Guide

> **Purpose:** Complete inventory of the research agent's capabilities, data flows, and
> integration with the scorecard system. 
>
> **Updated:** 2026-02-27 — Includes GLEIF Ownership, FEC Donations (Keyed), 
> Local Demographics, WARN notices, and the "Exhaustive Coverage" logic.

---

## 1. Strategic Vision: Scoring → Research → Gold Standard

The research agent transforms shallow scorecard signals into deep organizing intelligence.
The goal is to reach **100% field coverage** for every run. A confirmed "Zero" is as 
valuable as a positive find.

---

## 2. The 18 Research Tools

### 2.1 Corporate & Financial
*   **search_gleif_ownership (NEW):** Walks the corporate tree using the 12GB GLEIF database. Finds "real" owners and subsidiaries.
*   **search_political_donations (NEW):** Direct FEC API query (using key JFdTNkK4...) + Gemini analysis of PAC and individual CEO contributions.
*   **search_sec / search_990:** Standard public/nonprofit financial retrieval.
*   **search_mergent:** General business profile, revenue, and website.

### 2.2 Workplace & Enforcement
*   **search_warn_notices (NEW):** Forced search for WARN Act mass layoff notices. High-value turnover signal.
*   **search_osha / search_nlrb / search_whd:** Triple-enforcement check (Safety, Organizing, Wage Theft).

### 2.3 Workforce & Context
*   **search_local_demographics (NEW):** City-specific Census/ACS data (Population, Race, Income).
*   **search_job_postings:** Estimated hiring volume and sample roles.
*   **get_workforce_demographics:** Industry-level demographic baselines.

---

## 3. Dossier Structure (7 Sections, 72 Attributes)

The agent now enforces 100% population of these fields via the `_ensure_exhaustive_coverage` pass.

### Tiered Coverage Model (Updated)
| Tier | Profile State | Target Field Fill |
|------|---------------|-------------------|
| **Stub** | DB-only, no research. | 0-6% |
| **Bronze** | Partial DB data. | 7-20% |
| **Silver** | Standard research run. | 21-50% |
| **Gold** | Multi-source + Verified Negatives. | 51-85% |
| **Platinum** | Full 72-point profile (no blank fields). | 100% |

---

## 4. Auto-Grader & Quality Gate

**File:** `scripts/research/auto_grader.py`

### Quality Reward for "Verified None"
Historically, "not found" values were penalized. The grader now differentiates:
*   **Reward (+):** `"Verified None (search_osha searched)"` is treated as a successful research fact.
*   **Penalty (-):** `"Not searched (No strategy match)"` or `null` is penalized as missing research.

---

## 5. Integration Roadmap: Target Scorecard

Integration with the **target scorecard** (non-union universe) is the next priority.
The research priority formula:
```
research_priority = signals_present * has_enforcement * (8 - signals_present)
```

---

## 6. Known Issues & Future Improvements

1.  **Parallelization:** Agent calls tools sequentially. Moving to parallel tool dispatch would reduce run time from 2 mins to <45 seconds.
2.  **SOS Integration:** State Secretary of State records are missing.
3.  **Owner Deep Links:** Finding personal assets/addresses of owners for high-leverage campaigns.
4.  **Freshness:** Government databases are often 1yr+ old. Forced web tools (WARN, News) help, but we need more "live" signals.
