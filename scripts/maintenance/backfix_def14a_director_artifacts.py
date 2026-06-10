"""One-shot back-fix for DEF14A director-name suffix artifacts.

Background (2026-05-18): the historical parser
(`scripts/etl/load_def14a_directors.py`) left role-tag and company-name
artifacts on the end of ~85 director_name rows in `employer_directors`:

  - 46 rows: ", Director" / ", Chairman" / etc. comma-role suffix
  - 13 rows: " Key" mixed-case title-bleed
  - 12 rows: " KEY" ALL-CAPS title-bleed (Pfizer DEF14A)
  - 11 rows: " Boeing" company-name suffix (Boeing DEF14A)
  -  4 rows: " - Director" dash-role suffix
  -  1 row : " Apple" company suffix ("Timothy J. Apple" = Tim Cook)
  - sundry: other title bleeds

The live parser is now fixed
(`scripts.etl.director_name_sanitizer.sanitize_director_name` runs at
the end of `_norm_director_name`). This script back-applies the same
sanitizer to the existing rows in `employer_directors`.

Operating modes:
    --dry-run (DEFAULT)  Print a CSV preview to stdout; no writes.
    --commit             Apply UPDATEs (still requires explicit flag).

The script never DELETEs rows. If two sanitized names collide
(unlikely; would require two pre-existing rows with the same
post-sanitize director_name on the same filing accession), the UPDATE
is skipped and the conflict logged for manual review.

`filer_company` is resolved from `sec_companies.company_name` joined
on `filing_cik`; when available it enables aggressive-mode company-
suffix stripping (handles 2-word Boeing-suffix bleeds like
"Akhil Johri Boeing"). When unavailable the conservative mode runs.

Usage:
    py scripts/maintenance/backfix_def14a_director_artifacts.py
    py scripts/maintenance/backfix_def14a_director_artifacts.py --commit
    py scripts/maintenance/backfix_def14a_director_artifacts.py --limit 50 --commit

Exit codes:
    0  Success.
    2  DB unreachable.
"""
from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

# Project root on path so db_config / scripts.etl imports work
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

try:
    from db_config import get_connection
except Exception as exc:  # pragma: no cover
    print(f"ERROR: cannot import db_config: {exc}", file=sys.stderr)
    sys.exit(2)

from scripts.etl.director_name_sanitizer import sanitize_director_name


# Coarse "anything that looks suspicious" pre-filter, used to limit the
# SELECT to candidates only. The sanitizer is then applied per-row in
# Python (cheaper than expressing the full logic in SQL).
SUSPICIOUS_REGEX = (
    r",\s*(?:Director|Chairman|Chairwoman|Chair|President|CEO|CFO|COO|"
    r"Vice\s+Chair(?:man|woman|person)?|Lead\s+Director|"
    r"Independent\s+Director)\s*$|"
    r"\s+-{1,3}\s*(?:Director|Chairman|President|CEO)\s*$|"
    r"\s+(?:KEY|Key)\s*$|"
    r"\s+(?:Boeing|Pfizer|Apple)\s*$"
)


def fetch_candidates(cur, limit: int | None = None):
    """Return rows that look like they have a suffix artifact. Result
    schema: (id, director_name, filing_cik, filer_company)."""
    sql = """
        SELECT
            ed.id,
            ed.director_name,
            ed.filing_cik,
            sc.company_name AS filer_company
        FROM employer_directors ed
        LEFT JOIN sec_companies sc ON sc.cik = ed.filing_cik
        WHERE ed.director_name ~ %s
        ORDER BY ed.id
    """
    if limit:
        sql += f" LIMIT {int(limit)}"
    cur.execute(sql, (SUSPICIOUS_REGEX,))
    return cur.fetchall()


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument(
        "--commit",
        action="store_true",
        help="Apply UPDATEs to employer_directors. Default is dry-run.",
    )
    ap.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Max rows to process (for testing). Default = all.",
    )
    ap.add_argument(
        "--csv-path",
        type=str,
        default=None,
        help="Write dry-run preview to a CSV file instead of stdout.",
    )
    args = ap.parse_args()

    conn = get_connection()
    cur = conn.cursor()

    print("Fetching candidate rows ...", file=sys.stderr)
    rows = fetch_candidates(cur, limit=args.limit)
    print(f"Found {len(rows)} candidate row(s)", file=sys.stderr)

    # Compute proposed change per row
    actions = []  # list of (id, old, new, filer_company, no_change_flag)
    for row in rows:
        row_id, old_name, filing_cik, filer_company = row
        new_name = sanitize_director_name(old_name, filer_company=filer_company)
        if not new_name:
            # Sanitizer reduced the name to empty -- skip (would break NOT NULL)
            actions.append((row_id, old_name, new_name, filer_company, "EMPTY_RESULT"))
            continue
        if new_name == old_name:
            actions.append((row_id, old_name, new_name, filer_company, "NO_CHANGE"))
            continue
        actions.append((row_id, old_name, new_name, filer_company, "CHANGE"))

    n_change = sum(1 for a in actions if a[4] == "CHANGE")
    n_no_change = sum(1 for a in actions if a[4] == "NO_CHANGE")
    n_empty = sum(1 for a in actions if a[4] == "EMPTY_RESULT")
    print(
        f"Summary: {n_change} CHANGE, {n_no_change} NO_CHANGE, "
        f"{n_empty} EMPTY_RESULT (skipped)",
        file=sys.stderr,
    )

    # Emit preview
    if args.csv_path:
        out_path = Path(args.csv_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with out_path.open("w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh)
            w.writerow([
                "id", "old_director_name", "new_director_name",
                "filer_company", "flag",
            ])
            for a in actions:
                w.writerow(a)
        print(f"Wrote CSV preview to {out_path}", file=sys.stderr)
    else:
        w = csv.writer(sys.stdout)
        w.writerow([
            "id", "old_director_name", "new_director_name",
            "filer_company", "flag",
        ])
        for a in actions:
            w.writerow(a)

    if not args.commit:
        print(
            "Dry-run mode (default). Re-run with --commit to apply.",
            file=sys.stderr,
        )
        return

    # Commit path: UPDATE each CHANGE row in a single transaction
    print("Applying UPDATEs ...", file=sys.stderr)
    update_sql = (
        "UPDATE employer_directors "
        "SET director_name = %s, "
        "    name_norm = regexp_replace(lower(%s), '[^a-z0-9 ]', '', 'g') "
        "WHERE id = %s"
    )
    n_applied = 0
    n_skipped_conflict = 0
    for row_id, old, new, filer, flag in actions:
        if flag != "CHANGE":
            continue
        try:
            cur.execute(update_sql, (new, new, row_id))
            n_applied += cur.rowcount
        except Exception as exc:
            # Most likely cause: unique index conflict on (accession, name_norm)
            n_skipped_conflict += 1
            conn.rollback()
            print(
                f"  SKIP id={row_id} {old!r} -> {new!r} ({exc})",
                file=sys.stderr,
            )
            continue
    conn.commit()
    print(
        f"Applied {n_applied} UPDATE(s); skipped {n_skipped_conflict} on conflict.",
        file=sys.stderr,
    )

    cur.close()
    conn.close()


if __name__ == "__main__":
    main()
