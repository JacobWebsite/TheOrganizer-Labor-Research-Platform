# Scoring Integration Design for Phase 4 Data

**Date:** February 16, 2026
**Author:** Gemini

This document outlines the design for integrating the new Phase 4 data sources (BLS Density, OEWS Occupations, SEC/990 filings) into the `mv_organizing_scorecard`.

### 1. Factor 3: Industry Union Density (0-10 points)

This factor will be enhanced to use the new state-specific estimates, providing a much more granular and actionable score.

-   **Implementation:** The query should use the state-specific estimate and fall back to the national average if the estimate is not available.

    ```sql
    -- Logic for mv_organizing_scorecard
    COALESCE(
        e.estimated_density,
        n.union_density_pct
    ) as union_density_for_scoring
    ```

-   **Scoring Curve:** A linear scale is simple but doesn't capture the reality of organizing. A logarithmic or quartile-based scale is recommended to give more weight to changes at the lower end of the density spectrum.

    **Proposed Curve (Quartile-based):**
    ```sql
    CASE
        WHEN density_pct >= 20.0 THEN 10  -- Elite Density
        WHEN density_pct >= 15.0 THEN 9
        WHEN density_pct >= 10.0 THEN 7   -- Strong Density
        WHEN density_pct >= 7.5  THEN 5   -- Above Average
        WHEN density_pct >= 5.0  THEN 3   -- Some Presence
        WHEN density_pct >  2.0  THEN 1   -- Minimal Presence
        ELSE 0
    END
    ```

-   **Confidence Adjustment:** Scores derived from an estimate should be slightly penalized to reflect their lower certainty.

    ```sql
    -- Multiply final points by a confidence factor
    final_density_points = points_from_curve * CASE
        WHEN e.estimated_density IS NOT NULL THEN 0.9 -- It's an estimate
        ELSE 1.0 -- It's a measured national average
    END
    ```

### 2. Factor 8: Comparable Employers (0-5 points)

This factor can be enhanced by incorporating occupational similarity from the OEWS data. This finds employers who are "comparable" because they employ a similar mix of workers, even if they are in different industries.

-   **Implementation:** The existing Gower distance calculation should be combined with a new "occupation similarity" score.

-   **Weighting:** The final score for this factor should be a weighted average of the two methods.
    -   `final_comparable_score = (gower_score * 0.7) + (occupation_similarity_score * 0.3)`

-   **Occupation Similarity Score:** This can be calculated based on the number of employers found with a similar occupational profile above a certain threshold.

    -   **Threshold:** A similarity score threshold of **0.6** is recommended to start.
    -   **Scoring:**
        -   +2 points if > 10 comparable employers found.
        -   +1 point if 1-10 comparable employers found.
        -   0 points otherwise.

### 3. New Factor 10: Corporate Transparency (0-5 points)

A new factor should be added to reward transparency, based on the hypothesis that publicly accountable entities are more susceptible to organizing campaigns.

-   **Implementation:** A simple boolean check against the `corporate_identifier_crosswalk` and `national_990_filers` tables. A `corporate_disclosure_type` column could be added to `f7_employers_deduped` to simplify this (`None`, `SEC`, `Form 990`).

-   **Scoring Logic:**
    -   `+3 points` if the employer is a known SEC filer.
    -   `+2 points` if the employer is a known Form 990 filer.
    -   This is not mutually exclusive; a non-profit could have a publicly-traded parent. The max score from this would be 5.
    -   This approach avoids skewing scores toward large employers, as it's a flat bonus.

### 4. Migration Plan

The `mv_organizing_scorecard` materialized view must be updated.

1.  **Step 1: Add New Columns:** Add `factor_10_transparency_score`, `density_is_estimated`, and `occupation_similarity_score` to the materialized view definition.
2.  **Step 2: Update Scoring Logic:** Modify the `CREATE MATERIALIZED VIEW` statement to incorporate the new logic for Factors 3 and 8, and add the calculation for Factor 10.
3.  **Step 3: Refresh View:** Run `REFRESH MATERIALIZED VIEW mv_organizing_scorecard;` to apply the new scores to all 24,841 employers. This should be done during a maintenance window as it may take several minutes.
4.  **Step 4: Update Downstream Dashboards:** Any dashboards or reports that consume the scorecard will need to be updated to reflect the new `total_score` and potentially display the new factors.

---
