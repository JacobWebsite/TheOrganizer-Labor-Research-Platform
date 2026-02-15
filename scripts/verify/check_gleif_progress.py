"""Check GLEIF restore progress by querying table counts."""
import psycopg2
import os
from db_config import get_connection

DB_CONFIG = {
    'host': os.environ.get('DB_HOST', 'localhost'),
    'port': int(os.environ.get('DB_PORT', '5432')),
    'database': os.environ.get('DB_NAME', 'olms_multiyear'),
    'user': os.environ.get('DB_USER', 'postgres'),
    'password': os.environ.get('DB_PASSWORD', ''),
}

conn = get_connection()
cur = conn.cursor()

# Check if gleif schema exists
cur.execute("SELECT schema_name FROM information_schema.schemata WHERE schema_name = 'gleif'")
schemas = cur.fetchall()
print(f"gleif schema exists: {bool(schemas)}")

if schemas:
    # Check table counts
    tables = ['ooc_statement', 'ooc_interests', 'ooc_annotations', 'person_statement',
              'person_annotations', 'entity_statement', 'entity_identifiers',
              'entity_addresses', 'entity_annotations']
    for table in tables:
        try:
            cur.execute(f"SELECT COUNT(*) FROM gleif.{table}")
            count = cur.fetchone()[0]
            print(f"  gleif.{table}: {count:,}")
        except Exception as e:
            conn.rollback()
            print(f"  gleif.{table}: ERROR (still loading?) - {str(e)[:80]}")

# Check public schema tables
for table in ['gleif_us_entities', 'gleif_ownership_links', 'sec_companies']:
    try:
        cur.execute(f"SELECT COUNT(*) FROM {table}")
        count = cur.fetchone()[0]
        print(f"  {table}: {count:,}")
    except Exception as e:
        conn.rollback()
        print(f"  {table}: not yet created")

# Check active queries
cur.execute("""
    SELECT pid, state, LEFT(query, 100) as query,
           now() - query_start as duration
    FROM pg_stat_activity
    WHERE datname = 'olms_multiyear'
      AND state != 'idle'
      AND pid != pg_backend_pid()
    ORDER BY query_start
""")
active = cur.fetchall()
print(f"\nActive queries: {len(active)}")
for q in active:
    print(f"  PID {q[0]} ({q[1]}): {q[3]} - {q[2]}")

conn.close()
