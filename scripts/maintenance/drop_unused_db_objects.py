"""
Drop confirmed-unused database objects (Phase 2.4 cleanup).

These 7 objects have zero code references, zero API references,
and no dependent views. Safe to re-run (uses IF EXISTS).
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from db_config import get_connection

OBJECTS_TO_DROP = [
    ("TABLE", "cba_wage_schedules"),
    ("VIEW", "all_employers_unified"),
    ("VIEW", "bls_industry_union_density"),
    ("TABLE", "flra_olms_crosswalk"),
    ("VIEW", "union_sector_coverage"),
    ("VIEW", "v_990_by_state"),
    ("VIEW", "v_all_organizing_events"),
]


def main():
    conn = get_connection()
    conn.autocommit = True
    cur = conn.cursor()

    dropped = []
    skipped = []

    for obj_type, obj_name in OBJECTS_TO_DROP:
        # Check if object exists first
        if obj_type == "TABLE":
            cur.execute(
                "SELECT EXISTS(SELECT 1 FROM information_schema.tables "
                "WHERE table_schema = 'public' AND table_name = %s) AS e",
                (obj_name,),
            )
        else:
            cur.execute(
                "SELECT EXISTS(SELECT 1 FROM information_schema.views "
                "WHERE table_schema = 'public' AND table_name = %s) AS e",
                (obj_name,),
            )
        exists = cur.fetchone()[0]

        sql = f"DROP {obj_type} IF EXISTS {obj_name} CASCADE"
        cur.execute(sql)

        if exists:
            dropped.append(f"{obj_type} {obj_name}")
            print(f"  DROPPED: {obj_type} {obj_name}")
        else:
            skipped.append(f"{obj_type} {obj_name}")
            print(f"  SKIPPED (already gone): {obj_type} {obj_name}")

    cur.close()
    conn.close()

    print(f"\nSummary: {len(dropped)} dropped, {len(skipped)} already absent.")
    if dropped:
        print("Dropped:", ", ".join(dropped))


if __name__ == "__main__":
    main()
