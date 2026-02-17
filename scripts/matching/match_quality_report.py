"""
Match Quality Report.

Generates match rate, confidence distribution, method breakdown,
and state-level variation from unified_match_log.

Usage:
    py scripts/matching/match_quality_report.py
    py scripts/matching/match_quality_report.py --json
    py scripts/matching/match_quality_report.py --output docs/MATCH_QUALITY_REPORT.md
"""
import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from db_config import get_connection


def generate_report(conn):
    """Generate match quality metrics from unified_match_log."""
    report = {
        "generated_at": datetime.now().isoformat(),
        "sections": {},
    }

    with conn.cursor() as cur:
        # 1. Overall summary
        cur.execute("SELECT COUNT(*) FROM unified_match_log WHERE status = 'active'")
        total_active = cur.fetchone()[0]

        cur.execute("SELECT COUNT(DISTINCT target_id) FROM unified_match_log WHERE status = 'active'")
        unique_employers = cur.fetchone()[0]

        cur.execute("SELECT COUNT(*) FROM f7_employers_deduped")
        total_f7 = cur.fetchone()[0]

        report["sections"]["overview"] = {
            "total_active_matches": total_active,
            "unique_f7_employers_matched": unique_employers,
            "total_f7_employers": total_f7,
            "overall_coverage_pct": round(100.0 * unique_employers / max(total_f7, 1), 1),
        }

        # 2. By source system
        cur.execute("""
            SELECT source_system,
                   COUNT(*) as total_matches,
                   COUNT(DISTINCT target_id) as unique_employers,
                   ROUND(100.0 * COUNT(DISTINCT target_id) / %s, 1) as coverage_pct
            FROM unified_match_log
            WHERE status = 'active'
            GROUP BY source_system
            ORDER BY total_matches DESC
        """, [max(total_f7, 1)])
        report["sections"]["by_source"] = [
            {"source": r[0], "matches": r[1], "unique_employers": r[2], "coverage_pct": float(r[3])}
            for r in cur.fetchall()
        ]

        # 3. By confidence band (distinct employers + total rows)
        cur.execute("""
            SELECT source_system, confidence_band,
                   COUNT(*) as total_rows,
                   COUNT(DISTINCT target_id) as unique_employers
            FROM unified_match_log
            WHERE status = 'active'
            GROUP BY source_system, confidence_band
            ORDER BY source_system, confidence_band
        """)
        confidence_data = {}
        for r in cur.fetchall():
            src = r[0]
            if src not in confidence_data:
                confidence_data[src] = {}
            confidence_data[src][r[1]] = {"rows": r[2], "unique_employers": r[3]}
        report["sections"]["confidence_distribution"] = confidence_data

        # 4. By match method (top 20, distinct employers + total rows)
        cur.execute("""
            SELECT match_method, match_tier,
                   COUNT(*) as total_rows,
                   COUNT(DISTINCT target_id) as unique_employers
            FROM unified_match_log
            WHERE status = 'active'
            GROUP BY match_method, match_tier
            ORDER BY unique_employers DESC
            LIMIT 20
        """)
        report["sections"]["top_methods"] = [
            {"method": r[0], "tier": r[1], "total_rows": r[2], "unique_employers": r[3]}
            for r in cur.fetchall()
        ]

        # 5. State-level match rates (top 10 and bottom 10)
        cur.execute("""
            SELECT f.state,
                   COUNT(DISTINCT f.employer_id) as total_employers,
                   COUNT(DISTINCT m.target_id) as matched_employers,
                   ROUND(100.0 * COUNT(DISTINCT m.target_id) / GREATEST(COUNT(DISTINCT f.employer_id), 1), 1) as match_rate
            FROM f7_employers_deduped f
            LEFT JOIN unified_match_log m ON f.employer_id = m.target_id AND m.status = 'active'
            WHERE f.state IS NOT NULL
            GROUP BY f.state
            HAVING COUNT(DISTINCT f.employer_id) >= 50
            ORDER BY match_rate DESC
        """)
        states = [
            {"state": r[0], "total": r[1], "matched": r[2], "rate": float(r[3])}
            for r in cur.fetchall()
        ]
        report["sections"]["state_variation"] = {
            "top_10": states[:10],
            "bottom_10": states[-10:] if len(states) > 10 else states,
        }

        # 6. Recent runs
        cur.execute("""
            SELECT run_id, scenario, source_system, method_type,
                   started_at, completed_at, total_source, total_matched, match_rate,
                   high_count, medium_count, low_count
            FROM match_runs
            ORDER BY started_at DESC
            LIMIT 10
        """)
        report["sections"]["recent_runs"] = [
            {
                "run_id": r[0], "scenario": r[1], "source_system": r[2],
                "method_type": r[3],
                "started_at": r[4].isoformat() if r[4] else None,
                "completed_at": r[5].isoformat() if r[5] else None,
                "total_source": r[6], "total_matched": r[7],
                "match_rate": float(r[8]) if r[8] else None,
                "high": r[9], "medium": r[10], "low": r[11],
            }
            for r in cur.fetchall()
        ]

        # 7. Match rate baselines check
        baselines = {
            "osha": 13.0,  # Source perspective: >= 13%
            "whd": 6.0,
            "990": 2.0,
        }
        cur.execute("""
            SELECT source_system,
                   COUNT(DISTINCT target_id) as matched_employers
            FROM unified_match_log
            WHERE status = 'active' AND source_system IN ('osha', 'whd', '990')
            GROUP BY source_system
        """)
        current_rates = {}
        for r in cur.fetchall():
            rate = round(100.0 * r[1] / max(total_f7, 1), 1)
            current_rates[r[0]] = rate

        regressions = []
        for src, baseline in baselines.items():
            current = current_rates.get(src, 0)
            if current < baseline - 2.0:
                regressions.append({
                    "source": src, "current": current,
                    "baseline": baseline, "delta": round(current - baseline, 1),
                })
        report["sections"]["baseline_check"] = {
            "current_rates": current_rates,
            "baselines": baselines,
            "regressions": regressions,
        }

    return report


def format_markdown(report):
    """Format report as markdown."""
    lines = [
        "# Match Quality Report",
        f"\nGenerated: {report['generated_at']}\n",
    ]

    # Overview
    ov = report["sections"]["overview"]
    lines.append("## Overview\n")
    lines.append(f"| Metric | Value |")
    lines.append(f"|--------|-------|")
    lines.append(f"| Total active matches | {ov['total_active_matches']:,} |")
    lines.append(f"| Unique F7 employers matched | {ov['unique_f7_employers_matched']:,} |")
    lines.append(f"| Total F7 employers | {ov['total_f7_employers']:,} |")
    lines.append(f"| Overall coverage | {ov['overall_coverage_pct']}% |")

    # By source
    lines.append("\n## Match Rates by Source\n")
    lines.append("| Source | Matches | Unique Employers | Coverage |")
    lines.append("|--------|---------|-----------------|----------|")
    for s in report["sections"]["by_source"]:
        lines.append(f"| {s['source']} | {s['matches']:,} | {s['unique_employers']:,} | {s['coverage_pct']}% |")

    # Confidence
    lines.append("\n## Confidence Distribution\n")
    lines.append("| Source | HIGH | MEDIUM | LOW |")
    lines.append("|--------|------|--------|-----|")
    for src, bands in report["sections"]["confidence_distribution"].items():
        lines.append(f"| {src} | {bands.get('HIGH', 0):,} | {bands.get('MEDIUM', 0):,} | {bands.get('LOW', 0):,} |")

    # Top methods
    lines.append("\n## Top Match Methods\n")
    lines.append("| Method | Tier | Count |")
    lines.append("|--------|------|-------|")
    for m in report["sections"]["top_methods"]:
        lines.append(f"| {m['method']} | {m['tier']} | {m['count']:,} |")

    # Baselines
    bl = report["sections"]["baseline_check"]
    lines.append("\n## Baseline Check\n")
    for src, baseline in bl["baselines"].items():
        current = bl["current_rates"].get(src, 0)
        status = "PASS" if current >= baseline - 2.0 else "FAIL"
        lines.append(f"- **{src}**: {current}% (baseline: {baseline}%) -- {status}")

    if bl["regressions"]:
        lines.append("\n**REGRESSIONS DETECTED:**")
        for r in bl["regressions"]:
            lines.append(f"- {r['source']}: {r['current']}% vs {r['baseline']}% baseline ({r['delta']:+.1f}%)")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Match Quality Report")
    parser.add_argument("--json", action="store_true", help="Output JSON instead of markdown")
    parser.add_argument("--output", help="Write to file instead of stdout")
    args = parser.parse_args()

    conn = get_connection()
    try:
        report = generate_report(conn)
    finally:
        conn.close()

    if args.json:
        text = json.dumps(report, indent=2, default=str)
    else:
        text = format_markdown(report)

    if args.output:
        Path(args.output).write_text(text, encoding="utf-8")
        print(f"Report written to {args.output}")
    else:
        print(text)


if __name__ == "__main__":
    main()
