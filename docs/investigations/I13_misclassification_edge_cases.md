# I13 - Misclassification Edge Cases (`is_labor_org`)

Date: 2026-02-23  
DB: `olms_multiyear` (`postgres`)

## Question
- Are there false positives among rows flagged `is_labor_org = TRUE`?
- Are there obvious missed labor-org rows (keywords like union/local/council but not flagged)?

## SQL Used
```sql
SELECT COUNT(*) FROM f7_employers_deduped WHERE is_labor_org IS TRUE;

SELECT
  COUNT(*) FILTER (
    WHERE LOWER(employer_name) ~ '(school district|university|college|academy|public schools?)'
  ) AS edu_like,
  COUNT(*) FILTER (
    WHERE LOWER(employer_name) ~ '(hospital|medical|health|clinic|rehab|nursing)'
  ) AS health_like,
  COUNT(*) FILTER (
    WHERE LOWER(employer_name) ~ '(insurance|ins\\.|financial|bank|credit union)'
  ) AS finance_like
FROM f7_employers_deduped
WHERE is_labor_org IS TRUE;

SELECT COUNT(*)
FROM f7_employers_deduped
WHERE COALESCE(is_labor_org, FALSE) = FALSE
  AND LOWER(employer_name) ~ '(\\bunion\\b|\\blocal\\b|\\bcouncil\\b)';
```

## Findings
- `is_labor_org = TRUE` total: `1,843`

Potential edge-case buckets within flagged rows:
- education-like names: `1`
- health-like names: `35`
- finance-like names: `4`

Sample edge-case rows include:
- `Bank of America`
- multiple `SEIU Healthcare ...` records
- `... Health and Welfare Fund` / `... Pension Fund` records

Interpretation:
- many health-like matches are union benefit entities (not clear false positives),
- but some rows (e.g. `Bank of America`) look like likely false positives and should be reviewed.

Missed labor-org keyword check:
- non-flagged rows with `union|local|council` in name: `0`

## Conclusion
- Flagging has high recall on obvious labor-org keywords (no obvious misses by this keyword test).
- There are limited but real potential false positives that need targeted manual review, especially non-union commercial entities flagged by multi-signal heuristics.

