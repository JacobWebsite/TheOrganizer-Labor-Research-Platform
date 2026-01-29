"""
OSHA Database Exploration
=========================
Examine structure and identify integration opportunities
"""
import sqlite3
import os
from datetime import datetime

db_path = r"C:\Users\jakew\Downloads\osha_enforcement.db"

# Check file exists and size
if os.path.exists(db_path):
    size_mb = os.path.getsize(db_path) / (1024*1024)
    print(f"Database found: {size_mb:.1f} MB")
else:
    print("Database not found!")
    exit()

conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row
cur = conn.cursor()

# Get all tables
cur.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
tables = [r[0] for r in cur.fetchall()]

print(f"\n{'='*70}")
print(f"OSHA DATABASE STRUCTURE")
print(f"{'='*70}")
print(f"\nTables found: {len(tables)}")

for table in tables:
    cur.execute(f"SELECT COUNT(*) FROM [{table}]")
    count = cur.fetchone()[0]
    print(f"\n  {table}: {count:,} rows")
    
    # Get columns
    cur.execute(f"PRAGMA table_info([{table}])")
    cols = cur.fetchall()
    col_names = [c[1] for c in cols]
    print(f"    Columns: {col_names[:15]}")
    if len(col_names) > 15:
        print(f"    ... and {len(col_names)-15} more columns")

conn.close()
