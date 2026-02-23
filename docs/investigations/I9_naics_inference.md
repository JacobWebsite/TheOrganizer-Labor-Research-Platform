# Investigation I9: NAICS Inference

## Objective
Determine if NAICS codes can be inferred for the 22,183 employers (15.1% of the total) that currently lack them.

## Findings

### 1. Current Gap
Out of 146,863 employers in the `f7_employers_deduped` table, **22,183 (15.1%)** have a NULL NAICS code. This prevents the calculation of scoring factors that rely on industry growth or sector benchmarks.

### 2. Inference via External Sources
By looking at active matches to external sources that *do* have NAICS codes, we can fill some of this gap.

| Source | Employers with NULL NAICS that have matches |
|--------|-------------------------------------------|
| OSHA   | 4,398                                     |
| WHD    | 1,964 (some overlap with OSHA)            |

**Total potential recovery:** Approximately **5,000 - 6,000** employers (representing ~25% of the gap).

### 3. Other Inference Methods
- **Keywords:** Many employer names contain industry signals (e.g., "Construction", "Hospital", "School", "Trucking").
- **ML Classifiers:** Tools like `naicskit` can predict NAICS codes from company names with reasonable accuracy for common industries.

## Recommendations

1.  **OSHA/WHD Backfill:** Implement a script that updates `f7_employers_deduped.naics` using the `naics_code` from matched OSHA establishments and WHD cases.
2.  **Name Keyword Inference:** Build a mapping of common keywords to 2-digit NAICS sectors (e.g., "Construction" -> 23).
3.  **NAICSkit Integration:** For the remaining ~15,000 employers, run the names through `naicskit` and assign a code if the confidence is above a threshold (e.g., 0.8).
