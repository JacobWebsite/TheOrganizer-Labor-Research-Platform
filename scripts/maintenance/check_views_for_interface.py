"""
Check existing views and tables for the unified interface
"""
import psycopg2
import os

DB_CONFIG = {
    'host': os.environ.get('DB_HOST', 'localhost'),
    'port': int(os.environ.get('DB_PORT', '5432')),
    'database': os.environ.get('DB_NAME', 'olms_multiyear'),
    'user': os.environ.get('DB_USER', 'postgres'),
    'password': os.environ.get('DB_PASSWORD', ''),
}

conn = psycopg2.connect(**DB_CONFIG)
cursor = conn.cursor()

print("=" * 70)
print("EXISTING VIEWS AND TABLES")
print("=" * 70)

# List all views
print("\n--- Views ---")
cursor.execute("""
    SELECT table_name 
    FROM information_schema.views 
    WHERE table_schema = 'public'
    ORDER BY table_name
""")
for row in cursor.fetchall():
    print(f"  {row[0]}")

# List key tables
print("\n--- Key Tables ---")
cursor.execute("""
    SELECT table_name 
    FROM information_schema.tables 
    WHERE table_schema = 'public' AND table_type = 'BASE TABLE'
    ORDER BY table_name
""")
for row in cursor.fetchall():
    print(f"  {row[0]}")

# Check what columns are in unions_master
print("\n--- unions_master columns ---")
cursor.execute("""
    SELECT column_name, data_type
    FROM information_schema.columns
    WHERE table_name = 'unions_master'
    ORDER BY ordinal_position
""")
for row in cursor.fetchall():
    print(f"  {row[0]}: {row[1]}")

# Check nlrb_union_xref
print("\n--- nlrb_union_xref columns ---")
cursor.execute("""
    SELECT column_name, data_type
    FROM information_schema.columns
    WHERE table_name = 'nlrb_union_xref'
    ORDER BY ordinal_position
""")
for row in cursor.fetchall():
    print(f"  {row[0]}: {row[1]}")

# Sample query: Find union with NLRB data
print("\n--- Sample: SEIU with NLRB matches ---")
cursor.execute("""
    SELECT 
        um.f_num,
        um.union_name,
        um.aff_abbr,
        um.members,
        COUNT(DISTINCT x.nlrb_union_name) as nlrb_name_variants,
        COUNT(DISTINCT c.case_number) as nlrb_cases
    FROM unions_master um
    LEFT JOIN nlrb_union_xref x ON um.f_num = x.olms_f_num
    LEFT JOIN nlrb_participants p ON x.nlrb_union_name = p.participant_name AND p.subtype = 'Union'
    LEFT JOIN nlrb_cases c ON p.case_number = c.case_number
    WHERE um.aff_abbr = 'SEIU'
    GROUP BY um.f_num, um.union_name, um.aff_abbr, um.members
    ORDER BY um.members DESC NULLS LAST
    LIMIT 10
""")
print(f"\n{'f_num':<10} {'Name':<40} {'Members':>10} {'NLRB Cases':>12}")
print("-" * 75)
for row in cursor.fetchall():
    print(f"{row[0]:<10} {row[1][:38]:<40} {row[3] or 0:>10,} {row[5]:>12,}")

conn.close()
