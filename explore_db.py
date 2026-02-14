
import sys
from pathlib import Path
import argparse

# Add project root to path to allow importing db_config
project_root = Path(__file__).resolve().parent
sys.path.insert(0, str(project_root))

from db_config import get_connection

def list_tables(password: str):
    """Lists the tables in the public schema."""
    try:
        from db_config import DB_CONFIG
        DB_CONFIG['password'] = password
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("""
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'public'
            ORDER BY table_name;
        """)
        tables = [row[0] for row in cur.fetchall()]
        for table in tables:
            print(table)
        cur.close()
        conn.close()
    except Exception as e:
        print(f"Error: {e}")

def list_schemas(password: str):
    """Lists the schemas in the database."""
    try:
        from db_config import DB_CONFIG
        DB_CONFIG['password'] = password
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("""
            SELECT schema_name
            FROM information_schema.schemata
            ORDER BY schema_name;
        """)
        schemas = [row[0] for row in cur.fetchall()]
        for schema in schemas:
            print(schema)
        cur.close()
        conn.close()
    except Exception as e:
        print(f"Error: {e}")

def list_views(password: str):
    """Lists the views in the public schema."""
    try:
        from db_config import DB_CONFIG
        DB_CONFIG['password'] = password
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("""
            SELECT table_name
            FROM information_schema.views
            WHERE table_schema = 'public'
            ORDER BY table_name;
        """)
        views = [row[0] for row in cur.fetchall()]
        for view in views:
            print(view)
        cur.close()
        conn.close()
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Explore the database.')
    parser.add_argument('--password', type=str, required=True, help='Database password')
    parser.add_argument('--action', type=str, required=True, choices=['list_tables', 'list_schemas', 'list_views'], help='Action to perform')
    args = parser.parse_args()

    if args.action == 'list_tables':
        list_tables(args.password)
    elif args.action == 'list_schemas':
        list_schemas(args.password)
    elif args.action == 'list_views':
        list_views(args.password)
