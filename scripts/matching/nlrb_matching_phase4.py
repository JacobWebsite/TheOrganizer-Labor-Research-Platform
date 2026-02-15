import os
from db_config import get_connection
"""
NLRB Matching - Phase 4: Remaining Crosswalk Affiliations
=========================================================
"""

import psycopg2
from psycopg2.extras import RealDictCursor
from datetime import datetime

conn = get_connection()
conn.autocommit = False
cur = conn.cursor(cursor_factory=RealDictCursor)

print("=" * 70)
print("NLRB MATCHING - PHASE 4: REMAINING AFFILIATIONS")
print(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
print("=" * 70)

# Pre-match stats
cur.execute("""
    SELECT COUNT(*) as total, COUNT(matched_olms_fnum) as matched
    FROM nlrb_participants
    WHERE participant_type = 'Petitioner' AND participant_subtype = 'Union'
""")
pre = cur.fetchone()
print(f"\nPre-Phase 4: {pre['matched']:,}/{pre['total']:,} ({pre['matched']/pre['total']*100:.1f}%)")

# Look up file numbers for remaining affiliations
print("\n" + "-" * 70)
print("LOOKING UP REMAINING AFFILIATION FILE NUMBERS")
print("-" * 70)

affiliations_to_lookup = [
    ('NAGE', '%nage%'),
    ('CJA', '%carpenters%'),
    ('ATU', '%transit union%'),
    ('BSOIW', '%iron workers%'),
    ('GUA', '%graphics%'),
    ('ILA', '%longshoremen%'),
    ('BBF', '%boilermakers%'),
    ('SMART', '%sheet metal%'),
    ('IAFF', '%fire fighters%'),
    ('PAT', '%painters%'),
    ('PPF', '%plumbers%'),
    ('BCTGMI', '%bakery%'),
    ('TWU', '%transport workers%'),
    ('USWU', '%service workers%'),
    ('AGMA', '%musical artists%'),
    ('UWA', '%woodworkers%'),
    ('OPEIU', '%office%professional%'),
    ('BAC', '%bricklayers%'),
    ('APWU', '%postal workers%'),
]

found_fnums = {}
for aff, pattern in affiliations_to_lookup:
    cur.execute("""
        SELECT f_num, union_name, members
        FROM unions_master
        WHERE LOWER(union_name) LIKE %s
        ORDER BY members DESC NULLS LAST
        LIMIT 1
    """, (pattern,))
    result = cur.fetchone()
    if result:
        found_fnums[aff] = result['f_num']
        print(f"  {aff:10} -> F#{result['f_num']:6} ({result['union_name'][:35]})")

# Known international file numbers for these affiliations
AFFILIATION_FNUMS = {
    'NAGE': 90,        # National Association of Government Employees
    'CJA': 85,         # Carpenters
    'ATU': 111,        # Amalgamated Transit Union
    'BSOIW': 63,       # Iron Workers
    'GUA': 145,        # Graphic Communications
    'ILA': 95,         # International Longshoremen's Association
    'BBF': 88,         # Boilermakers
    'SMART': 100,      # Sheet Metal Workers
    'IAFF': 172,       # Fire Fighters
    'PAT': 79,         # Painters
    'PPF': 89,         # Plumbers & Pipe Fitters
    'BCTGMI': 177,     # Bakery Workers
    'TWU': 102,        # Transport Workers
    'AGMA': 10094,     # American Guild of Musical Artists
    'OPEIU': 99,       # Office & Professional Employees
    'BAC': 118,        # Bricklayers
    'APWU': 10164,     # American Postal Workers Union
    'AFGE': 91,        # Federal Employees
    'NEA': 10163,      # National Education Association
    'NALC': 10165,     # Letter Carriers
    'NPWU': 10160,     # NPMHU
}

print("\n" + "-" * 70)
print("PHASE 4: Applying Affiliation Matches")
print("-" * 70)

total_updated = 0
for aff, fnum in AFFILIATION_FNUMS.items():
    cur.execute(f"""
        UPDATE nlrb_participants p
        SET matched_olms_fnum = {fnum},
            match_method = 'crosswalk_aff_{aff.lower()}',
            match_confidence = c.pred_union_score * 0.85
        FROM union_names_crosswalk c
        WHERE LOWER(p.participant_name) = LOWER(c.union_name)
        AND c.pred_aff = '{aff}'
        AND p.matched_olms_fnum IS NULL
        AND p.participant_type = 'Petitioner'
        AND p.participant_subtype = 'Union'
    """)
    count = cur.rowcount
    if count > 0:
        print(f"  {aff:10} (F#{fnum}): {count:4} records")
        total_updated += count

print(f"\n  Total updated in Phase 4: {total_updated:,}")

# Check remaining unmatched
print("\n" + "-" * 70)
print("REMAINING UNMATCHED ANALYSIS")
print("-" * 70)

cur.execute("""
    SELECT participant_name, COUNT(*) as cnt
    FROM nlrb_participants
    WHERE participant_type = 'Petitioner' 
    AND participant_subtype = 'Union'
    AND matched_olms_fnum IS NULL
    GROUP BY participant_name
    ORDER BY cnt DESC
    LIMIT 25
""")
print("\nTop 25 still unmatched:")
for r in cur.fetchall():
    name = r['participant_name'][:55] if r['participant_name'] else 'NULL'
    print(f"  {name:55}: {r['cnt']:4}")

# Check remaining crosswalk affiliations
cur.execute("""
    SELECT c.pred_aff, COUNT(*) as cnt
    FROM nlrb_participants p
    INNER JOIN union_names_crosswalk c ON LOWER(p.participant_name) = LOWER(c.union_name)
    WHERE p.matched_olms_fnum IS NULL
    AND p.participant_type = 'Petitioner'
    AND p.participant_subtype = 'Union'
    AND c.pred_aff IS NOT NULL
    GROUP BY c.pred_aff
    ORDER BY cnt DESC
    LIMIT 15
""")
remaining_affs = cur.fetchall()
if remaining_affs:
    print("\nRemaining unmatched affiliations:")
    for r in remaining_affs:
        print(f"  {r['pred_aff']:15}: {r['cnt']:5}")

# Post-match stats
cur.execute("""
    SELECT 
        COUNT(*) as total,
        COUNT(matched_olms_fnum) as matched
    FROM nlrb_participants
    WHERE participant_type = 'Petitioner' AND participant_subtype = 'Union'
""")
post = cur.fetchone()

print("\n" + "=" * 70)
print("PHASE 4 RESULTS")
print("=" * 70)
print(f"Total union petitioners: {post['total']:,}")
print(f"Now matched: {post['matched']:,} ({post['matched']/post['total']*100:.1f}%)")
print(f"Still unmatched: {post['total'] - post['matched']:,}")
print(f"\nPhase 4 added: {post['matched'] - pre['matched']:,} records")

# Commit
conn.commit()
print("\nCHANGES COMMITTED")

conn.close()
