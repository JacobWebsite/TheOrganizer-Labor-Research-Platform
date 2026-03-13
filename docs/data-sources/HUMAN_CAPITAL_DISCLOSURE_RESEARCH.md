# Research Report: Human Capital Disclosures

**Project:** SEC EDGAR Integration
**Date:** February 17, 2026
**Author:** Gemini

## 1. Research Question

As per the `GEMINI_RESEARCH_HANDOFF.md` document, the third research task for the "SEC EDGAR Integration" project was to investigate the extractability of human capital disclosures from 10-K filings. The key questions were:
1.  How standardized are these disclosures in practice?
2.  What percentage of companies report specific metrics like union membership, turnover, or demographics?
3.  Are there any existing datasets or tools for this?

## 2. Summary of Findings

The SEC's 2020 rule on human capital disclosure is **principles-based**, granting companies wide discretion on what to report. As a result, the disclosures are **highly inconsistent and not standardized** across companies.

- **No Standard Format:** Disclosures vary dramatically in length, content, and format, ranging from a few sentences to several pages.
- **Quantitative Data is Rare:** While most companies provide some qualitative discussion of their workforce, the inclusion of specific, quantitative metrics (like turnover rates, diversity statistics, or union membership numbers) is inconsistent and cannot be reliably expected from a majority of filings.
- **No Public Datasets or Specialized Tools:** There are no pre-built, publicly available datasets of human capital disclosures. Similarly, no specialized open-source tools were found that are designed *only* for extracting this specific information. The extraction must be done as part of a broader filing analysis workflow.

This lack of standardization makes it impossible to use simple, rule-based parsing methods. This is a clear use case for a flexible and powerful Large Language Model (LLM).

## 3. Recommended Extraction Strategy

The most effective strategy for extracting human capital data is to use the same **hybrid approach** recommended for Exhibit 21 parsing:

1.  **Fetch with `edgartools`:** Use the `edgartools` library to retrieve the full text of a company's 10-K filing.
2.  **Parse with LLM:** Pass the full text to an LLM with instructions to find and extract any information related to human capital management.
3.  **Use a Flexible Schema:** The extraction should be guided by a `Pydantic` schema. However, unlike the more structured Exhibit 21, all fields in this schema should be defined as `Optional` to reflect the high probability that many metrics will not be present in any given filing.

### Pydantic Schema Example

```python
from pydantic import BaseModel, Field
from typing import Optional, List

class HumanCapitalMetrics(BaseModel):
    """
    A schema for extracting human capital disclosures. All fields are optional
    to account for the high variability in reporting.
    """
    employee_count: Optional[int] = Field(default=None, description="Total number of employees.")
    full_time_employees: Optional[int] = Field(default=None, description="Number of full-time employees.")
    part_time_employees: Optional[int] = Field(default=None, description="Number of part-time employees.")
    turnover_rate: Optional[float] = Field(default=None, description="Annual employee turnover rate.")
    union_membership_percentage: Optional[float] = Field(default=None, description="Percentage of workforce that is unionized.")
    workforce_demographics: Optional[str] = Field(default=None, description="A summary of workforce demographic data (e.g., gender, ethnicity).")
    summary: Optional[str] = Field(default=None, description="A qualitative summary of the company's human capital philosophy and initiatives.")
```

## 4. Conclusion

Extracting human capital disclosures is a challenging task due to the lack of standardization. However, by leveraging `edgartools` for data retrieval and an LLM for parsing with a flexible schema, the platform can build a system to extract whatever data is available on a case-by-case basis.

This concludes the research on human capital disclosures. The final research question for the "SEC EDGAR Integration" project is to investigate **corporate hierarchy alternatives beyond EDGAR**.
---
