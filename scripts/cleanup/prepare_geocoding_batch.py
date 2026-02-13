"""
Export f7_employers_deduped records needing geocoding to Census Bureau-compatible CSV batches.

The Census Bureau batch geocoder expects CSV with columns (no header):
    Unique ID, Street Address, City, State, ZIP

Output files:
    data/geocoding_batch_001.csv, _002.csv, etc. (max 10,000 per file)
    data/geocoding_po_boxes.csv (PO Box addresses for ZIP centroid fallback)

Usage:
    py scripts/cleanup/prepare_geocoding_batch.py
"""

import csv
import os
import re
import psycopg2
from psycopg2.extras import RealDictCursor


def get_connection():
    return psycopg2.connect(
        host='localhost',
        dbname='olms_multiyear',
        user='postgres',
        password=os.environ.get('DB_PASSWORD', '')
    )


BATCH_SIZE = 10000
OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'data')

# PO Box patterns (case-insensitive)
PO_BOX_PATTERNS = [
    re.compile(r'^p\.?o\.?\s*box\b', re.IGNORECASE),
    re.compile(r'^post\s+office\s+box\b', re.IGNORECASE),
]

# Suite/apt removal patterns
SUITE_PATTERNS = [
    re.compile(r',?\s*(suite|ste\.?|apt\.?|unit|room|rm\.?|floor|fl\.?|bldg\.?|building)\s*[#.]?\s*\S+$', re.IGNORECASE),
    re.compile(r',?\s*#\s*\S+$'),
]


def is_po_box(street):
    """Check if address is a PO Box."""
    if not street:
        return False
    # Normalize: remove dots and extra spaces
    normalized = re.sub(r'\.', '', street).strip()
    for pattern in PO_BOX_PATTERNS:
        if pattern.search(normalized):
            return True
    return False


def clean_address(street):
    """Clean street address for Census Bureau geocoder."""
    if not street:
        return None

    # Take first line only (handle multi-line addresses)
    line = street.split('\n')[0].split('|')[0].split('\r')[0].strip()

    # Remove suite/apt/unit suffixes
    for pattern in SUITE_PATTERNS:
        line = pattern.sub('', line)

    # Remove double spaces
    line = re.sub(r'\s+', ' ', line).strip()

    # Remove trailing commas
    line = line.rstrip(',').strip()

    if not line:
        return None

    return line


def clean_zip(zip_code):
    """Normalize ZIP to 5 digits."""
    if not zip_code:
        return ''
    # Take first 5 characters (strip ZIP+4)
    z = re.sub(r'[^0-9]', '', str(zip_code))
    return z[:5] if len(z) >= 5 else z


def main():
    conn = get_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)

    print("=" * 70)
    print("GEOCODING BATCH PREPARATION")
    print("Census Bureau Batch Geocoder Format")
    print("=" * 70)

    # Query all records needing geocoding
    cur.execute("""
        SELECT
            employer_id,
            employer_name,
            street,
            city,
            state,
            zip,
            geocode_status
        FROM f7_employers_deduped
        WHERE latitude IS NULL
        ORDER BY state, city, employer_name
    """)
    rows = cur.fetchall()
    total_needing = len(rows)

    print("\nTotal records needing geocoding: %d" % total_needing)

    # Categorize records
    street_records = []   # Valid street addresses for Census geocoder
    po_box_records = []   # PO Box -> ZIP centroid
    no_address = []       # No street at all

    for row in rows:
        street = row['street']
        if not street or street.strip() == '':
            no_address.append(row)
        elif is_po_box(street):
            po_box_records.append(row)
        else:
            cleaned = clean_address(street)
            if cleaned:
                row['cleaned_street'] = cleaned
                street_records.append(row)
            else:
                no_address.append(row)

    print("  Valid street addresses: %d" % len(street_records))
    print("  PO Box addresses (ZIP centroid): %d" % len(po_box_records))
    print("  No address (cannot geocode): %d" % len(no_address))

    # Ensure output directory exists
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # Write street address batches
    batch_num = 0
    batch_files = []
    for i in range(0, len(street_records), BATCH_SIZE):
        batch_num += 1
        batch = street_records[i:i + BATCH_SIZE]
        filename = "geocoding_batch_%03d.csv" % batch_num
        filepath = os.path.join(OUTPUT_DIR, filename)

        with open(filepath, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            for row in batch:
                writer.writerow([
                    row['employer_id'],
                    row['cleaned_street'],
                    row['city'] or '',
                    row['state'] or '',
                    clean_zip(row['zip']),
                ])

        batch_files.append(filepath)
        print("\n  Written: %s (%d records)" % (filename, len(batch)))

        # Show sample
        sample = batch[:3]
        for s in sample:
            print("    %s | %s | %s, %s %s" % (
                s['employer_id'][:12],
                s['cleaned_street'][:40],
                s['city'] or '?',
                s['state'] or '?',
                clean_zip(s['zip']),
            ))
        if len(batch) > 3:
            print("    ... and %d more" % (len(batch) - 3))

    # Write PO Box file
    po_box_file = os.path.join(OUTPUT_DIR, 'geocoding_po_boxes.csv')
    if po_box_records:
        with open(po_box_file, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            for row in po_box_records:
                writer.writerow([
                    row['employer_id'],
                    row['street'] or '',
                    row['city'] or '',
                    row['state'] or '',
                    clean_zip(row['zip']),
                ])
        print("\n  Written: geocoding_po_boxes.csv (%d records)" % len(po_box_records))
    else:
        print("\n  No PO Box records to write.")

    # Write no-address file for reference
    no_addr_file = os.path.join(OUTPUT_DIR, 'geocoding_no_address.csv')
    if no_address:
        with open(no_addr_file, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(['employer_id', 'employer_name', 'city', 'state', 'zip'])
            for row in no_address:
                writer.writerow([
                    row['employer_id'],
                    row['employer_name'] or '',
                    row['city'] or '',
                    row['state'] or '',
                    clean_zip(row['zip']),
                ])
        print("  Written: geocoding_no_address.csv (%d records)" % len(no_address))

    # Summary
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print("  Total needing geocoding: %d" % total_needing)
    print("  Exportable street addresses: %d" % len(street_records))
    print("  PO Box (ZIP centroid fallback): %d" % len(po_box_records))
    print("  No address (cannot geocode): %d" % len(no_address))
    print("  Batch files created: %d (max %d per file)" % (batch_num, BATCH_SIZE))
    print("  Output directory: %s" % os.path.abspath(OUTPUT_DIR))

    # Address cleaning stats
    original_suite = sum(1 for r in street_records
                         if r['cleaned_street'] != (r['street'].split('\n')[0].split('|')[0].strip() if r['street'] else ''))
    print("\n  Addresses cleaned (suite/multiline removed): %d" % original_suite)

    conn.close()
    print("\nDone. Next step: run scripts/cleanup/run_geocoding.py to submit batches.")


if __name__ == '__main__':
    main()
