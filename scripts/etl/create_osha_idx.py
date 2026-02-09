import os
import psycopg2

conn = psycopg2.connect(
    host="localhost",
    dbname="olms_multiyear",
    user="postgres",
    password="os.environ.get('DB_PASSWORD', '')",
)
cur = conn.cursor()

print("Creating btree index on LOWER(estab_name_normalized) ...", flush=True)
cur.execute("""
    CREATE INDEX IF NOT EXISTS idx_osha_est_name_norm_lower
    ON osha_establishments (LOWER(estab_name_normalized))
""")
conn.commit()
print("Done.", flush=True)

print("Creating composite index on LOWER(estab_name_normalized), site_state ...", flush=True)
cur.execute("""
    CREATE INDEX IF NOT EXISTS idx_osha_est_name_norm_state
    ON osha_establishments (LOWER(estab_name_normalized), UPPER(site_state))
""")
conn.commit()
print("Done.", flush=True)

cur.close()
conn.close()
