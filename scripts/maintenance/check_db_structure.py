import os
import sys
"""
Check available F-7 data sources - fixed
"""
from psycopg2.extras import RealDictCursor

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
from db_config import get_connection

conn = get_connection()
conn.autocommit = True  # Prevent transaction issues
cur = conn.cursor()

print("=" * 80)
print("CHECKING DATABASE STRUCTURE")
print("=" * 80)

# List all tables that start with f7
print("\n--- Tables containing 'f7' ---")
cur.execute("""
    SELECT table_name 
    FROM information_schema.tables 
    WHERE table_schema = 'public' 
    AND table_name LIKE '%f7%'
    ORDER BY table_name;
""")
for row in cur.fetchall():
    cur.execute(f"SELECT COUNT(*) FROM {row[0]}")
    count = cur.fetchone()[0]
    print(f"  {row[0]}: {count:,} rows")

# List views containing f7
print("\n--- Views containing 'f7' ---")
cur.execute("""
    SELECT table_name 
    FROM information_schema.views 
    WHERE table_schema = 'public' 
    AND table_name LIKE '%f7%'
    ORDER BY table_name;
""")
views = cur.fetchall()
for row in views:
    try:
        cur.execute(f"SELECT COUNT(*) FROM {row[0]}")
        count = cur.fetchone()[0]
        print(f"  {row[0]}: {count:,} rows")
    except:
        print(f"  {row[0]}: ERROR")

# Check v_f7_private_sector_cleaned structure
print("\n--- v_f7_private_sector_cleaned columns ---")
cur.execute("""
    SELECT column_name, data_type
    FROM information_schema.columns 
    WHERE table_name = 'v_f7_private_sector_cleaned'
    ORDER BY ordinal_position;
""")
for row in cur.fetchall():
    print(f"  {row[0]}: {row[1]}")

# Check data in v_f7_private_sector_cleaned
print("\n--- v_f7_private_sector_cleaned stats ---")
cur.execute("""
    SELECT 
        COUNT(*) as total,
        SUM(COALESCE(f7_reported_workers, 0)) as f7_workers,
        SUM(COALESCE(reconciled_workers, 0)) as reconciled_workers
    FROM v_f7_private_sector_cleaned
""")
row = cur.fetchone()
print(f"  Total: {row[0]:,} rows")
print(f"  F7 reported workers: {row[1]:,.0f}")
print(f"  Reconciled workers: {row[2]:,.0f}")

# Check by affiliation
print("\n--- Top affiliations in v_f7_private_sector_cleaned ---")
cur.execute("""
    SELECT 
        affiliation,
        COUNT(*) as employers,
        SUM(COALESCE(reconciled_workers, 0)) as workers
    FROM v_f7_private_sector_cleaned
    GROUP BY affiliation
    ORDER BY workers DESC
    LIMIT 15
""")
print(f"  {'Affiliation':<15} {'Employers':>10} {'Workers':>14}")
print("  " + "-" * 45)
for row in cur.fetchall():
    print(f"  {(row[0] or 'NULL')[:15]:<15} {row[1]:>10,} {row[2] or 0:>14,.0f}")

# Check unions_master for sector_revised
print("\n--- unions_master sector_revised ---")
cur.execute("""
    SELECT 
        sector_revised,
        COUNT(*) as unions,
        SUM(members) as members
    FROM unions_master
    GROUP BY sector_revised
    ORDER BY members DESC NULLS LAST
""")
print(f"  {'Sector':<25} {'Unions':>8} {'Members':>14}")
print("  " + "-" * 55)
for row in cur.fetchall():
    print(f"  {(row[0] or 'NULL')[:25]:<25} {row[1]:>8,} {row[2] or 0:>14,.0f}")

conn.close()
