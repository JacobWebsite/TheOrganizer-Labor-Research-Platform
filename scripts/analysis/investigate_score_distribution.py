"""
I17 - Score Distribution After Phase 1 Fixes
Analyzes tier distribution, weighted score histogram, per-factor statistics,
factor coverage, and overall score characteristics post-Phase-1.
"""
import argparse
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
from db_config import get_connection
from psycopg2.extras import RealDictCursor

FACTORS = [
    "score_osha",
    "score_nlrb",
    "score_whd",
    "score_contracts",
    "score_union_proximity",
    "score_industry_growth",
    "score_size",
    "score_similarity",
    "score_financial",
]


def main():
    parser = argparse.ArgumentParser(
        description="I17 - Score Distribution After Phase 1 Fixes"
    )
    parser.add_argument(
        "--output",
        default=os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
            "docs", "investigations", "I17_score_distribution_phase1.md",
        ),
        help="Output markdown file path",
    )
    args = parser.parse_args()

    conn = get_connection(cursor_factory=RealDictCursor)
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)

        # Query 1: Tier distribution
        cur.execute("""
            SELECT score_tier, COUNT(*) AS cnt,
                   ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 1) AS pct
            FROM mv_unified_scorecard
            GROUP BY score_tier
            ORDER BY CASE score_tier
                WHEN 'Priority' THEN 1 WHEN 'Strong' THEN 2
                WHEN 'Promising' THEN 3 WHEN 'Moderate' THEN 4
                WHEN 'Low' THEN 5 END
        """)
        tier_rows = cur.fetchall()

        # Query 2: Weighted score histogram (1-unit bins)
        cur.execute("""
            SELECT FLOOR(weighted_score)::int AS bin_floor,
                   COUNT(*) AS cnt
            FROM mv_unified_scorecard
            WHERE weighted_score IS NOT NULL
            GROUP BY FLOOR(weighted_score)::int
            ORDER BY bin_floor
        """)
        hist_rows = cur.fetchall()

        # Query 3: Per-factor statistics (UNION ALL)
        factor_selects = []
        for f in FACTORS:
            factor_selects.append(f"""
                SELECT '{f}' AS factor,
                       COUNT(*) AS total,
                       COUNT({f}) AS non_null,
                       ROUND(100.0 * COUNT({f}) / COUNT(*), 1) AS coverage_pct,
                       ROUND(AVG({f})::numeric, 2) AS mean,
                       PERCENTILE_CONT(0.25) WITHIN GROUP (ORDER BY {f}) AS p25,
                       PERCENTILE_CONT(0.50) WITHIN GROUP (ORDER BY {f}) AS p50,
                       PERCENTILE_CONT(0.75) WITHIN GROUP (ORDER BY {f}) AS p75
                FROM mv_unified_scorecard
            """)
        cur.execute("\nUNION ALL\n".join(factor_selects))
        factor_rows = cur.fetchall()

        # Query 4: Overall weighted_score stats
        cur.execute("""
            SELECT
                ROUND(MIN(weighted_score)::numeric, 2) AS min_score,
                ROUND(MAX(weighted_score)::numeric, 2) AS max_score,
                ROUND(AVG(weighted_score)::numeric, 2) AS avg_score,
                ROUND(STDDEV(weighted_score)::numeric, 2) AS stddev_score,
                ROUND(PERCENTILE_CONT(0.25) WITHIN GROUP (ORDER BY weighted_score)::numeric, 2) AS p25,
                ROUND(PERCENTILE_CONT(0.50) WITHIN GROUP (ORDER BY weighted_score)::numeric, 2) AS p50,
                ROUND(PERCENTILE_CONT(0.75) WITHIN GROUP (ORDER BY weighted_score)::numeric, 2) AS p75
            FROM mv_unified_scorecard
            WHERE weighted_score IS NOT NULL
        """)
        overall_stats = cur.fetchone()

        # Query 5: Factors_available distribution
        cur.execute("""
            SELECT factors_available, COUNT(*) AS cnt,
                   ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 1) AS pct
            FROM mv_unified_scorecard
            GROUP BY factors_available
            ORDER BY factors_available
        """)
        factor_avail_rows = cur.fetchall()

        cur.close()
    finally:
        conn.close()

    # Compute max histogram count for ASCII bar scaling
    max_hist = max((r["cnt"] for r in hist_rows), default=1)
    bar_max_width = 40

    # Build markdown report
    lines = []
    lines.append("# I17 - Score Distribution After Phase 1 Fixes")
    lines.append("")
    lines.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    lines.append("")

    # Summary
    lines.append("## Summary")
    lines.append("")
    total_employers = tier_rows[0]["cnt"] + sum(r["cnt"] for r in tier_rows[1:]) if tier_rows else 0
    total_employers = sum(r["cnt"] for r in tier_rows)
    lines.append(
        f"Total scored employers: **{total_employers:,}**. "
        f"Weighted score range: {overall_stats['min_score']}-{overall_stats['max_score']}, "
        f"mean {overall_stats['avg_score']}, median {overall_stats['p50']}."
    )
    lines.append("")

    # Tier Distribution
    lines.append("## Tier Distribution")
    lines.append("")
    lines.append("| Tier | Count | % |")
    lines.append("|------|------:|--:|")
    for r in tier_rows:
        lines.append(f"| {r['score_tier']} | {r['cnt']:,} | {r['pct']}% |")
    lines.append("")

    # Score Histogram
    lines.append("## Weighted Score Histogram")
    lines.append("")
    lines.append("```")
    lines.append(f"{'Bin':>5s}  {'Count':>7s}  Bar")
    for r in hist_rows:
        bar_len = int(r["cnt"] / max_hist * bar_max_width) if max_hist > 0 else 0
        bar = "#" * bar_len
        label = f"{r['bin_floor']}-{r['bin_floor'] + 1}"
        lines.append(f"{label:>5s}  {r['cnt']:>7,}  {bar}")
    lines.append("```")
    lines.append("")

    # Per-Factor Statistics
    lines.append("## Per-Factor Statistics")
    lines.append("")
    lines.append("| Factor | Non-Null | Coverage % | Mean | P25 | P50 | P75 |")
    lines.append("|--------|--------:|-----------:|-----:|----:|----:|----:|")
    for r in factor_rows:
        p25 = f"{float(r['p25']):.2f}" if r["p25"] is not None else "-"
        p50 = f"{float(r['p50']):.2f}" if r["p50"] is not None else "-"
        p75 = f"{float(r['p75']):.2f}" if r["p75"] is not None else "-"
        mean = f"{float(r['mean']):.2f}" if r["mean"] is not None else "-"
        lines.append(
            f"| {r['factor']} | {r['non_null']:,} | {r['coverage_pct']}% "
            f"| {mean} | {p25} | {p50} | {p75} |"
        )
    lines.append("")

    # Weighted Score Overall Stats
    lines.append("## Weighted Score Overall Stats")
    lines.append("")
    lines.append("| Statistic | Value |")
    lines.append("|-----------|------:|")
    lines.append(f"| Min | {overall_stats['min_score']} |")
    lines.append(f"| Max | {overall_stats['max_score']} |")
    lines.append(f"| Mean | {overall_stats['avg_score']} |")
    lines.append(f"| Std Dev | {overall_stats['stddev_score']} |")
    lines.append(f"| P25 | {overall_stats['p25']} |")
    lines.append(f"| Median (P50) | {overall_stats['p50']} |")
    lines.append(f"| P75 | {overall_stats['p75']} |")
    lines.append("")

    # Factor Coverage Distribution
    lines.append("## Factor Coverage Distribution")
    lines.append("")
    lines.append("Number of non-null score factors per employer:")
    lines.append("")
    lines.append("| Factors Available | Count | % |")
    lines.append("|------------------:|------:|--:|")
    for r in factor_avail_rows:
        lines.append(f"| {r['factors_available']} | {r['cnt']:,} | {r['pct']}% |")
    lines.append("")

    # Comparison to Pre-Phase-1
    lines.append("## Comparison to Pre-Phase-1")
    lines.append("")
    lines.append(
        "Before Phase 1 fixes, the weighted score distribution was bimodal with "
        "peaks at 0-1.5 (employers with sparse data) and 5-6.5 (employers with "
        "union proximity and industry growth only). Phase 1 fixes addressed:"
    )
    lines.append("")
    lines.append("- **score_contracts**: Was flat 4.00 for all contractors. Now uses obligation-based tiers (1/2/4/6/8/10).")
    lines.append("- **score_financial**: Was BLS-growth-only. Now uses 990 revenue scale + asset cushion + revenue-per-worker.")
    lines.append("- **score_tier**: Now percentile-based instead of fixed thresholds.")
    lines.append("- **score_nlrb**: Added ULP boost tiers (1=2, 2-3=4, 4-9=6, 10+=8) and 7yr decay.")
    lines.append("")

    # Implications
    lines.append("## Implications")
    lines.append("")
    lines.append(
        "- Check whether the bimodal distribution has smoothed out after Phase 1 fixes."
    )
    lines.append(
        "- Factors with low coverage (e.g., score_similarity at ~0.1%) contribute "
        "little to differentiation and may warrant reduced weight or removal."
    )
    lines.append(
        "- If the majority of employers cluster in 2-3 factors_available, "
        "score precision is limited and additional data enrichment would help."
    )
    lines.append("")

    # Write file
    os.makedirs(os.path.dirname(args.output), exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    # Print summary
    print("I17 - Score Distribution After Phase 1 Fixes")
    print(f"  Output: {args.output}")
    print(f"  Total employers: {total_employers:,}")
    print(f"  Weighted score: {overall_stats['min_score']}-{overall_stats['max_score']}, "
          f"mean={overall_stats['avg_score']}, median={overall_stats['p50']}")
    print(f"  Tiers:")
    for r in tier_rows:
        print(f"    {r['score_tier']:12s}  {r['cnt']:>7,}  ({r['pct']}%)")
    print(f"  Factor coverage distribution:")
    for r in factor_avail_rows:
        print(f"    {r['factors_available']} factors: {r['cnt']:>7,}  ({r['pct']}%)")


if __name__ == "__main__":
    main()
