# Research Report: Exhibit 21 Parsing Strategy

**Project:** SEC EDGAR Integration
**Date:** February 17, 2026
**Author:** Gemini

## 1. Research Question

As per the `GEMINI_RESEARCH_HANDOFF.md` document, the first research task for the "SEC EDGAR Integration" project was to determine the current best approach for parsing SEC Exhibit 21 filings. This involved three sub-questions:
1.  Are there newer open-source tools for this?
2.  Has anyone built a modern Python-based Exhibit 21 parser using LLMs?
3.  What is the estimated cost to use an LLM for this at scale?

## 2. Summary of Findings

The most effective and modern approach for parsing the varied and inconsistent formats of Exhibit 21 is to use a **Large Language Model (LLM) with a schema-enforcement mechanism**.

- **Dedicated open-source parsers for Exhibit 21 are lacking.** Existing tools like `sec-parser` and `datamule` are either not actively maintained or do not have specific features for handling the unique structure of Exhibit 21. A manual approach using libraries like `BeautifulSoup` is possible but would be brittle and require significant development effort.
- **An LLM-based approach is highly feasible and robust.** By combining a powerful LLM (like OpenAI's `gpt-4o`) with a Python library like `Pydantic` to define the desired JSON output structure, we can reliably extract subsidiary information even from messy HTML.
- **The cost of an LLM-based solution is very reasonable.** The estimated annual cost to process 7,000 filings is approximately **$122.50**.

## 3. LLM-Based Implementation Plan

The recommended approach is to create a Python script that orchestrates the following steps:

1.  **Fetch HTML:** Retrieve the raw HTML content of the Exhibit 21 filing. This requires a robust fetching mechanism with a proper User-Agent to comply with SEC's fair access policy.
2.  **Define Schema:** Use the `Pydantic` library to define the desired output structure. This provides clear instructions to the LLM and ensures the final data is validated.
3.  **Prompt LLM:** Send the HTML content to an LLM API, instructing it to extract the data according to the Pydantic schema. OpenAI's API provides a `response_format` feature that makes this particularly effective.
4.  **Store Data:** The LLM returns a validated JSON object that can be directly inserted into the database.

A proof-of-concept script demonstrating this complete workflow has been created and saved at:
`C:\Users\jakew\Downloads\labor-data-project\scripts\scraper\extract_ex21.py`

### Pydantic Schema Example

```python
from pydantic import BaseModel, Field
from typing import List

class Subsidiary(BaseModel):
    """Represents a single subsidiary company."""
    name: str = Field(description="The full legal name of the subsidiary company.")
    jurisdiction: str = Field(description="The state, province, or country of incorporation/organization.")

class SubsidiaryList(BaseModel):
    """A list of all subsidiary companies found in the document."""
    subsidiaries: List[Subsidiary]
```

## 4. Cost Analysis

The cost was estimated based on the following assumptions:
- **Model:** `gpt-4o`
- **Pricing:** $2.50/1M input tokens, $10.00/1M output tokens
- **Average Filing Size:** ~3,000 input tokens (based on Apple Inc.'s large and complex Exhibit 21).
- **Average Output Size:** ~1,000 output tokens (a generous estimate for the structured JSON).

| Metric | Cost |
| :--- | :--- |
| **Cost per Filing** | **~$0.0175** |
| **Annual Cost (7,000 filings)**| **~$122.50** |

**Note:** Costs can be further reduced by using a more cost-effective model (e.g., `gpt-4o-mini`, which is ~16x cheaper) or by taking advantage of batching discounts if the API provider offers them.

## 5. Conclusion & Next Steps

The LLM-based approach is the recommended path forward for parsing Exhibit 21 filings. It is powerful, flexible, and cost-effective.

The next step for the developer (Claude) would be to:
1.  Review the proof-of-concept script: `scripts/scraper/extract_ex21.py`.
2.  Integrate this logic into the platform's data pipeline, likely as an on-demand "deep dive" feature.
3.  Secure an API key for the chosen LLM provider and configure it in the production environment.
---
