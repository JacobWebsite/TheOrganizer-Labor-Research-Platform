import os
"""
NLRB Matching - Phase 5: Final Push
===================================
"""

import psycopg2
from psycopg2.extras import RealDictCursor
from datetime import datetime

conn = psycopg2.connect(
    host='localhost',
    dbname='olms_multiyear',
    user='postgres',
    password='os.environ.get('DB_PASSWORD', '')'
)
conn.autocommit = False
cur = conn.cursor(cursor_factory=RealDictCursor)

print("=" * 70)
print("NLRB MATCHING - PHASE 5: FINAL PUSH")
print(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
print("=" * 70)

# Pre-match stats
cur.execute("""
    SELECT COUNT(*) as total, COUNT(matched_olms_fnum) as matched
    FROM nlrb_participants
    WHERE participant_type = 'Petitioner' AND participant_subtype = 'Union'
""")
pre = cur.fetchone()
print(f"\nPre-Phase 5: {pre['matched']:,}/{pre['total']:,} ({pre['matched']/pre['total']*100:.1f}%)")

total_updated = 0

# Phase 5A: More crosswalk affiliations
print("\n" + "-" * 70)
print("PHASE 5A: Additional Crosswalk Affiliations")
print("-" * 70)

MORE_AFFILIATION_FNUMS = {
    'IUJAT': 165,      # Industrial, Jewelry & Allied Trades
    'USWU': 529203,    # United Service Workers Union
    'UWA': 164,        # Woodworkers (Allied Industrial)
    'PPPWU': 514755,   # Printing Pressmen
    'IBU': 545175,     # Inlandboatmen's Union
    'WGAE': 10049,     # Writers Guild East
    'UNAP': 544309,    # United Nurses -> NNU
    'NFOP': 411,       # National FOP
    'GMP': 195,        # Glass Molders Pottery
    'IUEC': 88,        # Elevator Constructors -> Boilermakers  
    'AGVA': 10108,     # American Guild of Variety Artists
    'PPAN': 544012,    # Plant Protection Association National
    'CLA': 500225,     # California Laborers Alliance
    'SDC': 10097,      # Stage Directors & Choreographers
    'AEA': 10023,      # Actors' Equity Association
    'UTWA': 146,       # Textile Workers
    'GCIU': 145,       # Graphic Communications
    'HERE': 141,       # Hotel Employees
    'SEATU': 137,      # SEIU variant
}

for aff, fnum in MORE_AFFILIATION_FNUMS.items():
    cur.execute(f"""
        UPDATE nlrb_participants p
        SET matched_olms_fnum = {fnum},
            match_method = 'crosswalk_aff5_{aff.lower()}',
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

# Phase 5B: Direct pattern matching for remaining high-frequency names
print("\n" + "-" * 70)
print("PHASE 5B: Direct Pattern Matching")
print("-" * 70)

patterns_phase5 = [
    # Security unions
    (545207, '%national league of justice%security%', 'NLJS'),
    (545207, '%leos-pba%', 'LEOS3'),
    
    # Puerto Rico
    (63086, '%unidad laboral%enfermera%', 'PR_NURSES'),
    (63086, '%ulee%', 'ULEE'),
    
    # Other patterns
    (10163, '%education association%', 'NEA2'),
    (10163, '%mea%education%', 'MEA'),
    (91, '%government employees%', 'AFGE2'),
    (411, '%patrolmen%benevolent%', 'PBA'),
    (411, '%police%association%', 'POLICE'),
    (544012, '%plant protection%', 'PPAN2'),
    (102, '%transport%production%warehouse%', 'TPW'),
    (544309, '%physicians%dentists%', 'UAPD'),
    (10049, '%writers guild%east%', 'WGAE2'),
    (10050, '%writers guild%west%', 'WGAW'),
    (10023, '%actors%equity%', 'AEA2'),
    (172, '%firefighter%', 'IAFF2'),
    (10094, '%guild of musical%', 'AGMA2'),
    (145, '%graphic%communication%', 'GCU'),
]

for fnum, pattern, name in patterns_phase5:
    cur.execute(f"""
        UPDATE nlrb_participants
        SET matched_olms_fnum = {fnum},
            match_method = 'pattern5_{name.lower()}',
            match_confidence = 0.80
        WHERE LOWER(participant_name) LIKE '{pattern}'
        AND matched_olms_fnum IS NULL
        AND participant_type = 'Petitioner'
        AND participant_subtype = 'Union'
    """)
    count = cur.rowcount
    if count > 0:
        print(f"  {name:10} (F#{fnum}): {count:4} records")
        total_updated += count

print(f"\n  Phase 5 total: {total_updated:,}")

# Check what's left
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
    LIMIT 30
""")
print("\nTop 30 still unmatched:")
for r in cur.fetchall():
    name = r['participant_name'][:55] if r['participant_name'] else 'NULL'
    print(f"  {name:55}: {r['cnt']:4}")

# Final stats
cur.execute("""
    SELECT 
        COUNT(*) as total,
        COUNT(matched_olms_fnum) as matched
    FROM nlrb_participants
    WHERE participant_type = 'Petitioner' AND participant_subtype = 'Union'
""")
post = cur.fetchone()

print("\n" + "=" * 70)
print("PHASE 5 RESULTS")
print("=" * 70)
print(f"Total union petitioners: {post['total']:,}")
print(f"Now matched: {post['matched']:,} ({post['matched']/post['total']*100:.1f}%)")
print(f"Still unmatched: {post['total'] - post['matched']:,}")
print(f"\nPhase 5 added: {post['matched'] - pre['matched']:,} records")

# Match method breakdown
cur.execute("""
    SELECT 
        CASE 
            WHEN match_method LIKE 'crosswalk_exact%' THEN 'Crosswalk Exact'
            WHEN match_method LIKE 'crosswalk_aff%' THEN 'Crosswalk Affiliation'
            WHEN match_method LIKE 'pattern%' THEN 'Pattern Match'
            ELSE match_method
        END as method_group,
        COUNT(*) as cnt
    FROM nlrb_participants
    WHERE participant_type = 'Petitioner' 
    AND participant_subtype = 'Union'
    AND matched_olms_fnum IS NOT NULL
    GROUP BY method_group
    ORDER BY cnt DESC
""")
print("\nMatch method summary:")
for r in cur.fetchall():
    print(f"  {r['method_group']:25}: {r['cnt']:6,}")

# Commit
conn.commit()
print("\nCHANGES COMMITTED")

conn.close()
