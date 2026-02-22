"""
Drop orphaned industry-specific views.

These views follow legacy naming patterns and are no longer maintained:
- v_{industry}_organizing_targets
- v_{industry}_target_stats
- v_{industry}_unionized

Default behavior is dry-run (list only). Use --execute to drop inside a
single transaction with rollback on error.
"""

import argparse
import os
import re
import sys
from collections import defaultdict
from typing import List

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
from db_config import get_connection


ORPHAN_VIEW_REGEX = r'^v_(.+)_(organizing_targets|target_stats|unionized)$'
REQUIRED_SUFFIXES = {'organizing_targets', 'target_stats', 'unionized'}


def fetch_matching_views(cur) -> List[str]:
    cur.execute(
        """
        SELECT table_name
        FROM information_schema.views
        WHERE table_schema = 'public'
          AND table_name ~ %s
        ORDER BY table_name
        """,
        (ORPHAN_VIEW_REGEX,),
    )
    candidates = [row[0] for row in cur.fetchall()]

    # Only drop full orphan industry triplets. This avoids singleton core views
    # like v_osha_organizing_targets, which are not part of the orphan set.
    grouped = defaultdict(set)
    for name in candidates:
        match = re.match(ORPHAN_VIEW_REGEX, name)
        if match:
            grouped[match.group(1)].add(match.group(2))

    orphan_industries = {
        industry for industry, suffixes in grouped.items() if suffixes == REQUIRED_SUFFIXES
    }
    return sorted(
        name for name in candidates
        if re.match(ORPHAN_VIEW_REGEX, name) and re.match(ORPHAN_VIEW_REGEX, name).group(1) in orphan_industries
    )


def fetch_total_view_count(cur) -> int:
    cur.execute(
        """
        SELECT COUNT(*)
        FROM information_schema.views
        WHERE table_schema = 'public'
        """
    )
    return cur.fetchone()[0]


def main() -> None:
    parser = argparse.ArgumentParser(description='Drop orphan industry views')
    parser.add_argument(
        '--execute',
        action='store_true',
        help='Actually drop views (default is dry-run)',
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='List orphan views without dropping (default behavior)',
    )
    args = parser.parse_args()

    execute = args.execute and not args.dry_run

    conn = get_connection()
    conn.autocommit = False

    try:
        with conn.cursor() as cur:
            before_total = fetch_total_view_count(cur)
            before_match = fetch_matching_views(cur)

            print(f"Mode: {'EXECUTE' if execute else 'DRY-RUN'}")
            print(f"Total public views (before): {before_total}")
            print(f"Orphan-pattern views found (before): {len(before_match)}")

            if before_match:
                print("\nViews:")
                for name in before_match:
                    print(f"  - {name}")
            else:
                print("\nNo matching orphan views found.")

            if execute and before_match:
                print("\nDropping views in one transaction...")
                for name in before_match:
                    cur.execute(f'DROP VIEW IF EXISTS public."{name}" CASCADE')
                conn.commit()
                print("Drop complete.")
            else:
                conn.rollback()
                print("No changes applied.")

            after_total = fetch_total_view_count(cur)
            after_match = fetch_matching_views(cur)

            print(f"\nTotal public views (after): {after_total}")
            print(f"Orphan-pattern views found (after): {len(after_match)}")

    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == '__main__':
    main()
