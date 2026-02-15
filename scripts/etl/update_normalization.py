"""
Update name_normalized columns in GLEIF and SEC tables using cleanco.
Run after installing cleanco to improve crosswalk matching.
"""
import psycopg2
import re
import time

from cleanco import basename as cleanco_basename
import os

from db_config import get_connection
DB_CONFIG = {
    'host': os.environ.get('DB_HOST', 'localhost'),
    'port': int(os.environ.get('DB_PORT', '5432')),
    'database': os.environ.get('DB_NAME', 'olms_multiyear'),
    'user': os.environ.get('DB_USER', 'postgres'),
    'password': os.environ.get('DB_PASSWORD', ''),
}

LEGAL_SUFFIX_RE = re.compile(
    r'\b(inc|incorporated|corp|corporation|llc|llp|ltd|limited|co|company|pc|pa|pllc|plc|lp)\b\.?',
    re.IGNORECASE
)
DBA_RE = re.compile(r'\bd/?b/?a\b\.?', re.IGNORECASE)
NON_ALNUM_RE = re.compile(r'[^\w\s]')
MULTI_SPACE_RE = re.compile(r'\s+')


def normalize_with_cleanco(name):
    """Apply cleanco + standard normalization."""
    if not name:
        return ''
    cleaned = cleanco_basename(name)
    result = cleaned.lower().strip()
    result = LEGAL_SUFFIX_RE.sub('', result)
    result = DBA_RE.sub('', result)
    result = NON_ALNUM_RE.sub(' ', result)
    result = MULTI_SPACE_RE.sub(' ', result).strip()
    return result


def update_table(conn, table, id_col, name_col, norm_col):
    """Update normalized names for a table."""
    cur = conn.cursor()
    cur.execute(f'SELECT {id_col}, {name_col} FROM {table} WHERE {name_col} IS NOT NULL')
    rows = cur.fetchall()
    total = len(rows)
    print(f'  Processing {total:,} rows...')

    start = time.time()
    batch = [(normalize_with_cleanco(name), row_id) for row_id, name in rows]

    batch_size = 5000
    updated = 0
    for i in range(0, len(batch), batch_size):
        chunk = batch[i:i + batch_size]
        cur.executemany(f'UPDATE {table} SET {norm_col} = %s WHERE {id_col} = %s', chunk)
        conn.commit()
        updated += len(chunk)
        if updated % 50000 < batch_size:
            elapsed = time.time() - start
            rate = updated / elapsed if elapsed > 0 else 0
            print(f'    {updated:,}/{total:,} ({rate:.0f}/s)')

    elapsed = time.time() - start
    print(f'  Updated {updated:,} rows in {elapsed:.1f}s')


def main():
    conn = get_connection()
    conn.autocommit = False

    print('=== Updating GLEIF name_normalized with cleanco ===')
    update_table(conn, 'gleif_us_entities', 'id', 'entity_name', 'name_normalized')

    print('\n=== Updating SEC name_normalized with cleanco ===')
    update_table(conn, 'sec_companies', 'id', 'company_name', 'name_normalized')

    # Sample changes
    cur = conn.cursor()
    print('\n=== Sample GLEIF changes (international suffixes) ===')
    cur.execute("""
        SELECT entity_name, name_normalized FROM gleif_us_entities
        WHERE entity_name ~* '(GmbH|S\\.A\\.|AG$| AB$| NV$| BV$)'
        LIMIT 10
    """)
    for row in cur.fetchall():
        print(f'  {row[0]} -> {row[1]}')

    conn.close()
    print('\nDone!')


if __name__ == '__main__':
    main()
