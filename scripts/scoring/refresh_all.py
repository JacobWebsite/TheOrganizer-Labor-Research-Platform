"""
Orchestrate full MV rebuild chain in dependency order.

Usage:
    py scripts/scoring/refresh_all.py              # full rebuild
    py scripts/scoring/refresh_all.py --skip-gower # skip Gower (faster)
    py scripts/scoring/refresh_all.py --with-report # include score change report
"""
import argparse
import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
from db_config import get_connection

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, '..', '..'))

# Ordered dependency chain
STEPS = [
    ("create_scorecard_mv",        "create_scorecard_mv.py"),
    ("compute_gower_similarity",   "compute_gower_similarity.py"),
    ("build_employer_data_sources", "build_employer_data_sources.py"),
    ("build_unified_scorecard",    "build_unified_scorecard.py"),
    ("build_target_data_sources",  "build_target_data_sources.py"),
    ("build_target_scorecard",     "build_target_scorecard.py"),
    ("rebuild_search_mv",          "rebuild_search_mv.py"),
]


def run_pre_checks():
    """Run pre-build checks before starting the chain."""
    print("Running pre-build checks...")
    conn = get_connection()
    try:
        # Import and call _check_contract_data from build_unified_scorecard
        # Skip if mv_employer_data_sources doesn't exist yet (it's built by step 3)
        cur = conn.cursor()
        cur.execute("""
            SELECT EXISTS (
                SELECT 1 FROM pg_matviews WHERE matviewname = 'mv_employer_data_sources'
            )
        """)
        if cur.fetchone()[0]:
            from scripts.scoring.build_unified_scorecard import _check_contract_data
            _check_contract_data(conn)
            print("  Pre-build checks passed.")
        else:
            print("  mv_employer_data_sources not yet built -- skipping pre-check (will be created in step 3).")
    finally:
        conn.close()


def run_step(name, script_file):
    """Run a single script and return (duration, return_code)."""
    script_path = os.path.join(SCRIPT_DIR, script_file)
    if not os.path.isfile(script_path):
        print(f"  WARNING: {script_path} not found, skipping.")
        return 0.0, -1

    print(f"\n{'=' * 60}")
    print(f"  Step: {name}")
    print(f"  Script: {script_file}")
    print(f"{'=' * 60}")

    t0 = time.time()
    result = subprocess.run(
        [sys.executable, script_path],
        cwd=PROJECT_ROOT,
    )
    duration = time.time() - t0

    status = "OK" if result.returncode == 0 else f"FAILED (rc={result.returncode})"
    print(f"  --> {status} in {duration:.1f}s")

    return duration, result.returncode


def run_report_step(subcommand):
    """Run score_change_report.py with the given subcommand."""
    script_path = os.path.join(SCRIPT_DIR, "score_change_report.py")
    if not os.path.isfile(script_path):
        print("  WARNING: score_change_report.py not found, skipping report.")
        return 0.0, -1

    print(f"\n{'=' * 60}")
    print(f"  Report: score_change_report.py {subcommand}")
    print(f"{'=' * 60}")

    t0 = time.time()
    result = subprocess.run(
        [sys.executable, script_path, subcommand],
        cwd=PROJECT_ROOT,
    )
    duration = time.time() - t0

    status = "OK" if result.returncode == 0 else f"FAILED (rc={result.returncode})"
    print(f"  --> {status} in {duration:.1f}s")

    return duration, result.returncode


def print_summary(results):
    """Print a summary table of all steps."""
    print(f"\n{'=' * 60}")
    print("  REBUILD SUMMARY")
    print(f"{'=' * 60}")
    print(f"  {'Step':<35s} {'Duration':>10s}  {'Status':<15s}")
    print(f"  {'-' * 35} {'-' * 10}  {'-' * 15}")

    total_time = 0.0
    for name, duration, rc in results:
        total_time += duration
        if rc == 0:
            status = "OK"
        elif rc == -1:
            status = "SKIPPED"
        else:
            status = f"FAILED (rc={rc})"
        dur_str = f"{duration:.1f}s"
        print(f"  {name:<35s} {dur_str:>10s}  {status:<15s}")

    print(f"  {'-' * 35} {'-' * 10}  {'-' * 15}")
    print(f"  {'TOTAL':<35s} {total_time:.1f}s")
    print()


def main():
    parser = argparse.ArgumentParser(
        description="Orchestrate full MV rebuild chain in dependency order."
    )
    parser.add_argument(
        '--skip-gower', action='store_true',
        help='Skip the slow Gower similarity computation'
    )
    parser.add_argument(
        '--with-report', action='store_true',
        help='Run score_change_report.py before and after build_unified_scorecard'
    )
    args = parser.parse_args()

    print("=" * 60)
    print("  MV REBUILD CHAIN -- Full Refresh")
    print("=" * 60)

    # Pre-build checks
    try:
        run_pre_checks()
    except Exception as e:
        print(f"\n  PRE-BUILD CHECK FAILED: {e}")
        print("  Aborting rebuild.")
        sys.exit(1)

    results = []

    for name, script_file in STEPS:
        # Skip Gower if requested
        if name == "compute_gower_similarity" and args.skip_gower:
            print(f"\n  Skipping {name} (--skip-gower)")
            results.append((name, 0.0, -1))
            continue

        # Run snapshot before build_unified_scorecard
        if name == "build_unified_scorecard" and args.with_report:
            dur, rc = run_report_step("snapshot")
            results.append(("score_change_report snapshot", dur, rc))
            if rc != 0 and rc != -1:
                print(f"\n  Score snapshot failed (rc={rc}), continuing anyway...")

        # Run the step
        duration, rc = run_step(name, script_file)
        results.append((name, duration, rc))

        # Stop on failure
        if rc != 0 and rc != -1:
            print(f"\n  STEP FAILED: {name} returned {rc}")
            print("  Stopping rebuild chain.")
            print_summary(results)
            sys.exit(1)

        # Run compare after build_unified_scorecard
        if name == "build_unified_scorecard" and args.with_report:
            dur, rc = run_report_step("compare")
            results.append(("score_change_report compare", dur, rc))
            if rc != 0 and rc != -1:
                print(f"\n  Score comparison failed (rc={rc}), continuing anyway...")

    print_summary(results)
    print("  Rebuild chain completed successfully.")


if __name__ == '__main__':
    main()
