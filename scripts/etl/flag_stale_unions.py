"""
Flag stale union records in unions_master.
Unions with yr_covered < 2022 are marked is_likely_inactive = TRUE.

Usage:
    py scripts/etl/flag_stale_unions.py              # dry-run
    py scripts/etl/flag_stale_unions.py --commit      # apply changes
"""
import argparse, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
from db_config import get_connection


def main():
    parser = argparse.ArgumentParser(description="Flag stale unions")
    parser.add_argument("--commit", action="store_true", help="Persist changes")
    args = parser.parse_args()

    conn = get_connection()
    try:
        cur = conn.cursor()

        # Add column if not exists
        cur.execute("""
            ALTER TABLE unions_master
            ADD COLUMN IF NOT EXISTS is_likely_inactive BOOLEAN DEFAULT FALSE
        """)
        conn.commit()

        # Count affected
        cur.execute("SELECT COUNT(*) FROM unions_master WHERE yr_covered < 2022")
        stale_count = cur.fetchone()[0]

        cur.execute("SELECT COUNT(*) FROM unions_master")
        total = cur.fetchone()[0]

        print("Stale union detection:")
        print("  Total unions:     %d" % total)
        print("  Stale (yr < 2022): %d" % stale_count)
        print("  Active:           %d" % (total - stale_count))

        if not args.commit:
            print("\n  [DRY-RUN] No changes made. Use --commit to persist.")
            return

        cur.execute("UPDATE unions_master SET is_likely_inactive = TRUE WHERE yr_covered < 2022")
        cur.execute("UPDATE unions_master SET is_likely_inactive = FALSE WHERE yr_covered >= 2022")
        updated = cur.rowcount

        # Create partial index
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_unions_master_inactive
            ON unions_master (is_likely_inactive) WHERE is_likely_inactive = TRUE
        """)

        conn.commit()
        print("\n  [COMMITTED] Flagged %d stale unions." % stale_count)

    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    main()
