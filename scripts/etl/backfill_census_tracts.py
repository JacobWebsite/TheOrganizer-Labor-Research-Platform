"""
Backfill census_tract for employers already geocoded but missing tract FIPS.

Two strategies:
1. For employers with real addresses: re-submit to Census Bureau geographies
   batch endpoint to get tract FIPS.
2. For ZIP_CENTROID employers (no real address): use FCC Area API to reverse
   geocode lat/lng to census block, extract tract (first 11 digits).

Usage:
    py scripts/etl/backfill_census_tracts.py                # dry-run
    py scripts/etl/backfill_census_tracts.py --apply        # apply to DB
    py scripts/etl/backfill_census_tracts.py --fcc-only     # only FCC reverse geocode
"""

import csv
import io
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
from db_config import get_connection
from psycopg2.extras import RealDictCursor

try:
    import requests
except ImportError:
    print("ERROR: 'requests' package required. Install with: pip install requests")
    sys.exit(1)

CENSUS_GEO_URL = "https://geocoding.geo.census.gov/geocoder/geographies/addressbatch"
FCC_API_URL = "https://geo.fcc.gov/api/census/block/find"
BENCHMARK = "Public_AR_Current"
BATCH_SIZE = 1000
DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), 'data')
MAX_RETRIES = 3
RETRY_DELAY = 10
API_TIMEOUT = 120


def get_employers_needing_tract(cur, fcc_only=False):
    """Get employers with lat/lng but no census_tract."""
    if fcc_only:
        cur.execute("""
            SELECT employer_id, latitude, longitude, geocode_status
            FROM f7_employers_deduped
            WHERE latitude IS NOT NULL
              AND census_tract IS NULL
              AND geocode_status = 'ZIP_CENTROID'
        """)
    else:
        cur.execute("""
            SELECT employer_id, street, city, state, zip,
                   latitude, longitude, geocode_status
            FROM f7_employers_deduped
            WHERE latitude IS NOT NULL
              AND census_tract IS NULL
        """)
    return cur.fetchall()


def submit_address_batch(csv_content):
    """Submit CSV content to Census geographies batch endpoint."""
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = requests.post(
                CENSUS_GEO_URL,
                files={'addressFile': ('batch.csv', csv_content.encode('utf-8'), 'text/csv')},
                data={
                    'benchmark': BENCHMARK,
                    'returntype': 'geographies',
                    'vintage': 'Current_Current',
                },
                timeout=API_TIMEOUT,
            )
            response.raise_for_status()

            results = {}
            reader = csv.reader(io.StringIO(response.text))
            for row in reader:
                if len(row) < 5:
                    continue
                record_id = row[0].strip().strip('"')
                match_status = row[2].strip().strip('"') if len(row) > 2 else ''

                if match_status == 'Match' and len(row) > 10:
                    st_fips = row[8].strip().strip('"') if len(row) > 8 else ''
                    co_fips = row[9].strip().strip('"') if len(row) > 9 else ''
                    tract_code = row[10].strip().strip('"') if len(row) > 10 else ''
                    if st_fips and co_fips and tract_code:
                        results[record_id] = st_fips + co_fips + tract_code
            return results

        except requests.exceptions.Timeout:
            print("    Timeout on attempt %d/%d" % (attempt, MAX_RETRIES))
        except requests.exceptions.RequestException as e:
            print("    Request error on attempt %d/%d: %s" % (attempt, MAX_RETRIES, str(e)[:100]))

        if attempt < MAX_RETRIES:
            time.sleep(RETRY_DELAY)

    return {}


def fcc_reverse_geocode(lat, lng):
    """Use FCC Area API to get census tract from lat/lng."""
    try:
        response = requests.get(
            FCC_API_URL,
            params={'latitude': lat, 'longitude': lng, 'format': 'json'},
            timeout=15,
        )
        response.raise_for_status()
        data = response.json()
        block_fips = data.get('Block', {}).get('FIPS', '')
        if len(block_fips) >= 11:
            return block_fips[:11]  # state(2) + county(3) + tract(6)
    except Exception:
        pass
    return None


def main():
    apply_mode = '--apply' in sys.argv
    fcc_only = '--fcc-only' in sys.argv

    conn = get_connection(cursor_factory=RealDictCursor)
    cur = conn.cursor()

    print("=" * 70)
    print("BACKFILL CENSUS TRACTS")
    print("Mode: %s" % ("APPLY" if apply_mode else "DRY-RUN"))
    if fcc_only:
        print("FCC-only mode (ZIP_CENTROID employers)")
    print("=" * 70)

    employers = get_employers_needing_tract(cur, fcc_only)
    print("\nEmployers needing census_tract: %d" % len(employers))

    if not employers:
        print("Nothing to do.")
        conn.close()
        return

    # Split into address-based (Census batch) and coordinate-based (FCC)
    address_employers = []
    coord_employers = []

    for emp in employers:
        if emp.get('geocode_status') == 'ZIP_CENTROID' or fcc_only:
            coord_employers.append(emp)
        else:
            street = (emp.get('street') or '').strip()
            if street:
                address_employers.append(emp)
            else:
                coord_employers.append(emp)

    # --- Census Bureau batch geocoding for address-based ---
    census_found = 0
    if address_employers:
        print("\n--- Census Bureau Batch Geocoding (%d employers) ---" % len(address_employers))
        for batch_start in range(0, len(address_employers), BATCH_SIZE):
            batch = address_employers[batch_start:batch_start + BATCH_SIZE]
            batch_num = batch_start // BATCH_SIZE + 1
            print("  Batch %d (%d records)..." % (batch_num, len(batch)))

            # Build CSV
            lines = []
            for emp in batch:
                lines.append('"%s","%s","%s","%s","%s"' % (
                    emp['employer_id'],
                    (emp.get('street') or '').replace('"', ''),
                    (emp.get('city') or '').replace('"', ''),
                    (emp.get('state') or '').replace('"', ''),
                    (emp.get('zip') or '')[:5],
                ))
            csv_content = '\n'.join(lines)

            results = submit_address_batch(csv_content)
            census_found += len(results)
            print("    Matched: %d / %d" % (len(results), len(batch)))

            if apply_mode:
                applied = 0
                for eid, tract in results.items():
                    cur.execute("""
                        UPDATE f7_employers_deduped
                        SET census_tract = %s
                        WHERE employer_id = %s AND census_tract IS NULL
                    """, (tract, eid))
                    if cur.rowcount > 0:
                        applied += 1
                print("    Applied: %d" % applied)

            if batch_start + BATCH_SIZE < len(address_employers):
                time.sleep(1)

    # --- FCC reverse geocode for coordinate-based ---
    fcc_found = 0
    if coord_employers:
        print("\n--- FCC Reverse Geocode (%d employers) ---" % len(coord_employers))
        for i, emp in enumerate(coord_employers):
            if i > 0 and i % 100 == 0:
                print("  Progress: %d / %d (found %d)" % (i, len(coord_employers), fcc_found))
            tract = fcc_reverse_geocode(emp['latitude'], emp['longitude'])
            if tract:
                fcc_found += 1
                if apply_mode:
                    cur.execute("""
                        UPDATE f7_employers_deduped
                        SET census_tract = %s
                        WHERE employer_id = %s AND census_tract IS NULL
                    """, (tract, emp['employer_id']))
            # Rate limit FCC API
            if i % 50 == 49:
                time.sleep(0.5)

    if apply_mode:
        conn.commit()

    # Summary
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print("  Census batch matched: %d" % census_found)
    print("  FCC reverse geocoded: %d" % fcc_found)
    print("  Total tracts found: %d / %d" % (census_found + fcc_found, len(employers)))

    if not apply_mode:
        print("\n[DRY-RUN] No changes made. Use --apply to commit updates.")
    else:
        print("\n[APPLIED] Changes committed to database.")

    # Final stats
    cur.execute("""
        SELECT
            COUNT(*) AS total,
            COUNT(*) FILTER (WHERE census_tract IS NOT NULL) AS has_tract,
            COUNT(*) FILTER (WHERE latitude IS NOT NULL) AS geocoded
        FROM f7_employers_deduped
    """)
    stats = cur.fetchone()
    print("\nCoverage: %d / %d geocoded have tracts (%.1f%%)" % (
        stats['has_tract'], stats['geocoded'],
        100.0 * stats['has_tract'] / stats['geocoded'] if stats['geocoded'] > 0 else 0
    ))

    conn.close()


if __name__ == '__main__':
    main()
