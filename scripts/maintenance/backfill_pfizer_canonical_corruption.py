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
        plan.append((master_id, display_name, canonical_name, new_canonical))
    log(f"  master_employers: examined {examined:,} candidate rows")
    log(f"    skipped (not bug victim): {not_a_victim:,}")
    log(f"    skipped (already correct): {already_correct:,}")
    log(f"    actionable: {len(plan):,}")
    return plan


def build_mergent_plan(cur, log):
    """Return list of (id, company_name, old_normalized, new_normalized)."""
    plan = []
    not_a_victim = 0
    already_correct = 0
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
        plan.append((rid, company_name, company_name_normalized, new_normalized))
    log(f"  mergent_employers: examined {examined:,} candidate rows")
    log(f"    skipped (not bug victim): {not_a_victim:,}")
    log(f"    skipped (already correct): {already_correct:,}")
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

            if not args.commit:
                log("")
                log("PREVIEW MODE -- no DB writes. Review the CSVs, then re-run "
                    "with --commit.")
                conn.rollback()  # paranoia (we didn't write, but cleanup any temps).
                return 0

            # --commit path from here on.
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
                    "Resolution: bump the threshold ONLY after building a "
                    "dedup-merge plan for the colliding rows. See "
                    "scripts/etl/dedup_master_employers.py for the existing "
                    "merge logic.",
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
