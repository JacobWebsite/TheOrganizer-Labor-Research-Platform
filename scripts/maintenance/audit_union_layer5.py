"""Union Explorer Audit -- Layer 5 (anomaly set: frozen + re-derived + diff).

Per Codex review 2026-05-04: maintain both a frozen corpus of known-weird
f_nums and a re-derived corpus computed each run. Compute the diff vs the
prior run to surface NEW anomalies (data drift) and GONE anomalies (resolved).

Anomaly categories (deterministic SQL):
  - large_active_zero_nlrb        -- members>5K, active, zero NLRB matches
  - active_no_recent_filing       -- active, no LM-2 since 2020
  - members_jump_or_drop          -- year-over-year membership delta >50%
  - employer_under_multiple_unions -- F-7 employer_id linked to >1 union
  - non_ascii_union_name          -- weird characters in union_name
  - parentless_local_named_local  -- desig_name='LOCAL' but parent_fnum NULL (currently all rows)
  - no_lm2_no_f7_no_nlrb          -- triple-null shells
  - giant_assets_zero_employers   -- >100M assets but zero F7 employers

Per Codex: LLM does NOT pick anomalies. Layer 4 (DeepSeek) can summarize/rank
these but does not generate them.

Usage:
  py scripts/maintenance/audit_union_layer5.py
  py scripts/maintenance/audit_union_layer5.py --output-dir custom/path
"""
from __future__ import annotations

import argparse
import datetime as dt
import decimal
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from db_config import get_connection

PROJECT_ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent


def _to_jsonable(v: Any) -> Any:
    if isinstance(v, decimal.Decimal):
        return float(v)
    if isinstance(v, (dt.date, dt.datetime)):
        return v.isoformat()
    return v


# ============================================================
# Anomaly queries
# ============================================================

ANOMALY_QUERIES: dict[str, str] = {
    "large_active_zero_nlrb": """
        WITH nlrb_matched AS (
            SELECT DISTINCT matched_olms_fnum AS f_num FROM nlrb_tallies
            WHERE matched_olms_fnum IS NOT NULL
        )
        SELECT um.f_num, um.union_name, um.aff_abbr, um.members, um.sector
        FROM unions_master um
        LEFT JOIN nlrb_matched nm ON nm.f_num = um.f_num
        WHERE NOT um.is_likely_inactive
          AND um.members > 5000
          AND nm.f_num IS NULL
        ORDER BY um.members DESC
    """,
    "active_no_recent_filing": """
        WITH recent AS (
            SELECT DISTINCT f_num FROM lm_data WHERE yr_covered >= 2020
        )
        SELECT um.f_num, um.union_name, um.aff_abbr, um.members
        FROM unions_master um
        LEFT JOIN recent r ON r.f_num = um.f_num
        WHERE NOT um.is_likely_inactive
          AND r.f_num IS NULL
        ORDER BY um.members DESC NULLS LAST
    """,
    "members_jump_or_drop_50pct": """
        WITH yearly AS (
            SELECT lm.f_num, lm.yr_covered,
                   SUM(am.number) FILTER (WHERE am.voting_eligibility = 'T') AS members
            FROM lm_data lm
            LEFT JOIN ar_membership am ON am.rpt_id = lm.rpt_id
            WHERE lm.yr_covered >= 2018
            GROUP BY lm.f_num, lm.yr_covered
        ),
        with_lag AS (
            SELECT f_num, yr_covered, members,
                   LAG(members) OVER (PARTITION BY f_num ORDER BY yr_covered) AS prev_members
            FROM yearly
        )
        SELECT um.f_num, um.union_name, um.aff_abbr,
               wl.yr_covered, wl.members, wl.prev_members,
               ROUND(100.0 * (wl.members - wl.prev_members) / NULLIF(wl.prev_members, 0), 0) AS pct_change
        FROM with_lag wl
        JOIN unions_master um ON um.f_num = wl.f_num
        WHERE wl.prev_members IS NOT NULL AND wl.prev_members > 100
          AND wl.members IS NOT NULL
          AND ABS(wl.members - wl.prev_members) > GREATEST(wl.prev_members * 0.5, 50)
          AND NOT um.is_likely_inactive
        ORDER BY ABS(wl.members - wl.prev_members) DESC
        LIMIT 200
    """,
    "employer_under_multiple_unions": """
        SELECT employer_id, COUNT(DISTINCT latest_union_fnum) AS union_count,
               STRING_AGG(DISTINCT latest_union_fnum::text, ', ') AS unions
        FROM f7_employers_deduped
        WHERE latest_union_fnum IS NOT NULL
        GROUP BY employer_id
        HAVING COUNT(DISTINCT latest_union_fnum) > 1
        ORDER BY COUNT(DISTINCT latest_union_fnum) DESC
        LIMIT 100
    """,
    "non_ascii_union_name": """
        SELECT f_num, union_name
        FROM unions_master
        WHERE union_name ~ '[^\\x00-\\x7F]'
        ORDER BY f_num
        LIMIT 100
    """,
    "no_lm2_no_f7_no_nlrb_active": """
        WITH lm AS (SELECT DISTINCT f_num FROM lm_data),
             f7 AS (SELECT DISTINCT latest_union_fnum::text AS f_num FROM f7_employers_deduped WHERE latest_union_fnum IS NOT NULL),
             nl AS (SELECT DISTINCT matched_olms_fnum AS f_num FROM nlrb_tallies WHERE matched_olms_fnum IS NOT NULL)
        SELECT um.f_num, um.union_name, um.aff_abbr, um.members
        FROM unions_master um
        LEFT JOIN lm ON lm.f_num = um.f_num
        LEFT JOIN f7 ON f7.f_num = um.f_num
        LEFT JOIN nl ON nl.f_num = um.f_num
        WHERE NOT um.is_likely_inactive
          AND lm.f_num IS NULL AND f7.f_num IS NULL AND nl.f_num IS NULL
        ORDER BY um.members DESC NULLS LAST
        LIMIT 200
    """,
    "giant_assets_zero_employers": """
        WITH latest AS (
            SELECT f_num, ttl_assets,
                   ROW_NUMBER() OVER (PARTITION BY f_num ORDER BY yr_covered DESC) AS rn
            FROM lm_data WHERE ttl_assets IS NOT NULL
        ),
        f7_count AS (
            SELECT latest_union_fnum::text AS f_num, COUNT(*) AS cnt
            FROM f7_employers_deduped WHERE latest_union_fnum IS NOT NULL
            GROUP BY latest_union_fnum
        )
        SELECT um.f_num, um.union_name, um.aff_abbr, l.ttl_assets, COALESCE(f.cnt, 0) AS f7_count
        FROM unions_master um
        JOIN latest l ON l.f_num = um.f_num AND l.rn = 1
        LEFT JOIN f7_count f ON f.f_num = um.f_num
        WHERE l.ttl_assets > 100000000  -- $100M
          AND COALESCE(f.cnt, 0) = 0
          AND NOT um.is_likely_inactive
        ORDER BY l.ttl_assets DESC
        LIMIT 100
    """,
}


# ============================================================
# Frozen corpus loader
# ============================================================

def load_frozen(path: Path) -> dict:
    if not path.is_file():
        return {"suppress_aff_abbr": [], "suppress_f_num": []}
    import yaml
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def _is_suppressed(row: dict, category: str, frozen: dict) -> tuple[bool, str]:
    aff = row.get("aff_abbr")
    f_num = row.get("f_num")
    for entry in frozen.get("suppress_aff_abbr", []) or []:
        if entry.get("aff_abbr") == aff and category in (entry.get("categories") or []):
            return True, f"frozen aff_abbr suppression: {entry.get('reason', '')}"
    for entry in frozen.get("suppress_f_num", []) or []:
        if entry.get("f_num") == f_num and category in (entry.get("categories") or []):
            return True, f"frozen f_num suppression: {entry.get('reason', '')}"
    return False, ""


# ============================================================
# Run + diff
# ============================================================

def run_anomaly_queries(cur) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {}
    for name, sql in ANOMALY_QUERIES.items():
        try:
            cur.execute(sql)
            cols = [c.name for c in cur.description] if cur.description else []
            rows = []
            for r in cur.fetchall():
                d = dict(zip(cols, r)) if not hasattr(r, "_asdict") else r._asdict()
                rows.append({k: _to_jsonable(v) for k, v in d.items()})
            out[name] = rows
        except Exception as exc:
            try:
                cur.connection.rollback()
            except Exception:
                pass
            out[name] = [{"_error": str(exc)}]
    return out


def find_prior_run(out_dir_today: Path) -> Path | None:
    parent = out_dir_today.parent
    if not parent.is_dir():
        return None
    candidates = sorted(
        [d for d in parent.iterdir() if d.is_dir() and d.name < out_dir_today.name],
        reverse=True,
    )
    for c in candidates:
        f = c / "layer5_anomaly_set.json"
        if f.is_file():
            return f
    return None


def diff_against_prior(current: dict[str, list[dict]], prior_path: Path | None) -> dict[str, dict]:
    if not prior_path:
        return {"prior_path": None, "new_per_category": {}, "gone_per_category": {}}
    try:
        prior = json.loads(prior_path.read_text(encoding="utf-8"))
    except Exception:
        return {"prior_path": str(prior_path), "_error": "could not load prior"}
    new_per: dict[str, list[str]] = {}
    gone_per: dict[str, list[str]] = {}
    for cat, rows in current.items():
        cur_keys = {(r.get("f_num") or r.get("employer_id") or "?") for r in rows}
        prior_rows = prior.get("anomalies", {}).get(cat, []) or []
        prior_keys = {(r.get("f_num") or r.get("employer_id") or "?") for r in prior_rows}
        new_per[cat] = sorted(cur_keys - prior_keys)
        gone_per[cat] = sorted(prior_keys - cur_keys)
    return {
        "prior_path": str(prior_path),
        "new_per_category": new_per,
        "gone_per_category": gone_per,
    }


def split_unexplained(current: dict[str, list[dict]], frozen: dict) -> dict[str, list[dict]]:
    """Bucket rows into (suppressed, unexplained) per category."""
    unexplained: dict[str, list[dict]] = {}
    for cat, rows in current.items():
        unexplained[cat] = []
        for r in rows:
            is_supp, _ = _is_suppressed(r, cat, frozen)
            if not is_supp:
                unexplained[cat].append(r)
    return unexplained


# ============================================================
# Main
# ============================================================

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--output-dir", default=None)
    ap.add_argument("--frozen", default=None,
                    help="Path to audit_union_anomaly_frozen.yaml (default: alongside this script)")
    args = ap.parse_args()

    out_dir = Path(args.output_dir) if args.output_dir else (
        PROJECT_ROOT / "audit_runs" / dt.date.today().isoformat()
    )
    out_dir.mkdir(parents=True, exist_ok=True)
    frozen_path = Path(args.frozen) if args.frozen else (HERE / "audit_union_anomaly_frozen.yaml")
    frozen = load_frozen(frozen_path)
    print(f"Loaded frozen corpus: "
          f"{len(frozen.get('suppress_aff_abbr', []))} aff suppressions, "
          f"{len(frozen.get('suppress_f_num', []))} f_num suppressions")

    print(f"Running {len(ANOMALY_QUERIES)} anomaly queries ...")
    with get_connection() as conn:
        with conn.cursor() as cur:
            current = run_anomaly_queries(cur)

    for cat, rows in current.items():
        n = len([r for r in rows if "_error" not in r])
        print(f"  {cat}: {n} row(s)")

    unexplained = split_unexplained(current, frozen)
    diff = diff_against_prior(current, find_prior_run(out_dir))

    out_path = out_dir / "layer5_anomaly_set.json"
    unx_path = out_dir / "layer5_unexplained.json"
    diff_path = out_dir / "layer5_diff.json"
    md_path = out_dir / "layer5_report.md"

    out_path.write_text(json.dumps({
        "ran_at": dt.datetime.now().isoformat(timespec="seconds"),
        "anomalies": current,
    }, indent=2, default=_to_jsonable), encoding="utf-8")
    unx_path.write_text(json.dumps(unexplained, indent=2, default=_to_jsonable), encoding="utf-8")
    diff_path.write_text(json.dumps(diff, indent=2, default=_to_jsonable), encoding="utf-8")

    lines = [
        "# Union Explorer Audit -- Layer 5 (Anomaly Set)",
        "",
        f"Run at: {dt.datetime.now().isoformat(timespec='seconds')}",
        "",
        "## Re-derived anomalies (today)",
        "",
    ]
    total_un = 0
    for cat, rows in current.items():
        n_total = len([r for r in rows if "_error" not in r])
        n_unx = len(unexplained.get(cat, []))
        total_un += n_unx
        lines.append(f"- **{cat}**: {n_total} total, {n_unx} unexplained (after frozen suppressions)")
    lines += ["", f"**Total unexplained anomalies: {total_un}**", ""]

    if diff.get("prior_path"):
        lines += ["## Diff vs prior run", "",
                  f"Prior: `{diff['prior_path']}`", ""]
        new_n = sum(len(v) for v in diff.get("new_per_category", {}).values())
        gone_n = sum(len(v) for v in diff.get("gone_per_category", {}).values())
        lines.append(f"- New since prior: {new_n}")
        lines.append(f"- Gone since prior: {gone_n}")
        lines.append("")
        for cat, fnums in (diff.get("new_per_category") or {}).items():
            if fnums:
                lines.append(f"### {cat} -- {len(fnums)} new")
                for f in fnums[:20]:
                    lines.append(f"  - {f}")
                if len(fnums) > 20:
                    lines.append(f"  - ... and {len(fnums)-20} more")
                lines.append("")
    else:
        lines += ["## Diff vs prior run", "", "(no prior run found in audit_runs/)", ""]

    md_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"\nResults written to:\n  {out_path}\n  {unx_path}\n  {diff_path}\n  {md_path}")
    print(f"Total unexplained anomalies: {total_un}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
