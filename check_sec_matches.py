from db_config import get_connection
from psycopg2.extras import RealDictCursor

conn = get_connection(cursor_factory=RealDictCursor)
cur = conn.cursor()

print("SEC Matching Results:")
print("=" * 60)

# Total matches by band
cur.execute("""
    SELECT
        status,
        confidence_band,
        COUNT(*) as count
    FROM unified_match_log
    WHERE source_system = 'sec'
    GROUP BY status, confidence_band
    ORDER BY status, confidence_band
""")

for row in cur.fetchall():
    print(f"  {row['status']:10} {row['confidence_band']:8} {row['count']:,}")

# Total
cur.execute("""
    SELECT COUNT(*) as count FROM unified_match_log WHERE source_system = 'sec_edgar'
""")
total = cur.fetchone()['count']
print(f"\nTotal SEC matches: {total:,}")

# Check run stats
cur.execute("""
    SELECT run_id, scenario, total_source, total_matched, match_rate, high_count, medium_count, low_count
    FROM match_runs
    WHERE source_system = 'sec'
    ORDER BY started_at DESC
    LIMIT 1
""")
run = cur.fetchone()
if run:
    print(f"\nLatest Run: {run['run_id']}")
    print(f"  Source records: {run['total_source']:,}")
    print(f"  Total matched: {run['total_matched']:,}")
    print(f"  Match rate: {run['match_rate']}%")
    print(f"  HIGH: {run['high_count']:,}")
    print(f"  MEDIUM: {run['medium_count']:,}")
    print(f"  LOW: {run['low_count']:,}")

conn.close()
