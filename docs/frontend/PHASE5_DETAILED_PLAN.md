# Phase 5 Detailed Plan: Scoring Evolution

**Date:** February 16, 2026
**Author:** Gemini

This document provides a detailed implementation plan for **Phase 5: Scoring Evolution**, breaking down the high-level roadmap goals into concrete, actionable blocks.

### Phase 5 Goals

-   **Primary:** Evolve the organizing scorecard to be more dynamic and accurate by incorporating temporal decay and broader industry classifications.
-   **Secondary:** Establish a framework for versioning scores and experiment with advanced ML-based scoring factors.

---

### Block 5A: Temporal Decay Implementation

-   **Goal:** Weight recent data (e.g., violations, filings) more heavily than older data.
-   **What:** Create a SQL function that returns a decay multiplier (0.0 to 1.0) based on the age of an event. Apply this multiplier to the points awarded for OSHA and WHD violations.
-   **Deliverables:**
    1.  SQL function `calculate_decay_multiplier(event_date DATE)` that implements a half-life decay (e.g., a 2-year half-life).
    2.  Updated logic in `mv_organizing_scorecard` to apply the multiplier: `final_points = base_points * calculate_decay_multiplier(violation_date)`.
    3.  Documentation on the chosen decay formula.
-   **Timeline:** 16-24 hours
-   **Success Criteria:** Scores for employers with recent violations increase relative to scores for employers with only old violations.

### Block 5B: Hierarchical NAICS Rollup

-   **Goal:** Allow for broader industry comparisons by mapping granular 6-digit NAICS codes to their parent 2, 3, and 4-digit industry groups.
-   **What:** Create and populate a NAICS hierarchy table and use it to create a view for easy roll-up.
-   **Deliverables:**
    1.  A new table, `naics_code_hierarchy`, populated with the official NAICS code structure (e.g., from a public CSV file).
    2.  A new view, `v_employer_naics_hierarchy`, that joins `f7_employers_deduped` to the hierarchy table, showing columns for `naics_2_digit_code`, `naics_3_digit_code`, etc., for each employer.
-   **Timeline:** 24-32 hours
-   **Success Criteria:** Analysts can query employers by broad industry groups (e.g., `WHERE naics_2_digit_code = '23' -- Construction`).

### Block 5C: Score Versioning

-   **Goal:** Track how employer scores change over time to identify emerging targets or trends.
-   **What:** Create a history table that logs a snapshot of employer scores whenever the main scorecard is refreshed.
-   **Deliverables:**
    1.  A new table, `scorecard_history`, with the same structure as `mv_organizing_scorecard` plus a `snapshot_date` column.
    2.  A PostgreSQL trigger or a scheduled function that runs after `mv_organizing_scorecard` is refreshed and inserts the new data into `scorecard_history`.
-   **Timeline:** 12-16 hours
-   **Success Criteria:** A complete historical record of scores is maintained, allowing for queries that show score changes between any two dates.

### Block 5D (Advanced): Gower Enhancement with OEWS

-   **Goal:** Improve the "Comparable Employers" score by incorporating occupational similarity.
-   **What:** Implement the weighted-average scoring logic designed in the Scoring Integration Design document.
-   **Deliverables:**
    1.  A materialized view, `mv_occupation_similarity`, that pre-calculates the similarity score between all pairs of industries.
    2.  Updated logic in `mv_organizing_scorecard` to calculate the final comparable employer score using the weighted average of Gower distance and occupation similarity.
-   **Timeline:** 30-40 hours
-   **Dependencies:** Block 5B (Hierarchical NAICS) can be useful for broader industry-occupation analysis.

### Block 5E (Experimental): Propensity Model

-   **Goal:** Build a proof-of-concept machine learning model to predict the likelihood of a successful organizing campaign.
-   **What:** Use historical NLRB election data, joined with employer characteristics from our database, to train a classification model (e.g., Logistic Regression or Gradient Boosting).
-   **Deliverables:**
    1.  A Python script (`train_propensity_model.py`) that uses scikit-learn to train the model and saves the trained model artifact.
    2.  A `requirements.txt` file including `scikit-learn` and `pandas`.
    3.  A separate prediction script or a simple FastAPI endpoint to score a given employer.
    4.  A document outlining model performance (AUC, Precision, Recall).
-   **Timeline:** 40-60+ hours
-   **Risk:** High. This is an experiment. Success is not guaranteed and depends heavily on the quality of historical NLRB data and the predictive power of our features.

---

### Execution Strategy & Risks

-   **Parallel Execution:**
    -   Blocks **5A, 5B, and 5C** can be worked on in parallel as they are independent.
    -   Block **5D** is more complex and can be started after the others are underway.
    -   Block **5E** is the most independent and riskiest; it should be time-boxed and can be de-prioritized if other blocks run over schedule.
-   **Risk Assessment:**
    -   **Low Risk:** 5A, 5C. These are well-defined and self-contained.
    -   **Medium Risk:** 5B, 5D. These involve external data (NAICS structure) and complex logic that will require significant testing.
    -   **High Risk:** 5E. This is an R&D effort. It may not yield a useful model.

---
