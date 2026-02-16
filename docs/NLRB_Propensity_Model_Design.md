# Design: NLRB Election Outcome Propensity Model

This document outlines the feature engineering strategy, model architecture, evaluation framework, and deployment plan for a model to predict the probability of union success in NLRB elections.

---

## 1. Feature Engineering

The primary challenge is the ~50-70% data loss when joining election data to the full employer feature set. A single model would either discard too much data or be too simplistic. Therefore, a **two-model strategy** is recommended.

-   **Model A (High-Fidelity):** Trained on the subset of elections (~30-50%) that successfully join to `mv_organizing_scorecard` and other rich feature sources.
-   **Model B (Low-Fidelity):** Trained on all elections, using only features available directly from `nlrb_elections` and `nlrb_participants`.

This approach maximizes both data utilization and predictive power. An employer receives a score from Model A if they have the requisite features; otherwise, they receive a score from Model B if they have any election history.

### Recommended Feature List

#### Model A: High-Fidelity Features
*   **From `nlrb_elections`:**
    *   `eligible_voters`: (Numerical) Key indicator of bargaining unit size. Use as-is, possibly log-transformed if distribution is heavily skewed.
    *   `election_type`: (Categorical) One-hot encode (`Initial`, `Rerun`, `Runoff`).
    *   `ballot_type`: (Categorical) One-hot encode.
    *   `election_year`: (Numerical) Extracted from `election_date`. Captures temporal trends.
    *   `election_month`: (Categorical) One-hot encode to capture seasonality in organizing.
*   **From `nlrb_participants`:**
    *   `state`: (Categorical) **Do not one-hot encode.** Instead, use the `state_multiplier` from `estimated_state_industry_density` as a powerful, pre-computed numerical feature representing state-level union favorability.
*   **From `mv_organizing_scorecard`:**
    *   `employee_count`: (Numerical) Company-wide size.
    *   `total_violations`, `total_penalties`: (Numerical) Direct measure of OSHA compliance history.
    *   `willful_count`, `repeat_count`: (Numerical) Captures the severity and pattern of violations.
    *   `naics_code`: (Categorical) Use the 2-digit NAICS sector. One-hot encode, as there are only ~20 sectors.
*   **From `estimated_state_industry_density`:**
    *   `estimated_density`: (Numerical) Crucial feature representing industry-specific union density in that state.
*   **From `employer_comparables`:**
    *   `gower_distance`: (Numerical) The distance to the nearest unionized comparable. A direct measure of peer effects.

#### Model B: Low-Fidelity Features (for all other elections)
*   `eligible_voters`
*   `election_type`
*   `ballot_type`
*   `election_year`
*   `election_month`
*   `state`: Use `state_multiplier` as in Model A.
*   `naics_sector` (if available from a simpler join path, otherwise omit).

### Interaction Terms
For initial simplicity, avoid interaction terms. If performance is insufficient, consider adding these to Model A:
-   `eligible_voters` x `estimated_density`: Does unit size have a different effect in high-density industries?
-   `naics_sector` x `total_violations`: Do violations matter more in certain industries?

---

## 2. Model Architecture

### Primary Model: Logistic Regression
-   **Rationale:** The primary goal is an interpretable "AI-suggested score." Logistic Regression provides clear coefficients for each feature, allowing us to explain *why* the model is making a certain prediction. This is essential for user trust and model debugging.
-   **Regularization:** Use **ElasticNet (L1+L2) regularization**. It handles correlated features gracefully (common in this dataset) and can perform some automatic feature selection by driving unimportant feature weights to zero. The mixing parameter should be tuned via cross-validation.

### Benchmark Model: Gradient Boosting (e.g., XGBoost, LightGBM)
-   **Rationale:** A Gradient Boosting model should be trained alongside the logistic regression model as a performance benchmark. It will reveal the potential "upper bound" of predictive accuracy achievable with the given features. If it dramatically outperforms logistic regression, it may indicate complex, non-linear relationships that the simpler model cannot capture.

### Class Imbalance
-   The 68/32 split is moderately imbalanced. The simplest and most effective starting point is to use **class weights** during model training (e.g., `class_weight='balanced'` in Scikit-learn). This adjusts the loss function to penalize misclassifications of the minority class more heavily.

---

## 3. Evaluation Framework

### Train/Test Split
-   A **strict temporal split** is mandatory. A random split would leak future information into the training set, leading to inflated performance metrics.
-   **Strategy:** Choose a cutoff date (e.g., Jan 1, 2022). Train the model on all elections before this date and evaluate it on all elections after this date.

### Key Performance Metrics
-   **AUC (Area Under the ROC Curve):** The primary metric for discriminative power.
    -   **Success Threshold:** `AUC > 0.65` (Ship as experimental feature).
    -   **Needs Work:** `AUC < 0.55` (Indicates features are not sufficiently predictive).
-   **Calibration Plot & Brier Score:** Since the output is a probability, it must be well-calibrated (i.e., when the model predicts 70%, the outcome should happen ~70% of the time). A calibration plot visually assesses this, and the Brier score quantifies it.
-   **Precision-Recall Curve (PRC):** More informative than ROC for imbalanced datasets.
-   **Precision@k:** What is the precision (success rate) of the top `k` (e.g., top 10%) highest-propensity elections? This directly measures the quality of the "opportunity score."

### Validation
-   **Feature Importance:** Examine the coefficients of the trained logistic regression model. If `election_year` and `state_multiplier` have disproportionately large weights compared to employer-specific features, it's a red flag that the model may be acting as a simple time/geography proxy.
-   **Partial Dependence Plots (PDP):** For the benchmark Gradient Boosting model, use PDPs to visualize the marginal effect of one or two features on the predicted outcome, ensuring they are intuitive and logical.

---

## 4. Deployment Integration

### Output and Storage
-   Create a new table: `ml_election_propensity_scores`.
-   **Columns:**
    -   `id` (PK)
    -   `employer_id` (FK to `f7_employers_deduped`)
    -   `propensity_score` (float, range 0-1)
    -   `model_version_id` (FK to `model_versions`)
    -   `created_at` (timestamp)
-   For employers with no NLRB history, no score can be calculated. The application UI must clearly state this, distinguishing it from a score of 0.

### Model Versioning
-   Create a table: `model_versions`.
-   **Columns:**
    -   `id` (PK)
    -   `version_string` (e.g., "logreg-v1.0-a", "logreg-v1.0-b")
    -   `model_type` (e.g., "High-Fidelity", "Low-Fidelity")
    -   `training_date` (date)
    -   `test_auc` (float)
    -   `parameters` (JSONB of model hyperparameters)
    -   `git_commit_hash` (string of training script version)

### Refresh Cadence
-   Retrain the model **quarterly or biannually** using a new temporal split.
-   Monitor the live model's performance on new data. If a significant concept drift is detected (i.e., performance degrades substantially), trigger an ad-hoc retrain.

---

## 5. Ethical Considerations & Risks

### Bias and Fairness
-   **Join Bias:** The High-Fidelity model is trained on a non-random subset of employers (those with representation cases and successful joins). It may not generalize well. **Action:** Clearly label scores from Model A vs. Model B in the backend and analyze performance differences between them.
-   **Proxy Bias:** Features like `state` and `naics_code` could act as proxies for demographic variables. **Action:** Conduct a fairness audit. Check if model performance (e.g., AUC, error rates) is consistent across different states and NAICS sectors. Document any significant disparities.

### Communication and Uncertainty
-   **UI/UX:** The score must be presented as an **"AI-suggested opportunity score,"** not a definitive prediction. It should be displayed alongside the existing 9-factor heuristic to provide multiple perspectives.
-   **Transparency:** Do not just show a single number. Communicate the uncertainty by either showing the probability (e.g., "68% Win Propensity") or binning it into categories (e.g., "High/Medium/Low Propensity"). Avoid presenting it as a deterministic "score" from 1-100.
-   **Misinterpretation:** The model predicts the probability of success, *assuming an election takes place*. It does not predict whether organizing *should* happen or is "easy." This distinction must be clear in user-facing documentation.

### Data Requirements
-   For the High-Fidelity model, a minimum of **5,000-10,000** complete records in the training set is a reasonable starting point for achieving a stable and meaningful result with logistic regression. Given the 30-50% join rate on 33k elections, this should be achievable.
