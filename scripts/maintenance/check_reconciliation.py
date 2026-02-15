import os
import psycopg2
from db_config import get_connection
conn = get_connection()
cur = conn.cursor()

# Check for sector-related tables/views
print("=== Sector-related objects ===")
cur.execute("""
    SELECT table_name FROM information_schema.tables 
    WHERE table_schema = 'public' 
    AND (table_name ILIKE '%sector%' OR table_name ILIKE '%private%' OR table_name ILIKE '%public%')
    ORDER BY table_name;
""")
for r in cur.fetchall():
    print(f"  {r[0]}")

# Check if there's already a cleaned private sector view
print("\n=== F-7 reconciled views ===")
cur.execute("""
    SELECT table_name FROM information_schema.views 
    WHERE table_schema = 'public' 
    AND table_name ILIKE '%f7%reconcil%'
    ORDER BY table_name;
""")
for r in cur.fetchall():
    print(f"  {r[0]}")

# Check v_f7_reconciled_private_sector
print("\n=== v_f7_reconciled_private_sector ===")
cur.execute("""
    SELECT column_name FROM information_schema.columns 
    WHERE table_name = 'v_f7_reconciled_private_sector'
    ORDER BY ordinal_position;
""")
cols = [r[0] for r in cur.fetchall()]
print(f"Columns: {cols}")

if cols:
    cur.execute("SELECT COUNT(*), SUM(workers_covered) FROM v_f7_reconciled_private_sector;")
    row = cur.fetchone()
    print(f"Records: {row[0]:,}, Workers: {row[1] or 0:,}")
    
    # Sample
    cur.execute("""
        SELECT employer_name, workers_covered, aff_abbr 
        FROM v_f7_reconciled_private_sector 
        ORDER BY workers_covered DESC NULLS LAST
        LIMIT 10;
    """)
    print("\nTop 10 in reconciled view:")
    for r in cur.fetchall():
        print(f"  {r[0][:45]:<45} {r[1] or 0:>10,} {r[2]}")

# Compare to v_employer_search
print("\n=== Contamination check ===")
cur.execute("""
    SELECT employer_name, bargaining_unit_size, affiliation
    FROM v_employer_search
    WHERE employer_name ILIKE '%postal%' 
       OR employer_name ILIKE '%veterans affairs%'
       OR employer_name ILIKE '%department of%'
    ORDER BY bargaining_unit_size DESC
    LIMIT 10;
""")
print("Federal employers in v_employer_search (contamination):")
for r in cur.fetchall():
    print(f"  {r[0][:45]:<45} {r[1] or 0:>10,} {r[2]}")

conn.close()
