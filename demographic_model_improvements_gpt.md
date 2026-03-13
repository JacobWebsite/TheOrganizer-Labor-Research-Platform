# Improving the Workforce Demographic Modeling Framework

## Overview

This document outlines recommended improvements to the current workforce
demographic estimation system that compares multiple estimation methods
against EEO‑1 ground truth data.

The existing framework already has strong foundations: - Multiple
estimation methodologies - Structured validation against EEO‑1 data -
Standardized error metrics - Real-world company case studies

The following improvements aim to move the system from an experimental
benchmark toward a production-grade demographic inference model.

------------------------------------------------------------------------

# 1. Expand the Validation Dataset

The current comparison relies on a small validation sample of companies.
While useful for debugging, this creates statistical instability.

## Recommended Approach

Build a **stratified validation sample of 150--300 companies** across:

  Dimension        Buckets
  ---------------- ---------------------------------
  Industry         15--20 NAICS groups
  Workforce Size   1--100, 100--1k, 1k--10k, 10k+
  Region           Northeast, South, Midwest, West
  Minority Share   Low / Medium / High
  Urbanicity       Urban / Suburban / Rural

### Benefits

-   Reduces outlier influence
-   Enables robust error distribution analysis
-   Produces reliable performance benchmarks

Important metrics to report:

-   Median MAE
-   90th percentile MAE
-   Worst‑case error
-   Bias direction by race group

------------------------------------------------------------------------

# 2. Replace Fixed Weights With Learned Weights

The current best-performing method uses a fixed ACS/LODES blend.
Instead, weights should be estimated empirically.

## Model Structure

    race_share =
        w1 * ACS_county +
        w2 * LODES_workplace +
        w3 * industry_baseline +
        w4 * occupation_weights +
        ε

## Recommended Techniques

-   Ridge regression
-   Constrained least squares (weights ≥ 0)
-   Cross‑validated regression

### Benefits

-   Industry-specific optimization
-   Data-driven weighting
-   Improved generalization

------------------------------------------------------------------------

# 3. Incorporate Occupation → Race Correlations

Most current estimates treat race as primarily geographic. However, many
industries have strong occupational segregation.

Example:

  Occupation     Typical Demographic Pattern
  -------------- ---------------------------------
  Housekeeping   High Hispanic / immigrant share
  Front desk     Higher White share
  Maintenance    Mixed
  Management     Higher White share

### Implementation

    industry staffing mix
    ×
    occupation race distribution
    = synthetic workforce demographics

This often significantly improves estimates in hospitality, healthcare,
and manufacturing.

------------------------------------------------------------------------

# 4. Correct Structural White Bias

Systematic overestimation of White workforce share is common when using
ACS and LODES.

## Cause 1: Commuting Bias

LODES workplace demographics reflect **commuters**, not actual hires.

Solution:

Use **LODES Origin-Destination commuting matrices** to model where
workers come from rather than where they work.

    workforce composition =
    weighted average of commuting origin tracts

## Cause 2: Hiring Pipeline Bias

Certain industries recruit heavily from specific labor pools (immigrant
communities, trade programs, etc.).

Solution:

Weight demographics of **tracts with high employment in the relevant
NAICS sector** rather than overall county demographics.

------------------------------------------------------------------------

# 5. Hybrid Model: Geography + IPF

Iterative proportional fitting (IPF) performs poorly for race but well
for gender.

This suggests a hybrid approach:

    Race estimation  = geography + occupation model
    Gender estimation = IPF constraint model

This preserves the advantages of each method.

------------------------------------------------------------------------

# 6. Move to a Bayesian Framework

Current methods produce single-point estimates. A Bayesian framework
allows uncertainty estimation.

## Model Structure

Prior:

    industry demographic distribution

Likelihood:

    geography
    occupation mix
    LODES workforce

Posterior:

    P(demographics | data)

### Benefits

-   Handles outlier workplaces
-   Produces uncertainty intervals
-   Improves interpretability

Example output:

    Black workforce share
    Mean: 28%
    95% interval: 21–36%

------------------------------------------------------------------------

# 7. Add Workforce Pipeline Signals

Hiring pipelines are often tied to educational institutions and training
programs.

Examples:

  Industry        Pipeline
  --------------- ----------------------
  Nursing homes   CNA programs
  Construction    Trade schools
  Hospitality     Community colleges
  Manufacturing   Technical institutes

Demographic data from these institutions can significantly improve
workforce estimates.

------------------------------------------------------------------------

# 8. Evaluate Error by Diversity Level

Performance varies depending on workplace diversity.

Classify firms by minority share:

  Category        Minority Share
  --------------- ----------------
  Low diversity   \<20%
  Medium          20--40%
  High            \>40%

Many models perform well in low-diversity workplaces but poorly in
high-diversity environments.

Understanding these patterns is crucial for model improvement.

------------------------------------------------------------------------

# 9. Address the NHOPI Data Gap

IPUMS often aggregates **Native Hawaiian and Pacific Islander (NHOPI)**
populations with Asian populations.

Solution:

Use detailed ACS tables (e.g., B02015) that separate:

-   Native Hawaiian
-   Samoan
-   Guamanian
-   Other Pacific Islander

This is essential for accurate modeling in Hawaii and Pacific Island
communities.

------------------------------------------------------------------------

# 10. Transition to Supervised Machine Learning

Once enough EEO‑1 training data is collected, the system can be reframed
as a supervised learning problem.

## Input Features

    NAICS
    county demographics
    LODES workforce composition
    occupation mix
    firm size
    urban density
    regional labor market signals

## Target

    EEO‑1 demographic distribution

## Candidate Models

-   Gradient Boosting
-   Random Forest
-   Bayesian Regression
-   Hierarchical Models

Existing estimation methods can become **input features** rather than
standalone models.

------------------------------------------------------------------------

# Conclusion

The current framework already provides a rigorous benchmarking structure
for demographic estimation. The primary next steps involve:

-   Expanding the validation dataset
-   Learning model parameters from data
-   Integrating occupational and pipeline signals
-   Incorporating probabilistic modeling

These improvements would transform the system into a scalable
demographic inference engine capable of estimating workforce composition
across industries and regions with significantly higher accuracy.
