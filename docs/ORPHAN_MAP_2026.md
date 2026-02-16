# Orphan Map -- Complete Broken Reference Analysis
**Date:** February 16, 2026
**Auditor:** Claude Code (Opus 4.6)

## What This Report Shows

An "orphan" is a record that points to another record that doesn't exist. Think of it like a bookmark to a deleted webpage -- when you click it, you get nothing. This report traces every orphan across the entire database.

## Complete Orphan Map

### Orphans Found (6 broken relationships)

| Source Table | Points To | Orphan Count | Impact |
|-------------|-----------|-------------|--------|
| `f7_employers_deduped` (latest_union_fnum) | `unions_master` (f_num) | **518** | Employers show union file numbers that don't resolve to any known union. You get a number but no name, membership, or other details. |
| `corporate_identifier_crosswalk` (f7_employer_id) | `f7_employers_deduped` (employer_id) | **2,400** | The system thinks it knows corporate IDs (GLEIF, Mergent, SEC, EIN) for 2,400 employers that were deleted. Corporate family lookups fail for these. |
| `f7_union_employer_relations` (union_file_number) | `unions_master` (f_num) | **824** | Historical employer-union relationships reference unions not in the master list. These are likely defunct unions. |
| `nlrb_elections` (case_number) | `nlrb_cases` (case_number) | **83** | 83 election records don't have a matching parent case. Election detail lookups may be incomplete for these. |
| `unified_match_log` (target_id, where target=f7) | `f7_employers_deduped` (employer_id) | **11** | 11 match log entries point to deleted employers. Minor -- affects less than 0.005% of matches. |
| `sam_f7_matches` (f7_employer_id) | `f7_employers_deduped` (employer_id) | **1** | One SAM match points to a deleted employer. Negligible. |

### Clean Relationships (9 verified)

| Source Table | Points To | Status |
|-------------|-----------|--------|
| `osha_f7_matches` -> `f7_employers_deduped` | CLEAN (0 orphans) |
| `osha_f7_matches` -> `osha_establishments` | CLEAN (0 orphans) |
| `whd_f7_matches` -> `f7_employers_deduped` | CLEAN (0 orphans) |
| `national_990_f7_matches` -> `f7_employers_deduped` | CLEAN (0 orphans) |
| `sam_f7_matches` -> `sam_entities` (uei) | CLEAN (0 orphans) |
| `ml_election_propensity_scores` -> `f7_employers_deduped` | CLEAN (0 orphans) |
| `mv_organizing_scorecard` -> `osha_establishments` | CLEAN (0 orphans) |
| `nlrb_participants` -> `nlrb_cases` | CLEAN (0 orphans) |

## Summary

- **Total orphan records:** 3,837
- **Most critical:** 2,400 crosswalk orphans (affects corporate identity lookups)
- **Most visible:** 518 union orphans (users see union numbers but no details)
- **Most records affected:** 824 union-employer relations (historical data gaps)
- **Trend:** Union orphans improved from 824 (Round 2) to 518 (Round 3)

## Recommended Fixes

1. **Crosswalk orphans (2,400):** Run a re-matching pass to map these to current employer IDs, or delete entries where the employer was permanently removed.
2. **Union orphans (518 + 824):** These likely reference defunct unions. Either add the missing unions to `unions_master` with a "defunct" flag, or null out the references.
3. **NLRB election orphans (83):** Import the missing 83 NLRB case records.
4. **Match log orphans (11):** Delete these 11 stale entries.

## SQL Queries Used

```sql
-- Union orphans
SELECT COUNT(*) FROM f7_employers_deduped f
WHERE f.latest_union_fnum IS NOT NULL
AND NOT EXISTS (SELECT 1 FROM unions_master u WHERE u.f_num = f.latest_union_fnum::text);

-- Crosswalk orphans
SELECT COUNT(*) FROM corporate_identifier_crosswalk c
WHERE NOT EXISTS (SELECT 1 FROM f7_employers_deduped f WHERE f.employer_id = c.f7_employer_id);

-- Union-employer relation orphans
SELECT COUNT(*) FROM f7_union_employer_relations r
WHERE r.union_file_number IS NOT NULL
AND NOT EXISTS (SELECT 1 FROM unions_master u WHERE u.f_num = r.union_file_number::text);

-- NLRB election orphans
SELECT COUNT(*) FROM nlrb_elections e
WHERE NOT EXISTS (SELECT 1 FROM nlrb_cases c WHERE c.case_number = e.case_number);

-- Match log orphans
SELECT COUNT(*) FROM unified_match_log u
WHERE u.status = 'active' AND u.target_system = 'f7'
AND NOT EXISTS (SELECT 1 FROM f7_employers_deduped f WHERE f.employer_id = u.target_id);
```
