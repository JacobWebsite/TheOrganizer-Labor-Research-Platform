"""
Resolve orphaned union file numbers in f7_union_employer_relations.

Orphan fnums are union_file_number values in f7_union_employer_relations
that have no corresponding entry in unions_master.f_num.

Resolution categories (applied in order):
  1. REMAP      -- crosswalk one-to-one cases with target in unions_master
  2. CWA_GEO    -- fnum 12590 geographic devolution to successor locals
  3. NAME_MATCH -- orphans with lm_data names matching unions_master (pg_trgm >= 0.7)
  4. ADD_MASTER  -- orphans with recent lm_data (2020+) but missing from unions_master
  5. DISSOLVED  -- orphans with last lm_data filing before 2015
  6. DATA_QUALITY -- orphans with no lm_data history at all
  7. INVESTIGATE -- everything else

All changes run in a single transaction with rollback on error.
Audit trail in union_fnum_resolution_log table.

Usage:
    py scripts/maintenance/resolve_missing_unions.py --diagnose
    py scripts/maintenance/resolve_missing_unions.py --dry-run
    py scripts/maintenance/resolve_missing_unions.py --apply
"""
from __future__ import annotations

import argparse
import os
import sys
from collections import defaultdict
from datetime import datetime
from typing import Dict, List, Optional, Tuple

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from db_config import get_connection

CWA_FNUM = 12590


def get_orphan_fnums(cur) -> List[int]:
    """Return all orphan file numbers."""
    cur.execute("""
        SELECT DISTINCT r.union_file_number
        FROM f7_union_employer_relations r
        LEFT JOIN unions_master u ON r.union_file_number::text = u.f_num
        WHERE u.f_num IS NULL
        ORDER BY r.union_file_number
    """)
    return [r[0] for r in cur.fetchall()]


def get_orphan_stats(cur, fnums: List[int]) -> Dict[int, dict]:
    """Get relation count and worker total for each orphan fnum."""
    if not fnums:
        return {}
    cur.execute("""
        SELECT r.union_file_number,
               COUNT(*) AS rels,
               COALESCE(SUM(r.bargaining_unit_size), 0) AS workers
        FROM f7_union_employer_relations r
        WHERE r.union_file_number = ANY(%s)
        GROUP BY r.union_file_number
    """, (fnums,))
    return {r[0]: {"rels": r[1], "workers": r[2]} for r in cur.fetchall()}


def get_total_relation_count(cur) -> int:
    cur.execute("SELECT COUNT(*) FROM f7_union_employer_relations")
    return cur.fetchone()[0]


# ============================================================================
# Category 1: REMAP (crosswalk one-to-one cases)
# ============================================================================

def find_remap_candidates(cur, orphans: List[int]) -> Dict[int, str]:
    """Find orphan fnums with exactly one crosswalk target in unions_master."""
    if not orphans:
        return {}
    # Exclude CWA_FNUM (handled separately)
    cur.execute("""
        WITH xwalk AS (
            SELECT c.f7_fnum,
                   c.matched_fnum,
                   c.matched_union_name,
                   c.confidence
            FROM f7_fnum_crosswalk c
            JOIN unions_master u ON u.f_num = c.matched_fnum::text
            WHERE c.f7_fnum = ANY(%s)
              AND c.f7_fnum != %s
        ),
        one_to_one AS (
            SELECT f7_fnum
            FROM xwalk
            GROUP BY f7_fnum
            HAVING COUNT(DISTINCT matched_fnum) = 1
        )
        SELECT x.f7_fnum, x.matched_fnum, x.matched_union_name, x.confidence
        FROM xwalk x
        JOIN one_to_one o ON o.f7_fnum = x.f7_fnum
    """, (orphans, CWA_FNUM))
    return {r[0]: r[1] for r in cur.fetchall()}


def apply_remap(cur, remap: Dict[int, str], dry_run: bool) -> int:
    """Remap orphan fnums to their crosswalk target."""
    count = 0
    for old_fnum, new_fnum in remap.items():
        if dry_run:
            cur.execute("""
                SELECT COUNT(*) FROM f7_union_employer_relations
                WHERE union_file_number = %s
            """, (old_fnum,))
            n = cur.fetchone()[0]
            print(f"  REMAP {old_fnum} -> {new_fnum} ({n} rows)")
            count += n
        else:
            cur.execute("""
                UPDATE f7_union_employer_relations
                SET union_file_number = %s
                WHERE union_file_number = %s
            """, (int(new_fnum), old_fnum))
            n = cur.rowcount
            print(f"  REMAP {old_fnum} -> {new_fnum} ({n} rows updated)")
            count += n
    return count


# ============================================================================
# Category 2: CWA_GEO (geographic devolution for fnum 12590)
# ============================================================================

def find_cwa_successor_states(cur) -> Dict[str, str]:
    """Map each successor local's fnum to the states it covers.

    Returns {state: successor_fnum} for the best successor in each state.
    """
    # Get successor fnums from crosswalk
    cur.execute("""
        SELECT c.matched_fnum
        FROM f7_fnum_crosswalk c
        JOIN unions_master u ON u.f_num = c.matched_fnum::text
        WHERE c.f7_fnum = %s
    """, (CWA_FNUM,))
    successor_fnums = [r[0] for r in cur.fetchall()]

    if not successor_fnums:
        # Fallback: find CWA locals that look like successors by name/affiliation
        cur.execute("""
            SELECT f_num, union_name, state
            FROM unions_master
            WHERE (aff_abbr ILIKE '%%CWA%%' OR union_name ILIKE '%%communication workers%%')
              AND f_num ~ '^[0-9]+$'
              AND CAST(f_num AS bigint) > 500000
            ORDER BY f_num
        """)
        rows = cur.fetchall()
        if rows:
            # Use these as successors, map by state from unions_master
            state_map = {}
            for r in rows:
                if r[2] and r[2] not in state_map:
                    state_map[r[2]] = r[0]
            return state_map
        return {}

    # For each successor, find states they serve via existing employer relations
    state_map = {}  # state -> (successor_fnum, relation_count)
    for sfnum in successor_fnums:
        cur.execute("""
            SELECT e.state, COUNT(*) AS cnt
            FROM f7_union_employer_relations r
            JOIN f7_employers_deduped e ON e.employer_id = r.employer_id
            WHERE r.union_file_number = %s::integer
            GROUP BY e.state
            ORDER BY cnt DESC
        """, (sfnum,))
        for row in cur.fetchall():
            state = row[0]
            cnt = row[1]
            if state and (state not in state_map or cnt > state_map[state][1]):
                state_map[state] = (sfnum, cnt)

    # Also check unions_master.state for successors (some may have no relations yet)
    for sfnum in successor_fnums:
        cur.execute("""
            SELECT state FROM unions_master WHERE f_num = %s
        """, (sfnum,))
        row = cur.fetchone()
        if row and row[0] and row[0] not in state_map:
            state_map[row[0]] = (sfnum, 0)

    return {state: info[0] for state, info in state_map.items()}


def apply_cwa_geo(cur, dry_run: bool) -> int:
    """Route CWA District 7 relations to successor locals by state."""
    # Check if 12590 is still an orphan
    cur.execute("SELECT f_num FROM unions_master WHERE f_num = '12590'")
    if cur.fetchone():
        print("  CWA_GEO: fnum 12590 already in unions_master, skipping.")
        return 0

    cur.execute("""
        SELECT COUNT(*) FROM f7_union_employer_relations
        WHERE union_file_number = %s
    """, (CWA_FNUM,))
    total_cwa = cur.fetchone()[0]
    if total_cwa == 0:
        print("  CWA_GEO: No relations for fnum 12590, skipping.")
        return 0

    state_map = find_cwa_successor_states(cur)
    if not state_map:
        print("  CWA_GEO: No successor locals found for fnum 12590.")
        print("  Will add 12590 directly to unions_master as fallback.")
        if not dry_run:
            _add_cwa_to_master(cur)
        return 0

    print(f"  CWA_GEO: Successor state map ({len(state_map)} states):")
    for state, sfnum in sorted(state_map.items()):
        cur.execute("SELECT union_name FROM unions_master WHERE f_num = %s", (sfnum,))
        name_row = cur.fetchone()
        name = (name_row[0] if name_row else "?")[:40]
        print(f"    {state}: -> {sfnum} ({name})")

    # Get each 12590 relation with its employer's state
    cur.execute("""
        SELECT r.id, r.employer_id, r.union_file_number,
               r.bargaining_unit_size, e.state
        FROM f7_union_employer_relations r
        JOIN f7_employers_deduped e ON e.employer_id = r.employer_id
        WHERE r.union_file_number = %s
    """, (CWA_FNUM,))
    relations = cur.fetchall()

    remapped = 0
    kept_as_district = 0
    for rel in relations:
        rel_id, emp_id, _, bu_size, emp_state = rel
        if emp_state and emp_state in state_map:
            target_fnum = state_map[emp_state]
            if dry_run:
                print(f"    Would remap rel {rel_id} ({emp_state}) -> {target_fnum}")
            else:
                cur.execute("""
                    UPDATE f7_union_employer_relations
                    SET union_file_number = %s
                    WHERE id = %s
                """, (int(target_fnum), rel_id))
            remapped += 1
        else:
            kept_as_district += 1

    # For relations in unmapped states, add 12590 to unions_master
    # so they resolve as-is (better than misattributing to wrong local)
    if kept_as_district > 0:
        print(f"  CWA_GEO: {kept_as_district} relations in unmapped states -- "
              f"adding 12590 to unions_master")
        if not dry_run:
            _add_cwa_to_master(cur)

    action = "would resolve" if dry_run else "resolved"
    print(f"  CWA_GEO: {action} {remapped} remapped to successors, "
          f"{kept_as_district} kept under 12590 (added to master)")
    return remapped + kept_as_district


def _add_cwa_to_master(cur) -> None:
    """Add CWA District 7 to unions_master as a fallback."""
    cur.execute("""
        INSERT INTO unions_master (f_num, union_name, aff_abbr)
        VALUES ('12590', 'Communications Workers of America District 7', 'CWA')
        ON CONFLICT (f_num) DO NOTHING
    """)


# ============================================================================
# Category 3: NAME_MATCH (pg_trgm similarity)
# ============================================================================

def find_name_matches(cur, orphans: List[int]) -> Dict[int, Tuple[str, str, float]]:
    """Find orphans with lm_data names matching unions_master (sim >= 0.7)."""
    if not orphans:
        return {}
    cur.execute("""
        WITH orphan_names AS (
            SELECT DISTINCT ON (lm.f_num) lm.f_num, lm.union_name
            FROM lm_data lm
            WHERE lm.f_num = ANY(%s::text[])
              AND lm.union_name IS NOT NULL
            ORDER BY lm.f_num, lm.yr_covered DESC
        )
        SELECT bn.f_num::integer, bn.union_name,
               u.f_num AS match_fnum, u.union_name AS match_name,
               similarity(LOWER(bn.union_name), LOWER(u.union_name)) AS sim
        FROM orphan_names bn
        CROSS JOIN LATERAL (
            SELECT u2.f_num, u2.union_name
            FROM unions_master u2
            WHERE similarity(LOWER(bn.union_name), LOWER(u2.union_name)) >= 0.7
            ORDER BY similarity(LOWER(bn.union_name), LOWER(u2.union_name)) DESC
            LIMIT 1
        ) u
    """, ([str(f) for f in orphans],))
    return {r[0]: (r[2], r[3], r[4]) for r in cur.fetchall()}


def apply_name_match(cur, matches: Dict[int, Tuple[str, str, float]], dry_run: bool) -> int:
    """Remap orphan fnums to their name-matched unions_master entry."""
    count = 0
    for old_fnum, (new_fnum, name, sim) in sorted(matches.items()):
        if dry_run:
            cur.execute("""
                SELECT COUNT(*) FROM f7_union_employer_relations
                WHERE union_file_number = %s
            """, (old_fnum,))
            n = cur.fetchone()[0]
            print(f"  NAME_MATCH {old_fnum} -> {new_fnum} (sim={sim:.3f}, {n} rows) '{name[:40]}'")
            count += n
        else:
            cur.execute("""
                UPDATE f7_union_employer_relations
                SET union_file_number = %s
                WHERE union_file_number = %s
            """, (int(new_fnum), old_fnum))
            n = cur.rowcount
            print(f"  NAME_MATCH {old_fnum} -> {new_fnum} (sim={sim:.3f}, {n} rows updated)")
            count += n
    return count


# ============================================================================
# Category 4: ADD_MASTER (recent lm_data filings, add to unions_master)
# ============================================================================

def find_add_master_candidates(cur, orphans: List[int]) -> List[dict]:
    """Find orphans with recent lm_data (2020+) not in unions_master."""
    if not orphans:
        return []
    cur.execute("""
        SELECT DISTINCT ON (lm.f_num)
               lm.f_num::integer AS fnum,
               lm.union_name,
               lm.aff_abbr,
               lm.members,
               lm.yr_covered,
               lm.city,
               lm.state
        FROM lm_data lm
        WHERE lm.f_num = ANY(%s::text[])
          AND lm.yr_covered >= '2020'
          AND lm.union_name IS NOT NULL
        ORDER BY lm.f_num, lm.yr_covered DESC
    """, ([str(f) for f in orphans],))
    return [{"fnum": r[0], "union_name": r[1], "aff_abbr": r[2],
             "members": r[3], "yr_covered": r[4], "city": r[5], "state": r[6]}
            for r in cur.fetchall()]


def apply_add_master(cur, candidates: List[dict], dry_run: bool) -> int:
    """Insert missing unions into unions_master from lm_data."""
    count = 0
    for c in candidates:
        if dry_run:
            print(f"  ADD_MASTER fnum {c['fnum']}: '{c['union_name'][:40]}' "
                  f"({c['aff_abbr']}, {c['state']}, yr={c['yr_covered']})")
        else:
            cur.execute("""
                INSERT INTO unions_master (f_num, union_name, aff_abbr, members, yr_covered, city, state)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (f_num) DO NOTHING
            """, (str(c["fnum"]), c["union_name"], c["aff_abbr"],
                  c["members"], c["yr_covered"], c["city"], c["state"]))
            if cur.rowcount > 0:
                print(f"  ADD_MASTER fnum {c['fnum']}: inserted '{c['union_name'][:40]}'")
        count += 1
    return count


# ============================================================================
# Category 5: DISSOLVED (last filing before 2015)
# ============================================================================

def find_dissolved(cur, orphans: List[int]) -> List[Tuple[int, str]]:
    """Find orphans whose last lm_data filing was before 2015."""
    if not orphans:
        return []
    cur.execute("""
        SELECT lm.f_num::integer AS fnum,
               MAX(lm.yr_covered) AS last_year
        FROM lm_data lm
        WHERE lm.f_num = ANY(%s::text[])
        GROUP BY lm.f_num
        HAVING MAX(lm.yr_covered) < '2015'
    """, ([str(f) for f in orphans],))
    return [(r[0], r[1]) for r in cur.fetchall()]


# ============================================================================
# Category 6/7: DATA_QUALITY and INVESTIGATE
# ============================================================================

def categorize_remaining(
    cur,
    orphans: List[int],
    resolved: set,
) -> Tuple[List[int], List[int]]:
    """Split remaining orphans into DATA_QUALITY (no lm_data) and INVESTIGATE."""
    remaining = [f for f in orphans if f not in resolved]
    if not remaining:
        return [], []

    # Check which have lm_data
    cur.execute("""
        SELECT DISTINCT f_num::integer
        FROM lm_data
        WHERE f_num = ANY(%s::text[])
    """, ([str(f) for f in remaining],))
    with_lm = {r[0] for r in cur.fetchall()}

    data_quality = [f for f in remaining if f not in with_lm]
    investigate = [f for f in remaining if f in with_lm]
    return data_quality, investigate


# ============================================================================
# Resolution log
# ============================================================================

def ensure_log_table(cur) -> None:
    """Create the resolution log table if it doesn't exist."""
    cur.execute("""
        CREATE TABLE IF NOT EXISTS union_fnum_resolution_log (
            id SERIAL PRIMARY KEY,
            orphan_fnum INTEGER NOT NULL,
            category TEXT NOT NULL,
            target_fnum TEXT,
            detail TEXT,
            rows_affected INTEGER DEFAULT 0,
            workers_affected INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)


def log_resolution(
    cur,
    orphan_fnum: int,
    category: str,
    target_fnum: Optional[str],
    detail: str,
    rows_affected: int,
    workers_affected: int,
) -> None:
    cur.execute("""
        INSERT INTO union_fnum_resolution_log
            (orphan_fnum, category, target_fnum, detail, rows_affected, workers_affected)
        VALUES (%s, %s, %s, %s, %s, %s)
    """, (orphan_fnum, category, target_fnum, detail, rows_affected, workers_affected))


# ============================================================================
# Main
# ============================================================================

def run_diagnose(cur) -> None:
    """Print diagnostic summary (same as verify_missing_unions.py but briefer)."""
    orphans = get_orphan_fnums(cur)
    stats = get_orphan_stats(cur, orphans)
    total_rows = sum(s["rels"] for s in stats.values())
    total_workers = sum(s["workers"] for s in stats.values())

    print(f"\nDIAGNOSE: {len(orphans)} orphan fnums, {total_rows} rows, {total_workers:,} workers")

    remap = find_remap_candidates(cur, orphans)
    print(f"  REMAP candidates:      {len(remap)}")

    cwa_in = CWA_FNUM in orphans
    print(f"  CWA_GEO (12590):       {'YES' if cwa_in else 'NO (already resolved)'}")

    name_matches = find_name_matches(cur, [f for f in orphans if f not in remap and f != CWA_FNUM])
    print(f"  NAME_MATCH candidates: {len(name_matches)}")

    remaining = [f for f in orphans if f not in remap and f != CWA_FNUM and f not in name_matches]
    add_master = find_add_master_candidates(cur, remaining)
    print(f"  ADD_MASTER candidates: {len(add_master)}")

    remaining2 = [f for f in remaining if f not in {c["fnum"] for c in add_master}]
    dissolved = find_dissolved(cur, remaining2)
    print(f"  DISSOLVED candidates:  {len(dissolved)}")

    resolved_set = set(remap) | {CWA_FNUM} | set(name_matches) | {c["fnum"] for c in add_master} | {d[0] for d in dissolved}
    dq, inv = categorize_remaining(cur, orphans, resolved_set)
    print(f"  DATA_QUALITY:          {len(dq)}")
    print(f"  INVESTIGATE:           {len(inv)}")

    est_resolved = len(remap) + (1 if cwa_in else 0) + len(name_matches) + len(add_master)
    est_remaining = len(orphans) - est_resolved
    print(f"\n  Estimated resolved fnums: {est_resolved}")
    print(f"  Estimated remaining:      {est_remaining} (logged as DISSOLVED/DATA_QUALITY/INVESTIGATE)")


def run_resolution(cur, dry_run: bool) -> None:
    """Run the full resolution pipeline."""
    orphans = get_orphan_fnums(cur)
    stats = get_orphan_stats(cur, orphans)
    total_rows_before = get_total_relation_count(cur)
    total_workers = sum(s["workers"] for s in stats.values())

    mode = "DRY-RUN" if dry_run else "APPLY"
    print(f"\n{'=' * 70}")
    print(f"RESOLVE MISSING UNIONS ({mode})")
    print(f"{'=' * 70}")
    print(f"Before: {len(orphans)} orphan fnums, {sum(s['rels'] for s in stats.values())} rows, "
          f"{total_workers:,} workers")
    print(f"Total relation rows: {total_rows_before:,}")

    if not dry_run:
        ensure_log_table(cur)

    resolved = set()  # Track resolved fnums
    total_remapped_rows = 0

    # --- Category 1: REMAP ---
    print(f"\n--- Category 1: REMAP (crosswalk one-to-one) ---")
    remap = find_remap_candidates(cur, orphans)
    if remap:
        rows = apply_remap(cur, remap, dry_run)
        total_remapped_rows += rows
        if not dry_run:
            for old_fnum, new_fnum in remap.items():
                s = stats.get(old_fnum, {"rels": 0, "workers": 0})
                log_resolution(cur, old_fnum, "REMAP", new_fnum,
                               f"Crosswalk one-to-one remap to {new_fnum}",
                               s["rels"], s["workers"])
        resolved.update(remap.keys())
    else:
        print("  No candidates.")

    # --- Category 2: CWA_GEO ---
    print(f"\n--- Category 2: CWA_GEO (fnum 12590 geographic devolution) ---")
    if CWA_FNUM in orphans:
        rows = apply_cwa_geo(cur, dry_run)
        total_remapped_rows += rows
        if not dry_run and rows > 0:
            s = stats.get(CWA_FNUM, {"rels": 0, "workers": 0})
            log_resolution(cur, CWA_FNUM, "CWA_GEO", "multiple",
                           f"Geographic devolution to successor locals ({rows} rows)",
                           s["rels"], s["workers"])
        resolved.add(CWA_FNUM)
    else:
        print("  Fnum 12590 already resolved.")

    # --- Category 3: NAME_MATCH ---
    print(f"\n--- Category 3: NAME_MATCH (pg_trgm >= 0.7) ---")
    remaining_for_name = [f for f in orphans if f not in resolved]
    name_matches = find_name_matches(cur, remaining_for_name)
    if name_matches:
        rows = apply_name_match(cur, name_matches, dry_run)
        total_remapped_rows += rows
        if not dry_run:
            for old_fnum, (new_fnum, name, sim) in name_matches.items():
                s = stats.get(old_fnum, {"rels": 0, "workers": 0})
                log_resolution(cur, old_fnum, "NAME_MATCH", new_fnum,
                               f"pg_trgm match (sim={sim:.3f}) to '{name[:50]}'",
                               s["rels"], s["workers"])
        resolved.update(name_matches.keys())
    else:
        print("  No candidates (orphan fnums have no lm_data names to match).")

    # --- Category 4: ADD_MASTER ---
    print(f"\n--- Category 4: ADD_MASTER (recent lm_data, add to unions_master) ---")
    remaining_for_add = [f for f in orphans if f not in resolved]
    add_candidates = find_add_master_candidates(cur, remaining_for_add)
    if add_candidates:
        n = apply_add_master(cur, add_candidates, dry_run)
        if not dry_run:
            for c in add_candidates:
                log_resolution(cur, c["fnum"], "ADD_MASTER", str(c["fnum"]),
                               f"Added to unions_master: '{c['union_name'][:50]}' ({c['yr_covered']})",
                               0, 0)
        resolved.update(c["fnum"] for c in add_candidates)
        print(f"  {n} unions added to unions_master.")
    else:
        print("  No candidates (no orphan fnums have recent lm_data filings).")

    # --- Category 5: DISSOLVED ---
    print(f"\n--- Category 5: DISSOLVED (last filing before 2015) ---")
    remaining_for_dissolved = [f for f in orphans if f not in resolved]
    dissolved = find_dissolved(cur, remaining_for_dissolved)
    if dissolved:
        for fnum, last_year in dissolved:
            print(f"  DISSOLVED fnum {fnum}: last filing {last_year}")
            if not dry_run:
                s = stats.get(fnum, {"rels": 0, "workers": 0})
                log_resolution(cur, fnum, "DISSOLVED", None,
                               f"Last lm_data filing: {last_year}",
                               s["rels"], s["workers"])
        resolved.update(d[0] for d in dissolved)
    else:
        print("  No candidates.")

    # --- Categories 6 & 7: DATA_QUALITY and INVESTIGATE ---
    dq, investigate = categorize_remaining(cur, orphans, resolved)

    print(f"\n--- Category 6: DATA_QUALITY (no lm_data history) ---")
    if dq:
        print(f"  {len(dq)} fnums with no lm_data history.")
        if not dry_run:
            for fnum in dq:
                s = stats.get(fnum, {"rels": 0, "workers": 0})
                log_resolution(cur, fnum, "DATA_QUALITY", None,
                               "No lm_data filing history found",
                               s["rels"], s["workers"])
    else:
        print("  None.")

    print(f"\n--- Category 7: INVESTIGATE (has lm_data but unresolved) ---")
    if investigate:
        print(f"  {len(investigate)} fnums need manual investigation:")
        for fnum in investigate:
            s = stats.get(fnum, {"rels": 0, "workers": 0})
            url = f"https://olmsapps.dol.gov/query/orgReport.do?rptId=&rptForm=&fileNum={fnum}"
            print(f"    fnum {fnum}: {s['rels']} rels, {s['workers']:,} workers  {url}")
            if not dry_run:
                log_resolution(cur, fnum, "INVESTIGATE", None,
                               f"OLMS lookup: {url}",
                               s["rels"], s["workers"])
    else:
        print("  None.")

    # --- Summary ---
    print(f"\n{'=' * 70}")
    print(f"SUMMARY ({mode})")
    print(f"{'=' * 70}")

    cat_counts = {
        "REMAP": len(remap),
        "CWA_GEO": 1 if CWA_FNUM in orphans else 0,
        "NAME_MATCH": len(name_matches),
        "ADD_MASTER": len(add_candidates),
        "DISSOLVED": len(dissolved),
        "DATA_QUALITY": len(dq),
        "INVESTIGATE": len(investigate),
    }
    for cat, cnt in cat_counts.items():
        print(f"  {cat:15s}: {cnt:>4} fnums")

    active_resolved = len(remap) + (1 if CWA_FNUM in orphans else 0) + len(name_matches) + len(add_candidates)
    print(f"\n  Actively resolved (remapped/added): {active_resolved} fnums")
    print(f"  Logged only (dissolved/dq/investigate): {len(dissolved) + len(dq) + len(investigate)} fnums")
    print(f"  Total rows remapped: {total_remapped_rows}")

    if not dry_run:
        # Verify final state
        post_orphans = get_orphan_fnums(cur)
        post_total = get_total_relation_count(cur)
        print(f"\n  Post-resolution orphan fnums: {len(post_orphans)}")
        print(f"  Total relation rows (before): {total_rows_before:,}")
        print(f"  Total relation rows (after):  {post_total:,}")
        if total_rows_before != post_total:
            print(f"  WARNING: Row count changed by {post_total - total_rows_before}!")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Resolve orphaned union file numbers in f7_union_employer_relations"
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--diagnose", action="store_true",
                       help="Print diagnostic summary without any changes")
    group.add_argument("--dry-run", action="store_true",
                       help="Show planned changes without writing")
    group.add_argument("--apply", action="store_true",
                       help="Apply all resolutions in a transaction")
    args = parser.parse_args()

    conn = get_connection()
    conn.autocommit = False

    try:
        with conn.cursor() as cur:
            if args.diagnose:
                run_diagnose(cur)
                conn.rollback()
            elif args.dry_run:
                run_resolution(cur, dry_run=True)
                conn.rollback()
                print("\nDry-run complete. No changes were written.")
            else:
                run_resolution(cur, dry_run=False)
                conn.commit()
                print("\nResolution complete. Transaction committed.")
    except Exception as exc:
        conn.rollback()
        print(f"\nERROR: {exc}")
        print("Rolled back transaction.")
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    main()
