# Research Report: Calibration Engine Feasibility

**Project:** Occupation-Based Similarity + Workforce Estimation
**Date:** February 17, 2026
**Author:** Gemini

## 1. Research Question

As per the `GEMINI_RESEARCH_HANDOFF.md` document, the fifth research task for the "Occupation-Based Similarity + Workforce Estimation" project was to assess the feasibility of the proposed "calibration engine." The key questions were:
1.  Is the idea of using NLRB election data as an "answer key" for workforce estimates a valid approach?
2.  What is the minimum number of data points per industry needed for this calibration to be meaningful?

## 2. Summary of Findings

- **The proposed calibration strategy is sound.** Using NLRB election data as a source of ground-truth employment numbers is a **practical and well-precedented approach**. While academic researchers use this data as a direct (though imperfect) measure of employment, the project's plan to use it as an "answer key" to calibrate a separate estimation model is a creative and valid application of the same principle.
- **There is no single "minimum number" of data points.** The required number depends on statistical factors, but general rules of thumb suggest that the project's dataset of ~50,000 NLRB records is more than sufficient to build a robust calibration model.

## 3. Validation of the Approach

Academic researchers have frequently used the "number of eligible voters" from NLRB election records as a proxy for establishment-level employment. This confirms that the NLRB data is a reliable source of real-world employment numbers at a granular level.

The project's plan to use this data to test and refine its own workforce estimates is, therefore, a strong and defensible methodology.

## 4. Minimum Data Points for Calibration

This is a statistical question, and there is no universal answer. However, based on common data science practices, the following guidelines can be applied:

- **General Rules of Thumb:** In statistics, a sample size of **30 to 50** is often considered a minimum for a reliable estimate of a group's characteristics. Aiming for at least this many data points per industry group is a good goal.
- **Focus on Distribution, Not a Hard Minimum:** With ~50,000 total records, the main challenge will not be the overall amount of data, but ensuring there is sufficient coverage across a wide range of industries.
- **Start Broad:** The calibration should begin with broader industry categories (e.g., 2- or 3-digit NAICS codes) to ensure that each group has a healthy number of data points. The model can be refined with more granular industry codes where sufficient data exists.

## 5. Recommendation

The project should proceed with the calibration engine plan. The methodology is sound, and the available data is more than adequate.

**Practical Steps for Implementation:**
1.  **Data Cleaning:** Ensure the NLRB election data is cleaned and that the "number of eligible voters" field is reliably populated.
2.  **Industry Classification:** Match each NLRB record to a NAICS code.
3.  **Start with Broad Industries:** Begin the calibration process by grouping the data by 2-digit NAICS codes.
4.  **Set a Practical Threshold:** Aim for a minimum of **50 records per industry group** for the initial calibration. If a group has fewer records, it can either be combined with a similar group or temporarily excluded.
5.  **Iterate and Refine:** Once the model is working with broad industry groups, it can be refined by testing it on more granular 4-digit NAICS codes where there is sufficient data density.

This concludes the research on the feasibility of the calibration engine.
---
