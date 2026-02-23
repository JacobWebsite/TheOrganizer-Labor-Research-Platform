"""
Task 2A.2: Infer missing F7 NAICS from active OSHA/WHD matches.

Default mode is dry-run.
Use --commit to persist updates.
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
from db_config import get_connection


def ensure_columns(cur):
    cur.execute(
        """
        ALTER TABLE f7_employers_deduped
        ADD COLUMN IF NOT EXISTS naics_source VARCHAR(50)
        """
    )


OSHA_CANDIDATE_SQL = """
WITH raw AS (
    SELECT
        uml.target_id AS employer_id,
        regexp_replace(COALESCE(o.naics_code, ''), '[^0-9]', '', 'g') AS naics_code
    FROM unified_match_log uml
    JOIN f7_employers_deduped f ON f.employer_id = uml.target_id
    JOIN osha_establishments o ON o.establishment_id::text = uml.source_id
    WHERE uml.status = 'active'
      AND uml.source_system = 'osha'
      AND f.naics IS NULL
      AND o.naics_code IS NOT NULL
),
agg AS (
    SELECT employer_id, naics_code, COUNT(*) AS cnt
    FROM raw
    WHERE LENGTH(naics_code) BETWEEN 2 AND 6
    GROUP BY employer_id, naics_code
),
picked AS (
    SELECT employer_id, naics_code,
           ROW_NUMBER() OVER (
               PARTITION BY employer_id
               ORDER BY cnt DESC, LENGTH(naics_code) DESC, naics_code
           ) AS rn
    FROM agg
)
SELECT employer_id, naics_code
FROM picked
WHERE rn = 1
"""


WHD_CANDIDATE_SQL = """
WITH raw AS (
    SELECT
        uml.target_id AS employer_id,
        regexp_replace(COALESCE(w.naics_code, ''), '[^0-9]', '', 'g') AS naics_code
    FROM unified_match_log uml
    JOIN f7_employers_deduped f ON f.employer_id = uml.target_id
    JOIN whd_cases w ON w.case_id::text = uml.source_id
    WHERE uml.status = 'active'
      AND uml.source_system = 'whd'
      AND f.naics IS NULL
      AND w.naics_code IS NOT NULL
),
agg AS (
    SELECT employer_id, naics_code, COUNT(*) AS cnt
    FROM raw
    WHERE LENGTH(naics_code) BETWEEN 2 AND 6
    GROUP BY employer_id, naics_code
),
picked AS (
    SELECT employer_id, naics_code,
           ROW_NUMBER() OVER (
               PARTITION BY employer_id
               ORDER BY cnt DESC, LENGTH(naics_code) DESC, naics_code
           ) AS rn
    FROM agg
)
SELECT employer_id, naics_code
FROM picked
WHERE rn = 1
"""


def fetch_candidates(cur, sql):
    cur.execute(sql)
    return cur.fetchall()


def main():
    parser = argparse.ArgumentParser(description="Infer missing F7 NAICS from active OSHA/WHD matches")
    parser.add_argument("--commit", action="store_true", help="Persist updates")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Explicit dry-run flag (default behavior if --commit is not provided)",
    )
    args = parser.parse_args()

    conn = get_connection()
    cur = conn.cursor()

    try:
        ensure_columns(cur)

        osha_rows = fetch_candidates(cur, OSHA_CANDIDATE_SQL)
        osha_map = {eid: naics for eid, naics in osha_rows}

        # WHD only for employers still missing after OSHA candidate pass.
        whd_rows = fetch_candidates(cur, WHD_CANDIDATE_SQL)
        whd_map = {}
        for eid, naics in whd_rows:
            if eid not in osha_map:
                whd_map[eid] = naics

        total_updates = len(osha_map) + len(whd_map)
        print(f"OSHA inferred candidates: {len(osha_map):,}")
        print(f"WHD inferred candidates:  {len(whd_map):,}")
        print(f"Total employers to update: {total_updates:,}")

        if total_updates:
            preview_ids = list(osha_map.keys())[:10] + list(whd_map.keys())[:10]
            cur.execute(
                """
                SELECT employer_id, employer_name, state
                FROM f7_employers_deduped
                WHERE employer_id = ANY(%s)
                ORDER BY employer_name
                """,
                (preview_ids,),
            )
            print("\nPreview:")
            for row in cur.fetchall():
                print(row)

        updates = 0
        for eid, naics in osha_map.items():
            cur.execute(
                """
                UPDATE f7_employers_deduped
                SET naics = %s,
                    naics_source = 'OSHA_INFERRED'
                WHERE employer_id = %s
                  AND naics IS NULL
                """,
                (naics, eid),
            )
            updates += cur.rowcount

        for eid, naics in whd_map.items():
            cur.execute(
                """
                UPDATE f7_employers_deduped
                SET naics = %s,
                    naics_source = 'WHD_INFERRED'
                WHERE employer_id = %s
                  AND naics IS NULL
                """,
                (naics, eid),
            )
            updates += cur.rowcount

        print(f"\nRows updated in transaction: {updates:,}")

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

