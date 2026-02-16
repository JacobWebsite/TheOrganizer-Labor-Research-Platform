"""
Load Teamsters official locals from CSV into PostgreSQL database
Creates teamsters_official_locals table and comparison view
"""

import psycopg2
import csv
import os

DB_CONFIG = {
    'host': os.environ.get('DB_HOST', 'localhost'),
    'port': int(os.environ.get('DB_PORT', '5432')),
    'database': os.environ.get('DB_NAME', 'olms_multiyear'),
    'user': os.environ.get('DB_USER', 'postgres'),
    'password': os.environ.get('DB_PASSWORD', ''),
}

def create_table(conn):
    """Create the teamsters_official_locals table."""
    cur = conn.cursor()

    cur.execute("""
        DROP TABLE IF EXISTS teamsters_official_locals CASCADE;

        CREATE TABLE teamsters_official_locals (
            local_number INTEGER PRIMARY KEY,
            local_name VARCHAR(255),
            city VARCHAR(100),
            state VARCHAR(20),
            zip VARCHAR(20),
            phone VARCHAR(30),
            email VARCHAR(255),
            website VARCHAR(500),
            leadership_name VARCHAR(255),
            leadership_title VARCHAR(100),
            divisions TEXT,
            full_address TEXT,
            scraped_at TIMESTAMP DEFAULT NOW()
        );
    """)
    conn.commit()
    print("Created teamsters_official_locals table")


def load_csv_data(conn, filename='teamsters_official_locals.csv'):
    """Load data from CSV into the table."""
    cur = conn.cursor()

    with open(filename, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        count = 0
        for row in reader:
            try:
                cur.execute("""
                    INSERT INTO teamsters_official_locals
                    (local_number, local_name, city, state, zip, phone, email,
                     website, leadership_name, leadership_title, divisions,
                     full_address, scraped_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (local_number) DO UPDATE SET
                        local_name = EXCLUDED.local_name,
                        city = EXCLUDED.city,
                        state = EXCLUDED.state,
                        zip = EXCLUDED.zip,
                        phone = EXCLUDED.phone,
                        email = EXCLUDED.email,
                        website = EXCLUDED.website,
                        leadership_name = EXCLUDED.leadership_name,
                        leadership_title = EXCLUDED.leadership_title,
                        divisions = EXCLUDED.divisions,
                        full_address = EXCLUDED.full_address,
                        scraped_at = EXCLUDED.scraped_at
                """, (
                    int(row['local_number']) if row['local_number'] else None,
                    row['local_name'],
                    row['city'],
                    row['state'],
                    row['zip'],
                    row['phone'],
                    row['email'],
                    row['website'],
                    row['leadership_name'],
                    row['leadership_title'],
                    row['divisions'],
                    row['full_address'],
                    row['scraped_at'] or None
                ))
                count += 1
            except Exception as e:
                print(f"Error loading row {row.get('local_number')}: {e}")

    conn.commit()
    print(f"Loaded {count} locals into database")


def create_comparison_view(conn):
    """Create view comparing official vs database locals."""
    cur = conn.cursor()

    cur.execute("""
        CREATE OR REPLACE VIEW v_teamsters_comparison AS
        SELECT
            COALESCE(o.local_number, d.local_number::integer) as local_number,
            CASE
                WHEN o.local_number IS NULL THEN 'DB_ONLY'
                WHEN d.local_number IS NULL THEN 'WEB_ONLY'
                WHEN o.state != d.state THEN 'STATE_MISMATCH'
                WHEN UPPER(o.city) != UPPER(d.city) THEN 'CITY_MISMATCH'
                ELSE 'MATCH'
            END as match_status,
            o.local_name as official_name,
            d.union_name as db_name,
            o.city as official_city,
            d.city as db_city,
            o.state as official_state,
            d.state as db_state,
            o.phone as official_phone,
            o.email as official_email,
            o.website as official_website,
            o.leadership_name,
            o.leadership_title,
            o.divisions,
            d.f_num,
            d.members,
            d.yr_covered
        FROM teamsters_official_locals o
        FULL OUTER JOIN (
            SELECT f_num, union_name, local_number, city, state, members, yr_covered
            FROM unions_master
            WHERE aff_abbr = 'IBT'
            AND desig_name IN ('LU', 'LU   ')
            AND local_number IS NOT NULL
            AND local_number != '0'
        ) d ON o.local_number = d.local_number::integer
        ORDER BY COALESCE(o.local_number, d.local_number::integer);
    """)
    conn.commit()
    print("Created v_teamsters_comparison view")


def print_summary(conn):
    """Print comparison summary."""
    cur = conn.cursor()

    print("\n" + "="*60)
    print("TEAMSTERS LOCALS DATABASE COMPARISON")
    print("="*60)

    cur.execute("SELECT COUNT(*) FROM teamsters_official_locals")
    print(f"\nOfficial Website Locals: {cur.fetchone()[0]}")

    cur.execute("""
        SELECT COUNT(*)
        FROM unions_master
        WHERE aff_abbr = 'IBT'
        AND desig_name IN ('LU', 'LU   ')
        AND local_number IS NOT NULL
        AND local_number != '0'
    """)
    print(f"Database IBT Locals (LU): {cur.fetchone()[0]}")

    cur.execute("""
        SELECT match_status, COUNT(*)
        FROM v_teamsters_comparison
        GROUP BY match_status
        ORDER BY COUNT(*) DESC
    """)
    print("\nComparison Results:")
    for row in cur.fetchall():
        print(f"   {row[0]}: {row[1]}")

    # Show Canadian locals (these are on website but likely not in US OLMS data)
    cur.execute("""
        SELECT COUNT(*)
        FROM teamsters_official_locals
        WHERE state IN ('CN', 'Quebec', 'Ont', 'BC', 'Alb')
    """)
    canadian = cur.fetchone()[0]
    print(f"\nCanadian Locals (expected missing from OLMS): {canadian}")

    print("\n" + "="*60)


def main():
    print("Loading Teamsters Official Locals to Database")
    print("-" * 50)

    conn = psycopg2.connect(**DB_CONFIG)

    try:
        create_table(conn)
        load_csv_data(conn)
        create_comparison_view(conn)
        print_summary(conn)
    finally:
        conn.close()


if __name__ == '__main__':
    main()
