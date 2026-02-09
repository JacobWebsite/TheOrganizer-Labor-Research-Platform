import os
"""Verify the Mergent employer load"""
import psycopg2

conn = psycopg2.connect(
    host='localhost',
    dbname='olms_multiyear',
    user='postgres',
    password='os.environ.get('DB_PASSWORD', '')'
)
cur = conn.cursor()

# Check total count
cur.execute("SELECT COUNT(*) FROM mergent_employers")
total = cur.fetchone()[0]
print(f"Total employers in mergent_employers: {total}")

# Check by sector
cur.execute("""
    SELECT sector_category, COUNT(*),
           SUM(employees_site) as total_employees,
           COUNT(CASE WHEN ein IS NOT NULL THEN 1 END) as with_ein,
           COUNT(CASE WHEN has_union = true THEN 1 END) as unionized
    FROM mergent_employers
    GROUP BY sector_category
    ORDER BY COUNT(*) DESC
""")

print(f"\n{'Sector':<25} {'Count':>8} {'Employees':>12} {'With EIN':>10} {'Unionized':>10}")
print("-" * 70)
for row in cur.fetchall():
    emp = f"{row[2]:,}" if row[2] else "N/A"
    print(f"{row[0] or 'NULL':<25} {row[1]:>8,} {emp:>12} {row[3]:>10,} {row[4]:>10,}")

cur.close()
conn.close()
