"""
Reject stale OSHA matches with name similarity < 0.80.
Mark matches as 'superseded' in unified_match_log.

Usage: python scripts/maintenance/reject_stale_osha.py [--dry-run]
"""
import sys
import os
import argparse
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
import psycopg2.extras
from db_config import get_connection

def reject_stale_osha(conn, dry_run=False):
    """Mark stale OSHA matches as superseded."""
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    # Find matches to reject
    # floor = 0.80 per Decision D1/1.4 roadmap
    query_find = """
        SELECT id, source_id, target_id, (evidence->>'name_similarity')::float as sim
        FROM unified_match_log
        WHERE match_method = 'FUZZY_SPLINK_ADAPTIVE'
          AND source_system = 'osha'
          AND (evidence->>'name_similarity')::float < 0.80
          AND status = 'active'
    """
    cur.execute(query_find)
    rows = cur.fetchall()
    count = len(rows)
    print(f"Found {count} active OSHA matches with name similarity < 0.80")

    if count == 0:
        return 0

    if dry_run:
        print(f"[DRY-RUN] Sample of 5 matches to supersede:")
        for r in rows[:5]:
            print(f"  Match ID {r['id']}: OSHA {r['source_id']} -> F7 {r['target_id']} (sim={r['sim']})")
        return count

    # Perform update
    query_update = """
        UPDATE unified_match_log
        SET status = 'superseded'
        WHERE match_method = 'FUZZY_SPLINK_ADAPTIVE'
          AND source_system = 'osha'
          AND (evidence->>'name_similarity')::float < 0.80
          AND status = 'active'
    """
    cur.execute(query_update)
    updated = cur.rowcount
    conn.commit()
    print(f"Successfully marked {updated} OSHA matches as 'superseded'")
    return updated

def main():
    parser = argparse.ArgumentParser(description="Reject stale OSHA matches.")
    parser.add_argument('--dry-run', action='store_true', help="Only show matches that would be affected.")
    args = parser.parse_args()

    conn = get_connection()
    try:
        reject_stale_osha(conn, dry_run=args.dry_run)
    finally:
        conn.close()

if __name__ == '__main__':
    main()
