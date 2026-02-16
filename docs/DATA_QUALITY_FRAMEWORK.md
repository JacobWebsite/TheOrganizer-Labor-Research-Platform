# Data Quality & Confidence Framework

**Date:** February 16, 2026
**Author:** Gemini

This document proposes a framework for systematically tracking, scoring, and utilizing data quality and confidence metrics across the platform.

### 1. Problem Statement

Our platform aggregates data from diverse sources with varying levels of quality, freshness, and certainty. To build trust and make our scores more transparent, we must move from treating all data as equal to actively quantifying its reliability. This framework introduces a "quality score" for each data source.

### 2. Confidence Scoring Methodology

A unified `quality_score` (ranging from 0.0 to 1.0) will be calculated for each data source. This score will be a weighted average of several key dimensions.

**Quality Dimensions:**

1.  **Authority (Weight: 40%):** The trustworthiness of the source.
    -   `Government Direct` (SEC, BLS): **1.0**
    -   `Government Estimate` (BLS estimates): **0.8**
    -   `Verified Third-Party` (Future data partners): **0.7**
    -   `Scraped/Inferred` (Future web scraping): **0.5**

2.  **Freshness (Weight: 30%):** How recently the data was updated. This will use a decay function.
    -   Score = `max(0, 1 - (days_since_update / 730))`
    -   This formula gives a score of 1.0 for brand new data, 0.5 for data that is one year old, and 0.0 for data two years or older.

3.  **Certainty (Weight: 30%):** The method used to obtain the data.
    -   `Measured/Actual`: **1.0**
    -   `Estimated`: **0.7**
    -   `Projected`: **0.6**

**Example Calculation (BLS State-Industry Density):**
-   Authority: `Government Estimate` = 0.8
-   Freshness: Updated 30 days ago = `1 - (30/730)` = 0.96
-   Certainty: `Estimated` = 0.7
-   **Quality Score:** `(0.8 * 0.4) + (0.96 * 0.3) + (0.7 * 0.3)` = `0.32 + 0.288 + 0.21` = **0.82**

### 3. Schema Design

The proposed `data_quality_metadata` table is a strong foundation. It should be implemented with the addition of `match_rate` and `last_checked` fields to provide a more complete picture.

```sql
CREATE TABLE data_quality_metadata (
    source_system VARCHAR(50) PRIMARY KEY,
    description TEXT,

    -- Quality Dimensions
    authority_level VARCHAR(20) NOT NULL, -- 'government_direct', 'government_estimate', etc.
    certainty_level VARCHAR(20) NOT NULL, -- 'actual', 'estimated', 'projected'
    last_updated_date DATE NOT NULL,      -- The date the source data was published
    last_checked_date DATE NOT NULL,      -- The date our ETL last ran successfully

    -- Calculated Score
    quality_score NUMERIC(3,2),           -- The calculated score (e.g., 0.82)

    -- Coverage Metrics
    source_row_count INTEGER,
    match_rate NUMERIC(5,4),              -- Percentage of F7 employers matched

    notes TEXT
);

COMMENT ON TABLE data_quality_metadata IS 'Central registry for data quality, freshness, and confidence scores for all integrated sources.';
```
A nightly or weekly job should run to update the `quality_score` for all sources based on the current date.

### 4. Integration with Scorecard

Data quality should not be an abstract metric; it must directly influence the organizing scorecard.

-   **Proposal:** Each of the 9 scoring factors in `mv_organizing_scorecard` should have its final score adjusted by the quality score of the data source that powers it.

    ```sql
    -- Example for the Union Density factor
    final_density_points = (base_points_from_curve * density_quality_score)
    ```
    Where `density_quality_score` is the `quality_score` from `data_quality_metadata` for the `bls_estimated_density` source.

-   **Benefit:** This creates a self-correcting system. As a data source becomes stale, its quality score will decrease, automatically reducing its influence on the overall organizing score.

### 5. Visualization Recommendations

The UI must surface these quality metrics to the end-users (organizers).

-   **Scorecard View:** Next to each of the 9 factor scores, a small, color-coded badge or icon should indicate the quality of the underlying data.
    -   **Green (0.8 - 1.0):** High Quality
    -   **Yellow (0.6 - 0.79):** Medium Quality
    -   **Red (< 0.6):** Low Quality / Stale
-   **Tooltips:** On mouse-over, the badge should display a tooltip with details: "Data from BLS, updated 30 days ago. Score is an estimate."
-   **Data Source Page:** A dedicated "Data Health" dashboard should be created that visualizes the `data_quality_metadata` table, showing the health and coverage of all integrated sources over time.

---
