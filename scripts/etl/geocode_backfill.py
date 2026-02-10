"""
Geocode backfill for F7 employers using city centroid fallback.

Strategy:
  1. Build city+state centroid map from already-geocoded employers
  2. Apply centroids to un-geocoded employers matching city+state
  3. For remaining (no city match), use state centroid
  4. Mark geocode_status = 'CITY_CENTROID' or 'STATE_CENTROID'

Usage:
    py scripts/etl/geocode_backfill.py              # Dry run
    py scripts/etl/geocode_backfill.py --apply       # Apply changes

Target: > 90% geocoded (up from 86%)
"""
import os
import sys
import argparse

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
from db_config import get_connection

# State centroids (approximate geographic center)
STATE_CENTROIDS = {
    'AL': (32.806671, -86.791130), 'AK': (61.370716, -152.404419),
    'AZ': (33.729759, -111.431221), 'AR': (34.969704, -92.373123),
    'CA': (36.116203, -119.681564), 'CO': (39.059811, -105.311104),
    'CT': (41.597782, -72.755371), 'DE': (39.318523, -75.507141),
    'DC': (38.897438, -77.026817), 'FL': (27.766279, -81.686783),
    'GA': (33.040619, -83.643074), 'HI': (21.094318, -157.498337),
    'ID': (44.240459, -114.478828), 'IL': (40.349457, -88.986137),
    'IN': (39.849426, -86.258278), 'IA': (42.011539, -93.210526),
    'KS': (38.526600, -96.726486), 'KY': (37.668140, -84.670067),
    'LA': (31.169546, -91.867805), 'ME': (44.693947, -69.381927),
    'MD': (39.063946, -76.802101), 'MA': (42.230171, -71.530106),
    'MI': (43.326618, -84.536095), 'MN': (45.694454, -93.900192),
    'MS': (32.741646, -89.678696), 'MO': (38.456085, -92.288368),
    'MT': (46.921925, -110.454353), 'NE': (41.125370, -98.268082),
    'NV': (38.313515, -117.055374), 'NH': (43.452492, -71.563896),
    'NJ': (40.298904, -74.521011), 'NM': (34.840515, -106.248482),
    'NY': (42.165726, -74.948051), 'NC': (35.630066, -79.806419),
    'ND': (47.528912, -99.784012), 'OH': (40.388783, -82.764915),
    'OK': (35.565342, -96.928917), 'OR': (44.572021, -122.070938),
    'PA': (40.590752, -77.209755), 'PR': (18.220833, -66.590149),
    'RI': (41.680893, -71.511780), 'SC': (33.856892, -80.945007),
    'SD': (44.299782, -99.438828), 'TN': (35.747845, -86.692345),
    'TX': (31.054487, -97.563461), 'UT': (40.150032, -111.862434),
    'VT': (44.045876, -72.710686), 'VA': (37.769337, -78.169968),
    'WA': (47.400902, -121.490494), 'WV': (38.491226, -80.954456),
    'WI': (44.268543, -89.616508), 'WY': (42.755966, -107.302490),
    'GU': (13.444304, 144.793731), 'VI': (18.335765, -64.896335),
    'AS': (-14.270972, -170.132217), 'MP': (15.097900, 145.673900),
}


def main():
    parser = argparse.ArgumentParser(description="Geocode backfill via city/state centroids")
    parser.add_argument('--apply', action='store_true', help='Apply changes')
    args = parser.parse_args()

    conn = get_connection()
    cur = conn.cursor()

    print("=" * 60)
    print("Geocode Backfill")
    print("=" * 60)

    # Current state
    cur.execute('SELECT COUNT(*) FROM f7_employers_deduped')
    total = cur.fetchone()[0]
    cur.execute('SELECT COUNT(*) FROM f7_employers_deduped WHERE latitude IS NOT NULL')
    already = cur.fetchone()[0]
    print(f"\nTotal employers: {total:,}")
    print(f"Already geocoded: {already:,} ({already/total:.1%})")
    print(f"Missing: {total - already:,}")

    # Build city+state centroid map from existing geocoded data
    print("\n--- Building city+state centroid map ---")
    cur.execute("""
        SELECT UPPER(city), state,
               PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY latitude) as med_lat,
               PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY longitude) as med_lon,
               COUNT(*) as cnt
        FROM f7_employers_deduped
        WHERE latitude IS NOT NULL AND longitude IS NOT NULL
          AND city IS NOT NULL AND state IS NOT NULL
          AND latitude BETWEEN 17 AND 72
          AND longitude BETWEEN -180 AND -60
        GROUP BY UPPER(city), state
        HAVING COUNT(*) >= 1
    """)
    city_centroids = {}
    for city, state, lat, lon, cnt in cur.fetchall():
        city_centroids[(city, state)] = (float(lat), float(lon), cnt)
    print(f"  City+state centroids: {len(city_centroids):,}")

    # Get un-geocoded employers
    cur.execute("""
        SELECT employer_id, city, state
        FROM f7_employers_deduped
        WHERE latitude IS NULL OR longitude IS NULL
        ORDER BY employer_id
    """)
    missing = cur.fetchall()

    city_matches = 0
    state_matches = 0
    no_match = 0
    updates = []

    for eid, city, state in missing:
        city_upper = (city or '').upper().strip()
        state_upper = (state or '').upper().strip()

        # Try city+state centroid
        if city_upper and state_upper and (city_upper, state_upper) in city_centroids:
            lat, lon, _ = city_centroids[(city_upper, state_upper)]
            updates.append((eid, lat, lon, 'CITY_CENTROID'))
            city_matches += 1
        elif state_upper and state_upper in STATE_CENTROIDS:
            lat, lon = STATE_CENTROIDS[state_upper]
            updates.append((eid, lat, lon, 'STATE_CENTROID'))
            state_matches += 1
        else:
            no_match += 1

    print(f"\n--- Results ---")
    print(f"  City centroid match: {city_matches:,}")
    print(f"  State centroid match: {state_matches:,}")
    print(f"  No match: {no_match:,}")
    new_total = already + city_matches + state_matches
    print(f"  New geocoded total: {new_total:,} ({new_total/total:.1%})")

    if args.apply:
        print(f"\n[APPLYING] Updating {len(updates):,} employers...")
        for eid, lat, lon, status in updates:
            cur.execute("""
                UPDATE f7_employers_deduped
                SET latitude = %s, longitude = %s, geocode_status = %s
                WHERE employer_id = %s
                  AND (latitude IS NULL OR longitude IS NULL)
            """, (lat, lon, status, eid))
        conn.commit()

        # Verify
        cur.execute('SELECT COUNT(*) FROM f7_employers_deduped WHERE latitude IS NOT NULL')
        final = cur.fetchone()[0]
        print(f"  Final geocoded: {final:,} ({final/total:.1%})")
        cur.execute("SELECT geocode_status, COUNT(*) FROM f7_employers_deduped GROUP BY geocode_status ORDER BY COUNT(*) DESC")
        print(f"  By status:")
        for r in cur.fetchall():
            print(f"    {r[0]}: {r[1]:,}")
    else:
        print(f"\n[DRY RUN] Use --apply to write changes.")

    conn.close()


if __name__ == '__main__':
    main()
