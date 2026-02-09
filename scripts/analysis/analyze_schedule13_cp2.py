import os
"""
Schedule 13 Membership Analysis - Checkpoint 2
Compare active members vs total members by national union
"""
import psycopg2
import pandas as pd

conn = psycopg2.connect(
    host='localhost', port=5432, database='olms_multiyear',
    user='postgres', password='os.environ.get('DB_PASSWORD', '')'
)

print("="*80)
print("CHECKPOINT 2: ACTIVE vs TOTAL MEMBERS BY NATIONAL UNION (2024)")
print("="*80)

# First, identify "active" categories
active_keywords = ['active', 'regular', 'full time', 'full-time', 'fulltime', 
                   'dues paying', 'dues-paying', 'working', 'career']
inactive_keywords = ['retire', 'pension', 'life member', 'honorary', 'inactive',
                     'withdrawn', 'exempt', 'disabled', 'gold card', 'emeritus']

# Build query to sum Schedule 13 members linked to lm_data
query = """
WITH membership_detail AS (
    SELECT 
        m.rpt_id,
        m.category,
        m.number,
        CASE 
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
            THEN 'inactive'
            WHEN LOWER(m.category) LIKE '%active%'
              OR LOWER(m.category) LIKE '%regular%'
              OR LOWER(m.category) LIKE '%full time%'
              OR LOWER(m.category) LIKE '%fulltime%'
              OR LOWER(m.category) LIKE '%full-time%'
              OR LOWER(m.category) LIKE '%dues paying%'
              OR LOWER(m.category) LIKE '%dues-paying%'
              OR LOWER(m.category) LIKE '%working%'
              OR LOWER(m.category) LIKE '%career%'
              OR LOWER(m.category) LIKE '%journeyman%'
              OR LOWER(m.category) LIKE '%journeymen%'
              OR LOWER(m.category) LIKE '%apprentice%'
            THEN 'active'
            ELSE 'other'
        END as member_status
    FROM ar_membership m
    WHERE m.load_year = 2024 AND m.membership_type = 2101
)
SELECT 
    l.aff_abbr,
    COUNT(DISTINCT l.rpt_id) as num_locals,
    SUM(l.members) as lm_total_members,
    SUM(CASE WHEN md.member_status = 'active' THEN md.number ELSE 0 END) as sched13_active,
    SUM(CASE WHEN md.member_status = 'inactive' THEN md.number ELSE 0 END) as sched13_inactive,
    SUM(CASE WHEN md.member_status = 'other' THEN md.number ELSE 0 END) as sched13_other,
    SUM(md.number) as sched13_total
FROM lm_data l
LEFT JOIN membership_detail md ON l.rpt_id = md.rpt_id
WHERE l.load_year = 2024 
  AND l.aff_abbr IS NOT NULL 
  AND l.aff_abbr != ''
GROUP BY l.aff_abbr
HAVING SUM(l.members) > 50000
ORDER BY SUM(l.members) DESC
"""

df = pd.read_sql(query, conn)

# Calculate percentages
df['active_pct'] = (df['sched13_active'] / df['sched13_total'] * 100).round(1)
df['inactive_pct'] = (df['sched13_inactive'] / df['sched13_total'] * 100).round(1)
df['lm_vs_sched13_diff'] = df['lm_total_members'] - df['sched13_total']
df['lm_vs_sched13_pct'] = ((df['lm_total_members'] - df['sched13_total']) / df['lm_total_members'] * 100).round(1)

print("\nNational Unions with >50K members - Active vs Inactive breakdown:\n")
pd.set_option('display.max_rows', 100)
pd.set_option('display.width', 200)
pd.set_option('display.max_columns', 15)

# Format for display
display_df = df[['aff_abbr', 'num_locals', 'lm_total_members', 'sched13_active', 
                 'sched13_inactive', 'sched13_other', 'active_pct', 'inactive_pct']].copy()
display_df.columns = ['Union', 'Locals', 'LM_Total', 'Sched13_Active', 'Sched13_Inactive', 
                      'Sched13_Other', 'Active%', 'Inactive%']
print(display_df.to_string(index=False))

# Find unions with HIGH inactive percentages
print("\n" + "="*80)
print("UNIONS WITH HIGHEST INACTIVE/RETIRED PERCENTAGES (>15%):")
print("="*80)
high_inactive = df[df['inactive_pct'] > 15].sort_values('inactive_pct', ascending=False)
for _, row in high_inactive.iterrows():
    print(f"{row['aff_abbr']:12} | {row['inactive_pct']:5.1f}% inactive | "
          f"{row['sched13_inactive']:>10,.0f} retirees of {row['sched13_total']:>12,.0f} total")

conn.close()
print("\n" + "="*80)
print("CHECKPOINT 2 COMPLETE")
print("="*80)
