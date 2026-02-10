"""Merge 5 confirmed duplicate pairs in mergent_employers (Category A)."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
from db_config import get_connection

MERGE_PAIRS = [
    # (keep_id, delete_id, name)
    (12460, 12894, "ALPHIE SOFTWARE LLC"),
    (37798, 38455, "FALL RIVER COMMERCE SOLAR HOLDINGS, LLC"),
    (10585, 10608, "NASSAU COUNTY BAR ASSOCIATION"),
    (27573, 30859, "PRICE CHOPPER OPERATING CO. OF NEW HAMPSHIRE, INC."),
    (37838, 41913, "UXBRIDGE SOLAR HOLDINGS, LLC"),
]

# Tables that reference mergent_employers.id
FK_TABLES = [
    ("employer_comparables", "employer_id"),
    ("employer_comparables", "comparable_employer_id"),
]

def main():
    conn = get_connection()
    cur = conn.cursor()

    for keep_id, delete_id, name in MERGE_PAIRS:
        print(f"\nMerging {name}: keep={keep_id}, delete={delete_id}")

        # Update foreign key references
        for table, col in FK_TABLES:
            cur.execute(f"""
                UPDATE {table} SET {col} = %s
                WHERE {col} = %s
                AND NOT EXISTS (
                    SELECT 1 FROM {table} t2
                    WHERE t2.employer_id = CASE WHEN '{col}' = 'employer_id' THEN %s ELSE t2.employer_id END
                    AND t2.comparable_employer_id = CASE WHEN '{col}' = 'comparable_employer_id' THEN %s ELSE t2.comparable_employer_id END
                )
            """, (keep_id, delete_id, keep_id, keep_id))
            updated = cur.rowcount
            if updated > 0:
                print(f"  Updated {updated} rows in {table}.{col}")

            # Delete any remaining references that would cause unique violations
            cur.execute(f"DELETE FROM {table} WHERE {col} = %s", (delete_id,))
            deleted = cur.rowcount
            if deleted > 0:
                print(f"  Deleted {deleted} conflicting rows in {table}.{col}")

        # Delete the duplicate
        cur.execute("DELETE FROM mergent_employers WHERE id = %s", (delete_id,))
        print(f"  Deleted mergent_employers id={delete_id}")

    conn.commit()
    conn.close()

    print(f"\n--- Done: merged {len(MERGE_PAIRS)} duplicate pairs ---")

if __name__ == "__main__":
    main()
