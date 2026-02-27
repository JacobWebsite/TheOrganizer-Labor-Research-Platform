# Strategic & Data Coverage Audit Report
**Date:** February 25, 2026
**Auditor:** Gemini (Strategic & Data Coverage Analyst)
**Status:** COMPLETE

---

## 1. Executive Summary

The platform represents a major technical achievement in labor data aggregation, but it currently suffers from a **fundamental strategic misalignment**. It is optimized to describe the *past* (existing union relationships and major safety failures) rather than predict the *future* (new organizing opportunities). 

The most critical finding is the **"Targeting Paradox"**: 95% of the 2.7 million employers in the master database are invisible to the scoring system because they currently lack either an F7 union contract or a "Critical" OSHA violation. Until the "Prospect Pool" of non-union employers is fully integrated into the scorecard, the platform remains a research tool for existing campaigns rather than a discovery tool for new ones.

---

## 2. Shared Overlap Zone (OQ1-OQ10)

| ID | Question | Finding |
|----|----------|---------|
| **OQ1** | Priority Tier Spot Check | Dominated by "Corporate Giants" (FedEx, Amazon) due to 3x weight on Size/Proximity. Ranks "Strategic Importance" rather than "Organizing Propensity." |
| **OQ2** | Match Accuracy | Estimated real-world False Positive rate of ~18% in fuzzy tiers. Splink over-weights geography (e.g., "City of X" matching local businesses). |
| **OQ3** | React/API Contract | Modern React frontend is live, but API fragmentation exists between two competing scorecard MVs. Dossier rendering suffers from "[object Object]" bugs. |
| **OQ4** | Data Freshness | OSHA/NLRB data is 2024-2025 (Good). F7 union data is the "stale core," with many matches based on 2-5 year old filings. |
| **OQ5** | Incomplete Re-runs | 990, WHD, and SAM sources use legacy matching, creating a "Data Quality Cliff" where some sections of an employer profile are significantly more reliable than others. |
| **OQ6** | Scoring Assessment | **Union Proximity (3x)** is the platform's most valuable unique insight. **Size (3x)** is over-weighted, burying winnable small shops under unorganizable giants. |
| **OQ7** | Test Suite | 456 tests pass, but they verify "Data Existence" rather than "Strategic Relevance." Code can be "correct" while the targeting is "wrong." |
| **OQ8** | Database Cleanup | 492K NLRB junk rows removed, but 12GB of unused GLEIF data remains. Deduplication of the "Identity Layer" is the top structural priority. |
| **OQ9** | Single Biggest Problem | **The Targeting Paradox.** The platform scores 146k union shops and 60k high-risk shops, but ignores 2.5 million potential organizing targets. |
| **OQ10** | Audit Follow-up | Auth and cleanup addressed. The **125-vs-392 win discrepancy** (Prediction Failure) remains unaddressed—the score does not yet correlate with real election wins. |

---

## 3. Specific Investigation Areas

### 3.1 The "Propensity Model" Deception
Investigation into `scripts/ml/train_propensity_model.py` reveals that the "Propensity Score" served to users is **not a machine learning model**. It is a hardcoded Python heuristic:
`score = 0.3 + 0.35 * violations + 0.35 * density`. 
Labeling this as "ML" is a strategic risk that creates a false sense of algorithmic intelligence. Model B (covering all employers) has an accuracy of **0.53 (Random)**.

### 3.2 Research Agent Persistence Failure
The Research Agent is the platform's only "thinking" component, but it currently **fails to save web-sourced facts** to the `research_facts` table. It merges data into the JSON dossier but "forgets" the individual facts, making the quality score (7.93/10) fundamentally dishonest as it labels all web data as "Database."

### 3.3 The Public Sector "Black Hole"
7 million unionized public sector workers are effectively invisible. Research on State PERB data (NY, CA, WA, etc.) is complete, but implementation is stalled. This is a critical gap for unions like SEIU and AFSCME.

---

## 4. The Organizer's Verdict

> "I like having the data in one place, but your 'Priority' list looks like a 'Fortune 500' list. I don't need a computer to tell me Amazon is a big target—I need it to tell me which 200-person warehouse in New Jersey is angry enough to sign cards tomorrow. This tool is great for a researcher, but it's not yet a targeting engine for an organizer."

---

## 5. Strategic Blind Spots

1. **The "Silent Discontent" Gap:** Employers with no government violations but high turnover and low wages (visible in Job Postings) are currently unscored.
2. **Persistence Failure:** The Agent's inability to save web facts means the platform loses its most valuable qualitative data.
3. **Identity Fragmentation:** An organizer cannot easily see that "FedEx Express" and "Federal Express" are the same strategic target because the deduplication layer is incomplete.

---

## 6. Recommended Priority List

| Priority | Task | Strategic Impact | Effort |
|----------|------|------------------|--------|
| **1** | **Score the 2.7M Prospects** | Ends the "Targeting Paradox" by scoring all non-union targets. | High |
| **2** | **Fix Fact Persistence** | Ensures web intelligence (news, news of layoffs) is saved and searchable. | Low |
| **3** | **Tune Scoring Weights** | Reduce Size to 1x; increase weight for active signals (OSHA/ULP). | Low |
| **4** | **Standardize Propensity** | Be honest about the heuristic or train a real model on non-union losses. | Med |
| **5** | **Capture Turnover** | Use "Job Posting" count as a negative score factor (Turnover = Organizing Killer). | Med |
| **6** | **Scrape Public PERB Data** | NY and CA data is critical for major union partners. | High |
