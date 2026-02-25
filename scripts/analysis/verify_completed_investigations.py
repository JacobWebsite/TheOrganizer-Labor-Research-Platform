"""
Verification Pass: Re-run key SQL queries from completed investigations
to confirm numbers still hold after Phase 1/2/2A/3 changes.

Compares current DB values against original report values.
Delta > 5% => STALE, <= 5% => OK, error => ERROR.
"""
import argparse
import os
import sys
from datetime import datetime

from psycopg2.extras import RealDictCursor

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
from db_config import get_connection


# ---------------------------------------------------------------------------
# Verification check definitions
# ---------------------------------------------------------------------------
# Each check is a dict with:
#   investigation_id  - str
#   metric_name       - str
#   original_value    - number or str (from the original investigation report)
#   sql               - str (SQL to run)
#   extract           - callable(cursor) -> value
#   note              - optional context
# ---------------------------------------------------------------------------

CHECKS = [
    {
        "investigation_id": "I1",
        "metric_name": "Proximity uses only groups+corp (should be 0)",
        "original_value": 0,
        "sql": """
            SELECT COUNT(*) AS cnt
            FROM mv_unified_scorecard u
            JOIN mv_employer_data_sources eds ON eds.employer_id = u.employer_id
            WHERE u.score_union_proximity > 0
              AND eds.canonical_group_id IS NULL
              AND eds.corporate_family_id IS NULL
        """,
        "extract": lambda row: row["cnt"],
    },
    {
        "investigation_id": "I3",
        "metric_name": "Active dangling UML (target not in f7)",
        "original_value": 1,
        "sql": """
            SELECT COUNT(*) AS cnt
            FROM unified_match_log uml
            WHERE uml.status = 'active'
              AND NOT EXISTS (
                  SELECT 1 FROM f7_employers_deduped f WHERE f.employer_id = uml.target_id
              )
              AND uml.target_id != 'AMBIGUOUS'
        """,
        "extract": lambda row: row["cnt"],
    },
    {
        "investigation_id": "I4",
        "metric_name": "Generic placeholder names",
        "original_value": 6,
        "sql": """
            SELECT COUNT(*) AS cnt
            FROM f7_employers_deduped
            WHERE LOWER(employer_name) IN (
                'company lists', 'employer name', 'm1',
                'see attached spreadsheets for employer names'
            )
        """,
        "extract": lambda row: row["cnt"],
    },
    {
        "investigation_id": "I4",
        "metric_name": "Very short names (<=2 alnum chars)",
        "original_value": 31,
        "sql": """
            SELECT COUNT(*) AS cnt
            FROM f7_employers_deduped
            WHERE LENGTH(REGEXP_REPLACE(employer_name, '[^a-zA-Z0-9]', '', 'g')) <= 2
        """,
        "extract": lambda row: row["cnt"],
    },
    {
        "investigation_id": "I6",
        "metric_name": "Membership overcounting (v_union_members_deduplicated SUM)",
        "original_value": 71950779,
        "sql": """
            SELECT SUM(members_2024) AS total
            FROM v_union_members_deduplicated
        """,
        "extract": lambda row: int(row["total"]) if row["total"] is not None else None,
        "note": "View may not exist",
    },
    {
        "investigation_id": "I7",
        "metric_name": "Superseded UML matches",
        "original_value": 538011,
        "sql": """
            SELECT COUNT(*) AS cnt
            FROM unified_match_log
            WHERE status = 'superseded'
        """,
        "extract": lambda row: row["cnt"],
    },
    {
        "investigation_id": "I8",
        "metric_name": "Large employer groups (>50 members)",
        "original_value": 51,
        "sql": """
            SELECT COUNT(*) AS cnt
            FROM employer_canonical_groups
            WHERE member_count > 50
        """,
        "extract": lambda row: row["cnt"],
    },
    {
        "investigation_id": "I10",
        "metric_name": "Multi-employer agreements (is_multi_employer or name pattern)",
        "original_value": 3039,
        # Two-strategy SQL: try is_multi_employer first via a UNION fallback
        # We handle this specially in run_check
        "sql": None,
        "extract": None,
        "note": "Column may not exist; falls back to name pattern",
    },
    {
        "investigation_id": "I13",
        "metric_name": "is_labor_org flagged",
        "original_value": 1843,
        "sql": """
            SELECT COUNT(*) AS cnt
            FROM f7_employers_deduped
            WHERE is_labor_org = TRUE
        """,
        "extract": lambda row: row["cnt"],
    },
    {
        "investigation_id": "BASELINE",
        "metric_name": "Total F7 employers",
        "original_value": 146863,
        "sql": """
            SELECT COUNT(*) AS cnt FROM f7_employers_deduped
        """,
        "extract": lambda row: row["cnt"],
    },
    {
        "investigation_id": "BASELINE",
        "metric_name": "Total active UML matches",
        "original_value": 135430,
        "sql": """
            SELECT COUNT(*) AS cnt FROM unified_match_log WHERE status = 'active'
        """,
        "extract": lambda row: row["cnt"],
        "note": "Expected ~135,430",
    },
]


def run_check_i10(cur):
    """Special handler for I10 multi-employer check with column fallback."""
    # Strategy 1: try is_multi_employer column
    try:
        cur.execute(
            "SELECT COUNT(*) AS cnt FROM f7_employers_deduped WHERE is_multi_employer = TRUE"
        )
        row = cur.fetchone()
        return row["cnt"], "is_multi_employer column"
    except Exception:
        # Column doesn't exist; roll back the failed statement
        cur.connection.rollback()

    # Strategy 2: name-pattern fallback
    cur.execute(
        """
        SELECT COUNT(*) AS cnt
        FROM f7_employers_deduped
        WHERE LOWER(employer_name) LIKE '%%building trades%%'
           OR LOWER(employer_name) LIKE '%%bldg trades%%'
        """
    )
    row = cur.fetchone()
    return row["cnt"], "name pattern fallback (building trades only)"


def compute_delta_pct(original, current):
    """Return percentage delta. Returns None if comparison is not meaningful."""
    if original is None or current is None:
        return None
    if isinstance(original, str) or isinstance(current, str):
        return None
    if original == 0:
        return 0.0 if current == 0 else 100.0
    return abs(current - original) / abs(original) * 100.0


def status_label(delta_pct):
    """Return OK / STALE based on 5% threshold."""
    if delta_pct is None:
        return "INFO"
    return "OK" if delta_pct <= 5.0 else "STALE"


def main():
    parser = argparse.ArgumentParser(
        description="Re-run key investigation SQL queries and verify numbers still hold"
    )
    parser.add_argument(
        "--output",
        default="docs/investigations/VERIFICATION_PASS.md",
        help="Output markdown path (default: docs/investigations/VERIFICATION_PASS.md)",
    )
    args = parser.parse_args()

    conn = get_connection(cursor_factory=RealDictCursor)
    cur = conn.cursor(cursor_factory=RealDictCursor)

    results = []  # list of dicts: check_num, inv_id, metric, original, current, delta_pct, status, note

    try:
        for idx, check in enumerate(CHECKS, start=1):
            inv_id = check["investigation_id"]
            metric = check["metric_name"]
            original = check["original_value"]
            note = check.get("note", "")

            # Special handling for I10
            if inv_id == "I10" and check["sql"] is None:
                try:
                    current, detail = run_check_i10(cur)
                    note = detail
                except Exception as exc:
                    results.append(
                        {
                            "num": idx,
                            "inv_id": inv_id,
                            "metric": metric,
                            "original": original,
                            "current": None,
                            "delta_pct": None,
                            "status": "ERROR",
                            "note": str(exc),
                        }
                    )
                    continue

                delta_pct = compute_delta_pct(original, current)
                results.append(
                    {
                        "num": idx,
                        "inv_id": inv_id,
                        "metric": metric,
                        "original": original,
                        "current": current,
                        "delta_pct": delta_pct,
                        "status": status_label(delta_pct),
                        "note": note,
                    }
                )
                continue

            # Standard check
            try:
                cur.execute(check["sql"])
                row = cur.fetchone()
                current = check["extract"](row)
            except Exception as exc:
                # Roll back the failed statement so the connection stays usable
                conn.rollback()
                results.append(
                    {
                        "num": idx,
                        "inv_id": inv_id,
                        "metric": metric,
                        "original": original,
                        "current": None,
                        "delta_pct": None,
                        "status": "ERROR",
                        "note": str(exc),
                    }
                )
                continue

            delta_pct = compute_delta_pct(original, current)
            results.append(
                {
                    "num": idx,
                    "inv_id": inv_id,
                    "metric": metric,
                    "original": original,
                    "current": current,
                    "delta_pct": delta_pct,
                    "status": status_label(delta_pct),
                    "note": note,
                }
            )

        # ------------------------------------------------------------------
        # Build markdown report
        # ------------------------------------------------------------------
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        lines = []
        lines.append("# Verification Pass: Completed Investigations")
        lines.append("")
        lines.append(f"Generated: {timestamp}")
        lines.append("")

        # Summary counts
        ok_count = sum(1 for r in results if r["status"] == "OK")
        info_count = sum(1 for r in results if r["status"] == "INFO")
        stale_count = sum(1 for r in results if r["status"] == "STALE")
        error_count = sum(1 for r in results if r["status"] == "ERROR")
        total_count = len(results)

        lines.append("## Summary")
        lines.append("")
        lines.append(f"- **{ok_count}** of **{total_count}** checks passed (OK)")
        if info_count:
            lines.append(f"- **{info_count}** informational (no numeric comparison)")
        if stale_count:
            lines.append(f"- **{stale_count}** stale (delta > 5%)")
        if error_count:
            lines.append(f"- **{error_count}** errors")
        lines.append("")

        # Results table
        lines.append("## Verification Results")
        lines.append("")
        lines.append("| # | Investigation | Metric | Original | Current | Delta | Status |")
        lines.append("|--:|:-------------|:-------|:---------|:--------|:------|:-------|")

        for r in results:
            orig_str = f"{r['original']:,}" if isinstance(r["original"], (int, float)) else str(r["original"])
            if r["current"] is not None:
                curr_str = f"{r['current']:,}" if isinstance(r["current"], (int, float)) else str(r["current"])
            else:
                curr_str = "N/A"
            if r["delta_pct"] is not None:
                delta_str = f"{r['delta_pct']:.1f}%"
            else:
                delta_str = "-"
            status_str = r["status"]
            if status_str == "STALE":
                status_str = "**STALE**"
            elif status_str == "ERROR":
                status_str = "**ERROR**"
            lines.append(
                f"| {r['num']} | {r['inv_id']} | {r['metric']} | {orig_str} | {curr_str} | {delta_str} | {status_str} |"
            )

        # Stale details
        stale_items = [r for r in results if r["status"] == "STALE"]
        if stale_items:
            lines.append("")
            lines.append("## Stale Checks (delta > 5%)")
            lines.append("")
            for r in stale_items:
                orig_val = r["original"]
                curr_val = r["current"]
                lines.append(f"### {r['inv_id']} - {r['metric']}")
                lines.append("")
                lines.append(f"- Original value: {orig_val:,}" if isinstance(orig_val, (int, float)) else f"- Original value: {orig_val}")
                lines.append(f"- Current value: {curr_val:,}" if isinstance(curr_val, (int, float)) else f"- Current value: {curr_val}")
                lines.append(f"- Delta: {r['delta_pct']:.1f}%")
                if r["note"]:
                    lines.append(f"- Note: {r['note']}")
                lines.append(
                    "- **Action:** Investigate whether this change is expected (data reload, pipeline re-run) "
                    "or indicates a regression."
                )
                lines.append("")

        # Error details
        error_items = [r for r in results if r["status"] == "ERROR"]
        if error_items:
            lines.append("")
            lines.append("## Errors")
            lines.append("")
            for r in error_items:
                lines.append(f"### {r['inv_id']} - {r['metric']}")
                lines.append("")
                lines.append(f"- Error: `{r['note']}`")
                lines.append(
                    "- **Action:** Check whether the table/view/column still exists or was renamed."
                )
                lines.append("")

        # Write markdown
        out_path = args.output
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")

        # Stdout summary
        print(f"Verification pass complete: {out_path}")
        print(f"  {ok_count} OK, {stale_count} STALE, {error_count} ERROR out of {total_count} checks")
        if stale_items:
            print("  Stale checks:")
            for r in stale_items:
                print(f"    - {r['inv_id']} {r['metric']}: {r['original']} -> {r['current']} ({r['delta_pct']:.1f}%)")
        if error_items:
            print("  Errors:")
            for r in error_items:
                print(f"    - {r['inv_id']} {r['metric']}: {r['note']}")

    finally:
        conn.close()


if __name__ == "__main__":
    main()
