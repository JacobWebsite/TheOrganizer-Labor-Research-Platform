# Parallel Query Plan Baseline

- Mode: EXPLAIN

## api_summary_unions
```sql
SELECT COUNT(*) as total_unions, SUM(members) as total_members,
               COUNT(DISTINCT aff_abbr) as affiliations
        FROM unions_master
```
```text
Aggregate  (cost=3761.53..3761.54 rows=1 width=24)
  ->  Sort  (cost=3494.88..3561.54 rows=26665 width=8)
        Sort Key: aff_abbr
        ->  Seq Scan on unions_master  (cost=0.00..1534.65 rows=26665 width=8)
```

## api_summary_employers
```sql
SELECT COUNT(*) as total_employers,
               SUM(latest_unit_size) as total_workers_raw,
               SUM(CASE WHEN exclude_from_counts = FALSE THEN latest_unit_size ELSE 0 END) as covered_workers,
               COUNT(DISTINCT state) as states,
               COUNT(CASE WHEN exclude_from_counts = TRUE THEN 1 END) as excluded_records,
               ROUND(100.0 * SUM(CASE WHEN exclude_from_counts = FALSE THEN latest_unit_size ELSE 0 END) / 7200000, 1) as bls_coverage_pct
        FROM f7_employers_deduped
```
```text
Aggregate  (cost=19006.90..19006.92 rows=1 width=72)
  ->  Sort  (cost=17301.20..17585.48 rows=113713 width=8)
        Sort Key: state
        ->  Seq Scan on f7_employers_deduped  (cost=0.00..7752.13 rows=113713 width=8)
```

## api_osha_summary
```sql
SELECT
            (SELECT COUNT(*) FROM osha_establishments) as total_establishments,
            (SELECT COUNT(*) FROM osha_establishments WHERE union_status = 'Y') as union_establishments,
            (SELECT COUNT(*) FROM osha_establishments WHERE union_status = 'N') as nonunion_establishments,
            (SELECT SUM(violation_count) FROM osha_violation_summary) as total_violations,
            (SELECT SUM(total_penalties) FROM osha_violation_summary) as total_penalties,
            (SELECT COUNT(*) FROM osha_accidents) as total_accidents,
            (SELECT COUNT(*) FROM osha_accidents WHERE is_fatality = true) as fatality_incidents,
            (SELECT COUNT(*) FROM osha_f7_matches) as f7_matches,
            (SELECT COUNT(DISTINCT f7_employer_id) FROM osha_f7_matches) as unique_f7_employers_matched
```
```text
Result  (cost=62932.09..62932.10 rows=1 width=96)
  InitPlan 1
    ->  Finalize Aggregate  (cost=18914.61..18914.62 rows=1 width=8)
          ->  Gather  (cost=18914.40..18914.61 rows=2 width=8)
                Workers Planned: 2
                ->  Partial Aggregate  (cost=17914.40..17914.41 rows=1 width=8)
                      ->  Parallel Index Only Scan using idx_osha_est_state on osha_establishments  (cost=0.42..16863.98 rows=420165 width=0)
  InitPlan 2
    ->  Aggregate  (cost=642.15..642.16 rows=1 width=8)
          ->  Index Only Scan using idx_osha_est_union on osha_establishments osha_establishments_1  (cost=0.42..588.28 rows=21546 width=0)
                Index Cond: (union_status = 'Y'::text)
  InitPlan 3
    ->  Aggregate  (cost=3339.02..3339.03 rows=1 width=8)
          ->  Index Only Scan using idx_osha_est_union on osha_establishments osha_establishments_2  (cost=0.42..3051.21 rows=115125 width=0)
                Index Cond: (union_status = 'N'::text)
  InitPlan 4
    ->  Finalize Aggregate  (cost=15182.73..15182.74 rows=1 width=8)
          ->  Gather  (cost=15182.52..15182.73 rows=2 width=8)
                Workers Planned: 2
                ->  Partial Aggregate  (cost=14182.52..14182.53 rows=1 width=8)
                      ->  Parallel Seq Scan on osha_violation_summary  (cost=0.00..13274.01 rows=363401 width=4)
  InitPlan 5
    ->  Finalize Aggregate  (cost=15182.74..15182.75 rows=1 width=32)
          ->  Gather  (cost=15182.52..15182.73 rows=2 width=32)
                Workers Planned: 2
                ->  Partial Aggregate  (cost=14182.52..14182.53 rows=1 width=32)
                      ->  Parallel Seq Scan on osha_violation_summary osha_violation_summary_1  (cost=0.00..13274.01 rows=363401 width=4)
  InitPlan 6
    ->  Aggregate  (cost=1311.94..1311.95 rows=1 width=8)
          ->  Index Only Scan using idx_osha_acc_fatal on osha_accidents  (cost=0.29..1154.28 rows=63066 width=0)
  InitPlan 7
    ->  Aggregate  (cost=588.19..588.20 rows=1 width=8)
          ->  Index Only Scan using idx_osha_acc_fatal on osha_accidents osha_accidents_1  (cost=0.29..525.20 rows=25195 width=0)
                Index Cond: (is_fatality = true)
  InitPlan 8
    ->  Aggregate  (cost=3369.25..3369.26 rows=1 width=8)
          ->  Index Only Scan using idx_osha_f7_ein on osha_f7_matches  (cost=0.29..3023.40 rows=138340 width=0)
  InitPlan 9
    ->  Aggregate  (cost=4401.37..4401.38 rows=1 width=8)
          ->  Index Only Scan using idx_osha_f7_emp on osha_f7_matches osha_f7_matches_1  (cost=0.42..4055.52 rows=138340 width=17)
```

## api_trends_national_raw
```sql
SELECT yr_covered as year,
               COUNT(DISTINCT f_num) as union_count,
               SUM(CASE WHEN members > 0 THEN members ELSE 0 END) as total_members_raw,
               COUNT(*) as filing_count
        FROM lm_data
        WHERE yr_covered BETWEEN 2010 AND 2024
        GROUP BY yr_covered
        ORDER BY yr_covered
```
```text
GroupAggregate  (cost=2403.29..46581.20 rows=16 width=28)
  Group Key: yr_covered
  ->  Incremental Sort  (cost=2403.29..42513.86 rows=325375 width=14)
        Sort Key: yr_covered, f_num
        Presorted Key: yr_covered
        ->  Index Scan using idx_lm_data_yr on lm_data  (cost=0.42..15162.93 rows=325375 width=14)
              Index Cond: ((yr_covered >= 2010) AND (yr_covered <= 2024))
```

## api_trends_national_dedup
```sql
SELECT
            SUM(CASE WHEN count_members THEN members ELSE 0 END) as deduplicated_total,
            SUM(members) as raw_total
        FROM v_union_members_deduplicated
```
```text
Aggregate  (cost=2141.48..2141.49 rows=1 width=16)
  ->  Hash Right Join  (cost=1111.38..2008.15 rows=26665 width=5)
        Hash Cond: ((l.f_num)::text = (h.f_num)::text)
        ->  Index Scan using idx_lm_data_yr on lm_data l  (cost=0.42..847.12 rows=19068 width=6)
              Index Cond: (yr_covered = 2024)
        ->  Hash  (cost=777.65..777.65 rows=26665 width=11)
              ->  Seq Scan on union_hierarchy h  (cost=0.00..777.65 rows=26665 width=11)
```
