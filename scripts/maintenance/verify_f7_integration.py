import os
"""Final verification of F-7 data integration"""
import psycopg2

PG_CONFIG = {
    'host': 'localhost',
    'database': 'olms_multiyear',
    'user': 'postgres',
    'password': os.environ.get('DB_PASSWORD', '')
}

conn = psycopg2.connect(**PG_CONFIG)
cursor = conn.cursor()

print("="*70)
print("F-7 DATA INTEGRATION - FINAL VERIFICATION")
print("="*70)

# Test v_lm_with_f7_summary - this joins lm_data with unions_master
cursor.execute("""
    SELECT COUNT(*) as total,
           SUM(CASE WHEN has_f7_employers THEN 1 ELSE 0 END) as with_f7
    FROM v_lm_with_f7_summary
    WHERE yr_covered = 2024
""")
row = cursor.fetchone()
print(f"\n2024 LM filings with F-7 linkage:")
print(f"  Total filings: {row[0]:,}")
print(f"  With F-7 employers: {row[1] or 0:,}")

# Test v_f7_employers_full - joins employers with union details
cursor.execute("""
    SELECT COUNT(*) as total,
           COUNT(sector) as with_sector
    FROM v_f7_employers_full
""")
row = cursor.fetchone()
print(f"\nEmployers with union sector info:")
print(f"  Total employers: {row[0]:,}")
print(f"  With sector classification: {row[1]:,}")

# Sample employer record with full details
cursor.execute("""
    SELECT employer_name, city, state, latest_unit_size, 
           latest_union_name, sector_name, governing_law
    FROM v_f7_employers_full
    WHERE latitude IS NOT NULL 
      AND sector IS NOT NULL
      AND latest_unit_size IS NOT NULL
      AND latest_unit_size < 500000
    ORDER BY latest_unit_size DESC
    LIMIT 5
""")
print(f"\nTop 5 employers by unit size (with full details):")
for row in cursor.fetchall():
    name, city, state, workers, union_name, sector, law = row
    union_short = (union_name or 'Unknown')[:50]
    print(f"  {name} ({city}, {state})")
    print(f"    Workers: {workers:,} | Union: {union_short}...")
    print(f"    Sector: {sector} | Law: {law}")

# Test sector summary view
cursor.execute("SELECT * FROM v_sector_summary")
print(f"\nSector Summary (v_sector_summary):")
print(f"  {'Sector':<25} {'Unions':>8} {'Members':>12} {'Employers':>10} {'Workers':>12}")
print(f"  {'-'*25} {'-'*8} {'-'*12} {'-'*10} {'-'*12}")
for row in cursor.fetchall():
    sector, name, law, f7_exp, unions, members, employers, workers = row
    members = members or 0
    employers = employers or 0
    workers = workers or 0
    print(f"  {name:<25} {unions:>8,} {members:>12,} {employers:>10,} {workers:>12,}")

# Test match status summary view
cursor.execute("SELECT * FROM v_match_status_summary")
print(f"\nMatch Status Summary (v_match_status_summary):")
for row in cursor.fetchall():
    status, name, desc, unions, members, employers = row
    unions = unions or 0
    members = members or 0
    employers = employers or 0
    print(f"  {name}: {unions:,} unions, {members:,} members, {employers:,} employers")

# Test state summary view
cursor.execute("SELECT * FROM v_f7_state_summary LIMIT 10")
print(f"\nState Summary - Top 10 (v_f7_state_summary):")
print(f"  {'State':<6} {'Employers':>10} {'Workers':>12} {'Geocoded':>10} {'Defunct':>8}")
print(f"  {'-'*6} {'-'*10} {'-'*12} {'-'*10} {'-'*8}")
for row in cursor.fetchall():
    state, emps, workers, defunct, geocoded, healthcare, unions = row
    workers = workers or 0
    print(f"  {state:<6} {emps:>10,} {workers:>12,} {geocoded:>10,} {defunct:>8,}")

# Sample query: Find employers for a specific union
cursor.execute("""
    SELECT e.employer_name, e.city, e.state, e.latest_unit_size
    FROM f7_employers e
    WHERE e.latest_union_fnum = 56  -- UFCW
    ORDER BY e.latest_unit_size DESC
    LIMIT 5
""")
print(f"\nSample: Top UFCW employers (f_num=56):")
for row in cursor.fetchall():
    print(f"  {row[0]} ({row[1]}, {row[2]}): {row[3] or 0:,} workers")

cursor.close()
conn.close()

print("\n" + "="*70)
print("INTEGRATION COMPLETE - ALL VIEWS WORKING")
print("="*70)
