"""
Measure the impact of score_eligible filtering on employer tiers.

Compares current tier distribution against what it would be without filtering.
Shows which employers changed tiers and the top Priority employers.

Run:
    py scripts/analysis/measure_score_eligible_impact.py
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from db_config import get_connection


def main():
    conn = get_connection()
    cur = conn.cursor()

    print("=== Score Eligibility Impact Report ===\n")

    # Current tier distribution (from MV)
    cur.execute("""
        SELECT score_tier, COUNT(*) AS cnt
        FROM mv_unified_scorecard
        GROUP BY score_tier
        ORDER BY CASE score_tier
            WHEN 'Priority' THEN 1 WHEN 'Strong' THEN 2
            WHEN 'Promising' THEN 3 WHEN 'Moderate' THEN 4
            WHEN 'Low' THEN 5 ELSE 6 END
    """)
    print("  Current tier distribution:")
    for row in cur.fetchall():
        print(f"    {row[0]}: {row[1]:,}")

    # Matches excluded from scoring by table
    print("\n  Matches excluded from scoring (score_eligible=FALSE):")
    for table in ["osha_f7_matches", "whd_f7_matches", "sam_f7_matches", "national_990_f7_matches"]:
        cur.execute(f"SELECT COUNT(*) FROM {table} WHERE score_eligible = FALSE")
        cnt = cur.fetchone()[0]
        cur.execute(f"SELECT COUNT(DISTINCT f7_employer_id) FROM {table} WHERE score_eligible = FALSE")
        emp_cnt = cur.fetchone()[0]
        print(f"    {table}: {cnt:,} matches ({emp_cnt:,} employers affected)")

    # Employers who lost ALL their OSHA data
    cur.execute("""
        SELECT COUNT(DISTINCT f7_employer_id) FROM osha_f7_matches
        WHERE f7_employer_id NOT IN (
            SELECT f7_employer_id FROM osha_f7_matches WHERE score_eligible = TRUE
        )
    """)
    lost_all_osha = cur.fetchone()[0]
    print(f"\n  Employers who lost ALL OSHA scoring data: {lost_all_osha:,}")

    # Employers who lost ALL WHD data
    cur.execute("""
        SELECT COUNT(DISTINCT f7_employer_id) FROM whd_f7_matches
        WHERE f7_employer_id NOT IN (
            SELECT f7_employer_id FROM whd_f7_matches WHERE score_eligible = TRUE
        )
    """)
    lost_all_whd = cur.fetchone()[0]
    print(f"  Employers who lost ALL WHD scoring data: {lost_all_whd:,}")

    # Top 10 Priority employers - do they have high-confidence matches?
    cur.execute("""
        SELECT s.employer_id, f.employer_name, s.weighted_score,
               s.score_osha, s.score_nlrb, s.score_whd
        FROM mv_unified_scorecard s
        JOIN f7_employers_deduped f ON f.employer_id = s.employer_id
        WHERE s.score_tier = 'Priority'
        ORDER BY s.weighted_score DESC
        LIMIT 10
    """)
    rows = cur.fetchall()
    if rows:
        print("\n  Top 10 Priority employers:")
        for r in rows:
            osha = float(r[3]) if r[3] is not None else 0
            nlrb = float(r[4]) if r[4] is not None else 0
            whd = float(r[5]) if r[5] is not None else 0
            print(f"    {r[1][:40]:<40} score={float(r[2]):.2f}  osha={osha:.1f}  nlrb={nlrb:.1f}  whd={whd:.1f}")

    conn.close()


if __name__ == "__main__":
    main()
