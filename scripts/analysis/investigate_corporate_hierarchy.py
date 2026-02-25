"""
I20 - Corporate Hierarchy (Factor 1) Coverage
Analyzes corporate_family_id coverage, crosswalk statistics, hierarchy edges,
score_union_proximity distribution, and overlap between canonical groups
and corporate families.
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
        description="I20 - Corporate Hierarchy (Factor 1) Coverage"
    )
    parser.add_argument(
        "--output",
        default=os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
            "docs", "investigations", "I20_corporate_hierarchy_coverage.md",
        ),
        help="Output markdown file path",
    )
    args = parser.parse_args()

    conn = get_connection(cursor_factory=RealDictCursor)
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)

        # Query 1: Corporate family coverage from mv_employer_data_sources
        cur.execute("""
            SELECT
                COUNT(*) AS total_f7,
                COUNT(corporate_family_id) AS has_corp_family,
                ROUND(100.0 * COUNT(corporate_family_id) / COUNT(*), 1) AS pct_corp_family
            FROM mv_employer_data_sources
        """)
        corp_coverage = cur.fetchone()

        # Query 2: Corporate crosswalk coverage
        cur.execute("""
            SELECT COUNT(*) AS crosswalk_entries,
                   COUNT(DISTINCT f7_employer_id) AS distinct_employers,
                   COUNT(DISTINCT corporate_family_id) AS distinct_families
            FROM corporate_identifier_crosswalk
        """)
        crosswalk = cur.fetchone()

        # Query 3: Corporate hierarchy edges (may not exist)
        hierarchy = None
        hierarchy_error = None
        try:
            cur.execute("""
                SELECT COUNT(*) AS total_edges,
                       COUNT(DISTINCT parent_id) AS distinct_parents,
                       COUNT(DISTINCT child_id) AS distinct_children
                FROM corporate_hierarchy
            """)
            hierarchy = cur.fetchone()
        except Exception as e:
            conn.rollback()
            hierarchy_error = str(e)

        # Query 4: score_union_proximity distribution from mv_unified_scorecard
        cur.execute("""
            SELECT
                COUNT(*) FILTER (WHERE score_union_proximity IS NOT NULL) AS has_proximity_score,
                COUNT(*) FILTER (WHERE score_union_proximity = 10) AS score_10,
                COUNT(*) FILTER (WHERE score_union_proximity = 5) AS score_5,
                COUNT(*) FILTER (WHERE score_union_proximity = 0) AS score_0,
                COUNT(*) FILTER (WHERE score_union_proximity IS NULL) AS score_null
            FROM mv_unified_scorecard
        """)
        proximity_dist = cur.fetchone()

        # Query 5: Overlap between canonical_group_id and corporate_family_id
        cur.execute("""
            SELECT
                COUNT(*) FILTER (WHERE canonical_group_id IS NOT NULL AND corporate_family_id IS NOT NULL) AS both,
                COUNT(*) FILTER (WHERE canonical_group_id IS NOT NULL AND corporate_family_id IS NULL) AS group_only,
                COUNT(*) FILTER (WHERE canonical_group_id IS NULL AND corporate_family_id IS NOT NULL) AS corp_only,
                COUNT(*) FILTER (WHERE canonical_group_id IS NULL AND corporate_family_id IS NULL) AS neither
            FROM mv_employer_data_sources
        """)
        overlap = cur.fetchone()

        cur.close()
    finally:
        conn.close()

    total = corp_coverage["total_f7"]

    # Build markdown report
    lines = []
    lines.append("# I20 - Corporate Hierarchy (Factor 1) Coverage")
    lines.append("")
    lines.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    lines.append("")

    # Summary
    lines.append("## Summary")
    lines.append("")
    lines.append(
        f"**{corp_coverage['has_corp_family']:,}** / **{total:,}** F7 employers "
        f"({corp_coverage['pct_corp_family']}%) have a `corporate_family_id`. "
        f"The corporate identifier crosswalk contains **{crosswalk['crosswalk_entries']:,}** "
        f"entries spanning **{crosswalk['distinct_families']:,}** distinct corporate families."
    )
    lines.append("")

    # Corporate Family Coverage
    lines.append("## Corporate Family Coverage")
    lines.append("")
    lines.append("| Metric | Value |")
    lines.append("|--------|------:|")
    lines.append(f"| Total F7 employers (in mv_employer_data_sources) | {total:,} |")
    lines.append(f"| With corporate_family_id | {corp_coverage['has_corp_family']:,} |")
    lines.append(f"| Without corporate_family_id | {total - corp_coverage['has_corp_family']:,} |")
    lines.append(f"| Coverage rate | {corp_coverage['pct_corp_family']}% |")
    lines.append("")

    # Crosswalk Statistics
    lines.append("## Crosswalk Statistics")
    lines.append("")
    lines.append("| Metric | Value |")
    lines.append("|--------|------:|")
    lines.append(f"| Total crosswalk entries | {crosswalk['crosswalk_entries']:,} |")
    lines.append(f"| Distinct employers | {crosswalk['distinct_employers']:,} |")
    lines.append(f"| Distinct corporate families | {crosswalk['distinct_families']:,} |")
    if crosswalk["distinct_families"] > 0:
        avg_per_family = round(
            crosswalk["crosswalk_entries"] / crosswalk["distinct_families"], 1
        )
        lines.append(f"| Avg entries per family | {avg_per_family} |")
    lines.append("")

    # Corporate Hierarchy
    lines.append("## Corporate Hierarchy")
    lines.append("")
    if hierarchy is not None:
        lines.append("| Metric | Value |")
        lines.append("|--------|------:|")
        lines.append(f"| Total edges | {hierarchy['total_edges']:,} |")
        lines.append(f"| Distinct parents | {hierarchy['distinct_parents']:,} |")
        lines.append(f"| Distinct children | {hierarchy['distinct_children']:,} |")
    else:
        lines.append(
            f"*`corporate_hierarchy` table does not exist.* "
            f"Error: `{hierarchy_error}`"
        )
    lines.append("")

    # Score Union Proximity Distribution
    lines.append("## Score Union Proximity Distribution")
    lines.append("")
    lines.append(
        "The `score_union_proximity` factor from `mv_unified_scorecard` "
        "uses canonical group size and corporate family membership:"
    )
    lines.append("")
    lines.append("| Score Value | Count | % |")
    lines.append("|------------|------:|--:|")
    total_scored = (
        proximity_dist["score_10"]
        + proximity_dist["score_5"]
        + proximity_dist["score_0"]
        + proximity_dist["score_null"]
    )
    for label, key in [("10 (group >= 3)", "score_10"), ("5 (group = 2 or corp family)", "score_5"),
                       ("0 (no group, no corp)", "score_0"), ("NULL", "score_null")]:
        cnt = proximity_dist[key]
        pct = round(100.0 * cnt / total_scored, 1) if total_scored > 0 else 0
        lines.append(f"| {label} | {cnt:,} | {pct}% |")
    lines.append("")

    # Canonical Group vs Corporate Family Overlap
    lines.append("## Canonical Group vs Corporate Family Overlap")
    lines.append("")
    lines.append("| Category | Count | % |")
    lines.append("|----------|------:|--:|")
    for label, key in [
        ("Both canonical_group_id AND corporate_family_id", "both"),
        ("canonical_group_id only", "group_only"),
        ("corporate_family_id only", "corp_only"),
        ("Neither", "neither"),
    ]:
        cnt = overlap[key]
        pct = round(100.0 * cnt / total, 1) if total > 0 else 0
        lines.append(f"| {label} | {cnt:,} | {pct}% |")
    lines.append("")

    # How Factor 1 Actually Works
    lines.append("## How Factor 1 (score_union_proximity) Actually Works")
    lines.append("")
    lines.append("From `build_unified_scorecard.py`, the SQL formula is:")
    lines.append("")
    lines.append("```sql")
    lines.append("CASE")
    lines.append("    WHEN up.member_count IS NULL AND eds.corporate_family_id IS NULL THEN NULL")
    lines.append("    WHEN GREATEST(COALESCE(up.member_count, 1) - 1, 0) >= 2 THEN 10")
    lines.append("    WHEN GREATEST(COALESCE(up.member_count, 1) - 1, 0) = 1")
    lines.append("         OR eds.corporate_family_id IS NOT NULL THEN 5")
    lines.append("    ELSE 0")
    lines.append("END AS score_union_proximity")
    lines.append("```")
    lines.append("")
    lines.append("Logic breakdown:")
    lines.append("")
    lines.append("- **Score 10**: Employer is in a canonical group with 3+ members (i.e., `member_count - 1 >= 2`, meaning at least 2 other union-represented locations).")
    lines.append("- **Score 5**: Employer is in a canonical group with exactly 2 members (1 peer), OR has a `corporate_family_id` (identified as part of a corporate family via SEC/GLEIF/CorpWatch data).")
    lines.append("- **Score 0**: Employer has a canonical group or corporate family entry but no peers.")
    lines.append("- **NULL**: No canonical group data and no corporate family data.")
    lines.append("")

    # Implications
    lines.append("## Implications")
    lines.append("")
    corp_pct = float(corp_coverage["pct_corp_family"])
    if corp_pct < 5.0:
        lines.append(
            f"- **Low corporate coverage ({corp_pct}%)**: The corporate_family_id "
            f"data covers fewer than 5% of employers. This means the corporate "
            f"hierarchy contributes minimally to score_union_proximity for most "
            f"employers. Consider reducing the weight of the corporate component "
            f"or investing in additional corporate data enrichment (e.g., more "
            f"CorpWatch/SEC/GLEIF matching)."
        )
    else:
        lines.append(
            f"- Corporate family coverage at {corp_pct}% provides meaningful "
            f"signal for the proximity factor."
        )
    lines.append(
        "- Employers with `corp_only` (corporate family but no canonical group) "
        "receive score_union_proximity = 5 solely from the corporate crosswalk. "
        "This is a binary boost, not a graduated signal."
    )
    lines.append(
        "- The NULL population receives no proximity score at all, which means "
        "the weighted average excludes this factor for them (reducing their "
        "factors_available count)."
    )
    lines.append(
        "- If the canonical grouping pipeline already covers most multi-location "
        "employers, the marginal value of corporate hierarchy is limited to "
        "single-location employers that happen to be subsidiaries."
    )
    lines.append("")

    # Write file
    os.makedirs(os.path.dirname(args.output), exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    # Print summary
    print("I20 - Corporate Hierarchy (Factor 1) Coverage")
    print(f"  Output: {args.output}")
    print(f"  Corporate family coverage: {corp_coverage['has_corp_family']:,} / {total:,} ({corp_coverage['pct_corp_family']}%)")
    print(f"  Crosswalk: {crosswalk['crosswalk_entries']:,} entries, {crosswalk['distinct_families']:,} families")
    if hierarchy is not None:
        print(f"  Hierarchy: {hierarchy['total_edges']:,} edges")
    else:
        print(f"  Hierarchy: table not found")
    print(f"  Proximity distribution: 10={proximity_dist['score_10']:,}, 5={proximity_dist['score_5']:,}, "
          f"0={proximity_dist['score_0']:,}, NULL={proximity_dist['score_null']:,}")
    print(f"  Overlap: both={overlap['both']:,}, group_only={overlap['group_only']:,}, "
          f"corp_only={overlap['corp_only']:,}, neither={overlap['neither']:,}")


if __name__ == "__main__":
    main()
