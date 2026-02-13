import os
"""
Schedule 13 Membership Analysis - Checkpoint 1
Explores ar_membership table structure and categories
"""
import psycopg2
import pandas as pd

conn = psycopg2.connect(
    host='localhost', port=5432, database='olms_multiyear',
    user='postgres', password=os.environ.get('DB_PASSWORD', '')
)

print("="*80)
print("CHECKPOINT 1: EXPLORING SCHEDULE 13 (ar_membership) STRUCTURE")
print("="*80)

# Get top categories by member count
query = """
SELECT category, COUNT(*) as num_records, SUM(number) as total_members
FROM ar_membership 
WHERE load_year = 2024 AND membership_type = 2101
GROUP BY category
ORDER BY total_members DESC
LIMIT 50
"""
df_cats = pd.read_sql(query, conn)
print("\nTop 50 membership categories by total members (2024):")
print(df_cats.to_string(index=False))

# Look for retired/inactive categories  
query2 = """
SELECT category, SUM(number) as total
FROM ar_membership 
WHERE load_year = 2024 
  AND (LOWER(category) LIKE '%retire%' 
       OR LOWER(category) LIKE '%inactive%'
       OR LOWER(category) LIKE '%honorary%'
       OR LOWER(category) LIKE '%life%'
       OR LOWER(category) LIKE '%pension%'
       OR LOWER(category) LIKE '%withdrawn%'
       OR LOWER(category) LIKE '%exempt%')
GROUP BY category
ORDER BY total DESC
LIMIT 30
"""
df_inactive = pd.read_sql(query2, conn)
print("\n\nNon-active type categories (retired, life, honorary, etc.):")
print(df_inactive.to_string(index=False))

conn.close()
print("\n" + "="*80)
print("CHECKPOINT 1 COMPLETE - Review output above")
print("="*80)
