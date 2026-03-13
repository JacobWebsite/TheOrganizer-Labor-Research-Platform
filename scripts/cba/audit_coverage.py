"""Coverage audit for CBA cross-contract comparison.

Shows what each contract covers, what's missing, and overall statistics.

Usage:
    py scripts/cba/audit_coverage.py                    # All contracts
    py scripts/cba/audit_coverage.py --cba-ids 21,22,26 # Specific contracts
    py scripts/cba/audit_coverage.py --json              # Output as JSON
    py scripts/cba/audit_coverage.py --verbose           # Include provision_class detail
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from db_config import get_connection


def get_all_provision_classes() -> dict[str, list[str]]:
    """Load all provision classes from JSON config, grouped by category."""
    config_dir = Path(__file__).resolve().parents[2] / "config" / "cba_rules"
    category_classes = {}
    for f in sorted(config_dir.glob("*.json")):
        with open(f) as fh:
            data = json.load(fh)
        category_classes[data["category"]] = data["provision_classes"]
    return category_classes


def run_audit(cba_ids: list[int] | None = None, *, verbose: bool = False) -> dict:
    """Run full coverage audit. Returns structured report."""

    all_classes = get_all_provision_classes()
    all_categories = sorted(all_classes.keys())

    with get_connection() as conn:
        with conn.cursor() as cur:
            # Get contracts
            if cba_ids:
                placeholders = ",".join(["%s"] * len(cba_ids))
                cur.execute(
                    f"""SELECT cba_id, employer_name_raw, union_name_raw, page_count,
                               LENGTH(full_text) AS text_length
                        FROM cba_documents WHERE cba_id IN ({placeholders})
                        ORDER BY cba_id""",
                    cba_ids,
                )
            else:
                cur.execute(
                    """SELECT cba_id, employer_name_raw, union_name_raw, page_count,
                              LENGTH(full_text) AS text_length
                       FROM cba_documents
                       WHERE extraction_status = 'completed'
                       ORDER BY cba_id"""
                )
            contracts = cur.fetchall()

            if not contracts:
                print("No completed contracts found.")
                return {}

            contract_ids = [c[0] for c in contracts]
            placeholders = ",".join(["%s"] * len(contract_ids))

            # Provision counts by cba_id x category x provision_class
            cur.execute(
                f"""SELECT cba_id, category, provision_class, COUNT(*) AS cnt
                    FROM cba_provisions
                    WHERE cba_id IN ({placeholders})
                    GROUP BY cba_id, category, provision_class
                    ORDER BY cba_id, category, provision_class""",
                contract_ids,
            )
            prov_data = cur.fetchall()

            # Text coverage (provision char spans vs full text)
            cur.execute(
                f"""SELECT p.cba_id,
                           SUM(GREATEST(p.char_end - p.char_start, 0)) AS prov_chars
                    FROM cba_provisions p
                    WHERE p.cba_id IN ({placeholders})
                    GROUP BY p.cba_id""",
                contract_ids,
            )
            char_coverage = {row[0]: row[1] for row in cur.fetchall()}

            # Section counts
            cur.execute(
                f"""SELECT cba_id, COUNT(*) AS section_count
                    FROM cba_sections
                    WHERE cba_id IN ({placeholders})
                    GROUP BY cba_id""",
                contract_ids,
            )
            section_counts = {row[0]: row[1] for row in cur.fetchall()}

            # Sections with zero provisions
            cur.execute(
                f"""SELECT s.cba_id, COUNT(*) AS empty_sections
                    FROM cba_sections s
                    LEFT JOIN cba_provisions p ON p.section_id = s.section_id
                    WHERE s.cba_id IN ({placeholders})
                    GROUP BY s.cba_id
                    HAVING COUNT(p.provision_id) = 0""",
                contract_ids,
            )
            # This query isn't quite right for per-section emptiness. Let me fix:
            cur.execute(
                f"""SELECT s.cba_id, COUNT(*) AS empty_sections
                    FROM cba_sections s
                    WHERE s.cba_id IN ({placeholders})
                      AND NOT EXISTS (
                          SELECT 1 FROM cba_provisions p
                          WHERE p.section_id = s.section_id
                      )
                    GROUP BY s.cba_id""",
                contract_ids,
            )
            empty_sections = {row[0]: row[1] for row in cur.fetchall()}

            # Confidence distribution
            cur.execute(
                f"""SELECT cba_id,
                           COUNT(*) FILTER (WHERE confidence_score >= 0.90) AS high,
                           COUNT(*) FILTER (WHERE confidence_score >= 0.80 AND confidence_score < 0.90) AS medium,
                           COUNT(*) FILTER (WHERE confidence_score >= 0.70 AND confidence_score < 0.80) AS low,
                           COUNT(*) FILTER (WHERE confidence_score < 0.70) AS very_low,
                           COUNT(*) AS total
                    FROM cba_provisions
                    WHERE cba_id IN ({placeholders})
                    GROUP BY cba_id""",
                contract_ids,
            )
            confidence_data = {}
            for row in cur.fetchall():
                confidence_data[row[0]] = {
                    "high_90": row[1], "medium_80": row[2],
                    "low_70": row[3], "very_low": row[4], "total": row[5],
                }

    # Build matrices
    # prov_data: (cba_id, category, provision_class, cnt)
    cat_matrix = defaultdict(lambda: defaultdict(int))   # [category][cba_id] -> count
    class_matrix = defaultdict(lambda: defaultdict(int)) # [provision_class][cba_id] -> count

    for cba_id, category, pclass, cnt in prov_data:
        cat_matrix[category][cba_id] += cnt
        class_matrix[pclass][cba_id] += cnt

    # Report
    report = {
        "contracts": [],
        "category_matrix": {},
        "provision_class_matrix": {},
        "gap_analysis": {},
    }

    print("=" * 80)
    print("CBA CROSS-CONTRACT COVERAGE AUDIT")
    print("=" * 80)

    # Contract overview
    print("\n--- Contract Overview ---")
    for c in contracts:
        cba_id, emp, union, pages, text_len = c
        prov_chars = char_coverage.get(cba_id, 0)
        text_cov = (prov_chars / text_len * 100) if text_len else 0
        sec_count = section_counts.get(cba_id, 0)
        empty = empty_sections.get(cba_id, 0)
        conf = confidence_data.get(cba_id, {})

        info = {
            "cba_id": cba_id,
            "employer": emp,
            "union": union,
            "pages": pages,
            "text_coverage_pct": round(text_cov, 1),
            "sections": sec_count,
            "empty_sections": empty,
            "confidence": conf,
        }
        report["contracts"].append(info)

        print(f"\n  CBA #{cba_id}: {emp} -- {union}")
        print(f"    Pages: {pages}, Text coverage: {text_cov:.1f}%")
        print(f"    Sections: {sec_count} ({empty} with 0 provisions)")
        if conf:
            print(f"    Confidence: {conf.get('high_90',0)} high / {conf.get('medium_80',0)} med / {conf.get('low_70',0)} low / {conf.get('very_low',0)} very low")

    # Category matrix
    print("\n\n--- Category Matrix (provisions per contract) ---")
    header = "Category".ljust(22) + "".join(f"CBA#{c[0]:<6}" for c in contracts)
    print(header)
    print("-" * len(header))

    for cat in all_categories:
        row = cat.ljust(22)
        for c in contracts:
            cnt = cat_matrix[cat].get(c[0], 0)
            cell = str(cnt) if cnt > 0 else " -"
            row += f"{cell:<8}"
        print(row)
        report["category_matrix"][cat] = {c[0]: cat_matrix[cat].get(c[0], 0) for c in contracts}

    # Provision class matrix (verbose only)
    if verbose:
        print("\n\n--- Provision Class Matrix ---")
        for cat in all_categories:
            print(f"\n  [{cat}]")
            for pclass in all_classes[cat]:
                row = f"    {pclass}".ljust(30)
                for c in contracts:
                    cnt = class_matrix[pclass].get(c[0], 0)
                    cell = str(cnt) if cnt > 0 else " -"
                    row += f"{cell:<8}"
                print(row)
                report["provision_class_matrix"][pclass] = {
                    c[0]: class_matrix[pclass].get(c[0], 0) for c in contracts
                }

    # Gap analysis
    print("\n\n--- Gap Analysis ---")
    for c in contracts:
        cba_id = c[0]
        covered = [cat for cat in all_categories if cat_matrix[cat].get(cba_id, 0) > 0]
        missing = [cat for cat in all_categories if cat_matrix[cat].get(cba_id, 0) == 0]
        report["gap_analysis"][cba_id] = {"covered": covered, "missing": missing}
        print(f"\n  CBA #{cba_id} ({c[1]}):")
        print(f"    Covered ({len(covered)}): {', '.join(covered)}")
        if missing:
            print(f"    Missing ({len(missing)}): {', '.join(missing)}")
        else:
            print(f"    Missing: none -- all {len(all_categories)} categories covered")

    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="CBA cross-contract coverage audit")
    parser.add_argument("--cba-ids", help="Comma-separated CBA IDs (default: all)")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument("--verbose", action="store_true", help="Include provision_class detail")
    args = parser.parse_args()

    cba_ids = None
    if args.cba_ids:
        cba_ids = [int(x.strip()) for x in args.cba_ids.split(",")]

    report = run_audit(cba_ids, verbose=args.verbose)

    if args.json and report:
        out_path = Path(__file__).resolve().parents[2] / "data" / "cba_coverage_audit.json"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w") as f:
            json.dump(report, f, indent=2, default=str)
        print(f"\nJSON report saved to: {out_path}")


if __name__ == "__main__":
    main()
