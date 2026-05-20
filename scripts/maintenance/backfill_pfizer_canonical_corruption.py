"""Back-fill the Mergent normalize_name() str.replace corruption.

Bug (2026-05-03 .. 2026-05-18): scripts/etl/load_mergent_universal.py and
load_mergent_al_fl.py used str.replace() with no word boundaries on a
list of legal suffixes, iterating shorter-first. " corp" matched the leading
space + "corp" inside " corporation", leaving "oration" glued to the prior
token. Same trick with " co" eating into " company" -> "mpany", and " inc"
into " incorporated" -> "orporated". ~19,140 master_employers rows and
~20,297 mergent_employers rows got corrupted. The fix landed 2026-05-18;
this script repairs the in-DB damage.

Approach (per-row reproducibility):
  1. Find candidate corrupt rows via a broad signature regex (oration/mpany/
     orporated endings).
  2. For each candidate, run the *original buggy* normalize_name() against
     `display_name` (preserved verbatim) and check if the buggy output
     equals the current `canonical_name`. If yes, this row was corrupted
     by the bug (high confidence). If no, the canonical came from a
     different path -- leave it alone.
  3. Re-compute the correct canonical via the new
     normalize_name_legal_suffixes_only() and emit a CSV preview row.
  4. With --commit, UPDATE master_employers.canonical_name and
     mergent_employers.company_name_normalized in a single transaction.

Safety:
  - Default is preview-only (NO --commit). Writes a CSV to
    files/pfizer_backfill_preview/<timestamp>.csv with master_id / old / new.
  - With --commit: hard-coded refusal if any of the 3 critical MVs
    (mv_unified_scorecard / mv_target_scorecard / mv_employer_search) is
    missing. Caller must rebuild MVs first.
  - With --commit: bails (ROLLBACK) if the post-fix dedup-merge candidate
    count exceeds --max-dedup-candidates (default 1000). The dedup-merge
    step itself is OUT OF SCOPE for this script and is a separate
    follow-up. We just refuse to leave the DB with > 1000 newly-colliding
    canonical_name rows.

Usage:
  # Preview only (safe, writes CSV, no DB writes):
  py scripts/maintenance/backfill_pfizer_canonical_corruption.py

  # Commit (DESTRUCTIVE — only run after preview review + MV check):
  py scripts/maintenance/backfill_pfizer_canonical_corruption.py --commit

  # Tighter sanity guard:
  py scripts/maintenance/backfill_pfizer_canonical_corruption.py --commit \\
    --max-dedup-candidates 500

Exit codes:
  0  Preview succeeded OR commit succeeded.
  1  Critical MV missing (refusing to run).
  2  Dedup-candidate count exceeded threshold (rolled back).
  3  DB connection or query error.

See: Open Problems/Pfizer Master Canonical Name Corruption.md
"""
import argparse
import csv
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))


# ============================================================================
# Bug reproduction (verbatim copy of the buggy normalize_name)
# ============================================================================
# This is INTENTIONALLY a verbatim copy of the buggy implementation so that
# we can per-row confirm which DB rows were the bug's victims. DO NOT FIX.

def _buggy_normalize_name_for_per_row_check(name):
    """Verbatim copy of the pre-fix load_mergent_universal.normalize_name.

    Used to confirm a row was corrupted by the bug (per-row reproducibility
    check). Same logic as load_mergent_al_fl with `'` instead of `"`.
    """
    if not name:
        return None
    name = str(name).lower().strip()
    for suffix in [" llc", " inc", " corp", " ltd", " co", " company",
                   " corporation", " incorporated", " limited",
                   ".", ",", '"', "'", " the"]:
        name = name.replace(suffix, "")
    name = re.sub(r"\s+", " ", name).strip()
    return name


# ============================================================================
# Candidate selection (broad signature regex)
# ============================================================================

# Matches any of the bug-signature endings:
#   *oration  (not preceded by 'c' -- otherwise matches "corporation")
#   *mpany    (not "company")
#   *orporated (not preceded by 'c' -- otherwise matches "incorporated")
# This is the SEARCH regex (cast a wide net). Per-row reproducibility
# narrows to actual victims.
CANDIDATE_REGEX_PG = r"(?<![c])oration$|(?<![p])mpany$|(?<![c])orporated$"

CRITICAL_MVS = ("mv_unified_scorecard", "mv_target_scorecard", "mv_employer_search")


# ============================================================================
# Helpers
# ============================================================================

def _check_critical_mvs(cur):
    """Return list of missing critical MVs (empty list = all present)."""
    cur.execute(
        "SELECT matviewname FROM pg_matviews "
        "WHERE schemaname = 'public' AND matviewname = ANY(%s)",
        (list(CRITICAL_MVS),),
    )
    present = {r[0] for r in cur.fetchall()}
    return [m for m in CRITICAL_MVS if m not in present]


def _fix_one(display_name):
    """Return the corrected canonical for a row."""
    from src.python.matching.name_normalization import (
        normalize_name_legal_suffixes_only,
    )
    return normalize_name_legal_suffixes_only(display_name)


def _is_bug_victim(display_name, canonical_name):
    """Per-row reproducibility: True iff the bug fully accounts for canonical."""
    buggy = _buggy_normalize_name_for_per_row_check(display_name)
    if buggy is None or canonical_name is None:
        return False
    return buggy == canonical_name


# ============================================================================
# Main back-fill logic
# ============================================================================

def collect_master_candidates(cur):
    """Yield (master_id, display_name, canonical_name) for candidate rows."""
    cur.execute(
        "SELECT master_id, display_name, canonical_name "
        "FROM master_employers "
        "WHERE canonical_name ~ %s "
        "ORDER BY master_id",
        (CANDIDATE_REGEX_PG,),
    )
    for master_id, display_name, canonical_name in cur.fetchall():
        yield master_id, display_name, canonical_name


def collect_mergent_candidates(cur):
    """Yield (id, company_name, company_name_normalized) for candidate rows."""
    cur.execute(
        "SELECT id, company_name, company_name_normalized "
        "FROM mergent_employers "
        "WHERE company_name_normalized ~ %s "
        "ORDER BY id",
        (CANDIDATE_REGEX_PG,),
    )
    for rid, company_name, company_name_normalized in cur.fetchall():
        yield rid, company_name, company_name_normalized


def build_master_plan(cur, log):
    """Return list of (master_id, display_name, old_canonical, new_canonical)."""
    plan = []
    not_a_victim = 0
    already_correct = 0
    skipped_empty = 0
    examined = 0
    for master_id, display_name, canonical_name in collect_master_candidates(cur):
        examined += 1
        if not _is_bug_victim(display_name, canonical_name):
            not_a_victim += 1
            continue
        new_canonical = _fix_one(display_name)
        if new_canonical == canonical_name:
            already_correct += 1
            continue
        if not new_canonical:
            # Don't replace a wrong-but-non-empty canonical with empty. The row
            # is a junk master (e.g. display_name == "COMPANY"); a separate
            # cleanup should delete or quarantine it.
            skipped_empty += 1
            continue
        plan.append((master_id, display_name, canonical_name, new_canonical))
    log(f"  master_employers: examined {examined:,} candidate rows")
    log(f"    skipped (not bug victim): {not_a_victim:,}")
    log(f"    skipped (already correct): {already_correct:,}")
    log(f"    skipped (new canonical empty): {skipped_empty:,}")
    log(f"    actionable: {len(plan):,}")
    return plan


def build_mergent_plan(cur, log):
    """Return list of (id, company_name, old_normalized, new_normalized)."""
    plan = []
    not_a_victim = 0
    already_correct = 0
    skipped_empty = 0
    examined = 0
    for rid, company_name, company_name_normalized in collect_mergent_candidates(cur):
        examined += 1
        if not _is_bug_victim(company_name, company_name_normalized):
            not_a_victim += 1
            continue
        new_normalized = _fix_one(company_name)
        if new_normalized == company_name_normalized:
            already_correct += 1
            continue
        if not new_normalized:
            skipped_empty += 1
            continue
        plan.append((rid, company_name, company_name_normalized, new_normalized))
    log(f"  mergent_employers: examined {examined:,} candidate rows")
    log(f"    skipped (not bug victim): {not_a_victim:,}")
    log(f"    skipped (already correct): {already_correct:,}")
    log(f"    skipped (new canonical empty): {skipped_empty:,}")
    log(f"    actionable: {len(plan):,}")
    return plan


def write_preview_csvs(master_plan, mergent_plan, output_dir):
    """Write master + mergent CSV previews. Returns (master_path, mergent_path)."""
    output_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    master_path = output_dir / f"master_employers_backfill_{ts}.csv"
    with master_path.open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["master_id", "display_name", "old_canonical_name", "new_canonical_name"])
        for row in master_plan:
            w.writerow(row)

    mergent_path = output_dir / f"mergent_employers_backfill_{ts}.csv"
    with mergent_path.open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["id", "company_name", "old_company_name_normalized",
                    "new_company_name_normalized"])
        for row in mergent_plan:
            w.writerow(row)

    return master_path, mergent_path


def estimate_dedup_candidates(cur, master_plan):
    """Count master rows whose NEW canonical would collide with an EXISTING row.

    A collision is (new_canonical, state, city) matching another row's
    (canonical_name, state, city). High collision counts indicate the
    back-fill would create silent dupes that need a merge step (out of
    scope for this script).
    """
    if not master_plan:
        return 0
    # Build a temp tuple list of (new_canonical, master_id) and check for
    # matches against other (different) master rows.
    cur.execute(
        "CREATE TEMP TABLE IF NOT EXISTS _pfizer_backfill_plan "
        "(master_id BIGINT, new_canonical TEXT) ON COMMIT DROP"
    )
    cur.execute("TRUNCATE _pfizer_backfill_plan")
    from psycopg2.extras import execute_values
    execute_values(
        cur,
        "INSERT INTO _pfizer_backfill_plan (master_id, new_canonical) VALUES %s",
        [(mid, new) for (mid, _disp, _old, new) in master_plan],
    )
    cur.execute(
        "SELECT COUNT(*) FROM _pfizer_backfill_plan p "
        "JOIN master_employers m "
        "  ON m.canonical_name = p.new_canonical "
        " AND m.master_id <> p.master_id"
    )
    return cur.fetchone()[0]


def commit_master(cur, master_plan, log):
    if not master_plan:
        log("  master_employers: no updates")
        return 0
    from psycopg2.extras import execute_values
    log(f"  master_employers: UPDATEing {len(master_plan):,} rows")
    cur.execute(
        "CREATE TEMP TABLE IF NOT EXISTS _pfizer_backfill_master "
        "(master_id BIGINT PRIMARY KEY, new_canonical TEXT) ON COMMIT DROP"
    )
    cur.execute("TRUNCATE _pfizer_backfill_master")
    execute_values(
        cur,
        "INSERT INTO _pfizer_backfill_master (master_id, new_canonical) VALUES %s",
        [(mid, new) for (mid, _d, _old, new) in master_plan],
    )
    cur.execute(
        "UPDATE master_employers m "
        "SET canonical_name = p.new_canonical, updated_at = NOW() "
        "FROM _pfizer_backfill_master p "
        "WHERE m.master_id = p.master_id"
    )
    return cur.rowcount


def commit_mergent(cur, mergent_plan, log):
    if not mergent_plan:
        log("  mergent_employers: no updates")
        return 0
    from psycopg2.extras import execute_values
    log(f"  mergent_employers: UPDATEing {len(mergent_plan):,} rows")
    cur.execute(
        "CREATE TEMP TABLE IF NOT EXISTS _pfizer_backfill_mergent "
        "(id INTEGER PRIMARY KEY, new_normalized TEXT) ON COMMIT DROP"
    )
    cur.execute("TRUNCATE _pfizer_backfill_mergent")
    execute_values(
        cur,
        "INSERT INTO _pfizer_backfill_mergent (id, new_normalized) VALUES %s",
        [(rid, new) for (rid, _c, _old, new) in mergent_plan],
    )
    cur.execute(
        "UPDATE mergent_employers e "
        "SET company_name_normalized = p.new_normalized "
        "FROM _pfizer_backfill_mergent p "
        "WHERE e.id = p.id"
    )
    return cur.rowcount


# ============================================================================
# Bundled-mode helpers (Phase C of pfizer_dedup_bundle_plan_2026_05_20)
# ============================================================================

# Arbitrary integer; pg_advisory_lock acquires across the whole session.
BUNDLED_ADVISORY_LOCK_ID = 18052026

PFIZER_BUNDLED_PHASE = "pfizer_bundled"


def _acquire_advisory_lock(cur):
    """Acquire pg_advisory_lock so two bundled migrations can't run concurrently.

    Released on session close / explicit unlock.
    """
    cur.execute("SELECT pg_try_advisory_lock(%s)", (BUNDLED_ADVISORY_LOCK_ID,))
    got = bool(cur.fetchone()[0])
    if not got:
        raise RuntimeError(
            f"Could not acquire pg_advisory_lock({BUNDLED_ADVISORY_LOCK_ID}). "
            "Another bundled migration may be running."
        )


def _set_timeouts_bundled(cur):
    """Generous timeouts for the bundled run (~10K merge_one calls)."""
    cur.execute("SET lock_timeout = '5min'")
    cur.execute("SET statement_timeout = '30min'")
    cur.execute("SET idle_in_transaction_session_timeout = '30min'")


def _stage_plan_temp_tables(cur, master_plan, mergent_plan):
    """Create + populate _pfizer_backfill_master / _pfizer_backfill_mergent temp tables.

    These persist for the lifetime of the txn so downstream SQL (collision-graph
    materialization, commit_master/commit_mergent UPDATEs) can JOIN against them.
    """
    from psycopg2.extras import execute_values
    cur.execute(
        "CREATE TEMP TABLE _pfizer_backfill_master "
        "(master_id BIGINT PRIMARY KEY, new_canonical TEXT) ON COMMIT DROP"
    )
    if master_plan:
        execute_values(
            cur,
            "INSERT INTO _pfizer_backfill_master (master_id, new_canonical) VALUES %s",
            [(mid, new) for (mid, _d, _old, new) in master_plan],
        )
    cur.execute(
        "CREATE TEMP TABLE _pfizer_backfill_mergent "
        "(id INTEGER PRIMARY KEY, new_normalized TEXT) ON COMMIT DROP"
    )
    if mergent_plan:
        execute_values(
            cur,
            "INSERT INTO _pfizer_backfill_mergent (id, new_normalized) VALUES %s",
            [(rid, new) for (rid, _c, _old, new) in mergent_plan],
        )


def _materialize_collision_groups(cur):
    """Build _post_fix_view + _collision_groups temp tables.

    A collision group is a (post_canonical, state, city) tuple with >=2
    master rows, where at least one row is in the back-fill plan. Returns
    the row count of _collision_groups.
    """
    cur.execute("DROP TABLE IF EXISTS _post_fix_view")
    cur.execute(
        """
        CREATE TEMP TABLE _post_fix_view AS
        SELECT m.master_id,
               COALESCE(p.new_canonical, m.canonical_name) AS post_canonical,
               m.state::TEXT AS state,
               m.city,
               m.source_origin,
               EXISTS (
                   SELECT 1 FROM master_employer_source_ids sid
                   WHERE sid.master_id = m.master_id AND sid.source_system = 'f7'
               ) AS has_f7
        FROM master_employers m
        LEFT JOIN _pfizer_backfill_master p USING (master_id)
        """
    )
    cur.execute("CREATE INDEX ON _post_fix_view (post_canonical, state, city)")
    cur.execute("DROP TABLE IF EXISTS _collision_groups")
    cur.execute(
        """
        CREATE TEMP TABLE _collision_groups AS
        SELECT post_canonical, state, city,
               array_agg(master_id ORDER BY master_id) AS ids
        FROM _post_fix_view
        WHERE post_canonical IS NOT NULL AND btrim(post_canonical) <> ''
          AND state IS NOT NULL
        GROUP BY post_canonical, state, city
        HAVING COUNT(*) >= 2
           AND COUNT(*) FILTER (
               WHERE master_id IN (SELECT master_id FROM _pfizer_backfill_master)
           ) >= 1
        """
    )
    cur.execute("SELECT COUNT(*) FROM _collision_groups")
    return int(cur.fetchone()[0])


def _pick_winners_for_groups(cur, ctx, log):
    """Walk _collision_groups; for each group pick one terminal winner via
    Employer.rank(); enumerate losers; skip f7-vs-f7 + id-conflict pairs.

    Returns (winner_map: dict[loser_mid, winner_mid], skipped_id_conflicts:
    list of (loser_mid, winner_mid, field, loser_value, winner_value),
    skipped_f7_vs_f7: int).
    """
    from src.python.matching.master_dedup import fetch_employers, has_id_conflict

    cur.execute("SELECT post_canonical, state, city, ids FROM _collision_groups")
    groups = cur.fetchall()
    winner_map: dict[int, int] = {}
    skipped_id_conflicts: list[tuple] = []
    skipped_f7_vs_f7 = 0

    # Batch-fetch all unique mids across all groups to avoid N round-trips.
    all_mids = sorted({m for _pc, _s, _c, ids in groups for m in ids})
    emps = {e.mid: e for e in fetch_employers(cur, ctx, all_mids)}

    for _pc, _state, _city, ids in groups:
        rows = [emps[m] for m in ids if m in emps]
        if len(rows) < 2:
            continue
        rows.sort(key=lambda x: x.rank())
        winner = rows[0]
        for loser in rows[1:]:
            if loser.mid == winner.mid:
                continue
            if winner.has_f7 and loser.has_f7:
                skipped_f7_vs_f7 += 1
                continue
            conflict_field = has_id_conflict(winner, loser)
            if conflict_field is not None:
                skipped_id_conflicts.append((
                    loser.mid, winner.mid, conflict_field,
                    getattr(loser, conflict_field, None),
                    getattr(winner, conflict_field, None),
                ))
                continue
            # Star-topology: every loser in the group points at the SAME winner.
            # If a loser was already assigned (group overlap), keep first.
            if loser.mid in winner_map:
                continue
            winner_map[loser.mid] = winner.mid

    log(f"  winner map: {len(winner_map):,} loser->winner pairs")
    log(f"  skipped (f7 vs f7): {skipped_f7_vs_f7:,}")
    log(f"  skipped (id conflict): {len(skipped_id_conflicts):,}")
    return winner_map, skipped_id_conflicts, skipped_f7_vs_f7


def _write_winner_map_table(cur, winner_map):
    """Persist winner_map to a temp table `_winner_map` (loser_master_id,
    winner_master_id BIGINT) for use by bulk_repoint().
    """
    from psycopg2.extras import execute_values
    cur.execute("DROP TABLE IF EXISTS _winner_map")
    cur.execute(
        "CREATE TEMP TABLE _winner_map "
        "(loser_master_id BIGINT PRIMARY KEY, winner_master_id BIGINT NOT NULL)"
    )
    if winner_map:
        execute_values(
            cur,
            "INSERT INTO _winner_map (loser_master_id, winner_master_id) VALUES %s",
            list(winner_map.items()),
        )
    cur.execute("CREATE INDEX ON _winner_map (winner_master_id)")


def _persist_skipped_id_conflicts(cur, ts, skipped):
    """Persist id-conflict skips to a permanent audit table
    `pfizer_skipped_id_conflicts_<TS>` so a human can review post-commit.
    """
    if not skipped:
        return None
    tbl = f"pfizer_skipped_id_conflicts_{ts}"
    cur.execute(
        f'CREATE TABLE "{tbl}" ('
        "  loser_master_id BIGINT, winner_master_id BIGINT,"
        "  conflict_field TEXT, loser_value TEXT, winner_value TEXT)"
    )
    from psycopg2.extras import execute_values
    execute_values(
        cur,
        f'INSERT INTO "{tbl}" '
        "(loser_master_id, winner_master_id, conflict_field, loser_value, winner_value) VALUES %s",
        [(l, w, f, str(lv) if lv is not None else None, str(wv) if wv is not None else None)
         for (l, w, f, lv, wv) in skipped],
    )
    return tbl


def validate_merge_map(cur, winner_map):
    """Fail fast if the winner_map has structural problems.

    Checks:
      - no self-merge (loser == winner)
      - no master_id appears as both winner and loser (no A->B->C chains)
      - every winner exists in master_employers
      - every loser exists in master_employers
    """
    for loser, winner in winner_map.items():
        if loser == winner:
            raise RuntimeError(f"validate_merge_map: self-merge for master_id={loser}")
    losers = set(winner_map.keys())
    winners = set(winner_map.values())
    both = losers & winners
    if both:
        raise RuntimeError(
            f"validate_merge_map: {len(both):,} master_ids appear as BOTH winner and "
            f"loser (chain risk). Sample: {sorted(both)[:5]}"
        )
    all_mids = list(losers | winners)
    if not all_mids:
        return
    cur.execute(
        "SELECT master_id FROM master_employers WHERE master_id = ANY(%s)",
        (all_mids,),
    )
    present = {r[0] for r in cur.fetchall()}
    missing = [m for m in all_mids if m not in present]
    if missing:
        raise RuntimeError(
            f"validate_merge_map: {len(missing):,} master_ids in winner_map do not "
            f"exist in master_employers. Sample: {missing[:5]}"
        )


def _create_snapshot_tables(cur, ts, log):
    """Persist a snapshot of the affected master/source/mergent rows BEFORE
    mutation. Tables survive the txn (committed-only); drop after next /ship.
    """
    master_tbl = f"backfill_pfizer_pre_{ts}"
    source_tbl = f"backfill_pfizer_source_ids_pre_{ts}"
    mergent_tbl = f"backfill_pfizer_mergent_pre_{ts}"
    cur.execute(
        f'CREATE TABLE "{master_tbl}" AS '
        "SELECT m.* FROM master_employers m "
        "WHERE m.master_id IN ("
        "  SELECT master_id FROM _pfizer_backfill_master"
        "  UNION SELECT loser_master_id FROM _winner_map"
        "  UNION SELECT winner_master_id FROM _winner_map)"
    )
    log(f"  snapshot: {master_tbl} ({cur.rowcount:,} rows)")
    cur.execute(
        f'CREATE TABLE "{source_tbl}" AS '
        "SELECT * FROM master_employer_source_ids "
        "WHERE master_id IN ("
        "  SELECT loser_master_id FROM _winner_map"
        "  UNION SELECT winner_master_id FROM _winner_map)"
    )
    log(f"  snapshot: {source_tbl} ({cur.rowcount:,} rows)")
    cur.execute(
        f'CREATE TABLE "{mergent_tbl}" AS '
        "SELECT * FROM mergent_employers "
        "WHERE id IN (SELECT id FROM _pfizer_backfill_mergent)"
    )
    log(f"  snapshot: {mergent_tbl} ({cur.rowcount:,} rows)")
    return [master_tbl, source_tbl, mergent_tbl]


def _verify_checksum_unchanged(cur, master_plan):
    """Abort if any planned master row has changed since the plan was built.

    Compares plan's (master_id, display_name, current canonical) against the
    live row. If display_name or canonical_name shifted, someone else is
    writing — bail to avoid clobbering.
    """
    if not master_plan:
        return
    mids = [mid for (mid, *_rest) in master_plan]
    plan_by_mid = {mid: (disp, old) for (mid, disp, old, _new) in master_plan}
    cur.execute(
        "SELECT master_id, display_name, canonical_name "
        "FROM master_employers WHERE master_id = ANY(%s)",
        (mids,),
    )
    shifted = []
    for mid, live_disp, live_canon in cur.fetchall():
        plan_disp, plan_canon = plan_by_mid.get(mid, (None, None))
        if live_disp != plan_disp or live_canon != plan_canon:
            shifted.append(mid)
    if shifted:
        raise RuntimeError(
            f"_verify_checksum_unchanged: {len(shifted):,} master rows shifted "
            f"between plan-build and commit. Sample: {shifted[:5]}. Re-run preview."
        )


def _lock_affected_rows_for_update(cur):
    """SELECT FOR UPDATE on every master row we're about to touch, in
    deterministic order to avoid deadlocks with concurrent writers."""
    cur.execute(
        "SELECT master_id FROM master_employers "
        "WHERE master_id IN ("
        "  SELECT master_id FROM _pfizer_backfill_master"
        "  UNION SELECT loser_master_id FROM _winner_map"
        "  UNION SELECT winner_master_id FROM _winner_map) "
        "ORDER BY master_id FOR UPDATE"
    )
    return cur.rowcount


def _ensure_migration_audit_table(cur):
    """Create the persistent maintenance-audit table if it doesn't exist."""
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS maintenance_migration_audit (
          migration_name TEXT PRIMARY KEY,
          counts JSONB,
          checksum TEXT,
          started_at TIMESTAMPTZ,
          completed_at TIMESTAMPTZ,
          notes TEXT
        )
        """
    )


def _insert_migration_audit_row(cur, name, counts, started_at, completed_at):
    """Record one row in maintenance_migration_audit."""
    import json
    cur.execute(
        """
        INSERT INTO maintenance_migration_audit
          (migration_name, counts, started_at, completed_at)
        VALUES (%s, %s::jsonb, %s, %s)
        ON CONFLICT (migration_name) DO UPDATE
        SET counts = EXCLUDED.counts,
            completed_at = EXCLUDED.completed_at
        """,
        (name, json.dumps(counts), started_at, completed_at),
    )


def _run_verification_ladder(cur, master_plan, mergent_plan, winner_map,
                              merge_log_baseline_id, audit_name, log):
    """In-txn pre-commit checks. Returns dict; 'all_pass' is False if any failed.

    V1/V2 use a plan-relative check (rows in the plan whose canonical_name
    still differs from the planned new value) rather than a regex against
    the full table. The corruption regex has false-positives for legitimate
    -oration words (restoration / collaboration / etc.) and the "not-company"
    lookbehind doesn't actually exclude "company" — the char before "mpany"
    in "company" is "o", not "p".

    V4 counts master_employer_merge_log rows with merge_id > the baseline
    captured immediately before the merge_one loop, scoped to merge_phase
    = PFIZER_BUNDLED_PHASE. This avoids the Postgres NOW()-is-frozen-in-txn
    pitfall that caused the time-based filter to always return 0.
    """
    results = {}

    # V1: every row in the master plan now holds the planned new_canonical.
    cur.execute(
        "SELECT COUNT(*) FROM _pfizer_backfill_master p "
        "JOIN master_employers m ON m.master_id = p.master_id "
        "WHERE m.canonical_name IS DISTINCT FROM p.new_canonical"
    )
    n = int(cur.fetchone()[0])
    results["V1_master_plan_applied"] = (n == 0, f"{n} rows still on old canonical")

    # V2: every row in the mergent plan now holds the planned new_normalized.
    cur.execute(
        "SELECT COUNT(*) FROM _pfizer_backfill_mergent p "
        "JOIN mergent_employers e ON e.id = p.id "
        "WHERE e.company_name_normalized IS DISTINCT FROM p.new_normalized"
    )
    n = int(cur.fetchone()[0])
    results["V2_mergent_plan_applied"] = (n == 0, f"{n} rows still on old normalized")

    # V3: loser FK orphans = 0 (for declared FKs)
    cur.execute(
        """
        SELECT (SELECT COUNT(*) FROM employer_directors d
                WHERE d.master_id IS NOT NULL
                  AND NOT EXISTS (SELECT 1 FROM master_employers m
                                   WHERE m.master_id = d.master_id)),
               (SELECT COUNT(*) FROM master_employer_source_ids s
                WHERE NOT EXISTS (SELECT 1 FROM master_employers m
                                   WHERE m.master_id = s.master_id))
        """
    )
    orphan_directors, orphan_sources = cur.fetchone()
    results["V3_orphan_directors"] = (orphan_directors == 0, orphan_directors)
    results["V3_orphan_source_ids"] = (orphan_sources == 0, orphan_sources)

    # V4: merge_log delta uses a captured baseline merge_id, not a time filter.
    cur.execute(
        "SELECT COUNT(*) FROM master_employer_merge_log "
        "WHERE merge_id > %s AND merge_phase = %s",
        (merge_log_baseline_id, PFIZER_BUNDLED_PHASE),
    )
    log_count = int(cur.fetchone()[0])
    expected = len(winner_map)
    results["V4_merge_log_count"] = (log_count == expected,
                                      f"{log_count} vs expected {expected}")

    # V5: every merge_log row points at a winner that exists in master_employers
    # (and the loser does NOT exist anymore).
    cur.execute(
        """
        SELECT COUNT(*) FROM master_employer_merge_log mml
        WHERE mml.merge_id > %s AND mml.merge_phase = %s
          AND (NOT EXISTS (SELECT 1 FROM master_employers w
                            WHERE w.master_id = mml.winner_master_id)
               OR EXISTS (SELECT 1 FROM master_employers l
                          WHERE l.master_id = mml.loser_master_id))
        """,
        (merge_log_baseline_id, PFIZER_BUNDLED_PHASE),
    )
    bad = int(cur.fetchone()[0])
    results["V5_merge_log_pointers_clean"] = (bad == 0,
                                                f"{bad} bad winner/loser refs")

    # V6: audit row inserted with completed_at set
    cur.execute(
        "SELECT completed_at IS NOT NULL FROM maintenance_migration_audit "
        "WHERE migration_name = %s",
        (audit_name,),
    )
    row = cur.fetchone()
    results["V6_audit_row_present"] = ((row is not None and bool(row[0])), row)

    all_pass = all(v[0] for v in results.values())
    results["all_pass"] = all_pass
    for k, v in results.items():
        if k == "all_pass":
            continue
        status = "PASS" if v[0] else "FAIL"
        log(f"  {k}: {status} ({v[1]})")
    return results


def run_bundled(conn, ctx, master_plan, mergent_plan, ts, log):
    """Bundled --commit flow: back-fill canonicals + dedup-merge in ONE txn.

    Caller MUST set conn.autocommit = False before calling. Caller commits on
    success; we raise on failure (caller rolls back).
    """
    from datetime import datetime, timezone
    started = datetime.now(timezone.utc)
    audit_name = f"pfizer_bundled_{ts}"

    with conn.cursor() as cur:
        _acquire_advisory_lock(cur)
        _set_timeouts_bundled(cur)
        _ensure_migration_audit_table(cur)
        _stage_plan_temp_tables(cur, master_plan, mergent_plan)
        collision_count = _materialize_collision_groups(cur)
        log(f"  collision groups: {collision_count:,}")
        winner_map, skipped_id_conflicts, skipped_f7 = _pick_winners_for_groups(cur, ctx, log)
        _write_winner_map_table(cur, winner_map)
        skip_tbl = _persist_skipped_id_conflicts(cur, ts, skipped_id_conflicts)
        if skip_tbl:
            log(f"  id-conflict skips persisted to: {skip_tbl}")
        validate_merge_map(cur, winner_map)
        log("  merge map validated (no self-merges, no chains, all rows exist)")
        _verify_checksum_unchanged(cur, master_plan)
        log("  checksum verified (no rows shifted since preview)")
        snapshot_tables = _create_snapshot_tables(cur, ts, log)
        locked = _lock_affected_rows_for_update(cur)
        log(f"  acquired row locks on {locked:,} master rows")

        from src.python.matching.master_dedup import bulk_repoint, fetch_employers, merge_one
        repoint_counts = bulk_repoint(cur)
        log(f"  bulk_repoint: {repoint_counts}")

        # Capture max merge_id BEFORE the loop so V4/V5 can count just-this-run
        # rows without relying on a time filter (Postgres NOW() is frozen at
        # txn start, so a Python now()-based filter is always wrong direction).
        cur.execute("SELECT COALESCE(MAX(merge_id), 0) FROM master_employer_merge_log")
        merge_log_baseline_id = int(cur.fetchone()[0])

        # Per-pair merge_one loop. Batch-fetch all winners+losers up-front.
        all_mids = sorted(set(winner_map.keys()) | set(winner_map.values()))
        emps = {e.mid: e for e in fetch_employers(cur, ctx, all_mids)}
        log(f"  applying {len(winner_map):,} merges via merge_one...")
        applied = 0
        t0 = time.time()
        for loser_mid, winner_mid in winner_map.items():
            winner = emps[winner_mid]
            loser = emps[loser_mid]
            merge_one(
                cur, ctx,
                winner=winner, loser=loser,
                phase=PFIZER_BUNDLED_PHASE,
                conf=0.95,
                ev={"rule": "post_backfill_collision",
                    "winner_canonical": winner.canonical_name,
                    "loser_canonical": loser.canonical_name},
            )
            applied += 1
            if applied % 1000 == 0:
                elapsed = time.time() - t0
                rate = applied / elapsed if elapsed > 0 else 0
                eta = (len(winner_map) - applied) / rate if rate > 0 else 0
                log(f"    {applied:,}/{len(winner_map):,} ({rate:.0f}/s, ETA {eta/60:.1f}min)")
        log(f"  merge_one calls: {applied:,} in {time.time()-t0:.1f}s")

        # Now UPDATE canonical_name on the survivors. Winners that got merged
        # into via merge_one() have already had their canonical_name re-pref'd
        # against the loser; the back-fill plan may still want to overwrite
        # with the explicit `new_canonical`. Run the master UPDATE last so
        # the planned new_canonical wins.
        master_updated = commit_master(cur, master_plan, log)
        mergent_updated = commit_mergent(cur, mergent_plan, log)

        completed = datetime.now(timezone.utc)
        counts = {
            "master_plan_size": len(master_plan),
            "mergent_plan_size": len(mergent_plan),
            "collision_groups": collision_count,
            "pairs_merged": applied,
            "skipped_id_conflicts": len(skipped_id_conflicts),
            "skipped_f7_vs_f7": skipped_f7,
            "master_updated": master_updated,
            "mergent_updated": mergent_updated,
            "repoint_counts": repoint_counts,
            "snapshot_tables": snapshot_tables,
        }
        _insert_migration_audit_row(cur, audit_name, counts, started, completed)

        verification = _run_verification_ladder(
            cur, master_plan, mergent_plan, winner_map,
            merge_log_baseline_id, audit_name, log,
        )
        if not verification["all_pass"]:
            raise RuntimeError(f"Verification ladder failed: {verification}")
        log("  verification ladder: all PASS")

    return {
        "ok": True,
        "audit_name": audit_name,
        "counts": counts,
        "verification": verification,
        "snapshot_tables": snapshot_tables,
    }


# ============================================================================
# Entry point
# ============================================================================

def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument(
        "--commit", action="store_true",
        help="ACTUALLY write to the DB. Default is preview-only (CSV).",
    )
    parser.add_argument(
        "--max-dedup-candidates", type=int, default=1000,
        help=(
            "Bail (rollback) if the post-fix back-fill would create more than "
            "this many (canonical_name, state, city)-collision pairs. The "
            "dedup-merge step is OUT OF SCOPE for this script; collisions need "
            "a separate follow-up. Default 1000."
        ),
    )
    parser.add_argument(
        "--output-dir", type=Path,
        default=PROJECT_ROOT / "files" / "pfizer_backfill_preview",
        help="Directory for preview CSVs (default: files/pfizer_backfill_preview)",
    )
    parser.add_argument(
        "--skip-mv-check", action="store_true",
        help="(DANGEROUS) skip the critical-MV sanity guard. Do not use in production.",
    )
    parser.add_argument(
        "--bundled", action="store_true",
        help=(
            "Atomic bundled mode: back-fill canonicals + dedup-merge in ONE "
            "transaction. Bypasses --max-dedup-candidates; instead picks "
            "winners per collision group via SOURCE_PRIORITY, repoints FKs, "
            "merges losers via merge_one(), then UPDATEs canonicals. See "
            "docs/scratch/pfizer_dedup_bundle_plan_2026_05_20.md."
        ),
    )
    args = parser.parse_args()

    def log(msg):
        print(msg, flush=True)

    log(f"[{datetime.now(timezone.utc).isoformat()}] Pfizer canonical_name back-fill")
    log(f"  mode: {'COMMIT (DB writes)' if args.commit else 'preview-only (CSV)'}")
    log(f"  max dedup candidates: {args.max_dedup_candidates:,}")
    log(f"  preview output dir: {args.output_dir}")

    try:
        from db_config import get_connection
        conn = get_connection()
    except Exception as exc:
        print(f"ERROR: could not connect to database: {exc}", file=sys.stderr)
        return 3

    conn.autocommit = False

    try:
        with conn.cursor() as cur:
            # HARD-CODED SAFETY: critical MV existence check.
            if args.commit and not args.skip_mv_check:
                missing = _check_critical_mvs(cur)
                if missing:
                    print(
                        "ERROR: critical materialized view(s) missing: "
                        + ", ".join(missing),
                        file=sys.stderr,
                    )
                    print(
                        "Run `py scripts/scoring/refresh_all.py --skip-gower` first, "
                        "then re-run this script.",
                        file=sys.stderr,
                    )
                    return 1
                log("  critical MV check: PASS (all 3 present)")

            log("Building back-fill plan from candidate corrupt rows...")
            t0 = time.time()
            master_plan = build_master_plan(cur, log)
            mergent_plan = build_mergent_plan(cur, log)
            log(f"  plan-build elapsed: {time.time() - t0:.1f}s")

            log("Writing preview CSVs...")
            master_csv, mergent_csv = write_preview_csvs(
                master_plan, mergent_plan, args.output_dir,
            )
            log(f"  master preview:  {master_csv}")
            log(f"  mergent preview: {mergent_csv}")

            ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

            if args.bundled:
                # Bundled preview ALWAYS runs the planning portion (cheap,
                # mostly read-only — creates temp tables that drop on rollback).
                from src.python.matching.master_dedup import MergeContext
                ctx = MergeContext.detect(cur, label="backfill_pfizer_bundled")

                if not args.commit:
                    log("BUNDLED PREVIEW: computing collisions + winner map...")
                    _set_timeouts_bundled(cur)
                    _stage_plan_temp_tables(cur, master_plan, mergent_plan)
                    collision_count = _materialize_collision_groups(cur)
                    log(f"  collision groups: {collision_count:,}")
                    winner_map, skipped_id_conflicts, skipped_f7 = _pick_winners_for_groups(cur, ctx, log)
                    log(f"  pairs that would be merged: {len(winner_map):,}")
                    log("")
                    log("PREVIEW MODE (--bundled, no --commit) -- no DB writes. "
                        "Re-run with --bundled --commit to apply.")
                    conn.rollback()
                    return 0

                log("BUNDLED mode: back-fill + dedup-merge in one transaction.")
                result = run_bundled(conn, ctx, master_plan, mergent_plan, ts, log)
                conn.commit()
                log(f"  audit_name: {result['audit_name']}")
                log(f"  snapshots: {result['snapshot_tables']}")
                log("")
                log("Done. Post-commit runbook:")
                log("  1. py scripts/maintenance/check_critical_mvs.py")
                log("  2. py scripts/scoring/refresh_all.py --skip-gower")
                log("  3. Overnight: py scripts/scoring/compute_gower_similarity.py")
                log("     (then py scripts/scoring/refresh_all.py)")
                log("     DO NOT pass --dry-run to compute_gower_similarity.py "
                    "(it DROPs employer_comparables -- napkin 2026-05-12).")
                log("  4. After next /ship: drop snapshot tables documented above.")
                return 0

            if not args.commit:
                log("")
                log("PREVIEW MODE -- no DB writes. Review the CSVs, then re-run "
                    "with --commit (or --bundled --commit for atomic dedup).")
                conn.rollback()
                return 0

            log("Estimating post-fix dedup-merge candidate count...")
            dedup_count = estimate_dedup_candidates(cur, master_plan)
            log(f"  estimated dedup-merge candidates: {dedup_count:,}")
            if dedup_count > args.max_dedup_candidates:
                print(
                    f"ERROR: estimated {dedup_count:,} (canonical_name, state, city) "
                    f"collisions would be created by this back-fill -- exceeds "
                    f"--max-dedup-candidates {args.max_dedup_candidates:,}. "
                    "Rolling back.",
                    file=sys.stderr,
                )
                print(
                    "Resolution: re-run with --bundled to merge collisions in "
                    "the same transaction. See "
                    "docs/scratch/pfizer_dedup_bundle_plan_2026_05_20.md.",
                    file=sys.stderr,
                )
                conn.rollback()
                return 2

            log("Committing UPDATEs in a single transaction...")
            master_updated = commit_master(cur, master_plan, log)
            mergent_updated = commit_mergent(cur, mergent_plan, log)
            conn.commit()
            log(f"  master_employers rows updated: {master_updated:,}")
            log(f"  mergent_employers rows updated: {mergent_updated:,}")
            log("Done. Now rebuild MVs: py scripts/scoring/refresh_all.py --skip-gower")
            return 0
    except Exception as exc:
        conn.rollback()
        print(f"ERROR during back-fill: {exc}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return 3
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
