"""
OSHA Database - Violation and Integration Analysis
===================================================
"""
import sqlite3

db_path = r"C:\Users\jakew\Downloads\osha_enforcement.db"
conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row
cur = conn.cursor()

# Union status code meanings
print("="*70)
print("UNION STATUS CODE ANALYSIS")
print("="*70)

cur.execute("""
    SELECT union_status, 
           COUNT(*) as cnt,
           AVG(nr_in_estab) as avg_employees,
           COUNT(DISTINCT naics_code) as naics_variety
    FROM inspection
    WHERE union_status IS NOT NULL
    GROUP BY union_status
""")
print(f"{'Code':<6} {'Count':>12} {'Avg Employees':>15} {'NAICS Codes':>12}")
for row in cur.fetchall():
    avg = f"{row[2]:.1f}" if row[2] else "N/A"
    print(f"{row[0]:<6} {row[1]:>12,} {avg:>15} {row[3]:>12,}")

# Violation types
print("\n" + "="*70)
print("VIOLATION TYPE ANALYSIS")
print("="*70)

cur.execute("""
    SELECT viol_type, COUNT(*) as cnt, 
           SUM(current_penalty) as total_penalty,
           AVG(current_penalty) as avg_penalty
    FROM violation
    GROUP BY viol_type
    ORDER BY cnt DESC
""")
print(f"{'Type':<10} {'Count':>12} {'Total Penalty':>18} {'Avg Penalty':>12}")
for row in cur.fetchall():
    vtype = row[0] if row[0] else 'NULL'
    total = f"${row[2]:,.0f}" if row[2] else "$0"
    avg = f"${row[3]:,.0f}" if row[3] else "$0"
    print(f"{vtype:<10} {row[1]:>12,} {total:>18} {avg:>12}")

# Most common NAICS codes
print("\n" + "="*70)
print("TOP 20 NAICS CODES IN OSHA DATA")
print("="*70)

cur.execute("""
    SELECT naics_code, COUNT(*) as cnt,
           COUNT(DISTINCT estab_name) as unique_estabs
    FROM inspection
    WHERE naics_code IS NOT NULL
    GROUP BY naics_code
    ORDER BY cnt DESC
    LIMIT 20
""")
print(f"{'NAICS':<10} {'Inspections':>12} {'Establishments':>15}")
for row in cur.fetchall():
    print(f"{row[0]:<10} {row[1]:>12,} {row[2]:>15,}")

# Geographic coverage
print("\n" + "="*70)
print("TOP 15 STATES BY INSPECTIONS")
print("="*70)

cur.execute("""
    SELECT site_state, COUNT(*) as cnt,
           COUNT(DISTINCT estab_name) as unique_estabs
    FROM inspection
    WHERE site_state IS NOT NULL
    GROUP BY site_state
    ORDER BY cnt DESC
    LIMIT 15
""")
print(f"{'State':<6} {'Inspections':>12} {'Establishments':>15}")
for row in cur.fetchall():
    print(f"{row[0]:<6} {row[1]:>12,} {row[2]:>15,}")

# Check accident/fatality data
print("\n" + "="*70)
print("ACCIDENT/FATALITY ANALYSIS")
print("="*70)

cur.execute("""
    SELECT fatality, COUNT(*) as cnt
    FROM accident
    GROUP BY fatality
""")
print("Fatality flag distribution:")
for row in cur.fetchall():
    print(f"  {row[0]}: {row[1]:,}")

# Severity analysis - serious violations
print("\n" + "="*70)
print("PENALTY DISTRIBUTION (violations with penalties)")
print("="*70)

cur.execute("""
    SELECT 
        CASE 
            WHEN current_penalty = 0 THEN '0 - No penalty'
            WHEN current_penalty < 1000 THEN '1-999'
            WHEN current_penalty < 5000 THEN '1K-5K'
            WHEN current_penalty < 15000 THEN '5K-15K'
            WHEN current_penalty < 50000 THEN '15K-50K'
            WHEN current_penalty < 100000 THEN '50K-100K'
            ELSE '100K+'
        END as penalty_range,
        COUNT(*) as cnt
    FROM violation
    GROUP BY penalty_range
    ORDER BY 
        CASE penalty_range
            WHEN '0 - No penalty' THEN 1
            WHEN '1-999' THEN 2
            WHEN '1K-5K' THEN 3
            WHEN '5K-15K' THEN 4
            WHEN '15K-50K' THEN 5
            WHEN '50K-100K' THEN 6
            ELSE 7
        END
""")
for row in cur.fetchall():
    print(f"  {row[0]:20}: {row[1]:>10,}")

conn.close()
