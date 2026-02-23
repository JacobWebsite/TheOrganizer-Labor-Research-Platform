import argparse
import os
import sys

from psycopg2.extras import RealDictCursor

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
from db_config import get_connection

SOURCE_SYSTEMS = ["osha", "nlrb", "whd", "990", "sam"]


def main():
    parser = argparse.ArgumentParser(description="State-by-state match coverage heatmap")
    parser.add_argument(
        "--output",
        default="docs/investigations/I17_state_coverage_heatmap.md",
        help="Output markdown path",
    )
    args = parser.parse_args()

    conn = get_connection(cursor_factory=RealDictCursor)
    cur = conn.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute(
            """
            WITH employer_sources AS (
                SELECT target_id AS employer_id,
                       COUNT(DISTINCT source_system) AS source_count,
                       MAX(CASE WHEN source_system = 'osha' THEN 1 ELSE 0 END) AS has_osha,
                       MAX(CASE WHEN source_system = 'nlrb' THEN 1 ELSE 0 END) AS has_nlrb,
                       MAX(CASE WHEN source_system = 'whd' THEN 1 ELSE 0 END) AS has_whd,
                       MAX(CASE WHEN source_system = '990' THEN 1 ELSE 0 END) AS has_990,
                       MAX(CASE WHEN source_system = 'sam' THEN 1 ELSE 0 END) AS has_sam
                FROM unified_match_log
                WHERE status = 'active'
                GROUP BY target_id
            )
            SELECT f.state,
                   COUNT(*) AS total_employers,
                   COUNT(*) FILTER (WHERE COALESCE(es.source_count, 0) >= 1) AS with_1plus,
                   COUNT(*) FILTER (WHERE COALESCE(es.source_count, 0) >= 2) AS with_2plus,
                   ROUND(COUNT(*) FILTER (WHERE COALESCE(es.source_count, 0) >= 1)::numeric / NULLIF(COUNT(*), 0) * 100, 1) AS coverage_pct,
                   COUNT(*) FILTER (WHERE COALESCE(es.has_osha, 0) = 1) AS has_osha,
                   COUNT(*) FILTER (WHERE COALESCE(es.has_nlrb, 0) = 1) AS has_nlrb,
                   COUNT(*) FILTER (WHERE COALESCE(es.has_whd, 0) = 1) AS has_whd,
                   COUNT(*) FILTER (WHERE COALESCE(es.has_990, 0) = 1) AS has_990,
                   COUNT(*) FILTER (WHERE COALESCE(es.has_sam, 0) = 1) AS has_sam
            FROM f7_employers_deduped f
            LEFT JOIN employer_sources es ON es.employer_id = f.employer_id
            WHERE COALESCE(f.is_historical, false) = false
              AND f.state IS NOT NULL
              AND btrim(f.state) <> ''
            GROUP BY f.state
            ORDER BY coverage_pct DESC, f.state
            """
        )
        rows = cur.fetchall()

        low_cov = [r for r in rows if (r["coverage_pct"] or 0) < 30]
        high_cov = [r for r in rows if (r["coverage_pct"] or 0) > 70]

        lines = []
        lines.append("# I17 Match Coverage Heatmap by State")
        lines.append("")
        lines.append("## Summary")
        lines.append(f"- States with employers: **{len(rows):,}**")
        lines.append(f"- Low coverage states (<30%): **{len(low_cov):,}**")
        lines.append(f"- High coverage states (>70%): **{len(high_cov):,}**")
        lines.append("")

        lines.append("## Coverage Ranking")
        lines.append("| Rank | State | Total employers | >=1 source | >=2 sources | Coverage % | Tier |")
        lines.append("|---:|---|---:|---:|---:|---:|---|")
        for idx, r in enumerate(rows, start=1):
            cov = float(r["coverage_pct"] or 0.0)
            if cov < 30:
                tier = "low coverage"
            elif cov > 70:
                tier = "high coverage"
            else:
                tier = "mid"
            lines.append(
                f"| {idx} | {r['state']} | {r['total_employers']:,} | {r['with_1plus']:,} | {r['with_2plus']:,} | {cov:.1f}% | {tier} |"
            )

        lines.append("")
        lines.append("## Source Coverage by State")
        lines.append("| State | OSHA% | NLRB% | WHD% | 990% | SAM% | Weakest source(s) |")
        lines.append("|---|---:|---:|---:|---:|---:|---|")
        for r in rows:
            total = r["total_employers"] or 1
            pcts = {
                "osha": (r["has_osha"] / total) * 100.0,
                "nlrb": (r["has_nlrb"] / total) * 100.0,
                "whd": (r["has_whd"] / total) * 100.0,
                "990": (r["has_990"] / total) * 100.0,
                "sam": (r["has_sam"] / total) * 100.0,
            }
            min_pct = min(pcts.values())
            weak = [k for k, v in pcts.items() if abs(v - min_pct) < 1e-9]
            lines.append(
                f"| {r['state']} | {pcts['osha']:.1f}% | {pcts['nlrb']:.1f}% | {pcts['whd']:.1f}% | {pcts['990']:.1f}% | {pcts['sam']:.1f}% | {', '.join(weak)} |"
            )

        lines.append("")
        lines.append("## Low Coverage States (<30%)")
        for r in low_cov:
            lines.append(f"- {r['state']}: {float(r['coverage_pct'] or 0):.1f}% ({r['with_1plus']:,}/{r['total_employers']:,})")

        lines.append("")
        lines.append("## High Coverage States (>70%)")
        for r in high_cov:
            lines.append(f"- {r['state']}: {float(r['coverage_pct'] or 0):.1f}% ({r['with_1plus']:,}/{r['total_employers']:,})")

        os.makedirs(os.path.dirname(args.output), exist_ok=True)
        with open(args.output, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")

        print(f"Wrote {args.output}")
        print(f"States analyzed: {len(rows):,}")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
