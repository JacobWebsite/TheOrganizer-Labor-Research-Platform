"""
Master pipeline script for union web scraper tiered extraction.

Chains all stages in order:
  1. discover_pages (sitemap/nav/probe discovery)
  2. extract_wordpress (WP REST API)
  3. extract_union_data (regex + structured HTML)
  4. fix_extraction (cleanup)
  5. extract_gemini_fallback (Gemini for 0-employer profiles)
  6. match_web_employers (matching)

Usage:
    py scripts/scraper/run_extraction_pipeline.py
    py scripts/scraper/run_extraction_pipeline.py --profile-id 42
    py scripts/scraper/run_extraction_pipeline.py --skip-gemini --skip-matching
    py scripts/scraper/run_extraction_pipeline.py --from-stage 3
    py scripts/scraper/run_extraction_pipeline.py --dry-run
"""
import sys
import os
import time
import argparse
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
from db_config import get_connection


# ── Stage Definitions ────────────────────────────────────────────────────

STAGES = [
    (1, 'discovery', 'Page Discovery'),
    (2, 'wordpress', 'WordPress API Extraction'),
    (3, 'extraction', 'Tiered Extraction (regex + HTML)'),
    (4, 'fix', 'Extraction Cleanup'),
    (5, 'gemini', 'Gemini Fallback'),
    (6, 'matching', 'Employer Matching'),
]


def run_discovery(conn, profile_id=None, union=None, **kwargs):
    """Stage 1: Discover pages via sitemap, nav links, probes."""
    import requests
    from scripts.scraper.discover_pages import discover_for_profile

    session = requests.Session()
    cur = conn.cursor()

    ids = _get_profile_ids(cur, profile_id, union)
    print(f"  Discovering pages for {len(ids)} profiles...")

    total = 0
    for pid in ids:
        total += discover_for_profile(conn, pid, session)

    print(f"  -> {total} new pages discovered")
    return total


def run_wordpress(conn, profile_id=None, union=None, **kwargs):
    """Stage 2: Extract from WordPress REST API."""
    import requests
    from scripts.scraper.extract_wordpress import extract_for_profile

    session = requests.Session()
    cur = conn.cursor()

    ids = _get_profile_ids(cur, profile_id, union, wp_only=True)
    print(f"  Processing {len(ids)} profiles for WP extraction...")

    total = 0
    for pid in ids:
        total += extract_for_profile(conn, pid, session)

    print(f"  -> {total} employers from WP API")
    return total


def run_extraction(conn, profile_id=None, union=None, **kwargs):
    """Stage 3: Run tiered extraction (regex + HTML parsing)."""
    from scripts.scraper.extract_union_data import extract_with_tiers, auto_extract_profile, insert_extracted

    cur = conn.cursor()
    ids = _get_profile_ids(cur, profile_id, union)
    print(f"  Running tiered extraction on {len(ids)} profiles...")

    total = 0
    for pid in ids:
        # Try tiered extraction first
        n = extract_with_tiers(conn, pid)
        if n > 0:
            total += n
        else:
            # Fall back to legacy auto_extract
            data = auto_extract_profile(conn, pid)
            if data and any(data.get(k) for k in ['employers', 'contracts', 'membership', 'news']):
                inserted = insert_extracted(conn, data)
                total += inserted.get('employers', 0)

    print(f"  -> {total} employers from tiered extraction")
    return total


def run_fix(conn, **kwargs):
    """Stage 4: Run extraction cleanup."""
    from scripts.scraper.fix_extraction import fix_employers, fix_membership

    print("  Running extraction fixes...")
    fix_employers(conn)
    fix_membership(conn)


def run_gemini(conn, profile_id=None, dry_run=False, **kwargs):
    """Stage 5: Gemini fallback for profiles with 0 employers."""
    from scripts.scraper.extract_gemini_fallback import get_qualifying_profiles, extract_with_gemini

    profiles = get_qualifying_profiles(conn, profile_id)
    print(f"  {len(profiles)} profiles qualify for Gemini fallback")

    if profiles:
        total = extract_with_gemini(conn, profiles, dry_run=dry_run)
        return total or 0
    return 0


def run_matching(conn, **kwargs):
    """Stage 6: Match employers against F7/OSHA."""
    from scripts.scraper.match_web_employers import run_matching as do_matching, print_summary

    stats = do_matching(conn)
    print_summary(conn, stats)
    return sum(v for k, v in stats.items() if k != 'unmatched')


# ── Helpers ──────────────────────────────────────────────────────────────

def _get_profile_ids(cur, profile_id=None, union=None, wp_only=False):
    """Get profile IDs to process."""
    if profile_id:
        return [profile_id]

    query = """
        SELECT id FROM web_union_profiles
        WHERE website_url IS NOT NULL
          AND scrape_status IN ('FETCHED', 'EXTRACTED')
    """
    params = []

    if wp_only:
        query += " AND (platform = 'WordPress' OR wp_api_available = TRUE)"

    if union:
        query += " AND union_name ILIKE %s"
        params.append(f'%{union}%')

    query += " ORDER BY id"
    cur.execute(query, params)
    return [r[0] for r in cur.fetchall()]


# ── Main Pipeline ────────────────────────────────────────────────────────

def run_pipeline(args):
    """Run the full extraction pipeline."""
    conn = get_connection()

    stage_runners = {
        1: ('discovery', run_discovery),
        2: ('wordpress', run_wordpress),
        3: ('extraction', run_extraction),
        4: ('fix', run_fix),
        5: ('gemini', run_gemini),
        6: ('matching', run_matching),
    }

    skips = set()
    if args.skip_discovery:
        skips.add(1)
    if args.skip_wordpress:
        skips.add(2)
    if args.skip_gemini:
        skips.add(5)
    if args.skip_matching:
        skips.add(6)

    started = datetime.now()
    print(f"{'='*60}")
    print(f"UNION WEB SCRAPER EXTRACTION PIPELINE")
    print(f"Started: {started.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*60}\n")

    kwargs = {
        'profile_id': args.profile_id,
        'union': args.union,
        'dry_run': args.dry_run,
    }

    for stage_num, (stage_name, runner) in stage_runners.items():
        if stage_num < args.from_stage:
            print(f"Stage {stage_num} ({stage_name}): SKIPPED (--from-stage {args.from_stage})")
            continue
        if stage_num in skips:
            print(f"Stage {stage_num} ({stage_name}): SKIPPED")
            continue

        stage_label = next(s[2] for s in STAGES if s[0] == stage_num)
        print(f"\n--- Stage {stage_num}: {stage_label} ---")
        stage_start = time.time()

        try:
            runner(conn, **kwargs)
        except Exception as e:
            print(f"  ERROR in stage {stage_num}: {e}")
            if not args.continue_on_error:
                print("  Stopping pipeline. Use --continue-on-error to proceed past failures.")
                break

        elapsed = time.time() - stage_start
        print(f"  (completed in {elapsed:.1f}s)")

    # Final summary
    total_elapsed = (datetime.now() - started).total_seconds()
    print(f"\n{'='*60}")
    print(f"PIPELINE COMPLETE ({total_elapsed:.0f}s)")
    print(f"{'='*60}")

    # Show final counts
    cur = conn.cursor()
    cur.execute("""
        SELECT extraction_method, COUNT(*)
        FROM web_union_employers
        GROUP BY extraction_method
        ORDER BY COUNT(*) DESC
    """)
    print(f"\nEmployers by extraction method:")
    total = 0
    for method, cnt in cur.fetchall():
        print(f"  {method:<25} {cnt:>6}")
        total += cnt
    print(f"  {'TOTAL':<25} {total:>6}")

    cur.execute("SELECT COUNT(DISTINCT web_profile_id) FROM web_union_employers")
    profiles_with = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM web_union_profiles WHERE scrape_status IN ('FETCHED','EXTRACTED')")
    total_profiles = cur.fetchone()[0]
    print(f"\nProfile coverage: {profiles_with}/{total_profiles} "
          f"({100*profiles_with/max(total_profiles,1):.0f}%)")

    conn.close()


# ── CLI ──────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description='Union web scraper extraction pipeline')
    parser.add_argument('--profile-id', type=int, help='Process single profile')
    parser.add_argument('--union', help='Filter by union name')
    parser.add_argument('--from-stage', type=int, default=1,
                        help='Start from stage N (1-6)')
    parser.add_argument('--skip-discovery', action='store_true')
    parser.add_argument('--skip-wordpress', action='store_true')
    parser.add_argument('--skip-gemini', action='store_true')
    parser.add_argument('--skip-matching', action='store_true')
    parser.add_argument('--dry-run', action='store_true',
                        help='Show what would be done without changes')
    parser.add_argument('--continue-on-error', action='store_true',
                        help='Continue pipeline even if a stage fails')
    args = parser.parse_args()

    run_pipeline(args)


if __name__ == '__main__':
    main()
