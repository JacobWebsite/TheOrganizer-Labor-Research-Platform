"""
Phase 1: Load GLEIF/Open Ownership BODS data into PostgreSQL.

Steps:
1. Restore pgdump.sql.gz -> creates 'gleif' schema with 9 tables (~52.7M rows)
2. Add indexes on gleif tables for efficient querying
3. Extract US entities into gleif_us_entities (public schema)
4. Extract US ownership links into gleif_ownership_links (public schema)
5. Print summary stats

Usage:
    py scripts/etl/load_gleif_bods.py
    py scripts/etl/load_gleif_bods.py --skip-restore    # if gleif schema already loaded
    py scripts/etl/load_gleif_bods.py --extract-only     # only do US extraction
"""

import sys
import os
import gzip
import subprocess
import time

import psycopg2
import psycopg2.extras

DB_CONFIG = {
    'host': os.environ.get('DB_HOST', 'localhost'),
    'port': int(os.environ.get('DB_PORT', '5432')),
    'database': os.environ.get('DB_NAME', 'olms_multiyear'),
    'user': os.environ.get('DB_USER', 'postgres'),
    'password': os.environ.get('DB_PASSWORD', ''),
}

PGDUMP_PATH = r'C:\Users\jakew\Downloads\pgdump.sql.gz'
PSQL_PATH = r'C:\Program Files\PostgreSQL\17\bin\psql.exe'


def restore_pgdump():
    """Restore the GLEIF pgdump into the database.

    The dump creates schema 'gleif' and loads all 9 tables via COPY.
    We stream gzip -> psql to avoid decompressing to disk.
    """
    print("=== Step 1: Restoring GLEIF pgdump ===")
    print(f"Source: {PGDUMP_PATH}")
    file_size = os.path.getsize(PGDUMP_PATH)
    print(f"Compressed size: {file_size / 1024 / 1024:.0f} MB")

    start = time.time()

    # Stream gzip through psql
    # On Windows, we read the gzip file and pipe to psql stdin
    env = os.environ.copy()
    env['PGPASSWORD'] = DB_CONFIG['password']

    proc = subprocess.Popen(
        [PSQL_PATH, '-h', DB_CONFIG['host'], '-U', DB_CONFIG['user'],
         '-d', DB_CONFIG['dbname'], '-q', '--set', 'ON_ERROR_STOP=on'],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env
    )

    bytes_read = 0
    last_report = 0
    chunk_size = 64 * 1024  # 64KB chunks

    with gzip.open(PGDUMP_PATH, 'rb') as f:
        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                break
            proc.stdin.write(chunk)
            bytes_read += len(chunk)

            # Progress report every 100MB
            mb_read = bytes_read / (1024 * 1024)
            if mb_read - last_report >= 100:
                elapsed = time.time() - start
                rate = mb_read / elapsed if elapsed > 0 else 0
                print(f"  Streamed {mb_read:.0f} MB ({rate:.1f} MB/s, {elapsed:.0f}s elapsed)...")
                last_report = mb_read

    proc.stdin.close()
    stdout, stderr = proc.communicate()

    elapsed = time.time() - start

    if proc.returncode != 0:
        print(f"ERROR: psql restore failed (exit code {proc.returncode})")
        print(f"stderr: {stderr.decode('utf-8', errors='replace')[:2000]}")
        sys.exit(1)

    print(f"  Restore complete in {elapsed:.0f}s ({bytes_read / 1024 / 1024:.0f} MB uncompressed)")
    return True


def add_gleif_indexes(conn):
    """Add indexes to gleif schema tables for efficient querying."""
    print("\n=== Step 2: Adding indexes to gleif tables ===")
    cur = conn.cursor()

    indexes = [
        ("idx_gleif_es_link", "gleif.entity_statement", "_link"),
        ("idx_gleif_es_name", "gleif.entity_statement", "name"),
        ("idx_gleif_ea_link", "gleif.entity_addresses", "_link_entity_statement"),
        ("idx_gleif_ea_country", "gleif.entity_addresses", "country"),
        ("idx_gleif_ei_link", "gleif.entity_identifiers", "_link_entity_statement"),
        ("idx_gleif_ei_scheme", "gleif.entity_identifiers", "scheme"),
        ("idx_gleif_ooc_subject", "gleif.ooc_statement", "subject_describedbyentitystatement"),
        ("idx_gleif_ooc_party_entity", "gleif.ooc_statement", "interestedparty_describedbyentitystatement"),
        ("idx_gleif_ooc_link", "gleif.ooc_statement", "_link"),
        ("idx_gleif_oi_link", "gleif.ooc_interests", "_link_ooc_statement"),
    ]

    for idx_name, table, column in indexes:
        try:
            cur.execute(f'CREATE INDEX IF NOT EXISTS {idx_name} ON {table} ("{column}")')
            conn.commit()
            print(f"  Created index {idx_name}")
        except Exception as e:
            conn.rollback()
            print(f"  Index {idx_name} skipped: {e}")

    # Verify row counts
    tables = [
        'gleif.entity_statement', 'gleif.entity_identifiers', 'gleif.entity_addresses',
        'gleif.ooc_statement', 'gleif.ooc_interests', 'gleif.ooc_annotations',
        'gleif.person_statement', 'gleif.person_annotations', 'gleif.entity_annotations'
    ]
    print("\n  Row counts:")
    for table in tables:
        try:
            cur.execute(f"SELECT COUNT(*) FROM {table}")
            count = cur.fetchone()[0]
            print(f"    {table}: {count:,}")
        except Exception as e:
            conn.rollback()
            print(f"    {table}: ERROR - {e}")


def extract_us_entities(conn):
    """Extract US entities with identifiers into gleif_us_entities table."""
    print("\n=== Step 3: Extracting US entities ===")
    cur = conn.cursor()

    # Create target table
    cur.execute("DROP TABLE IF EXISTS gleif_ownership_links CASCADE")
    cur.execute("DROP TABLE IF EXISTS gleif_us_entities CASCADE")
    cur.execute("""
        CREATE TABLE gleif_us_entities (
            id SERIAL PRIMARY KEY,
            bods_link TEXT NOT NULL,
            entity_name TEXT,
            entity_type TEXT,
            jurisdiction_code TEXT,
            address TEXT,
            address_city TEXT,
            address_state VARCHAR(10),
            address_zip VARCHAR(20),
            address_country VARCHAR(2),
            lei VARCHAR(20),
            registration_number TEXT,
            name_normalized TEXT,
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)
    conn.commit()

    # Extract US entities: join entity_statement + entity_addresses (country = 'US')
    # Plus entity_identifiers for LEI
    print("  Inserting US entities...")
    start = time.time()
    cur.execute("""
        INSERT INTO gleif_us_entities (bods_link, entity_name, entity_type, jurisdiction_code,
            address, address_city, address_state, address_zip, address_country, lei, name_normalized)
        SELECT DISTINCT ON (es._link)
            es._link,
            es.name,
            es.entitytype,
            es.incorporatedinjurisdiction_code,
            ea.address,
            -- Extract city from address (last element before state/zip, heuristic)
            NULL,  -- city parsed later
            -- Extract state from jurisdiction or address
            CASE
                WHEN es.incorporatedinjurisdiction_code LIKE 'US-%'
                THEN SUBSTRING(es.incorporatedinjurisdiction_code FROM 4)
                ELSE NULL
            END,
            ea.postcode,
            ea.country,
            -- LEI from identifiers
            (SELECT ei.id FROM gleif.entity_identifiers ei
             WHERE ei._link_entity_statement = es._link AND ei.scheme = 'XI-LEI'
             LIMIT 1),
            -- Normalized name
            LOWER(REGEXP_REPLACE(
                REGEXP_REPLACE(es.name, '\s+(INC|INCORPORATED|CORP|CORPORATION|LLC|LLP|LTD|LIMITED|CO|COMPANY)\.?$', '', 'i'),
                '[^a-zA-Z0-9 ]', ' ', 'g'
            ))
        FROM gleif.entity_statement es
        JOIN gleif.entity_addresses ea ON ea._link_entity_statement = es._link
        WHERE ea.country = 'US'
          AND es.entitytype = 'registeredEntity'
        ORDER BY es._link, ea.type  -- prefer 'registered' address type
    """)
    count = cur.rowcount
    conn.commit()
    elapsed = time.time() - start
    print(f"  Inserted {count:,} US entities in {elapsed:.0f}s")

    # Also get entities incorporated in US jurisdictions but with non-US addresses
    cur.execute("""
        INSERT INTO gleif_us_entities (bods_link, entity_name, entity_type, jurisdiction_code,
            address_state, lei, name_normalized)
        SELECT DISTINCT ON (es._link)
            es._link,
            es.name,
            es.entitytype,
            es.incorporatedinjurisdiction_code,
            CASE
                WHEN es.incorporatedinjurisdiction_code LIKE 'US-%'
                THEN SUBSTRING(es.incorporatedinjurisdiction_code FROM 4)
                ELSE NULL
            END,
            (SELECT ei.id FROM gleif.entity_identifiers ei
             WHERE ei._link_entity_statement = es._link AND ei.scheme = 'XI-LEI'
             LIMIT 1),
            LOWER(REGEXP_REPLACE(
                REGEXP_REPLACE(es.name, '\s+(INC|INCORPORATED|CORP|CORPORATION|LLC|LLP|LTD|LIMITED|CO|COMPANY)\.?$', '', 'i'),
                '[^a-zA-Z0-9 ]', ' ', 'g'
            ))
        FROM gleif.entity_statement es
        WHERE es.incorporatedinjurisdiction_code LIKE 'US-%'
          AND es.entitytype = 'registeredEntity'
          AND NOT EXISTS (
              SELECT 1 FROM gleif_us_entities g WHERE g.bods_link = es._link
          )
        ORDER BY es._link
    """)
    extra = cur.rowcount
    conn.commit()
    print(f"  Added {extra:,} US-incorporated entities without US address")

    # Create indexes
    cur.execute("CREATE INDEX idx_gus_bods_link ON gleif_us_entities(bods_link)")
    cur.execute("CREATE INDEX idx_gus_lei ON gleif_us_entities(lei) WHERE lei IS NOT NULL")
    cur.execute("CREATE INDEX idx_gus_name ON gleif_us_entities(name_normalized)")
    cur.execute("CREATE INDEX idx_gus_state ON gleif_us_entities(address_state)")
    conn.commit()
    print("  Indexes created")

    # Stats
    cur.execute("SELECT COUNT(*) FROM gleif_us_entities")
    total = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM gleif_us_entities WHERE lei IS NOT NULL")
    with_lei = cur.fetchone()[0]
    cur.execute("SELECT COUNT(DISTINCT address_state) FROM gleif_us_entities WHERE address_state IS NOT NULL")
    states = cur.fetchone()[0]
    print(f"  Total US entities: {total:,} ({with_lei:,} with LEI, {states} states)")


def extract_ownership_links(conn):
    """Extract ownership links where at least one side is a US entity."""
    print("\n=== Step 4: Extracting US ownership links ===")
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE gleif_ownership_links (
            id SERIAL PRIMARY KEY,
            parent_bods_link TEXT,
            child_bods_link TEXT,
            interest_level TEXT,
            parent_entity_id INTEGER REFERENCES gleif_us_entities(id),
            child_entity_id INTEGER REFERENCES gleif_us_entities(id),
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)
    conn.commit()

    # Extract entity-to-entity ownership where at least one side is US
    print("  Inserting ownership links...")
    start = time.time()
    cur.execute("""
        INSERT INTO gleif_ownership_links (parent_bods_link, child_bods_link, interest_level,
            parent_entity_id, child_entity_id)
        SELECT
            ooc.interestedparty_describedbyentitystatement as parent_bods_link,
            ooc.subject_describedbyentitystatement as child_bods_link,
            oi.interestlevel,
            p.id as parent_entity_id,
            c.id as child_entity_id
        FROM gleif.ooc_statement ooc
        LEFT JOIN gleif.ooc_interests oi ON oi._link_ooc_statement = ooc._link
        LEFT JOIN gleif_us_entities p ON p.bods_link = ooc.interestedparty_describedbyentitystatement
        LEFT JOIN gleif_us_entities c ON c.bods_link = ooc.subject_describedbyentitystatement
        WHERE ooc.interestedparty_describedbyentitystatement IS NOT NULL
          AND ooc.interestedparty_describedbyentitystatement != ''
          AND (p.id IS NOT NULL OR c.id IS NOT NULL)
    """)
    count = cur.rowcount
    conn.commit()
    elapsed = time.time() - start
    print(f"  Inserted {count:,} ownership links in {elapsed:.0f}s")

    # Create indexes
    cur.execute("CREATE INDEX idx_gol_parent ON gleif_ownership_links(parent_entity_id)")
    cur.execute("CREATE INDEX idx_gol_child ON gleif_ownership_links(child_entity_id)")
    cur.execute("CREATE INDEX idx_gol_parent_bods ON gleif_ownership_links(parent_bods_link)")
    cur.execute("CREATE INDEX idx_gol_child_bods ON gleif_ownership_links(child_bods_link)")
    conn.commit()
    print("  Indexes created")

    # Stats
    cur.execute("SELECT COUNT(*) FROM gleif_ownership_links WHERE parent_entity_id IS NOT NULL AND child_entity_id IS NOT NULL")
    both_us = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM gleif_ownership_links WHERE parent_entity_id IS NOT NULL AND child_entity_id IS NULL")
    parent_us = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM gleif_ownership_links WHERE parent_entity_id IS NULL AND child_entity_id IS NOT NULL")
    child_us = cur.fetchone()[0]
    cur.execute("SELECT COUNT(DISTINCT interest_level) FROM gleif_ownership_links")

    print(f"  Both US: {both_us:,}")
    print(f"  Parent US only: {parent_us:,}")
    print(f"  Child US only: {child_us:,}")

    # Interest level breakdown
    cur.execute("""
        SELECT COALESCE(interest_level, 'NULL') as level, COUNT(*)
        FROM gleif_ownership_links GROUP BY interest_level ORDER BY COUNT(*) DESC
    """)
    print("  Interest levels:")
    for row in cur.fetchall():
        print(f"    {row[0]}: {row[1]:,}")


def main():
    skip_restore = '--skip-restore' in sys.argv or '--extract-only' in sys.argv

    if not skip_restore:
        if not os.path.exists(PGDUMP_PATH):
            print(f"ERROR: pgdump not found at {PGDUMP_PATH}")
            sys.exit(1)
        restore_pgdump()
    else:
        print("Skipping pgdump restore (--skip-restore)")

    conn = psycopg2.connect(**DB_CONFIG)
    conn.autocommit = False
    psycopg2.extras.register_default_jsonb(conn)

    try:
        if not skip_restore:
            add_gleif_indexes(conn)

        extract_us_entities(conn)
        extract_ownership_links(conn)

        print("\n=== Phase 1 Complete ===")
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM gleif_us_entities")
        print(f"US entities: {cur.fetchone()[0]:,}")
        cur.execute("SELECT COUNT(*) FROM gleif_ownership_links")
        print(f"Ownership links: {cur.fetchone()[0]:,}")

    finally:
        conn.close()


if __name__ == '__main__':
    main()
