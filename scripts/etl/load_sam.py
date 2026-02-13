"""
Load SAM.gov Public V2 Monthly Extract into PostgreSQL.

Source: SAM_PUBLIC_UTF-8_MONTHLY_V2_20260201.zip (872,819 entities)
Target: sam_entities table in olms_multiyear database

Usage: py scripts/etl/load_sam.py
"""
import sys
import os
import zipfile
import time
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from db_config import get_connection

SAM_ZIP = r"C:\Users\jakew\Downloads\SAM_PUBLIC_UTF-8_MONTHLY_V2_20260201.zip"
BATCH_SIZE = 5000

# Column positions in pipe-delimited SAM V2 format
COL = {
    'uei': 0,
    'cage_code': 3,
    'sam_status': 5,
    'purpose_code': 6,
    'registration_date': 7,
    'expiration_date': 8,
    'last_update_date': 9,
    'legal_business_name': 11,
    'dba_name': 12,
    'physical_address': 15,
    'physical_address2': 16,
    'physical_city': 17,
    'physical_state': 18,
    'physical_zip': 19,
    'country': 21,
    'entity_start_date': 24,
    'fiscal_year_end': 25,
    'url': 26,
    'entity_structure': 27,
    'state_of_incorporation': 28,
    'naics_primary': 32,
    'naics_count': 33,
    'naics_all': 34,
    'psc_codes': 36,
}


def ts():
    return datetime.now().strftime('%H:%M:%S')


def parse_date(val):
    """Parse YYYYMMDD date string, return None if invalid."""
    val = val.strip()
    if not val or len(val) != 8 or not val.isdigit():
        return None
    try:
        return f"{val[:4]}-{val[4:6]}-{val[6:8]}"
    except Exception:
        return None


def parse_int(val):
    """Parse integer, return None if invalid."""
    val = val.strip()
    if not val:
        return None
    try:
        return int(val)
    except ValueError:
        return None


def get_field(fields, key):
    """Safely get a field by column key, return stripped string or empty."""
    idx = COL[key]
    if idx < len(fields):
        return fields[idx].strip()
    return ''


def create_table(cur, conn):
    """Create sam_entities table."""
    print(f"[{ts()}] Creating sam_entities table...")
    cur.execute("DROP TABLE IF EXISTS sam_entities CASCADE")
    cur.execute("""
        CREATE TABLE sam_entities (
            uei TEXT PRIMARY KEY,
            cage_code VARCHAR(10),
            sam_status CHAR(1),
            purpose_code VARCHAR(5),
            registration_date DATE,
            expiration_date DATE,
            last_update_date DATE,
            legal_business_name TEXT NOT NULL,
            dba_name TEXT,
            physical_address TEXT,
            physical_address2 TEXT,
            physical_city TEXT,
            physical_state VARCHAR(5),
            physical_zip VARCHAR(10),
            country VARCHAR(5),
            entity_start_date DATE,
            fiscal_year_end VARCHAR(4),
            url TEXT,
            entity_structure VARCHAR(5),
            state_of_incorporation VARCHAR(5),
            naics_primary VARCHAR(10),
            naics_count INTEGER,
            naics_all TEXT,
            psc_codes TEXT,
            name_normalized TEXT,
            name_aggressive TEXT
        )
    """)
    conn.commit()
    print("  Table created.")


def load_from_zip(cur, conn):
    """Read ZIP, parse pipe-delimited, bulk insert USA entities."""
    print(f"[{ts()}] Loading from {os.path.basename(SAM_ZIP)}...")

    from psycopg2.extras import execute_values

    total_read = 0
    total_inserted = 0
    skipped_non_usa = 0
    skipped_parse_error = 0
    batch = []

    insert_sql = """
        INSERT INTO sam_entities (
            uei, cage_code, sam_status, purpose_code,
            registration_date, expiration_date, last_update_date,
            legal_business_name, dba_name,
            physical_address, physical_address2, physical_city,
            physical_state, physical_zip, country,
            entity_start_date, fiscal_year_end, url,
            entity_structure, state_of_incorporation,
            naics_primary, naics_count, naics_all, psc_codes
        ) VALUES %s
        ON CONFLICT (uei) DO NOTHING
    """

    with zipfile.ZipFile(SAM_ZIP, 'r') as zf:
        fname = zf.infolist()[0].filename
        with zf.open(fname) as f:
            # Skip BOF header
            header = f.readline().decode('utf-8', errors='replace').strip()
            print(f"  BOF: {header}")

            for raw_line in f:
                line = raw_line.decode('utf-8', errors='replace').strip()
                if not line or line.startswith('EOF'):
                    continue

                fields = line.split('|')
                total_read += 1

                # Filter to USA only
                country = get_field(fields, 'country')
                if country != 'USA':
                    skipped_non_usa += 1
                    continue

                uei = get_field(fields, 'uei')
                name = get_field(fields, 'legal_business_name')
                if not uei or not name:
                    skipped_parse_error += 1
                    continue

                try:
                    row = (
                        uei,
                        get_field(fields, 'cage_code') or None,
                        get_field(fields, 'sam_status') or None,
                        get_field(fields, 'purpose_code') or None,
                        parse_date(get_field(fields, 'registration_date')),
                        parse_date(get_field(fields, 'expiration_date')),
                        parse_date(get_field(fields, 'last_update_date')),
                        name,
                        get_field(fields, 'dba_name') or None,
                        get_field(fields, 'physical_address') or None,
                        get_field(fields, 'physical_address2') or None,
                        get_field(fields, 'physical_city') or None,
                        get_field(fields, 'physical_state') or None,
                        get_field(fields, 'physical_zip') or None,
                        country,
                        parse_date(get_field(fields, 'entity_start_date')),
                        get_field(fields, 'fiscal_year_end') or None,
                        get_field(fields, 'url') or None,
                        get_field(fields, 'entity_structure') or None,
                        get_field(fields, 'state_of_incorporation') or None,
                        get_field(fields, 'naics_primary') or None,
                        parse_int(get_field(fields, 'naics_count')),
                        get_field(fields, 'naics_all') or None,
                        get_field(fields, 'psc_codes') or None,
                    )
                    batch.append(row)
                except Exception as e:
                    skipped_parse_error += 1
                    if skipped_parse_error <= 5:
                        print(f"  Parse error on record {total_read}: {e}")
                    continue

                if len(batch) >= BATCH_SIZE:
                    execute_values(cur, insert_sql, batch, page_size=BATCH_SIZE)
                    total_inserted += len(batch)
                    batch = []
                    conn.commit()

                    if total_inserted % 100000 == 0:
                        print(f"    {total_inserted:,} inserted ({total_read:,} read)...")

            # Final batch
            if batch:
                execute_values(cur, insert_sql, batch, page_size=BATCH_SIZE)
                total_inserted += len(batch)
                conn.commit()

    print(f"  Read: {total_read:,}")
    print(f"  Inserted: {total_inserted:,}")
    print(f"  Skipped (non-USA): {skipped_non_usa:,}")
    print(f"  Skipped (parse error): {skipped_parse_error:,}")
    return total_inserted


def normalize_names(cur, conn):
    """Normalize business names for matching (SQL-based bulk update)."""
    print(f"[{ts()}] Normalizing names...")

    # name_normalized: lowercase, trimmed
    cur.execute("""
        UPDATE sam_entities SET name_normalized =
            UPPER(TRIM(legal_business_name))
        WHERE legal_business_name IS NOT NULL
    """)
    print(f"  name_normalized: {cur.rowcount:,} rows")
    conn.commit()

    # name_aggressive: strip legal suffixes, punctuation, extra spaces
    cur.execute(r"""
        UPDATE sam_entities SET name_aggressive =
            TRIM(REGEXP_REPLACE(
                REGEXP_REPLACE(
                    REGEXP_REPLACE(
                        UPPER(TRIM(legal_business_name)),
                        E'\b(INC|INCORPORATED|CORP|CORPORATION|LLC|LLP|LTD|LIMITED|CO|COMPANY|ASSOC|ASSOCIATION|ASSN|PLLC|PC|PA|DBA|GROUP|HOLDINGS|ENTERPRISES|SERVICES|INTERNATIONAL|INTL|NATIONAL|NATL|THE)\b\.?',
                        '', 'g'),
                    E'[^A-Z0-9 ]', ' ', 'g'),
                E'\s+', ' ', 'g'))
        WHERE legal_business_name IS NOT NULL
    """)
    print(f"  name_aggressive: {cur.rowcount:,} rows")
    conn.commit()

    # Also normalize DBA names
    cur.execute(r"""
        UPDATE sam_entities SET dba_name =
            TRIM(REGEXP_REPLACE(
                REGEXP_REPLACE(
                    REGEXP_REPLACE(
                        UPPER(TRIM(dba_name)),
                        E'\b(INC|INCORPORATED|CORP|CORPORATION|LLC|LLP|LTD|LIMITED|CO|COMPANY|ASSOC|ASSOCIATION|ASSN|PLLC|PC|PA|DBA|GROUP|HOLDINGS|ENTERPRISES|SERVICES|INTERNATIONAL|INTL|NATIONAL|NATL|THE)\b\.?',
                        '', 'g'),
                    E'[^A-Z0-9 ]', ' ', 'g'),
                E'\s+', ' ', 'g'))
        WHERE dba_name IS NOT NULL AND dba_name != ''
    """)
    print(f"  dba_name normalized: {cur.rowcount:,} rows")
    conn.commit()


def create_indexes(cur, conn):
    """Create indexes for efficient matching."""
    print(f"[{ts()}] Creating indexes...")

    indexes = [
        ("idx_sam_state", "sam_entities(physical_state)"),
        ("idx_sam_naics", "sam_entities(naics_primary)"),
        ("idx_sam_cage", "sam_entities(cage_code)"),
        ("idx_sam_status", "sam_entities(sam_status)"),
        ("idx_sam_city", "sam_entities(physical_city)"),
        ("idx_sam_name_norm", "sam_entities(name_normalized)"),
    ]

    for idx_name, idx_def in indexes:
        cur.execute(f"CREATE INDEX IF NOT EXISTS {idx_name} ON {idx_def}")
        print(f"  {idx_name}")

    # GIN trigram index for fuzzy matching (requires pg_trgm extension)
    cur.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_sam_name_trgm
        ON sam_entities USING gin (name_aggressive gin_trgm_ops)
    """)
    print("  idx_sam_name_trgm (GIN trigram)")

    conn.commit()
    print("  All indexes created.")


def print_summary(cur):
    """Print data summary stats."""
    print(f"\n[{ts()}] === SAM ENTITIES SUMMARY ===")

    cur.execute("SELECT COUNT(*) FROM sam_entities")
    total = cur.fetchone()[0]
    print(f"  Total records: {total:,}")

    cur.execute("SELECT COUNT(*) FROM sam_entities WHERE sam_status = 'A'")
    active = cur.fetchone()[0]
    print(f"  Active: {active:,} ({100*active/total:.1f}%)")

    cur.execute("SELECT COUNT(*) FROM sam_entities WHERE naics_primary IS NOT NULL")
    has_naics = cur.fetchone()[0]
    print(f"  Has NAICS: {has_naics:,} ({100*has_naics/total:.1f}%)")

    cur.execute("SELECT COUNT(*) FROM sam_entities WHERE cage_code IS NOT NULL")
    has_cage = cur.fetchone()[0]
    print(f"  Has CAGE: {has_cage:,} ({100*has_cage/total:.1f}%)")

    cur.execute("SELECT COUNT(*) FROM sam_entities WHERE dba_name IS NOT NULL AND dba_name != ''")
    has_dba = cur.fetchone()[0]
    print(f"  Has DBA name: {has_dba:,} ({100*has_dba/total:.1f}%)")

    cur.execute("""
        SELECT physical_state, COUNT(*) as cnt
        FROM sam_entities
        WHERE physical_state IS NOT NULL
        GROUP BY physical_state
        ORDER BY cnt DESC
        LIMIT 10
    """)
    print("\n  Top 10 states:")
    for row in cur.fetchall():
        print(f"    {row[0]}: {row[1]:,}")

    cur.execute("""
        SELECT LEFT(naics_primary, 2) as n2, COUNT(*) as cnt
        FROM sam_entities
        WHERE naics_primary IS NOT NULL
        GROUP BY n2
        ORDER BY cnt DESC
        LIMIT 10
    """)
    print("\n  Top 10 NAICS (2-digit):")
    for row in cur.fetchall():
        print(f"    {row[0]}: {row[1]:,}")

    cur.execute("""
        SELECT entity_structure, COUNT(*) as cnt
        FROM sam_entities
        GROUP BY entity_structure
        ORDER BY cnt DESC
        LIMIT 8
    """)
    print("\n  Entity types:")
    struct_labels = {
        '2L': 'Corporate/LLC', '2K': 'Partnership/LLP', '2J': 'S-Corp',
        '2A': 'Government', '8H': 'Nonprofit/501c', 'ZZ': 'Other',
        'X6': 'Foreign', 'CY': 'Sole Prop'
    }
    for row in cur.fetchall():
        code = row[0] or '?'
        label = struct_labels.get(code, '?')
        print(f"    {code} ({label}): {row[1]:,}")


def main():
    start = time.time()
    print(f"[{ts()}] SAM.gov ETL Pipeline")
    print(f"  Source: {SAM_ZIP}")
    print(f"  Database: olms_multiyear")
    print()

    conn = get_connection()
    cur = conn.cursor()

    create_table(cur, conn)
    total = load_from_zip(cur, conn)
    normalize_names(cur, conn)
    create_indexes(cur, conn)
    print_summary(cur)

    elapsed = time.time() - start
    print(f"\n[{ts()}] Done in {elapsed:.0f}s ({elapsed/60:.1f} min)")

    cur.close()
    conn.close()


if __name__ == '__main__':
    main()
