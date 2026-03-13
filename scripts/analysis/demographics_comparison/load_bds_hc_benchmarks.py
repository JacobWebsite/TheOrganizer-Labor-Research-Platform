"""Parse BDS-HC bracket data into estimated benchmark percentages.

BDS-HC files contain firm counts by demographic composition BRACKETS
(e.g., "a) less than 10%"), not direct percentages. This script uses
bracket-midpoint weighted-average estimation.

Outputs: bds_hc_estimated_benchmarks table

Usage:
    py scripts/analysis/demographics_comparison/load_bds_hc_benchmarks.py
"""
import sys
import os
import csv
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..')))
from db_config import get_connection

sys.path.insert(0, os.path.dirname(__file__))
from config import BDS_DIR
from bds_hc_check import BUCKET_RANGES, _load_bds_file, _size_bucket

SCRIPT_DIR = os.path.dirname(__file__)


def estimate_pct_from_brackets(data, geo_key, size_bucket):
    """Compute estimated percentage from bracket data using midpoint weighting.

    Returns (est_pct, dominant_bucket, concentration, total_emp) or (None, None, 0, 0).
    """
    bucket_emps = {}
    total_emp = 0

    for bucket_letter in 'abcdef':
        # Try multiple key formats
        for key in [
            (geo_key, size_bucket, bucket_letter),
            (geo_key, size_bucket, '%s)' % bucket_letter),
        ]:
            if key in data:
                emp = data[key].get('emp', 0)
                if emp > 0:
                    bucket_emps[bucket_letter] = emp
                    total_emp += emp
                break
        else:
            # Try label format
            for label_key in data:
                if (label_key[0] == geo_key and
                    label_key[1] == size_bucket and
                    isinstance(label_key[2], str) and
                    label_key[2].startswith(bucket_letter + ')')):
                    emp = data[label_key].get('emp', 0)
                    if emp > 0:
                        bucket_emps[bucket_letter] = emp
                        total_emp += emp
                    break

    if total_emp == 0:
        return None, None, 0.0, 0

    # Weighted average using midpoints
    est_pct = 0.0
    for bucket, emp in bucket_emps.items():
        if bucket in BUCKET_RANGES:
            _, _, midpoint = BUCKET_RANGES[bucket]
            est_pct += midpoint * emp / total_emp

    # Dominant bucket and concentration
    dominant_bucket = max(bucket_emps.keys(), key=lambda b: bucket_emps[b])
    concentration = bucket_emps[dominant_bucket] / total_emp

    return round(est_pct, 2), dominant_bucket, round(concentration, 3), total_emp


def process_bds_files():
    """Process all BDS-HC files and compute estimated benchmarks."""
    results = []

    # Sector-level files
    file_configs = [
        ('bds2022_sec_ifzc_im_r.csv', 'sector', 'im_race', 'race', 'sector'),
        ('bds2022_sec_ifzc_im_sex.csv', 'sector', 'im_sex', 'sex', 'sector'),
        ('bds2022_sec_ifzc_im_h.csv', 'sector', 'im_hispanic', 'hispanic', 'sector'),
    ]

    # State-level files
    state_configs = [
        ('bds2022_st_ifzc_im_r.csv', 'st', 'im_race', 'race', 'state'),
        ('bds2022_st_ifzc_im_sex.csv', 'st', 'im_sex', 'sex', 'state'),
        ('bds2022_st_ifzc_im_h.csv', 'st', 'im_hispanic', 'hispanic', 'state'),
    ]

    all_configs = file_configs + state_configs

    for filename, geo_col, demo_col, dimension, geo_type in all_configs:
        filepath = os.path.join(BDS_DIR, filename)
        if not os.path.exists(filepath):
            print('  Skipping %s (not found)' % filename)
            continue

        print('  Processing %s...' % filename)
        data = _load_bds_file(filename, geo_col, demo_col)
        if not data:
            print('    No data loaded')
            continue

        # Get unique (geo_key, size_bucket) combinations
        seen = set()
        for key in data:
            geo_key, size_bucket, _ = key
            if (geo_key, size_bucket) not in seen:
                seen.add((geo_key, size_bucket))

        for geo_key, size_bucket in seen:
            est_pct, dominant, concentration, total_emp = estimate_pct_from_brackets(
                data, geo_key, size_bucket)
            if est_pct is not None:
                results.append({
                    'geo_type': geo_type,
                    'geo_key': geo_key,
                    'size_bucket': size_bucket,
                    'dimension': dimension,
                    'est_pct': est_pct,
                    'dominant_bucket': dominant,
                    'concentration': concentration,
                    'total_emp': total_emp,
                })

    print('Computed %d benchmark estimates' % len(results))
    return results


def load_to_db(results):
    """Create table and insert."""
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS bds_hc_estimated_benchmarks (
            geo_type VARCHAR(10),
            geo_key VARCHAR(10),
            size_bucket VARCHAR(20),
            dimension VARCHAR(10),
            est_pct FLOAT,
            dominant_bucket CHAR(1),
            concentration FLOAT,
            total_emp INTEGER,
            PRIMARY KEY (geo_type, geo_key, size_bucket, dimension)
        )
    """)
    conn.commit()

    cur.execute("DELETE FROM bds_hc_estimated_benchmarks")
    conn.commit()

    insert_sql = """
        INSERT INTO bds_hc_estimated_benchmarks
        (geo_type, geo_key, size_bucket, dimension, est_pct,
         dominant_bucket, concentration, total_emp)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
    """

    batch_size = 500
    for i in range(0, len(results), batch_size):
        batch = results[i:i + batch_size]
        rows = [(
            r['geo_type'], r['geo_key'], r['size_bucket'], r['dimension'],
            r['est_pct'], r['dominant_bucket'], r['concentration'], r['total_emp'],
        ) for r in batch]
        cur.executemany(insert_sql, rows)
        conn.commit()

    cur.execute("SELECT COUNT(*) FROM bds_hc_estimated_benchmarks")
    count = cur.fetchone()[0]
    print('Loaded %d rows into bds_hc_estimated_benchmarks' % count)

    # Spot check
    cur.execute("""
        SELECT geo_type, geo_key, size_bucket, dimension, est_pct,
               dominant_bucket, concentration
        FROM bds_hc_estimated_benchmarks
        WHERE geo_type = 'sector'
        ORDER BY total_emp DESC LIMIT 5
    """)
    print('')
    print('Top 5 sector estimates by employment:')
    for row in cur.fetchall():
        print('  %s/%s/%s  %s: %.1f%%  dom=%s  conc=%.2f' % (
            row[0], row[1], row[2], row[3], row[4], row[5], row[6]))

    conn.close()


def main():
    t0 = time.time()
    print('LOAD BDS-HC BENCHMARKS')
    print('=' * 60)

    results = process_bds_files()

    if results:
        load_to_db(results)
    else:
        print('No results to load.')

    print('')
    print('Done in %.0fs' % (time.time() - t0))


if __name__ == '__main__':
    main()
