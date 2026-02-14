# Finance Unionism Analysis

Standalone analysis of union financial health and organizing investment across
major international unions, built from OLMS LM-2 bulk data (2000-2025).

Methodology adapted from "The CWA Fortress: The Debate Over Union Finances and
the Future of the Labor Movement" (Wartel, 2025).

## Structure

- `scripts/` — ETL and metrics computation (reusable, eventually integratable)
- `notebooks/` — Exploratory analysis and visualization
- `output/` — Generated CSVs and artifacts

## Data Source

OLMS LM-2 bulk disclosure files: `lm-2 2000_2025/` (26 years, ~47 tables/year)

## Key Metrics (per union, per year)

- Membership trends and change rates
- Net assets (total assets - total liabilities)
- Total receipts and disbursements
- Revenue per member (per capita tax / dues)
- Surplus (receipts - disbursements)
- Strike fund disbursement ratios (strike benefits / net assets)
- Spending category breakdown (representational, political, overhead, admin)
- Inflation-adjusted comparisons

## Scope

Top ~30 international unions by membership, identified by NHQ designation
in OLMS filings.
