import os
import sys
"""
Trace the 6.6M vs 15M discrepancy
"""

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
from db_config import get_connection

conn = get_connection()
conn.autocommit = True
cur = conn.cursor()

print("=" * 80)
print("TRACING F-7 WORKER COUNTS")
print("=" * 80)

# Check all F-7 related views/tables
sources = [
    ("f7_employers", "latest_unit_size"),
    ("f7_employers_deduped", "latest_unit_size"),
    ("v_f7_union_summary", "workers_covered"),
    ("v_f7_private_sector_cleaned", "reconciled_workers"),
    ("v_f7_private_sector_cleaned", "f7_reported_workers"),
    ("v_f7_employers_adjusted", "workers_covered"),
    ("v_f7_employers_fully_adjusted", "workers_covered"),
    ("v_f7_reconciled_private_sector", "workers_covered"),
]

print("\n--- Worker Counts by Source ---")
print(f"{'Source':<40} {'Rows':>12} {'Workers':>15}")
print("-" * 70)

for table, col in sources:
    try:
        cur.execute(f"SELECT COUNT(*), SUM({col}) FROM {table}")
        row = cur.fetchone()
        print(f"{table:<40} {row[0]:>12,} {row[1] or 0:>15,.0f}")
    except Exception as e:
        print(f"{table:<40} ERROR: {str(e)[:30]}")

# Check v_f7_union_summary by sector_revised
print("\n--- v_f7_union_summary by sector_revised ---")
try:
    cur.execute("""
        SELECT 
            COALESCE(sector_revised, 'NULL') as sector,
            COUNT(*) as employers,
            SUM(workers_covered) as workers
        FROM v_f7_union_summary
        GROUP BY sector_revised
        ORDER BY workers DESC NULLS LAST
    """)
    print(f"{'Sector':<28} {'Employers':>10} {'Workers':>14}")
    print("-" * 55)
    total_emp = 0
    total_work = 0
    for row in cur.fetchall():
        print(f"{row[0]:<28} {row[1]:>10,} {row[2] or 0:>14,.0f}")
        total_emp += row[1]
        total_work += (row[2] or 0)
    print("-" * 55)
    print(f"{'TOTAL':<28} {total_emp:>10,} {total_work:>14,.0f}")
except Exception as e:
    print(f"ERROR: {e}")

# Check what v_f7_private_sector_cleaned is filtering
print("\n--- v_f7_private_sector_cleaned definition ---")
cur.execute("""
    SELECT pg_get_viewdef('v_f7_private_sector_cleaned'::regclass, true)
""")
viewdef = cur.fetchone()[0]
print(viewdef[:1500] + "..." if len(viewdef) > 1500 else viewdef)

conn.close()
