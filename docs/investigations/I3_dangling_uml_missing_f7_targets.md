# I3 - Dangling UML Records Pointing to Missing F7 Targets

Date: 2026-02-23  
DB: `olms_multiyear` (`postgres`)

## Question
What is in the 46,627 UML rows whose `target_id` does not exist in `f7_employers_deduped`?

## Current State
- Total dangling rows (all statuses): `46,627`
- By status:
  - `rejected`: `46,624`
  - `superseded`: `2`
  - `active`: `1`

This means the historical dangling population still exists, but almost all are already non-active.

## Pattern from Sample + Aggregates
Top patterns in dangling set:
- `AMBIGUOUS_NAME_STATE_EXACT` (rejected): `25,557`
- `AMBIGUOUS_NAME_AGGRESSIVE_STATE` (rejected): `19,405`
- `AMBIGUOUS_NAME_CITY_STATE_EXACT` (rejected): `1,654`

Sampled rows are overwhelmingly:
- `target_id = 'AMBIGUOUS'`
- ambiguity/rejection records with no concrete F7 target

Single active dangling row pattern:
- source: `nlrb`
- evidence source table: `nlrb_employer_xref`
- `target_id` is 16-char hex, but missing in current F7 deduped table

## Interpretation
- The 46,627 set is primarily historical ambiguity artifacts retained in UML for auditability, not active links.
- Immediate production risk is the `1` active dangling row.

## Remediation Direction
- Mark active dangling rows as `status='orphaned'` so they cannot be counted as active matches.
- Keep rejected/superseded dangling records for history unless a full cleanup is explicitly requested.

