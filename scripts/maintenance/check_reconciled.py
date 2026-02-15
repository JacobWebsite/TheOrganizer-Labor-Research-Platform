import os
import psycopg2
from db_config import get_connection
conn = get_connection()
cur = conn.cursor()

# Check v_f7_reconciled_private_sector properly
print("=== v_f7_reconciled_private_sector ===")
cur.execute("SELECT COUNT(*), SUM(reconciled_workers) FROM v_f7_reconciled_private_sector;")
row = cur.fetchone()
print(f"Records: {row[0]:,}, Workers (reconciled): {row[1] or 0:,.0f}")

# Top employers in reconciled view
cur.execute("""
    SELECT employer_name, reconciled_workers, affiliation, match_type
    FROM v_f7_reconciled_private_sector 
    ORDER BY reconciled_workers DESC NULLS LAST
    LIMIT 15;
""")
print("\nTop 15 in v_f7_reconciled_private_sector:")
print(f"{'Employer':<45} {'Workers':>12} {'Union':<10} {'Match Type'}")
print("-" * 85)
for r in cur.fetchall():
    print(f"{(r[0] or 'Unknown')[:45]:<45} {r[1] or 0:>12,.0f} {r[2] or 'N/A':<10} {r[3] or ''}")

# Check if federal contamination is filtered out
print("\n=== Federal contamination check ===")
cur.execute("""
    SELECT employer_name, reconciled_workers, affiliation
    FROM v_f7_reconciled_private_sector
    WHERE employer_name ILIKE '%postal%' 
       OR employer_name ILIKE '%veterans affairs%'
       OR employer_name ILIKE '%department of%'
       OR affiliation IN ('AFGE', 'APWU', 'NALC', 'NFFE', 'NTEU')
    ORDER BY reconciled_workers DESC
    LIMIT 10;
""")
results = cur.fetchall()
if results:
    print("WARNING: Still has federal contamination:")
    for r in results:
        print(f"  {r[0][:45]:<45} {r[1] or 0:>12,.0f} {r[2]}")
else:
    print("CLEAN: No federal contamination found")

# Check total workers in v_employer_search for comparison
print("\n=== Comparison ===")
cur.execute("SELECT COUNT(*), SUM(bargaining_unit_size) FROM v_employer_search;")
row = cur.fetchone()
print(f"v_employer_search: {row[0]:,} records, {row[1] or 0:,.0f} raw workers")

cur.execute("SELECT COUNT(*), SUM(reconciled_workers) FROM v_f7_reconciled_private_sector;")
row = cur.fetchone()
print(f"v_f7_reconciled_private_sector: {row[0]:,} records, {row[1] or 0:,.0f} reconciled workers")

conn.close()
