"""
Command-line interface for the unified matching module.

Usage:
    python -m scripts.matching run --list
    python -m scripts.matching run mergent_to_f7 --save
    python -m scripts.matching run mergent_to_f7 --save --diff
    python -m scripts.matching diff mergent_to_f7
    python -m scripts.matching run-all --save
"""

import argparse
import sys
import logging
from datetime import datetime

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def get_connection():
    """Get database connection."""
    import psycopg2
    return psycopg2.connect(
        host='localhost',
        dbname='olms_multiyear',
        user='postgres',
        password='Juniordog33!'
    )


def cmd_list_scenarios(args):
    """List available scenarios."""
    from .config import SCENARIOS

    print("\n" + "=" * 60)
    print("AVAILABLE MATCHING SCENARIOS")
    print("=" * 60 + "\n")

    for name, config in SCENARIOS.items():
        print(f"  {name}")
        print(f"    Source: {config.source_table} ({config.source_name_col})")
        print(f"    Target: {config.target_table} ({config.target_name_col})")
        if config.source_filter:
            print(f"    Filter: {config.source_filter}")
        print()


def cmd_run(args):
    """Run a matching scenario."""
    from .pipeline import MatchPipeline
    from .config import SCENARIOS

    if args.list:
        cmd_list_scenarios(args)
        return

    scenario = args.scenario
    if scenario not in SCENARIOS:
        print(f"Error: Unknown scenario '{scenario}'")
        print(f"Available: {', '.join(SCENARIOS.keys())}")
        sys.exit(1)

    print(f"\n{'='*60}")
    print(f"RUNNING SCENARIO: {scenario}")
    print(f"{'='*60}\n")

    conn = get_connection()

    try:
        pipeline = MatchPipeline(conn, scenario=scenario, skip_fuzzy=args.skip_fuzzy)

        def progress(processed, total, matched):
            pct = (processed / total * 100) if total else 0
            print(f"\r  Progress: {processed:,} / {total:,} ({pct:.1f}%) - {matched:,} matched", end="")

        stats = pipeline.run_scenario(
            batch_size=args.batch_size,
            limit=args.limit,
            progress_callback=progress if not args.quiet else None,
        )

        print("\n")
        print(f"{'='*60}")
        print(f"RESULTS")
        print(f"{'='*60}")
        print(f"  Total source:  {stats.total_source:,}")
        print(f"  Total matched: {stats.total_matched:,}")
        print(f"  Match rate:    {stats.match_rate:.1f}%")
        print()
        print("  By tier:")
        for tier, count in sorted(stats.by_tier.items()):
            from .config import TIER_NAMES
            print(f"    {TIER_NAMES.get(tier, tier)}: {count:,}")
        print()

        if args.save:
            from .pipeline import _save_run
            _save_run(conn, stats, pipeline)
            print(f"  Run saved with ID: {stats.run_id}")

        if args.diff:
            from .differ import DiffReport
            report = DiffReport(conn)
            report.generate(scenario)
            report.print_summary()

    finally:
        conn.close()


def cmd_run_all(args):
    """Run all matching scenarios."""
    from .config import SCENARIOS

    print(f"\n{'='*60}")
    print(f"RUNNING ALL SCENARIOS")
    print(f"{'='*60}\n")

    conn = get_connection()

    try:
        for scenario in SCENARIOS:
            print(f"\n--- {scenario} ---")
            try:
                from .pipeline import MatchPipeline, _save_run
                pipeline = MatchPipeline(conn, scenario=scenario)
                stats = pipeline.run_scenario(
                    batch_size=args.batch_size,
                    limit=args.limit,
                )
                print(f"  Matched: {stats.total_matched:,} / {stats.total_source:,} ({stats.match_rate:.1f}%)")

                if args.save:
                    _save_run(conn, stats, pipeline)
                    print(f"  Saved run: {stats.run_id}")

            except Exception as e:
                logger.error(f"  Failed: {e}")

    finally:
        conn.close()

    print(f"\n{'='*60}")
    print("ALL SCENARIOS COMPLETE")
    print(f"{'='*60}\n")


def cmd_diff(args):
    """Generate diff report."""
    from .differ import DiffReport

    scenario = args.scenario
    conn = get_connection()

    try:
        report = DiffReport(conn)
        report.generate(scenario, run_a=args.run_a, run_b=args.run_b)

        if args.format == "markdown":
            print(report.to_markdown())
        elif args.format == "json":
            import json
            print(json.dumps(report.to_dict(), indent=2, default=str))
        else:
            report.print_summary()

    finally:
        conn.close()


def cmd_test_match(args):
    """Test matching a single name."""
    from .pipeline import MatchPipeline
    from .config import SCENARIOS

    scenario = args.scenario
    if scenario not in SCENARIOS:
        print(f"Error: Unknown scenario '{scenario}'")
        sys.exit(1)

    conn = get_connection()

    try:
        pipeline = MatchPipeline(conn, scenario=scenario)
        result = pipeline.match(
            source_name=args.name,
            state=args.state,
            city=args.city,
            ein=args.ein,
        )

        print(f"\n{'='*60}")
        print(f"MATCH TEST")
        print(f"{'='*60}")
        print(f"  Input: {args.name}")
        if args.state:
            print(f"  State: {args.state}")
        if args.city:
            print(f"  City: {args.city}")
        print()

        if result.matched:
            print(f"  MATCHED!")
            print(f"  Target: {result.target_name}")
            print(f"  Target ID: {result.target_id}")
            print(f"  Method: {result.method} (Tier {result.tier})")
            print(f"  Score: {result.score:.4f}")
            print(f"  Confidence: {result.confidence}")
        else:
            print(f"  NO MATCH FOUND")

        print()

    finally:
        conn.close()


def main():
    parser = argparse.ArgumentParser(
        description="Unified Employer Matching CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python -m scripts.matching run --list
  python -m scripts.matching run mergent_to_f7 --limit 1000
  python -m scripts.matching run mergent_to_f7 --save --diff
  python -m scripts.matching diff mergent_to_f7 --format markdown
  python -m scripts.matching test mergent_to_f7 "ACME Hospital" --state NY
  python -m scripts.matching run-all --save
        """
    )

    subparsers = parser.add_subparsers(dest='command', help='Command to run')

    # Run command
    run_parser = subparsers.add_parser('run', help='Run a matching scenario')
    run_parser.add_argument('scenario', nargs='?', help='Scenario name')
    run_parser.add_argument('--list', '-l', action='store_true', help='List available scenarios')
    run_parser.add_argument('--save', '-s', action='store_true', help='Save results to database')
    run_parser.add_argument('--diff', '-d', action='store_true', help='Generate diff against previous run')
    run_parser.add_argument('--batch-size', '-b', type=int, default=1000, help='Batch size')
    run_parser.add_argument('--limit', type=int, help='Limit records to process')
    run_parser.add_argument('--quiet', '-q', action='store_true', help='Quiet mode')
    run_parser.add_argument('--skip-fuzzy', action='store_true', help='Skip Tier 4 fuzzy matching (faster)')
    run_parser.set_defaults(func=cmd_run)

    # Run-all command
    runall_parser = subparsers.add_parser('run-all', help='Run all scenarios')
    runall_parser.add_argument('--save', '-s', action='store_true', help='Save results to database')
    runall_parser.add_argument('--batch-size', '-b', type=int, default=1000, help='Batch size')
    runall_parser.add_argument('--limit', type=int, help='Limit records to process')
    runall_parser.set_defaults(func=cmd_run_all)

    # Diff command
    diff_parser = subparsers.add_parser('diff', help='Compare matching runs')
    diff_parser.add_argument('scenario', help='Scenario name')
    diff_parser.add_argument('--run-a', help='Older run ID')
    diff_parser.add_argument('--run-b', help='Newer run ID')
    diff_parser.add_argument('--format', '-f', choices=['summary', 'markdown', 'json'],
                            default='summary', help='Output format')
    diff_parser.set_defaults(func=cmd_diff)

    # Test command
    test_parser = subparsers.add_parser('test', help='Test matching a single name')
    test_parser.add_argument('scenario', help='Scenario name')
    test_parser.add_argument('name', help='Employer name to match')
    test_parser.add_argument('--state', '-s', help='State filter')
    test_parser.add_argument('--city', '-c', help='City filter')
    test_parser.add_argument('--ein', '-e', help='EIN for matching')
    test_parser.set_defaults(func=cmd_test_match)

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    args.func(args)


if __name__ == '__main__':
    main()
