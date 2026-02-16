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
        'f7_employers',
        'F-7 Employers (Deduped)',
        "SELECT COUNT(*) FROM f7_employers_deduped",
        None,
        'DOL OLMS Form F-7 employer filings',
    ),
    (
        'nlrb_cases',
        'NLRB Cases',
        "SELECT COUNT(*) FROM nlrb_cases",
        "SELECT MIN(earliest_date), MAX(latest_date) FROM nlrb_cases",
        'National Labor Relations Board case data',
    ),
    (
        'nlrb_elections',
        'NLRB Elections',
        "SELECT COUNT(*) FROM nlrb_elections",
        "SELECT MIN(election_date), MAX(election_date) FROM nlrb_elections",
        'NLRB representation election results',
    ),
    (
        'nlrb_allegations',
        'NLRB Allegations',
        "SELECT COUNT(*) FROM nlrb_allegations",
        None,
        'ULP and other NLRB allegations',
    ),
    (
        'osha_establishments',
        'OSHA Establishments',
        "SELECT COUNT(*) FROM osha_establishments",
        None,
        'OSHA inspection establishment records',
    ),
    (
        'osha_violations',
        'OSHA Violations',
        "SELECT COUNT(*) FROM osha_violations_detail",
        "SELECT MIN(issuance_date), MAX(issuance_date) FROM osha_violations_detail",
        'OSHA violation detail records',
    ),
    (
        'whd_cases',
        'WHD Wage & Hour Cases',
        "SELECT COUNT(*) FROM whd_cases",
        "SELECT MIN(findings_start_date), MAX(findings_end_date) FROM whd_cases",
        'DOL Wage and Hour Division enforcement',
    ),
    (
        'irs_990',
        'IRS Form 990',
        "SELECT COUNT(*) FROM national_990_filers",
        None,
        'IRS Form 990 nonprofit/labor org filings',
    ),
    (
        'sam_entities',
        'SAM.gov Entities',
        "SELECT COUNT(*) FROM sam_entities",
        None,
        'System for Award Management federal contractors',
    ),
    (
        'bls_national_industry',
        'BLS National Industry Density',
        "SELECT COUNT(*) FROM bls_national_industry_density",
        None,
        'BLS union density by industry (national averages)',
    ),
    (
        'bls_state_density',
        'BLS State Density',
        "SELECT COUNT(*) FROM bls_state_density",
        None,
        'BLS union density by state (overall)',
    ),
    (
        'bls_state_industry_estimates',
        'BLS State×Industry Estimates',
        "SELECT COUNT(*) FROM estimated_state_industry_density",
        None,
        'BLS state×industry union density estimates (51 states × 9 industries)',
    ),
    (
        'oews_occupation_matrix',
        'OEWS Occupation-Industry Matrix',
        "SELECT COUNT(*) FROM bls_industry_occupation_matrix",
        None,
        'BLS occupational employment by industry (staffing patterns)',
    ),
    (
        'mergent_employers',
        'Mergent Intellect',
        "SELECT COUNT(*) FROM mergent_employers",
        None,
        'Mergent Intellect employer enrichment',
    ),
    (
        'sec_companies',
        'SEC Companies',
        "SELECT COUNT(*) FROM sec_companies",
        None,
        'SEC EDGAR company filings',
    ),
    (
        'ny_state_contracts',
        'NY State Contracts',
        "SELECT COUNT(*) FROM ny_state_contracts",
        "SELECT MIN(start_date), MAX(end_date) FROM ny_state_contracts",
        'New York State government contracts',
    ),
    (
        'nyc_contracts',
        'NYC Contracts',
        "SELECT COUNT(*) FROM nyc_contracts",
        "SELECT MIN(start_date), MAX(end_date) FROM nyc_contracts",
        'New York City government contracts',
    ),
    (
        'unions_master',
        'Union Locals (Master)',
        "SELECT COUNT(*) FROM unions_master",
        None,
        'DOL OLMS union local registry',
    ),
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
