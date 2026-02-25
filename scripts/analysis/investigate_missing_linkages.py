"""
I15 - Missing Source ID Linkages Root Cause

Investigates legacy match tables that have records with no corresponding
active unified_match_log entry. For each legacy table, counts total,
linked, and orphaned records, then categorises orphans by UML status
(superseded, rejected, or absent).
"""
import argparse
import os
import random
import sys
from datetime import datetime

from psycopg2.extras import RealDictCursor

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
from db_config import get_connection

# Legacy tables: (table_name, source_system, source_id_column, target_id_column)
LEGACY_TABLES = [
    ("osha_f7_matches", "osha", "establishment_id", "f7_employer_id"),
    ("whd_f7_matches", "whd", "case_id", "f7_employer_id"),
    ("national_990_f7_matches", "990", "n990_id", "f7_employer_id"),
    ("sam_f7_matches", "sam", "sam_id", "f7_employer_id"),
    ("sec_f7_matches", "sec", "sec_company_id", "f7_employer_id"),
]


def md_table(headers, rows):
    """Build a markdown table string."""
    lines = []
    lines.append("| " + " | ".join(headers) + " |")
    lines.append("| " + " | ".join("---" for _ in headers) + " |")
    for row in rows:
        lines.append("| " + " | ".join(str(v) for v in row) + " |")
    return "\n".join(lines)


def analyze_table(cur, table_name, source_system, source_col, target_col):
    """Analyze one legacy table. Returns a dict of results or None if table missing."""
    result = {
        "table": table_name,
        "source_system": source_system,
        "source_col": source_col,
        "total": 0,
        "linked": 0,
        "orphaned": 0,
        "orphan_superseded": 0,
        "orphan_rejected": 0,
        "orphan_no_uml": 0,
        "sample_superseded": [],
        "sample_rejected": [],
        "sample_no_uml": [],
        "error": None,
    }

    # Cast to text for source_id comparison since UML source_id is TEXT
    cast_expr = f"lt.{source_col}::text"

    try:
        # 1. Total legacy records
        cur.execute(f"SELECT COUNT(*) AS cnt FROM {table_name}")
        result["total"] = cur.fetchone()["cnt"]

        # 2. Legacy records WITH active UML entry
        cur.execute(f"""
            SELECT COUNT(*) AS cnt
            FROM {table_name} lt
            WHERE EXISTS (
                SELECT 1 FROM unified_match_log uml
                WHERE uml.source_system = %s
                  AND uml.source_id = {cast_expr}
                  AND uml.target_id = lt.{target_col}
                  AND uml.status = 'active'
            )
        """, (source_system,))
        result["linked"] = cur.fetchone()["cnt"]

        # 3. Orphaned count
        result["orphaned"] = result["total"] - result["linked"]

        if result["orphaned"] == 0:
            return result

        # 4a. Orphans that have a SUPERSEDED UML entry
        cur.execute(f"""
            SELECT COUNT(*) AS cnt
            FROM {table_name} lt
            WHERE NOT EXISTS (
                SELECT 1 FROM unified_match_log uml
                WHERE uml.source_system = %s
                  AND uml.source_id = {cast_expr}
                  AND uml.target_id = lt.{target_col}
                  AND uml.status = 'active'
            )
            AND EXISTS (
                SELECT 1 FROM unified_match_log uml2
                WHERE uml2.source_system = %s
                  AND uml2.source_id = {cast_expr}
                  AND uml2.target_id = lt.{target_col}
                  AND uml2.status = 'superseded'
            )
        """, (source_system, source_system))
        result["orphan_superseded"] = cur.fetchone()["cnt"]

        # 4b. Orphans that have a REJECTED UML entry (but no active)
        cur.execute(f"""
            SELECT COUNT(*) AS cnt
            FROM {table_name} lt
            WHERE NOT EXISTS (
                SELECT 1 FROM unified_match_log uml
                WHERE uml.source_system = %s
                  AND uml.source_id = {cast_expr}
                  AND uml.target_id = lt.{target_col}
                  AND uml.status = 'active'
            )
            AND NOT EXISTS (
                SELECT 1 FROM unified_match_log uml2
                WHERE uml2.source_system = %s
                  AND uml2.source_id = {cast_expr}
                  AND uml2.target_id = lt.{target_col}
                  AND uml2.status = 'superseded'
            )
            AND EXISTS (
                SELECT 1 FROM unified_match_log uml3
                WHERE uml3.source_system = %s
                  AND uml3.source_id = {cast_expr}
                  AND uml3.target_id = lt.{target_col}
                  AND uml3.status = 'rejected'
            )
        """, (source_system, source_system, source_system))
        result["orphan_rejected"] = cur.fetchone()["cnt"]

        # 4c. Orphans with no UML entry at all
        result["orphan_no_uml"] = (
            result["orphaned"]
            - result["orphan_superseded"]
            - result["orphan_rejected"]
        )

        # Sample 5 from each category
        # Superseded samples
        if result["orphan_superseded"] > 0:
            cur.execute(f"""
                SELECT lt.{source_col}::text AS source_id,
                       lt.{target_col} AS target_id
                FROM {table_name} lt
                WHERE NOT EXISTS (
                    SELECT 1 FROM unified_match_log uml
                    WHERE uml.source_system = %s
                      AND uml.source_id = {cast_expr}
                      AND uml.target_id = lt.{target_col}
                      AND uml.status = 'active'
                )
                AND EXISTS (
                    SELECT 1 FROM unified_match_log uml2
                    WHERE uml2.source_system = %s
                      AND uml2.source_id = {cast_expr}
                      AND uml2.target_id = lt.{target_col}
                      AND uml2.status = 'superseded'
                )
                LIMIT 5
            """, (source_system, source_system))
            result["sample_superseded"] = cur.fetchall()

        # Rejected samples
        if result["orphan_rejected"] > 0:
            cur.execute(f"""
                SELECT lt.{source_col}::text AS source_id,
                       lt.{target_col} AS target_id
                FROM {table_name} lt
                WHERE NOT EXISTS (
                    SELECT 1 FROM unified_match_log uml
                    WHERE uml.source_system = %s
                      AND uml.source_id = {cast_expr}
                      AND uml.target_id = lt.{target_col}
                      AND uml.status = 'active'
                )
                AND NOT EXISTS (
                    SELECT 1 FROM unified_match_log uml2
                    WHERE uml2.source_system = %s
                      AND uml2.source_id = {cast_expr}
                      AND uml2.target_id = lt.{target_col}
                      AND uml2.status = 'superseded'
                )
                AND EXISTS (
                    SELECT 1 FROM unified_match_log uml3
                    WHERE uml3.source_system = %s
                      AND uml3.source_id = {cast_expr}
                      AND uml3.target_id = lt.{target_col}
                      AND uml3.status = 'rejected'
                )
                LIMIT 5
            """, (source_system, source_system, source_system))
            result["sample_rejected"] = cur.fetchall()

        # No-UML samples
        if result["orphan_no_uml"] > 0:
            cur.execute(f"""
                SELECT lt.{source_col}::text AS source_id,
                       lt.{target_col} AS target_id
                FROM {table_name} lt
                WHERE NOT EXISTS (
                    SELECT 1 FROM unified_match_log uml
                    WHERE uml.source_system = %s
                      AND uml.source_id = {cast_expr}
                      AND uml.target_id = lt.{target_col}
                )
                LIMIT 5
            """, (source_system,))
            result["sample_no_uml"] = cur.fetchall()

    except Exception as e:
        result["error"] = str(e)

    return result


def main():
    parser = argparse.ArgumentParser(
        description="I15 - Missing Source ID Linkages Root Cause"
    )
    parser.add_argument(
        "--output",
        default=os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
            "docs", "investigations", "I15_missing_source_id_linkages.md",
        ),
        help="Output markdown path",
    )
    args = parser.parse_args()

    random.seed(42)

    conn = get_connection(cursor_factory=RealDictCursor)
    cur = conn.cursor(cursor_factory=RealDictCursor)

    try:
        lines = []
        lines.append("# I15 - Missing Source ID Linkages Root Cause")
        lines.append("")
        lines.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append("")

        # ------------------------------------------------------------------
        # UML Active Counts by Source
        # ------------------------------------------------------------------
        cur.execute("""
            SELECT source_system, COUNT(*) AS active_count
            FROM unified_match_log
            WHERE status = 'active'
            GROUP BY source_system
            ORDER BY active_count DESC
        """)
        uml_counts = cur.fetchall()

        lines.append("## UML Active Counts by Source")
        lines.append("")
        uml_headers = ["Source System", "Active Count"]
        uml_data = [(r["source_system"], f'{r["active_count"]:,}') for r in uml_counts]
        lines.append(md_table(uml_headers, uml_data))
        lines.append("")

        # ------------------------------------------------------------------
        # Per-Source Analysis
        # ------------------------------------------------------------------
        lines.append("## Per-Source Analysis")
        lines.append("")

        all_results = []
        summary_data = []

        for table_name, source_system, source_col, target_col in LEGACY_TABLES:
            print(f"  Analyzing {table_name} ({source_system})...")
            result = analyze_table(cur, table_name, source_system, source_col, target_col)
            all_results.append(result)

            lines.append(f"### {table_name} (source_system='{source_system}')")
            lines.append("")

            if result["error"]:
                lines.append(f"**ERROR:** {result['error']}")
                lines.append("")
                lines.append(f"Table may not exist or has schema issues.")
                lines.append("")
                continue

            total = result["total"]
            linked = result["linked"]
            orphaned = result["orphaned"]
            pct_linked = (linked / total * 100) if total else 0
            pct_orphaned = (orphaned / total * 100) if total else 0

            lines.append(f"| Metric | Count | Pct |")
            lines.append(f"| --- | --- | --- |")
            lines.append(f"| Total legacy records | {total:,} | 100% |")
            lines.append(f"| Linked (active UML) | {linked:,} | {pct_linked:.1f}% |")
            lines.append(f"| Orphaned (no active UML) | {orphaned:,} | {pct_orphaned:.1f}% |")
            lines.append("")

            if orphaned > 0:
                lines.append("**Orphan categorization:**")
                lines.append("")
                lines.append(f"| Category | Count |")
                lines.append(f"| --- | --- |")
                lines.append(f"| Has superseded UML entry | {result['orphan_superseded']:,} |")
                lines.append(f"| Has rejected UML entry | {result['orphan_rejected']:,} |")
                lines.append(f"| No UML entry at all | {result['orphan_no_uml']:,} |")
                lines.append("")

            summary_data.append((
                table_name, source_system,
                f"{total:,}", f"{linked:,}", f"{orphaned:,}",
                f"{pct_orphaned:.1f}%",
            ))

        # ------------------------------------------------------------------
        # Sample Orphaned Records
        # ------------------------------------------------------------------
        lines.append("## Sample Orphaned Records")
        lines.append("")

        for result in all_results:
            if result["error"]:
                continue
            if result["orphaned"] == 0:
                continue

            lines.append(f"### {result['table']} orphan samples")
            lines.append("")

            if result["sample_superseded"]:
                lines.append("**Superseded UML entries:**")
                lines.append("")
                s_headers = ["source_id", "target_id"]
                s_data = [(r["source_id"], r["target_id"]) for r in result["sample_superseded"]]
                lines.append(md_table(s_headers, s_data))
                lines.append("")

            if result["sample_rejected"]:
                lines.append("**Rejected UML entries:**")
                lines.append("")
                s_headers = ["source_id", "target_id"]
                s_data = [(r["source_id"], r["target_id"]) for r in result["sample_rejected"]]
                lines.append(md_table(s_headers, s_data))
                lines.append("")

            if result["sample_no_uml"]:
                lines.append("**No UML entry at all:**")
                lines.append("")
                s_headers = ["source_id", "target_id"]
                s_data = [(r["source_id"], r["target_id"]) for r in result["sample_no_uml"]]
                lines.append(md_table(s_headers, s_data))
                lines.append("")

        # ------------------------------------------------------------------
        # Summary table
        # ------------------------------------------------------------------
        lines.append("## Summary")
        lines.append("")
        sum_headers = ["Table", "Source", "Total", "Linked", "Orphaned", "Orphan %"]
        lines.append(md_table(sum_headers, summary_data))
        lines.append("")

        # ------------------------------------------------------------------
        # Root Cause Analysis
        # ------------------------------------------------------------------
        lines.append("## Root Cause Analysis")
        lines.append("")
        lines.append("Orphaned legacy match records fall into three categories:")
        lines.append("")
        lines.append("1. **Superseded matches** -- The deterministic matcher re-ran with "
                     "`--rematch-all`, creating new UML entries and marking old ones as "
                     "superseded. The legacy table was not updated to reflect the new "
                     "source_id/target_id pair.")
        lines.append("2. **Rejected matches** -- Quality audits (e.g., trigram floor "
                     "rejection) marked UML entries as rejected, but the corresponding "
                     "legacy table row was not deleted.")
        lines.append("3. **Pre-UML matches** -- Legacy tables were populated before the "
                     "unified_match_log existed. These matches were never backfilled into UML.")
        lines.append("")

        # ------------------------------------------------------------------
        # Recommendations
        # ------------------------------------------------------------------
        lines.append("## Recommendations")
        lines.append("")
        lines.append("1. **Backfill missing UML entries** -- For 'no UML entry' orphans, "
                     "create active UML rows from legacy tables using `rebuild_legacy_tables.py`.")
        lines.append("2. **Clean superseded orphans** -- Delete legacy rows whose UML entry "
                     "is superseded (the new match takes precedence).")
        lines.append("3. **Clean rejected orphans** -- Delete legacy rows whose UML entry "
                     "is rejected (quality floor failure).")
        lines.append("4. **Add FK constraints** -- Consider adding foreign key relationships "
                     "between legacy tables and UML to prevent future drift.")
        lines.append("5. **Deprecate legacy tables** -- Long-term, stop writing to legacy "
                     "match tables and use UML as the single source of truth.")
        lines.append("")

        # Write output
        os.makedirs(os.path.dirname(args.output), exist_ok=True)
        with open(args.output, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))

        # Print summary to stdout
        print()
        print("I15 Missing Source ID Linkages complete.")
        print()
        for result in all_results:
            if result["error"]:
                print(f"  {result['table']}: ERROR - {result['error']}")
            else:
                print(f"  {result['table']}: {result['total']:,} total, "
                      f"{result['linked']:,} linked, {result['orphaned']:,} orphaned "
                      f"({result['orphaned']/result['total']*100:.1f}%)" if result['total'] else
                      f"  {result['table']}: 0 total")
        print(f"\n  Report: {args.output}")

    finally:
        conn.close()


if __name__ == "__main__":
    main()
