import os
import psycopg2
conn = psycopg2.connect(host='localhost', dbname='olms_multiyear', user='postgres', password='os.environ.get('DB_PASSWORD', '')')
cur = conn.cursor()

# Check for industry 238110 (Poured Concrete Foundation)
print("=== Data for industry 238110 (from CSV filename) ===")
cur.execute("""
    SELECT industry_code, occupation_code, occupation_title, emp_2024, emp_2034, emp_change_pct
    FROM bls_industry_occupation_matrix
    WHERE industry_code = '238110'
    ORDER BY occupation_code
    LIMIT 20
""")
rows = cur.fetchall()
print(f"Found {len(rows)} occupations for 238110")
for r in rows:
    print(f"  {r[1]} {r[2][:40]:40s} 2024: {r[3]:8.1f}  2034: {r[4]:8.1f}  change: {r[5]:5.1f}%")

# Count unique industries in the matrix
print("\n=== Industry coverage ===")
cur.execute("SELECT COUNT(DISTINCT industry_code) FROM bls_industry_occupation_matrix")
print(f"Unique industries in matrix: {cur.fetchone()[0]}")

# Count industries in projections table
cur.execute("SELECT COUNT(*) FROM bls_industry_projections")
print(f"Industries in projections table: {cur.fetchone()[0]}")

# Check a sample industry from the projections
print("\n=== Sample industry projection ===")
cur.execute("""
    SELECT matrix_code, industry_title, employment_2024, employment_2034, employment_change_pct
    FROM bls_industry_projections
    WHERE matrix_code LIKE '%238%'
    LIMIT 5
""")
for r in cur.fetchall():
    print(f"  {r}")

# Total occupation records
print("\n=== Summary ===")
cur.execute("SELECT COUNT(*) FROM bls_industry_occupation_matrix")
print(f"Total industry-occupation records: {cur.fetchone()[0]}")
cur.execute("SELECT COUNT(*) FROM bls_occupation_projections")
print(f"National occupation projections: {cur.fetchone()[0]}")

conn.close()
