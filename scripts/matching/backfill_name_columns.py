"""
Add and backfill pre-computed name normalization columns on f7_employers_deduped.

Adds: name_standard, name_aggressive, name_fuzzy
These enable fast SQL-side matching without Python round-trips.

Usage:
    py scripts/matching/backfill_name_columns.py
    py scripts/matching/backfill_name_columns.py --dry-run
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from db_config import get_connection

# Import canonical normalization
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from src.python.matching.name_normalization import (
    normalize_name_standard,
    normalize_name_aggressive,
    normalize_name_fuzzy,
)

BATCH_SIZE = 5000


def ensure_columns(conn):
    """Add name columns if they don't exist."""
    with conn.cursor() as cur:
        for col in ("name_standard", "name_aggressive", "name_fuzzy"):
            cur.execute(f"""
                DO $$
                BEGIN
                    IF NOT EXISTS (
                        SELECT 1 FROM information_schema.columns
                        WHERE table_name = 'f7_employers_deduped' AND column_name = '{col}'
                    ) THEN
                        ALTER TABLE f7_employers_deduped ADD COLUMN {col} TEXT;
                    END IF;
                END $$;
            """)
        conn.commit()
    print("Columns ensured: name_standard, name_aggressive, name_fuzzy")


def backfill(conn, dry_run=False):
    """Compute and store normalized names for all employers."""
    with conn.cursor() as cur:
        cur.execute("SELECT employer_id, employer_name FROM f7_employers_deduped")
        rows = cur.fetchall()
        total = len(rows)
        print(f"Processing {total:,} employers...")

        if dry_run:
            # Show sample
            for r in rows[:5]:
                eid, name = r
                print(f"  {name[:50]:50s} -> std={normalize_name_standard(name)[:30]}, "
                      f"agg={normalize_name_aggressive(name)[:30]}, "
                      f"fuz={normalize_name_fuzzy(name)[:30]}")
            print(f"  ... and {total - 5:,} more")
            return

        updates = []
        for r in rows:
            eid, name = r
            updates.append((
                normalize_name_standard(name or ""),
                normalize_name_aggressive(name or ""),
                normalize_name_fuzzy(name or ""),
                eid,
            ))

        # Batch update
        from psycopg2.extras import execute_batch
        sql = """
            UPDATE f7_employers_deduped
            SET name_standard = %s, name_aggressive = %s, name_fuzzy = %s
            WHERE employer_id = %s
        """
        for i in range(0, len(updates), BATCH_SIZE):
            chunk = updates[i:i + BATCH_SIZE]
            execute_batch(cur, sql, chunk, page_size=1000)
            done = min(i + BATCH_SIZE, len(updates))
            print(f"  Updated {done:,} / {total:,}")

        conn.commit()

        # Create indexes
        print("Creating indexes on name columns...")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_f7_name_standard ON f7_employers_deduped(name_standard)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_f7_name_aggressive ON f7_employers_deduped(name_aggressive)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_f7_name_fuzzy ON f7_employers_deduped(name_fuzzy)")
        conn.commit()

        # Verify
        cur.execute("SELECT COUNT(*) FROM f7_employers_deduped WHERE name_standard IS NOT NULL")
        filled = cur.fetchone()[0]
        print(f"\nBackfill complete: {filled:,} / {total:,} rows have name_standard")


def main():
    parser = argparse.ArgumentParser(description="Backfill name normalization columns")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    conn = get_connection()
    try:
        ensure_columns(conn)
        backfill(conn, args.dry_run)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
