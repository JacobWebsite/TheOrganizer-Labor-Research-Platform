"""Build zip_tract_crosswalk table from existing LODES tract data.

Creates a mapping from ZIP codes to census tracts using:
1. zip_county_crosswalk (ZIP -> county)
2. cur_lodes_tract_metrics (county -> tracts with employment data)

For each ZIP, distributes business ratios across tracts in the
same county proportionally to tract employment.

Usage:
    py scripts/analysis/demographics_comparison/build_zip_tract_crosswalk.py

Creates table: zip_tract_crosswalk
    zip_code    TEXT
    tract_geoid TEXT
    res_ratio   FLOAT  (residential weight -- set equal to bus_ratio)
    bus_ratio   FLOAT  (business weight -- proportional to tract employment)
"""
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..')))
from db_config import get_connection


def main():
    conn = get_connection()
    cur = conn.cursor()

    # Check if table already exists
    cur.execute(
        "SELECT EXISTS(SELECT 1 FROM pg_tables WHERE tablename = 'zip_tract_crosswalk') AS e")
    if cur.fetchone()[0]:
        print('zip_tract_crosswalk already exists.')
        cur.execute("SELECT COUNT(*) FROM zip_tract_crosswalk")
        print('  Rows: %d' % cur.fetchone()[0])
        conn.close()
        return

    print('Building zip_tract_crosswalk from LODES tract data...')

    # Create table
    cur.execute("""
        CREATE TABLE zip_tract_crosswalk (
            zip_code    TEXT NOT NULL,
            tract_geoid TEXT NOT NULL,
            res_ratio   DOUBLE PRECISION DEFAULT 0,
            bus_ratio   DOUBLE PRECISION DEFAULT 0
        )
    """)
    conn.commit()
    print('  Created table.')

    # Build crosswalk:
    # For each ZIP -> county mapping, find all tracts in that county
    # and distribute the ratio proportionally to employment
    cur.execute("""
        INSERT INTO zip_tract_crosswalk (zip_code, tract_geoid, res_ratio, bus_ratio)
        SELECT
            zc.zip_code,
            lt.tract_fips AS tract_geoid,
            CASE WHEN county_total.total_emp > 0
                 THEN lt.total_jobs::DOUBLE PRECISION / county_total.total_emp
                 ELSE 0 END AS res_ratio,
            CASE WHEN county_total.total_emp > 0
                 THEN lt.total_jobs::DOUBLE PRECISION / county_total.total_emp
                 ELSE 0 END AS bus_ratio
        FROM zip_county_crosswalk zc
        JOIN cur_lodes_tract_metrics lt ON lt.county_fips = zc.county_fips
        JOIN (
            SELECT county_fips, SUM(total_jobs) AS total_emp
            FROM cur_lodes_tract_metrics
            GROUP BY county_fips
        ) county_total ON county_total.county_fips = zc.county_fips
        WHERE lt.total_jobs > 0
    """)
    inserted = cur.rowcount
    conn.commit()
    print('  Inserted %d rows.' % inserted)

    # Create indexes
    cur.execute("CREATE INDEX idx_zip_tract_xwalk_zip ON zip_tract_crosswalk (zip_code)")
    cur.execute("CREATE INDEX idx_zip_tract_xwalk_tract ON zip_tract_crosswalk (tract_geoid)")
    conn.commit()
    print('  Created indexes.')

    # Stats
    cur.execute("SELECT COUNT(DISTINCT zip_code) FROM zip_tract_crosswalk")
    n_zips = cur.fetchone()[0]
    cur.execute("SELECT COUNT(DISTINCT tract_geoid) FROM zip_tract_crosswalk")
    n_tracts = cur.fetchone()[0]
    print('  Coverage: %d ZIPs -> %d tracts' % (n_zips, n_tracts))

    conn.close()
    print('Done.')


if __name__ == '__main__':
    main()
