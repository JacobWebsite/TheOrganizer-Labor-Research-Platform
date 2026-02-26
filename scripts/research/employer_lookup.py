"""Auto-lookup employer_id from f7_employers_deduped by company name.

Strategy (first match wins):
  1. Exact match on name_standard (normalized)
  2. Prefix match: F7 name_standard starts with query
  3. Trigram similarity on employer_name_aggressive (>= 0.45 threshold)

When multiple F7 records match (e.g. Starbucks has 2 bargaining units),
picks the one with the largest latest_unit_size.

Returns (employer_id, employer_name, match_method) or (None, None, None).
"""
from __future__ import annotations

import logging
import os
import sys
from typing import Optional, Tuple

# Ensure project root importable
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from src.python.matching.name_normalization import (
    normalize_name_standard,
    normalize_name_aggressive,
)

_log = logging.getLogger(__name__)

# Minimum trigram similarity to accept
_TRGM_THRESHOLD = 0.45


def lookup_employer(
    cur,
    company_name: str,
    state: Optional[str] = None,
) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """Look up the best F7 employer match for a company name.

    Parameters
    ----------
    cur : psycopg2 cursor (any cursor type)
    company_name : raw company name from research request
    state : optional 2-letter state code to prefer matches in that state

    Returns
    -------
    (employer_id, employer_name, match_method) or (None, None, None)
    """
    if not company_name or not company_name.strip():
        return None, None, None

    std = normalize_name_standard(company_name)
    agg = normalize_name_aggressive(company_name)

    if not std:
        return None, None, None

    # ------------------------------------------------------------------
    # 1. Exact match on name_standard
    # ------------------------------------------------------------------
    cur.execute(
        """
        SELECT employer_id, employer_name, latest_unit_size, state
        FROM f7_employers_deduped
        WHERE name_standard = %s
        ORDER BY COALESCE(latest_unit_size, 0) DESC
        LIMIT 5
        """,
        (std,),
    )
    rows = _fetch_tuples(cur)
    if rows:
        pick = _best_row(rows, state)
        _log.info("employer_lookup: exact match %r -> %s (%s)", company_name, pick[0], pick[1])
        return pick[0], pick[1], "exact_standard"

    # ------------------------------------------------------------------
    # 2. Prefix match: F7 name starts with the query
    #    e.g. "xpo logistics" matches "xpo logistics freight inc"
    #    Only for 2+ token queries (single tokens are too ambiguous —
    #    "amazon" would wrongly match "amazon masonry").
    # ------------------------------------------------------------------
    if len(std.split()) >= 2:
        prefix_pat = std + " %"
        cur.execute(
            """
            SELECT employer_id, employer_name, latest_unit_size, state
            FROM f7_employers_deduped
            WHERE name_standard LIKE %s
            ORDER BY COALESCE(latest_unit_size, 0) DESC
            LIMIT 10
            """,
            (prefix_pat,),
        )
        rows = _fetch_tuples(cur)
        if rows:
            pick = _best_row(rows, state)
            _log.info("employer_lookup: prefix match %r -> %s (%s)", company_name, pick[0], pick[1])
            return pick[0], pick[1], "prefix_standard"

    # ------------------------------------------------------------------
    # 3. Trigram similarity on employer_name_aggressive
    #    Uses GIN index idx_f7_name_agg_trgm
    # ------------------------------------------------------------------
    cur.execute(
        """
        SELECT employer_id, employer_name, latest_unit_size, state,
               similarity(employer_name_aggressive, %s) AS sim
        FROM f7_employers_deduped
        WHERE employer_name_aggressive %% %s
          AND similarity(employer_name_aggressive, %s) >= %s
        ORDER BY sim DESC, COALESCE(latest_unit_size, 0) DESC
        LIMIT 5
        """,
        (agg, agg, agg, _TRGM_THRESHOLD),
    )
    rows = _fetch_tuples(cur)
    if rows:
        pick = _best_row(rows, state)
        _log.info(
            "employer_lookup: trigram match %r -> %s (%s, sim=%.3f)",
            company_name, pick[0], pick[1],
            rows[0][4] if len(rows[0]) > 4 else 0,
        )
        return pick[0], pick[1], "trigram"

    _log.info("employer_lookup: no match for %r", company_name)
    return None, None, None


def _fetch_tuples(cur) -> list:
    """Fetch all rows as tuples regardless of cursor type."""
    rows = cur.fetchall()
    if not rows:
        return []
    # RealDictCursor returns dicts — convert to tuples
    if isinstance(rows[0], dict):
        keys = list(rows[0].keys())
        return [tuple(r[k] for k in keys) for r in rows]
    return list(rows)


def _best_row(rows: list, state: Optional[str]) -> tuple:
    """Pick the best row, preferring same state, then largest unit size."""
    if not rows:
        return (None, None)
    if state and len(rows) > 1:
        state_u = state.upper().strip()
        in_state = [r for r in rows if r[3] and r[3].upper().strip() == state_u]
        if in_state:
            return in_state[0]
    return rows[0]


def backfill_employer_ids(conn, dry_run: bool = True) -> int:
    """Backfill employer_id on research_runs where it's NULL.

    Returns the number of rows updated.
    """
    cur = conn.cursor()
    cur.execute("""
        SELECT id, company_name, company_state
        FROM research_runs
        WHERE employer_id IS NULL
        ORDER BY id
    """)
    unlinked = _fetch_tuples(cur)
    _log.info("backfill: %d unlinked research runs", len(unlinked))

    updated = 0
    for run_id, company_name, company_state in unlinked:
        emp_id, emp_name, method = lookup_employer(cur, company_name, company_state)
        if emp_id:
            if not dry_run:
                cur.execute(
                    "UPDATE research_runs SET employer_id = %s WHERE id = %s",
                    (emp_id, run_id),
                )
            updated += 1
            print(
                "  run %3d: %s -> %s (%s) [%s]"
                % (run_id, company_name, emp_name, emp_id[:12], method)
            )
        else:
            print("  run %3d: %s -> NO MATCH" % (run_id, company_name))

    if not dry_run:
        conn.commit()
        _log.info("backfill: committed %d updates", updated)
    else:
        print("\nDry run: %d of %d would be linked. Use --commit to persist." % (updated, len(unlinked)))

    return updated


if __name__ == "__main__":
    import argparse
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    parser = argparse.ArgumentParser(description="Backfill employer_id on research_runs")
    parser.add_argument("--commit", action="store_true", help="Persist changes")
    parser.add_argument("--test", type=str, help="Test lookup for a single name")
    args = parser.parse_args()

    from db_config import get_connection

    conn = get_connection()

    if args.test:
        cur = conn.cursor()
        emp_id, emp_name, method = lookup_employer(cur, args.test)
        if emp_id:
            print("%s -> %s (%s) [%s]" % (args.test, emp_name, emp_id, method))
        else:
            print("%s -> NO MATCH" % args.test)
        conn.close()
    else:
        backfill_employer_ids(conn, dry_run=not args.commit)
        conn.close()
