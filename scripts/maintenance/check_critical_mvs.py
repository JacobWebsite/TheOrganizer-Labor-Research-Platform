"""
Verify all critical materialized views exist with non-trivial row counts.

Reads config/critical_mvs.txt (one `<mv_name> <min_rows>` line per MV) and
asserts each MV exists in the public schema with at least `min_rows`. The
companion to scripts/maintenance/check_critical_routes.py: routes is the
"is the API code mounted" check; this is the "is the data behind the API
actually present" check.

Usage:
    py scripts/maintenance/check_critical_mvs.py
    py scripts/maintenance/check_critical_mvs.py --manifest /path/to/manifest.txt

Exit codes:
    0  All MVs present and at or above their floors.
    1  One or more MVs missing or under-floor (release-blocking).
    2  Could not reach the database.

Background: 2026-04-30 incident -- `mv_target_scorecard` silently
disappeared between R7 baseline (2026-04-25, 5.38M rows) and the next
verification run. API returned 503 on every `/api/targets/scorecard*`
call; master-side scoring was dead. No alert fired. This script is the
deployment-hygiene gate added to RELEASE_CHECKLIST.md to catch that
class of bug before a deploy.
"""
import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MANIFEST = PROJECT_ROOT / "config" / "critical_mvs.txt"

sys.path.insert(0, str(PROJECT_ROOT))


def load_manifest(path: Path) -> list[tuple[str, int]]:
    if not path.exists():
        print(f"ERROR: manifest not found at {path}", file=sys.stderr)
        sys.exit(2)
    entries: list[tuple[str, int]] = []
    for lineno, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        if len(parts) != 2:
            print(f"ERROR: {path}:{lineno}: expected '<mv_name> <min_rows>', got {raw!r}",
                  file=sys.stderr)
            sys.exit(2)
        name, min_rows_s = parts
        try:
            min_rows = int(min_rows_s)
        except ValueError:
            print(f"ERROR: {path}:{lineno}: min_rows {min_rows_s!r} is not an integer",
                  file=sys.stderr)
            sys.exit(2)
        entries.append((name, min_rows))
    return entries


def check_mvs(entries: list[tuple[str, int]]) -> tuple[list[str], list[str]]:
    """Returns (ok_lines, fail_lines) — printable strings per MV."""
    try:
        from db_config import get_connection
        conn = get_connection()
    except Exception as exc:
        print(f"ERROR: could not connect to database: {exc}", file=sys.stderr)
        sys.exit(2)

    ok: list[str] = []
    fail: list[str] = []
    try:
        cur = conn.cursor()
        # Fetch the set of existing MVs in one query (avoids N round-trips).
        names = [name for name, _ in entries]
        cur.execute(
            "SELECT matviewname FROM pg_matviews "
            "WHERE schemaname = 'public' AND matviewname = ANY(%s)",
            (names,),
        )
        present_mvs = {r[0] for r in cur.fetchall()}

        # employer_comparables is a regular table, not an MV — treat the
        # manifest pragmatically: anything not in pg_matviews falls back
        # to pg_class for existence check.
        cur.execute(
            "SELECT relname FROM pg_class WHERE relname = ANY(%s) "
            "AND relkind IN ('r','m','v','p')",
            (names,),
        )
        present_relations = {r[0] for r in cur.fetchall()}

        # Codex review 2026-04-30: don't string-format relation names into SQL
        # even though pg_class restricts the choices; future manifest entries
        # could be malicious or malformed. psycopg2.sql.Identifier quotes safely.
        from psycopg2 import sql

        for name, min_rows in entries:
            if name not in present_relations:
                fail.append(f"  MISSING  {name:<35s} (expected >= {min_rows:,})")
                continue
            cur.execute(
                sql.SQL("SELECT COUNT(*) FROM {}").format(sql.Identifier(name))
            )
            count = cur.fetchone()[0]
            kind = "MV" if name in present_mvs else "table"
            if count < min_rows:
                fail.append(
                    f"  UNDER    {name:<35s} {count:>15,} rows ({kind}; floor {min_rows:,})"
                )
            else:
                ok.append(
                    f"  OK       {name:<35s} {count:>15,} rows ({kind}; floor {min_rows:,})"
                )
    finally:
        conn.close()
    return ok, fail


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--manifest", default=str(DEFAULT_MANIFEST),
                        help=f"Path to critical MVs manifest (default: {DEFAULT_MANIFEST})")
    args = parser.parse_args()

    entries = load_manifest(Path(args.manifest))
    print(f"Checking {len(entries)} critical MVs/tables against the database.")

    ok, fail = check_mvs(entries)
    for line in ok:
        print(line)
    for line in fail:
        print(line, file=sys.stderr)

    if fail:
        print(f"\nFAIL: {len(fail)} critical MV/table issue(s).", file=sys.stderr)
        print("Likely fix: run the relevant build script "
              "(e.g. py scripts/scoring/build_target_scorecard.py).", file=sys.stderr)
        return 1
    print(f"\nOK: all {len(entries)} critical MVs/tables present and at floor.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
