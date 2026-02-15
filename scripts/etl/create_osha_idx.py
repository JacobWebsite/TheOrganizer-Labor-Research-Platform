import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
from db_config import get_connection

conn = get_connection()
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
