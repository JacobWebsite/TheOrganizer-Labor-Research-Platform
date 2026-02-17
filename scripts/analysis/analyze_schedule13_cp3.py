import os
"""
Schedule 13 Membership Analysis - Checkpoint 3
Calculate TRUE ACTIVE membership by national union
Compare to headline LM total members
"""
import psycopg2
from db_config import get_connection
import pandas as pd

conn = get_connection()

print("="*80)
print("CHECKPOINT 3: TRUE ACTIVE MEMBERSHIP BY NATIONAL UNION (2024)")
print("="*80)

# Get deduplicated LM totals (excluding federations) and Schedule 13 active counts
query = """
WITH lm_summary AS (
    SELECT 
        aff_abbr,
        COUNT(DISTINCT rpt_id) as num_locals,
        SUM(members) as lm_total
    FROM lm_data 
    WHERE load_year = 2024 
      AND aff_abbr IS NOT NULL 
      AND aff_abbr != ''
      AND aff_abbr NOT IN ('AFLCIO', 'ACT', 'SOC', 'TTD', 'BCTD', 'MTD')  -- Exclude federations
    GROUP BY aff_abbr
),
sched13_summary AS (
    SELECT 
        l.aff_abbr,
        SUM(CASE 
            WHEN LOWER(m.category) LIKE '%retire%' 
              OR LOWER(m.category) LIKE '%pension%'
              OR LOWER(m.category) LIKE '%life member%'
              OR LOWER(m.category) LIKE '%honorary%'
              OR LOWER(m.category) LIKE '%inactive%'
              OR LOWER(m.category) LIKE '%withdrawn%'
              OR LOWER(m.category) LIKE '%exempt%'
              OR LOWER(m.category) LIKE '%disabled%'
              OR LOWER(m.category) LIKE '%gold card%'
              OR LOWER(m.category) LIKE '%emeritus%'
              OR LOWER(m.category) LIKE '%retiree%'
            THEN m.number ELSE 0 END) as inactive_members,
        SUM(CASE 
            WHEN LOWER(m.category) LIKE '%active%'
              OR LOWER(m.category) LIKE '%regular%'
              OR LOWER(m.category) LIKE '%full time%'
              OR LOWER(m.category) LIKE '%fulltime%'
              OR LOWER(m.category) LIKE '%full-time%'
              OR LOWER(m.category) LIKE '%dues paying%'
              OR LOWER(m.category) LIKE '%dues-paying%'
              OR LOWER(m.category) LIKE '%working member%'
              OR LOWER(m.category) LIKE '%career%'
              OR LOWER(m.category) LIKE '%journeyman%'
              OR LOWER(m.category) LIKE '%journeymen%'
              OR LOWER(m.category) LIKE '%apprentice%'
            THEN m.number ELSE 0 END) as active_members,
        SUM(m.number) as sched13_total
    FROM lm_data l
    JOIN ar_membership m ON l.rpt_id = m.rpt_id
    WHERE l.load_year = 2024 
      AND m.load_year = 2024 
      AND m.membership_type = 2101
      AND l.aff_abbr NOT IN ('AFLCIO', 'ACT', 'SOC', 'TTD', 'BCTD', 'MTD')
    GROUP BY l.aff_abbr
)
SELECT 
    lm.aff_abbr as union_abbr,
    lm.num_locals,
    lm.lm_total,
    COALESCE(s.sched13_total, 0) as sched13_total,
    COALESCE(s.active_members, 0) as sched13_active,
    COALESCE(s.inactive_members, 0) as sched13_inactive,
    -- Estimated true active = Sched13 total minus inactive
    COALESCE(s.sched13_total, 0) - COALESCE(s.inactive_members, 0) as est_active_members
FROM lm_summary lm
LEFT JOIN sched13_summary s ON lm.aff_abbr = s.aff_abbr
WHERE lm.lm_total > 10000
ORDER BY lm.lm_total DESC
"""

df = pd.read_sql(query, conn)

# Calculate key metrics
df['inactive_pct'] = (df['sched13_inactive'] / df['sched13_total'].replace(0, 1) * 100).round(1)
df['lm_vs_active_diff'] = df['lm_total'] - df['est_active_members']
df['inflation_pct'] = ((df['lm_total'] - df['est_active_members']) / df['est_active_members'].replace(0, 1) * 100).round(1)

print("\n" + "="*80)
print("TOP 40 UNIONS: LM TOTAL vs ESTIMATED ACTIVE MEMBERS")
print("="*80)
print(f"{'Union':<10} {'Locals':>7} {'LM_Total':>12} {'Sched13_Tot':>12} {'Est_Active':>12} {'Inactive':>10} {'Inact%':>7} {'Inflat%':>8}")
print("-"*90)

for _, row in df.head(40).iterrows():
    print(f"{row['union_abbr']:<10} {row['num_locals']:>7,} {row['lm_total']:>12,} "
          f"{row['sched13_total']:>12,} {row['est_active_members']:>12,} "
          f"{row['sched13_inactive']:>10,} {row['inactive_pct']:>6.1f}% {row['inflation_pct']:>7.1f}%")

# Summary statistics
print("\n" + "="*80)
print("SUMMARY STATISTICS (Excluding Federation Double-Counts)")
print("="*80)
total_lm = df['lm_total'].sum()
total_active = df['est_active_members'].sum()
total_inactive = df['sched13_inactive'].sum()

print(f"Total LM Reported Members:     {total_lm:>15,}")
print(f"Total Estimated Active:        {total_active:>15,}")
print(f"Total Retired/Inactive:        {total_inactive:>15,}")
print(f"Overall Inactive Rate:         {total_inactive/total_active*100:>14.1f}%")

# Big discrepancies - where LM total >> Sched13 total
print("\n" + "="*80)
print("UNIONS WITH BIGGEST LM vs SCHED13 DISCREPANCIES (potential data issues)")
print("="*80)
df['sched13_coverage'] = (df['sched13_total'] / df['lm_total'] * 100).round(1)
low_coverage = df[df['sched13_coverage'] < 50].sort_values('lm_total', ascending=False).head(15)
print(f"{'Union':<10} {'LM_Total':>12} {'Sched13_Tot':>12} {'Coverage%':>10}")
print("-"*50)
for _, row in low_coverage.iterrows():
    print(f"{row['union_abbr']:<10} {row['lm_total']:>12,} {row['sched13_total']:>12,} {row['sched13_coverage']:>9.1f}%")

conn.close()
print("\n" + "="*80)
print("CHECKPOINT 3 COMPLETE")
print("="*80)
