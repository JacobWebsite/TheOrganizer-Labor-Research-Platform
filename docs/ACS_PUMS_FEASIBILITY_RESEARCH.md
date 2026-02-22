# Research Report: ACS PUMS Demographics Feasibility

**Project:** Occupation-Based Similarity + Workforce Estimation
**Date:** February 17, 2026
**Author:** Gemini

## 1. Research Question

As per the `GEMINI_RESEARCH_HANDOFF.md` document, the fourth research task for the "Occupation-Based Similarity + Workforce Estimation" project was to assess the practical feasibility of using ACS PUMS data to create demographic profiles. The key questions were:
1.  How large are the PUMS files and is it realistic to pre-compute the required profiles?
2.  What does IPUMS access require?
3.  Are there any pre-computed datasets available?

## 2. Summary of Findings

Using the ACS PUMS data to create custom demographic profiles is **highly feasible and the recommended approach**.

- **File Size is Manageable:** The PUMS data files are large (typically 10-20 GB for a 5-year sample), but they can be processed on a standard modern computer or cloud server in a one-time, offline operation.
- **IPUMS is the Best Access Method:** The IPUMS platform provides **free and easy access** to the necessary PUMS data. It requires a simple registration but has no fees. This is significantly easier than working with the raw files from the Census Bureau.
- **Pre-computation is Necessary:** No pre-computed datasets were found that provide the required cross-tabulation of **occupation × demographics × metro area**. The project will need to perform this computation itself, but this is a realistic and well-defined data processing task.

## 3. Implementation Plan

The plan outlined in the project documents—to use PUMS data to create demographic profiles for the 50 largest metro areas—is the correct one. The workflow would be:

1.  **Register for IPUMS Access:** The developer will need to create a free account at `ipums.org`.
2.  **Download PUMS Data:** Download the 5-year ACS PUMS data for the relevant variables (Occupation, Metro Area, and desired demographic characteristics like age, sex, race, etc.).
3.  **Process the Data:** Write a script (using Python with `pandas` or `duckdb` is recommended) to perform the following steps:
    a.  Filter the microdata for only the 50 largest metropolitan areas.
    b.  Group the data by metro area, occupation code, and the relevant demographic fields.
    c.  Calculate the desired summary statistics (e.g., counts, proportions).
    d.  Export the resulting aggregated data.
4.  **Load into Platform:** The final aggregated dataset will be much smaller than the original PUMS file and can be easily loaded into the platform's database for use in the application.

## 4. Conclusion

The project should proceed with confidence in using the ACS PUMS data via IPUMS. It is the most practical and cost-effective way to obtain the detailed demographic data required for the workforce estimation model. While it requires a dedicated data processing step, this is a one-time effort that will produce a high-value, custom dataset for the platform.

This concludes the research on the feasibility of using ACS PUMS data.
---
