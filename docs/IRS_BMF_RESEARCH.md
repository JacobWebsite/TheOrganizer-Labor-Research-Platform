# IRS BMF ETL Research

**Date:** 2026-02-16
**Developer:** Gemini

## Data Source Chosen: ProPublica Nonprofit Explorer API

I have chosen to use the ProPublica Nonprofit Explorer API as recommended in the project documentation. It provides a clean, well-structured JSON response that will be easier and faster to parse than the fixed-width IRS bulk data file.

## Estimated Record Count

The API documentation and initial tests suggest a very large number of records, likely over 1.8 million. A search for "union" returns over 10,000 results, but a blank search is required to iterate through all organizations. The ETL script will need to paginate through all results.

## Available Fields

The API provides the following fields which map to our target `irs_bmf` table schema:

| ProPublica API Field | `irs_bmf` column      | Notes                                        |
|----------------------|-----------------------|----------------------------------------------|
| `ein`                | `ein`                 | Primary Key. Appears to be reliable.         |
| `name`               | `org_name`            | The organization's name.                     |
| `state`              | `state`               | Two-letter state code.                       |
| `city`               | `city`                | City name.                                   |
| `zipcode`            | `zip_code`            | 5-digit zip code.                            |
| `ntee_code`          | `ntee_code`           | National Taxonomy of Exempt Entities code.   |
| `subsection_code`    | `subsection_code`     | From `subseccd` field in API. (e.g. 3, 5, 6) |
| `ruling_date`        | `ruling_date`         | Date of tax-exempt ruling.                   |
| `deductibility_code` | `deductibility_code`  | Contribution deductibility information.      |
| `foundation_code`    | `foundation_code`     | Foundation status code.                      |
| `income_amount`      | `income_amount`       | Available in detailed organization responses.|
| `asset_amount`       | `asset_amount`        | Available in detailed organization responses.|

## Limitations & Risks

1.  **Rate Limiting:** The API does not have officially documented rate limits. The instructions suggest a 0.5-second delay between paged requests to be courteous. This will make the full ETL process take a considerable amount of time.
2.  **Incomplete Dataset:** The ProPublica API may not contain the absolute full 1.8 million records from the BMF. However, it is expected to be comprehensive enough for the project's needs and far exceeds the current 586K records in `n990_organizations`.
3.  **API Changes:** The API is an external dependency and could change, but it has been stable for years.

Based on this research, the ProPublica API is the correct choice for this task.
