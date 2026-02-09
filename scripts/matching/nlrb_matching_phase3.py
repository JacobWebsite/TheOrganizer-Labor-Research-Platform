import os
"""
NLRB Participant Matching - Phase 3: Extended Pattern Matching
===============================================================
Handles remaining unmatched unions including:
- UE (United Electrical Workers) - F#58
- State nurses associations
- Security unions
- SAG-AFTRA
- Other independent unions
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
print(f"\nPre-Phase 3: {pre['matched']:,}/{pre['total']:,} ({pre['matched']/pre['total']*100:.1f}%)")

total_updated = 0

# Phase 3A: UE - United Electrical Workers (F#58)
print("\n" + "-" * 70)
print("PHASE 3A: UE - United Electrical Workers")
print("-" * 70)

cur.execute("""
    UPDATE nlrb_participants
    SET matched_olms_fnum = 58,
        match_method = 'pattern_ue',
        match_confidence = 0.90
    WHERE (LOWER(participant_name) LIKE '%united electrical%radio%machine%'
        OR LOWER(participant_name) LIKE '% ue,%'
        OR LOWER(participant_name) LIKE '%(ue)%'
        OR LOWER(participant_name) LIKE 'ue local%'
        OR LOWER(participant_name) LIKE 'ue -%')
    AND matched_olms_fnum IS NULL
    AND participant_type = 'Petitioner'
    AND participant_subtype = 'Union'
""")
ue_count = cur.rowcount
print(f"  UE (F#58): {ue_count:,} records")
total_updated += ue_count

# Also match via crosswalk UE affiliation
cur.execute("""
    UPDATE nlrb_participants p
    SET matched_olms_fnum = 58,
        match_method = 'crosswalk_ue',
        match_confidence = c.pred_union_score * 0.9
    FROM union_names_crosswalk c
    WHERE LOWER(p.participant_name) = LOWER(c.union_name)
    AND c.pred_aff = 'UE'
    AND p.matched_olms_fnum IS NULL
    AND p.participant_type = 'Petitioner'
    AND p.participant_subtype = 'Union'
""")
ue_xwalk = cur.rowcount
print(f"  UE via crosswalk: {ue_xwalk:,} records")
total_updated += ue_xwalk

# Phase 3B: Utility Workers (F#39)
print("\n" + "-" * 70)
print("PHASE 3B: UWUA - Utility Workers Union of America")
print("-" * 70)

cur.execute("""
    UPDATE nlrb_participants
    SET matched_olms_fnum = 39,
        match_method = 'pattern_uwua',
        match_confidence = 0.90
    WHERE (LOWER(participant_name) LIKE '%utility workers%'
        OR LOWER(participant_name) LIKE '%uwua%')
    AND matched_olms_fnum IS NULL
    AND participant_type = 'Petitioner'
    AND participant_subtype = 'Union'
""")
uwua_count = cur.rowcount
print(f"  UWUA (F#39): {uwua_count:,} records")
total_updated += uwua_count

# Phase 3C: State Nurses Associations
print("\n" + "-" * 70)
print("PHASE 3C: State Nurses Associations")
print("-" * 70)

nurses_patterns = [
    (15724, '%california nurses association%', 'CNA'),
    (530315, '%minnesota nurses association%', 'MNA'),
    (67961, '%michigan nurses association%', 'MNA-MI'),
    (544309, '%national nurses united%', 'NNU'),
    (544309, '%national nurses organizing%', 'NNOC'),
    (544309, '% nnu%', 'NNU2'),
]

for fnum, pattern, name in nurses_patterns:
    cur.execute(f"""
        UPDATE nlrb_participants
        SET matched_olms_fnum = {fnum},
            match_method = 'pattern_nurses_{name.lower()}',
            match_confidence = 0.90
        WHERE LOWER(participant_name) LIKE '{pattern}'
        AND matched_olms_fnum IS NULL
        AND participant_type = 'Petitioner'
        AND participant_subtype = 'Union'
    """)
    count = cur.rowcount
    if count > 0:
        print(f"  {name} (F#{fnum}): {count:,} records")
        total_updated += count

# Generic state nurses association pattern -> NNU
cur.execute("""
    UPDATE nlrb_participants
    SET matched_olms_fnum = 544309,
        match_method = 'pattern_state_nurses',
        match_confidence = 0.85
    WHERE (LOWER(participant_name) LIKE '%state nurses association%'
        OR LOWER(participant_name) LIKE '%nurses association%')
    AND matched_olms_fnum IS NULL
    AND participant_type = 'Petitioner'
    AND participant_subtype = 'Union'
""")
nurses_generic = cur.rowcount
print(f"  Generic State Nurses -> NNU (F#544309): {nurses_generic:,} records")
total_updated += nurses_generic

# Phase 3D: SAG-AFTRA (F#391)
print("\n" + "-" * 70)
print("PHASE 3D: SAG-AFTRA")
print("-" * 70)

cur.execute("""
    UPDATE nlrb_participants
    SET matched_olms_fnum = 391,
        match_method = 'pattern_sagaftra',
        match_confidence = 0.95
    WHERE (LOWER(participant_name) LIKE '%sag-aftra%'
        OR LOWER(participant_name) LIKE '%screen actors guild%'
        OR LOWER(participant_name) LIKE '%sag %'
        OR LOWER(participant_name) LIKE '%aftra%')
    AND matched_olms_fnum IS NULL
    AND participant_type = 'Petitioner'
    AND participant_subtype = 'Union'
""")
sag_count = cur.rowcount
print(f"  SAG-AFTRA (F#391): {sag_count:,} records")
total_updated += sag_count

# Phase 3E: Security/Police Unions
print("\n" + "-" * 70)
print("PHASE 3E: Security and Police Unions")
print("-" * 70)

security_patterns = [
    (544348, '%federal contract guards%', 'FCGOA'),
    (544348, '%fcgoa%', 'FCGOA2'),
    (69855, '%special and superior officers%', 'SSOBA'),
    (69855, '%ssoba%', 'SSOBA2'),
    (411, '%fraternal order of police%', 'FOP'),
    (411, '% fop%', 'FOP2'),
]

for fnum, pattern, name in security_patterns:
    cur.execute(f"""
        UPDATE nlrb_participants
        SET matched_olms_fnum = {fnum},
            match_method = 'pattern_security_{name.lower()}',
            match_confidence = 0.90
        WHERE LOWER(participant_name) LIKE '{pattern}'
        AND matched_olms_fnum IS NULL
        AND participant_type = 'Petitioner'
        AND participant_subtype = 'Union'
    """)
    count = cur.rowcount
    if count > 0:
        print(f"  {name} (F#{fnum}): {count:,} records")
        total_updated += count

# Phase 3F: Other Unions
print("\n" + "-" * 70)
print("PHASE 3F: Other Specific Unions")
print("-" * 70)

other_patterns = [
    (71, '%rwdsu%', 'RWDSU'),
    (71, '%retail%wholesale%department%', 'RWDSU2'),
    (546370, '%central general de trabajadores%', 'CGT'),
    (63086, '%union general de trabajadores%', 'UGT'),
    (542424, '%natca%', 'NATCA'),
    (542424, '%air traffic controllers%', 'NATCA2'),
    (545867, '%international brotherhood of trade unions%', 'IBTU'),
    (165, '%iujat%', 'IUJAT'),
    (10052, '%iatse%', 'IATSE'),
    (10052, '%theatrical stage%', 'IATSE2'),
    (10052, '%international alliance of theatrical%', 'IATSE3'),
    (100, '%sheet metal%air%rail%', 'SMART'),
    (100, '%(smart)%', 'SMART2'),
]

for fnum, pattern, name in other_patterns:
    cur.execute(f"""
        UPDATE nlrb_participants
        SET matched_olms_fnum = {fnum},
            match_method = 'pattern_{name.lower()}',
            match_confidence = 0.85
        WHERE LOWER(participant_name) LIKE '{pattern}'
        AND matched_olms_fnum IS NULL
        AND participant_type = 'Petitioner'
        AND participant_subtype = 'Union'
    """)
    count = cur.rowcount
    if count > 0:
        print(f"  {name} (F#{fnum}): {count:,} records")
        total_updated += count

# Phase 3G: Match remaining crosswalk affiliations
print("\n" + "-" * 70)
print("PHASE 3G: Remaining Crosswalk Affiliations")
print("-" * 70)

# Get remaining unmatched with crosswalk affiliations
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
    LIMIT 20
""")
print("\nRemaining affiliations in crosswalk (top 20):")
for r in cur.fetchall():
    print(f"  {r['pred_aff']:15}: {r['cnt']:5} records")

# Post-match stats
cur.execute("""
    SELECT 
        COUNT(*) as total,
        COUNT(matched_olms_fnum) as matched,
        COUNT(*) - COUNT(matched_olms_fnum) as unmatched
    FROM nlrb_participants
    WHERE participant_type = 'Petitioner' AND participant_subtype = 'Union'
""")
post = cur.fetchone()

print("\n" + "=" * 70)
print("PHASE 3 RESULTS")
print("=" * 70)
print(f"Total union petitioners: {post['total']:,}")
print(f"Now matched: {post['matched']:,} ({post['matched']/post['total']*100:.1f}%)")
print(f"Still unmatched: {post['unmatched']:,} ({post['unmatched']/post['total']*100:.1f}%)")
print(f"\nPhase 3 added: {post['matched'] - pre['matched']:,} records")

# Commit
conn.commit()
print("\nCHANGES COMMITTED")

conn.close()
