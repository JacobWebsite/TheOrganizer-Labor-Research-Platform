# I4 - Junk/Placeholder Records in Scoring Universe

Date: 2026-02-23  
DB: `olms_multiyear` (`postgres`)

## Universe
- `f7_employers_deduped` total rows: `146,863`

## Counts (SQL Pattern Based)
- Generic placeholders (exact names): `6`
  - includes `Company Lists`, `Employer Name`, `M1`
- Very short names (alnum length <= 2): `31`
- Agency-like names (federal/municipal pattern query): `1,956`
- School/university/public school patterns: `2,281`

## Known Named Junk/Non-Employer Examples Present
- `Company Lists`
- `Employer Name`
- `M1`
- `Laner Muchin`, `CSP-C/O Laner Muchin`
- `Pension Benefit Guaranty Corporation` (+ PBGC variant)
- `See attached spreadsheets for employer names`

## Notes
- Agency/school pattern counts are broad and include many potentially real public-sector employers.
- Cleanup for Phase 1.5 should focus on high-confidence junk first:
  - placeholders
  - symbol/2-char records
  - known non-employer entities
  - known aggregation artifacts (e.g., USPS TX)

