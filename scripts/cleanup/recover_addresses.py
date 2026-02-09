import os
"""
Recover missing street addresses for f7_employers_deduped from lm_data historical filings.

Finds F7 employers with NULL/empty street fields and recovers addresses from
the most recent LM filing that has a valid street address.

Usage:
    py scripts/cleanup/recover_addresses.py             # dry-run (default)
    py scripts/cleanup/recover_addresses.py --apply     # apply changes
"""

import sys
import psycopg2
from psycopg2.extras import RealDictCursor

# Fix Windows console encoding
sys.stdout.reconfigure(encoding='utf-8', errors='replace')


def get_connection():
    return psycopg2.connect(
        host='localhost',
        dbname='olms_multiyear',
        user='postgres',
        password='os.environ.get('DB_PASSWORD', '')'
    )


RECOVERY_QUERY = """
WITH recovery AS (
    SELECT DISTINCT ON (e.employer_id)
        e.employer_id,
        e.employer_name,
        e.street AS current_street,
        e.city AS current_city,
        e.state AS current_state,
        e.zip AS current_zip,
        l.street AS lm_street,
        l.city AS lm_city,
        l.state AS lm_state,
        l.zip AS lm_zip,
        l.yr_covered
    FROM f7_employers_deduped e
    JOIN lm_data l ON CAST(e.latest_union_fnum AS TEXT) = l.f_num
    WHERE (e.street IS NULL OR TRIM(e.street) = '')
      AND l.street IS NOT NULL AND TRIM(l.street) != ''
    ORDER BY e.employer_id, l.yr_covered DESC
)
SELECT * FROM recovery
ORDER BY employer_name
"""


def main():
    apply_mode = '--apply' in sys.argv

    conn = get_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)

    print("=" * 70)
    print("ADDRESS RECOVERY: f7_employers_deduped from lm_data")
    print("Mode: %s" % ("APPLY" if apply_mode else "DRY-RUN"))
    print("=" * 70)

    # Get current stats
    cur.execute("""
        SELECT
            COUNT(*) AS total,
            COUNT(*) FILTER (WHERE street IS NULL OR TRIM(street) = '') AS missing_street,
            COUNT(*) FILTER (WHERE latitude IS NOT NULL) AS geocoded,
            COUNT(*) FILTER (WHERE latitude IS NULL) AS not_geocoded
        FROM f7_employers_deduped
    """)
    stats = cur.fetchone()
    print("\nCurrent state:")
    print("  Total employers: %d" % stats['total'])
    print("  Missing street: %d" % stats['missing_street'])
    print("  Geocoded: %d" % stats['geocoded'])
    print("  Not geocoded: %d" % stats['not_geocoded'])

    # Find recoverable addresses
    print("\nSearching lm_data for recoverable addresses...")
    cur.execute(RECOVERY_QUERY)
    rows = cur.fetchall()

    print("Found %d employers with recoverable addresses\n" % len(rows))

    if len(rows) == 0:
        print("Nothing to recover.")
        conn.close()
        return

    # Display recovery details
    print("%-45s | %-25s | %-30s | %s" % ("Employer", "Old Street", "New Street", "Source Year"))
    print("-" * 140)

    updated = 0
    city_filled = 0
    zip_filled = 0

    for row in rows:
        old_street = row['current_street'] or '(none)'
        new_street = row['lm_street']
        yr = row['yr_covered']

        name_display = row['employer_name'][:45] if row['employer_name'] else '(unknown)'
        old_display = old_street[:25]
        new_display = new_street[:30] if new_street else '(none)'

        extras = []
        if not row['current_city'] and row['lm_city']:
            extras.append("+city")
            city_filled += 1
        if not row['current_zip'] and row['lm_zip']:
            extras.append("+zip")
            zip_filled += 1

        suffix = " [%s]" % ", ".join(extras) if extras else ""

        print("%-45s | %-25s | %-30s | %d%s" % (
            name_display, old_display, new_display, yr, suffix))

        if apply_mode:
            cur.execute("""
                UPDATE f7_employers_deduped
                SET street = %(lm_street)s,
                    city = COALESCE(NULLIF(TRIM(city), ''), %(lm_city)s),
                    zip = COALESCE(NULLIF(TRIM(zip), ''), %(lm_zip)s)
                WHERE employer_id = %(employer_id)s
            """, {
                'lm_street': row['lm_street'],
                'lm_city': row['lm_city'],
                'lm_zip': row['lm_zip'],
                'employer_id': row['employer_id'],
            })
            updated += 1

    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print("  Addresses recoverable: %d" % len(rows))
    print("  City also filled: %d" % city_filled)
    print("  ZIP also filled: %d" % zip_filled)

    if apply_mode:
        conn.commit()
        print("  Records updated: %d" % updated)

        # Verify
        cur.execute("""
            SELECT COUNT(*) AS cnt
            FROM f7_employers_deduped
            WHERE street IS NULL OR TRIM(street) = ''
        """)
        remaining = cur.fetchone()['cnt']
        print("  Remaining missing streets: %d" % remaining)
        print("\n  [APPLIED] Changes committed to database.")
    else:
        print("\n  [DRY-RUN] No changes made. Use --apply to commit.")

    conn.close()


if __name__ == '__main__':
    main()
