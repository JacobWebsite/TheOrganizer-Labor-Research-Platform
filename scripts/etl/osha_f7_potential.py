import os
"""
OSHA-F7 Matching Potential Analysis
===================================
Explore how well OSHA data can match to existing F-7 employers
"""
import sqlite3
import psycopg2
from psycopg2.extras import RealDictCursor

# Connect to both databases
osha_conn = sqlite3.connect(r"C:\Users\jakew\Downloads\osha_enforcement.db")
osha_conn.row_factory = sqlite3.Row
osha_cur = osha_conn.cursor()

pg_conn = psycopg2.connect(
    host='localhost',
    dbname='olms_multiyear',
    user='postgres',
    password='os.environ.get('DB_PASSWORD', '')'
)
pg_cur = pg_conn.cursor(cursor_factory=RealDictCursor)

print("="*70)
print("OSHA-F7 MATCHING POTENTIAL ANALYSIS")
print("="*70)

# Get F-7 state distribution
pg_cur.execute("""
    SELECT state, COUNT(*) as cnt, SUM(latest_unit_size) as workers
    FROM f7_employers_deduped
    GROUP BY state
    ORDER BY cnt DESC
    LIMIT 10
""")
print("\nTop 10 F-7 States:")
f7_states = {}
for row in pg_cur.fetchall():
    f7_states[row['state']] = row['cnt']
    workers = row['workers'] or 0
    print(f"  {row['state']}: {row['cnt']:,} employers, {workers:,} workers")

# Get OSHA recent inspections by state (2020+)
osha_cur.execute("""
    SELECT site_state, 
           COUNT(*) as inspections,
           COUNT(DISTINCT estab_name) as establishments
    FROM inspection
    WHERE open_date >= '2020-01-01'
    GROUP BY site_state
    ORDER BY inspections DESC
    LIMIT 10
""")
print("\nTop 10 OSHA States (2020+ inspections):")
for row in osha_cur.fetchall():
    print(f"  {row[0]}: {row[1]:,} inspections, {row[2]:,} establishments")

# Check NAICS overlap
print("\n" + "="*70)
print("NAICS CODE OVERLAP ANALYSIS")
print("="*70)

# Get F-7 NAICS distribution
pg_cur.execute("""
    SELECT LEFT(naics::text, 2) as naics_2, 
           COUNT(*) as cnt,
           SUM(latest_unit_size) as workers
    FROM f7_employers_deduped
    WHERE naics IS NOT NULL
    GROUP BY naics_2
    ORDER BY cnt DESC
""")
print("\nF-7 employers by NAICS 2-digit:")
for row in pg_cur.fetchall():
    workers = row['workers'] or 0
    print(f"  {row['naics_2']}: {row['cnt']:,} employers, {workers:,} workers")

# Get OSHA NAICS distribution (recent)
osha_cur.execute("""
    SELECT substr(CAST(naics_code AS TEXT), 1, 2) as naics_2,
           COUNT(*) as inspections,
           COUNT(DISTINCT estab_name) as establishments
    FROM inspection
    WHERE naics_code > 0 AND open_date >= '2020-01-01'
    GROUP BY naics_2
    ORDER BY inspections DESC
    LIMIT 15
""")
print("\nOSHA inspections by NAICS 2-digit (2020+):")
for row in osha_cur.fetchall():
    print(f"  {row[0]}: {row[1]:,} inspections, {row[2]:,} establishments")

# Sample exact name matches
print("\n" + "="*70)
print("SAMPLE EXACT NAME MATCHING TEST")
print("="*70)

# Get some F-7 employer names
pg_cur.execute("""
    SELECT employer_name, city, state
    FROM f7_employers_deduped
    WHERE employer_name IS NOT NULL
    ORDER BY latest_unit_size DESC NULLS LAST
    LIMIT 100
""")
f7_samples = pg_cur.fetchall()

matches = 0
for emp in f7_samples[:50]:
    osha_cur.execute("""
        SELECT estab_name, site_city, site_state, COUNT(*) as inspections
        FROM inspection
        WHERE UPPER(estab_name) = ?
        GROUP BY estab_name, site_city, site_state
        LIMIT 1
    """, (emp['employer_name'].upper() if emp['employer_name'] else '',))
    result = osha_cur.fetchone()
    if result:
        matches += 1
        if matches <= 5:
            print(f"  MATCH: {emp['employer_name'][:40]} ({emp['state']})")
            print(f"         -> {result[0][:40]} ({result[2]}) - {result[3]} inspections")

print(f"\nExact name matches in top 50 F-7 employers: {matches}/50 ({matches*2}%)")

# Count recent OSHA establishments with violations
print("\n" + "="*70)
print("RECENT VIOLATION SUMMARY (2020+)")
print("="*70)

osha_cur.execute("""
    SELECT COUNT(DISTINCT i.estab_name) as establishments_with_violations,
           COUNT(DISTINCT i.activity_nr) as inspections_with_violations,
           COUNT(*) as total_violations
    FROM violation v
    JOIN inspection i ON v.activity_nr = i.activity_nr
    WHERE v.issuance_date >= '2020-01-01'
""")
row = osha_cur.fetchone()
print(f"  Establishments with violations (2020+): {row[0]:,}")
print(f"  Inspections with violations: {row[1]:,}")
print(f"  Total violations: {row[2]:,}")

# Union vs non-union violations
osha_cur.execute("""
    SELECT i.union_status,
           COUNT(DISTINCT i.estab_name) as establishments,
           COUNT(*) as violations,
           SUM(v.current_penalty) as total_penalties
    FROM violation v
    JOIN inspection i ON v.activity_nr = i.activity_nr
    WHERE v.issuance_date >= '2020-01-01'
    GROUP BY i.union_status
    ORDER BY violations DESC
""")
print("\nViolations by union status (2020+):")
print(f"{'Status':<8} {'Establishments':>15} {'Violations':>12} {'Penalties':>18}")
for row in osha_cur.fetchall():
    status = row[0] if row[0] else 'NULL'
    penalties = f"${row[3]:,.0f}" if row[3] else "$0"
    print(f"{status:<8} {row[1]:>15,} {row[2]:>12,} {penalties:>18}")

osha_conn.close()
pg_conn.close()
