"""
Submit geocoding batches to Census Bureau API and apply results.

Reads batch CSV files from data/geocoding_batch_*.csv, submits to the Census
Bureau batch geocoder, parses results, and updates f7_employers_deduped.

For PO Box addresses, falls back to ZIP centroid coordinates derived from
existing geocoded records in the same ZIP code.

Census Bureau API:
    URL: https://geocoding.geo.census.gov/geocoder/locations/addressbatch
    Method: POST multipart/form-data
    Fields: addressFile (CSV), benchmark, returntype

Usage:
    py scripts/cleanup/run_geocoding.py                # dry-run (default)
    py scripts/cleanup/run_geocoding.py --apply        # apply to DB
    py scripts/cleanup/run_geocoding.py --po-box-only  # only process PO Box fallback
"""

import csv
import glob
import io
import os
import sys
import time
import psycopg2
from psycopg2.extras import RealDictCursor

try:
    import requests
except ImportError:
    print("ERROR: 'requests' package required. Install with: pip install requests")
    sys.exit(1)


CENSUS_API_URL = "https://geocoding.geo.census.gov/geocoder/locations/addressbatch"
BENCHMARK = "Public_AR_Current"
DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'data')
MAX_RETRIES = 3
RETRY_DELAY = 10       # seconds between retries
BATCH_DELAY = 1        # seconds between batch submissions
API_TIMEOUT = 120      # seconds per API call


def get_connection():
    return psycopg2.connect(
        host='localhost',
        dbname='olms_multiyear',
        user='postgres',
        password='Juniordog33!'
    )


def submit_batch(csv_path):
    """Submit a CSV batch to Census Bureau geocoder. Returns list of result dicts."""
    results = []

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            with open(csv_path, 'rb') as f:
                response = requests.post(
                    CENSUS_API_URL,
                    files={'addressFile': ('batch.csv', f, 'text/csv')},
                    data={
                        'benchmark': BENCHMARK,
                        'returntype': 'locations',
                    },
                    timeout=API_TIMEOUT,
                )
            response.raise_for_status()

            # Parse CSV response
            reader = csv.reader(io.StringIO(response.text))
            for row in reader:
                if len(row) < 5:
                    continue

                record_id = row[0].strip().strip('"')
                input_addr = row[1].strip().strip('"') if len(row) > 1 else ''
                match_status = row[2].strip().strip('"') if len(row) > 2 else ''
                match_type = row[3].strip().strip('"') if len(row) > 3 else ''
                matched_addr = row[4].strip().strip('"') if len(row) > 4 else ''

                lat = None
                lon = None
                if match_status == 'Match' and len(row) > 5:
                    coords = row[5].strip().strip('"')
                    if ',' in coords:
                        parts = coords.split(',')
                        try:
                            lon = float(parts[0])
                            lat = float(parts[1])
                        except (ValueError, IndexError):
                            pass

                results.append({
                    'employer_id': record_id,
                    'match': match_status == 'Match',
                    'match_type': match_type,
                    'matched_address': matched_addr,
                    'latitude': lat,
                    'longitude': lon,
                })

            return results

        except requests.exceptions.Timeout:
            print("    Timeout on attempt %d/%d" % (attempt, MAX_RETRIES))
        except requests.exceptions.RequestException as e:
            print("    Request error on attempt %d/%d: %s" % (attempt, MAX_RETRIES, str(e)[:100]))

        if attempt < MAX_RETRIES:
            print("    Retrying in %d seconds..." % RETRY_DELAY)
            time.sleep(RETRY_DELAY)

    print("    FAILED after %d attempts" % MAX_RETRIES)
    return results


def build_zip_centroids(cur):
    """Build ZIP centroid lookup from existing geocoded records."""
    cur.execute("""
        SELECT
            LEFT(zip, 5) AS zip5,
            AVG(latitude) AS avg_lat,
            AVG(longitude) AS avg_lon,
            COUNT(*) AS cnt
        FROM f7_employers_deduped
        WHERE latitude IS NOT NULL
          AND zip IS NOT NULL AND TRIM(zip) != ''
        GROUP BY LEFT(zip, 5)
        HAVING COUNT(*) >= 1
    """)
    centroids = {}
    for row in cur.fetchall():
        centroids[row['zip5']] = {
            'latitude': float(row['avg_lat']),
            'longitude': float(row['avg_lon']),
            'count': row['cnt'],
        }
    return centroids


def process_po_boxes(cur, apply_mode, centroids):
    """Process PO Box addresses using ZIP centroid fallback."""
    po_box_file = os.path.join(DATA_DIR, 'geocoding_po_boxes.csv')

    if not os.path.exists(po_box_file):
        print("\n  No PO Box file found at %s" % po_box_file)
        print("  Run prepare_geocoding_batch.py first.")
        return 0, 0

    total = 0
    matched = 0
    updated = 0

    with open(po_box_file, 'r', encoding='utf-8') as f:
        reader = csv.reader(f)
        for row in reader:
            if len(row) < 5:
                continue
            total += 1
            employer_id = row[0]
            zip_code = row[4].strip()
            zip5 = zip_code[:5] if zip_code else ''

            if zip5 in centroids:
                matched += 1
                c = centroids[zip5]
                if apply_mode:
                    cur.execute("""
                        UPDATE f7_employers_deduped
                        SET latitude = %s,
                            longitude = %s,
                            geocode_status = 'ZIP_CENTROID'
                        WHERE employer_id = %s
                          AND latitude IS NULL
                    """, (c['latitude'], c['longitude'], employer_id))
                    if cur.rowcount > 0:
                        updated += 1

    print("\n--- PO Box ZIP Centroid Fallback ---")
    print("  PO Box records: %d" % total)
    print("  ZIP centroids found: %d" % matched)
    print("  ZIP centroids missing: %d" % (total - matched))
    if apply_mode:
        print("  Records updated: %d" % updated)

    return total, matched


def main():
    apply_mode = '--apply' in sys.argv
    po_box_only = '--po-box-only' in sys.argv

    conn = get_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)

    print("=" * 70)
    print("CENSUS BUREAU BATCH GEOCODING")
    print("Mode: %s" % ("APPLY" if apply_mode else "DRY-RUN"))
    if po_box_only:
        print("PO Box only mode")
    print("=" * 70)

    # Get current stats
    cur.execute("""
        SELECT
            COUNT(*) AS total,
            COUNT(*) FILTER (WHERE latitude IS NOT NULL) AS geocoded,
            COUNT(*) FILTER (WHERE latitude IS NULL) AS not_geocoded
        FROM f7_employers_deduped
    """)
    stats = cur.fetchone()
    print("\nBefore:")
    print("  Total: %d | Geocoded: %d | Not geocoded: %d | Coverage: %.1f%%" % (
        stats['total'], stats['geocoded'], stats['not_geocoded'],
        100.0 * stats['geocoded'] / stats['total'] if stats['total'] > 0 else 0
    ))

    # Build ZIP centroids for PO Box fallback
    print("\nBuilding ZIP centroid lookup from existing geocoded records...")
    centroids = build_zip_centroids(cur)
    print("  ZIP centroids available: %d" % len(centroids))

    total_submitted = 0
    total_matched = 0
    total_no_match = 0
    batches_processed = 0

    if not po_box_only:
        # Find batch files
        batch_pattern = os.path.join(DATA_DIR, 'geocoding_batch_*.csv')
        batch_files = sorted(glob.glob(batch_pattern))

        if not batch_files:
            print("\nNo batch files found at: %s" % batch_pattern)
            print("Run prepare_geocoding_batch.py first.")
        else:
            print("\nFound %d batch file(s)" % len(batch_files))

            for batch_file in batch_files:
                batches_processed += 1
                filename = os.path.basename(batch_file)

                # Count records in file
                with open(batch_file, 'r', encoding='utf-8') as f:
                    line_count = sum(1 for line in f if line.strip())

                print("\n--- Batch %d: %s (%d records) ---" % (
                    batches_processed, filename, line_count))

                # Submit to Census API
                print("  Submitting to Census Bureau geocoder...")
                results = submit_batch(batch_file)

                batch_matched = sum(1 for r in results if r['match'])
                batch_no_match = sum(1 for r in results if not r['match'])
                total_submitted += len(results)
                total_matched += batch_matched
                total_no_match += batch_no_match

                match_rate = 100.0 * batch_matched / len(results) if results else 0
                print("  Results: %d matched, %d no match (%.1f%% match rate)" % (
                    batch_matched, batch_no_match, match_rate))

                # Apply matches
                if apply_mode:
                    applied = 0
                    for r in results:
                        if r['match'] and r['latitude'] and r['longitude']:
                            cur.execute("""
                                UPDATE f7_employers_deduped
                                SET latitude = %s,
                                    longitude = %s,
                                    geocode_status = 'CENSUS_MATCH'
                                WHERE employer_id = %s
                                  AND latitude IS NULL
                            """, (r['latitude'], r['longitude'], r['employer_id']))
                            if cur.rowcount > 0:
                                applied += 1
                    print("  Applied: %d records updated" % applied)

                # Show sample matches
                sample_matches = [r for r in results if r['match']][:3]
                if sample_matches:
                    print("  Sample matches:")
                    for s in sample_matches:
                        print("    %s -> %.4f, %.4f (%s)" % (
                            s['employer_id'][:12],
                            s['latitude'] or 0,
                            s['longitude'] or 0,
                            s['match_type'],
                        ))

                # Pause between batches
                if batches_processed < len(batch_files):
                    print("  Pausing %d second(s) before next batch..." % BATCH_DELAY)
                    time.sleep(BATCH_DELAY)

    # Process PO Box records
    po_total, po_matched = process_po_boxes(cur, apply_mode, centroids)

    # Commit if applying
    if apply_mode:
        conn.commit()

    # Final stats
    cur.execute("""
        SELECT
            COUNT(*) AS total,
            COUNT(*) FILTER (WHERE latitude IS NOT NULL) AS geocoded,
            COUNT(*) FILTER (WHERE latitude IS NULL) AS not_geocoded,
            COUNT(*) FILTER (WHERE geocode_status = 'CENSUS_MATCH') AS census_match,
            COUNT(*) FILTER (WHERE geocode_status = 'ZIP_CENTROID') AS zip_centroid,
            COUNT(*) FILTER (WHERE geocode_status = 'geocoded') AS original_geocoded,
            COUNT(*) FILTER (WHERE geocode_status = 'failed') AS still_failed
        FROM f7_employers_deduped
    """)
    final = cur.fetchone()

    print("\n" + "=" * 70)
    print("FINAL SUMMARY")
    print("=" * 70)
    print("\nCensus Bureau API:")
    print("  Batches processed: %d" % batches_processed)
    print("  Total submitted: %d" % total_submitted)
    print("  Matched: %d" % total_matched)
    print("  No match: %d" % total_no_match)
    if total_submitted > 0:
        print("  Overall match rate: %.1f%%" % (100.0 * total_matched / total_submitted))

    print("\nPO Box fallback:")
    print("  PO Box records: %d" % po_total)
    print("  ZIP centroids applied: %d" % po_matched)

    print("\nGeocoding coverage:")
    print("  Total employers: %d" % final['total'])
    print("  Geocoded (all methods): %d" % final['geocoded'])
    print("  Not geocoded: %d" % final['not_geocoded'])
    print("  Coverage: %.1f%%" % (
        100.0 * final['geocoded'] / final['total'] if final['total'] > 0 else 0))

    print("\nBy method:")
    print("  Original geocoded: %d" % (final['original_geocoded'] or 0))
    print("  Census match: %d" % (final['census_match'] or 0))
    print("  ZIP centroid: %d" % (final['zip_centroid'] or 0))
    print("  Failed: %d" % (final['still_failed'] or 0))

    if not apply_mode:
        print("\n[DRY-RUN] No changes made. Use --apply to commit updates.")
    else:
        print("\n[APPLIED] Changes committed to database.")

    conn.close()


if __name__ == '__main__':
    main()
