"""
Create and populate the data_source_freshness table.
Tracks record counts and date ranges for all major data sources.

Usage:
    py scripts/maintenance/create_data_freshness.py          # Create table + populate
    py scripts/maintenance/create_data_freshness.py --refresh  # Re-query all sources
"""
import sys
import os
import argparse

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
from db_config import get_connection
from api.data_source_catalog import DATA_SOURCE_ENTRIES


CREATE_SQL = """
CREATE TABLE IF NOT EXISTS data_source_freshness (
    source_name   TEXT PRIMARY KEY,
    display_name  TEXT NOT NULL,
    last_updated  TIMESTAMP DEFAULT NOW(),
    record_count  BIGINT,
    date_range_start DATE,
    date_range_end   DATE,
    notes         TEXT
);
"""

# Each source: (source_name, display_name, count_query, date_range_query_or_None, notes)
# date_range_query should return (min_date, max_date) or None if not applicable
SOURCES = [
    (
        src["source_name"],
        src["display_name"],
        src["count_query"],
        src.get("date_query"),
        src.get("freshness_notes", src.get("description", "")),
    )
    for src in DATA_SOURCE_ENTRIES
]


def populate_freshness(conn):
    """Query each source and upsert into data_source_freshness."""
    cur = conn.cursor()
    for source_name, display_name, count_q, date_q, notes in SOURCES:
        try:
            cur.execute(count_q)
            record_count = cur.fetchone()[0]
        except Exception as e:
            print(f"  SKIP {source_name}: {e}")
            conn.rollback()
            continue

        date_start = None
        date_end = None
        if date_q:
            try:
                cur.execute(date_q)
                row = cur.fetchone()
                date_start = row[0]
                date_end = row[1]
            except Exception:
                conn.rollback()

        cur.execute("""
            INSERT INTO data_source_freshness
                (source_name, display_name, last_updated, record_count,
                 date_range_start, date_range_end, notes)
            VALUES (%s, %s, NOW(), %s, %s, %s, %s)
            ON CONFLICT (source_name) DO UPDATE SET
                display_name = EXCLUDED.display_name,
                last_updated = NOW(),
                record_count = EXCLUDED.record_count,
                date_range_start = EXCLUDED.date_range_start,
                date_range_end = EXCLUDED.date_range_end,
                notes = EXCLUDED.notes
        """, [source_name, display_name, record_count, date_start, date_end, notes])
        conn.commit()
        print(f"  {display_name}: {record_count:,} records"
              + (f" ({date_start} to {date_end})" if date_start else ""))


def main():
    parser = argparse.ArgumentParser(description='Create/refresh data_source_freshness table')
    parser.add_argument('--refresh', action='store_true', help='Re-query all sources')
    args = parser.parse_args()

    conn = get_connection()
    try:
        cur = conn.cursor()
        if not args.refresh:
            print("Creating data_source_freshness table...")
            cur.execute(CREATE_SQL)
            conn.commit()
        print("Populating freshness data...")
        populate_freshness(conn)
        print("Done.")
    finally:
        conn.close()


if __name__ == '__main__':
    main()
