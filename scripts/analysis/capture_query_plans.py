"""
Capture EXPLAIN plans for representative slow-endpoint queries.

Default mode uses EXPLAIN (FORMAT TEXT) only.
Use --analyze to run EXPLAIN ANALYZE (heavier).
"""
from __future__ import annotations

import argparse
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[2]
REPORT = ROOT / "docs" / "PARALLEL_QUERY_PLAN_BASELINE.md"

sys.path.insert(0, str(ROOT))
from db_config import get_connection  # noqa: E402


QUERIES = {
    "api_summary_unions": """
        SELECT COUNT(*) as total_unions, SUM(members) as total_members,
               COUNT(DISTINCT aff_abbr) as affiliations
        FROM unions_master
    """,
    "api_summary_employers": """
        SELECT COUNT(*) as total_employers,
               SUM(latest_unit_size) as total_workers_raw,
               SUM(CASE WHEN exclude_from_counts = FALSE THEN latest_unit_size ELSE 0 END) as covered_workers,
               COUNT(DISTINCT state) as states,
               COUNT(CASE WHEN exclude_from_counts = TRUE THEN 1 END) as excluded_records,
               ROUND(100.0 * SUM(CASE WHEN exclude_from_counts = FALSE THEN latest_unit_size ELSE 0 END) / 7200000, 1) as bls_coverage_pct
        FROM f7_employers_deduped
    """,
    "api_osha_summary": """
        SELECT
            (SELECT COUNT(*) FROM osha_establishments) as total_establishments,
            (SELECT COUNT(*) FROM osha_establishments WHERE union_status = 'Y') as union_establishments,
            (SELECT COUNT(*) FROM osha_establishments WHERE union_status = 'N') as nonunion_establishments,
            (SELECT SUM(violation_count) FROM osha_violation_summary) as total_violations,
            (SELECT SUM(total_penalties) FROM osha_violation_summary) as total_penalties,
            (SELECT COUNT(*) FROM osha_accidents) as total_accidents,
            (SELECT COUNT(*) FROM osha_accidents WHERE is_fatality = true) as fatality_incidents,
            (SELECT COUNT(*) FROM osha_f7_matches) as f7_matches,
            (SELECT COUNT(DISTINCT f7_employer_id) FROM osha_f7_matches) as unique_f7_employers_matched
    """,
    "api_trends_national_raw": """
        SELECT yr_covered as year,
               COUNT(DISTINCT f_num) as union_count,
               SUM(CASE WHEN members > 0 THEN members ELSE 0 END) as total_members_raw,
               COUNT(*) as filing_count
        FROM lm_data
        WHERE yr_covered BETWEEN 2010 AND 2024
        GROUP BY yr_covered
        ORDER BY yr_covered
    """,
    "api_trends_national_dedup": """
        SELECT
            SUM(CASE WHEN count_members THEN members ELSE 0 END) as deduplicated_total,
            SUM(members) as raw_total
        FROM v_union_members_deduplicated
    """,
}


def explain_sql(cur, sql: str, analyze: bool) -> str:
    prefix = "EXPLAIN (ANALYZE, BUFFERS, FORMAT TEXT)" if analyze else "EXPLAIN (FORMAT TEXT)"
    cur.execute(f"{prefix} {sql}")
    rows = cur.fetchall()
    # psycopg2 returns one-column tuples for EXPLAIN text
    return "\n".join(str(r[0]) for r in rows)


def main() -> int:
    parser = argparse.ArgumentParser(description="Capture query plans for key API queries")
    parser.add_argument("--analyze", action="store_true", help="Use EXPLAIN ANALYZE (heavier)")
    args = parser.parse_args()

    conn = get_connection()
    try:
        cur = conn.cursor()
        lines = [
            "# Parallel Query Plan Baseline",
            "",
            f"- Mode: {'EXPLAIN ANALYZE' if args.analyze else 'EXPLAIN'}",
            "",
        ]

        for name, sql in QUERIES.items():
            lines.append(f"## {name}")
            lines.append("```sql")
            lines.append(sql.strip())
            lines.append("```")
            try:
                plan = explain_sql(cur, sql, args.analyze)
                lines.append("```text")
                lines.append(plan)
                lines.append("```")
            except Exception as exc:
                lines.append("```text")
                lines.append(f"PLAN ERROR: {exc}")
                lines.append("```")
            lines.append("")

        REPORT.write_text("\n".join(lines), encoding="utf-8")
        print(f"Wrote: {REPORT}")
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())

