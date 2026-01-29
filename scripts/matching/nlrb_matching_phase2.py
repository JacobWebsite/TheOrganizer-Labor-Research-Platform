"""
NLRB Participant Matching - Phase 2: Multi-Match Resolution
============================================================
Resolves multi-match crosswalk entries using international parent f_nums
and affiliation-based matching.
"""

import psycopg2
from psycopg2.extras import RealDictCursor
from datetime import datetime

conn = psycopg2.connect(
    host='localhost',
    dbname='olms_multiyear',
    user='postgres',
    password='Juniordog33!'
)
conn.autocommit = False
cur = conn.cursor(cursor_factory=RealDictCursor)

print("=" * 70)
print("NLRB MATCHING - PHASE 2: AFFILIATION-BASED MATCHING")
print(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
print("=" * 70)

# Known international parent file numbers from roadmap
INTERNATIONAL_FNUMS = {
    'SEIU': 137,
    'IBT': 93,       # Teamsters
    'USW': 117,      # Steelworkers
    'UAW': 105,      # Auto Workers
    'UFCW': 76,      # Food & Commercial Workers
    'CWA': 78,       # Communications Workers
    'IBEW': 68,      # Electrical Workers
    'IAM': 107,      # Machinists
    'AFSCME': 92,    # State/County/Municipal
    'AFT': 189,      # Teachers
    'LIUNA': 80,     # Laborers
    'IUOE': 132,     # Operating Engineers
    'UNITE HERE': 141,
    'UNITHE': 141,   # Alias
    'WU': 518899,    # Workers United (SEIU affiliate)
}

# Pre-match stats
cur.execute("""
    SELECT COUNT(*) as total, COUNT(matched_olms_fnum) as matched
    FROM nlrb_participants
    WHERE participant_type = 'Petitioner' AND participant_subtype = 'Union'
""")
pre = cur.fetchone()
print(f"\nPre-Phase 2 status: {pre['matched']:,}/{pre['total']:,} ({pre['matched']/pre['total']*100:.1f}%)")

# Phase 2A: Match by affiliation to international parent
print("\n" + "-" * 70)
print("PHASE 2A: Affiliation-based matching to international parent")
print("-" * 70)

total_updated = 0
for aff, fnum in INTERNATIONAL_FNUMS.items():
    cur.execute(f"""
        UPDATE nlrb_participants p
        SET matched_olms_fnum = {fnum},
            match_method = 'crosswalk_affiliation',
            match_confidence = c.pred_union_score * 0.9
        FROM union_names_crosswalk c
        WHERE LOWER(p.participant_name) = LOWER(c.union_name)
        AND c.pred_aff = '{aff}'
        AND p.matched_olms_fnum IS NULL
        AND p.participant_type = 'Petitioner'
        AND p.participant_subtype = 'Union'
    """)
    count = cur.rowcount
    if count > 0:
        print(f"  {aff:12} (F#{fnum}): {count:5} records")
        total_updated += count

print(f"\n  Total updated in Phase 2A: {total_updated:,}")

# Phase 2B: Pattern-based matching for specific unions
print("\n" + "-" * 70)
print("PHASE 2B: Pattern-based matching for specific unions")
print("-" * 70)

# SPFPA - Security, Police, Fire Professionals
cur.execute("""
    UPDATE nlrb_participants p
    SET matched_olms_fnum = 518836,
        match_method = 'pattern_spfpa',
        match_confidence = 0.85
    FROM union_names_crosswalk c
    WHERE LOWER(p.participant_name) = LOWER(c.union_name)
    AND c.pred_aff = 'SPFPA'
    AND p.matched_olms_fnum IS NULL
    AND p.participant_type = 'Petitioner'
    AND p.participant_subtype = 'Union'
""")
spfpa_count = cur.rowcount
print(f"  SPFPA (F#518836): {spfpa_count:,} records")
total_updated += spfpa_count

# LEOS-PBA
cur.execute("""
    UPDATE nlrb_participants p
    SET matched_olms_fnum = 545207,
        match_method = 'pattern_leos',
        match_confidence = 0.85
    FROM union_names_crosswalk c
    WHERE LOWER(p.participant_name) = LOWER(c.union_name)
    AND c.pred_aff = 'LEOS-PBA'
    AND p.matched_olms_fnum IS NULL
    AND p.participant_type = 'Petitioner'
    AND p.participant_subtype = 'Union'
""")
leos_count = cur.rowcount
print(f"  LEOS-PBA (F#545207): {leos_count:,} records")
total_updated += leos_count

# UGSOA - United Government Security Officers
cur.execute("""
    UPDATE nlrb_participants p
    SET matched_olms_fnum = 544000,
        match_method = 'pattern_ugsoa',
        match_confidence = 0.85
    FROM union_names_crosswalk c
    WHERE LOWER(p.participant_name) = LOWER(c.union_name)
    AND c.pred_aff = 'UGSOA'
    AND p.matched_olms_fnum IS NULL
    AND p.participant_type = 'Petitioner'
    AND p.participant_subtype = 'Union'
""")
ugsoa_count = cur.rowcount
print(f"  UGSOA (F#544000): {ugsoa_count:,} records")
total_updated += ugsoa_count

# Phase 2C: Direct pattern matching without crosswalk
print("\n" + "-" * 70)
print("PHASE 2C: Direct pattern matching (no crosswalk required)")
print("-" * 70)

# NUHW - National Union of Healthcare Workers
cur.execute("""
    UPDATE nlrb_participants
    SET matched_olms_fnum = 545058,
        match_method = 'pattern_nuhw',
        match_confidence = 0.90
    WHERE LOWER(participant_name) LIKE '%nuhw%'
    OR LOWER(participant_name) LIKE '%national union of healthcare workers%'
    AND matched_olms_fnum IS NULL
    AND participant_type = 'Petitioner'
    AND participant_subtype = 'Union'
""")
nuhw_count = cur.rowcount
print(f"  NUHW (F#545058): {nuhw_count:,} records")
total_updated += nuhw_count

# Oregon Nurses Association
cur.execute("""
    UPDATE nlrb_participants
    SET matched_olms_fnum = 537684,
        match_method = 'pattern_ona',
        match_confidence = 0.90
    WHERE LOWER(participant_name) LIKE '%oregon nurses association%'
    AND matched_olms_fnum IS NULL
    AND participant_type = 'Petitioner'
    AND participant_subtype = 'Union'
""")
ona_count = cur.rowcount
print(f"  Oregon Nurses Association (F#537684): {ona_count:,} records")
total_updated += ona_count

# ILWU - International Longshore and Warehouse Union
cur.execute("""
    UPDATE nlrb_participants
    SET matched_olms_fnum = 98,
        match_method = 'pattern_ilwu',
        match_confidence = 0.90
    WHERE (LOWER(participant_name) LIKE '%longshore%warehouse%'
        OR LOWER(participant_name) LIKE '%ilwu%')
    AND matched_olms_fnum IS NULL
    AND participant_type = 'Petitioner'
    AND participant_subtype = 'Union'
""")
ilwu_count = cur.rowcount
print(f"  ILWU (F#98): {ilwu_count:,} records")
total_updated += ilwu_count

# PASNAP - Pennsylvania Staff Nurses
cur.execute("""
    UPDATE nlrb_participants
    SET matched_olms_fnum = 530152,
        match_method = 'pattern_pasnap',
        match_confidence = 0.90
    WHERE LOWER(participant_name) LIKE '%pennsylvania%staff nurses%'
    AND matched_olms_fnum IS NULL
    AND participant_type = 'Petitioner'
    AND participant_subtype = 'Union'
""")
pasnap_count = cur.rowcount
print(f"  PASNAP (F#530152): {pasnap_count:,} records")
total_updated += pasnap_count

# Post-match stats
cur.execute("""
    SELECT 
        COUNT(*) as total,
        COUNT(matched_olms_fnum) as matched,
        COUNT(*) FILTER (WHERE match_method LIKE 'crosswalk%') as crosswalk,
        COUNT(*) FILTER (WHERE match_method LIKE 'pattern%') as pattern
    FROM nlrb_participants
    WHERE participant_type = 'Petitioner' AND participant_subtype = 'Union'
""")
post = cur.fetchone()

print("\n" + "=" * 70)
print("PHASE 2 RESULTS")
print("=" * 70)
print(f"Total union petitioners: {post['total']:,}")
print(f"Now matched: {post['matched']:,}")
print(f"Match rate: {post['matched']/post['total']*100:.1f}%")
print(f"\nBy method category:")
print(f"  Crosswalk-based: {post['crosswalk']:,}")
print(f"  Pattern-based: {post['pattern']:,}")
print(f"\nPhase 2 added: {post['matched'] - pre['matched']:,} records")

# Commit
conn.commit()
print("\n" + "=" * 70)
print("CHANGES COMMITTED")
print("=" * 70)

conn.close()
