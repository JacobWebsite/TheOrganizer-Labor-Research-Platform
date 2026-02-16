"""
Phase 2: Load SEC EDGAR submissions into PostgreSQL.

Steps:
1. Create sec_companies table
2. Iterate 955K JSON files from submissions.zip
3. Extract company metadata (cik, name, ein, lei, sic, addresses, tickers)
4. Normalize names, batch insert via COPY
5. Print summary stats

Usage:
    py scripts/etl/load_sec_edgar.py
    py scripts/etl/load_sec_edgar.py --limit 10000    # for testing
"""

import sys
import os
import json
import re
import io
import time
import zipfile

import psycopg2
import psycopg2.extras

DB_CONFIG = {
    'host': os.environ.get('DB_HOST', 'localhost'),
    'port': int(os.environ.get('DB_PORT', '5432')),
    'database': os.environ.get('DB_NAME', 'olms_multiyear'),
    'user': os.environ.get('DB_USER', 'postgres'),
    'password': os.environ.get('DB_PASSWORD', ''),
}

SUBMISSIONS_PATH = r'C:\Users\jakew\Downloads\submissions.zip'

# Legal suffixes to strip
LEGAL_SUFFIXES = re.compile(
    r'\b(inc|incorporated|corp|corporation|llc|llp|ltd|limited|co|company|'
    r'assoc|association|assn|foundation|fund|trust|society|institute|'
    r'the|of|and|for|a|an)\b',
    re.IGNORECASE
)
STRIP_CHARS = re.compile(r'[^a-z0-9 ]')


def normalize_name(name):
    """Normalize employer name for matching."""
    if not name:
        return ''
    name = name.lower().strip()
    name = STRIP_CHARS.sub(' ', name)
    name = LEGAL_SUFFIXES.sub('', name)
    name = re.sub(r'\s+', ' ', name).strip()
    return name


def clean_ein(ein):
    """Clean EIN: strip dashes, filter out all-zeros."""
    if not ein:
        return None
    ein = str(ein).strip().replace('-', '')
    if ein in ('', '000000000', '0'):
        return None
    # EIN should be 9 digits
    if not ein.isdigit():
        return None
    return ein


def clean_state(state_code):
    """Clean state code - must be 2-letter US state."""
    if not state_code or len(str(state_code).strip()) != 2:
        return None
    state = str(state_code).strip().upper()
    # Filter out country codes (foreign locations)
    us_states = {
        'AL','AK','AZ','AR','CA','CO','CT','DE','FL','GA','HI','ID','IL','IN',
        'IA','KS','KY','LA','ME','MD','MA','MI','MN','MS','MO','MT','NE','NV',
        'NH','NJ','NM','NY','NC','ND','OH','OK','OR','PA','RI','SC','SD','TN',
        'TX','UT','VT','VA','WA','WV','WI','WY','DC','PR','VI','GU','AS','MP'
    }
    if state not in us_states:
        return None
    return state


def create_table(conn):
    """Create sec_companies table."""
    cur = conn.cursor()
    cur.execute("DROP TABLE IF EXISTS sec_companies CASCADE")
    cur.execute("""
        CREATE TABLE sec_companies (
            id SERIAL PRIMARY KEY,
            cik INTEGER NOT NULL UNIQUE,
            company_name TEXT,
            name_normalized TEXT,
            ein VARCHAR(20),
            lei VARCHAR(20),
            sic_code VARCHAR(10),
            sic_description TEXT,
            entity_type VARCHAR(50),
            state_of_incorporation VARCHAR(10),
            state VARCHAR(10),
            city TEXT,
            zip VARCHAR(20),
            street_address TEXT,
            ticker VARCHAR(20),
            exchange VARCHAR(20),
            is_public BOOLEAN DEFAULT FALSE,
            fiscal_year_end VARCHAR(4),
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)
    conn.commit()
    print("  Created sec_companies table")


def parse_sec_json(data):
    """Extract relevant fields from a SEC EDGAR JSON."""
    try:
        cik = int(str(data.get('cik', '0')).lstrip('0') or '0')
    except (ValueError, TypeError):
        return None

    if cik == 0:
        return None

    company_name = data.get('name', '').strip()
    if not company_name:
        return None

    ein = clean_ein(data.get('ein'))
    lei = data.get('lei') or None
    if lei and len(str(lei).strip()) < 10:
        lei = None

    sic_code = str(data.get('sic', '')).strip() or None
    sic_description = data.get('sicDescription', '').strip() or None
    entity_type = data.get('entityType', '').strip() or None
    state_of_incorp = data.get('stateOfIncorporation', '').strip() or None

    # Extract address - prefer business, fall back to mailing
    addresses = data.get('addresses', {})
    biz = addresses.get('business', {}) or {}
    mail = addresses.get('mailing', {}) or {}

    city = (biz.get('city') or mail.get('city') or '').strip().upper() or None
    state = clean_state(biz.get('stateOrCountry') or mail.get('stateOrCountry'))
    zip_code = (biz.get('zipCode') or mail.get('zipCode') or '').strip() or None
    street = (biz.get('street1') or mail.get('street1') or '').strip() or None

    # Tickers/exchanges
    tickers = data.get('tickers', [])
    exchanges = data.get('exchanges', [])
    ticker = tickers[0] if tickers else None
    exchange = exchanges[0] if exchanges else None
    is_public = bool(ticker)

    fiscal_year_end = data.get('fiscalYearEnd', '').strip() or None

    return {
        'cik': cik,
        'company_name': company_name,
        'name_normalized': normalize_name(company_name),
        'ein': ein,
        'lei': lei,
        'sic_code': sic_code,
        'sic_description': sic_description,
        'entity_type': entity_type,
        'state_of_incorporation': state_of_incorp,
        'state': state,
        'city': city,
        'zip': zip_code,
        'street_address': street,
        'ticker': ticker,
        'exchange': exchange,
        'is_public': is_public,
        'fiscal_year_end': fiscal_year_end,
    }


def escape_copy(val):
    """Escape a value for PostgreSQL COPY format."""
    if val is None:
        return '\\N'
    s = str(val)
    s = s.replace('\\', '\\\\').replace('\t', '\\t').replace('\n', '\\n').replace('\r', '\\r')
    return s


def load_sec_data(conn, limit=None):
    """Load SEC EDGAR submissions from zip file."""
    print("\n=== Loading SEC EDGAR submissions ===")
    print(f"Source: {SUBMISSIONS_PATH}")

    start = time.time()
    records = {}  # Dedup by CIK
    skipped_submissions = 0
    skipped_parse = 0
    errors = 0

    z = zipfile.ZipFile(SUBMISSIONS_PATH)
    names = z.namelist()
    total_files = len(names)
    print(f"  Total files in zip: {total_files:,}")

    # Filter to main CIK files only (skip -submissions-NNN.json which are filing pages)
    main_files = [n for n in names if '-submissions-' not in n and n.endswith('.json')]
    print(f"  Main company files: {len(main_files):,}")

    if limit:
        main_files = main_files[:limit]
        print(f"  Limited to: {limit}")

    for i, filename in enumerate(main_files):
        try:
            raw = z.read(filename)
            data = json.loads(raw)
            record = parse_sec_json(data)

            if record is None:
                skipped_parse += 1
                continue

            cik = record['cik']
            if cik not in records:
                records[cik] = record
        except Exception as e:
            errors += 1
            if errors <= 5:
                print(f"  Error parsing {filename}: {e}")

        if (i + 1) % 50000 == 0:
            elapsed = time.time() - start
            rate = (i + 1) / elapsed
            print(f"  Processed {i+1:,}/{len(main_files):,} files ({rate:.0f}/sec)")

    elapsed = time.time() - start
    print(f"  Parsed {len(records):,} unique companies in {elapsed:.0f}s")
    print(f"  Skipped: {skipped_parse} (no name/CIK), {errors} errors")

    # Bulk insert via COPY
    print("  Bulk inserting via COPY...")
    insert_start = time.time()

    columns = ['cik', 'company_name', 'name_normalized', 'ein', 'lei',
               'sic_code', 'sic_description', 'entity_type', 'state_of_incorporation',
               'state', 'city', 'zip', 'street_address', 'ticker', 'exchange',
               'is_public', 'fiscal_year_end']

    buf = io.StringIO()
    for rec in records.values():
        row = '\t'.join(escape_copy(rec[col]) for col in columns)
        buf.write(row + '\n')

    buf.seek(0)
    cur = conn.cursor()
    cur.copy_from(buf, 'sec_companies', columns=columns, null='\\N')
    conn.commit()

    insert_elapsed = time.time() - insert_start
    print(f"  Inserted {len(records):,} records in {insert_elapsed:.1f}s")

    # Create indexes
    print("  Creating indexes...")
    cur.execute("CREATE INDEX idx_sec_cik ON sec_companies(cik)")
    cur.execute("CREATE INDEX idx_sec_ein ON sec_companies(ein) WHERE ein IS NOT NULL")
    cur.execute("CREATE INDEX idx_sec_lei ON sec_companies(lei) WHERE lei IS NOT NULL")
    cur.execute("CREATE INDEX idx_sec_name ON sec_companies(name_normalized)")
    cur.execute("CREATE INDEX idx_sec_state ON sec_companies(state)")
    cur.execute("CREATE INDEX idx_sec_ticker ON sec_companies(ticker) WHERE ticker IS NOT NULL")
    cur.execute("CREATE INDEX idx_sec_sic ON sec_companies(sic_code)")
    conn.commit()
    print("  Indexes created")

    return len(records)


def print_stats(conn):
    """Print summary statistics."""
    print("\n=== SEC Companies Summary ===")
    cur = conn.cursor()

    cur.execute("SELECT COUNT(*) FROM sec_companies")
    print(f"Total companies: {cur.fetchone()[0]:,}")

    cur.execute("SELECT COUNT(*) FROM sec_companies WHERE ein IS NOT NULL")
    ein_count = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM sec_companies")
    total = cur.fetchone()[0]
    print(f"With EIN: {ein_count:,} ({100*ein_count/total:.1f}%)")

    cur.execute("SELECT COUNT(*) FROM sec_companies WHERE lei IS NOT NULL")
    lei_count = cur.fetchone()[0]
    print(f"With LEI: {lei_count:,} ({100*lei_count/total:.1f}%)")

    cur.execute("SELECT COUNT(*) FROM sec_companies WHERE is_public = TRUE")
    public = cur.fetchone()[0]
    print(f"Public (has ticker): {public:,} ({100*public/total:.1f}%)")

    cur.execute("SELECT COUNT(*) FROM sec_companies WHERE state IS NOT NULL")
    with_state = cur.fetchone()[0]
    print(f"With US state: {with_state:,} ({100*with_state/total:.1f}%)")

    cur.execute("""
        SELECT entity_type, COUNT(*) as cnt
        FROM sec_companies
        GROUP BY entity_type
        ORDER BY cnt DESC
        LIMIT 10
    """)
    print("\nBy entity type:")
    for row in cur.fetchall():
        print(f"  {row[0] or 'NULL'}: {row[1]:,}")

    cur.execute("""
        SELECT state, COUNT(*) as cnt
        FROM sec_companies
        WHERE state IS NOT NULL
        GROUP BY state
        ORDER BY cnt DESC
        LIMIT 10
    """)
    print("\nTop states:")
    for row in cur.fetchall():
        print(f"  {row[0]}: {row[1]:,}")

    # SIC sector breakdown
    cur.execute("""
        SELECT LEFT(sic_code, 2) as sic2, COUNT(*) as cnt
        FROM sec_companies
        WHERE sic_code IS NOT NULL AND sic_code != '' AND sic_code != '0000'
        GROUP BY sic2
        ORDER BY cnt DESC
        LIMIT 10
    """)
    print("\nTop SIC sectors (2-digit):")
    for row in cur.fetchall():
        print(f"  {row[0]}: {row[1]:,}")


def main():
    limit = None
    for arg in sys.argv[1:]:
        if arg.startswith('--limit'):
            if '=' in arg:
                limit = int(arg.split('=')[1])
            else:
                idx = sys.argv.index(arg)
                if idx + 1 < len(sys.argv):
                    limit = int(sys.argv[idx + 1])

    if not os.path.exists(SUBMISSIONS_PATH):
        print(f"ERROR: submissions.zip not found at {SUBMISSIONS_PATH}")
        sys.exit(1)

    conn = psycopg2.connect(**DB_CONFIG)
    conn.autocommit = False

    try:
        create_table(conn)
        load_sec_data(conn, limit=limit)
        print_stats(conn)
        print("\n=== Phase 2 Complete ===")
    finally:
        conn.close()


if __name__ == '__main__':
    main()
