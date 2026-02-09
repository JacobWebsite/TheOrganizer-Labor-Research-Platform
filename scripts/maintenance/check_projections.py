import os
import psycopg2
conn = psycopg2.connect(host='localhost', database='olms_multiyear', user='postgres', password='os.environ.get('DB_PASSWORD', '')')
cur = conn.cursor()

# Get sector-level totals (like '620000' for Healthcare)
cur.execute("""
    SELECT naics_2digit, sector_name, naics_code, industry_title, 
           employment_2024, employment_2034, employment_change, percent_change
    FROM v_naics_projections
    WHERE naics_code LIKE '%0000'
    ORDER BY naics_2digit
    LIMIT 20
""")
print("Sector-level projections (ending in 0000):")
for r in cur.fetchall():
    print(f"  {r[0]} - {r[1]}: {r[4]} -> {r[5]} ({r[7]}%)")

conn.close()
