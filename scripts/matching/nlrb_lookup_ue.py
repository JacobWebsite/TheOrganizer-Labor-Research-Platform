import os
"""
NLRB Lookup - UE specifically
"""

import psycopg2
from psycopg2.extras import RealDictCursor

conn = psycopg2.connect(
    host='localhost',
    dbname='olms_multiyear',
    user='postgres',
    password='os.environ.get('DB_PASSWORD', '')'
)
cur = conn.cursor(cursor_factory=RealDictCursor)

# Look for UE - United Electrical, Radio and Machine Workers
cur.execute("""
    SELECT f_num, union_name, members
    FROM unions_master 
    WHERE (LOWER(union_name) LIKE '%electrical%radio%machine%'
       OR LOWER(union_name) LIKE '%ue %'
       OR LOWER(union_name) LIKE '% ue'
       OR union_name LIKE 'UE %')
    ORDER BY members DESC NULLS LAST
    LIMIT 10
""")
print("UE - United Electrical, Radio and Machine Workers:")
for r in cur.fetchall():
    name = r['union_name'][:55] if r['union_name'] else 'N/A'
    mem = r['members'] if r['members'] else 0
    print(f"  F#{r['f_num']:6} ({mem:>8,} mem) - {name}")

# Also check the crosswalk for UE
cur.execute("""
    SELECT union_name, pred_fnum, pred_aff
    FROM union_names_crosswalk
    WHERE pred_aff = 'UE'
    LIMIT 10
""")
print("\nCrosswalk entries with pred_aff='UE':")
for r in cur.fetchall():
    print(f"  {r['union_name'][:50]} -> F#{r['pred_fnum']} ({r['pred_aff']})")

# Look for the international
cur.execute("""
    SELECT f_num, union_name, members
    FROM unions_master 
    WHERE LOWER(union_name) LIKE '%united electrical%'
    ORDER BY members DESC NULLS LAST
    LIMIT 5
""")
print("\nUnited Electrical unions:")
for r in cur.fetchall():
    name = r['union_name'][:55] if r['union_name'] else 'N/A'
    mem = r['members'] if r['members'] else 0
    print(f"  F#{r['f_num']:6} ({mem:>8,} mem) - {name}")

conn.close()
