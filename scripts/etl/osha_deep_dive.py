"""
OSHA Database Deep Dive - Inspection Table
==========================================
"""
import sqlite3
from datetime import datetime

db_path = r"C:\Users\jakew\Downloads\osha_enforcement.db"
conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row
cur = conn.cursor()

print("="*70)
print("INSPECTION TABLE - FULL COLUMN ANALYSIS")
print("="*70)

# Get all columns from inspection table
cur.execute("PRAGMA table_info(inspection)")
cols = cur.fetchall()
print(f"\nAll {len(cols)} columns:")
for c in cols:
    print(f"  {c[1]:25} ({c[2]})")

# Get sample row
print("\n" + "="*70)
print("SAMPLE INSPECTION RECORD")
print("="*70)
cur.execute("SELECT * FROM inspection LIMIT 1")
row = cur.fetchone()
for i, col in enumerate(cols):
    val = row[i]
    if val is not None:
        print(f"  {col[1]:25}: {str(val)[:60]}")

# Find most recent inspection
print("\n" + "="*70)
print("DATE RANGE ANALYSIS")
print("="*70)

cur.execute("""
    SELECT 
        MIN(open_date) as earliest,
        MAX(open_date) as latest,
        COUNT(*) as total,
        COUNT(DISTINCT estab_name) as unique_establishments
    FROM inspection
    WHERE open_date IS NOT NULL
""")
dates = cur.fetchone()
print(f"  Earliest inspection: {dates[0]}")
print(f"  Latest inspection: {dates[1]}")
print(f"  Total inspections: {dates[2]:,}")
print(f"  Unique establishments: {dates[3]:,}")

# Check union status column
print("\n" + "="*70)
print("UNION STATUS ANALYSIS")
print("="*70)

cur.execute("""
    SELECT union_status, COUNT(*) as cnt
    FROM inspection
    GROUP BY union_status
    ORDER BY cnt DESC
""")
print("\nUnion status distribution:")
for row in cur.fetchall():
    status = row[0] if row[0] else 'NULL'
    print(f"  {status:20}: {row[1]:>10,}")

# Check violations per year
print("\n" + "="*70)
print("VIOLATIONS BY YEAR (recent)")
print("="*70)

cur.execute("""
    SELECT 
        substr(issuance_date, 1, 4) as year,
        COUNT(*) as violations,
        SUM(current_penalty) as total_penalties
    FROM violation
    WHERE issuance_date IS NOT NULL
    GROUP BY year
    ORDER BY year DESC
    LIMIT 15
""")
print(f"{'Year':<6} {'Violations':>12} {'Total Penalties':>18}")
for row in cur.fetchall():
    penalties = f"${row[2]:,.0f}" if row[2] else "$0"
    print(f"{row[0]:<6} {row[1]:>12,} {penalties:>18}")

conn.close()
