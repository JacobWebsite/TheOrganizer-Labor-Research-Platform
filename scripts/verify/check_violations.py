import os
import psycopg2

from db_config import get_connection
conn = get_connection()
cur = conn.cursor()

# Check what normalized names look like in violations table
cur.execute("SELECT employer_name, employer_name_normalized FROM nyc_wage_theft_nys LIMIT 10")
print("=== Violations (source) ===")
for r in cur.fetchall():
    print(f"  {r[0]} -> {r[1]}")

# Check what normalized names look like in mergent
cur.execute("SELECT company_name, company_name_normalized FROM mergent_employers WHERE state='NY' LIMIT 10")
print("\n=== Mergent (target) ===")
for r in cur.fetchall():
    print(f"  {r[0]} -> {r[1]}")

# Check if there are ANY overlapping normalized names
cur.execute("""
    SELECT v.employer_name, v.employer_name_normalized, m.company_name, m.company_name_normalized
    FROM nyc_wage_theft_nys v
    JOIN mergent_employers m ON LOWER(v.employer_name_normalized) = LOWER(m.company_name_normalized)
    WHERE m.state = 'NY'
    LIMIT 10
""")
rows = cur.fetchall()
print(f"\n=== Direct normalized join matches: {len(rows)} ===")
for r in rows:
    print(f"  {r[0]} ({r[1]}) -> {r[2]} ({r[3]})")

# Try with aggressive normalization inline
cur.execute("""
    SELECT v.employer_name, m.company_name
    FROM nyc_wage_theft_nys v
    JOIN mergent_employers m ON LOWER(REGEXP_REPLACE(v.employer_name, '[^a-zA-Z0-9 ]', '', 'g')) = LOWER(m.company_name_normalized)
    WHERE m.state = 'NY'
    LIMIT 10
""")
rows = cur.fetchall()
print(f"\n=== Inline regex join matches: {len(rows)} ===")
for r in rows:
    print(f"  {r[0]} -> {r[1]}")

# Check if violations are mostly NYC vs statewide
cur.execute("SELECT city, COUNT(*) FROM nyc_wage_theft_nys GROUP BY city ORDER BY COUNT(*) DESC LIMIT 10")
print("\n=== Top cities in violations ===")
for r in cur.fetchall():
    print(f"  {r[0]}: {r[1]}")

# Check mergent city coverage
cur.execute("SELECT city, COUNT(*) FROM mergent_employers WHERE state='NY' GROUP BY city ORDER BY COUNT(*) DESC LIMIT 10")
print("\n=== Top cities in Mergent (NY) ===")
for r in cur.fetchall():
    print(f"  {r[0]}: {r[1]}")

conn.close()
