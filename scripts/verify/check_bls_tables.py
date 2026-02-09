import os
import psycopg2
conn = psycopg2.connect(host='localhost', dbname='olms_multiyear', user='postgres', password='os.environ.get('DB_PASSWORD', '')')
cur = conn.cursor()

# Check bls_industry_occupation_matrix
print("=== bls_industry_occupation_matrix ===")
cur.execute("SELECT COUNT(*) FROM bls_industry_occupation_matrix")
print(f"Count: {cur.fetchone()[0]}")
cur.execute("SELECT * FROM bls_industry_occupation_matrix LIMIT 3")
rows = cur.fetchall()
cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name = 'bls_industry_occupation_matrix' ORDER BY ordinal_position")
cols = [c[0] for c in cur.fetchall()]
print(f"Columns: {cols}")
for r in rows:
    print(f"  {r}")

# Check bls_industry_projections
print("\n=== bls_industry_projections ===")
cur.execute("SELECT COUNT(*) FROM bls_industry_projections")
print(f"Count: {cur.fetchone()[0]}")
cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name = 'bls_industry_projections' ORDER BY ordinal_position")
cols = [c[0] for c in cur.fetchall()]
print(f"Columns: {cols}")
cur.execute("SELECT * FROM bls_industry_projections LIMIT 3")
for r in cur.fetchall():
    print(f"  {r}")

# Check bls_occupation_projections
print("\n=== bls_occupation_projections ===")
cur.execute("SELECT COUNT(*) FROM bls_occupation_projections")
print(f"Count: {cur.fetchone()[0]}")
cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name = 'bls_occupation_projections' ORDER BY ordinal_position")
cols = [c[0] for c in cur.fetchall()]
print(f"Columns: {cols}")
cur.execute("SELECT * FROM bls_occupation_projections LIMIT 3")
for r in cur.fetchall():
    print(f"  {r}")

# Check if we have the detailed occupation breakdown per industry
print("\n=== Sample from matrix for a specific industry ===")
cur.execute("""
    SELECT industry_code, occupation_code, occupation_title, employment_2024, employment_2034, percent_change
    FROM bls_industry_occupation_matrix
    WHERE industry_code LIKE '238%'
    LIMIT 10
""")
for r in cur.fetchall():
    print(f"  {r}")

conn.close()
