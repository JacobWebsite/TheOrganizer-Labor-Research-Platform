import os
import psycopg2

from db_config import get_connection
conn = get_connection()
cur = conn.cursor()

# Get table columns
cur.execute("""
    SELECT column_name 
    FROM information_schema.columns 
    WHERE table_name = 'f7_employers_deduped' 
    ORDER BY ordinal_position
""")
print("F7_EMPLOYERS_DEDUPED COLUMNS:")
print([r[0] for r in cur.fetchall()])

# Check current match status
cur.execute("""
    SELECT COUNT(*) as total_employers
    FROM f7_employers_deduped
""")
print(f"\nTotal employers: {cur.fetchone()[0]}")

# Check for any NLRB-related columns
cur.execute("""
    SELECT column_name 
    FROM information_schema.columns 
    WHERE table_name = 'f7_employers_deduped' 
    AND column_name LIKE '%nlrb%' OR column_name LIKE '%match%' OR column_name LIKE '%file%'
""")
print("\nMatching-related columns:")
print([r[0] for r in cur.fetchall()])

conn.close()
