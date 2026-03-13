"""
Load O*NET 30.2 data from MySQL SQL dump zip into PostgreSQL.

Source: db_30_2_mysql.zip (from https://www.onetcenter.org/database.html)
Format: MySQL SQL dumps with INSERT INTO ... VALUES (...); per row.

Tables loaded:
  Reference:  onet_occupations, onet_content_model, onet_scales
  Data:       onet_skills, onet_knowledge, onet_abilities, onet_work_context,
              onet_work_activities, onet_job_zones, onet_education,
              onet_work_values, onet_tasks, onet_alternate_titles

Usage:
  py scripts/etl/load_onet_data.py --drop-existing
  py scripts/etl/load_onet_data.py --only onet_skills
  py scripts/etl/load_onet_data.py --status
"""

import argparse
import os
import re
import sys
import zipfile
from pathlib import Path

from psycopg2.extras import execute_values

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
from db_config import get_connection

BATCH_SIZE = 5000

# Map: pg_table_name -> (zip_entry, create_sql, insert_sql, column_count)
TABLE_DEFS = {
    # --- Reference tables ---
    'onet_occupations': {
        'file': 'db_30_2_mysql/03_occupation_data.sql',
        'create': """
            CREATE TABLE IF NOT EXISTS onet_occupations (
                onetsoc_code TEXT PRIMARY KEY,
                title TEXT,
                description TEXT
            )
        """,
        'insert': """INSERT INTO onet_occupations (onetsoc_code, title, description) VALUES %s
                     ON CONFLICT (onetsoc_code) DO UPDATE SET title=EXCLUDED.title, description=EXCLUDED.description""",
        'cols': 3,
    },
    'onet_content_model': {
        'file': 'db_30_2_mysql/01_content_model_reference.sql',
        'create': """
            CREATE TABLE IF NOT EXISTS onet_content_model (
                element_id TEXT PRIMARY KEY,
                element_name TEXT,
                description TEXT
            )
        """,
        'insert': """INSERT INTO onet_content_model (element_id, element_name, description) VALUES %s
                     ON CONFLICT (element_id) DO UPDATE SET element_name=EXCLUDED.element_name, description=EXCLUDED.description""",
        'cols': 3,
    },
    'onet_scales': {
        'file': 'db_30_2_mysql/04_scales_reference.sql',
        'create': """
            CREATE TABLE IF NOT EXISTS onet_scales (
                scale_id TEXT PRIMARY KEY,
                scale_name TEXT,
                minimum DOUBLE PRECISION,
                maximum DOUBLE PRECISION
            )
        """,
        'insert': """INSERT INTO onet_scales (scale_id, scale_name, minimum, maximum) VALUES %s
                     ON CONFLICT (scale_id) DO UPDATE SET scale_name=EXCLUDED.scale_name""",
        'cols': 4,
    },
    # --- Data tables (shared schema pattern: onetsoc_code, element_id, scale_id, data_value, ...) ---
    'onet_skills': {
        'file': 'db_30_2_mysql/16_skills.sql',
        'create': """
            CREATE TABLE IF NOT EXISTS onet_skills (
                id BIGSERIAL PRIMARY KEY,
                onetsoc_code TEXT, element_id TEXT, scale_id TEXT,
                data_value DOUBLE PRECISION, n INTEGER,
                standard_error DOUBLE PRECISION, lower_ci_bound DOUBLE PRECISION,
                upper_ci_bound DOUBLE PRECISION, recommend_suppress TEXT,
                not_relevant TEXT, date_updated TEXT, domain_source TEXT
            )
        """,
        'insert': """INSERT INTO onet_skills (onetsoc_code, element_id, scale_id, data_value, n,
                     standard_error, lower_ci_bound, upper_ci_bound, recommend_suppress,
                     not_relevant, date_updated, domain_source) VALUES %s""",
        'cols': 12,
    },
    'onet_knowledge': {
        'file': 'db_30_2_mysql/15_knowledge.sql',
        'create': """
            CREATE TABLE IF NOT EXISTS onet_knowledge (
                id BIGSERIAL PRIMARY KEY,
                onetsoc_code TEXT, element_id TEXT, scale_id TEXT,
                data_value DOUBLE PRECISION, n INTEGER,
                standard_error DOUBLE PRECISION, lower_ci_bound DOUBLE PRECISION,
                upper_ci_bound DOUBLE PRECISION, recommend_suppress TEXT,
                not_relevant TEXT, date_updated TEXT, domain_source TEXT
            )
        """,
        'insert': """INSERT INTO onet_knowledge (onetsoc_code, element_id, scale_id, data_value, n,
                     standard_error, lower_ci_bound, upper_ci_bound, recommend_suppress,
                     not_relevant, date_updated, domain_source) VALUES %s""",
        'cols': 12,
    },
    'onet_abilities': {
        'file': 'db_30_2_mysql/11_abilities.sql',
        'create': """
            CREATE TABLE IF NOT EXISTS onet_abilities (
                id BIGSERIAL PRIMARY KEY,
                onetsoc_code TEXT, element_id TEXT, scale_id TEXT,
                data_value DOUBLE PRECISION, n INTEGER,
                standard_error DOUBLE PRECISION, lower_ci_bound DOUBLE PRECISION,
                upper_ci_bound DOUBLE PRECISION, recommend_suppress TEXT,
                not_relevant TEXT, date_updated TEXT, domain_source TEXT
            )
        """,
        'insert': """INSERT INTO onet_abilities (onetsoc_code, element_id, scale_id, data_value, n,
                     standard_error, lower_ci_bound, upper_ci_bound, recommend_suppress,
                     not_relevant, date_updated, domain_source) VALUES %s""",
        'cols': 12,
    },
    'onet_work_context': {
        'file': 'db_30_2_mysql/20_work_context.sql',
        'create': """
            CREATE TABLE IF NOT EXISTS onet_work_context (
                id BIGSERIAL PRIMARY KEY,
                onetsoc_code TEXT, element_id TEXT, scale_id TEXT,
                category TEXT, data_value DOUBLE PRECISION, n INTEGER,
                standard_error DOUBLE PRECISION, lower_ci_bound DOUBLE PRECISION,
                upper_ci_bound DOUBLE PRECISION, recommend_suppress TEXT,
                not_relevant TEXT, date_updated TEXT, domain_source TEXT
            )
        """,
        'insert': """INSERT INTO onet_work_context (onetsoc_code, element_id, scale_id, category, data_value, n,
                     standard_error, lower_ci_bound, upper_ci_bound, recommend_suppress,
                     not_relevant, date_updated, domain_source) VALUES %s""",
        'cols': 13,
    },
    'onet_work_activities': {
        'file': 'db_30_2_mysql/19_work_activities.sql',
        'create': """
            CREATE TABLE IF NOT EXISTS onet_work_activities (
                id BIGSERIAL PRIMARY KEY,
                onetsoc_code TEXT, element_id TEXT, scale_id TEXT,
                data_value DOUBLE PRECISION, n INTEGER,
                standard_error DOUBLE PRECISION, lower_ci_bound DOUBLE PRECISION,
                upper_ci_bound DOUBLE PRECISION, recommend_suppress TEXT,
                not_relevant TEXT, date_updated TEXT, domain_source TEXT
            )
        """,
        'insert': """INSERT INTO onet_work_activities (onetsoc_code, element_id, scale_id, data_value, n,
                     standard_error, lower_ci_bound, upper_ci_bound, recommend_suppress,
                     not_relevant, date_updated, domain_source) VALUES %s""",
        'cols': 12,
    },
    'onet_job_zones': {
        'file': 'db_30_2_mysql/14_job_zones.sql',
        'create': """
            CREATE TABLE IF NOT EXISTS onet_job_zones (
                id BIGSERIAL PRIMARY KEY,
                onetsoc_code TEXT, job_zone INTEGER,
                date_updated TEXT, domain_source TEXT
            )
        """,
        'insert': """INSERT INTO onet_job_zones (onetsoc_code, job_zone, date_updated, domain_source) VALUES %s""",
        'cols': 4,
    },
    'onet_education': {
        'file': 'db_30_2_mysql/12_education_training_experience.sql',
        'create': """
            CREATE TABLE IF NOT EXISTS onet_education (
                id BIGSERIAL PRIMARY KEY,
                onetsoc_code TEXT, element_id TEXT, scale_id TEXT,
                category TEXT, data_value DOUBLE PRECISION, n INTEGER,
                standard_error DOUBLE PRECISION, lower_ci_bound DOUBLE PRECISION,
                upper_ci_bound DOUBLE PRECISION, recommend_suppress TEXT,
                date_updated TEXT, domain_source TEXT
            )
        """,
        'insert': """INSERT INTO onet_education (onetsoc_code, element_id, scale_id, category, data_value, n,
                     standard_error, lower_ci_bound, upper_ci_bound, recommend_suppress,
                     date_updated, domain_source) VALUES %s""",
        'cols': 12,
    },
    'onet_work_values': {
        'file': 'db_30_2_mysql/22_work_values.sql',
        'create': """
            CREATE TABLE IF NOT EXISTS onet_work_values (
                id BIGSERIAL PRIMARY KEY,
                onetsoc_code TEXT, element_id TEXT, scale_id TEXT,
                data_value DOUBLE PRECISION, date_updated TEXT,
                domain_source TEXT
            )
        """,
        'insert': """INSERT INTO onet_work_values (onetsoc_code, element_id, scale_id, data_value,
                     date_updated, domain_source) VALUES %s""",
        'cols': 6,
    },
    'onet_tasks': {
        'file': 'db_30_2_mysql/17_task_statements.sql',
        'create': """
            CREATE TABLE IF NOT EXISTS onet_tasks (
                id BIGSERIAL PRIMARY KEY,
                onetsoc_code TEXT, task_id TEXT, task TEXT,
                task_type TEXT, incumbents_responding INTEGER,
                date_updated TEXT, domain_source TEXT
            )
        """,
        'insert': """INSERT INTO onet_tasks (onetsoc_code, task_id, task, task_type,
                     incumbents_responding, date_updated, domain_source) VALUES %s""",
        'cols': 7,
    },
    'onet_alternate_titles': {
        'file': 'db_30_2_mysql/29_alternate_titles.sql',
        'create': """
            CREATE TABLE IF NOT EXISTS onet_alternate_titles (
                id BIGSERIAL PRIMARY KEY,
                onetsoc_code TEXT, alternate_title TEXT,
                short_title TEXT, sources TEXT
            )
        """,
        'insert': """INSERT INTO onet_alternate_titles (onetsoc_code, alternate_title, short_title, sources) VALUES %s""",
        'cols': 4,
    },
}


def parse_mysql_value(val_str):
    """Parse a single MySQL value from an INSERT statement."""
    val_str = val_str.strip()
    if val_str.upper() == 'NULL':
        return None
    if val_str.startswith("'") and val_str.endswith("'"):
        # Unescape MySQL string
        inner = val_str[1:-1]
        inner = inner.replace("\\'", "'")
        inner = inner.replace('\\"', '"')
        inner = inner.replace("\\\\", "\\")
        inner = inner.replace("\\n", "\n")
        inner = inner.replace("\\r", "\r")
        return inner
    # Numeric
    try:
        if '.' in val_str:
            return float(val_str)
        return int(val_str)
    except ValueError:
        return val_str


def parse_insert_values(line):
    """Extract tuple of values from a MySQL INSERT INTO ... VALUES (...) line.

    Handles quoted strings with commas and escaped quotes inside them.
    """
    # Find the VALUES keyword, then extract the content between the LAST matching parens
    idx = line.upper().find(' VALUES ')
    if idx < 0:
        idx = line.upper().find(' VALUES(')
    if idx < 0:
        return None

    # Find opening paren after VALUES
    rest = line[idx + 7:].lstrip()
    if not rest.startswith('('):
        return None

    # Extract content between ( and last );
    paren_start = rest.index('(')
    # Find the matching close paren (handle nested quotes)
    content = rest[paren_start + 1:]
    # Strip trailing );
    if content.rstrip().endswith(');'):
        content = content.rstrip()[:-2]
    elif content.rstrip().endswith(')'):
        content = content.rstrip()[:-1]
    values_str = content

    # Parse values handling quoted strings
    values = []
    current = []
    in_quote = False
    i = 0
    while i < len(values_str):
        ch = values_str[i]
        if ch == '\\' and in_quote and i + 1 < len(values_str):
            current.append(ch)
            current.append(values_str[i + 1])
            i += 2
            continue
        if ch == "'" and not in_quote:
            in_quote = True
            current.append(ch)
        elif ch == "'" and in_quote:
            # Check for '' (MySQL double-quote escape)
            if i + 1 < len(values_str) and values_str[i + 1] == "'":
                current.append("\\'")
                i += 2
                continue
            in_quote = False
            current.append(ch)
        elif ch == ',' and not in_quote:
            values.append(parse_mysql_value(''.join(current)))
            current = []
        else:
            current.append(ch)
        i += 1
    if current:
        values.append(parse_mysql_value(''.join(current)))

    return tuple(values)


def iter_inserts_from_zip(zip_path, entry_name):
    """Yield parsed value tuples from INSERT statements in a zip entry."""
    with zipfile.ZipFile(zip_path, 'r') as zf:
        with zf.open(entry_name) as f:
            for raw_line in f:
                line = raw_line.decode('utf-8', errors='replace').rstrip()
                if not line.startswith('INSERT INTO'):
                    continue
                vals = parse_insert_values(line)
                if vals is not None:
                    yield vals


def load_table(conn, table_name, table_def, zip_path, drop_existing=False):
    """Load a single O*NET table from the zip."""
    entry = table_def['file']
    print(f"  Loading {table_name} from {entry}...")

    with conn.cursor() as cur:
        if drop_existing:
            cur.execute(f"DROP TABLE IF EXISTS {table_name} CASCADE")

        cur.execute(table_def['create'])

        # Truncate if table already exists (idempotent re-run)
        cur.execute(f"TRUNCATE TABLE {table_name}")

        # Parse and batch-insert
        batch = []
        inserted = 0
        expected_cols = table_def['cols']

        for vals in iter_inserts_from_zip(zip_path, entry):
            # Pad or trim to expected column count
            if len(vals) < expected_cols:
                vals = vals + (None,) * (expected_cols - len(vals))
            elif len(vals) > expected_cols:
                vals = vals[:expected_cols]

            batch.append(vals)
            if len(batch) >= BATCH_SIZE:
                execute_values(cur, table_def['insert'], batch, page_size=BATCH_SIZE)
                inserted += len(batch)
                batch = []

        if batch:
            execute_values(cur, table_def['insert'], batch, page_size=BATCH_SIZE)
            inserted += len(batch)

        # Create index on onetsoc_code (skip for reference tables without it)
        if table_name not in ('onet_content_model', 'onet_scales'):
            idx_name = f"idx_{table_name}_soc"
            cur.execute(f"DROP INDEX IF EXISTS {idx_name}")
            cur.execute(f"CREATE INDEX {idx_name} ON {table_name} (onetsoc_code)")

    conn.commit()
    print(f"    -> {inserted:,} rows")
    return inserted


def show_status(conn):
    """Show row counts for all O*NET tables."""
    print("O*NET table status:")
    with conn.cursor() as cur:
        for name in TABLE_DEFS:
            cur.execute(f"""
                SELECT EXISTS(
                    SELECT 1 FROM information_schema.tables
                    WHERE table_name = '{name}'
                ) AS e
            """)
            exists = cur.fetchone()[0]
            if exists:
                cur.execute(f"SELECT COUNT(*) FROM {name}")
                cnt = cur.fetchone()[0]
                print(f"  {name:30s} {cnt:>10,} rows")
            else:
                print(f"  {name:30s}  (not created)")


def main():
    parser = argparse.ArgumentParser(description='Load O*NET 30.2 data from MySQL dump zip')
    parser.add_argument('--drop-existing', action='store_true',
                        help='Drop and recreate target tables before load')
    parser.add_argument('--only', type=str, default=None,
                        help='Load only this table (e.g., onet_skills)')
    parser.add_argument('--status', action='store_true',
                        help='Show current row counts and exit')
    parser.add_argument('--zip', type=str, default=None,
                        help='Path to zip file (default: db_30_2_mysql.zip in project root)')
    args = parser.parse_args()

    conn = get_connection()
    conn.autocommit = False

    if args.status:
        show_status(conn)
        conn.close()
        return

    # Find zip file
    zip_path = args.zip or 'db_30_2_mysql.zip'
    if not Path(zip_path).exists():
        print(f"Zip file not found: {zip_path}")
        print("Download from https://www.onetcenter.org/database.html")
        conn.close()
        return

    tables_to_load = TABLE_DEFS
    if args.only:
        if args.only not in TABLE_DEFS:
            print(f"Unknown table: {args.only}")
            print(f"Available: {', '.join(TABLE_DEFS)}")
            conn.close()
            return
        tables_to_load = {args.only: TABLE_DEFS[args.only]}

    print(f"Loading O*NET data from {zip_path}")
    print(f"Tables: {len(tables_to_load)}")
    print()

    total = 0
    try:
        for name, defn in tables_to_load.items():
            cnt = load_table(conn, name, defn, zip_path, drop_existing=args.drop_existing)
            total += cnt
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    print()
    print(f"Done. Total rows loaded: {total:,}")


if __name__ == '__main__':
    main()
