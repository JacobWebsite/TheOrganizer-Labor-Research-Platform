import os
import psycopg2
conn = psycopg2.connect(host='localhost', dbname='olms_multiyear', user='postgres', password=os.environ.get('DB_PASSWORD', ''))
cur = conn.cursor()

# Check what whd_match_method values exist on mergent
cur.execute("""
    SELECT whd_match_method, COUNT(*)
    FROM mergent_employers
    WHERE whd_violation_count IS NOT NULL
    GROUP BY whd_match_method
""")
print("Mergent WHD match methods:")
for r in cur.fetchall():
    print(f"  {r[0]}: {r[1]:,}")

# F7 Tier 1 count already committed
cur.execute("SELECT COUNT(*) FROM f7_employers_deduped WHERE whd_violation_count IS NOT NULL")
print(f"\nF7 with WHD data (Tier 1 only): {cur.fetchone()[0]:,}")

# Check if any active queries still
cur.execute("""
    SELECT COUNT(*) FROM pg_stat_activity
    WHERE datname='olms_multiyear' AND state != 'idle' AND pid != pg_backend_pid()
""")
print(f"Active queries: {cur.fetchone()[0]}")

conn.close()
