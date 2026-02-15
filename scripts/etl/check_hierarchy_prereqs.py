"""Check prerequisites for corporate hierarchy integration."""
import psycopg2
import os

DB_CONFIG = {
    'host': os.environ.get('DB_HOST', 'localhost'),
    'port': int(os.environ.get('DB_PORT', '5432')),
    'database': os.environ.get('DB_NAME', 'olms_multiyear'),
    'user': os.environ.get('DB_USER', 'postgres'),
    'password': os.environ.get('DB_PASSWORD', ''),
}

conn = get_connection()
cur = conn.cursor()

# Check existing schemas
cur.execute("SELECT schema_name FROM information_schema.schemata WHERE schema_name IN ('gleif','bods_staging')")
schemas = [r[0] for r in cur.fetchall()]
print(f"Existing schemas: {schemas}")

# Check existing tables
cur.execute("""
from db_config import get_connection
    SELECT table_schema, table_name
    FROM information_schema.tables
    WHERE table_name IN ('sec_companies','gleif_us_entities','gleif_ownership_links',
                         'corporate_hierarchy','corporate_identifier_crosswalk','corporate_ultimate_parents')
""")
tables = cur.fetchall()
print(f"Existing target tables: {tables}")

# Check data file sizes
pgdump = r'C:\Users\jakew\Downloads\pgdump.sql.gz'
submissions = r'C:\Users\jakew\Downloads\submissions.zip'
if os.path.exists(pgdump):
    print(f"pgdump.sql.gz: {os.path.getsize(pgdump):,} bytes ({os.path.getsize(pgdump)/1024/1024:.0f} MB)")
if os.path.exists(submissions):
    print(f"submissions.zip: {os.path.getsize(submissions):,} bytes ({os.path.getsize(submissions)/1024/1024:.0f} MB)")

# Check Mergent EIN coverage
cur.execute("SELECT COUNT(*) FROM mergent_employers WHERE ein IS NOT NULL AND ein != ''")
print(f"Mergent employers with EIN: {cur.fetchone()[0]}")

# Check F7 columns
cur.execute("""
    SELECT column_name FROM information_schema.columns
    WHERE table_name = 'f7_employers_deduped' AND column_name IN ('sec_cik','sec_ticker','ultimate_parent_name','corporate_family_id')
""")
existing_cols = [r[0] for r in cur.fetchall()]
print(f"F7 hierarchy columns already present: {existing_cols}")

cur.execute("""
    SELECT column_name FROM information_schema.columns
    WHERE table_name = 'mergent_employers' AND column_name IN ('sec_cik','sec_ticker','gleif_lei','ultimate_parent_name','corporate_family_id')
""")
existing_cols = [r[0] for r in cur.fetchall()]
print(f"Mergent hierarchy columns already present: {existing_cols}")

conn.close()
print("Done.")
