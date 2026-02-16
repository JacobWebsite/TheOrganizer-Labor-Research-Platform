import os
"""
Analyze UNKNOWN affiliation employers
"""
import psycopg2

conn = psycopg2.connect(host='localhost', dbname='olms_multiyear', user='postgres', password=os.environ.get('DB_PASSWORD', ''))
cur = conn.cursor()

print("=" * 80)
print("UNKNOWN Affiliation Analysis")
print("=" * 80)

# Summary
cur.execute("""
    SELECT COUNT(*), SUM(reconciled_workers)
    FROM v_f7_private_sector_cleaned
    WHERE affiliation = 'UNKNOWN' OR affiliation IS NULL;
""")
r = cur.fetchone()
print(f"\nTotal UNKNOWN: {r[0]:,} employers, {r[1] or 0:,.0f} workers")

# Top 50 UNKNOWN employers by size
print("\n--- Top 50 UNKNOWN Employers ---")
cur.execute("""
    SELECT employer_name, city, state, reconciled_workers, match_type
    FROM v_f7_private_sector_cleaned
    WHERE affiliation = 'UNKNOWN' OR affiliation IS NULL
    ORDER BY reconciled_workers DESC
    LIMIT 50;
""")
print(f"{'Employer':<50} {'City':<15} {'St':<3} {'Workers':>10} {'Type'}")
print("-" * 95)
for r in cur.fetchall():
    print(f"{(r[0] or 'Unknown')[:50]:<50} {(r[1] or '')[:15]:<15} {r[2] or '':<3} {r[3] or 0:>10,.0f} {r[4]}")

# By match type
print("\n--- UNKNOWN by Match Type ---")
cur.execute("""
    SELECT match_type, COUNT(*), SUM(reconciled_workers)
    FROM v_f7_private_sector_cleaned
    WHERE affiliation = 'UNKNOWN' OR affiliation IS NULL
    GROUP BY match_type
    ORDER BY SUM(reconciled_workers) DESC;
""")
for r in cur.fetchall():
    print(f"  {r[0]:<20} {r[1]:>8,} employers, {r[2] or 0:>12,.0f} workers")

# By state
print("\n--- UNKNOWN by State (Top 15) ---")
cur.execute("""
    SELECT state, COUNT(*), SUM(reconciled_workers)
    FROM v_f7_private_sector_cleaned
    WHERE affiliation = 'UNKNOWN' OR affiliation IS NULL
    GROUP BY state
    ORDER BY SUM(reconciled_workers) DESC
    LIMIT 15;
""")
for r in cur.fetchall():
    print(f"  {r[0] or 'N/A':<5} {r[1]:>6,} employers, {r[2] or 0:>10,.0f} workers")

conn.close()
