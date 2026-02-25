"""
I18 - Active Unions (Filed LM in Last 3 Years)
Counts active unions by recency, cross-references with unions_master,
compares to BLS national estimates, and identifies top unions by employer count.
"""
import argparse
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
from db_config import get_connection
from psycopg2.extras import RealDictCursor


def main():
    parser = argparse.ArgumentParser(
        description="I18 - Active Unions (Filed LM in Last 3 Years)"
    )
    parser.add_argument(
        "--output",
        default=os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
            "docs", "investigations", "I18_active_unions.md",
        ),
        help="Output markdown file path",
    )
    args = parser.parse_args()

    conn = get_connection(cursor_factory=RealDictCursor)
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)

        # Query 1: Active union count (filed LM with yr_covered >= 2022)
        cur.execute("""
            SELECT COUNT(DISTINCT f_num) AS active_unions
            FROM lm_data
            WHERE yr_covered >= 2022
        """)
        active_count = cur.fetchone()["active_unions"]

        # Total distinct unions in lm_data
        cur.execute("SELECT COUNT(DISTINCT f_num) AS total_unions FROM lm_data")
        total_lm_unions = cur.fetchone()["total_unions"]

        # Query 2: Recency breakdown
        cur.execute("""
            SELECT
                CASE
                    WHEN max_yr >= 2024 THEN 'Filed 2024'
                    WHEN max_yr = 2023 THEN 'Filed 2023'
                    WHEN max_yr = 2022 THEN 'Filed 2022'
                    WHEN max_yr >= 2019 THEN 'Filed 2019-2021'
                    ELSE 'Older or unknown'
                END AS recency_bucket,
                COUNT(*) AS union_count
            FROM (
                SELECT f_num, MAX(yr_covered) AS max_yr
                FROM lm_data
                GROUP BY f_num
            ) sub
            GROUP BY 1
            ORDER BY MIN(max_yr) DESC
        """)
        recency_rows = cur.fetchall()

        # Query 3: Cross-reference with unions_master
        unions_master_info = None
        has_f7_column = True
        try:
            cur.execute("""
                SELECT
                    COUNT(*) AS total_unions_master,
                    COUNT(*) FILTER (WHERE has_f7_employers) AS with_f7_employers,
                    COUNT(*) FILTER (WHERE NOT has_f7_employers OR has_f7_employers IS NULL) AS without_f7_employers
                FROM unions_master
            """)
            unions_master_info = cur.fetchone()
        except Exception:
            conn.rollback()
            # Try without has_f7_employers column
            has_f7_column = False
            try:
                cur.execute("SELECT COUNT(*) AS total_unions_master FROM unions_master")
                row = cur.fetchone()
                unions_master_info = {
                    "total_unions_master": row["total_unions_master"],
                    "with_f7_employers": None,
                    "without_f7_employers": None,
                }
            except Exception:
                conn.rollback()
                unions_master_info = None

        # Query 5: Top 10 unions by employer count
        top_unions = []
        try:
            cur.execute("""
                SELECT um.union_name, COUNT(DISTINCT e.employer_id) AS employer_count
                FROM unions_master um
                JOIN f7_employers_deduped e ON e.latest_union_fnum = um.f_num
                GROUP BY um.union_name
                ORDER BY employer_count DESC
                LIMIT 10
            """)
            top_unions = cur.fetchall()
        except Exception:
            conn.rollback()
            # Fallback: latest_union_fnum may not exist
            top_unions = []

        cur.close()
    finally:
        conn.close()

    # Build markdown report
    lines = []
    lines.append("# I18 - Active Unions (Filed LM in Last 3 Years)")
    lines.append("")
    lines.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    lines.append("")

    # Summary
    lines.append("## Summary")
    lines.append("")
    lines.append(
        f"**{active_count:,}** unions filed an LM report with `yr_covered >= 2022`, "
        f"out of **{total_lm_unions:,}** total distinct unions in `lm_data`."
    )
    lines.append("")

    # Active Union Counts
    lines.append("## Active Union Counts")
    lines.append("")
    lines.append(f"| Metric | Count |")
    lines.append(f"|--------|------:|")
    lines.append(f"| Unions with LM filed 2022+ | {active_count:,} |")
    lines.append(f"| Total distinct unions in lm_data | {total_lm_unions:,} |")
    lines.append(
        f"| Active rate | "
        f"{round(100.0 * active_count / total_lm_unions, 1) if total_lm_unions else 0}% |"
    )
    lines.append("")

    # Recency Breakdown
    lines.append("## Recency Breakdown")
    lines.append("")
    lines.append("Most recent LM filing year per union:")
    lines.append("")
    lines.append("| Recency Bucket | Union Count |")
    lines.append("|----------------|------------:|")
    for r in recency_rows:
        lines.append(f"| {r['recency_bucket']} | {r['union_count']:,} |")
    lines.append("")

    # BLS Comparison
    lines.append("## BLS Comparison")
    lines.append("")
    lines.append(
        "BLS reports approximately **16,000** unions nationally (based on the "
        "Current Population Survey union membership data). Our LM filings show "
        f"**{active_count:,}** active unions (2022+), and **{total_lm_unions:,}** "
        "total unions with any LM filing on record."
    )
    lines.append("")
    if active_count > 16000:
        lines.append(
            f"Our count exceeds the BLS estimate by ~{active_count - 16000:,}. "
            "This likely reflects the fact that LM filings include locals, councils, "
            "and intermediate bodies that the BLS counts as part of a single national union."
        )
    elif active_count < 16000:
        lines.append(
            f"Our count is below the BLS estimate by ~{16000 - active_count:,}. "
            "Some unions may not have filed recent LM reports, or small locals may "
            "be exempt from filing requirements."
        )
    else:
        lines.append("Our count closely matches the BLS estimate.")
    lines.append("")

    # unions_master Coverage
    lines.append("## unions_master Coverage")
    lines.append("")
    if unions_master_info is None:
        lines.append("*`unions_master` table not found or not accessible.*")
    elif not has_f7_column:
        lines.append(f"| Metric | Count |")
        lines.append(f"|--------|------:|")
        lines.append(
            f"| Total in unions_master | {unions_master_info['total_unions_master']:,} |"
        )
        lines.append("")
        lines.append("*Note: `has_f7_employers` column does not exist on `unions_master`.*")
    else:
        lines.append(f"| Metric | Count |")
        lines.append(f"|--------|------:|")
        lines.append(
            f"| Total in unions_master | {unions_master_info['total_unions_master']:,} |"
        )
        lines.append(
            f"| With F7 employers | {unions_master_info['with_f7_employers']:,} |"
        )
        lines.append(
            f"| Without F7 employers | {unions_master_info['without_f7_employers']:,} |"
        )
    lines.append("")

    # Top 10 Unions by Employer Count
    lines.append("## Top 10 Unions by Employer Count")
    lines.append("")
    if top_unions:
        lines.append("| Union Name | Employer Count |")
        lines.append("|------------|---------------:|")
        for r in top_unions:
            lines.append(f"| {r['union_name']} | {r['employer_count']:,} |")
    else:
        lines.append(
            "*Could not retrieve top unions (column `latest_union_fnum` may not exist "
            "on `f7_employers_deduped`, or `unions_master` may not be joinable).*"
        )
    lines.append("")

    # Implications
    lines.append("## Implications")
    lines.append("")
    lines.append(
        "- The active union count provides a baseline for how many unions are "
        "currently reporting. Unions that stopped filing may have dissolved, merged, "
        "or fallen below filing thresholds."
    )
    lines.append(
        "- The recency breakdown helps identify unions that may need follow-up "
        "or whose employer relationships could be stale."
    )
    lines.append(
        "- Cross-referencing with unions_master shows how well our union directory "
        "covers the employer-union relationships in the F7 data."
    )
    lines.append(
        "- Comparing to BLS totals helps calibrate expectations about coverage "
        "and identify potential gaps in the LM filing data."
    )
    lines.append("")

    # Write file
    os.makedirs(os.path.dirname(args.output), exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    # Print summary
    print("I18 - Active Unions (Filed LM in Last 3 Years)")
    print(f"  Output: {args.output}")
    print(f"  Active unions (2022+): {active_count:,}")
    print(f"  Total unions in lm_data: {total_lm_unions:,}")
    print(f"  Recency breakdown:")
    for r in recency_rows:
        print(f"    {r['recency_bucket']:20s}  {r['union_count']:>6,}")
    if top_unions:
        print(f"  Top union: {top_unions[0]['union_name']} ({top_unions[0]['employer_count']:,} employers)")


if __name__ == "__main__":
    main()
