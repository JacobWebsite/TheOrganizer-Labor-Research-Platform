"""
Debug designation field values
"""

import psycopg2

DB_CONFIG = {
    'host': 'localhost',
    'database': 'olms_multiyear',
    'user': 'postgres',
    'password': 'Juniordog33!'
}

conn = psycopg2.connect(**DB_CONFIG)
cursor = conn.cursor()

print("1. Sample of designation fields:")
cursor.execute("""
    SELECT f_num, union_name, desig_name, desig_num, aff_abbr, members
    FROM lm_data
    WHERE yr_covered = 2024
    LIMIT 20
""")
for row in cursor.fetchall():
    print(f"  f_num={row[0]}, desig_name='{row[2]}', desig_num='{row[3]}', aff={row[4]}, members={row[5]}")

print("\n2. All distinct desig_name values:")
cursor.execute("""
    SELECT DISTINCT desig_name, COUNT(*) as cnt
    FROM lm_data
    WHERE yr_covered = 2024
    GROUP BY desig_name
    ORDER BY cnt DESC
    LIMIT 30
""")
for row in cursor.fetchall():
    print(f"  '{row[0]}': {row[1]:,}")

print("\n3. Check TRIM on desig_name:")
cursor.execute("""
    SELECT DISTINCT TRIM(desig_name) as dn, COUNT(*) as cnt
    FROM lm_data
    WHERE yr_covered = 2024
    GROUP BY TRIM(desig_name)
    ORDER BY cnt DESC
    LIMIT 30
""")
for row in cursor.fetchall():
    print(f"  '{row[0]}': {row[1]:,}")

print("\n4. Check for 'LU' specifically:")
cursor.execute("""
    SELECT COUNT(*) FROM lm_data 
    WHERE yr_covered = 2024 AND desig_name = 'LU'
""")
print(f"  Exact match 'LU': {cursor.fetchone()[0]}")

cursor.execute("""
    SELECT COUNT(*) FROM lm_data 
    WHERE yr_covered = 2024 AND TRIM(desig_name) = 'LU'
""")
print(f"  TRIM match 'LU': {cursor.fetchone()[0]}")

cursor.execute("""
    SELECT COUNT(*) FROM lm_data 
    WHERE yr_covered = 2024 AND UPPER(TRIM(desig_name)) = 'LU'
""")
print(f"  UPPER TRIM match 'LU': {cursor.fetchone()[0]}")

print("\n5. Sample LU records:")
cursor.execute("""
    SELECT f_num, union_name, desig_name, desig_num, members, aff_abbr
    FROM lm_data
    WHERE yr_covered = 2024 AND UPPER(TRIM(desig_name)) = 'LU'
    ORDER BY members DESC
    LIMIT 10
""")
for row in cursor.fetchall():
    print(f"  {row[0]}: {row[4]:,} members - {row[1][:40]}")

cursor.close()
conn.close()
