"""
Database initialization and verification script.

Usage:
    py scripts/setup/init_database.py              # Verify existing database
    py scripts/setup/init_database.py --create      # Create database from scratch
    py scripts/setup/init_database.py --schema-only # Apply schema files only
    py scripts/setup/init_database.py --restore backup.dump  # Restore from backup

Requires: PostgreSQL 17+, pg_trgm extension, DB credentials in .env
"""
import os
import sys
import subprocess
import argparse

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
from db_config import DB_CONFIG, get_connection

PROJECT_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..')
SCHEMA_DIR = os.path.join(PROJECT_ROOT, 'sql', 'schema')

# Schema files in dependency order
SCHEMA_FILES = [
    'f7_schema.sql',
    'f7_crosswalk_schema.sql',
    'nlrb_schema_phase1.sql',
    'vr_schema.sql',
    'bls_phase1_schema.sql',
    'schema_v4_employer_search.sql',
    'unionstats_schema.sql',
    'afscme_ny_schema.sql',
]

# Core tables expected after full setup
EXPECTED_TABLES = {
    'unions_master': 25000,       # ~26,665
    'lm_data': 300000,            # 331K loaded (2024); full 2010-2024 = ~2.6M
    'f7_employers_deduped': 55000, # ~60,953
    'f7_union_employer_relations': 100000, # ~150,386
    'nlrb_elections': 30000,      # ~33,096
    'nlrb_participants': 1000000, # ~1.9M
    'osha_establishments': 900000, # ~1M
    'osha_violations_detail': 2000000, # ~2.2M
    'whd_cases': 300000,          # ~363K
    'gleif_us_entities': 300000,  # ~379K
    'gleif_ownership_links': 400000, # ~499K
    'sec_companies': 400000,      # ~517K
    'federal_contract_recipients': 40000, # ~47K
    'qcew_annual': 1500000,       # ~1.9M
    'corporate_identifier_crosswalk': 10000, # ~14,561
    'corporate_hierarchy': 100000, # ~125K
    'mergent_employers': 50000,   # ~56K
    'national_990_filers': 500000, # ~587K
}

REQUIRED_EXTENSIONS = ['pg_trgm']


def check_connection():
    """Verify database connection."""
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("SELECT version()")
        version = cur.fetchone()[0]
        conn.close()
        print(f"  Connected to: {DB_CONFIG['host']}:{DB_CONFIG['port']}/{DB_CONFIG['database']}")
        print(f"  PostgreSQL: {version.split(',')[0]}")
        return True
    except Exception as e:
        print(f"  FAILED: {e}")
        return False


def check_extensions():
    """Verify required PostgreSQL extensions."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT extname FROM pg_extension")
    installed = {row[0] for row in cur.fetchall()}
    conn.close()

    all_ok = True
    for ext in REQUIRED_EXTENSIONS:
        if ext in installed:
            print(f"  {ext}: installed")
        else:
            print(f"  {ext}: MISSING")
            all_ok = False
    return all_ok


def enable_extensions():
    """Enable required extensions."""
    conn = get_connection()
    conn.autocommit = True
    cur = conn.cursor()
    for ext in REQUIRED_EXTENSIONS:
        try:
            cur.execute(f"CREATE EXTENSION IF NOT EXISTS {ext}")
            print(f"  Enabled: {ext}")
        except Exception as e:
            print(f"  Failed to enable {ext}: {e}")
    conn.close()


def check_tables():
    """Verify core tables exist and have expected row counts."""
    conn = get_connection()
    cur = conn.cursor()

    # Get all tables
    cur.execute("""
        SELECT tablename FROM pg_tables
        WHERE schemaname = 'public'
        ORDER BY tablename
    """)
    existing = {row[0] for row in cur.fetchall()}
    print(f"  Total tables in database: {len(existing)}")

    results = {}
    missing = []
    low_count = []

    for table, min_rows in EXPECTED_TABLES.items():
        if table not in existing:
            missing.append(table)
            results[table] = ('MISSING', 0, min_rows)
            continue

        cur.execute(f"SELECT COUNT(*) FROM {table}")
        count = cur.fetchone()[0]

        if count < min_rows:
            low_count.append((table, count, min_rows))
            results[table] = ('LOW', count, min_rows)
        else:
            results[table] = ('OK', count, min_rows)

    conn.close()

    # Print results
    for table in sorted(results.keys()):
        status, count, expected = results[table]
        if status == 'OK':
            print(f"  {table}: {count:,} rows (OK)")
        elif status == 'LOW':
            print(f"  {table}: {count:,} rows (expected >= {expected:,}) WARNING")
        else:
            print(f"  {table}: MISSING")

    if missing:
        print(f"\n  {len(missing)} missing tables: {', '.join(missing)}")
    if low_count:
        print(f"  {len(low_count)} tables with low row counts")

    return len(missing) == 0 and len(low_count) == 0


def check_materialized_views():
    """Check materialized views exist and are populated."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT matviewname FROM pg_matviews
        WHERE schemaname = 'public'
        ORDER BY matviewname
    """)
    views = [row[0] for row in cur.fetchall()]
    print(f"  Materialized views: {len(views)}")

    for view in views:
        try:
            cur.execute(f"SELECT COUNT(*) FROM {view}")
            count = cur.fetchone()[0]
            status = "OK" if count > 0 else "EMPTY"
            print(f"    {view}: {count:,} rows ({status})")
        except Exception as e:
            print(f"    {view}: ERROR ({e})")

    conn.close()
    return len(views) > 0


def apply_schema(files=None):
    """Apply schema SQL files."""
    files = files or SCHEMA_FILES
    conn = get_connection()
    conn.autocommit = True
    cur = conn.cursor()

    for fname in files:
        fpath = os.path.join(SCHEMA_DIR, fname)
        if not os.path.exists(fpath):
            print(f"  SKIP (not found): {fname}")
            continue
        try:
            with open(fpath, 'r') as f:
                sql = f.read()
            cur.execute(sql)
            print(f"  Applied: {fname}")
        except Exception as e:
            print(f"  FAILED: {fname} - {e}")

    conn.close()


def restore_backup(dump_path):
    """Restore database from pg_dump custom format backup."""
    if not os.path.exists(dump_path):
        print(f"  Backup file not found: {dump_path}")
        return False

    size_mb = os.path.getsize(dump_path) / (1024 * 1024)
    print(f"  Restoring from: {dump_path} ({size_mb:.0f} MB)")

    env = os.environ.copy()
    env['PGPASSWORD'] = DB_CONFIG['password']

    cmd = [
        'pg_restore',
        '-U', DB_CONFIG['user'],
        '-h', DB_CONFIG['host'],
        '-p', str(DB_CONFIG['port']),
        '-d', DB_CONFIG['database'],
        '--no-owner',
        '--no-privileges',
        '--verbose',
        dump_path
    ]

    result = subprocess.run(cmd, env=env, capture_output=True, text=True)
    if result.returncode == 0:
        print("  Restore completed successfully")
        return True
    else:
        # pg_restore returns non-zero even on warnings
        if 'ERROR' in result.stderr:
            print(f"  Restore completed with errors:\n{result.stderr[:500]}")
        else:
            print("  Restore completed (with warnings)")
        return True


def main():
    parser = argparse.ArgumentParser(description="Database initialization and verification")
    parser.add_argument('--create', action='store_true', help='Create database and apply schema')
    parser.add_argument('--schema-only', action='store_true', help='Apply schema files only')
    parser.add_argument('--restore', type=str, help='Restore from backup .dump file')
    args = parser.parse_args()

    print("=" * 60)
    print("Labor Research Platform - Database Setup")
    print("=" * 60)

    if args.restore:
        print("\n[1/3] Checking connection...")
        if not check_connection():
            sys.exit(1)
        print("\n[2/3] Enabling extensions...")
        enable_extensions()
        print("\n[3/3] Restoring from backup...")
        restore_backup(args.restore)
        return

    if args.schema_only:
        print("\n[1/2] Checking connection...")
        if not check_connection():
            sys.exit(1)
        print("\n[2/2] Applying schema files...")
        apply_schema()
        return

    # Default: verify existing database
    print("\n[1/4] Checking connection...")
    conn_ok = check_connection()
    if not conn_ok:
        print("\nCannot connect to database. Check .env credentials.")
        sys.exit(1)

    print("\n[2/4] Checking extensions...")
    ext_ok = check_extensions()
    if not ext_ok:
        print("  Attempting to enable missing extensions...")
        enable_extensions()

    print("\n[3/4] Checking core tables...")
    tables_ok = check_tables()

    print("\n[4/4] Checking materialized views...")
    views_ok = check_materialized_views()

    print("\n" + "=" * 60)
    if conn_ok and tables_ok and views_ok:
        print("RESULT: All checks PASSED")
    else:
        issues = []
        if not conn_ok:
            issues.append("connection failed")
        if not tables_ok:
            issues.append("missing/empty tables")
        if not views_ok:
            issues.append("missing materialized views")
        print(f"RESULT: Issues found: {', '.join(issues)}")
        print("\nTo restore from backup:")
        print("  py scripts/setup/init_database.py --restore backup_20260209.dump")
    print("=" * 60)


if __name__ == '__main__':
    main()
