import os
"""
Check available F-7 data sources and their stats
"""
import psycopg2

conn = psycopg2.connect(
    host="localhost",
    dbname="olms_multiyear",
    user="postgres",
    password="os.environ.get('DB_PASSWORD', '')"
)
cur = conn.cursor()

print("=" * 80)
print("CHECKING F-7 DATA SOURCES")
print("=" * 80)

# Check various possible sources
sources = [
    "v_f7_private_sector_cleaned",
    "v_f7_union_summary",
    "f7_employers_deduped",
    "f7_employers",
    "v_f7_reconciled_private_sector",
    "v_f7_employers_fully_adjusted"
]

for src in sources:
    try:
        cur.execute(f"SELECT COUNT(*) FROM {src}")
        count = cur.fetchone()[0]
        
        # Try to get workers
        try:
            # Try different column names
            for col in ['workers_covered', 'reconciled_workers', 'latest_unit_size', 'f7_reported_workers', 'total_workers']:
                try:
                    cur.execute(f"SELECT SUM({col}) FROM {src}")
                    workers = cur.fetchone()[0]
                    if workers:
                        print(f"  {src}: {count:,} rows, {workers:,.0f} workers ({col})")
                        break
                except:
                    continue
            else:
                print(f"  {src}: {count:,} rows (no workers column found)")
        except Exception as e:
            print(f"  {src}: {count:,} rows (workers error: {str(e)[:30]})")
    except Exception as e:
        print(f"  {src}: NOT FOUND")

# Check sector_revised column
print("\n--- Checking sector_revised in unions_master ---")
try:
    cur.execute("""
        SELECT sector_revised, COUNT(*), SUM(members)
        FROM unions_master
        WHERE sector_revised IS NOT NULL
        GROUP BY sector_revised
        ORDER BY SUM(members) DESC NULLS LAST
    """)
    print("sector_revised values:")
    for row in cur.fetchall():
        print(f"  {row[0]}: {row[1]:,} unions, {row[2] or 0:,.0f} members")
except Exception as e:
    print(f"  Error: {e}")

# Check v_f7_union_summary structure
print("\n--- v_f7_union_summary columns ---")
cur.execute("""
    SELECT column_name, data_type
    FROM information_schema.columns 
    WHERE table_name = 'v_f7_union_summary'
    ORDER BY ordinal_position
    LIMIT 20;
""")
for row in cur.fetchall():
    print(f"  {row[0]}: {row[1]}")

# Check v_f7_union_summary by sector_revised
print("\n--- v_f7_union_summary by sector (if available) ---")
try:
    cur.execute("""
        SELECT 
            COALESCE(sector_revised, 'UNKNOWN') as sector,
            COUNT(*) as employers,
            SUM(workers_covered) as workers
        FROM v_f7_union_summary
        GROUP BY sector_revised
        ORDER BY workers DESC NULLS LAST
    """)
    print(f"  {'Sector':<25} {'Employers':>12} {'Workers':>14}")
    print("  " + "-" * 55)
    for row in cur.fetchall():
        print(f"  {row[0] or 'NULL':<25} {row[1]:>12,} {row[2] or 0:>14,.0f}")
except Exception as e:
    print(f"  Error: {e}")

conn.close()
