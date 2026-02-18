"""
CLI for running deterministic matching against F7 employers.

Usage:
    py scripts/matching/run_deterministic.py osha
    py scripts/matching/run_deterministic.py whd --limit 1000
    py scripts/matching/run_deterministic.py all --dry-run
    py scripts/matching/run_deterministic.py osha --unmatched-only
"""
import argparse
import sys
import uuid
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from db_config import get_connection
from scripts.matching.deterministic_matcher import DeterministicMatcher
from scripts.matching.adapters import osha_adapter, whd_adapter, n990_adapter, sam_adapter, sec_adapter_module, bmf_adapter_module

ADAPTERS = {
    "osha": osha_adapter,
    "whd": whd_adapter,
    "990": n990_adapter,
    "sam": sam_adapter,
    "sec": sec_adapter_module,
    "bmf": bmf_adapter_module,
}


def run_source(conn, source_name, adapter, args):
    """Run matching for a single source."""
    run_id = f"det-{source_name}-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    print(f"\n{'='*60}")
    print(f"Source: {source_name.upper()}")
    print(f"Run ID: {run_id}")
    print(f"{'='*60}")

    # Register run
    if not args.dry_run:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO match_runs (run_id, scenario, started_at, source_system, method_type)
                VALUES (%s, %s, NOW(), %s, %s)
                ON CONFLICT (run_id) DO NOTHING
            """, [run_id, f"deterministic_{source_name}", source_name, "deterministic_v2"])

            # When re-matching all, mark old active entries as superseded
            if not args.unmatched_only:
                cur.execute("""
                    UPDATE unified_match_log
                    SET status = 'superseded'
                    WHERE source_system = %s AND status = 'active'
                """, [source_name])
                superseded = cur.rowcount
                if superseded:
                    print(f"Superseded {superseded:,} old active matches in unified_match_log")

            conn.commit()

    # Load source records
    if args.unmatched_only:
        print("Loading unmatched records...")
        records = adapter.load_unmatched(conn, limit=args.limit)
    else:
        print("Loading all records...")
        records = adapter.load_all(conn, limit=args.limit)

    print(f"Loaded {len(records):,} source records")

    if not records:
        print("No records to match.")
        return

    # Run matching
    matcher = DeterministicMatcher(conn, run_id, source_name, dry_run=args.dry_run,
                                   skip_fuzzy=args.skip_fuzzy)
    matches = matcher.match_batch(records)
    matcher.print_stats()

    # Write to legacy tables (HIGH + MEDIUM only, skip LOW/rejected)
    if not args.dry_run and matches and not args.skip_legacy:
        quality_matches = [m for m in matches if m["band"] != "LOW"]
        if quality_matches:
            print(f"\nWriting {len(quality_matches):,} HIGH/MEDIUM matches to legacy table "
                  f"(skipping {len(matches) - len(quality_matches):,} LOW)...")
            adapter.write_legacy(conn, quality_matches)
        else:
            print("\nNo HIGH/MEDIUM matches to write to legacy table.")

    # Update run stats
    if not args.dry_run:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE match_runs
                SET completed_at = NOW(),
                    total_source = %s,
                    total_matched = %s,
                    match_rate = %s,
                    high_count = %s,
                    medium_count = %s,
                    low_count = %s
                WHERE run_id = %s
            """, [
                len(records), len(matches),
                round(len(matches) / max(len(records), 1) * 100, 2),
                matcher.stats["by_band"]["HIGH"],
                matcher.stats["by_band"]["MEDIUM"],
                matcher.stats["by_band"]["LOW"],
                run_id,
            ])
            conn.commit()

    return matches


def main():
    parser = argparse.ArgumentParser(description="Run deterministic matching")
    parser.add_argument("source", choices=["osha", "whd", "990", "sam", "sec", "bmf", "all"],
                        help="Source system to match")
    parser.add_argument("--limit", type=int, help="Limit number of source records")
    parser.add_argument("--dry-run", action="store_true", help="Don't write to database")
    parser.add_argument("--unmatched-only", action="store_true", default=True,
                        help="Only match unmatched records (default)")
    parser.add_argument("--rematch-all", action="store_true",
                        help="Re-match all records, not just unmatched")
    parser.add_argument("--skip-legacy", action="store_true",
                        help="Skip writing to legacy match tables")
    parser.add_argument("--skip-fuzzy", action="store_true",
                        help="Skip tier 5 fuzzy matching (fast exact-only mode)")
    args = parser.parse_args()

    if args.rematch_all:
        args.unmatched_only = False

    conn = get_connection()
    try:
        if args.source == "all":
            for name in ["osha", "whd", "990", "sam", "sec", "bmf"]:
                run_source(conn, name, ADAPTERS[name], args)
        else:
            run_source(conn, args.source, ADAPTERS[args.source], args)
    finally:
        conn.close()

    print("\nDone.")


if __name__ == "__main__":
    main()
