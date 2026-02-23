# I14 - Geographic Coverage Gaps

Date: 2026-02-23  
DB: `olms_multiyear` (`postgres`)

## Question
- Which states/territories have low F7 employer counts?
- Are low-count regions true low-union regions or data-coverage gaps?

## SQL Used
```sql
SELECT state, COUNT(*) AS employer_count
FROM f7_employers_deduped
GROUP BY state
ORDER BY employer_count ASC NULLS FIRST;

WITH state_counts AS (
  SELECT state, COUNT(*) AS employer_count
  FROM f7_employers_deduped
  WHERE state IS NOT NULL AND state <> ''
  GROUP BY state
)
SELECT sc.state, sc.employer_count, esb.members_total, r.win_rate_pct
FROM state_counts sc
LEFT JOIN epi_state_benchmarks esb ON esb.state = sc.state
LEFT JOIN ref_nlrb_state_win_rates r ON r.state = sc.state
WHERE sc.employer_count < 100
ORDER BY sc.employer_count ASC, sc.state;
```

## Findings
- Distinct state/territory codes in F7: `62`
- Codes with `<100` employers: `10`

Low-count codes:
- `AB` (1), `AS` (1), `MB` (1), `ON` (2), `MP` (6), `MH` (7), `PW` (9), `GU` (16), `WY` (89), `VI` (93)

Cross-reference:
- `WY` has low F7 count (`89`) but non-trivial benchmark membership (`members_total = 13,076`) and strong NLRB win rate (`78.6`) -> likely data coverage gap.
- `VI` has low F7 count (`93`) and NLRB win rate `20.0`; `members_total` benchmark missing -> mixed signal.
- Most other low-count codes are non-US or territory codes with no benchmark rows, suggesting domain/scope mismatch rather than direct union-density inference.

## Conclusion
- The strongest potential US-state gap is `WY`.
- Most `<100` buckets are territories/non-US codes lacking benchmark support, so they should be segmented from 50-state coverage diagnostics.

