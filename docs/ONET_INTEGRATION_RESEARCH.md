# Research Report: O*NET Integration

**Project:** Occupation-Based Similarity + Workforce Estimation
**Date:** February 17, 2026
**Author:** Gemini

## 1. Research Question

As per the `GEMINI_RESEARCH_HANDOFF.md` document, the sixth and final research task for the "Occupation-Based Similarity + Workforce Estimation" project was to verify the ease of access and integration of the O*NET database. The key questions were:
1.  Are O*NET bulk downloads still freely available?
2.  What are the most useful data tables?
3.  How does O*NET map to the Standard Occupational Classification (SOC) system?

## 2. Summary of Findings

Integrating the O*NET database into the platform is **highly feasible and strongly recommended**.

- **Free and Easy Access:** The entire O*NET database is **freely available for bulk download** from the O*NET Resource Center. No scraping is required. The data is provided in multiple formats, including tab-delimited text files that are easy to process.
- **Rich, Useful Data:** O*NET provides a wealth of information beyond simple job titles. The most useful tables for this project will be **Skills**, **Knowledge**, **Work Activities**, and **Technology Skills**, which provide a deep, multi-faceted view of what each job entails. The **Alternate Titles** table is also invaluable for mapping real-world job titles to the structured O*NET-SOC codes.
- **Straightforward SOC Mapping:** The O*NET-SOC classification is a more granular extension of the standard SOC system. A **crosswalk file is provided** by O*NET, which allows for a direct and reliable mapping between O*NET occupations and the SOC codes used by other datasets like the BLS OEWS.

## 3. Detailed Findings

### Data Access
- The O*NET database is available as a single ZIP archive from the O*NET Resource Center website.
- The archive contains the data in multiple formats (tab-delimited text, Excel, SQL), ensuring easy integration regardless of the platform's data-loading workflow.
- The data is provided under a Creative Commons license, making it free to use in this project.

### Most Useful Data Tables
The handoff document mentioned "Work Context" and "Job Zones," which are useful. However, the following tables will provide the most value for building a powerful occupation similarity engine:

- **`Skills.txt`:** The specific skills required for an occupation.
- **`Knowledge.txt`:** The knowledge areas associated with a job.
- **`Work Activities.txt`:** The day-to-day tasks and activities performed.
- **`Technology Skills.txt`:** The software and hardware used on the job. This is a very powerful feature for identifying modern, comparable work.
- **`Alternate Titles.txt`:** A crucial "Rosetta Stone" that links informal, real-world job titles to the formal O*NET-SOC codes.

### O*NET to SOC Mapping
- The relationship between O*NET and SOC is well-defined. Every O*NET occupation maps to a parent SOC code.
- The O*NET database includes a crosswalk file that makes this mapping explicit and easy to implement. This will allow the platform to seamlessly join the rich O*NET data with the employment data from the BLS OEWS, which also uses SOC codes.

## 4. Conclusion

The O*NET database is a high-value, low-cost (free) dataset that is essential for this project. Its rich data on skills, activities, and technology will allow the platform to build a much more nuanced and accurate occupation similarity model than would be possible with just job titles and industry codes. The integration is straightforward due to the bulk download availability and the clear mapping to the SOC system.

This concludes the research for the "Occupation-Based Similarity + Workforce Estimation" project.
---
