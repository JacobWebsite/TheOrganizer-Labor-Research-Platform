import os
from db_config import get_connection
"""
NLRB Matching - Phase 6: Final Cleanup
======================================
Note: Law firms (Levy Ratner, Kroll Heineman, Norton Brainard) are
attorneys representing unions - they should NOT be matched to unions.
"""

import psycopg2
from psycopg2.extras import RealDictCursor
from datetime import datetime

conn = get_connection()
conn.autocommit = False
cur = conn.cursor(cursor_factory=RealDictCursor)

print("=" * 70)
print("NLRB MATCHING - PHASE 6: FINAL CLEANUP")
print(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
print("=" * 70)

# Pre-match stats
cur.execute("""
    SELECT COUNT(*) as total, COUNT(matched_olms_fnum) as matched
    FROM nlrb_participants
    WHERE participant_type = 'Petitioner' AND participant_subtype = 'Union'
""")
pre = cur.fetchone()
print(f"\nPre-Phase 6: {pre['matched']:,}/{pre['total']:,} ({pre['matched']/pre['total']*100:.1f}%)")

total_updated = 0

# Phase 6: Final patterns for remaining unions
print("\n" + "-" * 70)
print("PHASE 6: Final Pattern Matching")
print("-" * 70)

final_patterns = [
    # Security unions
    (518836, '%security employees union%', 'SEU'),
    (518836, '%security alliance%', 'SAFE'),
    (544348, '%security officers%', 'SEC_OFF'),
    (544348, '%union security guards%', 'USG'),
    
    # Law enforcement
    (411, '%law enforcement%benevolent%', 'LEBA'),
    (411, '%law enforcement officers%', 'LEO'),
    (411, '%special patrolman%', 'SPA'),
    (411, '%command officers%michigan%', 'POAM'),
    (411, '%michigan%police%', 'MIPOLICE'),
    
    # Railroad
    (125, '%train dispatchers%', 'ATDA'),
    
    # NNU variants
    (544309, '%national nurse%organizing%', 'NNOC2'),
    
    # Industrial
    (165, '%amalgamated%industrial%toy%novelty%', 'AITNW'),
    (165, '%amalgamated%industrial%', 'AITU'),
    
    # Construction
    (85, '%construction trades%industrial%', 'CTIE'),
    
    # Local independent
    (137, '%new seasons labor%', 'NSEASONS'),  # SEIU affiliate
    (500001, '%public service employees%572%', 'PSEU572'),
    (500001, '%minnesota public employees%', 'MPEA'),
    
    # Writers
    (10049, '%writers guild%', 'WGA'),
    
    # Puerto Rico
    (63086, '%profesionales%seguridad%', 'PRSS'),
    
    # Longshoremen variants  
    (95, '%hudson county%', 'ILA_HUDSON'),
    
    # Other specific patterns
    (145, '%f.a.i.r.%', 'FAIR'),
    (145, '%fair%', 'FAIR2'),
    (102, '%truck drivers%helpers%', 'TWU2'),
]

for fnum, pattern, name in final_patterns:
    cur.execute(f"""
        UPDATE nlrb_participants
        SET matched_olms_fnum = {fnum},
            match_method = 'pattern6_{name.lower()}',
            match_confidence = 0.75
        WHERE LOWER(participant_name) LIKE '{pattern}'
        AND matched_olms_fnum IS NULL
        AND participant_type = 'Petitioner'
        AND participant_subtype = 'Union'
    """)
    count = cur.rowcount
    if count > 0:
        print(f"  {name:12} (F#{fnum}): {count:4} records")
        total_updated += count

print(f"\n  Phase 6 total: {total_updated:,}")

# Mark law firms as non-union
print("\n" + "-" * 70)
print("IDENTIFYING NON-UNION ENTRIES (Law Firms)")
print("-" * 70)

cur.execute("""
    SELECT participant_name, COUNT(*) as cnt
    FROM nlrb_participants
    WHERE participant_type = 'Petitioner' 
    AND participant_subtype = 'Union'
    AND matched_olms_fnum IS NULL
    AND (LOWER(participant_name) LIKE '%law office%'
        OR LOWER(participant_name) LIKE '%llc%'
        OR LOWER(participant_name) LIKE '%p.c.%'
        OR LOWER(participant_name) LIKE '%ratner%'
        OR LOWER(participant_name) LIKE '%brainard%'
        OR LOWER(participant_name) LIKE '%kroll%'
        OR LOWER(participant_name) LIKE '%mccarthy%')
    GROUP BY participant_name
    ORDER BY cnt DESC
""")
law_firms = cur.fetchall()
law_firm_count = sum(r['cnt'] for r in law_firms)
print(f"  Law firms (should not be matched): {law_firm_count} records")
for r in law_firms[:10]:
    print(f"    - {r['participant_name'][:50]}: {r['cnt']}")

# Final stats
cur.execute("""
    SELECT 
        COUNT(*) as total,
        COUNT(matched_olms_fnum) as matched,
        COUNT(*) FILTER (WHERE participant_name IS NULL) as null_names
    FROM nlrb_participants
    WHERE participant_type = 'Petitioner' AND participant_subtype = 'Union'
""")
post = cur.fetchone()

unmatched_true = post['total'] - post['matched'] - post['null_names'] - law_firm_count
match_rate_adjusted = (post['matched']) / (post['total'] - post['null_names'] - law_firm_count) * 100

print("\n" + "=" * 70)
print("FINAL RESULTS")
print("=" * 70)
print(f"Total union petitioners: {post['total']:,}")
print(f"Matched: {post['matched']:,} ({post['matched']/post['total']*100:.1f}%)")
print(f"Unmatched: {post['total'] - post['matched']:,}")
print(f"\n  Breakdown of unmatched:")
print(f"    NULL names: {post['null_names']:,}")
print(f"    Law firms (correctly excluded): {law_firm_count:,}")
print(f"    Remaining true unions: ~{unmatched_true:,}")
print(f"\n  ADJUSTED MATCH RATE (excluding NULL & law firms): {match_rate_adjusted:.1f}%")

# Commit
conn.commit()
print("\nCHANGES COMMITTED")

conn.close()
