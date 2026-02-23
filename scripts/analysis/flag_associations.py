"""
Task 2A.6: Flag association-like F7 records.

Default mode is dry-run.
Use --commit to persist updates.
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
from db_config import get_connection


ASSOCIATION_REGEX = (
    r"(?i)"
    r"(association|contractors?\s+association|builders?\s+association|"
    r"joint\s+board|district\s+council|allied\s+employers)"
)


def ensure_columns(cur):
    cur.execute(
        """
        ALTER TABLE f7_employers_deduped
        ADD COLUMN IF NOT EXISTS is_association BOOLEAN DEFAULT FALSE
        """
    )


def main():
    parser = argparse.ArgumentParser(description="Flag association-like employers in f7_employers_deduped")
    parser.add_argument("--commit", action="store_true", help="Persist updates")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Explicit dry-run flag (default behavior if --commit is not provided)",
    )
    parser.add_argument("--preview", type=int, default=30, help="Preview row count")
    args = parser.parse_args()

    conn = get_connection()
    cur = conn.cursor()
    try:
        ensure_columns(cur)

        cur.execute(
            f"""
            SELECT employer_id, employer_name, state, city
            FROM f7_employers_deduped
            WHERE employer_name ~ %s
            ORDER BY employer_name
            """,
            (ASSOCIATION_REGEX,),
        )
        matches = cur.fetchall()
        print(f"Association-like records matched: {len(matches):,}")

        print("\nPreview:")
        for row in matches[: args.preview]:
            print(row)

        cur.execute(
            """
            UPDATE f7_employers_deduped
            SET is_association = TRUE
            WHERE employer_name ~ %s
            """,
            (ASSOCIATION_REGEX,),
        )
        print(f"\nRows updated in transaction: {cur.rowcount:,}")

        if args.commit:
            conn.commit()
            print("Committed.")
        else:
            conn.rollback()
            print("Dry-run complete (rolled back). Use --commit to persist.")
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    main()

