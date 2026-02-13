import os
"""
NLRB Lookup - Additional unions
"""

import psycopg2
from psycopg2.extras import RealDictCursor

conn = psycopg2.connect(
    host='localhost',
    dbname='olms_multiyear',
    user='postgres',
    password=os.environ.get('DB_PASSWORD', '')
)
cur = conn.cursor(cursor_factory=RealDictCursor)

lookups = [
    "RWDSU",
    "Retail Wholesale",
    "New York State Nurses",
    "Washington State Nurses",
    "CGT",
    "Trabajadores",
    "Contract Guards",
    "FCGOA",
    "Superior Officers",
    "SSOBA",
    "EMT",
    "Paramedic",
    "IAEP",
    "National Nurses United",
    "NNU",
    "SMART",
    "IATSE",
    "Theatrical Stage",
    "Trade Unions",
    "IBTU",
]

for term in lookups:
    cur.execute("""
        SELECT f_num, union_name, members
        FROM unions_master 
        WHERE LOWER(union_name) LIKE %s
        ORDER BY members DESC NULLS LAST
        LIMIT 3
    """, (f'%{term.lower()}%',))
    results = cur.fetchall()
    if results:
        print(f"\n{term}:")
        for r in results:
            name = r['union_name'][:45] if r['union_name'] else 'N/A'
            mem = r['members'] if r['members'] else 0
            print(f"  F#{r['f_num']:6} ({mem:>8,} mem) - {name}")
    else:
        print(f"\n{term}: NO RESULTS")

conn.close()
