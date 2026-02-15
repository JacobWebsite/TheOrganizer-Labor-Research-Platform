import os
from db_config import get_connection
"""
Add indexes to speed up unified view queries
"""
import psycopg2

conn = get_connection()
conn.autocommit = True
cur = conn.cursor()

print("=" * 60)
print("Adding indexes for performance")
print("=" * 60)

# The view queries the underlying tables - we need indexes there
indexes = [
    # For v_f7_private_sector_cleaned (based on v_f7_reconciled_private_sector)
    "CREATE INDEX IF NOT EXISTS idx_f7_reconciled_affiliation ON f7_employers_deduped(latest_union_fnum);",
    "CREATE INDEX IF NOT EXISTS idx_f7_reconciled_state ON f7_employers_deduped(state);",
    
    # For public_sector_employers
    "CREATE INDEX IF NOT EXISTS idx_public_sector_union ON public_sector_employers(union_acronym);",
    "CREATE INDEX IF NOT EXISTS idx_public_sector_state ON public_sector_employers(state);",
    
    # For federal_bargaining_units
    "CREATE INDEX IF NOT EXISTS idx_federal_bu_agency ON federal_bargaining_units(agency_name);",
    "CREATE INDEX IF NOT EXISTS idx_federal_bu_union ON federal_bargaining_units(union_acronym);",
]

for idx in indexes:
    try:
        print(f"  Creating: {idx[:60]}...")
        cur.execute(idx)
        print("    [OK]")
    except Exception as e:
        print(f"    [SKIP] {e}")

# Check if we can create a materialized view for better performance
print("\n--- Creating materialized view for faster queries ---")
try:
    cur.execute("DROP MATERIALIZED VIEW IF EXISTS mv_employers_unified CASCADE;")
    cur.execute("""
        CREATE MATERIALIZED VIEW mv_employers_unified AS
        SELECT * FROM all_employers_unified;
    """)
    cur.execute("CREATE INDEX idx_mv_unified_sector ON mv_employers_unified(sector_code);")
    cur.execute("CREATE INDEX idx_mv_unified_union ON mv_employers_unified(union_acronym);")
    cur.execute("CREATE INDEX idx_mv_unified_state ON mv_employers_unified(state);")
    cur.execute("CREATE INDEX idx_mv_unified_name ON mv_employers_unified USING gin(to_tsvector('english', employer_name));")
    print("  [OK] Created mv_employers_unified with indexes")
except Exception as e:
    print(f"  [FAIL] {e}")

conn.close()
print("\nDone!")
