import os
"""
Schedule 13 Membership Analysis - TOTAL ESTIMATE
Calculate total estimated union members across ALL unions
"""
import psycopg2
import pandas as pd

conn = psycopg2.connect(
    host='localhost', port=5432, database='olms_multiyear',
    user='postgres', password=os.environ.get('DB_PASSWORD', '')
)

print("="*80)
print("TOTAL ESTIMATED UNION MEMBERSHIP (2024) - ALL UNIONS")
print("="*80)

# Get ALL unions with Schedule 13 breakdown
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
    COALESCE(s.inactive_members, 0) as sched13_inactive,
    COALESCE(s.sched13_total, 0) - COALESCE(s.inactive_members, 0) as est_active_members
FROM lm_summary lm
LEFT JOIN sched13_summary s ON lm.aff_abbr = s.aff_abbr
ORDER BY lm.lm_total DESC
"""

df = pd.read_sql(query, conn)

# Calculate totals
total_unions = len(df)
total_locals = df['num_locals'].sum()
total_lm_reported = df['lm_total'].sum()
total_sched13 = df['sched13_total'].sum()
total_inactive = df['sched13_inactive'].sum()
total_est_active = df['est_active_members'].sum()

print(f"\n{'='*80}")
print("GRAND TOTALS (Excluding Federation Double-Counts)")
print(f"{'='*80}")
print(f"Number of National Unions:          {total_unions:>15,}")
print(f"Number of Local Unions:             {total_locals:>15,}")
print(f"")
print(f"LM Form Total Members Reported:     {total_lm_reported:>15,}")
print(f"Schedule 13 Total Members:          {total_sched13:>15,}")
print(f"Schedule 13 Inactive/Retired:       {total_inactive:>15,}")
print(f"")
print(f"{'='*80}")
print(f"ESTIMATED ACTIVE UNION MEMBERS:     {total_est_active:>15,}")
print(f"{'='*80}")

# Comparison to BLS
print(f"\nBLS Reported Union Members (2024):  ~14,300,000")
print(f"Our Estimate (Active):              {total_est_active:>11,}")
print(f"Difference:                         {total_est_active - 14300000:>+11,}")

# Break down by size tier
print(f"\n{'='*80}")
print("BREAKDOWN BY UNION SIZE TIER")
print(f"{'='*80}")

df['size_tier'] = pd.cut(df['lm_total'], 
                         bins=[0, 10000, 50000, 100000, 500000, 1000000, 10000000],
                         labels=['<10K', '10K-50K', '50K-100K', '100K-500K', '500K-1M', '>1M'])

tier_summary = df.groupby('size_tier', observed=True).agg({
    'union_abbr': 'count',
    'num_locals': 'sum',
    'lm_total': 'sum',
    'est_active_members': 'sum',
    'sched13_inactive': 'sum'
}).rename(columns={'union_abbr': 'num_unions'})

print(f"{'Tier':<12} {'Unions':>8} {'Locals':>10} {'LM_Total':>15} {'Est_Active':>15} {'Inactive':>12}")
print("-"*75)
for tier, row in tier_summary.iterrows():
    print(f"{tier:<12} {row['num_unions']:>8,} {row['num_locals']:>10,} {row['lm_total']:>15,} {row['est_active_members']:>15,} {row['sched13_inactive']:>12,}")

# Full union list
print(f"\n{'='*80}")
print("COMPLETE LIST - ALL UNIONS BY ESTIMATED ACTIVE MEMBERS")
print(f"{'='*80}")
df_sorted = df.sort_values('est_active_members', ascending=False)
df_sorted['inactive_pct'] = (df_sorted['sched13_inactive'] / df_sorted['sched13_total'].replace(0,1) * 100).round(1)

print(f"{'Union':<12} {'Locals':>7} {'LM_Total':>12} {'Est_Active':>12} {'Inactive':>10} {'Inact%':>7}")
print("-"*65)
for _, row in df_sorted.iterrows():
    print(f"{row['union_abbr']:<12} {row['num_locals']:>7,} {row['lm_total']:>12,} {row['est_active_members']:>12,} {row['sched13_inactive']:>10,} {row['inactive_pct']:>6.1f}%")

# Save to CSV
output_path = r"C:\Users\jakew\Downloads\labor-data-project\union_membership_estimate_2024.csv"
df_sorted.to_csv(output_path, index=False)
print(f"\n\nSaved complete data to: {output_path}")

conn.close()
print(f"\n{'='*80}")
print("ANALYSIS COMPLETE")
print(f"{'='*80}")
