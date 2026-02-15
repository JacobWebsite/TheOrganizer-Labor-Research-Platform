import os
from db_config import get_connection
"""
NLRB Participant Matching - Phase 3: Extended Pattern Matching
===============================================================
Handles remaining unmatched unions including:
- State nurses associations
- UE (United Electrical Workers)
- Security unions
- SAG-AFTRA
- Other independent unions
"""

import psycopg2
from psycopg2.extras import RealDictCursor
from datetime import datetime

conn = get_connection()
conn.autocommit = False
cur = conn.cursor(cursor_factory=RealDictCursor)

print("=" * 70)
print("NLRB MATCHING - PHASE 3: EXTENDED PATTERN MATCHING")
print(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
print("=" * 70)

# Pre-match stats
cur.execute("""
    SELECT COUNT(*) as total, COUNT(matched_olms_fnum) as matched
    FROM nlrb_participants
    WHERE participant_type = 'Petitioner' AND participant_subtype = 'Union'
""")
pre = cur.fetchone()
print(f"\nPre-Phase 3 status: {pre['matched']:,}/{pre['total']:,} ({pre['matched']/pre['total']*100:.1f}%)")

# First, let's find the file numbers for these unions
print("\n" + "-" * 70)
print("LOOKING UP FILE NUMBERS FOR TARGET UNIONS")
print("-" * 70)

lookups = [
    ("United Electrical", "ue"),
    ("Utility Workers", "uwua"),
    ("Minnesota Nurses", "mna"),
    ("California Nurses", "cna"),
    ("New York State Nurses", "nysna"),
    ("Washington State Nurses", "wsna"),
    ("Michigan Nurses", "mna_mi"),
    ("SAG-AFTRA", "sag"),
    ("Screen Actors Guild", "sag2"),
    ("NATCA", "natca"),
    ("Fraternal Order of Police", "fop"),
    ("RWDSU", "rwdsu"),
    ("Sheet Metal Workers", "smart"),
]

for search_term, key in lookups:
    cur.execute("""
        SELECT f_num, union_name 
        FROM unions_master 
        WHERE LOWER(union_name) LIKE %s
        ORDER BY members DESC NULLS LAST
        LIMIT 3
    """, (f'%{search_term.lower()}%',))
    results = cur.fetchall()
    if results:
        print(f"\n{search_term}:")
        for r in results:
            name = r['union_name'][:50] if r['union_name'] else 'N/A'
            print(f"  F#{r['f_num']:6} - {name}")

conn.close()
