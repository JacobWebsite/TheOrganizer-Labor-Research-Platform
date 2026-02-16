#!/usr/bin/env python3
"""
IRS Business Master File Adapter (Stub)
Claude will implement the full matching logic
"""
import sys
import os
from pathlib import Path

# Add the project root to the sys.path
script_dir = Path(__file__).resolve().parent
project_root = script_dir.parent.parent.parent # Assumes script is in scripts/matching/adapters/
sys.path.insert(0, str(project_root))

from db_config import get_connection
from psycopg2.extras import RealDictCursor


class BMFAdapter:
    """Adapter for IRS BMF matching to F7 employers"""

    def __init__(self):
        self.source_system = 'irs_bmf'
        self.target_system = 'f7_employers_deduped'

    def load_unmatched(self, limit=None):
        """
        Load BMF orgs not yet in unified_match_log

        Returns: List of dicts with:
            - source_id (EIN)
            - org_name
            - state
            - city
            - ntee_code (J40 = unions)
            - subsection_code (05 = 501(c)(5) labor orgs)
        """
        conn = get_connection(cursor_factory=RealDictCursor)
        cur = conn.cursor()

        query = """
            SELECT
                b.ein as source_id,
                b.org_name,
                b.state,
                b.city,
                b.ntee_code,
                b.subsection_code
            FROM irs_bmf b
            LEFT JOIN unified_match_log uml
                ON uml.source_system = 'irs_bmf'
                AND uml.source_id = b.ein
                AND uml.status = 'active'
            WHERE uml.id IS NULL
        """

        if limit:
            query += f" LIMIT {limit}"

        cur.execute(query)
        return cur.fetchall()

    def load_all(self):
        """Load all BMF orgs (for reprocessing)"""
        conn = get_connection(cursor_factory=RealDictCursor)
        cur = conn.cursor()

        cur.execute("""
            SELECT ein as source_id, org_name, state, city,
                   ntee_code, subsection_code
            FROM irs_bmf
        """)
        return cur.fetchall()


# Test the adapter
if __name__ == '__main__':
    # Add project root to sys.path for db_config
    # This block is not needed as it's added at the top of the file now.
    # import sys
    # import os
    # from pathlib import Path
    # script_dir = Path(__file__).resolve().parent
    # project_root = script_dir.parent.parent # Assumes script is in scripts/matching/adapters/
    # sys.path.insert(0, str(project_root))

    adapter = BMFAdapter()
    unmatched = adapter.load_unmatched(limit=10)
    print(f"\nUnmatched BMF organizations: {len(unmatched)}")
    if unmatched:
        print(f"Sample: {unmatched[0]}")

    # Count labor organizations
    conn = get_connection(cursor_factory=RealDictCursor)
    cur = conn.cursor()

    cur.execute("""
        SELECT
            COUNT(*) FILTER (WHERE ntee_code = 'J40') as unions,
            COUNT(*) FILTER (WHERE subsection_code = '05') as labor_orgs_501c5,
            COUNT(*) FILTER (WHERE ntee_code LIKE 'J%%') as labor_related
        FROM irs_bmf
    """)
    stats = cur.fetchone()
    print(f"\nLabor organization counts:")
    print(f"  Unions (NTEE J40): {stats['unions']:,}")
    print(f"  501(c)(5) orgs: {stats['labor_orgs_501c5']:,}")
    print(f"  All labor-related: {stats['labor_related']:,}")
