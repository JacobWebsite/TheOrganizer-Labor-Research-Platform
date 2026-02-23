"""Generate a score validation test set spanning all tiers, industries, and sizes."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from db_config import get_connection
from psycopg2.extras import RealDictCursor


def main():
    conn = get_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)

    cur.execute("""
    WITH tier_samples AS (
        SELECT s.*, LEFT(s.naics, 2) AS naics_2,
               ROW_NUMBER() OVER (PARTITION BY s.score_tier, LEFT(s.naics, 2) ORDER BY random()) AS rn
        FROM mv_unified_scorecard s
        WHERE s.naics IS NOT NULL AND s.employer_name IS NOT NULL
          AND LENGTH(s.employer_name) > 5
    ),
    selected AS (
        SELECT * FROM tier_samples WHERE rn = 1
    ),
    final AS (
        (SELECT * FROM selected WHERE score_tier = 'Priority' ORDER BY random() LIMIT 3)
        UNION ALL
        (SELECT * FROM selected WHERE score_tier = 'Strong' ORDER BY random() LIMIT 3)
        UNION ALL
        (SELECT * FROM selected WHERE score_tier = 'Promising' ORDER BY random() LIMIT 3)
        UNION ALL
        (SELECT * FROM selected WHERE score_tier = 'Moderate' ORDER BY random() LIMIT 3)
        UNION ALL
        (SELECT * FROM selected WHERE score_tier = 'Low' ORDER BY random() LIMIT 3)
    )
    SELECT
        f.employer_id, f.employer_name, f.state, f.naics, f.naics_2,
        ns.sector_name,
        f.latest_unit_size, f.score_tier,
        f.weighted_score, f.factors_available,
        f.score_osha, f.score_nlrb, f.score_whd, f.score_contracts,
        f.score_union_proximity, f.score_industry_growth, f.score_financial,
        f.score_size, f.score_similarity,
        f.has_recent_violations, f.has_active_contracts,
        f.osha_total_violations, f.osha_total_penalties,
        f.nlrb_election_count, f.nlrb_win_count, f.nlrb_ulp_count,
        f.whd_case_count
    FROM final f
    LEFT JOIN naics_sectors ns ON f.naics_2 = ns.naics_2digit
    ORDER BY CASE f.score_tier
        WHEN 'Priority' THEN 1 WHEN 'Strong' THEN 2 WHEN 'Promising' THEN 3
        WHEN 'Moderate' THEN 4 ELSE 5 END,
        f.weighted_score DESC
    """)
    rows = cur.fetchall()

    print(f"Score Validation Test Set ({len(rows)} employers)")
    print("=" * 130)
    for r in rows:
        sector = (r["sector_name"] or "Unknown")[:25]
        size = r["latest_unit_size"] or 0
        pen = r["osha_total_penalties"] or 0
        print(
            f"\n{r['score_tier']:10s} | {r['employer_name'][:40]:40s} | {r['state']} "
            f"| {sector:25s} | size={size:>6}"
        )
        print(
            f"  weighted={r['weighted_score']}  factors={r['factors_available']}  "
            f"recent_violations={r['has_recent_violations']}  "
            f"active_contracts={r['has_active_contracts']}"
        )
        print(
            f"  OSHA={r['score_osha']}  NLRB={r['score_nlrb']}  WHD={r['score_whd']}  "
            f"contracts={r['score_contracts']}  proximity={r['score_union_proximity']}  "
            f"growth={r['score_industry_growth']}  financial={r['score_financial']}  "
            f"size={r['score_size']}"
        )
        print(
            f"  Data: osha_viol={r['osha_total_violations']}  osha_pen={pen}  "
            f"nlrb_elections={r['nlrb_election_count']}  nlrb_wins={r['nlrb_win_count']}  "
            f"ulps={r['nlrb_ulp_count']}  whd_cases={r['whd_case_count']}"
        )

    conn.close()


if __name__ == "__main__":
    main()
