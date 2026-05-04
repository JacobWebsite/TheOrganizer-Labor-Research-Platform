"""
Identify F7 orphans that are RECOVERABLE — i.e. they once had a Splink-based
match (now superseded) but currently have no active match in any source.

This is the candidate set for the V2-cascade rematch (Week 2 of the
2026-05-04 → 2026-07-05 launch roadmap; recommendation #1 from the F7
Orphan Rate Regression Open Problem).

Strategy: an F7 employer is a "recoverable orphan" if it satisfies BOTH:
  (a) Has at least one historical FUZZY_SPLINK_ADAPTIVE match, status='superseded'
      (= the V1 matcher found *something* for this F7, but V2 hasn't beaten it)
  (b) Has zero status='active' matches from any source today
      (= it's currently orphaned)

The output is:
  1. A staging table `_recoverable_f7_orphans` populated with the candidate set
  2. A breakdown by NAICS-2 sector (where most concentration is), state, and
     historical-source mix (which sources had Splink matches that we need to
     rematch via V2).

Usage:
    py scripts/matching/identify_recoverable_orphans.py
    py scripts/matching/identify_recoverable_orphans.py --replace
    py scripts/matching/identify_recoverable_orphans.py --dry-run

Exit codes:
  0 success
  1 candidate set is implausibly small/large (likely a query bug)
  2 DB unreachable

The recovered staging table feeds the Week 2 V2-cascade rematch executor
(separate script, TBD). This script is read-only; it only creates a TEMP-
persisted staging table.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

try:
    from db_config import get_connection
except Exception as exc:  # pragma: no cover
    print(f"ERROR: cannot import db_config: {exc}", file=sys.stderr)
    sys.exit(2)


STAGING_TABLE = "_recoverable_f7_orphans"

# Plausibility band — 2026-05-04 baseline measured 15,537 candidates.
# A reading outside [5,000 - 30,000] strongly suggests a query bug or that
# matching pipeline state has changed in unexpected ways.
MIN_PLAUSIBLE = 5_000
MAX_PLAUSIBLE = 30_000


CREATE_SQL = f"""
DROP TABLE IF EXISTS {STAGING_TABLE};

CREATE TABLE {STAGING_TABLE} AS
SELECT
    f.employer_id,
    f.employer_name,
    f.city,
    f.state,
    f.zip,
    f.naics,
    LEFT(COALESCE(f.naics, ''), 2) AS naics_2,
    f.latest_unit_size,
    -- Track which sources had Splink matches we superseded. Useful for
    -- the rematch executor to know where to look.
    (SELECT array_agg(DISTINCT uml.source_system ORDER BY uml.source_system)
     FROM unified_match_log uml
     WHERE uml.target_system = 'f7'
       AND uml.target_id = f.employer_id
       AND uml.match_method = 'FUZZY_SPLINK_ADAPTIVE'
       AND uml.status = 'superseded') AS source_systems_to_retry,
    -- Number of distinct sources that had Splink matches.
    (SELECT COUNT(DISTINCT uml.source_system)
     FROM unified_match_log uml
     WHERE uml.target_system = 'f7'
       AND uml.target_id = f.employer_id
       AND uml.match_method = 'FUZZY_SPLINK_ADAPTIVE'
       AND uml.status = 'superseded') AS source_count_to_retry,
    NOW() AS staged_at
FROM f7_employers_deduped f
WHERE EXISTS (
    SELECT 1 FROM unified_match_log uml
    WHERE uml.target_system = 'f7'
      AND uml.target_id = f.employer_id
      AND uml.match_method = 'FUZZY_SPLINK_ADAPTIVE'
      AND uml.status = 'superseded'
)
AND NOT EXISTS (
    SELECT 1 FROM unified_match_log uml
    WHERE uml.target_system = 'f7'
      AND uml.target_id = f.employer_id
      AND uml.status = 'active'
);

CREATE INDEX idx_{STAGING_TABLE}_employer_id ON {STAGING_TABLE}(employer_id);
CREATE INDEX idx_{STAGING_TABLE}_naics_2 ON {STAGING_TABLE}(naics_2);
CREATE INDEX idx_{STAGING_TABLE}_state ON {STAGING_TABLE}(state);
"""


COUNT_QUERY = f"SELECT COUNT(*) FROM {STAGING_TABLE}"


BREAKDOWNS = [
    (
        "By NAICS-2 sector (top 12)",
        f"""
        SELECT
            COALESCE(naics_2, '(NULL)') AS sector,
            COUNT(*) AS recoverable
        FROM {STAGING_TABLE}
        GROUP BY 1 ORDER BY 2 DESC LIMIT 12
        """,
    ),
    (
        "By state (top 12)",
        f"""
        SELECT
            COALESCE(state, '(NULL)') AS state,
            COUNT(*) AS recoverable
        FROM {STAGING_TABLE}
        GROUP BY 1 ORDER BY 2 DESC LIMIT 12
        """,
    ),
    (
        "By historical source mix",
        f"""
        SELECT
            source_count_to_retry AS sources_per_f7,
            COUNT(*) AS recoverable
        FROM {STAGING_TABLE}
        GROUP BY 1 ORDER BY 1
        """,
    ),
    (
        "Most-common single-source historical mix",
        f"""
        SELECT
            source_systems_to_retry,
            COUNT(*) AS recoverable
        FROM {STAGING_TABLE}
        WHERE source_count_to_retry = 1
        GROUP BY 1 ORDER BY 2 DESC LIMIT 10
        """,
    ),
]


def _print_breakdown(cur, title: str, sql: str):
    print(f"\n  {title}")
    cur.execute(sql)
    for row in cur.fetchall():
        # Cursor mode could be dict or tuple
        if isinstance(row, dict):
            cols = list(row.values())
        else:
            cols = list(row)
        # Format: pad first col, right-align numeric last col
        first = str(cols[0])[:50] if cols[0] is not None else "—"
        last_n = cols[-1] if isinstance(cols[-1], int) else cols[-1]
        print(f"    {first:<50} {last_n:>10,}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--replace", action="store_true",
                        help=f"Drop and recreate {STAGING_TABLE} even if it exists")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print the planned SQL without executing it")
    args = parser.parse_args()

    if args.dry_run:
        print(CREATE_SQL)
        return 0

    try:
        conn = get_connection()
    except Exception as exc:
        print(f"ERROR: db connect: {exc}", file=sys.stderr)
        return 2

    try:
        cur = conn.cursor()

        # Skip recreation if the staging table already exists and --replace
        # not passed (cheap re-run).
        cur.execute("SELECT to_regclass(%s)", [STAGING_TABLE])
        existing = cur.fetchone()
        already_exists = (existing[0] if isinstance(existing, tuple)
                          else existing.get("to_regclass")) is not None
        if already_exists and not args.replace:
            cur.execute(COUNT_QUERY)
            row = cur.fetchone()
            n = row[0] if isinstance(row, tuple) else row.get("count")
            print(f"{STAGING_TABLE} already exists with {n:,} rows. "
                  f"Pass --replace to rebuild.")
        else:
            print(f"Creating {STAGING_TABLE}...")
            cur.execute(CREATE_SQL)
            conn.commit()
            cur.execute(COUNT_QUERY)
            row = cur.fetchone()
            n = row[0] if isinstance(row, tuple) else row.get("count")
            print(f"  -> {n:,} recoverable F7 orphans staged")

        # Plausibility check
        if n < MIN_PLAUSIBLE or n > MAX_PLAUSIBLE:
            print(
                f"\nWARNING: staged count {n:,} is outside the plausible "
                f"band [{MIN_PLAUSIBLE:,}, {MAX_PLAUSIBLE:,}]. Either the "
                "matching pipeline state changed substantially or the "
                "candidate query has a bug. Investigate before running "
                "the rematch executor.",
                file=sys.stderr,
            )
            # Continue but signal via exit code
            return 1

        # Breakdowns
        for title, sql in BREAKDOWNS:
            _print_breakdown(cur, title, sql)

        # Help text
        print(f"\nNext step: feed {STAGING_TABLE}.employer_id into the V2-cascade")
        print("rematch executor (Week 2 of launch roadmap). Expected yield ~50%")
        print("of candidates -> ~7,500 newly-matched F7s. Orphan rate would")
        print("drop from ~65.2% to ~60% (beating R6 baseline 64.7%).")

    finally:
        conn.close()

    return 0


if __name__ == "__main__":
    sys.exit(main())
