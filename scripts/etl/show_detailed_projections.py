import os
import psycopg2
conn = psycopg2.connect(host='localhost', dbname='olms_multiyear', user='postgres', password='os.environ.get('DB_PASSWORD', '')')
cur = conn.cursor()

print("=== Detailed Industry Projections (Construction sub-industries) ===\n")
cur.execute("""
    SELECT matrix_code, industry_title, employment_2024, employment_2034,
           employment_change_pct, growth_category
    FROM bls_industry_projections
    WHERE matrix_code LIKE '23%'
    ORDER BY matrix_code
""")
print(f"{'Code':<8} {'Industry':<55} {'2024':>10} {'2034':>10} {'Change':>8}")
print("-" * 95)
for r in cur.fetchall():
    print(f"{r[0]:<8} {r[1][:54]:<55} {r[2]:>10,.1f} {r[3]:>10,.1f} {r[4]:>7.1f}%")

print("\n\n=== Top Occupations in Poured Concrete (238110) ===\n")
cur.execute("""
    SELECT occupation_code, occupation_title, emp_2024, emp_2034, emp_change_pct
    FROM bls_industry_occupation_matrix
    WHERE industry_code = '238110'
    AND occupation_type = 'Line Item'
    ORDER BY emp_2024 DESC
    LIMIT 15
""")
print(f"{'SOC':<10} {'Occupation':<50} {'2024':>8} {'2034':>8} {'Chg%':>7}")
print("-" * 88)
for r in cur.fetchall():
    print(f"{r[0]:<10} {r[1][:49]:<50} {r[2]:>8,.1f} {r[3]:>8,.1f} {r[4]:>6.1f}%")

conn.close()
