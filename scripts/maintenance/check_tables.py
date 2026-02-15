import os
import psycopg2
from db_config import get_connection
conn = get_connection()
cur = conn.cursor()

# List all tables
cur.execute("""
    SELECT table_name 
    FROM information_schema.tables 
    WHERE table_schema = 'public' 
    ORDER BY table_name;
""")
print('Tables in olms_multiyear:')
for row in cur.fetchall():
    print(f'  {row[0]}')

# Check for anything with 'employer' in the name
cur.execute("""
    SELECT table_name 
    FROM information_schema.tables 
    WHERE table_schema = 'public' 
    AND table_name ILIKE '%employer%';
""")
emp_tables = cur.fetchall()
print(f'\nTables with "employer" in name: {[r[0] for r in emp_tables]}')

# Check for F-7 related tables
cur.execute("""
    SELECT table_name 
    FROM information_schema.tables 
    WHERE table_schema = 'public' 
    AND (table_name ILIKE '%f7%' OR table_name ILIKE '%f_7%');
""")
f7_tables = cur.fetchall()
print(f'F-7 related tables: {[r[0] for r in f7_tables]}')

conn.close()
