import os
import psycopg2
conn = psycopg2.connect(host='localhost', dbname='olms_multiyear', user='postgres', password='os.environ.get('DB_PASSWORD', '')')
cur = conn.cursor()

# Cancel the long-running query
cur.execute("""
    SELECT pg_cancel_backend(pid)
    FROM pg_stat_activity
    WHERE datname='olms_multiyear' AND state != 'idle' AND pid != pg_backend_pid()
      AND query LIKE '%whd_state_agg%'
""")
cancelled = cur.fetchall()
print(f"Cancelled {len(cancelled)} queries")

# Check current state - what already committed?
# Steps 1-3 + Tier 1 F7 should be committed, Tier 2 F7 was rolled back

# MV exists?
cur.execute("SELECT COUNT(*) FROM mv_whd_employer_agg")
print(f"MV rows: {cur.fetchone()[0]:,}")

# F7 WHD columns?
cur.execute("SELECT COUNT(*) FROM f7_employers_deduped WHERE whd_violation_count IS NOT NULL")
print(f"F7 with WHD data: {cur.fetchone()[0]:,}")

# Mergent WHD columns?
cur.execute("SELECT COUNT(*) FROM mergent_employers WHERE whd_violation_count IS NOT NULL")
print(f"Mergent with WHD data: {cur.fetchone()[0]:,}")

conn.close()
