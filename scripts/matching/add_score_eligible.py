"""
Add score_eligible BOOLEAN column to legacy match tables and populate it.

Rules:
  - score_eligible = TRUE if match_confidence >= 0.85
  - score_eligible = TRUE if match_method is a deterministic identity method
    (EIN_EXACT, CROSSWALK, CIK_BRIDGE) regardless of confidence
  - score_eligible = FALSE otherwise (aggressive name matches < 0.85)
  - DEFAULT TRUE for future inserts

Run:
    py scripts/matching/add_score_eligible.py             # dry-run
    py scripts/matching/add_score_eligible.py --commit    # apply changes
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from db_config import get_connection


TABLES = [
    "osha_f7_matches",
    "whd_f7_matches",
    "sam_f7_matches",
    "national_990_f7_matches",
]

# Identity-based methods that are always score-eligible regardless of confidence
IDENTITY_METHODS = ("EIN_EXACT", "CROSSWALK", "CIK_BRIDGE")


def add_column(conn, table, commit=False):
    """Add score_eligible column if not exists. Returns True if added."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT 1 FROM information_schema.columns "
            "WHERE table_name = %s AND column_name = 'score_eligible'",
            (table,),
        )
        if cur.fetchone():
            return False  # already exists

        if commit:
            cur.execute(
                f"ALTER TABLE {table} ADD COLUMN score_eligible BOOLEAN DEFAULT TRUE"
            )
            conn.commit()
        return True


def populate_score_eligible(conn, table, commit=False):
    """Set score_eligible based on confidence and method. Returns counts dict."""
    identity_list = ", ".join(f"'{m}'" for m in IDENTITY_METHODS)

    # Count current state
    with conn.cursor() as cur:
        cur.execute(f"SELECT COUNT(*) FROM {table}")
        total = cur.fetchone()[0]

        # Count would-be-eligible
        cur.execute(
            f"SELECT COUNT(*) FROM {table} "
            f"WHERE match_confidence >= 0.85 "
            f"   OR UPPER(match_method) IN ({identity_list})"
        )
        eligible = cur.fetchone()[0]

        # Count would-be-ineligible
        ineligible = total - eligible

        if commit:
            # First set all to FALSE
            cur.execute(f"UPDATE {table} SET score_eligible = FALSE")
            # Then set eligible ones to TRUE
            cur.execute(
                f"UPDATE {table} SET score_eligible = TRUE "
                f"WHERE match_confidence >= 0.85 "
                f"   OR UPPER(match_method) IN ({identity_list})"
            )
            conn.commit()

    return {"total": total, "eligible": eligible, "ineligible": ineligible}


def main():
    parser = argparse.ArgumentParser(description="Add score_eligible to match tables")
    parser.add_argument("--commit", action="store_true", help="Apply changes")
    args = parser.parse_args()

    conn = get_connection()

    print("=== Score Eligibility Migration ===\n")

    for table in TABLES:
        added = add_column(conn, table, commit=args.commit)
        status = "ADDED" if added else "EXISTS"
        print(f"  {table}.score_eligible: {status}")

    if args.commit:
        # Re-get connection to ensure columns are visible
        conn.close()
        conn = get_connection()

    print("\n=== Population Report ===\n")
    grand_total = 0
    grand_ineligible = 0
    for table in TABLES:
        counts = populate_score_eligible(conn, table, commit=args.commit)
        pct = (counts["ineligible"] / counts["total"] * 100) if counts["total"] else 0
        print(
            f"  {table}: {counts['total']} total, "
            f"{counts['eligible']} eligible, "
            f"{counts['ineligible']} ineligible ({pct:.1f}%)"
        )
        grand_total += counts["total"]
        grand_ineligible += counts["ineligible"]

    print(
        f"\n  TOTAL: {grand_total} matches, "
        f"{grand_ineligible} now ineligible for scoring "
        f"({grand_ineligible / grand_total * 100:.1f}%)"
    )

    if not args.commit:
        print("\nDRY RUN. Use --commit to apply.")

    conn.close()


if __name__ == "__main__":
    main()
