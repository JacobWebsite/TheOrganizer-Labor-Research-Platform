"""
Load national 990 extract CSV into national_990_filers table.

Steps:
1. Create table if not exists
2. Read CSV, normalize names, filter out 990T and no-EIN records
3. Dedup by EIN: keep latest tax_year per EIN
4. Bulk insert via COPY
5. Update ny_990_filers with any new/newer NY records
6. Match to F7 (via OSHA EIN) and Mergent (direct EIN)
7. Print summary stats

Usage:
    py scripts/etl/load_national_990.py
    py scripts/etl/load_national_990.py --csv data/national_990_extract.csv
    py scripts/etl/load_national_990.py --skip-extract  # if CSV already exists
"""

import csv
import re
import sys
import os
import io
from collections import defaultdict
from datetime import datetime

import psycopg2
import psycopg2.extras

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

DB_CONFIG = {
    'host': os.environ.get('DB_HOST', 'localhost'),
    'port': int(os.environ.get('DB_PORT', '5432')),
    'database': os.environ.get('DB_NAME', 'olms_multiyear'),
    'user': os.environ.get('DB_USER', 'postgres'),
    'password': os.environ.get('DB_PASSWORD', ''),
}

# Legal suffixes to strip for normalization
LEGAL_SUFFIXES = re.compile(
    r'\b(inc|incorporated|corp|corporation|llc|llp|ltd|limited|co|company|'
    r'assoc|association|assn|foundation|fund|trust|society|institute|'
    r'council|committee|board|authority|commission|dept|department|'
    r'the|of|and|for|a|an)\b',
    re.IGNORECASE
)

STRIP_CHARS = re.compile(r'[^a-z0-9 ]')


def normalize_name(name):
    """Normalize employer name: lowercase, strip legal suffixes, extra spaces."""
    if not name:
        return ''
    name = name.lower().strip()
    name = STRIP_CHARS.sub(' ', name)
    name = LEGAL_SUFFIXES.sub('', name)
    name = re.sub(r'\s+', ' ', name).strip()
    return name


def safe_int(val):
    """Convert to int, return None if not numeric."""
    if not val or val == '':
        return None
    try:
        return int(float(val))
    except (ValueError, TypeError):
        return None


def safe_bigint(val):
    """Convert to bigint, return None if not numeric."""
    if not val or val == '':
        return None
    try:
        return int(float(val))
    except (ValueError, TypeError):
        return None


def create_table(conn):
    """Create national_990_filers table."""
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS national_990_filers (
            id SERIAL PRIMARY KEY,
            ein VARCHAR(20),
            business_name TEXT,
            name_normalized TEXT,
            street_address TEXT,
            city TEXT,
            state VARCHAR(2),
            zip_code VARCHAR(10),
            form_type VARCHAR(10),
            tax_year INTEGER,
            total_revenue BIGINT,
            total_employees INTEGER,
            total_assets BIGINT,
            total_expenses BIGINT,
            ntee_code VARCHAR(10),
            activity_description TEXT,
            source_file TEXT,
            created_at TIMESTAMP DEFAULT NOW()
        );
    """)
    # Create indexes
    for idx_sql in [
        "CREATE INDEX IF NOT EXISTS idx_n990_ein ON national_990_filers(ein);",
        "CREATE INDEX IF NOT EXISTS idx_n990_state ON national_990_filers(state);",
        "CREATE INDEX IF NOT EXISTS idx_n990_state_name ON national_990_filers(state, name_normalized);",
        "CREATE INDEX IF NOT EXISTS idx_n990_name_normalized ON national_990_filers(name_normalized);",
        "CREATE INDEX IF NOT EXISTS idx_n990_tax_year ON national_990_filers(tax_year);",
    ]:
        cur.execute(idx_sql)
    conn.commit()
    print("Table national_990_filers created/verified.")


def load_csv_deduped(csv_path):
    """Read CSV, dedup by EIN (keep latest tax_year), return list of records."""
    print(f"Reading {csv_path}...")

    # Track by EIN -> keep latest tax_year
    ein_records = {}  # ein -> record dict
    total_rows = 0
    skipped_no_ein = 0
    skipped_990t = 0
    skipped_no_state = 0
    error_rows = 0

    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            total_rows += 1

            if total_rows % 100000 == 0:
                print(f"  Read {total_rows:,} rows...")

            # Skip error rows
            if row.get('error'):
                error_rows += 1
                continue

            # Skip 990T forms
            form_type = (row.get('form_type') or '').strip()
            if form_type == '990T':
                skipped_990t += 1
                continue

            # Skip records with no EIN
            ein = (row.get('ein') or '').strip()
            if not ein:
                skipped_no_ein += 1
                continue

            # Skip records with no state
            state = (row.get('state') or '').strip().upper()
            if not state or len(state) != 2:
                skipped_no_state += 1
                continue

            tax_year = safe_int(row.get('tax_year'))
            if not tax_year:
                tax_year = 0

            # Dedup: keep latest tax_year per EIN
            if ein in ein_records:
                existing_year = ein_records[ein].get('tax_year') or 0
                if tax_year <= existing_year:
                    continue

            org_name = (row.get('org_name') or '').strip()

            ein_records[ein] = {
                'ein': ein,
                'business_name': org_name,
                'name_normalized': normalize_name(org_name),
                'street_address': (row.get('street') or '').strip(),
                'city': (row.get('city') or '').strip().upper(),
                'state': state,
                'zip_code': (row.get('zip') or '').strip()[:10],
                'form_type': form_type,
                'tax_year': tax_year,
                'total_revenue': safe_bigint(row.get('total_revenue')),
                'total_employees': safe_int(row.get('num_employees')),
                'total_assets': safe_bigint(row.get('total_assets')),
                'total_expenses': safe_bigint(row.get('total_expenses')),
                'ntee_code': (row.get('ntee_code') or '').strip()[:10] or None,
                'activity_description': (row.get('activity_desc') or '').strip()[:500] or None,
                'source_file': (row.get('filename') or '').strip(),
            }

    records = list(ein_records.values())

    print(f"\nCSV Summary:")
    print(f"  Total rows:        {total_rows:,}")
    print(f"  Errors:            {error_rows:,}")
    print(f"  Skipped 990T:      {skipped_990t:,}")
    print(f"  Skipped no EIN:    {skipped_no_ein:,}")
    print(f"  Skipped no state:  {skipped_no_state:,}")
    print(f"  Unique EINs:       {len(records):,}")

    return records


def bulk_insert(conn, records):
    """Bulk insert records using COPY for speed."""
    cur = conn.cursor()

    # Truncate existing data
    cur.execute("TRUNCATE TABLE national_990_filers RESTART IDENTITY;")

    # Use StringIO + COPY for fast loading
    columns = [
        'ein', 'business_name', 'name_normalized', 'street_address',
        'city', 'state', 'zip_code', 'form_type', 'tax_year',
        'total_revenue', 'total_employees', 'total_assets', 'total_expenses',
        'ntee_code', 'activity_description', 'source_file'
    ]

    buf = io.StringIO()
    for rec in records:
        values = []
        for col in columns:
            val = rec.get(col)
            if val is None:
                values.append('\\N')
            else:
                # Escape tabs and newlines for COPY format
                val = str(val).replace('\\', '\\\\').replace('\t', ' ').replace('\n', ' ').replace('\r', '')
                values.append(val)
        buf.write('\t'.join(values) + '\n')

    buf.seek(0)
    cur.copy_from(buf, 'national_990_filers', columns=columns, null='\\N')
    conn.commit()

    # Verify
    cur.execute("SELECT COUNT(*) FROM national_990_filers;")
    count = cur.fetchone()[0]
    print(f"\nInserted {count:,} records into national_990_filers.")
    return count


def update_ny_990_filers(conn):
    """Update ny_990_filers with new/newer NY records from national table."""
    cur = conn.cursor()

    # Check if ny_990_filers exists
    cur.execute("""
        SELECT EXISTS (
            SELECT FROM information_schema.tables
            WHERE table_name = 'ny_990_filers'
        );
    """)
    if not cur.fetchone()[0]:
        print("ny_990_filers table does not exist, skipping update.")
        return

    # Get current count
    cur.execute("SELECT COUNT(*) FROM ny_990_filers;")
    before_count = cur.fetchone()[0]

    # Get ny_990_filers columns to understand schema
    cur.execute("""
        SELECT column_name FROM information_schema.columns
        WHERE table_name = 'ny_990_filers'
        ORDER BY ordinal_position;
    """)
    ny_columns = [r[0] for r in cur.fetchall()]
    print(f"\nny_990_filers columns: {ny_columns}")
    print(f"Current ny_990_filers count: {before_count:,}")

    # Insert new NY records not already in ny_990_filers (by EIN)
    # We need to map national columns to ny_990_filers columns
    # First check what columns overlap
    cur.execute("""
        SELECT column_name FROM information_schema.columns
        WHERE table_name = 'national_990_filers'
        ORDER BY ordinal_position;
    """)
    nat_columns = [r[0] for r in cur.fetchall()]
    print(f"national_990_filers columns: {nat_columns}")

    # ny_990_filers uses: address (not street_address), return_type (not form_type)
    # and lacks: total_expenses, ntee_code

    # Insert new NY EINs not in ny_990_filers
    cur.execute("""
        INSERT INTO ny_990_filers (ein, business_name, name_normalized,
            address, city, state, zip_code, return_type, tax_year,
            total_revenue, total_employees, total_assets,
            activity_description, source_file)
        SELECT n.ein, n.business_name, n.name_normalized,
            n.street_address, n.city, n.state, n.zip_code, n.form_type, n.tax_year,
            n.total_revenue, n.total_employees, n.total_assets,
            n.activity_description, n.source_file
        FROM national_990_filers n
        WHERE n.state = 'NY'
        AND NOT EXISTS (
            SELECT 1 FROM ny_990_filers ny WHERE ny.ein = n.ein
        );
    """)
    new_inserted = cur.rowcount
    print(f"  New NY records inserted: {new_inserted:,}")

    # Update existing NY records if national has newer tax_year
    cur.execute("""
        UPDATE ny_990_filers ny
        SET business_name = n.business_name,
            name_normalized = n.name_normalized,
            address = n.street_address,
            city = n.city,
            zip_code = n.zip_code,
            return_type = n.form_type,
            tax_year = n.tax_year,
            total_revenue = n.total_revenue,
            total_employees = n.total_employees,
            total_assets = n.total_assets,
            activity_description = n.activity_description,
            source_file = n.source_file
        FROM national_990_filers n
        WHERE ny.ein = n.ein
        AND n.state = 'NY'
        AND n.tax_year > COALESCE(ny.tax_year, 0);
    """)
    updated = cur.rowcount
    print(f"  Existing NY records updated (newer year): {updated:,}")

    conn.commit()

    cur.execute("SELECT COUNT(*) FROM ny_990_filers;")
    after_count = cur.fetchone()[0]
    print(f"  ny_990_filers: {before_count:,} -> {after_count:,}")


def match_to_f7(conn):
    """Match national 990 to F7 employers by normalized name + state."""
    cur = conn.cursor()

    print("\n--- Matching to F7 by name + state ---")

    # F7 has no EIN column. Match by normalized name + state.
    cur.execute("""
        SELECT COUNT(DISTINCT n.ein) as matched_eins,
               COUNT(DISTINCT f.employer_id) as matched_f7
        FROM national_990_filers n
        JOIN f7_employers_deduped f
          ON n.name_normalized = f.employer_name_aggressive
          AND n.state = f.state;
    """)
    row = cur.fetchone()
    print(f"  990 EINs matched to F7 (name+state): {row[0]:,}")
    print(f"  Distinct F7 employers matched:       {row[1]:,}")

    # Also match by name + state + city for higher confidence
    cur.execute("""
        SELECT COUNT(DISTINCT n.ein) as matched_eins,
               COUNT(DISTINCT f.employer_id) as matched_f7
        FROM national_990_filers n
        JOIN f7_employers_deduped f
          ON n.name_normalized = f.employer_name_aggressive
          AND n.state = f.state
          AND n.city = UPPER(f.city);
    """)
    row = cur.fetchone()
    print(f"  990 EINs matched to F7 (name+state+city): {row[0]:,}")
    print(f"  Distinct F7 employers matched:            {row[1]:,}")


def match_to_mergent(conn):
    """Match national 990 to Mergent employers by EIN."""
    cur = conn.cursor()

    print("\n--- Matching to Mergent by EIN ---")

    cur.execute("""
        SELECT COUNT(DISTINCT n.ein) as matched_eins,
               COUNT(DISTINCT m.duns) as matched_mergent
        FROM national_990_filers n
        JOIN mergent_employers m ON n.ein = m.ein
        WHERE m.ein IS NOT NULL AND m.ein != '';
    """)
    row = cur.fetchone()
    print(f"  990 EINs matched to Mergent: {row[0]:,}")
    print(f"  Distinct Mergent employers:  {row[1]:,}")

    # Show what we gain: employee count enrichment
    cur.execute("""
        SELECT COUNT(*) as enrichable
        FROM mergent_employers m
        JOIN national_990_filers n ON m.ein = n.ein
        WHERE n.total_employees IS NOT NULL
        AND n.total_employees > 0
        AND (m.employees_site IS NULL OR m.employees_site = 0);
    """)
    enrichable = cur.fetchone()[0]
    print(f"  Mergent employers enrichable with 990 employee count: {enrichable:,}")

    # Revenue enrichment
    cur.execute("""
        SELECT COUNT(*) as enrichable
        FROM mergent_employers m
        JOIN national_990_filers n ON m.ein = n.ein
        WHERE n.total_revenue IS NOT NULL
        AND n.total_revenue > 0
        AND (m.sales_amount IS NULL OR m.sales_amount = 0);
    """)
    enrichable_rev = cur.fetchone()[0]
    print(f"  Mergent employers enrichable with 990 revenue:        {enrichable_rev:,}")


def print_summary(conn):
    """Print summary statistics."""
    cur = conn.cursor()

    print("\n" + "=" * 60)
    print("NATIONAL 990 FILERS - SUMMARY")
    print("=" * 60)

    # Total count
    cur.execute("SELECT COUNT(*) FROM national_990_filers;")
    total = cur.fetchone()[0]
    print(f"\nTotal unique filers: {total:,}")

    # By form type
    print("\nBy form type:")
    cur.execute("""
        SELECT form_type, COUNT(*) as cnt
        FROM national_990_filers
        GROUP BY form_type
        ORDER BY cnt DESC;
    """)
    for row in cur.fetchall():
        print(f"  {row[0] or 'UNKNOWN':<10} {row[1]:>10,}")

    # By tax year
    print("\nBy tax year:")
    cur.execute("""
        SELECT tax_year, COUNT(*) as cnt
        FROM national_990_filers
        GROUP BY tax_year
        ORDER BY tax_year DESC
        LIMIT 10;
    """)
    for row in cur.fetchall():
        print(f"  {row[0] or 0:<6} {row[1]:>10,}")

    # Top 10 states
    print("\nTop 15 states:")
    cur.execute("""
        SELECT state, COUNT(*) as cnt
        FROM national_990_filers
        GROUP BY state
        ORDER BY cnt DESC
        LIMIT 15;
    """)
    for row in cur.fetchall():
        print(f"  {row[0]:<4} {row[1]:>10,}")

    # Employee data coverage
    cur.execute("""
        SELECT
            COUNT(*) as total,
            COUNT(total_employees) FILTER (WHERE total_employees > 0) as has_employees,
            COUNT(total_revenue) FILTER (WHERE total_revenue > 0) as has_revenue,
            COUNT(ntee_code) FILTER (WHERE ntee_code IS NOT NULL) as has_ntee
        FROM national_990_filers;
    """)
    row = cur.fetchone()
    print(f"\nData coverage:")
    print(f"  Has employee count: {row[1]:,} ({row[1]/row[0]*100:.1f}%)")
    print(f"  Has revenue:        {row[2]:,} ({row[2]/row[0]*100:.1f}%)")
    print(f"  Has NTEE code:      {row[3]:,} ({row[3]/row[0]*100:.1f}%)")

    # Employees distribution
    cur.execute("""
        SELECT
            COUNT(*) FILTER (WHERE total_employees BETWEEN 1 AND 10) as small,
            COUNT(*) FILTER (WHERE total_employees BETWEEN 11 AND 50) as medium,
            COUNT(*) FILTER (WHERE total_employees BETWEEN 51 AND 250) as large,
            COUNT(*) FILTER (WHERE total_employees BETWEEN 251 AND 1000) as xlarge,
            COUNT(*) FILTER (WHERE total_employees > 1000) as enterprise
        FROM national_990_filers
        WHERE total_employees > 0;
    """)
    row = cur.fetchone()
    print(f"\nEmployee size distribution:")
    print(f"  1-10:      {row[0]:>10,}")
    print(f"  11-50:     {row[1]:>10,}")
    print(f"  51-250:    {row[2]:>10,}")
    print(f"  251-1000:  {row[3]:>10,}")
    print(f"  1000+:     {row[4]:>10,}")


def main():
    import argparse
    parser = argparse.ArgumentParser(description='Load national 990 data into database')
    parser.add_argument('--csv', default='data/national_990_extract.csv',
                       help='Path to national 990 extract CSV')
    args = parser.parse_args()

    csv_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        args.csv
    )

    if not os.path.exists(csv_path):
        print(f"Error: CSV not found: {csv_path}")
        print("Run extract_990_data.py first to generate the CSV.")
        sys.exit(1)

    print(f"CSV path: {csv_path}")
    print(f"Connecting to database...")

    conn = psycopg2.connect(**DB_CONFIG)

    try:
        # Step 1: Create table
        create_table(conn)

        # Step 2: Load and dedup CSV
        records = load_csv_deduped(csv_path)

        # Step 3: Bulk insert
        bulk_insert(conn, records)

        # Step 4: Update ny_990_filers
        update_ny_990_filers(conn)

        # Step 5: Match to F7 by name
        match_to_f7(conn)

        # Step 6: Match to Mergent
        match_to_mergent(conn)

        # Step 7: Summary
        print_summary(conn)

    finally:
        conn.close()

    print("\nDone!")


if __name__ == '__main__':
    main()
