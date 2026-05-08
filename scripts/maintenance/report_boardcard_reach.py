"""
Report BoardCard reach — how many master profiles will render the
BoardCard with meaningful data, and how that breaks down by relevant
subsets (SEC-linked, scorecard tier).

This is reach REPORTING, not gating — useful as a launch-time metric
and as a re-runnable script when DEF14A loads grow.

Run after the batch loader finishes (or any time):
    py scripts/maintenance/report_boardcard_reach.py
    py scripts/maintenance/report_boardcard_reach.py --json

Background: BoardCard is fundamentally a public-company tool because
DEF14A is an SEC filing. Most master_employers are private companies
that will correctly show "no DEF14A on file." The reach metric is
therefore best read against the SEC-linked subset, not the full
master universe.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from db_config import get_connection


def gather_reach() -> dict:
    conn = get_connection()
    try:
        cur = conn.cursor()

        cur.execute(
            "SELECT COUNT(*), COUNT(DISTINCT master_id), COUNT(DISTINCT filing_cik) "
            "FROM employer_directors"
        )
        row = cur.fetchone()
        if isinstance(row, tuple):
            n_directors, n_masters_with_dirs, n_ciks = row
        else:
            n_directors, n_masters_with_dirs, n_ciks = (
                row["count"], row["count_1"], row["count_2"],
            )

        cur.execute("SELECT COUNT(*) FROM director_interlocks")
        row = cur.fetchone()
        n_interlocks = row[0] if isinstance(row, tuple) else row["count"]

        cur.execute(
            """
            SELECT COUNT(DISTINCT m) FROM (
              SELECT master_id_a AS m FROM director_interlocks
              UNION
              SELECT master_id_b FROM director_interlocks
            ) x
            """
        )
        row = cur.fetchone()
        n_masters_interlocked = row[0] if isinstance(row, tuple) else row["count"]

        cur.execute(
            """
            SELECT gold_standard_tier,
                   COUNT(*) AS total,
                   COUNT(*) FILTER (WHERE EXISTS (
                     SELECT 1 FROM employer_directors d WHERE d.master_id = ts.master_id
                   )) AS with_directors
            FROM mv_target_scorecard ts
            WHERE gold_standard_tier IS NOT NULL
            GROUP BY gold_standard_tier
            ORDER BY 1
            """
        )
        tier_breakdown = {}
        for r in cur.fetchall() or []:
            if isinstance(r, tuple):
                tier, total, with_dir = r
            else:
                tier, total, with_dir = r["gold_standard_tier"], r["total"], r["with_directors"]
            tier_breakdown[tier] = {"total": total, "with_directors": with_dir}

        cur.execute(
            """
            WITH sec_masters AS (
              SELECT DISTINCT master_id FROM master_employer_source_ids
              WHERE source_system = 'sec'
            )
            SELECT
              (SELECT COUNT(*) FROM sec_masters) AS total,
              (SELECT COUNT(DISTINCT master_id) FROM employer_directors d
               WHERE d.master_id IN (SELECT master_id FROM sec_masters)) AS with_directors
            """
        )
        sec = cur.fetchone()
        if isinstance(sec, tuple):
            sec_total, sec_with = sec
        else:
            sec_total, sec_with = sec["total"], sec["with_directors"]

        cur.execute(
            """
            SELECT
              COUNT(*) FILTER (WHERE dc = 1) AS one_dir,
              COUNT(*) FILTER (WHERE dc BETWEEN 2 AND 4) AS sparse,
              COUNT(*) FILTER (WHERE dc BETWEEN 5 AND 9) AS typical,
              COUNT(*) FILTER (WHERE dc >= 10) AS large_board,
              ROUND(AVG(dc)::numeric, 1) AS avg_dirs,
              MAX(dc) AS max_dirs
            FROM (SELECT master_id, COUNT(*) AS dc FROM employer_directors GROUP BY master_id) t
            """
        )
        row = cur.fetchone()
        if isinstance(row, tuple):
            one, sparse, typical, large, avg_d, max_d = row
        else:
            one, sparse, typical, large, avg_d, max_d = (
                row["one_dir"], row["sparse"], row["typical"],
                row["large_board"], row["avg_dirs"], row["max_dirs"],
            )

    finally:
        conn.close()

    return {
        "totals": {
            "directors": n_directors,
            "masters_with_directors": n_masters_with_dirs,
            "ciks_covered": n_ciks,
            "interlocks": n_interlocks,
            "masters_with_interlocks": n_masters_interlocked,
        },
        "sec_subset": {
            "sec_linked_masters": sec_total,
            "with_directors": sec_with,
            "coverage_pct": round(100.0 * sec_with / sec_total, 2) if sec_total else 0,
        },
        "director_count_distribution": {
            "1_director_only": one,
            "2-4_sparse": sparse,
            "5-9_typical": typical,
            "10+_large_board": large,
            "avg_per_master": float(avg_d) if avg_d is not None else None,
            "max_per_master": max_d,
        },
        "gold_standard_tier": tier_breakdown,
    }


def print_human(report: dict):
    t = report["totals"]
    print("=== BoardCard reach ===\n")
    print(f"Directors loaded: {t['directors']:,}")
    print(f"Masters with >=1 director: {t['masters_with_directors']:,}")
    print(f"Distinct CIKs covered: {t['ciks_covered']:,}")
    print(f"Cross-company interlocks: {t['interlocks']:,}")
    print(f"Masters with >=1 interlock: {t['masters_with_interlocks']:,}")
    print()
    s = report["sec_subset"]
    print(f"SEC-linked masters: {s['sec_linked_masters']:,}")
    print(f"  with directors: {s['with_directors']:,} ({s['coverage_pct']:.2f}%)")
    print()
    d = report["director_count_distribution"]
    print("Director-count distribution:")
    print(f"  1 director only:           {d['1_director_only']:,}")
    print(f"  2-4 (sparse):              {d['2-4_sparse']:,}")
    print(f"  5-9 (typical public co):   {d['5-9_typical']:,}")
    print(f"  10+ (large board):         {d['10+_large_board']:,}")
    print(f"  avg directors/master:      {d['avg_per_master']}")
    print(f"  max directors/master:      {d['max_per_master']}")
    print()
    print("Gold-standard tier coverage:")
    for tier, vals in report["gold_standard_tier"].items():
        pct = 100.0 * vals["with_directors"] / vals["total"] if vals["total"] else 0
        print(f"  {tier:<10} {vals['total']:>10,} total, {vals['with_directors']:>5,} with directors ({pct:.2f}%)")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--json", action="store_true",
                        help="Emit JSON (one object) instead of human text")
    args = parser.parse_args()

    try:
        report = gather_reach()
    except Exception as exc:
        print(f"ERROR: gather_reach failed: {exc}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(report, default=str, indent=2))
    else:
        print_human(report)
    return 0


if __name__ == "__main__":
    sys.exit(main())
