"""
Clean NLRB participants table: remove literal CSV header text from city/state/zip.

Problem: ~379,558 rows have 'Charged Party Address City' in city,
'Charged Party Address State' in state, 'Charged Party Address Zip' in zip.
Another ~112,638 have 'Charging Party Zip' in zip.
These are CSV headers that got imported as data.

After NULLing junk, attempts to backfill state from other participants in
the same case who have valid state values.

Usage:
    py scripts/etl/clean_nlrb_participants.py              # dry-run
    py scripts/etl/clean_nlrb_participants.py --commit      # apply changes
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
from db_config import get_connection

# Known header-text junk values
JUNK_CITY = ['Charged Party Address City']
JUNK_STATE = ['Charged Party Address State']
JUNK_ZIP = ['Charged Party Address Zip', 'Charging Party Zip']


def null_junk(conn, commit):
    """Phase 1: NULL out literal CSV header text in city/state/zip."""
    cur = conn.cursor()

    cur.execute("SELECT COUNT(*) FROM nlrb_participants")
    total = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM nlrb_participants WHERE city = ANY(%s)", (JUNK_CITY,))
    junk_city_count = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM nlrb_participants WHERE state = ANY(%s)", (JUNK_STATE,))
    junk_state_count = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM nlrb_participants WHERE zip = ANY(%s)", (JUNK_ZIP,))
    junk_zip_count = cur.fetchone()[0]

    print("\nBefore cleanup:")
    print("  Total participants: %d" % total)
    print("  Junk city values:   %d" % junk_city_count)
    print("  Junk state values:  %d" % junk_state_count)
    print("  Junk zip values:    %d" % junk_zip_count)

    cur.execute("UPDATE nlrb_participants SET city = NULL WHERE city = ANY(%s)", (JUNK_CITY,))
    print("\n  NULLed city:  %d rows" % cur.rowcount)

    cur.execute("UPDATE nlrb_participants SET state = NULL WHERE state = ANY(%s)", (JUNK_STATE,))
    print("  NULLed state: %d rows" % cur.rowcount)

    cur.execute("UPDATE nlrb_participants SET zip = NULL WHERE zip = ANY(%s)", (JUNK_ZIP,))
    print("  NULLed zip:   %d rows" % cur.rowcount)

    if commit:
        conn.commit()
        print("  [COMMITTED] Junk NULLing saved.")
    else:
        conn.rollback()
        print("  [DRY-RUN] Rolled back.")


def backfill_state(conn, commit):
    """Phase 2: Backfill NULL state from co-participants in same case.
    Requires index on (case_number, state) for performance."""
    cur = conn.cursor()

    # Create index if missing (idempotent)
    print("\n  Ensuring index on (case_number, state)...")
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_nlrb_participants_case_state
        ON nlrb_participants (case_number, state)
    """)
    conn.commit()
    print("  Index ready.")

    # Also index for the UPDATE join
    print("  Ensuring index on (case_number) WHERE state IS NULL...")
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_nlrb_participants_case_null_state
        ON nlrb_participants (case_number) WHERE state IS NULL
    """)
    conn.commit()
    print("  Index ready.")

    print("  Running backfill query...")
    cur.execute("""
        WITH case_states AS (
            SELECT
                case_number,
                state,
                COUNT(*) AS cnt
            FROM nlrb_participants
            WHERE state IS NOT NULL
              AND LENGTH(state) = 2
            GROUP BY case_number, state
        ),
        unique_state AS (
            SELECT case_number, MIN(state) AS state
            FROM case_states
            GROUP BY case_number
            HAVING COUNT(*) = 1
        )
        UPDATE nlrb_participants p
        SET state = us.state
        FROM unique_state us
        WHERE p.case_number = us.case_number
          AND p.state IS NULL
    """)
    backfilled = cur.rowcount
    print("  Backfilled state from co-participants: %d rows" % backfilled)

    if commit:
        conn.commit()
        print("  [COMMITTED] Backfill saved.")
    else:
        conn.rollback()
        print("  [DRY-RUN] Rolled back.")

    return backfilled


def main():
    parser = argparse.ArgumentParser(description="Clean NLRB participants header junk")
    parser.add_argument("--commit", action="store_true", help="Persist changes")
    parser.add_argument("--skip-backfill", action="store_true",
                        help="Skip state backfill (slow on large tables)")
    args = parser.parse_args()

    conn = get_connection()

    try:
        print("=" * 70)
        print("NLRB PARTICIPANTS DATA CLEANUP")
        print("Mode: %s" % ("COMMIT" if args.commit else "DRY-RUN"))
        print("=" * 70)

        # Phase 1: NULL out junk (fast, ~2 min)
        null_junk(conn, args.commit)

        # Phase 2: Backfill state (slower, benefits from index)
        backfilled = 0
        if not args.skip_backfill:
            backfilled = backfill_state(conn, args.commit)
        else:
            print("\n  Skipping state backfill (--skip-backfill)")

        # Final summary
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM nlrb_participants WHERE city = ANY(%s)", (JUNK_CITY,))
        remaining_city = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM nlrb_participants WHERE state = ANY(%s)", (JUNK_STATE,))
        remaining_state = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM nlrb_participants WHERE zip = ANY(%s)", (JUNK_ZIP,))
        remaining_zip = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM nlrb_participants WHERE state IS NULL")
        null_state = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM nlrb_participants WHERE city IS NULL")
        null_city = cur.fetchone()[0]

        print("\n" + "=" * 70)
        print("FINAL SUMMARY")
        print("=" * 70)
        print("  Junk city remaining:  %d" % remaining_city)
        print("  Junk state remaining: %d" % remaining_state)
        print("  Junk zip remaining:   %d" % remaining_zip)
        print("  NULL city total:      %d" % null_city)
        print("  NULL state total:     %d (backfilled %d)" % (null_state, backfilled))

    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    main()
