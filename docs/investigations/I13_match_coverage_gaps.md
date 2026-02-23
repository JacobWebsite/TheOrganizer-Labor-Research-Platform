# I13 - Match Coverage Gap Analysis

Date: 2026-02-23  
DB: `olms_multiyear` (`postgres`)

## Scope
Measure source-system match coverage and unmatched ceilings.

## SQL Used
```sql
-- OSHA
SELECT 'osha' AS source,
       COUNT(*) AS total_records,
       COUNT(*) FILTER (WHERE EXISTS (
           SELECT 1 FROM unified_match_log u
           WHERE u.source_id = e.establishment_id::text
             AND u.source_system = 'osha' AND u.status = 'active'
       )) AS matched,
       ROUND(COUNT(*) FILTER (WHERE EXISTS (
           SELECT 1 FROM unified_match_log u
           WHERE u.source_id = e.establishment_id::text
             AND u.source_system = 'osha' AND u.status = 'active'
       ))::numeric / COUNT(*) * 100, 1) AS match_pct
FROM osha_establishments e
WHERE e.estab_name_normalized IS NOT NULL;

-- SAM
SELECT 'sam' AS source,
       COUNT(*) AS total_records,
       COUNT(*) FILTER (WHERE EXISTS (
           SELECT 1 FROM unified_match_log u
           WHERE u.source_id = s.uei::text
             AND u.source_system = 'sam' AND u.status = 'active'
       )) AS matched,
       ROUND(COUNT(*) FILTER (WHERE EXISTS (
           SELECT 1 FROM unified_match_log u
           WHERE u.source_id = s.uei::text
             AND u.source_system = 'sam' AND u.status = 'active'
       ))::numeric / COUNT(*) * 100, 1) AS match_pct
FROM sam_entities s
WHERE s.uei IS NOT NULL;

-- WHD
SELECT 'whd' AS source,
       COUNT(*) AS total_records,
       COUNT(*) FILTER (WHERE EXISTS (
           SELECT 1 FROM unified_match_log u
           WHERE u.source_id = w.case_id::text
             AND u.source_system = 'whd' AND u.status = 'active'
       )) AS matched,
       ROUND(COUNT(*) FILTER (WHERE EXISTS (
           SELECT 1 FROM unified_match_log u
           WHERE u.source_id = w.case_id::text
             AND u.source_system = 'whd' AND u.status = 'active'
       ))::numeric / COUNT(*) * 100, 1) AS match_pct
FROM whd_cases w
WHERE w.case_id IS NOT NULL;

-- 990
SELECT '990' AS source,
       COUNT(*) AS total_records,
       COUNT(*) FILTER (WHERE m.f7_employer_id IS NOT NULL) AS matched,
       ROUND(COUNT(*) FILTER (WHERE m.f7_employer_id IS NOT NULL)::numeric / COUNT(*) * 100, 1) AS match_pct
FROM national_990_filers f
LEFT JOIN (
    SELECT DISTINCT ein, f7_employer_id
    FROM national_990_f7_matches
    WHERE f7_employer_id IS NOT NULL
) m ON m.ein = f.ein
WHERE f.ein IS NOT NULL;

-- SEC
SELECT 'sec' AS source,
       COUNT(*) AS total_records,
       COUNT(*) FILTER (WHERE EXISTS (
           SELECT 1 FROM unified_match_log u
           WHERE u.source_id = s.cik::text
             AND u.source_system = 'sec' AND u.status = 'active'
       )) AS matched,
       ROUND(COUNT(*) FILTER (WHERE EXISTS (
           SELECT 1 FROM unified_match_log u
           WHERE u.source_id = s.cik::text
             AND u.source_system = 'sec' AND u.status = 'active'
       ))::numeric / COUNT(*) * 100, 1) AS match_pct
FROM sec_companies s
WHERE s.cik IS NOT NULL;
```

## Findings
| Source | Total | Matched | Match % | Unmatched |
|---|---:|---:|---:|---:|
| osha | 1,007,217 | 50,021 | 5.0% | 957,163 |
| sam | 826,042 | 17,687 | 2.1% | 808,355 |
| whd | 363,365 | 12,355 | 3.4% | 351,010 |
| 990 | 586,767 | 20,005 | 3.4% | 566,762 |
| sec | 517,403 | 2,559 | 0.5% | 514,844 |

## Interpretation
- The absolute headroom is largest in OSHA and SAM due to source size.
- SEC has the lowest match percentage and highest relative gap.
- These unmatched volumes define the practical upper bound for further matching improvements absent source-quality or entity-resolution changes.

