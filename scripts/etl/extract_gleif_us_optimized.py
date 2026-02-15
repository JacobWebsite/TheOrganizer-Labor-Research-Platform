"""
Optimized GLEIF US entity extraction.
Replaces the single slow INSERT+correlated subquery with a 2-step approach:
1. INSERT entities without LEI (fast JOIN + DISTINCT ON)
2. UPDATE LEI via indexed JOIN (fast)
"""
import psycopg2
import time
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
conn.autocommit = False
cur = conn.cursor()

# Step 1: Recreate the table fresh
print('=== Step 1: Recreating gleif_us_entities ===')
cur.execute('DROP TABLE IF EXISTS gleif_ownership_links CASCADE')
cur.execute('DROP TABLE IF EXISTS gleif_us_entities CASCADE')
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
print('  Table created')

# Step 2: Insert US entities WITHOUT the LEI subquery
print('\n=== Step 2: Inserting US entities (no LEI yet) ===')
start = time.time()
cur.execute(r"""
    INSERT INTO gleif_us_entities (bods_link, entity_name, entity_type, jurisdiction_code,
        address, address_state, address_zip, address_country, name_normalized)
    SELECT DISTINCT ON (es._link)
        es._link,
        es.name,
        es.entitytype,
        es.incorporatedinjurisdiction_code,
        ea.address,
        CASE
            WHEN es.incorporatedinjurisdiction_code LIKE 'US-%%'
            THEN SUBSTRING(es.incorporatedinjurisdiction_code FROM 4)
            ELSE NULL
        END,
        ea.postcode,
        ea.country,
        LOWER(REGEXP_REPLACE(
            REGEXP_REPLACE(es.name, '\s+(INC|INCORPORATED|CORP|CORPORATION|LLC|LLP|LTD|LIMITED|CO|COMPANY)\.?$', '', 'i'),
            '[^a-zA-Z0-9 ]', ' ', 'g'
        ))
    FROM gleif.entity_statement es
    JOIN gleif.entity_addresses ea ON ea._link_entity_statement = es._link
    WHERE ea.country = 'US'
      AND es.entitytype = 'registeredEntity'
    ORDER BY es._link, ea.type
""")
count1 = cur.rowcount
conn.commit()
elapsed1 = time.time() - start
print(f'  Inserted {count1:,} US entities in {elapsed1:.1f}s')

# Step 2b: US-incorporated entities without US address
print('\n=== Step 2b: US-incorporated without US address ===')
start = time.time()
cur.execute(r"""
    INSERT INTO gleif_us_entities (bods_link, entity_name, entity_type, jurisdiction_code,
        address_state, name_normalized)
    SELECT DISTINCT ON (es._link)
        es._link,
        es.name,
        es.entitytype,
        es.incorporatedinjurisdiction_code,
        CASE
            WHEN es.incorporatedinjurisdiction_code LIKE 'US-%%'
            THEN SUBSTRING(es.incorporatedinjurisdiction_code FROM 4)
            ELSE NULL
        END,
        LOWER(REGEXP_REPLACE(
            REGEXP_REPLACE(es.name, '\s+(INC|INCORPORATED|CORP|CORPORATION|LLC|LLP|LTD|LIMITED|CO|COMPANY)\.?$', '', 'i'),
            '[^a-zA-Z0-9 ]', ' ', 'g'
        ))
    FROM gleif.entity_statement es
    WHERE es.incorporatedinjurisdiction_code LIKE 'US-%%'
      AND es.entitytype = 'registeredEntity'
      AND NOT EXISTS (
          SELECT 1 FROM gleif_us_entities g WHERE g.bods_link = es._link
      )
    ORDER BY es._link
""")
count2 = cur.rowcount
conn.commit()
elapsed2 = time.time() - start
print(f'  Added {count2:,} US-incorporated entities in {elapsed2:.1f}s')

# Step 3: Index bods_link for the LEI update
print('\n=== Step 3: Indexing bods_link ===')
start = time.time()
cur.execute('CREATE INDEX idx_gus_bods_link ON gleif_us_entities(bods_link)')
conn.commit()
print(f'  Index created in {time.time()-start:.1f}s')

# Step 4: UPDATE LEI via JOIN
print('\n=== Step 4: Updating LEI via JOIN ===')
start = time.time()
cur.execute("""
    UPDATE gleif_us_entities g
    SET lei = ei.id
    FROM gleif.entity_identifiers ei
    WHERE ei._link_entity_statement = g.bods_link
      AND ei.scheme = 'XI-LEI'
""")
lei_count = cur.rowcount
conn.commit()
elapsed4 = time.time() - start
print(f'  Updated {lei_count:,} LEI values in {elapsed4:.1f}s')

# Step 5: Final indexes
print('\n=== Step 5: Final indexes ===')
start = time.time()
cur.execute('CREATE INDEX idx_gus_lei ON gleif_us_entities(lei) WHERE lei IS NOT NULL')
cur.execute('CREATE INDEX idx_gus_name ON gleif_us_entities(name_normalized)')
cur.execute('CREATE INDEX idx_gus_state ON gleif_us_entities(address_state)')
conn.commit()
print(f'  Indexes created in {time.time()-start:.1f}s')

# Summary
print('\n=== Summary ===')
cur.execute('SELECT COUNT(*) FROM gleif_us_entities')
total = cur.fetchone()[0]
cur.execute('SELECT COUNT(*) FROM gleif_us_entities WHERE lei IS NOT NULL')
with_lei = cur.fetchone()[0]
cur.execute('SELECT COUNT(DISTINCT address_state) FROM gleif_us_entities WHERE address_state IS NOT NULL')
states = cur.fetchone()[0]
print(f'Total US entities: {total:,}')
print(f'With LEI: {with_lei:,}')
print(f'States: {states}')

conn.close()
print('\nDone!')
