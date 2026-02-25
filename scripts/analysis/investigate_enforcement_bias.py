"""
I12 - Geographic Enforcement Bias Analysis
Asks: does geographic enforcement density (more OSHA inspections in some states)
systematically inflate organizing scores?

Computes OSHA match rates per state, correlates with average weighted_score,
breaks down within-industry comparisons, and isolates which score components
are most affected by enforcement geography.
"""
import argparse
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
from db_config import get_connection
from psycopg2.extras import RealDictCursor


def pearson_r(xs, ys):
    """Compute Pearson correlation coefficient without numpy."""
    n = len(xs)
    if n < 3:
        return None
    mean_x = sum(xs) / n
    mean_y = sum(ys) / n
    num = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))
    den_x = sum((x - mean_x) ** 2 for x in xs) ** 0.5
    den_y = sum((y - mean_y) ** 2 for y in ys) ** 0.5
    if den_x == 0 or den_y == 0:
        return None
    return num / (den_x * den_y)


def percentile(values, pct):
    """Compute percentile from a sorted list (linear interpolation)."""
    if not values:
        return 0
    s = sorted(values)
    k = (len(s) - 1) * pct / 100.0
    f = int(k)
    c = f + 1
    if c >= len(s):
        return s[f]
    return s[f] + (k - f) * (s[c] - s[f])


def fmt(val, decimals=2):
    """Format a numeric value for markdown, handling None."""
    if val is None:
        return "N/A"
    return f"{float(val):.{decimals}f}"


def main():
    parser = argparse.ArgumentParser(
        description="I12 - Geographic Enforcement Bias Analysis"
    )
    parser.add_argument(
        "--output",
        default=os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
            "docs", "investigations", "I12_geographic_enforcement_bias.md",
        ),
        help="Output markdown file path",
    )
    args = parser.parse_args()

    conn = get_connection(cursor_factory=RealDictCursor)
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)

        # ------------------------------------------------------------------
        # Query 1: OSHA match rate per state
        # ------------------------------------------------------------------
        cur.execute("""
            SELECT f.state,
                   COUNT(DISTINCT f.employer_id) AS total_f7,
                   COUNT(DISTINCT CASE WHEN uml.id IS NOT NULL
                         THEN f.employer_id END) AS osha_matched,
                   ROUND(100.0 * COUNT(DISTINCT CASE WHEN uml.id IS NOT NULL
                         THEN f.employer_id END)
                         / NULLIF(COUNT(DISTINCT f.employer_id), 0), 1
                   ) AS osha_match_pct
            FROM f7_employers_deduped f
            LEFT JOIN unified_match_log uml
              ON uml.target_id = f.employer_id
              AND uml.source_system = 'osha'
              AND uml.status = 'active'
            WHERE f.state IS NOT NULL
            GROUP BY f.state
            ORDER BY osha_match_pct DESC
        """)
        osha_by_state = cur.fetchall()

        # Build lookup: state -> osha_match_pct
        osha_pct_map = {
            r["state"]: float(r["osha_match_pct"] or 0)
            for r in osha_by_state
        }

        # ------------------------------------------------------------------
        # Query 2: Average weighted_score per state
        # ------------------------------------------------------------------
        cur.execute("""
            SELECT state,
                   COUNT(*) AS employers,
                   ROUND(AVG(weighted_score)::numeric, 2) AS avg_score,
                   ROUND(STDDEV(weighted_score)::numeric, 2) AS std_score,
                   ROUND(PERCENTILE_CONT(0.5) WITHIN GROUP
                         (ORDER BY weighted_score)::numeric, 2) AS median_score
            FROM mv_unified_scorecard
            WHERE state IS NOT NULL
            GROUP BY state
            ORDER BY avg_score DESC
        """)
        score_by_state = cur.fetchall()

        score_map = {
            r["state"]: r for r in score_by_state
        }

        # ------------------------------------------------------------------
        # Combine scatter data and compute correlation
        # ------------------------------------------------------------------
        scatter_data = []
        for r in osha_by_state:
            st = r["state"]
            if st in score_map:
                scatter_data.append({
                    "state": st,
                    "osha_match_pct": float(r["osha_match_pct"] or 0),
                    "avg_score": float(score_map[st]["avg_score"] or 0),
                    "total_f7": r["total_f7"],
                    "osha_matched": r["osha_matched"],
                    "employers_scored": score_map[st]["employers"],
                    "median_score": float(score_map[st]["median_score"] or 0),
                })
        scatter_data.sort(key=lambda x: x["osha_match_pct"], reverse=True)

        xs = [d["osha_match_pct"] for d in scatter_data]
        ys = [d["avg_score"] for d in scatter_data]
        r_value = pearson_r(xs, ys)

        # Also correlate with median
        ys_median = [d["median_score"] for d in scatter_data]
        r_median = pearson_r(xs, ys_median)

        # ------------------------------------------------------------------
        # Determine enforcement quartiles
        # ------------------------------------------------------------------
        all_pcts = sorted([float(r["osha_match_pct"] or 0) for r in osha_by_state])
        q75 = percentile(all_pcts, 75)
        q25 = percentile(all_pcts, 25)

        high_enforcement_states = [
            r["state"] for r in osha_by_state
            if float(r["osha_match_pct"] or 0) >= q75
        ]
        low_enforcement_states = [
            r["state"] for r in osha_by_state
            if float(r["osha_match_pct"] or 0) <= q25
        ]

        # ------------------------------------------------------------------
        # Query 3: Top 5 most common 2-digit NAICS codes
        # ------------------------------------------------------------------
        cur.execute("""
            SELECT LEFT(naics, 2) AS naics_2, COUNT(*) AS cnt
            FROM mv_unified_scorecard
            WHERE naics IS NOT NULL
            GROUP BY LEFT(naics, 2)
            ORDER BY cnt DESC
            LIMIT 5
        """)
        top_naics = cur.fetchall()

        # ------------------------------------------------------------------
        # Query 4: Within-industry comparison (high vs low enforcement)
        # ------------------------------------------------------------------
        industry_comparisons = []
        for naics_row in top_naics:
            naics_2 = naics_row["naics_2"]
            cur.execute("""
                SELECT
                    CASE WHEN u.state = ANY(%(high)s) THEN 'HIGH'
                         WHEN u.state = ANY(%(low)s) THEN 'LOW'
                    END AS enforcement_level,
                    COUNT(*) AS employers,
                    ROUND(AVG(u.weighted_score)::numeric, 2) AS avg_score,
                    ROUND(AVG(u.score_osha)::numeric, 2) AS avg_score_osha
                FROM mv_unified_scorecard u
                WHERE LEFT(u.naics, 2) = %(naics)s
                  AND (u.state = ANY(%(high)s) OR u.state = ANY(%(low)s))
                GROUP BY 1
                ORDER BY 1
            """, {
                "high": high_enforcement_states,
                "low": low_enforcement_states,
                "naics": naics_2,
            })
            rows = cur.fetchall()
            industry_comparisons.append({
                "naics_2": naics_2,
                "count": naics_row["cnt"],
                "rows": rows,
            })

        # ------------------------------------------------------------------
        # Query 5: Score component isolation (high vs low enforcement)
        # ------------------------------------------------------------------
        cur.execute("""
            SELECT
                CASE WHEN u.state = ANY(%(high)s) THEN 'HIGH_ENFORCEMENT'
                     ELSE 'LOW_ENFORCEMENT' END AS group_label,
                COUNT(*) AS employers,
                ROUND(AVG(weighted_score)::numeric, 2) AS avg_weighted,
                ROUND(AVG(score_osha)::numeric, 2) AS avg_osha,
                ROUND(AVG(score_nlrb)::numeric, 2) AS avg_nlrb,
                ROUND(AVG(score_whd)::numeric, 2) AS avg_whd,
                ROUND(AVG(score_contracts)::numeric, 2) AS avg_contracts,
                ROUND(AVG(score_union_proximity)::numeric, 2) AS avg_prox,
                ROUND(AVG(score_industry_growth)::numeric, 2) AS avg_growth,
                ROUND(AVG(score_size)::numeric, 2) AS avg_size,
                ROUND(AVG(score_financial)::numeric, 2) AS avg_financial
            FROM mv_unified_scorecard u
            WHERE u.state IS NOT NULL
              AND (u.state = ANY(%(high)s) OR u.state = ANY(%(low)s))
            GROUP BY 1
            ORDER BY 1
        """, {
            "high": high_enforcement_states,
            "low": low_enforcement_states,
        })
        component_rows = cur.fetchall()

        cur.close()
    finally:
        conn.close()

    # ==================================================================
    # Build markdown report
    # ==================================================================
    lines = []
    lines.append("# I12 - Geographic Enforcement Bias Analysis")
    lines.append("")
    lines.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    lines.append("")

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------
    lines.append("## Summary")
    lines.append("")
    lines.append(
        "This investigation examines whether geographic enforcement density "
        "(specifically OSHA inspection/match rates by state) systematically "
        "inflates organizing scores. If states with more OSHA data also score "
        "higher, the scorecard may reflect enforcement geography rather than "
        "genuine organizing potential."
    )
    lines.append("")
    lines.append(f"- **States analyzed:** {len(scatter_data)}")
    lines.append(
        f"- **OSHA match rate range:** "
        f"{min(xs):.1f}% - {max(xs):.1f}%"
        if xs else "- **OSHA match rate range:** N/A"
    )
    lines.append(
        f"- **Avg weighted score range:** "
        f"{min(ys):.2f} - {max(ys):.2f}"
        if ys else "- **Avg weighted score range:** N/A"
    )
    lines.append(
        f"- **Pearson r (OSHA match % vs avg score):** "
        f"**{r_value:.4f}**"
        if r_value is not None else
        "- **Pearson r (OSHA match % vs avg score):** N/A (insufficient data)"
    )
    lines.append(
        f"- **Pearson r (OSHA match % vs median score):** "
        f"**{r_median:.4f}**"
        if r_median is not None else
        "- **Pearson r (OSHA match % vs median score):** N/A"
    )
    lines.append(
        f"- **Enforcement quartile thresholds:** "
        f"Q25 = {q25:.1f}%, Q75 = {q75:.1f}%"
    )
    lines.append(
        f"- **High-enforcement states (>= Q75):** "
        f"{len(high_enforcement_states)} states"
    )
    lines.append(
        f"- **Low-enforcement states (<= Q25):** "
        f"{len(low_enforcement_states)} states"
    )
    lines.append("")

    # Interpret the correlation
    if r_value is not None:
        abs_r = abs(r_value)
        if abs_r < 0.1:
            interp = "negligible"
        elif abs_r < 0.3:
            interp = "weak"
        elif abs_r < 0.5:
            interp = "moderate"
        elif abs_r < 0.7:
            interp = "strong"
        else:
            interp = "very strong"
        direction = "positive" if r_value > 0 else "negative"
        lines.append(
            f"**Interpretation:** The correlation is **{interp}** and "
            f"**{direction}** (r = {r_value:.4f}). "
        )
        if abs_r < 0.3:
            lines.append(
                "This suggests that OSHA enforcement density does NOT "
                "systematically inflate scores at a concerning level."
            )
        elif abs_r < 0.5:
            lines.append(
                "This suggests a moderate relationship that warrants monitoring "
                "but may not require immediate geographic normalization."
            )
        else:
            lines.append(
                "This suggests a substantial relationship. Geographic "
                "normalization of the OSHA score component should be considered."
            )
        lines.append("")

    # ------------------------------------------------------------------
    # OSHA Match Rate by State (top 10 and bottom 10)
    # ------------------------------------------------------------------
    lines.append("## OSHA Match Rate by State")
    lines.append("")
    lines.append("### Top 10 States (Highest OSHA Match Rate)")
    lines.append("")
    lines.append("| State | F7 Employers | OSHA Matched | Match % |")
    lines.append("|-------|------------:|-----------:|--------:|")
    for r in osha_by_state[:10]:
        lines.append(
            f"| {r['state']} | {r['total_f7']:,} | "
            f"{r['osha_matched']:,} | {fmt(r['osha_match_pct'], 1)}% |"
        )
    lines.append("")

    lines.append("### Bottom 10 States (Lowest OSHA Match Rate)")
    lines.append("")
    lines.append("| State | F7 Employers | OSHA Matched | Match % |")
    lines.append("|-------|------------:|-----------:|--------:|")
    for r in osha_by_state[-10:]:
        lines.append(
            f"| {r['state']} | {r['total_f7']:,} | "
            f"{r['osha_matched']:,} | {fmt(r['osha_match_pct'], 1)}% |"
        )
    lines.append("")

    # ------------------------------------------------------------------
    # Average Weighted Score by State (top 10 and bottom 10)
    # ------------------------------------------------------------------
    lines.append("## Average Weighted Score by State")
    lines.append("")
    lines.append("### Top 10 States (Highest Avg Weighted Score)")
    lines.append("")
    lines.append("| State | Employers | Avg Score | Std Dev | Median |")
    lines.append("|-------|--------:|---------:|--------:|-------:|")
    for r in score_by_state[:10]:
        lines.append(
            f"| {r['state']} | {r['employers']:,} | "
            f"{fmt(r['avg_score'])} | {fmt(r['std_score'])} | "
            f"{fmt(r['median_score'])} |"
        )
    lines.append("")

    lines.append("### Bottom 10 States (Lowest Avg Weighted Score)")
    lines.append("")
    lines.append("| State | Employers | Avg Score | Std Dev | Median |")
    lines.append("|-------|--------:|---------:|--------:|-------:|")
    for r in score_by_state[-10:]:
        lines.append(
            f"| {r['state']} | {r['employers']:,} | "
            f"{fmt(r['avg_score'])} | {fmt(r['std_score'])} | "
            f"{fmt(r['median_score'])} |"
        )
    lines.append("")

    # ------------------------------------------------------------------
    # Correlation Analysis
    # ------------------------------------------------------------------
    lines.append("## Correlation Analysis")
    lines.append("")
    lines.append(
        "| Metric | Value |"
    )
    lines.append("|--------|------:|")
    lines.append(
        f"| Pearson r (OSHA match % vs avg score) | "
        f"{fmt(r_value, 4) if r_value is not None else 'N/A'} |"
    )
    lines.append(
        f"| Pearson r (OSHA match % vs median score) | "
        f"{fmt(r_median, 4) if r_median is not None else 'N/A'} |"
    )
    lines.append(f"| States in analysis | {len(scatter_data)} |")
    lines.append(
        f"| Q25 enforcement threshold | {q25:.1f}% |"
    )
    lines.append(
        f"| Q75 enforcement threshold | {q75:.1f}% |"
    )
    lines.append("")

    # ------------------------------------------------------------------
    # Scatter Data (all states)
    # ------------------------------------------------------------------
    lines.append("## Scatter Data (All States)")
    lines.append("")
    lines.append(
        "Sorted by OSHA match rate descending. Can be used to plot "
        "enforcement density vs. organizing score."
    )
    lines.append("")
    lines.append(
        "| State | OSHA Match % | Avg Score | Median Score | "
        "F7 Employers | OSHA Matched |"
    )
    lines.append(
        "|-------|------------:|---------:|------------:|"
        "------------:|-----------:|"
    )
    for d in scatter_data:
        lines.append(
            f"| {d['state']} | {d['osha_match_pct']:.1f}% | "
            f"{d['avg_score']:.2f} | {d['median_score']:.2f} | "
            f"{d['total_f7']:,} | {d['osha_matched']:,} |"
        )
    lines.append("")

    # ------------------------------------------------------------------
    # Within-Industry Comparison
    # ------------------------------------------------------------------
    lines.append("## Within-Industry Comparison")
    lines.append("")
    lines.append(
        "For the top 5 most common 2-digit NAICS codes, compare average "
        "scores in high-enforcement states (top quartile, >= "
        f"{q75:.1f}%) vs low-enforcement states (bottom quartile, <= "
        f"{q25:.1f}%)."
    )
    lines.append("")

    for ic in industry_comparisons:
        lines.append(f"### NAICS {ic['naics_2']} ({ic['count']:,} employers)")
        lines.append("")
        if not ic["rows"]:
            lines.append("No data for this NAICS in the selected states.")
            lines.append("")
            continue
        lines.append(
            "| Enforcement Level | Employers | Avg Weighted Score | "
            "Avg OSHA Score |"
        )
        lines.append(
            "|-------------------|--------:|-----------------:|"
            "--------------:|"
        )
        high_row = None
        low_row = None
        for r in ic["rows"]:
            level = r["enforcement_level"]
            lines.append(
                f"| {level} | {r['employers']:,} | "
                f"{fmt(r['avg_score'])} | {fmt(r['avg_score_osha'])} |"
            )
            if level == "HIGH":
                high_row = r
            elif level == "LOW":
                low_row = r
        if high_row and low_row:
            delta_weighted = float(high_row["avg_score"] or 0) - float(low_row["avg_score"] or 0)
            delta_osha = (float(high_row["avg_score_osha"]) if high_row["avg_score_osha"] else 0) - \
                         (float(low_row["avg_score_osha"]) if low_row["avg_score_osha"] else 0)
            lines.append(
                f"| **DELTA (HIGH - LOW)** | | "
                f"**{delta_weighted:+.2f}** | **{delta_osha:+.2f}** |"
            )
        lines.append("")

    # ------------------------------------------------------------------
    # Score Component Isolation
    # ------------------------------------------------------------------
    lines.append("## Score Component Isolation")
    lines.append("")
    lines.append(
        "Average score by component in high-enforcement vs low-enforcement "
        "states. Large deltas in score_osha with small deltas elsewhere would "
        "confirm enforcement-driven bias rather than genuine differences."
    )
    lines.append("")

    components = [
        ("weighted_score", "avg_weighted"),
        ("score_osha", "avg_osha"),
        ("score_nlrb", "avg_nlrb"),
        ("score_whd", "avg_whd"),
        ("score_contracts", "avg_contracts"),
        ("score_union_proximity", "avg_prox"),
        ("score_industry_growth", "avg_growth"),
        ("score_size", "avg_size"),
        ("score_financial", "avg_financial"),
    ]

    high_comp = None
    low_comp = None
    for r in component_rows:
        if r["group_label"] == "HIGH_ENFORCEMENT":
            high_comp = r
        elif r["group_label"] == "LOW_ENFORCEMENT":
            low_comp = r

    lines.append(
        "| Component | High Enforcement | Low Enforcement | Delta | "
        "Pct of Weighted Delta |"
    )
    lines.append(
        "|-----------|----------------:|---------------:|------:|"
        "--------------------:|"
    )

    weighted_delta = None
    if high_comp and low_comp:
        weighted_delta = float(high_comp["avg_weighted"] or 0) - float(low_comp["avg_weighted"] or 0)
        for label, key in components:
            h = float(high_comp[key]) if high_comp[key] is not None else None
            l_val = float(low_comp[key]) if low_comp[key] is not None else None
            if h is not None and l_val is not None:
                delta = h - l_val
                pct_of_total = (
                    f"{100 * delta / weighted_delta:.1f}%"
                    if weighted_delta and weighted_delta != 0
                    else "N/A"
                )
                lines.append(
                    f"| {label} | {h:.2f} | {l_val:.2f} | "
                    f"{delta:+.2f} | {pct_of_total} |"
                )
            else:
                lines.append(
                    f"| {label} | {fmt(h)} | {fmt(l_val)} | N/A | N/A |"
                )

        lines.append("")
        lines.append(
            f"**High-enforcement states:** "
            f"{', '.join(sorted(high_enforcement_states))}"
        )
        lines.append(
            f"**Low-enforcement states:** "
            f"{', '.join(sorted(low_enforcement_states))}"
        )
    else:
        lines.append("| (insufficient data) | | | | |")
    lines.append("")

    # ------------------------------------------------------------------
    # Conclusion
    # ------------------------------------------------------------------
    lines.append("## Conclusion")
    lines.append("")

    if r_value is not None:
        abs_r = abs(r_value)
        if abs_r < 0.3:
            lines.append(
                "Geographic enforcement density does **not** appear to "
                "systematically inflate organizing scores at a concerning "
                f"level (r = {r_value:.4f}). While states with higher OSHA "
                "match rates do tend to have slightly different score profiles, "
                "the effect is weak enough that the current scoring approach "
                "is defensible without geographic normalization."
            )
        elif abs_r < 0.5:
            lines.append(
                "There is a **moderate** correlation between OSHA enforcement "
                f"density and organizing scores (r = {r_value:.4f}). This "
                "indicates that geographic enforcement patterns have a "
                "measurable but not dominant influence on scores. Consider "
                "monitoring this metric over time and introducing geographic "
                "normalization if the effect grows."
            )
        else:
            lines.append(
                "There is a **strong** correlation between OSHA enforcement "
                f"density and organizing scores (r = {r_value:.4f}). "
                "Geographic enforcement density is systematically inflating "
                "scores in high-enforcement states. Geographic normalization "
                "of the OSHA score component is recommended."
            )
    else:
        lines.append(
            "Insufficient data to draw a conclusion about enforcement bias."
        )
    lines.append("")

    if high_comp and low_comp and weighted_delta is not None:
        osha_delta = (float(high_comp["avg_osha"]) if high_comp["avg_osha"] else 0) - \
                     (float(low_comp["avg_osha"]) if low_comp["avg_osha"] else 0)
        lines.append(
            f"The OSHA component delta between high and low enforcement "
            f"states is **{osha_delta:+.2f}** points. The overall weighted "
            f"score delta is **{weighted_delta:+.2f}** points."
        )
        if weighted_delta != 0:
            pct = 100 * osha_delta / weighted_delta
            lines.append(
                f"OSHA accounts for approximately **{pct:.1f}%** of the "
                f"total score gap between enforcement quartiles."
            )
        lines.append("")

    # ------------------------------------------------------------------
    # Recommendations
    # ------------------------------------------------------------------
    lines.append("## Recommendations")
    lines.append("")

    if r_value is not None and abs(r_value) >= 0.5:
        lines.append(
            "1. **Geographic normalization:** Apply state-level z-score "
            "normalization to `score_osha` so that within-state ranking is "
            "preserved but cross-state comparisons are not inflated by "
            "enforcement density."
        )
        lines.append(
            "2. **Weighted score adjustment:** After normalizing OSHA, "
            "re-evaluate component weights to ensure the weighted score "
            "reflects genuine organizing potential."
        )
        lines.append(
            "3. **Re-run this investigation** after normalization to "
            "confirm the bias is reduced."
        )
    elif r_value is not None and abs(r_value) >= 0.3:
        lines.append(
            "1. **Monitor:** Re-run this investigation after any OSHA "
            "re-matching or scoring changes to track whether the moderate "
            "correlation grows."
        )
        lines.append(
            "2. **Consider partial normalization:** If the within-industry "
            "deltas above are large (> 0.5 points), apply light geographic "
            "normalization to `score_osha`."
        )
        lines.append(
            "3. **Document:** Note the moderate correlation in scoring "
            "methodology documentation so users are aware of the limitation."
        )
    else:
        lines.append(
            "1. **No immediate action required.** The weak/negligible "
            "correlation does not warrant geographic normalization at this time."
        )
        lines.append(
            "2. **Document:** Note the finding in scoring methodology "
            "documentation to demonstrate that enforcement bias was investigated "
            "and found to be minor."
        )
        lines.append(
            "3. **Re-run periodically:** As new OSHA data is ingested or "
            "matching algorithms change, re-run this investigation to ensure "
            "the conclusion still holds."
        )
    lines.append("")

    # ==================================================================
    # Write file
    # ==================================================================
    os.makedirs(os.path.dirname(args.output), exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    # ==================================================================
    # Print summary to stdout
    # ==================================================================
    print("I12 - Geographic Enforcement Bias Analysis")
    print(f"  Output: {args.output}")
    print(f"  States analyzed: {len(scatter_data)}")
    if xs:
        print(f"  OSHA match rate range: {min(xs):.1f}% - {max(xs):.1f}%")
    if r_value is not None:
        print(f"  Pearson r (OSHA match % vs avg score): {r_value:.4f}")
    if r_median is not None:
        print(f"  Pearson r (OSHA match % vs median score): {r_median:.4f}")
    print(f"  Enforcement Q25: {q25:.1f}%, Q75: {q75:.1f}%")
    print(f"  High-enforcement states ({len(high_enforcement_states)}): "
          f"{', '.join(sorted(high_enforcement_states))}")
    print(f"  Low-enforcement states ({len(low_enforcement_states)}): "
          f"{', '.join(sorted(low_enforcement_states))}")
    if high_comp and low_comp:
        print(f"  Avg weighted score - HIGH: {high_comp['avg_weighted']}, "
              f"LOW: {low_comp['avg_weighted']}")
        print(f"  Avg OSHA score - HIGH: {high_comp['avg_osha']}, "
              f"LOW: {low_comp['avg_osha']}")
    print(f"  Top 5 NAICS: {', '.join(n['naics_2'] for n in top_naics)}")
    print(f"  Industry comparisons written: {len(industry_comparisons)}")


if __name__ == "__main__":
    main()
