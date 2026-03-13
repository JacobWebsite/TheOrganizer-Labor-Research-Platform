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
import re
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
    address: Optional[str] = None,
) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """Look up the best F7 employer match for a company name.

    Parameters
    ----------
    cur : psycopg2 cursor (any cursor type)
    company_name : raw company name from research request
    state : optional 2-letter state code to prefer matches in that state
    address : optional street address or zip code to narrow search

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
    # 0. Address-Based Stricter Match (if address provided)
    # ------------------------------------------------------------------
    if address:
        addr_clean = address.strip().lower()
        # Try to extract zip if it looks like one (5 digits)
        zip_match = re.search(r'\b(\d{5})\b', addr_clean)
        zip_code = zip_match.group(1) if zip_match else None
        
        # Strategy: Name similarity + Street or Zip match
        cur.execute(
            """
            SELECT employer_id, employer_name, latest_unit_size, state, street, zip
            FROM f7_employers_deduped
            WHERE (name_standard = %s OR employer_name_aggressive %% %s)
              AND (
                (%s IS NOT NULL AND zip = %s)
                OR (%s IS NOT NULL AND street ILIKE %s)
              )
            ORDER BY similarity(employer_name_aggressive, %s) DESC, COALESCE(latest_unit_size, 0) DESC
            LIMIT 5
            """,
            (std, agg, zip_code, zip_code, addr_clean, f"%{addr_clean}%", agg),
        )
        rows = _fetch_tuples(cur)
        if rows:
            pick = _best_row(rows, state)
            _log.info("employer_lookup: address-verified match %r + %r -> %s (%s)", 
                      company_name, address, pick[0], pick[1])
            return pick[0], pick[1], "name_and_address"

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

    # ------------------------------------------------------------------
    # 4. UML evidence fallback: search unified_match_log evidence->>'source_name'
    #    via trigram similarity. Useful for research runs where name variants differ.
    # ------------------------------------------------------------------
    uml_result = _lookup_uml_evidence(cur, company_name, agg, state)
    if uml_result[0]:
        return uml_result

    # ------------------------------------------------------------------
    # 5. Master employers fallback (4.5M rows, non-F7 employers)
    # ------------------------------------------------------------------
    master_result = _lookup_master(cur, company_name, std, agg, state)
    if master_result[0]:
        return master_result

    _log.info("employer_lookup: no match for %r", company_name)
    return None, None, None


def _lookup_uml_evidence(
    cur,
    company_name: str,
    agg: str,
    state: Optional[str] = None,
) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """Fallback: search unified_match_log evidence->>'source_name' via trigram.

    Returns (f7_employer_id, employer_name, 'uml_evidence') or (None, None, None).
    """
    try:
        state_clause = ""
        params = [agg, agg, agg, 0.40]
        if state:
            state_clause = "AND evidence->>'state' = %s"
            params.append(state.upper().strip())

        cur.execute(
            f"""
            SELECT target_id AS employer_id,
                   evidence->>'source_name' AS source_name,
                   similarity(evidence->>'source_name', %s) AS sim
            FROM unified_match_log
            WHERE status = 'active'
              AND target_system = 'f7'
              AND evidence->>'source_name' IS NOT NULL
              AND evidence->>'source_name' %% %s
              AND similarity(evidence->>'source_name', %s) >= %s
              {state_clause}
            ORDER BY sim DESC
            LIMIT 1
            """,
            params,
        )
        rows = _fetch_tuples(cur)
        if rows:
            emp_id = rows[0][0]
            # Get actual employer name from F7
            cur.execute(
                "SELECT employer_name FROM f7_employers_deduped WHERE employer_id = %s",
                (emp_id,),
            )
            name_rows = _fetch_tuples(cur)
            emp_name = name_rows[0][0] if name_rows else rows[0][1]
            _log.info(
                "employer_lookup: UML evidence match %r -> %s (%s)",
                company_name, emp_id, emp_name,
            )
            return emp_id, emp_name, "uml_evidence"
    except Exception as exc:
        _log.debug("UML evidence lookup failed: %s", exc)
        # Reset transaction state so subsequent queries don't fail
        try:
            cur.connection.rollback()
        except Exception:
            pass

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


_MASTER_TRGM_THRESHOLD = 0.50


def _lookup_master(
    cur,
    company_name: str,
    std: str,
    agg: str,
    state: Optional[str] = None,
) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """Fallback lookup in master_employers (4.5M rows).

    Returns (master_id::TEXT, display_name, match_method) or (None, None, None).
    """
    state_clause = ""
    params_exact: list = [std]
    params_trgm: list = [agg, agg, agg, _MASTER_TRGM_THRESHOLD]

    if state:
        state_clause = "AND me.state = %s"
        params_exact.append(state.upper().strip())
        params_trgm.append(state.upper().strip())

    # Tier 1: Exact match on canonical_name
    cur.execute(
        f"""
        SELECT me.master_id::TEXT AS employer_id, me.display_name,
               COALESCE(tds.source_count, 0) AS source_count
        FROM master_employers me
        LEFT JOIN mv_target_data_sources tds ON tds.master_id = me.master_id
        WHERE me.canonical_name = %s
          {state_clause}
        ORDER BY COALESCE(tds.source_count, 0) DESC,
                 COALESCE(me.employee_count, 0) DESC
        LIMIT 5
        """,
        params_exact,
    )
    rows = _fetch_tuples(cur)
    if rows:
        pick = rows[0]
        _log.info(
            "employer_lookup: master exact match %r -> %s (%s)",
            company_name, pick[0], pick[1],
        )
        return pick[0], pick[1], "master_exact"

    # Tier 2: Trigram on canonical_name (uses idx_master_employers_canonical_name_trgm)
    cur.execute(
        f"""
        SELECT me.master_id::TEXT AS employer_id, me.display_name,
               similarity(me.canonical_name, %s) AS sim
        FROM master_employers me
        WHERE me.canonical_name %% %s
          AND similarity(me.canonical_name, %s) >= %s
          {state_clause}
        ORDER BY sim DESC, COALESCE(me.employee_count, 0) DESC
        LIMIT 5
        """,
        params_trgm,
    )
    rows = _fetch_tuples(cur)
    if rows:
        pick = rows[0]
        _log.info(
            "employer_lookup: master trigram match %r -> %s (%s, sim=%.3f)",
            company_name, pick[0], pick[1],
            rows[0][2] if len(rows[0]) > 2 else 0,
        )
        return pick[0], pick[1], "master_trigram"

    return None, None, None


def backfill_employer_ids(conn, dry_run: bool = True) -> int:
    """Backfill employer_id on research_runs where it's NULL.

    Returns the number of rows updated.
    """
    cur = conn.cursor()
    cur.execute("""
        SELECT id, company_name, company_state, company_address
        FROM research_runs
        WHERE employer_id IS NULL
        ORDER BY id
    """)
    unlinked = _fetch_tuples(cur)
    _log.info("backfill: %d unlinked research runs", len(unlinked))

    updated = 0
    for run_id, company_name, company_state, company_address in unlinked:
        emp_id, emp_name, method = lookup_employer(cur, company_name, company_state, company_address)
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
