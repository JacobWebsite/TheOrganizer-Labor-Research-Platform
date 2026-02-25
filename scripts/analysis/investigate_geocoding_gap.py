"""
I11 - Geocoding Gap by Score Tier
Analyzes how geocoding coverage varies across unified scorecard tiers,
identifies top states with gaps, and reports overall geocoding rates.
"""
import argparse
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
from db_config import get_connection
from psycopg2.extras import RealDictCursor


def main():
    parser = argparse.ArgumentParser(description="I11 - Geocoding Gap by Score Tier")
    parser.add_argument(
        "--output",
        default=os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
            "docs", "investigations", "I11_geocoding_gap_by_tier.md",
        ),
        help="Output markdown file path",
    )
    args = parser.parse_args()

    conn = get_connection(cursor_factory=RealDictCursor)
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)

        # Query 1: Geocoding rate by score tier
        cur.execute("""
            SELECT u.score_tier, COUNT(*) AS total,
                   COUNT(*) FILTER (WHERE f.latitude IS NOT NULL) AS geocoded,
                   ROUND(100.0 * COUNT(*) FILTER (WHERE f.latitude IS NOT NULL) / COUNT(*), 1) AS pct
            FROM mv_unified_scorecard u
            JOIN f7_employers_deduped f ON f.employer_id = u.employer_id
            GROUP BY u.score_tier
            ORDER BY CASE u.score_tier
                WHEN 'Priority' THEN 1 WHEN 'Strong' THEN 2
                WHEN 'Promising' THEN 3 WHEN 'Moderate' THEN 4
                WHEN 'Low' THEN 5 END
        """)
        tier_rows = cur.fetchall()

        # Query 2: Overall geocoding rate
        cur.execute("""
            SELECT COUNT(*) AS total,
                   COUNT(*) FILTER (WHERE f.latitude IS NOT NULL) AS geocoded,
                   ROUND(100.0 * COUNT(*) FILTER (WHERE f.latitude IS NOT NULL) / COUNT(*), 1) AS pct
            FROM mv_unified_scorecard u
            JOIN f7_employers_deduped f ON f.employer_id = u.employer_id
        """)
        overall = cur.fetchone()

        # Query 3: Top 10 states by geocoding gap
        cur.execute("""
            SELECT f.state, COUNT(*) AS total,
                   COUNT(*) FILTER (WHERE f.latitude IS NULL) AS missing,
                   ROUND(100.0 * COUNT(*) FILTER (WHERE f.latitude IS NULL) / COUNT(*), 1) AS pct_missing
            FROM f7_employers_deduped f
            WHERE f.state IS NOT NULL
            GROUP BY f.state
            HAVING COUNT(*) FILTER (WHERE f.latitude IS NULL) > 0
            ORDER BY COUNT(*) FILTER (WHERE f.latitude IS NULL) DESC
            LIMIT 10
        """)
        state_rows = cur.fetchall()

        cur.close()
    finally:
        conn.close()

    # Build markdown report
    lines = []
    lines.append(f"# I11 - Geocoding Gap by Score Tier")
    lines.append(f"")
    lines.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    lines.append(f"")

    # Summary
    lines.append(f"## Summary")
    lines.append(f"")
    lines.append(
        f"Overall geocoding rate: **{overall['geocoded']:,}** / "
        f"**{overall['total']:,}** ({overall['pct']}%). "
        f"**{overall['total'] - overall['geocoded']:,}** employers lack coordinates."
    )
    lines.append(f"")

    # Geocoding Rate by Score Tier
    lines.append(f"## Geocoding Rate by Score Tier")
    lines.append(f"")
    lines.append(f"| Score Tier | Total | Geocoded | % Geocoded |")
    lines.append(f"|------------|------:|--------:|-----------:|")
    for r in tier_rows:
        lines.append(
            f"| {r['score_tier']} | {r['total']:,} | {r['geocoded']:,} | {r['pct']}% |"
        )
    lines.append(f"")

    # Overall Rate
    lines.append(f"## Overall Rate")
    lines.append(f"")
    lines.append(f"| Metric | Value |")
    lines.append(f"|--------|------:|")
    lines.append(f"| Total employers | {overall['total']:,} |")
    lines.append(f"| Geocoded | {overall['geocoded']:,} |")
    lines.append(f"| Missing coordinates | {overall['total'] - overall['geocoded']:,} |")
    lines.append(f"| Geocoding rate | {overall['pct']}% |")
    lines.append(f"")

    # Top States with Gaps
    lines.append(f"## Top 10 States with Geocoding Gaps")
    lines.append(f"")
    lines.append(f"| State | Total | Missing | % Missing |")
    lines.append(f"|-------|------:|--------:|----------:|")
    for r in state_rows:
        lines.append(
            f"| {r['state']} | {r['total']:,} | {r['missing']:,} | {r['pct_missing']}% |"
        )
    lines.append(f"")

    # Implications
    lines.append(f"## Implications")
    lines.append(f"")
    lines.append(
        f"- Geocoding gaps affect geographic search, map visualizations, "
        f"and metro-level analysis."
    )
    lines.append(
        f"- If higher-priority tiers have lower geocoding rates, those employers "
        f"are under-represented in location-based features."
    )
    lines.append(
        f"- States with the largest absolute gaps should be prioritized for "
        f"batch geocoding runs (Census Bureau batch geocoder, max 10K per batch)."
    )
    lines.append(
        f"- Consider geocoding Priority and Strong tiers first to maximize "
        f"value from the geocoding pipeline."
    )
    lines.append(f"")

    # Write file
    os.makedirs(os.path.dirname(args.output), exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    # Print summary to stdout
    print(f"I11 - Geocoding Gap by Score Tier")
    print(f"  Output: {args.output}")
    print(f"  Overall geocoding rate: {overall['geocoded']:,} / {overall['total']:,} ({overall['pct']}%)")
    print(f"  Tiers:")
    for r in tier_rows:
        print(f"    {r['score_tier']:12s}  {r['geocoded']:,} / {r['total']:,} ({r['pct']}%)")
    print(f"  Top gap state: {state_rows[0]['state']} ({state_rows[0]['missing']:,} missing)" if state_rows else "  No state gaps found")


if __name__ == "__main__":
    main()
