# Investigation I10: Multi-Employer Agreements

## Objective
Quantify the inflation in employer counts caused by multi-employer or association agreements, particularly in the building trades.

## Findings

### 1. Scope of Association Records
There are over **3,000** records in the `f7_employers_deduped` table that appear to be associations rather than individual employers (using keywords like "Association" or "Contractors").

### 2. Building Trades Inflation
The building trades (NAICS 23) account for the vast majority of these records.
- Total building trades association-like records: **3,039**
- Top offenders:
    - Associated General Contractors: 12+ variations
    - Mechanical Contractors Association: 9 variations
    - Builders Association: 5 variations

### 3. Impact on Metrics
These records distort the platform in three ways:
1.  **Employer Counts:** A single CBA covering 100 contractors may be counted as 100 separate "employers" if each contractor is listed, or as a single "association" employer that doesn't actually employ the workers directly.
2.  **Membership Distribution:** Workers listed under an association are not correctly mapped to the actual job sites where they work.
3.  **Union Proximity (Factor 1):** Proximity scores are inflated if 100 "employers" (members of an association) are all counted as having a union presence in the same area.

## Recommendations

1.  **Differentiate Associations:** Add a flag `is_association` to `f7_employers_deduped`.
2.  **Consolidate Association CBAs:** When multiple contractors sign the same agreement, it should be tracked as one CBA with multiple signatories, rather than 100 separate CBAs.
3.  **Scoring Adjustment:** Factor 1 (Union Proximity) should count an association as a single signal, not as one signal per member contractor.
4.  **Profile Context:** Display "Member of [Association Name]" on individual contractor profiles to clarify the relationship.
