"""
Create the v_nlrb_employer_history view.

Unified NLRB history per employer: elections (RC/RD/RM), ULP (CA/CB/CC/CD/CP),
and unit clarification (UC/UD) in one queryable view.

Usage:
    py scripts/matching/create_nlrb_bridge.py
    py scripts/matching/create_nlrb_bridge.py --drop
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from db_config import get_connection


VIEW_SQL = """
CREATE OR REPLACE VIEW v_nlrb_employer_history AS

-- Representation cases (elections)
SELECT
    p.matched_employer_id AS f7_employer_id,
    c.case_number,
    c.case_type,
    'representation' AS case_category,
    COALESCE(e.election_date, c.earliest_date) AS event_date,
    c.earliest_date AS case_open_date,
    c.latest_date AS case_close_date,
    p.participant_name AS employer_name,
    p.city,
    p.state,
    e.election_type,
    e.eligible_voters,
    e.union_won,
    e.vote_margin,
    t.labor_org_name AS union_name,
    um.aff_abbr AS union_abbr,
    NULL::text AS allegation_section,
    p.match_confidence,
    p.match_method
FROM nlrb_participants p
JOIN nlrb_cases c ON p.case_number = c.case_number
LEFT JOIN nlrb_elections e ON c.case_number = e.case_number
LEFT JOIN nlrb_tallies t ON c.case_number = t.case_number AND t.tally_type = 'For'
LEFT JOIN unions_master um ON t.matched_olms_fnum = um.f_num
WHERE p.participant_type = 'Employer'
  AND p.matched_employer_id IS NOT NULL
  AND c.case_type IN ('RC', 'RD', 'RM')

UNION ALL

-- ULP cases (unfair labor practices)
SELECT
    p.matched_employer_id AS f7_employer_id,
    c.case_number,
    c.case_type,
    'ulp' AS case_category,
    c.earliest_date AS event_date,
    c.earliest_date AS case_open_date,
    c.latest_date AS case_close_date,
    p.participant_name AS employer_name,
    p.city,
    p.state,
    NULL AS election_type,
    NULL AS eligible_voters,
    NULL AS union_won,
    NULL AS vote_margin,
    NULL AS union_name,
    NULL AS union_abbr,
    (SELECT string_agg(DISTINCT a.section, ', ')
     FROM nlrb_allegations a WHERE a.case_number = c.case_number
    ) AS allegation_section,
    p.match_confidence,
    p.match_method
FROM nlrb_participants p
JOIN nlrb_cases c ON p.case_number = c.case_number
WHERE p.participant_type IN ('Charged Party', 'Employer')
  AND p.matched_employer_id IS NOT NULL
  AND c.case_type IN ('CA', 'CB', 'CC', 'CD', 'CP', 'CE', 'CG')

UNION ALL

-- Unit clarification cases
SELECT
    p.matched_employer_id AS f7_employer_id,
    c.case_number,
    c.case_type,
    'unit_clarification' AS case_category,
    c.earliest_date AS event_date,
    c.earliest_date AS case_open_date,
    c.latest_date AS case_close_date,
    p.participant_name AS employer_name,
    p.city,
    p.state,
    NULL AS election_type,
    NULL AS eligible_voters,
    NULL AS union_won,
    NULL AS vote_margin,
    NULL AS union_name,
    NULL AS union_abbr,
    NULL AS allegation_section,
    p.match_confidence,
    p.match_method
FROM nlrb_participants p
JOIN nlrb_cases c ON p.case_number = c.case_number
WHERE p.participant_type = 'Employer'
  AND p.matched_employer_id IS NOT NULL
  AND c.case_type IN ('UC', 'UD')
;
"""


def main():
    parser = argparse.ArgumentParser(description="Create NLRB bridge view")
    parser.add_argument("--drop", action="store_true", help="Drop view first")
    args = parser.parse_args()

    conn = get_connection()
    try:
        with conn.cursor() as cur:
            if args.drop:
                print("Dropping existing view...")
                cur.execute("DROP VIEW IF EXISTS v_nlrb_employer_history CASCADE")

            print("Creating v_nlrb_employer_history view...")
            cur.execute(VIEW_SQL)
            conn.commit()

            # Verify
            cur.execute("""
                SELECT case_category, COUNT(*)
                FROM v_nlrb_employer_history
                GROUP BY case_category
                ORDER BY case_category
            """)
            print("\nView created. Row counts by category:")
            total = 0
            for r in cur.fetchall():
                print(f"  {r[0]:25s} {r[1]:>8,}")
                total += r[1]
            print(f"  {'TOTAL':25s} {total:>8,}")

            cur.execute("""
                SELECT COUNT(DISTINCT f7_employer_id)
                FROM v_nlrb_employer_history
            """)
            print(f"\nUnique F7 employers with NLRB history: {cur.fetchone()[0]:,}")

    finally:
        conn.close()

    print("\nDone.")


if __name__ == "__main__":
    main()
